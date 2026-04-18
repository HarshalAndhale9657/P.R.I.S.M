"""
P.R.I.S.M. — Stylometric Feature Extraction Engine
Extracts 7 content-independent linguistic features per paragraph using spaCy.

Features are chosen to capture AUTHOR STYLE, not CONTENT:
  1. avg_sentence_length  — structural complexity
  2. avg_word_length      — vocabulary sophistication
  3. pronoun_ratio        — personal vs impersonal tone
  4. preposition_ratio    — syntactic construction preference
  5. conjunction_ratio    — clause-linking habits
  6. passive_voice_pct    — academic formality level
  7. yules_k              — lexical richness (length-resistant)

These features form an N×7 matrix fed into HDBSCAN for authorship clustering.
"""

import logging
import numpy as np
import spacy
from collections import Counter
from typing import List, Dict, Any, Optional
import os
import openai
from sklearn.decomposition import PCA

from models import PipelineContext, WarningCode, WarningSeverity

logger = logging.getLogger(__name__)

# Load spaCy model once — disable NER for speed (irrelevant for stylometry)
try:
    nlp = spacy.load("en_core_web_sm", disable=["ner"])
    logger.info("[P.R.I.S.M.] spaCy model loaded successfully")
except OSError:
    logger.error("[P.R.I.S.M.] spaCy model not found! Run: python -m spacy download en_core_web_sm")
    raise RuntimeError("spaCy model 'en_core_web_sm' not installed. Run: python -m spacy download en_core_web_sm")


# ─── Feature Names (order matters — matches matrix columns) ──────────────────
FEATURE_NAMES = [
    "avg_sentence_length",
    "avg_word_length",
    "pronoun_ratio",
    "preposition_ratio",
    "conjunction_ratio",
    "passive_voice_pct",
    "yules_k",
    "semantic_1",
    "semantic_2",
    "semantic_3",
]


