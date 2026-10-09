import stat
import tempfile
import unittest

import helpers  # noqa: F401
from paper_sift import keys


class KeysTest(unittest.TestCase):
    def test_environment_wins_over_file(self):
        with tempfile.TemporaryDirectory() as home:
            keys.save_key("typesafe", "from-file", home=home)
            self.assertEqual(keys.get_key("typesafe", env={"TYPESAFE_API_KEY": "from-env"}, home=home), "from-env")
            self.assertEqual(keys.get_key("typesafe", env={}, home=home), "from-file")

    def test_missing_or_blank_key_is_none(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertIsNone(keys.get_key("s2", env={}, home=home))
            self.assertIsNone(keys.get_key("s2", env={"S2_API_KEY": "  "}, home=home))

    def test_saved_file_is_private(self):
        with tempfile.TemporaryDirectory() as home:
            path = keys.save_key("s2", "  abc  ", home=home)
            self.assertEqual(path, keys.key_path("s2", home))
            self.assertEqual(path.read_text(), "abc")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_empty_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            with self.assertRaises(ValueError):
                keys.save_key("typesafe", "   ", home=home)

    def test_two_line_key_file_is_malformed_and_the_error_names_the_file_not_the_key(self):
        with tempfile.TemporaryDirectory() as home:
            path = keys.key_path("typesafe", home)
            path.parent.mkdir(parents=True)
            path.write_text("tsk-secret\nsecond-line\n")
            with self.assertRaises(keys.KeyFormatError) as ctx:
                keys.get_key("typesafe", env={}, home=home)
        e = ctx.exception
        self.assertEqual((e.service, e.source), ("typesafe", str(path)))
        self.assertIn(str(path), str(e))
        self.assertIn("typesafe", str(e))
        for part in ("tsk-secret", "second-line"):
            self.assertNotIn(part, str(e))
            self.assertNotIn(part, repr(e))

    def test_newline_in_the_environment_is_malformed_and_the_error_names_the_variable(self):
        with tempfile.TemporaryDirectory() as home:
            with self.assertRaises(keys.KeyFormatError) as ctx:
                keys.get_key("s2", env={"S2_API_KEY": "s2-secret\nmore"}, home=home)
        self.assertEqual((ctx.exception.service, ctx.exception.source), ("s2", "S2_API_KEY"))
        self.assertIn("S2_API_KEY", str(ctx.exception))
        self.assertNotIn("s2-secret", str(ctx.exception))

    def test_spaces_controls_and_non_ascii_are_malformed(self):
        for value in ("tsk secret", "tsk\tsecret", "tsk\rsecret", "tsk\x00secret", "tsk\x7f", "tsk-\u00e9",
                      "tsk\u00a0secret", "tsk\u200bsecret"):
            with self.subTest(value=value), self.assertRaises(keys.KeyFormatError):
                keys.get_key("typesafe", env={"TYPESAFE_API_KEY": value}, home="/nonexistent")

    def test_key_file_that_is_not_ascii_is_malformed(self):
        with tempfile.TemporaryDirectory() as home:
            path = keys.key_path("typesafe", home)
            path.parent.mkdir(parents=True)
            path.write_bytes(b"tsk-\xff\xfesecret")
            with self.assertRaises(keys.KeyFormatError) as ctx:
                keys.get_key("typesafe", env={}, home=home)
        self.assertNotIn("secret", str(ctx.exception))

    def test_surrounding_whitespace_is_still_stripped(self):
        with tempfile.TemporaryDirectory() as home:
            path = keys.key_path("s2", home)
            path.parent.mkdir(parents=True)
            path.write_text("  s2-key\n")
            self.assertEqual(keys.get_key("s2", env={}, home=home), "s2-key")
            self.assertEqual(keys.get_key("s2", env={"S2_API_KEY": " env-key\n"}, home=home), "env-key")

    def test_save_rejects_keys_with_spaces_line_breaks_or_non_ascii(self):
        with tempfile.TemporaryDirectory() as home:
            for value in ("a\nb", "a b", "tsk-\u00e9"):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, "^key contains spaces, line breaks or non-ASCII characters$"):
                        keys.save_key("typesafe", value, home=home)
            self.assertFalse(keys.key_path("typesafe", home).exists())
