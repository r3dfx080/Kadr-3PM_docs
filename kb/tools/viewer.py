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
          note="Заметка", note_ph="Заметки рецензента по листу…",
          add_span="＋ заметка", span_ph="Заметка к фрагменту…", delete="Удалить",
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
                risk=risk(status, issues, all_issues, p.get("score")), meta=meta, note=p.get("note") or "",
                spans=db.spans(book, stem) if body_ok else [],
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
#issues,#note{position:fixed;top:0;right:0;height:100vh;width:min(440px,92vw);overflow:auto;padding:8px 16px;z-index:9;
  background:var(--bg);border-left:1px solid var(--line);box-shadow:-4px 0 16px #0003;transform:translateX(105%);transition:transform .2s}
#issues.open,#note.open{transform:none}#issues h3,#note h3{display:flex;justify-content:space-between;align-items:center}
#note textarea{height:50vh}
button.btn{background:var(--bg);color:var(--fg);font:inherit;cursor:pointer}
#go,#f{font:inherit;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
#go{width:6em}#f{cursor:pointer}
input[type=checkbox]{accent-color:var(--note);width:15px;height:15px;cursor:pointer;vertical-align:-2px}
input[type=checkbox]:disabled{cursor:default}
.done{opacity:.5;text-decoration:line-through}
textarea{width:100%;height:60vh;font:13px/1.4 ui-monospace,monospace;background:var(--bg);color:var(--fg);
  border:1px solid var(--line);border-radius:6px;padding:8px 10px;resize:vertical}
textarea::placeholder,input::placeholder{color:var(--mut)}
textarea:focus,#go:focus,#f:focus{outline:none;border-color:var(--fg);box-shadow:0 0 0 2px var(--chip)}
mark.anno{background:var(--mark);color:inherit;cursor:pointer;border-bottom:2px solid var(--note)}
#pop{position:absolute;z-index:20;width:min(320px,80vw);padding:8px;background:var(--bg);border:1px solid var(--line);
  border-radius:8px;box-shadow:0 4px 16px #0004}#pop textarea{height:5em;font:inherit}
#pop .row{display:flex;gap:8px;margin-top:6px}#pop .frag{font-size:13px;color:var(--mut);max-height:3em;overflow:auto}
#addbtn{position:absolute;z-index:20}
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
if($('nsave'))$('nsave').onclick=()=>post('/api/note',{note:$('ntxt').value}).then(()=>location.reload(),e=>alert(e.message));
if($('unproof'))$('unproof').onclick=()=>post('/api/unproof',{}).then(()=>location.reload(),e=>alert(e.message));
if($('proof'))$('proof').onclick=()=>post('/api/proof',{}).then(()=>location.reload(),e=>alert(e.message));
"""
# Span notes: anchor each saved note to prefix+quote+suffix in #view, let the reviewer select text and attach one.
CTX = 24                                         # chars of context kept on each side to relocate a span after edits
SPAN_JS = """
const V=$('view'),SP=JSON.parse(S.spans||'[]');
// text nodes of #view plus the concatenated text and, per node, its start offset in that text
const model=()=>{const w=document.createTreeWalker(V,NodeFilter.SHOW_TEXT),nodes=[];let t='';
  for(let n;n=w.nextNode();){nodes.push({node:n,at:t.length});t+=n.nodeValue}return{nodes,text:t}};
const locate=(m,i)=>{for(let k=m.nodes.length-1;k>=0;k--)if(m.nodes[k].at<=i)      // char index -> (node, offset)
  return{node:m.nodes[k].node,offset:i-m.nodes[k].at};return{node:m.nodes[0].node,offset:0}};
// wrap [i,j) of the model text in <mark class=anno>, splitting text nodes at the edges; may span several nodes
const wrap=(m,i,j,sp)=>{const a=locate(m,i),b=locate(m,j),r=document.createRange();
  r.setStart(a.node,a.offset);r.setEnd(b.node,b.offset);
  const mk=document.createElement('mark');mk.className='anno';mk.dataset.id=sp.id;mk.title=sp.note;
  try{r.surroundContents(mk)}catch(e){                 // selection crosses element edges: wrap each text slice
    const parts=[];const w=document.createTreeWalker(V,NodeFilter.SHOW_TEXT);
    for(let n;n=w.nextNode();){if(r.intersectsNode(n))parts.push(n)}
    parts.forEach(n=>{const rr=document.createRange();rr.selectNodeContents(n);
      if(n===a.node)rr.setStart(n,a.offset);if(n===b.node)rr.setEnd(n,b.offset);
      const e2=mk.cloneNode();rr.surroundContents(e2)})}};
