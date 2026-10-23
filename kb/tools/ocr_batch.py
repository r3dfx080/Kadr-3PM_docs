"""OCR sheets of one book with `claude -p` (uses the Claude subscription login) into kb page format.

Usage:
  python ocr_batch.py <book_dir> <out_dir> [--model haiku] [--sheets 40,41,32б,l025_insert1] [--jobs 4]

Images are SOURCES_JPEG/<book>/<stem>.jpg (run make_jpegs.py first). Front-matter is built from
manifest.csv/book.json (never from the model); the model supplies kind (used only when the manifest has
none), section, rev, marks, uncertain, suggest (glossary hints, never applied to the text) and the text. Already-written pages are skipped, so a run can be
resumed after hitting a usage limit. Per-page usage goes to <out_dir>/_runlog.jsonl.
"""
import argparse, csv, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from make_jpegs import stems

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(TOOLS))           # folder holding the scan folders

LAT2CYR = str.maketrans("ABCEHKMOPTXaceopxy", "АВСЕНКМОРТХасеорху")


def normalize(text):
    """Typewriter I→1 / O→0 inside numbers and designators; Latin look-alikes → Cyrillic in Russian tokens."""
    def fix(tok):
        # number/designator: [sign][≤3-letter prefix][-]digits-with-typewriter-I/O[≤2-letter suffix][% or °]
        m = re.fullmatch(r"([+\-]?)([A-ZА-ЯЁ]{0,3}?)(-?)([IОO0-9][IОO0-9.,/+\-]*)([A-HJ-NP-ZА-НП-ЯЁ]{0,2}[%°]?)", tok)
        if m and not (m[2] + m[4]).startswith("ТО"):      # «ТОI» is document ТО1, not Т01
            pre, num = m[2], m[4]
            if re.search(r"[I\d]", num) and (re.search(r"\d", num) or num.endswith(".")
                                             or (len(num) > 1 and re.search(r"[OО0]", num))):
                pre = pre.translate(LAT2CYR) if re.fullmatch(r"[ABCEHKMOPTX]*", pre) else pre
                num = re.sub(r"[IОO]", lambda c: "1" if c[0] == "I" else "0", num)
                return m[1] + pre + m[3] + num + m[5].translate(LAT2CYR)
        if re.fullmatch(r"[ABCEHKMOPTX]{1,2}", tok) or (re.search(r"[А-Яа-яЁё]", tok) and re.search(r"[A-Za-z]", tok)):
            return tok.translate(LAT2CYR)                  # «M», «MB», mixed-script «MОДУЛЯТОР»
        return tok
    text = re.sub(r"(?<=[аА][дД][рР]-)З(?=[пП][мМ])", "3", text)   # product name «Кадр-3ПМ», З misread for 3
    text = text.replace("І", "I")             # the model sometimes writes the typewriter I as Cyrillic-block І
    # a comma before a digit stays inside the token (decimal comma: «I,15» → «1,15»); other commas split
    # a number glued to a Russian abbreviation is its own token: «см.п.6.I0.9.» → «см.п.» + «6.I0.9.»
    glued = lambda t: "".join(fix(x) for x in re.split(r"(?<=[А-Яа-яЁё]\.)(?=[\dIОO])", t))
    tok = lambda s: re.sub(r"(?:[^\s«»\"'(),;:]|,(?=[\dIОO]))+", lambda m: glued(m[0]), s)
    # HTML tags (<sup>, </sub>, <br>) are markup, not text: never normalized, and they split tokens
    return "".join(p if i % 2 else tok(p) for i, p in enumerate(re.split(r"(</?[a-z]+\s*/?>)", text)))


def parse(reply):
    """-> (kind, section, rev, marks, uncertain, body, suggest); only SECTION and TEXT are required
    (REV: old replies only; SUGGEST: newer replies only)."""
    m = re.search(r"(?s)(?:KIND:(.*?)\n)?SECTION:(.*?)\n(?:REV:(.*?)\n)?(?:MARKS:(.*?)\n)?(?:UNCERTAIN:(.*?)\n)?"
                  r"(?:SUGGEST:(.*?)\n)?TEXT:\s*\n?(.*)$", reply)
    if not m:
        raise ValueError("reply not in the expected format")
    items = lambda s: [l.strip()[2:].strip() for l in (s or "").splitlines() if l.strip().startswith("- ")]
    return (m[1] or "").strip(), m[2].strip(), (m[3] or "").strip(), items(m[4]), items(m[5]), m[7].strip(), items(m[6])


