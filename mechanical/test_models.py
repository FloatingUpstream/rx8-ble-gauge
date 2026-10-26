"""Optional CAD checks: run with system Python and FreeCAD's module path."""

import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest.mock import patch

import FreeCAD as App
from build_cradle import cylinder, tilted
from build_enclosed_cradle import build
from build_top_loading import build as build_top_loading
from export_verified_stl import export_verified
from validate_stl import validate


class MechanicalTests(unittest.TestCase):
    def test_native_public_metadata_and_no_external_paths(self):
        native = Path(__file__).parent / "models/cradle-v4.FCStd"
        with zipfile.ZipFile(native) as archive:
            root = ET.fromstring(archive.read("Document.xml"))
            properties = root.find("Properties")
            for field, value in (
                ("License", "The Unlicense"),
                ("LicenseURL", "https://unlicense.org/"),
                ("CreatedBy", ""),
                ("LastModifiedBy", ""),
                ("Company", ""),
            ):
                self.assertEqual(
                    properties.find(f"Property[@name='{field}']/String").get("value"), value
                )
            for name in archive.namelist():
                if name.endswith((".xml", ".txt")):
                    text = archive.read(name).decode()
                    self.assertNotIn("/home/", text)
                    self.assertNotIn("mechanical-prototypes", text)

    def test_committed_stl_matches_current_native_and_report(self):
        folder = Path(__file__).parent / "models"
        result = validate(folder / "cradle-v4.stl", folder / "cradle-v4.FCStd")
        self.assertTrue(result["passed"], result["errors"])
        recorded = json.loads((folder / "cradle-v4.validation.json").read_text())
        self.assertEqual(result["stl_sha256"], recorded["stl_sha256"])
        self.assertEqual(result["cad_reference"]["sha256"], recorded["cad_reference"]["sha256"])

    def test_verified_export_publishes_only_passing_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            doc = App.newDocument("ExportFixture")
            cube = doc.addObject("Part::Box", "TopLoadingCradle")
            cube.Length, cube.Width, cube.Height = 10, 20, 30
            doc.recompute()
            cad = folder / "cube.FCStd"
            doc.saveAs(str(cad))
            App.closeDocument(doc.Name)
            result = export_verified(cad, folder / "cube.stl", folder / "report.json")
            self.assertTrue(result["passed"])
            self.assertEqual(result["cad_reference"]["file"], "cube.FCStd")
            with self.assertRaises(FileExistsError):
                export_verified(cad, folder / "cube.stl", folder / "another.json")
            with patch(
                "export_verified_stl.validate",
                return_value={
                    "passed": False,
                    "errors": ["injected failure"],
                    "note": "test",
                    "cad_reference": {"file": str(cad)},
                },
            ):
                with self.assertRaises(ValueError):
                    export_verified(cad, folder / "rejected.stl", folder / "rejected.json")
            self.assertFalse((folder / "rejected.stl").exists())
            self.assertFalse(any(folder.glob("stl-candidate-*")))

    def test_tilt_preserves_local_offsets_with_canonical_expression_paths(self):
        doc = App.newDocument("PlacementRegression")
        try:
            sheet = doc.addObject("Spreadsheet::Sheet", "Dimensions")
            for row, (name, value) in enumerate((("Tilt", "75 deg"), ("CentreHeight", "43 mm")), 1):
                sheet.set(f"B{row}", value)
                sheet.setAlias(f"B{row}", name)
            obj = cylinder(doc, "OffsetCylinder", "2 mm", "5 mm", "2.4 mm", "37.4 mm")
            self.assertIn(".Placement.Base.z", dict(obj.ExpressionEngine))
            tilted(obj)
            doc.recompute()
            angle = math.radians(75)
            self.assertAlmostEqual(
                obj.Placement.Base.y, 37.4 * math.cos(angle) - 2.4 * math.sin(angle)
            )
            self.assertAlmostEqual(
                obj.Placement.Base.z, 43 + 37.4 * math.sin(angle) + 2.4 * math.cos(angle)
            )
        finally:
            App.closeDocument(doc.Name)

    def test_enclosed_model_exports_and_front_insertion(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "model"
            build(out)
            report = json.loads((out / "validation.json").read_text())
            self.assertTrue(report["front_insertion_path_checked"])
            self.assertTrue(report["native_reopen_checked"])
            self.assertEqual(report["nominal_rigid_intersection_mm3"], 0)
            self.assertGreater((out / "enclosed-cradle.stl").stat().st_size, 1000)
            with self.assertRaises(FileExistsError):
                build(out)

    def test_top_loading_with_only_intentional_detent_contact(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "top"
            build_top_loading(out)
            report = json.loads((out / "validation.json").read_text())
            self.assertTrue(report["native_reopen_checked"])
            self.assertGreater(report["junction_blend_radius_mm"], 0)
            contacts = report["sampled_insertion_contacts"]
            self.assertEqual(contacts[0]["detent_interference_mm3"], 0)
            self.assertGreater(max(c["detent_interference_mm3"] for c in contacts), 0)

    def test_simple_cradle_has_editable_tree_and_clear_drop_in_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "simple"
            build_top_loading(out, detents=False)
            report = json.loads((out / "validation.json").read_text())
            self.assertFalse(report["detents_present"])
            self.assertTrue(
                all(c["detent_interference_mm3"] == 0 for c in report["sampled_insertion_contacts"])
            )
            doc = App.openDocument(str(out / "top-loading-cradle.FCStd"))
            try:
                self.assertIsNotNone(doc.getObject("Construction"))
                self.assertIsNotNone(doc.getObject("ReferenceGeometry"))
                self.assertEqual(doc.getObject("ClosedPedestal").TypeId, "Part::Loft")
                self.assertIsNone(doc.getObject("RightGuide"))
                self.assertIsNone(doc.getObject("LeftDetent"))
                self.assertIsNone(doc.getObject("RoundedFoot"))
                self.assertEqual(doc.getObject("Dimensions").DomeTopOffset.Value, -9)
                for obj in doc.Objects:
                    self.assertNotEqual(obj.TypeId, "Part::FeaturePython")
                    self.assertTrue(all(link.Document.Name == doc.Name for link in obj.OutList))
                published = App.openDocument(str(Path(__file__).parent / "models/cradle-v4.FCStd"))
                try:
                    published.recompute()
                    expected = published.getObject("TopLoadingCradle").Shape
                    generated = doc.getObject("TopLoadingCradle").Shape
                    self.assertAlmostEqual(expected.Volume, generated.Volume, places=6)
                    self.assertLess(expected.cut(generated).Volume, 1e-6)
                    self.assertLess(generated.cut(expected).Volume, 1e-6)
                finally:
                    App.closeDocument(published.Name)
                # A real saved native feature edit, not a change to a label.
                old_volume = doc.getObject("TopLoadingCradle").Shape.Volume
                doc.getObject("Dimensions").set("B18", "1.2 mm")
                doc.recompute()
                self.assertTrue(doc.getObject("TopLoadingCradle").Shape.isValid())
                self.assertNotAlmostEqual(
                    doc.getObject("TopLoadingCradle").Shape.Volume, old_volume, places=3
                )
            finally:
                App.closeDocument(doc.Name)


if __name__ == "__main__":
    unittest.main()
