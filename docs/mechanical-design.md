# Mechanical design

The current v4 concept is a top-loading cradle: smooth domed base, hollow
underside with adhesive flange, back support and lower semicircular lip.
There are no flexible clips, soft pads or upward latch. Nominal reference housing
is 61.6 mm diameter × 14.6 mm deep; the hard cavity diameter is 62.2 mm.
Reference geometry is not part of the manufactured solid.

## What has been checked

The editable FreeCAD model has a native feature tree, spreadsheet-driven
dimensions and a single valid final solid. Regression tests exercise native
reopening, dimension edits and sampled insertion positions. The primary STL
has an independent topology check, FreeCAD mesh intersection checks, bounds,
volume and sampled cavity comparisons against the exact native model.
The Blender cradle uses those verified triangles without geometry modifiers.

## What has not been established

- As-built housing dimensions, cable/connector access and back curvature.
- Printed fit, shrinkage, surface finish, insertion force or long-term wear.
- Retention against upward motion, braking, impact, vibration or crash loads.
- Adhesive selection, dashboard curvature, surface preparation or hot-car creep.
- Visibility, glare, driver distraction, airbag clearance or legal compliance.

Gravity seating and a lower lip are **not positive retention**. Do not treat a
successful digital check or attractive render as approval for vehicle use.
Measure the actual device and installation, prototype off-vehicle, and establish
material, mounting and retention requirements before considering road use.

## Files and workflows

- [Native authoritative CAD](../mechanical/models/cradle-v4.FCStd)
- [Primary STL](../mechanical/models/cradle-v4.stl) and
  [validation report](../mechanical/models/cradle-v4.validation.json)
- [Mechanical guide: viewing, source generation, protected export and tests](../mechanical/README.md)
- [Validation scope](../mechanical/STL-validation.md)
- [Packed Blender scene/render workflow](../mechanical/RENDERING.md)
- [Studio presentation](../mechanical/renders/cradle-v4-studio.png)

Original project assets retain the repository's Unlicense; third-party notices
and licensing remain separate.
