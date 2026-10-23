"""Static side-by-side viewer (spec §3 «Viewer», plan Task 7): scan JPEG on the left, page text and open
doubts on the right. Writes kb/viewer/index.html and kb/viewer/<book>/<stem>.html; no server, no external JS.

Usage: python -I -X utf8 kb/tools/viewer.py        (ingest.py and review.py also rebuild it)

Status, risk and open issues come from kb/review.sqlite (filled by `review.py sync`); read-only.
Served by serve.py, the same pages also edit text, resolve issues and mark sheets proofread.
"""
import html, json, os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
import ingest, review

UI = dict(title="Документация «Кадр-3ПМ»", sheet="Лист", kind="Тип", status="Статус", risk="Риск",
          issues="Замечания", engine="Распознано", scan="Скан", prev="← пред.", next="след. →",
          back="К списку", no_text="Текст ещё не распознан", all="Все", marks="Рукописные пометки",
          page_file="Файл страницы", edit_text="Править текст", save="Сохранить", do_proof="Вычитан",
          stats="Статистика", total="Всего", sheets="Листов", hot="из них с риском > 2",
          open_issues="Открытых замечаний", done_pct="Вычитано",
          resolve="отметить как исправленное", resolve_all="Отметить все как исправленные",
          sort="Сортировать: по убыванию, по возрастанию, по листам", unproof="Снять отметку «вычитан»",
          reopen="снять отметку — замечание снова открыто",resolved="исправлено", wontfix="не требует исправления", cancel="Отмена", source="Источник", goto="лист №", no_sheet="Нет такого листа",
          new="не распознан", ocr_done="распознан", needs_rescan="на перераспознавание",
          needs_proof="на вычитку", proofread="вычитан")
STATUSES = review.STATUSES
HOT_RISK = 2                                    # needs_proof sheets riskier than this show a red chip
chip = lambda s: (" hot" if s["status"] == "needs_proof" and s["risk"] != "" and s["risk"] > HOT_RISK
                 else " ok" if s["status"] == "proofread" else "")
ISSUE_WEIGHT = {"illegible": 3, "uncertain": 2, "handwritten": 1}     # ingest.score() weights; suggestions 0
risk_txt = lambda s: "" if s["risk"] == "" else f'{s["risk"]} ({s["score"]})'


def risk(status, issues, all_issues, score):
    """Risk now: the original score scaled by the share of issue weight (ingest.score() weights) still open,
    so it never exceeds the original and is 0 once all are resolved or the sheet is proofread. "" if not scored."""
    if score is None:
        return ""
    if status == "proofread":
        return 0
    w = lambda xs: sum(ISSUE_WEIGHT.get(i["kind"], 0) for i in xs if not re.search("штамп:|подпись:", i["detail"]))
    return round(score * w(issues) / w(all_issues)) if w(all_issues) else score


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
            meta[key] = [] if v in ("", "[]") and key in ("marks", "uncertain", "suggest") else (
                json.loads(v) if v.startswith('"') else v)
    return meta, body


def sheet_info(db, book, row, stem):
    path = os.path.join(ingest.KB, book, "pages", stem + ".md")
    p = db.page(book, stem) or {}
    body_ok = p.get("status") in ("needs_proof", "proofread") and os.path.exists(path)
    meta, body = read_page(path) if body_ok else ({}, "")
    kind, status, issues = row["kind"] or meta.get("kind", ""), p.get("status", "new"), db.issues(book, stem)
    all_issues = db.issues(book, stem, None)
    return dict(stem=stem, sheet=row["sheet"] or stem, kind=kind, status=status, score=p.get("score"),
                risk=risk(status, issues, all_issues, p.get("score")), meta=meta,
                body=body, issues=issues, all_issues=all_issues, path=path, hash=review.text_hash(path) if body_ok else "")


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
.index{display:grid;grid-template-columns:1fr auto;gap:16px}.stats{position:sticky;top:0;align-self:start;padding:0 16px}
.stats td{text-align:right}@media (max-width:900px){.index{grid-template-columns:1fr}.stats{position:static;order:-1}}
th.sort{cursor:pointer;user-select:none}th.sort::after{content:" ↕";color:var(--mut)}
th.sort[data-dir=desc]::after{content:" ↓";color:inherit}th.sort[data-dir=asc]::after{content:" ↑";color:inherit}
.chip.hot{background:#c62828;color:#fff}.chip.ok{background:#2e7d32;color:#fff}
.btn{border:1px solid var(--line);border-radius:6px;padding:2px 10px;text-decoration:none}a.btn:hover,button.btn:hover{border-color:var(--fg)}
#issues{position:fixed;top:0;right:0;height:100vh;width:min(440px,92vw);overflow:auto;padding:8px 16px;z-index:9;
  background:var(--bg);border-left:1px solid var(--line);box-shadow:-4px 0 16px #0003;transform:translateX(105%);transition:transform .2s}
#issues.open{transform:none}#issues h3{display:flex;justify-content:space-between;align-items:center}
button.btn{background:var(--bg);color:var(--fg);font:inherit;cursor:pointer}
#go,#f{font:inherit;padding:1px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
#go{width:6em}#f{cursor:pointer}
.done{opacity:.5;text-decoration:line-through}
textarea{width:100%;height:60vh;font:13px/1.4 ui-monospace,monospace;background:var(--bg);color:var(--fg)}
"""
# Edit controls save only when served by serve.py (http://127.0.0.1); opened as a file they say how to start it.
LIVE_JS = """
const S=document.getElementById('sheet').dataset,$=id=>document.getElementById(id);
const post=(u,d)=>!location.protocol.startsWith('http')?Promise.reject(new Error(
  'Сохранять можно только через сервер: python -I -X utf8 kb/tools/serve.py, затем http://127.0.0.1:8765/kb/viewer/index.html')):fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(Object.assign({book:S.book,stem:S.stem},d))}).then(async r=>{if(!r.ok)throw new Error(await r.text())});
