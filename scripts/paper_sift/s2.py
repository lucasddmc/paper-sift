"""Semantic Scholar Graph API client: search, batch lookup, citation edges, recommendations."""
import time
import urllib.parse

from .net import request_json

API = "https://api.semanticscholar.org/graph/v1"
REC_API = "https://api.semanticscholar.org/recommendations/v1/papers/"
FIELDS = "paperId,title,abstract,year,venue,externalIds,citationCount,publicationTypes"
EDGE_CAP = 9_999  # S2 refuses offset + limit >= 10,000, so this is all it serves per paper and relation
BATCH = 500


class S2:
    def __init__(self, key=None, transport=None, sleep=time.sleep, pause=1.1, retries=10):
        self.key, self.transport, self.sleep = key, transport, sleep
        self.pause, self.retries = pause, retries

    def _call(self, method, url, payload=None):
        headers = {"x-api-key": self.key} if self.key else {}
        data = request_json(method, url, headers=headers, payload=payload, transport=self.transport,
                            sleep=self.sleep, retries=self.retries)
        self.sleep(self.pause)  # stay under the per-second rate limit
        return data

    def search(self, query, limit=100, fields=FIELDS):
        q = urllib.parse.urlencode({"query": query, "limit": min(limit, 100), "fields": fields})
        return [p for p in self._call("GET", f"{API}/paper/search?{q}").get("data") or [] if p.get("paperId")]

    def batch(self, ids, fields=FIELDS):
        out = []
        for i in range(0, len(ids), BATCH):
            out += self._call("POST", f"{API}/paper/batch?fields={fields}", {"ids": list(ids[i:i + BATCH])})
        return out

    def edges(self, paper_id, relation):
        if relation not in ("citations", "references"):
            raise ValueError(f"unknown relation {relation!r}")
        key = "citingPaper" if relation == "citations" else "citedPaper"
        out, offset = [], 0
        while offset < EDGE_CAP:
            limit = min(1000, EDGE_CAP - offset)
            page = self._call("GET", f"{API}/paper/{paper_id}/{relation}?fields={FIELDS}&limit={limit}&offset={offset}")
            out += [e[key] for e in page.get("data") or [] if (e.get(key) or {}).get("paperId")]
            if "next" not in page or not page.get("data"):
                break
            offset = page["next"]
        return out

    def recommendations(self, positive_ids, limit=500):
        data = self._call("POST", f"{REC_API}?fields={FIELDS}&limit={limit}",
                          {"positivePaperIds": list(positive_ids)})
        return [p for p in data.get("recommendedPapers") or [] if p.get("paperId")]