def yaml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def yaml_list(name, xs):
    return [f"{name}:"] + [f"  - {yaml_str(x)}" for x in xs] if xs else [f"{name}: []"]


def run_one(row, stem, prev, nxt, meta, args):
    out = os.path.join(args.out, stem + ".md")
    if os.path.exists(out):
        return stem, "skipped"
    img = os.path.join(ROOT, "SOURCES_JPEG", os.path.basename(os.path.abspath(args.book)), stem + ".jpg")
    if not os.path.exists(img):
        return stem, "FAILED: no JPEG, run make_jpegs.py"
    sheet = row["sheet"] or f"вставка после листа {prev} (не входит в документ)"
    prompt = open(os.path.join(TOOLS, "ocr_prompt.md"), encoding="utf-8").read().format(
        sheet=sheet, doc=meta["code"], prev=prev, next=nxt, image=img,
        glossary=os.path.join(os.path.dirname(TOOLS), "glossary.csv"))
    t0 = time.time()
    # isolated session: only the Read tool, no user settings (plugins, hooks), skills or MCP servers, which
    # otherwise add ~40k tokens per call and once leaked a plugin's "not verified" note into TEXT
    # (--bare would be cleaner but refuses the subscription login)
    p = subprocess.run(["claude", "-p", prompt, "--model", args.model, "--tools", "Read", "--allowedTools", "Read",
                        "--setting-sources", "project,local", "--disable-slash-commands",
                        "--strict-mcp-config", "--no-session-persistence", "--output-format", "json"],
                       cwd=os.path.dirname(img), capture_output=True, text=True, encoding="utf-8", timeout=600)
    try:
        res = json.loads(p.stdout)
        if res.get("is_error"):
            raise ValueError(res.get("result"))
        fields = parse(res["result"])
    except Exception as e:                                  # keep the raw reply for inspection
        open(out + ".failed.txt", "w", encoding="utf-8").write(p.stdout + "\n" + p.stderr)
        return stem, f"FAILED: {e}"
    model = next(iter(res.get("modelUsage", {})), args.model)
    os.makedirs(os.path.join(args.out, "_raw"), exist_ok=True)
    with open(os.path.join(args.out, "_raw", stem + ".txt"), "w", encoding="utf-8") as f:
        f.write(f"model: {model}\n" + res["result"])          # raw reply: lets --renormalize redo the cleanup
    write_page(out, row, meta, model, *fields)
    if os.path.exists(out + ".failed.txt"):
        os.remove(out + ".failed.txt")
    with open(os.path.join(args.out, "_runlog.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"sheet": row["sheet"] or stem, "model": model, "sec": round(time.time() - t0),
                            "cost_usd_equiv": res.get("total_cost_usd"), "usage": res.get("usage")},
                           ensure_ascii=False) + "\n")
    return stem, "ok"


def write_page(out, row, meta, model, kind, section, rev, marks, uncertain, body, suggest=(), ocr_note=None):
    section, marks, uncertain = normalize(section), [normalize(x) for x in marks], [normalize(x) for x in uncertain]
    fm = ["---", f"doc: {meta['code']}", f'sheet: "{row["sheet"]}"', f"scan: {row['scan']}",
          f"kind: {row['kind'] or kind}", f"section: {yaml_str(section)}", f"rev: {yaml_str(rev)}"]
    fm += yaml_list("marks", marks) + yaml_list("uncertain", uncertain) + yaml_list("suggest", list(suggest))
    fm += [f"ocr: {ocr_note or model + ' via claude -p; normalized; not proofread'}", "---", ""]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(fm) + normalize(body) + "\n")


def read_raw(out_dir, stem):
    """-> (model, parsed fields) from a saved raw reply, or None."""
    raw = os.path.join(out_dir, "_raw", stem + ".txt")
    if not os.path.exists(raw):
        return None
    model, reply = open(raw, encoding="utf-8").read().split("\n", 1)
    return model.removeprefix("model: "), parse(reply)


def renormalize(rows, meta, out_dir):
    """Rebuild page files from the saved raw replies (after changing normalize/front-matter rules)."""
    for r, stem in rows:
        got = read_raw(out_dir, stem)
        if got:
            write_page(os.path.join(out_dir, stem + ".md"), r, meta, got[0], *got[1])
            print(stem, "renormalized")