// reload so risk and counts are current; #issues reopens the panel at the same scroll position
const reloadIss=()=>{try{sessionStorage.issTop=$('issues').scrollTop}catch(e){}history.replaceState(null,'','#issues');location.reload()};
document.querySelectorAll('input[data-id]').forEach(c=>c.onchange=()=>{c.disabled=true;
  post('/api/resolve',{id:+c.dataset.id}).then(reloadIss,e=>{c.checked=false;c.disabled=false;alert(e.message)})});
const fit=()=>{const h=document.querySelector('.scan img').offsetHeight;if(h>200)$('txt').style.height=h+'px'};
const editing=on=>{$('editor').hidden=!on;$('view').hidden=on;$('edit').hidden=on;if(on){fit();$('txt').focus()}};
if($('edit')){$('edit').onclick=()=>editing(true);$('cancel').onclick=()=>editing(false);addEventListener('resize',fit)}
if($('save'))$('save').onclick=()=>post('/api/save',{body:$('txt').value,hash:S.hash}).then(()=>location.reload(),e=>alert(e.message));
if($('resolve_all'))$('resolve_all').onclick=()=>confirm('Отметить все открытые замечания на этом листе как исправленные?')&&
  post('/api/resolve_all',{}).then(reloadIss,e=>alert(e.message));
document.querySelectorAll('input[data-reopen]').forEach(c=>c.onchange=()=>{c.disabled=true;
  post('/api/reopen',{id:+c.dataset.reopen}).then(reloadIss,e=>{c.checked=true;c.disabled=false;alert(e.message)})});
