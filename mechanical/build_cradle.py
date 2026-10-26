"""FreeCAD cradle concept; dimensions and retention are provisional, not road-rated."""

import argparse
import json
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part
import Sketcher
from build_fit_test import dimension
from project_paths import prototype_output, public_metadata


def expr(obj, field, formula):
    obj.setExpression(field, formula)


def tilted(obj):
    # FreeCAD canonicalises placement paths with a leading dot.
    expressions = {path.lstrip("."): formula for path, formula in obj.ExpressionEngine}
    local_y = expressions.get("Placement.Base.y", "0 mm")
    local_z = expressions.get("Placement.Base.z", "0 mm")
    obj.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), 75))
    expr(
        obj,
        "Placement.Base.y",
        f"cos(Dimensions.Tilt)*({local_y})-sin(Dimensions.Tilt)*({local_z})",
    )
    expr(
        obj,
        "Placement.Base.z",
        f"Dimensions.CentreHeight+sin(Dimensions.Tilt)*({local_y})"
        f"+cos(Dimensions.Tilt)*({local_z})",
    )
    expr(obj, "Placement.Rotation.Angle", "Dimensions.Tilt")
    return obj


def box(doc, name, x, y, z, length, width, height):
    obj = doc.addObject("Part::Box", name)
    for field, formula in (
        ("Length", length),
        ("Width", width),
        ("Height", height),
        ("Placement.Base.x", x),
        ("Placement.Base.y", y),
        ("Placement.Base.z", z),
    ):
        expr(obj, field, formula)
    return obj


def cylinder(doc, name, radius, height, z="0 mm", y="0 mm", angle=None):
    obj = doc.addObject("Part::Cylinder", name)
    expr(obj, "Radius", radius)
    expr(obj, "Height", height)
    expr(obj, "Placement.Base.z", z)
    expr(obj, "Placement.Base.y", y)
    if angle is not None:
        obj.Angle = angle
        obj.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), 200)
    return obj


def cut(doc, name, base, tool):
    obj = doc.addObject("Part::Cut", name)
    obj.Base, obj.Tool, obj.Refine = base, tool, True
    return obj


def fuse(doc, name, shapes):
    obj = doc.addObject("Part::MultiFuse", name)
    obj.Shapes, obj.Refine = shapes, True
    return obj


def rectangle(doc, name, width, depth, z, y):
    """Fully constrained, spreadsheet-driven centred rectangle for the brace loft."""
    sketch = doc.addObject("Sketcher::SketchObject", name)
    points = [(-10, -10), (10, -10), (10, 10), (-10, 10)]
    for i, (x, yy) in enumerate(points):
        xx, yyy = points[(i + 1) % 4]
        sketch.addGeometry(Part.LineSegment(App.Vector(x, yy, 0), App.Vector(xx, yyy, 0)))
        sketch.addConstraint(Sketcher.Constraint("Horizontal" if i % 2 == 0 else "Vertical", i))
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    for constraint, name_, formula in (
        (Sketcher.Constraint("DistanceX", 0, 1, -10.0), "Left", f"-({width}) / 2"),
        (Sketcher.Constraint("DistanceY", 0, 1, -10.0), "Bottom", f"-({depth}) / 2"),
        (Sketcher.Constraint("Distance", 0, 20.0), "Width", width),
        (Sketcher.Constraint("Distance", 1, 20.0), "Depth", depth),
    ):
        index = sketch.addConstraint(constraint)
        sketch.renameConstraint(index, name_)
        expr(sketch, f"Constraints.{name_}", formula)
    expr(sketch, "Placement.Base.z", z)
    expr(sketch, "Placement.Base.y", y)
    return sketch


