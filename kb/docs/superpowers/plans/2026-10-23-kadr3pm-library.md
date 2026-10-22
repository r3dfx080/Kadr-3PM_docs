# Кадр-3ПМ Documentation Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A resumable OCR pipeline (Haiku → risk score → Opus rescan of risky sheets → human proofreading) with a per-sheet review database and a static side-by-side HTML viewer, under one master CLI.

**Architecture:** A small stdlib-only Python package `kb/tools/kblib/` (paths, manifest, normalize, page files, SQLite review DB, OCR via `claude -p`, Tesseract, scoring, viewer) driven by `kb/tools/kb.py` subcommands. Text lives in Markdown page files; workflow state lives in `kb/review.sqlite`; scans are never touched.

**Tech Stack:** Python 3.13 stdlib (`sqlite3`, `argparse`, `unittest`, `html`, `concurrent.futures`), Pillow 12 (installed), Claude Code CLI 2.1 (`claude -p`, subscription login), Tesseract 5.4 + `tessdata_best` rus, git.

**Spec:** `kb/docs/superpowers/specs/2026-10-23-kadr3pm-library-design.md`

## Global Constraints

- No new dependencies: stdlib + Pillow only. Tests use `unittest` (pytest is not installed).
- Run Python as `python -I -X utf8` (isolated mode; UTF-8 console on Windows).
- All paths inside `kb/` ASCII. Cyrillic only inside files. Masters live in `SOURCES/<scan folder>/` (project root, outside `kb/`) and are read-only inputs; manifest `scan` paths are relative to the project root (`SOURCES/Operating Instructions/045.tif`).
- Sheet images for LLMs and the viewer: `SOURCES_JPEG/<slug>/<stem>.jpg` (project root, outside `kb/`, disposable), grayscale, long side 2000, quality 85. Generator already exists as `kb/tools/make_jpegs.py`; Task 3 moves its logic into the package.
- Page-name suffix mapping is positional (`а→a б→b в→c г→d д→e е→f ж→g з→h`), never phonetic — file names must sort in document order.
- User-facing strings (viewer HTML, CLI output) in Russian; code, comments, docs, AGENTS.md in English.
- `claude -p` must NOT use `--bare` (it disables subscription OAuth). Use `--strict-mcp-config --no-session-persistence --output-format json --allowedTools Read`.
- Tesseract: `C:/Program Files/Tesseract-OCR/tesseract.exe`, `--tessdata-dir` = `kb/tools/tessdata` (copy `rus`, `eng`, `osd` traineddata there from the scratchpad download or re-download from `tesseract-ocr/tessdata_best`), image via stdin.
- Never overwrite: masters; a page whose DB status is `proofread`; a page whose file hash ≠ hash recorded at last machine write.
- Git repo root = the project folder `D:\KADR3PM_DOCS` (already initialized; root `.gitignore` excludes `SOURCES/`, `SOURCES_JPEG/`, `**/_img/`, `__pycache__/`). Commits use the user's identity; **no Claude/AI signature or Co-Authored-By trailer** (see `kb/AGENTS.md`).
- Test command (used in every task): `cd /d/KADR3PM_DOCS && python -I -X utf8 -m unittest discover -s kb/tools/tests -t kb/tools -v`

## Review Focus

1. Re-running OCR on a book after a human corrected some pages must leave those pages untouched — test in Task 4 (`test_ocr_skips_human_edited_page`).
2. Hitting the usage limit mid-batch (`claude -p` exits non-zero / `is_error: true` / non-JSON stdout) must leave the sheet `new`, record one `ocr_failed` issue, and let the next run resume — test in Task 4 (`test_ocr_failure_keeps_status_new`).
3. Scan paths with spaces/Cyrillic (user renames folders) must work for previews and Tesseract; a missing scan must be a `check` error, not a crash — tests in Task 3 (`test_preview_cyrillic_path`) and Task 1 (`test_check_missing_scan`).
4. Navigation order with suffix sheets and inserts (l021 → l021a → l022; l025 → l025_insert1) must follow manifest order — test in Task 7 (`test_viewer_prev_next_follows_manifest`).
5. Page text containing `<`, `&`, `≥`, or model-emitted `<br>` must render safely (escaped; only `<br>` passes as a line break) — test in Task 7 (`test_md_escapes_html_keeps_br`).

---

## File Structure

