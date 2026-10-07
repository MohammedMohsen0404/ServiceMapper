"""Orchestrator verification of new-series result hand-backs (usage:
python verify_batches.py 1013 1011 ...). Checks row counts, order,
byte-identical canonical_id/service_normalized vs the input batch, counts
UNK/SKIP/HCPCS:V2020, issue-problem distribution, and validates every
distinct emitted code against its named catalog (as merge_results.py does).
"""
import csv
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = r"D:\Tuba\TubaCode\Source"
CATALOGS = [
    ("ACHI", os.path.join(SRC_DIR, "ACHI.csv"), "Code_id", "utf-8-sig"),
    ("SBS", os.path.join(SRC_DIR, "SBS_V3.csv"), "SBS Code Hyphenated", "cp1256"),
    ("DRG", os.path.join(SRC_DIR, "MS-DRG.csv"), "MS-DRG ", "utf-8-sig"),
    ("HCPCS", os.path.join(SRC_DIR, "HCPCII.csv"), "HCPC", "utf-8-sig"),
    ("LOINC", os.path.join(SRC_DIR, "LONIC.csv"), "LOINC_NUM", "utf-8-sig"),
    ("SNOMED", os.path.join(SRC_DIR, "SNOMED-CT.csv"), "Code", "utf-8-sig"),
]


def load_valid():
    valid = {}
    for tag, path, col, enc in CATALOGS:
        ids = set()
        with open(path, encoding=enc, errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                v = (r.get(col) or "").strip()
                if v:
                    ids.add(v)
                if tag == "SBS":
                    # some codes only appear in later columns; scan every field
                    for v in r.values():
                        v = (v or "").strip()
                        if v.count("-") == 2 and len(v.split("-")) == 3:
                            first = v.split("-")[0]
                            if first.isdigit() and all(x.isdigit() for x in v.split("-")[1:]):
                                ids.add(v)
        valid[tag] = ids
    return valid


def code_ok(code, valid):
    for part in code.split("|"):
        if ":" not in part:
            return False
        tag, cid = part.split(":", 1)
        if tag == "MS-DRG":
            tag = "DRG"  # agents emit MS-DRG:nnn; the valid-dict key is DRG
        if tag not in valid or cid not in valid[tag]:
            return False
    return True


def main(pairs):
    valid = load_valid()
    all_ok = True
    for n, new in pairs:
        res = os.path.join(BASE, "results", "batch_%d_result.csv" % new)
        iss = os.path.join(BASE, "results", "issue_batch_%d.csv" % new)
        inp = os.path.join(BASE, "batches_pending", "batch_%03d.csv" % n)
        rows = list(csv.DictReader(open(res, encoding="utf-8-sig", newline="")))
        issues = list(csv.DictReader(open(iss, encoding="utf-8-sig", newline="")))
        source = list(csv.DictReader(open(inp, encoding="utf-8-sig", newline="")))
        ok = all(
            a["canonical_id"] == b["canonical_id"]
            and a["service_normalized"] == b["service_normalized"]
            for a, b in zip(rows, source)
        )
        codes = [r["code"].strip() for r in rows]
        unk = codes.count("UNK")
        skip = codes.count("SKIP")
        v20 = codes.count("HCPCS:V2020")
        bad = sorted({c for c in codes if c not in ("UNK", "SKIP") and not code_ok(c, valid)})
        probs = {}
        for r in issues:
            probs[r["problem"]] = probs.get(r["problem"], 0) + 1
        good = ok and not bad and len(rows) == len(source)
        all_ok = all_ok and good
        print(
            "batch_%d: rows=%d issue=%d order_ok=%s UNK=%d SKIP=%d V2020=%d bad=%d %s"
            % (new, len(rows), len(issues), ok, unk, skip, v20, len(bad), bad[:8])
        )
        print("   problems:", probs)
    print("ALL PASS" if all_ok else "FAILURES PRESENT")


if __name__ == "__main__":
    main([(int(a) - 1000, int(a)) for a in sys.argv[1:]])