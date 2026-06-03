"""
P.R.I.S.M. Research — Evaluation Dataset Builder
=================================================
Builds a unified evaluation corpus from three sources:
  1. PAN 2023 Style Change Detection (Zenodo download)
  2. Synthetic stitched documents (arXiv splicing)
  3. Genuine single-author documents (arXiv verified)

Output: Normalized JSON documents in research/datasets/ with a manifest.json index.

Each document follows the unified schema:
{
    "id": "pan_easy_001",
    "source": "pan2023_easy",
    "paragraphs": ["...", "..."],
    "ground_truth": {
        "is_multi_author": true,
        "author_labels": [0, 0, 1, 1, 0],
        "boundaries": [2, 4],
        "changes": [0, 1, 0, 1]
    }
}

Usage:
    python dataset_builder.py --pan-dir ../datasets/pan --output-dir ../datasets
    python dataset_builder.py --build-synthetic --output-dir ../datasets
    python dataset_builder.py --build-genuine --output-dir ../datasets
    python dataset_builder.py --build-all --output-dir ../datasets
"""

import json
import os
import re
import random
import hashlib
import argparse
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ─── Constants ───────────────────────────────────────────────────────────────

DATASETS_DIR = Path(__file__).parent.parent / "datasets"
PAN_ZENODO_URL = "https://doi.org/10.5281/zenodo.7729177"
MIN_PARAGRAPH_WORDS = 30  # Skip paragraphs shorter than this


# ─── PAN Dataset Ingestion ───────────────────────────────────────────────────

