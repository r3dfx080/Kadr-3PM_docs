"""Review database (spec §3 «Review database», «Issue retention»): kb/review.sqlite with `pages` (status,
engine, score, hash, reviewer) and `issues` (per-sheet doubts and corrections with source and resolution).
`sync` fills it from files on disk; humans act through this CLI; every change rewrites the sorted CSV copies
kb/review/*.csv (for git diffs) and the viewer.

Usage (python -I -X utf8 kb/tools/review.py …):
  sync                                  read ingest state and page files into the DB
  issues [book] [stem] [--all]          list open (or all) issues
  resolve <id>… [--note TEXT] [--wontfix]
  note <book> <stem> TEXT               add a human_note issue
  proof <book> <stem> [--by NAME]       needs_proof -> proofread (needs no open issues)

Issue sources: haiku/opus (model doubts, glossary suggestions, [неразборчиво]) stay until a human resolves them; `score`
(handwritten marks, changelog sheets, numbers mixing typewriter I and digit 1) and `ingest` (OCR failures) are
re-derived on every sync.
An issue a human resolved is never re-opened by sync. Page text is corrected in the page file itself;
promote() leaves a page alone once it is proofread or its hash differs from the last machine write.

`sync` also regenerates kb/abbreviations.csv (abbreviation -> sheets) from page text; never edit it by hand.
Confirmed 3ПМ meanings go into glossary.csv (scope 3ПМ) and show up in its `glossary` column.
"""
import argparse, csv, hashlib, os, re, sqlite3, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import ingest
from ocr_batch import normalize

STATUSES = ("new", "ocr_done", "needs_rescan", "needs_proof", "proofread")
ISSUE_KINDS = ("illegible", "uncertain", "handwritten", "tess_mismatch", "model_disagreement", "numbering",
               "ocr_failed", "suggestion", "human_note")
DERIVED = ("score", "ingest")                   # sources sync replaces wholesale
SCHEMA = """
CREATE TABLE IF NOT EXISTS pages(book TEXT, stem TEXT, status TEXT, engine TEXT, score INTEGER, text_hash TEXT,
  reviewer TEXT, reviewed_at TEXT, updated_at TEXT, PRIMARY KEY(book, stem));
CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY, book TEXT, stem TEXT, kind TEXT, source TEXT,
  detail TEXT, status TEXT DEFAULT 'open', note TEXT DEFAULT '', created_at TEXT, resolved_at TEXT);
PRAGMA user_version = 1;
"""
now = lambda: datetime.now().isoformat(timespec="seconds")
HUMAN = "human"                                 # text_hash of a page a person owns: never equals a real hash


def text_hash(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


class ReviewDB:
    def __init__(self, path=None):
        self.con = sqlite3.connect(path or os.path.join(ingest.KB, "review.sqlite"))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    def close(self):
        self.con.commit()
        self.con.close()

    def page(self, book, stem):
        r = self.con.execute("SELECT * FROM pages WHERE book=? AND stem=?", (book, stem)).fetchone()
        return dict(r) if r else None

    def set_page(self, book, stem, **fields):
        assert set(fields) <= {"status", "engine", "score", "text_hash", "reviewer", "reviewed_at"}, fields
        assert fields.get("status", "new") in STATUSES, fields
        self.con.execute("INSERT OR IGNORE INTO pages(book, stem, status) VALUES(?, ?, 'new')", (book, stem))
        cols = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE pages SET {cols}, updated_at=? WHERE book=? AND stem=?",
                         (*fields.values(), now(), book, stem))

    def add_issue(self, book, stem, kind, source, detail):
        """-> id; an issue equal after normalize() in any status is reused (its detail updated to the new
        spelling), so sync never re-opens a resolved one and a normalizer fix does not duplicate issues."""
        assert kind in ISSUE_KINDS, kind
        for i, d in self.con.execute("SELECT id, detail FROM issues WHERE book=? AND stem=? AND kind=? AND source=?"
                                     " ORDER BY id", (book, stem, kind, source)).fetchall():
            if d == detail or normalize(d) == normalize(detail):
                if d != detail:
                    self.con.execute("UPDATE issues SET detail=? WHERE id=?", (detail, i))
                return i
        return self.con.execute("INSERT INTO issues(book, stem, kind, source, detail, created_at) VALUES(?,?,?,?,?,?)",
                                (book, stem, kind, source, detail, now())).lastrowid

    def issues(self, book=None, stem=None, status="open"):
        q, args = "SELECT * FROM issues WHERE 1", []
        for col, v in (("book", book), ("stem", stem), ("status", status)):
            if v:
                q, args = q + f" AND {col}=?", args + [v]
        return [dict(r) for r in self.con.execute(q + " ORDER BY id", args)]

    def resolve(self, issue_id, note="", status="resolved"):
        if not self.con.execute("UPDATE issues SET status=?, note=?, resolved_at=? WHERE id=?",
                                (status, note, now(), issue_id)).rowcount:
            raise KeyError(f"no issue {issue_id}")

    def reopen(self, issue_id):
        if not self.con.execute("UPDATE issues SET status='open', note='', resolved_at=NULL WHERE id=? AND status!='open'",
                                (issue_id,)).rowcount:
            raise KeyError(f"no resolved issue {issue_id}")

    def clear_open(self, book, stem, source, keep=()):
        """Delete open issues from one source, except ids in `keep` (so unchanged issues keep their id)."""
        self.con.execute(f"DELETE FROM issues WHERE book=? AND stem=? AND source=? AND status='open'"
                         f" AND id NOT IN ({','.join('?' * len(keep))})", (book, stem, source, *keep))


