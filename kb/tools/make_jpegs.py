"""Convert source scans to grayscale JPEGs for LLMs and the viewer.

SOURCES/<scan folder>/<n>.tif  ->  SOURCES_JPEG/<book slug>/<stem>.jpg
<stem> is the sheet's page name from manifest.csv (l032b, l025_insert1), so the file name tells which
sheet it is. Long side 2000 px, quality 85. Existing JPEGs newer than their source are skipped.

Usage: python make_jpegs.py [--book M181-600-000_IE] [--force] [--jobs 4]
"""
import argparse, csv, os, sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from check_manifest import page_name

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
OUT = os.path.join(ROOT, "SOURCES_JPEG")
LONG_SIDE, QUALITY = 2000, 85


def stems(rows):
    """Manifest rows -> page stems; a row without a sheet is an insert after the previous sheet."""
    out, last, k = [], "0", 0
    for r in rows:
        if r["sheet"]:
            last, k = r["sheet"], 0
            out.append(page_name(last))
        else:
            k += 1
            out.append(f"{page_name(last)}_insert{k}")
    return out


def convert(src, dst, force=False):
    if not force and os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return "skip"
    im = Image.open(src).convert("L")
    im.thumbnail((LONG_SIDE, LONG_SIDE))
    tmp = dst + ".part"
    im.save(tmp, "JPEG", quality=QUALITY)
    os.replace(tmp, dst)                     # never leave a half-written JPEG behind
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    books = [args.book] if args.book else sorted(
        d for d in os.listdir(KB) if os.path.exists(os.path.join(KB, d, "manifest.csv")))
    for book in books:
        rows = list(csv.DictReader(open(os.path.join(KB, book, "manifest.csv"), encoding="utf-8")))
        os.makedirs(os.path.join(OUT, book), exist_ok=True)
        jobs = [(os.path.join(ROOT, r["scan"]), os.path.join(OUT, book, s + ".jpg")) for r, s in zip(rows, stems(rows))]
        missing = [src for src, _ in jobs if not os.path.exists(src)]
        if missing:
            sys.exit(f"{book}: нет исходных файлов: {missing[:3]}…")
        with ThreadPoolExecutor(args.jobs) as ex:
            res = list(ex.map(lambda j: convert(*j, force=args.force), jobs))
        expected = {os.path.basename(dst) for _, dst in jobs}
        stale = [f for f in os.listdir(os.path.join(OUT, book)) if f not in expected]
        for f in stale:                      # generated folder: drop files no manifest row produces
            os.remove(os.path.join(OUT, book, f))
        print(f"{book}: создано {res.count('ok')}, пропущено {res.count('skip')}, "
              f"удалено устаревших {len(stale)}, всего {len(res)}")


if __name__ == "__main__":
    assert stems([{"sheet": "21"}, {"sheet": "21а"}, {"sheet": ""}, {"sheet": "22"}]) == \
        ["l021", "l021a", "l021a_insert1", "l022"]
    main()
