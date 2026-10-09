import copy
import json
import pathlib
import tempfile
import unittest

import helpers
from paper_sift import spec as specmod

FIXTURE = json.loads((helpers.ROOT / "tests" / "fixtures" / "spec.json").read_text())


def valid(**changes):
    raw = copy.deepcopy(FIXTURE)
    raw.update(changes)
    return raw


class SpecTest(unittest.TestCase):
    def test_fixture_is_valid_and_gets_defaults(self):
        s = specmod.validate(copy.deepcopy(FIXTURE))
        self.assertEqual(s["model"], "jev-1.13.0")
        self.assertEqual(s["tau"], 0.5)
        self.assertEqual(s["sources"]["search_per_query"], 100)
        self.assertEqual(s["policy"]["fulltext"]["top"], 3)
        self.assertEqual(specmod.subtopics(s), ["sub_sampling", "sub_guidance"])

    def test_pool_size_bounds(self):
        for n in (99, 3001, "800", True):
            with self.subTest(n=n), self.assertRaises(specmod.SpecError):
                specmod.validate(valid(pool_size=n))
        self.assertEqual(specmod.validate(valid(pool_size=3000))["pool_size"], 3000)
        raw = valid()
        del raw["pool_size"]
        self.assertEqual(specmod.validate(raw)["pool_size"], 800)

    def test_gate_question_required(self):
        raw = valid()
        del raw["questions"]["topic"]
        raw["policy"]["gate"], raw["policy"]["priority"] = "survey", "p.survey"
        with self.assertRaisesRegex(specmod.SpecError, "topic"):
            specmod.validate(raw)

    def test_bad_question_names(self):
        for name in ("p", "importance", "Sub-x", "1abc"):
            raw = valid()
            raw["questions"][name] = {"instructions": "i", "true": "t", "false": "f"}
            with self.subTest(name=name), self.assertRaises(specmod.SpecError):
                specmod.validate(raw)

    def test_gate_cannot_use_fulltext_facts(self):
        raw = valid()
        raw["policy"]["gate"] = "topic and didactic"
        with self.assertRaisesRegex(specmod.SpecError, "policy.gate"):
            specmod.validate(raw)

    def test_names_cannot_repeat_across_stages(self):
        raw = valid()
        raw["fulltext_questions"]["survey"] = raw["questions"]["survey"]
        with self.assertRaises(specmod.SpecError):
            specmod.validate(raw)

    def test_question_hash_follows_the_text_only(self):
        q = {"instructions": "a", "true": "b", "false": "c"}
        self.assertEqual(specmod.question_hash(q), specmod.question_hash(dict(q, label="ignored")))
        self.assertNotEqual(specmod.question_hash(q), specmod.question_hash(dict(q, true="B")))

    def test_load_reports_unreadable_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(specmod.SpecError):
                specmod.load(pathlib.Path(d) / "missing.json")
