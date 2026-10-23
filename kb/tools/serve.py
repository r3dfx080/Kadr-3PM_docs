"""Local editable viewer: serves the project folder on http://127.0.0.1 so kb/viewer pages can save page text,
resolve issues and mark sheets proofread. Every change re-syncs kb/review.sqlite, rewrites kb/review/*.csv and
rebuilds the viewer, as the review.py CLI does. Threaded (browsers hold idle preconnect sockets), writes serialized.

Usage: python -I -X utf8 kb/tools/serve.py [--port 8765]
"""
import argparse, http.server, importlib, json, os, re, sys, threading

sys.path.insert(0, os.path.dirname(__file__))
import ingest, review, viewer

ROOT = os.path.dirname(ingest.KB)


def page_path(book, stem):
    path = os.path.join(ingest.KB, str(book), "pages", f"{stem}.md")
    if book not in ingest.books() or not re.fullmatch(r"\w+", str(stem)) or not os.path.exists(path):
        raise ValueError(f"нет страницы {book} {stem}")
    return path


def save(db, d):
    """Replace the page body (front-matter kept); refused if the file changed since the page was rendered."""
    path = page_path(d["book"], d["stem"])
    if review.text_hash(path) != d["hash"]:
        raise ValueError("Файл страницы изменён на диске — перезагрузите страницу (правка не сохранена)")
    if not (db.page(d["book"], d["stem"]) or {}).get("text_hash"):   # else sync would take the edit as machine text
        db.set_page(d["book"], d["stem"], text_hash=d["hash"])
    _, fm, _ = open(path, encoding="utf-8").read().split("---\n", 2)
    body = d["body"].replace("\r\n", "\n").rstrip("\n") + "\n"
    open(path, "w", encoding="utf-8").write(f"---\n{fm}---\n{body}")
    review.sync(db)                             # re-derives score issues; text_hash left alone marks it hand-edited


def resolve(db, d):
    if d["id"] not in [x["id"] for x in db.issues(d["book"], d["stem"])]:
        raise ValueError(f"нет открытого замечания #{d['id']} на этом листе")
    db.resolve(d["id"])


def resolve_all(db, d):
    page_path(d["book"], d["stem"])
    for x in db.issues(d["book"], d["stem"]):
        db.resolve(x["id"])


def proof(db, d):
    page_path(d["book"], d["stem"])
    review.proof(db, d["book"], d["stem"], os.environ.get("USERNAME", ""))


def unproof(db, d):
    page_path(d["book"], d["stem"])
    review.unproof(db, d["book"], d["stem"])


def reopen(db, d):
    review.reopen(db, d["book"], d["stem"], d["id"])


ACTIONS = {"/api/save": save, "/api/resolve": resolve, "/api/resolve_all": resolve_all, "/api/proof": proof,
           "/api/unproof": unproof, "/api/reopen": reopen}
LOCK = threading.Lock()                         # one writer to the DB, page files and viewer at a time


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # pages are rebuilt after every change
        super().end_headers()

    def reply(self, code, text=""):
        data = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        act = ACTIONS.get(self.path)
        if not act:
            return self.reply(404, "нет такого действия")
        if self.headers.get("Content-Type") != "application/json":   # forces a CORS preflight on cross-site posts
            return self.reply(415, "нужен application/json")
        d = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with LOCK:
            try:
                d = json.loads(d)
                db = review.ReviewDB()
                try:
                    act(db, d)
                    review.export(db)
                finally:
                    db.close()
            except (ValueError, KeyError, TypeError) as e:
                return self.reply(409, str(e))
            importlib.reload(viewer).build_viewer()     # a long-running server must not rebuild with stale page code
        self.reply(200, "ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    port = ap.parse_args().port
    viewer.build_viewer()
    url = f"http://127.0.0.1:{port}/kb/viewer/index.html"
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(url, "(Ctrl+C — остановить)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
