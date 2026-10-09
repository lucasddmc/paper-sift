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

    def test_cjk_query_against_unrelated_cjk_result_returns_none(self):
        # "深度学习综述" (deep learning survey) should not match unrelated CJK work
        t = transport_with([{"title": "机器学习基础", "abstract_inverted_index": INV}])
        self.assertIsNone(openalex.find_abstract("深度学习综述", transport=t, sleep=lambda s: None))

    def test_blank_title_returns_none_without_request(self):
        # Blank title should return None immediately without calling transport
        def transport_that_fails(method, url, headers, body, timeout):
            raise AssertionError("transport should not be called for blank title")
        self.assertIsNone(openalex.find_abstract("", transport=transport_that_fails, sleep=lambda s: None))
        self.assertIsNone(openalex.find_abstract("   ", transport=transport_that_fails, sleep=lambda s: None))

    def test_diacritics_match_across_normalization(self):
        # "Schrödinger" (with diacritic) should match "Schrodinger" (without diacritic)
        t = transport_with([{"title": "Schrodinger Equation Solvers", "abstract_inverted_index": INV}])
        self.assertEqual(openalex.find_abstract("Schrödinger equation solvers", transport=t, sleep=lambda s: None),
                         "Diffusion models work.")

    def test_lookup_tells_a_match_a_miss_and_a_failure_apart(self):
        def noop(s):
            return None

        def never(*args):
            raise AssertionError("blank titles are not looked up")

        cases = [(transport_with([{"title": "Diffusion Models Work!", "abstract_inverted_index": INV}]),
                  ("found", "Diffusion models work.")),
                 (transport_with([{"title": "Something else entirely", "abstract_inverted_index": INV}]),
                  ("none", None)),
                 (transport_with([]), ("none", None)),
                 (transport_with([], status=503), ("failed", None)),
                 (lambda *a: (200, b"<html>not json</html>"), ("failed", None)),
                 (lambda *a: (200, b'{"error": "unexpected"}'), ("failed", None))]
        for transport, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(openalex.lookup("Diffusion models work", transport=transport, sleep=noop), expected)
        self.assertEqual(openalex.lookup("  ", transport=never, sleep=noop), ("none", None))

    def test_html_response_returns_none(self):
        # Non-JSON response should be gracefully handled
        def transport_html(method, url, headers, body, timeout):
            return 200, b"<html>not json</html>"
        self.assertIsNone(openalex.find_abstract("test", transport=transport_html, sleep=lambda s: None))
