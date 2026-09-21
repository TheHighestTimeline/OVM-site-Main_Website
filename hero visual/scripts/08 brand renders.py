"""08 brand renders. Two transparent PNGs of the stone wordmark for the site chrome.

  renders/wordmark stone.png   the whole OneVibeMedia wordmark, tight crop, for the nav and footer
  renders/favicon stone O.png  the ring O alone, square, for the browser tab icon

Both are rendered from LOGO.stone as built by 04 and lit as in 05, with every hat hidden,
through a temporary camera that frames the logo bounds. Nothing in the scene is changed:
the camera is removed and hidden objects restored before the script ends.
Skipped when HATHERO_SKIP_RENDERS=1.
"""
import bpy
import math
import os
import time
from mathutils import Vector

SCRIPT = "08 brand renders"
SKIP_RENDERS = os.environ.get("HATHERO_SKIP_RENDERS") == "1"
WORDMARK_WIDTH = 2400      # px, wide enough to stay crisp at any nav size
ICON_SIZE = 512            # px, square
SAMPLES = 128
MARGIN = 0.04              # fraction of the subject width left clear on each side


def workdir():
    candidates = []
    if bpy.data.filepath:
        candidates.append(os.path.dirname(bpy.data.filepath))
    try:
        text = bpy.context.space_data.text
        if text and text.filepath:
            candidates.append(os.path.dirname(bpy.path.abspath(text.filepath)))
    except Exception:
        pass
    candidates.append(os.getcwd())
    for start in candidates:
        d = start
        for _ in range(4):
            if os.path.isdir(os.path.join(d, "scripts")):
                return d
            d = os.path.dirname(d)
    raise RuntimeError("Cannot locate the Hat Hero working folder (needs a scripts subfolder)")


def require(name):
    ob = bpy.data.objects.get(name)
    if ob is None:
        raise RuntimeError(f"{SCRIPT}: required object '{name}' is missing. Run the earlier scripts first.")
    return ob


def bounds(points):
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return lo, hi


def render_subject(scene, cam, lo, hi, width, height, path):
    """Frame the box lo..hi square on from the front with an orthographic camera and render."""
    centre = (lo + hi) * 0.5
    span_x, span_z = hi.x - lo.x, hi.z - lo.z
    aspect = width / height
    ortho = max(span_x * (1.0 + 2 * MARGIN), span_z * (1.0 + 2 * MARGIN) * aspect)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho
    cam.location = Vector((centre.x, lo.y - 3.0, centre.z))
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    return time.time() - t0


def main():
    work = workdir()
    scene = bpy.context.scene
    logo = require("LOGO.stone")
    print(f"\n[{SCRIPT}] working folder: {work}")
    if SKIP_RENDERS:
        print("  HATHERO_SKIP_RENDERS=1, nothing rendered")
        return

    hidden = [o for o in scene.objects if o.name.startswith(("HAT.", "STITCH.")) and not o.hide_render]
    keep = {
        "camera": scene.camera, "engine": scene.render.engine, "samples": scene.cycles.samples,
        "res": (scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage),
        "transparent": scene.render.film_transparent, "format": scene.render.image_settings.file_format,
        "mode": scene.render.image_settings.color_mode, "frame": scene.frame_current,
    }
    cam_data = bpy.data.cameras.new("CAM.brand")
    cam = bpy.data.objects.new("CAM.brand", cam_data)
    scene.collection.objects.link(cam)
    try:
        scene.frame_set(1)
        for o in hidden:
            o.hide_render = True
        scene.render.engine = "CYCLES"
        scene.cycles.samples = SAMPLES
        scene.cycles.use_denoising = True
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"

        mw = logo.matrix_world
        me = logo.data
        all_pts = [mw @ Vector(c) for c in logo.bound_box]
        ring_v = set()
        for poly in me.polygons:
            if poly.material_index == 1:
                ring_v.update(poly.vertices)
        if not ring_v:
            raise RuntimeError(f"{SCRIPT}: LOGO.stone has no ring faces in material slot 1")
        ring_pts = [mw @ me.vertices[i].co for i in ring_v]

        lo, hi = bounds(all_pts)
        height = int(round(WORDMARK_WIDTH * (hi.z - lo.z) / (hi.x - lo.x)))
        p1 = os.path.join(work, "renders", "wordmark stone.png")
        t1 = render_subject(scene, cam, lo, hi, WORDMARK_WIDTH, height, p1)

        rlo, rhi = bounds(ring_pts)
        # hide the letters for the icon: render only the ring by cropping tightly to its bounds
        p2 = os.path.join(work, "renders", "favicon stone O.png")
        t2 = render_subject(scene, cam, rlo, rhi, ICON_SIZE, ICON_SIZE, p2)

        print(f"==== {SCRIPT} runtime report ====")
        print(f"  wordmark {WORDMARK_WIDTH}x{height}, {t1:.0f} s -> {p1}")
        print(f"  icon {ICON_SIZE}x{ICON_SIZE}, {t2:.0f} s -> {p2}")
        print("=================================")
    finally:
        for o in hidden:
            o.hide_render = False
        bpy.data.objects.remove(cam)
        bpy.data.cameras.remove(cam_data)
        scene.camera = keep["camera"]
        scene.render.engine = keep["engine"]
        scene.cycles.samples = keep["samples"]
        scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = keep["res"]
        scene.render.film_transparent = keep["transparent"]
        scene.render.image_settings.file_format = keep["format"]
        scene.render.image_settings.color_mode = keep["mode"]
        scene.frame_set(keep["frame"])


main()