const anchor=()=>{SP.forEach(sp=>{const m=model();let i=m.text.indexOf(sp.prefix+sp.quote+sp.suffix);
  i=i<0?m.text.indexOf(sp.quote):i+sp.prefix.length;if(i>=0)wrap(m,i,i+sp.quote.length,sp)})};
if(V&&!V.hidden)anchor();
// popover: create/edit/delete a span note; add button appears by a fresh selection
const POP=$('pop'),ADD=$('addbtn');let cur=null;
const hide=()=>{POP.hidden=true;ADD.hidden=true};
const openPop=(x,y,sp,quote,pre,suf)=>{cur={sp,quote,pre,suf};ADD.hidden=true;
  $('ptxt').value=sp?sp.note:'';$('pfrag').textContent='«'+(sp?sp.quote:quote)+'»';
  $('pdel').hidden=!sp;POP.style.left=Math.min(x,innerWidth-POP.offsetWidth-8)+'px';POP.style.top=y+'px';
  POP.hidden=false;$('ptxt').focus()};
if(V)V.addEventListener('mouseup',e=>{if(V.hidden)return;setTimeout(()=>{   // let the selection settle
  if(e.target.closest('mark.anno'))return;const s=getSelection();
  if(s.isCollapsed||!V.contains(s.anchorNode)||!V.contains(s.focusNode)){if(POP.hidden)hide();return}
  const m=model(),r=s.getRangeAt(0),pre=document.createRange();
  pre.setStart(m.nodes[0].node,0);pre.setEnd(r.startContainer,r.startOffset);
  const i=pre.toString().length,q=r.toString();if(!q.trim())return;
  cur={quote:q,pre:m.text.slice(Math.max(0,i-"""+str(CTX)+"""),i),suf:m.text.slice(i+q.length,i+q.length+"""+str(CTX)+""")};
  const rect=r.getBoundingClientRect();ADD.style.left=(rect.left+scrollX)+'px';ADD.style.top=(rect.bottom+scrollY+4)+'px';
  ADD.hidden=false},0)});
if(ADD)ADD.onclick=()=>{const rect=ADD.getBoundingClientRect();openPop(rect.left+scrollX,rect.top+scrollY,null,cur.quote,cur.pre,cur.suf)};
if(V)V.addEventListener('click',e=>{const mk=e.target.closest('mark.anno');if(!mk)return;
  const sp=SP.find(x=>x.id==mk.dataset.id);if(!sp)return;const rect=mk.getBoundingClientRect();
  openPop(rect.left+scrollX,rect.bottom+scrollY+4,sp)});
if($('psave'))$('psave').onclick=()=>{const note=$('ptxt').value;
  const done=()=>location.reload(),err=e=>alert(e.message);
  if(cur.sp)post('/api/editspan',{id:cur.sp.id,note}).then(done,err);
  else post('/api/addspan',{quote:cur.quote,prefix:cur.pre,suffix:cur.suf,note}).then(done,err)};
if($('pdel'))$('pdel').onclick=()=>cur.sp&&confirm('Удалить заметку к фрагменту?')&&
  post('/api/delspan',{id:cur.sp.id}).then(()=>location.reload(),e=>alert(e.message));
