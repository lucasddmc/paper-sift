"""OpenAlex fallback for abstracts that Semantic Scholar does not serve. Called serially:
parallel requests were refused in testing."""
import difflib
import re
import time
import urllib.parse

from .net import HttpError, request_json

API = "https://api.openalex.org/works"
MIN_SIMILARITY = 0.92


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower())


def title_similarity(a, b):
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def rebuild(inverted_index):
    positions = sorted((i, word) for word, idxs in inverted_index.items() for i in idxs)
    return " ".join(word for _, word in positions)


def find_abstract(title, *, transport=None, sleep=time.sleep):
    q = urllib.parse.urlencode({"search": title, "per-page": 3, "select": "title,abstract_inverted_index"})
    try:
        results = request_json("GET", f"{API}?{q}", transport=transport, sleep=sleep, retries=3,
                               timeout=30).get("results") or []
    except HttpError:
        return None
    for work in results:
        if work.get("abstract_inverted_index") and title_similarity(work.get("title"), title) >= MIN_SIMILARITY:
            return rebuild(work["abstract_inverted_index"])
    return None
