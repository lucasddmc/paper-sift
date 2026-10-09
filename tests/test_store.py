import tempfile
import unittest

import helpers  # noqa: F401
from paper_sift import store


class StoreTest(unittest.TestCase):
    def test_json_gzip_lines_and_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            s = store.Survey(d)
            s.write("pool", {"papers": [{"paperId": "a"}]})
            self.assertEqual(s.read("pool"), {"papers": [{"paperId": "a"}]})
            self.assertEqual(s.path("pool").read_bytes()[:2], b"\x1f\x8b")
            s.append_lines("scores", [{"paperId": "a"}])
            s.append_lines("scores", [{"paperId": "b"}])
            self.assertEqual([r["paperId"] for r in s.read_lines("scores")], ["a", "b"])
            self.assertIsNone(s.read("fulltext"))
            self.assertEqual(s.read("fulltext", {}), {})
            s.write("sample", {"papers": []})
            self.assertTrue(s.exists("sample"))
            s.write_text("report", "# hi\n")
            self.assertEqual(s.path("report").read_text(), "# hi\n")
