# PRISM — Research-Grade Diagnostic Report

---

## 🔴 TOP 3 MOST LIKELY ROOT CAUSES (ranked by likelihood)

**1. The embedding similarity detector is carrying the system; stylometric features are nearly non-discriminative.** Your ablation data proves this: removing any individual stylometric feature (or entire groups like punctuation, hapax) causes **zero F1 change**. 20 of 27 features have f1_drop = 0.0. The best system (`fusion3`, F1=0.397) gets almost all of its signal from MiniLM embedding similarity (F1=0.374 standalone). Your 27-dimensional stylometric feature vector is contributing roughly **+0.023 F1 over embeddings alone** — essentially noise. The feature engineering layer is broken at a fundamental level.

**2. The paragraph-level granularity is too fine for reliable stylometric measurement.** Your own HONEST_AUDIT.md documents that PAN 2023 paragraphs have a median of 41 words, and 61% produce all-zero feature vectors. Even with windowing (target=100 words), Yule's K needs 2000–5000 words for stability (Grieve 2007), hapax legomena ratio is meaningless below ~500 words, and your 10 hardcoded character trigrams are too few to form a discriminative distribution at paragraph scale. You're computing features at a granularity where the statistical estimators have unacceptable variance.

**3. The system lacks a proper authorship verification model — it's doing unsupervised boundary detection as a proxy.** PRISM uses HDBSCAN + PELT + embedding similarity to find where style "changes" within a single document, but never actually learns what an author's style *is*. No contrastive learning, no author embeddings, no pairwise verification model. PAN@CLEF top systems (Tavan & Najafi 2024, Halvani et al. 2023) all use **learned similarity functions** (fine-tuned transformers, contrastive training). PRISM is trying to solve a supervised problem with unsupervised methods.

---

## LAYER 1 — DATA PIPELINE

### 1.1 Preprocessing Decisions That Destroy Stylometric Signal

| Operation | Signal Destroyed | Recommendation |
|:---|:---|:---|
| **Lowercasing** (line 96, `feature_engine.py`: `token.text.lower()`) | Destroys capitalization patterns — a proven author marker (Stamatatos 2009). Unusual capitalization, ALL-CAPS tendencies, sentence-initial patterns are lost. | Keep original case for character n-gram extraction. Lowercase only for word-frequency features. |
| **`token.is_alpha` filtering** (line 96) | Strips all punctuation, numbers, and special characters before word-level analysis. Punctuation is later extracted separately from raw text, but **mixed alphanumeric tokens** (e.g., "COVID-19", "v2.0") are lost entirely. | Use a two-pass approach: extract character-level features from raw text, word-level from filtered tokens. |
| **spaCy tokenization with `en_core_web_sm`** | The `sm` model has ~96% POS accuracy — 4% error rate at paragraph level means 2–4 mistagged tokens per paragraph, introducing noise into POS ratio features. | Upgrade to `en_core_web_trf` (transformer-based, ~98% accuracy) for research evaluation. Keep `sm` for production speed. |
| **No whitespace normalization** | Multiple spaces, tabs, PDF extraction artifacts are passed through. Character n-grams computed on raw PDF text capture formatting noise, not author style. | Normalize whitespace to single spaces before character n-gram extraction. Preserve original for punctuation features. |

