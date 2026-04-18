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
        
        doc_data = {
            "clustering": {
                "estimated_authors": clusters.get("estimated_authors", 1),
                "anomaly_count": clusters.get("anomaly_count", 0),
                "noise_percentage": clusters.get("noise_percentage", 0.0),
            },
            "reasoning": analysis_data.get("reasoning", {}).get("boundary_explanations", {}),
            "citations": analysis_data.get("citations", {}).get("temporal_anomalies", []),
            "sources": []
        }
        
        # Extract source matches if present
        source_matches = analysis_data.get("sources", [])
        if source_matches:
            doc_data["sources"] = [{"title": s.get("source", {}).get("title"), "similarity": s.get("similarity_score")} for s in source_matches]

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
        Generate a basic rule-based report if GPT-4o fails or is unavailable.
        Maintains the frontend's expected schema so the dashboard doesn't crash.
        """
        clustering = data.get("clustering", {})
        noise = clustering.get("noise_percentage", 0.0)
        source_matches = data.get("sources", {}).get("matches", [])
        citation_anomalies = data.get("citations", {}).get("temporal_anomalies", [])
        
        # Base score on HDBSCAN noise percentage
        score = 10.0 - (noise * 10)
        
        # Subtract penalties for hard evidence
        if citation_anomalies:
            score -= 1.5
        if source_matches:
            score -= 2.5
            
        # Clamp between 0.0 and 10.0
        score = max(0.0, min(10.0, score))
        
        verdict = "Clean"
        if score < 4.0: 
            verdict = "Highly Plagiarized"
        elif score < 7.5: 
            verdict = "Suspicious"

        return {
            "integrity_score": round(score, 1),
            "verdict": verdict,
            "executive_summary": f"[DEGRADED MODE] Report generated via rule-engine (Error: {error}). The document exhibits {noise*100:.1f}% stylistic noise.",
            "evidence_breakdown": {
                "stylometric_analysis": f"Mathematical clustering revealed {clustering.get('estimated_authors', 1)} distinct author signatures.",
                "citation_analysis": f"Found {len(citation_anomalies)} temporal citation anomalies." if citation_anomalies else "No obvious temporal citation anomalies.",
                "source_matches": f"Embedded search found {len(source_matches)} match(es) from Arxiv." if source_matches else "No confirmed external source matches."
            },
            "conclusion": "This is a fallback analysis. Add OPENAI_API_KEY for a full GPT-4o forensic synthesis."
        }
