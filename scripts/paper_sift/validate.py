"""Optional blind check of the abstract gate. Runs only after the user agrees to its cost."""
import math
import random


def draw(recs, passed_ids, *, n_rejected=30, n_accepted=15, seed=42):
    """Shuffled sample ids and the subset the gate rejected. Deterministic for a given seed."""
    rejected = sorted(r["paperId"] for r in recs if r["paperId"] not in passed_ids)
    accepted = sorted(r["paperId"] for r in recs if r["paperId"] in passed_ids)
    rng = random.Random(seed)
    pick_rejected = rng.sample(rejected, min(n_rejected, len(rejected)))
    pick_accepted = rng.sample(accepted, min(n_accepted, len(accepted)))
    order = pick_rejected + pick_accepted
    rng.shuffle(order)
    return order, set(pick_rejected)


def binomial_cdf(k, n, p):
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def upper_bound(k, n, alpha=0.05):
    """One-sided Clopper-Pearson upper bound for a rate, after k events in n trials."""
    if n == 0 or k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if binomial_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def compare(order, rejected_ids, labels):
    """labels: {paperId: "relevant" | "not_relevant"} from the blind labeler."""
    checked = [i for i in order if i in labels]
    rejected = [i for i in checked if i in rejected_ids]
    accepted = [i for i in checked if i not in rejected_ids]
    missed = [i for i in rejected if labels[i] == "relevant"]
    false_pass = [i for i in accepted if labels[i] != "relevant"]
    agree = len(checked) - len(missed) - len(false_pass)
    return {
        "checked": len(checked),
        "unlabeled": [i for i in order if i not in labels],
        "agreement": round(agree / len(checked), 4) if checked else None,
        "rejected_checked": len(rejected),
        "missed": missed,
        "miss_rate_upper95": round(upper_bound(len(missed), len(rejected)), 4) if rejected else None,
        "accepted_checked": len(accepted),
        "false_pass": false_pass,
        "precision": round(1 - len(false_pass) / len(accepted), 4) if accepted else None,
        "disagreements": (missed + false_pass)[:8],
    }
