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


_WS_BYTES = b" \t\r\n\x00\xef\xbb\xbf\xff\xfe"
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
    """True/False once decidable; None while the bytes are only BOM and whitespace.

    XML means: after an optional BOM and whitespace, the first character is "<"
    in UTF-8, UTF-16LE or UTF-16BE.
    """
    if not head.strip(_WS_BYTES):
        return None
    candidates = [(head, enc) for enc in ("utf-8", "utf-16-le", "utf-16-be")]
    for bom, enc in _BOMS:
        if head.startswith(bom):
            candidates.append((head[len(bom):], enc))
    return any(
        body.decode(enc, "ignore").lstrip(" \t\r\n﻿").startswith("<")
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
    pending = b""
    deciding = parse_xml
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
                if parser is None and not deciding:
                    continue
                if total > MAX_PARSE_BYTES:
                    if parser is not None or (deciding and _looks_like_xml(pending + chunk)):
                        unchecked = True
                    parser = None
                    deciding = False
                    pending = b""
                    continue
                if deciding:
                    pending += chunk
                    verdict = _looks_like_xml(pending)
                    if verdict is None:
                        continue
                    deciding = False
                    if not verdict:
                        pending = b""
                        continue
                    collector = _Collector(counts, is_rels, is_root_rels)
                    parser = ET.XMLParser(target=collector)
                    chunk, pending = pending, b""
                if parser is not None:
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
