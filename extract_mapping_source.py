import csv

SRC = r"D:\Tuba\Service Mapper\service_classified.csv"
OUT = r"D:\Tuba\Service Mapper\mapping_descriptions.csv"

EXCLUDED = {"drug", "person", "vaccine"}

with open(SRC, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    rows = [r for r in reader if r["category"] not in EXCLUDED]

with open(OUT, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["canonical_id", "service_normalized", "occurrences", "category"])
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "canonical_id": r["canonical_id"],
            "service_normalized": r["service_normalized"],
            "occurrences": r["occurrences"],
            "category": r["category"],
        })

print(f"{len(rows)} eligible rows -> {OUT}")
