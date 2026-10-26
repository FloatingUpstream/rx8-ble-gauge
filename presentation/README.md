# README artwork

The UI gallery is generated from the actual native LVGL app, not a redraw or
an AI image. Readings/devices are synthetic fixtures and labelled as such.

```sh
bash tools/build-desktop.sh
python3 presentation/make_screenshots.py --force
```

Individual PNGs are written to `docs/images/`. The gallery SVG embeds them
without external image dependencies. `rsvg-convert` additionally generates the
README's gallery PNG (Ubuntu/Debian: `librsvg2-bin`; Arch: `librsvg`).

The studio image has a separate recipe and packed editable Blender scene:
[mechanical/RENDERING.md](../mechanical/RENDERING.md). Its housing is illustrative;
it is not a photograph or physical validation.
