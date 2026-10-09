#!/usr/bin/env python3
"""paper-sift command line. The /paper-sift:survey skill runs these steps; each prints a short summary
with titles, metadata and scores, never abstracts or paper text.

  survey.py doctor [--data-dir DIR]        check Python, keys and PDF support
  survey.py search "QUERY" [--limit N]     papers matching a query, with IDs (to pick seeds)
  survey.py lookup ID [ID ...]             resolve arXiv:/DOI:/S2 IDs
  survey.py check DIR                      validate DIR/spec.json
  survey.py estimate DIR                   rough cost and time
  survey.py collect DIR [--fresh]          build the pool
  survey.py score DIR                      abstract stage (incremental)
  survey.py sample DIR                     write the blind-check sample
  survey.py validate DIR                   compare the blind labels with the gate
  survey.py fulltext DIR [--data-dir DIR]  full-text stage (incremental)
  survey.py report DIR                     write report.md
  survey.py export DIR                     write reading-list.bib and scored.csv
"""
import argparse
import datetime
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from paper_sift import deps as depsmod  # noqa: E402
from paper_sift import estimate as estimatemod  # noqa: E402
from paper_sift import fulltext, jev, keys, openalex, pool, report, screen, store, validate  # noqa: E402
from paper_sift.net import AuthError, HttpError  # noqa: E402
from paper_sift.pdftext import extract as pdf_extract  # noqa: E402
from paper_sift.ranking import Policy, records  # noqa: E402
from paper_sift.s2 import S2  # noqa: E402
from paper_sift.spec import SpecError, load  # noqa: E402

SETUP = pathlib.Path(__file__).resolve().parent / "setup_key.py"
SHOW_FIELDS = "paperId,title,year,externalIds,citationCount"


class Deps:
    """External services; tests replace them with fakes."""

    def __init__(self, s2=None, ask=None, find_abstract=None, extract=None, transport=None, sleep=time.sleep,
                 log=print, data_dir=None):
        self.s2, self.ask, self.find_abstract, self.extract = s2, ask, find_abstract, extract
        self.transport, self.sleep, self.log, self.data_dir = transport, sleep, log, data_dir


def real_deps(spec=None, data_dir=None):
    key = keys.get_key("typesafe")
    ask = None
    if key and spec:
        def ask(state, questions):
            return jev.ask(state, questions, key=key, model=spec["model"])
    return Deps(s2=S2(key=keys.get_key("s2")), ask=ask, find_abstract=openalex.find_abstract,
                extract=pdf_extract, data_dir=depsmod.data_dir(data_dir))


def key_problem(rejected=False):
    print("TypeSafe rejected the key." if rejected else "TypeSafe key missing.")
    print("Ask the user to run this in their own terminal (not in the chat), then try again:")
    print(f'  python3 "{SETUP}" typesafe')
    return 3


def malformed_key(e):
    """A key with a line break, space or non-ASCII character: say where it is, never what it is."""
    print(f'The {e.service} key at {e.source} is malformed: run python3 "{SETUP}" {e.service} again.')
    var = keys.SERVICES[e.service][0]
    if e.source == var:
        print(f"{var} is set in the environment and overrides the saved key: unset it as well.")
    return 3


def show(papers):
    for p in papers:
        ids = p.get("externalIds") or {}
        alt = f"arXiv:{ids['ArXiv']}" if ids.get("ArXiv") else (f"DOI:{ids['DOI']}" if ids.get("DOI") else "")
        print(f"{p['paperId']} | {alt:24} | {p.get('year') or '----'} | {p.get('citationCount') or 0:>6} cit | "
              f"{(p.get('title') or '')[:100]}")


def scored_records(survey, spec):
    data = survey.read("pool")
    if data is None:
        raise SpecError("no pool yet: run collect first")
    done = screen.current(survey.read_lines("scores"), spec["questions"])
    return data, done, records(data["papers"], done, spec["questions"])


