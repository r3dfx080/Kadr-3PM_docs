"""OCR sheets of one book with `claude -p` (uses the Claude subscription login) into kb page format.

Usage:
  python ocr_batch.py <book_dir> <out_dir> [--model haiku] [--sheets 40,41,32б] [--jobs 4]

Front-matter is built from manifest.csv/book.json (never from the model); the model supplies
section, rev, marks and the text. Already-written pages are skipped, so a run can be resumed
after hitting a usage limit. Per-page usage goes to <out_dir>/_runlog.jsonl.
"""
import argparse, csv, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from check_manifest import page_name

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(TOOLS))           # folder holding the scan folders

LAT2CYR = str.maketrans("ABCEHKMOPTXaceopxy", "АВСЕНКМОРТХасеорху")


def normalize(text):
    """Typewriter I→1 / O→0 inside numbers and designators; Latin look-alikes → Cyrillic in Russian tokens."""
    def fix(tok):
        # number/designator: [sign][≤3-letter prefix][-]digits-with-typewriter-I/O[≤2-letter suffix]
        m = re.fullmatch(r"([+\-]?)([A-ZА-ЯЁ]{0,3}?)(-?)([IОO0-9][IОO0-9.,/+\-]*)([A-HJ-NP-ZА-НП-ЯЁ]{0,2})", tok)
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
    return re.sub(r"[^\s«»\"'(),;:]+", lambda m: fix(m[0]), text)


def preview(scan, dst):
    im = Image.open(os.path.join(ROOT, scan)).convert("L")
    im.thumbnail((2000, 2000))
    im.save(dst, quality=85)


def parse(reply):
    m = re.search(r"(?s)SECTION:(.*?)\nREV:(.*?)\nMARKS:(.*?)\nTEXT:\s*\n?(.*)$", reply)
    if not m:
        raise ValueError("reply not in the expected format")
    marks = [l.strip()[2:].strip() for l in m[3].splitlines() if l.strip().startswith("- ")]
    return m[1].strip(), m[2].strip(), marks, m[4].strip()


def yaml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_one(row, prev, nxt, meta, args, work):
    stem = page_name(row["sheet"])
    out = os.path.join(args.out, stem + ".md")
    if os.path.exists(out):
        return stem, "skipped"
    img = os.path.join(work, stem + ".jpg")
    preview(row["scan"], img)
    prompt = open(os.path.join(TOOLS, "ocr_prompt.md"), encoding="utf-8").read().format(
        sheet=row["sheet"], doc=meta["code"], prev=prev, next=nxt, image=img)
    t0 = time.time()
    p = subprocess.run(["claude", "-p", prompt, "--model", args.model, "--allowedTools", "Read",
                        "--strict-mcp-config", "--no-session-persistence", "--output-format", "json"],
                       cwd=work, capture_output=True, text=True, encoding="utf-8", timeout=600)
    try:
        res = json.loads(p.stdout)
        section, rev, marks, body = parse(res["result"])
    except Exception as e:                                  # keep the raw reply for inspection
        open(out + ".failed.txt", "w", encoding="utf-8").write(p.stdout + "\n" + p.stderr)
        return stem, f"FAILED: {e}"
    model = next(iter(res.get("modelUsage", {})), args.model)
    os.makedirs(os.path.join(args.out, "_raw"), exist_ok=True)
    with open(os.path.join(args.out, "_raw", stem + ".txt"), "w", encoding="utf-8") as f:
        f.write(f"model: {model}\n" + res["result"])          # raw reply: lets --renormalize redo the cleanup
    write_page(out, row, meta, model, section, rev, marks, body)
    with open(os.path.join(args.out, "_runlog.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"sheet": row["sheet"], "model": model, "sec": round(time.time() - t0),
                            "cost_usd_equiv": res.get("total_cost_usd"), "usage": res.get("usage")},
                           ensure_ascii=False) + "\n")
    return stem, "ok"


def write_page(out, row, meta, model, section, rev, marks, body):
    section, marks = normalize(section), [normalize(x) for x in marks]
    fm = ["---", f"doc: {meta['code']}", f'sheet: "{row["sheet"]}"', f"scan: {row['scan']}",
          f"kind: {row['kind'] or ''}", f"section: {yaml_str(section)}", f"rev: {yaml_str(rev)}"]
    fm += ["marks:"] + [f"  - {yaml_str(x)}" for x in marks] if marks else ["marks: []"]
    fm += [f"ocr: {model} via claude -p; normalized; not proofread", "---", ""]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(fm) + normalize(body) + "\n")


def renormalize(rows, meta, out_dir):
    """Rebuild page files from the saved raw replies (after changing normalize/front-matter rules)."""
    for r in rows:
        stem = page_name(r["sheet"])
        raw = os.path.join(out_dir, "_raw", stem + ".txt")
        if os.path.exists(raw):
            model, reply = open(raw, encoding="utf-8").read().split("\n", 1)
            write_page(os.path.join(out_dir, stem + ".md"), r, meta, model.removeprefix("model: "), *parse(reply))
            print(stem, "renormalized")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book"); ap.add_argument("out")
    ap.add_argument("--model", default="haiku"); ap.add_argument("--sheets", default="")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--renormalize", action="store_true", help="only rebuild pages from _raw/ replies")
    args = ap.parse_args()
    meta = json.load(open(os.path.join(args.book, "book.json"), encoding="utf-8"))
    rows = [r for r in csv.DictReader(open(os.path.join(args.book, "manifest.csv"), encoding="utf-8")) if r["sheet"]]
    labels = [r["sheet"] for r in rows]
    want = set(args.sheets.split(",")) if args.sheets else set(labels)
    if args.renormalize:
        return renormalize([r for r in rows if r["sheet"] in want], meta, args.out)
    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(args.out, "_img"); os.makedirs(work, exist_ok=True)
    jobs = [(r, labels[i - 1] if i else "", labels[i + 1] if i + 1 < len(labels) else "")
            for i, r in enumerate(rows) if r["sheet"] in want]
    with ThreadPoolExecutor(args.jobs) as ex:
        for stem, status in ex.map(lambda j: run_one(*j, meta, args, work), jobs):
            print(stem, status, flush=True)


if __name__ == "__main__":
    for raw, want in [("6.II.I.", "6.11.1."), ("МI02", "М102"), ("ВIOI", "В101"), ("+I70", "+170"),
                      ("MI8I-600-000", "М181-600-000"), ("СI-64", "С1-64"), ("TR-0884/KOI7", "TR-0884/KOI7"),
                      ("COLOUR BAR I", "COLOUR BAR I"), ("I. ВВЕДЕНИЕ", "1. ВВЕДЕНИЕ"), ("АI04.", "А104."),
                      ("MОДУЛЯТОР", "МОДУЛЯТОР"), ("М 06/I", "М 06/1"), ("ЧМ сигнала", "ЧМ сигнала"),
                      ("канала II", "канала II"), ("ОГИБ.", "ОГИБ."), ("( 5 - IO )", "( 5 - 10 )"),
                      ("БВГ-30IМ", "БВГ-301М"), ("ВК-2I4 MB", "ВК-214 МВ"), ("ТОI", "ТОI"), ("Э4.I", "Э4.1"),
                      ("КАДР-ЗПМ", "КАДР-3ПМ"), ("Кадр-ЗПМ", "Кадр-3ПМ"), ("ИСО", "ИСО"), ("ТО", "ТО"),
                      ("WHITE", "WHITE"), ("BARI", "BARI")]:
        assert normalize(raw) == want, (raw, normalize(raw), want)
    main()
