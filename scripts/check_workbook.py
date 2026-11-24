"""Pre-read safety checker for Excel workbooks received from outside.

Standalone on purpose: standard library only, reads only the target file, and
prints only fixed vocabulary, counts and booleans (never strings from the file).
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import stat
import struct
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
import zlib

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".xltx", ".xltm", ".xlam", ".xlsb")
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_PARTS = 10_000
MAX_TOTAL_UNCOMPRESSED = 1024 ** 3
MAX_RATIO = 100
RATIO_GRACE_BYTES = 100 * 1024
READ_CHUNK = 64 * 1024
MAX_PARSE_BYTES = 32 * 1024 * 1024
LONG_STRING_CHARS = 10_000

FAILURE_CODES = (
    "unsupported_extension",
    "file_too_large",
    "encrypted",
    "not_zip",
    "too_many_parts",
    "unsafe_part_name",
    "uncompressed_too_large",
    "compression_ratio_too_high",
    "xml_dtd",
)

WARNING_CODES = (
    "vba_project",
    "external_link",
    "data_connection",
    "external_relationship",
    "power_query",
    "embedded_object",
    "activex",
    "hidden_sheet",
    "very_hidden_sheet",
    "invisible_characters",
    "instruction_like_text",
    "very_long_string",
    "strings_not_checked",
)

INSTRUCTION_PHRASES = (
    "ignore previous", "ignore all previous", "ignore the above", "disregard previous",
    "system prompt", "you are now", "new instructions", "do not tell the user",
    "前の指示を無視", "以前の指示を無視", "上記の指示を無視", "これまでの指示を無視",
    "システムプロンプト", "あなたは今から",
)
INVISIBLE_CODEPOINTS = (
    set(range(0x200B, 0x2010)) | {0x2060, 0xFEFF, 0x061C}
    | set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
    | set(range(0xE0000, 0xE0080))
)
_INVISIBLE_CHARS = frozenset(chr(c) for c in INVISIBLE_CODEPOINTS)
_INVISIBLE_STRIP = {c: None for c in INVISIBLE_CODEPOINTS}
_BOMS = ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))
_REL_OFFICE_DOCUMENT = "/relationships/officeDocument"

OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
ENCRYPTED_PACKAGE = "EncryptedPackage".encode("utf-16-le")
ALLOWED_METHODS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
# Errors zipfile raises for corrupt or crafted archives.
ZIP_ERRORS = (
    zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, zlib.error,
    EOFError, NotImplementedError, OSError,
)
_DTD_WORDS = ("<!DOCTYPE", "<!ENTITY")
_DTD_NEEDLES = tuple(
    w.encode(enc) for w in _DTD_WORDS for enc in ("utf-8", "utf-16-le", "utf-16-be")
)
_TAIL = max(len(n) for n in _DTD_NEEDLES) - 1
_DRIVE = re.compile(r"^[A-Za-z]:")


def _result(failures, warnings=None, counts=None):
    return {
        "result": "fail" if failures else "pass",
        "failures": failures,
        "warnings": warnings or [],
        "counts": counts or {},
    }


def _unsafe_name(name):
    if name.startswith("/") or "\\" in name or _DRIVE.match(name):
        return True
    return ".." in name.split("/")


def _check_part(zf, info, total):
    """Stream one part. Returns (failure_or_None, new_total)."""
    size = 0
    tail = b""
    with zf.open(info) as f:
        while True:
            chunk = f.read(READ_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            total += len(chunk)
            if total > MAX_TOTAL_UNCOMPRESSED:
                return "uncompressed_too_large", total
            if size > RATIO_GRACE_BYTES and size > MAX_RATIO * max(info.compress_size, 1):
                return "compression_ratio_too_high", total
            # Part types come from the package metadata, so scan every part.
            window = tail + chunk
            if any(n in window for n in _DTD_NEEDLES):
                return "xml_dtd", total
            tail = window[-_TAIL:]
    return None, total


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


SNIFF_BYTES = 4096
_MASHUP_NEEDLES = tuple(
    "DataMashup".encode(enc) for enc in ("utf-8", "utf-16-le", "utf-16-be")
)
_MASHUP_TAIL = max(len(n) for n in _MASHUP_NEEDLES) - 1
# Relationship Type suffix -> warning code. Renaming a part does not change this.
_REL_TYPE_WARNINGS = (
    ("/vbaProject", "vba_project"),
    ("/externalLink", "external_link"),
    ("/oleObject", "embedded_object"),
    ("/package", "embedded_object"),
    ("/control", "activex"),
    ("/connections", "data_connection"),
)
_MAX_OFFICE_TARGETS = 100


def _looks_like_xml(head):
    """True when, after an optional BOM and whitespace, the first character is "<".

    Only the first SNIFF_BYTES are looked at, so the decision is linear; a part
    with more leading whitespace than that is treated as not XML.
    """
    head = head[:SNIFF_BYTES]
    candidates = [(head, enc) for enc in ("utf-8", "utf-16-le", "utf-16-be")]
    for bom, enc in _BOMS:
        if head.startswith(bom):
            candidates.append((head[len(bom):], enc))
    return any(
        body.decode(enc, "ignore").lstrip(" \t\r\n\ufeff").startswith("<")
        for body, enc in candidates
    )


class _Collector(object):
    """Event target for the XML parser: keeps counters, never a tree."""

    def __init__(self, counts, is_rels, is_root_rels):
        self.counts = counts
        self.is_rels = is_rels
        self.is_root_rels = is_root_rels
        self.office_targets = []
        self.hidden = 0
        self.very_hidden = 0
        self._text = []

    def _flush(self):
        if self._text:
            _count_string("".join(self._text), self.counts)
            self._text = []

    def start(self, tag, attrib):
        self._flush()
        for v in attrib.values():
            _count_string(v, self.counts)
        name = _local(tag)
        if name == "sheet":
            state = attrib.get("state")
            if state == "hidden":
                self.hidden += 1
            elif state == "veryHidden":
                self.very_hidden += 1
        elif name == "Relationship" and self.is_rels:
            rtype = attrib.get("Type", "")
            external = attrib.get("TargetMode", "").lower() == "external"
            if external:
                self.counts["external_relationship"] += 1
            for suffix, code in _REL_TYPE_WARNINGS:
                if rtype.endswith(suffix):
                    self.counts[code] += 1
            if (
                self.is_root_rels and not external
                and rtype.endswith(_REL_OFFICE_DOCUMENT)
                and len(self.office_targets) < _MAX_OFFICE_TARGETS
            ):
                self.office_targets.append(attrib.get("Target", ""))

    def end(self, tag):
        self._flush()

    def data(self, text):
        self._text.append(text)

    def close(self):
        self._flush()


def _count_string(value, counts):
    if not value or not value.strip():
        return
    if len(value) > LONG_STRING_CHARS:
        counts["very_long_string"] += 1
    if not _INVISIBLE_CHARS.isdisjoint(value):
        counts["invisible_characters"] += 1
    folded = unicodedata.normalize("NFKC", value).lower().translate(_INVISIBLE_STRIP)
    if any(p in folded for p in INSTRUCTION_PHRASES):
        counts["instruction_like_text"] += 1


def _scan_part(zf, info, counts, parse_xml, is_rels, is_root_rels):
    """Stream one part once: DataMashup marker scan plus, when asked, an XML pass.

    Returns the collector (or None when the part was not parsed as XML).
    """
    collector = None
    parser = None
    first = True
    total = 0
    mashup = False
    unchecked = False
    tail = b""
    try:
        with zf.open(info) as f:
            while True:
                chunk = f.read(READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                window = tail + chunk
                if not mashup and any(n in window for n in _MASHUP_NEEDLES):
                    mashup = True
                tail = window[-_MASHUP_TAIL:]
                if first:
                    first = False
                    if parse_xml and _looks_like_xml(chunk):
                        collector = _Collector(counts, is_rels, is_root_rels)
                        parser = ET.XMLParser(target=collector)
                if parser is None:
                    continue
                if total > MAX_PARSE_BYTES:
                    parser = None
                    unchecked = True
                    continue
                parser.feed(chunk)
            if parser is not None:
                parser.close()
    except Exception:
        unchecked = True
    if mashup:
        counts["power_query"] += 1
    if unchecked:
        counts["strings_not_checked"] += 1
    return collector


def _resolve(by_lower, target):
    """Resolve a root-relationship target inside the archive ("/" = package root)."""
    target = posixpath.normpath(target.lstrip("/"))
    if target in ("", ".", "..") or target.startswith("../"):
        return None
    return by_lower.get(target.lower())


def _scan_warnings(zf, infos, is_xlsb):
    # Count units: file-name and relationship warnings count parts/relationships
    # (one object found through both a name and a relationship counts twice);
    # string warnings count values (text runs and attribute values); the sheet
    # warnings count <sheet> elements; strings_not_checked counts parts.
    counts = dict.fromkeys(WARNING_CODES, 0)
    by_lower = {i.filename.lower(): i for i in infos}
    sheets = {}
    office_targets = []
    for info in infos:
        name = info.filename.lower()
        if name.endswith("/"):
            continue
        if name.endswith("vbaproject.bin"):
            counts["vba_project"] += 1
        if "externallinks/" in name:
            counts["external_link"] += 1
        if name.rsplit("/", 1)[-1] == "connections.xml":
            counts["data_connection"] += 1
        if "embeddings/" in name:
            counts["embedded_object"] += 1
        if "activex/" in name:
            counts["activex"] += 1
        # customXml/ is never parsed: it holds data, not workbook strings.
        parse_xml = not is_xlsb and not name.startswith("customxml/")
        collector = _scan_part(
            zf, info, counts, parse_xml, name.endswith(".rels"), info.filename == "_rels/.rels"
        )
        if collector is not None:
            sheets[name] = (collector.hidden, collector.very_hidden)
            office_targets.extend(collector.office_targets)
    if is_xlsb:
        # Binary parts are not read, so neither strings nor sheet states are known.
        counts["strings_not_checked"] += 1
    else:
        seen = set()
        for target in office_targets:
            info = _resolve(by_lower, target)
            if info is None or info.filename in seen or info.filename.lower() not in sheets:
                continue
            seen.add(info.filename)
            hidden, very_hidden = sheets[info.filename.lower()]
            counts["hidden_sheet"] += hidden
            counts["very_hidden_sheet"] += very_hidden
    warnings = [c for c in WARNING_CODES if counts[c]]
    return warnings, {c: counts[c] for c in warnings}


_EOCD_SIG = b"PK\x05\x06"
_ZIP64_LOCATOR_SIG = b"PK\x06\x07"
_CEN_SIG = b"PK\x01\x02"
_LOC_SIG = b"PK\x03\x04"
_DD_SIG = b"PK\x07\x08"
_EOCD_LEN = 22
_CEN_LEN = 46
_LOC_LEN = 30
_EXTRA_ZIP64 = 0x0001
_EXTRA_UNICODE_PATH = 0x7075
_FLAG_DESCRIPTOR = 0x8
_FLAG_UTF8 = 0x800


def _read_at(f, offset, length):
    f.seek(offset)
    data = f.read(length)
    return data if len(data) == length else None


def _extra_ok(extra):
    """True when extra is an exact run of (id, length, data) blocks without ZIP64 or Unicode Path."""
    pos = 0
    while pos < len(extra):
        if pos + 4 > len(extra):
            return False
        block_id, block_len = struct.unpack("<HH", extra[pos:pos + 4])
        if block_id in (_EXTRA_ZIP64, _EXTRA_UNICODE_PATH):
            return False
        pos += 4 + block_len
    return pos == len(extra)


def _bad_name(name, flags, csize, usize):
    """True when the entry name is not one every reader decodes and splits alike."""
    if flags & _FLAG_UTF8:
        try:
            name.decode("utf-8")
        except UnicodeDecodeError:
            return True
    elif any(b > 0x7F for b in name):
        return True
    if b"\x00" in name:
        return True
    is_dir = name.endswith(b"/")
    if is_dir and (csize or usize):
        return True
    segments = (name[:-1] if is_dir else name).split(b"/")
    return any(s in (b"", b".") for s in segments)


def _check_layout(path, size):
    """Accept only ZIP layouts that every reader reads the same way.

    Reads the bytes directly, since readers disagree on prefixes, comments,
    several central directories, ZIP64 and Unicode Path. Returns a failure code
    or None.
    """
    if size < _EOCD_LEN:
        return "not_zip"
    with open(path, "rb") as f:
        eocd = _read_at(f, size - _EOCD_LEN, _EOCD_LEN)
        if eocd is None or eocd[:4] != _EOCD_SIG:
            return "not_zip"
        disk, cd_disk, n_disk, n_total, cd_size, cd_off, comment_len = struct.unpack(
            "<HHHHIIH", eocd[4:]
        )
        if comment_len or disk or cd_disk or n_disk != n_total:
            return "not_zip"
        if size >= _EOCD_LEN + 20 and _read_at(f, size - 42, 4) == _ZIP64_LOCATOR_SIG:
            return "not_zip"
        if 0xFFFF in (n_disk, n_total) or 0xFFFFFFFF in (cd_size, cd_off):
            return "not_zip"
        if cd_off + cd_size != size - _EOCD_LEN:
            return "not_zip"
        cd = _read_at(f, cd_off, cd_size)
        if cd is None:
            return "not_zip"
        entries = []
        pos = 0
        for _ in range(n_total):
            head = cd[pos:pos + _CEN_LEN]
            if len(head) < _CEN_LEN or head[:4] != _CEN_SIG:
                return "not_zip"
            (flags, method, _t, _d, crc, csize, usize, nlen, xlen, clen,
             _dn, _ia, _ea, off) = struct.unpack("<HHHHIIIHHHHHII", head[8:])
            if 0xFFFFFFFF in (csize, usize, off):
                return "not_zip"
            end = pos + _CEN_LEN + nlen + xlen + clen
            if end > len(cd):
                return "not_zip"
            name = cd[pos + _CEN_LEN:pos + _CEN_LEN + nlen]
            if not _extra_ok(cd[pos + _CEN_LEN + nlen:pos + _CEN_LEN + nlen + xlen]):
                return "not_zip"
            entries.append((off, flags, method, crc, csize, usize, name))
            pos = end
        if pos != len(cd):
            return "not_zip"
        entries.sort(key=lambda e: e[0])
        expected = 0
        for off, flags, method, crc, csize, usize, name in entries:
            if off != expected:
                return "not_zip"
            loc = _read_at(f, off, _LOC_LEN)
            if loc is None or loc[:4] != _LOC_SIG:
                return "not_zip"
            lflags, lmethod, _t, _d, lcrc, lcsize, lusize, lnlen, lxlen = struct.unpack(
                "<HHHHIIIHH", loc[6:]
            )
            if lflags != flags or lmethod != method or lnlen != len(name):
                return "not_zip"
            if not flags & _FLAG_DESCRIPTOR and (lcrc, lcsize, lusize) != (crc, csize, usize):
                return "not_zip"
            tail = _read_at(f, off + _LOC_LEN, lnlen + lxlen)
            if tail is None or tail[:lnlen] != name or not _extra_ok(tail[lnlen:]):
                return "not_zip"
            expected = off + _LOC_LEN + lnlen + lxlen + csize
            if flags & _FLAG_DESCRIPTOR:
                sig = _read_at(f, expected, 4)
                if sig is None:
                    return "not_zip"
                expected += 16 if sig == _DD_SIG else 12
        if expected != cd_off:
            return "not_zip"
    for _off, flags, _m, _c, csize, usize, name in entries:
        if _bad_name(name, flags, csize, usize):
            return "unsafe_part_name"
    return None


def check(path):
    if os.path.splitext(path)[1].lower() not in SUPPORTED_EXTENSIONS:
        return _result(["unsupported_extension"])
    if os.path.getsize(path) > MAX_FILE_BYTES:
        return _result(["file_too_large"])
    with open(path, "rb") as f:
        head = f.read(len(OLE_MAGIC))
        if head == OLE_MAGIC:
            data = head + f.read(MAX_FILE_BYTES)
            return _result(["encrypted" if ENCRYPTED_PACKAGE in data else "not_zip"])
    layout = _check_layout(path, os.path.getsize(path))
    if layout:
        return _result([layout])
    try:
        zf = zipfile.ZipFile(path)
    except ZIP_ERRORS:
        return _result(["not_zip"])
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_PARTS:
            return _result(["too_many_parts"])
        if any(i.compress_type not in ALLOWED_METHODS for i in infos):
            return _result(["not_zip"])
        if any(_unsafe_name(i.filename) for i in infos):
            return _result(["unsafe_part_name"])
        # OPC part names are unique when compared case-insensitively.
        if len({i.filename.lower() for i in infos}) != len(infos):
            return _result(["unsafe_part_name"])
        if any(i.flag_bits & 0x1 for i in infos):
            return _result(["encrypted"])
        # Declared sizes can lie; their sum cannot exceed the file itself.
        if sum(i.compress_size for i in infos) > os.path.getsize(path):
            return _result(["not_zip"])
        total = 0
        for info in infos:
            try:
                failure, total = _check_part(zf, info, total)
            except ZIP_ERRORS + (RuntimeError,):
                return _result(["not_zip"])
            if failure:
                return _result([failure])
        try:
            is_xlsb = os.path.splitext(path)[1].lower() == ".xlsb"
            warnings, counts = _scan_warnings(zf, infos, is_xlsb)
        except ZIP_ERRORS + (RuntimeError,):
            return _result(["not_zip"])
    return _result([], warnings, counts)


def _emit(result, failures):
    out = {"result": result, "failures": failures, "warnings": [], "counts": {}}
    sys.stdout.write(json.dumps(out) + "\n")


def main(argv):
    if len(argv) != 1 or not os.path.isabs(argv[0]):
        _emit("error", ["usage"])
        return 2
    try:
        fd = os.open(argv[0], os.O_RDONLY | os.O_NONBLOCK)
        try:
            regular = stat.S_ISREG(os.fstat(fd).st_mode)
        finally:
            os.close(fd)
        if not regular:
            raise OSError
        result = check(argv[0])
    except Exception:
        _emit("error", ["unreadable"])
        return 2
    sys.stdout.write(json.dumps(result) + "\n")
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
