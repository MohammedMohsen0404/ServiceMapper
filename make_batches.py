import csv
import os
from math import ceil

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "mapping_descriptions.csv")
OUTDIR = os.path.join(BASE, "batches")
SIZE = 500

os.makedirs(OUTDIR, exist_ok=True)

with open(SRC, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

n = len(rows)
nb = ceil(n / SIZE)

for i in range(nb):
    batch_rows = rows[i * SIZE:(i + 1) * SIZE]
    path = os.path.join(OUTDIR, f"batch_{i + 1:03d}.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["canonical_id", "service_normalized", "occurrences", "category"])
        writer.writeheader()
        writer.writerows(batch_rows)

print(f"{n} rows -> {nb} batches in {OUTDIR}")