def load(book):
    meta = json.load(open(os.path.join(book, "book.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(os.path.join(book, "manifest.csv"), encoding="utf-8")))
    return meta, list(zip(rows, stems(rows)))


def ocr(book, out, model, want=None, jobs=4, renorm=False):
    """OCR rows whose sheet label or stem is in `want` (all if None) -> [(stem, status)]."""
    meta, rows = load(book)
    sel = [i for i, (r, s) in enumerate(rows) if want is None or r["sheet"] in want or s in want]
    if renorm:
        return renormalize([rows[i] for i in sel], meta, out) or []
    os.makedirs(out, exist_ok=True)
    args = argparse.Namespace(book=book, out=out, model=model)
    label = lambda i: (rows[i][0]["sheet"] or rows[i][1]) if 0 <= i < len(rows) else ""
    with ThreadPoolExecutor(jobs) as ex:
        return list(ex.map(lambda i: run_one(*rows[i], label(i - 1), label(i + 1), meta, args), sel))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book"); ap.add_argument("out")
    ap.add_argument("--model", default="haiku"); ap.add_argument("--sheets", default="")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--renormalize", action="store_true", help="only rebuild pages from _raw/ replies")
    args = ap.parse_args()
    for stem, status in ocr(args.book, args.out, args.model, args.sheets.split(",") if args.sheets else None,
                            args.jobs, args.renormalize):
        print(stem, status, flush=True)


if __name__ == "__main__":
    for raw, want in [("6.II.I.", "6.11.1."), ("МI02", "М102"), ("ВIOI", "В101"), ("+I70", "+170"),
                      ("MI8I-600-000", "М181-600-000"), ("СI-64", "С1-64"), ("TR-0884/KOI7", "TR-0884/KOI7"),
                      ("COLOUR BAR I", "COLOUR BAR I"), ("I. ВВЕДЕНИЕ", "1. ВВЕДЕНИЕ"), ("АI04.", "А104."),
                      ("MОДУЛЯТОР", "МОДУЛЯТОР"), ("М 06/I", "М 06/1"), ("ЧМ сигнала", "ЧМ сигнала"),
                      ("канала II", "канала II"), ("ОГИБ.", "ОГИБ."), ("( 5 - IO )", "( 5 - 10 )"),
                      ("БВГ-30IМ", "БВГ-301М"), ("ВК-2I4 MB", "ВК-214 МВ"), ("ТОI", "ТОI"), ("Э4.I", "Э4.1"),
                      ("КАДР-ЗПМ", "КАДР-3ПМ"), ("Кадр-ЗПМ", "Кадр-3ПМ"), ("ИСО", "ИСО"), ("ТО", "ТО"),
                      ("WHITE", "WHITE"), ("BARI", "BARI"), ("(I,15 ± 0,35)", "(1,15 ± 0,35)"),
                      ("-I,5 В", "-1,5 В"), ("I,55,", "1,55,"), ("M, MB,", "М, МВ,"), ("I, II", "I, II"),
                      ("ЗИПа,УO2-00-000.", "ЗИПа,У02-00-000."), ("I5%", "15%"), ("+ IO° С", "+ 10° С"),
                      ("3O°", "30°"), ("І2,5 кГц", "12,5 кГц"), ("«НІ03»", "«Н103»"),
                      ("мм<sup>2</sup>", "мм<sup>2</sup>"), ("3<sup>+3</sup><sub>-I</sub>", "3<sup>+3</sup><sub>-I</sub>"),
                      ("x<br>I,5 В", "x<br>1,5 В"), ("(см.п.6.I0.9.).", "(см.п.6.10.9.)."),
                      ("Рис.I2.", "Рис.12."), ("ВХ.ВС", "ВХ.ВС"), ("т.е.Об", "т.е.Об"), ("<!-- изм. 3: было «I5%» -->", "<!-- изм. 3: было «15%» -->")]:
        assert normalize(raw) == want, (raw, normalize(raw), want)
    for reply, n in [("SECTION: s\nREV: \nMARKS:\n- m\nTEXT:\nbody", 1),
                     ("KIND: text\nSECTION: s\nREV: 3\nMARKS:\nUNCERTAIN:\n- 27 — blur\nTEXT:\nbody", 1),
                     ("KIND: text\nSECTION: s\nMARKS:\nUNCERTAIN:\n- лист: напечатано «X л.4» — x\nTEXT:\nbody", 1),
                     ("KIND: toc\nSECTION:\nUNCERTAIN:\n- x — y\nTEXT:\nbody", 1), ("KIND: toc\nSECTION:\nTEXT:\nbody", 0)]:
        f = parse(reply)
        assert f[5] == "body" and len(f[3]) + len(f[4]) == n, f
    main()
