import unittest

import helpers  # noqa: F401
from paper_sift import validate


class ValidateTest(unittest.TestCase):
    def test_draw_is_deterministic_and_sized(self):
        recs = [{"paperId": f"p{i:03}"} for i in range(100)]
        passed = {f"p{i:03}" for i in range(20)}
        a = validate.draw(recs, passed)
        self.assertEqual(a, validate.draw(list(reversed(recs)), passed))
        order, rejected = a
        self.assertEqual((len(order), len(rejected)), (45, 30))
        self.assertTrue(rejected.isdisjoint(passed))

    def test_draw_with_small_groups(self):
        order, rejected = validate.draw([{"paperId": "a"}, {"paperId": "b"}], {"a"})
        self.assertEqual(sorted(order), ["a", "b"])
        self.assertEqual(rejected, {"b"})

    def test_upper_bound(self):
        self.assertAlmostEqual(validate.upper_bound(0, 30), 1 - 0.05 ** (1 / 30), places=6)
        self.assertGreater(validate.upper_bound(2, 30), validate.upper_bound(1, 30))
        self.assertEqual(validate.upper_bound(0, 0), 1.0)

    def test_compare(self):
        order = ["r1", "r2", "a1", "a2", "r3"]
        labels = {"r1": "relevant", "r2": "not_relevant", "a1": "relevant", "a2": "not_relevant"}
        out = validate.compare(order, {"r1", "r2", "r3"}, labels)
        self.assertEqual(out["missed"], ["r1"])
        self.assertEqual(out["false_pass"], ["a2"])
        self.assertEqual(out["unlabeled"], ["r3"])
        self.assertEqual(out["agreement"], 0.5)
        self.assertEqual(out["precision"], 0.5)
        self.assertEqual(out["disagreements"], ["r1", "a2"])
