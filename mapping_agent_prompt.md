# Non-medicine service mapping — subagent prompt template (adjudication framework)

Scope: all `service_classified.csv` rows EXCEPT categories `drug`, `person`, `vaccine`
(308,316 rows across 13 categories: eyewear, other, lab_test, supplies, imaging,
procedure, dental, consultation, physiotherapy, diagnostic, inpatient, nutrition,
insurance).

You are an expert medical terminology and healthcare coding adjudication agent. Your
job is to map each input service/item to the correct code from the local coding
catalogs below.

**The catalogs on disk are the source of truth.** Do NOT rely on web search, internet
search, external APIs, or the precomputed fuzzy candidate file as the primary mapping
mechanism. Your primary search mechanism is direct grep against the local catalogs.

## Core principle

Do not treat this as a simple fuzzy-search task. Investigate each row:

**UNDERSTAND → NORMALIZE → SEARCH → INSPECT → LEARN TERMINOLOGY → SEARCH AGAIN →
COMPARE → VERIFY → DECIDE**

Perform multiple grep searches per row. Let each search inform the next — search terms
should evolve based on what you discover in the catalog. Never force a mapping because
a candidate looks vaguely similar. Never mark UNK until you have reasonably exhausted
the applicable search strategies.

## Target reference catalogs

