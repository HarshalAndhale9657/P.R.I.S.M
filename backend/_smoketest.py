"""In-process end-to-end smoke test for the PRISM pipeline.
Generates a real multi-paragraph PDF with PyMuPDF and runs every stage,
printing per-stage results / exceptions. No server, no API key required.
"""
import asyncio
import traceback
import json
import fitz  # PyMuPDF

from models import PipelineContext
from services.pdf_parser import AcademicPDFParser
from services.feature_engine import FeatureEngine
from services.hdbscan_detector import AuthorshipClustering
from services.gpt_analyzer import GPTAnalyzer
from services.citation_forensics import CitationForensics
from services.source_tracer import SourceTracer
from services.report_generator import ReportGenerator

# ── Build a stitched-style document: formal academic + informal blocks ──
FORMAL = [
    "The proliferation of transformer-based architectures has fundamentally reshaped the landscape of natural language processing. Attention mechanisms permit the model to weigh the relevance of each token with respect to every other token, thereby capturing long-range dependencies that recurrent networks struggle to represent. Empirical evaluations across a broad spectrum of benchmarks demonstrate that these architectures consistently outperform their predecessors (Vaswani, 2017).",
    "Density-based clustering methods offer a principled approach to the identification of latent structure within high-dimensional feature spaces. Unlike centroid-based techniques, they do not presuppose a fixed number of clusters, and they exhibit robustness in the presence of noise. Consequently, they are particularly well suited to forensic applications wherein the number of contributing authors is not known a priori (Campello, 2013).",
    "Stylometric analysis proceeds from the premise that every author leaves an involuntary linguistic fingerprint. Quantifiable measures such as vocabulary richness, sentence-length variance, and function-word frequency have been shown to remain remarkably stable across the corpus of a single author. These invariants furnish the mathematical foundation upon which authorship attribution rests (Stamatatos, 2009).",
    "The evaluation protocol adopted throughout this investigation adheres to established methodological conventions. Each document is partitioned into paragraph-level units, features are extracted deterministically, and the resulting matrix is subjected to normalization prior to clustering. This pipeline guarantees reproducibility and eliminates the confounding influence of stochastic initialization.",
]
INFORMAL = [
    "So basically what we did here is pretty simple when you think about it. We just took a bunch of paragraphs and threw them at the model to see what would stick. Turns out it works way better than we expected, which honestly was a nice surprise for everyone on the team who had been grinding on this thing for weeks now.",
    "Look, the whole point is that people copy stuff all the time and they think nobody notices. But the numbers don't lie, right? When you stitch together text from a bunch of different places the writing style jumps around like crazy and that is exactly the kind of thing our little tool is really good at picking up on very quickly.",
    "Anyway the cool part is you dont even need a fancy setup to run any of this. Just point it at a PDF and wait a couple seconds and boom you get a full report telling you whether the paper smells fishy or not. We tested it on a ton of papers from friends and it caught the sketchy ones almost every single time.",
]
REFS = [
    "References",
    "[1] Vaswani, A. et al. Attention Is All You Need. NeurIPS, 2017.",
    "[2] Campello, R. J. G. B. Density-Based Clustering. PAKDD, 2013.",
    "[3] Stamatatos, E. A Survey of Modern Authorship Attribution Methods. JASIST, 2009.",
]

def build_pdf() -> bytes:
    doc = fitz.open()
    import os
    reps = int(os.getenv("SMOKE_REPS", "1"))
    blocks = []
    # interleave to create style boundaries; repeat to grow the sample size
    for _ in range(reps):
        for i in range(4):
            blocks.append(FORMAL[i])
            if i < len(INFORMAL):
                blocks.append(INFORMAL[i])
    body = "\n\n".join(blocks)
    # page 1..n body
    for chunk_start in range(0, len(blocks), 2):
        page = doc.new_page()
        text = "\n\n".join(blocks[chunk_start:chunk_start + 2])
        page.insert_textbox(fitz.Rect(50, 50, 545, 780), text, fontsize=11, fontname="helv")
    # references page
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 545, 780), "\n".join(REFS), fontsize=11, fontname="helv")
    return doc.tobytes()


async def main():
    pdf_bytes = build_pdf()
    print(f"[gen] PDF built: {len(pdf_bytes)} bytes")
    ctx = PipelineContext()

    def stage(name, fn):
        try:
            r = fn()
            print(f"[OK] {name}")
            return r
        except Exception as e:
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
            return None

    parser = AcademicPDFParser()
    parsed = stage("parse", lambda: parser.parse_safe(pdf_bytes, ctx))
    if not parsed or not parsed["paragraphs"]:
        print("  -> no paragraphs, aborting"); print(json.dumps(parsed, default=str)[:500]); return
    print(f"  paragraphs={len(parsed['paragraphs'])} refs={len(parsed['references'])} method={parsed['extraction_method']}")

    fe = FeatureEngine()
    features = stage("features", lambda: fe.extract_all(parsed["paragraphs"], ctx))
    if features:
        print(f"  valid={features['valid_paragraphs']}/{features['total_paragraphs']} matrix={features['feature_matrix'].shape} names={len(features['feature_names'])}")
        print(f"  profile[0] keys sample: {list(features['profiles'][0].keys())[:8]}")

    clu = AuthorshipClustering(min_cluster_size=2, min_samples=2)
    cluster_result = stage("cluster", lambda: clu.cluster(features["feature_matrix"], ctx))
    if cluster_result:
        print(f"  clusters={cluster_result['clusters']} authors={cluster_result['estimated_authors']} boundaries={cluster_result['boundaries']} noise%={cluster_result['noise_percentage']} conf={cluster_result['confidence']}")
    enriched = stage("get_cluster_summary", lambda: clu.get_cluster_summary(parsed["paragraphs"], cluster_result))

    gpt = GPTAnalyzer()
    reasoning = None
    try:
        reasoning = await gpt.analyze_boundaries(parsed["paragraphs"], cluster_result, ctx)
        print(f"[OK] reasoning available={reasoning.get('available')}")
    except Exception as e:
        print(f"[FAIL] reasoning: {type(e).__name__}: {e}"); traceback.print_exc()

    cf = CitationForensics(temporal_threshold=10)
    citations = stage("citations", lambda: cf.analyze(parsed["paragraphs"], parsed["references"], cluster_result, ctx))
    if isinstance(citations, dict):
        print(f"  citation keys: {list(citations.keys())}")
        print(f"  total_citations_found={citations.get('total_citations_found')}")

    st = SourceTracer(similarity_threshold=0.50)
    anomalous = [p for p in enriched if p.get("is_anomaly")][:1]
    sources = stage("source_tracer", lambda: st.trace(anomalous, ctx))
    print(f"  sources type={type(sources).__name__} len={len(sources) if hasattr(sources,'__len__') else 'n/a'}")

    rg = ReportGenerator()
    try:
        report = await rg.generate_report({
            "clustering": cluster_result, "reasoning": reasoning,
            "citations": citations, "sources": sources,
            "features": features,
        })
        print(f"[OK] report verdict={report.get('verdict')} score={report.get('integrity_score')}")
        print(f"  summary: {report.get('executive_summary','')[:160]}")
        print(f"  evidence keys: {list(report.get('evidence_breakdown',{}).keys())}")
    except Exception as e:
        print(f"[FAIL] report: {type(e).__name__}: {e}"); traceback.print_exc()

    print("\n[warnings]", ctx.warning_count if hasattr(ctx,'warning_count') else len(ctx.warnings))
    for w in ctx.warnings:
        print("  -", w.code, w.severity, "|", w.message[:70])


if __name__ == "__main__":
    asyncio.run(main())
