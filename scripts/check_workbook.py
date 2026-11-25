"""Pre-read safety checker for Excel workbooks received from outside.

Standalone on purpose: standard library only, reads only the target file, and
prints only fixed vocabulary, counts and booleans (never strings from the file).
"""
from __future__ import annotations

import codecs
import json
import os
import re
import stat
import struct
import sys
import unicodedata
import zipfile
import zlib
from xml.parsers import expat

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".xltx", ".xltm", ".xlam", ".xlsb")
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_PARTS = 10_000
MAX_TOTAL_UNCOMPRESSED = 1024 ** 3
MAX_RATIO = 100
RATIO_GRACE_BYTES = 100 * 1024
READ_CHUNK = 64 * 1024
MAX_PARSE_BYTES = 32 * 1024 * 1024
LONG_STRING_CHARS = 10_000
PHRASE_OVERLAP = 256
# pyofficeeditor refuses an element nested deeper than this below the root.
MAX_DEPTH = 256

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
    """Stream one part's data bytes. Returns (failure_or_None, new_total).

    Reads the bytes the central directory points at, not what zipfile makes of
    them: the stream must end exactly at the compressed size, inflate to exactly
    the declared size and match the declared CRC, so every reader sees the same.
    """
    fp = zf.fp
    fp.seek(info.header_offset + 26)
    nlen, xlen = struct.unpack("<HH", fp.read(4))
    fp.seek(info.header_offset + _LOC_LEN + nlen + xlen)
    stored = info.compress_type == zipfile.ZIP_STORED
    if stored and info.compress_size != info.file_size:
        return "not_zip", total
    inflater = None if stored else zlib.decompressobj(-15)
    remaining = info.compress_size
    state = {"size": 0, "crc": 0, "total": total, "tail": b""}

    def take(chunk):
        """Account for one output chunk. Returns a failure code or None."""
        state["size"] += len(chunk)
        state["total"] += len(chunk)
        state["crc"] = zlib.crc32(chunk, state["crc"])
        if state["total"] > MAX_TOTAL_UNCOMPRESSED:
            return "uncompressed_too_large"
        size = state["size"]
        if size > RATIO_GRACE_BYTES and size > MAX_RATIO * max(info.compress_size, 1):
            return "compression_ratio_too_high"
        # Part types come from the package metadata, so scan every part.
        window = state["tail"] + chunk
        if any(n in window for n in _DTD_NEEDLES):
            return "xml_dtd"
        state["tail"] = window[-_TAIL:]
        if size > info.file_size:
            return "not_zip"
        return None

    while remaining > 0 or (inflater is not None and not inflater.eof):
        raw = fp.read(min(READ_CHUNK, remaining))
        if not raw:
            return "not_zip", state["total"]
        remaining -= len(raw)
        if inflater is None:
            failure = take(raw)
            if failure:
                return failure, state["total"]
            continue
        buf = raw
        while True:
            # Never inflate past what the central directory allows (+1 to notice).
            limit = min(READ_CHUNK, info.file_size - state["size"] + 1)
            out = inflater.decompress(buf, limit)
            buf = inflater.unconsumed_tail
            if out:
                failure = take(out)
                if failure:
                    return failure, state["total"]
            # Keep draining while the output limit, not the input, stopped zlib.
            if inflater.eof or (not buf and len(out) < limit):
                break
        if inflater.eof and (buf or inflater.unused_data or remaining):
            return "not_zip", state["total"]
    if state["size"] != info.file_size or state["crc"] != info.CRC:
        return "not_zip", state["total"]
    return None, state["total"]


def _local(name):
    """The part of a qualified name after the last ":" (xmlns:Target -> Target)."""
    return name.rpartition(":")[2]


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
# Codec pyofficeeditor decodes a part with -> the same encoding's name in expat.
_EXPAT_ENCODINGS = {"utf-8": "UTF-8", "utf-16-le": "UTF-16LE", "utf-16-be": "UTF-16BE"}
# Excel's escape for one UTF-16 code unit, as xlide decodes it.
_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{4})_")
_SURROGATE_SEARCH = re.compile("[\ud800-\udfff]").search
_TEXT_BLOCK = 8192
# Finds any of INSTRUCTION_PHRASES in one call (values are many and mostly short).
_PHRASE_SEARCH = re.compile("|".join(re.escape(p) for p in INSTRUCTION_PHRASES)).search


