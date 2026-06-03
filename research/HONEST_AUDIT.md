# P.R.I.S.M. — Brutally Honest Technical Audit

## Date: April 23, 2026

> This document pulls no punches. Every weakness, every bug, every questionable
> design decision is listed here. If we want to build the BEST plagiarism
> detection system, we must first understand where the current one is broken.

---

## 🔴 CRITICAL BUGS (Must Fix Before Any Research)

### Bug 1: Idea Triplet Extraction Is Broken
**File:** `backend/services/source_tracer.py`, line 25
```python
nlp = spacy.load("en_core_web_sm", disable=["ner", "parser"])
```
**Problem:** The parser is DISABLED, but `_extract_triplets()` at line 68-83 
relies on dependency parsing (`token.dep_`, `token.lefts`, `token.rights`) 
to extract Subject-Verb-Object triplets. Without the parser, `dep_` returns 
empty strings, `lefts` and `rights` yield nothing.

**Impact:** **The entire Idea Triplet system is non-functional.** It always 
returns an empty set. The "+6% per triplet" boost NEVER fires. Every claim 
about anti-Quillbot resistance in the README is currently false.

**Fix:** 
```python
nlp = spacy.load("en_core_web_sm", disable=["ner"])  # Keep parser enabled
```

### Bug 2: Semantic Weight Indexing Assumes No Column Filtering
**File:** `backend/services/clustering.py`, line 138-139
```python
if scaled_features.shape[1] >= 11:
    scaled_features[:, 8:11] *= 0.20
```
**Problem:** Earlier at lines 114-117, zero-variance columns are REMOVED 
from the matrix. After filtering, column indices shift. Index 8,9,10 may 
no longer correspond to semantic features — they could be structural features 
that got reindexed. The 0.20 weight could be applied to the wrong features.

**Impact:** The semantic down-weighting is unreliable. In some documents, 
it may accidentally down-weight structural features instead of semantic ones.

---

## 🟡 SERIOUS DESIGN WEAKNESSES

### Weakness 1: Yule's K at Paragraph Level Is Scientifically Unreliable
**Evidence:** Published research (Grieve 2007, confirmed by our web research) 
shows that Yule's K requires **2000-5000 words** for stable measurement. 
A typical paragraph has 50-150 words. At this scale, Yule's K has:
- Extremely high variance
- Poor discriminative power
- Heavy topic dependency (captures WHAT was written, not HOW)

**Recommendation:** Keep Yule's K but:
1. **Honestly report** its instability at paragraph level in the paper
2. Run ablation study to measure its actual contribution
3. Consider computing it over sliding windows of 3-5 paragraphs instead
4. Add character n-gram features (proven most effective for short text stylometry)

### Weakness 2: Burstiness Threshold (0.30) Is Arbitrary and Contested
**Evidence:** Multiple 2024-2025 studies show burstiness has:
- High false positive rate for non-native English speakers
- High false positive rate for technical/mathematical writing
- Modern LLMs (GPT-4, Claude) can mimic human-like burstiness when prompted
- Not validated on any standard dataset

**The 0.30 threshold was picked without empirical justification.**

**Recommendation:** 
1. Validate on a labeled human-vs-AI corpus (minimum 200 samples)
2. Plot ROC curve, find optimal threshold via Youden's J statistic
3. Report AUC, sensitivity, specificity honestly
4. Likely need to RAISE the threshold or make it per-domain adaptive

### Weakness 3: HDBSCAN May Be The Wrong Algorithm
**Evidence:** Research shows HDBSCAN is designed for CLUSTERING (grouping 
similar items together), NOT for CHANGE POINT DETECTION (finding where a 
sequence changes). Stitched plagiarism is fundamentally a sequential problem:

- Paragraph 1: Author A ← detectable ORDER
- Paragraph 2: Author A
- Paragraph 3: Author B ← BOUNDARY HERE
- Paragraph 4: Author B
- Paragraph 5: Author A ← BOUNDARY HERE

HDBSCAN ignores paragraph order entirely. It treats paragraph [1] and [5] 
as the same because they have similar features, even though they're separated 
by Author B's text.

**Better alternatives to test:**
1. **Change Point Detection** (PELT algorithm, Binary Segmentation) — designed 
   specifically for detecting shifts in sequential data
2. **Sliding Window + Distance** — compare adjacent window features, flag 
   when distance exceeds threshold
3. **HDBSCAN + Sequential Post-Processing** — use clusters but add order-aware 
   boundary refinement

**Recommendation:** Keep HDBSCAN as one approach, but implement Change Point 
Detection as a second engine and compare them empirically. The paper should 
honestly report which works better.