if($('pclose'))$('pclose').onclick=hide;
document.addEventListener('click',e=>{if(!e.target.closest('#pop,#addbtn,mark.anno'))hide()},true);
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
            + (f'<button id="edit" class="btn" title="E">{UI["edit_text"]}</button>'
               if s["hash"] else "") + "</header>")
    right = [f'<details class="mut"><summary>{UI["source"]}</summary>{UI["scan"]}: <code>{html.escape(m.get("scan", ""))}'
             f'</code><br>{UI["engine"]}: {html.escape(m.get("ocr", "—"))}<br>{UI["page_file"]}: <code>'
             f'{html.escape(os.path.relpath(s["path"], os.path.dirname(ingest.KB)).replace(os.sep, "/"))}</code></details>']
    right.append('<div id="view">' + (md_to_html(s["body"]) if s["body"] else f"<p><mark>{UI['no_text']}</mark></p>")
                 + "</div>")
    if s["hash"]:                                       # the header's edit button swaps #view for this
        right.append(f'<div id="editor" hidden><textarea id="txt" spellcheck="false">\n{html.escape(s["body"])}'
                     f'</textarea><p><button id="save" class="btn" title="Ctrl+Enter">{UI["save"]}</button> '
                     f'<button id="cancel" class="btn">{UI["cancel"]}</button></p></div>')
    panel = ""                                          # slides in from the right, opened by the header button
    if s["all_issues"]:                                 # open count in the title; resolved ones stay listed, greyed
        n = f'{UI["issues"]} ({len(s["issues"])})'
        head = head.replace("</header>", f'<button id="iss" class="btn" title="I">{n}</button></header>')
        panel = (f'<aside id="issues"><h3>{n} <button class="btn x" title="Esc">×</button></h3><ul class="issues">' + "".join(
            (f'<li><input type="checkbox" data-id="{i["id"]}" title="{UI["resolve"]}"> ' if i["status"] == "open" else
             f'<li class="done" title="{UI.get(i["status"], i["status"])}{html.escape(" — " + i["note"]) if i["note"] else ""}">'
             + ('<input type="checkbox" checked disabled> ' if s["status"] == "proofread" else
                f'<input type="checkbox" checked data-reopen="{i["id"]}" title="{UI["reopen"]}"> '))
            + f'<span class="mut">#{i["id"]} {i["kind"]}/{i["source"]}:</span> {inline(i["detail"])}</li>'
            for i in s["all_issues"]) + "</ul></aside>")
        if s["issues"]:
            panel = panel.replace("</h3>", f'</h3><p><button id="resolve_all" class="btn">{UI["resolve_all"]}</button></p>', 1)
    # reviewer note: own slide-in panel; • on the button when a note is present
    nb = f'{UI["note"]}{" •" if s["note"] else ""}'
    head = head.replace("</header>", f'<button id="noteb" class="btn" title="N">{nb}</button></header>')
    panel += (f'<aside id="note"><h3>{UI["note"]} <button class="btn x" title="Esc">×</button></h3>'
              f'<textarea id="ntxt" spellcheck="false" placeholder="{UI["note_ph"]}">{html.escape(s["note"])}</textarea>'
              f'<p><button id="nsave" class="btn" title="Ctrl+Enter">{UI["save"]}</button></p></aside>')
    if m.get("marks"):
        right.append(f'<h3>{UI["marks"]} ({len(m["marks"])})</h3><ul class="issues">'
                     + "".join(f"<li>{inline(x)}</li>" for x in m["marks"]) + "</ul>")
    if s["status"] == "needs_proof":
        right.append(f'<p><button id="proof" class="btn">{UI["do_proof"]}</button></p>')
    elif s["status"] == "proofread":
        right.append(f'<p><button id="unproof" class="btn">{UI["unproof"]}</button></p>')
    spans = html.escape(json.dumps([{k: sp[k] for k in ("id", "quote", "prefix", "suffix", "note")}
                                    for sp in s["spans"]], ensure_ascii=False), quote=True)
    body = (head + f'<div class="wrap" id="sheet" data-book="{book}" data-stem="{s["stem"]}" data-hash="{s["hash"]}"'
            f' data-spans="{spans}">'
            f'<div class="scan" onclick="this.classList.toggle(\'full\')">'
            f'<img src="{img}" alt="{UI["scan"]} {html.escape(s["sheet"])}"></div><div>{"".join(right)}</div></div>{panel}'
            + (f'<button id="addbtn" class="btn" hidden>{UI["add_span"]}</button>'
               f'<div id="pop" hidden><div class="frag" id="pfrag"></div>'
               f'<textarea id="ptxt" spellcheck="false" placeholder="{UI["span_ph"]}"></textarea>'
               f'<div class="row"><button id="psave" class="btn" title="Ctrl+Enter">{UI["save"]}</button>'
               f'<button id="pdel" class="btn" hidden>{UI["delete"]}</button>'
               f'<button id="pclose" class="btn">{UI["cancel"]}</button></div></div>'
               if s["hash"] else ""))
    # arrows (or Ctrl+arrows, also from the go-to field) turn sheets; never from the text editor, where Ctrl+arrow jumps words
    # #issues (optional) and #note both slide in from the right; opening one closes the other, so they never overlap
    # hotkeys: Esc closes any open pop-up (panel, editor or span popover; the note's text isn't saved on close),
    # Ctrl+Enter saves the active pop-up (main text editor or note), E/I/N open editor / issues / note when not typing
    keys = ("const P=document.getElementById('issues'),N=document.getElementById('note'),PANES=[[P,'iss'],[N,'noteb']];"
            "const toggle=p=>PANES.forEach(([q])=>q&&q.classList.toggle('open',q===p&&!p.classList.contains('open')));"
            "PANES.forEach(([q,b])=>{if(!q)return;document.getElementById(b).onclick=()=>toggle(q);"
            "q.querySelector('.x').onclick=()=>q.classList.remove('open')});"
            "document.addEventListener('click',e=>PANES.forEach(([q,b])=>{"
            "if(q&&!q.contains(e.target)&&!e.target.closest('#'+b))q.classList.remove('open')}));"
            "if(P&&location.hash=='#issues'){P.classList.add('open');try{P.scrollTop=+sessionStorage.issTop||0}catch(e){}}"
            "const click=id=>{const b=document.getElementById(id);if(b)b.click()};"
            "document.onkeydown=e=>{const t=e.target.tagName,typing=t=='TEXTAREA'||t=='INPUT';"
            # Esc closes whatever pop-up is open; prefer the span popover, then the editor, then a slide-in panel
            "if(e.key=='Escape'){const pop=document.getElementById('pop'),ed=document.getElementById('editor');"
            "if(pop&&!pop.hidden)click('pclose');else if(ed&&!ed.hidden)click('cancel');"
            "else PANES.forEach(([q])=>q&&q.classList.remove('open'));e.target.blur&&e.target.blur();return}"
            # Ctrl+Enter saves the active pop-up: span popover, main text editor, or the note panel
            "if(e.key=='Enter'&&e.ctrlKey){const pop=document.getElementById('pop'),ed=document.getElementById('editor');"
            "if(pop&&!pop.hidden)click('psave');else if(ed&&!ed.hidden)click('save');"
            "else if(N&&N.classList.contains('open'))click('nsave');else return;e.preventDefault();return}"
            # E/I/N open editor / issues / note — only when not typing and no modifier is held
            "if(!typing&&!e.ctrlKey&&!e.altKey&&!e.metaKey){const k=e.key.toLowerCase();"
            "if(k=='e'||k=='у'){click('edit');e.preventDefault();return}"        # у = E on a Russian keyboard
            "if(k=='i'||k=='ш'){if(P)toggle(P);e.preventDefault();return}"       # ш = I
            "if(k=='n'||k=='т'){if(N)toggle(N);e.preventDefault();return}}"      # т = N
            "if(e.altKey||e.metaKey||typing)return;"
            "const a=document.getElementById(e.key=='ArrowLeft'?'prev':e.key=='ArrowRight'?'next':'');"
            "if(a){e.preventDefault();location=a.href}}")
    go = (f";const SHEETS={sheets},go=document.getElementById('go');go.oninput=()=>go.setCustomValidity('');"
          "go.onkeydown=e=>{if(e.key!='Enter')return;const v=go.value.trim().toLowerCase(),"
          "t=SHEETS[v]||SHEETS[v.replace(/^0+/,'')];if(t)location=t+'.html';"
          "else{go.setCustomValidity('"+UI["no_sheet"]+"');go.reportValidity()}};")
    return page_html(f"{meta['code']} · {UI['sheet']} {s['sheet']}", body, keys + go + LIVE_JS + SPAN_JS)


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
