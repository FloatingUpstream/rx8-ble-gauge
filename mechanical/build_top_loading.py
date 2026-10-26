"""Top-loading concepts with a domed base; optional detents. NOT vehicle validated."""

import argparse
import json
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part
from build_cradle import box, check_solid, cut, cylinder, expr, fuse, tilted
from build_enclosed_cradle import build as build_baseline
from build_enclosed_cradle import ellipse
from build_fit_test import dimension
from project_paths import prototype_output


def blend_junction(doc, base, pedestal, pod):
    """Select the actual boolean intersection seam, not arbitrary numbered edges."""
    doc.recompute()
    seam = pedestal.Shape.section(pod.Shape)
    indices = []
    for index, edge in enumerate(base.Shape.Edges, 1):
        points = [
            edge.valueAt(edge.FirstParameter + f * (edge.LastParameter - edge.FirstParameter))
            for f in (0.2, 0.5, 0.8)
        ]
        if all(Part.Vertex(point).distToShape(seam)[0] < 1e-5 for point in points):
            indices.append(index)
    if not indices:
        raise ValueError("Could not identify pod/pedestal intersection for blending")
    for radius in (8, 6, 4, 3, 2, 1):
        obj = doc.addObject("Part::Fillet", "PodBaseBlend")
        obj.Base, obj.Edges = base, [(index, radius, radius) for index in indices]
        doc.recompute()
        if not obj.Shape.isNull() and obj.Shape.isValid() and len(obj.Shape.Solids) == 1:
            return obj, radius
        doc.removeObject(obj.Name)
        doc.recompute()
    raise ValueError("No valid pod/pedestal blend found")


def tidy_tree(doc, main):
    """Retain the complete native dependency graph; drop unused baseline branches."""
    keep = set()

    def visit(obj):
        if obj.Name in keep:
            return
        keep.add(obj.Name)
        for dependency in obj.OutList:
            visit(dependency)

    for obj in (
        main,
        doc.getObject("Dimensions"),
        doc.getObject("DeviceEnvelope"),
        doc.getObject("ScreenReference"),
    ):
        visit(obj)
    for obj in list(doc.Objects):
        if obj.Name not in keep:
            doc.removeObject(obj.Name)
    sheet = doc.getObject("Dimensions")
    # No longer used after replacing the baseline foot and removing its soft pads.
    for row in (11, 15):
        sheet.setAlias(f"B{row}", "")
        sheet.clear(f"A{row}")
        sheet.clear(f"B{row}")
    sheet.Label = "Dimensions — editable controls and derived sizes"
    labels = {
        "ClosedPedestal": "Domed base — smooth four-section loft",
        "PodBaseBlend": "Smooth pod-to-base junction — editable fillet",
        "DeviceCavity": "Housing clearance — diameter driven by Dimensions",
        "LowerCaptureLip": "Lower semicircular retaining lip",
        "TopEntryTool": "Cut tool — open top, preserve back support",
        "PedestalVoid": "Underside hollow — leave adhesive flange",
    }
    for name, label in labels.items():
        doc.getObject(name).Label = label
    references = doc.addObject("App::DocumentObjectGroup", "ReferenceGeometry")
    references.Label = "Device reference — not a manufactured part"
    references.addObjects([doc.getObject("DeviceEnvelope"), doc.getObject("ScreenReference")])
    construction = doc.addObject("App::DocumentObjectGroup", "Construction")
    construction.Label = "Construction — editable native features"
    excluded = {
        main.Name,
        sheet.Name,
        references.Name,
        construction.Name,
        "DeviceEnvelope",
        "ScreenReference",
    }
    construction.addObjects([obj for obj in doc.Objects if obj.Name not in excluded])
    doc.recompute()