if($('unproof'))$('unproof').onclick=()=>post('/api/unproof',{}).then(()=>location.reload(),e=>alert(e.message));
if($('proof'))$('proof').onclick=()=>post('/api/proof',{}).then(()=>location.reload(),e=>alert(e.message));
"""


def page_html(title, body, script=""):
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body>{body}<script>{script}\n"
            # Back/Forward restores a stale copy from the browser's cache; pages are rebuilt after every change
            "addEventListener('pageshow',e=>{if(e.persisted)location.reload()})</script></body></html>")


def sheet_html(book, meta, infos, i):
    s = infos[i]
    link = lambda j, label: (f'<a id="{"prev" if j < i else "next"}" href="{infos[j]["stem"]}.html" class="btn">{label}</a>'
                             if 0 <= j < len(infos) else f'<span class="btn mut">{label}</span>')
    sheets = json.dumps({x["sheet"].lower(): x["stem"] for x in infos}, ensure_ascii=False)
    img = f"../../../SOURCES_JPEG/{book}/{s['stem']}.jpg"
    m = s["meta"]
    head = (f'<header><a href="../index.html">{UI["back"]}</a>{link(i - 1, UI["prev"])}{link(i + 1, UI["next"])}'
            f'<input id="go" size="5" placeholder="{UI["goto"]}" title="{UI["goto"]}: номер листа, Enter">'
            f'<b>{html.escape(meta["code"])} · {UI["sheet"]} {html.escape(s["sheet"])}</b>'
            f'<span class="chip{chip(s)}">{UI[s["status"]]}</span><span>{UI["risk"]}: {risk_txt(s)}</span>'
            f'<span class="mut">{UI["kind"]}: {html.escape(s["kind"])}</span>'
            + (f'<button id="edit" class="btn">{UI["edit_text"]}</button>'
               if s["hash"] else "") + "</header>")
    right = [f'<details class="mut"><summary>{UI["source"]}</summary>{UI["scan"]}: <code>{html.escape(m.get("scan", ""))}'
             f'</code><br>{UI["engine"]}: {html.escape(m.get("ocr", "—"))}<br>{UI["page_file"]}: <code>'
             f'{html.escape(os.path.relpath(s["path"], os.path.dirname(ingest.KB)).replace(os.sep, "/"))}</code></details>']
    right.append('<div id="view">' + (md_to_html(s["body"]) if s["body"] else f"<p><mark>{UI['no_text']}</mark></p>")
                 + "</div>")
    if s["hash"]:                                       # the header's edit button swaps #view for this
        right.append(f'<div id="editor" hidden><textarea id="txt" spellcheck="false">\n{html.escape(s["body"])}'
                     f'</textarea><p><button id="save" class="btn">{UI["save"]}</button> '
                     f'<button id="cancel" class="btn">{UI["cancel"]}</button></p></div>')
    panel = ""                                          # slides in from the right, opened by the header button
    if s["all_issues"]:                                 # open count in the title; resolved ones stay listed, greyed
        n = f'{UI["issues"]} ({len(s["issues"])})'
        head = head.replace("</header>", f'<button id="iss" class="btn">{n}</button></header>')
        panel = (f'<aside id="issues"><h3>{n} <button class="btn x" title="Esc">×</button></h3><ul class="issues">' + "".join(
            (f'<li><input type="checkbox" data-id="{i["id"]}" title="{UI["resolve"]}"> ' if i["status"] == "open" else
             f'<li class="done" title="{UI.get(i["status"], i["status"])}{html.escape(" — " + i["note"]) if i["note"] else ""}">'
             + ('<input type="checkbox" checked disabled> ' if s["status"] == "proofread" else
                f'<input type="checkbox" checked data-reopen="{i["id"]}" title="{UI["reopen"]}"> '))
            + f'<span class="mut">#{i["id"]} {i["kind"]}/{i["source"]}:</span> {inline(i["detail"])}</li>'
            for i in s["all_issues"]) + "</ul></aside>")
        if s["issues"]:
            panel = panel.replace("</h3>", f'</h3><p><button id="resolve_all" class="btn">{UI["resolve_all"]}</button></p>', 1)
    if m.get("marks"):
        right.append(f'<h3>{UI["marks"]} ({len(m["marks"])})</h3><ul class="issues">'
                     + "".join(f"<li>{inline(x)}</li>" for x in m["marks"]) + "</ul>")
    if s["status"] == "needs_proof":
        right.append(f'<p><button id="proof" class="btn">{UI["do_proof"]}</button></p>')
    elif s["status"] == "proofread":
        right.append(f'<p><button id="unproof" class="btn">{UI["unproof"]}</button></p>')
    body = (head + f'<div class="wrap" id="sheet" data-book="{book}" data-stem="{s["stem"]}" data-hash="{s["hash"]}">'
            f'<div class="scan" onclick="this.classList.toggle(\'full\')">'
            f'<img src="{img}" alt="{UI["scan"]} {html.escape(s["sheet"])}"></div><div>{"".join(right)}</div></div>{panel}')
    # arrows (or Ctrl+arrows, also from the go-to field) turn sheets; never from the text editor, where Ctrl+arrow jumps words
    keys = ("const P=document.getElementById('issues');if(P){document.getElementById('iss').onclick=()=>P.classList.toggle('open');"
            "P.querySelector('.x').onclick=()=>P.classList.remove('open');"
            "document.addEventListener('click',e=>{if(!P.contains(e.target)&&!e.target.closest('#iss'))P.classList.remove('open')});"
            "if(location.hash=='#issues'){P.classList.add('open');try{P.scrollTop=+sessionStorage.issTop||0}catch(e){}}}"
            "document.onkeydown=e=>{const t=e.target.tagName;if(e.key=='Escape'&&P)P.classList.remove('open');"
            "if(e.altKey||e.metaKey||t=='TEXTAREA'||(t=='INPUT'&&!e.ctrlKey))return;"
            "const a=document.getElementById(e.key=='ArrowLeft'?'prev':e.key=='ArrowRight'?'next':'');"
            "if(a){e.preventDefault();location=a.href}}")
    go = (f";const SHEETS={sheets},go=document.getElementById('go');go.oninput=()=>go.setCustomValidity('');"
          "go.onkeydown=e=>{if(e.key!='Enter')return;const v=go.value.trim().toLowerCase(),"
          "t=SHEETS[v]||SHEETS[v.replace(/^0+/,'')];if(t)location=t+'.html';"
          "else{go.setCustomValidity('"+UI["no_sheet"]+"');go.reportValidity()}};")
    return page_html(f"{meta['code']} · {UI['sheet']} {s['sheet']}", body, keys + go + LIVE_JS)


def stats_html(books):
    """Sidebar table: sheets per status, open issues and share proofread, per book and in total."""
    cols = {**books, UI["total"]: [s for infos in books.values() for s in infos]}
    row = lambda label, f: f"<tr><th>{label}</th>" + "".join(f"<td>{f(v)}</td>" for v in cols.values()) + "</tr>"
    pct = lambda v: f'{100 * sum(s["status"] == "proofread" for s in v) / len(v):.1f}%' if v else "—"
    return (f'<aside class="stats"><h2>{UI["stats"]}</h2><table><tr><th></th>'
            + "".join(f"<th>{html.escape(k)}</th>" for k in cols) + "</tr>"
            + row(UI["sheets"], len)
            + "".join(row(UI[k],
                          lambda v, k=k: sum(s["status"] == k for s in v) or "")
                      + (row(UI["hot"], lambda v: sum(chip(s) == " hot" for s in v) or "") if k == "needs_proof" else "")
                      for k in STATUSES)
            + row(UI["open_issues"], lambda v: sum(len(s["issues"]) for s in v))
            + row(UI["done_pct"], pct) + "</table></aside>")


def build_viewer(out=None):
    out = out or os.path.join(ingest.KB, "viewer")
    db = review.ReviewDB()
    opts = "".join(f'<option value="{k}">{UI[k]}</option>' for k in STATUSES)
    parts = [f'<header><b>{UI["title"]}</b><label>{UI["status"]}: <select id="f"><option value="">{UI["all"]}</option>'
             f"{opts}</select></label></header><div class=\"index\"><main>"]
    stats = {}                                          # short book code -> sheet infos, for the sidebar
    for b in ingest.books():
        meta, rows = ingest.load(os.path.join(ingest.KB, b))
        infos = stats[meta["code"].split()[-1]] = [sheet_info(db, b, r, s) for r, s in rows]
        os.makedirs(os.path.join(out, b), exist_ok=True)
        for i, s in enumerate(infos):
            open(os.path.join(out, b, s["stem"] + ".html"), "w", encoding="utf-8").write(sheet_html(b, meta, infos, i))
        trs = "".join(f'<tr data-status="{s["status"]}" data-i="{n}"><td><a href="{b}/{s["stem"]}.html" class="btn">{html.escape(s["sheet"])}</a></td>'
                      f'<td>{html.escape(s["kind"])}</td><td><span class="chip{chip(s)}">{UI[s["status"]]}</span></td>'
                      f'<td data-v="{s["risk"]}">{risk_txt(s)}</td>'
                      f'<td data-v="{len(s["issues"])}">{len(s["issues"]) or ""}</td></tr>' for n, s in enumerate(infos))
        parts.append(f'<h2>{html.escape(meta["code"])} — {html.escape(meta.get("title", ""))}</h2><table><tr>'
                     + "".join(f'<th class="sort" title="{UI["sort"]}">{UI[k]}</th>' if k in ("risk", "issues")
                               else f"<th>{UI[k]}</th>" for k in ("sheet", "kind", "status", "risk", "issues"))
                     + f"</tr>{trs}</table>")
    script = ("document.getElementById('f').onchange=e=>document.querySelectorAll('tr[data-status]')"
              ".forEach(r=>r.hidden=!!e.target.value&&r.dataset.status!=e.target.value);\n"
              # click: most first, again: least first, third time: sheet order. Sorts by the current number
              # (data-v, not the original in brackets); unscored sheets go last.
              "document.querySelectorAll('th.sort').forEach(th=>th.onclick=()=>{"
              "const t=th.closest('table'),c=th.cellIndex,rows=[...t.querySelectorAll('tr[data-status]')],"
              "d=th.dataset.dir==='desc'?'asc':th.dataset.dir==='asc'?'':'desc';"
              "t.querySelectorAll('th.sort').forEach(h=>delete h.dataset.dir);if(d)th.dataset.dir=d;"
              "const v=r=>{const x=r.cells[c].dataset.v;return x===''?null:+x};"
              "rows.sort((a,b)=>!d?a.dataset.i-b.dataset.i:v(a)===null?1:v(b)===null?-1:d==='desc'?v(b)-v(a):v(a)-v(b))"
              ".forEach(r=>t.appendChild(r))})")
    db.close()
    index = os.path.join(out, "index.html")
    open(index, "w", encoding="utf-8").write(page_html(UI["title"], "".join(parts) + "</main>" + stats_html(stats) + "</div>", script))
    return index


if __name__ == "__main__":
    print(build_viewer())
