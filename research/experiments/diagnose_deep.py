import json
import numpy as np

data = json.load(open(r'd:\Devclash\research\results\evaluation\evaluation_results.json'))
f3 = data['detectors']['fusion3']
details = f3['per_doc_details']

# Check genuine docs — F1=0 on genuine is actually BAD
genuine = [d for d in details if 'genuine' in d['doc_id']]
print("=== Genuine Documents (should have no boundaries) ===")
for d in genuine:
    print(f"  {d['doc_id']}: true_b={d['true_boundaries']}, pred_b={d['pred_boundaries']}, f1={d['f1']}, correct={d['correct']}")

# Look at the F1 computation issue: when true=[] and pred=[], it returns F1=1.0
# But when true=[] and pred=[x], it should return F1=0 (false positive)
print("\n=== Docs with no true boundaries ===")
no_true = [d for d in details if not d['true_boundaries']]
print(f"  Total docs with no true boundaries: {len(no_true)}")
for d in no_true[:10]:
    print(f"  {d['doc_id']}: pred_b={d['pred_boundaries']}, f1={d['f1']}, correct={d['correct']}")

# Check: how many PAN docs have 0 true boundaries?
pan_no_true = [d for d in details if 'pan' in d['doc_id'] and not d['true_boundaries']]
print(f"\n  PAN docs with 0 true boundaries: {len(pan_no_true)}")

# Recall problem analysis: look at paragraph counts in recall failures
recall_fails = [d for d in details if d['true_boundaries'] and not d['pred_boundaries']]
print(f"\n=== Recall Failures by Category ===")
from collections import Counter
cats = Counter()
for d in recall_fails:
    if 'pan_easy' in d['doc_id']: cats['pan_easy'] += 1
    elif 'pan_medium' in d['doc_id']: cats['pan_medium'] += 1
    elif 'pan_hard' in d['doc_id']: cats['pan_hard'] += 1
    else: cats['other'] += 1
for c, n in cats.most_common():
    print(f"  {c}: {n}")

# Look at boundary locations in recall failures
print(f"\n=== True boundary positions in recall failures (first 20) ===")
for d in recall_fails[:20]:
    print(f"  {d['doc_id']}: true={d['true_boundaries']}")
