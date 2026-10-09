import time
import unittest

import helpers  # noqa: F401
from paper_sift import pdftext


class PdfTextTest(unittest.TestCase):
    def test_cuts_at_first_heading_after_30_percent(self):
        text = ("Contents\nReferences\n" + "body " * 200 + "\nReferences\n[1] A.\n"
                + "Appendix " * 50 + "\nReferences\n[9] B.")
        body, cut = pdftext.cut_references(text)
        self.assertTrue(cut)
        self.assertEqual(body.count("body"), 200)
        self.assertNotIn("[1] A.", body)
        self.assertNotIn("Appendix", body)

    def test_no_heading_keeps_text(self):
        self.assertEqual(pdftext.cut_references("just text"), ("just text", False))

    def test_prepare_caps_length(self):
        body, cut, total = pdftext.prepare("x" * 100_000)
        self.assertEqual((len(body), cut, total), (pdftext.MAX_CHARS, False, 100_000))

    def test_cut_references_fast_on_many_newlines(self):
        text = "\n" * 200_000
        start = time.perf_counter()
        body, cut = pdftext.cut_references(text)
        elapsed = time.perf_counter() - start
        self.assertEqual((body, cut), (text, False))
        self.assertLess(elapsed, 1.0, f"cut_references took {elapsed:.2f}s, must be <1s")