class PANIngester:
    """
    Ingest PAN 2023 Style Change Detection datasets into P.R.I.S.M.'s
    unified format. Handles all three difficulty levels (easy/medium/hard)
    and all splits (train/validation/test).

    PAN format:
        problem-X.txt          -> paragraphs separated by \\n\\n
        truth-problem-X.json   -> {"authors": N, "changes": [0,0,1,...]}
    """

    DIFFICULTY_MAP = {
        "dataset1": "easy",
        "dataset2": "medium",
        "dataset3": "hard",
    }

    def __init__(self, pan_root: Path):
        """
        Args:
            pan_root: Path to extracted PAN dataset root.
            Supports both short naming (dataset1/) and long PAN Zenodo naming
            (pan23-multi-author-analysis-dataset1/).
        """
        self.pan_root = Path(pan_root)

    def _find_dataset_dir(self, dataset_key: str) -> Optional[Path]:
        """Find the dataset directory, supporting both short and long naming."""
        # Try short name first: dataset1/
        short = self.pan_root / dataset_key
        if short.exists():
            return short
        # Try long PAN Zenodo name: pan23-multi-author-analysis-dataset1/
        for candidate in self.pan_root.iterdir():
            if candidate.is_dir() and candidate.name.endswith(dataset_key):
                return candidate
        return None

    def _find_split_dir(self, dataset_path: Path, split: str) -> Optional[Path]:
        """Find the split directory, supporting both short and long naming."""
        # Try short name first: train/
        short = dataset_path / split
        if short.exists():
            return short
        # Try long PAN Zenodo name: pan23-multi-author-analysis-dataset1-train/
        for candidate in dataset_path.iterdir():
            if candidate.is_dir() and candidate.name.endswith(f"-{split}"):
                return candidate
        return None

    def ingest_all(self) -> List[Dict[str, Any]]:
        """Ingest all PAN datasets and return unified document list."""
        documents = []

        for dataset_key, difficulty in self.DIFFICULTY_MAP.items():
            dataset_path = self._find_dataset_dir(dataset_key)
            if dataset_path is None:
                logger.warning(f"PAN directory not found for {dataset_key} in {self.pan_root}")
                continue

            logger.info(f"Found PAN {difficulty}: {dataset_path.name}")

            # Process each split (train has ground truth, validation has ground truth, test may not)
            for split in ["train", "validation"]:
                split_path = self._find_split_dir(dataset_path, split)
                if split_path is None:
                    logger.warning(f"Split '{split}' not found in {dataset_path}")
                    continue

                docs = self._ingest_split(split_path, difficulty, split)
                documents.extend(docs)
                logger.info(f"PAN {difficulty}/{split}: {len(docs)} documents ingested")

        logger.info(f"Total PAN documents: {len(documents)}")
        return documents

    def _ingest_split(
        self, split_path: Path, difficulty: str, split: str
    ) -> List[Dict[str, Any]]:
        """Ingest a single PAN split directory."""
        documents = []

        # Find all problem files
        problem_files = sorted(split_path.glob("problem-*.txt"))

        for problem_file in problem_files:
            problem_id = problem_file.stem.replace("problem-", "")
            truth_file = split_path / f"truth-problem-{problem_id}.json"

            if not truth_file.exists():
                logger.debug(f"No ground truth for {problem_file.name}, skipping")
                continue

            # Read text and split into paragraphs
            # PAN 2023 uses single \n as paragraph separator (not \n\n)
            with open(problem_file, "r", newline="", encoding="utf-8") as f:
                text = f.read()

            # Try double newline first, fall back to single newline (PAN 2023 format)
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            if len(paragraphs) <= 1:
                paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

            # Skip documents with too few paragraphs
            if len(paragraphs) < 3:
                continue

            # Read ground truth
            with open(truth_file, "r", encoding="utf-8") as f:
                truth = json.load(f)

            changes = truth.get("changes", [])
            num_authors = truth.get("authors", 1)

            # Validate: changes array should have len(paragraphs) - 1 entries
            expected_paras = len(changes) + 1
            if len(paragraphs) != expected_paras:
                # Truncate or skip if mismatch
                if len(paragraphs) > expected_paras:
                    paragraphs = paragraphs[:expected_paras]
                else:
                    logger.debug(
                        f"Skipping {problem_file.name}: {len(paragraphs)} paragraphs "
                        f"but changes array expects {expected_paras}"
                    )
                    continue

            # Convert changes array to boundaries and author labels
            boundaries = [i + 1 for i, c in enumerate(changes) if c == 1]
            author_labels = self._changes_to_labels(changes)

            doc_id = f"pan_{difficulty}_{split}_{problem_id}"

            documents.append({
                "id": doc_id,
                "source": f"pan2023_{difficulty}",
                "source_split": split,
                "difficulty": difficulty,
                "paragraphs": paragraphs,
                "ground_truth": {
                    "is_multi_author": num_authors > 1,
                    "num_authors": num_authors,
                    "author_labels": author_labels,
                    "boundaries": boundaries,
                    "changes": changes,
                },
            })

        return documents

    @staticmethod
    def _changes_to_labels(changes: List[int]) -> List[int]:
        """
        Convert PAN changes array [0,0,1,0,1] to author labels [0,0,0,1,1,2].
        Each 1 in changes means the next paragraph has a different author.
        """
        labels = [0]
        current_author = 0
        for change in changes:
            if change == 1:
                current_author += 1
            labels.append(current_author)
        return labels


# ─── Synthetic Document Builder ──────────────────────────────────────────────

