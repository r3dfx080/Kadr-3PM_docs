# Кадр-3ПМ documentation library — design

Condensed from the pilot (167 scans, 3 books, Tesseract vs Opus vs Haiku comparison, numbering survey).
Language rule: **user-facing interfaces (HTML viewer, CLI messages) in Russian; docs, code, comments and
agent-facing files in English.**

## 1. Goals

1. Turn ~1000 scanned sheets (many GOST documents) into a text library an AI agent or a person can navigate,
   search and cite, with every sheet traceable to its scan.
2. Cheap first pass with Haiku; automatic risk scoring per sheet; Opus re-reads only risky sheets;
   everything else goes to a human proofreading queue. Still log all uncertain moments (that Haiku misread) into separate per-sheet list.
3. A per-sheet database of uncertainties/corrections that drives that workflow and records human review.
4. One master script that runs the pipeline and builds a static HTML viewer: scan image and text side by side.
5. Naming/numbering rules that survive new documents, rescans, inserted/withdrawn sheets and re-OCR.

## 2. Pilot findings that constrain the design

- Scan order ≠ sheet number; sheet labels have Cyrillic suffixes (21а, 32а–32г, 92а–92д, 15а); sheets get
  withdrawn (97а, 98), hand-renumbered (89… → 87), and may be missing (46). Foreign inserts exist (ТО scan 26).
- Typewriter uses `I` for 1 and `О` for 0 in numbers; Latin/Cyrillic look-alikes are mixed; «Кадр-ЗПМ» (З for 3).
- Haiku: 96.9 % word agreement with Opus on 20 sheets; read every known-hard value correctly; failed only on
  handwritten change-register tables. Opus also erred there. Handwriting/changelog sheets always need a human.
- Tesseract (rus, tessdata_best) is free and its errors are uncorrelated with LLM errors: useful as a numeric
  cross-check, useless as text. Tesseract on Windows cannot open Cyrillic paths → feed images via stdin.
- `claude -p` works with the subscription login (not `--bare`); ~22 s and ~$0.006-equivalent per Haiku sheet;
  per-call overhead ~70–90k cached tokens. Usage limits can interrupt a batch → everything must be resumable.

## 3. Decisions

**Identity.** Book = one GOST designation (`М181-600-000 ИЭ`); folder = ASCII slug (`M181-600-000_IE`).
Sheet ID = title-block label (string); page file `lNNN<translit suffix>.md`; inserts `lNNN_insertK.md`.
`manifest.csv` (one row per scan, physical order) is the source of truth for sheet↔scan; `book.json` holds
title-block facts (sheet total, withdrawn, known missing, related docs). Masters are never renamed.
Masters live in `SOURCES/` (project root); `SOURCES_JPEG/<slug>/<stem>.jpg` holds disposable grayscale
2000 px JPEGs named by sheet, used by OCR models, agents and the viewer. Suffix letters map by alphabet
position (в→c, г→d) so file names sort in document order.

**Text versions.** Each OCR engine writes to `<book>/ocr/<engine>/` (+ `_raw/` replies). `<book>/pages/` holds
the canonical text = latest accepted version + human edits. OCR never overwrites a page that is proofread or
was edited by a human (detected by content hash recorded at the last machine write).

**Review database.** SQLite `kb/review.sqlite` (stdlib), committed; `kb.py export` writes sorted CSV copies
(`kb/review/*.csv`) so git shows diffs. Tables: `pages` (status, engine, score, hash, reviewer) and
`issues` (per-sheet uncertainty/correction items with source and resolution).

**Page status flow.** `new → ocr_done → (score) → needs_rescan | needs_proof`; `needs_rescan → (Opus) →
needs_proof`; `needs_proof → proofread` (human, via CLI). Changelog sheets are always at least `needs_proof`
with an open issue.

**Risk score.** Additive, per sheet, from: model-declared uncertainties, `[неразборчиво]`, handwritten
corrections, page kind, and the share of numeric tokens the model and Tesseract disagree on.
Threshold for Opus rescan is one constant.

**Issue retention.** Issues raised by Haiku (uncertain, illegible) and Haiku-vs-Opus disagreements stay
in the sheet's issue list after an Opus rescan; only a human resolves them. Re-scoring replaces only the
issues the scorer itself created.

**Glossary (suggestions only).** `kb/glossary.csv` (columns `abbr, expansion, scope, string_seen_in_3pm,
note`) is imported from the user's Кадр-103СЦ abbreviation list (`Abbreviations.xls`). It is never used to
change text. Two uses: (1) the OCR model may Read it when an abbreviation looks strange and then report a
`SUGGEST:` line — the text keeps what is printed; (2) a deterministic check reports all-caps tokens that are
one edit away from a glossary entry. Both become `suggestion` issues on that sheet for the proofreader.
`scope` = `103СЦ` until a person confirms the meaning in 3ПМ documents; `string_seen_in_3pm` only says the
string occurs, not that the meaning matches.

**Viewer.** Static HTML generated into `kb/viewer/` (not committed): index per book with status/risk/issue
filters, one page per sheet with the preview JPEG on the left and rendered text plus open issues on the
right, prev/next by manifest order, keyboard ←/→. No server, no external JS. The viewer is read-only;
human actions go through the CLI (the viewer shows the exact command to copy).

**Future documents.** `kb.py new-book` bootstraps folder/manifest/book.json from a scan folder;
`kb.py read-sheets` lets Haiku read sheet labels from the title-block corner; `kb.py check` validates
numbering against book.json and turns anomalies into issues. Multi-volume documents stay one book (scan
column may point to several folders).

## 4. Out of scope

Transcribing drawings/wiring (Э4.1 sheets: metadata and connector list only), sections/ assembly,
full-text search index, editing text in the browser.
