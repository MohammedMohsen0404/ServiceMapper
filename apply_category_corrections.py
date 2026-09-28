"""
Apply corrected_category values from batch result files back into the
source service_classified.csv, so category fixes discovered during mapping
persist and don't need rediscovering in future runs.

Usage: python apply_category_corrections.py batch_001_result.csv [more_result_files...]
   or: python apply_category_corrections.py --all   (applies every results/batch_*_result.csv)
"""
import csv
import glob
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "service_classified.csv")
RESULTS_DIR = os.path.join(BASE, "results")


def load_corrections(result_paths):
    corrections = {}
    conflicts = []
    for path in result_paths:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                cid = r["canonical_id"]
                new_cat = r["corrected_category"].strip()
                if not new_cat:
                    continue
                if cid in corrections and corrections[cid] != new_cat:
                    conflicts.append((cid, corrections[cid], new_cat, path))
                corrections[cid] = new_cat
    return corrections, conflicts


def main():
    args = sys.argv[1:]
    if not args:
        print("usage: python apply_category_corrections.py batch_NNN_result.csv [...] | --all", file=sys.stderr)
        sys.exit(1)

    if args == ["--all"]:
        result_paths = sorted(glob.glob(os.path.join(RESULTS_DIR, "batch_*_result.csv")))
    else:
        result_paths = []
        for p in args:
            if os.path.isabs(p) or os.path.exists(p):
                result_paths.append(p)
            else:
                result_paths.append(os.path.join(RESULTS_DIR, os.path.basename(p)))

    if not result_paths:
        print("no result files found", file=sys.stderr)
        sys.exit(1)

    corrections, conflicts = load_corrections(result_paths)
    print(f"loaded {len(corrections)} corrections from {len(result_paths)} result file(s)")

    if conflicts:
        print(f"WARNING: {len(conflicts)} conflicting corrections for the same canonical_id (kept last seen):")
        for cid, old, new, path in conflicts[:20]:
            print(f"  {cid}: {old} -> {new} (from {os.path.basename(path)})")

    with open(SRC, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    changed = 0
    for row in rows:
        cid = row["canonical_id"]
        if cid in corrections and corrections[cid] != row["category"]:
            row["category"] = corrections[cid]
            changed += 1

    with open(SRC, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{changed} rows updated in {SRC}")
    print(f"{len(rows)} total rows written (row count preserved: {len(rows) == len(rows)})")


if __name__ == "__main__":
    main()
