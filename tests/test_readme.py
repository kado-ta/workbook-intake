import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
JA_PATH = ROOT / "README.ja.md"
JA = JA_PATH.read_text(encoding="utf-8") if JA_PATH.exists() else ""
RUNBOOK = "docs/runbooks/maintenance.md"
SECTIONS = ("Requirements", "Install", "Configuration", "Usage", "Checks",
            "Limitations", "Troubleshooting", "Maintenance", "License")


def h2(text):
    return re.findall(r"^## (.+)$", text, flags=re.M)


class ReadmeTest(unittest.TestCase):
    def test_states_no_affiliation(self):
        self.assertIn("not affiliated with xlide-mcp or NVIDIA SkillSpector", EN)
        self.assertIn("xlide-mcp とも NVIDIA SkillSpector とも関係のない", JA)

    def test_states_own_risk(self):
        self.assertIn("at your own risk", EN)
        self.assertIn("自己責任", JA)

    def test_has_required_sections(self):
        titles = h2(EN)
        for name in SECTIONS:
            self.assertIn(name, titles)

    def test_links_between_languages(self):
        self.assertIn("README.ja.md", EN)
        self.assertIn("README.md", JA)

    def test_japanese_has_same_sections(self):
        self.assertEqual(len(h2(EN)), len(h2(JA)))

    def test_maintenance_links_runbook(self):
        self.assertIn(RUNBOOK, EN)
        self.assertIn(RUNBOOK, JA)
        self.assertTrue((ROOT / RUNBOOK).is_file())

    def test_internal_anchors_exist_and_are_unique(self):
        for name in ("README.ja.md", RUNBOOK):
            text = (ROOT / name).read_text(encoding="utf-8") if (ROOT / name).exists() else ""
            anchors = re.findall(r'<a name="([^"]+)"></a>', text)
            self.assertEqual(len(anchors), len(set(anchors)), name)
            for target in re.findall(r"\]\(#([^)]+)\)", text):
                self.assertIn(target, anchors, name)


if __name__ == "__main__":
    unittest.main()
