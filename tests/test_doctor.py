import os
import platform
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

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

    def run_doctor(self):
        env = {
            "HOME": str(self.home),
            "PATH": str(self.bin) + ":/usr/bin:/bin",
        }
        return subprocess.run(
            ["/bin/bash", str(DOCTOR)], env=env, capture_output=True, text=True, timeout=30)

    def test_all_present_and_protected(self):
        self._fake_uvx()
        os.chmod(self.intake, 0)
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
        os.chmod(self.intake, 0)
        r = self.run_doctor()
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing uvx", r.stdout)

    def test_env_override_folder(self):
        self._fake_uvx()
        other = self.home / "other"
        other.mkdir()
        self.addCleanup(os.chmod, other, 0o700)
        os.chmod(other, 0)
        env = {"HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin",
               "WORKBOOK_INTAKE_DIR": str(other)}
        r = subprocess.run(["/bin/bash", str(DOCTOR)], env=env, capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
