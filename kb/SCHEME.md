# Numbering and storage scheme

Derived from all 167 scans (title-block sheet numbers read on every page) and ~30 transcribed sample pages
from the three books. `tools/check_manifest.py` enforces the rules below.

## What the documents actually do (why the scheme looks like this)

| Finding | Where | Consequence |
|---|---|---|
| Scan number ≠ sheet number (offset drifts 0…11) | ИЭ | never use the scan number as an ID |
| Inserted sheets with letter suffix: 21а, 32а–32г, 74а, 92а–92д, 94а, 95а, 15а | ИЭ, Э4.1 | sheet ID is a **string** `<number><cyrillic suffix>` |
| Sheets withdrawn by a change: 97а, 98 (изм. 57) | ИЭ л.110 | gaps are legal only if declared |
| Sheet 46 absent with no surviving record; count still matches «Листов 121» | ИЭ | most likely withdrawn by a lost change sheet; declared as `known_missing`, verify on paper |
| Printed sheet no. struck out and re-numbered by hand (89… → 87, 88) | ИЭ scans 092–093 | the **current** (hand-corrected) number is the ID; printed one goes in `note` |
| Title page carries no sheet number | all | it is sheet 1 by GOST convention |
| Landscape sheets, title block rotated | ИЭ 9, 13, 100–102; ТО 26; Э4.1 almost all | `orient` column; rotate previews, never the masters |
| Foreign page not belonging to the document (modern sketch) | ТО scan 26 | `kind: insert`, no sheet number, named after the preceding sheet |
| Hand-made revisions on the text (strike-through + circled change no.) | everywhere | recorded in `marks:`; text holds the **corrected** reading, old reading in an HTML comment |
| Document codes on the typewriter use `I` for `1` (МI8I) | all | IDs and text use the normalized form `М181` |
| One book references others not (yet) in the corpus (ТО1–ТО4, М181-403-050 ИЭ) | ТО л.4, ИЭ л.97 | `related` list in `book.json` |
| Cyrillic folder names broke Tesseract on Windows | — | **all paths ASCII**, Cyrillic only inside files |

## Rules

1. **Book = one GOST document**, identified by its designation (`М181-600-000 ИЭ`).
   Folder name is the ASCII form: `M181-600-000_IE`, `M181-600-000_TO`, `M181-700-000_E4.1`
   (ИЭ→IE, ТО→TO, Э→E).
2. **Page ID = the sheet label from the title block** (`32б`). Stable across rescans and the thing people cite.
   - File name: `l` + 3-digit number + suffix mapped **by alphabet position** (а→a б→b в→c г→d д→e е→f
     ж→g з→h): `l032b.md` = л.32б, `l032d.md` = л.32г. Phonetic transliteration (в→v, г→g) is NOT used
     because it breaks sort order. Zero-padding + positional suffixes make plain alphabetical order =
     document order (l032 < l032a < l032b < l032c < l032d < l033).
   - Foreign inserts: `l025_insert1.md` (sorts right after the sheet it follows).
3. **`manifest.csv` is the single source of truth** for each book, one row per scan, in physical order:
   `sheet, scan, orient, kind, note`. Scan files are never renamed or moved; the manifest points at them.
   `kind` ∈ title, toc, text, table, figure, diagram, changelog, insert (blank = not classified yet).
4. **`book.json`** holds what the title block and change sheets say: `sheets_total`, `withdrawn`,
   `known_missing`, `related`. The checker fails on any gap that is not declared there.
5. **Page file = front-matter + verbatim text.** Front-matter fields:
   `doc, sheet, scan, kind, section, rev, marks, uncertain, ocr`. `rev` = the change number in that sheet's title block.
   `uncertain` = readings the OCR models were unsure of (`haiku: …` / `opus: …`; `штамп:` = title block,
   `подпись:` = signatures); a proofreader checks them against the scan and removes the line.
   The text keeps the document's own structure (headings 6.11, 6.11.1…; tables as Markdown tables) and
   page-continuation comments (`<!-- продолжение на листе 41 -->`).
