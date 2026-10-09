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

    def test_malformed_specs_raise_specerror(self):
        """Finding 1: Non-SpecError exceptions on malformed specs must be caught."""
        test_cases = [
            ([], "JSON list at top level"),
            (valid(questions={"topic": "plain string"}), "question as string"),
            (valid(policy={"gate": None, "priority": "p.topic * importance"}), "gate: null"),
            (valid(policy={"gate": "topic", "priority": "p.topic * importance", "fulltext": None}), "fulltext: null"),
            (valid(sources=None), "sources: null"),
            (valid(policy="x"), "policy: string"),
            (valid(model=None), "model: null"),
            (valid(model=1.13), "model: float"),
            (valid(model=""), "model: empty string"),
        ]
        for raw, desc in test_cases:
            with self.subTest(case=desc), self.assertRaises(specmod.SpecError):
                specmod.validate(raw)

    def test_load_with_invalid_utf8_raises_specerror(self):
        """Finding 1: Invalid UTF-8 in spec file must raise SpecError."""
        with tempfile.TemporaryDirectory() as d:
            spec_path = pathlib.Path(d) / "spec.json"
            spec_path.write_bytes(b"\x80\x81\x82")  # Invalid UTF-8
            with self.assertRaises(specmod.SpecError):
                specmod.load(spec_path)

    def test_validate_does_not_share_mutable_state_with_defaults(self):
        """Finding 2: Returned spec must be a deep copy, not sharing state with DEFAULTS."""
        s1 = specmod.validate(copy.deepcopy(FIXTURE))
        s1["sources"]["citations"] = False
        s1["policy"]["fulltext"]["top"] = 999

        # Fresh validate should not be affected
        s2 = specmod.validate(copy.deepcopy(FIXTURE))
        self.assertTrue(s2["sources"]["citations"])
        self.assertEqual(s2["policy"]["fulltext"]["top"], 3)

        # DEFAULTS should not be affected
        self.assertTrue(specmod.DEFAULTS["sources"]["citations"])
        self.assertEqual(specmod.DEFAULTS["policy"]["fulltext"]["top"], 30)

    def test_question_hash_includes_context(self):
        """Finding 3: question_hash must include area and model context."""
        s1 = specmod.validate(copy.deepcopy(FIXTURE))
        hash1 = specmod.question_hash(s1["questions"]["topic"])

        # Change area, hash should differ
        s2 = specmod.validate(valid(area="A completely different area for a different topic"))
        hash2 = specmod.question_hash(s2["questions"]["topic"])
        self.assertNotEqual(hash1, hash2, "Hash should differ when area changes")

        # Change model, hash should differ
        s3 = specmod.validate(valid(model="different-model"))
        hash3 = specmod.question_hash(s3["questions"]["topic"])
        self.assertNotEqual(hash1, hash3, "Hash should differ when model changes")

        # Same spec validated twice should give same hash
        s4 = specmod.validate(copy.deepcopy(FIXTURE))
        hash4 = specmod.question_hash(s4["questions"]["topic"])
        self.assertEqual(hash1, hash4, "Hash should be identical for same spec")
