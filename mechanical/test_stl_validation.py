"""Hermetic tests of the independent, read-only STL checks (no CAD dependency)."""

import struct
import tempfile
import unittest
from pathlib import Path

from validate_stl import bore_samples, compare_dimensions, read_stl, topology


def tetrahedron():
    a, b, c, d = (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)
    return [(a, c, b), (a, d, c), (a, b, d), (b, c, d)]


class STLTests(unittest.TestCase):
    def test_closed_oriented_tetrahedron(self):
        result = topology(tetrahedron())
        self.assertEqual(result["boundary_edges"], 0)
        self.assertEqual(result["nonmanifold_edges"], 0)
        self.assertEqual(result["nonmanifold_vertices"], 0)
        self.assertEqual(result["winding_conflicts"], 0)
        self.assertEqual(result["surface_components"], 1)
        self.assertAlmostEqual(result["signed_volume_mm3"], 1 / 6)

    def test_hole_duplicate_face_and_inverted_winding_are_detected(self):
        triangles = tetrahedron()
        self.assertEqual(topology(triangles[:-1])["boundary_edges"], 3)
        duplicate = topology(triangles + triangles[:1])
        self.assertEqual(duplicate["duplicate_triangles"], 1)
        self.assertEqual(duplicate["nonmanifold_edges"], 3)
        flipped = topology([tuple(reversed(triangles[0])), *triangles[1:]])
        self.assertEqual(flipped["winding_conflicts"], 3)
        self.assertLess(topology([tuple(reversed(t)) for t in triangles])["signed_volume_mm3"], 0)

    def test_degenerate_disconnected_and_pinched_vertex(self):
        triangles = tetrahedron()
        bad = (triangles[0][0], triangles[0][0], triangles[0][1])
        self.assertEqual(topology([*triangles, bad])["degenerate_triangles"], 1)
        shifted = [tuple(tuple(x + 3 for x in v) for v in t) for t in triangles]
        self.assertEqual(topology(triangles + shifted)["surface_components"], 2)
        touching = [tuple(reversed([tuple(-x for x in v) for v in t])) for t in triangles]
        self.assertEqual(topology(triangles + touching)["nonmanifold_vertices"], 1)

    def test_binary_and_ascii_roundtrip_and_bad_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.stl"
            triangles = tetrahedron()
            data = bytearray(b"solid binary despite this header".ljust(80, b"\0"))
            data.extend(struct.pack("<I", len(triangles)))
            for tri in triangles:
                data.extend(struct.pack("<12fH", 0, 0, 0, *(x for v in tri for x in v), 0))
            path.write_bytes(data)
            self.assertEqual(read_stl(path)[0], triangles)
            text = (
                "solid test\n"
                + "\n".join("vertex " + " ".join(map(str, v)) for t in triangles for v in t)
                + "\nendsolid test\n"
            )
            path.write_text(text)
            self.assertEqual(read_stl(path)[0], triangles)
            path.write_text(text.replace("vertex 0 0 0", "vertex nan 0 0", 1))
            with self.assertRaises(ValueError):
                read_stl(path)

    def test_dimension_and_volume_mismatch(self):
        result = topology(tetrahedron())
        reference = {
            **{key: result[key] for key in ("bounds_min_mm", "bounds_max_mm", "dimensions_mm")},
            "volume_mm3": result["signed_volume_mm3"],
        }
        self.assertEqual(compare_dimensions(result, reference), [])
        reference["dimensions_mm"] = (10, 10, 10)
        reference["volume_mm3"] *= 2
        self.assertEqual(len(compare_dimensions(result, reference)), 2)

    def test_bore_ray_measurement(self):
        # A square tube, with each side as two vertical triangles. Rays in the
        # lower half must find the nearer inner wall, not the outer wall.
        triangles = []
        for size in (10, 20):
            corners = [(-size, -size), (size, -size), (size, size), (-size, size)]
            for a, b in zip(corners, corners[1:] + corners[:1], strict=True):
                p, q = (*a, -1), (*b, -1)
                r, s = (*b, 1), (*a, 1)
                triangles.extend(((p, q, r), (p, r, s)))
        samples = bore_samples(
            triangles,
            {
                "inverse_matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                "section_z_mm": 0,
            },
        )
        middle = next(s for s in samples if s["angle_degrees"] == 270)
        self.assertAlmostEqual(middle["diameter_mm"], 20)


if __name__ == "__main__":
    unittest.main()
