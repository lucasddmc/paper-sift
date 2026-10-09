"""Apply a spec's policy: gate, priority, full-text selection and the final reading list."""
from .policy import Expr
from .spec import subtopics


def records(papers, scores, questions):
    """Pool metadata plus current answers, for papers answered on every question. Abstracts stay out."""
    out = []
    for paper in papers:
        answers = scores.get(paper["paperId"], {}).get("answers", {})
        if not all(name in answers for name in questions):
            continue
        rec = {k: v for k, v in paper.items() if k != "abstract"}
        rec.update(answers)
        rec["citations"] = paper.get("citationCount") or 0
        out.append(rec)
    return out


def label(spec, name):
    q = spec["questions"].get(name) or spec["fulltext_questions"].get(name) or {}
    return q.get("label") or name.removeprefix("sub_").replace("_", " ")


class Policy:
    def __init__(self, spec):
        self.spec, self.tau = spec, spec["tau"]
        policy = spec["policy"]
        abstract = list(spec["questions"])
        everything = abstract + list(spec["fulltext_questions"])
        self.gate = Expr(policy["gate"], abstract)
        self.priority = Expr(policy["priority"], abstract)
        self.start_here = Expr(policy["start_here"], everything)
        self.final_rank = Expr(policy["final_rank"], everything)

    def passing(self, recs):
        return [r for r in recs if self.gate(r, self.tau)]

    def by_priority(self, recs):
        return sorted(recs, key=lambda r: (-float(self.priority(r, self.tau)), r["paperId"]))

    def for_fulltext(self, recs, seed_ids):
        """Seeds, the top papers by priority, and the top papers of each subtopic, without duplicates."""
        ft = self.spec["policy"]["fulltext"]
        passing = self.by_priority(self.passing(recs))
        chosen = {}
        if ft["include_seeds"]:
            for r in recs:
                if r["paperId"] in seed_ids:
                    chosen[r["paperId"]] = r
        for r in passing[:ft["top"]]:
            chosen.setdefault(r["paperId"], r)
        for sub in subtopics(self.spec):
            for r in [x for x in passing if x.get(sub, 0.0) >= self.tau][:ft["per_subtopic"]]:
                chosen.setdefault(r["paperId"], r)
        return self.by_priority(chosen.values())

    def reading_list(self, recs):
        """[(section, records)]: Start here, then subtopics taking turns, then the rest; final_top in all."""
        cap = self.spec["policy"]["final_top"]
        ordered = sorted(recs, key=lambda r: (-float(self.final_rank(r, self.tau)), r["paperId"]))
        used, sections = set(), []

        def room():
            return cap - len(used)

        start = [r for r in ordered if self.start_here(r, self.tau)][:max(room(), 0)]
        used.update(r["paperId"] for r in start)
        if start:
            sections.append(("Start here", start))
        subs = subtopics(self.spec)
        queues = {s: [r for r in ordered if r.get(s, 0.0) >= self.tau] for s in subs}
        picks = {s: [] for s in subs}
        moved = True
        while room() > 0 and moved:
            moved = False
            for s in subs:
                queue = queues[s]
                while queue and queue[0]["paperId"] in used:
                    queue.pop(0)
                if queue and room() > 0:
                    r = queue.pop(0)
                    picks[s].append(r)
                    used.add(r["paperId"])
                    moved = True
        sections += [(label(self.spec, s), picks[s]) for s in subs if picks[s]]
        rest = [r for r in ordered if r["paperId"] not in used][:max(room(), 0)]
        if rest:
            sections.append(("Also worth reading", rest))
        return sections
