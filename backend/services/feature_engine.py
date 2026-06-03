"""
P.R.I.S.M. — Stylometric Feature Extraction Engine v3
======================================================
Extracts ~27 content-independent linguistic features per paragraph using spaCy.
No API calls — fully offline, deterministic, millisecond-speed.

Feature groups:
  1. Structural (8):  avg_sentence_length, avg_word_length, pronoun_ratio,
                      preposition_ratio, conjunction_ratio, passive_voice_pct,
                      yules_k, burstiness_coefficient
  2. Character trigrams (10): Top 10 most discriminative char 3-grams
  3. Function words (5): Frequency of top 5 English function words
  4. Punctuation (3): comma_rate, semicolon_rate, dash_rate
  5. Hapax legomena (1): Words appearing exactly once / total words

Tiered extraction based on paragraph word count:
  - <50 words:  SKIP (insufficient text)
  - 50-99 words: REDUCED (char trigrams + function words + avg_sentence_length)
  - >=100 words: FULL extraction

These features form an N×27 matrix fed into HDBSCAN + PELT for detection.
"""

import logging
import numpy as np
import spacy
from collections import Counter
from typing import List, Dict, Any, Optional

from models import PipelineContext, WarningCode, WarningSeverity

logger = logging.getLogger(__name__)

# Load spaCy model once — disable NER for speed (irrelevant for stylometry)
try:
    nlp = spacy.load("en_core_web_sm", disable=["ner"])
    logger.info("[P.R.I.S.M.] spaCy model loaded successfully")
except OSError:
    logger.error("[P.R.I.S.M.] spaCy model not found! Run: python -m spacy download en_core_web_sm")
    raise RuntimeError("spaCy model 'en_core_web_sm' not installed. Run: python -m spacy download en_core_web_sm")


# ─── Top 10 Character Trigrams (English academic text) ───────────────────────
# Selected by document frequency from academic corpora. These capture:
# - Word boundaries (' th', 'he ', 'the') → captures function word usage
# - Morphological patterns ('ing', 'tion', 'ent') → captures suffix preferences
# - Punctuation habits (', t', '. T') → captures punctuation style
TOP_CHAR_TRIGRAMS = [
    " th", "the", "he ", "ing", " an", "nd ", " in", "ion", "ed ", " of",
]

# ─── Top 5 Function Words ───────────────────────────────────────────────────
# Most discriminative for authorship (Stamatatos 2009, Koppel 2009).
# Frequency of these words is highly author-specific and topic-independent.
TOP_FUNCTION_WORDS = ["the", "of", "and", "to", "in"]


# ─── Feature Names (order matters — matches matrix columns) ──────────────────
STRUCTURAL_FEATURES = [
    "avg_sentence_length",
    "avg_word_length",
    "pronoun_ratio",
    "preposition_ratio",
    "conjunction_ratio",
    "passive_voice_pct",
    "yules_k",
    "burstiness_coefficient",
]

TRIGRAM_FEATURES = [f"char3_{tg.strip().replace(' ', '_')}" for tg in TOP_CHAR_TRIGRAMS]
FUNCWORD_FEATURES = [f"fw_{w}" for w in TOP_FUNCTION_WORDS]
PUNCT_FEATURES = ["comma_rate", "semicolon_rate", "dash_rate"]
HAPAX_FEATURES = ["hapax_legomena_ratio"]

FEATURE_NAMES = (
    STRUCTURAL_FEATURES
    + TRIGRAM_FEATURES
    + FUNCWORD_FEATURES
    + PUNCT_FEATURES
    + HAPAX_FEATURES
)

# Tier thresholds
# Lowered from 50/100 after PAN 2023 analysis: median paragraph is 41 words.
# Old thresholds caused 61% of paragraphs to produce all-zero feature vectors.
TIER_SKIP = 20        # <20 words → skip (only 5% of PAN paragraphs)
TIER_REDUCED = 50     # 20-49 words → reduced features only


