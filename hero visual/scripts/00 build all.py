"""00 build all.py

Runs every numbered phase one script in order on a fresh empty scene and
saves the result as OVM Hat Hero.blend in the working folder.

Run with Blender:   blender --background --python "00 build all.py"
Or the bpy module:  python "00 build all.py"
Or from the Blender Text Editor with Run Script (the current file is
overwritten by the saved result, so run it from an unsaved or scratch file).

Set the environment variable HATHERO_SKIP_RENDERS=1 to build without
rendering any previews.
"""
import bpy
import os
import re
import runpy
import time


def here():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        text = bpy.context.space_data.text
        return os.path.dirname(bpy.path.abspath(text.filepath))


SCRIPTS_DIR = here()
WORK = os.path.dirname(SCRIPTS_DIR)
BLEND = os.path.join(WORK, "OVM Hat Hero.blend")

scripts = sorted(f for f in os.listdir(SCRIPTS_DIR) if re.match(r"^0[1-9] .*\.py$", f))
print(f"[00 build all] {len(scripts)} scripts: {scripts}")

bpy.ops.wm.read_homefile(use_empty=True)
t0 = time.time()
for name in scripts:
    print(f"\n{'#' * 70}\n# {name}\n{'#' * 70}")
    runpy.run_path(os.path.join(SCRIPTS_DIR, name), run_name="__main__")

# drop anything that lost its last user along the way (old meshes, fonts)
for _ in range(3):
    bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

# link the scripts into the Text Editor so they can be re-run from inside the file
for name in ["00 build all.py"] + scripts:
    path = os.path.join(SCRIPTS_DIR, name)
    if name not in bpy.data.texts:
        bpy.data.texts.load(path, internal=False)

bpy.context.scene.render.filepath = "//renders/"
bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True, relative_remap=True)
size_mb = os.path.getsize(BLEND) / 1e6
print(f"\n[00 build all] saved {BLEND} ({size_mb:.1f} MB) in {time.time() - t0:.0f} s total")
