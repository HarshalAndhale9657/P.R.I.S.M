"""
P.R.I.S.M. — Pipeline Orchestrator
====================================
Central coordinator for the analysis pipeline. Extracts the shared
logic that was duplicated across 5+ endpoints in main.py.

Pipeline stages:
  1. Parse PDF → paragraphs + references
  2. Extract features (spaCy, 27 features)
  3. HDBSCAN clustering
  4. PELT change-point detection
  5. Embedding similarity detection (new — strongest signal)
  6. Boundary fusion (3-way: HDBSCAN + PELT + Embedding)
  7. GPT reasoning (flagged boundaries only)
  8. Citation forensics
  9. Source tracing (anomalies only)
  10. Topic coherence (new — was orphaned)
  11. Scoring engine (deterministic, all sub-scores)
  12. Report generation

All endpoints can call orchestrator.run(pdf_bytes, through_stage=N)
to get results up to any stage, eliminating copy-pasted pipeline code.
"""

import logging
import numpy as np
from typing import Dict, Any, List, Optional
from fastapi.concurrency import run_in_threadpool

from services.pdf_parser import AcademicPDFParser
from services.feature_engine import FeatureEngine
from services.hdbscan_detector import AuthorshipClustering
from services.pelt_detector import PELTDetector
from services.boundary_fusion import BoundaryFusion
from services.embedding_similarity_detector import EmbeddingSimilarityDetector
from services.topic_coherence import TopicCoherenceAnalyzer
from services.scoring_engine import ScoringEngine
from services.gpt_analyzer import GPTAnalyzer
from services.citation_forensics import CitationForensics
from services.report_generator import ReportGenerator
from services.source_tracer import SourceTracer
from services.window_aggregator import WindowAggregator
from models import PipelineContext, WarningCode, WarningSeverity

logger = logging.getLogger(__name__)

# Median word count below which windowed feature extraction kicks in.
# PAN 2023 paragraphs have median ~41 words; FeatureEngine needs 50+ for
# reliable extraction. When the document's median paragraph word count is
# below this threshold we build overlapping windows first.
_SHORT_PARAGRAPH_THRESHOLD = 60


