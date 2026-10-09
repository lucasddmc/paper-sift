import json
import unittest

import helpers  # noqa: F401
from paper_sift import pool as poolmod


def P(pid, year=2020, cites=0, abstract="An abstract.", title=None):
    return {"paperId": pid, "title": title or f"Paper {pid}", "year": year, "citationCount": cites,
            "abstract": abstract}


class FakeS2:
    def __init__(self):
        self.seeds = {"arXiv:1": P("S1", cites=500), "arXiv:2": P("S2", cites=50)}

    def batch(self, ids, fields=None):
        return [self.seeds.get(i) for i in ids]

    def edges(self, pid, relation):
        if relation == "citations":
            return [P("A", cites=10), P("B", year=2010, cites=3)] if pid == "S1" else [P("A", cites=10)]
        return [P("C", abstract=None)]

    def recommendations(self, ids):
        return [P("D", cites=1)]

    def search(self, query, limit=100):
        return [P("A", cites=10), P("E", year=2024)]


class RecordingS2(FakeS2):
    """FakeS2 that records each source it is asked for and fails on the one named `fail_on`."""

    def __init__(self, fail_on=None):
        super().__init__()
        self.calls, self.fail_on = [], fail_on

    def _asked(self, name):
        self.calls.append(name)
        if name == self.fail_on:
            raise RuntimeError(f"{name} failed")

    def batch(self, ids, fields=None):
        self._asked("batch")
        return super().batch(ids, fields)

    def edges(self, pid, relation):
        self._asked(f"{pid}:{relation}")
        return super().edges(pid, relation)

    def recommendations(self, ids):
        self._asked("recommendations")
        return super().recommendations(ids)

    def search(self, query, limit=100):
        self._asked("search")
        return super().search(query, limit)


def spec(**over):
    s = {"seeds": [{"id": "arXiv:1"}, {"id": "arXiv:2"}, {"id": "arXiv:404"}], "queries": ["q"], "years": None,
         "pool_size": 100,
         "sources": {"citations": True, "references": True, "recommendations": True, "search_per_query": 100}}
    s.update(over)
    return s


