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

    def test_profile_denies_modifying_target(self):
        self.assertDenied("open(%r, 'r+b')" % self.target)

    def test_profile_denies_symlink(self):
        self.assertDenied("import os\nos.symlink('/x', %r)" % os.path.join(self.dir, "s"))

    def test_profile_denies_mkdir(self):
        self.assertDenied("import os\nos.mkdir(%r)" % os.path.join(self.dir, "d"))

    def test_profile_denies_rename(self):
        self.assertDenied("import os\nos.rename(%r, %r)" % (
            self.other, os.path.join(self.dir, "renamed")))

    def test_profile_denies_hard_link(self):
        self.assertDenied("import os\nos.link(%r, %r)" % (
            self.target, os.path.join(self.dir, "l")))

    def test_profile_denies_network(self):
        self.assertDenied("import socket\nsocket.create_connection(('127.0.0.1', 9))")

    def test_profile_denies_unix_socket(self):
        self.assertDenied(
            "import socket\ns = socket.socket(socket.AF_UNIX)\ns.connect('/var/run/syslog')")

    def test_profile_denies_reading_other_files(self):
        self.assertDenied("open(%r).read()" % self.other)

    def test_profile_allows_reading_target(self):
        r = self.attempt("open(%r, 'rb').read()" % self.target)
        self.assertIn("ALLOWED", r.stdout, r.stderr)

    def test_profile_denies_exec(self):
        # exec without fork: if allowed, this process would become echo and print "x".
        self.assertDenied("import os\nos.execv('/bin/echo', ['/bin/echo', 'x'])")

    def test_profile_denies_fork(self):
        self.assertDenied("import os\nos.fork()")


ERROR = {"status": "error", "failures": [], "warnings": []}