### Weakness 4: Only 8 Structural Features — Missing Proven Features
**Evidence:** Research consensus shows the most effective stylometric features 
for short text are:

| Feature | Status in PRISM | Research Effectiveness |
|:---|:---:|:---:|
| Character 3-grams | ❌ MISSING | ⭐⭐⭐⭐⭐ Best for short text |
| Function word frequencies (top 50) | ❌ MISSING | ⭐⭐⭐⭐⭐ Highly effective |
| Punctuation patterns | ❌ MISSING | ⭐⭐⭐⭐ Very effective |
| Hapax legomena ratio | ❌ MISSING | ⭐⭐⭐ Good |
| Avg sentence length | ✅ Present | ⭐⭐⭐ Good |
| Avg word length | ✅ Present | ⭐⭐ Moderate |
| POS ratios | ✅ Present | ⭐⭐⭐ Good |
| Passive voice % | ✅ Present | ⭐⭐ Moderate |
| Yule's K (paragraph) | ✅ Present | ⭐ Weak at paragraph scale |
| Burstiness | ✅ Present | ⭐⭐ Contested |

We're missing the TOP features and relying on weaker ones.

### Weakness 5: PCA to 3 Dimensions Loses Information
**Problem:** OpenAI embeddings are 1536-dimensional. PCA reducing to only 3 
dimensions likely loses the vast majority of style-relevant information. 
The explained variance ratio is probably <5%.

**Recommendation:**
1. Record and report `pca.explained_variance_ratio_`
2. Test PCA to 5, 10, 20, 50 dimensions
3. Test UMAP as an alternative to PCA (preserves local structure better)
4. Consider using a LOCAL embedding model (all-MiniLM-L6-v2, 384 dims) 
   which is cheaper and can be tested with different reduction strategies

### Weakness 6: The Fallback Scoring System Uses Arbitrary Weights
**File:** `backend/services/report_generator.py`, lines 138-186
```python
score -= noise * 8.0         # Why 8.0? Not justified
score -= (estimated_authors - 1) * 1.5  # Why 1.5?
score -= 6.0  # AI penalty — why 6.0?
```
Every weight in the rule-based scoring engine is a magic number with no 
empirical justification. The system claims "integrity score 0-10" but the 
scoring function wasn't fit to any ground truth data.

### Weakness 7: Benchmark Claims Are Based on N=2
**Current claim:** "100% accuracy, 0.91 confidence"
**Reality:** This is based on exactly 2 test documents. This is not 
statistically meaningful. You could flip a coin and sometimes get 100%.

A real benchmark needs:
- Minimum N=100 documents
- Cross-validation
- Statistical significance tests
- Comparison against published systems

---

## 🟢 GENUINE STRENGTHS (What's Actually Good)

### Strength 1: The Hybrid Architecture Concept
The idea of "math provides proof, AI provides explanation" is genuinely 
novel and practically useful. Separating deterministic evidence from 
AI interpretation is the RIGHT design.

### Strength 2: Citation Temporal Forensics
Using citation year distribution as an independent evidence stream is 
creative and novel. No other system does this. However, it needs 
validation on documents that actually have citations.

### Strength 3: Enterprise-Grade Degradation
The fallback chain and PipelineContext warning system is excellent 
engineering. Every stage can fail without crashing the system. This is 
production-quality design and worth highlighting.

### Strength 4: Zero-Training Approach
Not requiring labeled training data or a reference corpus is a genuine 
advantage over supervised systems. This is a real contribution.

### Strength 5: Multi-Stage Evidence Fusion
Having 7 stages that each contribute independent evidence is architecturally 
sound, even if individual stages have weaknesses. The framework is right — 
the individual components need strengthening.

---

## Summary: What the Research Must Do

The research paper cannot just evaluate the current system and claim it's 
great. An honest paper must:

1. **Fix the bugs** (triplet extraction, semantic weight indexing)
2. **Add missing features** (character n-grams, function word profiles)
3. **Implement alternatives** (Change Point Detection alongside HDBSCAN)
4. **Validate every threshold** (burstiness, semantic weight, triplet boost)
5. **Test on real datasets** (100+ documents, not 2)
6. **Report failures honestly** (where does the system fail?)
7. **Compare against real baselines** (not just TF-IDF)
8. **Use proper statistical tests** (significance, confidence intervals)

The goal is NOT to prove P.R.I.S.M. is perfect. The goal is to build the 
best possible system, honestly evaluate it, and report what works, what 
doesn't, and why.
