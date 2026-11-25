"""Builds small .xlsx files for tests. Nothing binary is tracked in the repository."""
import base64
import io
import struct
import zipfile
import zlib


def minimal_parts():
    return {
        "[Content_Types].xml": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            b"</Types>"
        ),
        "_rels/.rels": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            b"</Relationships>"
        ),
        "xl/workbook.xml": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            b'<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            b"</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>'
        ),
        "xl/sharedStrings.xml": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1">'
            b"<si><t>hello</t></si></sst>"
        ),
    }


def write_workbook(path, parts, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", compression) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


def raw_zip(parts, compression=zipfile.ZIP_STORED):
    """Return the bytes of a zip built in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return buf.getvalue()


def split_zip(raw):
    """Split zip bytes into (entry bytes, central directory bytearray, entry count)."""
    e = raw.rfind(b"PK\x05\x06")
    size, off = struct.unpack("<II", raw[e + 12:e + 20])
    return raw[:off], bytearray(raw[off:off + size]), struct.unpack("<H", raw[e + 10:e + 12])[0]


def central_entries(cd):
    """Yield the position of each central directory entry in a bytearray."""
    pos = 0
    while pos < len(cd):
        nl, xl, cl = struct.unpack("<HHH", cd[pos + 28:pos + 34])
        yield pos
        pos += 46 + nl + xl + cl


def shift_central_offsets(cd, delta):
    for pos in central_entries(cd):
        off = struct.unpack("<I", cd[pos + 42:pos + 46])[0]
        cd[pos + 42:pos + 46] = struct.pack("<I", off + delta)


def assemble_zip(body, cd, count, comment=b"", count_in_eocd=None):
    """Join entry bytes and a central directory with a fresh EOCD."""
    n = count if count_in_eocd is None else count_in_eocd
    eocd = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, n, n, len(cd), len(body), len(comment))
    return body + bytes(cd) + eocd + comment


def write_raw(path, data):
    with open(path, "wb") as f:
        f.write(data)
    return path


# field -> (offset in local header, offset in central entry, struct format)
_ENTRY_FIELDS = {
    "flags": (6, 8, "<H"), "method": (8, 10, "<H"), "crc": (14, 16, "<I"),
    "csize": (18, 20, "<I"), "usize": (22, 24, "<I"),
}


def patch_entry(raw, name, central=None, local=None):
    """Return raw with fields of one entry replaced in its central entry and/or local header."""
    data = bytearray(raw)
    body, cd, _n = split_zip(bytes(data))
    for pos in central_entries(cd):
        nl = struct.unpack("<H", cd[pos + 28:pos + 30])[0]
        if bytes(cd[pos + 46:pos + 46 + nl]) != name.encode("utf-8"):
            continue
        loc = struct.unpack("<I", cd[pos + 42:pos + 46])[0]
        base = len(body)
        for field, value in (central or {}).items():
            off, fmt = _ENTRY_FIELDS[field][1], _ENTRY_FIELDS[field][2]
            struct.pack_into(fmt, data, base + pos + off, value)
        for field, value in (local or {}).items():
            off, fmt = _ENTRY_FIELDS[field][0], _ENTRY_FIELDS[field][2]
            struct.pack_into(fmt, data, loc + off, value)
        return bytes(data)
    raise KeyError(name)


def build_zip(entries):
    """Build a zip by hand from {name: (method, stored payload, plain bytes)}."""
    body = bytearray()
    cd = bytearray()
    for name, (method, payload, plain) in entries.items():
        nb = name.encode()
        off = len(body)
        crc = zlib.crc32(plain)
        fields = (20, 0, method, 0, 0x21, crc, len(payload), len(plain), len(nb), 0)
        body += b"PK\x03\x04" + struct.pack("<HHHHHIIIHH", *fields) + nb + payload
        cd += b"PK\x01\x02" + struct.pack(
            "<HHHHHHIIIHHHHHII", 20, 20, 0, method, 0, 0x21, crc,
            len(payload), len(plain), len(nb), 0, 0, 0, 0, 0, off) + nb
    n = len(entries)
    eocd = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, n, n, len(cd), len(body), 0)
    return bytes(body + cd + eocd)


def build_hand_zip(parts, local_extra=b"", central_extra=b"", descriptor=None):
    """Build a stored zip by hand with an extra field on every entry.

    descriptor is None, "short" (12 bytes) or "signed" (16 bytes). With a
    descriptor, flag bit 3 is set and the local CRC and sizes are zero.
    """
    body = bytearray()
    cd = bytearray()
    flags = 0x8 if descriptor else 0
    for name, plain in parts.items():
        nb = name.encode()
        off = len(body)
        crc = zlib.crc32(plain)
        lcrc, lsize = (0, 0) if descriptor else (crc, len(plain))
        body += b"PK\x03\x04" + struct.pack(
            "<HHHHHIIIHH", 20, flags, 0, 0, 0x21, lcrc, lsize, lsize, len(nb), len(local_extra)
        ) + nb + local_extra + plain
        dd = struct.pack("<III", crc, len(plain), len(plain))
        if descriptor == "signed":
            body += b"PK\x07\x08" + dd
        elif descriptor == "short":
            body += dd
        cd += b"PK\x01\x02" + struct.pack(
            "<HHHHHHIIIHHHHHII", 20, 20, flags, 0, 0, 0x21, crc,
            len(plain), len(plain), len(nb), len(central_extra), 0, 0, 0, 0, off
        ) + nb + central_extra
    n = len(parts)
    eocd = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, n, n, len(cd), len(body), 0)
    return bytes(body + cd + eocd)


def local_entry(name, method, payload, usize):
    """One local header and its data, declaring usize whatever payload holds (CRC zero)."""
    nb = name.encode()
    return b"PK\x03\x04" + struct.pack(
        "<HHHHHIIIHH", 20, 0, method, 0, 0x21, 0, len(payload), usize, len(nb), 0
    ) + nb + payload


_MASHUP_HEAD = (
    '<?xml version="1.0" encoding="utf-16"?>'
    '<DataMashup xmlns="http://schemas.microsoft.com/DataMashup">'
)
_MASHUP_PERMISSIONS = (
    b'<?xml version="1.0" encoding="utf-8"?><PermissionList>'
    b"<CanEvaluateFuturePackages>false</CanEvaluateFuturePackages>"
    b"<FirewallEnabled>true</FirewallEnabled></PermissionList>"
)
_MASHUP_METADATA = (
    b'<?xml version="1.0" encoding="utf-8"?><LocalPackageMetadataFile><Items/></LocalPackageMetadataFile>'
)


def mashup_item(package, encoding="utf-16"):
    """A customXml item in Excel's DataMashup wrapper around package.

    The base64 holds version 0, then four length-prefixed sections: package,
    a permission list, metadata and an empty one. encoding "utf-16" gives
    UTF-16LE with a BOM, "utf-8" gives UTF-8 without one.
    """
    blob = struct.pack("<I", 0)
    for section in (package, _MASHUP_PERMISSIONS, _MASHUP_METADATA, b""):
        blob += struct.pack("<I", len(section)) + section
    text = _MASHUP_HEAD + base64.b64encode(blob).decode("ascii") + "</DataMashup>"
    if encoding == "utf-8":
        return text.encode("utf-8")
    return b"\xff\xfe" + text.encode("utf-16-le")


def deflated_entries(parts):
    """Entries for build_zip: every part raw-deflated."""
    entries = {}
    for name, data in parts.items():
        c = zlib.compressobj(6, zlib.DEFLATED, -15)
        entries[name] = (zipfile.ZIP_DEFLATED, c.compress(data) + c.flush(), data)
    return entries


class _Bits(object):
    def __init__(self):
        self.acc = 0
        self.n = 0
        self.out = bytearray()

    def put(self, value, nbits):
        self.acc |= value << self.n
        self.n += nbits
        while self.n >= 8:
            self.out.append(self.acc & 0xFF)
            self.acc >>= 8
            self.n -= 8

    def huff(self, code, nbits):
        self.put(int(format(code, "0%db" % nbits)[::-1], 2), nbits)

    def done(self):
        if self.n:
            self.out.append(self.acc & 0xFF)
        return bytes(self.out)


def deflate_split_at_output_limit(n=65536 - 1 - 100):
    """A valid raw deflate stream whose 64 KiB output limit falls inside its last match.

    A stored block of n bytes, then a final fixed-Huffman block: one literal, a
    length-258 match, end of block. Returns (stream, plain bytes).
    """
    stored = bytes((i * 7 + 3) & 0xFF for i in range(n))
    head = b"\x00" + struct.pack("<HH", n, n ^ 0xFFFF) + stored
    b = _Bits()
    b.put(1, 1)
    b.put(1, 2)
    b.huff(0x190, 9)
    b.huff(0xC0 + 5, 8)
    b.huff(0, 5)
    b.huff(0, 7)
    return head + b.done(), stored + b"\x90" * 259