class SyntheticBuilder:
    """
    Builds synthetic stitched documents by splicing paragraphs from
    different source texts. Creates documents with known ground truth
    for boundary detection evaluation.

    Three splicing strategies:
      1. Random: interleave paragraphs from 2-4 authors
      2. Block: take contiguous blocks from different authors (realistic)
      3. Single-author control: genuine documents (no stitching)
    """

    def __init__(self, source_dir: Optional[Path] = None):
        self.source_dir = source_dir or DATASETS_DIR / "source_texts"
        self._source_texts: Dict[str, List[str]] = {}

    def build_all(self, count: int = 20) -> List[Dict[str, Any]]:
        """Build synthetic documents using available source texts."""
        self._load_sources()

        if len(self._source_texts) < 2:
            logger.warning(
                f"Need at least 2 source authors, found {len(self._source_texts)}. "
                "Creating from built-in samples."
            )
            self._create_builtin_samples()

        documents = []
        authors = list(self._source_texts.keys())

        # Strategy 1: Random interleave (40% of docs)
        n_random = max(1, int(count * 0.4))
        for i in range(n_random):
            doc = self._build_random_interleave(authors, i)
            if doc:
                documents.append(doc)

        # Strategy 2: Block splicing (40% of docs)
        n_block = max(1, int(count * 0.4))
        for i in range(n_block):
            doc = self._build_block_splice(authors, i)
            if doc:
                documents.append(doc)

        # Strategy 3: Single-author control (20% of docs)
        n_genuine = max(1, count - n_random - n_block)
        for i in range(n_genuine):
            doc = self._build_single_author(authors, i)
            if doc:
                documents.append(doc)

        logger.info(f"Built {len(documents)} synthetic documents")
        return documents

    def _load_sources(self):
        """Load source texts from the source_texts directory."""
        if not self.source_dir.exists():
            self.source_dir.mkdir(parents=True, exist_ok=True)
            return

        for author_dir in sorted(self.source_dir.iterdir()):
            if author_dir.is_dir():
                paragraphs = []
                for txt_file in sorted(author_dir.glob("*.txt")):
                    with open(txt_file, "r", encoding="utf-8") as f:
                        text = f.read()
                    file_paras = [
                        p.strip()
                        for p in text.split("\n\n")
                        if p.strip() and len(p.split()) >= MIN_PARAGRAPH_WORDS
                    ]
                    paragraphs.extend(file_paras)

                if paragraphs:
                    self._source_texts[author_dir.name] = paragraphs
                    logger.info(
                        f"Loaded {len(paragraphs)} paragraphs from author '{author_dir.name}'"
                    )

    def _create_builtin_samples(self):
        """Create minimal built-in samples for testing when no source texts exist."""
        # These are stylistically distinct sample paragraphs for testing
        self._source_texts["author_formal"] = [
            "The investigation of computational methods for textual analysis has yielded significant advances in recent decades. Methodologies rooted in statistical inference provide robust frameworks for characterizing authorial style. Furthermore, the application of machine learning algorithms to linguistic feature extraction has demonstrated considerable promise in forensic contexts. The systematic evaluation of these approaches remains paramount to establishing their validity in academic settings.",
            "Empirical evidence suggests that stylometric features, when properly calibrated, can achieve discriminative accuracy exceeding traditional approaches. The deployment of density-based clustering algorithms, particularly HDBSCAN, offers advantages in scenarios where the number of authorial voices is unknown a priori. Such unsupervised methodologies circumvent the requirement for labeled training corpora.",
            "The theoretical underpinnings of authorship attribution derive from the hypothesis that each writer possesses a unique linguistic fingerprint. This fingerprint manifests through consistent patterns in syntactic construction, lexical selection, and punctuation deployment. Quantitative analysis of these patterns enables the construction of multidimensional feature vectors suitable for computational comparison.",
            "Contemporary research has expanded the scope of stylometric analysis to encompass paragraph-level granularity. This fine-grained approach introduces challenges related to statistical reliability, as shorter text segments yield less stable feature measurements. The development of features robust to length variation remains an active area of investigation.",
            "Cross-domain evaluation protocols are essential for establishing the generalizability of authorship attribution systems. Training on one text genre and evaluating on another provides a rigorous test of whether the system captures genuine stylistic markers rather than superficial topical correlations. The PAN competition series has established standardized benchmarks for such evaluations.",
        ]
        self._source_texts["author_casual"] = [
            "So here's the thing about detecting plagiarism - it's way harder than most people think. You can't just look for copied sentences anymore because students have gotten really good at paraphrasing. What you need is something that looks at HOW someone writes, not just WHAT they write. That's where stylometry comes in, and honestly, it's pretty cool stuff.",
            "I've been working with clustering algorithms for a while now, and let me tell you, HDBSCAN is a game changer. Unlike k-means where you have to guess how many clusters you want, HDBSCAN figures it out on its own. Plus it handles noise really well - those weird data points that don't fit anywhere just get labeled as outliers instead of getting forced into a cluster where they don't belong.",
            "The biggest challenge we face is short text. Like, how do you analyze someone's writing style from just one paragraph? Some features work great on long documents but fall apart when you only have 50-100 words to work with. Character n-grams seem to hold up better than most other features at short lengths, which is why they're so popular in the research community.",
            "One thing that really bugs me about current plagiarism detection tools is how many false positives they generate. Every time a student uses common phrases or standard academic vocabulary, the tool flags it as suspicious. We need smarter systems that understand the difference between genuine coincidence and actual copying. That's basically what our project is trying to solve.",
            "Testing is super important but also super annoying. You need hundreds of documents with known ground truth to get any meaningful results. The PAN datasets are great for this - they give you real text with labels showing exactly where the author changes. Without that kind of data, you're basically just guessing whether your system actually works.",
        ]
        self._source_texts["author_technical"] = [
            "Algorithm 1 implements the PELT change-point detection procedure with O(n) expected complexity. Given an input signal x of length n and a penalty parameter beta, PELT recursively partitions the signal by minimizing the penalized cost function C(x[a:b]) + beta over all possible partition points. The rbf kernel cost function computes inter-point distances in a reproducing kernel Hilbert space.",
            "The feature extraction pipeline processes each paragraph independently through the spaCy NLP engine. Token-level attributes including part-of-speech tags, dependency labels, and morphological features are aggregated into 8 scalar statistics per paragraph. The resulting N x 8 feature matrix serves as input to both the HDBSCAN density estimator and the PELT sequential detector.",
            "StandardScaler normalization is applied prior to clustering to prevent features with large magnitudes from dominating the Euclidean distance metric. Without normalization, Yule's K (typical range 50-300) would overwhelm pronoun_ratio (typical range 0.01-0.10) by a factor of approximately 3000x, rendering the latter effectively invisible to the distance computation.",
            "HDBSCAN's min_cluster_size parameter controls the minimum number of paragraphs required to form a distinct authorial cluster. Setting this value too low increases sensitivity but also increases false positive rate, as natural stylistic variation within a single author's text may be misinterpreted as evidence of multiple authors. Cross-validation on the training set determines the optimal value.",
            "The boundary fusion module implements a majority-voting scheme between two independent detectors. HDBSCAN identifies boundaries as positions where cluster labels change between adjacent paragraphs. PELT identifies boundaries as statistically significant change points in the feature time series. Boundaries detected by both engines receive HIGH confidence; those detected by only one receive MEDIUM confidence.",
        ]

        # Save samples to disk for reproducibility
        for author, paragraphs in self._source_texts.items():
            author_dir = self.source_dir / author
            author_dir.mkdir(parents=True, exist_ok=True)
            with open(author_dir / "sample.txt", "w", encoding="utf-8") as f:
                f.write("\n\n".join(paragraphs))

        logger.info(f"Created {len(self._source_texts)} built-in sample authors")

    def _build_random_interleave(
        self, authors: List[str], index: int
    ) -> Optional[Dict[str, Any]]:
        """Build a document by randomly interleaving paragraphs from 2-3 authors."""
        n_authors = random.choice([2, 3])
        selected = random.sample(authors, min(n_authors, len(authors)))

        paragraphs = []
        labels = []

        # Pick 3-8 paragraphs total
        n_paras = random.randint(5, 10)
        for _ in range(n_paras):
            author_idx = random.randint(0, len(selected) - 1)
            author = selected[author_idx]
            available = self._source_texts.get(author, [])
            if available:
                paragraphs.append(random.choice(available))
                labels.append(author_idx)

        if len(paragraphs) < 3:
            return None

        # Derive boundaries from labels
        changes = [1 if labels[i] != labels[i - 1] else 0 for i in range(1, len(labels))]
        boundaries = [i + 1 for i, c in enumerate(changes) if c == 1]

        return {
            "id": f"synthetic_random_{index:03d}",
            "source": "synthetic_random",
            "strategy": "random_interleave",
            "paragraphs": paragraphs,
            "ground_truth": {
                "is_multi_author": len(set(labels)) > 1,
                "num_authors": len(set(labels)),
                "author_labels": labels,
                "boundaries": boundaries,
                "changes": changes,
            },
        }

    def _build_block_splice(
        self, authors: List[str], index: int
    ) -> Optional[Dict[str, Any]]:
        """Build a document by taking contiguous blocks from 2-3 authors (realistic)."""
        n_authors = random.choice([2, 3])
        selected = random.sample(authors, min(n_authors, len(authors)))

        paragraphs = []
        labels = []

        for author_idx, author in enumerate(selected):
            available = self._source_texts.get(author, [])
            if not available:
                continue
            # Take a contiguous block of 2-4 paragraphs
            block_size = min(random.randint(2, 4), len(available))
            start = random.randint(0, max(0, len(available) - block_size))
            block = available[start : start + block_size]
            paragraphs.extend(block)
            labels.extend([author_idx] * len(block))

        if len(paragraphs) < 3:
            return None

        changes = [1 if labels[i] != labels[i - 1] else 0 for i in range(1, len(labels))]
        boundaries = [i + 1 for i, c in enumerate(changes) if c == 1]

        return {
            "id": f"synthetic_block_{index:03d}",
            "source": "synthetic_block",
            "strategy": "block_splice",
            "paragraphs": paragraphs,
            "ground_truth": {
                "is_multi_author": len(set(labels)) > 1,
                "num_authors": len(set(labels)),
                "author_labels": labels,
                "boundaries": boundaries,
                "changes": changes,
            },
        }

    def _build_single_author(
        self, authors: List[str], index: int
    ) -> Optional[Dict[str, Any]]:
        """Build a genuine single-author document (control group)."""
        author = random.choice(authors)
        available = self._source_texts.get(author, [])

        if len(available) < 3:
            return None

        n_paras = min(random.randint(4, 8), len(available))
        paragraphs = random.sample(available, n_paras)
        labels = [0] * len(paragraphs)
        changes = [0] * (len(paragraphs) - 1)

        return {
            "id": f"synthetic_genuine_{index:03d}",
            "source": "synthetic_genuine",
            "strategy": "single_author",
            "paragraphs": paragraphs,
            "ground_truth": {
                "is_multi_author": False,
                "num_authors": 1,
                "author_labels": labels,
                "boundaries": [],
                "changes": changes,
            },
        }


