"""
Sample 100 random conversations from data/arena_candidates.json
Output: data/arena_sample100.json
"""

import json, random
from pathlib import Path
from collections import Counter

IN_FILE  = Path("data/arena_candidates.json")
OUT_FILE = Path("data/arena_sample100.json")

with open(IN_FILE) as f:
    data = json.load(f)

n = min(100, len(data))
sample = random.sample(data, n)

with open(OUT_FILE, "w") as f:
    json.dump(sample, f, indent=2)

print(f"Sampled {n} from {len(data)} total")
print("Signal breakdown:")
for sig, cnt in Counter(r["feedback_type"] for r in sample).most_common():
    print(f"  {sig}: {cnt}")
print(f"Saved -> {OUT_FILE}")