def cmd_doctor(args, deps):
    ok = sys.version_info >= (3, 9)
    print(f"python: {sys.version.split()[0]} ({'ok' if ok else 'too old: paper-sift needs 3.9+'})")
    key = keys.get_key("typesafe")
    if not key:
        print("typesafe key: missing")
        print(f'setup: python3 "{SETUP}" typesafe')
    else:
        try:
            print(f"typesafe key: ok ({jev.check_key(key, transport=deps.transport)})")
        except AuthError:
            print("typesafe key: rejected by TypeSafe")
            print(f'setup: python3 "{SETUP}" typesafe')
        except HttpError as e:
            print(f"typesafe key: present, not verified now (HTTP {e.status})")
    if keys.get_key("s2"):
        print("s2 key: present")
    else:
        print("s2 key: not set (optional; recommended above ~1,000 papers)")
        print(f'optional setup: python3 "{SETUP}" s2')
    ready = depsmod.have_pypdf() or depsmod.venv_python(deps.data_dir).exists()
    print("pdf support: " + ("ready" if ready else
                             f"pypdf will be installed into {deps.data_dir / 'venv'} on the first full-text run"))
    print(f"data dir: {deps.data_dir}")
    return 0 if ok else 1


def cmd_search(args, deps):
    show(deps.s2.search(args.query, limit=args.limit, fields=SHOW_FIELDS))
    return 0


def cmd_lookup(args, deps):
    for given, paper in zip(args.ids, deps.s2.batch(args.ids, fields=SHOW_FIELDS)):
        if paper:
            show([paper])
        else:
            print(f"not found: {given}")
    return 0


def cmd_check(args, deps):
    spec = load(pathlib.Path(args.dir) / "spec.json")
    subs = [n for n in spec["questions"] if n.startswith("sub_")]
    print(f"spec ok: {spec['slug']} | {len(spec['seeds'])} seeds | {len(spec['queries'])} queries | "
          f"{len(spec['questions'])} abstract questions ({len(subs)} subtopics) | "
          f"{len(spec['fulltext_questions'])} full-text questions | pool ceiling {spec['pool_size']:,}")
    return 0


def cmd_estimate(args, deps):
    spec = load(pathlib.Path(args.dir) / "spec.json")
    e = estimatemod.estimate(spec, have_s2_key=bool(keys.get_key("s2")))
    lo, hi = e["minutes"]["collect"]
    print(f"pool ceiling {e['pool_size']:,} | full text for up to {e['fulltext_max']} papers")
    print(f"Jev tokens: ~{e['tokens_abstract']:,} (abstracts) + ~{e['tokens_fulltext']:,} (full text), "
          f"about US$ {e['cost_usd']:.2f}")
    print(f"time (rough): collect {lo:.0f}-{hi:.0f} min, score ~{e['minutes']['score']:.0f} min, "
          f"full text ~{e['minutes']['fulltext']:.0f} min")
    return 0


def cmd_collect(args, deps):
    survey = store.Survey(args.dir)
    spec = load(survey.path("spec"))
    data = None if args.fresh else survey.read("pool")
    if data is None:
        try:
            data = pool.collect(spec, deps.s2, log=deps.log)
        except pool.NoSeedsError as e:
            print(str(e))
            seed_ids = ' '.join(s['id'] for s in spec['seeds'])
            print(f"Verify seed IDs with: survey.py lookup {seed_ids}")
            return 2
        survey.write("pool", data)
    if "with_abstract" not in data["stats"]:  # resumes here if a previous run stopped during the lookups
        found, _ = pool.fill_abstracts(data["papers"], deps.find_abstract, log=deps.log, sleep=deps.sleep)
        data["stats"]["openalex_found"] = found
        data["stats"]["with_abstract"] = sum(1 for p in data["papers"] if p.get("abstract"))
        survey.write("pool", data)
    s = data["stats"]
    print(f"found {s['found']:,} | outside years {s['outside_years']:,} | kept {s['kept']:,} of ceiling "
          f"{spec['pool_size']:,} (trimmed {s['trimmed']:,}) | with abstract {s['with_abstract']:,}")
    if data["missing_seeds"]:
        print(f"seeds not found: {', '.join(data['missing_seeds'])}")
    return 0


