import copy
import json
import unittest

import helpers
from paper_sift import estimate
from paper_sift import spec as specmod

SPEC = specmod.validate(json.loads((helpers.ROOT / "tests" / "fixtures" / "spec.json").read_text()))


class EstimateTest(unittest.TestCase):
    def test_fixture_estimate(self):
        e = estimate.estimate(SPEC, have_s2_key=False)
        self.assertEqual(e["pool_size"], 100)
        self.assertEqual(e["fulltext_max"], 1 + 3 + 1 * 2)
        self.assertGreater(e["tokens_abstract"], 100 * estimate.ABSTRACT_TOKENS)
        self.assertLess(e["cost_usd"], 0.05)
        lo, hi = e["minutes"]["collect"]
        self.assertLess(lo, hi)

    def test_no_fulltext_questions(self):
        s = copy.deepcopy(SPEC)
        s["fulltext_questions"] = {}
        e = estimate.estimate(s, have_s2_key=True)
        self.assertEqual((e["fulltext_max"], e["tokens_fulltext"]), (0, 0))
