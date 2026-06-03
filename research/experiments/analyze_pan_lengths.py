"""Quick analysis of PAN paragraph lengths to diagnose feature extraction issues."""
import statistics
from pathlib import Path

pan_root = Path(r"d:/Devclash/pan23-multi-author-analysis/release")
word_counts = []
para_counts = []
ds_stats = {}

datasets = [
    ("pan23-multi-author-analysis-dataset1", "easy"),
    ("pan23-multi-author-analysis-dataset2", "medium"),
    ("pan23-multi-author-analysis-dataset3", "hard"),
]

for ds_dir, diff in datasets:
    ds_words = []
    for split_suffix in ["-train", "-validation"]:
        split_name = ds_dir + split_suffix
        split_dir = pan_root / ds_dir / split_name
        if not split_dir.exists():
            continue
        files = sorted(split_dir.glob("problem-*.txt"))[:200]
        for f in files:
            text = f.read_text(encoding="utf-8")
            paras = [p.strip() for p in text.split("\n") if p.strip()]
            para_counts.append(len(paras))
            for p in paras:
                wc = len(p.split())
                word_counts.append(wc)
                ds_words.append(wc)
    ds_stats[diff] = ds_words

print(f"Sampled {len(para_counts)} documents, {len(word_counts)} paragraphs")
print(f"Paragraphs per doc: min={min(para_counts)} max={max(para_counts)} mean={statistics.mean(para_counts):.1f} median={statistics.median(para_counts):.0f}")
print(f"Words per paragraph: min={min(word_counts)} max={max(word_counts)} mean={statistics.mean(word_counts):.1f} median={statistics.median(word_counts):.0f}")
print()

# Distribution buckets
limits = [10, 20, 30, 50, 100]
labels = ["<10", "10-19", "20-29", "30-49", "50-99", "100+"]
for diff, ws in ds_stats.items():
    print(f"--- {diff.upper()} ({len(ws)} paragraphs) ---")
    for i, label in enumerate(labels):
        lo = limits[i-1] if i > 0 else 0
        hi = limits[i] if i < len(limits) else 999999
        count = len([w for w in ws if lo <= w < hi])
        pct = 100 * count / max(len(ws), 1)
        bar = "#" * int(pct / 2)
        print(f"  {label:>8s}: {count:5d} ({pct:5.1f}%)  {bar}")
    print()

# Current tier pass rates
total = len(word_counts)
skip = len([w for w in word_counts if w < 50])
reduced = len([w for w in word_counts if 50 <= w < 100])
full = len([w for w in word_counts if w >= 100])
print(f"=== CURRENT TIER PASS RATES ===")
print(f"  SKIP    (<50 words):  {skip:5d}/{total} = {100*skip/total:.1f}%  <-- ALL ZEROS in feature matrix!")
print(f"  REDUCED (50-99):      {reduced:5d}/{total} = {100*reduced/total:.1f}%  <-- Only avg_sentence_length")
print(f"  FULL    (100+):       {full:5d}/{total} = {100*full/total:.1f}%  <-- All 27 features")
print()

# What would a 20-word threshold give?
skip20 = len([w for w in word_counts if w < 20])
usable20 = total - skip20
print(f"=== IF WE LOWER SKIP TO 20 WORDS ===")
print(f"  Would skip:  {skip20:5d}/{total} = {100*skip20/total:.1f}%")
print(f"  Would use:   {usable20:5d}/{total} = {100*usable20/total:.1f}%")
print()

# Per-difficulty: avg valid features with current thresholds  
print(f"=== PER-DOC VALID PARAGRAPH RATIO (current 50-word threshold) ===")
for diff, ws in ds_stats.items():
    valid = len([w for w in ws if w >= 50])
    print(f"  {diff:>8s}: {valid}/{len(ws)} paragraphs valid = {100*valid/max(len(ws),1):.1f}%")
