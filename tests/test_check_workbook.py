import contextlib
import io
import json
import os
import subprocess
import sys
import struct
import tempfile
import zipfile
import unittest
import warnings
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import check_workbook  # noqa: E402
from tests.workbook_factory import (  # noqa: E402
    assemble_zip, central_entries, minimal_parts, patch_entry, raw_zip, shift_central_offsets,
    split_zip, write_raw, write_workbook,
)

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
        p = write_workbook(self.path(marker + "file.xlsx"), parts)
        proc = subprocess.run([sys.executable, "-B", SCRIPT, p], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["failures"], ["xml_dtd"])
        self.assertNotIn(marker, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.count("\n"), 1)

    def patch_zip(self, path, edit):
        with open(path, "rb") as f:
            data = bytearray(f.read())
        edit(data)
        with open(path, "wb") as f:
            f.write(data)

    def each_entry(self, data, sig, fn):
        i = data.find(sig)
        while i != -1:
            fn(data, i)
            i = data.find(sig, i + 4)

    def test_corrupt_deflate_data_is_not_zip(self):
        p = self.build()
        with zipfile.ZipFile(p) as z:
            info = z.getinfo("xl/worksheets/sheet1.xml")
        def edit(data):
            start = info.header_offset + 30 + len(info.filename) + 0
            data[start:start + 8] = b"\xff" * 8
        self.patch_zip(p, edit)
        self.assertEqual(self.failures(p), ["not_zip"])

    def test_unsupported_compression_methods_are_not_zip(self):
        for method in (12, 14):
            with self.subTest(method=method):
                p = self.build()
                def edit(data, method=method):
                    self.each_entry(data, b"PK\x01\x02", lambda d, i: d.__setitem__(i + 10, method))
                self.patch_zip(p, edit)
                self.assertEqual(self.failures(p), ["not_zip"])

    def test_invalid_utf8_name_is_unsafe(self):
        p = self.with_part("xl/worksheets/a\u00e9.xml", b"<a/>")
        self.patch_zip(p, lambda d: d.__setitem__(slice(0, len(d)), bytes(d).replace(b"\xc3\xa9", b"\xc3\xff")))
        self.assertEqual(self.failures(p), ["unsafe_part_name"])

    def test_inflated_declared_compress_size_is_not_zip(self):
        p = self.build()
        def edit(data):
            self.each_entry(data, b"PK\x01\x02", lambda d, i: d.__setitem__(slice(i + 20, i + 24), struct.pack("<I", 0x7FFFFFFF)))
        self.patch_zip(p, edit)
        self.assertEqual(self.failures(p), ["not_zip"])

    def test_doctype_in_utf16be_part_fails(self):
        p = self.with_part("xl/worksheets/sheet1.xml", "\ufeff<!DOCTYPE x><x/>".encode("utf-16-be"))
        self.assertEqual(self.failures(p), ["xml_dtd"])

    def test_entity_in_utf16_part_fails(self):
        for enc in ("utf-16-le", "utf-16-be"):
            with self.subTest(enc=enc):
                p = self.with_part("xl/worksheets/sheet1.xml", "<x><!ENTITY a 'b'></x>".encode(enc))
                self.assertEqual(self.failures(p), ["xml_dtd"])

    def test_doctype_in_part_with_non_xml_name_fails(self):
        p = self.with_part("xl/worksheets/sheet1.bin", b"<!DOCTYPE x><x/>")
        self.assertEqual(self.failures(p), ["xml_dtd"])

    def run_main(self, path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = check_workbook.main([path])
        return rc, buf.getvalue()

    def test_non_regular_target_is_unreadable(self):
        d = self.path("dir.xlsx")
        os.mkdir(d)
        fifo = self.path("fifo.xlsx")
        os.mkfifo(fifo)
        for target in (d, fifo):
            with self.subTest(target=os.path.basename(target)):
                rc, out = self.run_main(target)
                self.assertEqual(rc, 2)
                self.assertEqual(json.loads(out)["failures"], ["unreadable"])

    def test_main_last_resort_hides_exception_text(self):
        p = self.build()
        with mock.patch.object(check_workbook, "check", side_effect=RuntimeError("SECRETTEXT")):
            rc, out = self.run_main(p)
        self.assertEqual(rc, 2)
        self.assertEqual(
            json.loads(out),
            {"result": "error", "failures": ["unreadable"], "warnings": [], "counts": {}},
        )
        self.assertNotIn("SECRETTEXT", out)

    # --- warnings ---

    def warn(self, parts):
        return check_workbook.check(self.build(parts))

    def parts_with(self, **extra):
        parts = minimal_parts()
        parts.update({k.replace("__", "/"): v for k, v in extra.items()})
        return parts

    def sst(self, *values):
        body = "".join("<si><t>%s</t></si>" % v for v in values)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">%s</sst>' % body
        ).encode("utf-8")

    def sst_parts(self, *values, name="xl/sharedStrings.xml"):
        parts = minimal_parts()
        del parts["xl/sharedStrings.xml"]
        parts[name] = self.sst(*values)
        return parts

    def sheets_xml(self, *states):
        body = "".join('<sheet name="S%d" sheetId="%d" state="%s"/>' % (i, i, s) for i, s in enumerate(states, 1))
        return (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets>%s</sheets></workbook>' % body
        ).encode()

    def test_vba_project_warns(self):
        r = self.warn(self.parts_with(**{"xl__vbaProject.bin": b"\x00\x01"}))
        self.assertEqual(r["result"], "pass")
        self.assertIn("vba_project", r["warnings"])

    def test_external_link_warns(self):
        r = self.warn(self.parts_with(**{"xl__externalLinks__externalLink1.xml": b"<externalLink/>"}))
        self.assertIn("external_link", r["warnings"])

    def test_connections_warns(self):
        r = self.warn(self.parts_with(**{"xl__connections.xml": b"<connections/>"}))
        self.assertIn("data_connection", r["warnings"])

    def test_external_target_mode_warns(self):
        parts = minimal_parts()
        parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
            b"</Relationships>",
            b'<Relationship Id="rId9" Type="http://x/hyperlink" Target="http://example.invalid/" TargetMode="External"/></Relationships>',
        )
        self.assertIn("external_relationship", self.warn(parts)["warnings"])

    def test_power_query_warns(self):
        data = "\ufeff<DataMashup xmlns='x'>AAAA</DataMashup>".encode("utf-16-le")
        r = self.warn(self.parts_with(**{"customXml__item1.xml": data}))
        self.assertIn("power_query", r["warnings"])

    def test_embeddings_and_activex_warn(self):
        r = self.warn(self.parts_with(**{"xl__embeddings__x.bin": b"\x00", "xl__activeX__activeX1.xml": b"<ocx/>"}))
        self.assertIn("embedded_object", r["warnings"])
        self.assertIn("activex", r["warnings"])

    def test_case_only_duplicate_part_names_fail(self):
        parts = minimal_parts()
        parts["xl/workbook.xml"] = self.sheets_xml("veryHidden")
        parts["xl/Workbook.xml"] = self.sheets_xml("visible")
        self.assertEqual(self.failures(self.build(parts)), ["unsafe_part_name"])

    def test_exact_duplicate_part_names_fail(self):
        p = self.path()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(p, "w") as z:
                for name, data in minimal_parts().items():
                    z.writestr(name, data)
                z.writestr("xl/workbook.xml", self.sheets_xml("visible"))
        self.assertEqual(self.failures(p), ["unsafe_part_name"])

    def test_renamed_vba_project_with_relationship_warns(self):
        parts = minimal_parts()
        parts["xl/foo.bin"] = b"\x00"
        parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
            b"</Relationships>",
            b'<Relationship Id="rId8" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="foo.bin"/></Relationships>',
        )
        self.assertIn("vba_project", self.warn(parts)["warnings"])

    def test_renamed_external_link_with_relationship_warns(self):
        parts = minimal_parts()
        parts["xl/other.xml"] = b"<externalLink/>"
        parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
            b"</Relationships>",
            b'<Relationship Id="rId8" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="other.xml"/></Relationships>',
        )
        self.assertIn("external_link", self.warn(parts)["warnings"])

    def test_relationship_types_map_to_warnings(self):
        base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
        for suffix, code in (("oleObject", "embedded_object"), ("package", "embedded_object"),
                             ("control", "activex"), ("connections", "data_connection")):
            with self.subTest(suffix=suffix):
                parts = minimal_parts()
                parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
                    b"</Relationships>",
                    ('<Relationship Id="rId8" Type="%s%s" Target="x.bin"/></Relationships>' % (base, suffix)).encode(),
                )
                self.assertIn(code, self.warn(parts)["warnings"])

    def test_data_mashup_outside_custom_xml_warns(self):
        r = self.warn(self.parts_with(**{"xl__misc__blob.bin": b"\x00DataMashup\x00"}))
        self.assertIn("power_query", r["warnings"])

    def test_whitespace_only_part_is_not_xml(self):
        r = self.warn(self.parts_with(**{"xl__blank.bin": b" \n" * 100}))
        self.assertEqual(r["warnings"], [])

    def test_second_office_document_relationship_is_considered(self):
        parts = minimal_parts()
        parts["xl/book.xml"] = self.sheets_xml("veryHidden")
        parts["_rels/.rels"] = parts["_rels/.rels"].replace(
            b"</Relationships>",
            b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/book.xml"/></Relationships>',
        ).replace(b'Target="xl/workbook.xml"', b'Target="xl/gone.xml"')
        self.assertIn("very_hidden_sheet", self.warn(parts)["warnings"])

    def test_hidden_and_very_hidden_sheets_warn(self):
        r = self.warn(self.parts_with(**{"xl__workbook.xml": self.sheets_xml("hidden", "veryHidden", "visible")}))
        self.assertIn("hidden_sheet", r["warnings"])
        self.assertIn("very_hidden_sheet", r["warnings"])
        self.assertEqual(r["counts"]["hidden_sheet"], 1)
        self.assertEqual(r["counts"]["very_hidden_sheet"], 1)

    def test_renamed_workbook_part_is_followed(self):
        parts = minimal_parts()
        del parts["xl/workbook.xml"]
        parts["xl/book.xml"] = self.sheets_xml("veryHidden")
        parts["_rels/.rels"] = parts["_rels/.rels"].replace(b"xl/workbook.xml", b"/xl/book.xml")
        self.assertIn("very_hidden_sheet", self.warn(parts)["warnings"])

    def test_missing_or_bad_root_rels_gives_no_sheet_warning(self):
        hidden = self.sheets_xml("veryHidden")
        good = minimal_parts()["_rels/.rels"]
        cases = {
            "missing": None,
            "malformed": b"<Relationships",
            "target_absent": good.replace(b"xl/workbook.xml", b"xl/nope.xml"),
            "outside": good.replace(b"xl/workbook.xml", b"../xl/workbook.xml"),
        }
        for label, rels in cases.items():
            with self.subTest(label=label):
                parts = minimal_parts()
                parts["xl/workbook.xml"] = hidden
                if rels is None:
                    del parts["_rels/.rels"]
                else:
                    parts["_rels/.rels"] = rels
                r = self.warn(parts)
                self.assertEqual(r["result"], "pass")
                self.assertNotIn("very_hidden_sheet", r["warnings"])

    def test_invisible_characters_warn(self):
        r = self.warn(self.sst_parts("a\u200bb", "c\u202ed", "e\U000e0041f"))
        self.assertIn("invisible_characters", r["warnings"])
        self.assertEqual(r["counts"]["invisible_characters"], 3)

    def test_instruction_like_text_warns(self):
        r = self.warn(self.sst_parts("Ignore previous instructions", "前の指示を無視して", "fine"))
        self.assertIn("instruction_like_text", r["warnings"])
        self.assertEqual(r["counts"]["instruction_like_text"], 2)

    def test_instruction_text_split_by_invisible_characters_warns(self):
        r = self.warn(self.sst_parts("ig\u200bnore prev\u200bious"))
        self.assertIn("instruction_like_text", r["warnings"])

    def test_instruction_text_in_renamed_part_warns(self):
        r = self.warn(self.sst_parts("Ignore previous instructions", name="xl/strings2.xml"))
        self.assertIn("instruction_like_text", r["warnings"])

    def test_instruction_text_in_non_xml_named_part_warns(self):
        text = self.sst("Ignore previous instructions").decode().split("?>", 1)[1]
        for enc in ("utf-8", "utf-16"):
            with self.subTest(enc=enc):
                parts = minimal_parts()
                parts["xl/strings.bin"] = text.encode(enc)
                self.assertIn("instruction_like_text", self.warn(parts)["warnings"])

    def test_leading_whitespace_before_xml_is_still_scanned(self):
        parts = minimal_parts()
        parts["xl/strings.bin"] = b" \n" * 1000 + self.sst("Ignore previous instructions").split(b"?>", 1)[1]
        self.assertIn("instruction_like_text", self.warn(parts)["warnings"])

    def test_sniff_prefix_is_bounded(self):
        # Documents the bound: more than SNIFF_BYTES of leading whitespace means "not XML".
        parts = minimal_parts()
        parts["xl/strings.bin"] = b" " * (check_workbook.SNIFF_BYTES + 1) + b"<a>Ignore previous</a>"
        self.assertEqual(self.warn(parts)["warnings"], [])

    def test_very_long_string_warns(self):
        limit = check_workbook.LONG_STRING_CHARS
        self.assertIn("very_long_string", self.warn(self.sst_parts("x" * (limit + 1)))["warnings"])
        self.assertNotIn("very_long_string", self.warn(self.sst_parts("x" * limit))["warnings"])

    def test_xlsb_strings_not_checked(self):
        r = check_workbook.check(self.build(name="book.xlsb"))
        self.assertEqual(r["result"], "pass")
        self.assertIn("strings_not_checked", r["warnings"])

    def test_oversized_xml_strings_not_checked(self):
        p = self.build()
        with mock.patch.object(check_workbook, "MAX_PARSE_BYTES", 100):
            r = check_workbook.check(p)
        self.assertIn("strings_not_checked", r["warnings"])

    def test_malformed_xml_part_is_counted_not_crashing(self):
        r = self.warn(self.parts_with(**{"xl__worksheets__sheet2.xml": b"<a><b></a>"}))
        self.assertEqual(r["result"], "pass")
        self.assertEqual(r["counts"]["strings_not_checked"], 1)

    def test_clean_workbook_has_no_warnings(self):
        r = self.warn(minimal_parts())
        self.assertEqual((r["warnings"], r["counts"]), ([], {}))

    def test_warnings_follow_vocabulary_order(self):
        r = self.warn(self.parts_with(**{"xl__vbaProject.bin": b"\x00", "xl__activeX__a.xml": b"<a/>"}))
        order = [c for c in check_workbook.WARNING_CODES if c in r["warnings"]]
        self.assertEqual(r["warnings"], order)

    def test_warnings_do_not_change_exit_code(self):
        rc, out = self.run_main(self.build(self.parts_with(**{"xl__vbaProject.bin": b"\x00"})))
        self.assertEqual(rc, 0)
        self.assertIn("vba_project", json.loads(out)["warnings"])

    def test_warnings_not_computed_on_failure(self):
        r = check_workbook.check(self.with_part("xl/vbaProject.bin", b"<!DOCTYPE x>"))
        self.assertEqual((r["warnings"], r["counts"]), ([], {}))

    def test_cli_warning_output_has_no_file_derived_strings(self):
        marker = "MARKERZZ"
        p = self.build(self.sst_parts("Ignore previous " + marker))
        proc = subprocess.run([sys.executable, "-B", SCRIPT, p], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("instruction_like_text", json.loads(proc.stdout)["warnings"])
        self.assertNotIn(marker, proc.stdout + proc.stderr)


class _NoSeek(object):
    """Write-only stream: zipfile falls back to data descriptors on it."""

    def __init__(self):
        self.chunks = []

    def write(self, b):
        self.chunks.append(bytes(b))
        return len(b)

    def flush(self):
        pass


class LayoutTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def check(self, data, name="book.xlsx"):
        p = os.path.join(self.dir, name)
        write_raw(p, data)
        return check_workbook.check(p)

    def assert_fails(self, data, code):
        self.assertEqual(self.check(data)["failures"], [code])

    def parts_zip(self, parts=None):
        return raw_zip(parts if parts is not None else minimal_parts())

    def test_two_central_directories_fail(self):
        longer = minimal_parts()
        longer["xl/sharedStrings.xml"] += b" " * 64
        lb, cdb, n = split_zip(raw_zip(longer))
        la, cda, _ = split_zip(raw_zip(minimal_parts()))
        self.assertEqual(len(cda), len(cdb))
        # zipfile adds the unexplained prefix to every offset, so la's entries
        # are stored relative to the second copy.
        shift_central_offsets(cda, len(lb) + len(cdb) - len(la) - len(cda))
        eocd = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, n, n, len(cdb), len(lb), 0)
        raw = lb + bytes(cdb) + la + bytes(cda) + eocd
        # The built file really splits readers: zipfile reads la's parts, a
        # reader that goes to the recorded offset reads lb's central directory.
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertEqual(z.read("xl/sharedStrings.xml"), minimal_parts()["xl/sharedStrings.xml"])
        at_offset = raw[len(lb):len(lb) + len(cdb)]
        self.assertEqual(at_offset, bytes(cdb))
        self.assert_fails(raw, "not_zip")

    def test_prefixed_data_fails(self):
        self.assert_fails(b"x" + self.parts_zip(), "not_zip")

    def test_archive_comment_fails(self):
        body, cd, n = split_zip(self.parts_zip())
        self.assert_fails(assemble_zip(body, cd, n, comment=b"x"), "not_zip")

    def test_trailing_bytes_after_eocd_fail(self):
        self.assert_fails(self.parts_zip() + b"x", "not_zip")

    def test_gap_between_entries_fails(self):
        body, cd, n = split_zip(self.parts_zip())
        offsets = [struct.unpack("<I", cd[p + 42:p + 46])[0] for p in central_entries(cd)]
        second = offsets[1]
        for p in central_entries(cd):
            off = struct.unpack("<I", cd[p + 42:p + 46])[0]
            if off >= second:
                cd[p + 42:p + 46] = struct.pack("<I", off + 1)
        body = body[:second] + b"x" + body[second:]
        self.assert_fails(assemble_zip(body, cd, n), "not_zip")

    def test_entry_count_mismatch_fails(self):
        body, cd, n = split_zip(self.parts_zip())
        self.assert_fails(assemble_zip(body, cd, n, count_in_eocd=n - 1), "not_zip")

    def test_local_name_mismatch_fails(self):
        raw = self.parts_zip()
        self.assertIn(b"[Content_Types].xml", raw)
        self.assert_fails(raw.replace(b"[Content_Types].xml", b"[Content_Types].xmX", 1), "not_zip")

    def stored_book(self, extra_parts=None):
        parts = minimal_parts()
        parts.update(extra_parts or {})
        return raw_zip(parts)

    def test_local_header_values_must_match_central(self):
        sheet = "xl/worksheets/sheet1.xml"
        cases = {
            "crc": {"crc": 1},
            "method": {"method": 8},
            "flags": {"flags": 0x2},
            "csize": {"csize": 1},
            "usize": {"usize": 1},
        }
        for label, local in cases.items():
            with self.subTest(label=label):
                raw = patch_entry(self.stored_book(), sheet, local=local)
                self.assert_fails(raw, "not_zip")

    def test_local_name_mismatch_is_caught_by_layout(self):
        raw = self.stored_book().replace(b"[Content_Types].xml", b"[Content_Types].xmX", 1)
        p = os.path.join(self.dir, "book.xlsx")
        write_raw(p, raw)
        self.assertEqual(check_workbook._check_layout(p, len(raw)), "not_zip")

    def test_overlapping_entries_fail(self):
        # Two central entries that point at the same local header.
        body, cd, n = split_zip(self.stored_book())
        cd += bytes(cd[:46 + struct.unpack("<H", cd[28:30])[0]])
        self.assert_fails(assemble_zip(body, cd, n + 1), "not_zip")

    def test_stored_size_mismatch_hides_trailing_bytes(self):
        base = b"a" * 162
        raw = self.stored_book({"xl/pad.bin": base + b"<!DOCTYPE x>" + b"b" * 18})
        raw = patch_entry(raw, "xl/pad.bin", central={"usize": 162, "crc": zlib.crc32(base)},
                          local={"usize": 162, "crc": zlib.crc32(base)})
        self.assert_fails(raw, "not_zip")

    def test_deflate_expanding_past_declared_size_fails(self):
        big = b"\x00" * (20 * 1024 * 1024)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in minimal_parts().items():
                z.writestr(name, data)
            z.writestr("xl/pad.bin", big)
        crc = zlib.crc32(b"\x00" * 162)
        raw = patch_entry(buf.getvalue(), "xl/pad.bin", central={"usize": 162, "crc": crc},
                          local={"usize": 162, "crc": crc})
        self.assert_fails(raw, "not_zip")

    def test_crc_mismatch_fails(self):
        raw = patch_entry(self.stored_book(), "xl/sharedStrings.xml",
                          central={"crc": 1}, local={"crc": 1})
        self.assert_fails(raw, "not_zip")

    def test_unicode_path_extra_fails(self):
        body, cd, n = split_zip(self.parts_zip())
        nl, xl = struct.unpack("<HH", cd[28:32])
        extra = struct.pack("<HH", 0x7075, 5) + b"\x01\x00\x00\x00\x00"
        cd[30:32] = struct.pack("<H", xl + len(extra))
        cd[46 + nl + xl:46 + nl + xl] = extra
        self.assert_fails(assemble_zip(body, cd, n), "not_zip")

    def test_zip64_records_fail(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for name, data in minimal_parts().items():
                with z.open(zipfile.ZipInfo(name), "w", force_zip64=True) as f:
                    f.write(data)
        self.assert_fails(buf.getvalue(), "not_zip")

    def test_data_descriptor_layout_passes(self):
        stream = _NoSeek()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in minimal_parts().items():
                z.writestr(name, data)
        raw = b"".join(stream.chunks)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertTrue(all(i.flag_bits & 0x8 for i in z.infolist()))
        self.assertEqual(self.check(raw)["result"], "pass")

    def test_empty_segment_name_fails(self):
        parts = minimal_parts()
        parts["xl//workbook.xml"] = b"<a/>"
        self.assert_fails(self.parts_zip(parts), "unsafe_part_name")

    def test_dot_segment_name_fails(self):
        parts = minimal_parts()
        parts["xl/./a.xml"] = b"<a/>"
        self.assert_fails(self.parts_zip(parts), "unsafe_part_name")

    def test_nul_in_name_fails(self):
        parts = minimal_parts()
        parts["xl/aXb.xml"] = b"<a/>"
        raw = self.parts_zip(parts).replace(b"xl/aXb.xml", b"xl/a\x00b.xml")
        self.assert_fails(raw, "unsafe_part_name")

    def test_directory_entry_with_content_fails(self):
        parts = minimal_parts()
        parts["xl/book.xml/"] = b"x"
        self.assert_fails(self.parts_zip(parts), "unsafe_part_name")

    def test_empty_directory_entry_passes(self):
        parts = minimal_parts()
        parts["xl/"] = b""
        self.assertEqual(self.check(self.parts_zip(parts))["result"], "pass")

    def test_non_ascii_name_without_utf8_flag_fails(self):
        parts = minimal_parts()
        parts["xl/表.xml"] = b"<a/>"
        raw = bytearray(self.parts_zip(parts))
        for sig, offset in ((b"PK\x03\x04", 7), (b"PK\x01\x02", 9)):
            i = raw.find(sig)
            while i != -1:
                raw[i + offset] &= ~0x08
                i = raw.find(sig, i + 4)
        self.assert_fails(bytes(raw), "unsafe_part_name")


if __name__ == "__main__":
    unittest.main()
