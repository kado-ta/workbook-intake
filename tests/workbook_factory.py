"""Builds small .xlsx files for tests. Nothing binary is tracked in the repository."""
import io
import struct
import zipfile


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
