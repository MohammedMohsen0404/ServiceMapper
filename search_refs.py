import argparse
import csv
import re
import urllib.parse
from difflib import SequenceMatcher

ACHI_PATH = r"D:\Tuba\TubaCode\Source\ACHI.csv"
SBS_PATH = r"D:\Tuba\TubaCode\Source\SBS_V3.csv"
DRG_PATH = r"D:\Tuba\TubaCode\Source\MS-DRG.csv"
HCPCS_PATH = r"D:\Tuba\TubaCode\Source\HCPCII.csv"
CPT_PATH = r"D:\Tuba\TubaCode\Source\CPT.csv"
LOINC_PATH = r"D:\Tuba\TubaCode\Source\LONIC.csv"
SNOMED_PATH = r"D:\Tuba\TubaCode\Source\SNOMED-CT.csv"

STOPWORDS = {
    "the", "of", "and", "with", "in", "to", "a", "an", "for", "by", "at",
    "on", "or", "from", "nec", "nos", "unspecified", "other", "without",
    "unilateral", "bilateral", "per", "session", "each",
}


def normalize_query(s):
    # source data sometimes carries URL-encoded / mis-decoded text
    # (e.g. "%20amylase%20" -> " amylase ", stray zero-width/Arabic diacritic
    # bytes like %e2%80%8e, %d9%90). Decode repeatedly in case of
    # double-encoding, then strip non-printable/diacritic leftovers.
    prev = s
    for _ in range(3):
        try:
            decoded = urllib.parse.unquote(prev)
        except Exception:
            break
        if decoded == prev:
            break
        prev = decoded
    # drop zero-width and combining/diacritic characters that survive decoding
    prev = re.sub(r"[​-‏̀-ͯؐ-ؚ﻿]", " ", prev)
    return prev


def tokenize(s):
    s = normalize_query(s)
    tokens = re.findall(r"[a-z0-9]+", s.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def load_achi():
    entries = []
    with open(ACHI_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            text = r["ascii_desc"] or ""
            entries.append({
                "source": "ACHI",
                "id": r["Code_id"],
                "desc": text,
                "tokens": set(tokenize(text)),
                "text_lower": text.lower(),
            })
    return entries


def load_sbs():
    entries = []
    with open(SBS_PATH, encoding="cp1256", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            text = r["Long Description"] or ""
            entries.append({
                "source": "SBS",
                "id": r["SBS Code Hyphenated"],
                "desc": text,
                "tokens": set(tokenize(text)),
                "text_lower": text.lower(),
            })
    return entries


def load_drg():
    entries = []
    with open(DRG_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            text = r["MS-DRG Title"] or ""
            entries.append({
                "source": "DRG",
                "id": r["MS-DRG "].strip(),
                "desc": text,
                "tokens": set(tokenize(text)),
                "text_lower": text.lower(),
            })
    return entries


def load_hcpcs():
    entries = []
    with open(HCPCS_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            text = r["LONG DESCRIPTION"] or ""
            entries.append({
                "source": "HCPCS",
                "id": r["HCPC"].strip(),
                "desc": text,
                "tokens": set(tokenize(text)),
                "text_lower": text.lower(),
            })
    return entries


def load_cpt():
    entries = []
    with open(CPT_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            text = r["description"] or ""
            entries.append({
                "source": "CPT",
                "id": r["cpt_code"].strip(),
                "desc": text,
                "tokens": set(tokenize(text)),
                "text_lower": text.lower(),
            })
    return entries


def load_loinc():
    entries = []
    with open(LOINC_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # match against the long name plus its known synonyms/brand names
            # (RELATEDNAMES2 carries brand names like "Pyrilinks D")
            text = r["LONG_COMMON_NAME"] or ""
            synonyms = r["RELATEDNAMES2"] or ""
            match_text = f"{text} {synonyms}"
            entries.append({
                "source": "LOINC",
                "id": r["LOINC_NUM"].strip(),
                "desc": text,
                "tokens": set(tokenize(match_text)),
                "text_lower": match_text.lower(),
            })
    return entries


def load_snomed():
    entries = []
    with open(SNOMED_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            text = r["Description"] or ""
            entries.append({
                "source": "SNOMED",
                "id": r["Code"].strip(),
                "desc": text,
                "tokens": set(tokenize(text)),
                "text_lower": text.lower(),
            })
    return entries


def score(query, entry):
    q_tokens = tokenize(query)
    if not q_tokens:
        return 0.0
    q_set = set(q_tokens)
    overlap = q_set & entry["tokens"]
    s = 3.0 * len(overlap) / len(q_set)

    query_norm = " ".join(q_tokens)
    if query_norm and query_norm in entry["text_lower"]:
        s += 5.0

    ratio = SequenceMatcher(None, normalize_query(query).lower(), entry["text_lower"]).ratio()
    s += 2.0 * ratio

    for t in q_tokens:
        if f" {t} " in f" {entry['text_lower']} ":
            s += 0.5

    return s


def search(query, entries, max_n=10):
    scored = [(score(query, e), e) for e in entries]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:max_n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--source", choices=["achi", "sbs", "drg", "hcpcs", "cpt", "loinc", "snomed", "both"], default="both",
                     help="which reference catalog(s) to search")
    ap.add_argument("--max", type=int, default=15)
    args = ap.parse_args()

    entries = []
    if args.source in ("achi", "both"):
        entries += load_achi()
    if args.source in ("sbs", "both"):
        entries += load_sbs()
    if args.source == "drg":
        entries += load_drg()
    if args.source == "hcpcs":
        entries += load_hcpcs()
    if args.source == "cpt":
        entries += load_cpt()
    if args.source == "loinc":
        entries += load_loinc()
    if args.source == "snomed":
        entries += load_snomed()

    results = search(args.query, entries, args.max)
    if not results or results[0][0] <= 0:
        print("NO_MATCHES")
        return
    for sc, e in results:
        if sc <= 0:
            continue
        print(f"{e['source']} {e['id']} | {e['desc']} | {sc:.2f}")


if __name__ == "__main__":
    main()