# ─── Manifest Builder ────────────────────────────────────────────────────────

class ManifestBuilder:
    """Saves documents to disk and builds a manifest.json index."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def save(self, documents: List[Dict[str, Any]]) -> Path:
        """Save all documents and build manifest."""
        # Create subdirectories
        for subdir in ["pan", "synthetic", "genuine"]:
            (self.output_dir / subdir).mkdir(parents=True, exist_ok=True)

        manifest_entries = []

        for doc in documents:
            doc_id = doc["id"]
            source = doc.get("source", "unknown")

            # Determine subdirectory
            if source.startswith("pan"):
                subdir = "pan"
            elif source.startswith("synthetic_genuine"):
                subdir = "genuine"
            else:
                subdir = "synthetic"

            # Save document JSON
            doc_path = self.output_dir / subdir / f"{doc_id}.json"
            with open(doc_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)

            # Build manifest entry
            gt = doc.get("ground_truth", {})
            manifest_entries.append({
                "id": doc_id,
                "source": source,
                "path": str(doc_path.relative_to(self.output_dir)),
                "num_paragraphs": len(doc.get("paragraphs", [])),
                "is_multi_author": gt.get("is_multi_author", False),
                "num_authors": gt.get("num_authors", 1),
                "num_boundaries": len(gt.get("boundaries", [])),
            })

        # Build manifest
        manifest = {
            "version": "1.0",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_documents": len(manifest_entries),
            "breakdown": {
                "pan": len([e for e in manifest_entries if e["source"].startswith("pan")]),
                "synthetic_stitched": len([e for e in manifest_entries if e["source"].startswith("synthetic_") and e["source"] != "synthetic_genuine"]),
                "genuine": len([e for e in manifest_entries if e["source"] == "synthetic_genuine" or not e["is_multi_author"]]),
            },
            "documents": manifest_entries,
        }

        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.info(f"Manifest saved to {manifest_path}")
        logger.info(
            f"  PAN: {manifest['breakdown']['pan']} | "
            f"Synthetic: {manifest['breakdown']['synthetic_stitched']} | "
            f"Genuine: {manifest['breakdown']['genuine']}"
        )

        return manifest_path


# ─── Dataset Loader (for experiments) ────────────────────────────────────────

class DatasetLoader:
    """
    Load evaluation dataset from manifest for use in experiments.
    This is the interface that run_ablation.py, run_baselines.py, etc. will use.
    """

    def __init__(self, datasets_dir: Optional[Path] = None):
        self.datasets_dir = Path(datasets_dir or DATASETS_DIR)
        self.manifest_path = self.datasets_dir / "manifest.json"

    def load_manifest(self) -> Dict[str, Any]:
        """Load the manifest index."""
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_all(self) -> List[Dict[str, Any]]:
        """Load all documents from the manifest."""
        manifest = self.load_manifest()
        documents = []
        for entry in manifest["documents"]:
            doc_path = self.datasets_dir / entry["path"]
            with open(doc_path, "r", encoding="utf-8") as f:
                documents.append(json.load(f))
        return documents

    def load_by_source(self, source_prefix: str) -> List[Dict[str, Any]]:
        """Load documents matching a source prefix (e.g., 'pan', 'synthetic')."""
        manifest = self.load_manifest()
        documents = []
        for entry in manifest["documents"]:
            if entry["source"].startswith(source_prefix):
                doc_path = self.datasets_dir / entry["path"]
                with open(doc_path, "r", encoding="utf-8") as f:
                    documents.append(json.load(f))
        return documents

    def load_multi_author_only(self) -> List[Dict[str, Any]]:
        """Load only multi-author documents (for boundary detection)."""
        return [d for d in self.load_all() if d["ground_truth"]["is_multi_author"]]

    def load_genuine_only(self) -> List[Dict[str, Any]]:
        """Load only genuine single-author documents (for false positive rate)."""
        return [d for d in self.load_all() if not d["ground_truth"]["is_multi_author"]]

    def summary(self) -> str:
        """Print a human-readable summary of the dataset."""
        manifest = self.load_manifest()
        lines = [
            f"P.R.I.S.M. Evaluation Dataset v{manifest['version']}",
            f"Created: {manifest['created']}",
            f"Total documents: {manifest['total_documents']}",
            f"  PAN: {manifest['breakdown']['pan']}",
            f"  Synthetic stitched: {manifest['breakdown']['synthetic_stitched']}",
            f"  Genuine: {manifest['breakdown']['genuine']}",
        ]
        return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="P.R.I.S.M. Evaluation Dataset Builder"
    )
    parser.add_argument(
        "--pan-dir",
        type=str,
        default=str(DATASETS_DIR / "pan"),
        help="Path to extracted PAN 2023 dataset root",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DATASETS_DIR),
        help="Output directory for built dataset",
    )
    parser.add_argument(
        "--build-pan",
        action="store_true",
        help="Ingest PAN datasets",
    )
    parser.add_argument(
        "--build-synthetic",
        action="store_true",
        help="Build synthetic stitched documents",
    )
    parser.add_argument(
        "--synthetic-count",
        type=int,
        default=20,
        help="Number of synthetic documents to generate",
    )
    parser.add_argument(
        "--build-all",
        action="store_true",
        help="Build all dataset sources",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print dataset summary from existing manifest",
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    if args.summary:
        loader = DatasetLoader(output_dir)
        print(loader.summary())
        return

    all_documents = []

    if args.build_pan or args.build_all:
        logger.info("=== Ingesting PAN datasets ===")
        pan = PANIngester(Path(args.pan_dir))
        all_documents.extend(pan.ingest_all())

    if args.build_synthetic or args.build_all:
        logger.info("=== Building synthetic documents ===")
        synthetic = SyntheticBuilder()
        all_documents.extend(synthetic.build_all(count=args.synthetic_count))

    if not all_documents:
        logger.info("No data sources specified. Use --build-all, --build-pan, or --build-synthetic")
        logger.info(f"\nTo download PAN 2023 data: {PAN_ZENODO_URL}")
        logger.info("Extract to: research/datasets/pan/dataset1, dataset2, dataset3")
        return

    # Save everything
    builder = ManifestBuilder(output_dir)
    manifest_path = builder.save(all_documents)
    print(f"\n[OK] Dataset built successfully!")
    print(f"   Manifest: {manifest_path}")
    print(f"   Total documents: {len(all_documents)}")


if __name__ == "__main__":
    main()
