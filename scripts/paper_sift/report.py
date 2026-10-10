"""report.md, reading-list.bib and scored.csv. Titles, metadata and scores only; never abstracts."""
import csv
import io
import re

from .jev import cost
from .pool import connectivity
from .ranking import label


def link(r):
    ids = r.get("externalIds") or {}
    if ids.get("ArXiv"):
        return f"https://arxiv.org/abs/{ids['ArXiv']}"
    if ids.get("DOI"):
        return f"https://doi.org/{ids['DOI']}"
    return f"https://www.semanticscholar.org/paper/{r['paperId']}"


def why(r, spec):
    """The facts that put a paper on the list."""
    tau = spec["tau"]
    parts = [f"{name} {r[name]:.2f}" for name in spec["fulltext_questions"] if name in r]
    parts += [label(spec, name) for name in spec["questions"] if name != "topic" and r.get(name, 0.0) >= tau]
    parts.append(f"importance {r.get('importance', 0.0):.2f}")
    return " · ".join(parts)


UNREAD = {"no_pdf": "no open PDF", "no_text": "no usable text", "error": "error"}


def _pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def render(spec, ctx):
    models = ", ".join(sorted(ctx["models"])) or spec["model"]
    s = ctx["stats"]
    read = sum(1 for v in ctx["fulltext"].values() if v.get("status") == "read")
    listed = sum(len(recs) for _, recs in ctx["sections"])
    funnel = [("candidates found", s["found"]), ("outside the year range", s["outside_years"]),
              (f"kept in the pool (ceiling {spec['pool_size']:,})", s["kept"]),
              ("with an abstract", ctx["with_abstract"]), ("scored by Jev", ctx["scored"]),
              (f"passed the gate (`{spec['policy']['gate']}`)", ctx["passed"]),
              ("selected for full text", len(ctx["selected"])), ("full text read", read),
              ("in the reading list", listed)]
    out = [f"# Reading list: {spec['slug']}", "", f"_{ctx['date']} · paper-sift · {models}_", "",
           "## Area", "", spec["area"], "", "## Funnel", "", "| stage | papers |", "|---|---:|"]
    out += [f"| {name} | {n:,} |" for name, n in funnel]
    out += ["", "## Reading list", ""]
    n = 0
    for title, recs in ctx["sections"]:
        out += [f"### {title}", ""]
        for r in recs:
            n += 1
            venue = f", {r['venue']}" if r.get("venue") else ""
            out += [f"{n}. **{r.get('title')}** ({r.get('year') or 'n.d.'}{venue}). [link]({link(r)})",
                    f"   {why(r, spec)} · found by {', '.join(r.get('via', []))}"]
        out.append("")
    out += ["## Seeds", ""] + [f"- seed{i}: {seed.get('title')}" for i, seed in enumerate(ctx["seeds"], 1)] + [""]
    seeds_unscreened = ctx.get("seeds_no_abstract") or []
    if ctx["no_pdf"] or ctx["no_abstract"] or seeds_unscreened:
        out += ["## Check by hand", ""]
        if seeds_unscreened:
            out += [f"- {p.get('title')} ({p.get('year') or 'n.d.'}): seed without an abstract (not screened). "
                    f"[link]({link(p)})" for p in seeds_unscreened]
            out.append("")
        if ctx["no_pdf"]:
            out += ["Selected for full text but not read (no open PDF, no usable text, or an error):", ""]
            out += [f"- {r.get('title')} ({r.get('year') or 'n.d.'}): "
                    f"{UNREAD.get(r.get('fulltext_status'), r.get('fulltext_status') or 'not read')}. [link]({link(r)})"
                    for r in ctx["no_pdf"]]
            out.append("")
        if ctx["no_abstract"]:
            out += ["Found by several sources but without an abstract, so never screened:", ""]
            out += [f"- {p.get('title')} ({p.get('year') or 'n.d.'}), {connectivity(p)} sources. [link]({link(p)})"
                    for p in ctx["no_abstract"]]
            out.append("")
    v = ctx.get("validation")
    if v and v["checked"]:
        out += ["## Blind check of the gate", "",
                f"A separate reader labeled {v['checked']} abstracts without seeing the scores. Agreement: "
                f"{_pct(v['agreement'])}. Relevant papers among the {v['rejected_checked']} rejected: "
                f"{len(v['missed'])}, so at most {_pct(v['miss_rate_upper95'])} of the rejected papers are likely "
                f"relevant (95% upper bound). Precision among the accepted: {_pct(v['precision'])}. The labels "
                "come from Claude, not from ground truth, and a sample this size catches gross failures only.", ""]
    tokens = ctx["tokens_abstract"] + ctx["tokens_fulltext"]
    out += ["## Cost", "", f"{ctx['tokens_abstract']:,} Jev tokens on abstracts and {ctx['tokens_fulltext']:,} on "
            f"full text: about US$ {cost(tokens):.2f} at the published price.", ""]
    return "\n".join(out)


def _bib_key(r, used):
    authors = r.get("authors") or []
    last = re.sub(r"[^a-z]", "", (authors[0].split()[-1] if authors else "anon").lower()) or "anon"
    words = (r.get("title") or "paper").split() or ["paper"]
    first = re.sub(r"[^a-z]", "", words[0].lower()) or "paper"
    base = f"{last}{r.get('year') or ''}{first}"
    key, n = base, 1
    while key in used:
        n += 1
        key = f"{base}{n}"
    used.add(key)
    return key


def bibtex(recs):
    used, entries = set(), []
    for r in recs:
        ids = r.get("externalIds") or {}
        title = (r.get("title") or "").replace("{", "").replace("}", "")
        fields = [("title", "{" + title + "}"), ("author", " and ".join(r.get("authors") or [])),
                  ("year", r.get("year")), ("howpublished", r.get("venue")), ("doi", ids.get("DOI")),
                  ("eprint", ids.get("ArXiv")), ("archiveprefix", "arXiv" if ids.get("ArXiv") else None),
                  ("url", link(r))]
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
        entries.append(f"@misc{{{_bib_key(r, used)},\n{body}\n}}")
    return "\n\n".join(entries) + "\n"


def scored_csv(recs, spec, passed_ids, fulltext):
    names = list(spec["questions"]) + list(spec["fulltext_questions"])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["paperId", "title", "year", "venue", "citations", "importance", "connectivity", "passed_gate",
                     "fulltext_status", *names, "link"])
    for r in recs:
        ft = fulltext.get(r["paperId"], {})
        answers = {**r, **ft.get("answers", {})}
        writer.writerow([r["paperId"], r.get("title"), r.get("year"), r.get("venue"), r.get("citations"),
                         r.get("importance"), connectivity(r), r["paperId"] in passed_ids, ft.get("status", ""),
                         *["" if answers.get(n) is None else round(answers[n], 4) for n in names], link(r)])
    return buf.getvalue()
