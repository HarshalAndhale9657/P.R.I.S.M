"""
P.R.I.S.M. — Sentence-pair benchmark loader (ADR-0016: public datasets only)
============================================================================
A unified schema over ready-made public paraphrase / semantic-similarity sets so
any of them drops into the eval harness identically. This is the source of truth
for the paraphrase pillar of the matcher — it replaces both the self-authored
32-case set and PAN (which is the wrong task; see ADR-0016).

On-disk unified format — one JSON object per line at `eval/data/<name>/pairs.jsonl`:

    {"a": "...", "b": "...", "label": 1, "stratum": "paraphrase", "id": "paws-42"}

`label`: 1 = paraphrase/positive, 0 = negative.
`stratum`: a grouping for per-stratum FPR (the safety view). Convention:
    "paraphrase"             — positive pairs
    "high_overlap_negative"  — non-paraphrase w/ high lexical overlap (the ESL /
                               boilerplate trap; PAWS is built exactly for this)
    "non_paraphrase"         — ordinary negative
    "graded"                 — binarized from a graded-similarity set (STS-B)

The datasets themselves are NOT vendored (licences + size). Fetch them explicitly
with `python -m eval.fetch_datasets <name>` (writes the JSONL above). Until then
the loader raises `DatasetNotAvailable` with the exact command to run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

_EVAL_DIR = Path(__file__).resolve().parent
DATA_DIR = _EVAL_DIR / "data"


class DatasetNotAvailable(FileNotFoundError):
    """Raised when a registered dataset has not been fetched to disk yet."""


@dataclass(frozen=True)
class PairCase:
    a: str
    b: str
    label: int              # 1 = paraphrase/positive, 0 = negative
    stratum: str = "-"
    id: Optional[str] = None
    dataset: str = ""


@dataclass(frozen=True)
class DatasetInfo:
    name: str
    relpath: str            # relative to eval/data/
    description: str
    license: str
    homepage: str


# Registry of the public sets we sanctioned in ADR-0016. NO PAN.
DATASETS: Dict[str, DatasetInfo] = {
    "sample": DatasetInfo(
        "sample", "sample/pairs.jsonl",
        "Tiny hand-made smoke sample — NOT a benchmark, just to exercise the harness offline.",
        "internal", "",
    ),
    "paws": DatasetInfo(
        "paws", "paws/pairs.jsonl",
        "PAWS — paraphrase vs. non-paraphrase with HIGH lexical overlap (hard negatives).",
        "PAWS (Google Research), research use", "https://github.com/google-research-datasets/paws",
    ),
    "mrpc": DatasetInfo(
        "mrpc", "mrpc/pairs.jsonl",
        "Microsoft Research Paraphrase Corpus (GLUE/MRPC).",
        "MSR / GLUE terms", "https://www.microsoft.com/en-us/download/details.aspx?id=52398",
    ),
    "stsb": DatasetInfo(
        "stsb", "stsb/pairs.jsonl",
        "STS-B — graded semantic similarity, binarized for detection (sim>=4/5 -> paraphrase).",
        "STS Benchmark, research", "https://ixa2.si.ehu.eus/stswiki/index.php/STSbenchmark",
    ),
    "qqp": DatasetInfo(
        "qqp", "qqp/pairs.jsonl",
        "Quora Question Pairs — duplicate vs. non-duplicate questions.",
        "Quora QQP terms", "https://quoradata.quora.com/First-Quora-Dataset-Release-Question-Pairs",
    ),
    "pawsx": DatasetInfo(
        "pawsx", "pawsx/pairs.jsonl",
        "PAWS-X — multilingual PAWS (for translated / cross-lingual paraphrase).",
        "PAWS-X (Google Research), research use", "https://github.com/google-research-datasets/paws/tree/master/pawsx",
    ),
}


def available_datasets() -> List[DatasetInfo]:
    return list(DATASETS.values())


def _fetch_hint(name: str) -> str:
    return (f"Dataset {name!r} not found. Fetch it first:\n"
            f"    python -m eval.fetch_datasets {name}\n"
            f"(writes eval/data/{DATASETS[name].relpath})")


def load_jsonl(path: Path, dataset: str = "") -> List[PairCase]:
    cases: List[PairCase] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                cases.append(PairCase(
                    a=obj["a"], b=obj["b"], label=int(obj["label"]),
                    stratum=obj.get("stratum", "-"), id=obj.get("id"),
                    dataset=dataset or obj.get("dataset", ""),
                ))
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"{path}:{lineno}: malformed pair record ({exc})") from exc
    return cases


def load_dataset(name: str) -> List[PairCase]:
    """Load a registered dataset from disk. Raises DatasetNotAvailable if absent."""
    if name not in DATASETS:
        raise KeyError(f"Unknown dataset {name!r}. Known: {sorted(DATASETS)}")
    path = DATA_DIR / DATASETS[name].relpath
    if not path.exists():
        raise DatasetNotAvailable(_fetch_hint(name))
    return load_jsonl(path, dataset=name)