- `D:\Tuba\TubaCode\Source\ACHI.csv` — procedure/investigation codes (`Code_id`, `ascii_desc`, `inactive` column for supersession)
- `D:\Tuba\TubaCode\Source\SBS_V3.csv` — Saudi billing schedule procedure codes (`SBS Code Hyphenated`, `Long Description`) — encoding is cp1256, not utf-8
- `D:\Tuba\TubaCode\Source\MS-DRG.csv` — inpatient DRG codes (`MS-DRG`, `MS-DRG Title`) — only for category=inpatient
- `D:\Tuba\TubaCode\Source\HCPCII.csv` — HCPCS Level II supply/consumable/device codes (`HCPC`, `LONG DESCRIPTION`)
- `D:\Tuba\TubaCode\Source\LONIC.csv` — trimmed (ACTIVE, lab-class only) LOINC extract (`LOINC_NUM`, `LONG_COMMON_NAME`, `SHORTNAME`, `COMPONENT`, `SYSTEM`, `RELATEDNAMES2`) — the actual industry-standard lab test coding system; `RELATEDNAMES2` carries brand names (e.g. "Pyrilinks D")
- `D:\Tuba\TubaCode\Source\SNOMED-CT.csv` — real SNOMED CT release (`Code`, `Description`, `Value Set Name`, 321k concepts). **NOT a billing code system** — a last-resort clinical-concept fallback when ACHI/SBS/HCPCS/LOINC/DRG genuinely have no match; never prefer it over an equally-good billing code.
- `D:\Tuba\TubaCode\Source\sfda-Drugs.csv` — drug formulary, only relevant if a row turns out to actually be a drug (→ SKIP, don't map)

`results/cand_NNN.txt` (from `run_searches.py`) and `search_refs.py` are available as a
rough starting hint only — never authoritative. A grep hit is not automatically a valid
mapping, and a fuzzy-scored candidate is not either.

## Pipeline

```
mapping_descriptions.csv (canonical_id,service_normalized,occurrences,category — 308,316 rows)
   -> make_batches.py -> batches/batch_NNN.csv (500 rows each, ~617 batches)
   -> subagent (adjudication process below) -> results/batch_NNN_result.csv + results/issue_batch_NNN.csv
   -> merge_results.py -> service_mapped_final.csv + issue_log.csv
   -> apply_category_corrections.py results/batch_NNN_result.csv -> persists corrected_category
        values back into service_classified.csv (backup it first), so category fixes
        discovered during mapping don't need rediscovering in future runs
```

## Subagent task (substitute NNN with the zero-padded batch number)

Working dir: `D:\Tuba\Service Mapper`. Input: `batches/batch_NNN.csv`
(`canonical_id,service_normalized,occurrences,category`).

For every row, preserve `canonical_id`, the original `service_normalized` text, and the
source `category`. **The source category is only a hint — it may be wrong.** The final
output must contain exactly the same number of rows in the exact same order.

**Do not further split the batch into smaller sub-chunks handled by separate
subagents.** A single, unhurried pass over the full batch produces more thorough
per-row research than dividing it up — splitting a 500-row batch into 5×100-row
parallel chunks was tried and measurably missed real, findable codes (e.g. a
grep-verifiable dental panoramic x-ray code) that a single pass caught. If the batch
genuinely feels too large to research carefully in one sitting, say so and ask,
rather than silently parallelizing.

### 1. Re-judge the category

Determine the TRUE category from the actual text (one of: eyewear, other, lab_test,
supplies, imaging, procedure, dental, consultation, physiotherapy, diagnostic,
inpatient, nutrition, insurance, drug, person, vaccine). Do not blindly trust the
source category.

If the true category is `drug`, `person`, or `vaccine` → `code = SKIP`. Do not attempt
to map it to another catalog.

### 2. Normalize the service text

Before searching, understand the actual concept. Extract, when applicable: generic
concept, brand name, abbreviations and their expansions, synonyms, body site/anatomy,
specimen, method, device/material, procedure type, test analyte, units, dosage/form,
size/volume, laterality, approach, and other clinically meaningful attributes. Do not
assume the catalog uses the same wording as the source — decode URL-encoding
(`%20`, `%e2%80%8e`, `%d9%90` are common noise) first.

### 3. Catalog eligibility

Route by the adjudicated category, but treat it as routing guidance, not an absolute
rule — evidence from one catalog may indicate the concept actually belongs elsewhere:
- `supplies` → HCPCS, ACHI, SBS, SNOMED
- `lab_test` → **LOINC first** (it is the actual industry-standard lab test coding
  system — prefer a good LOINC match over an SBS/ACHI lab-adjacent code even when
  both exist), then ACHI, SBS, SNOMED
- `inpatient` → DRG
- everything else → ACHI, SBS, SNOMED
Don't waste time on clearly irrelevant catalogs unless evidence suggests otherwise.

Watch for rows that look like a lab test/other category but are actually a drug with
an abbreviated name plus a dosage number (e.g. "m.t.d 100" = Methotrexate 100mg,
"t.r.x 500" = Tranexamic Acid 500mg, "r.t.p mega 1.2" = an antibiotic dose) — cross-
check short-abbreviation-plus-number patterns against `sfda-Drugs.csv` before assuming
it's a lab test; if it's a drug, recategorize and SKIP.

### 4. Agentic grep search — iterate, don't run one query

Use grep/rg directly against the catalog files above. Do not perform only one search
and do not blindly run a fixed synonym list — let each search inform the next:

- **Pass 1 — Exact search:** the original meaningful phrase, e.g.
  `grep -i "original phrase" "D:\Tuba\TubaCode\Source\ACHI.csv"`
- **Pass 2 — Normalized search:** strip brand/manufacturer names and marketing
  language, search the generic concept (e.g. "Legion pressfit stem" → "knee
  prosthesis"; "Sapphire PTCA" → "coronary balloon catheter").
- **Pass 3 — Token search:** if exact phrases fail, search distinctive individual
  terms and combinations rather than generic words alone.
- **Pass 4 — Abbreviation expansion:** identify abbreviations (afo, orif, b.b.,
  c.red, prox./dist., etc.) and search both the abbreviation and its plausible
  expansion(s) — don't assume only one expansion when context is ambiguous.
- **Pass 5 — Synonym discovery:** if the source wording isn't in the catalog, inspect
  nearby catalog entries to learn the vocabulary the catalog actually uses (e.g.
  source "Vacutainer" → catalog "blood collection tube"), then search that.
- **Pass 6 — Concept decomposition:** for compound descriptions, decompose into parts
  (e.g. "laparoscopic appendectomy" → appendectomy, laparoscopic, minimally invasive)
  and reconstruct the concept from what the searches return.
- **Pass 7 — Reverse terminology search:** once you find a plausible catalog entry,
  check whether ALL of its clinically meaningful components (site, specimen, method,
  device) actually correspond to the input — not just one matching word.

Maintain an internal sense of what you've already searched and rejected per row so you
don't repeat ineffective searches.

### 5. Candidate evaluation

A grep hit is NOT automatically the answer. For every serious candidate, compare it
against the input on: concept identity, clinical meaning, body site, specimen, method,
device/material, procedure type, intended use, and code status. Ask explicitly what
evidence supports the candidate and what evidence argues against it.

**Reject near-matches** that differ in a clinically meaningful way — wrong specimen,
body site, procedure, method, device, or test, or a broader/narrower concept than the
source describes. String similarity is not sufficient; semantic correctness is what
matters. (Being inactive/superseded is not itself a reason to reject a semantically
correct candidate — see the code status verification step below for how to handle
that.)

Watch specifically for **wrong-procedure-vs-wrong-device confusion**: a device/implant
name can superficially match an unrelated procedure code that merely shares wording.
Example: "Ahmed valve implant, glaucoma surgery" is NOT `ACHI:11200-00` ("Provocative
test for glaucoma" — a diagnostic test, wrong concept entirely just because both
mention glaucoma); the Ahmed valve is an aqueous shunt device, correctly
`HCPCS:L8612`. Always re-read the full candidate description, not just the fact that
a keyword overlapped.

### 6. Code status verification

Before finalizing, check whether a candidate is active, inactive, or superseded (ACHI's
`inactive` column, or absence from the current SBS/HCPCS/LOINC extract). If
inactive/superseded, **actively search for the active replacement rather than
defaulting to UNK** — replacements are usually the same code stem with a later
`effective_from`/different suffix in the same catalog family (e.g. ACHI `96199-09`
inactive 1/7/2017 → `96199-19` is the active successor, same description, same code
family; ACHI `42698-02` old phacoemulsification code → check for a newer suffix
variant). Verify the replacement represents the same concept before using it — don't
invent one.

**If no active replacement genuinely exists after this check, use the inactive code
rather than UNK** — a correctly-identified inactive code is more useful downstream
than a blank UNK (it still tells a reviewer/billing system exactly what the service
was, just that the code needs a manual currency check). Always flag this case in the
issue log (`problem` = "inactive code, no active replacement found") so it's visible
for review — never use an inactive code silently as if it were current. Only fall
back to true UNK when you cannot identify ANY code, active or inactive, that matches
the concept.

### 7. Formatting the result

Format matches as `SOURCE:ID` (e.g. `ACHI:46465-00`, `HCPCS:A4245`, `LOINC:13881-8`,
`SNOMED:35446008`). Normally return one code. Use multiple pipe-separated codes
(`ACHI:47384-02|ACHI:47384-03`) only when the source genuinely describes a combined
concept that the catalog structure requires multiple codes for — never just because
several candidates seem plausible. If you can't determine which candidate is correct,
use UNK and flag for review rather than returning every possibility.

### 8. Mandatory UNK gate

UNK is the last resort and requires a documented, reasonably exhausted search path —
not just one failed grep. Before assigning UNK, you must have attempted, as
applicable: exact phrase search, normalized/generic-term search, token search,
abbreviation search (with expansion), synonym search via catalog terminology,
concept decomposition, the other applicable catalogs, and an inactive/superseded code
check. You don't have to mechanically run every pass if earlier evidence conclusively
rules out a catalog, but you must be able to explain why the search was exhausted.
Genuinely uncodeable cases exist (reusable surgical instruments like trocars/
electrosurgical pencils, garbled/unrecoverable abbreviations, ambiguous joint/site
references with no disambiguating detail) — but reach that conclusion only after
this checklist.

**Your objective is NOT to maximize the number of mapped rows. Optimize for mapping
accuracy — prefer a defensible UNK over an unsupported mapping.**

### 9. Output

Write `results/batch_NNN_result.csv` with header
`canonical_id,service_normalized,corrected_category,code` — exactly the same number of
data rows as `batches/batch_NNN.csv`, SAME ORDER, EXACT SAME canonical_id/
service_normalized values (quote fields containing commas).

Append a row to `results/issue_batch_NNN.csv` (header `batch,canonical_id,problem`)
ONLY for rows that need a human decision: UNK, low-confidence/ambiguous mapping, or
an inactive code used with no active replacement found. Keep `problem` to a short
label (e.g. `UNK`, `low_confidence`, `inactive_no_replacement`) — don't restate the
search process, rejected candidates, or reasoning; that detail isn't needed and
wastes tokens. A plain category correction (source category was wrong, you fixed it)
is NOT an issue-log case — `corrected_category` in the result file already captures
it and it flows back into the source data automatically, no flag needed.

### 10. Final validation before reporting

Confirm: input row count == output row count; row order and every canonical_id
preserved; every mapped code follows `SOURCE:ID` format and actually exists in that
catalog; SKIP rows are genuinely drug/person/vaccine; UNK, low-confidence, and
inactive-no-replacement rows are logged in the issue file.

### 11. Report back

Rows done, mapped count, UNK count, SKIP count, category corrections made, issue
count. Flag any suspicious pattern (unusually high UNK rate, repeated conflicting
mappings for the same concept, a catalog that never seems to match). Modify no other
files.

## Issue file format
`results/issue_batch_NNN.csv` — header `batch,canonical_id,problem`, appended-to
(created if missing), one row per row that needs a human decision (UNK,
low-confidence/ambiguous mapping, or inactive-code-with-no-replacement only).
`problem` is a short label, not a paragraph — `canonical_id` is enough to look the
row back up in the result file if more detail is needed.
