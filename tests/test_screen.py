import unittest

import helpers  # noqa: F401
from paper_sift import screen
from paper_sift.net import AuthError
from paper_sift.spec import question_hash

Q = {"topic": {"instructions": "Is `paper` about X?", "true": "y", "false": "n"},
     "survey": {"instructions": "Is `paper` a survey?", "true": "y", "false": "n"}}
H = {name: question_hash(q) for name, q in Q.items()}
SPEC = {"area": "An area description long enough.", "questions": Q}


class ScreenTest(unittest.TestCase):
    def test_current_drops_edited_questions_and_errors(self):
        rows = [{"paperId": "a", "answers": {"topic": 0.9, "survey": 0.1},
                 "hashes": {"topic": H["topic"], "survey": "old"}, "tokens": 10, "model": "m"},
                {"paperId": "b", "error": "boom"}]
        self.assertEqual(screen.current(rows, Q), {"a": {"answers": {"topic": 0.9}, "tokens": 10, "model": "m"}})

    def test_pending_asks_only_what_is_missing(self):
        papers = [{"paperId": "a", "abstract": "x"}, {"paperId": "b", "abstract": None},
                  {"paperId": "c", "abstract": "y"}]
        work = screen.pending(papers, {"a": {"answers": {"topic": 0.9}}}, Q)
        self.assertEqual([(p["paperId"], sorted(need)) for p, need in work],
                         [("a", ["survey"]), ("c", ["survey", "topic"])])

    def test_score_sends_state_and_records_hashes(self):
        seen, rows = [], []

        def ask(state, questions):
            seen.append(state)
            return {"answers": {n: 0.7 for n in questions}, "tokens": 50, "model": "jev-1.13.0"}

        ok, errors = screen.score([({"paperId": "a", "title": "T", "abstract": "A"}, Q)], SPEC, ask,
                                  sink=rows.append, log=lambda m: None)
        self.assertEqual((ok, errors), (1, 0))
        self.assertEqual(seen[0], {"area": SPEC["area"], "paper": {"title": "T", "abstract": "A"}})
        self.assertEqual(rows[0]["hashes"], H)

    def test_failures_are_recorded_but_auth_errors_stop(self):
        rows = []

        def flaky(state, questions):
            raise RuntimeError("timeout")

        ok, errors = screen.score([({"paperId": "a", "abstract": "A"}, Q)], SPEC, flaky, sink=rows.append,
                                  log=lambda m: None)
        self.assertEqual((ok, errors), (0, 1))
        self.assertIn("timeout", rows[0]["error"])

        def denied(state, questions):
            raise AuthError(401, b"", "u")

        with self.assertRaises(AuthError):
            screen.score([({"paperId": "a", "abstract": "A"}, Q)], SPEC, denied, sink=rows.append,
                         log=lambda m: None)
