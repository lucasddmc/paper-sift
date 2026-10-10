import json
import unittest
import urllib.parse

import helpers  # noqa: F401
from paper_sift import s2


class Recorder:
    """Transport that answers through a handler(method, url, payload) and records requests."""

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def __call__(self, method, url, headers, body, timeout):
        payload = json.loads(body) if body else None
        self.calls.append({"method": method, "url": url, "headers": headers, "payload": payload})
        return 200, json.dumps(self.handler(method, url, payload)).encode()


def client(handler, key=None):
    rec = Recorder(handler)
    return s2.S2(key=key, transport=rec, sleep=lambda s: None), rec


def offset_of(url):
    return int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["offset"][0])


def limit_of(url):
    return int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["limit"][0])


class S2Test(unittest.TestCase):
    def test_search_sends_key_and_drops_entries_without_id(self):
        c, rec = client(lambda m, u, p: {"data": [{"paperId": "a"}, {"paperId": None}]}, key="secret")
        self.assertEqual([p["paperId"] for p in c.search("diffusion models", limit=150)], ["a"])
        query = urllib.parse.parse_qs(urllib.parse.urlparse(rec.calls[0]["url"]).query)
        self.assertEqual(query["limit"], ["100"])
        self.assertEqual(query["query"], ["diffusion models"])
        self.assertEqual(rec.calls[0]["headers"]["x-api-key"], "secret")

    def test_no_key_header_without_key(self):
        c, rec = client(lambda m, u, p: {"data": []})
        c.search("x")
        self.assertNotIn("x-api-key", rec.calls[0]["headers"])

    def test_batch_chunks_by_500_and_keeps_order(self):
        c, rec = client(lambda m, u, p: [{"paperId": i} for i in p["ids"]])
        ids = [f"id{i}" for i in range(1200)]
        self.assertEqual([p["paperId"] for p in c.batch(ids)], ids)
        self.assertEqual([len(call["payload"]["ids"]) for call in rec.calls], [500, 500, 200])

    def test_edges_follow_pages(self):
        def handler(m, u, p):
            if offset_of(u) == 0:
                return {"offset": 0, "next": 1000,
                        "data": [{"citingPaper": {"paperId": f"c{i}"}} for i in range(1000)]}
            return {"offset": 1000, "data": [{"citingPaper": {"paperId": "last"}}, {"citingPaper": {"paperId": None}}]}
        c, rec = client(handler)
        got = c.edges("P1", "citations")
        self.assertEqual(len(got), 1001)
        self.assertEqual(got[-1]["paperId"], "last")
        self.assertIn("/paper/P1/citations?", rec.calls[0]["url"])

    def test_edges_stop_at_cap(self):
        def handler(m, u, p):
            o, limit = offset_of(u), limit_of(u)
            return {"offset": o, "next": o + limit,
                    "data": [{"citedPaper": {"paperId": f"r{o}-{i}"}} for i in range(limit)]}
        c, rec = client(handler)
        self.assertEqual(s2.EDGE_CAP, 9_999)
        self.assertEqual(len(c.edges("P1", "references")), s2.EDGE_CAP)
        self.assertEqual(len(rec.calls), 10)
        last = rec.calls[-1]["url"]
        self.assertEqual((offset_of(last), limit_of(last)), (9000, 999))  # offset + limit stays below 10,000

    def test_recommendations_post_seed_ids(self):
        c, rec = client(lambda m, u, p: {"recommendedPapers": [{"paperId": "r1"}]})
        self.assertEqual([p["paperId"] for p in c.recommendations(["a", "b"])], ["r1"])
        self.assertEqual(rec.calls[0]["payload"], {"positivePaperIds": ["a", "b"]})
        self.assertTrue(rec.calls[0]["url"].startswith(s2.REC_API))