def cmd_score(args, deps):
    survey = store.Survey(args.dir)
    spec = load(survey.path("spec"))
    if deps.ask is None:
        return key_problem()
    data, done, _ = scored_records(survey, spec)
    work = screen.pending(data["papers"], done, spec["questions"])
    ok, errors = screen.score(work, spec, deps.ask, sink=lambda row: survey.append_lines("scores", [row]),
                              log=deps.log)
    _, _, recs = scored_records(survey, spec)
    policy = Policy(spec)
    passed = policy.by_priority(policy.passing(recs))
    print(f"asked now: {ok:,} ok, {errors:,} failed | scored in total: {len(recs):,} | "
          f"pass the gate: {len(passed):,} ({len(passed) / max(len(recs), 1):.0%})")
    if errors:
        print("some calls failed: run score again to retry only those")
    print("top by priority:")
    for r in passed[:15]:
        print(f"  {r.get('topic', 0.0):.2f} {r.get('year') or '----'} {(r.get('title') or '')[:90]}")
    return 0


def cmd_sample(args, deps):
    survey = store.Survey(args.dir)
    spec = load(survey.path("spec"))
    data, _, recs = scored_records(survey, spec)
    passed = {r["paperId"] for r in Policy(spec).passing(recs)}
    order, rejected = validate.draw(recs, passed)
    by_id = {p["paperId"]: p for p in data["papers"]}
    survey.write("sample", {"area": spec["area"], "papers": [
        {"id": i, "title": by_id[i].get("title"), "abstract": by_id[i].get("abstract")} for i in order]})
    survey.write("sample_key", {"order": order, "rejected": sorted(rejected)})
    print(f"sample: {len(order)} papers ({len(rejected)} rejected by the gate, "
          f"{len(order) - len(rejected)} accepted), shuffled")
    print(f"for the blind labeler: {survey.path('sample').resolve()}")
    print(f"save its JSON reply to: {survey.path('labels').resolve()}")
    return 0


def cmd_validate(args, deps):
    survey = store.Survey(args.dir)
    spec = load(survey.path("spec"))
    key = survey.read("sample_key")
    if key is None:
        print(f"run sample first and save the labeler's reply to {survey.path('labels')}")
        return 2

    # Read labels from file directly to handle malformed JSON
    labels_path = survey.path("labels")
    if not labels_path.exists():
        print(f"run sample first and save the labeler's reply to {labels_path}")
        return 2

    try:
        text = labels_path.read_text(encoding="utf-8")
        # Strip code fence if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove opening fence (possibly with language specifier)
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            # Remove closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        raw = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"malformed labels file: {labels_path}")
        print("expected shape: {\"labels\": [{\"id\": \"...\", \"label\": \"relevant\" | \"not_relevant\", \"reason\": \"...\"}]}")
        return 2

    # Handle both {"labels": [...]} and bare list
    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = raw.get("labels", [])
    else:
        print(f"malformed labels file: {labels_path}")
        print("expected shape: {\"labels\": [{\"id\": \"...\", \"label\": \"relevant\" | \"not_relevant\", \"reason\": \"...\"}]}")
        return 2

    # Skip entries that are not dicts or lack required fields
    labels = {}
    reasons = {}
    for x in entries:
        if not isinstance(x, dict) or not isinstance(x.get("id"), str):
            continue
        if x.get("label") in ("relevant", "not_relevant"):
            labels[x["id"]] = x["label"]
            reasons[x["id"]] = x.get("reason", "")
    result = validate.compare(key["order"], set(key["rejected"]), labels)
    if not result["checked"]:
        print("the labels file has no usable labels")
        return 2
    survey.write("validation", result)
    _, _, recs = scored_records(survey, spec)
    by_id = {r["paperId"]: r for r in recs}
    line = (f"labeled {result['checked']} | agreement {result['agreement']:.0%} | relevant among rejected: "
            f"{len(result['missed'])}/{result['rejected_checked']}")
    if result["miss_rate_upper95"] is not None:
        line += f" (at most {result['miss_rate_upper95']:.0%} of rejected papers, 95%)"
    if result["precision"] is not None:
        line += f" | precision of accepted: {result['precision']:.0%}"
    print(line)
    if result["unlabeled"]:
        print(f"unlabeled: {len(result['unlabeled'])}")
    for pid in result["disagreements"]:
        r = by_id.get(pid, {})
        gate = "rejected" if pid in result["missed"] else "accepted"
        print(f"- gate {gate}, labeler {labels[pid]}: {(r.get('title') or pid)[:90]} | "
              f"topic {r.get('topic', 0.0):.2f} | {reasons.get(pid, '')}")
    return 0


