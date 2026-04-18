import numpy as np

# Simulate human
human1 = [10, 25, 8, 40]  # highly variable
human2 = [18, 5, 22]

# Simulate AI
ai1 = [20, 22, 19, 21] 
ai2 = [15, 17, 16]     

def calc_burst(lengths):
    mean = sum(lengths)/len(lengths)
    return float(np.std(lengths) / max(mean, 1.0))

print(f"Human 1 burstiness: {calc_burst(human1):.4f}")
print(f"Human 2 burstiness: {calc_burst(human2):.4f}")
print(f"AI 1 burstiness: {calc_burst(ai1):.4f}")
print(f"AI 2 burstiness: {calc_burst(ai2):.4f}")
