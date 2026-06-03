import json
import numpy as np

# Load manifest to check paragraph counts in failing docs
manifest = json.load(open(r'd:\Devclash\research\datasets\manifest.json'))

# Build a lookup
doc_lookup = {}
for doc in manifest:
    doc_lookup[doc['id']] = doc

# Load eval results
data = json.load(open(r'd:\Devclash\research\results\evaluation\evaluation_results.json'))
f3 = data['detectors']['fusion3']
details = f3['per_doc_details']

recall_fails = [d for d in details if d['true_boundaries'] and not d['pred_boundaries']]

# Check paragraph counts for recall failures
para_counts = []
for d in recall_fails:
    doc = doc_lookup.get(d['doc_id'])
    if doc:
        n = len(doc.get('paragraphs', []))
        para_counts.append(n)

print(f"Recall failures: {len(recall_fails)} docs")
print(f"  Avg paragraphs: {np.mean(para_counts):.1f}")
print(f"  Median paragraphs: {np.median(para_counts):.1f}")
print(f"  Min: {min(para_counts)}, Max: {max(para_counts)}")
print(f"  Docs with <=5 paragraphs: {sum(1 for p in para_counts if p <= 5)}")
print(f"  Docs with <=3 paragraphs: {sum(1 for p in para_counts if p <= 3)}")

# Successful detections
successes = [d for d in details if d['f1'] > 0.5]
succ_counts = []
for d in successes:
    doc = doc_lookup.get(d['doc_id'])
    if doc:
        succ_counts.append(len(doc.get('paragraphs', [])))

print(f"\nSuccessful detections (F1>0.5): {len(successes)}")
if succ_counts:
    print(f"  Avg paragraphs: {np.mean(succ_counts):.1f}")
    print(f"  Median paragraphs: {np.median(succ_counts):.1f}")

# Overall dataset paragraph distribution
all_counts = [len(d.get('paragraphs', [])) for d in manifest]
print(f"\nOverall dataset:")
print(f"  Total docs: {len(manifest)}")
print(f"  Avg paragraphs: {np.mean(all_counts):.1f}")
print(f"  Median paragraphs: {np.median(all_counts):.1f}")
print(f"  <=3 paragraphs: {sum(1 for p in all_counts if p <= 3)} ({100*sum(1 for p in all_counts if p <= 3)/len(all_counts):.1f}%)")
print(f"  <=5 paragraphs: {sum(1 for p in all_counts if p <= 5)} ({100*sum(1 for p in all_counts if p <= 5)/len(all_counts):.1f}%)")
print(f"  <=10 paragraphs: {sum(1 for p in all_counts if p <= 10)} ({100*sum(1 for p in all_counts if p <= 10)/len(all_counts):.1f}%)")

# Word counts per paragraph
word_counts = []
for doc in manifest[:50]:  # Sample
    for p in doc.get('paragraphs', []):
        word_counts.append(len(p.split()))
print(f"\nWord counts per paragraph (sample of 50 docs):")
print(f"  Avg: {np.mean(word_counts):.1f}")
print(f"  Median: {np.median(word_counts):.1f}")
print(f"  <50 words: {sum(1 for w in word_counts if w < 50)} ({100*sum(1 for w in word_counts if w < 50)/len(word_counts):.1f}%)")
