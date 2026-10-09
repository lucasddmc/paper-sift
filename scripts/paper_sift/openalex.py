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


def find_abstract(title, *, transport=None, sleep=time.sleep):
    # Return immediately if title normalizes to empty string
    if not _norm(title):
        return None

    q = urllib.parse.urlencode({"search": title, "per-page": 3, "select": "title,abstract_inverted_index"})
    try:
        response = request_json("GET", f"{API}?{q}", transport=transport, sleep=sleep, retries=3, timeout=30)
        # Ensure response is a dict and results is a list
        if not isinstance(response, dict):
            return None
        results = response.get("results") or []
        if not isinstance(results, list):
            return None
    except (HttpError, ValueError):
        # ValueError catches JSONDecodeError (malformed JSON) and other JSON-related errors
        return None

    for work in results:
        if work.get("abstract_inverted_index") and title_similarity(work.get("title"), title) >= MIN_SIMILARITY:
            return rebuild(work["abstract_inverted_index"])
    return None
