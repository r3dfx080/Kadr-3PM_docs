"""Static side-by-side viewer (spec §3 «Viewer», plan Task 7): scan JPEG on the left, page text and open
doubts on the right. Writes kb/viewer/index.html and kb/viewer/<book>/<stem>.html; no server, no external JS.

Usage: python -I -X utf8 kb/tools/viewer.py        (ingest.py also rebuilds it after every batch)

shortcut: status and issues come from files on disk (ingest state, the page's `uncertain:` list and
[неразборчиво] marks), not from review.sqlite; switch to the DB once kb.py (plan Tasks 2, 8) exists.
"""
import html, json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import ingest

UI = dict(title="Документация «Кадр-3ПМ»", sheet="Лист", kind="Тип", status="Статус", risk="Риск",
          issues="Замечания", engine="Распознано", scan="Скан", prev="← пред.", next="след. →",
          back="К списку", no_text="Текст ещё не распознан", all="Все", marks="Рукописные пометки",
          edit="Исправления и закрытие замечаний — в файле страницы:", illegible="[неразборчиво] в тексте",
          new="не распознан", ocr_done="распознан", needs_rescan="на перераспознавание",
          needs_proof="на вычитку", proofread="вычитан")
STATUSES = ("new", "ocr_done", "needs_rescan", "needs_proof", "proofread")


