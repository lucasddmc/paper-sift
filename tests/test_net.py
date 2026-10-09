import http.client
import ssl
import tempfile
import unittest
import urllib.error

import helpers  # noqa: F401
from paper_sift import USER_AGENT, store
from paper_sift.net import AuthError, HttpError, request, request_json

CERT_MESSAGE = b"certificate verification failed (python.org builds: run Install Certificates.command)"


def scripted(*responses):
    """A transport that returns (or raises) the given responses in order and records the calls."""
    queue, calls = list(responses), []

    def transport(method, url, headers, body, timeout):
        calls.append((method, url, headers, body))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    transport.calls = calls
    return transport


class NetTest(unittest.TestCase):
    def test_returns_json_and_sends_user_agent(self):
        t = scripted((200, b'{"ok": true}'))
        self.assertEqual(request_json("POST", "https://x.test/a", payload={"q": 1}, transport=t), {"ok": True})
        method, url, headers, body = t.calls[0]
        self.assertEqual(headers["User-Agent"], USER_AGENT)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(body, b'{"q": 1}')

    def test_retries_rate_limits_and_network_errors(self):
        waits = []
        t = scripted((429, b""), (529, b""), OSError("reset"), (200, b"[]"))
        self.assertEqual(request_json("GET", "https://x.test", transport=t, sleep=waits.append), [])
        self.assertEqual(waits, [2.0, 4.0, 8.0])

    def test_backoff_is_capped(self):
        waits = []
        t = scripted(*[(503, b"")] * 7, (200, b"1"))
        request("GET", "https://x.test", transport=t, sleep=waits.append, max_wait=10.0)
        self.assertEqual(waits, [2.0, 4.0, 8.0, 10.0, 10.0, 10.0, 10.0])

    def test_auth_errors_are_not_retried(self):
        t = scripted((401, b"bad key"))
        with self.assertRaises(AuthError):
            request("GET", "https://x.test", transport=t, sleep=lambda s: None)
        self.assertEqual(len(t.calls), 1)

    def test_client_errors_raise_with_body(self):
        t = scripted((422, b'{"detail": "questions.topic.instructions"}'))
        with self.assertRaises(HttpError) as ctx:
            request("POST", "https://x.test", payload={}, transport=t, sleep=lambda s: None)
        self.assertEqual(ctx.exception.status, 422)
        self.assertIn(b"questions.topic", ctx.exception.body)

    def test_gives_up_after_retries(self):
        t = scripted((500, b""), (500, b""), (500, b""))
        with self.assertRaises(HttpError) as ctx:
            request("GET", "https://x.test", transport=t, retries=2, sleep=lambda s: None)
        self.assertEqual(ctx.exception.status, 500)

    def test_invalid_header_value_becomes_http_error_without_the_value(self):
        t = scripted(ValueError("Invalid header value b'Bearer secret'"))
        with self.assertRaises(HttpError) as ctx:
            request("GET", "https://x.test/a", transport=t, sleep=lambda s: self.fail("not retried"))
        e = ctx.exception
        self.assertEqual((e.status, e.body, e.url), (0, b"invalid request (header or URL)", "https://x.test/a"))
        self.assertNotIn("secret", str(e))
        self.assertNotIn("secret", repr(e))
        self.assertIsNone(e.__context__)  # the original error, which quotes the value, is not chained
        self.assertEqual(len(t.calls), 1)

    def test_lone_surrogates_become_replacement_characters(self):
        body = b'{"title": "a\\ud800b", "list": ["\\udfff"], "\\ud800key": 1, "pair": "\\ud83d\\ude00"}'
        got = request_json("GET", "https://x.test", transport=scripted((200, body)))
        self.assertEqual(got, {"title": "a\ufffdb", "list": ["\ufffd"], "\ufffdkey": 1, "pair": "\U0001F600"})
        with tempfile.TemporaryDirectory() as d:
            store.Survey(d).write("pool", got)  # raised UnicodeEncodeError before

    def test_invalid_json_becomes_http_error(self):
        for body in (b"<html>not json</html>", b'{"a": "\xff"}'):
            with self.subTest(body=body):
                with self.assertRaises(HttpError) as ctx:
                    request_json("GET", "https://x.test/j", transport=scripted((200, body)))
                e = ctx.exception
                self.assertEqual((e.status, e.body, e.url), (0, b"invalid JSON response", "https://x.test/j"))
                self.assertIsNone(e.__context__)  # the decoder error holds the whole reply; it is not chained

    def test_certificate_errors_fail_at_once(self):
        cert = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        for error in (urllib.error.URLError(cert), cert):
            with self.subTest(error=type(error).__name__):
                t = scripted(error)
                with self.assertRaises(HttpError) as ctx:
                    request("GET", "https://x.test", transport=t, sleep=lambda s: self.fail("not retried"))
                self.assertEqual((ctx.exception.status, ctx.exception.body), (0, CERT_MESSAGE))
                self.assertEqual(len(t.calls), 1)

    def test_retries_truncated_responses(self):
        waits = []
        t = scripted(http.client.IncompleteRead(b"x"), (200, b"[]"))
        self.assertEqual(request_json("GET", "https://x.test", transport=t, sleep=waits.append), [])
        self.assertEqual(waits, [2.0])
