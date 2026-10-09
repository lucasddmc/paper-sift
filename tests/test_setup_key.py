import contextlib
import io
import stat
import tempfile
import unittest

import helpers  # noqa: F401
import setup_key
from paper_sift import keys
from paper_sift.net import AuthError, HttpError


def run(argv, entered, checker, existing=None):
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as home:
        if existing is not None and argv and argv[0] in keys.SERVICES:
            keys.save_key(argv[0], existing, home=home)
        with contextlib.redirect_stdout(out):
            code = setup_key.main(argv, getpass_fn=lambda prompt: entered, checker=checker, home=home)
        path = keys.key_path(argv[0], home) if argv and argv[0] in keys.SERVICES else None
        saved = path.read_text() if path and path.exists() else None
        mode = stat.S_IMODE(path.stat().st_mode) if saved is not None else None
    return code, out.getvalue(), saved, mode


class SetupKeyTest(unittest.TestCase):
    def test_saves_privately_and_never_prints_the_key(self):
        code, out, saved, mode = run(["typesafe"], " tsk-123 ", lambda s, k: "jev-1.13.0")
        self.assertEqual((code, saved, mode), (0, "tsk-123", 0o600))
        self.assertIn("OK", out)
        self.assertNotIn("tsk-123", out)

    def test_rejected_key_exits_1(self):
        def reject(service, key):
            raise AuthError(401, b"", "u")
        code, out, saved, _ = run(["typesafe"], "bad", reject)
        self.assertEqual((code, saved), (1, None))
        self.assertIn("rejected", out)

    def test_rejected_key_keeps_the_previous_one(self):
        def reject(service, key):
            raise AuthError(401, b"", "u")
        code, out, saved, _ = run(["typesafe"], "bad", reject, existing="old-key")
        self.assertEqual((code, saved), (1, "old-key"))
        self.assertIn("previous key was kept", out)

    def test_unverifiable_key_is_kept(self):
        def offline(service, key):
            raise HttpError(503, b"", "u")
        code, _, saved, _ = run(["s2"], "s2k", offline)
        self.assertEqual((code, saved), (0, "s2k"))

    def test_empty_input_saves_nothing(self):
        code, _, saved, _ = run(["s2"], "   ", lambda s, k: "x")
        self.assertEqual((code, saved), (1, None))

    def test_usage_on_bad_arguments(self):
        code, out, _, _ = run([], "", lambda s, k: "x")
        self.assertEqual(code, 2)
        self.assertIn("setup_key.py typesafe", out)