> [!CAUTION]
> **Critical finding:** Your character trigram extraction at [feature_engine.py:301](file:///d:/prism2/P.R.I.S.M/backend/services/feature_engine.py#L301) lowercases the text (`text_lower = text.lower()`) but your TOP_CHAR_TRIGRAMS include space-prefixed trigrams like `" th"`, `" an"`, `" in"`. These are being computed correctly, but the lowercasing means you're losing case-sensitive n-grams like `" Th"` vs `" th"` which are strong authorship markers (initial capitalization patterns).

### 1.2 Document Length Effects

**Known literature thresholds:**

| Minimum Length | Source | What It Enables |
|:---|:---|:---|
| **~100 words** | Luyckx & Daelemans (2008) | Bare minimum for any stylometric classification; character n-grams only |
| **~500 words** | Stamatatos (2009), PAN baselines | Reliable function word distributions, POS ratios |
| **~1,000 words** | Koppel et al. (2012) | Stable lexical richness measures (TTR, hapax) |
| **2,000–5,000 words** | Grieve (2007) | Reliable Yule's K, vocabulary richness metrics |
| **10,000+ words** | PAN@CLEF 2020 guidelines | Full author profiling with high confidence |

**Your current thresholds:** TIER_SKIP=20 words, TIER_REDUCED=50 words, FULL=100 words. Your "full" threshold is at the **absolute minimum** for any stylometric analysis. At 100 words:
- Yule's K has coefficient of variation > 50% (effectively random)
- Hapax legomena ratio is dominated by sample size artifact
- Function word distribution (only 5 words: "the", "of", "and", "to", "in") is too sparse to be stable

**Checklist:**
- [ ] Log the distribution of paragraph word counts in your evaluation data
- [ ] Compute per-feature coefficient of variation at 50, 100, 200, 500 word thresholds
- [ ] Raise TIER_REDUCED to at least 100, FULL to at least 200
- [ ] Your window aggregator (target_words=100) should target 250–500 words

### 1.3 Genre/Domain Imbalance

**How cross-genre testing degrades performance (PAN findings):**

- PAN 2023 specifically tested **cross-discourse type** verification (written vs. spoken text from the Aston 100 Idiolects Corpus). Performance dropped 15–25% compared to within-genre testing across all participants.
- Features most affected by genre: sentence length distributions (academic vs. fiction), punctuation patterns (legal vs. informal), passive voice percentage (scientific vs. narrative). These are exactly the features PRISM relies on.
- Character n-grams are the **most genre-robust** feature (Stamatatos 2013), which is why PAN top systems rely heavily on them.

**For PRISM-Bench stratification:**
- Minimum 5 genres: academic, fiction, news/journalism, informal/blog, technical
- Each genre needs both genuine and stitched pairs
- Test matrix: train-on-genre-A/test-on-genre-B for every pair
- Report per-genre and cross-genre results separately

### 1.4 Label Noise in Verification Tasks

**Systemic failure modes from mislabeled pairs:**

1. **Same-author topic change mislabeled as different-author:** When a genuine author shifts topic dramatically (e.g., methodology → discussion), PRISM's embedding similarity drops sharply and it registers a false boundary. Your system literally cannot distinguish "same author, different topic" from "different author."
2. **Ghost-writing with style mimicry:** If a ghost-writer deliberately imitates the nominal author's style, the ground truth says "different author" but features say "same" — training on these cases pushes the model toward content-based rather than style-based discrimination.
3. **Self-plagiarism labeled as plagiarism:** Reused text by the same author has identical style but is labeled as plagiarism, teaching the model the wrong signal.

### 1.5 Train/Val/Test Leakage Vectors

**Authorship-specific leakage (not generic ML leakage):**

| Leakage Type | How It Happens | Detection Method |
|:---|:---|:---|
| **Author overlap** | Same author appears in train and test sets → model memorizes author fingerprints rather than learning general stylometric patterns | Verify author IDs are disjoint across splits. Group-by-author splitting. |
| **Temporal bleed** | Training on 2020 papers, testing on 2019 → future knowledge leaks | Ensure temporal ordering: train ≤ val ≤ test by publication date |
| **Topic bleed** | Same research topic in train and test → model learns topic, not style | Check that specific subtopics don't span splits. Topic-stratified splitting. |
| **Document pair leakage** | A appears in pair (A,B) in train and (A,C) in test | Verify that no individual document appears in more than one split |

> [!IMPORTANT]
> Your current evaluation in [run_evaluation.py](file:///d:/prism2/P.R.I.S.M/research/experiments/run_evaluation.py) has **no train/test split at all** — it runs detectors directly on all 395 documents. This is acceptable for unsupervised methods (HDBSCAN, PELT, embedding similarity don't train), but if you add any supervised component, you need proper splitting.

### 1.6 PRISM-Bench Construction

**Positive:Negative pair ratio:**
- PAN standard: 1:1 (50% same-author, 50% different-author pairs)
- For verification tasks, 1:1 is critical — skewed ratios inflate AUC artificially
- For your boundary detection task: include ~50% single-author documents (negative class) and ~50% multi-author/stitched documents (positive class)

**Hard negative construction:**
- **Same author, different topic:** Author A writes about topic X and topic Y → pair them. The style should be similar but topic changes. If PRISM detects a boundary here, it's a false positive caused by topic sensitivity.
- **Same author, different time period:** Author's early vs. late work — style drift without authorship change.
- **Different author, same topic:** Two NLP researchers writing about transformers — topic is identical but style differs. If PRISM misses this, it's relying on content not style.
- **Different author, style-matched:** Select author pairs with similar sentence length distributions and vocabulary levels. This tests whether PRISM detects fine-grained stylistic differences.

---

## LAYER 2 — FEATURE ENGINEERING

### 2.1 Per-Group Analysis

#### (1) Lexical Richness: Yule's K, Hapax Legomena Ratio

**Failure modes:**
- **Yule's K at paragraph level is scientifically invalid.** Your HONEST_AUDIT correctly identifies this. At 50–150 words, Yule's K has variance so high it cannot discriminate authors. The formula `K = 10000 * (M2 - M1) / M1²` is dominated by M1 (total words) at small sample sizes.
- **Hapax legomena ratio is a function of document length, not author style,** below ~500 words (Baayen 2001). At 100 words, ~50% of words appear exactly once regardless of author — this is a statistical property of natural language, not a stylometric signal.
- **Both features are heavily topic-dependent.** Technical vocabulary (jargon) inflates hapax counts; simple vocabulary deflates Yule's K. Neither is isolated from content.

**Ablation evidence from your data:** Removing Yule's K → F1 drop = 0.0. Removing hapax → F1 drop = 0.0. **Neither feature contributes anything.**

**Length normalization sensitivity:** Both are the *most* sensitive to document length of all your features. Yule's K has a known 1/N bias (Holmes 1992).

**Fix:** Compute both over sliding windows of 500+ words if you keep them. Better: replace with **Simpson's Diversity Index** which stabilizes faster (at ~200 words).

#### (2) Syntactic Patterns: POS ratios, passive voice, sentence length, burstiness

**Failure modes:**
- **POS ratios with `en_core_web_sm` have ~4% error** — at 100 tokens, that's 4 wrong tags. For rare categories (SCONJ, passive constructions), this error rate approaches or exceeds the base rate.
- **Passive voice detection** at [feature_engine.py:277-282](file:///d:/prism2/P.R.I.S.M/backend/services/feature_engine.py#L277-L282) relies on `nsubjpass`/`auxpass` dep labels — these are **Universal Dependencies v1 labels that spaCy v3 doesn't produce reliably.** The morphological fallback `morph.get("Voice") == ["Pass"]` partially compensates but `en_core_web_sm` has poor morphological feature coverage. Your passive voice count is systematically undercounted.
- **Burstiness coefficient** (CV of sentence lengths) is contested as a stylometric marker. Your ablation shows F1 drop = 0.0 when removed.

**Topic/content contamination:**
- Sentence length is highly genre-dependent (academic: 25–35 words, fiction: 12–18, informal: 8–15). This is genre signal, not author signal.
- Preposition ratio varies with content type (spatial descriptions → high, abstract arguments → lower).

**Missing syntactic features (used by PAN top systems):**
- Syntactic tree depth distribution
- Dependency relation n-grams (dep trigrams: nsubj-ROOT-dobj patterns)
- Clause complexity (subordinate clause count per sentence)
- Sentence-initial word/POS patterns

#### (3) Character N-grams

**Failure modes in your implementation:**

> [!WARNING]
> **Critical design flaw:** You use only 10 hardcoded character trigrams: `" th", "the", "he ", "ing", " an", "nd ", " in", "ion", "ed ", " of"`. These are the **most common English trigrams** — they capture English language frequency, not author style. Every English author produces roughly the same distribution of these trigrams. PAN@CLEF winning systems use the **top 1,000–5,000 most frequent character n-grams** (2–5 grams) computed *from the training corpus*, then use TF-IDF or relative frequency as features. 10 fixed trigrams have essentially zero discriminative power.

**What "good" looks like:**
- Stamatatos (2013): Character 4-grams, top 2,500 by frequency, with TF-IDF weighting → best single feature group across PAN competitions
- Koppel & Winter (2014): Character 3–5 grams, top 2,000, cosine similarity between author profiles
- PAN 2023 top systems: 1,000–3,000 character n-grams, normalized by document length

**Your ablation confirms the problem:** Removing all 10 char trigrams → F1 drops from 0.22 to 0.184 (a drop of 0.036). But this group has the *most* features (10) and the least per-feature impact. The trigrams are noisy, not discriminative.

**Fix (highest priority):**
1. Compute ALL character 3-grams from the document
2. Select top 500–2,000 by corpus frequency or mutual information
3. Represent as TF-IDF vector, not raw frequency
4. Add character 4-grams and 5-grams (4-grams are the sweet spot per Stamatatos 2013)

#### (4) Punctuation/Formatting

**Failure modes:**
- Comma rate, semicolon rate, dash rate are computed per-sentence, which is fine for normalization
- But at paragraph level (5–10 sentences), semicolons have count 0 in >80% of paragraphs → extremely sparse, zero-variance, useless for discrimination
- **Missing:** Quotation mark usage, parenthesis patterns, ellipsis usage, exclamation/question mark ratios, colon usage — all proven more discriminative than semicolons for authorship

**Your ablation:** Removing all punctuation features → F1 drop = 0.0. Zero contribution.

#### (5) Function Word Distributions

**Failure modes:**
- You use only 5 function words: `"the", "of", "and", "to", "in"`. The literature uses **50–200 function words** (Koppel & Schler 2004, Argamon 2007). Five is insufficient.
- "The", "of", "and" are so frequent that their distribution is nearly uniform across authors — they capture English, not author style.
- At paragraph level (50–150 words), each function word appears 0–5 times. The frequency estimates have enormous sampling variance.

**Missing high-signal function words:**
- Modals: "would", "could", "should", "might"
- Discourse markers: "however", "therefore", "moreover", "furthermore"
- Personal pronouns (disaggregated): "I", "we", "they", "he", "she" — individually, not as a single ratio
- Articles and determiners: "a", "an", "this", "that"
- Conjunctions: "but", "because", "although", "while"

### 2.2 How to Combine Feature Groups

**Current problem: scale dominance and zero-variance features.**

Your [hdbscan_detector.py](file:///d:/prism2/P.R.I.S.M/backend/services/hdbscan_detector.py#L68-L81) does StandardScaler + variance-based downweighting. But:

1. **StandardScaler on zero-variance columns** (which you have many of, from sparse punctuation and hapax at paragraph level) produces NaN or division by zero. Your `_VARIANCE_FLOOR = 1e-6` prevents crashes but creates artificially large z-scores for tiny fluctuations in near-constant features.

2. **No redundancy removal.** `char3_th`, `char3_the`, `char3_he` are highly correlated (they literally overlap as substrings). `fw_of` and `char3_of` measure the same signal. Redundant features inflate the effective dimensionality and dilute discriminative features.

**Recommended pipeline:**
1. Remove features with near-zero variance (σ² < 0.001 across the corpus, not per-document)
2. Remove features with |Pearson correlation| > 0.90 (keep one from each correlated pair)
3. Apply **RobustScaler** (median/IQR-based) instead of StandardScaler — more robust to paragraph-level outliers
4. Apply PCA or Truncated SVD retaining 95% variance for dimensionality reduction
5. Weight feature groups by their **individual discriminative power** (measure via cross-validated AUC on a held-out labeled set)

**Per-sentence vs per-paragraph vs per-document computation:**
- **Per-sentence:** Punctuation features, sentence length, POS ratios (then aggregate to paragraph via mean and std)
- **Per-paragraph:** Character n-grams, function word distributions (need enough text for stable estimates)
- **Per-document or per-window (500+ words):** Yule's K, hapax ratio, vocabulary richness measures

---

## LAYER 3 — CORE DETECTION ENGINE

### 3.1 Classical ML Path: Why Your Current Approach Fails

**Your system doesn't use an SVM or Random Forest at all.** It uses unsupervised methods: HDBSCAN (density clustering) and PELT (change-point detection). This is a fundamental architectural problem.

**Why unsupervised fails for stylometric tasks:**

1. **No decision boundary is learned.** HDBSCAN clusters paragraphs by feature similarity, but "similar" in feature space doesn't mean "same author." Two authors can have similar sentence lengths and vocabulary levels. Without labeled examples, the algorithm cannot learn which feature *differences* matter for authorship.

2. **HDBSCAN ignores document order** (correctly noted in your HONEST_AUDIT). A-B-A authorship pattern gets clustered as {A, A} + {B}, losing the boundary positions.

3. **PELT with penalty=1.0 is over-sensitive on noisy features** (your own results: pelt_rbf F1=0.021, worse than random at 0.055). The feature noise drowns the true signal. PELT detects "change points" that are actually statistical fluctuation in non-discriminative features.

**What the literature recommends for classical ML on stylometric verification:**

| Component | Recommendation | Source |
|:---|:---|:---|
| Classifier | **SVM with RBF kernel** | PAN 2019–2023 consensus; handles high-dimensional sparse features well |
| Regularization | C = 1.0–10.0, γ = scale | Grid search on held-out author pairs |
| Feature input | **Pairwise difference/similarity vector**, not raw features | Koppel & Schler (2004), Halvani et al. (2017) |
| Training paradigm | **Siamese / contrastive** | Learn d(author_A, author_B) from positive/negative pairs |

**Key insight:** The SVM should operate on a **difference vector** between two text samples — not on features of individual paragraphs. For each pair (text_A, text_B), compute features independently, then take |feature_A - feature_B| as input. The SVM learns which feature differences discriminate same-author from different-author. This is the Unmasking approach (Koppel & Schler 2004) that dominated PAN for years.

### 3.2 Transformer Path: Model Selection (2024–2025)

**Best pretrained models for authorship verification tasks:**

| Model | Task Fit | Key Finding |
|:---|:---|:---|
| **DeBERTa-v3-large** | ⭐⭐⭐⭐⭐ Best general-purpose | Fine-tuned DeBERTa-v3 achieved SOTA on PAN 2023 cross-discourse verification. Superior to BERT/RoBERTa on stylistic discrimination. |
| **Longformer / LED** | ⭐⭐⭐⭐ Long documents | 4096+ token context window handles full documents without truncation. Critical for stylometric tasks where truncation destroys style signal. |
| **Mistral-7B (fine-tuned)** | ⭐⭐⭐⭐ PAN 2024 winner | Tavan & Najafi's winning system fine-tuned Mistral + Llama 2 ensemble. Best for human-vs-AI discrimination. |
| **all-MiniLM-L6-v2** (your current) | ⭐⭐ Weak baseline | General-purpose sentence embedding model. Not trained for stylistic similarity. Captures **semantic similarity** (topic), not **stylistic similarity** (authorship). |

> [!IMPORTANT]
> **Your MiniLM model is detecting topic changes, not style changes.** MiniLM is trained to embed sentences with similar *meaning* closely. When it detects a "boundary," it's finding where the *topic* shifts (e.g., methodology → results). A true authorship boundary between two paragraphs on the *same* topic would be invisible to MiniLM. This explains why `embed_sim` (F1=0.374) outperforms stylometric features — your evaluation data probably has topic shifts correlated with author changes. **This is a confound, not a feature.**

**Fine-tuning strategy recommendation:**

For **verification** (is this pair same-author?):
- **Contrastive learning (best):** Train on (anchor, positive, negative) triplets where anchor+positive are same-author, anchor+negative are different-author. Use **NT-Xent** or **SupCon** loss. This learns a stylistic embedding space.
- **Siamese classification:** Feed [CLS] embeddings from both texts through a learned comparator head. Cross-entropy loss on same/different labels.

For **attribution** (who wrote this?):
- **Classification head** on a fine-tuned transformer, one class per author. Only works for closed-set (known authors).

For **boundary detection** (your actual task):
- **Pairwise verification sliding window:** Run a trained verification model on every adjacent pair (paragraph_i, paragraph_i+1). Where the model says "different author," that's a boundary. This converts your boundary detection problem into a sequence of verification decisions.

### 3.3 Fusion Strategy

**Your current 3-way fusion** ([pipeline_orchestrator.py:364-452](file:///d:/prism2/P.R.I.S.M/backend/services/pipeline_orchestrator.py#L364-L452)) uses majority voting with fallback to embedding-only. Your eval shows fusion3 (F1=0.397) beats embed_sim alone (F1=0.374).

**Better fusion approaches:**

1. **Learned fusion (recommended for publication):** Train a meta-classifier (logistic regression or small MLP) that takes as input the confidence scores from each engine and outputs a boundary probability. Requires labeled boundary data for training, but yields better calibrated scores.

2. **Stacking with confidence weighting:** Instead of binary votes, weight each engine's vote by its standalone performance. Given your data: embed_sim gets weight 0.374, w_fused gets 0.215, everything else < 0.1. This approximation gives embedding ~3x the vote of stylometric methods.

3. **Cascaded filtering:** Use the cheap stylometric analysis as a first-pass filter (high recall, low precision), then run the expensive embedding analysis only on flagged regions. Reduces computation while preserving accuracy.

### 3.4 Decision Boundary Failure Modes

**Your system will collapse on unseen authors because it has no author model:**
- For seen authors (in training data): Can memorize individual author fingerprints
- For unseen authors (generalization): Must rely on general stylometric principles → your features don't capture these reliably

**Specific failure modes:**
1. **Genre shift:** Academic → informal text appears as "style change" even with single author
2. **Translation effects:** Non-native English speakers have higher stylistic variance → more false positives
3. **Collaborative writing:** Legitimate co-authorship appears as plagiarism
4. **Section-dependent style:** Abstract vs. Methods vs. Discussion have different stylistic profiles within the same author's paper

### 3.5 Confidence Calibration

**How to detect uncalibrated scores:**

Your current confidence is a categorical string ("high", "medium", "low") based on noise percentage thresholds at [hdbscan_detector.py:147-154](file:///d:/prism2/P.R.I.S.M/backend/services/hdbscan_detector.py#L147-L154). This is not a probability and cannot be calibrated.

**What a well-calibrated verification system produces:**
- P(same_author | text_A, text_B) ∈ [0, 1]
- Among all pairs where the model outputs P = 0.8, approximately 80% should truly be same-author
- Measured via **reliability diagram** (calibration curve): bin predictions by confidence, plot actual accuracy per bin
- **Brier score** < 0.2 for acceptable calibration; < 0.1 for good calibration

**To calibrate:**
1. Get raw model outputs (logits or distances)
2. Apply Platt scaling (logistic regression on held-out set) or isotonic regression
3. Evaluate calibration with Brier score and Expected Calibration Error (ECE)

---

## LAYER 4 — EVALUATION METHODOLOGY

### 4.1 Metrics PRISM Should Report

| Metric | Used In | What It Measures | Your Current Status |
|:---|:---|:---|:---|
| **AUC-ROC** | PAN 2024 (primary) | Discrimination ability across all thresholds | ❌ Not computed. Your benchmark endpoint only computes binary metrics. |
| **c@1** | PAN 2013–2023 (primary) | Modified accuracy rewarding abstention on uncertain cases: `c@1 = (1/n)(nc + nu × nc/n)` where nc = correct, nu = unanswered | ❌ Not computed. Your system has no abstention mechanism. |
| **F1** | PAN (secondary), your evaluation | Harmonic mean of precision/recall | ✅ Computed. Best result: F1=0.397 (fusion3). |
| **Brier score** | PAN 2024 | Calibration quality: mean squared error of probability predictions | ❌ Not computed. Requires probabilistic output. |
| **Boundary F1** | Your custom metric | Boundary detection with tolerance window | ✅ Computed with tolerance=1. |
| **Plagdet** | PAN text reuse (2010–2015) | F1 / log2(1 + granularity) penalizing over-detection | ✅ Implemented in evaluate_metrics.py but not used in evaluation runs. |

> [!IMPORTANT]
> **c@1 is the PAN primary metric for verification and PRISM must support it.** c@1 rewards systems that say "I don't know" on ambiguous cases rather than guessing wrong. Your current system always outputs a binary decision with no confidence-based abstention. **Add a threshold-based abstention mechanism:** if confidence < τ, output "unanswered" (0.5). Tune τ on validation data to maximize c@1.

### 4.2 What PAN Evaluation Penalizes

**PAN@CLEF evaluation protocol specifics:**

1. **c@1 penalizes false confidence:** If your system answers everything (no abstentions), it gets credit only for correct answers and is penalized for all mistakes. A system that correctly abstains on 50% of hard cases can outscore a system that answers everything at 70% accuracy.

2. **AUC-ROC is threshold-independent:** Your current threshold (noise_percentage > 60% → low confidence) is irrelevant to AUC. What matters is the *ranking* — do genuinely different-author pairs get higher anomaly scores than same-author pairs?

3. **F1 with tolerance=1 is generous.** PAN boundary detection uses exact matching (tolerance=0) for segment-level evaluation. Your tolerance=1 inflates your metrics. Report both tolerance=0 and tolerance=1.

4. **Granularity penalty (Plagdet):** If one plagiarized passage is split into 5 detected fragments, Plagdet divides F1 by log2(6) ≈ 2.58. Your HDBSCAN noise labeling likely causes over-fragmentation.

### 4.3 Closed-Set vs Open-Set Evaluation

**Closed-set:** Test authors were seen during training. Model can memorize author fingerprints. Typical accuracy: 90%+. **This overstates real-world performance.**

**Open-set:** Test authors are entirely new — never seen during training. Model must generalize stylometric principles. Typical accuracy drops 15–40% from closed-set.

**Why this matters for PRISM:**
- Your system is currently unsupervised, so this distinction doesn't apply directly
- But if you add any supervised component (SVM, fine-tuned transformer), you MUST evaluate in open-set mode
- **Split by author, not by document.** All documents from author X must be in the same split.

**How to detect author memorization:**
1. Train on authors {A, B, C, ..., X}
2. Test on held-out documents from authors {A, B, C} (closed-set) vs. new authors {Y, Z} (open-set)
3. If closed-set accuracy >> open-set accuracy, the model is memorizing, not generalizing
4. **Target:** Open-set performance within 5–10% of closed-set

### 4.4 Memorization vs Generalization Detection

Beyond open-set testing:
- **Feature importance analysis:** If the model relies heavily on lexical features (specific word choices) rather than structural features (syntax patterns), it's likely memorizing topic/author vocabulary
- **Cross-domain evaluation:** Train on academic, test on fiction. If performance collapses, the model learned genre, not author style.
- **Adversarial paraphrasing:** Take known-author text, paraphrase it with GPT-4. If the model can still attribute it, it's learning deep style. If it fails, it's learning surface patterns.

### 4.5 Ablation Studies Required for ACL SRW Publication

| Ablation | Purpose | How |
|:---|:---|:---|
| **Feature group ablation** ✅ | Show contribution of each feature group | Remove one group, re-run. You've done this but results show almost everything has F1 drop = 0. |
| **Engine ablation** ✅ | Show contribution of each detection engine | Run each engine solo. You've done this: embed_sim >> everything else. |
| **Windowing ablation** ✅ | Show impact of window aggregation | Compare per-paragraph vs windowed. You've done this: windowing helps. |
| **Feature count ablation** ❌ | Vary character n-gram vocabulary size | Test 10, 50, 100, 500, 1000, 2000 n-grams. Currently missing. |
| **Document length ablation** ❌ | Show performance vs document length | Bin documents by word count, report F1 per bin. Critical for understanding minimum viable input size. |
| **Author pair difficulty** ❌ | Show performance on easy vs hard cases | Stratify by style similarity between paired authors. Report per-stratum. |
| **Cross-genre ablation** ❌ | Robustness to genre shift | Train/eval within genre vs across genre. |
| **LLM paraphrase robustness** ❌ | Adversarial evaluation | Take detected passages, paraphrase with GPT-4/Claude, re-test detection. **Required for 2024+ publication.** |

---

## LAYER 5 — RESEARCH GAPS & NOVELTY

### 5.1 Most Cited Failure Modes of Current SOTA (2022–2025)

1. **LLM-assisted paraphrasing defeats surface stylometry.** GPT-4, Claude, and specialized "humanizer" tools can paraphrase text while eliminating most traditional stylometric markers (sentence length distribution, vocabulary richness, function word frequencies). Systems relying solely on these features drop to near-chance performance (Sadasivan et al. 2024, Krishna et al. 2024).

2. **Topic confound dominates style signal.** When topics change at author boundaries (which they often do in stitched plagiarism), systems detect topic change and attribute it to style change. Removing topic signal (via topic normalization or adversarial debiasing) typically reduces accuracy by 20–40%, revealing how much "stylometric" performance was actually topic-driven (Wegmann et al., ACL 2022).

3. **Short text degradation.** Below 500 words, most stylometric features become unreliable. Social media authorship attribution (50–280 characters) requires entirely different approaches (character-level CNNs, subword embeddings) than document-level methods. PRISM's paragraph-level analysis falls in this "dead zone" between document-level and character-level methods.

4. **Generalization failure across domains.** Systems trained on one domain (e.g., academic text) consistently fail when deployed on another (e.g., fiction, legal). No current system achieves >70% accuracy in true cross-domain evaluation without domain adaptation.

### 5.2 LLM Paraphrase Robustness

**Is PRISM robust to LLM paraphrasing? Almost certainly not.**

Evidence:
- Your primary signal comes from MiniLM embedding similarity (F1=0.374). MiniLM embeds by **semantic meaning** — paraphrasing preserves meaning by definition, so MiniLM similarity will remain high even between paraphrased and original text. A paraphrased passage inserted into a document will appear semantically coherent with its neighbors, making it invisible to your embedding detector.
- Your stylometric features (sentence length, POS ratios, function word distribution) are exactly the features that LLM paraphrasing is designed to alter. GPT-4 can match target sentence length distributions and vocabulary levels when prompted.
- **The only features with partial robustness to LLM paraphrasing** are: deep syntactic patterns (clause structure, dependency tree shapes), subconscious punctuation habits (comma splice tendencies, dash vs. parenthetical preferences), and rare character-level patterns (typos, spacing habits). PRISM captures very few of these.

**Robustness testing protocol:**
1. Select 50 genuinely stitched documents where PRISM correctly detects boundaries
2. Paraphrase the stitched sections using: (a) GPT-4, (b) Claude, (c) Quillbot
3. Re-run PRISM on paraphrased documents
4. Report detection rate drop per paraphrasing method
5. Expected result: >50% detection rate drop, likely >70%

### 5.3 The One Most Impactful Change

> [!CAUTION]
> **Replace MiniLM with a style-aware contrastive embedding model.** Train a DeBERTa-v3-base (or distilled version for speed) using contrastive learning on author-verified pairs. The model should embed text such that same-author texts are close and different-author texts are far — in **style space**, not **semantic space**. This single change addresses your three root causes simultaneously:
>
> 1. It replaces your non-discriminative 27 stylometric features with a learned 768-dimensional style representation
> 2. It operates on the full text (512+ tokens), not paragraph-level snippets
> 3. It learns an actual similarity function from labeled data, replacing the unsupervised proxy

**Training data:** Use the PAN 2020–2023 verification corpora (publicly available), augmented with your PRISM-Bench data.

**Fallback (lower effort, lower impact):** Fine-tune `sentence-transformers/all-MiniLM-L6-v2` with contrastive loss on (author_A, author_A, author_B) triplets from your dataset. Even without changing the architecture, training on stylistic similarity rather than semantic similarity would dramatically improve boundary detection.

### 5.4 What PAN 2023 and 2024 Top Systems Did Differently

**PAN 2023 (Cross-Discourse Authorship Verification):**
- Top systems used character n-gram profiles (1000+ n-grams) with cosine similarity as the primary feature
- Winning approaches extracted features at **multiple granularities** (sentence, paragraph, document) and fused them
- PPM (Prediction by Partial Matching) compression-based methods were competitive baselines — they capture character-level style without explicit feature engineering
- Key innovation: several systems used **discourse-type normalization** — identifying whether text is spoken vs. written and adjusting features accordingly

**PAN 2024 (Generative AI Authorship Verification):**
- Task shifted to human vs. AI detection (related but different from your task)
- Winning system (Tavan & Najafi, mean score 0.924): **ensemble of fine-tuned Mistral + Llama 2** combined with the Binoculars baseline
- Key innovation: treating AI detection as authorship verification, not binary classification. The question "is this human?" becomes "does this match human stylistic patterns?"
- BERT-based approaches (cnlp-nits-pp) achieved ROC-AUC > 97.6% — showing that even relatively small transformers can distinguish AI from human when fine-tuned on the right data
- **Methodological shift:** the best 2024 systems moved away from handcrafted stylometric features entirely, using end-to-end learned representations

---

## PRIORITY ACTION LIST — Top 5 This Week

### 1. Replace hardcoded character trigrams with a proper n-gram profile (Expected impact: +0.10–0.15 F1)

Your 10 hardcoded trigrams are the most common English trigrams and provide near-zero discriminative power. Replace with:
- Compute **all** character 3-grams and 4-grams from each text
- Represent as TF-IDF vectors (top 1,000–2,000 by corpus frequency)
- Use cosine similarity between adjacent paragraph TF-IDF vectors as a feature
- This is the single highest-signal feature in PAN history and you have a broken version of it

**File to modify:** [feature_engine.py](file:///d:/prism2/P.R.I.S.M/backend/services/feature_engine.py)

### 2. Fine-tune MiniLM for stylistic (not semantic) similarity (Expected impact: +0.15–0.25 F1)

Your embed_sim detector is strong (F1=0.374) but measures topic similarity, not style similarity. Even a quick contrastive fine-tuning on PAN verification pairs would separate these signals:
- Use PAN 2020 or 2022 same/different author pairs as training data
- Contrastive loss: same-author pairs should have high cosine similarity, different-author pairs should have low
- Train for 3–5 epochs with learning rate 2e-5
- This converts your best detector from a topic detector into a style detector

**File to modify:** [local_embeddings.py](file:///d:/prism2/P.R.I.S.M/backend/services/local_embeddings.py)

### 3. Expand the function word list from 5 to 50+ and increase window size to 300+ words (Expected impact: +0.05–0.10 F1)

The Koppel function word list (300 words) or the LIWC function word categories (150+ words) are standard. Five function words give you noise, not signal. Simultaneously, increase your window aggregator target from 100 to 300 words minimum — this alone will stabilize all feature estimators.

**Files to modify:** [feature_engine.py](file:///d:/prism2/P.R.I.S.M/backend/services/feature_engine.py), [window_aggregator.py](file:///d:/prism2/P.R.I.S.M/backend/services/window_aggregator.py)

### 4. Add c@1 metric and abstention mechanism (Expected impact: +0.05–0.15 on PAN primary metric)

Your system always outputs a binary decision. PAN rewards abstention on uncertain cases. Add:
- Confidence score as a continuous value [0, 1] instead of categorical "high/medium/low"
- Abstention threshold: if confidence < τ, output "unanswered"
- Tune τ to maximize c@1 on validation set
- Report c@1 alongside F1 and AUC

**Files to modify:** [hdbscan_detector.py](file:///d:/prism2/P.R.I.S.M/backend/services/hdbscan_detector.py), [scoring_engine.py](file:///d:/prism2/P.R.I.S.M/backend/services/scoring_engine.py), [evaluate_metrics.py](file:///d:/prism2/P.R.I.S.M/research/experiments/evaluate_metrics.py)

### 5. Run LLM paraphrase robustness test and report results honestly (Expected impact: critical for publication credibility)

Generate adversarial test cases:
- Take 50 multi-author documents where fusion3 correctly detects boundaries
- Paraphrase the non-primary-author sections with GPT-4 (instruction: "rewrite in the same style as the surrounding text")
- Re-run detection and report the detection rate drop
- This is a **required experiment** for any 2024+ stylometric paper — reviewers will ask for it

**New script needed** in `research/experiments/`

---

## APPENDIX: Your Current Numbers in Context

| System | Boundary F1 | Doc Accuracy | Notes |
|:---|:---|:---|:---|
| PRISM random baseline | 0.055 | 0.170 | Chance level |
| PRISM PELT (rbf) | 0.021 | 0.046 | **Worse than random** — features are noise |
| PRISM distance | 0.129 | 0.279 | Basic distance baseline |
| PRISM w_fused (stylometric) | 0.215 | 0.476 | Best stylometric-only result |
| PRISM embed_sim (MiniLM) | 0.374 | 0.734 | Topic similarity, not style |
| **PRISM fusion3 (best)** | **0.397** | **0.739** | Marginal gain over embedding alone |
| PAN 2023 top system | ~0.85+ c@1 | — | Character n-grams + learned similarity |
| PAN 2024 top system (Tavan) | 0.924 mean | — | Mistral + Llama ensemble |

**The gap between PRISM's best (F1=0.397) and PAN SOTA (c@1 > 0.85) is enormous.** But the path to closing it is clear: the problem is not architecture (your pipeline/fusion design is sound) but the quality of individual signals feeding into it. Fix the character n-grams, fine-tune the embeddings for style rather than semantics, and expand the function word vocabulary — and you should see F1 jump to the 0.55–0.70 range, which is publishable for ACL SRW with the right framing (analysis paper showing which signals matter, not claiming SOTA).