class FeatureEngine:
    """
    Extracts content-independent stylometric features from text paragraphs
    using spaCy NLP pipeline. All operations are deterministic and local —
    zero API calls, zero cost, millisecond-speed.
    """

    def __init__(self, min_words: int = 10):
        """
        Args:
            min_words: Minimum word count for a paragraph to be analyzable.
                       Paragraphs shorter than this produce unreliable features.
        """
        self.min_words = min_words

    # ─── Public API ──────────────────────────────────────────────────────────

    def extract_features(self, text: str) -> np.ndarray:
        """
        Extract a 7-dimensional feature vector from a single paragraph.

        Args:
            text: Raw paragraph text string.

        Returns:
            np.ndarray of shape (7,) with stylometric features.
            Returns zeros if text is too short.
        """
        doc = nlp(text)

        # Get alpha-only tokens (words, no punctuation/numbers)
        words = [token.text.lower() for token in doc if token.is_alpha]

        if len(words) < self.min_words:
            return np.zeros(7) # We rely on 7 structural features

        # ── 1. Structural Features ───────────────────────────────────────────
        sentences = list(doc.sents)
        num_sentences = max(len(sentences), 1)
        num_tokens = max(len(doc), 1)

        avg_sentence_length = len(words) / num_sentences
        avg_word_length = sum(len(w) for w in words) / max(len(words), 1)

        # ── 2. Function Word Ratios (POS-based) ─────────────────────────────
        pos_counts = Counter(token.pos_ for token in doc)

        pronoun_ratio = pos_counts.get("PRON", 0) / num_tokens
        preposition_ratio = pos_counts.get("ADP", 0) / num_tokens
        conjunction_ratio = (
            pos_counts.get("CCONJ", 0) + pos_counts.get("SCONJ", 0)
        ) / num_tokens

        # ── 3. Passive Voice Detection ───────────────────────────────────────
        passive_count = 0
        for token in doc:
            # spaCy labels passive subjects as "nsubjpass" in dependency parse
            if token.dep_ in ("nsubjpass", "auxpass"):
                passive_count += 1

        passive_voice_pct = (passive_count / num_sentences) * 100

        # ── 4. Lexical Richness — Yule's K ──────────────────────────────────
        yules_k = self._calculate_yules_k(words)

        return np.array([
            avg_sentence_length,
            avg_word_length,
            pronoun_ratio,
            preposition_ratio,
            conjunction_ratio,
            passive_voice_pct,
            yules_k,
        ])

    def extract_all(
        self,
        paragraphs: List[Dict[str, Any]],
        ctx: Optional[PipelineContext] = None,
    ) -> Dict[str, Any]:
        """
        Extract features for all paragraphs and return the feature matrix
        along with per-paragraph profile dictionaries.

        Args:
            paragraphs: List of paragraph dicts with at least a "text" key.
            ctx: Optional PipelineContext for warning accumulation.

        Returns:
            Dict with:
                - feature_matrix: np.ndarray of shape (N, 7)
                - feature_names: list of 7 feature name strings
                - profiles: list of per-paragraph feature dicts (for frontend)
                - valid_indices: indices of paragraphs with enough text
        """
        if ctx is None:
            ctx = PipelineContext()

        feature_vectors = []
        profiles = []
        valid_indices = []

        for i, para in enumerate(paragraphs):
            text = para.get("text", "")
            features = self.extract_features(text)

            # Track which paragraphs had enough text for analysis
            is_valid = np.any(features != 0)
            if is_valid:
                valid_indices.append(i)

            feature_vectors.append(features)

        # ── 5. OpenAI Deep Semantic Embeddings ──────────────────────────────
        try:
            # Only run if we actually have text and valid OPENAI_API_KEY
            if os.getenv("OPENAI_API_KEY") and valid_indices:
                logger.info(f"[P.R.I.S.M.] Generating high-dimensional embeddings for {len(valid_indices)} paragraphs via OpenAI")
                client = openai.Client()
                texts_to_embed = [paragraphs[i].get("text", "") for i in valid_indices]
                
                # Batch request embeddings (fast)
                response = client.embeddings.create(
                    input=texts_to_embed,
                    model="text-embedding-3-small"
                )
                embeddings = np.array([r.embedding for r in response.data])
                
                # Reduce 1536 dims down to 3 using PCA so HDBSCAN doesn't suffer the curse of dimensionality
                n_components = min(3, len(valid_indices))
                pca = PCA(n_components=n_components)
                reduced_embeddings = pca.fit_transform(embeddings)
                
                # Pad with zeros if n_components < 3 (extremely short document)
                if n_components < 3:
                    pad = np.zeros((len(valid_indices), 3 - n_components))
                    reduced_embeddings = np.hstack([reduced_embeddings, pad])
                
                # Map back to the original full feature_vectors array
                semantic_dict = {orig_idx: red_emb for orig_idx, red_emb in zip(valid_indices, reduced_embeddings)}
            else:
                semantic_dict = {}
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Failed to extract semantic embeddings: {e}")
            semantic_dict = {}

        # Merge structural and semantic features
        final_feature_vectors = []
        for i, structural_feats in enumerate(feature_vectors):
            if i in valid_indices:
                semantic_feats = semantic_dict.get(i, np.zeros(3))
                combined = np.concatenate([structural_feats, semantic_feats])
            else:
                combined = np.concatenate([structural_feats, np.zeros(3)])
            final_feature_vectors.append(combined)

        # Build profiles
        for i, features in enumerate(final_feature_vectors):
            is_valid = i in valid_indices
            profile = {
                "paragraph_index": i,
                "is_valid": bool(is_valid),
            }
            for j, name in enumerate(FEATURE_NAMES):
                profile[name] = round(float(features[j]), 4)

            profiles.append(profile)

        feature_matrix = np.array(final_feature_vectors) if final_feature_vectors else np.zeros((0, len(FEATURE_NAMES)))

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
            f"[P.R.I.S.M.] Extracted features for {len(paragraphs)} paragraphs "
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

        Returns:
            Dict with all features + additional metadata.
        """
        doc = nlp(text)
        words = [token.text.lower() for token in doc if token.is_alpha]
        features = self.extract_features(text)

        # Additional metadata not in the 7-feature vector
        sentences = list(doc.sents)
        pos_counts = Counter(token.pos_ for token in doc)

        # Top function words
        function_words = [
            token.text.lower() for token in doc
            if token.pos_ in ("ADP", "CCONJ", "SCONJ", "PRON", "DET", "AUX")
            and token.is_alpha
        ]
        top_function_words = Counter(function_words).most_common(5)

        summary = {
            "word_count": len(words),
            "sentence_count": len(sentences),
            "unique_words": len(set(words)),
            "top_function_words": [{"word": w, "count": c} for w, c in top_function_words],
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

        # Simulate semantic features since we don't fire an API call for a single click
        for j, name in enumerate(FEATURE_NAMES):
            summary[name] = round(float(features[j]) if j < 7 else 0.0, 4)

        return summary

    # ─── Private Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _calculate_yules_k(words: List[str]) -> float:
        """
        Compute Yule's Characteristic K — a robust measure of lexical richness
        that is resistant to text length fluctuations (unlike Type-Token Ratio).

        Formula: K = 10000 × (M2 - M1) / M1²
        where:
            M1 = total number of words
            M2 = sum of (count²) for each unique word

        Low K = highly diverse vocabulary
        High K = repetitive vocabulary
        """
        if len(words) < 2:
            return 0.0

        word_counts = Counter(words)
        m1 = len(words)  # Total words
        m2 = sum(count ** 2 for count in word_counts.values())  # Sum of squared frequencies

        if m1 <= 1:
            return 0.0

        return 10000.0 * (m2 - m1) / (m1 ** 2)