```
kb/                                  git repo root
├── .gitignore                       viewer/, **/_img/, __pycache__/, tools/tessdata/
├── AGENTS.md  SCHEME.md             agent docs (English) — updated in Task 10
├── glossary.csv                     Кадр-103СЦ abbreviations, suggestions only (already created)
├── review.sqlite                    review DB (committed)
├── review/pages.csv  review/issues.csv   sorted exports for diffs (Task 8)
├── viewer/                          static HTML (generated)
├── <book>/book.json  manifest.csv
├── <book>/pages/<stem>.md           canonical text
├── <book>/ocr/<engine>/<stem>.md    per-engine output; ocr/<engine>/_raw/<stem>.txt raw replies
└── tools/
    ├── kb.py                        master CLI (Task 8)
    ├── ocr_prompt.md                prompt (moved from current, extended in Task 4)
    ├── kblib/__init__.py
    ├── kblib/paths.py               ROOT, KB, book_dir, page_name, book_slug        (Task 1)
    ├── kblib/manifest.py            load_book, check_book                           (Task 1)
    ├── kblib/normalize.py           normalize                                       (Task 1)
    ├── kblib/pagefile.py            PageFile read/write, text_hash                  (Task 2)
    ├── kblib/db.py                  ReviewDB                                        (Task 2)
    ├── kblib/previews.py            make_preview, ensure_previews                   (Task 3)
    ├── kblib/ocr.py                 build_prompt, parse_reply, ocr_sheet, ocr_book  (Task 4)
    ├── kblib/tess.py                tesseract_sheet                                 (Task 5)
    ├── kblib/score.py               signals, score_sheet, numeric_disagreements     (Task 5–6)
    ├── kblib/mdmini.py              md_to_html                                      (Task 7)
    ├── kblib/viewer.py              build_viewer, UI strings (Russian)              (Task 7)
    ├── kblib/onboard.py             new_book, read_sheets                           (Task 9)
    └── tests/test_*.py              one file per module, fixtures in tests/fixtures/
```

Replaced and deleted at the end of Task 8: `tools/check_manifest.py`, `tools/ocr_batch.py`, `tools/compare_pages.py`, `tools/make_jpegs.py` (→ `kb.py previews`).

---

### Task 0: Repository and test harness

**Files:**
- Modify: `.gitignore` (project root, exists); Create: `kb/tools/kblib/__init__.py`, `kb/tools/tests/__init__.py`, `kb/tools/tests/test_smoke.py`

- [ ] **Step 1:** Append to the root `.gitignore`: `kb/viewer/`, `kb/tools/tessdata/`, `*.failed.txt` (the repo already exists with a baseline commit).
- [ ] **Step 2:** `test_smoke.py`: `test_kblib_importable` → `import kblib` succeeds.
- [ ] **Step 3:** Run the test command. Expected: 1 test OK.
- [ ] **Step 4:** Commit `chore: test harness`.

---

### Task 1: paths, manifest, normalize (move existing logic into the package)

**Files:**
- Create: `kblib/paths.py`, `kblib/manifest.py`, `kblib/normalize.py`
- Test: `tests/test_paths.py`, `tests/test_manifest.py`, `tests/test_normalize.py`, fixtures `tests/fixtures/book_ok/` (book.json + manifest.csv + 3 tiny PNG "scans")

**Interfaces:**
- Produces:
  - `paths.ROOT: Path` (parent of `kb/`), `paths.KB: Path`, `paths.book_dir(slug) -> Path`
  - `paths.page_name(label: str) -> str` (existing behaviour: `"32б"→"l032b"`, `"5"→"l005"`, `"15а"→"l015a"`); `paths.insert_name(after: str, k: int) -> str` (`("25",1)→"l025_insert1"`)
  - `paths.book_slug(code: str) -> str`
  - `manifest.Row` (dataclass: `sheet, scan, orient, kind, note, stem`) — `stem` = `page_name(sheet)` or `insert_name(previous sheet, k)` for rows with empty sheet
  - `manifest.load_book(book_dir) -> tuple[dict, list[Row]]`
  - `manifest.check_book(book_dir, root=paths.ROOT) -> tuple[list[str], list[str]]` (errors, warnings) — the current `check_manifest.check` logic plus `known_missing`/`withdrawn` handling, unchanged rules
  - `normalize.normalize(text: str) -> str` — current function from `ocr_batch.py`, unchanged

