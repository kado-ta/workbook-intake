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


def _looks_like_xml(head):
    """True when, after an optional BOM and whitespace, the first character is "<"."""
    candidates = [(head, enc) for enc in ("utf-8", "utf-16-le", "utf-16-be")]
    for bom, enc in _BOMS:
        if head.startswith(bom):
            candidates.append((head[len(bom):], enc))
    for body, enc in candidates:
        text = body.decode(enc, "ignore").lstrip()
        if text.startswith("<"):
            return True
        if not text and body:
            return True  # nothing but whitespace in the first chunk
    return False


def _load(zf, info):
    """Parse one part. Returns (status, root); status is skip, unchecked or ok."""
    if info.filename.endswith("/") or info.file_size == 0:
        return "skip", None
    try:
        with zf.open(info) as f:
            head = f.read(READ_CHUNK)
            if not _looks_like_xml(head):
                return "skip", None
            data = head + f.read(MAX_PARSE_BYTES + 1 - len(head))
        if len(data) > MAX_PARSE_BYTES:
            return "unchecked", None
        return "ok", ET.fromstring(data)
    except Exception:
        return "unchecked", None


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


def _count_strings(root, counts):
    for el in root.iter():
        _count_string(el.text, counts)
        _count_string(el.tail, counts)
        for v in el.attrib.values():
            _count_string(v, counts)


def _workbook_part(zf, by_lower, root_rels):
    """Resolve the officeDocument target from _rels/.rels, inside the archive only."""
    if root_rels is None:
        return None
    for rel in root_rels.iter():
        if _local(rel.tag) != "Relationship":
            continue
        if not rel.get("Type", "").endswith(_REL_OFFICE_DOCUMENT):
            continue
        if rel.get("TargetMode", "").lower() == "external":
            continue
        target = rel.get("Target", "")
        target = posixpath.normpath(target.lstrip("/"))
        if target in ("", ".") or target == ".." or target.startswith("../"):
            continue
        return by_lower.get(target.lower())
    return None


def _scan_warnings(zf, infos, is_xlsb):
    counts = dict.fromkeys(WARNING_CODES, 0)
    by_lower = {i.filename.lower(): i for i in infos}
    root_rels = None
    for info in infos:
        name = info.filename.lower()
        base = name.rsplit("/", 1)[-1]
        if name.endswith("vbaproject.bin"):
            counts["vba_project"] += 1
        if "externallinks/" in name:
            counts["external_link"] += 1
        if base == "connections.xml":
            counts["data_connection"] += 1
        if "embeddings/" in name:
            counts["embedded_object"] += 1
        if "activex/" in name:
            counts["activex"] += 1
        if name.startswith("customxml/"):
            # Power Query keeps its mashup in customXml; the marker may be UTF-16.
            try:
                with zf.open(info) as f:
                    data = f.read(MAX_PARSE_BYTES + 1)
            except ZIP_ERRORS + (RuntimeError,):
                data = b""
            if len(data) > MAX_PARSE_BYTES:
                counts["strings_not_checked"] += 1
            elif any(m in data for m in (b"DataMashup", "DataMashup".encode("utf-16-le"), "DataMashup".encode("utf-16-be"))):
                counts["power_query"] += 1
            continue
        status, root = _load(zf, info)
        if status == "unchecked":
            counts["strings_not_checked"] += 1
            continue
        if status == "skip":
            continue
        if info.filename == "_rels/.rels":
            root_rels = root
        if name.endswith(".rels") and any(
            _local(e.tag) == "Relationship" and e.get("TargetMode", "").lower() == "external"
            for e in root.iter()
        ):
            counts["external_relationship"] += 1
        if not is_xlsb:
            _count_strings(root, counts)
    if is_xlsb:
        # Binary parts are not read, so neither strings nor sheet states are known.
        counts["strings_not_checked"] += 1
    else:
        info = _workbook_part(zf, by_lower, root_rels)
        if info is not None:
            status, root = _load(zf, info)
            if status == "ok":
                for el in root.iter():
                    if _local(el.tag) == "sheet":
                        state = el.get("state")
                        if state == "hidden":
                            counts["hidden_sheet"] += 1
                        elif state == "veryHidden":
                            counts["very_hidden_sheet"] += 1
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