def inline(s, keep_br=False):
    s = html.escape(s, quote=False)
    s = re.sub(r"&lt;!--\s*(.*?)\s*--&gt;", r'<span class="note">\1</span>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = s.replace("[неразборчиво]", "<mark>[неразборчиво]</mark>")
    return re.sub(r"&lt;br\s*/?&gt;", "<br>", s) if keep_br else s


def md_to_html(md):
    """The Markdown subset page files use: ##/### headings, paragraphs, pipe tables, **bold**, comments."""
    out = []
    for block in re.split(r"\n\s*\n", md.strip()):
        lines = block.splitlines()
        if re.match(r"#{2,3} ", lines[0]):                 # a heading may have its text right below it
            n = lines[0].index(" ")
            out.append(f"<h{n}>{inline(lines[0][n + 1:])}</h{n}>")
            lines = lines[1:]
            if not lines:
                continue
        if len(lines) > 1 and all(l.lstrip().startswith("|") for l in lines) and re.fullmatch(r"[\s|:\-]+", lines[1]):
            cells = lambda l: [c.strip() for c in l.strip().strip("|").split("|")]
            row = lambda l, t: "<tr>" + "".join(f"<{t}>{inline(c, True)}</{t}>" for c in cells(l)) + "</tr>"
            out.append("<table>" + row(lines[0], "th") + "".join(row(l, "td") for l in lines[2:]) + "</table>")
        else:
            out.append("<p>" + "<br>".join(inline(l) for l in lines) + "</p>")
    return "\n".join(out)


def read_page(path):
    """-> (front-matter dict with lists for marks/uncertain, body)."""
    text = open(path, encoding="utf-8").read()
    _, fm, body = text.split("---\n", 2)
    meta, key = {}, None
    for line in fm.splitlines():
        if line.startswith("  - ") and key:
            meta[key].append(json.loads(line[4:]))          # yaml_str quoting is JSON-compatible
        elif ":" in line:
            key, v = line.split(":", 1)
            v = v.strip()
            meta[key] = [] if v in ("", "[]") and key in ("marks", "uncertain") else (
                json.loads(v) if v.startswith('"') else v)
    return meta, body


def sheet_info(book, row, stem):
    st = ingest.sheet_state(book, row, stem)
    path = os.path.join(ingest.KB, book, "pages", stem + ".md")
    meta, body = read_page(path) if os.path.exists(path) else ({}, "")
    status = ("needs_proof" if body else "needs_rescan" if st["opus"] in ("needed", "FAILED")
              else "ocr_done" if st["haiku"] == "ok" else "new")
    issues = list(meta.get("uncertain", [])) + [UI["illegible"]] * body.count("[неразборчиво]")
    return dict(stem=stem, sheet=row["sheet"] or stem, kind=row["kind"] or meta.get("kind", ""), status=status,
                risk=st["score"], meta=meta, body=body, issues=issues, path=path)


CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--line:#d9d9de;--note:#7a5c00;--mark:#ffe08a;--chip:#f1f1f4}
@media (prefers-color-scheme:dark){:root{--bg:#18181b;--fg:#e8e8ea;--mut:#9a9aa2;--line:#3a3a40;--note:#e0c060;--mark:#6b5300;--chip:#26262b}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
a{color:inherit}header{padding:8px 16px;border-bottom:1px solid var(--line);display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.mut{color:var(--mut)}.chip{background:var(--chip);border-radius:4px;padding:1px 6px}
.wrap{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px}
@media (max-width:900px){.wrap{grid-template-columns:1fr}}
.scan img{width:100%;cursor:zoom-in;border:1px solid var(--line);background:#fff}.scan.full{overflow:auto;max-height:90vh}
.scan.full img{width:auto;max-width:none;cursor:zoom-out}
table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid var(--line);padding:3px 6px;vertical-align:top;text-align:left}
.note{color:var(--note);font-size:13px}.note::before{content:"‹";}.note::after{content:"›"}mark{background:var(--mark);color:inherit}
.issues li{margin:4px 0}code{font-size:13px;background:var(--chip);padding:1px 4px;border-radius:3px;word-break:break-all}
main{padding:0 16px 32px}
"""


def page_html(title, body, script=""):
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body>{body}<script>{script}</script></body></html>")


def sheet_html(book, meta, infos, i):
    s = infos[i]
    link = lambda j, label: (f'<a id="{"prev" if j < i else "next"}" href="{infos[j]["stem"]}.html">{label}</a>'
                             if 0 <= j < len(infos) else f'<span class="mut">{label}</span>')
    img = f"../../../SOURCES_JPEG/{book}/{s['stem']}.jpg"
    m = s["meta"]
    head = (f'<header><a href="../index.html">{UI["back"]}</a>{link(i - 1, UI["prev"])}{link(i + 1, UI["next"])}'
            f'<b>{html.escape(meta["code"])} · {UI["sheet"]} {html.escape(s["sheet"])}</b>'
            f'<span class="chip">{UI[s["status"]]}</span><span>{UI["risk"]}: {s["risk"]}</span>'
            f'<span class="mut">{UI["kind"]}: {html.escape(s["kind"])}</span></header>')
    right = [f'<p class="mut">{UI["scan"]}: <code>{html.escape(m.get("scan", ""))}</code><br>'
             f'{UI["engine"]}: {html.escape(m.get("ocr", "—"))}</p>']
    right.append(md_to_html(s["body"]) if s["body"] else f"<p><mark>{UI['no_text']}</mark></p>")
    for label, items in ((UI["issues"], s["issues"]), (UI["marks"], m.get("marks", []))):
        if items:
            right.append(f"<h3>{label} ({len(items)})</h3><ul class=\"issues\">"
                         + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
    rel = os.path.relpath(s["path"], os.path.dirname(ingest.KB)).replace(os.sep, "/")
    right.append(f'<p class="mut">{UI["edit"]} <code>{html.escape(rel)}</code></p>')
    body = (head + f'<div class="wrap"><div class="scan" onclick="this.classList.toggle(\'full\')">'
            f'<img src="{img}" alt="{UI["scan"]} {html.escape(s["sheet"])}"></div><div>{"".join(right)}</div></div>')
    keys = ("document.onkeydown=e=>{if(e.altKey||e.ctrlKey||e.metaKey)return;"
            "const a=document.getElementById(e.key=='ArrowLeft'?'prev':e.key=='ArrowRight'?'next':'');if(a)location=a.href}")
    return page_html(f"{meta['code']} · {UI['sheet']} {s['sheet']}", body, keys)


def build_viewer(out=None):
    out = out or os.path.join(ingest.KB, "viewer")
    books = sorted(b for b in os.listdir(ingest.KB) if os.path.exists(os.path.join(ingest.KB, b, "manifest.csv")))
    opts = "".join(f'<option value="{k}">{UI[k]}</option>' for k in STATUSES)
    parts = [f'<header><b>{UI["title"]}</b><label>{UI["status"]}: <select id="f"><option value="">{UI["all"]}</option>'
             f"{opts}</select></label></header><main>"]
    for b in books:
        meta, rows = ingest.load(os.path.join(ingest.KB, b))
        infos = [sheet_info(b, r, s) for r, s in rows]
        os.makedirs(os.path.join(out, b), exist_ok=True)
        for i, s in enumerate(infos):
            open(os.path.join(out, b, s["stem"] + ".html"), "w", encoding="utf-8").write(sheet_html(b, meta, infos, i))
        trs = "".join(f'<tr data-status="{s["status"]}"><td><a href="{b}/{s["stem"]}.html">{html.escape(s["sheet"])}</a></td>'
                      f'<td>{html.escape(s["kind"])}</td><td>{UI[s["status"]]}</td><td>{s["risk"]}</td>'
                      f'<td>{len(s["issues"]) or ""}</td></tr>' for s in infos)
        parts.append(f'<h2>{html.escape(meta["code"])} — {html.escape(meta.get("title", ""))}</h2><table><tr>'
                     + "".join(f"<th>{UI[k]}</th>" for k in ("sheet", "kind", "status", "risk", "issues"))
                     + f"</tr>{trs}</table>")
    script = ("document.getElementById('f').onchange=e=>document.querySelectorAll('tr[data-status]')"
              ".forEach(r=>r.hidden=!!e.target.value&&r.dataset.status!=e.target.value)")
    index = os.path.join(out, "index.html")
    open(index, "w", encoding="utf-8").write(page_html(UI["title"], "".join(parts) + "</main>", script))
    return index


if __name__ == "__main__":
    print(build_viewer())