- [ ] **Step 1: Write failing tests**
  - `test_page_name`: the three cases above, plus `"32г"→"l032d"`; `test_insert_name`.
  - `test_page_names_sort_in_document_order`: `[page_name(s) for s in ["32","32а","32б","32в","32г","33"]]` equals its own `sorted()`.
  - `test_book_slug`: `"М181-600-000 ИЭ"→"M181-600-000_IE"`, `"М181-600-000 ТО"→"M181-600-000_TO"`, `"М181-700-000 Э4.1"→"M181-700-000_E4.1"`, `"М181-600-000 ТО1"→"M181-600-000_TO1"`, `"М181-403-050 ИЭ"→"M181-403-050_IE"`.
  - `test_normalize_cases`: every pair from the `__main__` self-check list of current `ocr_batch.py` (copy verbatim).
  - `test_check_ok`: fixture book → `([], [])`.
  - `test_check_undeclared_gap`: fixture manifest without sheet 2 → error containing `"sheet 2 absent — UNDECLARED"`.
  - `test_check_missing_scan`: manifest row pointing at a nonexistent file → error `"scan missing: …"`, no exception.
  - `test_stem_for_insert_row`: row with empty sheet after sheet `"3"` → `stem == "l003_insert1"`.
- [ ] **Step 2:** Run tests. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement. `book_slug`: transliterate with `str.maketrans` over Cyrillic capitals (`А→A Б→B В→V Г→G Д→D Е→E Ж→ZH З→Z И→I К→K Л→L М→M Н→N О→O П→P Р→R С→S Т→T У→U Ф→F Х→KH Ц→TS Ч→CH Ш→SH Э→E Ю→YU Я→YA`), replace `" "` with `"_"`; keep digits, `-`, `.`. Note `ИЭ→IE` follows from the table.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat: kblib paths/manifest/normalize`.

---

### Task 2: page files and review database

**Files:**
- Create: `kblib/pagefile.py`, `kblib/db.py`
- Test: `tests/test_pagefile.py`, `tests/test_db.py`

**Interfaces:**
- Produces:
  - `pagefile.Page` dataclass: `doc, sheet, scan, kind, section, rev, marks: list[str], uncertain: list[str], ocr, body`
  - `pagefile.read_page(path) -> Page`; `pagefile.write_page(path, page) -> str` (returns `text_hash`); `pagefile.text_hash(path) -> str` (sha256 of file bytes, hex)
  - Front-matter order exactly: `doc, sheet, scan, kind, section, rev, marks, uncertain, ocr`; strings double-quoted with `\"` escaping; empty lists as `[]`. `read_page` must also read the existing 30 pages (which lack `uncertain`).
  - `db.STATUSES = ("new", "ocr_done", "needs_rescan", "needs_proof", "proofread")`
  - `db.ISSUE_KINDS = ("illegible", "uncertain", "handwritten", "tess_mismatch", "model_disagreement", "numbering", "ocr_failed", "suggestion", "human_note")`
  - `db.ReviewDB(path)` with methods:
    - `ensure_pages(book: str, stems: list[str])` — insert missing rows with status `new`
    - `get_page(book, stem) -> dict | None`; `pages(book=None, status=None) -> list[dict]`
    - `set_page(book, stem, **fields)` — fields among `status, engine, score, text_hash, reviewer, reviewed_at`; validates status
    - `add_issue(book, stem, kind, source, detail) -> int` — skips exact duplicates (same book, stem, kind, source, detail, status open); returns id
    - `issues(book=None, stem=None, status="open") -> list[dict]`
    - `resolve(issue_id, note="", status="resolved")`
    - `clear_open(book, stem, source)` — deletes open issues from one source (used before re-scoring)
  - Schema: `pages(book TEXT, stem TEXT, status TEXT, engine TEXT, score INTEGER, text_hash TEXT, reviewer TEXT, reviewed_at TEXT, updated_at TEXT, PRIMARY KEY(book, stem))`; `issues(id INTEGER PRIMARY KEY, book, stem, kind, source, detail, status DEFAULT 'open', note, created_at, resolved_at)`; `PRAGMA user_version = 1`.