def _encoding(head):
    """The codec pyofficeeditor reads a part with, chosen from its first bytes."""
    for bom, enc in _BOMS:
        if head.startswith(bom):
            return enc
    if head[:2] == b"<\x00":
        return "utf-16-le"
    if head[:2] == b"\x00<":
        return "utf-16-be"
    return "utf-8"


class _Text(object):
    """Text that arrives in pieces, joined every _TEXT_BLOCK pieces so the pieces do not stay objects."""

    __slots__ = ("blocks", "pieces")

    def __init__(self):
        self.blocks = []
        self.pieces = []

    def add(self, text):
        self.pieces.append(text)
        if len(self.pieces) >= _TEXT_BLOCK:
            self.blocks.append("".join(self.pieces))
            self.pieces = []

    def value(self):
        self.blocks.append("".join(self.pieces))
        self.pieces = []
        return "".join(self.blocks)


class _Joined(object):
    """Text values joined twice: as written, and each one unescaped before joining."""

    __slots__ = ("raw", "decoded", "changed", "lines")

    def __init__(self):
        self.raw = _Text()
        self.decoded = _Text()
        self.changed = False
        self.lines = 0

    def add(self, raw, decoded):
        self.raw.add(raw)
        self.decoded.add(decoded)
        if decoded != raw:
            self.changed = True

    def add_line(self, raw, decoded):
        """Add one paragraph, after a newline unless it is the first."""
        if self.lines:
            self.add("\n", "\n")
        self.lines += 1
        self.add(raw, decoded)

    def count(self, counts):
        """Count both joins. Returns them (as written, unescaped)."""
        raw = self.raw.value()
        _count_string(raw, counts)
        decoded = raw
        if self.changed:
            decoded = self.decoded.value()
            _count_string(decoded, counts)
        return raw, decoded


class _Collector(object):
    """expat handlers that count into one part's own counters, never a tree.

    Strings are the values xlide reads:
    - each element's direct text joined across its children (as
      Element.text, without CDATA), and each CDATA section on its own;
    - for si and is, the text of their r/t runs joined (shared and inline
      strings);
    - for p, the text of every t below it joined, and for rich, its p
      children joined with newlines (chart titles and series names).
    Joined runs are also checked with each run unescaped first, as xlide
    decodes each run before joining. A t inside another t below an open p,
    or a rich in a p, is not joined in xlide's order and marks the part
    unchecked.
    """

    def __init__(self):
        self.counts = dict.fromkeys(WARNING_CODES, 0)
        self.unchecked = False
        # One [local name, direct text, _Joined or None] per open element.
        self._open = []
        self._cdata = None
        # The outermost open p collects every t below it.
        self._paragraph = None
        self._open_t = 0
        # Open t elements when the outermost p opened.
        self._paragraph_t = 0

    def start(self, name, attrs):
        if len(self._open) > MAX_DEPTH:
            raise ValueError("nested deeper than xlide reads")
        # attrs is [name, value, ...] in document order, xmlns declarations included.
        first = {}
        for i in range(0, len(attrs), 2):
            _count_string(attrs[i + 1], self.counts)
            local = _local(attrs[i])
            if local in first:
                self.unchecked = True
            else:
                first[local] = attrs[i + 1]
        name = _local(name)
        joined = None
        if name in ("si", "is"):
            joined = _Joined()
        elif name == "p":
            if self._paragraph is None:
                joined = self._paragraph = _Joined()
                self._paragraph_t = self._open_t
        elif name == "rich":
            if self._paragraph is None:
                joined = _Joined()
            else:
                self.unchecked = True
        elif name == "t":
            # Only a t inside another t below the p (not one around it, as
            # SmartArt's dgm:t text body) changes xlide's order.
            if self._paragraph is not None and self._open_t > self._paragraph_t:
                self.unchecked = True
            self._open_t += 1
        self._open.append([name, None, joined])
        if name == "sheet":
            state = first.get("state")
            if state == "hidden":
                self.counts["hidden_sheet"] += 1
            elif state == "veryHidden":
                self.counts["very_hidden_sheet"] += 1
        elif name == "Relationship":
            if first.get("TargetMode", "").lower() == "external":
                self.counts["external_relationship"] += 1
            rtype = first.get("Type", "")
            for suffix, code in _REL_TYPE_WARNINGS:
                if rtype.endswith(suffix):
                    self.counts[code] += 1
        elif name == "externalReference":
            self.counts["external_link"] += 1

    def end(self, name):
        local, text, joined = self._open.pop()
        value = "" if text is None else text.value()
        decoded = None
        if local == "t":
            self._open_t -= 1
            run_of = None
            if len(self._open) > 1 and self._open[-1][0] == "r" and self._open[-2][0] in ("si", "is"):
                run_of = self._open[-2][2]
            if run_of is not None or self._paragraph is not None:
                decoded = _unescape(value)
                if run_of is not None:
                    run_of.add(value, decoded)
                if self._paragraph is not None:
                    self._paragraph.add(value, decoded)
        elif joined is not None:
            line, line_decoded = joined.count(self.counts)
            if joined is self._paragraph:
                self._paragraph = None
                parent = self._open[-1] if self._open else None
                if parent is not None and parent[0] == "rich" and parent[2] is not None:
                    parent[2].add_line(line, line_decoded)
        if value:
            _count_string(value, self.counts, decoded)

    def data(self, text):
        if self._cdata is not None:
            self._cdata.add(text)
            return
        top = self._open[-1]
        if top[1] is None:
            top[1] = _Text()
        top[1].add(text)

    def cdata_start(self):
        self._cdata = _Text()

    def cdata_end(self):
        text, self._cdata = self._cdata, None
        _count_string(text.value(), self.counts)

    def close(self):
        """Count what is still open, for a part that ended early or failed."""
        if self._cdata is not None:
            self.cdata_end()
        while self._open:
            self.end(None)


