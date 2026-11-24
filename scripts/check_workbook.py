"""Pre-read safety checker for Excel workbooks received from outside.

Standalone on purpose: standard library only, reads only the target file, and
prints only fixed vocabulary, counts and booleans (never strings from the file).
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import zipfile
import zlib

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".xltx", ".xltm", ".xlam", ".xlsb")
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_PARTS = 10_000
MAX_TOTAL_UNCOMPRESSED = 1024 ** 3
MAX_RATIO = 100
RATIO_GRACE_BYTES = 100 * 1024
READ_CHUNK = 64 * 1024

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
    return _result([])


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