- [ ] **Step 1: Write failing tests**
  - `test_roundtrip`: write Page with marks containing `"` and `«»` → read back equal; hash equals `text_hash(path)`.
  - `test_read_existing_page`: copy `kb/M181-600-000_IE/pages/l040.md` into fixtures; `read_page` → `sheet == "40"`, `uncertain == []`, body starts with `"## 6.11."`.
  - `test_db_status_validation`: `set_page(..., status="bogus")` raises `ValueError`.
  - `test_issue_dedup`: two identical `add_issue` calls → one open issue.
  - `test_clear_open_only_source`: issues from `"score"` and `"human"`; `clear_open(..., "score")` leaves the human one.
  - `test_resolve`: resolved issue disappears from `issues()` default, appears with `status="resolved"`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement (DB uses `sqlite3`, one connection per instance, `row_factory = sqlite3.Row`, timestamps `datetime.now().isoformat(timespec="seconds")`).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat: page file io and review database`.

---

### Task 3: previews (move `make_jpegs.py` into the package)

**Files:**
- Create: `kblib/previews.py` (logic of the existing `tools/make_jpegs.py`: `convert`, atomic `.part` write, stale-file removal)
- Test: `tests/test_previews.py`

**Interfaces:**
- Consumes: `manifest.load_book` (rows carry `stem`), `paths.ROOT`
- Produces: `paths.JPEG = ROOT / "SOURCES_JPEG"`; `previews.make_preview(src: Path, dst: Path, long_side=2000, quality=85) -> Path`; `previews.preview_path(slug, stem) -> Path` (`JPEG/<slug>/<stem>.jpg`); `previews.ensure_previews(slug, force=False) -> dict` with counts `{"ok", "skip", "stale_removed"}`

- [ ] **Step 1: Write failing tests**
  - `test_preview_size_and_mode`: 3000×4000 RGB source → JPEG, mode `L`, `max(size) == 2000`.
  - `test_preview_cyrillic_path`: source in `tmp/Папка со сканами/01.tif` works.
  - `test_ensure_skips_existing`: second call does not rewrite (mtime unchanged), counts `skip == n`.
  - `test_ensure_removes_stale`: an extra `l999.jpg` in the book's JPEG folder is removed; `stale_removed == 1`.
  - `test_insert_preview_named_after_sheet`: manifest rows `25`, `""` → `l025.jpg`, `l025_insert1.jpg`.
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** Commit `feat: preview generation`.

---

### Task 4: OCR via `claude -p` (resumable, protected writes, uncertainties)

**Files:**
- Create: `kblib/ocr.py`; Modify: move `tools/ocr_prompt.md` content, add UNCERTAIN section
- Test: `tests/test_ocr.py` (fake runner, no real model calls)

**Interfaces:**
- Consumes: `load_book`, `normalize`, `Page/write_page/read_page/text_hash`, `ReviewDB`, `ensure_previews`
- Produces:
  - `ocr.build_prompt(meta, row, prev_label, next_label, image_path) -> str`
  - `ocr.parse_reply(text) -> tuple[str, str, list[str], list[str], list[str], str]` = `(section, rev, marks, uncertain, suggest, body)`; `UNCERTAIN:` and `SUGGEST:` blocks optional (old raw replies have none)
  - `ocr.Runner = Callable[[list[str], Path], subprocess.CompletedProcess]`; `ocr.default_runner` wraps `subprocess.run(..., capture_output=True, text=True, encoding="utf-8", timeout=600)`
  - `ocr.ocr_sheet(slug, row, meta, prev, nxt, engine: str, model: str, db, runner=default_runner) -> str` returning one of `"ok" | "skipped" | "protected" | "failed"`
  - `ocr.ocr_book(slug, engine, model, stems: list[str] | None, jobs=4, db=None, runner=default_runner) -> dict[str, str]`
- Behaviour:
  - Writes `kb/<slug>/ocr/<engine>/<stem>.md` and `_raw/<stem>.txt` (first line `model: <id>`), appends `ocr/<engine>/_runlog.jsonl`.
  - `ocr.ENGINE_RANK = {"tesseract": 0, "haiku": 1, "opus": 2, "opus-chat": 2}`.
  - Promotes to `pages/<stem>.md` unless the page is protected: DB status `proofread`; or file exists and `text_hash(file) != db.text_hash` (human edit); or `ENGINE_RANK[engine] < ENGINE_RANK[current db engine]`. Protected → return `"protected"`, still keep the engine output.
  - Calls `db.ensure_pages(slug, [row.stem])` first, so a sheet missing from the DB is created as `new`.
  - On success: `set_page(status="ocr_done", engine=engine, text_hash=…)`; one `uncertain` issue per UNCERTAIN line, one `illegible` issue per `[неразборчиво]`, one `suggestion` issue per SUGGEST line, source = engine. SUGGEST lines never alter the body.
  - The glossary is copied to `ocr/<engine>/_img/glossary.csv` so the model's Read tool (cwd there) can open it.
  - On failure (non-zero exit, non-JSON, `is_error`, unparseable): write `<stem>.md.failed.txt`, `add_issue(kind="ocr_failed", source=engine)`, status unchanged; return `"failed"`.
  - `"skipped"` when `ocr/<engine>/<stem>.md` exists (resume).
  - Engines: `haiku` → model `haiku`; `opus` → model `opus`.
- Prompt additions (blocks inserted between MARKS and TEXT in `ocr_prompt.md`, plus rules):
  - `UNCERTAIN:` then `- <exact reading> — <why unsure>` lines for every value, word or table cell you are not sure of; omit if none.
  - `SUGGEST:` then `- <abbreviation as printed> → <glossary entry> — <reason>` lines. Rule text: "If an abbreviation looks strange or unknown, you may Read `glossary.csv` (abbreviations from the related Кадр-103СЦ; meanings may differ in this machine). Never change TEXT because of it — transcribe what is printed and report the possible match in SUGGEST."

- [ ] **Step 1: Write failing tests** (fake runner returns canned JSON `{"result": "...", "modelUsage": {"claude-haiku-5-5": {}}, "total_cost_usd": 0.006, "usage": {...}}`)
  - `test_parse_reply_with_and_without_uncertain` (also: reply with a `SUGGEST:` block → `suggest` list parsed, body identical to the same reply without the block)
  - `test_ocr_suggestion_issue_does_not_change_text` → reply `SUGGEST: - ИЩЛВ → ИЦЛВ — …` with body containing `ИЩЛВ` → page body still `ИЩЛВ`, one open `suggestion` issue
  - `test_ocr_writes_engine_and_page` → both files exist, DB status `ocr_done`, body normalized (`"6.II.I."` in reply → `"6.11.1."` in page).
  - `test_ocr_creates_uncertainty_issues` → reply with 2 UNCERTAIN lines and one `[неразборчиво]` → 2 `uncertain` + 1 `illegible` open issues.
  - `test_ocr_skips_human_edited_page` → after first run, append a line to `pages/<stem>.md`, delete engine output, rerun → returns `"protected"`, page file unchanged.
  - `test_ocr_skips_proofread` → status `proofread` → `"protected"`.
  - `test_haiku_does_not_replace_opus_page` → page registered with engine `opus-chat` and matching hash → Haiku run returns `"protected"`; engine output still written to `ocr/haiku/`.
  - `test_ocr_failure_keeps_status_new` → runner returns `returncode=1, stdout="Usage limit reached"` → `"failed"`, status `new`, one `ocr_failed` issue, `.failed.txt` exists; second call with good runner → `"ok"`.
  - `test_ocr_resume_skips_existing`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement (reuse arg list from current `ocr_batch.py`; image path = preview from Task 3, copied to `ocr/<engine>/_img/` because `claude -p` runs with `cwd` there).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Live smoke test (spends usage, ~1 sheet): `python -I -X utf8 -c "from kblib.ocr import ocr_book; print(ocr_book('M181-600-000_IE','haiku','haiku',['l040'],jobs=1))"` from `kb/tools` with a temp copy of the DB → `{'l040': 'ok'}` or `'protected'`.
- [ ] **Step 6:** Commit `feat: resumable claude -p OCR with protected writes and uncertainty issues`.

---

### Task 5: Tesseract cross-check and risk score

**Files:**
- Create: `kblib/tess.py`, `kblib/score.py`
- Test: `tests/test_score.py` (Tesseract itself mocked; one optional live test skipped when the exe is absent)

**Interfaces:**
- Consumes: previews, `read_page`, `ReviewDB`, `normalize`
- Produces:
  - `tess.tesseract_sheet(slug, stem) -> str` — writes and returns `kb/<slug>/ocr/tesseract/<stem>.txt`, image via stdin, `-l rus`; skips if exists
  - `score.numeric_tokens(text) -> list[str]` — tokens containing a digit, after `normalize` and look-alike folding
  - `score.signals(page: Page, tess_text: str | None) -> dict` with keys `illegible, uncertain, handwritten, kind_weight, tess_ratio`
  - `score.score_sheet(sig: dict) -> int` = `3*illegible + 2*uncertain + handwritten + kind_weight + round(10*tess_ratio)`
  - `score.RESCAN_THRESHOLD = 6`; `score.KIND_WEIGHT = {"changelog": 5, "table": 2, "insert": 3}` (others 0)
  - `score.load_glossary(path=KB/"glossary.csv") -> dict[str, dict]` (keyed by `abbr`)
  - `score.glossary_suggestions(body: str, glossary) -> list[str]` — for each distinct Cyrillic token of 2–6 letters that starts with a capital and has ≥ 2 capitals (covers `ВСС` and mixed-case `ДвПрм`, `ВСОп`), is not a glossary key but is exactly one edit (substitute/insert/delete) from one: `"«<token>» — возможно «<abbr>» (<expansion>), глоссарий 103СЦ"`; contributes 0 to the score
  - `score.score_book(slug, db) -> dict[str, int]` — for each `ocr_done` sheet: add `glossary_suggestions` as `suggestion` issues (source `glossary`); clear open `score` issues, add `handwritten` / `tess_mismatch` issues (source `score`), set `score`, set status `needs_rescan` if score ≥ threshold and `ENGINE_RANK[engine] < 2`, else `needs_proof`; `changelog` sheets always get an open `handwritten` issue
- Definitions: `handwritten` = count of `<!-- изм` comments + marks containing `рукоп` or `от руки`; `tess_ratio` = share of the page's numeric tokens absent from the Tesseract numeric tokens (0 when there's no Tesseract text or no numeric tokens).

- [ ] **Step 1: Write failing tests**
  - `test_numeric_tokens_folds_typewriter` (`"МI02 +I70 В"` → `["М102", "+170"]`)
  - `test_tess_ratio` (page tokens `80, 64, 0,5`; tess `60, 64, 0,5` → ratio `1/3`)
  - `test_score_formula` (illegible 1, uncertain 1, handwritten 1, changelog, ratio 0.2 → `3+2+1+5+2 = 13`)
  - `test_score_book_status_split` (two pages: clean → `needs_proof`; one with 2 illegible → `needs_rescan`)
  - `test_opus_page_never_needs_rescan` (engines `opus` and `opus-chat`, score 20 → `needs_proof`)
  - `test_rescore_replaces_score_issues` (score twice → no duplicated `score`/`glossary` issues; human issues survive)
  - `test_glossary_near_miss` (glossary `{"ВСС", "ДУ"}`; body `"сигнал ВСЗ и ВСС, ДУ"` → one suggestion mentioning `«ВСЗ»` and `«ВСС»`; exact matches and `"ДУ"` produce none)
  - `test_glossary_never_affects_score` (same page with/without glossary → equal `score_sheet`)
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** Commit `feat: tesseract cross-check and risk scoring`.

---

### Task 6: Opus rescan and model disagreement

**Files:**
- Modify: `kblib/score.py` (add `numeric_disagreements`, `rescan_book`)
- Test: `tests/test_rescan.py`

**Interfaces:**
- Consumes: `ocr_book`, `score_book`, `numeric_tokens`
- Produces:
  - `score.numeric_disagreements(a: str, b: str) -> list[str]` — `difflib.SequenceMatcher` over word tokens (logic of current `compare_pages.py`), returning `"<a tokens> -> <b tokens>"` for non-equal opcodes touching a numeric token
  - `score.rescan_book(slug, db, runner=default_runner) -> dict[str, str]` — runs `ocr_book(engine="opus", stems=<needs_rescan stems>)`; for each ok sheet adds one `model_disagreement` issue (source `rescan`) per item of `numeric_disagreements(haiku_body, opus_body)`, bodies read from `ocr/haiku/<stem>.md` and `ocr/opus/<stem>.md`; then `score_book`

- [ ] **Step 1: Write failing tests**
  - `test_numeric_disagreements` (`"период 80 мкс"` vs `"период 60 мкс"` → `["80 -> 60"]`; identical texts → `[]`)
  - `test_rescan_only_flagged` (fake runner records calls; only `needs_rescan` stems are OCR'd)
  - `test_rescan_creates_disagreement_issues_and_needs_proof`
  - `test_rescan_keeps_haiku_issues` (Haiku `uncertain` issue open before rescan → still open after rescan and re-score)
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** Commit `feat: opus rescan of risky sheets with disagreement issues`.

---

### Task 7: HTML viewer

**Files:**
- Create: `kblib/mdmini.py`, `kblib/viewer.py`
- Test: `tests/test_mdmini.py`, `tests/test_viewer.py`

**Interfaces:**
- Consumes: `load_book`, `read_page`, `ReviewDB`, previews
- Produces:
  - `mdmini.md_to_html(md: str) -> str` — supports exactly: `## `/`### ` headings, blank-line paragraphs (single newlines → `<br>`), pipe tables with a `|---|` separator, `**bold**`, `<!-- … -->` → `<span class="note">…</span>`, `[неразборчиво]` → `<mark>[неразборчиво]</mark>`, literal `<br>` inside table cells kept; everything else HTML-escaped
  - `viewer.UI` dict of Russian strings (exact values): `title="Документация «Кадр-3ПМ»"`, `sheet="Лист"`, `kind="Тип"`, `status="Статус"`, `risk="Риск"`, `issues="Замечания"`, `engine="Распознано"`, `scan="Скан"`, `prev="← пред."`, `next="след. →"`, `back="К списку"`, `no_text="Текст ещё не распознан"`, `cmd_proof="Отметить как вычитанный:"`, `cmd_resolve="Закрыть замечание:"`, `all="Все"`; status labels `new="не распознан"`, `ocr_done="распознан"`, `needs_rescan="на перераспознавание"`, `needs_proof="на вычитку"`, `proofread="вычитан"`
  - `viewer.build_viewer(out=KB/"viewer") -> Path` — writes `index.html` (one table per book: sheet, kind, status, risk, open-issue count; a `<select>` status filter via inline JS) and `<slug>/<stem>.html` per manifest row; returns index path
