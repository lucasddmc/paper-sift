import json
import unittest

import helpers  # noqa: F401
from paper_sift import jev
from paper_sift.net import AuthError

Q = {"topic": {"instructions": "Is `paper` about X?", "true": "Yes, X", "false": "No", "label": "ignored"}}


def fake(status, body):
    seen = {}

    def transport(method, url, headers, data, timeout):
        seen.update(method=method, url=url, headers=headers, payload=json.loads(data))
        return status, json.dumps(body).encode()

    transport.seen = seen
    return transport


class JevTest(unittest.TestCase):
    def test_ask_sends_nouls_and_parses_answers(self):
        t = fake(200, {"model": "jev-1.13.0", "answers": {"topic": {"noul": 0.87}},
                       "usage": {"input_tokens": 412, "output_tokens": 3}})
        out = jev.ask({"paper": {"title": "T"}}, Q, key="k", transport=t)
        self.assertEqual(out, {"answers": {"topic": 0.87}, "tokens": 412, "model": "jev-1.13.0"})
        self.assertEqual(t.seen["url"], jev.ENDPOINT)
        self.assertEqual(t.seen["headers"]["Authorization"], "Bearer k")
        self.assertEqual(t.seen["payload"]["model"], "jev-1.13.0")
        self.assertEqual(t.seen["payload"]["state"], {"paper": {"title": "T"}})
        self.assertEqual(t.seen["payload"]["questions"]["topic"],
                         {"type": "noul", "instructions": "Is `paper` about X?",
                          "criteria": {"true": "Yes, X", "false": "No"}})

    def test_check_key_returns_model(self):
        t = fake(200, {"model": "jev-1.13.0", "answers": {"probe": {"noul": 0.99}}, "usage": {"input_tokens": 30}})
        self.assertEqual(jev.check_key("k", transport=t), "jev-1.13.0")

    def test_check_key_raises_on_bad_key(self):
        with self.assertRaises(AuthError):
            jev.check_key("bad", transport=fake(401, {"error": "invalid key"}))

    def test_cost(self):
        self.assertAlmostEqual(jev.cost(1_000_000), 0.042)
