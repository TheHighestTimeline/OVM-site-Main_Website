# OVM Hat Hero, Blender build

Phase one of the scroll hero from the Hat Hero handbook (v2). Assets only:
the cap, its fabric and stitching, the embroidered words, the stone mark,
and the hero still. No animation yet, that is phase two and it waits on the
hero still being approved.

## Open it

Double click `OVM Hat Hero.blend`. The scene is the hero still: five hats on
the left, `LOGO.stone` front and centre right, `CAM.hero` at 85 mm, Cycles,
transparent film. Press F12 to render, or view through the camera (numpad 0)
with rendered shading.

Every build script is linked into the Text Editor inside the file, so you
can tweak a parameter at the top of a script and press Run Script. Each
script rebuilds only the objects it owns, by name, so they can be re-run in
any order after the first pass.

## Rebuild from scratch

    blender --background --python "scripts/00 build all.py"

That runs 01 to 05 in order on an empty scene, renders every preview into
`renders`, and saves the .blend. Set `HATHERO_SKIP_RENDERS=1` to skip the
previews, or `HATHERO_SKIP_FULL_RENDER=1` to skip only the 1400 px still.
It also runs with the bpy module: `python "scripts/00 build all.py"`.

## Folder

| Path | What |
|---|---|
| `scripts/01 hat model.py` | `HAT.base`, procedural six panel cap, `CAM.hero`, three point rig |
| `scripts/02 fabric and seams.py` | `MAT.fabric black`, `MAT.thread bone`, `MAT.thread gold`, `STITCH.seam` |
| `scripts/03 lettering.py` | `STITCH.letters.<name>` satin stitch words, five of them |
| `scripts/04 logo stone.py` | `LOGO.stone`, the OneVibeMedia wordmark: ring project O plus neVibeMedia in Cinzel small caps, `MAT.stone` |
| `scripts/05 hero still.py` | the five `HAT.<name>` linked duplicates, layout, lights, `LIGHT.founder`, full render |
| `renders/` | 800 px previews named after the script that made them, plus `05 hero still.png` at 1400 px |
| `frames/` | empty until phase two, the PNG sequence lands here |
| `reference/OVM ring.blend` | the engraved O ring from the 3D printed ring project (`MayanRingDebossedBoth`), appended by script 04 |
| `reference/fonts/` | Cinzel (OFL). `Cinzel Bold.ttf` is a static instance with overlaps removed. The variable file is kept for reference only, Blender cannot fill its glyphs |
| `reference/OneVibeMediaGroup stone reference.webp` | the stone render the mark is modelled after, minus Group |
| `reference/OVM wordmark black.png` | the flat wordmark |

## Things to tune first

All at the top of each script, in metres.

- `01`: `CROWN_WIDTH`, `CROWN_HEIGHT`, `PROFILE`, brim length and curl.
- `02`: `FABRIC_BASE`, `SHEEN_WEIGHT`, stitch length and thread width, light power.
- `03`: `CAP_HEIGHT`, `STITCH_ANGLE`, `PITCH`, `LETTER_Z`.
- `04`: `O_DIAMETER` (the whole mark is about six times this wide), `DEPTH`, `LETTER_CAP_HEIGHT`, `SMALL_CAPS_SCALE`, stone colours in `build_stone_material`.
- `05`: `STACK_X`, `STACK_SPACING`, `LOGO_LOCATION`, `FRAME_MARGIN` (the camera auto frames stack and mark together), light power in `relight`.

## Cap reference

The cap follows Tanner's reference photos (a white six panel cap, shared in
chat on 18 September 2026, not saved as files): low rounded crown, long
pre curved brim with the sides bending down, double topstitch straddling
each seam, six stitched brim rows, one eyelet per panel, a covered button.

## Rules carried from the handbook

Spaces in file names, never underscores (the frame sequence is the one
exception). Object names are the interface between scripts and are locked.
Every figure in a runtime report is measured, never asserted. Gold thread is
never a metal shader. The hat never changes material.