def build(out, *, detents=True):
    out.mkdir(parents=True, exist_ok=False)
    build_baseline(out / "baseline")
    doc = App.openDocument(str(out / "baseline/enclosed-cradle.FCStd"))
    sheet = doc.getObject("Dimensions")
    if detents:
        dimension(sheet, 16, "RailWall", "1.8 mm", "PROVISIONAL flexible guide wall")
        dimension(sheet, 17, "DetentRadius", "0.7 mm", "PROVISIONAL rounded detent radius")
    controls = [
        ("LipInset", "1.5 mm", "Retaining lip radial overlap into clearance opening"),
        ("LipThickness", "1.4 mm", "Retaining lip axial thickness"),
        ("DomeLowerWidth", "=B9*75/76", "Lower dome section width"),
        ("DomeLowerDepth", "=B10*46/50", "Lower dome section depth"),
        ("DomeLowerHeight", "12 mm", "Lower dome section height"),
        ("DomeLowerOffset", "-1 mm", "Lower dome fore/aft offset"),
        ("DomeUpperWidth", "=B9*66/76", "Upper dome section width"),
        ("DomeUpperDepth", "=B10*32/50", "Upper dome section depth"),
        ("DomeUpperHeight", "25 mm", "Upper dome section height"),
        ("DomeUpperOffset", "-6 mm", "Upper dome fore/aft offset"),
        ("DomeTopWidth", "=B9*56/76", "Top dome section width"),
        ("DomeTopDepth", "=B10*22/50", "Top dome section depth"),
        ("DomeTopHeight", "36 mm", "Top dome section height"),
        ("DomeTopOffset", "-9 mm", "Top dome fore/aft offset"),
    ]
    for row, (name, value, description) in enumerate(controls, 18):
        dimension(sheet, row, name, value, description)
    sheet.set("B14", "=B5+B2+B6+B19")
    d = "Dimensions."
    pedestal = doc.getObject("ClosedPedestal")
    lower, upper = doc.getObject("PedestalBase"), doc.getObject("PedestalTop")
    expr(lower, "Placement.Base.z", "0 mm")
    for field, alias in (("MajorRadius", "DomeTopWidth"), ("MinorRadius", "DomeTopDepth")):
        expr(upper, field, f"{d}{alias}/2")
    expr(upper, "Placement.Base.z", f"{d}DomeTopHeight")
    expr(upper, "Placement.Base.y", f"{d}DomeTopOffset")
    mid1 = ellipse(
        doc,
        "DomeLower",
        f"{d}DomeLowerWidth",
        f"{d}DomeLowerDepth",
        f"{d}DomeLowerHeight",
        f"{d}DomeLowerOffset",
    )
    mid2 = ellipse(
        doc,
        "DomeUpper",
        f"{d}DomeUpperWidth",
        f"{d}DomeUpperDepth",
        f"{d}DomeUpperHeight",
        f"{d}DomeUpperOffset",
    )
    pedestal.Sections, pedestal.Ruled = [lower, mid1, mid2, upper], False
    blank = doc.getObject("EnclosedBlank")
    pod = doc.getObject("RoundedPod")
    blank.Shapes = [pedestal, pod]  # no separate plate/pedestal crease at the foot
    blended, radius = blend_junction(doc, blank, pedestal, pod)
    doc.getObject("OpenFront").Base = blended
    for name in [
        o.Name for o in doc.Objects if o.Name.startswith(("SoftPad", "PadOuter", "PadInner"))
    ]:
        doc.removeObject(name)
    old_main = doc.getObject("EnclosedCradle")
    old_main.Label = "Construction — cavity and underside"
    outer_lip = cylinder(
        doc,
        "LowerLipOuter",
        f"{d}OuterRadius",
        f"{d}LipThickness",
        f"{d}CupDepth-{d}LipThickness",
        angle=180,
    )
    outer_lip.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), 180)
    inner_lip = cylinder(
        doc,
        "LowerLipInner",
        f"{d}InnerRadius-{d}LipInset",
        f"{d}LipThickness",
        f"{d}CupDepth-{d}LipThickness",
    )
    lip = tilted(cut(doc, "LowerCaptureLip", outer_lip, inner_lip))
    with_lip = fuse(doc, "WithLowerLip", [old_main, lip])
    # Preserve the rear plate. The simple version leaves precisely the lower
    # semicircle; the older detent version substitutes straight flexible guides.
    opening = tilted(
        box(
            doc,
            "TopEntryTool",
            f"-{d}OuterRadius-5 mm",
            "-10 mm" if detents else "0 mm",
            f"{d}Back+0.1 mm",
            f"2*{d}OuterRadius+10 mm",
            f"{d}OuterRadius+20 mm",
            f"{d}CupDepth+3 mm",
        )
    )
    open_shell = cut(doc, "TopOpenShell" if detents else "TopLoadingCradle", with_lip, opening)
    if detents:
        rails = []
        for name, x, front_x in (
            ("Right", f"{d}InnerRadius", f"{d}InnerRadius-1.5 mm"),
            ("Left", f"-{d}InnerRadius-{d}RailWall", f"-{d}InnerRadius-{d}RailWall"),
        ):
            rail = tilted(
                box(
                    doc,
                    f"{name}Guide",
                    x,
                    "-12 mm",
                    f"{d}Back+0.25 mm",
                    f"{d}RailWall",
                    "21 mm",
                    f"{d}CupDepth-{d}Back-0.25 mm",
                )
            )
            front = tilted(
                box(
                    doc,
                    f"{name}CaptureLip",
                    front_x,
                    "-12 mm",
                    f"{d}CupDepth-1.4 mm",
                    f"{d}RailWall+1.5 mm",
                    "21 mm",
                    "1.4 mm",
                )
            )
            rails.extend((rail, front))
        rigid = fuse(doc, "GuideStructure", [open_shell, *rails])
        nubs = []
        for name, sign in (("RightDetent", ""), ("LeftDetent", "-")):
            sphere = doc.addObject("Part::Sphere", name)
            expr(sphere, "Radius", f"{d}DetentRadius")
            expr(sphere, "Placement.Base.x", f"{sign}{d}InnerRadius")
            expr(sphere, "Placement.Base.y", "6.5 mm")
            expr(sphere, "Placement.Base.z", f"{d}Back+{d}DeviceDepth/2")
            tilted(sphere)
            nubs.append(sphere)
        main = fuse(doc, "TopLoadingCradle", [rigid, *nubs])
    else:
        main = rigid = open_shell
    main.Label = (
        "TOP-LOADING CRADLE — provisional flex detents"
        if detents
        else "SIMPLE CRADLE — lower semicircular lip, no clips"
    )
    doc.recompute()
    housing = doc.getObject("DeviceEnvelope")
    check_solid(main)
    if main.Shape.common(housing.Shape).Volume > 1e-6:
        raise ValueError("Seated device intersects cradle")
    insertion_axis = housing.Placement.Rotation.multVec(App.Vector(0, 1, 0))
    contacts = []
    for distance in (0, 2, 4, 6.5, 8, 10, 12, 20, 40, 70):
        moving = housing.Shape.copy()
        moving.translate(insertion_axis * distance)
        if rigid.Shape.common(moving).Volume > 1e-6:
            raise ValueError(f"Top entry blocked outside detents at {distance} mm")
        contacts.append(
            {"lift_mm": distance, "detent_interference_mm3": main.Shape.common(moving).Volume}
        )
    if detents and max(item["detent_interference_mm3"] for item in contacts) <= 0:
        raise ValueError("Detents do not engage along insertion path")
    sheet.set("B1", "62.6 mm")
    doc.recompute()
    check_solid(main)
    sheet.set("B1", "61.6 mm")
    doc.recompute()
    check_solid(main)
    mesh = MeshPart.meshFromShape(
        Shape=main.Shape, LinearDeflection=0.05, AngularDeflection=0.1, Relative=False
    )
    if not mesh.isSolid() or mesh.hasNonManifolds():
        raise ValueError("Non-solid/non-manifold mesh")
    mesh.write(str(out / "top-loading-cradle-draft.stl"))
    Part.export([main], str(out / "top-loading-cradle.step"))
    tidy_tree(doc, main)
    check_solid(main)
    doc.saveAs(str(out / "top-loading-cradle.FCStd"))
    report = {
        "status": "Digital concept: physical fit, retention and vehicle use NOT validated",
        "entry": "Top, along device face; no front insertion",
        "hard_opening_mm": 62.2,
        "junction_blend_radius_mm": radius,
        "detents_present": detents,
        "nominal_detent_deflection_per_side_mm": 0.4 if detents else 0,
        "note": (
            "Intentional detent interference requires unverified elastic deflection"
            if detents
            else "Gravity seated; lower lip/back support, no upward latch"
        ),
        "sampled_insertion_contacts": contacts,
        "valid_single_solid": True,
        "closed_manifold_mesh": True,
        "manufacturing_stl_requires_export_verification": True,
        "diameter_edit_checked": True,
    }
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(out / "top-loading-cradle.FCStd"))
    reopened.recompute()
    check_solid(reopened.getObject("TopLoadingCradle"))
    App.closeDocument(reopened.Name)
    report["native_reopen_checked"] = True
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Generated and checked: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
    )
    parser.add_argument(
        "--no-detents",
        action="store_true",
        help="Simple lower semicircle; no rails, clips or soft pads",
    )
    args = parser.parse_args()
    out = args.out or prototype_output("cradle-v4" if args.no_detents else "detent-concept")
    build(out.resolve(), detents=not args.no_detents)
