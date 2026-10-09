import threading
import time
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

    def test_rows_sink_immediately_while_earlier_items_block(self):
        """Verify rows reach sink as they complete, not in submission order."""
        rows = []
        blocker = threading.Event()

        def ask_with_block(state, questions):
            if state["paper"]["abstract"] == "BLOCK":
                blocker.wait()
            return {"answers": {n: 0.7 for n in questions}, "tokens": 10, "model": "m"}

        work = [
            ({"paperId": "block", "abstract": "BLOCK"}, Q),
            ({"paperId": "fast1", "abstract": "A"}, Q),
            ({"paperId": "fast2", "abstract": "B"}, Q),
        ]

        def run_score():
            screen.score(work, SPEC, ask_with_block, sink=rows.append, workers=4, log=lambda m: None)

        thread = threading.Thread(target=run_score)
        thread.start()

        # Wait for fast items to be sunk while blocker is still pending
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if len(rows) == 2:
                # fast1 and fast2 should have reached sink
                break
            time.sleep(0.01)

        self.assertEqual(len(rows), 2, "fast items should reach sink while blocker waits")
        blocker.set()
        thread.join(timeout=5.0)
        self.assertEqual(len(rows), 3, "all rows should eventually reach sink")

    def test_cache_key_round_trip_with_context(self):
        """Verify question hash and current() work correctly with _context."""
        Q2 = {name: dict(q, _context="ctx1") for name, q in Q.items()}
        H2 = {name: question_hash(q) for name, q in Q2.items()}
        papers = [{"paperId": "a", "abstract": "test"}]

        rows_list = []

        def ask(state, questions):
            return {"answers": {n: 0.9 for n in questions}, "tokens": 20, "model": "m"}

        ok, errors = screen.score([(papers[0], Q2)], SPEC, ask, sink=rows_list.append, log=lambda m: None)
        self.assertEqual((ok, errors), (1, 0))

        done = screen.current(rows_list, Q2)
        self.assertEqual(set(done["a"]["answers"].keys()), {"topic", "survey"})

        pending = screen.pending(papers, done, Q2)
        self.assertEqual(pending, [], "all questions should be answered")

        # Edit one question's instructions (changes hash)
        Q3 = {name: q for name, q in Q2.items()}
        Q3["topic"] = dict(Q2["topic"], instructions="Is `paper` about Y?", _context="ctx1")

        # current(rows, Q3) should drop the topic answer (hash mismatch)
        done_after_edit = screen.current(rows_list, Q3)
        self.assertNotIn("topic", done_after_edit["a"]["answers"], "edited question should be dropped")
        self.assertIn("survey", done_after_edit["a"]["answers"], "unchanged question should remain")

        # pending should find the edited question
        pending_after_edit = screen.pending(papers, done_after_edit, Q3)
        self.assertEqual(len(pending_after_edit), 1, "edited question should need re-asking")
        self.assertIn("topic", pending_after_edit[0][1])