def check_solid(obj):
    if not obj.Shape.isValid() or len(obj.Shape.Solids) != 1 or obj.Shape.Volume <= 0:
        raise ValueError(f"{obj.Name}: expected one valid solid")


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    doc = App.newDocument("CradleConcept")
    public_metadata(doc)
    sheet = doc.addObject("Spreadsheet::Sheet", "Dimensions")
    entries = [
        ("DeviceDiameter", "61.6 mm", "Nominal housing diameter"),
        ("DeviceDepth", "14.6 mm", "Nominal housing depth"),
        ("Clearance", "0.6 mm", "Provisional DIAMETRAL clearance"),
        ("Wall", "3 mm", "Radial wall"),
        ("Back", "2.4 mm", "Back plate thickness"),
        ("AxialClearance", "0.8 mm", "Total provisional axial clearance"),
        ("LipInset", "1.5 mm", "Front lip radial inset"),
        ("LipThickness", "1.4 mm", "Front lip thickness"),
        ("Tilt", "75 deg", "Screen plane above horizontal: 15 deg back from vertical"),
        ("CentreHeight", "43 mm", "Housing centre height above flat foot"),
        ("FootWidth", "76 mm", "Provisional flat adhesive foot width"),
        ("FootDepth", "50 mm", "Provisional flat adhesive foot depth"),
        ("FootThickness", "3 mm", "Foot thickness"),
        ("ScrewClearance", "3.4 mm", "Provisional M3 clearance hole"),
        ("InnerRadius", "=(B1 + B3) / 2", "Cradle internal radius"),
        ("OuterRadius", "=B15 + B4", "Cradle external radius"),
        ("FrontZ", "=B5 + B2 + B6", "Start of front retaining lip"),
        ("KeeperY", "=B16 + 3.3 mm", "Keeper fastener local Y"),
    ]
    for row, (name, value, description) in enumerate(entries, 1):
        dimension(sheet, row, name, value, description)
    sheet.setColumnWidth("A", 440)
    sheet.setColumnWidth("B", 130)
    d = "Dimensions."
    foot = box(
        doc,
        "FlatFoot",
        f"-{d}FootWidth/2",
        f"-{d}FootDepth/2",
        "0 mm",
        f"{d}FootWidth",
        f"{d}FootDepth",
        f"{d}FootThickness",
    )
    back = tilted(cylinder(doc, "RoundBack", f"{d}OuterRadius", f"{d}Back"))
    # Lower 140 degrees only: top and most side edges remain open.
    outer = cylinder(
        doc,
        "WallOuter",
        f"{d}OuterRadius",
        f"{d}DeviceDepth+{d}AxialClearance",
        f"{d}Back",
        angle=140,
    )
    inner = cylinder(
        doc, "WallInner", f"{d}InnerRadius", f"{d}DeviceDepth+{d}AxialClearance", f"{d}Back"
    )
    wall = tilted(cut(doc, "LowerWall", outer, inner))
    lip_outer = cylinder(
        doc, "LipOuter", f"{d}OuterRadius", f"{d}LipThickness", f"{d}FrontZ", angle=140
    )
    lip_inner = cylinder(
        doc, "LipInner", f"{d}InnerRadius-{d}LipInset", f"{d}LipThickness", f"{d}FrontZ"
    )
    lip = tilted(cut(doc, "LowerLip", lip_outer, lip_inner))
    tab = tilted(
        box(
            doc,
            "KeeperMount",
            "-8 mm",
            f"{d}OuterRadius-7.1 mm",
            "0 mm",
            "16 mm",
            "15 mm",
            f"{d}Back",
        )
    )
    bottom = rectangle(doc, "BraceBase", "20 mm", "24 mm", f"{d}FootThickness-0.5 mm", "10 mm")
    top = rectangle(doc, "BraceTop", "20 mm", "4 mm", f"{d}CentreHeight-3 mm", "-0.5 mm")
    brace = doc.addObject("Part::Loft", "RearBrace")
    brace.Sections, brace.Solid, brace.Ruled = [bottom, top], True, True
    frame = fuse(doc, "FrameBeforeHole", [foot, back, wall, lip, tab, brace])
    fastener = tilted(
        cylinder(
            doc,
            "FrameFastenerHole",
            f"{d}ScrewClearance/2",
            f"{d}FrontZ+{d}LipThickness+2 mm",
            y=f"{d}KeeperY",
        )
    )
    main = cut(doc, "Cradle", frame, fastener)
    main.Label = "CRADLE — provisional flat adhesive foot"

    column = box(
        doc,
        "KeeperColumn",
        "-6 mm",
        f"{d}OuterRadius+0.3 mm",
        f"{d}Back+0.3 mm",
        "12 mm",
        "6 mm",
        f"{d}FrontZ+{d}LipThickness-{d}Back-0.3 mm",
    )
    hook = box(
        doc,
        "KeeperLip",
        "-6 mm",
        f"{d}InnerRadius-{d}LipInset",
        f"{d}FrontZ",
        "12 mm",
        f"{d}OuterRadius+6.3 mm-{d}InnerRadius+{d}LipInset",
        f"{d}LipThickness",
    )
    keeper_blank = fuse(doc, "KeeperBeforeHole", [column, hook])
    keeper_hole = cylinder(
        doc,
        "KeeperFastenerHole",
        f"{d}ScrewClearance/2",
        f"{d}FrontZ+{d}LipThickness+2 mm",
        y=f"{d}KeeperY",
    )
    keeper = tilted(cut(doc, "TopKeeper", keeper_blank, keeper_hole))
    keeper.Label = "REMOVABLE TOP KEEPER — fastener not supplied/modelled"

    # Envelope references only; no claim to reproduce actual housing curvature/ports.
    housing = cylinder(doc, "DeviceEnvelope", f"{d}DeviceDiameter/2", f"{d}DeviceDepth")
    tilted(housing)
    # Move along the tilted axis, not along world Z.
    rear = f"{d}Back+{d}AxialClearance/2"
    expr(housing, "Placement.Base.y", f"-sin({d}Tilt)*({rear})")
    expr(housing, "Placement.Base.z", f"{d}CentreHeight+cos({d}Tilt)*({rear})")
    housing.Label = "REFERENCE ONLY — nominal housing; ports/back curvature unknown"
    glass = tilted(cylinder(doc, "ScreenReference", "27.5 mm", "0.15 mm"))
    face = f"{rear}+{d}DeviceDepth"
    expr(glass, "Placement.Base.y", f"-sin({d}Tilt)*({face})")
    expr(glass, "Placement.Base.z", f"{d}CentreHeight+cos({d}Tilt)*({face})")
    glass.Label = "REFERENCE ONLY — simplified front face"
    doc.recompute()
    for obj in (main, keeper, housing):
        check_solid(obj)
    if main.Shape.common(keeper.Shape).Volume > 1e-6:
        raise ValueError("Keeper intersects frame")
    if main.Shape.common(housing.Shape).Volume > 1e-6:
        raise ValueError("Cradle intersects nominal device")
    if keeper.Shape.common(housing.Shape).Volume > 1e-6:
        raise ValueError("Keeper intersects nominal device")
    if not bottom.FullyConstrained or not top.FullyConstrained:
        raise ValueError("Unconstrained brace sketch")
    # Prove that a housing-size edit updates the assembly without breaking solids.
    sheet.set("B1", "62.6 mm")
    doc.recompute()
    for obj in (main, keeper):
        check_solid(obj)
    sheet.set("B1", "61.6 mm")
    doc.recompute()
    report = {
        "status": "Digital concept only; not print/vehicle/adhesive validated",
        "opening_mm": 62.2,
        "flat_foot_mm": [76, 50, 3],
        "tilt_degrees_above_horizontal": 75,
        "nominal_interference_mm3": 0,
        "spreadsheet_diameter_change_checked": True,
        "parts": {},
    }
    for obj, filename in ((main, "cradle"), (keeper, "top-keeper")):
        check_solid(obj)
        mesh = MeshPart.meshFromShape(
            Shape=obj.Shape, LinearDeflection=0.05, AngularDeflection=0.1, Relative=False
        )
        if not mesh.isSolid() or mesh.hasNonManifolds():
            raise ValueError(f"{filename}: invalid mesh")
        mesh.write(str(out / f"{filename}.stl"))
        report["parts"][filename] = {
            "volume_mm3": obj.Shape.Volume,
            "valid_single_solid": True,
            "closed_mesh": True,
        }
    Part.export([main, keeper], str(out / "cradle.step"))
    doc.saveAs(str(out / "cradle.FCStd"))
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(out / "cradle.FCStd"))
    reopened.recompute()
    for name in ("Cradle", "TopKeeper"):
        check_solid(reopened.getObject(name))
    App.closeDocument(reopened.Name)
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Generated and checked: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=prototype_output("cradle-base"),
    )
    build(parser.parse_args().out.resolve())
