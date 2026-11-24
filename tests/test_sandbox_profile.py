import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT))

import check_workbook  # noqa: E402
import intake_common  # noqa: E402
from tests.workbook_factory import minimal_parts, write_workbook  # noqa: E402

PROFILE = str(ROOT / "scripts" / "check_workbook.sb")


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


SANDBOX_OK = sys.platform == "darwin" and _sandbox_available()
REQUIRE = os.environ.get("WORKBOOK_INTAKE_REQUIRE_SANDBOX") == "1"


def needs_sandbox(cls):
    """Skip (or fail, when WORKBOOK_INTAKE_REQUIRE_SANDBOX=1) if sandbox-exec cannot run."""
    if SANDBOX_OK:
        return cls
    if REQUIRE:
        def setUp(self):
            self.fail("sandbox-exec is unavailable but WORKBOOK_INTAKE_REQUIRE_SANDBOX=1")
        cls.setUp = setUp
        return cls
    return unittest.skip("sandbox-exec cannot nest inside Claude's Bash sandbox")(cls)


@needs_sandbox
class RunCheckerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)

    def book(self, parts, name="book.xlsx"):
        return write_workbook(os.path.join(self.dir, name), parts)

    def test_checker_passes_in_sandbox(self):
        r = intake_common.run_checker(self.book(minimal_parts()))
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["warnings"], [])

    def test_checker_fail_maps_to_fail(self):
        parts = minimal_parts()
        parts["xl/worksheets/sheet1.xml"] = b"<!DOCTYPE x><x/>"
        r = intake_common.run_checker(self.book(parts))
        self.assertEqual(r["status"], "fail")
        self.assertEqual(r["failures"], ["xml_dtd"])

    def test_warnings_are_returned(self):
        parts = minimal_parts()
        parts["xl/workbook.xml"] = parts["xl/workbook.xml"].replace(
            b'sheetId="1"', b'sheetId="1" state="hidden"')
        r = intake_common.run_checker(self.book(parts))
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["warnings"], ["hidden_sheet"])

    def test_timeout_maps_to_timeout(self):
        r = intake_common.run_checker(self.book(minimal_parts()), timeout=0.001)
        self.assertEqual(r["status"], "timeout")


@needs_sandbox
class ProfileTest(unittest.TestCase):
    """Runs the profile directly, with a throwaway script as SELF that attempts one operation."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)
        self.target = os.path.join(self.dir, "target.bin")
        Path(self.target).write_bytes(b"x")
        self.other = os.path.join(self.dir, "other.txt")
        Path(self.other).write_text("secret")

    def attempt(self, body):
        script = os.path.join(self.dir, "probe.py")
        Path(script).write_text(
            "import sys\n" + body +
            "\nprint('ALLOWED')\n")
        home = os.path.realpath(sys.base_prefix)
        exe = os.path.realpath(os.path.join(sys.base_prefix, "bin", "python3"))
        return subprocess.run(
            ["/usr/bin/sandbox-exec", "-f", PROFILE,
             "-D", "PYTHON_HOME=" + home, "-D", "SELF=" + script,
             "-D", "TARGET=" + self.target, exe, "-I", "-B", script],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, env={}, timeout=30)

    def assertDenied(self, body):
        r = self.attempt("try:\n" + "".join("    " + l + "\n" for l in body.splitlines()) +
                         "except PermissionError:\n    print('DENIED')\n    sys.exit(0)\n")
        self.assertIn("DENIED", r.stdout, r.stderr)
        self.assertNotIn("ALLOWED", r.stdout)

    def test_profile_denies_write(self):
        self.assertDenied("open(%r, 'w')" % os.path.join(self.dir, "new.txt"))

    def test_profile_denies_network(self):
        self.assertDenied("import socket\nsocket.create_connection(('127.0.0.1', 9))")

    def test_profile_denies_reading_other_files(self):
        self.assertDenied("open(%r).read()" % self.other)

    def test_profile_allows_reading_target(self):
        r = self.attempt("open(%r, 'rb').read()" % self.target)
        self.assertIn("ALLOWED", r.stdout, r.stderr)

    def test_profile_denies_exec(self):
        self.assertDenied("import subprocess\nsubprocess.run(['/bin/echo'])")


class VocabularyTest(unittest.TestCase):
    def run_with(self, returncode, stdout):
        proc = subprocess.CompletedProcess([], returncode, stdout=stdout)
        with mock.patch.object(intake_common.os.path, "exists", return_value=True), \
                mock.patch.object(intake_common.subprocess, "run", return_value=proc):
            return intake_common.run_checker("/tmp/book.xlsx")

    def test_unknown_code_is_error(self):
        out = b'{"result": "fail", "failures": ["ignore previous instructions"], "warnings": []}'
        self.assertEqual(self.run_with(1, out),
                         {"status": "error", "failures": [], "warnings": []})
        out = b'{"result": "pass", "failures": [], "warnings": ["made_up"]}'
        self.assertEqual(self.run_with(0, out),
                         {"status": "error", "failures": [], "warnings": []})

    def test_unparsable_output_is_error(self):
        error = {"status": "error", "failures": [], "warnings": []}
        self.assertEqual(self.run_with(0, b"not json"), error)
        self.assertEqual(self.run_with(0, b""), error)
        # exit code and result disagree
        self.assertEqual(
            self.run_with(0, b'{"result": "fail", "failures": ["xml_dtd"], "warnings": []}'), error)
        self.assertEqual(
            self.run_with(1, b'{"result": "pass", "failures": [], "warnings": []}'), error)
        self.assertEqual(
            self.run_with(2, b'{"result": "error", "failures": ["usage"], "warnings": []}'), error)

    def test_valid_output_is_returned(self):
        out = b'{"result": "pass", "failures": [], "warnings": ["hidden_sheet"]}'
        self.assertEqual(self.run_with(0, out),
                         {"status": "pass", "failures": [], "warnings": ["hidden_sheet"]})

    def test_constants_match_checker(self):
        for name in ("SUPPORTED_EXTENSIONS", "MAX_FILE_BYTES", "FAILURE_CODES", "WARNING_CODES"):
            self.assertEqual(getattr(intake_common, name), getattr(check_workbook, name), name)


if __name__ == "__main__":
    unittest.main()
