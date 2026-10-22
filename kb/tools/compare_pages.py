"""Compare two directories of kb page files (reference vs candidate OCR).

Usage: python compare_pages.py <ref_pages_dir> <cand_pages_dir>
Per page: word agreement, every disagreeing token that contains a digit, correction comments found,
and the KEY_FACTS checks. Both sides are folded the same way (case, ё, Latin look-alikes), so only
real reading differences count.
"""
import difflib, glob, os, re, sys

FOLD = str.maketrans("ABCEHKMOPTXaceopxyё", "АВСЕНКМОРТХасеорхуе")
# hard spots found in this sample set: sheet -> strings the candidate text must contain (after folding)
KEY_FACTS = {"40": ["+10 в"], "43": ["80 мкс"], "36": ["320"], "37": ["sin", "20t"], "39": ["d"],
             "5": ["формуляром на осциллограф"], "109": ["50лим", "697-096"], "97": ["26,236"]}


def load(path):
    t = open(path, encoding="utf-8").read()
    body = re.sub(r"(?s)^---.*?\n---\n", "", t)
    fixes = len(re.findall(r"<!--\s*изм", body))
    marks = len(re.findall(r"^  - ", re.match(r"(?s)^---.*?\n---\n", t)[0], re.M))
    text = re.sub(r"(?s)<!--.*?-->", " ", body).lower().translate(FOLD)
    text = re.sub(r"<br>|[*#|`]", " ", text)
    return text, re.findall(r"[^\s«»\"'(),;:]+", text), fixes, marks


def main(ref_dir, cand_dir):
    tot_m = tot_n = 0
    for ref in sorted(glob.glob(os.path.join(ref_dir, "*.md"))):
        cand = os.path.join(cand_dir, os.path.basename(ref))
        if not os.path.exists(cand):
            print(os.path.basename(ref), "missing in candidate"); continue
        rt, rw, rf, rm = load(ref)
        ct, cw, cf, cm = load(cand)
        sm = difflib.SequenceMatcher(None, rw, cw, autojunk=False)
        match = sum(b.size for b in sm.get_matching_blocks()); tot_m += match; tot_n += len(rw)
        diffs = [f"{' '.join(rw[i1:i2]) or '∅'} -> {' '.join(cw[j1:j2]) or '∅'}"
                 for op, i1, i2, j1, j2 in sm.get_opcodes()
                 if op != "equal" and any(re.search(r"\d", w) for w in rw[i1:i2] + cw[j1:j2])]
        sheet = re.search(r'^sheet: "(.*)"', open(ref, encoding="utf-8").read(), re.M)[1]
        facts = [f for f in KEY_FACTS.get(sheet, []) if f not in ct.replace("\n", " ")]
        pct = 100 * match / max(len(rw), 1)
        print(f"л.{sheet:>4}: {pct:5.1f}% words  corrections ref/cand {rf}/{cf}  marks {rm}/{cm}  "
              f"numeric diffs {len(diffs)}" + (f"  MISSING FACT: {facts}" if facts else ""))
        for d in diffs[:12]:
            print("        ", d[:120])
    print(f"TOTAL: {100 * tot_m / max(tot_n, 1):.1f}% of reference words matched")


if __name__ == "__main__":
    main(*sys.argv[1:3])
