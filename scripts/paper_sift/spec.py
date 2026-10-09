"""Load and validate a survey's spec.json."""
import copy
import hashlib
import json
import pathlib
import re

from .policy import VARIABLES, Expr, PolicyError

POOL_MIN, POOL_MAX, POOL_DEFAULT = 100, 3000, 800
RECIPES = ("learn-area",)
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEFAULTS = {
    "version": 1, "recipe": "learn-area", "model": "jev-1.13.0", "tau": 0.5, "years": None,
    "pool_size": POOL_DEFAULT, "queries": [],
    "sources": {"citations": True, "references": True, "recommendations": True, "search_per_query": 100},
    "fulltext_questions": {},
    "policy": {"gate": "topic", "priority": "p.topic * importance",
               "fulltext": {"top": 30, "per_subtopic": 5, "include_seeds": True},
               "start_here": "False", "final_rank": "p.topic", "final_top": 20},
}


class SpecError(ValueError):
    pass


def question_hash(q):
    context = q.get("_context", "")
    text = "\x1f".join((q["instructions"], q["true"], q["false"], context))
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def subtopics(spec):
    return [name for name in spec["questions"] if name.startswith("sub_")]


def _merge(defaults, given):
    out = dict(defaults)
    for k, v in given.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _check_questions(questions, where):
    if not isinstance(questions, dict):
        raise SpecError(f"{where} must be an object")
    for name, q in questions.items():
        if not isinstance(q, dict):
            raise SpecError(f"{where}.{name} must be an object")
        if not NAME.match(name) or name == "p" or name in VARIABLES:
            raise SpecError(f"{where}: invalid name {name!r} (lowercase letters, digits and _; "
                            f"not 'p' or {', '.join(VARIABLES)})")
        for field in ("instructions", "true", "false"):
            if not isinstance(q.get(field), str) or not q[field].strip():
                raise SpecError(f"{where}.{name}: missing {field!r}")


def validate(raw):
    # Guard raw as dict
    if not isinstance(raw, dict):
        raise SpecError("spec must be an object")
    # Deep copy to avoid sharing mutable state
    raw = copy.deepcopy(raw)
    spec = _merge(copy.deepcopy(DEFAULTS), raw)
    if spec["version"] != 1:
        raise SpecError("version must be 1")
    if spec["recipe"] not in RECIPES:
        raise SpecError(f"recipe must be one of {', '.join(RECIPES)}")
    if not isinstance(spec.get("slug"), str) or not SLUG.match(spec["slug"]):
        raise SpecError("slug must be lowercase words joined by '-'")
    if not isinstance(spec.get("area"), str) or len(spec["area"].strip()) < 40:
        raise SpecError("area must describe the area and the reader in a few sentences")
    tau = spec["tau"]
    if isinstance(tau, bool) or not isinstance(tau, (int, float)) or not 0 < tau < 1:
        raise SpecError("tau must be between 0 and 1")
    seeds = spec.get("seeds")
    if not isinstance(seeds, list) or not seeds or not all(isinstance(s, dict) and isinstance(s.get("id"), str)
                                                          for s in seeds):
        raise SpecError("seeds must be a non-empty list of {id, title, why}")
    if not isinstance(spec["queries"], list) or not all(isinstance(q, str) and q.strip() for q in spec["queries"]):
        raise SpecError("queries must be a list of strings")
    n = spec["pool_size"]
    if isinstance(n, bool) or not isinstance(n, int) or not POOL_MIN <= n <= POOL_MAX:
        raise SpecError(f"pool_size must be an integer from {POOL_MIN} to {POOL_MAX} (got {n!r})")
    years = spec["years"]
    if years is not None and not (isinstance(years, list) and len(years) == 2
                                  and all(isinstance(y, int) for y in years) and years[0] <= years[1]):
        raise SpecError("years must be null or [first, last]")
    # Guard sources as dict
    if not isinstance(spec.get("sources"), dict):
        raise SpecError("sources must be an object")
    per_query = spec["sources"].get("search_per_query")
    if isinstance(per_query, bool) or not isinstance(per_query, int) or not 0 <= per_query <= 100:
        raise SpecError("sources.search_per_query must be an integer from 0 to 100")
    if "questions" not in spec:
        raise SpecError("questions missing")
    _check_questions(spec["questions"], "questions")
    if "topic" not in spec["questions"]:
        raise SpecError("questions must include 'topic', the gate question")
    _check_questions(spec["fulltext_questions"], "fulltext_questions")
    clash = set(spec["questions"]) & set(spec["fulltext_questions"])
    if clash:
        raise SpecError(f"names used in both question sets: {sorted(clash)}")
    # Guard policy as dict
    if not isinstance(spec.get("policy"), dict):
        raise SpecError("policy must be an object")
    policy = spec["policy"]
    # Guard policy.fulltext as dict
    if not isinstance(policy.get("fulltext"), dict):
        raise SpecError("policy.fulltext must be an object")
    abstract = list(spec["questions"])
    everything = abstract + list(spec["fulltext_questions"])
    for key, facts in (("gate", abstract), ("priority", abstract), ("start_here", everything),
                       ("final_rank", everything)):
        expr_str = policy.get(key)
        if not isinstance(expr_str, str):
            raise SpecError(f"policy.{key} must be a string")
        try:
            Expr(expr_str, facts)
        except PolicyError as e:
            raise SpecError(f"policy.{key}: {e}") from None
    for key in ("top", "per_subtopic"):
        value = policy["fulltext"].get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SpecError(f"policy.fulltext.{key} must be a non-negative integer")
    final_top = policy["final_top"]
    if isinstance(final_top, bool) or not isinstance(final_top, int) or final_top < 1:
        raise SpecError("policy.final_top must be a positive integer")

    # Finding 3: Add context hash to all questions
    context = hashlib.sha256((spec["area"] + "\x1f" + spec["model"]).encode()).hexdigest()[:12]
    for q in spec["questions"].values():
        q["_context"] = context
    for q in spec["fulltext_questions"].values():
        q["_context"] = context

    return spec


def load(path):
    path = pathlib.Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise SpecError(f"cannot read {path}: {e}") from None
    return validate(raw)
