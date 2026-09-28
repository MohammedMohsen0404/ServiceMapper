import csv
import os
import sys

from search_refs import load_achi, load_sbs, load_drg, load_hcpcs, load_loinc, load_snomed, search

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) != 2:
        print("usage: python run_searches.py NNN", file=sys.stderr)
        sys.exit(1)

    nnn = sys.argv[1]
    batch_path = os.path.join(BASE, "batches", f"batch_{nnn}.csv")

    achi_sbs = load_achi() + load_sbs()
    drg = load_drg()
    hcpcs = load_hcpcs()
    loinc = load_loinc()
    snomed = load_snomed()

    with open(batch_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for i, r in enumerate(rows, start=1):
        query = r["service_normalized"]
        category = r["category"]
        print(f"### {i}: [{category}] {query}")

        if category == "inpatient":
            entries, max_n = drg, 10
        elif category == "supplies":
            # supplies are consumables/devices, not procedures -- search HCPCS
            # primarily, but keep ACHI/SBS in the mix in case it's actually a
            # procedure mislabeled as supplies. SNOMED as a fallback for
            # clinical-concept matches billing codes don't cover.
            entries, max_n = hcpcs + achi_sbs + snomed, 25
        elif category == "lab_test":
            # LOINC is the actual industry-standard lab test coding system and
            # covers many specific/branded lab tests ACHI/SBS don't; keep SBS
            # and SNOMED in the mix too.
            entries, max_n = loinc + achi_sbs + snomed, 25
        else:
            entries, max_n = achi_sbs + snomed, 15

        results = search(query, entries, max_n)
        printed = False
        for sc, e in results:
            if sc <= 0:
                continue
            print(f"{e['source']} {e['id']} | {e['desc']} | {sc:.2f}")
            printed = True
        if not printed:
            print("NO_MATCHES")
        print()


if __name__ == "__main__":
    main()