def cmd_fulltext(args, deps):
    survey = store.Survey(args.dir)
    spec = load(survey.path("spec"))
    if not spec["fulltext_questions"]:
        print("the spec has no full-text questions; nothing to do")
        return 0
    if deps.ask is None:
        return key_problem()
    data, _, recs = scored_records(survey, spec)
    selected = Policy(spec).for_fulltext(recs, {s["paperId"] for s in data["seeds"]})
    previous = survey.read("fulltext", {"papers": {}})["papers"]
    results = fulltext.run(selected, spec, deps.s2, deps.ask, deps.data_dir / "pdfs", previous,
                           extract=deps.extract, transport=deps.transport, sleep=deps.sleep, log=deps.log)
    survey.write("fulltext", {"selected": [r["paperId"] for r in selected], "papers": results})
    counts = {}
    for r in selected:
        status = results.get(r["paperId"], {}).get("status", "missing")
        counts[status] = counts.get(status, 0) + 1
    print(f"selected {len(selected)} | " + " | ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    if counts.get("error"):
        print("some calls failed: run fulltext again to retry them")
    return 0


def build(survey, spec):
    """Everything report.render needs, plus `recs` and `passed_ids` for the exports."""
    data, _, recs = scored_records(survey, spec)
    policy = Policy(spec)
    passed = policy.passing(recs)
    ft = survey.read("fulltext", {"selected": [], "papers": {}})
    by_id = {r["paperId"]: r for r in recs}
    selected = [by_id[i] for i in ft["selected"] if i in by_id]
    read, no_pdf = [], []
    for r in selected:
        res = ft["papers"].get(r["paperId"], {})
        enriched = {**r, "authors": res.get("authors") or []}
        if res.get("status") == "read":
            read.append({**enriched, **res["answers"]})
        else:
            no_pdf.append(enriched)
    sections = policy.reading_list(read if spec["fulltext_questions"] else policy.by_priority(passed))
    no_abstract = sorted((p for p in data["papers"] if not p.get("abstract") and pool.connectivity(p) >= 2),
                         key=lambda p: -pool.connectivity(p))[:15]
    rows = survey.read_lines("scores")
    models = {r["model"] for r in rows if r.get("model")} | {v["model"] for v in ft["papers"].values()
                                                              if v.get("model")}
    return {"stats": data["stats"], "with_abstract": data["stats"].get("with_abstract", 0), "scored": len(recs),
            "passed": len(passed), "passed_ids": {r["paperId"] for r in passed}, "recs": recs,
            "selected": selected, "fulltext": ft["papers"], "sections": sections, "no_pdf": no_pdf,
            "no_abstract": no_abstract, "seeds": data["seeds"], "validation": survey.read("validation"),
            "tokens_abstract": sum(r.get("tokens", 0) for r in rows if "error" not in r),
            "tokens_fulltext": sum(v.get("tokens", 0) for v in ft["papers"].values()),
            "models": models, "date": datetime.date.today().isoformat()}


def _ready_for_report(survey, spec):
    if spec["fulltext_questions"] and not survey.exists("fulltext"):
        print("run fulltext first")
        return False
    return True


def cmd_report(args, deps):
    survey = store.Survey(args.dir)
    spec = load(survey.path("spec"))
    if not _ready_for_report(survey, spec):
        return 2
    ctx = build(survey, spec)
    survey.write_text("report", report.render(spec, ctx))
    print(f"report: {survey.path('report').resolve()}")
    n = 0
    for title, recs in ctx["sections"]:
        print(f"{title}:")
        for r in recs:
            n += 1
            print(f"  {n}. {(r.get('title') or '')[:90]} ({r.get('year') or 'n.d.'})")
    return 0


def cmd_export(args, deps):
    survey = store.Survey(args.dir)
    spec = load(survey.path("spec"))
    if not _ready_for_report(survey, spec):
        return 2
    ctx = build(survey, spec)
    listed = [r for _, recs in ctx["sections"] for r in recs]
    survey.write_text("bib", report.bibtex(listed))
    survey.write_text("csv", report.scored_csv(ctx["recs"], spec, ctx["passed_ids"], ctx["fulltext"]))
    print(f"bibtex: {survey.path('bib').resolve()} ({len(listed)} entries)")
    print(f"csv: {survey.path('csv').resolve()} ({len(ctx['recs'])} rows)")
    return 0


COMMANDS = {"doctor": cmd_doctor, "search": cmd_search, "lookup": cmd_lookup, "check": cmd_check,
            "estimate": cmd_estimate, "collect": cmd_collect, "score": cmd_score, "sample": cmd_sample,
            "validate": cmd_validate, "fulltext": cmd_fulltext, "report": cmd_report, "export": cmd_export}


def _maybe_reexec(python, argv, environ, execv):
    """Detect re-exec loop and return error code instead of exec'ing forever."""
    if environ.get("PAPER_SIFT_REEXEC") == "1" and python:
        print("error: pypdf still not available after venv setup; check your environment")
        return 5
    if python:
        environ["PAPER_SIFT_REEXEC"] = "1"
        execv(str(python), [str(python)] + argv)
    return None


def parser():
    ap = argparse.ArgumentParser(prog="survey.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor").add_argument("--data-dir")
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)
    sub.add_parser("lookup").add_argument("ids", nargs="+")
    for name in ("check", "estimate", "score", "sample", "validate", "report", "export"):
        sub.add_parser(name).add_argument("dir")
    p = sub.add_parser("collect")
    p.add_argument("dir")
    p.add_argument("--fresh", action="store_true")
    p = sub.add_parser("fulltext")
    p.add_argument("dir")
    p.add_argument("--data-dir")
    return ap


