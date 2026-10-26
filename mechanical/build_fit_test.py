"""Generate native, constrained FreeCAD housing-fit coupons (not a road-ready cradle).

Arch Linux:
    PYTHONPATH=/usr/lib/freecad/lib /usr/bin/python mechanical/build_fit_test.py
"""

import argparse
import json
import math
from pathlib import Path

import FreeCAD as App
import MeshPart
import Part
import Sketcher
from project_paths import prototype_output, public_metadata


def dimension(sheet, row, name, value, description):
    sheet.set(f"A{row}", description)
    # A leading minus is otherwise stored as text by the spreadsheet.
    if value.startswith("-"):
        value = "=" + value
    sheet.set(f"B{row}", value)
    sheet.setAlias(f"B{row}", name)


def coupon(doc, sheet, index, clearance):
    body = doc.addObject("PartDesign::Body", f"Coupon{index}")
    body.Label = f"Coupon {index}: {clearance:.2f} mm DIAMETRAL clearance"
    body.Placement.Base = App.Vector((index - 1) * 80, 0, 0)
    sketch = doc.addObject("Sketcher::SketchObject", f"Profile{index}")
    body.addObject(sketch)
    inner = (61.6 + clearance) / 2
    outer = inner + 3
    for radius in (outer, inner):
        sketch.addGeometry(
            Part.ArcOfCircle(Part.Circle(App.Vector(), App.Vector(0, 0, 1), radius), 0, math.pi),
            False,
        )
    sketch.addGeometry(Part.LineSegment(App.Vector(-outer, 0, 0), App.Vector(-inner, 0, 0)), False)
    sketch.addGeometry(Part.LineSegment(App.Vector(inner, 0, 0), App.Vector(outer, 0, 0)), False)
    for arc in (0, 1):
        sketch.addConstraint(Sketcher.Constraint("Coincident", arc, 3, -1, 1))
        for endpoint in (1, 2):
            sketch.addConstraint(Sketcher.Constraint("PointOnObject", arc, endpoint, -1))
    for line, point, arc, endpoint in ((2, 1, 0, 2), (2, 2, 1, 2), (3, 1, 1, 1), (3, 2, 0, 1)):
        sketch.addConstraint(Sketcher.Constraint("Coincident", line, point, arc, endpoint))
    for arc, radius, name in ((0, outer, "OuterRadius"), (1, inner, "InnerRadius")):
        constraint = sketch.addConstraint(Sketcher.Constraint("Radius", arc, radius))
        sketch.renameConstraint(constraint, name)
    inner_expression = f"(Dimensions.DeviceDiameter + Dimensions.Clearance{index}) / 2"
    sketch.setExpression("Constraints.InnerRadius", inner_expression)
    sketch.setExpression(
        "Constraints.OuterRadius", f"{inner_expression} + Dimensions.WallThickness"
    )
    pad = body.newObject("PartDesign::Pad", f"Pad{index}")
    pad.Profile = sketch
    pad.setExpression("Length", "Dimensions.CouponDepth")
    doc.recompute()
    sketch.Visibility = False
    return body, sketch


def validate(body, sketch, diameter, clearance, wall=3, depth=6):
    shape = body.Shape
    inner = (diameter + clearance) / 2
    outer = inner + wall
    expected_volume = math.pi / 2 * (outer**2 - inner**2) * depth
    if not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError(f"{body.Name}: invalid or non-solid geometry")
    if not sketch.FullyConstrained:
        raise ValueError(f"{sketch.Name}: unconstrained sketch")
    for actual, expected in (
        (shape.Volume, expected_volume),
        (shape.BoundBox.XLength, 2 * outer),
        (shape.BoundBox.YLength, outer),
        (shape.BoundBox.ZLength, depth),
    ):
        if not math.isclose(actual, expected, abs_tol=1e-5):
            raise ValueError(f"{body.Name}: geometry mismatch {actual} != {expected}")
    return {
        "diametral_clearance_mm": clearance,
        "inner_diameter_mm": diameter + clearance,
        "volume_mm3": shape.Volume,
        "fully_constrained": True,
        "valid_single_solid": True,
    }


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    doc = App.newDocument("HousingFit")
    public_metadata(doc)
    sheet = doc.addObject("Spreadsheet::Sheet", "Dimensions")
    dimension(sheet, 1, "DeviceDiameter", "61.60 mm", "Nominal device outer diameter")
    dimension(sheet, 2, "WallThickness", "3.00 mm", "Coupon radial wall")
    dimension(sheet, 3, "CouponDepth", "6.00 mm", "Coupon axial depth")
    clearances = (0.3, 0.6, 0.9)
    for index, clearance in enumerate(clearances, 1):
        dimension(
            sheet,
            index + 4,
            f"Clearance{index}",
            f"{clearance} mm",
            f"Coupon {index} diametral clearance (not radial)",
        )
    sheet.setColumnWidth("A", 330)
    sheet.setColumnWidth("B", 120)
    pairs = [coupon(doc, sheet, index, clearance) for index, clearance in enumerate(clearances, 1)]
    report = {"note": "Bench fit coupons only; not retaining mounts or validated tolerances."}
    report["coupons"] = [
        validate(body, sketch, 61.6, clearance)
        for (body, sketch), clearance in zip(pairs, clearances, strict=True)
    ]
    # Prove the spreadsheet actually drives the saved solids, not only their labels.
    sheet.set("B1", "62.60 mm")
    doc.recompute()
    for (body, sketch), clearance in zip(pairs, clearances, strict=True):
        validate(body, sketch, 62.6, clearance)
    sheet.set("B1", "61.60 mm")
    doc.recompute()
    doc.saveAs(str(out / "housing-fit.FCStd"))
    Part.export([body for body, _ in pairs], str(out / "housing-fit.step"))
    for (body, sketch), clearance in zip(pairs, clearances, strict=True):
        validate(body, sketch, 61.6, clearance)
        shape = body.Shape.copy()
        shape.translate(-body.Placement.Base)  # individual exports share a local origin
        mesh = MeshPart.meshFromShape(
            Shape=shape, LinearDeflection=0.05, AngularDeflection=0.1, Relative=False
        )
        if not mesh.isSolid() or mesh.hasNonManifolds():
            raise ValueError(f"{body.Name}: non-solid/non-manifold mesh")
        mesh.write(str(out / f"fit-clearance-{clearance:.2f}mm.stl"))
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(out / "housing-fit.FCStd"))
    reopened.recompute()
    for index, clearance in enumerate(clearances, 1):
        validate(
            reopened.getObject(f"Coupon{index}"),
            reopened.getObject(f"Profile{index}"),
            61.6,
            clearance,
        )
    App.closeDocument(reopened.Name)
    report["spreadsheet_change_and_reopen_checked"] = True
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Generated and validated: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=prototype_output("housing-fit"),
        help="New output directory; existing directories are never overwritten",
    )
    build(parser.parse_args().out.resolve())
