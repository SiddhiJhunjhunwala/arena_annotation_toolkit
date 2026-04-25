"""
Sample 100 random conversations from data/arena_candidates.json
Output: data/arena_sample_100.json
"""

import json, random
from pathlib import Path

IN_FILE  = Path("data/arena_candidates.json")
OUT_FILE = Path("data/arena_sample_100.json")

with open(IN_FILE) as f:
    data = json.load(f)

n = min(100, len(data))
sample = random.sample(data, n)

with open(OUT_FILE, "w") as f:
    json.dump(sample, f, indent=2)

# Quick breakdown
from collections import Counter
counts = Counter(r["feedback_type"] for r in sample)
print(f"Sampled {n} from {len(data)} total")
print(f"Signal breakdown:")
for sig, cnt in counts.most_common():
    print(f"  {sig}: {cnt}")
print(f"Saved → {OUT_FILE}")