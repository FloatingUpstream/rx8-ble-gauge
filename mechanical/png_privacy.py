"""Remove textual/EXIF/time metadata from static PNGs without re-encoding pixels."""

import struct
import zlib
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"
PRIVATE_CHUNKS = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}


def strip_metadata(path):
    path = Path(path)
    raw = path.read_bytes()
    if not raw.startswith(SIGNATURE):
        raise ValueError("Not a PNG")
    output, removed, offset = bytearray(SIGNATURE), [], len(SIGNATURE)
    ended = False
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ValueError("Truncated PNG chunk")
        length = struct.unpack_from(">I", raw, offset)[0]
        end = offset + 12 + length
        if end > len(raw):
            raise ValueError("Truncated PNG payload")
        kind = raw[offset + 4 : offset + 8]
        data = raw[offset + 8 : offset + 8 + length]
        expected = struct.unpack_from(">I", raw, offset + 8 + length)[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != expected:
            raise ValueError("PNG CRC mismatch")
        if kind in PRIVATE_CHUNKS:
            removed.append(kind.decode("ascii"))
        else:
            output.extend(raw[offset:end])
        offset = end
        if kind == b"IEND":
            ended = True
            break
    if not ended or offset != len(raw):
        raise ValueError("Missing IEND or unexpected trailing data")
    if removed:
        path.write_bytes(output)
    return removed
