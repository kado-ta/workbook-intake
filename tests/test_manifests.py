import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

XLIDE_ARGS = [
    "--no-config",
    "--from", "xlide-mcp==1.2.4",
    "--with", "pyopenvba==6.6.0",
    "--with", "pyofficeeditor==0.4.1",
    "--with", "pyvbaanalysis==3.0.3",
    "--with", "mcp==2.3.0",
    "xlide-mcp", "--root", "${WORKBOOK_INTAKE_DIR:-~/workbook-intake}", "--read-only",
]
XLIDE_ENV = {"XLIDE_MCP_ALLOW_OUTSIDE_ROOTS": "0"}


def load_json(relative_path):
    with open(ROOT / relative_path, encoding="utf-8") as f:
        return json.load(f)


def without_root_value(args):
    i = args.index("--root")
    return args[: i + 1] + args[i + 2:]


class ManifestTest(unittest.TestCase):
    def test_plugin_json(self):
        p = load_json(".claude-plugin/plugin.json")
        self.assertEqual(p["name"], "workbook-intake")
        self.assertEqual(p["license"], "MIT")
        self.assertEqual(p["engines"], {"claude-code": ">=2.1.295"})

    def test_marketplace_json(self):
        m = load_json(".claude-plugin/marketplace.json")
        self.assertEqual(m["name"], "workbook-intake")
        self.assertEqual([(x["name"], x["source"]) for x in m["plugins"]], [("workbook-intake", "./")])

    def test_mcp_json_pins_versions_and_read_only(self):
        s = load_json(".mcp.json")["mcpServers"]
        self.assertEqual(list(s), ["xlide"])
        self.assertEqual(s["xlide"]["command"], "uvx")
        self.assertEqual(s["xlide"]["args"], XLIDE_ARGS)
        self.assertEqual(s["xlide"]["env"], XLIDE_ENV)

    def test_dependabot_mirror_matches_mcp_json(self):
        pins = {XLIDE_ARGS[i + 1] for i, a in enumerate(XLIDE_ARGS) if a in ("--from", "--with")}
        lines = (ROOT / "deps/requirements.txt").read_text(encoding="utf-8").splitlines()
        mirror = {l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")}
        self.assertEqual(mirror, pins)

    def test_probe_pins_match_plugin(self):
        probe = load_json("dev/probe/workbook-intake/.mcp.json")["mcpServers"]["xlide"]
        self.assertEqual(without_root_value(probe["args"]), without_root_value(XLIDE_ARGS))
        self.assertEqual(probe["env"], XLIDE_ENV)
