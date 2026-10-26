"""Rounded slide-in FreeCAD pod concept; physical retention remains unverified."""

import argparse
import json
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part
from build_cradle import check_solid, cut, cylinder, expr, fuse, tilted
from build_fit_test import dimension
from project_paths import prototype_output, public_metadata


def ellipse(doc, name, width, depth, z, y="0 mm"):
    obj = doc.addObject("Part::Ellipse", name)
    expr(obj, "MajorRadius", f"({width})/2")
    expr(obj, "MinorRadius", f"({depth})/2")
    expr(obj, "Placement.Base.z", z)
    expr(obj, "Placement.Base.y", y)
    return obj


def loft(doc, name, bottom, top):
    obj = doc.addObject("Part::Loft", name)
    obj.Sections, obj.Solid, obj.Ruled = [bottom, top], True, True
    return obj


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    doc = App.newDocument("EnclosedCradle")
    public_metadata(doc)
    sheet = doc.addObject("Spreadsheet::Sheet", "Dimensions")
    entries = [
        ("DeviceDiameter", "61.6 mm", "Nominal device envelope"),
        ("DeviceDepth", "14.6 mm", "Nominal depth; rear contour unknown"),
        ("Clearance", "0.6 mm", "Provisional DIAMETRAL clearance"),
        ("Wall", "3 mm", "Nominal pod radial wall"),
        ("Back", "2.4 mm", "Closed pod rear thickness"),
        ("AxialClearance", "0.8 mm", "Axial allowance behind/in front of nominal device"),
        ("Tilt", "75 deg", "Screen plane above horizontal"),
        ("CentreHeight", "43 mm", "Device centre above foot"),
        ("FootWidth", "76 mm", "Rounded foot width"),
        ("FootDepth", "50 mm", "Rounded foot depth"),
        ("FootThickness", "3 mm", "Foot thickness"),
        ("InnerRadius", "=(B1+B3)/2", "Hard shell internal radius"),
        ("OuterRadius", "=B12+B4", "Hard shell outer radius"),
        ("CupDepth", "=B5+B2+B6+1.4 mm", "Overall pod axial length"),
        ("PadThickness", "0.4 mm", "Illustrative soft pad thickness; not material selection"),
    ]
    for row, (name, value, description) in enumerate(entries, 1):
        dimension(sheet, row, name, value, description)
    sheet.setColumnWidth("A", 460)
    sheet.setColumnWidth("B", 130)
    d = "Dimensions."
    foot_profile = ellipse(doc, "FootOutline", f"{d}FootWidth", f"{d}FootDepth", "0 mm")
    foot = doc.addObject("Part::Extrusion", "RoundedFoot")
    foot.Base, foot.Dir, foot.Solid = foot_profile, App.Vector(0, 0, 1), True
    expr(foot, "LengthFwd", f"{d}FootThickness")
    lower = ellipse(
        doc, "PedestalBase", f"{d}FootWidth", f"{d}FootDepth", f"{d}FootThickness-0.5 mm"
    )
    upper = ellipse(doc, "PedestalTop", "56 mm", "22 mm", "31 mm", "-9 mm")
    pedestal = loft(doc, "ClosedPedestal", lower, upper)
    outer = cylinder(doc, "OuterPodBlank", f"{d}OuterRadius", f"{d}CupDepth")
    doc.recompute()
    rounded = doc.addObject("Part::Fillet", "RoundedPod")
    rounded.Base = outer
    circular_edges = [
        i for i, edge in enumerate(outer.Shape.Edges, 1) if edge.BoundBox.ZLength < 1e-6
    ]
    rounded.Edges = [(i, 1.2, 1.2) for i in circular_edges]
    tilted(rounded)
    blank = fuse(doc, "EnclosedBlank", [foot, pedestal, rounded])
    cavity = tilted(
        cylinder(doc, "DeviceCavity", f"{d}InnerRadius", f"{d}CupDepth+2 mm-{d}Back", f"{d}Back")
    )
    hollow = cut(doc, "OpenFront", blank, cavity)
    bevel = doc.addObject("Part::Cone", "MouthLeadIn")
    expr(bevel, "Radius1", f"{d}InnerRadius")
    expr(bevel, "Radius2", f"{d}InnerRadius+0.6 mm")
    expr(bevel, "Height", "1.05 mm")
    expr(bevel, "Placement.Base.z", f"{d}CupDepth-1 mm")
    tilted(bevel)
    lead_in = cut(doc, "LeadIn", hollow, bevel)
    scallops = cylinder(doc, "FingerRelief", "4.5 mm", f"2*({d}OuterRadius+2 mm)")
    scallops.Placement.Rotation = App.Rotation(App.Vector(0, 1, 0), 90)
    expr(scallops, "Placement.Base.x", f"-{d}OuterRadius-2 mm")
    expr(scallops, "Placement.Base.y", f"-sin({d}Tilt)*{d}CupDepth")
    expr(scallops, "Placement.Base.z", f"{d}CentreHeight+cos({d}Tilt)*{d}CupDepth")
    relieved = cut(doc, "FingerCutouts", lead_in, scallops)
    # Open underside, broad adhesive flange; no trapped support-filled cavity.
    inner_bottom = ellipse(doc, "UndersideOpening", "58 mm", "32 mm", "-1 mm")
    inner_top = ellipse(doc, "PedestalInnerTop", "44 mm", "8 mm", "26 mm", "-9 mm")
    interior = loft(doc, "PedestalVoid", inner_bottom, inner_top)
    main = cut(doc, "EnclosedCradle", relieved, interior)
    main.Label = "ENCLOSED CRADLE — rounded slide-in concept"

    pads = []
    for index, angle in enumerate((90, 210, 330), 1):
        outer_pad = cylinder(
            doc, f"PadOuter{index}", f"{d}InnerRadius", "6 mm", f"{d}Back+4 mm", angle=12
        )
        outer_pad.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), angle - 6)
        inner_pad = cylinder(
            doc, f"PadInner{index}", f"{d}InnerRadius-{d}PadThickness", "6 mm", f"{d}Back+4 mm"
        )
        pad = tilted(cut(doc, f"SoftPad{index}", outer_pad, inner_pad))
        pad.Label = f"REFERENCE soft friction pad {index} — compression/material untested"
        pads.append(pad)
    housing = tilted(cylinder(doc, "DeviceEnvelope", f"{d}DeviceDiameter/2", f"{d}DeviceDepth"))
    rear = f"{d}Back+{d}AxialClearance/2"
    expr(housing, "Placement.Base.y", f"-sin({d}Tilt)*({rear})")
    expr(housing, "Placement.Base.z", f"{d}CentreHeight+cos({d}Tilt)*({rear})")
    housing.Label = "REFERENCE ONLY — nominal device, ports/curvature omitted"
    face = tilted(cylinder(doc, "ScreenReference", "27.5 mm", "0.15 mm"))
    front = f"{rear}+{d}DeviceDepth"
    expr(face, "Placement.Base.y", f"-sin({d}Tilt)*({front})")
    expr(face, "Placement.Base.z", f"{d}CentreHeight+cos({d}Tilt)*({front})")
    face.Label = "REFERENCE ONLY — simplified screen face"
    doc.recompute()
    for obj in (main, housing, *pads):
        check_solid(obj)
    rigid_intersection = main.Shape.common(housing.Shape).Volume
    if rigid_intersection > 1e-6:
        raise ValueError(f"Rigid shell intersects nominal device: {rigid_intersection}")
    # Clearance at rest is not enough: the device must also pass through the mouth.
    insertion_axis = housing.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    for distance in (1, 2, 4, 8, 16, 24):
        moving = housing.Shape.copy()
        moving.translate(insertion_axis * distance)
        if main.Shape.common(moving).Volume > 1e-6:
            raise ValueError(f"Rigid shell blocks front insertion at {distance} mm")
    for pad in pads:
        overlap = pad.Shape.common(housing.Shape).Volume
        if not 0 < overlap < 10:
            raise ValueError(f"{pad.Name}: unexpected nominal soft contact {overlap}")
    initial_volume = main.Shape.Volume
    sheet.set("B1", "62.6 mm")
    doc.recompute()
    check_solid(main)
    if abs(main.Shape.Volume - initial_volume) < 0.1:
        raise ValueError("Diameter edit did not change shell")
    sheet.set("B1", "61.6 mm")
    doc.recompute()
    check_solid(main)
    mesh = MeshPart.meshFromShape(
        Shape=main.Shape, LinearDeflection=0.05, AngularDeflection=0.1, Relative=False
    )
    if not mesh.isSolid() or mesh.hasNonManifolds():
        raise ValueError("Non-solid/non-manifold shell mesh")
    mesh.write(str(out / "enclosed-cradle.stl"))
    Part.export([main], str(out / "enclosed-cradle.step"))
    doc.saveAs(str(out / "enclosed-cradle.FCStd"))
    report = {
        "status": "Digital concept only: slide-in friction retention NOT validated",
        "hard_opening_mm": 62.2,
        "soft_pad_thickness_mm": 0.4,
        "nominal_soft_radial_compression_mm": 0.1,
        "pad_note": "Illustrative compliant parts only; omitted from fabrication exports",
        "nominal_rigid_intersection_mm3": rigid_intersection,
        "foot": "76x50mm elliptical, flat adhesive flange with open underside",
        "valid_single_solid": True,
        "closed_manifold_mesh": True,
        "diameter_change_checked": True,
        "front_insertion_path_checked": True,
    }
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(out / "enclosed-cradle.FCStd"))
    reopened.recompute()
    check_solid(reopened.getObject("EnclosedCradle"))
    App.closeDocument(reopened.Name)
    report["native_reopen_checked"] = True
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Generated and checked: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=prototype_output("enclosed-base"),
    )
    build(parser.parse_args().out.resolve())