- Sheet page layout: two columns (CSS grid, 50/50, stacks below 900 px): left `<img src="../../../SOURCES_JPEG/<slug>/<stem>.jpg">` (relative path from `kb/viewer/<slug>/`), click toggles fit-width ↔ natural size; right: header (doc, «Лист N», scan path, status, risk), rendered text, open issues list each with its `python kb/tools/kb.py resolve <id>` command, and the `kb.py proof <slug> <sheet>` command. Prev/next by manifest order; `←`/`→` keys navigate. No external resources. `<html lang="ru">`, UTF-8.

- [ ] **Step 1: Write failing tests**
  - `test_md_headings_paragraphs`, `test_md_table`, `test_md_note_and_illegible`
  - `test_md_escapes_html_keeps_br` (`"a < b & c ≥ d"` escaped; `"| x<br>y |"` cell keeps `<br>`; `"<script>"` escaped)
  - `test_viewer_prev_next_follows_manifest` (fixture rows `21, 21а, 22` and an insert → `l021a.html` links prev `l021.html`, next `l022.html`; insert linked after its sheet)
  - `test_viewer_page_without_text` (no page file → contains `UI["no_text"]`, still has image)
  - `test_viewer_index_counts_open_issues`
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** Build on real data: `python -I -X utf8 -c "from kblib.viewer import build_viewer; print(build_viewer())"` from `kb/tools` (after `ensure_previews` for the IE book) and open `kb/viewer/M181-600-000_IE/l040.html` in the browser pane: scan left, text right, «+10 В» visible.
- [ ] **Step 6:** Commit `feat: static side-by-side viewer (Russian UI)`.

