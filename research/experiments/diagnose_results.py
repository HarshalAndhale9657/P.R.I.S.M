import json
import numpy as np

data = json.load(open(r'd:\Devclash\research\results\evaluation\evaluation_results.json'))

# Analyze fusion3 (best detector) per-doc to understand failure modes
f3 = data['detectors']['fusion3']
details = f3['per_doc_details']

# Categorize
perfect = [d for d in details if d['f1'] == 1.0]
partial = [d for d in details if 0 < d['f1'] < 1.0]
zero_f1 = [d for d in details if d['f1'] == 0.0]

print(f"Total docs evaluated: {len(details)}")
print(f"  Perfect (F1=1.0):  {len(perfect)} ({100*len(perfect)/len(details):.1f}%)")
print(f"  Partial (0<F1<1):  {len(partial)} ({100*len(partial)/len(details):.1f}%)")  
print(f"  Zero    (F1=0.0):  {len(zero_f1)} ({100*len(zero_f1)/len(details):.1f}%)")

# Breakdown of zero-F1 failures
print(f"\n=== Zero-F1 Failure Analysis ===")
no_true_no_pred = [d for d in zero_f1 if not d['true_boundaries'] and not d['pred_boundaries']]
has_true_no_pred = [d for d in zero_f1 if d['true_boundaries'] and not d['pred_boundaries']]
no_true_has_pred = [d for d in zero_f1 if not d['true_boundaries'] and d['pred_boundaries']]
both_but_miss = [d for d in zero_f1 if d['true_boundaries'] and d['pred_boundaries']]

print(f"  No true, no pred (shouldn't be F1=0):  {len(no_true_no_pred)}")
print(f"  Has true, no pred (RECALL failure):    {len(has_true_no_pred)}")
print(f"  No true, has pred (PRECISION failure):  {len(no_true_has_pred)}")
print(f"  Both exist, none match (LOCATION err):  {len(both_but_miss)}")

# Avg boundary counts for recall failures
if has_true_no_pred:
    avg_true_b = np.mean([len(d['true_boundaries']) for d in has_true_no_pred])
    print(f"\n  Recall failures avg true boundaries: {avg_true_b:.1f}")
    # Show first 5
    print(f"\n  First 5 recall failures:")
    for d in has_true_no_pred[:5]:
        print(f"    {d['doc_id']}: true={d['true_boundaries']}, pred={d['pred_boundaries']}")

# Doc-level breakdown
correct_count = sum(1 for d in details if d['correct'])
print(f"\n=== Doc-Level ===")
print(f"  Correct: {correct_count}/{len(details)} = {100*correct_count/len(details):.1f}%")

# Category breakdown
from collections import defaultdict
cat_f1 = defaultdict(list)
for d in details:
    did = d['doc_id']
    if 'pan_easy' in did: cat = 'pan_easy'
    elif 'pan_medium' in did: cat = 'pan_medium'
    elif 'pan_hard' in did: cat = 'pan_hard'
    elif 'genuine' in did: cat = 'genuine'
    elif 'stitched' in did: cat = 'stitched'
    elif 'ai_mixed' in did: cat = 'ai_mixed'
    elif 'edge' in did: cat = 'edge_case'
    else: cat = 'other'
    cat_f1[cat].append(d['f1'])

print(f"\n=== By Category ===")
for cat, f1s in sorted(cat_f1.items()):
    print(f"  {cat:15s}  n={len(f1s):3d}  mean_F1={np.mean(f1s):.4f}  median_F1={np.median(f1s):.4f}")