class PoolTest(unittest.TestCase):
    def test_add_merges_sources_and_abstract(self):
        pool = {}
        poolmod.add(pool, P("A", abstract=None), "query:1")
        poolmod.add(pool, P("A"), "cites:seed1")
        poolmod.add(pool, P("A"), "cites:seed1")
        self.assertEqual(pool["A"]["via"], ["query:1", "cites:seed1"])
        self.assertEqual(pool["A"]["abstract"], "An abstract.")

    def test_importance_is_a_within_year_mid_rank(self):
        papers = [P("a", cites=0), P("b", cites=10), P("c", cites=10), P("d", cites=50), P("old", year=1999, cites=1)]
        poolmod.set_importance(papers)
        self.assertEqual([p["importance"] for p in papers], [0.125, 0.5, 0.5, 0.875, 0.5])

    def test_collect_records_provenance_and_missing_seeds(self):
        logs = []
        out = poolmod.collect(spec(), FakeS2(), log=logs.append)
        by_id = {p["paperId"]: p for p in out["papers"]}
        self.assertEqual(out["missing_seeds"], ["arXiv:404"])
        self.assertEqual([s["paperId"] for s in out["seeds"]], ["S1", "S2"])
        self.assertEqual(sorted(by_id["A"]["via"]), ["cites:seed1", "cites:seed2", "query:1"])
        self.assertEqual(by_id["C"]["via"], ["cited-by:seed1", "cited-by:seed2"])
        self.assertEqual(out["stats"]["found"], 7)
        self.assertTrue(any("seed not found" in line for line in logs))

    def test_no_resolvable_seed_raises_no_seeds_error(self):
        s2 = FakeS2()
        s2.seeds = {}
        with self.assertRaises(poolmod.NoSeedsError):
            poolmod.collect(spec(), s2, log=lambda m: None)
        self.assertFalse(issubclass(poolmod.NoSeedsError, ValueError))  # the CLI catches it and nothing else

    def test_years_filter_spares_seeds(self):
        out = poolmod.collect(spec(years=[2015, 2030]), FakeS2(), log=lambda m: None)
        self.assertNotIn("B", {p["paperId"] for p in out["papers"]})
        self.assertEqual(out["stats"]["outside_years"], 1)

    def test_trim_keeps_seeds_then_best_connected(self):
        papers = [dict(P("s"), via=["seed"]), dict(P("x", cites=99), via=["query:1"]),
                  dict(P("y"), via=["cites:seed1", "query:1"]), dict(P("z"), via=["recommended"])]
        poolmod.set_importance(papers)
        kept, trimmed = poolmod.trim(papers, 2)
        self.assertEqual([p["paperId"] for p in kept], ["s", "y"])
        self.assertEqual([p["paperId"] for p in trimmed], ["x", "z"])

    def test_fill_abstracts_is_serial_and_counts(self):
        papers = [P("a", abstract=None), P("b"), P("c", abstract=None)]
        counts = poolmod.fill_abstracts(papers, lambda t: ("found", "Recovered.") if t == "Paper a" else ("none", None),
                                        sleep=lambda s: None, log=lambda m: None)
        self.assertEqual(counts, (1, 1, 0))  # found, none, failed
        self.assertEqual(papers[0]["abstract_source"], "openalex")

    def test_fill_abstracts_records_outcomes_and_retries_only_failures(self):
        papers = [P("a", abstract=None), P("b"), P("c", abstract=None), P("d", abstract=None)]
        outcome = {"Paper a": ("none", None), "Paper c": ("failed", None), "Paper d": ("found", "Recovered.")}
        asked, saves = [], []

        def lookup(title):
            asked.append(title)
            return outcome[title]

        counts = poolmod.fill_abstracts(papers, lookup, sleep=lambda s: None, log=lambda m: None, every=2,
                                        save=lambda: saves.append(len(asked)))
        self.assertEqual(counts, (1, 1, 1))
        self.assertEqual([p.get("abstract_lookup") for p in papers], ["none", None, "failed", "found"])
        self.assertEqual((papers[3]["abstract"], papers[3]["abstract_source"]), ("Recovered.", "openalex"))
        self.assertNotIn("abstract", {k for k, v in papers[2].items() if v})
        self.assertEqual(saves, [2])  # every 2 lookups
        asked.clear()
        outcome["Paper c"] = ("found", "Second try.")
        self.assertEqual(poolmod.fill_abstracts(papers, lookup, sleep=lambda s: None, log=lambda m: None),
                         (2, 1, 0))
        self.assertEqual(asked, ["Paper c"])  # found and none are not asked again

    def test_collect_saves_after_each_named_source(self):
        done = []
        poolmod.collect(spec(), FakeS2(), log=lambda m: None, save=lambda state: done.append(list(state["done"])))
        self.assertEqual(done[-1], ["seeds", "seed1:citations", "seed1:references", "seed2:citations",
                                    "seed2:references", "recommendations", "query1"])
        self.assertEqual([len(d) for d in done], [1, 2, 3, 4, 5, 6, 7])

    def test_collect_resumes_from_a_checkpoint(self):
        states = []
        with self.assertRaises(RuntimeError):
            poolmod.collect(spec(), RecordingS2(fail_on="S1:references"), log=lambda m: None,
                            save=lambda state: states.append(json.loads(json.dumps(state))))  # as stored on disk
        checkpoint = states[-1]
        self.assertEqual((checkpoint["done"], checkpoint["missing"]), (["seeds", "seed1:citations"], ["arXiv:404"]))
        again = RecordingS2()
        resumed = poolmod.collect(spec(), again, log=lambda m: None, checkpoint=checkpoint)
        self.assertEqual(again.calls, ["S1:references", "S2:citations", "S2:references", "recommendations", "search"])
        self.assertEqual(resumed, poolmod.collect(spec(), FakeS2(), log=lambda m: None))
