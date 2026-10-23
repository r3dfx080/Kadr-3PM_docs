import csv, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ingest, ocr_batch, review

PAGE = ('---\ndoc: М181 ИЭ\nsheet: "21"\nscan: s/1.tif\nkind: text\nsection: ""\nrev: ""\nmarks:\n  - "изм. 3"\n'
        'uncertain:\n  - "haiku: 27 — размыто"\nocr: x; hybrid ingest\n---\nтекст [неразборчиво]\n')


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old, ingest.KB = ingest.KB, self.tmp.name
        b = os.path.join(self.tmp.name, "BOOK")
        os.makedirs(os.path.join(b, "pages"))
        json.dump({"code": "М181 ИЭ", "title": "т"}, open(os.path.join(b, "book.json"), "w", encoding="utf-8"))
        open(os.path.join(b, "manifest.csv"), "w", encoding="utf-8").write("sheet,scan,orient,kind,note\n21,s/1.tif,P,text,\n")
        os.makedirs(os.path.join(b, "ocr", "haiku"))
        open(os.path.join(b, "ocr", "haiku", "l021.md"), "w").close()
        self.page = os.path.join(b, "pages", "l021.md")
        open(self.page, "w", encoding="utf-8").write(PAGE)
        self.db = review.ReviewDB()

    def tearDown(self):
        self.db.close()
        ingest.KB = self.old
        self.tmp.cleanup()

    def kinds(self, status="open"):
        return sorted((i["kind"], i["source"]) for i in self.db.issues("BOOK", "l021", status))

    def test_sync_creates_issues_and_status(self):
        review.sync(self.db)
        self.assertEqual(self.kinds(), [("handwritten", "score"), ("illegible", "haiku"), ("uncertain", "haiku")])
        self.assertEqual(self.db.page("BOOK", "l021")["status"], "needs_proof")

    def test_issue_dedup(self):
        a = self.db.add_issue("BOOK", "l021", "human_note", "human", "x")
        self.assertEqual(a, self.db.add_issue("BOOK", "l021", "human_note", "human", "x"))
        self.assertEqual(len(self.db.issues()), 1)

    def test_respelled_issue_keeps_id(self):
        a = self.db.add_issue("BOOK", "l021", "uncertain", "haiku", "«НІ03» — неясно")
        self.assertEqual(a, self.db.add_issue("BOOK", "l021", "uncertain", "haiku", "«Н103» — неясно"))
        self.assertEqual([i["detail"] for i in self.db.issues()], ["«Н103» — неясно"])

    def test_resolved_issue_not_reopened_by_sync(self):
        review.sync(self.db)
        for i in self.db.issues():
            self.db.resolve(i["id"], "ok")
        review.sync(self.db)
        self.assertEqual(self.kinds(), [])
        self.assertEqual(len(self.kinds("resolved")), 3)

    def test_sync_replaces_only_derived_issues(self):
        review.sync(self.db)
        ids = [i["id"] for i in self.db.issues()]
        review.sync(self.db)
        self.assertEqual(ids, [i["id"] for i in self.db.issues()])      # unchanged issues keep their id
        self.db.add_issue("BOOK", "l021", "human_note", "human", "проверить")
        open(self.page, "w", encoding="utf-8").write(PAGE.replace('marks:\n  - "изм. 3"\n', "marks: []\n"))
        review.sync(self.db)
        self.assertEqual(self.kinds(), [("human_note", "human"), ("illegible", "haiku"), ("uncertain", "haiku")])

    def test_hand_edited_or_proofread_page_is_protected(self):
        review.sync(self.db)
        self.assertTrue(review.may_write(self.db, "BOOK", "l021", self.page))
        open(self.page, "a", encoding="utf-8").write("правка\n")
        self.assertFalse(review.may_write(self.db, "BOOK", "l021", self.page))
        self.db.set_page("BOOK", "l021", status="proofread", text_hash=review.text_hash(self.page))
        self.assertFalse(review.may_write(self.db, "BOOK", "l021", self.page))
        review.sync(self.db)
        self.assertEqual(self.db.page("BOOK", "l021")["status"], "proofread")

    def test_mixed_i1_issue_from_raw_reply(self):
        raw = os.path.join(self.tmp.name, "BOOK", "ocr", "haiku", "_raw")
        os.makedirs(raw)
        open(os.path.join(raw, "l021.txt"), "w", encoding="utf-8").write(
            "model: x\nKIND: text\nSECTION:\nMARKS:\nUNCERTAIN:\nTEXT:\n6.II.1. длительностью I16 мкс и I6 мкс\n")
        review.sync(self.db)
        hits = [i["detail"] for i in self.db.issues() if "смешаны" in i["detail"]]
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].startswith("«I16»"))
        self.assertEqual(self.db.page("BOOK", "l021")["score"], 2)          # also raises the risk score

    def test_parse_suggest_optional(self):
        old = "KIND: text\nSECTION: 6\nMARKS:\nUNCERTAIN:\n- 27 — blur\nTEXT:\nИЩЛВ\n"
        self.assertEqual(ocr_batch.parse(old), ("text", "6", "", [], ["27 — blur"], "ИЩЛВ", []))
        new = old.replace("TEXT:", "SUGGEST:\n- ИЩЛВ → ИЦЛВ — одна буква\nTEXT:")
        self.assertEqual(ocr_batch.parse(new)[5:], ("ИЩЛВ", ["ИЩЛВ → ИЦЛВ — одна буква"]))

    def test_suggestion_issue_does_not_change_text(self):
        open(self.page, "w", encoding="utf-8").write(
            PAGE.replace("ocr:", 'suggest:\n  - "opus: ИЩЛВ → ИЦЛВ — одна буква"\nocr:').replace("текст", "ИЩЛВ"))
        review.sync(self.db)
        s = [i for i in self.db.issues() if i["kind"] == "suggestion"]
        self.assertEqual([(i["source"], i["detail"]) for i in s], [("opus", "ИЩЛВ → ИЦЛВ — одна буква")])
        self.assertIn("ИЩЛВ [неразборчиво]", open(self.page, encoding="utf-8").read())

    def test_abbreviation_index(self):
        open(self.page, "w", encoding="utf-8").write(PAGE.replace(
            "текст [неразборчиво]", "Нажать ВКУ и ВХОД, вход ВКУ, блок А104, КМ-1, ГОСТ II <!-- было «ЛПМ» -->"))
        open(os.path.join(self.tmp.name, "glossary.csv"), "w", encoding="utf-8").write(
            "abbr,expansion,scope,string_seen_in_3pm,note\nГОСТ,стандарт,103СЦ,,\n")
        review.sync(self.db)
        rows = list(csv.reader(open(os.path.join(self.tmp.name, "abbreviations.csv"), encoding="utf-8")))
        self.assertEqual(rows, [["abbr", "count", "pages", "likely_word", "glossary"],
                                ["ВКУ", "1", "ИЭ л.21", "", ""],
                                ["ВХОД", "1", "ИЭ л.21", "yes", ""],
                                ["ГОСТ", "1", "ИЭ л.21", "", "стандарт (103СЦ)"]])

    def test_export_csv(self):
        review.sync(self.db)
        review.export(self.db)
        rows = open(os.path.join(self.tmp.name, "review", "issues.csv"), encoding="utf-8").read().splitlines()
        self.assertEqual(rows[0].split(",")[:3], ["id", "book", "stem"])
        self.assertEqual(len(rows), 4)


if __name__ == "__main__":
    unittest.main()