6. **Normalization** (applied to page text, done by script after OCR, not by the model):
   `I`→`1` in numbers/designators; designators in Cyrillic (А104, Х3, К203); sheet suffixes lower-case Cyrillic.
7. **Figures and diagrams: caption + labels only.** The drawing itself is never re-drawn or transcribed.
   For Э4.1 wiring sheets the page file lists only connectors on the sheet, notes and title-block data.
8. **Citation format:** `<doc> л.<sheet> п.<item>` — e.g. `М181-600-000 ИЭ л.40 п.6.11.3`.
   The page file's `scan:` gives the original image for verification.

## Glossary (suggestions only)

`glossary.csv` — 103 abbreviations converted from the user's `Abbreviations.xls` (Кадр-103СЦ).
Columns: `abbr, expansion, scope, string_seen_in_3pm, note`.

- `expansion` is the source wording; remarks that are not expansions («понятно», «?», «(?)», «TBC»)
  were moved to `note` and the expansion left empty or kept with the remark.
- `scope` is `103СЦ` for every row until a person confirms the meaning in a 3ПМ document; then add `3ПМ`.
- `string_seen_in_3pm` lists sheets where the string occurs in transcribed 3ПМ text (regenerate after
  OCR runs). It says nothing about whether the meaning matches.
- The CSV is now the source of truth; `Abbreviations.xls` is kept as the original.
- **It never changes page text.** OCR models may consult it for odd-looking abbreviations and report a
  `SUGGEST:` line; a deterministic check flags all-caps tokens one edit away from an entry. Both end up as
  `suggestion` items in the proofreading database for that sheet.

## Layout

```
SOURCES/                      master scans, LZW TIFF, never modified (folder names as scanned)
├── Operating Instructions/001.tif …
SOURCES_JPEG/                 generated by kb/tools/make_jpegs.py — for LLMs and the viewer
├── M181-600-000_IE/l001.jpg … grayscale, long side 2000 px, q85, named by sheet (l032d.jpg = л.32г)
kb/
├── AGENTS.md                 entry point for models and people
├── SCHEME.md                 this file
├── glossary.csv              Кадр-103СЦ abbreviations — suggestions only
├── tools/check_manifest.py   run after every batch; exit 1 on any inconsistency
├── tools/make_jpegs.py       SOURCES → SOURCES_JPEG; skips up-to-date files, removes stale ones
├── tools/ingest.py           hybrid OCR in batches: Haiku → risk score → Opus re-read → pages/
├── INGEST_STATUS.md          generated per-sheet ingest state; where the next agent continues
├── tools/viewer.py           static HTML viewer → kb/viewer/ (git-ignored), tests in tools/tests/
├── M181-600-000_IE/
│   ├── book.json
│   ├── manifest.csv          121 rows
│   ├── ocr/haiku/, ocr/opus/ engine output + _raw/ replies + _runlog.jsonl
│   ├── pages/l001.md …       one file per sheet (promoted from ocr/)
│   └── sections/             (next step) generated from pages/, one file per section
├── M181-600-000_TO/          26 rows (25 sheets + 1 insert)
└── M181-700-000_E4.1/        20 rows (19 sheets + 15а), metadata-only pages
```

`scan:` paths in manifests and page front-matter are relative to the project root (`SOURCES/…`).
`SOURCES_JPEG/` is disposable: delete it and rerun `python -I -X utf8 kb/tools/make_jpegs.py` (~10 s for
167 sheets). Re-run it after any manifest change; files whose sheet label changed are regenerated and the
old names removed.

## Still open

- **ИЭ л.46**: check the paper copy (missing scan, or withdrawn by a change recorded on a lost sheet?).
- **ИЭ change log for changes 1–55** is not in the scans (only л.110 with изм. 56–58 exists).
- Revision numbers in title blocks (`rev`) are partly illegible; the change-sheet tables need a proofread.
- `kind` is filled only for pages actually viewed; the rest gets classified during the full OCR run.
