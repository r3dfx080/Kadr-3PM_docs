"""Validate each book's manifest.csv against its book.json.

Checks: sheet labels are unique and in order; every gap in the numbering is declared
(withdrawn or known_missing); sheet count matches the title block; every scan exists;
every page file in pages/ matches a manifest row.
Usage: python check_manifest.py [kb_dir]     (exit code 1 if any error)
"""
import csv, json, os, re, sys

SUFFIX = "абвгдежз"                     # inserted-sheet suffixes, in order
TRANSLIT = dict(zip(SUFFIX, "abcdefgh"))  # by position, so file names sort in document order (32в < 32г)


def key(label):
    """'32б' -> (32, 2); '45' -> (45, 0)."""
    m = re.fullmatch(r"(\d+)([а-я]?)", label)
    if not m:
        raise ValueError(f"bad sheet label {label!r}")
    return int(m[1]), SUFFIX.index(m[2]) + 1 if m[2] else 0


def page_name(label):
    """Sheet label -> page file stem: '32б' -> 'l032b', '5' -> 'l005'."""
    n, _ = key(label)
    return f"l{n:03d}" + "".join(TRANSLIT[c] for c in re.sub(r"\d", "", label))


def check(book_dir, root):
    errors, warns = [], []
    meta = json.load(open(os.path.join(book_dir, "book.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(os.path.join(book_dir, "manifest.csv"), encoding="utf-8")))
    labels = [r["sheet"] for r in rows if r["sheet"]]

    dup = {l for l in labels if labels.count(l) > 1}
    if dup:
        errors.append(f"duplicate sheets: {sorted(dup, key=key)}")
    for a, b in zip(labels, labels[1:]):
        if key(b) <= key(a):
            errors.append(f"out of order: {a} then {b}")

    present = {key(l) for l in labels}
    declared = {key(l) for l in meta["withdrawn"]} | {key(l) for l in meta["known_missing"]}
    nums = [n for n, _ in present]
    gaps = [(n, 0) for n in range(1, max(nums) + 1) if (n, 0) not in present]
    for g in gaps:
        (warns if g in declared else errors).append(
            f"sheet {g[0]} absent" + (" (declared)" if g in declared else " — UNDECLARED"))

    if len(labels) != meta["sheets_total"]:
        warns.append(f"{len(labels)} sheets scanned, title block says {meta['sheets_total']}")

    for r in rows:
        if not os.path.exists(os.path.join(root, r["scan"])):
            errors.append(f"scan missing: {r['scan']}")

    by_name = {page_name(r["sheet"]): r for r in rows if r["sheet"]}
    by_scan = {r["scan"]: r for r in rows}
    pages = os.path.join(book_dir, "pages")
    for f in (os.listdir(pages) if os.path.isdir(pages) else []):
        stem = f.removesuffix(".md")
        if stem not in by_name and not re.fullmatch(r"l\d{3}[a-z]*_insert\d+", stem):
            errors.append(f"page file with no manifest row: {f}")
            continue
        text = open(os.path.join(pages, f), encoding="utf-8").read()
        fm = dict(re.findall(r'^(sheet|scan): "?(.*?)"?$', text, re.M))
        row = by_scan.get(fm.get("scan"))
        if row is None or row["sheet"] != fm.get("sheet") or by_name.get(stem, row) is not row:
            errors.append(f"{f}: front-matter sheet/scan disagree with manifest")
    return errors, warns


if __name__ == "__main__":
    assert key("32б") == (32, 2) and key("45") == (45, 0) and key("32") < key("32а") < key("33")
    assert page_name("32б") == "l032b" and page_name("5") == "l005" and page_name("15а") == "l015a"
    assert [page_name(s) for s in ["32", "32а", "32б", "32в", "32г", "33"]] == \
        sorted(page_name(s) for s in ["32", "32а", "32б", "32в", "32г", "33"])
    kb = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..")
    kb = os.path.abspath(kb)
    failed = False
    for d in sorted(os.listdir(kb)):
        bd = os.path.join(kb, d)
        if os.path.exists(os.path.join(bd, "manifest.csv")):
            errs, warns = check(bd, os.path.dirname(kb))
            print(f"{d}: {'OK' if not errs else 'FAIL'}")
            for w in warns: print("   warn:", w)
            for e in errs: print("  ERROR:", e)
            failed |= bool(errs)
    sys.exit(failed)
