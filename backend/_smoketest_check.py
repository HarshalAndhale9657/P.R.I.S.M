"""Offline unit-smoke for the PlagiarismMatcher (no server, no API key).

Verbatim matching is deterministic and needs no model. Paraphrase matching runs
only if sentence-transformers is installed; otherwise it degrades gracefully.
Exit code 0 = pass, 1 = fail (CI-usable).
"""
import sys
from services.plagiarism_matcher import PlagiarismMatcher, SourceDoc

SOURCE_A = (
    "The transformer architecture relies entirely on self-attention mechanisms to draw "
    "global dependencies between input and output sequences. "
    "Density-based clustering automatically determines the number of clusters present in a "
    "dataset without requiring a preset count parameter. "
    "Empirical evaluation on standard benchmarks shows consistent gains over recurrent baselines."
)

# Document: [original] + [verbatim copy from A] + [paraphrase of A] + [original]
DOCUMENT = (
    "In this paper we study machine learning methods for text analysis and their behaviour. "
    "The transformer architecture relies entirely on self-attention mechanisms to draw "
    "global dependencies between input and output sequences. "
    "Clustering techniques based on density can infer how many groups exist in the data "
    "without needing a fixed number to be specified in advance. "
    "Our own contribution is a small user study conducted with twenty volunteers over two weeks."
)

VERBATIM_NEEDLE = "self-attention mechanisms to draw global dependencies"


def main() -> int:
    matcher = PlagiarismMatcher()
    result = matcher.check(DOCUMENT, [SourceDoc(id="src-0", name="Source A", text=SOURCE_A)])

    ov = result["overall"]
    print(f"paraphrase_enabled={result['paraphrase_enabled']}")
    print(f"overall: similarity={ov['similarity_pct']}%  verbatim={ov['verbatim_pct']}%  "
          f"paraphrase={ov['paraphrase_pct']}%  matched={ov['matched_words']}/{ov['total_words']}  "
          f"matches={ov['match_count']}")
    for m in result["matches"]:
        print(f"  [{m['match_type']}] sim={m['similarity']} "
              f"doc='{m['doc_excerpt'][:70]}...' <- src='{m['source_excerpt'][:60]}...'")
    for w in result["warnings"]:
        print("  warning:", w)

    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), "-", msg)
        ok = ok and cond

    verbatim = [m for m in result["matches"] if m["match_type"] == "verbatim"]
    check(len(verbatim) >= 1, "found at least one verbatim match")
    check(any(VERBATIM_NEEDLE in m["doc_excerpt"] for m in verbatim),
          "verbatim match covers the copied passage")
    check(ov["total_words"] > 0, "counted document words")
    check(ov["verbatim_pct"] > 0, "verbatim contributes to the similarity score")

    if result["paraphrase_enabled"]:
        para = [m for m in result["matches"] if m["match_type"] == "paraphrase"]
        check(len(para) >= 1, "found at least one paraphrase match (model available)")
    else:
        print("NOTE - paraphrase model unavailable; skipped paraphrase assertions")

    # A clearly original sentence must NOT be flagged.
    flagged = any("twenty volunteers" in m["doc_excerpt"] for m in result["matches"])
    check(not flagged, "original passage is not falsely flagged")

    # ── Translated (cross-lingual) case ──
    if result["paraphrase_enabled"]:
        fr = ("L'architecture du transformateur repose entièrement sur des mécanismes d'auto-attention "
              "pour établir des dépendances globales entre les séquences d'entrée et de sortie.")
        doc2 = ("The transformer architecture relies entirely on self-attention mechanisms to establish "
                "global dependencies between input and output sequences. "
                "Our own separate work adds a brief survey of evaluation tools.")
        res2 = matcher.check(doc2, [SourceDoc(id="fr-0", name="French Source", text=fr)])
        tr = [m for m in res2["matches"] if m["match_type"] == "translated"]
        check(len(tr) >= 1, "cross-lingual copy is flagged as 'translated'")
        if tr:
            print(f"   translated: {tr[0].get('source_lang')}->{tr[0].get('doc_lang')} sim={tr[0]['similarity']}")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
