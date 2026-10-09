import unittest

import helpers  # noqa: F401
from paper_sift.policy import Expr, PolicyError

FACTS = ["topic", "survey", "didactic"]
R = {"topic": 0.8, "survey": 0.3, "didactic": 0.6, "importance": 0.5, "year": 2021, "citations": 120}


def ev(source, record=R, tau=0.5):
    return Expr(source, FACTS)(record, tau)


class PolicyTest(unittest.TestCase):
    def test_bare_fact_is_a_threshold(self):
        self.assertTrue(ev("topic"))
        self.assertFalse(ev("survey"))
        self.assertTrue(ev("survey", tau=0.3))

    def test_p_dot_fact_is_the_probability(self):
        self.assertAlmostEqual(ev("p.topic * importance"), 0.4)

    def test_boolean_logic(self):
        self.assertTrue(ev("topic and not survey"))
        self.assertTrue(ev("(survey or didactic) and topic"))
        self.assertFalse(ev("survey or not topic"))

    def test_comparisons_and_metadata(self):
        self.assertTrue(ev("year >= 2020 and citations > 100"))
        self.assertTrue(ev("0.5 < p.topic <= 0.8"))
        self.assertFalse(ev("p.topic > 0.9"))

    def test_missing_fact_counts_as_zero(self):
        self.assertFalse(ev("didactic", record={"topic": 0.9}))
        self.assertEqual(ev("p.didactic", record={}), 0.0)

    def test_division_by_zero_is_zero(self):
        self.assertEqual(ev("p.topic / citations", record={"topic": 0.9, "citations": 0}), 0.0)

    def test_constants(self):
        self.assertFalse(ev("False"))

    def test_rejects_unknown_names_and_code(self):
        for bad in ("relevance", "p.relevance", "__import__('os')", "topic.real", "[1]",
                    "topic if survey else didactic", "lambda: 1", "'text'", "topic ** 2"):
            with self.subTest(bad=bad), self.assertRaises(PolicyError):
                Expr(bad, FACTS)

    def test_syntax_error(self):
        with self.assertRaises(PolicyError):
            Expr("topic and", FACTS)
