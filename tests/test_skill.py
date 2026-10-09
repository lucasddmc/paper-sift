import re
import unittest

import helpers
import survey

SKILL_DIR = helpers.ROOT / "skills" / "survey"


def frontmatter(path):
    head = path.read_text().split("---\n")[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


class SkillTest(unittest.TestCase):
    def test_skill_frontmatter(self):
        fm = frontmatter(SKILL_DIR / "SKILL.md")
        self.assertEqual(fm["name"], "survey")
        self.assertIn("reading list", fm["description"])
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/survey.py", fm["allowed-tools"])

    def test_every_command_in_the_skill_exists(self):
        used = set(re.findall(r"survey\.py (\w+)", (SKILL_DIR / "SKILL.md").read_text()))
        self.assertTrue(used)
        self.assertLessEqual(used, set(survey.COMMANDS))

    def test_supporting_files_exist_and_are_linked(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        for name in ("spec-reference.md", "question-guide.md"):
            self.assertIn(name, text)
            self.assertTrue((SKILL_DIR / name).exists())

    def test_key_rule_present(self):
        self.assertIn("Never ask for, accept, read or print an API key", (SKILL_DIR / "SKILL.md").read_text())

    def test_agent_is_read_only(self):
        fm = frontmatter(helpers.ROOT / "agents" / "blind-labeler.md")
        self.assertEqual(fm["name"], "blind-labeler")
        self.assertEqual(fm["tools"], "Read")
