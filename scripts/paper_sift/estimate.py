"""Rough cost and time before anything runs. Tokens are estimated from text length (4 chars/token)."""
from .jev import cost
from .spec import subtopics

ABSTRACT_TOKENS = 350     # a typical title and abstract
FULLTEXT_TOKENS = 22_000  # a typical paper body after the 90k-character cap
QUESTION_OVERHEAD = 20    # per question, beyond its text
OPENALEX_SHARE = 0.4      # guess: share of pool papers without an S2 abstract
OPENALEX_SECONDS = 0.75   # one serial lookup, pause included
S2_SECONDS = 1.5          # one S2 request with the pause; much more when rate-limited


def tokens_of(text):
    return len(text) // 4 + 1


def question_tokens(questions):
    return sum(tokens_of(q["instructions"] + q["true"] + q["false"]) + QUESTION_OVERHEAD
               for q in questions.values())


def estimate(spec, *, have_s2_key):
    area = tokens_of(spec["area"])
    pool = spec["pool_size"]
    ft = spec["policy"]["fulltext"]
    n_text = 0
    if spec["fulltext_questions"]:
        n_text = ((len(spec["seeds"]) if ft["include_seeds"] else 0) + ft["top"]
                  + ft["per_subtopic"] * len(subtopics(spec)))
    tok_abstract = pool * (area + ABSTRACT_TOKENS + question_tokens(spec["questions"]))
    tok_text = n_text * (area + FULLTEXT_TOKENS + question_tokens(spec["fulltext_questions"]))
    requests = len(spec["seeds"]) * 2 * 2 + len(spec["queries"]) + 2
    collect_lo = (requests * S2_SECONDS + pool * OPENALEX_SHARE * OPENALEX_SECONDS) / 60
    collect_hi = collect_lo * (2 if have_s2_key else 4)
    return {"pool_size": pool, "fulltext_max": n_text, "tokens_abstract": tok_abstract, "tokens_fulltext": tok_text,
            "cost_usd": round(cost(tok_abstract + tok_text), 3),
            "minutes": {"collect": [round(collect_lo, 1), round(collect_hi, 1)],
                        "score": round(pool / 16 / 60 + 0.5, 1),
                        "fulltext": round(n_text * 4.5 / 60 + 0.5, 1)}}