def may_write(db, book, stem, path):
    """False once a human owns the page: proofread, or edited since the last machine write."""
    p = db.page(book, stem)
    if not p or not os.path.exists(path):
        return True
    return p["status"] != "proofread" and (not p["text_hash"] or p["text_hash"] == text_hash(path))


def sync(db):
    """Pages and issues from ingest state and page files (no model calls)."""
    import viewer
    for book in ingest.books():
        _, rows = ingest.load(os.path.join(ingest.KB, book))
        for row, stem in rows:
            st = ingest.sheet_state(book, row, stem)
            path = os.path.join(ingest.KB, book, "pages", stem + ".md")
            p = db.page(book, stem) or {}
            status = ("needs_proof" if st["page"] == "done" else "needs_rescan" if st["opus"] in ("needed", "FAILED")
                      else "ocr_done" if st["haiku"] == "ok" else "new")
            fields = dict(engine="opus" if st["opus"] == "ok" else "haiku" if st["haiku"] == "ok" else "",
                          score=st["score"] if st["score"] != "" else None)
            if p.get("status") != "proofread":
                fields["status"] = status
            if st["page"] == "done" and not p.get("text_hash"):
                fields["text_hash"] = text_hash(path)       # first sync: pages on disk are machine-written
            db.set_page(book, stem, **fields)
            keep = []                                   # derived issues still true this sync
            for eng in ("haiku", "opus"):
                if st[eng] == "FAILED":
                    keep.append(db.add_issue(book, stem, "ocr_failed", "ingest", f"{eng}: ocr/{eng}/{stem}.md.failed.txt"))
            meta, body = viewer.read_page(path) if st["page"] == "done" else ({}, "")
            model = fields["engine"] or "ocr"           # engine output may be gone; the page is still a model's
            for x in meta.get("uncertain", []):
                src, _, rest = x.partition(": ")
                src, x = (src, rest) if src in ("haiku", "opus") else (model, x)
                db.add_issue(book, stem, "uncertain", src, x)
            for x in meta.get("suggest", []):          # model's glossary hint; text keeps what is printed
                src, _, rest = x.partition(": ")
                src, x = (src, rest) if src in ("haiku", "opus") else (model, x)
                db.add_issue(book, stem, "suggestion", src, x)
            for m in re.finditer(r"\[неразборчиво\]", body):
                ctx = " ".join(body[max(0, m.start() - 40):m.end() + 40].split())
                db.add_issue(book, stem, "illegible", model, f"…{ctx}…")
            for x in meta.get("marks", []):
                keep.append(db.add_issue(book, stem, "handwritten", "score", x))
            raw = body and ingest.read_raw(os.path.join(ingest.KB, book, "ocr", model), stem)
            for t, ctx in (ingest.mixed_i1(raw[1][5]) if raw else []):     # raw reply: normalize erases the mix
                keep.append(db.add_issue(book, stem, "uncertain", "score",
                                         f"«{t}»: в числе смешаны машинописное I и цифра 1 — сверить со сканом: …{ctx}…"))
            if body and (row["kind"] or meta.get("kind")) == "changelog":
                keep.append(db.add_issue(book, stem, "handwritten", "score", "лист регистрации изменений: сверить со сканом"))
            for src in DERIVED:
                db.clear_open(book, stem, src, keep)
    db.con.commit()
    write_abbreviations()


ABBR = re.compile(r"(?<![\w-])[А-ЯЁA-Z]{2,}[а-яё]?(?![\w-])")     # ВКУ, ЛПМ, МГц; not А104 or КМ-1


