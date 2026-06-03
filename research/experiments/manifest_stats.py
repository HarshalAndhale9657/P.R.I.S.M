import json, numpy as np
m = json.load(open(r'd:\Devclash\research\datasets\manifest.json'))
docs = m['documents']
paras = [d['num_paragraphs'] for d in docs]
print(f"Total: {len(docs)}")
print(f"Avg paras: {np.mean(paras):.1f}")
print(f"Median: {np.median(paras):.1f}")
print(f"<=3: {sum(1 for p in paras if p<=3)}")
print(f"<=5: {sum(1 for p in paras if p<=5)}")
print(f"<=10: {sum(1 for p in paras if p<=10)}")
print(f"Breakdown: {m.get('breakdown', {})}")