---

### Task 8: Master CLI `kb.py`

**Files:**
- Create: `kb/tools/kb.py`; Delete: `tools/check_manifest.py`, `tools/ocr_batch.py`, `tools/compare_pages.py`, `tools/make_jpegs.py`
- Test: `tests/test_cli.py` (calls `kb.main(argv)` with a temp KB and fake runner)

**Interfaces:**
- Consumes: everything above
- Produces: `kb.main(argv: list[str] | None = None) -> int` with subcommands (Russian help/output):
  - `check` — `check_book` for every book; `db.ensure_pages` for every manifest stem; numbering errors also become `numbering` issues (source `check`); exit 1 on errors
  - `previews [--book B]`
  - `ocr --book B [--engine haiku|opus] [--sheets l040,l032b] [--jobs 4]` — default: all sheets with status `new`
  - `tess --book B`, `score --book B`, `rescan --book B`
  - `run --book B [--no-rescan]` — `check → previews → ocr(haiku, status new) → tess → score → rescan → viewer`; prints summary per status
  - `viewer`
  - `status [--book B]` — counts per status and open issues per book (Russian labels from `viewer.UI`)
  - `issues [--book B] [--sheet S] [--kind K]`
  - `resolve ID [--note TEXT] [--wontfix]`
  - `proof BOOK SHEET [--by NAME]` — sets `proofread`, `reviewer`, `reviewed_at`, records current `text_hash`; refuses if open issues remain unless `--force`
  - `note BOOK SHEET TEXT` — adds `human_note` issue
  - `export` — writes `kb/review/pages.csv`, `kb/review/issues.csv` sorted by (book, stem, id)
