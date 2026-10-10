import copy
import json
import pathlib
import tempfile
import unittest

import helpers
from paper_sift import jev
from paper_sift import spec as specmod

FIXTURE = json.loads((helpers.ROOT / "tests" / "fixtures" / "spec.json").read_text())


def valid(**changes):
    raw = copy.deepcopy(FIXTURE)
    raw.update(changes)
    return raw


# Each level of spec.json with a key it does not define: (level, where the error points, the key, the keys
# the level allows, a change that adds the key to a valid spec).
UNKNOWN_KEY_CASES = [
    ("top level", "top level", "fulltext_chars",
     ("version", "recipe", "slug", "model", "tau", "area", "seeds", "queries", "sources", "years", "pool_size",
      "questions", "fulltext_questions", "policy"),
     lambda raw: raw.update(fulltext_chars=90000)),
    ("sources", "sources", "max_hops",
     ("citations", "references", "recommendations", "search_per_query"),
     lambda raw: raw.update(sources={"citations": True, "max_hops": 2})),
    ("policy", "policy", "fulltext_limit",
     ("gate", "priority", "fulltext", "start_here", "final_rank", "final_top"),
     lambda raw: raw["policy"].update(fulltext_limit=5)),
    ("policy.fulltext", "policy.fulltext", "chars",
     ("top", "per_subtopic", "include_seeds"),
     lambda raw: raw["policy"]["fulltext"].update(chars=1000)),
    ("seed", "seeds[0]", "doi",
     ("id", "title", "why"),
     lambda raw: raw["seeds"][0].update(doi="10.1/x")),
    ("abstract question", "questions.topic", "description",
     ("instructions", "true", "false", "label"),
     lambda raw: raw["questions"]["topic"].update(description="x")),
    ("full-text question", "fulltext_questions.map", "note",
     ("instructions", "true", "false", "label"),
     lambda raw: raw["fulltext_questions"]["map"].update(note="x")),
]


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

    def test_default_model_comes_from_the_jev_client(self):
        self.assertEqual(specmod.DEFAULTS["model"], jev.DEFAULT_MODEL)
        source = (helpers.ROOT / "scripts" / "paper_sift" / "spec.py").read_text()
        self.assertNotIn(jev.DEFAULT_MODEL, source)  # one literal, in jev.py
        self.assertNotIn("Finding", source)

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

    def test_unknown_keys_are_rejected_at_every_level(self):
        """A key the spec does not define used to be ignored without a word: the value never took effect."""
        for level, where, key, allowed, add in UNKNOWN_KEY_CASES:
            raw = valid()
            add(raw)
            with self.subTest(level=level):
                with self.assertRaises(specmod.SpecError) as caught:
                    specmod.validate(raw)
                named, listed = str(caught.exception).split(" (allowed: ")
                self.assertIn(f"{where}: unknown key '{key}'", named)
                self.assertEqual(set(listed.rstrip(")").split(", ")), set(allowed))

    def test_every_unknown_key_is_named(self):
        with self.assertRaises(specmod.SpecError) as caught:
            specmod.validate(valid(extra_one=1, extra_two=2))
        message = str(caught.exception)
        self.assertIn("unknown keys", message)
        self.assertIn("'extra_one'", message)
        self.assertIn("'extra_two'", message)

    def test_a_misspelled_key_is_named_before_anything_is_reported_missing(self):
        raw = valid()
        raw["quesitons"] = raw.pop("questions")
        with self.assertRaisesRegex(specmod.SpecError, "unknown key 'quesitons'"):
            specmod.validate(raw)
        raw = valid()
        topic = raw["questions"]["topic"]
        topic["instruction"] = topic.pop("instructions")
        with self.assertRaisesRegex(specmod.SpecError, "unknown key 'instruction'"):
            specmod.validate(raw)

    def test_a_validated_spec_validates_again(self):
        """validate adds _context to every question, and the validated spec is what the rest of the code holds."""
        once = specmod.validate(copy.deepcopy(FIXTURE))
        self.assertIn("_context", once["questions"]["topic"])
        self.assertEqual(specmod.validate(once), once)