class PipelineOrchestrator:
    """
    Single entry point for the P.R.I.S.M. analysis pipeline.
    Each stage writes to a shared result dict.
    Callers can specify through_stage to stop early.
    """

    def __init__(self):
        self.pdf_parser = AcademicPDFParser()
        self.feature_engine = FeatureEngine()
        self.clustering_engine = AuthorshipClustering(min_cluster_size=2, min_samples=2)
        self.pelt_detector = PELTDetector(model="rbf", default_penalty=1.0)
        self.boundary_fusion = BoundaryFusion(tolerance=1)
        self.embed_detector = EmbeddingSimilarityDetector(sigma=1.0, min_similarity_drop=0.05)
        self.topic_coherence = TopicCoherenceAnalyzer(sigma_threshold=2.0)
        self.window_aggregator = WindowAggregator(target_words=100, stride=1)
        self.scoring_engine = ScoringEngine()
        self.gpt_analyzer = GPTAnalyzer()
        self.citation_forensics = CitationForensics(temporal_threshold=10)
        self.source_tracer = SourceTracer(similarity_threshold=0.50)
        self.report_generator = ReportGenerator()

    async def run(
        self,
        pdf_bytes: bytes,
        through_stage: int = 12,
        filename: str = "document.pdf",
    ) -> Dict[str, Any]:
        """
        Run the pipeline up to the specified stage.

        Stages:
          1  = Parse only
          2  = + Features
          3  = + HDBSCAN clustering
          4  = + PELT detection
          5  = + Embedding similarity detection
          6  = + Boundary fusion (3-way)
          7  = + GPT reasoning
          8  = + Citation forensics
          9  = + Source tracing
          10 = + Topic coherence
          11 = + Scoring
          12 = + Report generation (default)

        Returns:
            Dict with all computed data up to the requested stage.
        """
        ctx = PipelineContext()
        result = {
            "filename": filename,
            "status": "success",
        }

        # ── Stage 1: Parse PDF ───────────────────────────────────────────────
        parsed = await run_in_threadpool(self.pdf_parser.parse_safe, pdf_bytes, ctx)
        result["parsed"] = parsed
        result["paragraphs"] = parsed.get("paragraphs", [])
        result["references"] = parsed.get("references", [])
        result["metadata"] = {
            "pages": parsed.get("page_count", 0),
            "total_paragraphs": len(result["paragraphs"]),
            "extraction_method": parsed.get("extraction_method", "none"),
            "degraded_mode": parsed.get("degraded_mode", False) or ctx.degraded_mode,
        }

        if not result["paragraphs"]:
            result["status"] = "error"
            result["error"] = "No text could be extracted from this PDF."
            result.update(ctx.to_dict())
            return result

        if through_stage < 2:
            result.update(ctx.to_dict())
            return result

        # ── Stage 2: Extract features ────────────────────────────────────────
        # Detect if paragraphs are short and use windowed extraction if needed.
        paragraph_texts = [
            p["text"] if isinstance(p, dict) else p
            for p in result["paragraphs"]
        ]
        word_counts = [len(t.split()) for t in paragraph_texts]
        median_wc = float(np.median(word_counts)) if word_counts else 0

        used_windowing = False
        windows_meta = None

        if median_wc < _SHORT_PARAGRAPH_THRESHOLD and len(paragraph_texts) >= 3:
            # Short paragraphs → use overlapping windows for feature extraction
            logger.info(
                f"[P.R.I.S.M.] Median word count {median_wc:.0f} < {_SHORT_PARAGRAPH_THRESHOLD} — "
                f"using windowed feature extraction"
            )
            windows_meta, window_texts = self.window_aggregator.build_windows(paragraph_texts)

            if window_texts:
                window_para_dicts = [{"text": t} for t in window_texts]
                features = await run_in_threadpool(
                    self.feature_engine.extract_all, window_para_dicts, ctx
                )
                used_windowing = True
            else:
                features = await run_in_threadpool(
                    self.feature_engine.extract_all, result["paragraphs"], ctx
                )
        else:
            features = await run_in_threadpool(
                self.feature_engine.extract_all, result["paragraphs"], ctx
            )

        result["features"] = {
            "feature_names": features["feature_names"],
            "profiles": features["profiles"],
            "total_paragraphs": features["total_paragraphs"],
            "valid_paragraphs": features["valid_paragraphs"],
            "used_windowing": used_windowing,
            "median_word_count": round(median_wc, 1),
        }

        if through_stage < 3:
            result.update(ctx.to_dict())
            return result

        # ── Stage 3: HDBSCAN clustering ──────────────────────────────────────
        cluster_result = await run_in_threadpool(
            self.clustering_engine.cluster, features["feature_matrix"], ctx
        )
        enriched_paragraphs = await run_in_threadpool(
            self.clustering_engine.get_cluster_summary, result["paragraphs"], cluster_result
        )
        result["paragraphs"] = enriched_paragraphs
        result["clustering"] = cluster_result

        # Extract HDBSCAN boundary positions as List[int] for the fusion module.
        # HDBSCAN returns boundaries as dicts with "after_paragraph" key.
        hdbscan_boundaries_raw = cluster_result.get("boundaries", [])
        hdbscan_boundaries: List[int] = [
            b["after_paragraph"] if isinstance(b, dict) else b
            for b in hdbscan_boundaries_raw
        ]

        if through_stage < 4:
            result.update(ctx.to_dict())
            return result

        # ── Stage 4: PELT detection ──────────────────────────────────────────
        try:
            pelt_result = await run_in_threadpool(
                self.pelt_detector.detect, features["feature_matrix"]
            )
            result["pelt"] = pelt_result
            pelt_boundaries = pelt_result.get("change_points", [])

            # If windowed, map PELT boundaries back to paragraph-level
            if used_windowing and windows_meta:
                pelt_boundaries = self.window_aggregator.map_boundaries(
                    pelt_boundaries, windows_meta, len(paragraph_texts)
                )
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] PELT detection failed: {e}")
            result["pelt"] = {"change_points": [], "error": str(e)}
            pelt_boundaries = []

        if through_stage < 5:
            result.update(ctx.to_dict())
            return result

        # ── Stage 5: Embedding similarity detection ──────────────────────────
        try:
            embed_result = await run_in_threadpool(
                self.embed_detector.detect, paragraph_texts
            )
            result["embedding_similarity"] = embed_result
            embed_boundaries = embed_result.get("boundaries", [])
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Embedding similarity failed: {e}")
            result["embedding_similarity"] = {"boundaries": [], "error": str(e)}
            embed_boundaries = []

        if through_stage < 6:
            result.update(ctx.to_dict())
            return result

        # ── Stage 6: 3-way boundary fusion ───────────────────────────────────
        # Fuse HDBSCAN + PELT as before, then integrate embedding boundaries
        # using majority voting (≥2 of 3 engines must agree).
        fusion_result = self._3way_fuse(
            hdbscan_boundaries, pelt_boundaries, embed_boundaries
        )
        result["fusion"] = fusion_result

        if through_stage < 7:
            result.update(ctx.to_dict())
            return result

        # ── Stage 7: GPT reasoning ───────────────────────────────────────────
        try:
            reasoning = await self.gpt_analyzer.analyze_boundaries(
                result["parsed"]["paragraphs"], cluster_result, ctx
            )
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] GPT reasoning crashed: {e}")
            ctx.add_warning(
                WarningCode.GPT_TIMEOUT, WarningSeverity.ERROR, "gpt_analyzer",
                f"GPT reasoning failed: {str(e)[:200]}",
            )
            reasoning = {
                "available": False,
                "error": str(e),
                "boundary_explanations": {},
                "anomaly_profiles": {},
            }
        result["reasoning"] = reasoning

        if through_stage < 8:
            result.update(ctx.to_dict())
            return result

        # ── Stage 8: Citation forensics ──────────────────────────────────────
        try:
            citations = self.citation_forensics.analyze(
                result["parsed"]["paragraphs"], result["references"], cluster_result, ctx
            )
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Citation forensics crashed: {e}")
            citations = {
                "per_paragraph": [],
                "total_citations_found": 0,
                "error": str(e),
            }
        result["citations"] = citations

        if through_stage < 9:
            result.update(ctx.to_dict())
            return result

        # ── Stage 9: Source tracing ───────────────────────────────────────────
        try:
            anomalous_paragraphs = [
                p for p in enriched_paragraphs if p.get("is_anomaly")
            ][:1]  # Limit to 1 for speed to prevent Render 502 timeout
            sources = await run_in_threadpool(
                self.source_tracer.trace, anomalous_paragraphs, ctx
            )
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Source tracing crashed: {e}")
            ctx.add_warning(
                WarningCode.SOURCE_EMBEDDING_FAILED, WarningSeverity.WARNING, "source_tracer",
                f"Source tracing failed: {str(e)[:200]}",
            )
            sources = []
        result["sources"] = sources

        if through_stage < 10:
            result.update(ctx.to_dict())
            return result

        # ── Stage 10: Topic coherence ────────────────────────────────────────
        try:
            coherence_result = await run_in_threadpool(
                self.topic_coherence.analyze, paragraph_texts
            )
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Topic coherence failed: {e}")
            coherence_result = {
                "coherence_score": None,
                "error": str(e),
            }
        result["topic_coherence"] = coherence_result

        if through_stage < 11:
            result.update(ctx.to_dict())
            return result

        # ── Stage 11: Deterministic scoring ──────────────────────────────────
        burstiness_values = [
            p.get("burstiness_coefficient", p.get("burstiness_score", 0))
            for p in features.get("profiles", [])
            if isinstance(p, dict) and p.get("num_sentences", 1) >= 2
        ]

        scoring_result = self.scoring_engine.score(
            boundary_result=fusion_result,
            coherence_result=coherence_result,
            citation_result=citations,
            burstiness_values=burstiness_values,
        )
        result["scoring"] = scoring_result

        if through_stage < 12:
            result.update(ctx.to_dict())
            return result

        # ── Stage 12: Generate report ────────────────────────────────────────
        analysis_data = {
            "clustering": cluster_result,
            "reasoning": reasoning,
            "citations": citations,
            "sources": sources,
            "features": result["features"],
        }
        report = await self.report_generator.generate_report(analysis_data)
        result["report"] = report

        result.update(ctx.to_dict())
        return result

    # ─── 3-Way Fusion ────────────────────────────────────────────────────────

    def _3way_fuse(
        self,
        hdbscan_boundaries: List[int],
        pelt_boundaries: List[int],
        embed_boundaries: List[int],
    ) -> Dict[str, Any]:
        """
        Fuse boundaries from 3 engines using majority voting.

        A boundary position is included if ≥2 of the 3 engines agree
        (within ±tolerance). This mirrors the evaluation pipeline's
        fusion3 strategy which achieved the best F1 (0.397).

        Fallback: if strict voting finds nothing but embedding alone
        detected boundaries, use embedding results (strongest signal).
        """
        tolerance = self.boundary_fusion.tolerance

        # Collect all candidate positions
        all_candidates = sorted(set(hdbscan_boundaries) | set(pelt_boundaries) | set(embed_boundaries))

        if not all_candidates:
            return self.boundary_fusion._empty_result()

        voted_boundaries = []
        detected_by_map = {}

        for pos in all_candidates:
            engines = []
            if any(abs(pos - b) <= tolerance for b in hdbscan_boundaries):
                engines.append("hdbscan")
            if any(abs(pos - b) <= tolerance for b in pelt_boundaries):
                engines.append("pelt")
            if any(abs(pos - b) <= tolerance for b in embed_boundaries):
                engines.append("embedding")

            if len(engines) >= 2:
                voted_boundaries.append(pos)
                detected_by_map[pos] = engines

        # Fallback: embedding alone is the strongest single signal (F1=0.374).
        # If voting finds nothing, trust embedding detections.
        if not voted_boundaries and embed_boundaries:
            voted_boundaries = list(embed_boundaries)
            detected_by_map = {b: ["embedding"] for b in embed_boundaries}

        # Deduplicate boundaries that are too close (within tolerance)
        deduped = []
        for b in sorted(voted_boundaries):
            if not deduped or abs(b - deduped[-1]) > tolerance:
                deduped.append(b)

        # Classify confidence
        high_count = 0
        boundaries_output = []
        for b in deduped:
            engines = detected_by_map.get(b, [])
            is_high = len(engines) >= 2
            if is_high:
                high_count += 1
            boundaries_output.append({
                "after_paragraph": b,
                "corroboration": "high" if is_high else "medium",
                "detected_by": engines,
            })

        medium_count = len(boundaries_output) - high_count
        total = len(boundaries_output)
        agreement_rate = high_count / max(total, 1)

        logger.info(
            f"[P.R.I.S.M.] 3-way fusion: {total} boundaries "
            f"({high_count} HIGH, {medium_count} MEDIUM, "
            f"agreement rate: {agreement_rate:.0%})"
        )

        return {
            "boundaries": boundaries_output,
            "high_confidence_count": high_count,
            "medium_confidence_count": medium_count,
            "total_boundaries": total,
            "agreement_rate": round(agreement_rate, 4),
            "engines_used": ["hdbscan", "pelt", "embedding"],
            "engine_counts": {
                "hdbscan": len(hdbscan_boundaries),
                "pelt": len(pelt_boundaries),
                "embedding": len(embed_boundaries),
            },
        }
