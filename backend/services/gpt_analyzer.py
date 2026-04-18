"""
P.R.I.S.M. — GPT Style Reasoning Layer
Uses GPT-4o-mini to explain stylometric differences in natural language.
Only runs on boundaries flagged by HDBSCAN to save costs and latency.
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from prompts.style_profile import STYLE_PROFILE_PROMPT
from prompts.style_compare import COMPARE_PROMPT

logger = logging.getLogger(__name__)

class GPTAnalyzer:
    """
    AI layer that adds explainability to the deterministic mathematical clusters.
    """
    
    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> Optional[AsyncOpenAI]:
        """Lazy initialization of the OpenAI client."""
        if not self._client:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("[P.R.I.S.M.] OPENAI_API_KEY not found. GPT Reasoning will run in degraded mode.")
                return None
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def generate_style_profile(self, text: str) -> str:
        client = self._get_client()
        if not client:
            return "AI reasoning unavailable: Missing API Key"

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": STYLE_PROFILE_PROMPT.format(paragraph_text=text)}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=200
            )
            data = json.loads(response.choices[0].message.content)
            return data.get("style_profile", "Could not generate profile.")
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Style profiling failed: {e}")
            return "AI reasoning unavailable: API Error"

    async def explain_boundary(self, para_a: str, para_b: str) -> str:
        client = self._get_client()
        if not client:
            return "AI reasoning unavailable: Missing API Key"

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": COMPARE_PROMPT.format(para_A=para_a, para_B=para_b)}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=250
            )
            data = json.loads(response.choices[0].message.content)
            return data.get("explanation", "Could not explain boundary.")
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Boundary explanation failed: {e}")
            return "AI reasoning unavailable: API Error"

    async def analyze_boundaries(self, paragraphs: List[Dict[str, Any]], cluster_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the boundaries and flagged anomalies with GPT-4o-mini.
        This provides natural language reasoning for the math engine's output.
        """
        if not self._get_client():
            return {
                "available": False,
                "error": "OPENAI_API_KEY missing",
                "boundary_explanations": {},
                "anomaly_profiles": {}
            }

        boundaries = cluster_result.get("boundaries", [])
        anomaly_indices = cluster_result.get("anomaly_indices", [])
        
        boundary_tasks = []
        boundary_info = []

        # 1. Explain anomaly boundaries
        for boundary in boundaries:
            if boundary.get("is_anomaly_transition"):
                pa_idx = boundary["after_paragraph"]
                pb_idx = pa_idx + 1
                if pb_idx < len(paragraphs):
                    para_a = paragraphs[pa_idx].get("text", "")
                    para_b = paragraphs[pb_idx].get("text", "")
                    boundary_tasks.append(self.explain_boundary(para_a, para_b))
                    boundary_info.append(f"{pa_idx}_to_{pb_idx}")

        boundary_results = await asyncio.gather(*boundary_tasks, return_exceptions=True)
        
        explanations = {}
        for key, res in zip(boundary_info, boundary_results):
            if isinstance(res, Exception):
                explanations[key] = f"AI reasoning failed: {res}"
            else:
                explanations[key] = res

        # 2. Profile individual anomalies (to avoid huge parallel loads, maybe cap at 10)
        profile_tasks = []
        profile_indices = []
        for idx in anomaly_indices[:10]:  # Limit to 10 anomalies for speed
            para_text = paragraphs[idx].get("text", "")
            profile_tasks.append(self.generate_style_profile(para_text))
            profile_indices.append(str(idx))
            
        profile_results = await asyncio.gather(*profile_tasks, return_exceptions=True)
        
        profiles = {}
        for idx_str, res in zip(profile_indices, profile_results):
            if isinstance(res, Exception):
                profiles[idx_str] = f"AI reasoning failed: {res}"
            else:
                profiles[idx_str] = res
                
        logger.info(
            f"[P.R.I.S.M.] GPT reasoning complete. Generated {len(explanations)} boundary explanations "
            f"and {len(profiles)} anomaly profiles."
        )

        return {
            "available": True,
            "boundary_explanations": explanations,
            "anomaly_profiles": profiles
        }
