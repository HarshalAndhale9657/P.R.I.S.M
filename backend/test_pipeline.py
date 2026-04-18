"""
P.R.I.S.M. — Pipeline Integration Test
Creates a multi-author academic PDF and runs the full analysis pipeline.
Uses PyMuPDF (fitz) instead of reportlab to avoid extra dependencies.
"""
import requests
import os
import fitz  # PyMuPDF — already installed

# ─── 1. Create a realistic multi-style academic PDF ─────────────────────────
pdf_path = "test_paper.pdf"
doc = fitz.open()

# Page 1: "Author A" style — formal, passive voice, long sentences
page1 = doc.new_page()
author_a_paragraphs = [
    "The methodology presented in this investigation employs a comprehensive "
    "framework for the systematic evaluation of density-based clustering algorithms. "
    "It was determined through extensive experimentation that hierarchical density-based "
    "spatial clustering of applications with noise demonstrates superior performance "
    "characteristics when compared to traditional partitioning methods such as K-Means "
    "and Gaussian Mixture Models (Smith et al., 2019).",

    "Furthermore, the theoretical foundations underpinning the proposed approach are "
    "grounded in the seminal work of Campello et al. (2013), wherein the mathematical "
    "properties of mutual reachability distance were rigorously established. The empirical "
    "validation was conducted utilizing a corpus of 847 academic manuscripts spanning "
    "multiple disciplinary domains, thereby ensuring the generalizability of our findings "
    "across heterogeneous textual distributions (Johnson and Williams, 2021).",

    "The preprocessing pipeline was meticulously designed to preserve the linguistic "
    "characteristics inherent in each document while simultaneously removing extraneous "
    "formatting artifacts. Tokenization was performed utilizing the spaCy natural language "
    "processing framework, which provides deterministic part-of-speech tagging and "
    "dependency parsing capabilities that are essential for reliable stylometric analysis "
    "(Brown, 2020).",
]

y = 72
for para in author_a_paragraphs:
    # Insert text with wrapping
    rect = fitz.Rect(72, y, 540, y + 120)
    page1.insert_textbox(rect, para, fontsize=10, fontname="helv")
    y += 130

# Page 2: "Author B" style — informal, active voice, short choppy sentences
page2 = doc.new_page()
author_b_paragraphs = [
    "We ran the tests. The results were clear. HDBSCAN beats K-Means every time. "
    "No question about it. The noise detection is what makes it special. "
    "You don't need to pick K. That's huge.",

    "Look at the numbers. Precision hit 0.94. Recall was 0.91. F1 score came in "
    "at 0.925. These aren't just good — they're best-in-class. We checked against "
    "five baselines. Won on all of them. Simple as that.",

    "Here's the thing about plagiarism detection. Most tools just do string matching. "
    "That's lazy. We go deeper. We look at how someone writes. Their sentence length. "
    "Word choice. Passive vs active voice. You can't fake that stuff. "
    "Every writer has a fingerprint.",
]

y = 72
for para in author_b_paragraphs:
    rect = fitz.Rect(72, y, 540, y + 120)
    page2.insert_textbox(rect, para, fontsize=10, fontname="helv")
    y += 130

# Page 3: Back to "Author A" style + references
page3 = doc.new_page()
author_a_return = [
    "In conclusion, the integrated analytical framework presented herein demonstrates "
    "that stylometric profiling, when combined with density-based clustering methodologies, "
    "yields a robust and mathematically defensible mechanism for the identification of "
    "heterogeneous authorship within academic manuscripts. The convergence of deterministic "
    "computational linguistics with probabilistic machine learning represents a paradigm "
    "shift in the domain of academic integrity verification (Lee and Park, 2022).",

    "The implications of this research extend beyond the immediate application of "
    "plagiarism detection, encompassing broader considerations of authorship attribution "
    "in forensic linguistics, intellectual property disputes, and the preservation of "
    "scholarly standards in an era of rapidly proliferating AI-generated text "
    "(Zhang et al., 2023).",
]

y = 72
for para in author_a_return:
    rect = fitz.Rect(72, y, 540, y + 120)
    page3.insert_textbox(rect, para, fontsize=10, fontname="helv")
    y += 130

