"""Candidate pool: seeds, their citation neighborhood, recommendations and keyword search."""
import bisect
import time


class NoSeedsError(Exception):
    """None of the spec's seeds was found on Semantic Scholar."""


def add(pool, paper, via):
    """Insert or merge a paper; `via` records which source found it."""
    entry = pool.get(paper["paperId"])
    if entry is None:
        entry = pool[paper["paperId"]] = {**paper, "via": []}
    elif not entry.get("abstract") and paper.get("abstract"):
        entry["abstract"] = paper["abstract"]
    if via not in entry["via"]:
        entry["via"].append(via)
    return entry


def connectivity(paper):
    return sum(1 for v in paper.get("via", []) if v != "seed")


def set_importance(papers):
    """Citation percentile among papers of the same year (mid-rank, 0..1): recent papers are not
    buried under older, more-cited ones."""
    by_year = {}
    for p in papers:
        by_year.setdefault(p.get("year"), []).append(p.get("citationCount") or 0)
    for counts in by_year.values():
        counts.sort()
    for p in papers:
        counts = by_year[p.get("year")]
        c = p.get("citationCount") or 0
        less, upto = bisect.bisect_left(counts, c), bisect.bisect_right(counts, c)
        p["importance"] = round((less + 0.5 * (upto - less)) / len(counts), 4)


def in_years(paper, years):
    return years is None or paper.get("year") is None or years[0] <= paper["year"] <= years[1]


def trim(papers, size):
    """Keep every seed, then the best-connected papers (ties: importance). Returns (kept, trimmed)."""
    seeds = [p for p in papers if "seed" in p["via"]]
    rest = sorted((p for p in papers if "seed" not in p["via"]),
                  key=lambda p: (-connectivity(p), -p.get("importance", 0.0), p["paperId"]))
    room = max(size - len(seeds), 0)
    return seeds + rest[:room], rest[room:]


def collect(spec, s2, *, log=print):
    found = s2.batch([s["id"] for s in spec["seeds"]])
    pool, seeds, missing = {}, [], []
    for given, paper in zip(spec["seeds"], found):
        if not paper or not paper.get("paperId"):
            missing.append(given["id"])
            log(f"seed not found on Semantic Scholar: {given['id']}")
            continue
        seeds.append(paper)
        add(pool, paper, "seed")
    if not seeds:
        raise NoSeedsError("none of the seeds was found on Semantic Scholar")
    src = spec["sources"]
    for n, seed in enumerate(seeds, 1):
        name = (seed.get("title") or seed["paperId"])[:60]
        for relation, label, wanted in (("citations", "cites", src["citations"]),
                                        ("references", "cited-by", src["references"])):
            if wanted:
                got = s2.edges(seed["paperId"], relation)
                log(f"seed{n} {name}: {len(got)} {relation}")
                for p in got:
                    add(pool, p, f"{label}:seed{n}")
    if src["recommendations"]:
        got = s2.recommendations([s["paperId"] for s in seeds])
        log(f"recommendations: {len(got)}")
        for p in got:
            add(pool, p, "recommended")
    if src["search_per_query"]:
        for i, query in enumerate(spec["queries"], 1):
            got = s2.search(query, limit=src["search_per_query"])
            log(f"query{i} {query!r}: {len(got)}")
            for p in got:
                add(pool, p, f"query:{i}")
    candidates = [p for p in pool.values() if "seed" in p["via"] or in_years(p, spec["years"])]
    set_importance(candidates)
    kept, trimmed = trim(candidates, spec["pool_size"])
    return {"seeds": [{"paperId": s["paperId"], "title": s.get("title")} for s in seeds],
            "missing_seeds": missing,
            "stats": {"found": len(pool), "outside_years": len(pool) - len(candidates),
                      "candidates": len(candidates), "kept": len(kept), "trimmed": len(trimmed)},
            "papers": kept,
            "trimmed": [{"paperId": p["paperId"], "title": p.get("title"), "via": p["via"]} for p in trimmed]}


def fill_abstracts(papers, find_abstract, *, log=print, sleep=time.sleep, pause=0.25, every=50):
    """Serial OpenAlex lookups for papers without an abstract. Returns (found, looked_up)."""
    missing = [p for p in papers if not p.get("abstract")]
    found = 0
    for i, p in enumerate(missing, 1):
        text = find_abstract(p.get("title") or "")
        if text:
            p["abstract"], p["abstract_source"] = text, "openalex"
            found += 1
        sleep(pause)
        if i % every == 0:
            log(f"OpenAlex: {i}/{len(missing)} looked up, {found} found")
    return found, len(missing)
