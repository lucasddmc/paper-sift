import contextlib
import io
import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

import helpers
import survey
from paper_sift import keys

SEED = {"paperId": "S1", "title": "Denoising Diffusion Probabilistic Models", "year": 2020, "citationCount": 9000,
        "abstract": "We present diffusion probabilistic models for image synthesis.",
        "externalIds": {"ArXiv": "2006.11239"}}


def P(pid, title, abstract, year=2022, cites=10, arxiv=None):
    return {"paperId": pid, "title": title, "abstract": abstract, "year": year, "citationCount": cites,
            "externalIds": {"ArXiv": arxiv} if arxiv else {}}


CITING = [P("A", "A fast sampler for diffusion models", "A new sampler for diffusion models.", arxiv="2201.00001"),
          P("B", "Classifier-free guidance for diffusion", "Guidance improves diffusion samples.", cites=500),
          P("C", "Diffusion models: a survey and tutorial", "A survey of diffusion models.", cites=300),
          P("D", "Graph neural networks for molecules", "Message passing on molecular graphs."),
          P("E", "Untitled workshop note", None)]
REFS = [P("F", "Score matching and denoising", "Diffusion-like score matching for densities.", year=2011)]
RECS = [P("G", "Speeding up diffusion with a sampler", "Diffusion sampler distillation.")]
SEARCH = [P("H", "Protein folding with transformers", "Structure prediction from sequence.")]


class FakeS2:
    def batch(self, ids, fields=None):
        if fields and "openAccessPdf" in fields:
            return [{"paperId": i, "authors": [{"name": "Ada Lovelace"}],
                     "openAccessPdf": {"url": f"https://oa.test/{i}.pdf"}} for i in ids]
        return [dict(SEED) if i == "arXiv:2006.11239" else None for i in ids]

    def edges(self, pid, relation):
        return [dict(p) for p in (CITING if relation == "citations" else REFS)]

    def recommendations(self, ids):
        return [dict(p) for p in RECS]

    def search(self, query, limit=100, fields=None):
        return [dict(p) for p in SEARCH]


RULES = {"topic": "diffusion", "survey": "survey", "sub_sampling": "sampler", "sub_guidance": "guidance",
         "didactic": "tutorial", "map": "survey"}


def fake_ask(state, questions):
    paper = state["paper"]
    text = f"{paper['title']} {paper.get('abstract') or paper.get('text') or ''}".lower()
    return {"answers": {n: 0.9 if RULES[n] in text else 0.1 for n in questions}, "tokens": 100,
            "model": "jev-1.13.0"}


def fake_extract(path):
    words = "survey tutorial diffusion " if path.stem == "C" else "diffusion results "
    return words * 300 + "\nReferences\n[1] x"


def pdf_transport(method, url, headers, body, timeout):
    return 200, b"%PDF-1.4 fake"


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.dir = base / "paper-sift" / "2026-10-09-diffusion-models"
        self.dir.mkdir(parents=True)
        shutil.copy(helpers.ROOT / "tests" / "fixtures" / "spec.json", self.dir / "spec.json")
        self.deps = survey.Deps(s2=FakeS2(), ask=fake_ask, find_abstract=lambda title: None, extract=fake_extract,
                                transport=pdf_transport, sleep=lambda s: None, log=lambda m: None,
                                data_dir=base / "data")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = survey.main(list(argv), deps=self.deps)
        return code, out.getvalue()

    def test_full_pipeline(self):
        d = str(self.dir)
        code, out = self.cli("check", d)
        self.assertEqual(code, 0, out)
        self.assertIn("spec ok", out)
        self.assertIn("US$", self.cli("estimate", d)[1])
        code, out = self.cli("collect", d)
        self.assertEqual(code, 0, out)
        self.assertIn("kept 9 of ceiling 100", out)
        self.assertIn("pass the gate: 6", self.cli("score", d)[1])
        self.assertIn("asked now: 0 ok", self.cli("score", d)[1])
        code, out = self.cli("sample", d)
        self.assertEqual(code, 0, out)
        sample = json.loads((self.dir / "validation" / "sample.json").read_text())
        self.assertEqual(set(sample), {"area", "papers"})
        self.assertTrue(all(set(p) == {"id", "title", "abstract"} for p in sample["papers"]))
        labels = {"labels": [{"id": p["id"], "label": "relevant", "reason": "test"} for p in sample["papers"]]}
        (self.dir / "validation" / "labels.json").write_text(json.dumps(labels))
        code, out = self.cli("validate", d)
        self.assertEqual(code, 0, out)
        self.assertIn("agreement 75%", out)
        code, out = self.cli("fulltext", d)
        self.assertEqual(code, 0, out)
        self.assertIn("read 5", out)
        code, out = self.cli("report", d)
        self.assertEqual(code, 0, out)
        text = (self.dir / "report.md").read_text()
        self.assertIn("## Funnel", text)
        self.assertIn("### Start here", text)
        self.assertIn("Diffusion models: a survey and tutorial", text)
        self.assertNotIn("Message passing on molecular graphs", text)  # abstracts never reach the report
        code, out = self.cli("export", d)
        self.assertEqual(code, 0, out)
        self.assertIn("@misc", (self.dir / "reading-list.bib").read_text())
        self.assertIn("paperId,title", (self.dir / "scored.csv").read_text())

    def test_invalid_spec_exits_2(self):
        (self.dir / "spec.json").write_text("{}")
        code, out = self.cli("check", str(self.dir))
        self.assertEqual(code, 2)
        self.assertIn("spec error", out)

    def test_score_without_key_exits_3(self):
        self.cli("collect", str(self.dir))
        self.deps.ask = None
        code, out = self.cli("score", str(self.dir))
        self.assertEqual(code, 3)
        self.assertIn("setup_key.py", out)

    def test_doctor_without_key_shows_setup_command(self):
        with mock.patch.object(keys, "get_key", return_value=None):
            code, out = self.cli("doctor")
        self.assertIn("typesafe key: missing", out)
        self.assertIn('setup_key.py" typesafe', out)

    def test_doctor_never_prints_the_key(self):
        def jev_ok(method, url, headers, body, timeout):
            return 200, json.dumps({"model": "jev-1.13.0", "answers": {"probe": {"noul": 0.9}},
                                    "usage": {"input_tokens": 9}}).encode()
        self.deps.transport = jev_ok
        with mock.patch.object(keys, "get_key",
                               side_effect=lambda service, **kw: "tsk-secret" if service == "typesafe" else None):
            code, out = self.cli("doctor")
        self.assertIn("typesafe key: ok (jev-1.13.0)", out)
        self.assertNotIn("tsk-secret", out)
