"""Applies the documented merge-convert ledger (conventions.md) to the
batch_*_result.csv files, so the merge harmonization recorded across the
run reaches the final file. Deterministic rule set; prints per-rule counts.
Deferred (ambiguous wording-scope) entries stay untouched — see ledger notes:
092 14680-3->5912-1, polarized V2762-vs-039, cast-removal 007/099 decision.
"""
import csv
import glob
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE, "results")

BY_ID = {
    "145922": "HCPCS:A4670",   # 141/144: BP monitor A4670 exists (false UNK)
    "145899": "HCPCS:C1769",   # 141/149: C1769 Guide wire exists (false UNK)
    "145900": "HCPCS:C1769",
    "146000": "HCPCS:C1769",
}

# Batches whose hand-backs are not yet verified (in-flight agents) — never
# touch their files; a later ledger run covers them once verified.
SKIP_BATCHES = {112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123,
                124, 158}

RULES = [
    # (name, batch_or_any, match_fn(code), wording_fn(service), replacement_fn)
    ("rfa 50950-00 -> 90299-02", "*", lambda c: c == "ACHI:50950-00", None, lambda c, w: "ACHI:90299-02"),
    ("cerclage inserts -> 16511-00", "*",
     lambda c: c in ("SNOMED:265636007", "SNOMED:90442009", "SNOMED:46681009",
                     "SNOMED:236946009", "SNOMED:236947000"), None,
     lambda c, w: "ACHI:16511-00"),
    ("cerclage removal -> 16512-00", "*", lambda c: c == "SNOMED:149899004", None,
     lambda c, w: "ACHI:16512-00"),
    ("ear C&S -> SBS 73050-40-34", "*", lambda c: c == "LOINC:112891-7",
     lambda w: re.search(r"\bear\b", w, re.I), lambda c, w: "SBS:73050-40-34"),
    ("CXL cornea uni -> 42652-00-11", "*", lambda c: c == "SNOMED:816029007",
     lambda w: re.search(r"cornea|cross.?link|cxl", w, re.I)
               and not re.search(r"bilat|both|\b2 eye|\bboth eye", w, re.I),
     lambda c, w: "SBS:42652-00-11"),
    ("CXL cornea bil -> 42652-00-12", "*", lambda c: c == "SNOMED:816029007",
     lambda w: re.search(r"cornea|cross.?link|cxl", w, re.I)
               and re.search(r"bilat|both", w, re.I),
     lambda c, w: "SBS:42652-00-12"),
    ("092 A&P KUB-contrast -> 56507-00-00", "092",
     lambda c: "SBS:56507-00-10" in c,
     lambda w: not re.search(r"kub|\bwith contrast\b", w, re.I),
     lambda c, w: c.replace("SBS:56507-00-10", "SBS:56507-00-00")),
    ("099 Titan C1752 -> C1750", "099", lambda c: c == "HCPCS:C1752",
     lambda w: re.search(r"titan", w, re.I), lambda c, w: "HCPCS:C1750"),
    ("038 Acuvue V2523 -> V2520", "038", lambda c: c == "HCPCS:V2523",
     lambda w: re.search(r"acuvue", w, re.I), lambda c, w: "HCPCS:V2520"),
    ("043 quant d-dimer -> 111766-2", "043", lambda c: c == "LOINC:48058-2",
     lambda w: re.search(r"quant", w, re.I), lambda c, w: "LOINC:111766-2"),
    # user directive: ALL eyewear rows -> HCPCS:V2020 (UNK leftovers in done
    # batches; walking frames / frameworks excluded by is_eyewear).
    ("eyewear UNK -> V2020", "*",
     lambda c: c == "UNK",
     lambda w: is_eyewear(w),
     lambda c, w: "HCPCS:V2020"),
    # (085-090-era plain-CT rows; wording must name brain/head since the
    # catalog entry is brain-specific).
    ("plain-brain CT 56007 -> 56001 (all)", "*",
     lambda c: c == "SBS:56007-00-00",
     lambda w: "contrast" not in w
               and re.search(r"\bbrain\b|\bhead\b", w, re.I),
     lambda c, w: "SBS:56001-00-00"),
    # dual-phase wordings must carry the 56001|56007 pipe (082 precedent).
    ("dual-phase w-only 56007 -> pipe", "*",
     lambda c: c == "SBS:56007-00-00",
     lambda w: "contrast" in w and re.search(r"w/o|without|before and after", w, re.I)
               and re.search(r"w/|with", w, re.I),
     lambda c, w: "SBS:56001-00-00|SBS:56007-00-00"),
    # catalog titles read directly by 159-verify: fluoride literal sits on
    # 97121-00; -01 is the remineralisation agent.
    ("fluoride -> 97121-00", "*",
     lambda c: c == "ACHI:97121-01",
     lambda w: re.search(r"fluorid|flourid", w),
     lambda c, w: "ACHI:97121-00"),
]


def main():
    counts = {r[0]: 0 for r in RULES}
    changed = {}
    for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "batch_*_result.csv"))):
        base = os.path.basename(path)
        batch_n = base.split("_")[1]
        if batch_n.isdigit() and int(batch_n) in SKIP_BATCHES:
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else None
        dirty = False
        for r in rows:
            cid = r.get("canonical_id", "")
            code = r.get("code", "")
            word = (r.get("service_normalized") or "").lower()
            new_code = code
            if cid in BY_ID and code.strip() == "UNK":
                new_code = BY_ID[cid]
                counts["by-id " + new_code] = counts.get("by-id " + new_code, 0) + 1
            else:
                for name, batch, mtch, wordr, repl in RULES:
                    if batch != "*" and batch != batch_n:
                        continue
                    if mtch(code) and (wordr is None or wordr(word)):
                        new_code = repl(code, word)
                        counts[name] += 1
                        break
            if new_code != code:
                r["code"] = new_code
                changed.setdefault(name if cid not in BY_ID else "by-id", []).append(cid)
                dirty = True
        if dirty:
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
    for name, n in counts.items():
        if n:
            print(f"{n:5d}  {name}")
    total = sum(counts.values())
    print(f"TOTAL conversions: {total}")
    patch_merged_eyewear()


def is_eyewear(w):
    if re.search(r"walking frame|framework", w, re.I):
        return False
    return bool(re.search(r"\b(eyewear|eye wear|frames?|glasses|sunglasses?|spectacles?|eye glasses)\b", w, re.I))


def patch_merged_eyewear():
    """Post-merge pass on service_mapped_final.csv: every UNK eyewear row
    (frames/glasses/sunglasses/spectacles) -> HCPCS:V2020, counted as
    processed per the user's eyewear directive. Must run AFTER
    merge_results.py; survives every re-merge because it re-runs each time."""
    out_path = os.path.join(BASE, "service_mapped_final.csv")
    if not os.path.exists(out_path):
        print("patch_merged_eyewear: no merged file yet")
        return
    with open(out_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    n = 0
    for r in rows:
        if (r.get("code") or "").strip() == "UNK" and is_eyewear(r.get("service_normalized") or ""):
            r["code"] = "HCPCS:V2020"
            n += 1
    if n:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"merged-file eyewear -> V2020: {n}")


if __name__ == "__main__":
    main()