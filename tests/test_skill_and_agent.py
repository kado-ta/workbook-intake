import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))

import guard_xlide as gx  # noqa: E402
import intake_common as ic  # noqa: E402

AGENT = ROOT / "agents" / "excel-analyst.md"
SKILL = ROOT / "skills" / "analyze" / "SKILL.md"
ALLOWLIST = ROOT / "hooks" / "allowed-tools.txt"


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, "no frontmatter in %s" % path
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


class AgentTest(unittest.TestCase):
    def test_agent_tools_match_allowlist(self):
        names = set()
        for line in ALLOWLIST.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                names.add(gx.TOOL_PREFIX + line.split()[0])
        tools = {t.strip() for t in frontmatter(AGENT)["tools"].split(",")}
        self.assertEqual(tools, names)

    def test_agent_has_no_unsupported_fields(self):
        fields = frontmatter(AGENT)
        for key in ("hooks", "mcpServers", "permissionMode"):
            self.assertNotIn(key, fields)
        self.assertEqual(fields["name"], "excel-analyst")


class SkillTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_skill_contains_consent_copy(self):
        for name in ("CONSENT_HEADER", "CONSENT_QUESTION_PREFIX", "CONFIRM_LABEL",
                     "CONFIRM_DESCRIPTION", "CANCEL_LABEL", "CANCEL_DESCRIPTION",
                     "WARNINGS_HEADER", "WARNINGS_QUESTION_PREFIX", "WARNINGS_LIST_PREFIX",
                     "CONTINUE_LABEL", "CONTINUE_DESCRIPTION", "STOP_LABEL",
                     "STOP_DESCRIPTION"):
            self.assertIn(getattr(ic, name), self.text, name)

    def test_fixed_blocks_equal_constants(self):
        blocks = re.findall(r"```text\n(.*?)\n```", self.text, re.S)
        expected = [
            ic.CONSENT_HEADER, ic.CONSENT_QUESTION_PREFIX + "<path>",
            ic.CONFIRM_LABEL, ic.CONFIRM_DESCRIPTION,
            ic.CANCEL_LABEL, ic.CANCEL_DESCRIPTION,
            ic.WARNINGS_HEADER,
            ic.WARNINGS_QUESTION_PREFIX + "<path>" + ic.WARNINGS_LIST_PREFIX + "<warnings>",
            ic.CONTINUE_LABEL, ic.CONTINUE_DESCRIPTION,
            ic.STOP_LABEL, ic.STOP_DESCRIPTION,
        ]
        self.assertEqual(blocks, expected)

    def test_skill_checks_the_guard_first(self):
        for word in ("xlide_doctor", "wrong_caller"):
            self.assertIn(word, self.text, word)
        paragraphs = self.text.split("\n\n")
        check = [i for i, p in enumerate(paragraphs)
                 if "xlide_doctor" in p and "wrong_caller" in p]
        start = [i for i, p in enumerate(paragraphs)
                 if "Start the `workbook-intake:excel-analyst` subagent" in p]
        step1 = [i for i, p in enumerate(paragraphs) if p.startswith("## Step 1")]
        self.assertTrue(check)
        self.assertTrue(start)
        self.assertTrue(step1)
        self.assertLess(check[0], step1[0])
        self.assertLess(check[0], start[0])

    def test_skill_does_not_rely_on_start_flags(self):
        self.assertNotIn(
            "Stop instead if Claude Code was started with `--agent-teams`", self.text)

    def test_file_name_not_in_shell_command(self):
        self.assertNotIn("realpath", self.text)
        self.assertNotIn("<file name>\"", self.text)

    def test_skill_does_not_run_checker_in_bash(self):
        self.assertNotIn("check_workbook.py", self.text)

    def test_skill_description_makes_no_safety_claim(self):
        description = frontmatter(SKILL)["description"].lower()
        for word in ("safe", "secure", "安全"):
            self.assertNotIn(word, description)
        self.assertEqual(frontmatter(SKILL)["name"], "analyze")


if __name__ == "__main__":
    unittest.main()
