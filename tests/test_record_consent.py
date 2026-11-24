import copy
import io
import json
import os
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

import intake_common as ic  # noqa: E402
import record_consent as rc  # noqa: E402
from tests.workbook_factory import minimal_parts, write_workbook  # noqa: E402

PASS = {"status": "pass", "failures": [], "warnings": []}
SESSION = "session-1"
MARKER = "SECRETMARK"


def _sandbox_available():
    try:
        r = subprocess.run(
            ["/usr/bin/sandbox-exec", "-n", "no-network", "/usr/bin/true"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=10,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


REQUIRE = os.environ.get("WORKBOOK_INTAKE_REQUIRE_SANDBOX") == "1"


def consent_input(path, answer=ic.CONFIRM_LABEL, session=SESSION, questions=None):
    qs = questions if questions is not None else ic.expected_questions(path)
    return {
        "session_id": session,
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": qs},
        "tool_response": {"answers": {ic.consent_question(path): answer}},
    }


def warnings_input(path, warnings, answer=ic.CONTINUE_LABEL, session=SESSION, asked=None):
    asked = warnings if asked is None else asked
    question = ic.warnings_question(path, asked)
    return {
        "session_id": session,
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": ic.expected_warnings_questions(path, asked)},
        "tool_response": {"answers": {question: answer}},
    }


@unittest.skipUnless(sys.platform == "darwin", "hook tests are macOS-only")
class RecordConsentTest(unittest.TestCase):
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
        patcher = mock.patch.object(ic, "run_checker", return_value=dict(PASS))
        self.checker = patcher.start()
        self.addCleanup(patcher.stop)

    def book(self, name="book.xlsx", parts=None):
        return write_workbook(os.path.join(self.intake, name), parts or minimal_parts())

    def recorded(self, path, session=SESSION):
        real = os.path.realpath(path)
        return ic.find_consent(session, ic.file_key(real), ic.file_sha256(real))

    def test_records_confirmed_answer(self):
        path = self.book()
        out = rc.handle(consent_input(path))
        self.assertTrue(out.startswith("workbook-intake: consent=recorded"))
        rec = self.recorded(path)
        self.assertEqual(rec["kind"], "consent")
        self.assertEqual(rec["status"], "pass")
        mode = os.stat(os.path.join(self.data, "consents")).st_mode & 0o777
        self.assertEqual(mode, 0o700)

    def test_returns_check_result(self):
        path = self.book()
        self.checker.return_value = {"status": "pass", "failures": [], "warnings": ["vba_project"]}
        self.assertEqual(
            rc.handle(consent_input(path)),
            "workbook-intake: consent=recorded; check=pass; failures=none; warnings=vba_project",
        )

    def test_failed_check_is_recorded_and_reported(self):
        path = self.book()
        self.checker.return_value = {"status": "fail", "failures": ["xml_dtd"], "warnings": []}
        out = rc.handle(consent_input(path))
        self.assertIn("check=fail; failures=xml_dtd", out)
        self.assertEqual(self.recorded(path)["status"], "fail")

    def test_cancel_not_recorded(self):
        path = self.book()
        out = rc.handle(consent_input(path, answer=ic.CANCEL_LABEL))
        self.assertEqual(out, "workbook-intake: consent=not_recorded; reason=not_confirmed")
        self.assertIsNone(self.recorded(path))

    def test_altered_question_not_recorded(self):
        path = self.book()
        qs = ic.expected_questions(path)
        qs[0]["question"] = qs[0]["question"].replace("Before", "before", 1)
        out = rc.handle(consent_input(path, questions=qs))
        self.assertEqual(out, "workbook-intake: consent=not_recorded; reason=question_mismatch")
        self.assertIsNone(self.recorded(path))

    def test_altered_options_not_recorded(self):
        path = self.book()
        base = ic.expected_questions(path)
        variants = []
        v = copy.deepcopy(base)
        v[0]["options"][0]["description"] += " "
        variants.append(v)
        v = copy.deepcopy(base)
        v[0]["options"].append({"label": "Other", "description": "x"})
        variants.append(v)
        v = copy.deepcopy(base)
        v[0]["multiSelect"] = True
        variants.append(v)
        v = copy.deepcopy(base)
        v.append(copy.deepcopy(base[0]))
        variants.append(v)
        for qs in variants:
            out = rc.handle(consent_input(path, questions=qs))
            if len(qs) == 1:
                self.assertEqual(
                    out, "workbook-intake: consent=not_recorded; reason=question_mismatch")
            else:
                self.assertIsNone(out)
            self.assertIsNone(self.recorded(path))

    def test_path_outside_intake_not_recorded(self):
        outside = write_workbook(os.path.join(self.home, "other.xlsx"), minimal_parts())
        out = rc.handle(consent_input(outside))
        self.assertEqual(out, "workbook-intake: consent=not_recorded; reason=outside_intake")

    def test_relative_path_not_recorded(self):
        out = rc.handle(consent_input("book.xlsx"))
        self.assertEqual(out, "workbook-intake: consent=not_recorded; reason=path_not_absolute")

    def test_missing_file_reported(self):
        out = rc.handle(consent_input(os.path.join(self.intake, "none.xlsx")))
        self.assertEqual(out, "workbook-intake: consent=not_recorded; reason=not_regular_file")

    def test_other_tool_not_recorded(self):
        path = self.book()
        data = consent_input(path)
        data["tool_name"] = "Bash"
        self.assertIsNone(rc.handle(data))
        self.assertIsNone(self.recorded(path))

    def test_other_question_produces_no_output(self):
        data = {
            "session_id": SESSION,
            "tool_name": "AskUserQuestion",
            "tool_input": {"questions": [{"question": "Which color?", "header": "c",
                                          "options": [], "multiSelect": False}]},
            "tool_response": {"answers": {"Which color?": "red"}},
        }
        self.assertIsNone(rc.handle(data))

    def test_malformed_input_not_recorded(self):
        path = self.book()
        for bad in (None, [], "x", {}, {"tool_name": "AskUserQuestion"},
                    {"tool_name": "AskUserQuestion", "tool_input": {"questions": "x"}},
                    {"tool_name": "AskUserQuestion", "tool_input": {"questions": [1]}}):
            self.assertIsNone(rc.handle(bad))
        data = consent_input(path)
        data["tool_response"] = "oops"
        self.assertEqual(rc.handle(data),
                         "workbook-intake: consent=not_recorded; reason=not_confirmed")
        data = consent_input(path)
        data["session_id"] = 5
        self.assertEqual(rc.handle(data),
                         "workbook-intake: consent=not_recorded; reason=bad_input")
        self.assertIsNone(self.recorded(path))
        for raw in ("not json", "[]", ""):
            out = io.StringIO()
            with mock.patch.object(sys, "stdin", io.StringIO(raw)), \
                    mock.patch.object(sys, "stdout", out):
                self.assertEqual(rc.main(), 0)
            self.assertEqual(out.getvalue(), "")

    def test_main_prints_additional_context(self):
        path = self.book()
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(consent_input(path)))), \
                mock.patch.object(sys, "stdout", out):
            self.assertEqual(rc.main(), 0)
        body = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(body["hookEventName"], "PostToolUse")
        self.assertIn("consent=recorded", body["additionalContext"])

    def test_internal_error_reported(self):
        path = self.book()
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(consent_input(path)))), \
                mock.patch.object(sys, "stdout", out), \
                mock.patch.object(ic, "run_checker", side_effect=RuntimeError("boom")):
            self.assertEqual(rc.main(), 0)
        text = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(text, "workbook-intake: consent=not_recorded; reason=internal_error")

    def test_missing_plugin_data_not_recorded(self):
        path = self.book()
        del os.environ["CLAUDE_PLUGIN_DATA"]
        out = rc.handle(consent_input(path))
        self.assertEqual(out,
                         "workbook-intake: consent=not_recorded; reason=consent_store_unavailable")

    def test_nfd_and_nfc_paths_are_same_file(self):
        nfd = unicodedata.normalize("NFD", "ガイド.xlsx")
        nfc = unicodedata.normalize("NFC", "ガイド.xlsx")
        self.assertNotEqual(nfd, nfc)
        nfd_path = self.book(name=nfd)
        nfc_path = os.path.join(self.intake, nfc)
        out = rc.handle(consent_input(nfc_path))
        self.assertIn("consent=recorded", out)
        self.assertIsNotNone(self.recorded(nfd_path))

    def test_consent_is_per_session(self):
        path = self.book()
        rc.handle(consent_input(path))
        self.assertIsNone(self.recorded(path, session="other"))

    def test_consent_is_per_content(self):
        path = self.book()
        rc.handle(consent_input(path))
        parts = minimal_parts()
        parts["docProps/extra.xml"] = b"<x/>"
        write_workbook(path, parts)
        self.assertIsNone(self.recorded(path))

    def test_warnings_ack_recorded(self):
        path = self.book()
        self.checker.return_value = {"status": "pass", "failures": [], "warnings": ["vba_project"]}
        rc.handle(consent_input(path))
        out = rc.handle(warnings_input(path, ["vba_project"]))
        self.assertEqual(out, "workbook-intake: warnings_ack=recorded")
        real = os.path.realpath(path)
        self.assertTrue(ic.has_warnings_ack(
            SESSION, ic.file_key(real), ic.file_sha256(real), ["vba_project"]))
        self.assertFalse(ic.has_warnings_ack(
            SESSION, ic.file_key(real), ic.file_sha256(real), ["hidden_sheet"]))

    def test_warnings_ack_with_other_warnings_not_recorded(self):
        path = self.book()
        self.checker.return_value = {"status": "pass", "failures": [], "warnings": ["vba_project"]}
        rc.handle(consent_input(path))
        out = rc.handle(warnings_input(path, ["vba_project"], asked=["hidden_sheet"]))
        self.assertEqual(out, "workbook-intake: warnings_ack=not_recorded; reason=question_mismatch")

    def test_warnings_ack_without_consent_not_recorded(self):
        path = self.book()
        out = rc.handle(warnings_input(path, ["vba_project"]))
        self.assertEqual(out, "workbook-intake: warnings_ack=not_recorded; reason=no_consent")

    def test_warnings_ack_stop_not_recorded(self):
        path = self.book()
        self.checker.return_value = {"status": "pass", "failures": [], "warnings": ["vba_project"]}
        rc.handle(consent_input(path))
        out = rc.handle(warnings_input(path, ["vba_project"], answer=ic.STOP_LABEL))
        self.assertEqual(out, "workbook-intake: warnings_ack=not_recorded; reason=not_confirmed")

    def test_context_has_no_file_derived_strings(self):
        path = self.book(name=MARKER + ".xlsx")
        for data in (consent_input(path), consent_input(path, answer=ic.CANCEL_LABEL),
                     consent_input(os.path.join(self.home, MARKER + ".xlsx")),
                     consent_input("/" + MARKER + "/x.xlsx"),
                     warnings_input(path, ["vba_project"])):
            out = rc.handle(data)
            self.assertNotIn(MARKER, out)


class WrapperTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "hook tests are macOS-only")
    def test_wrapper_end_to_end(self):
        if not _sandbox_available():
            if REQUIRE:
                self.fail("sandbox-exec is unavailable but WORKBOOK_INTAKE_REQUIRE_SANDBOX=1")
            self.skipTest("sandbox-exec cannot nest inside Claude's Bash sandbox")
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.realpath(tmp)
            intake = os.path.join(home, "workbook-intake")
            os.mkdir(intake)
            path = write_workbook(os.path.join(intake, "book.xlsx"), minimal_parts())
            env = {"HOME": home, "CLAUDE_PLUGIN_DATA": os.path.join(home, "data"),
                   "PATH": "/usr/bin:/bin"}
            r = subprocess.run(
                ["/bin/bash", str(ROOT / "hooks" / "record-consent.sh")],
                input=json.dumps(consent_input(path)).encode(), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            body = json.loads(r.stdout.decode())["hookSpecificOutput"]
            self.assertEqual(body["hookEventName"], "PostToolUse")
            self.assertIn("consent=recorded; check=pass", body["additionalContext"])
            consents = os.path.join(home, "data", "consents")
            self.assertEqual(len(os.listdir(consents)), 1)


if __name__ == "__main__":
    unittest.main()
