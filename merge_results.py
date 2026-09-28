import csv
import glob
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "mapping_descriptions.csv")
RESULTS_DIR = os.path.join(BASE, "results")
OUT = os.path.join(BASE, "service_mapped_final.csv")
ISSUE_LOG = os.path.join(BASE, "issue_log.csv")

ACHI_PATH = r"D:\Tuba\TubaCode\Source\ACHI.csv"
SBS_PATH = r"D:\Tuba\TubaCode\Source\SBS_V3.csv"
DRG_PATH = r"D:\Tuba\TubaCode\Source\MS-DRG.csv"
HCPCS_PATH = r"D:\Tuba\TubaCode\Source\HCPCII.csv"
LOINC_PATH = r"D:\Tuba\TubaCode\Source\LONIC.csv"
SNOMED_PATH = r"D:\Tuba\TubaCode\Source\SNOMED-CT.csv"

BATCH_SIZE = 500


def load_valid_codes():
    achi_ids = set()
    with open(ACHI_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            achi_ids.add(r["Code_id"])

    sbs_ids = set()
    with open(SBS_PATH, encoding="cp1256", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            sbs_ids.add(r["SBS Code Hyphenated"])

    drg_ids = set()
    with open(DRG_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            drg_ids.add(r["MS-DRG "].strip())

    hcpcs_ids = set()
    with open(HCPCS_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            hcpcs_ids.add(r["HCPC"].strip())

    loinc_ids = set()
    with open(LOINC_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            loinc_ids.add(r["LOINC_NUM"].strip())

    snomed_ids = set()
    with open(SNOMED_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            snomed_ids.add(r["Code"].strip())

    return {
        "ACHI": achi_ids, "SBS": sbs_ids, "DRG": drg_ids, "HCPCS": hcpcs_ids,
        "LOINC": loinc_ids, "SNOMED": snomed_ids,
    }


def is_valid_code(code, valid):
    if code in ("UNK", "SKIP"):
        return True
    # combined procedures may carry multiple pipe-separated codes,
    # e.g. "ACHI:47384-02|ACHI:47384-03" for a both-bones ORIF
    parts = code.split("|")
    for part in parts:
        if ":" not in part:
            return False
        source, cid = part.split(":", 1)
        if source not in valid or cid not in valid[source]:
            return False
    return True


def load_all_batch_results():
    """Build a canonical_id -> result-row lookup across every batch result
    file present, plus a record of which batch each id came from. Keying by
    canonical_id (not positional index) makes this robust to batches/ being
    regenerated (e.g. after category corrections change row counts/order)."""
    by_id = {}
    for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "batch_*_result.csv"))):
        base = os.path.basename(path)
        # batch_NNN_result.csv -> NNN
        batch_n = base.split("_")[1]
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                cid = r.get("canonical_id", "").strip()
                if not cid:
                    continue
                by_id[cid] = (batch_n, r)
    return by_id


def main():
    valid = load_valid_codes()

    with open(SRC, encoding="utf-8-sig", newline="") as f:
        source_rows = list(csv.DictReader(f))

    n = len(source_rows)
    nb = (n + BATCH_SIZE - 1) // BATCH_SIZE

    results_by_id = load_all_batch_results()
    issues = []
    out_rows = []
    missing_files = 0
    mapped = 0
    unk = 0
    skip = 0

    for row in source_rows:
        cid = row["canonical_id"]
        code = "UNK"
        corrected_category = row["category"]

        entry = results_by_id.get(cid)
        if entry is None:
            missing_files += 1
            issues.append({
                "batch": "",
                "canonical_id": cid,
                "problem": "not_yet_processed",
            })
        else:
            batch_n, r = entry
            candidate = (r.get("code") or "UNK").strip()
            corrected_category = (r.get("corrected_category") or row["category"]).strip()
            if not is_valid_code(candidate, valid):
                issues.append({
                    "batch": batch_n,
                    "canonical_id": cid,
                    "problem": f"invalid_code:{candidate}",
                })
                code = "UNK"
            else:
                code = candidate

        if code == "UNK":
            unk += 1
        elif code == "SKIP":
            skip += 1
        else:
            mapped += 1

        out_rows.append({
            "canonical_id": row["canonical_id"],
            "service_normalized": row["service_normalized"],
            "occurrences": row["occurrences"],
            "original_category": row["category"],
            "corrected_category": corrected_category,
            "code": code,
        })

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "canonical_id", "service_normalized", "occurrences",
            "original_category", "corrected_category", "code",
        ])
        writer.writeheader()
        writer.writerows(out_rows)

    for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "issue_batch_*.csv"))):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                issues.append({
                    "batch": r.get("batch", ""),
                    "canonical_id": r.get("canonical_id", ""),
                    "problem": r.get("problem", ""),
                })

    with open(ISSUE_LOG, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["batch", "canonical_id", "problem"])
        writer.writeheader()
        writer.writerows(issues)

    print(f"rows={n} nb={nb} missing_files={missing_files} mapped={mapped} UNK={unk} SKIP={skip} issue_log_rows={len(issues)}")


if __name__ == "__main__":
    main()
