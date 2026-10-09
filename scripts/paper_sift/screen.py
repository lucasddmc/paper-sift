"""Abstract stage: ask the spec's questions of every pool paper that has an abstract.

scores.jsonl is append-only. Each row holds the answers of one call plus a hash of each question's
text; `current` folds the rows and drops answers to questions edited since.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from .net import AuthError
from .spec import question_hash


def current(rows, questions):
    hashes = {name: question_hash(q) for name, q in questions.items()}
    out = {}
    for row in rows:
        if "error" in row:
            continue
        entry = out.setdefault(row["paperId"], {"answers": {}, "tokens": 0, "model": None})
        entry["tokens"] += row.get("tokens", 0)
        entry["model"] = row.get("model") or entry["model"]
        for name, prob in row["answers"].items():
            if name in hashes and row.get("hashes", {}).get(name) == hashes[name]:
                entry["answers"][name] = prob
    return out


def pending(papers, done, questions):
    """[(paper, questions still to ask)] for papers that have an abstract."""
    work = []
    for paper in papers:
        if not paper.get("abstract"):
            continue
        have = done.get(paper["paperId"], {}).get("answers", {})
        need = {name: q for name, q in questions.items() if name not in have}
        if need:
            work.append((paper, need))
    return work


def score(work, spec, ask, *, sink, workers=16, log=print, every=100):
    """Ask in parallel; every row goes to sink(row) as it arrives. Returns (ok, errors)."""
    def one(item):
        paper, need = item
        state = {"area": spec["area"],
                 "paper": {"title": paper.get("title") or "", "abstract": paper["abstract"]}}
        try:
            out = ask(state, need)
        except AuthError:
            raise
        except Exception as e:  # recorded; the next run retries it
            return {"paperId": paper["paperId"], "error": repr(e)[:300]}
        return {"paperId": paper["paperId"], "answers": out["answers"], "tokens": out["tokens"],
                "model": out["model"], "hashes": {name: question_hash(q) for name, q in need.items()}}

    errors = 0
    with ThreadPoolExecutor(workers) as executor:
        futures = {executor.submit(one, item): item for item in work}
        try:
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    row = future.result()
                except AuthError:
                    # Cancel remaining futures and re-raise
                    for f in futures:
                        f.cancel()
                    raise
                sink(row)
                errors += "error" in row
                if i % every == 0:
                    log(f"scored {i}/{len(work)}")
        except AuthError:
            raise
    return len(work) - errors, errors
