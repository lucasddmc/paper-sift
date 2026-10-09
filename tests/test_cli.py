import contextlib
import io
import json
import pathlib
import shutil
import ssl
import tempfile
import unittest
import urllib.error
from unittest import mock

import helpers
import survey
from paper_sift import keys
from paper_sift.s2 import S2

REAL_GET_KEY = keys.get_key  # the CLI tests patch keys.get_key; tests that need real lookups use this one

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
        no_keys = mock.patch.object(keys, "get_key", return_value=None)  # never read the real key files
        no_keys.start()
        self.addCleanup(no_keys.stop)

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

    def test_malformed_key_file_exits_3_without_printing_it(self):
        with tempfile.TemporaryDirectory() as home:
            path = keys.key_path("typesafe", home)
            path.parent.mkdir(parents=True)
            path.write_text("tsk-secret\nsecond-line\n")
            with mock.patch.object(keys, "get_key",
                                   side_effect=lambda service, **kw: REAL_GET_KEY(service, env={}, home=home)):
                code, out = self.cli("doctor")
        self.assertEqual(code, 3, out)
        self.assertIn(f"The typesafe key at {path} is malformed: run python3 \"{survey.SETUP}\" typesafe again.", out)
        self.assertNotIn("tsk-secret", out)
        self.assertNotIn("second-line", out)

    def test_malformed_key_in_the_environment_exits_3_before_any_command(self):
        env = {"TYPESAFE_API_KEY": "tsk-secret\nx"}
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as home, \
                mock.patch.object(keys, "get_key",
                                  side_effect=lambda service, **kw: REAL_GET_KEY(service, env=env, home=home)), \
                contextlib.redirect_stdout(out):
            code = survey.main(["check", str(self.dir)])  # real deps: the key is read before the command runs
        self.assertEqual(code, 3, out.getvalue())
        self.assertIn("The typesafe key at TYPESAFE_API_KEY is malformed", out.getvalue())
        self.assertIn("unset", out.getvalue())
        self.assertNotIn("tsk-secret", out.getvalue())

    def test_collect_never_prints_a_rejected_header_value(self):
        def refuse_header(method, url, headers, body, timeout):
            raise ValueError(f"Invalid header value {headers['x-api-key'].encode()!r}")

        self.deps.s2 = S2(key="s2-secret\nx", transport=refuse_header, sleep=lambda s: None)
        code, out = self.cli("collect", str(self.dir))
        self.assertEqual(code, 4, out)
        self.assertNotIn("s2-secret", out)

    def test_doctor_prints_the_network_reason_instead_of_http_0(self):
        cert = urllib.error.URLError(ssl.SSLCertVerificationError(1, "certificate verify failed"))
        refused = urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        for error, expected in ((cert, "certificate verification failed (python.org builds: run Install "
                                       "Certificates.command)"),
                                (refused, "Connection refused")):
            with self.subTest(expected=expected):
                waits = []

                def offline(method, url, headers, body, timeout):
                    raise error

                self.deps.transport, self.deps.sleep = offline, waits.append
                with mock.patch.object(keys, "get_key",
                                       side_effect=lambda service, **kw: "tsk-secret" if service == "typesafe" else None):
                    code, out = self.cli("doctor")
                line = next(x for x in out.splitlines() if x.startswith("typesafe key:"))
                self.assertIn("typesafe key: present, not verified now (", line)
                self.assertIn(expected, line)
                self.assertNotIn("HTTP 0", out)
                self.assertNotIn("tsk-secret", out)
        self.assertEqual(waits, [2.0, 4.0])  # the refused connection was retried with the fake sleep

    def test_search_and_lookup_give_up_after_3_retries_on_rate_limits(self):
        for argv in (["search", "diffusion models"], ["lookup", "arXiv:2006.11239"]):
            with self.subTest(command=argv[0]):
                calls, waits = [], []

                def rate_limited(method, url, headers, body, timeout):
                    calls.append(url)
                    return 429, b'{"message": "Too Many Requests"}'

                self.deps.s2 = S2(transport=rate_limited, sleep=waits.append)  # default: 10 retries
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertEqual(len(calls), 4)
                self.assertEqual(waits, [2.0, 4.0, 8.0])
                self.assertIn("Semantic Scholar is rate-limiting requests without a key. Get a free key at "
                              "https://www.semanticscholar.org/product/api and save it with: "
                              f'python3 "{survey.SETUP}" s2', out)

    def test_rate_limit_with_a_key_does_not_ask_for_a_key(self):
        self.deps.s2 = S2(key="s2-key", transport=lambda *a: (429, b""), sleep=lambda s: None)
        code, out = self.cli("search", "diffusion")
        self.assertEqual(code, 4, out)
        self.assertNotIn("without a key", out)
        self.assertIn("429", out)

    def test_s2_refusal_blames_the_key_only_when_one_is_set(self):
        for key, code_wanted, wanted in ((None, 4, "Semantic Scholar refused the request (HTTP 403)."),
                                         ("s2-key", 3, "Semantic Scholar rejected the S2 key.")):
            with self.subTest(key=key):
                self.deps.s2 = S2(key=key, transport=lambda *a: (403, b""), sleep=lambda s: None)
                code, out = self.cli("search", "diffusion")
                self.assertEqual(code, code_wanted, out)
                self.assertIn(wanted, out)
                if key is None:
                    self.assertNotIn("S2 key", out)

    def test_doctor_reports_the_s2_api_state(self):
        offline = urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        for answer, wanted in (((200, b'[{"paperId": "x", "title": "Attention Is All You Need"}]'),
                                "s2 api: reachable"),
                               ((429, b""), "s2 api: rate-limited (429): a free key is strongly recommended"),
                               (offline, "s2 api: unreachable (URLError(ConnectionRefusedError(61, "
                                         "'Connection refused')))")):
            with self.subTest(wanted=wanted):
                calls = []

                def s2_only(method, url, headers, body, timeout):
                    calls.append(url)
                    if isinstance(answer, Exception):
                        raise answer
                    return answer

                self.deps.transport = s2_only
                code, out = self.cli("doctor")  # no keys: TypeSafe is not called
                self.assertIn(wanted, out.splitlines())
                self.assertEqual(len(calls), 1)  # one request, no retries
                self.assertTrue(calls[0].startswith("https://api.semanticscholar.org/"))
                self.assertIn("s2 key: not set (strongly recommended", out)
                self.assertIn(f'python3 "{survey.SETUP}" s2', out)

    def test_collect_with_unresolvable_seeds_exits_2(self):
        # Fake S2 that returns None for all batch calls
        class FakeBadS2(FakeS2):
            def batch(self, ids, fields=None):
                return [None] * len(ids)

        self.deps.s2 = FakeBadS2()
        d = str(self.dir)
        code, out = self.cli("collect", d)
        self.assertEqual(code, 2, out)
        self.assertIn("none of the seeds", out)
        self.assertIn("lookup", out)

    def test_validate_with_code_fence_wrapped_labels(self):
        d = str(self.dir)
        self.cli("check", d)
        self.cli("collect", d)
        self.cli("score", d)
        code, out = self.cli("sample", d)
        self.assertEqual(code, 0)

        # Write labels with code fence
        labels = {"labels": [{"id": p["id"], "label": "relevant", "reason": "test"}
                            for p in json.loads((self.dir / "validation" / "sample.json").read_text())["papers"]]}
        fenced = f"```json\n{json.dumps(labels)}\n```"
        (self.dir / "validation" / "labels.json").write_text(fenced)

        code, out = self.cli("validate", d)
        self.assertEqual(code, 0, out)
        self.assertIn("agreement", out)

    def test_validate_with_malformed_labels_exits_2(self):
        d = str(self.dir)
        self.cli("check", d)
        self.cli("collect", d)
        self.cli("score", d)
        self.cli("sample", d)

        # Write invalid JSON
        (self.dir / "validation" / "labels.json").write_text("not json")

        code, out = self.cli("validate", d)
        self.assertEqual(code, 2)
        self.assertIn("expected shape", out.lower())

    def test_reexec_detection_marker_present(self):
        # Test that _maybe_reexec returns 5 when marker is set and python is not None
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = survey._maybe_reexec(
                python=pathlib.Path("/fake/python"),
                argv=["survey.py", "fulltext", "/some/dir"],
                environ={"PAPER_SIFT_REEXEC": "1"},
                execv=lambda *a: None  # mock execv
            )
        self.assertEqual(result, 5)
        self.assertIn("pypdf still not available", out.getvalue())

    def test_reexec_calls_execv_once_marker_absent(self):
        # Test that _maybe_reexec calls execv once when marker is absent
        called = []
        def mock_execv(prog, args):
            called.append((prog, args))

        environ = {}
        result = survey._maybe_reexec(
            python=pathlib.Path("/fake/python"),
            argv=["survey.py", "fulltext", "/d"],
            environ=environ,
            execv=mock_execv
        )

        # execv should be called exactly once
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0], ("/fake/python", ["/fake/python", "survey.py", "fulltext", "/d"]))
        # environ should have marker set
        self.assertEqual(environ["PAPER_SIFT_REEXEC"], "1")

    def test_reexec_returns_none_when_python_is_none(self):
        # Test that _maybe_reexec returns None and doesn't call execv when python is None
        called = []
        def mock_execv(prog, args):
            called.append((prog, args))

        result = survey._maybe_reexec(
            python=None,
            argv=["survey.py", "fulltext", "/d"],
            environ={},
            execv=mock_execv
        )

        self.assertIsNone(result)
        self.assertEqual(len(called), 0)

    def test_validate_with_invalid_utf8_labels(self):
        d = str(self.dir)
        self.cli("check", d)
        self.cli("collect", d)
        self.cli("score", d)
        self.cli("sample", d)

        # Write invalid UTF-8 bytes
        (self.dir / "validation" / "labels.json").write_bytes(b"\xff\xfe")

        code, out = self.cli("validate", d)
        self.assertEqual(code, 2)
        self.assertIn("expected shape", out.lower())
