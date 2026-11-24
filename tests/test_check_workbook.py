import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import check_workbook  # noqa: E402
from tests.workbook_factory import minimal_parts, write_workbook  # noqa: E402

SCRIPT = str(ROOT / "scripts" / "check_workbook.py")
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


class CheckWorkbookTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def path(self, name="book.xlsx"):
        return os.path.join(self.dir, name)

    def build(self, parts=None, name="book.xlsx"):
        return write_workbook(self.path(name), parts if parts is not None else minimal_parts())

    def failures(self, path):
        return check_workbook.check(path)["failures"]

    def with_part(self, name, data):
        parts = minimal_parts()
        parts[name] = data
        return self.build(parts)

    def test_minimal_workbook_passes(self):
        result = check_workbook.check(self.build())
        self.assertEqual(result["result"], "pass")
        self.assertEqual(result["failures"], [])

    def test_uppercase_extension_passes(self):
        self.assertEqual(check_workbook.check(self.build(name="book.XLSX"))["result"], "pass")

    def test_unsupported_extension_fails(self):
        for name in ("book.xls", "book.csv", "book.docm"):
            with self.subTest(name=name):
                self.assertIn("unsupported_extension", self.failures(self.build(name=name)))

    def test_file_too_large_fails(self):
        p = self.build()
        with mock.patch.object(check_workbook, "MAX_FILE_BYTES", 100):
            self.assertIn("file_too_large", self.failures(p))

    def test_not_zip_fails(self):
        p = self.path()
        with open(p, "wb") as f:
            f.write(b"just some text")
        self.assertEqual(self.failures(p), ["not_zip"])

    def test_ole_encrypted_package_fails(self):
        p = self.path()
        with open(p, "wb") as f:
            f.write(OLE_MAGIC + b"\x00" * 64 + "EncryptedPackage".encode("utf-16-le") + b"\x00" * 16)
        self.assertEqual(self.failures(p), ["encrypted"])

    def test_ole_without_encrypted_package_is_not_zip(self):
        p = self.path()
        with open(p, "wb") as f:
            f.write(OLE_MAGIC + b"\x00" * 64)
        self.assertEqual(self.failures(p), ["not_zip"])

    def test_zip_encryption_flag_fails(self):
        p = self.build()
        with open(p, "rb") as f:
            data = bytearray(f.read())
        for sig, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            i = data.find(sig)
            while i != -1:
                data[i + offset] |= 1
                i = data.find(sig, i + 4)
        with open(p, "wb") as f:
            f.write(data)
        self.assertIn("encrypted", self.failures(p))

    def test_too_many_parts_fails(self):
        p = self.build()
        with mock.patch.object(check_workbook, "MAX_PARTS", 3):
            self.assertIn("too_many_parts", self.failures(p))

    def test_unsafe_part_names_fail(self):
        for name in ("../x.xml", "/x.xml", "xl/../../x.xml", "C:/x.xml", "xl\\..\\x.xml"):
            with self.subTest(name=name):
                p = self.with_part(name, b"<a/>")
                self.assertIn("unsafe_part_name", self.failures(p))

    def test_total_uncompressed_limit_fails(self):
        p = self.with_part("xl/media/blob.bin", os.urandom(2 * 1024 * 1024))
        with mock.patch.object(check_workbook, "MAX_TOTAL_UNCOMPRESSED", 1024 * 1024):
            self.assertIn("uncompressed_too_large", self.failures(p))

    def test_compression_ratio_fails(self):
        p = self.with_part("xl/media/zeros.bin", b"\x00" * (2 * 1024 * 1024))
        self.assertIn("compression_ratio_too_high", self.failures(p))

    def test_small_highly_compressed_part_passes(self):
        data = b"<a/>" * (50 * 1024 // 4)
        p = self.with_part("xl/worksheets/sheet2.xml", data)
        self.assertEqual(check_workbook.check(p)["result"], "pass")

    def test_doctype_fails(self):
        p = self.with_part("xl/worksheets/sheet1.xml", b'<!DOCTYPE x [<!ELEMENT x ANY>]><x/>')
        self.assertEqual(self.failures(p), ["xml_dtd"])

    def test_entity_fails(self):
        p = self.with_part("xl/worksheets/sheet1.xml", b'<x><!ENTITY a "b"></x>')
        self.assertEqual(self.failures(p), ["xml_dtd"])

    def test_doctype_in_utf16_part_fails(self):
        data = "\ufeff<!DOCTYPE x><x/>".encode("utf-16-le")
        p = self.with_part("xl/worksheets/sheet1.xml", data)
        self.assertEqual(self.failures(p), ["xml_dtd"])

    def test_doctype_split_across_read_chunks_fails(self):
        chunk = check_workbook.READ_CHUNK
        data = b"<x>" + b" " * (chunk - 3 - 4) + b"<!DOCTYPE x><x/>"
        self.assertEqual(data.index(b"<!DOCTYPE"), chunk - 4)
        p = self.with_part("xl/worksheets/sheet1.xml", data)
        self.assertEqual(self.failures(p), ["xml_dtd"])

    def test_cli_usage_error(self):
        for args in ([], ["relative.xlsx"], ["/a.xlsx", "/b.xlsx"]):
            with self.subTest(args=args):
                proc = subprocess.run([sys.executable, "-B", SCRIPT] + args, capture_output=True, text=True)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(json.loads(proc.stdout)["failures"], ["usage"])

    def test_cli_unreadable(self):
        proc = subprocess.run([sys.executable, "-B", SCRIPT, self.path("missing.xlsx")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["failures"], ["unreadable"])

    def test_cli_exit_codes(self):
        ok = subprocess.run([sys.executable, "-B", SCRIPT, self.build()], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(json.loads(ok.stdout)["result"], "pass")
        bad = subprocess.run([sys.executable, "-B", SCRIPT, self.build(name="b.csv")], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)["result"], "fail")

    def test_cli_output_has_no_file_derived_strings(self):
        marker = "MARKERZZ"
        parts = minimal_parts()
        parts["xl/workbook.xml"] = parts["xl/workbook.xml"].replace(b"Sheet1", marker.encode() + b"sheet")
        parts["xl/worksheets/" + marker + "part.xml"] = b"<!DOCTYPE x><x/>"
        parts["../" + marker + "evil.xml"] = b"<x/>"
        p = write_workbook(self.path(marker + "file.xlsx"), parts)
        proc = subprocess.run([sys.executable, "-B", SCRIPT, p], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn(marker, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
