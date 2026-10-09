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