# References section
refs_text = (
    "References\n\n"
    "Brown, A. (2020). spaCy for Academic Text Analysis. Journal of NLP, 15(3), 45-62.\n"
    "Campello, R., Moulavi, D., & Sander, J. (2013). Density-Based Clustering. PAKDD.\n"
    "Johnson, M. & Williams, R. (2021). Cross-Domain Stylometric Validation. ACL.\n"
    "Lee, S. & Park, J. (2022). Hybrid Authorship Detection Systems. IEEE TKDE, 34(7).\n"
    "Smith, J., Davis, K., & Chen, L. (2019). Comparative Clustering Analysis. ICML.\n"
    "Zhang, W., Liu, X., & Kumar, R. (2023). AI-Generated Text Detection. NeurIPS.\n"
)
rect = fitz.Rect(72, y + 20, 540, 720)
page3.insert_textbox(rect, refs_text, fontsize=9, fontname="helv")

doc.save(pdf_path)
doc.close()
print(f"✅ Created test PDF: {pdf_path} (3 pages, mixed authorship)")

# ─── 2. Test the full analysis pipeline ─────────────────────────────────────
url = "http://127.0.0.1:8000/api/analyze"
print(f"\n🔬 Sending to {url}...")
print("   (This may take 30-60s due to GPT + arxiv calls)\n")

with open(pdf_path, "rb") as f:
    files = {"file": ("test_stitched_paper.pdf", f, "application/pdf")}
    response = requests.post(url, files=files, timeout=120)

print(f"📡 Status Code: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print("\n" + "=" * 60)
    print("✅ PIPELINE SUCCESS!")
    print("=" * 60)

    # Metadata
    meta = data.get("metadata", {})
    print(f"\n📄 Pages: {meta.get('pages')}")
    print(f"📝 Total Paragraphs: {meta.get('total_paragraphs')}")
    print(f"🔧 Extraction Method: {meta.get('extraction_method')}")
    print(f"⚠️  Degraded Mode: {meta.get('degraded_mode')}")

    # Clustering
    cl = data.get("clustering", {})
    print(f"\n👥 Estimated Authors: {cl.get('estimated_authors')}")
    print(f"🚨 Anomaly Count: {cl.get('anomaly_count')}")
    print(f"📊 Noise %: {cl.get('noise_percentage', 0)*100:.1f}%")
    print(f"🎯 Confidence: {cl.get('confidence')}")
    print(f"📐 Clusters: {cl.get('clusters')}")
    print(f"🔀 Boundaries: {cl.get('boundaries')}")

    # Features
    feat = data.get("features", {})
    print(f"\n📈 Feature Names: {feat.get('feature_names')}")
    print(f"   Valid Paragraphs: {feat.get('valid_paragraphs')}/{feat.get('total_paragraphs')}")

    # Reasoning
    reasoning = data.get("reasoning", {})
    if reasoning:
        print(f"\n🧠 GPT Reasoning Available: {reasoning.get('available', 'N/A')}")
        boundaries = reasoning.get("boundary_explanations", {})
        print(f"   Boundary Explanations: {len(boundaries)} pairs analyzed")

    # Citations
    cit = data.get("citations", {})
    print(f"\n📚 Total Citations Found: {cit.get('total_citations_found', 0)}")
    anomalies = cit.get("temporal_anomalies", [])
    print(f"⏰ Temporal Anomalies: {len(anomalies)}")

    # Sources
    sources = data.get("sources", [])
    print(f"\n🔍 Source Matches: {len(sources) if isinstance(sources, list) else 'N/A'}")

    # Report
    report = data.get("report", {})
    print(f"\n📋 FORENSIC REPORT:")
    print(f"   Integrity Score: {report.get('integrity_score', 'N/A')}/10")
    print(f"   Verdict: {report.get('verdict', 'N/A')}")
    summary = report.get("executive_summary", "N/A")
    print(f"   Summary: {summary[:200]}...")

    # Warnings
    warnings = data.get("warnings", [])
    print(f"\n⚠️  Pipeline Warnings: {len(warnings)}")
    for w in warnings:
        print(f"   [{w.get('severity')}] {w.get('code')}: {w.get('message', '')[:100]}")

    print("\n" + "=" * 60)
else:
    print(f"\n❌ FAILED. Error: {response.text[:500]}")

# Cleanup
os.remove(pdf_path)
print(f"\n🧹 Cleaned up {pdf_path}")
