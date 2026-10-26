"""Read-only validation of exported triangles against native CAD (millimetres).

Full check requires FreeCAD's system Python module:
PYTHONPATH=/usr/lib/freecad/lib /usr/bin/python mechanical/validate_stl.py FILE \
    --cad mechanical/models/cradle-v4.FCStd --report REPORT.json
"""

import argparse
import collections
import hashlib
import json
import math
import os
import struct
from pathlib import Path


def read_stl(path):
    raw = path.read_bytes()
    if len(raw) >= 84 and len(raw) == 84 + 50 * struct.unpack_from("<I", raw, 80)[0]:
        triangles = [
            tuple(tuple(values[j : j + 3]) for j in (3, 6, 9))
            for values in struct.iter_unpack("<12fH", raw[84:])
        ]
    else:
        text = raw.decode("ascii")
        if not text.lstrip().lower().startswith("solid") or "endsolid" not in text.lower():
            raise ValueError("Not an exact-length binary STL or complete ASCII STL")
        vertices = [
            tuple(map(float, line.split()[1:]))
            for line in text.splitlines()
            if line.strip().lower().startswith("vertex ")
        ]
        if not vertices or len(vertices) % 3 or any(len(v) != 3 for v in vertices):
            raise ValueError("Malformed ASCII STL vertex records")
        triangles = [tuple(vertices[i : i + 3]) for i in range(0, len(vertices), 3)]
    if not triangles or not all(math.isfinite(x) for tri in triangles for v in tri for x in v):
        raise ValueError("Empty STL or nonfinite coordinates")
    return triangles, hashlib.sha256(raw).hexdigest()


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def topology(triangles):
    """Independent edge/winding/vertex-link checks; exact stored coordinates."""
    vertices, faces = {}, []
    for tri in triangles:
        faces.append(tuple(vertices.setdefault(v, len(vertices)) for v in tri))
    edges = collections.defaultdict(list)
    links = collections.defaultdict(list)
    seen = set()
    duplicates = degenerates = 0
    parent = list(range(len(faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for index, (face, tri) in enumerate(zip(faces, triangles, strict=True)):
        canonical = tuple(sorted(face))
        duplicates += canonical in seen
        seen.add(canonical)
        normal = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
        degenerates += len(set(face)) != 3 or dot(normal, normal) <= 1e-24
        for a, b, c in (
            (face[0], face[1], face[2]),
            (face[1], face[2], face[0]),
            (face[2], face[0], face[1]),
        ):
            edges[tuple(sorted((a, b)))].append((index, a < b))
            links[a].append((b, c))
    for incidents in edges.values():
        for index, _ in incidents[1:]:
            parent[find(index)] = find(incidents[0][0])
    bad_vertices = 0
    for pairs in links.values():
        graph = collections.defaultdict(list)
        for a, b in pairs:
            graph[a].append(b)
            graph[b].append(a)
        reached, stack = set(), [next(iter(graph))]
        while stack:
            point = stack.pop()
            if point not in reached:
                reached.add(point)
                stack.extend(graph[point])
        bad_vertices += len(reached) != len(graph) or any(len(v) != 2 for v in graph.values())
    minimum = [min(v[i] for v in vertices) for i in range(3)]
    maximum = [max(v[i] for v in vertices) for i in range(3)]
    origin = [(a + b) / 2 for a, b in zip(minimum, maximum, strict=True)]
    volume = math.fsum(
        dot(sub(a, origin), cross(sub(b, origin), sub(c, origin))) / 6 for a, b, c in triangles
    )
    return {
        "triangles": len(faces),
        "unique_vertices": len(vertices),
        "boundary_edges": sum(len(v) == 1 for v in edges.values()),
        "nonmanifold_edges": sum(len(v) > 2 for v in edges.values()),
        "nonmanifold_vertices": bad_vertices,
        "winding_conflicts": sum(len(v) == 2 and v[0][1] == v[1][1] for v in edges.values()),
        "duplicate_triangles": duplicates,
        "degenerate_triangles": degenerates,
        "surface_components": len({find(i) for i in range(len(faces))}),
        "bounds_min_mm": minimum,
        "bounds_max_mm": maximum,
        "dimensions_mm": sub(maximum, minimum),
        "signed_volume_mm3": volume,
        "vertex_matching": "exact coordinates as stored; no welding/repair performed",
    }


def bore_samples(triangles, reference):
    """First shell crossing along nine radial rays in the lower cavity section."""
    matrix, height = reference["inverse_matrix"], reference["section_z_mm"]

    def local(v):
        return [
            sum(matrix[i * 4 + j] * v[j] for j in range(3))
            + matrix[i * 4 + 3]
            - (height if i == 2 else 0)
            for i in range(3)
        ]

    segments = []
    for triangle in triangles:
        points = list(map(local, triangle))
        crossings = []
        for a, b in ((points[0], points[1]), (points[1], points[2]), (points[2], points[0])):
            if (a[2] < 0 < b[2]) or (b[2] < 0 < a[2]):
                t = -a[2] / (b[2] - a[2])
                crossings.append(tuple(a[i] + t * (b[i] - a[i]) for i in range(2)))
            elif abs(a[2]) < 1e-9:
                crossings.append(tuple(a[:2]))
        crossings = list(dict.fromkeys(crossings))
        if len(crossings) == 2 and crossings[0] != crossings[1]:
            segments.append(crossings)

    def cross2(a, b):
        return a[0] * b[1] - a[1] * b[0]

    samples = []
    for angle in range(210, 331, 15):
        direction = (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
        distances = []
        for p, q in segments:
            edge = sub(q, p)
            denominator = cross2(direction, edge)
            if abs(denominator) < 1e-12:
                continue
            radius = cross2(p, edge) / denominator
            t = cross2(p, direction) / denominator
            if radius > 0 and -1e-8 <= t <= 1 + 1e-8:
                distances.append(radius)
        if not distances:
            raise ValueError(f"No cavity wall found along {angle} degree bore ray")
        samples.append({"angle_degrees": angle, "diameter_mm": 2 * min(distances)})
    return samples


def compare_dimensions(result, reference, tolerance=0.1, volume_fraction=0.001):
    errors = []
    for field in ("bounds_min_mm", "bounds_max_mm", "dimensions_mm"):
        if any(
            abs(a - b) > tolerance for a, b in zip(result[field], reference[field], strict=True)
        ):
            errors.append(f"{field} differs from CAD by more than {tolerance} mm")
    if abs(result["signed_volume_mm3"] - reference["volume_mm3"]) > (
        volume_fraction * reference["volume_mm3"]
    ):
        errors.append(f"Volume differs from CAD by more than {100 * volume_fraction:g}%")
    return errors


def validate(path, cad, object_name="TopLoadingCradle", tolerance=0.1):
    # Initialise FreeCAD before Mesh: Part/Mesh modules require its runtime.
    import FreeCAD as App
    import Mesh

    triangles, stl_hash = read_stl(path)
    result = topology(triangles)
    errors = []
    for field in (
        "boundary_edges",
        "nonmanifold_edges",
        "nonmanifold_vertices",
        "winding_conflicts",
        "duplicate_triangles",
        "degenerate_triangles",
    ):
        if result[field]:
            errors.append(f"{field}: {result[field]}")
    if result["surface_components"] != 1:
        errors.append("Expected one connected surface for this cradle")
    if result["signed_volume_mm3"] <= 0:
        errors.append("Nonpositive signed volume (inverted/invalid surface)")
    mesh = Mesh.Mesh(str(path))
    intersections = mesh.getSelfIntersections()
    checks = {
        "closed_solid": mesh.isSolid(),
        "nonmanifolds": mesh.hasNonManifolds(),
        "inconsistent_orientation": mesh.hasNonUniformOrientedFacets(),
        "self_intersection_pairs": len(intersections),
        "intersection_facet_samples": [[item[0], item[1]] for item in intersections[:10]],
    }
    if not checks["closed_solid"] or checks["nonmanifolds"] or checks["inconsistent_orientation"]:
        errors.append("FreeCAD mesh topology/orientation check failed")
    if intersections:
        errors.append(f"FreeCAD flags {len(intersections)} self-intersecting facet pairs")
    doc = App.openDocument(str(cad))
    try:
        doc.recompute()
        obj = doc.getObject(object_name)
        if obj is None or not obj.Shape.isValid() or len(obj.Shape.Solids) != 1:
            raise ValueError("CAD reference must contain one valid final solid")
        shape = obj.Shape
        bounds = shape.optimalBoundingBox(False, False)
        reference = {
            "file": str(cad),
            "sha256": hashlib.sha256(cad.read_bytes()).hexdigest(),
            "object": object_name,
            "volume_mm3": shape.Volume,
            "bounds_min_mm": [bounds.XMin, bounds.YMin, bounds.ZMin],
            "bounds_max_mm": [bounds.XMax, bounds.YMax, bounds.ZMax],
            "dimensions_mm": [bounds.XLength, bounds.YLength, bounds.ZLength],
        }
        errors.extend(compare_dimensions(result, reference, tolerance))
        cavity = doc.getObject("DeviceCavity")
        sheet = doc.getObject("Dimensions")
        device = doc.getObject("DeviceEnvelope")
        if device is not None:
            reference["device_envelope"] = {
                "diameter_mm": 2 * device.Radius.Value,
                "depth_mm": device.Height.Value,
                "matrix": list(device.Placement.Matrix.A),
            }
        if cavity is not None and sheet is not None:
            bore = {
                "diameter_mm": 2 * cavity.Radius.Value,
                "inverse_matrix": list(cavity.Placement.inverse().Matrix.A),
                "section_z_mm": sheet.DeviceDepth.Value / 2,
            }
            samples = bore_samples(triangles, bore)
            reference["bore"] = bore
            result["bore_samples"] = samples
            if any(abs(s["diameter_mm"] - bore["diameter_mm"]) > tolerance for s in samples):
                errors.append("Sampled STL cavity diameters differ from CAD")
    finally:
        App.closeDocument(doc.Name)
    return {
        "passed": not errors,
        "errors": errors,
        "stl_file": str(path),
        "stl_sha256": stl_hash,
        "units": "mm by CAD convention; STL itself stores no units",
        "limits": {"dimension_tolerance_mm": tolerance, "volume_fraction": 0.001},
        "stl": result,
        "freecad_mesh": checks,
        "cad_reference": reference,
        "note": "Read-only. No mesh repair. Digital checks do not prove printed fit or strength.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stl", type=Path)
    parser.add_argument("--cad", type=Path, required=True)
    parser.add_argument("--object", default="TopLoadingCradle")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Choose a new report path; existing reports are preserved")
    result = validate(args.stl.resolve(), args.cad.resolve(), args.object)
    result["stl_file"] = os.path.relpath(args.stl.resolve(), args.report.resolve().parent)
    result["cad_reference"]["file"] = os.path.relpath(
        args.cad.resolve(), args.report.resolve().parent
    )
    result["path_convention"] = "Artifact paths are relative to this report's directory"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print("PASS" if result["passed"] else "FAIL", args.stl)
    for error in result["errors"]:
        print(" -", error)
    print("Dimensions (mm):", result["stl"]["dimensions_mm"])
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
