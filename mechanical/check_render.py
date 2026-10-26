"""Check the opened Blender scene against the published report and STL.

blender --background mechanical/renders/cradle-v4-studio.blend \
    --python mechanical/check_render.py
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_stl import read_stl  # noqa: E402

root = Path(__file__).resolve().parent
report = json.loads((root / "models/cradle-v4.validation.json").read_text())
triangles, stl_hash = read_stl(root / "models/cradle-v4.stl")
cad_hash = hashlib.sha256((root / "models/cradle-v4.FCStd").read_bytes()).hexdigest()
scene = bpy.context.scene
assert report["passed"]
assert scene["cad_sha256"] == cad_hash == report["cad_reference"]["sha256"]
assert scene["stl_sha256"] == stl_hash == report["stl_sha256"]
cradle = next(obj for obj in scene.objects if obj.get("stl_sha256") == stl_hash)
assert not cradle.modifiers
assert len(cradle.data.polygons) == len(triangles)
for polygon, triangle in zip(cradle.data.polygons, triangles, strict=True):
    assert len(polygon.vertices) == 3
    for index, expected in zip(polygon.vertices, triangle, strict=True):
        actual = cradle.matrix_world @ cradle.data.vertices[index].co
        assert all(
            math.isclose(a, b / 1000, abs_tol=1e-8) for a, b in zip(actual, expected, strict=True)
        )
images = [image for image in bpy.data.images if image.source == "FILE"]
assert len(images) == 1
image = images[0]
assert image.packed_file is not None
assert (
    hashlib.sha256(image.packed_file.data).hexdigest()
    == hashlib.sha256((root / "render-assets/gauge-normal.png").read_bytes()).hexdigest()
)
assert image.filepath.startswith("//")
assert all(packed.filepath.startswith("//") for packed in image.packed_files)
assert scene.render.filepath == "//cradle-v4-studio.png"
assert not any(
    getattr(scene.render, prop.identifier)
    for prop in scene.render.bl_rna.properties
    if prop.identifier.startswith("use_stamp") and prop.type == "BOOLEAN"
)
assert all(
    path.startswith("//") or not Path(path).is_absolute()
    for path in bpy.utils.blend_paths(absolute=False)
)
print("PASS packed image, portable paths, CAD/STL hash binding and exact cradle mesh")
