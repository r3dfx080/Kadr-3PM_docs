import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ingest, review, viewer
from viewer import UI, md_to_html


class MdTest(unittest.TestCase):
    def test_md_headings_paragraphs(self):
        self.assertEqual(md_to_html("## 6.11. А\n\nстрока 1\nстрока 2"), "<h2>6.11. А</h2>\n<p>строка 1<br>строка 2</p>")

    def test_md_table(self):
        self.assertIn("<tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr>", md_to_html("| a | b |\n|---|---|\n| 1 | 2 |"))

    def test_md_note_and_illegible(self):
        h = md_to_html("x [неразборчиво] y\n<!-- изм. 41: было «минус 27 В» -->")
        self.assertIn("<mark>[неразборчиво]</mark>", h)
        self.assertIn('<span class="note">изм. 41: было «минус 27 В»</span>', h)

    def test_md_escapes_html_keeps_br(self):
        self.assertIn("a &lt; b &amp; c ≥ d", md_to_html("a < b & c ≥ d"))
        self.assertIn("<td>x<br>y</td>", md_to_html("| h |\n|---|\n| x<br>y |"))
        self.assertNotIn("<script>", md_to_html("<script>alert(1)</script>"))


class ViewerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old, ingest.KB = ingest.KB, self.tmp.name
        b = os.path.join(self.tmp.name, "BOOK")
        os.makedirs(os.path.join(b, "pages"))
        json.dump({"code": "М181 ИЭ", "title": "т"}, open(os.path.join(b, "book.json"), "w", encoding="utf-8"))
        open(os.path.join(b, "manifest.csv"), "w", encoding="utf-8").write(
            "sheet,scan,orient,kind,note\n21,s/1.tif,P,text,\n21а,s/2.tif,P,,\n22,s/3.tif,P,,\n,s/4.tif,L,insert,\n")
        open(os.path.join(b, "pages", "l021.md"), "w", encoding="utf-8").write(
            '---\ndoc: М181 ИЭ\nsheet: "21"\nscan: s/1.tif\nkind: text\nsection: ""\nrev: ""\nmarks: []\n'
            'uncertain:\n  - "haiku: 27 — размыто"\n  - "opus: «Х3»"\nocr: x; hybrid ingest\n---\nтекст [неразборчиво]\n')
        db = review.ReviewDB()
        review.sync(db)
        db.close()
        self.index = viewer.build_viewer(os.path.join(self.tmp.name, "viewer"))
        self.read = lambda stem: open(os.path.join(self.tmp.name, "viewer", "BOOK", stem + ".html"), encoding="utf-8").read()

    def tearDown(self):
        ingest.KB = self.old
        self.tmp.cleanup()

    def test_viewer_prev_next_follows_manifest(self):
        h = self.read("l021a")
        self.assertIn('id="prev" href="l021.html"', h)
        self.assertIn('id="next" href="l022.html"', h)
        self.assertIn('id="next" href="l022_insert1.html"', self.read("l022"))

    def test_viewer_page_without_text(self):
        h = self.read("l022")
        self.assertIn(UI["no_text"], h)
        self.assertIn('src="../../../SOURCES_JPEG/BOOK/l022.jpg"', h)

    def test_viewer_index_counts_open_issues(self):
        self.assertIn("<td>3</td></tr>", open(self.index, encoding="utf-8").read())   # 2 uncertain + 1 illegible

    def test_index_stats(self):
        h = open(self.index, encoding="utf-8").read()
        self.assertIn(f'<th>{UI["sheets"]}</th><td>4</td><td>4</td>', h)          # ИЭ column, then total
        self.assertIn(f'<th>{UI["open_issues"]}</th><td>3</td><td>3</td>', h)
        self.assertIn(f'<th>{UI["done_pct"]}</th><td>0.0%</td><td>0.0%</td>', h)

    def test_resolved_issue_stays_listed_greyed(self):
        db = review.ReviewDB()
        first = db.issues("BOOK", "l021")[0]["id"]
        db.resolve(first, "ok")
        db.close()
        viewer.build_viewer(os.path.join(self.tmp.name, "viewer"))
        h = self.read("l021")
        self.assertIn(f'{UI["issues"]} (2)', h)                                     # title counts open ones
        self.assertEqual(h.count('<li class="done"'), 1)
        self.assertEqual(h.count("data-id="), 2)


if __name__ == "__main__":
    unittest.main()
