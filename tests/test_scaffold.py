import json
import unittest

import helpers
import paper_sift


class ScaffoldTest(unittest.TestCase):
    def test_user_agent_names_version(self):
        self.assertEqual(paper_sift.USER_AGENT.split()[0], f"paper-sift/{paper_sift.__version__}")

    def test_manifests_match_package(self):
        manifest = json.loads((helpers.ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "paper-sift")
        self.assertEqual(manifest["version"], paper_sift.__version__)
        market = json.loads((helpers.ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.assertEqual(market["name"], "paper-sift")
        self.assertEqual([p["name"] for p in market["plugins"]], ["paper-sift"])
