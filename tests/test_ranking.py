import copy
import json
import unittest

import helpers
from paper_sift import spec as specmod
from paper_sift.ranking import Policy, records

SPEC = specmod.validate(json.loads((helpers.ROOT / "tests" / "fixtures" / "spec.json").read_text()))


def R(pid, topic, importance=0.5, **facts):
    rec = {"paperId": pid, "title": pid, "topic": topic, "survey": 0.0, "sub_sampling": 0.0,
           "sub_guidance": 0.0, "importance": importance}
    rec.update(facts)
    return rec


def titles(sections):
    return [(title, [r["paperId"] for r in recs]) for title, recs in sections]


class RankingTest(unittest.TestCase):
    def test_records_require_every_answer_and_drop_abstracts(self):
        papers = [{"paperId": "a", "abstract": "x", "citationCount": 7}, {"paperId": "b", "abstract": "y"}]
        scores = {"a": {"answers": {n: 0.6 for n in SPEC["questions"]}}, "b": {"answers": {"topic": 0.9}}}
        recs = records(papers, scores, SPEC["questions"])
        self.assertEqual([r["paperId"] for r in recs], ["a"])
        self.assertNotIn("abstract", recs[0])
        self.assertEqual(recs[0]["citations"], 7)

    def test_fulltext_selection(self):
        recs = [R("seed", 0.1), R("t1", 0.9, 0.9), R("t2", 0.9, 0.8), R("t3", 0.9, 0.7), R("t4", 0.9, 0.6),
                R("g", 0.6, 0.1, sub_guidance=0.8), R("off", 0.2, 1.0)]
        chosen = [r["paperId"] for r in Policy(SPEC).for_fulltext(recs, {"seed"})]
        self.assertEqual(sorted(chosen), ["g", "seed", "t1", "t2", "t3"])

    def test_reading_list_sections_and_cap(self):
        recs = [R("s", 0.9, survey=0.9, didactic=0.95), R("m", 0.9, map=0.8, didactic=0.6),
                R("a", 0.9, sub_sampling=0.9, didactic=0.9), R("b", 0.9, sub_sampling=0.9, didactic=0.8),
                R("c", 0.9, sub_guidance=0.9, didactic=0.7), R("d", 0.9, didactic=0.5), R("e", 0.9, didactic=0.4)]
        self.assertEqual(titles(Policy(SPEC).reading_list(recs)),
                         [("Start here", ["s", "m"]), ("Sampling", ["a", "b"]), ("Guidance and conditioning", ["c"])])
        wider = copy.deepcopy(SPEC)
        wider["policy"]["final_top"] = 7
        self.assertEqual(titles(Policy(wider).reading_list(recs))[-1], ("Also worth reading", ["d", "e"]))
