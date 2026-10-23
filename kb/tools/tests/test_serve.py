import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import review, serve
from tests.test_review import ReviewTest


class ServeTest(unittest.TestCase):
    setUp, tearDown = ReviewTest.setUp, ReviewTest.tearDown

    def test_save_keeps_front_matter_and_resyncs(self):
        review.sync(self.db)
        h = review.text_hash(self.page)
        serve.save(self.db, dict(book="BOOK", stem="l021", hash=h, body="текст исправлен\r\n"))
        text = open(self.page, encoding="utf-8").read()
        self.assertTrue(text.startswith("---\ndoc: М181 ИЭ\n") and text.endswith("---\nтекст исправлен\n"))
        self.assertFalse(review.may_write(self.db, "BOOK", "l021", self.page))    # now hand-edited
        with self.assertRaises(ValueError):                                       # stale hash: refused
            serve.save(self.db, dict(book="BOOK", stem="l021", hash=h, body="x"))

    def test_resolve_and_proof(self):
        review.sync(self.db)
        with self.assertRaises(ValueError):
            serve.proof(self.db, dict(book="BOOK", stem="l021"))                   # open issues left
        for i in self.db.issues():
            serve.resolve(self.db, dict(book="BOOK", stem="l021", id=i["id"]))
        serve.proof(self.db, dict(book="BOOK", stem="l021"))
        self.assertEqual(self.db.page("BOOK", "l021")["status"], "proofread")

    def test_rejects_other_pages(self):
        for book, stem in (("BOOK", "../x"), ("..", "l021"), ("BOOK", "l999")):
            with self.assertRaises(ValueError):
                serve.page_path(book, stem)


if __name__ == "__main__":
    unittest.main()
