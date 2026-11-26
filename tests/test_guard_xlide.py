import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT))

import guard_xlide as gx  # noqa: E402
import intake_common as ic  # noqa: E402
from tests.test_record_consent import REQUIRE, _sandbox_available, write_path_shims  # noqa: E402
from tests.workbook_factory import minimal_parts, write_workbook  # noqa: E402

PASS = {"status": "pass", "failures": [], "warnings": []}
SESSION = "session-1"
MARKER = "SECRETMARK"
READ_TOOL = gx.TOOL_PREFIX + "xlide_list_sheets"


def call(path=None, tool=READ_TOOL, agent=gx.ANALYST_AGENT_TYPE, session=SESSION,
         extra=None, server=None):
    tool_input = {} if path is None else {"file_path": path}
    tool_input.update(extra or {})
    data = {"session_id": session, "hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": tool_input}
    if agent is not None:
        data["agent_type"] = agent
    if server is not None:
        data["mcp_server"] = server
    return data


@unittest.skipUnless(sys.platform == "darwin", "hook tests are macOS-only")
class GuardXlideTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = os.path.realpath(tmp.name)
        self.data = os.path.join(self.home, "plugin-data")
        self.intake = os.path.join(self.home, "workbook-intake")
        os.mkdir(self.intake)
        env = mock.patch.dict(os.environ, {"HOME": self.home, "CLAUDE_PLUGIN_DATA": self.data})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("WORKBOOK_INTAKE_DIR", None)
        os.environ.pop("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", None)
        self.patcher = mock.patch.object(ic, "run_checker", return_value=dict(PASS))
        self.checker = self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def book(self, name="book.xlsx", parts=None):
        return write_workbook(os.path.join(self.intake, name), parts or minimal_parts())

    def consent(self, path, check=None):
        real = os.path.realpath(path)
        self.assertTrue(ic.record_consent(
            SESSION, ic.file_key(real), ic.file_sha256(real), check or dict(PASS)))

    def consented(self, name="book.xlsx", parts=None):
        path = self.book(name, parts)
        self.consent(path)
        return path

    def ack(self, path, warnings):
        real = os.path.realpath(path)
        self.assertTrue(ic.record_warnings_ack(
            SESSION, ic.file_key(real), ic.file_sha256(real), warnings))

    def assertDenied(self, hook_input, reason):
        self.assertEqual(gx.decide(hook_input), ("deny", reason))

    # allow paths

    def test_allows_consented_file_with_clean_check(self):
        path = self.consented()
        self.assertEqual(gx.decide(call(path)), ("allow", "ok"))

    def test_nofile_tool_allowed_for_analyst(self):
        data = call(tool=gx.TOOL_PREFIX + "xlide_doctor")
        self.assertEqual(gx.decide(data), ("allow", "ok"))

    def test_uppercase_extension_allowed(self):
        path = self.consented("BOOK.XLSX")
        self.assertEqual(gx.decide(call(path)), ("allow", "ok"))

    def test_consent_matches_across_unicode_normalization(self):
        name = unicodedata.normalize("NFC", "café.xlsx")
        path = self.book(name)
        self.consent(path)
        nfd = os.path.join(self.intake, unicodedata.normalize("NFD", name))
        self.assertEqual(gx.decide(call(nfd)), ("allow", "ok"))

    def test_symlink_alias_denied(self):
        # xlide strips the path before resolving it, so "b.xlsm " opens b.xlsm while the
        # guard resolves the symlink to a.xlsx, which has consent and a passing check.
        target = self.consented("a.xlsx")
        self.book("b.xlsm")
        alias = os.path.join(self.intake, "b.xlsm ")
        os.symlink(target, alias)
        self.assertDenied(call(alias), "path_not_canonical")

    def test_trailing_space_file_denied(self):
        # A regular file whose name ends in a space has no supported extension, so it is
        # stopped before the canonical-path check; either way it is never allowed.
        path = self.consented("c.xlsx ")
        self.assertDenied(call(path), "unsupported_extension")

    def test_template_extensions_denied(self):
        for name in ("t.xltx", "t.xltm"):
            with self.subTest(name=name):
                path = self.consented(name)
                self.assertDenied(call(path), "unsupported_extension")

    def test_xlide_list_shapes_not_allowed(self):
        path = self.consented()
        self.assertDenied(call(path, tool=gx.TOOL_PREFIX + "xlide_list_shapes"),
                          "tool_not_allowed")

    def test_warnings_with_ack_allowed(self):
        path = self.consented()
        self.checker.return_value = {"status": "pass", "failures": [], "warnings": ["vba_project"]}
        self.ack(path, ["vba_project"])
        self.assertEqual(gx.decide(call(path)), ("allow", "ok"))

    # caller, server and tool

    def test_denies_non_plugin_xlide(self):
        self.assertDenied(call(tool="mcp__xlide__xlide_doctor"), "not_plugin_server")

    def test_denies_wrong_server_name_and_source(self):
        path = self.consented()
        good = {"name": "plugin:workbook-intake:xlide", "source": "plugin"}
        self.assertEqual(gx.decide(call(path, server=good)), ("allow", "ok"))
        for server in ({"name": "xlide", "source": "plugin"},
                       {"name": "plugin:workbook-intake:xlide", "source": "user"},
                       {"name": "plugin:workbook-intake:xlide"}, "plugin", None):
            data = call(path)
            data["mcp_server"] = server
            self.assertDenied(data, "not_plugin_server")

    def test_absent_mcp_server_relies_on_prefix(self):
        data = call(tool=gx.TOOL_PREFIX + "xlide_doctor")
        self.assertNotIn("mcp_server", data)
        self.assertEqual(gx.decide(data), ("allow", "ok"))

    def test_denies_tool_not_in_allowlist(self):
        path = self.consented()
        self.assertDenied(call(path, tool=gx.TOOL_PREFIX + "xlide_write_cells"),
                          "tool_not_allowed")

    def test_denies_main_conversation(self):
        path = self.consented()
        self.assertDenied(call(path, agent=None), "wrong_caller")
        self.assertDenied(call(path, agent="other:agent"), "wrong_caller")

    # arguments

    def test_calculate_denied(self):
        path = self.consented()
        for value in (True, "true", 1, None):
            self.assertDenied(call(path, extra={"calculate": value}), "calculation_not_allowed")

    def test_calculate_denied_before_consent(self):
        path = self.book()
        self.assertDenied(call(path, extra={"calculate": True}), "calculation_not_allowed")

    def test_calculate_false_passes_on(self):
        path = self.consented()
        self.assertEqual(gx.decide(call(path, extra={"calculate": False})), ("allow", "ok"))

    def test_regex_denied(self):
        path = self.consented()
        for value in (True, "true", 1, None):
            self.assertDenied(call(path, extra={"is_regex": value}), "regex_not_allowed")

    def test_regex_denied_before_consent(self):
        path = self.book()
        self.assertDenied(call(path, extra={"is_regex": True}), "regex_not_allowed")

    def test_regex_false_passes_on(self):
        path = self.consented()
        self.assertEqual(gx.decide(call(path, extra={"is_regex": False})), ("allow", "ok"))

    def test_query_too_long_denied(self):
        path = self.book()
        self.assertDenied(call(path, extra={"query": "a" * 257}), "query_too_long")

    def test_query_at_limit_passes_on(self):
        path = self.consented()
        self.assertEqual(gx.decide(call(path, extra={"query": "a" * 256})), ("allow", "ok"))

    def test_agent_teams_denied(self):
        path = self.consented()
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}):
            self.assertDenied(call(path), "agent_teams_enabled")

    def test_agent_teams_empty_passes_on(self):
        path = self.consented()
        self.assertEqual(gx.decide(call(path)), ("allow", "ok"))
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": ""}):
            self.assertEqual(gx.decide(call(path)), ("allow", "ok"))

    def test_analyze_not_allowed(self):
        path = self.consented()
        self.assertDenied(call(path, tool=gx.TOOL_PREFIX + "xlide_analyze"), "tool_not_allowed")

    def test_rules_not_allowed(self):
        self.assertDenied(call(tool=gx.TOOL_PREFIX + "xlide_rules"), "tool_not_allowed")

    def test_check_cells_not_allowed(self):
        path = self.consented()
        self.assertDenied(call(path, tool=gx.TOOL_PREFIX + "xlide_check_cells"),
                          "tool_not_allowed")

    def test_evaluate_formula_not_allowed(self):
        path = self.consented()
        self.assertDenied(call(path, tool=gx.TOOL_PREFIX + "xlide_evaluate_formula"),
                          "tool_not_allowed")

    def test_extra_path_argument_denied(self):
        path = self.consented()
        for key in ("output_path", "directory", "Folder", "root", "source_file"):
            self.assertDenied(call(path, extra={key: "/tmp/x"}), "unexpected_path_argument")

    def test_missing_file_path_denied(self):
        self.assertDenied(call(), "missing_file_path")

    def test_non_dict_tool_input_denied(self):
        data = call()
        data["tool_input"] = ["x"]
        self.assertDenied(data, "bad_input")

    def test_non_string_file_path_denied(self):
        self.assertDenied(call(["a"]), "bad_input")
        self.assertDenied(call(5), "bad_input")

    def test_relative_path_denied(self):
        self.assertDenied(call("book.xlsx"), "path_not_absolute")

    def test_outside_intake_denied(self):
        outside = write_workbook(os.path.join(self.home, "o.xlsx"), minimal_parts())
        self.assertDenied(call(outside), "outside_intake")

    def test_symlink_to_outside_denied(self):
        outside = write_workbook(os.path.join(self.home, "o.xlsx"), minimal_parts())
        link = os.path.join(self.intake, "l.xlsx")
        os.symlink(outside, link)
        self.assertDenied(call(link), "outside_intake")

    def test_intake_dir_symlink_denied(self):
        real = os.path.join(self.home, "real")
        os.mkdir(real)
        write_workbook(os.path.join(real, "b.xlsx"), minimal_parts())
        os.rmdir(self.intake)
        os.symlink(real, self.intake)
        self.assertDenied(call(os.path.join(self.intake, "b.xlsx")), "intake_dir_invalid")

    def test_directory_denied(self):
        d = os.path.join(self.intake, "d.xlsx")
        os.mkdir(d)
        self.assertDenied(call(d), "not_regular_file")

    def test_oversized_file_denied_before_hashing(self):
        path = self.book()
        with mock.patch.object(ic, "MAX_FILE_BYTES", 10), \
                mock.patch.object(ic, "file_sha256", side_effect=AssertionError("hashed")):
            self.assertDenied(call(path), "file_too_large")

    # consent and check

    def test_no_consent_denied(self):
        path = self.book()
        self.assertDenied(call(path), "no_consent")
        self.checker.assert_not_called()

    def test_consent_store_unavailable_denied(self):
        path = self.consented()
        with mock.patch.dict(os.environ):
            os.environ.pop("CLAUDE_PLUGIN_DATA")
            self.assertDenied(call(path), "consent_store_unavailable")

    def test_changed_content_after_consent_denied(self):
        path = self.consented()
        write_workbook(path, dict(minimal_parts(), **{"xl/extra.xml": b"<a/>"}))
        self.assertDenied(call(path), "no_consent")

    def test_check_failure_reports_codes(self):
        path = self.consented()
        self.checker.return_value = {"status": "fail", "failures": ["xml_dtd"], "warnings": []}
        data = gx.decide_detail(call(path))
        self.assertEqual(data, ("deny", "check_failed", ["xml_dtd"]))
        self.assertIn("(xml_dtd)", json.loads(gx._output(*data))["hookSpecificOutput"]
                      ["permissionDecisionReason"])

    def test_failed_check_denied_despite_consent_and_ack(self):
        path = self.consented()
        self.ack(path, ["vba_project"])
        self.checker.return_value = {"status": "fail", "failures": ["xml_dtd"],
                                     "warnings": ["vba_project"]}
        self.assertDenied(call(path), "check_failed")

    def test_checker_error_denied(self):
        path = self.consented()
        for status, reason in (("error", "check_error"), ("sandbox_missing", "sandbox_missing"),
                               ("timeout", "check_timeout"), ("weird", "check_error")):
            self.checker.return_value = {"status": status, "failures": [], "warnings": []}
            self.assertDenied(call(path), reason)

    def test_warnings_without_ack_denied(self):
        path = self.consented()
        self.checker.return_value = {"status": "pass", "failures": [], "warnings": ["vba_project"]}
        detail = gx.decide_detail(call(path))
        self.assertEqual(detail, ("deny", "warnings_not_acknowledged", ["vba_project"]))
        self.assertIn("(vba_project)", json.loads(gx._output(*detail))["hookSpecificOutput"]
                      ["permissionDecisionReason"])

    def test_malformed_pass_result_denied(self):
        path = self.consented()
        for check in ({"status": "pass", "failures": [], "warnings": ["not-a-code"]},
                      {"status": "pass", "failures": [], "warnings": "vba_project"},
                      {"status": "pass", "failures": [], "warnings": [5]},
                      {"status": "pass", "failures": ["xml_dtd"], "warnings": []},
                      {"status": "pass", "warnings": []},
                      {"status": "pass", "failures": []}):
            self.checker.return_value = check
            self.assertDenied(call(path), "check_error")

    def test_file_changed_during_check_denied(self):
        path = self.consented()

        def change(real, *args, **kwargs):
            write_workbook(real, dict(minimal_parts(), **{"xl/extra.xml": b"<a/>"}))
            return dict(PASS)

        self.checker.side_effect = change
        self.assertDenied(call(path), "check_error")

    def test_type_confusion_denied(self):
        path = self.consented()
        self.assertDenied(call(path, agent=[gx.ANALYST_AGENT_TYPE]), "wrong_caller")
        for session in (None, 5, ["s"], ""):
            data = call(path, session=session)
            self.assertEqual(gx.decide(data)[0], "deny")
        data = call(path)
        del data["session_id"]
        self.assertEqual(gx.decide(data)[0], "deny")
        for key in ("filePath", "FILE_PATH"):
            self.assertDenied(call(path, extra={key: path}), "unexpected_path_argument")

    def test_ack_for_other_warnings_denied(self):
        path = self.consented()
        self.ack(path, ["external_link"])
        self.checker.return_value = {"status": "pass", "failures": [], "warnings": ["vba_project"]}
        self.assertDenied(call(path), "warnings_not_acknowledged")

    # real checker (needs a nested sandbox)

    def _need_sandbox(self):
        if not _sandbox_available():
            if REQUIRE:
                self.fail("sandbox-exec is unavailable but WORKBOOK_INTAKE_REQUIRE_SANDBOX=1")
            self.skipTest("sandbox-exec cannot nest inside Claude's Bash sandbox")

    def test_allows_consented_checked_file(self):
        self._need_sandbox()
        self.patcher.stop()
        path = self.book()
        self.consent(path)
        self.assertEqual(gx.decide(call(path)), ("allow", "ok"))

    def test_check_failure_denied(self):
        self._need_sandbox()
        self.patcher.stop()
        path = self.book("bomb.xlsx", dict(minimal_parts(),
                                            **{"xl/media/zeros.bin": b"\x00" * (2 * 1024 * 1024)}))
        self.consent(path)
        detail = gx.decide_detail(call(path))
        self.assertEqual(detail[:2], ("deny", "check_failed"))
        self.assertIn("compression_ratio_too_high", detail[2])

    def test_check_timeout_denied(self):
        self._need_sandbox()
        self.patcher.stop()
        path = self.book()
        self.consent(path)
        with mock.patch.object(ic, "CHECK_TIMEOUT_SECONDS", 0.001):
            self.assertDenied(call(path), "check_timeout")

    # main and wrapper

    def run_main(self, stdin_text):
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(stdin_text)), \
                mock.patch.object(sys, "stdout", out):
            code = gx.main()
        return code, out.getvalue()

    def test_malformed_input_denied(self):
        for text in ("", "not json", "[]", "null", "5"):
            code, out = self.run_main(text)
            self.assertEqual(code, 0)
            body = json.loads(out)["hookSpecificOutput"]
            self.assertEqual(body["permissionDecision"], "deny")
            self.assertIn("workbook-intake: bad_input", body["permissionDecisionReason"])

    def test_internal_error_denied(self):
        path = self.consented()
        with mock.patch.object(gx, "decide_detail", side_effect=RuntimeError("boom")):
            code, out = self.run_main(json.dumps(call(path)))
        self.assertEqual(code, 0)
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(body["permissionDecision"], "deny")
        self.assertIn("workbook-intake: internal_error", body["permissionDecisionReason"])

    def test_allow_output_shape(self):
        code, out = self.run_main(json.dumps(call(tool=gx.TOOL_PREFIX + "xlide_doctor")))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "allow",
            "permissionDecisionReason":
                "workbook-intake: ok. See the README (Troubleshooting)."}})

    def test_wrapper_denies_without_python(self):
        env = {"HOME": self.home, "PATH": "/usr/bin:/bin",
               "DEVELOPER_DIR": os.path.join(self.home, "missing")}
        r = subprocess.run(["/bin/bash", str(ROOT / "hooks" / "guard-xlide.sh")],
                           input=b"{}", env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = json.loads(r.stdout.decode())["hookSpecificOutput"]
        self.assertEqual(body["permissionDecision"], "deny")
        self.assertIn("workbook-intake: python_missing", body["permissionDecisionReason"])

    def test_wrapper_end_to_end_denies_main_conversation(self):
        env = {"HOME": self.home, "CLAUDE_PLUGIN_DATA": self.data, "PATH": "/usr/bin:/bin"}
        data = call(tool=gx.TOOL_PREFIX + "xlide_doctor", agent=None)
        r = subprocess.run(["/bin/bash", str(ROOT / "hooks" / "guard-xlide.sh")],
                           input=json.dumps(data).encode(), env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = json.loads(r.stdout.decode())["hookSpecificOutput"]
        self.assertEqual(body["permissionDecision"], "deny")
        self.assertIn("workbook-intake: wrong_caller", body["permissionDecisionReason"])

    def test_configured_command_ignores_bash_env(self):
        # hooks.json runs the wrapper with bash -p, so a BASH_ENV file is not sourced.
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"]
        command = hooks[0]["hooks"][0]["command"]
        argv = shlex.split(command.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)))
        self.assertEqual(argv[:2], ["/bin/bash", "-p"])
        data = json.dumps(call(tool=gx.TOOL_PREFIX + "xlide_doctor", agent=None)).encode()
        with tempfile.TemporaryDirectory() as tmp:
            marker = os.path.join(tmp, "ran")
            rc_file = os.path.join(tmp, "bash_env.sh")
            with open(rc_file, "w") as f:
                f.write(": > '%s'\n" % marker)
            env = {"HOME": self.home, "CLAUDE_PLUGIN_DATA": self.data,
                   "PATH": "/usr/bin:/bin", "BASH_ENV": rc_file}
            r = subprocess.run(argv, input=data, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=60)
            self.assertFalse(os.path.exists(marker), "BASH_ENV ran under bash -p")
            self.assertIn(b"workbook-intake: wrong_caller", r.stdout)
            # Control: without -p the same BASH_ENV does run.
            subprocess.run(["/bin/bash", argv[2]], input=data, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60)
            self.assertTrue(os.path.exists(marker), "BASH_ENV did not run without -p")

    def test_wrapper_ignores_commands_on_path(self):
        # A directory early in PATH may be writable from Claude's sandbox; the hook
        # runs outside it, so it must not run any command found there.
        with tempfile.TemporaryDirectory() as tmp:
            marker = write_path_shims(tmp)
            env = {"HOME": self.home, "CLAUDE_PLUGIN_DATA": self.data,
                   "PATH": os.path.join(tmp, "bin") + ":/usr/bin:/bin"}
            data = call(tool=gx.TOOL_PREFIX + "xlide_doctor", agent=None)
            r = subprocess.run(["/bin/bash", str(ROOT / "hooks" / "guard-xlide.sh")],
                               input=json.dumps(data).encode(), env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            self.assertFalse(os.path.exists(marker), "a command from PATH ran")
        body = json.loads(r.stdout.decode())["hookSpecificOutput"]
        self.assertIn("workbook-intake: wrong_caller", body["permissionDecisionReason"])

    def test_wrapper_denies_when_python_fails(self):
        env = {"HOME": self.home, "PATH": "/usr/bin:/bin"}
        with tempfile.TemporaryDirectory() as tmp:
            here = os.path.join(tmp, "hooks")
            os.mkdir(here)
            with open(ROOT / "hooks" / "guard-xlide.sh", "rb") as f:
                script = f.read()
            with open(os.path.join(here, "guard-xlide.sh"), "wb") as f:
                f.write(script)
            with open(os.path.join(here, "guard_xlide.py"), "w") as f:
                f.write("raise SystemExit(3)\n")
            r = subprocess.run(["/bin/bash", os.path.join(here, "guard-xlide.sh")],
                               input=b"{}", env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = json.loads(r.stdout.decode())["hookSpecificOutput"]
        self.assertEqual(body["permissionDecision"], "deny")
        self.assertIn("workbook-intake: internal_error", body["permissionDecisionReason"])

    def test_wrapper_denies_when_python_prints_nothing(self):
        env = {"HOME": self.home, "PATH": "/usr/bin:/bin"}
        with tempfile.TemporaryDirectory() as tmp:
            here = os.path.join(tmp, "hooks")
            os.mkdir(here)
            with open(ROOT / "hooks" / "guard-xlide.sh", "rb") as f:
                script = f.read()
            with open(os.path.join(here, "guard-xlide.sh"), "wb") as f:
                f.write(script)
            with open(os.path.join(here, "guard_xlide.py"), "w") as f:
                f.write("pass\n")
            r = subprocess.run(["/bin/bash", os.path.join(here, "guard-xlide.sh")],
                               input=b"{}", env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        body = json.loads(r.stdout.decode())["hookSpecificOutput"]
        self.assertEqual(body["permissionDecision"], "deny")
        self.assertIn("workbook-intake: internal_error", body["permissionDecisionReason"])

    def test_reason_has_no_file_derived_strings(self):
        name = "%s.xlsx" % MARKER
        path = self.book(name)
        for check in ({"status": "fail", "failures": ["xml_dtd", MARKER], "warnings": [MARKER]},
                      {"status": "pass", "failures": [], "warnings": ["vba_project", MARKER]},
                      dict(PASS)):
            self.checker.return_value = check
            for target in (path, os.path.join(self.intake, MARKER, "x.xlsx"), path + MARKER):
                code, out = self.run_main(json.dumps(call(target)))
                self.assertEqual(code, 0)
                self.assertNotIn(MARKER, out)
        # Even a consented file with marker-bearing check output stays clean.
        self.consent(path)
        self.checker.return_value = {"status": "fail", "failures": [MARKER], "warnings": [MARKER]}
        _, out = self.run_main(json.dumps(call(path)))
        self.assertNotIn(MARKER, out)


class ManifestTest(unittest.TestCase):
    def test_matcher_covers_plugin_tools(self):
        pre = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"]
        matcher = pre[0]["matcher"]
        for name in ("mcp__plugin_workbook-intake_xlide__read_workbook", "mcp__other__xlide_doctor"):
            self.assertIsNotNone(re.fullmatch(matcher, name), name)
        self.assertIsNone(re.fullmatch(matcher, "mcp__other__read"))

    def test_hooks_json(self):
        data = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
        pre = data["PreToolUse"]
        self.assertEqual(len(pre), 1)
        self.assertEqual(pre[0]["matcher"],
                         "mcp__plugin_workbook-intake_xlide__.*|mcp__.*__xlide_.*")
        self.assertEqual(pre[0]["hooks"], [{
            "type": "command",
            "command": '/bin/bash -p "${CLAUDE_PLUGIN_ROOT}/hooks/guard-xlide.sh"',
            "timeout": 30, "onFailure": "block"}])
        post = data["PostToolUse"]
        self.assertEqual(len(post), 1)
        self.assertEqual(post[0]["matcher"], "AskUserQuestion")
        self.assertEqual(post[0]["hooks"], [{
            "type": "command",
            "command": '/bin/bash -p "${CLAUDE_PLUGIN_ROOT}/hooks/record-consent.sh"',
            "timeout": 30}])

    def test_allowlist_format(self):
        tools = gx.load_allowlist()
        expected = dict.fromkeys((
            "project_info", "validate_project", "list_modules", "read_module",
            "list_procedures", "search_modules", "list_references", "list_forms",
            "read_form", "list_queries", "read_query", "list_sheets", "read_cells",
            "page_setup"), "file")
        expected.update({"doctor": "nofile"})
        self.assertEqual(tools, {"xlide_" + k: v for k, v in expected.items()})

    def test_allowlist_reviewed_for_pinned_version(self):
        first = (ROOT / "hooks" / "allowed-tools.txt").read_text().splitlines()[0]
        self.assertTrue(first.startswith("# reviewed-for: "))
        reviewed = first[len("# reviewed-for: "):]
        args = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["xlide"]["args"]
        pinned = args[args.index("--from") + 1]
        self.assertEqual(reviewed, pinned)


if __name__ == "__main__":
    unittest.main()
