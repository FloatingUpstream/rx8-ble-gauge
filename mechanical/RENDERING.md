# Studio render

Published PNGs have textual/EXIF/time metadata removed without re-encoding image
pixels. The renderer disables Blender stamp metadata and applies the same
sanitisation after saving so local render paths are not published accidentally.

The packed `renders/cradle-v4-studio.blend` is editable in Blender 4.5.
The cradle mesh is the exact validated STL, converted mm → metres, with smooth
shading/material only and **no geometry modifiers**. Device housing, cover glass
and ports are presentation approximations. The yellow RX-8 UI texture is the
current desktop screenshot from `docs/images/coolant.png`: a **synthetic fixture**
showing coolant 87 °C and MAF 12.40 g/s, not live vehicle data. Its `LIVE` indicator
is fixture state, not evidence of a vehicle connection. This is not
evidence of physical fit, readability or vehicle suitability.

From the repository root, with Blender available on `PATH`:

```sh
blender --background --factory-startup --python mechanical/render_cradle.py -- \
  --out .local/aux/mechanical/studio-new

blender --background mechanical/renders/cradle-v4-studio.blend \
  --python mechanical/check_render.py
```

By default the script reads the published STL/report/UI texture and writes a new
directory under `${GAUGE_AUX:-<repo>/.local/aux}/mechanical/studio`.
It refuses an existing directory. Options include `--stl`, `--validation`,
`--screen`, `--samples`, `--width` and `--height`.

The script verifies the passing report against both exact STL bytes and current
CAD bytes before building the scene. Outputs are `cradle-v4-studio.blend`,
`cradle-v4-studio.png`, and `cradle-v4-studio.metadata.json` (hash bindings,
units, settings and approximation notes). Re-export/re-audit after any CAD edit,
including metadata-only edits, then build a new scene with that report.

The image is packed and its fallback path is relative to the saved scene.
The render output uses `//cradle-v4-studio.png`, relative to that scene too.
If relocating a scene alone, packed resources still work; update fallback paths
relative to its new location before publishing. The published layout uses
`//../render-assets/gauge-normal.png`. No private tools or source directories
are needed to open or render the scene.

To render a hand-edited scene without regenerating over it, copy it to a scratch
directory and use Blender's UI or `blender --background FILE.blend --render-frame 1`.
That command writes the scene's configured image output; choose a new output path
in Blender if you need to preserve an existing PNG.
