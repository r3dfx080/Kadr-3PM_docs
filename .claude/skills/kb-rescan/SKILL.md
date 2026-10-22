---
name: kb-rescan
description: Report-only audit of the Кадр-3ПМ knowledge base pages (kb/*/pages/*.md) against kb/SCHEME.md. Use when asked to re-scan, audit, validate or check pages against the spec. Never edits, fixes or commits anything.
---

# kb-rescan — audit pages against the spec

**Report only.** Do not edit, rename, normalize, fix or commit anything, even if the fix looks obvious.
Fixes happen only after the user picks items from the report.

## Procedure (same every run)

1. Read `kb/AGENTS.md` and `kb/SCHEME.md` in full, now. SCHEME.md is the only source of rules; if this
   checklist and SCHEME.md disagree, follow SCHEME.md and report the disagreement as a `skill` problem.
2. Run `python -I -X utf8 kb/tools/check_manifest.py kb` and put its output verbatim in the report.
3. For each book folder in `kb/` (alphabetical), for each file in `pages/` (alphabetical = document order),
   apply **every** check below. Do not sample, do not stop early, do not skip a check because earlier pages passed.
4. Write the report (format below). Then stop and wait.

## Checklist (one ID per check — use the ID in the report)

| ID | Rule (SCHEME.md) | Check |
|---|---|---|
| R1 | Rule 2 | File stem = `l` + 3-digit number + positional suffix (а→a б→b в→c г→d д→e е→f ж→g з→h) of `sheet:`; foreign inserts `lNNN_insertN`. |
| R2 | Rule 3 | Page has a matching `manifest.csv` row; `sheet:`, `scan:`, `kind:` agree with that row (blank manifest `kind` is not an error). |
| R3 | Rule 5 | Front-matter has exactly the fields `doc, sheet, scan, kind, section, rev, marks, ocr`; `doc:` equals the book's designation. |
| R4 | Rule 3 | `kind` ∈ title, toc, text, table, figure, diagram, changelog, insert. |
| R5 | Rule 5 | Text keeps the document's structure (numbered headings, Markdown tables) and continuation comments where the sheet continues. |
| R6 | Rule 6 | No Latin `I` for `1` in numbers/designators/codes (`МI8I`); designators use Cyrillic letters (А104, Х3, К203 — watch Latin look-alikes A, X, K, C, E, H, M, O, P, T); sheet suffixes lower-case Cyrillic. |
| R7 | Rule 7 | Figures/diagrams: caption + labels only, nothing re-drawn. Э4.1 wiring sheets: only connectors on the sheet, notes, title-block data — no wiring. |
| R8 | Findings table | Each handwritten correction: corrected reading in the text, original in an HTML comment, and an entry in `marks:`. |
| R9 | Glossary | No page text changed because of `glossary.csv` (expansions inserted from it = problem). |
| R10 | Scan check | Only when a wording/number/figure looks doubtful: compare with `SOURCES_JPEG/<book>/<stem>.jpg` (never the TIFF). If you did not open the image, say `check scan` — never guess. |

Mechanical checks (R1–R4, R6) must cite the exact offending text. Judgment checks (R5, R7, R8, R10)
must say what you saw and mark `confidence: low` when unsure.

## Report format (always this shape)

```
## kb-rescan report — <date>
Spec: kb/SCHEME.md (read this run)
check_manifest.py: <exit code>
<verbatim output>

### Problems
| book | page | check | problem | evidence (line / quote) | confidence |
|---|---|---|---|---|---|

### Pages with no problems
<book>: l001, l002, …

### Not checked
<anything skipped and why — must be empty or explained>
```

Every page appears in exactly one of "Problems" or "Pages with no problems", so a missing page is visible.
