import os
import platform
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_sandbox_profile import needs_sandbox

ROOT = Path(__file__).resolve().parent.parent
DOCTOR = ROOT / "scripts" / "doctor.sh"


@unittest.skipUnless(platform.system() == "Darwin", "macOS only")
class DoctorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(os.path.realpath(self._tmp.name)) / "home"
        self.home.mkdir()
        self.bin = Path(self._tmp.name) / "bin"
        self.bin.mkdir()
        self.intake = self.home / "workbook-intake"
        self.intake.mkdir()
        self.addCleanup(self._restore)

    def _restore(self):
        if self.intake.exists():
            os.chmod(self.intake, 0o700)

    def _fake_uvx(self):
        path = self.bin / "uvx"
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(stat.S_IRWXU)

    def _fake_ls(self):
        # Stands in for the refusal the sandbox gives under sandbox.filesystem.denyRead.
        path = self.bin / "ls"
        path.write_text('#!/bin/sh\necho "ls: $*: Operation not permitted" >&2\nexit 1\n')
        path.chmod(stat.S_IRWXU)

    def run_doctor(self):
        env = {
            "HOME": str(self.home),
            "PATH": str(self.bin) + ":/usr/bin:/bin",
        }
        return subprocess.run(
            ["/bin/bash", str(DOCTOR)], env=env, capture_output=True, text=True, timeout=30)

    def test_all_present_and_protected(self):
        self._fake_uvx()
        self._fake_ls()
        r = self.run_doctor()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("missing", r.stdout)
        self.assertIn("ok intake_dir_protected", r.stdout)

    def test_readable_intake_dir_stops(self):
        self._fake_uvx()
        r = self.run_doctor()
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing intake_dir_protected", r.stdout)
        self.assertIn("See README: Requirements", r.stdout)

    def test_uvx_missing(self):
        self._fake_ls()
        r = self.run_doctor()
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing uvx", r.stdout)

    def test_env_override_folder(self):
        self._fake_uvx()
        other = self.home / "other"
        other.mkdir()
        self._fake_ls()
        env = {"HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin",
               "WORKBOOK_INTAKE_DIR": str(other)}
        r = subprocess.run(["/bin/bash", str(DOCTOR)], env=env, capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout)

    def _run_env(self, **extra):
        env = {"HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin"}
        env.update(extra)
        return subprocess.run(["/bin/bash", str(DOCTOR)], env=env, capture_output=True,
                              text=True, timeout=30)

    def test_python_not_owned_by_root_is_missing(self):
        self._fake_uvx()
        self._fake_ls()
        dev = Path(os.path.realpath(self._tmp.name)) / "dev"
        (dev / "usr" / "bin").mkdir(parents=True)
        fake = dev / "usr" / "bin" / "python3"
        fake.write_text("#!/bin/bash\nexit 1\n")
        fake.chmod(stat.S_IRWXU)
        r = self._run_env(DEVELOPER_DIR=str(dev))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("missing python3", r.stdout)

    def test_folder_line_with_realpath(self):
        self._fake_uvx()
        self._fake_ls()
        r = self._run_env()
        self.assertIn("folder " + str(self.intake), r.stdout.splitlines())

    def test_no_folder_line_when_folder_missing(self):
        self._fake_uvx()
        self._fake_ls()
        self.intake.rmdir()
        r = self._run_env()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("folder ", r.stdout)

    def test_home_with_spaces(self):
        self._fake_uvx()
        home = Path(os.path.realpath(self._tmp.name)) / "my home"
        (home / "workbook-intake").mkdir(parents=True)
        self._fake_ls()
        r = self._run_env(HOME=str(home))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("folder " + str(home / "workbook-intake"), r.stdout.splitlines())

    def test_empty_env_uses_default(self):
        self._fake_uvx()
        self._fake_ls()
        r = self._run_env(WORKBOOK_INTAKE_DIR="")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("folder " + str(self.intake), r.stdout.splitlines())

    def test_env_starting_with_tilde(self):
        self._fake_uvx()
        other = self.home / "tilde dir"
        other.mkdir()
        self._fake_ls()
        r = self._run_env(WORKBOOK_INTAKE_DIR="~/tilde dir")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("folder " + str(other), r.stdout.splitlines())

    def test_permission_denied_is_not_protected(self):
        self._fake_uvx()
        os.chmod(self.intake, 0)
        r = self.run_doctor()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("missing intake_dir_protected", r.stdout)

    def test_missing_folder_is_not_protected(self):
        self._fake_uvx()
        self.intake.rmdir()
        r = self.run_doctor()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("missing intake_dir_protected", r.stdout)

    def test_sandbox_refusal_is_protected(self):
        self._fake_uvx()
        self._fake_ls()
        r = self.run_doctor()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok intake_dir_protected", r.stdout)

    @needs_sandbox
    def test_seatbelt_denied_folder_is_protected(self):
        self._fake_uvx()
        profile = self.home.parent / "deny.sb"
        profile.write_text(
            '(version 1)\n(allow default)\n(deny file-read-data (subpath "%s"))\n'
            % os.path.realpath(self.intake))
        env = {"HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin"}
        r = subprocess.run(["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/bash", str(DOCTOR)],
                           env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok intake_dir_protected", r.stdout)


if __name__ == "__main__":
    unittest.main()