def _escaped_char(m):
    return chr(int(m.group(1), 16))


def _unescape(value):
    """value with _xHHHH_ escapes decoded and surrogate halves joined, as xlide reads it."""
    if "_x" not in value:
        return value
    if len(value) <= _TEXT_BLOCK:
        decoded = _ESCAPE.sub(_escaped_char, value)
    else:
        # Like _ESCAPE.sub, but joined as it goes so a long value made of
        # escapes does not hold one object per escape.
        done, pieces, last = [], [], 0
        for m in _ESCAPE.finditer(value):
            pieces.append(value[last:m.start()])
            pieces.append(_escaped_char(m))
            last = m.end()
            if len(pieces) >= _TEXT_BLOCK:
                done.append("".join(pieces))
                pieces = []
        pieces.append(value[last:])
        done.append("".join(pieces))
        decoded = "".join(done)
    if _SURROGATE_SEARCH(decoded):
        decoded = decoded.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")
    return decoded


def _has_phrase(value):
    """True when an instruction-like phrase appears in value once folded.

    A long value loses its invisible characters first and is then folded in
    overlapping windows, so normalize never sees more than
    LONG_STRING_CHARS + PHRASE_OVERLAP characters.
    """
    if len(value) > LONG_STRING_CHARS and not _INVISIBLE_CHARS.isdisjoint(value):
        value = value.translate(_INVISIBLE_STRIP)
    for start in range(0, len(value), LONG_STRING_CHARS):
        window = value[start:start + LONG_STRING_CHARS + PHRASE_OVERLAP]
        folded = unicodedata.normalize("NFKC", window).lower().translate(_INVISIBLE_STRIP)
        if _PHRASE_SEARCH(folded):
            return True
    return False


def _count_string(value, counts, decoded=None):
    """Count one value; decoded is _unescape(value) when the caller has it already."""
    if not value or not value.strip():
        return
    if len(value) > LONG_STRING_CHARS:
        counts["very_long_string"] += 1
    if decoded is None:
        decoded = _unescape(value)
    if decoded == value:
        invisible = not _INVISIBLE_CHARS.isdisjoint(value)
        phrase = _has_phrase(value)
    else:
        invisible = not (_INVISIBLE_CHARS.isdisjoint(value) and _INVISIBLE_CHARS.isdisjoint(decoded))
        phrase = _has_phrase(value) or _has_phrase(decoded)
    if invisible:
        counts["invisible_characters"] += 1
    if phrase:
        counts["instruction_like_text"] += 1


