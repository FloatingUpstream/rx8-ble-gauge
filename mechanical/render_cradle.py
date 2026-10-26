"""Blender 4.5 studio render of the verified v4 mesh; never modifies native CAD.

blender --background --factory-startup --python mechanical/render_cradle.py -- \
    --stl FILE --validation REPORT --out NEW_DIRECTORY
"""

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_stl import read_stl  # noqa: E402


def material(name, color, metallic=0, roughness=0.4):
    obj = bpy.data.materials.new(name)
    obj.use_nodes = True
    shader = obj.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    return obj, shader


def fine_texture(mat, shader, scale, strength, distance):
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 2
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])


def mesh_object(name, points, faces, mat):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    if hasattr(mesh, "set_sharp_from_angle"):
        mesh.set_sharp_from_angle(angle=math.radians(35))
    return obj


def lathe(name, profile_mm, mat, pose, count=192):
    points, rings, faces = [], [], []
    for radius, z in profile_mm:
        if radius == 0:
            rings.append([len(points)])
            points.append((0, 0, z / 1000))
        else:
            rings.append(list(range(len(points), len(points) + count)))
            points.extend(
                (
                    radius * math.cos(i * math.tau / count) / 1000,
                    radius * math.sin(i * math.tau / count) / 1000,
                    z / 1000,
                )
                for i in range(count)
            )
    for a, b in zip(rings, rings[1:], strict=False):
        for i in range(count):
            j = (i + 1) % count
            if len(a) == 1:
                faces.append((a[0], b[j], b[i]))
            elif len(b) == 1:
                faces.append((a[i], a[j], b[0]))
            else:
                faces.append((a[i], a[j], b[j], b[i]))
    obj = mesh_object(name, points, faces, mat)
    obj.matrix_world = pose
    return obj


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def area(name, position, target, power, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.shape, data.size, data.color = power, "DISK", size, color
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = position
    look_at(obj, target)


def build(args):
    report = json.loads(args.validation.read_text())
    triangles, stl_hash = read_stl(args.stl)
    if not report["passed"] or stl_hash != report["stl_sha256"]:
        raise ValueError("Render requires passing validation for these exact STL bytes")
    cad = Path(report["cad_reference"]["file"])
    if not cad.is_absolute():
        cad = args.validation.resolve().parent / cad
    if hashlib.sha256(cad.read_bytes()).hexdigest() != report["cad_reference"]["sha256"]:
        raise ValueError("CAD changed since STL validation; re-export/revalidate first")
    args.out.mkdir(parents=True, exist_ok=False)
    # A fresh scene avoids startup brush asset references to the tool installation.
    scene = bpy.data.scenes.new("Cradle studio")
    scene.world = bpy.data.worlds.new("Studio world")
    bpy.context.window.scene = scene
    for other in list(bpy.data.scenes):
        if other != scene:
            bpy.data.scenes.remove(other)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    # Unused startup workspaces retain brush libraries and file-browser history.
    current_workspace = bpy.context.window.workspace
    bpy.data.batch_remove(
        ids=[workspace for workspace in bpy.data.workspaces if workspace != current_workspace]
    )
    bpy.data.batch_remove(
        ids=[screen for screen in bpy.data.screens if screen != bpy.context.window.screen]
    )
    bpy.data.orphans_purge(do_recursive=True)
    for screen in bpy.data.screens:
        for editor in screen.areas:
            for space in editor.spaces:
                if space.type == "FILE_BROWSER" and space.params:
                    space.params.directory = b"//"
    grey, grey_shader = material("Cradle — satin grey polymer", (0.12, 0.13, 0.14), roughness=0.43)
    fine_texture(grey, grey_shader, 25000, 0.1, 0.000015)
    points, faces, mapping = [], [], {}
    for triangle in triangles:
        face = []
        for point in triangle:
            if point not in mapping:
                mapping[point] = len(points)
                points.append(tuple(value / 1000 for value in point))
            face.append(mapping[point])
        faces.append(face)
    cradle = mesh_object(
        "Verified v4 cradle — exact STL, millimetres to metres", points, faces, grey
    )
    cradle["stl_sha256"] = stl_hash
    cradle["geometry_modifiers"] = "none; smooth shading/material only"

    reference = report["cad_reference"]["device_envelope"]
    values = reference["matrix"]
    pose = Matrix([values[i : i + 4] for i in range(0, 16, 4)])
    for i in range(3):
        pose[i][3] /= 1000
    radius, depth = reference["diameter_mm"] / 2, reference["depth_mm"]
    metal, metal_shader = material("Device — satin aluminium", (0.63, 0.66, 0.69), 0.92, 0.25)
    metal_shader.inputs["Anisotropic"].default_value = 0.25
    fine_texture(metal, metal_shader, 60000, 0.08, 0.000005)
    body = lathe(
        "Device housing — approximate rounded envelope",
        [
            (0, 0),
            (radius - 1.2, 0),
            (radius - 0.4, 0.5),
            (radius, 1.5),
            (radius, depth - 1.4),
            (radius - 0.2, depth - 0.6),
            (radius - 0.5, depth),
            (0, depth),
        ],
        metal,
        pose,
    )
    body["note"] = "Presentation approximation, not an as-built housing CAD model; ports omitted"
    glass, glass_shader = material("Black cover glass", (0.008, 0.011, 0.016), 0.05, 0.16)
    glass_shader.inputs["Coat Weight"].default_value = 0.5
    glass_shader.inputs["Coat Roughness"].default_value = 0.1
    lathe(
        "Cover glass — nominal 55mm diameter",
        [
            (0, depth),
            (27.35, depth),
            (27.5, depth + 0.04),
            (27.4, depth + 0.10),
            (0, depth + 0.10),
        ],
        glass,
        pose,
    )
    screen, screen_shader = material("Actual shared gauge UI — simulated reading", (0, 0, 0))
    texture = screen.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(args.screen.resolve()))
    texture.image.pack()
    # Packed bytes are authoritative; the fallback path is relative to the .blend.
    texture.image.filepath = "//" + os.path.relpath(args.screen.resolve(), args.out.resolve())
    for packed in texture.image.packed_files:
        packed.filepath = texture.image.filepath
    screen.node_tree.links.new(texture.outputs["Color"], screen_shader.inputs["Base Color"])
    screen.node_tree.links.new(texture.outputs["Color"], screen_shader.inputs["Emission Color"])
    screen_shader.inputs["Emission Strength"].default_value = 0.7
    screen_shader.inputs["Roughness"].default_value = 0.25
    screen_shader.inputs["Coat Weight"].default_value = 0.2
    active_radius = 45.68 / 2 / 1000
    screen_z = (depth + 0.12) / 1000
    vertices = [(0, 0, screen_z)] + [
        (
            active_radius * math.cos(i * math.tau / 192),
            active_radius * math.sin(i * math.tau / 192),
            screen_z,
        )
        for i in range(192)
    ]
    polygons = [(0, 1 + i, 1 + (i + 1) % 192) for i in range(192)]
    display = mesh_object("LCD — vendor nominal 45.68mm active circle", vertices, polygons, screen)
    display.matrix_world = pose
    uv = display.data.uv_layers.new(name="Actual UI")
    for polygon in display.data.polygons:
        for loop in polygon.loop_indices:
            vertex = display.data.vertices[display.data.loops[loop].vertex_index].co
            uv.data[loop].uv = (
                vertex.x / (2 * active_radius) + 0.5,
                vertex.y / (2 * active_radius) + 0.5,
            )
    floor_mat, _ = material("Studio floor", (0.68, 0.70, 0.73), roughness=0.75)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.00002))
    bpy.context.object.name = "Studio floor"
    bpy.context.object.data.materials.append(floor_mat)
    area("Key — large softbox", (-0.12, -0.12, 0.22), (0, 0, 0.035), 2, 0.16, (1, 0.96, 0.90))
    area("Fill — cool softbox", (0.17, -0.05, 0.12), (0, 0, 0.035), 0.7, 0.16, (0.83, 0.90, 1))
    area("Rim — overhead rear", (0.03, 0.14, 0.19), (0, 0, 0.04), 3, 0.10, (1, 1, 1))
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    scene.unit_settings.length_unit = "MILLIMETERS"
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.7, 0.76, 0.85, 1)
    background.inputs["Strength"].default_value = 0.25
    camera_data = bpy.data.cameras.new("Product camera")
    camera = bpy.data.objects.new("Product camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (0.135, -0.21, 0.14)
    look_at(camera, (0, -0.005, 0.038))
    camera_data.lens = 75
    camera_data.clip_start = 0.001
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.seed = 8
    scene.render.threads_mode = "FIXED"
    scene.render.threads = min(12, os.cpu_count() or 1)
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    for prop in scene.render.bl_rna.properties:
        if prop.identifier.startswith("use_stamp") and prop.type == "BOOLEAN":
            setattr(scene.render, prop.identifier, False)
    scene.render.filepath = "//cradle-v4-studio.png"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -0.5
    scene["note"] = (
        "Concept render. Exact verified cradle; approximate device details, actual demo UI."
    )
    scene["stl_sha256"] = stl_hash
    scene["cad_sha256"] = report["cad_reference"]["sha256"]
    scene["license"] = "The Unlicense (original project assets)"
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out.resolve() / "cradle-v4-studio.blend"))
    metadata = {
        "blender": bpy.app.version_string,
        "stl_sha256": stl_hash,
        "cad_sha256": report["cad_reference"]["sha256"],
        "screen_sha256": hashlib.sha256(args.screen.read_bytes()).hexdigest(),
        "screen_source": (
            "Synthetic desktop fixture: coolant 87 C / MAF 12.40 g/s, yellow RX-8 UI; "
            "not live vehicle data. The screenshot's LIVE indicator is fixture state."
        ),
        "cradle": "Exact validated STL; shading only, no geometry modifiers",
        "device": "Approximate rounded nominal envelope; detailed ports/back curvature unmeasured",
        "lighting": "Three area softboxes and neutral studio environment",
        "units": "Source mm converted to Blender metres",
        "samples": args.samples,
        "resolution": [args.width, args.height],
    }
    (args.out / "cradle-v4-studio.metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    bpy.ops.render.render(write_still=True)
    from png_privacy import strip_metadata

    strip_metadata(args.out / "cradle-v4-studio.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    from project_paths import prototype_output

    parser.add_argument("--stl", type=Path, default=Path(__file__).parent / "models/cradle-v4.stl")
    parser.add_argument(
        "--validation",
        type=Path,
        default=Path(__file__).parent / "models/cradle-v4.validation.json",
    )
    parser.add_argument("--out", type=Path, default=prototype_output("studio"))
    parser.add_argument(
        "--screen", type=Path, default=Path(__file__).parent / "render-assets/gauge-normal.png"
    )
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1400)
    build(parser.parse_args(sys.argv[sys.argv.index("--") + 1 :]))
