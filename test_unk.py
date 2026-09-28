"""
Small test tool: for every current UNK row in a batch result, grep all reference
catalogs in D:\Tuba\TubaCode\Source for the row's key terms (and any matching
medical abbreviation expansion), and print what turns up for manual review.

Usage: python test_unk.py batch_001_result.csv
"""
import csv
import re
import sys
import urllib.parse
from pathlib import Path

SRC_DIR = Path(r"D:\Tuba\TubaCode\Source")
CATALOGS = {
    "ACHI": (SRC_DIR / "ACHI.csv", "utf-8-sig"),
    "SBS": (SRC_DIR / "SBS_V3.csv", "cp1256"),
    "HCPCS": (SRC_DIR / "HCPCII.csv", "utf-8-sig"),
    "CPT": (SRC_DIR / "CPT.csv", "utf-8-sig"),
    "DRG": (SRC_DIR / "MS-DRG.csv", "utf-8-sig"),
}
ABBR_PATH = SRC_DIR / "Medical_Abbreviations.csv"

STOPWORDS = {
    "the", "of", "and", "with", "in", "to", "a", "an", "for", "by", "at",
    "on", "or", "from", "nec", "nos", "unspecified", "other", "without",
    "unilateral", "bilateral", "per", "session", "each", "size", "left",
    "right", "s", "x", "mg", "ml", "cm", "mm",
}


def normalize(s):
    prev = s
    for _ in range(3):
        try:
            decoded = urllib.parse.unquote(prev)
        except Exception:
            break
        if decoded == prev:
            break
        prev = decoded
    prev = re.sub(r"[\u200b-\u200f\u0300-\u036f\u0610-\u061a\ufeff]", " ", prev)
    return prev


def tokenize(s):
    s = normalize(s)
    tokens = re.findall(r"[a-zA-Z]{2,}", s.lower())
    return [t for t in tokens if t not in STOPWORDS]


def load_abbreviations():
    abbr = {}
    with open(ABBR_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            key = r["Abbreviation"].strip().lower().replace(".", "")
            if key:
                abbr[key] = r["Stands For"].strip()
    return abbr


def load_lines(path, encoding):
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        return f.readlines()


def grep_all(term, catalog_lines, max_hits=5):
    results = {}
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    for name, lines in catalog_lines.items():
        hits = [ln.strip() for ln in lines if pattern.search(ln)]
        if hits:
            results[name] = hits[:max_hits]
    return results


def main():
    if len(sys.argv) != 2:
        print("usage: python test_unk.py batch_NNN_result.csv", file=sys.stderr)
        sys.exit(1)

    result_path = Path(sys.argv[1])
    if not result_path.is_absolute():
        result_path = Path(__file__).parent / result_path

    abbr = load_abbreviations()

    print("Loading catalogs...", file=sys.stderr)
    catalog_lines = {name: load_lines(path, enc) for name, (path, enc) in CATALOGS.items()}

    with open(result_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    unk_rows = [r for r in rows if r["code"] == "UNK"]
    print(f"{len(unk_rows)} UNK rows to test\n")

    for r in unk_rows:
        text = r["service_normalized"]
        norm = normalize(text)
        tokens = tokenize(text)

        print("=" * 100)
        print(f"canonical_id={r['canonical_id']} | category={r['corrected_category']}")
        print(f"raw:        {text}")
        if norm != text:
            print(f"decoded:    {norm}")

        # abbreviation expansions found in this row's tokens
        expansions = []
        for t in tokens:
            if t in abbr:
                expansions.append(f"{t} = {abbr[t]}")
        # also try dotted-abbreviation forms like k.k.t -> kkt
        dotted = re.findall(r"\b(?:[a-zA-Z]\.){2,}[a-zA-Z]?\b", norm)
        for d in dotted:
            key = d.replace(".", "").lower()
            if key in abbr:
                expansions.append(f"{d} = {abbr[key]}")
        if expansions:
            print("abbreviation matches: " + "; ".join(expansions))

        # grep each significant token (longer tokens first, cap at 4 terms to keep output sane)
        significant = sorted(set(tokens), key=len, reverse=True)[:4]
        any_hit = False
        for term in significant:
            if len(term) < 4:
                continue
            hits = grep_all(term, catalog_lines)
            if hits:
                any_hit = True
                print(f"-- grep '{term}' --")
                for src, lines in hits.items():
                    for ln in lines:
                        print(f"   [{src}] {ln[:160]}")
        if not any_hit:
            print("(no grep hits across ACHI/SBS/HCPCS/CPT/DRG for main terms)")
        print()


if __name__ == "__main__":
    main()
