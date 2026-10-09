import pathlib
import tempfile
import unittest

import helpers  # noqa: F401
from paper_sift import fulltext
from paper_sift.net import HttpError
from paper_sift.spec import question_hash

SPEC = {"area": "Area text long enough for the test.", "fulltext_questions": {
    "didactic": {"instructions": "Could a newcomer learn from `paper`?", "true": "y", "false": "n"}}}
PDF = b"%PDF-1.4 fake"
LONG = "word " * 1000 + "\nReferences\n[1] x"


class FakeS2:
    def batch(self, ids, fields=None):
        return [{"paperId": i, "authors": [{"name": "Ada Lovelace"}],
                 "openAccessPdf": None if i == "closed" else {"url": f"https://oa.test/{i}.pdf"}} for i in ids]


def transport(method, url, headers, body, timeout):
    return (200, b"<html>") if url.endswith("broken.pdf") else (200, PDF)


class FulltextTest(unittest.TestCase):
    def test_lookup_prefers_arxiv(self):
        recs = [{"paperId": "a", "externalIds": {"ArXiv": "2006.11239"}}, {"paperId": "b"}, {"paperId": "closed"}]
        meta = fulltext.lookup(recs, FakeS2())
        self.assertEqual(meta["a"]["url"], "https://arxiv.org/pdf/2006.11239")
        self.assertEqual(meta["b"]["url"], "https://oa.test/b.pdf")
        self.assertIsNone(meta["closed"]["url"])
        self.assertEqual(meta["a"]["authors"], ["Ada Lovelace"])

    def test_download_rejects_non_pdf_and_uses_cache(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(fulltext.download("https://oa.test/broken.pdf", pathlib.Path(d) / "x.pdf",
                                                transport=transport, sleep=lambda s: None))
            path = fulltext.download("https://oa.test/ok.pdf", pathlib.Path(d) / "y.pdf", transport=transport,
                                     sleep=lambda s: None)
            self.assertEqual(path.read_bytes(), PDF)

            def offline(*args):
                raise AssertionError("should use the cache")

            self.assertEqual(fulltext.download("https://oa.test/ok.pdf", path, transport=offline), path)

    def test_ask_text_halves_on_error(self):
        sizes = []

        def ask(state, questions):
            sizes.append(len(state["paper"]["text"]))
            if len(sizes) == 1:
                raise HttpError(422, b"too long", "u")
            return {"answers": {"didactic": 0.8}, "tokens": 9, "model": "m"}

        out = fulltext.ask_text({"title": "T"}, "x" * 1000, SPEC, ask)
        self.assertEqual(sizes, [1000, 500])
        self.assertEqual(out["chars"], 500)

    def test_run_statuses_and_skips_done(self):
        recs = [{"paperId": "ok"}, {"paperId": "closed"}, {"paperId": "short"}, {"paperId": "done"}]
        hashes = {"didactic": question_hash(SPEC["fulltext_questions"]["didactic"])}
        done = {"done": {"status": "read", "hashes": hashes, "answers": {"didactic": 0.9}}}
        asked = []

        def ask(state, questions):
            asked.append(state["paper"]["title"])
            return {"answers": {"didactic": 0.7}, "tokens": 5, "model": "m"}

        with tempfile.TemporaryDirectory() as d:
            res = fulltext.run(recs, SPEC, FakeS2(), ask, d, done,
                               extract=lambda path: "tiny" if path.name == "short.pdf" else LONG,
                               transport=transport, sleep=lambda s: None, log=lambda m: None)
        self.assertEqual({k: v["status"] for k, v in res.items()},
                         {"ok": "read", "closed": "no_pdf", "short": "no_text", "done": "read"})
        self.assertTrue(res["ok"]["cut_references"])
        self.assertEqual(res["ok"]["authors"], ["Ada Lovelace"])
        self.assertEqual(len(asked), 1)
