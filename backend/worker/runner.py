"""
P.R.I.S.M. — Check runner
=========================
Owns the lifecycle of one originality check: accept validated uploads, hand
them to the bounded executor, run the pipeline, and record the outcome in the
job store. This is the only place that knows about *both* the HTTP-facing job
model and the pipeline, so the routers stay thin and the pipeline stays pure.

Collaborators are injected (matcher, academic search, model registry hooks)
so tests can substitute fakes — the same seam the old ``main`` globals provided.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.logging_config import job_id_var
from app.settings import APP_VERSION, Settings
from pipeline import CheckContext, PipelineError, RawInput, build_check_stages, run_pipeline
from services.plagiarism_matcher import PlagiarismMatcher

from .executor import BoundedExecutor, QueueFull
from .store import JobRecord, JobStore, TTLCache

logger = logging.getLogger(__name__)

SearchFn = Callable[[str], Tuple[list, List[str]]]
Upload = Tuple[str, bytes]


@dataclass
class CheckRequest:
    paper: Upload
    references: List[Upload]
    use_academic: bool
    base_warnings: List[str]

    def content_hash(self) -> str:
        h = hashlib.sha256()
        h.update(self.paper[1])
        for _, raw in sorted(self.references, key=lambda r: r[1]):
            h.update(b"\x00")
            h.update(raw)
        h.update(b"|academic=" + (b"1" if self.use_academic else b"0"))
        return h.hexdigest()


class CheckRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        store: JobStore,
        executor: BoundedExecutor,
        matcher: PlagiarismMatcher,
        academic_search: SearchFn,
        result_cache: Optional[TTLCache] = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.executor = executor
        self.matcher = matcher
        self.academic_search = academic_search
        self.cache: TTLCache = result_cache or TTLCache(
            max_size=settings.result_cache_size, ttl_seconds=settings.result_cache_ttl_seconds
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def submit(self, req: CheckRequest) -> JobRecord:
        """Queue a check. Raises QueueFull when the worker backlog is at capacity."""
        rec = self.store.create()
        try:
            self.executor.submit(self._run, rec.id, req)
        except QueueFull:
            self.store.update(rec.id, status="error", error="Server busy.")
            raise
        return rec

    def status(self, job_id: str) -> Optional[JobRecord]:
        return self.store.get(job_id)

    # ── Worker side ───────────────────────────────────────────────────────────

    def _run(self, job_id: str, req: CheckRequest) -> None:
        token = job_id_var.set(job_id)
        started = time.perf_counter()
        self.store.update(job_id, status="running")
        try:
            key = req.content_hash()
            result = self.cache.get(key)
            if result is None:
                result = self._compute(req)
                self.cache.put(key, result)
            else:
                logger.info("check served from result cache")
            self.store.update(job_id, status="done", result=result)
            logger.info("check done in %.2fs (%d matches)", time.perf_counter() - started,
                        result["overall"]["match_count"])
        except PipelineError as exc:
            self.store.update(job_id, status="error", error=str(exc))
            logger.info("check rejected: %s", exc)
        except Exception:
            logger.exception("check failed")
            self.store.update(job_id, status="error", error="Originality check failed. Please try again.")
        finally:
            job_id_var.reset(token)

    def _compute(self, req: CheckRequest) -> Dict[str, Any]:
        s = self.settings
        ctx = CheckContext(
            raw_document=RawInput(name=req.paper[0], data=req.paper[1]),
            raw_sources=[RawInput(name=n, data=d) for n, d in req.references],
            warnings=list(req.base_warnings),
        )
        stages = build_check_stages(
            matcher=self.matcher,
            search_fn=self.academic_search,
            use_academic=req.use_academic and s.academic_enabled,
            rerank=s.rerank,
            rerank_model=s.rerank_model,
            max_pdf_pages=s.max_pdf_pages,
            max_document_chars=s.max_document_chars,
        )
        ctx = run_pipeline(ctx, stages)
        return self._assemble(ctx, req)

    def _assemble(self, ctx: CheckContext, req: CheckRequest) -> Dict[str, Any]:
        assert ctx.document is not None
        s = self.settings
        from modelhub import describe  # local import: keeps worker importable without torch

        reranked_any = bool(ctx.artifacts.get("reranked_count"))
        academic_used = bool(ctx.artifacts.get("academic_used", False))
        acad = [x for x in ctx.sources if x.origin != "upload"]
        coverage = _coverage_statement(
            n_uploads=len(req.references),
            academic=academic_used,
            n_fulltext=sum(1 for x in acad if x.kind == "fulltext"),
            n_abstract=sum(1 for x in acad if x.kind != "fulltext"),
            providers=sorted({x.origin for x in acad}),
        )
        return {
            "filename": ctx.document.name,
            "status": "success",
            "document_text": ctx.document.text,
            "paragraphs": [
                {"index": p["index"], "page": p.get("page"), "start": p["start"], "end": p["end"]}
                for p in ctx.document.paragraphs
            ],
            "page_count": ctx.document.page_count,
            "academic_used": academic_used,
            "sources": [{"id": x.id, "name": x.name, "origin": x.origin, "url": x.url, "kind": x.kind}
                        for x in ctx.sources],
            "overall": ctx.artifacts["overall"],
            "per_source": ctx.artifacts["per_source"],
            "matches": ctx.artifacts["matches"],
            "paraphrase_enabled": ctx.artifacts.get("paraphrase_enabled"),
            "warnings": ctx.warnings,
            "triage_summary": ctx.artifacts.get("triage_summary"),
            "timings_ms": ctx.artifacts.get("timings_ms", {}),
            "engine": {
                "version": APP_VERSION,
                "bi_encoder": describe("bi-encoder").name,
                "paraphrase_threshold": self.matcher.paraphrase_threshold,
                # The cutoff actually applied — it scales with corpus size (ADR-0024).
                "confident_threshold": (ctx.artifacts.get("confident_threshold_used")
                                        or self.matcher.confident_threshold),
                "confident_threshold_base": self.matcher.confident_threshold,
                "corpus_sentences": ctx.artifacts.get("corpus_sentences", 0),
                "reranked": reranked_any,
                "rerank_model": s.rerank_model if reranked_any else None,
                "coverage": coverage,
            },
        }


_PROVIDER_LABELS = {"openalex": "OpenAlex", "arxiv": "arXiv", "semanticscholar": "Semantic Scholar"}


def _coverage_statement(*, n_uploads: int, academic: bool, n_fulltext: int = 0, n_abstract: int = 0,
                        providers: Optional[List[str]] = None) -> str:
    parts: List[str] = []
    if n_uploads:
        parts.append(f"{n_uploads} uploaded reference file{'s' if n_uploads != 1 else ''}")
    if academic:
        names = ", ".join(_PROVIDER_LABELS.get(p, p) for p in (providers or [])) or "open-access databases"
        detail = []
        if n_fulltext:
            detail.append(f"{n_fulltext} with full text")
        if n_abstract:
            detail.append(f"{n_abstract} abstract-only")
        parts.append(f"{n_fulltext + n_abstract} open-access sources from {names}"
                     + (f" ({', '.join(detail)})" if detail else ""))
    checked = " and ".join(parts) if parts else "no sources"
    return (f"Checked against {checked}. Not checked: the wider web, subscription journal databases, "
            f"or student-paper repositories — a clean result here is not a guaranteed pass elsewhere.")
