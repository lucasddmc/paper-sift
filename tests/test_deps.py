import pathlib
import unittest
from unittest import mock

import helpers  # noqa: F401
from paper_sift import deps


class DepsTest(unittest.TestCase):
    def test_data_dir(self):
        fallback = pathlib.Path.home() / ".cache" / "paper-sift"
        self.assertEqual(deps.data_dir("/tmp/x"), pathlib.Path("/tmp/x"))
        self.assertEqual(deps.data_dir("${CLAUDE_PLUGIN_DATA}"), fallback)
        self.assertEqual(deps.data_dir(""), fallback)
        self.assertEqual(deps.data_dir(None), fallback)

    def test_no_venv_when_pypdf_imports(self):
        with mock.patch.object(deps, "have_pypdf", return_value=True):
            self.assertIsNone(deps.ensure_pypdf("/nonexistent"))

    def test_venv_python_lives_in_the_data_dir(self):
        self.assertTrue(str(deps.venv_python("/d")).startswith(str(pathlib.Path("/d") / "venv")))
