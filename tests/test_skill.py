import json
import re
import unittest

import helpers
import survey
from paper_sift import spec as specmod

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

    def test_the_references_live_inside_skill_md(self):
        """The spec reference and the question guide are the last two sections of SKILL.md, not files beside it.

        Files beside SKILL.md sit in the plugin directory, outside the user's project, and the agent could not
        Read them after the first turn. SKILL.md itself is always loaded with the skill.
        """
        text = (SKILL_DIR / "SKILL.md").read_text()
        self.assertEqual(re.findall(r"^## (.+)$", text, re.M)[-2:], ["spec.json reference", "Writing the questions"])
        for name in ("spec-reference.md", "question-guide.md"):
            self.assertTrue(name not in text, f"SKILL.md still mentions {name}")
            self.assertFalse((SKILL_DIR / name).exists(), f"{name} still exists")
        step = text.split("## 4. Search plan", 1)[1].split("\n## ", 1)[0]
        for title in ("spec.json reference", "Writing the questions"):
            self.assertIn(title, step)

    def test_the_example_in_the_spec_reference_is_a_valid_spec(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        marker = "\n## spec.json reference\n"
        self.assertTrue(marker in text, "SKILL.md has no '## spec.json reference' section")
        section = text.split(marker, 1)[1].split("\n## ", 1)[0]
        example = re.search(r"```json\n(.*?)\n```", section, re.S)
        self.assertTrue(example, "the reference has no ```json example")
        self.assertEqual(specmod.validate(json.loads(example.group(1)))["slug"], "diffusion-models")

    def test_the_user_is_told_to_allow_the_survey_commands(self):
        """The user is asked to allow the survey commands for the project, and every command stays plain.

        allowed-tools pre-approves survey.py only for the turn that invoked the skill, and a plugin cannot ship
        standing allow rules; a command prefixed with `cd ... &&` would not match the rule either.
        """
        text = (SKILL_DIR / "SKILL.md").read_text()
        preflight = text.split("## 1. Preflight", 1)[1].split("\n## ", 1)[0]
        self.assertIn("Yes, and don't ask again", preflight)
        self.assertLess(preflight.index("Yes, and don't ask again"), preflight.index("survey.py doctor"))
        self.assertIn("never prefixed with `cd ... &&`", preflight)
        self.assertIn("Yes, and don't ask again", (helpers.ROOT / "README.md").read_text())

    def test_key_rule_present(self):
        self.assertIn("Never ask for, accept, read or print an API key", (SKILL_DIR / "SKILL.md").read_text())

    def test_a_key_in_a_message_is_flagged_first_even_as_an_aside(self):
        """Any key in a message is flagged first, even when the user mentions it as an aside.

        In the first real test the user wrote 'my TypeSafe key is ..., if needed' and the agent left the key
        unused without saying a word about it.
        """
        text = (SKILL_DIR / "SKILL.md").read_text()
        rule = text.split("1. **Keys never pass through the chat.**", 1)[1].split("\n2. ", 1)[0]
        rule = " ".join(rule.split())  # the text is wrapped at 100 columns
        for phrase in ("looks like an API key", "even as an aside", 'even "if needed"', "first thing",
                       "must not be shared in the chat", "conversation history", "revoke", "setup command",
                       "without using it"):
            self.assertIn(phrase, rule)

    def test_s2_key_is_strongly_recommended(self):
        skill = (SKILL_DIR / "SKILL.md").read_text()
        self.assertIn("s2 api: rate-limited", skill)
        self.assertIn("before collecting", skill)
        for text in (skill, (helpers.ROOT / "README.md").read_text()):
            self.assertIn("strongly recommended", text)
            self.assertNotIn("1,000 papers", text)

    def test_long_stages_run_in_the_background(self):
        text = (SKILL_DIR / "SKILL.md").read_text()
        self.assertIn("**Long stages run in the background.**", text)
        rule = text.split("**Long stages run in the background.**", 1)[1].split("\n\n", 1)[0]
        self.assertIn("run_in_background", rule)
        self.assertIn("2 hours", rule)
        background, foreground = rule.split("foreground", 1)
        for command in ("collect", "score", "fulltext"):
            self.assertIn(f"`{command}`", background)
        for command in ("doctor", "search", "lookup", "check", "estimate", "sample", "validate", "report", "export"):
            self.assertIn(f"`{command}`", foreground)
        self.assertNotIn("above about 40", text)
        self.assertNotIn("When the pool ceiling is above", text)

    def test_agent_is_read_only(self):
        fm = frontmatter(helpers.ROOT / "agents" / "blind-labeler.md")
        self.assertEqual(fm["name"], "blind-labeler")
        self.assertEqual(fm["tools"], "Read")