- `--book` accepts slug or code (`book_slug` applied).

- [ ] **Step 1: Write failing tests**
  - `test_cli_run_pipeline_fake` (temp KB with 2 sheets, fake runner, fake tesseract → after `run`, both sheets have status in `{needs_proof, needs_rescan}` and `viewer/index.html` exists)
  - `test_cli_proof_refuses_with_open_issues` (exit code 1, message contains `"открытые замечания"`)
  - `test_cli_export_sorted_and_stable` (two exports → identical bytes)
  - `test_cli_book_accepts_code` (`--book "М181-600-000 ИЭ"` resolves)
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** `python -I -X utf8 kb/tools/kb.py check` → same OK/warn output as the old checker. Then delete the three old scripts; rerun the full test suite. Expected: PASS.
- [ ] **Step 6:** Commit `feat: kb.py master CLI; remove superseded scripts`.

---

### Task 9: Onboarding future documents

**Files:**
- Create: `kblib/onboard.py`; Modify: `kb.py` (add `new-book`, `read-sheets`)
- Test: `tests/test_onboard.py`

**Interfaces:**
- Produces:
  - `onboard.new_book(code: str, scan_folder: str, title: str = "") -> Path` — creates `kb/<book_slug(code)>/` with `book.json` (`code, title, sheets_total: null, withdrawn: [], known_missing: [], related: []`) and `manifest.csv` with one row per `*.tif|*.tiff|*.jpg|*.png` in name order, `sheet` blank, `orient` from image size; refuses if the folder exists
  - `onboard.read_sheets(slug, runner=default_runner, jobs=4) -> dict[str, str]` — for rows with blank `sheet`, crops the title-block corner (portrait: right 38 % × bottom 7 %; landscape: rotate 90° first, same crop), asks Haiku via `claude -p` to reply `SHEET: <label or NONE>`, writes the label into the manifest (`note` += `"sheet read by haiku"`); `NONE` leaves it blank and adds a `numbering` issue
  - CLI: `kb.py new-book "<code>" "<scan folder>" [--title T]`, `kb.py read-sheets --book B`