class FeatureEngine:
    """
    Extracts content-independent stylometric features from text paragraphs
    using spaCy NLP pipeline. All operations are deterministic and local —
    zero API calls, zero cost, millisecond-speed.

    v3 changes:
      - Removed OpenAI semantic embeddings (moved to topic_coherence module)
      - Added char trigrams, function words, punctuation, hapax legomena
      - Tiered extraction based on paragraph length
      - Burstiness is a soft feature (no hard threshold/penalty)
    """

    def __init__(self, min_words: int = 10):
        """
        Args:
            min_words: Absolute minimum word count. Paragraphs below this
                       return zeros (not even reduced features).
        """
        self.min_words = min_words

    # ─── Public API ──────────────────────────────────────────────────────────

    def extract_features(self, text: str) -> np.ndarray:
        """
        Extract a feature vector from a single paragraph.
        Applies tiered extraction based on word count.

        Args:
            text: Raw paragraph text string.

        Returns:
            np.ndarray of shape (N_FEATURES,) with stylometric features.
            Returns zeros if text is too short.
        """
        doc = nlp(text)
        words = [token.text.lower() for token in doc if token.is_alpha]
        word_count = len(words)

        if word_count < self.min_words:
            return np.zeros(len(FEATURE_NAMES))

        # Always compute: char trigrams, function words (work on short text)
        trigram_feats = self._extract_char_trigrams(text, word_count)
        funcword_feats = self._extract_function_words(words)

        if word_count < TIER_SKIP:
            # Below 50 words: insufficient for reliable extraction
            return np.zeros(len(FEATURE_NAMES))

        elif word_count < TIER_REDUCED:
            # 50-99 words: reduced feature set
            # Only avg_sentence_length from structural (most stable at short lengths)
            sentences = list(doc.sents)
            avg_sl = sum(len(s.text.split()) for s in sentences) / max(len(sentences), 1)
            structural = np.array([avg_sl, 0, 0, 0, 0, 0, 0, 0])
            punct_feats = np.zeros(3)
            hapax_feats = np.zeros(1)

        else:
            # ≥100 words: full extraction
            structural = self._extract_structural(doc, words)
            punct_feats = self._extract_punctuation(text, doc)
            hapax_feats = self._extract_hapax(words)

        return np.concatenate([
            structural,
            trigram_feats,
            funcword_feats,
            punct_feats,
            hapax_feats,
        ])

    def extract_all(
        self,
        paragraphs: List[Dict[str, Any]],
        ctx: Optional[PipelineContext] = None,
    ) -> Dict[str, Any]:
        """
        Extract features for all paragraphs and return the feature matrix.

        Args:
            paragraphs: List of paragraph dicts with at least a "text" key.
            ctx: Optional PipelineContext for warning accumulation.

        Returns:
            Dict with feature_matrix, feature_names, profiles, valid_indices.
        """
        if ctx is None:
            ctx = PipelineContext()

        feature_vectors = []
        profiles = []
        valid_indices = []

        for i, para in enumerate(paragraphs):
            text = para.get("text", "")
            features = self.extract_features(text)

            is_valid = np.any(features != 0)
            if is_valid:
                valid_indices.append(i)

            feature_vectors.append(features)

        # Build profiles for frontend
        for i, features in enumerate(feature_vectors):
            is_valid = i in valid_indices
            text = paragraphs[i].get("text", "")
            word_count = len(text.split())

            # Determine tier
            if word_count < TIER_SKIP:
                tier = "insufficient"
            elif word_count < TIER_REDUCED:
                tier = "reduced"
            else:
                tier = "full"

            profile = {
                "paragraph_index": i,
                "is_valid": bool(is_valid),
                "word_count": word_count,
                "extraction_tier": tier,
                "num_sentences": len(list(nlp(text).sents)) if is_valid else 1,
            }
            for j, name in enumerate(FEATURE_NAMES):
                profile[name] = round(float(features[j]), 4)

            profiles.append(profile)

        feature_matrix = (
            np.array(feature_vectors)
            if feature_vectors
            else np.zeros((0, len(FEATURE_NAMES)))
        )

        # ── Edge Case: Short paper (<5 paragraphs) ───────────────────────────
        SHORT_PAPER_THRESHOLD = 5
        if len(paragraphs) < SHORT_PAPER_THRESHOLD:
            ctx.add_warning(
                WarningCode.FEATURES_SHORT_PAPER, WarningSeverity.WARNING, "feature_engine",
                f"Document has only {len(paragraphs)} paragraphs (threshold: {SHORT_PAPER_THRESHOLD}). "
                f"Stylometric clustering will be skipped — insufficient data for reliable authorship detection.",
                {"paragraph_count": len(paragraphs), "threshold": SHORT_PAPER_THRESHOLD},
            )
            ctx.skip_clustering = True

        # ── Edge Case: Too few valid paragraphs ──────────────────────────────
        MIN_VALID_FOR_CLUSTERING = 3
        if len(valid_indices) < MIN_VALID_FOR_CLUSTERING:
            ctx.add_warning(
                WarningCode.FEATURES_TOO_FEW_VALID, WarningSeverity.WARNING, "feature_engine",
                f"Only {len(valid_indices)} paragraphs had enough text for feature extraction "
                f"(minimum: {MIN_VALID_FOR_CLUSTERING}). Clustering may be unreliable.",
                {"valid_count": len(valid_indices), "minimum": MIN_VALID_FOR_CLUSTERING},
            )
            if len(valid_indices) < 2:
                ctx.skip_clustering = True

        logger.info(
            f"[P.R.I.S.M.] Extracted {len(FEATURE_NAMES)} features for {len(paragraphs)} paragraphs "
            f"({len(valid_indices)} valid, {len(paragraphs) - len(valid_indices)} too short)"
        )

        return {
            "feature_matrix": feature_matrix,
            "feature_names": FEATURE_NAMES,
            "profiles": profiles,
            "valid_indices": valid_indices,
            "total_paragraphs": len(paragraphs),
            "valid_paragraphs": len(valid_indices),
        }

    def get_paragraph_summary(self, text: str) -> Dict[str, Any]:
        """
        Get a detailed style summary for a single paragraph.
        Used for the frontend side panel when clicking a paragraph.
        """
        doc = nlp(text)
        words = [token.text.lower() for token in doc if token.is_alpha]
        features = self.extract_features(text)
        sentences = list(doc.sents)
        pos_counts = Counter(token.pos_ for token in doc)

        # Top function words used
        func_tokens = [
            token.text.lower() for token in doc
            if token.pos_ in ("ADP", "CCONJ", "SCONJ", "PRON", "DET", "AUX")
            and token.is_alpha
        ]
        top_func = Counter(func_tokens).most_common(5)

        summary = {
            "word_count": len(words),
            "sentence_count": len(sentences),
            "unique_words": len(set(words)),
            "extraction_tier": (
                "insufficient" if len(words) < TIER_SKIP
                else "reduced" if len(words) < TIER_REDUCED
                else "full"
            ),
            "top_function_words": [{"word": w, "count": c} for w, c in top_func],
            "pos_distribution": {
                "nouns": pos_counts.get("NOUN", 0),
                "verbs": pos_counts.get("VERB", 0),
                "adjectives": pos_counts.get("ADJ", 0),
                "adverbs": pos_counts.get("ADV", 0),
                "pronouns": pos_counts.get("PRON", 0),
                "prepositions": pos_counts.get("ADP", 0),
                "conjunctions": pos_counts.get("CCONJ", 0) + pos_counts.get("SCONJ", 0),
            },
        }

        for j, name in enumerate(FEATURE_NAMES):
            summary[name] = round(float(features[j]) if j < len(features) else 0.0, 4)

        return summary

    # ─── Private: Structural Features ────────────────────────────────────────

    def _extract_structural(self, doc, words: List[str]) -> np.ndarray:
        """Extract the 8 structural features (full tier)."""
        sentences = list(doc.sents)
        num_sentences = max(len(sentences), 1)
        num_tokens = max(len(doc), 1)

        # Sentence lengths
        sentence_lengths = [len(s.text.split()) for s in sentences] if sentences else [0]
        avg_sentence_length = sum(sentence_lengths) / num_sentences

        # Burstiness (CV of sentence length) — soft feature, no threshold
        burstiness = float(np.std(sentence_lengths) / max(avg_sentence_length, 1.0))

        avg_word_length = sum(len(w) for w in words) / max(len(words), 1)

        # POS ratios
        pos_counts = Counter(token.pos_ for token in doc)
        pronoun_ratio = pos_counts.get("PRON", 0) / num_tokens
        preposition_ratio = pos_counts.get("ADP", 0) / num_tokens
        conjunction_ratio = (
            pos_counts.get("CCONJ", 0) + pos_counts.get("SCONJ", 0)
        ) / num_tokens

        # Passive voice
        passive_count = sum(1 for t in doc if t.dep_ in ("nsubjpass", "auxpass"))
        passive_voice_pct = (passive_count / num_sentences) * 100

        # Yule's K
        yules_k = self._calculate_yules_k(words)

        return np.array([
            avg_sentence_length,
            avg_word_length,
            pronoun_ratio,
            preposition_ratio,
            conjunction_ratio,
            passive_voice_pct,
            yules_k,
            burstiness,
        ])

    # ─── Private: Character Trigrams ─────────────────────────────────────────

    @staticmethod
    def _extract_char_trigrams(text: str, word_count: int) -> np.ndarray:
        """
        Extract frequency of top 10 character trigrams.
        Normalized by total trigram count for length independence.
        """
        text_lower = text.lower()
        total_trigrams = max(len(text_lower) - 2, 1)

        freqs = []
        for trigram in TOP_CHAR_TRIGRAMS:
            count = 0
            for i in range(len(text_lower) - 2):
                if text_lower[i:i+3] == trigram:
                    count += 1
            freqs.append(count / total_trigrams)

        return np.array(freqs)

    # ─── Private: Function Words ─────────────────────────────────────────────

    @staticmethod
    def _extract_function_words(words: List[str]) -> np.ndarray:
        """
        Extract frequency of top 5 function words.
        Normalized by total word count.
        """
        total = max(len(words), 1)
        word_counts = Counter(words)
        return np.array([word_counts.get(fw, 0) / total for fw in TOP_FUNCTION_WORDS])

    # ─── Private: Punctuation Features ───────────────────────────────────────

    @staticmethod
    def _extract_punctuation(text: str, doc) -> np.ndarray:
        """
        Extract punctuation rates per sentence.
        Captures author-specific punctuation habits.
        """
        num_sentences = max(len(list(doc.sents)), 1)
        comma_count = text.count(",")
        semicolon_count = text.count(";")
        dash_count = text.count("-") + text.count("\u2014") + text.count("\u2013")

        return np.array([
            comma_count / num_sentences,
            semicolon_count / num_sentences,
            dash_count / num_sentences,
        ])

    # ─── Private: Hapax Legomena ─────────────────────────────────────────────

    @staticmethod
    def _extract_hapax(words: List[str]) -> np.ndarray:
        """
        Hapax legomena ratio: words appearing exactly once / total words.
        High ratio = diverse vocabulary = potentially different author.
        """
        total = max(len(words), 1)
        word_counts = Counter(words)
        hapax = sum(1 for count in word_counts.values() if count == 1)
        return np.array([hapax / total])

    # ─── Private: Yule's K ──────────────────────────────────────────────────

    @staticmethod
    def _calculate_yules_k(words: List[str]) -> float:
        """
        Compute Yule's Characteristic K — a robust measure of lexical richness
        that is resistant to text length fluctuations (unlike Type-Token Ratio).

        Formula: K = 10000 * (M2 - M1) / M1^2
        where M1 = total words, M2 = sum of (count^2) for each unique word.
        Low K = diverse vocabulary, High K = repetitive vocabulary.
        """
        if len(words) < 2:
            return 0.0

        word_counts = Counter(words)
        m1 = len(words)
        m2 = sum(count ** 2 for count in word_counts.values())

        if m1 <= 1:
            return 0.0

        return 10000.0 * (m2 - m1) / (m1 ** 2)
