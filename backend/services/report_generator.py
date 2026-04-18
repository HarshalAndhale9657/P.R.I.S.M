"""
P.R.I.S.M. — Forensic Report Generator
Takes all evidence from the pipeline (clustering, reasoning, citations, sources)
and uses GPT-4o to synthesize a structured, prosecutable JSON report.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from openai import AsyncOpenAI

from prompts.report_synthesis import REPORT_SYNTHESIS_PROMPT

logger = logging.getLogger(__name__)

class ReportGenerator:
    """
    Final synthesis layer. Unlike GPTAnalyzer (which uses 4o-mini for speed and cost),
    this uses the full GPT-4o model to weigh multiple streams of evidence and 
    produce a final verdict and integrity score.
    """
    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> Optional[AsyncOpenAI]:
        """Lazy initialization of the OpenAI client."""
        if not self._client:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("[P.R.I.S.M.] OPENAI_API_KEY not found. Falling back to rule-based report generation.")
                return None
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def generate_report(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize all pipeline evidence into a final structured report.
        """
        client = self._get_client()
        if not client:
            return self._fallback_report(analysis_data)
        
        # Serialize the data down to relevant bits to save context window tokens
        clusters = analysis_data.get("clustering", {})
        reasoning = analysis_data.get("reasoning", {})
        citations = analysis_data.get("citations", {})
        sources = analysis_data.get("sources", [])
        
        doc_data = {
            "clustering": {
                "estimated_authors": clusters.get("estimated_authors", 1),
                "anomaly_count": clusters.get("anomaly_count", 0),
                "noise_percentage": clusters.get("noise_percentage", 0.0),
                "boundary_count": clusters.get("boundary_count", 0),
                "confidence": clusters.get("confidence", 1.0),
                "noise_override": clusters.get("noise_override", False),
                "too_short": clusters.get("too_short", False),
            },
            "reasoning": reasoning.get("boundary_explanations", {}) if isinstance(reasoning, dict) else {},
            "anomaly_profiles": reasoning.get("anomaly_profiles", {}) if isinstance(reasoning, dict) else {},
            "citations": {
                "total_found": citations.get("total_citations_found", 0) if isinstance(citations, dict) else 0,
                "temporal_anomalies": citations.get("temporal_anomalies", []) if isinstance(citations, dict) else [],
                "temporal_anomaly_count": citations.get("temporal_anomaly_count", 0) if isinstance(citations, dict) else 0,
            },
            "sources": []
        }
        
        # Extract source matches — sources is a list, not a dict
        if isinstance(sources, list) and sources:
            doc_data["sources"] = [
                {
                    "title": s.get("source", {}).get("title", "Unknown"),
                    "similarity": s.get("similarity_score", 0),
                    "year": s.get("source", {}).get("year"),
                    "paragraph_id": s.get("paragraph_id"),
                }
                for s in sources
            ]

        try:
            response = await client.chat.completions.create(
                model="gpt-4o",  # 4o for superior synthesis capabilities
                messages=[{"role": "user", "content": REPORT_SYNTHESIS_PROMPT.format(document_data=json.dumps(doc_data))}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=800
            )
            report_data = json.loads(response.choices[0].message.content)
            logger.info(f"[P.R.I.S.M.] Generated final report. Verdict: {report_data.get('verdict')} | Score: {report_data.get('integrity_score')}")
            return report_data
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Report synthesis failed via GPT-4o: {e}. Executing fallback rule-engine.")
            return self._fallback_report(analysis_data, error=str(e))

    def _fallback_report(self, data: Dict[str, Any], error: str = "Missing API Key") -> Dict[str, Any]:
        """
        Generate a rule-based report if GPT-4o fails or is unavailable.
        Uses actual pipeline evidence to compute a meaningful score.
        """
        clustering = data.get("clustering", {})
        reasoning = data.get("reasoning", {})
        citations = data.get("citations", {})
        
        # Sources is a LIST, not a dict
        source_matches = data.get("sources", [])
        if not isinstance(source_matches, list):
            source_matches = []
        
        # Citation anomalies — handle both nested and flat
        citation_anomalies = []
        if isinstance(citations, dict):
            citation_anomalies = citations.get("temporal_anomalies", [])
        
        noise = clustering.get("noise_percentage", 0.0)
        anomaly_count = clustering.get("anomaly_count", 0)
        estimated_authors = clustering.get("estimated_authors", 1)
        boundary_count = clustering.get("boundary_count", 0)
        noise_override = clustering.get("noise_override", False)
        too_short = clustering.get("too_short", False)
        
        # ── Compute integrity score from multiple evidence streams ──
        score = 10.0
        
        # 1. Noise-based penalty (HDBSCAN noise = stylistic anomalies)
        if noise > 0:
            score -= noise * 8.0  # e.g., 30% noise = -2.4 points
        
        # 2. Multiple authors penalty
        if estimated_authors > 1:
            score -= (estimated_authors - 1) * 1.5  # Each extra author = -1.5
        
        # 3. Anomaly count penalty
        if anomaly_count > 0:
            score -= min(anomaly_count * 0.5, 3.0)  # Cap at -3
        
        # 4. Boundary transitions penalty
        if boundary_count > 2:
            score -= min((boundary_count - 2) * 0.3, 1.5)
        
        # 5. Citation temporal anomalies penalty
        if citation_anomalies:
            high_severity = sum(1 for a in citation_anomalies if a.get("severity") == "high")
            medium_severity = sum(1 for a in citation_anomalies if a.get("severity") == "medium")
            score -= high_severity * 1.5
            score -= medium_severity * 0.8
            score -= len(citation_anomalies) * 0.3  # Base penalty per anomaly
        
        # 6. Source match penalties (strongest evidence)
        if source_matches:
            for match in source_matches:
                sim = match.get("similarity_score", 0)
                if sim >= 0.9:
                    score -= 3.0  # Very high similarity = major penalty
                elif sim >= 0.8:
                    score -= 2.0
                elif sim >= 0.75:
                    score -= 1.5
        
        # 7. GPT reasoning evidence (if available)
        if isinstance(reasoning, dict) and reasoning.get("available"):
            boundary_explanations = reasoning.get("boundary_explanations", {})
            anomaly_profiles = reasoning.get("anomaly_profiles", {})
            if boundary_explanations:
                score -= min(len(boundary_explanations) * 0.3, 1.5)
        
        # Clamp between 0.0 and 10.0
        score = max(0.0, min(10.0, round(score, 1)))
        
        # Determine verdict based on score
        if score < 4.0:
            verdict = "Highly Plagiarized"
        elif score < 7.5:
            verdict = "Suspicious"
        else:
            verdict = "Clean"

        # Build evidence descriptions
        stylometric_desc = f"Mathematical clustering detected {estimated_authors} distinct author signature(s)."
        if anomaly_count > 0:
            stylometric_desc += f" {anomaly_count} paragraph(s) were flagged as stylistic anomalies."
        if boundary_count > 0:
            stylometric_desc += f" {boundary_count} authorship boundary transition(s) detected."
        if noise_override:
            stylometric_desc += " Note: HDBSCAN noise saturation occurred — clustering may be unreliable."
        if too_short:
            stylometric_desc += " Note: Document had too few paragraphs for optimal clustering."
        
        citation_desc = "No temporal citation anomalies detected."
        if citation_anomalies:
            citation_desc = (
                f"Found {len(citation_anomalies)} temporal citation anomalie(s). "
                f"Paragraphs cite sources from significantly different time periods than the core document."
            )
        
        source_desc = "No confirmed external source matches from arXiv."
        if source_matches:
            max_sim = max(m.get("similarity_score", 0) for m in source_matches)
            source_desc = (
                f"Semantic source tracing found {len(source_matches)} match(es) on arXiv "
                f"(highest similarity: {max_sim*100:.1f}%)."
            )

        # Executive summary
        if verdict == "Clean":
            summary = f"The document shows consistent writing style with {noise*100:.1f}% stylistic noise. No significant plagiarism indicators were found."
        elif verdict == "Suspicious":
            summary = f"The document exhibits {noise*100:.1f}% stylistic noise with {anomaly_count} anomalous section(s). Multiple evidence streams suggest potential integrity concerns."
        else:
            summary = f"The document shows strong plagiarism indicators: {noise*100:.1f}% stylistic noise, {anomaly_count} anomalous section(s), and {len(source_matches)} external source match(es)."

        return {
            "integrity_score": score,
            "verdict": verdict,
            "executive_summary": f"[Rule-Based Analysis] {summary}",
            "evidence_breakdown": {
                "stylometric_analysis": stylometric_desc,
                "citation_analysis": citation_desc,
                "source_matches": source_desc,
            },
            "conclusion": f"Based on mathematical analysis, this document is assessed as '{verdict}' with an integrity score of {score}/10. {('Full GPT-4o synthesis unavailable: ' + error + '.') if error != 'Missing API Key' else 'Add OPENAI_API_KEY for a comprehensive AI-powered forensic synthesis.'}"
        }
