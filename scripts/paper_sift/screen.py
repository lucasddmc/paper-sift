"""Abstract stage: ask the spec's questions of every pool paper that has an abstract.

scores.jsonl is append-only. Each row holds the answers of one call plus a hash of each question's
text; `current` folds the rows and drops answers to questions edited since.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from .jev import ENDPOINT
from .net import HttpError, is_client_error
from .spec import question_hash

MAX_CONSECUTIVE_FAILURES = 20  # failed calls in a row (completion order): TypeSafe is likely down


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
    """Ask in parallel; every row goes to sink(row) as it arrives. Returns (ok, errors). A client error
    (4xx other than 429, auth included) or MAX_CONSECUTIVE_FAILURES failed calls in a row stop the stage:
    the queued calls are cancelled and the error is raised."""
    def one(item):
        paper, need = item
        state = {"area": spec["area"],
                 "paper": {"title": paper.get("title") or "", "abstract": paper["abstract"]}}
        try:
            out = ask(state, need)
        except HttpError as e:
            if is_client_error(e):  # every other call would be refused the same way
                raise
            return {"paperId": paper["paperId"], "error": f"HttpError {e.status}"}  # the status, never the body
        except Exception as e:  # recorded; the next run retries it
            return {"paperId": paper["paperId"], "error": repr(e)[:300]}
        return {"paperId": paper["paperId"], "answers": out["answers"], "tokens": out["tokens"],
                "model": out["model"], "hashes": {name: question_hash(q) for name, q in need.items()}}

    errors = streak = 0
    with ThreadPoolExecutor(workers) as executor:
        futures = {executor.submit(one, item): item for item in work}
        try:
            for i, future in enumerate(as_completed(futures), 1):
                row = future.result()
                sink(row)
                failed = "error" in row
                errors += failed
                streak = streak + 1 if failed else 0
                if streak >= MAX_CONSECUTIVE_FAILURES:
                    raise HttpError(0, b"too many consecutive failures; TypeSafe may be down", ENDPOINT)
                if i % every == 0:
                    log(f"scored {i}/{len(work)}")
        except BaseException:
            # Cancel remaining futures and re-raise
            for f in futures:
                f.cancel()
            raise
    return len(work) - errors, errors
