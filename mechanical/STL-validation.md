# STL validation

`models/cradle-v4.stl` is the sole published manufacturing mesh. STL is unitless;
import it as **mm**. Its JSON report binds the exact STL and native CAD bytes by
SHA-256, with artifact paths relative to the report directory.

Current audit: **PASS**, 40,056 triangles, one connected closed surface,
zero boundary/nonmanifold edges or vertices, winding conflicts, duplicate or
degenerate triangles; FreeCAD reports zero self-intersecting facet pairs.
STL bounds are approximately **76.437 × 52.549 × 76.576 mm**.
Nine lower-cavity section rays give diameters 62.189–62.199 mm against the
native 62.2 mm cavity.

The exporter tessellates `TopLoadingCradle` with 0.02 mm linear deflection,
0.1 rad angular deflection, absolute mode. It reloads the candidate bytes,
independently checks exact-coordinate topology and winding, checks FreeCAD mesh
intersections, compares native optimal bounds (0.1 mm tolerance), volume (0.1%)
and sampled bore dimensions, then publishes only a passing candidate. No welding,
repair, scaling or CAD modification is performed. Existing outputs are protected.

For public release, only the native document's license/URL metadata changed to
the project's selected Unlicense. Every other archive member, including native
shape BREP data and GUI state, remained byte-identical. The STL bytes did not
change. The full read-only audit was rerun and the report/render CAD hash updated;
all measured geometry metrics remained identical.

These are digital consistency checks, not manufacturing certification. Section
rays are samples, not an exhaustive clearance proof; tolerances are comparison
thresholds, not printer accuracy guarantees. Check slicing, units, orientation,
supports, material shrinkage and printed fit yourself. Draft STL files from
generators are not substitutes for the audited export.
