import importlib.util
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

    def test_japanese_sections_match_in_order(self):
        ja_anchors = re.findall(r'<a name="([^"]+)"></a>\n\n## ', JA)
        required = [name.lower() for name in SECTIONS]
        self.assertEqual([a for a in ja_anchors if a in required], required)
        en_order = [t for t in h2(EN) if t in SECTIONS]
        self.assertEqual(en_order, list(SECTIONS))

    def test_vocabulary_is_documented_in_both(self):
        spec = importlib.util.spec_from_file_location(
            "check_workbook", ROOT / "scripts" / "check_workbook.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        doctor = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
        items = re.findall(r"^\s*if .*; then report (\w+) 0;", doctor, flags=re.M)
        items += re.findall(r"report (intake_dir_protected) [01]", doctor)
        self.assertIn("uvx", items)
        codes = list(module.FAILURE_CODES) + list(module.WARNING_CODES) + items
        for name, text in (("README.md", EN), ("README.ja.md", JA)):
            for code in codes:
                self.assertIn("`%s`" % code, text, "%s: %s" % (name, code))

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
