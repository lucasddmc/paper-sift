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
        found, looked = poolmod.fill_abstracts(papers, lambda t: "Recovered." if t == "Paper a" else None,
                                               sleep=lambda s: None, log=lambda m: None)
        self.assertEqual((found, looked), (1, 2))
        self.assertEqual(papers[0]["abstract_source"], "openalex")