def main(argv=None, deps=None):
    args = parser().parse_args(argv)
    try:
        if deps is None:
            spec = None
            if getattr(args, "dir", None):
                try:
                    spec = load(pathlib.Path(args.dir) / "spec.json")
                except SpecError:
                    pass  # the command reports it
            if args.command == "fulltext" and spec and spec["fulltext_questions"]:
                try:
                    python = depsmod.ensure_pypdf(depsmod.data_dir(args.data_dir))
                except RuntimeError as e:
                    print(e)
                    return 5
                sys.stdout.flush()
                sys.stderr.flush()
                result = _maybe_reexec(
                    python=python,
                    argv=[str(pathlib.Path(__file__).resolve()), *sys.argv[1:]],
                    environ=os.environ,
                    execv=os.execv
                )
                if result is not None:
                    return result
            deps = real_deps(spec, getattr(args, "data_dir", None))
        return COMMANDS[args.command](args, deps)
    except keys.KeyFormatError as e:
        return malformed_key(e)
    except SpecError as e:
        print(f"spec error: {e}")
        return 2
    except AuthError as e:
        if "semanticscholar" in e.url:
            print(f'Semantic Scholar rejected the S2 key. Replace it with: python3 "{SETUP}" s2 '
                  "(or unset S2_API_KEY).")
            return 3
        return key_problem(rejected=True)
    except HttpError as e:
        print(f"service error: HTTP {e.status} from {e.url}: {e.body[:200]!r}")
        return 4


if __name__ == "__main__":
    sys.exit(main())
