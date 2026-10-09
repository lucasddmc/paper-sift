import json
import unittest

import helpers  # noqa: F401
from paper_sift import openalex

INV = {"Diffusion": [0], "models": [1], "work.": [2]}


def transport_with(results, status=200):
    def t(method, url, headers, body, timeout):
        return status, json.dumps({"results": results}).encode()
    return t


class OpenAlexTest(unittest.TestCase):
    def test_rebuild_orders_words_by_position(self):
        self.assertEqual(openalex.rebuild({"b": [1, 3], "a": [0], "c": [2]}), "a b c b")

    def test_matching_title_returns_abstract(self):
        t = transport_with([{"title": "Diffusion Models Work!", "abstract_inverted_index": INV}])
        self.assertEqual(openalex.find_abstract("Diffusion models work", transport=t, sleep=lambda s: None),
                         "Diffusion models work.")

    def test_different_title_is_ignored(self):
        t = transport_with([{"title": "Something else entirely", "abstract_inverted_index": INV}])
        self.assertIsNone(openalex.find_abstract("Diffusion models work", transport=t, sleep=lambda s: None))

    def test_http_failure_returns_none(self):
        t = transport_with([], status=400)
        self.assertIsNone(openalex.find_abstract("x", transport=t, sleep=lambda s: None))
