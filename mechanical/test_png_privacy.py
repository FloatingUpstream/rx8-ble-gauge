"""Ensure publish sanitisation leaves the actual compressed image bytes intact."""

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from png_privacy import SIGNATURE, strip_metadata


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


class PNGPrivacyTests(unittest.TestCase):
    def test_removes_metadata_without_changing_image_chunks(self):
        header = chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 2, 0, 0, 0))
        image = chunk(b"IDAT", zlib.compress(b"\0\x11\x22\x33"))
        end = chunk(b"IEND", b"")
        clean = SIGNATURE + header + image + end
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "image.png"
            path.write_bytes(
                SIGNATURE
                + header
                + chunk(b"tEXt", b"File\0PRIVATE_RENDER_PATH")
                + chunk(b"eXIf", b"private data")
                + image
                + end
            )
            self.assertEqual(strip_metadata(path), ["tEXt", "eXIf"])
            self.assertEqual(path.read_bytes(), clean)
            self.assertEqual(strip_metadata(path), [])

    def test_refuses_corrupt_input_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "image.png"
            original = SIGNATURE + chunk(b"IDAT", b"broken")[:-1]
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                strip_metadata(path)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
