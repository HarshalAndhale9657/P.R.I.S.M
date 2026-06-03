import json
data = json.load(open(r'd:\Devclash\research\results\evaluation\evaluation_results.json'))
print(f"Dataset size: {data.get('dataset_size', '?')}")
print(f"Feature count: {data.get('feature_count', '?')}")
print()
print(f"{'Detector':20s} {'F1':>8} {'DocAcc':>8} {'Prec':>8} {'Recall':>8}")
print("-" * 56)
for k, v in data['detectors'].items():
    print(f"{k:20s} {v['mean_boundary_f1']:8.4f} {v['doc_accuracy']:8.4f} {v['mean_precision']:8.4f} {v['mean_recall']:8.4f}")

print()
print("=== Statistical Tests ===")
for k, v in data.get('statistical_tests', {}).items():
    if 'error' in v:
        print(f"  {k}: {v['error']}")
    else:
        sig = "SIG" if v.get('significant_at_005') else "n.s."
        print(f"  {k}: p={v['p_value']:.4f} ({sig}) improvement={v.get('improvement', 0):+.4f}")
