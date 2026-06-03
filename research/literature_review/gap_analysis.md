# P.R.I.S.M. Research — Honest Gap Analysis

## Date: April 23, 2026

> This is the HONEST version. No marketing, no inflated claims.
> Every statement here is what we can defend under peer review.

---

## 1. What P.R.I.S.M. Attempts to Solve

**Stitched plagiarism** = assembling a paper by splicing paragraphs from 
multiple sources, potentially paraphrasing each. This is:
- **Different from copy-paste** (which Turnitin catches)
- **Different from AI generation** (which GPTZero targets)
- **A real, growing problem** in academia

P.R.I.S.M. attempts to detect this through internal stylometric analysis 
— asking "does this document read like it was written by one person?"

## 2. Honest Assessment: Where P.R.I.S.M. Stands vs SOTA

### What SOTA Actually Looks Like (2024-2025)

| System | Approach | Performance |
|:---|:---|:---|
| PAN 2025 winners | Semantic embeddings (Linq-Embed-Mistral) | ~0.8 recall, ~0.5 precision |
| PAN SCD winners | Transformer + LoRA fine-tuning | F1 ~0.7 on paragraph boundaries |
| Commercial (Turnitin) | Massive reference corpus | High on verbatim, 0 on paraphrased |
| GPTZero | Perplexity/burstiness | Only AI detection, not stitching |
| IISAS systems | BERT + SVM | Need labeled training data |

### Where P.R.I.S.M Currently Is (Honest)

| Aspect | Status | Honest Assessment |
|:---|:---:|:---|
| **Accuracy** | ❓ UNKNOWN | Tested on only 2 documents. Not measurable. |
| **Feature engineering** | 🟡 Partial | Missing the most effective features (char n-grams, function words). Has features with known limitations (Yule's K at paragraph level). |
| **Clustering algorithm** | 🟡 Questionable | HDBSCAN ignores paragraph order — a fundamental limitation for sequential change detection. |
| **AI detection (burstiness)** | 🔴 Unvalidated | Threshold is arbitrary. Research shows high false positive rates. |
| **Idea Triplets** | 🔴 BROKEN | Bug discovered: spaCy parser disabled, triplets always empty. |
| **Citation forensics** | 🟢 Novel | Genuinely unique approach, but only works on papers WITH citations. |
| **Architecture** | 🟢 Sound | Multi-stage evidence fusion and graceful degradation are well-designed. |
| **Deployment readiness** | 🟢 Strong | FastAPI, zero-build frontend, works offline — excellent engineering. |

## 3. Novelty Claims — Honest Assessment

### Claim 1: Hybrid Feature Space
**What we claim:** Fusing 8 structural stylometric features with 3 PCA-reduced 
semantic embeddings in an 11-dim space for HDBSCAN clustering.

**Honest assessment:** The IDEA has merit. But:
- Missing the most effective features (char n-grams)
- PCA to 3 dims likely loses most information
- No evidence this specific combination outperforms simpler approaches
- **VERDICT: Needs empirical validation. Could be a real contribution IF we 
  improve the features and prove it works.**

### Claim 2: HDBSCAN Noise as Anomaly Proxy
**What we claim:** Cluster -1 = stylistically foreign paragraph.

**Honest assessment:** 
- Clever idea, but HDBSCAN doesn't respect paragraph order
- A paragraph with unusual TOPIC (not unusual STYLE) could trigger false positives
- The semantic weight (0.20) was supposed to prevent topic-based separation, 
  but due to Bug #2, may not be applied correctly
- **VERDICT: May work, but Change Point Detection should be compared directly.**

### Claim 3: Idea Triplet Anti-Paraphraser
**What we claim:** SVO triplets defeat AI paraphrasers.

**Honest assessment:**
- **Currently 100% broken.** Parser is disabled. Returns empty set.
- AFTER fixing the bug, the concept has real merit — SVO structure is preserved 
  through paraphrasing
- The +6% boost per triplet is an arbitrary number
- **VERDICT: Fix the bug, then honestly test if it helps.**

### Claim 4: Citation Temporal Forensics
**What we claim:** Comparing citation year distributions between HDBSCAN 
clusters can detect stitched content.

**Honest assessment:**
- Genuinely novel — no other system does this
- Only works on papers with inline citations (not all papers have them)
- Depends on HDBSCAN clustering being correct (circular dependency)
- **VERDICT: Real contribution. Needs validation but conceptually sound.**

### Claim 5: Burstiness-Based AI Detection
**What we claim:** Coefficient of Variation < 0.30 = AI-generated.

**Honest assessment:**
- Research (2024-2025) explicitly warns against relying on burstiness
- High false positive rate for: non-native speakers, technical writing, 
  certain genres
- Modern LLMs can mimic human burstiness when prompted
- We haven't validated on ANY labeled dataset
- **VERDICT: Weakest claim. Must present with heavy caveats or remove entirely 
  if validation fails.**

### Claim 6: Zero-Training Approach
**What we claim:** No labeled data or reference corpus needed.

**Honest assessment:**
- This is genuinely true and a real advantage
- Does create limitations (can't learn from known examples)
- **VERDICT: Legitimate contribution. Easy to defend.**

## 4. What the Research Must Address

### Must Show (or Honestly Admit Can't)
- [ ] Does the improved feature space beat the original?
- [ ] Does HDBSCAN or Change Point Detection work better for boundary detection?
- [ ] Are Idea Triplets useful AFTER the bug fix?
- [ ] What is the actual burstiness false positive rate?
- [ ] Does the system generalize across academic domains?
- [ ] What F1 score do we achieve on a real dataset (N≥100)?

### Must Honestly Report
- Where the system fails and why
- Which features contribute and which don't (ablation)
- Comparison against at least 2 published baselines
- All hyperparameters and their sensitivity
- Runtime characteristics and scalability limits

### Must NOT Claim
- "100% accuracy" (based on N=2 — meaningless)
- "Defeats all AI paraphrasers" (not proven, triplets were broken)
- "Zero false positive rate" (not validated on diverse corpus)
- "Superior to all existing tools" (haven't compared against SOTA)

## 5. The Path to Genuine Excellence

If we do this research honestly, the paper's contributions become:

1. **An improved hybrid feature space** — adding what's actually proven effective 
   (char n-grams, function words) to what we already have
2. **A fair comparison of HDBSCAN vs Change Point Detection** — answering a 
   real open question in the field
3. **The first empirical evaluation of Idea Triplets** (after fixing the bug) — 
   novel anti-paraphraser technique
4. **Citation temporal forensics validation** — a genuinely unique evidence stream
5. **An honest assessment of burstiness** — contributing to the ongoing debate 
   about AI detection reliability
6. **A complete, reproducible evaluation framework** — enabling future research

This is a stronger paper than "our system is perfect" because it contributes 
KNOWLEDGE to the field, not just a product demo.