- Rule: `sheets_total` stays `null` until a person copies it from the title block; `check_book` treats `null` as "not verified" (warning, not error).

- [ ] **Step 1: Write failing tests**
  - `test_new_book_creates_manifest` (3 fixture images incl. one landscape → 3 rows, `orient` `P,P,L`)
  - `test_new_book_refuses_existing`
  - `test_read_sheets_fills_labels` (fake runner answers `SHEET: 32б`, `SHEET: NONE`) → manifest has `32б` and blank; one `numbering` issue
  - `test_check_null_sheets_total_is_warning`
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** Commit `feat: onboarding for new documents`.

---

### Task 10: Migrate pilot data, calibrate, update agent docs

**Files:**
- Move: `ocr_runs/haiku/M181-600-000_IE/*.md` → `kb/M181-600-000_IE/ocr/haiku/`; existing `kb/*/pages/*.md` copied to `kb/<book>/ocr/opus-chat/` (engine name for the hand-run Opus transcriptions)
- Modify: `kb/SCHEME.md` (add sections “Text versions”, “Review database”, “Status flow”, “Risk score”), `kb/AGENTS.md` (prefer `status: proofread`; check open issues via `kb.py issues --sheet`; viewer path)
- Copy: tessdata files into `kb/tools/tessdata/`

- [ ] **Step 1:** `kb.py check`, then register pages: for every existing `pages/<stem>.md` set `engine="opus-chat"`, `status="ocr_done"`, `text_hash` = current hash (one-off snippet run from `kb/tools`, not a CLI command).
- [ ] **Step 2:** `kb.py tess --book M181-600-000_IE` and `kb.py score --book M181-600-000_IE`.
- [ ] **Step 3: Calibration check.** `kb.py status --book M181-600-000_IE` and `kb.py issues --book M181-600-000_IE --sheet 110`. Expected: л.110 (changelog) has an open `handwritten` issue; no `opus-chat` page is `needs_rescan`. Then calibrate the threshold on Haiku output: snippet computing `score_sheet(signals(read_page(ocr/haiku/<stem>.md), tess))` for the 20 sheets, printed as a table. Expected: л.110 ≥ 6 and at least 15 of 20 sheets < 6. If not, change only `RESCAN_THRESHOLD`, and record the chosen value and the distribution in SCHEME.md.
- [ ] **Step 4:** `kb.py viewer`; open `kb/viewer/index.html` in the browser pane; spot-check l040, l100 (landscape table), l110, ТО l025_insert1.
- [ ] **Step 5:** `kb.py export`; commit `chore: migrate pilot OCR into review DB; docs for agents`.

---

## Execution notes

- Live model calls happen only in Task 4 Step 5, Task 10 (none by default) and real `run`s afterwards; tests always use the fake runner.
- After the plan: full run per book = `python -I -X utf8 kb/tools/kb.py run --book M181-600-000_TO` (smallest book first), then IE, then E4.1 (expect most E4.1 sheets `needs_proof` with metadata-only text).