def write_abbreviations(out=None):
    """kb/abbreviations.csv: every all-caps token in page text (comments skipped) with the sheets it is on.
    likely_word = the same word also occurs in lowercase (panel labels, headings) — flagged, not dropped."""
    import viewer
    sheets, lower = {}, set()
    for book in ingest.books():
        meta, rows = ingest.load(os.path.join(ingest.KB, book))
        short = meta["code"].split()[-1]
        for row, stem in rows:
            path = os.path.join(ingest.KB, book, "pages", stem + ".md")
            if not os.path.exists(path):
                continue
            body = re.sub(r"(?s)<!--.*?-->", "", viewer.read_page(path)[1])
            lower |= set(re.findall(r"\b[а-яё]{2,}\b", body))
            cite = f"{short} л.{row['sheet'] or stem}"
            for t in ABBR.findall(body):
                if not re.fullmatch(r"[IVX]+", t) and cite not in sheets.setdefault(t, []):
                    sheets[t].append(cite)
    gloss, gpath = {}, os.path.join(ingest.KB, "glossary.csv")
    for g in csv.DictReader(open(gpath, encoding="utf-8")) if os.path.exists(gpath) else []:
        gloss.setdefault(g["abbr"], []).append(f"{g['expansion']} ({g['scope']})")
    with open(out or os.path.join(ingest.KB, "abbreviations.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["abbr", "count", "pages", "likely_word", "glossary"])
        for t in sorted(sheets):
            w.writerow([t, len(sheets[t]), "; ".join(sheets[t]), "yes" if t.lower() in lower else "",
                        " | ".join(gloss.get(t, []))])


def proof(db, book, stem, by):
    """needs_proof -> proofread; ValueError while the page has open issues."""
    p, left = db.page(book, stem), db.issues(book, stem)
    if not p or p["status"] != "needs_proof":
        raise ValueError(f"{book} {stem}: статус {p and p['status']}, а не needs_proof")
    if left:
        raise ValueError(f"{book} {stem}: открытых замечаний {len(left)} — сначала resolve")
    path = os.path.join(ingest.KB, book, "pages", stem + ".md")
    db.set_page(book, stem, status="proofread", reviewer=by, reviewed_at=now(), text_hash=text_hash(path))


def unproof(db, book, stem):
    """proofread -> needs_proof. proof() overwrote the machine text hash, so the page stays human-owned
    (text_hash HUMAN never matches): OCR must not overwrite text a person may have corrected."""
    p = db.page(book, stem)
    if not p or p["status"] != "proofread":
        raise ValueError(f"{book} {stem}: статус {p and p['status']}, а не proofread")
    db.set_page(book, stem, status="needs_proof", reviewer=None, reviewed_at=None, text_hash=HUMAN)


def reopen(db, book, stem, issue_id):
    """Resolved issue -> open; refused on a proofread sheet (it would be proofread with open issues)."""
    if (db.page(book, stem) or {}).get("status") == "proofread":
        raise ValueError(f"{book} {stem}: лист вычитан — сначала снимите отметку (unproof)")
    if issue_id not in [x["id"] for x in db.issues(book, stem, None) if x["status"] != "open"]:
        raise ValueError(f"нет исправленного замечания #{issue_id} на листе {book} {stem}")
    db.reopen(issue_id)


def export(db, out=None):
    """Sorted CSV copies for git diffs."""
    out = out or os.path.join(ingest.KB, "review")
    os.makedirs(out, exist_ok=True)
    for table, order in (("pages", "book, stem"), ("issues", "id")):
        cur = db.con.execute(f"SELECT * FROM {table} ORDER BY {order}")
        with open(os.path.join(out, table + ".csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(d[0] for d in cur.description)
            w.writerows(cur)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    a = sub.add_parser("issues"); a.add_argument("book", nargs="?"); a.add_argument("stem", nargs="?")
    a.add_argument("--all", action="store_true")
    a = sub.add_parser("resolve"); a.add_argument("ids", nargs="+", type=int); a.add_argument("--note", default="")
    a.add_argument("--wontfix", action="store_true")
    a = sub.add_parser("note"); a.add_argument("book"); a.add_argument("stem"); a.add_argument("text")
    a = sub.add_parser("proof"); a.add_argument("book"); a.add_argument("stem")
    a.add_argument("--by", default=os.environ.get("USERNAME", ""))
    a = sub.add_parser("unproof"); a.add_argument("book"); a.add_argument("stem")
    a = sub.add_parser("reopen"); a.add_argument("ids", nargs="+", type=int)
    args = ap.parse_args()
    db = ReviewDB()
    if args.cmd == "issues":
        for i in db.issues(args.book, args.stem, None if args.all else "open"):
            print(f"{i['id']:>5} {i['book']} {i['stem']} [{i['kind']}/{i['source']}] {i['status']}: {i['detail']}")
        return db.close()
    if args.cmd == "sync":
        sync(db)
    elif args.cmd == "resolve":
        for i in args.ids:
            db.resolve(i, args.note, "wontfix" if args.wontfix else "resolved")
    elif args.cmd == "note":
        print(db.add_issue(args.book, args.stem, "human_note", "human", args.text))
    elif args.cmd in ("proof", "unproof", "reopen"):
        try:
            if args.cmd == "proof":
                proof(db, args.book, args.stem, args.by)
            elif args.cmd == "unproof":
                unproof(db, args.book, args.stem)
            for i in getattr(args, "ids", []):
                x = db.con.execute("SELECT book, stem FROM issues WHERE id=?", (i,)).fetchone()
                if not x:
                    raise ValueError(f"нет замечания #{i}")
                reopen(db, x["book"], x["stem"], i)
        except ValueError as e:
            sys.exit(str(e))
    export(db)
    db.close()
    import viewer
    viewer.build_viewer()


if __name__ == "__main__":
    main()
