"""OpenAlex fallback for abstracts that Semantic Scholar does not serve. Called serially:
parallel requests were refused in testing."""
import difflib
import re
import time
import unicodedata
import urllib.parse

from .net import HttpError, request_json

API = "https://api.openalex.org/works"
MIN_SIMILARITY = 0.92


def _norm(s):
    # Unicode-aware normalization: decompose diacritics, casefold, normalize whitespace
    s = unicodedata.normalize("NFKD", s or "").casefold()
    # Replace dashes with spaces
    s = re.sub(r"[-–—]", " ", s)
    # Remove combining marks and non-word characters, keep word characters and spaces
    s = re.sub(r"[^\w\s]", "", s)
    # Collapse whitespace
    return " ".join(s.split())


def title_similarity(a, b):
    norm_a = _norm(a)
    norm_b = _norm(b)
    # Return 0.0 if either normalized string is empty
    if not norm_a or not norm_b:
        return 0.0
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


def rebuild(inverted_index):
    positions = sorted((i, word) for word, idxs in inverted_index.items() for i in idxs)
    return " ".join(word for _, word in positions)


def lookup(title, *, transport=None, sleep=time.sleep):
    """("found", abstract); ("none", None) when no result matches the title; ("failed", None) when OpenAlex
    could not be asked (an HTTP or network error after retries, or a reply that is not the expected JSON),
    so that a later run tries again."""
    if not _norm(title):  # a blank title would match anything
        return "none", None
    q = urllib.parse.urlencode({"search": title, "per-page": 3, "select": "title,abstract_inverted_index"})
    try:
        response = request_json("GET", f"{API}?{q}", transport=transport, sleep=sleep, retries=3, timeout=30)
    except (HttpError, ValueError):
        return "failed", None
    results = response.get("results") if isinstance(response, dict) else None
    if not isinstance(results, list):
        return "failed", None
    for work in results:
        if work.get("abstract_inverted_index") and title_similarity(work.get("title"), title) >= MIN_SIMILARITY:
            text = rebuild(work["abstract_inverted_index"])
            if text.strip():
                return "found", text
    return "none", None


def find_abstract(title, *, transport=None, sleep=time.sleep):
    """The abstract, or None. Kept for compatibility: `lookup` also tells a miss from a failure."""
    return lookup(title, transport=transport, sleep=sleep)[1]
