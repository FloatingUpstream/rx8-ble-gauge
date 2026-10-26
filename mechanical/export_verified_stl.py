"""Export from authoritative native CAD, validate reloaded bytes, then publish.

No CAD changes or mesh repairs. Existing outputs/reports are never overwritten.
Run using system Python with FreeCAD's module path.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

import FreeCAD as App
import MeshPart
from validate_stl import validate


def export_verified(cad, out, report, object_name="TopLoadingCradle"):
    cad, out, report = cad.resolve(), out.resolve(), report.resolve()
    if out.exists() or report.exists():
        raise FileExistsError("Choose new STL/report paths; existing artifacts are preserved")
    out.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="stl-candidate-", suffix=".stl", dir=out.parent)
    os.close(descriptor)
    candidate = Path(name)
    try:
        doc = App.openDocument(str(cad))
        try:
            doc.recompute()
            obj = doc.getObject(object_name)
            if obj is None or not obj.Shape.isValid() or len(obj.Shape.Solids) != 1:
                raise ValueError("Expected one valid native CAD solid")
            mesh = MeshPart.meshFromShape(
                Shape=obj.Shape, LinearDeflection=0.02, AngularDeflection=0.1, Relative=False
            )
            mesh.write(str(candidate))
        finally:
            App.closeDocument(doc.Name)
        result = validate(candidate, cad, object_name)
        result["export_parameters"] = {
            "linear_deflection_mm": 0.02,
            "angular_deflection_radians": 0.1,
            "relative": False,
            "mesh_repaired": False,
        }
        result["stl_file"] = os.path.relpath(out, report.parent)
        result["cad_reference"]["file"] = os.path.relpath(cad, report.parent)
        result["path_convention"] = "Artifact paths are relative to this report's directory"
        if result["passed"]:
            os.link(candidate, out)  # atomic publication; refuses an existing target
        else:
            result["stl_file"] = None
            result["note"] += " Failed candidate was not published."
        with report.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        if not result["passed"]:
            raise ValueError("STL export rejected: " + "; ".join(result["errors"]))
        print(f"Verified STL: {out}\nReport: {report}")
        return result
    finally:
        candidate.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cad", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--object", default="TopLoadingCradle")
    args = parser.parse_args()
    export_verified(args.cad, args.out, args.report, args.object)