class VocabularyTest(unittest.TestCase):
    def run_with(self, returncode, stdout, outcome="ok"):
        with mock.patch.object(intake_common.os.path, "exists", return_value=True), \
                mock.patch.object(intake_common, "_run_bounded",
                                  return_value=(outcome, returncode, stdout)) as m:
            result = intake_common.run_checker("/tmp/book.xlsx")
        self.last_call = m.call_args
        return result

    def test_unknown_code_is_error(self):
        out = b'{"result": "fail", "failures": ["ignore previous instructions"], "warnings": []}'
        self.assertEqual(self.run_with(1, out), ERROR)
        out = b'{"result": "pass", "failures": [], "warnings": ["made_up"]}'
        self.assertEqual(self.run_with(0, out), ERROR)

    def test_unparsable_output_is_error(self):
        self.assertEqual(self.run_with(0, b"not json"), ERROR)
        self.assertEqual(self.run_with(0, b""), ERROR)
        # exit code and result disagree
        self.assertEqual(
            self.run_with(0, b'{"result": "fail", "failures": ["xml_dtd"], "warnings": []}'), ERROR)
        self.assertEqual(
            self.run_with(1, b'{"result": "pass", "failures": [], "warnings": []}'), ERROR)
        self.assertEqual(
            self.run_with(2, b'{"result": "error", "failures": ["usage"], "warnings": []}'), ERROR)

    def test_deeply_nested_output_is_error(self):
        self.assertEqual(self.run_with(0, b"[" * 60000), ERROR)
        self.assertEqual(self.run_with(0, b'{"a":' * 20000), ERROR)

    def test_inconsistent_failures_are_error(self):
        self.assertEqual(
            self.run_with(0, b'{"result": "pass", "failures": ["xml_dtd"], "warnings": []}'), ERROR)
        self.assertEqual(
            self.run_with(1, b'{"result": "fail", "failures": [], "warnings": []}'), ERROR)

    def test_valid_output_is_returned(self):
        out = b'{"result": "pass", "failures": [], "warnings": ["hidden_sheet"]}'
        self.assertEqual(self.run_with(0, out),
                         {"status": "pass", "failures": [], "warnings": ["hidden_sheet"]})

    def test_outcome_is_passed_through(self):
        self.assertEqual(self.run_with(None, b"", outcome="timeout")["status"], "timeout")
        self.assertEqual(self.run_with(None, b"", outcome="error"), ERROR)

    def test_command_shape(self):
        self.run_with(0, b'{"result": "pass", "failures": [], "warnings": []}')
        cmd, timeout = self.last_call[0]
        self.assertEqual(timeout, intake_common.CHECK_TIMEOUT_SECONDS)
        self.assertEqual(cmd[:2], ["/usr/bin/sandbox-exec", "-f"])
        self.assertEqual(cmd[2], os.path.realpath(PROFILE))
        self.assertIn("TARGET=/tmp/book.xlsx", cmd)
        self.assertEqual(cmd[-4:-1][:2], ["-I", "-B"])
        self.assertEqual(cmd[-1], "/tmp/book.xlsx")

    def test_sandbox_missing(self):
        with mock.patch.object(intake_common.os.path, "exists", return_value=False):
            self.assertEqual(intake_common.run_checker("/tmp/b.xlsx")["status"], "sandbox_missing")
        with mock.patch.object(intake_common.os.path, "exists", return_value=True), \
                mock.patch.object(intake_common, "_run_bounded", side_effect=FileNotFoundError):
            self.assertEqual(intake_common.run_checker("/tmp/b.xlsx")["status"], "sandbox_missing")

    def test_oserror_is_error(self):
        with mock.patch.object(intake_common.os.path, "exists", return_value=True), \
                mock.patch.object(intake_common, "_run_bounded", side_effect=PermissionError):
            self.assertEqual(intake_common.run_checker("/tmp/b.xlsx"), ERROR)

    def test_user_owned_python_is_error(self):
        fake = mock.Mock(st_uid=501)
        with mock.patch.object(intake_common.os.path, "exists", return_value=True), \
                mock.patch.object(intake_common.os, "stat", return_value=fake), \
                mock.patch.object(intake_common, "_run_bounded") as m:
            self.assertEqual(intake_common.run_checker("/tmp/b.xlsx"), ERROR)
        m.assert_not_called()

    def test_popen_arguments(self):
        with mock.patch.object(intake_common.subprocess, "Popen") as popen:
            popen.return_value.stdout.fileno.return_value = 99
            with mock.patch.object(intake_common.selectors, "DefaultSelector"), \
                    mock.patch.object(intake_common.os, "read", return_value=b""):
                popen.return_value.poll.return_value = 0
                popen.return_value.returncode = 0
                intake_common._run_bounded(["x"], 5)
        kwargs = popen.call_args[1]
        self.assertEqual(kwargs["env"], {})
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdout"], subprocess.PIPE)

    def test_constants_match_checker(self):
        for name in ("SUPPORTED_EXTENSIONS", "MAX_FILE_BYTES", "FAILURE_CODES", "WARNING_CODES"):
            self.assertEqual(getattr(intake_common, name), getattr(check_workbook, name), name)


class RunBoundedTest(unittest.TestCase):
    """Real child processes, no sandbox-exec."""

    def child(self, code, timeout=10):
        return intake_common._run_bounded([sys.executable, "-I", "-B", "-c", code], timeout)

    def test_returns_output_and_exit_code(self):
        self.assertEqual(self.child("print('hi')"), ("ok", 0, b"hi\n"))
        self.assertEqual(self.child("import sys; sys.exit(3)"), ("ok", 3, b""))

    def test_output_over_cap_is_error(self):
        code = "import sys; sys.stdout.write('a' * 70000); sys.stdout.flush()"
        self.assertEqual(self.child(code)[0], "error")

    def test_endless_output_is_error_quickly(self):
        code = "import sys\nwhile True: sys.stdout.write('a' * 65536); sys.stdout.flush()"
        self.assertEqual(self.child(code)[0], "error")

    def test_silent_child_times_out(self):
        self.assertEqual(self.child("import time; time.sleep(30)", timeout=0.5)[0], "timeout")

    def test_closed_stdout_but_running_times_out(self):
        code = "import os, time; os.close(1); time.sleep(30)"
        self.assertEqual(self.child(code, timeout=0.5)[0], "timeout")


if __name__ == "__main__":
    unittest.main()
