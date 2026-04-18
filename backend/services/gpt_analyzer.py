"""
P.R.I.S.M. — GPT Style Reasoning Layer
Uses GPT-4o-mini to explain stylometric differences in natural language.
Only runs on boundaries flagged by HDBSCAN to save costs and latency.

Edge-case handling:
  - Missing API key → returns structured "unavailable" result
  - Timeout on individual calls → partial results with warning
  - Rate limiting → exponential backoff via asyncio
  - Total batch timeout → returns whatever completed so far
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from prompts.style_profile import STYLE_PROFILE_PROMPT
from prompts.style_compare import COMPARE_PROMPT
from models import PipelineContext, WarningCode, WarningSeverity

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────
GPT_CALL_TIMEOUT = 30          # Seconds per individual GPT call
GPT_BATCH_TIMEOUT = 120        # Seconds for the entire batch of GPT calls
MAX_ANOMALY_PROFILES = 3      # Cap parallel profile requests
MAX_RETRIES = 2                # Retries per GPT call on transient errors


class GPTAnalyzer:
    """
    AI layer that adds explainability to the deterministic mathematical clusters.
    Handles API key missing, per-call timeouts, and partial result delivery.
    """

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None
        self._semaphore = asyncio.Semaphore(4)

    def _get_client(self) -> Optional[AsyncOpenAI]:
        """Lazy initialization of the OpenAI client."""
        if not self._client:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key or api_key.startswith("sk-your"):
                logger.warning("[P.R.I.S.M.] OPENAI_API_KEY not found or using dummy key. GPT Reasoning will run in degraded mode.")
                return None
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def _safe_gpt_call(self, coro, label: str) -> tuple:
        """
        Wrap a GPT coroutine with timeout + retry logic.
        Uses a semaphore to throttle concurrent OpenAI API calls.
        Returns (result, error_string_or_None).
        """
        async with self._semaphore:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    result = await asyncio.wait_for(coro(), timeout=GPT_CALL_TIMEOUT)
                    return result, None
                except asyncio.TimeoutError:
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    logger.warning(f"[P.R.I.S.M.] GPT call timed out after {GPT_CALL_TIMEOUT}s: {label}")
                    return None, f"Timed out after {GPT_CALL_TIMEOUT}s"
                except Exception as e:
                    error_msg = str(e)
                    # Detect rate limiting
                    if "rate_limit" in error_msg.lower() or "429" in error_msg:
                        if attempt < MAX_RETRIES:
                            wait_time = 2 ** (attempt + 1)
                            logger.warning(f"[P.R.I.S.M.] Rate limited, retrying in {wait_time}s: {label}")
                            await asyncio.sleep(wait_time)
                            continue
                        return None, f"Rate limited after {MAX_RETRIES + 1} attempts"
                    logger.error(f"[P.R.I.S.M.] GPT call failed ({label}): {e}")
                    return None, f"API error: {error_msg[:100]}"

    async def generate_style_profile(self, text: str) -> str:
        client = self._get_client()
        if not client:
            return "AI reasoning unavailable: Missing API Key"

        async def _call():
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": STYLE_PROFILE_PROMPT.format(paragraph_text=text)}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=200
            )
            data = json.loads(response.choices[0].message.content)
            return data.get("style_profile", "Could not generate profile.")

        result, error = await self._safe_gpt_call(_call, "style_profile")
        if error:
            return f"AI reasoning unavailable: {error}"
        return result

    async def explain_boundary(self, para_a: str, para_b: str) -> str:
        client = self._get_client()
        if not client:
            return "AI reasoning unavailable: Missing API Key"

        async def _call():
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": COMPARE_PROMPT.format(para_A=para_a, para_B=para_b)}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=250
            )
            data = json.loads(response.choices[0].message.content)
            return data.get("explanation", "Could not explain boundary.")

        result, error = await self._safe_gpt_call(_call, "boundary_explanation")
        if error:
            return f"AI reasoning unavailable: {error}"
        return result

    async def analyze_boundaries(
        self,
        paragraphs: List[Dict[str, Any]],
        cluster_result: Dict[str, Any],
        ctx: Optional[PipelineContext] = None,
    ) -> Dict[str, Any]:
        """
        Analyze the boundaries and flagged anomalies with GPT-4o-mini.
        This provides natural language reasoning for the math engine's output.

        Edge cases handled:
          - Missing API key → returns unavailable result
          - Individual call timeouts → fills partial results
          - Batch timeout → returns whatever completed
          - Rate limiting → exponential backoff per call
        """
        if ctx is None:
            ctx = PipelineContext()

        if not self._get_client():
            ctx.add_warning(
                WarningCode.GPT_UNAVAILABLE, WarningSeverity.WARNING, "gpt_analyzer",
                "OpenAI API key not configured. AI-powered style reasoning is disabled. "
                "Mathematical analysis (spaCy + HDBSCAN) results are still available.",
            )
            return {
                "available": False,
                "error": "OPENAI_API_KEY missing",
                "boundary_explanations": {},
                "anomaly_profiles": {}
            }

        # Skip if upstream signaled
        if ctx.skip_gpt:
            ctx.add_warning(
                WarningCode.GPT_UNAVAILABLE, WarningSeverity.INFO, "gpt_analyzer",
                "GPT reasoning skipped (upstream signal).",
            )
            return {
                "available": False,
                "error": "Skipped by pipeline",
                "boundary_explanations": {},
                "anomaly_profiles": {}
            }

        boundaries = cluster_result.get("boundaries", [])
        anomaly_indices = cluster_result.get("anomaly_indices", [])

        # ── Boundary explanations ────────────────────────────────────────────
        boundary_tasks = []
        boundary_info = []

        valid_boundaries = [b for b in boundaries if b.get("is_anomaly_transition")][:3]
        for boundary in valid_boundaries:
            pa_idx = boundary["after_paragraph"]
            pb_idx = pa_idx + 1
            if pb_idx < len(paragraphs):
                para_a = paragraphs[pa_idx].get("text", "")
                para_b = paragraphs[pb_idx].get("text", "")
                boundary_tasks.append(self.explain_boundary(para_a, para_b))
                boundary_info.append(f"{pa_idx}_to_{pb_idx}")

        # ── Anomaly profile tasks ────────────────────────────────────────────
        profile_tasks = []
        profile_indices = []
        for idx in anomaly_indices[:MAX_ANOMALY_PROFILES]:
            para_text = paragraphs[idx].get("text", "")
            profile_tasks.append(self.generate_style_profile(para_text))
            profile_indices.append(str(idx))

        # ── Execute all with batch timeout ───────────────────────────────────
        all_tasks = boundary_tasks + profile_tasks
        timeout_occurred = False
        failed_count = 0

        if all_tasks:
            try:
                all_results = await asyncio.wait_for(
                    asyncio.gather(*all_tasks, return_exceptions=True),
                    timeout=GPT_BATCH_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[P.R.I.S.M.] GPT batch timed out after {GPT_BATCH_TIMEOUT}s. "
                    f"Returning partial results."
                )
                timeout_occurred = True
                # Fill remaining with timeout messages
                completed = len(boundary_tasks) + len(profile_tasks)
                all_results = [
                    f"AI reasoning timed out (batch limit: {GPT_BATCH_TIMEOUT}s)"
                ] * completed
        else:
            all_results = []

        # ── Split results back ───────────────────────────────────────────────
        boundary_results = all_results[:len(boundary_info)]
        profile_results = all_results[len(boundary_info):]

        explanations = {}
        for key, res in zip(boundary_info, boundary_results):
            if isinstance(res, Exception):
                explanations[key] = f"AI reasoning failed: {res}"
                failed_count += 1
            else:
                explanations[key] = res

        profiles = {}
        for idx_str, res in zip(profile_indices, profile_results):
            if isinstance(res, Exception):
                profiles[idx_str] = f"AI reasoning failed: {res}"
                failed_count += 1
            else:
                profiles[idx_str] = res

        # ── Record warnings for partial/failed results ───────────────────────
        if timeout_occurred:
            ctx.add_warning(
                WarningCode.GPT_TIMEOUT, WarningSeverity.WARNING, "gpt_analyzer",
                f"GPT reasoning batch timed out after {GPT_BATCH_TIMEOUT}s. "
                f"Some explanations may be missing or incomplete.",
                {"batch_timeout_seconds": GPT_BATCH_TIMEOUT},
            )
            ctx.partial_results = True

        if failed_count > 0:
            total_tasks = len(boundary_info) + len(profile_indices)
            ctx.add_warning(
                WarningCode.GPT_PARTIAL_RESULTS, WarningSeverity.WARNING, "gpt_analyzer",
                f"{failed_count} of {total_tasks} GPT reasoning calls failed. "
                f"Partial AI explanations are available.",
                {"failed": failed_count, "total": total_tasks},
            )
            ctx.partial_results = True

        logger.info(
            f"[P.R.I.S.M.] GPT reasoning complete. Generated {len(explanations)} boundary explanations "
            f"and {len(profiles)} anomaly profiles. "
            f"(failures: {failed_count}, timeout: {timeout_occurred})"
        )

        return {
            "available": True,
            "partial": timeout_occurred or failed_count > 0,
            "boundary_explanations": explanations,
            "anomaly_profiles": profiles
        }
