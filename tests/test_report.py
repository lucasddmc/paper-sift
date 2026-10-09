import json
import unittest

import helpers
from paper_sift import report
from paper_sift import spec as specmod

SPEC = specmod.validate(json.loads((helpers.ROOT / "tests" / "fixtures" / "spec.json").read_text()))
REC = {"paperId": "abc", "title": "Denoising {Diffusion} Models", "year": 2020, "venue": "NeurIPS",
       "via": ["seed", "query:1"], "externalIds": {"ArXiv": "2006.11239", "DOI": "10.1/x"},
       "authors": ["Jonathan Ho", "Pieter Abbeel"], "topic": 0.9, "survey": 0.1, "sub_sampling": 0.8,
       "sub_guidance": 0.1, "didactic": 0.85, "map": 0.2, "importance": 0.97, "citations": 9000}


def ctx(**over):
    c = {"stats": {"found": 10, "outside_years": 1, "kept": 9}, "with_abstract": 8, "scored": 8, "passed": 6,
         "selected": [REC], "fulltext": {"abc": {"status": "read"}}, "sections": [("Start here", [REC])],
         "no_pdf": [], "no_abstract": [], "seeds": [{"paperId": "abc", "title": "Denoising Diffusion Models"}],
         "validation": None, "tokens_abstract": 1_000_000, "tokens_fulltext": 0, "models": {"jev-1.13.0"},
         "date": "2026-10-09"}
    c.update(over)
    return c


class ReportTest(unittest.TestCase):
    def test_link_prefers_arxiv_then_doi(self):
        self.assertEqual(report.link(REC), "https://arxiv.org/abs/2006.11239")
        self.assertEqual(report.link({"paperId": "p", "externalIds": {"DOI": "10.1/x"}}), "https://doi.org/10.1/x")
        self.assertEqual(report.link({"paperId": "p"}), "https://www.semanticscholar.org/paper/p")

    def test_render_has_funnel_list_and_cost(self):
        text = report.render(SPEC, ctx())
        self.assertIn("| scored by Jev | 8 |", text)
        self.assertIn("### Start here", text)
        self.assertIn("didactic 0.85 · map 0.20 · Sampling · importance 0.97", text)
        self.assertIn("found by seed, query:1", text)
        self.assertIn("about US$ 0.04", text)
        self.assertNotIn("Check by hand", text)
        self.assertNotIn("Blind check", text)

    def test_render_optional_sections(self):
        v = {"checked": 45, "agreement": 0.91, "rejected_checked": 30, "missed": [], "miss_rate_upper95": 0.095,
             "precision": 0.8}
        text = report.render(SPEC, ctx(no_pdf=[REC], validation=v))
        self.assertIn("## Check by hand", text)
        self.assertIn("at most 10% of the rejected papers", text)

    def test_bibtex(self):
        bib = report.bibtex([REC, dict(REC, paperId="def")])
        self.assertIn("@misc{ho2020denoising,", bib)
        self.assertIn("@misc{ho2020denoising2,", bib)
        self.assertIn("title = {{Denoising Diffusion Models}}", bib)
        self.assertIn("author = {Jonathan Ho and Pieter Abbeel}", bib)
        self.assertIn("eprint = {2006.11239}", bib)

    def test_csv(self):
        text = report.scored_csv([REC], SPEC, {"abc"},
                                 {"abc": {"status": "read", "answers": {"didactic": 0.85, "map": 0.2}}})
        header, row = text.strip().splitlines()
        self.assertTrue(header.startswith("paperId,title,year,venue,citations,importance,connectivity,"
                                          "passed_gate,fulltext_status,topic"))
        self.assertIn("read", row)
        self.assertIn("True", row)