def _new_parser(enc, collector):
    # No namespace processing; the given encoding overrides any declared one.
    parser = expat.ParserCreate(encoding=_EXPAT_ENCODINGS[enc])
    parser.ordered_attributes = True
    parser.buffer_text = True
    parser.StartElementHandler = collector.start
    parser.EndElementHandler = collector.end
    parser.CharacterDataHandler = collector.data
    # With buffer_text, pending text is handed over before these are called.
    parser.StartCdataSectionHandler = collector.cdata_start
    parser.EndCdataSectionHandler = collector.cdata_end
    return parser


def _scan_part(zf, info, counts, read_xml):
    """Stream one part once: DataMashup marker scan and, when asked, an XML pass.

    The part is XML when all of it decodes strictly in the encoding its first
    bytes select and it contains "<". It is parsed in the same pass into its
    own counters, which are added to counts only once the part is known to be
    XML. An XML part expat cannot read, or that _Collector marks unchecked
    (two attributes of one local name on an element, nesting it cannot join
    as xlide does), adds one strings_not_checked.
    """
    mashup = False
    tail = b""
    decoder = parser = collector = None
    is_text = read_xml
    has_lt = False
    failed = False
    with zf.open(info) as f:
        while True:
            chunk = f.read(READ_CHUNK)
            if not chunk:
                break
            window = tail + chunk
            if not mashup and any(n in window for n in _MASHUP_NEEDLES):
                mashup = True
            tail = window[-_MASHUP_TAIL:]
            if not is_text:
                continue
            if decoder is None:
                # zipfile's read(n) returns n bytes unless the part is shorter.
                enc = _encoding(chunk)
                decoder = codecs.getincrementaldecoder(enc)("strict")
                if info.file_size <= MAX_PARSE_BYTES:
                    collector = _Collector()
                    # Without a BOM, expat itself switches to UTF-16 when either
                    # of the first two bytes is NUL; read as UTF-8 they are not XML.
                    if enc == "utf-8" and b"\x00" in chunk[:2]:
                        failed = True
                    else:
                        parser = _new_parser(enc, collector)
            try:
                has_lt = "<" in decoder.decode(chunk) or has_lt
            except UnicodeDecodeError:
                is_text = False
                continue
            if parser is not None:
                parser, failed = _feed(parser, chunk, False, collector)
    if is_text and decoder is not None:
        try:
            decoder.decode(b"", True)
        except UnicodeDecodeError:
            is_text = False
    if is_text and parser is not None:
        parser, failed = _feed(parser, b"", True, collector)
    if mashup:
        counts["power_query"] += 1
    if not (is_text and has_lt):
        return
    if collector is None:
        # Larger than MAX_PARSE_BYTES: not read.
        counts["strings_not_checked"] += 1
        return
    collector.close()
    for code, n in collector.counts.items():
        counts[code] += n
    if failed or collector.unchecked:
        counts["strings_not_checked"] += 1


def _feed(parser, data, final, collector):
    """Parse data. Returns (parser, failed); the parser is None once it has failed."""
    try:
        parser.Parse(data, final)
        return parser, False
    except Exception:
        # Keep what was read: turning buffering off hands over buffered text.
        try:
            parser.buffer_text = False
        except Exception:
            pass
        collector.close()
        return None, True


def _scan_warnings(zf, infos, is_xlsb):
    # Count units: file-name and relationship warnings count parts/relationships
    # (one object found through both a name and a relationship counts twice);
    # external_link also counts <externalReference> elements; string warnings
    # count values (attribute values, each element's direct text, each CDATA
    # section, the joined runs of si, is, p and rich); the sheet warnings count
    # <sheet> elements in any part; strings_not_checked counts parts.
    counts = dict.fromkeys(WARNING_CODES, 0)
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
        # Parts are chosen by content, not by name, relationship or folder.
        _scan_part(zf, info, counts, not is_xlsb)
    if is_xlsb:
        # Binary parts are not read, so neither strings nor sheet states are known.
        counts["strings_not_checked"] += 1
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
            # Bits 5 and 6 (patched data, strong encryption): zipfile refuses to open such a part.
            if flags & 0x60:
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
