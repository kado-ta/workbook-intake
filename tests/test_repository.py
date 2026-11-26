import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")


class RepositoryTest(unittest.TestCase):
    def test_no_user_home_paths_in_tracked_files(self):
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, stdout=subprocess.PIPE
        ).stdout.decode("utf-8")
        offenders = []
        for name in filter(None, out.split("\0")):
            path = ROOT / name
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", errors="replace")
            if HOME_PATH.search(text):
                offenders.append(name)
        self.assertEqual(offenders, [])
