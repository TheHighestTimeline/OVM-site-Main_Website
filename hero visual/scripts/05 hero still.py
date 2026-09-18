"""05 hero still.py

OVM Hat Hero, phase one, step 1E. The poster frame.

Builds the five hats as linked duplicates of HAT.base (one mesh, five
objects), each carrying its own STITCH.seam.<name> instance and its
STITCH.letters.<name> word, stacked on the left of frame. Moves LOGO.stone
front and centre right, large. Sets CAM.hero, relights for a dark
background with a real rim on everything, adds LIGHT.founder (off until
phase two). Flat transparent background. Renders at full quality, 1400 px.

Idempotent. Rebuilds the five hats and their stitch instances by name and
re-parents the lettering.
"""
import bpy
import math
import os
import random
import time
from mathutils import Vector

SCRIPT = "05 hero still"

HATS = ["socials", "content", "website", "branding", "founder"]   # top to bottom

# ---------------------------------------------------------------- parameters
STACK_X = -0.80
STACK_Y = 0.05
STACK_BASE_Z = 0.0
STACK_SPACING = 0.104          # floating, with air between the hats
STACK_YAW_JITTER = 6.0         # degrees, deterministic per hat
STACK_XY_JITTER = 0.012        # metres
LOGO_LOCATION = Vector((-0.02, -0.35, 0.28))  # centre of the O, nearer the camera than the hats
CAMERA_LOCATION = Vector((-0.15, -4.60, 0.46))
CAMERA_TARGET = Vector((-0.15, -0.10, 0.25))
CAMERA_FSTOP = 5.6
FULL_WIDTH = 1400
FULL_HEIGHT = 800
FULL_SAMPLES = 256
SKIP_RENDERS = os.environ.get("HATHERO_SKIP_RENDERS") == "1"
FULL_RENDER = os.environ.get("HATHERO_SKIP_FULL_RENDER") != "1"


# ------------------------------------------------------------ shared helpers
def workdir():
    candidates = []
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    try:
        text = bpy.context.space_data.text
        if text and text.filepath:
            candidates.append(os.path.dirname(bpy.path.abspath(text.filepath)))
    except Exception:
        pass
    if bpy.data.filepath:
        candidates.append(os.path.dirname(bpy.data.filepath))
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


def require_material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        raise RuntimeError(f"{SCRIPT}: required material '{name}' is missing. Run 02 fabric and seams first.")
    return mat


def remove_object(name):
    ob = bpy.data.objects.get(name)
    if ob is None:
        return
    bpy.data.objects.remove(ob, do_unlink=True)


def collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    return col


def link(ob, col):
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    col.objects.link(ob)


def look_at(ob, target):
    direction = Vector(target) - ob.location
    ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def copy_modifiers(src, dst):
    dst.modifiers.clear()
    for m in src.modifiers:
        n = dst.modifiers.new(m.name, m.type)
        for prop in m.bl_rna.properties:
            if prop.is_readonly or prop.identifier in ("rna_type", "name", "type"):
                continue
            try:
                setattr(n, prop.identifier, getattr(m, prop.identifier))
            except Exception:
                pass


def world_bbox(objects):
    pts = [ob.matrix_world @ Vector(c) for ob in objects for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def fmt_v(v):
    return f"({v.x:.3f}, {v.y:.3f}, {v.z:.3f})"


# ------------------------------------------------------------------- build
def build_stack(base, seam_master, hats_col):
    rng = random.Random(2026)
    bone = require_material("MAT.thread bone")
    gold = require_material("MAT.thread gold")
    hats = []
    for i, key in enumerate(HATS):
        level = len(HATS) - 1 - i          # founder at the bottom, socials on top
        name = f"HAT.{key}"
        remove_object(name)
        remove_object(f"STITCH.seam.{key}")
        hat = bpy.data.objects.new(name, base.data)   # linked duplicate, shared mesh
        link(hat, hats_col)
        copy_modifiers(base, hat)
        yaw = math.radians(rng.uniform(-STACK_YAW_JITTER, STACK_YAW_JITTER))
        if key == "founder":
            yaw = math.radians(2.0)        # the founder hat sits square
        hat.location = Vector((STACK_X + rng.uniform(-STACK_XY_JITTER, STACK_XY_JITTER),
                               STACK_Y + rng.uniform(-STACK_XY_JITTER, STACK_XY_JITTER),
                               STACK_BASE_Z + level * STACK_SPACING))
        hat.rotation_euler = (0.0, 0.0, yaw)

        seam = bpy.data.objects.new(f"STITCH.seam.{key}", seam_master.data)
        link(seam, hats_col)
        seam.parent = hat
        if key == "founder":
            seam.material_slots[0].link = "OBJECT"
            seam.material_slots[0].material = gold
        else:
            seam.material_slots[0].link = "DATA"

        letters = require(f"STITCH.letters.{key}")
        letters.parent = hat
        letters.matrix_parent_inverse.identity()
        letters.location = (0.0, 0.0, 0.0)
        letters.rotation_euler = (0.0, 0.0, 0.0)
        letters.hide_render = False
        letters.hide_viewport = False
        link(letters, hats_col)
        hats.append(hat)
    return hats


def hide_masters(base, seam_master):
    masters = collection("Masters")
    link(base, masters)
    link(seam_master, masters)
    masters.hide_render = True
    masters.hide_viewport = True


def place_logo(logo):
    logo.location = LOGO_LOCATION
    logo.rotation_euler = (0.0, 0.0, 0.0)


def set_camera(cam):
    cam.location = CAMERA_LOCATION
    look_at(cam, CAMERA_TARGET)
    cam.data.lens = 85.0
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = CAMERA_FSTOP
    cam.data.dof.focus_distance = (CAMERA_TARGET - cam.location).length
    bpy.context.scene.camera = cam


def relight(rig_col, hats, logo):
    lo, hi = world_bbox(hats + [logo])
    centre = (lo + hi) / 2.0
    key = require("LIGHT.key")
    fill = require("LIGHT.fill")
    rim = require("LIGHT.rim")
    # key, high front left, warm white, soft
    key.location = centre + Vector((-2.2, -2.6, 2.4))
    look_at(key, centre)
    key.data.size = 1.6
    key.data.energy = 170.0
    key.data.color = (1.0, 0.98, 0.95)
    # fill, low front right, cool, very soft and weak
    fill.location = centre + Vector((2.6, -2.4, 0.3))
    look_at(fill, centre)
    fill.data.size = 3.0
    fill.data.energy = 22.0
    fill.data.color = (0.90, 0.94, 1.0)
    # rim, a long strip behind and above, the thing that separates black from black
    rim.location = centre + Vector((0.6, 2.2, 1.9))
    look_at(rim, centre + Vector((0.0, 0.0, 0.1)))
    rim.data.shape = "RECTANGLE"
    rim.data.size = 3.6
    rim.data.size_y = 0.35
    rim.data.energy = 1100.0
    rim.data.color = (1.0, 1.0, 1.0)
    # founder light, a warm spot on the bottom hat, off for the still
    remove_object("LIGHT.founder")
    data = bpy.data.lights.new("LIGHT.founder", "SPOT")
    data.energy = 0.0
    data.spot_size = math.radians(28.0)
    data.spot_blend = 0.6
    data.color = (1.0, 0.90, 0.72)
    data.shadow_soft_size = 0.25
    founder_light = bpy.data.objects.new("LIGHT.founder", data)
    link(founder_light, rig_col)
    founder = require("HAT.founder")
    target = founder.matrix_world @ Vector((0.0, -0.12, 0.08))
    founder_light.location = target + Vector((-0.9, -1.6, 1.1))
    look_at(founder_light, target)
    founder_light.hide_render = True
    return key, fill, rim, founder_light


def main():
    global WORK
    WORK = workdir()
    scene = bpy.context.scene
    print(f"\n[{SCRIPT}] working folder: {WORK}")
    base = require("HAT.base")
    seam_master = require("STITCH.seam")
    logo = require("LOGO.stone")
    cam = require("CAM.hero")
    hats_col = collection("Hats")
    rig_col = collection("Camera and Lights")

    hats = build_stack(base, seam_master, hats_col)
    hide_masters(base, seam_master)
    place_logo(logo)
    set_camera(cam)
    bpy.context.view_layer.update()      # fresh bounding boxes for the new objects
    key, fill, rim, founder_light = relight(rig_col, hats, logo)
    scene.render.film_transparent = True

    path = os.path.join(WORK, "renders", "05 hero still.png")
    dt = 0.0
    if SKIP_RENDERS or not FULL_RENDER:
        print(f"  full render skipped: {path}")
    else:
        scene.render.resolution_x = FULL_WIDTH
        scene.render.resolution_y = FULL_HEIGHT
        scene.render.resolution_percentage = 100
        scene.cycles.samples = FULL_SAMPLES
        scene.render.filepath = path
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - t0
        print(f"  rendered 05 hero still: {FULL_WIDTH}x{FULL_HEIGHT}, {FULL_SAMPLES} samples, {dt:.1f} s -> {path}")

    lo, hi = world_bbox(hats)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    total_verts = 0
    for ob in scene.objects:
        if ob.type == "MESH" and not ob.hide_render and ob.visible_get():
            me = ob.evaluated_get(depsgraph).to_mesh()
            total_verts += len(me.vertices)
            ob.evaluated_get(depsgraph).to_mesh_clear()
    print("")
    print(f"==== {SCRIPT} runtime report ====")
    print(f"  scene objects: {len(scene.objects)}, evaluated render vertices: {total_verts}")
    print(f"  HAT.base vertices: {len(base.data.vertices)}, shared by {base.data.users} objects")
    for hat in hats:
        print(f"  {hat.name}: location {fmt_v(hat.location)}, yaw {math.degrees(hat.rotation_euler.z):.1f} deg, "
              f"children {[c.name for c in hat.children]}")
    print(f"  stack world bounding box: min {fmt_v(lo)} max {fmt_v(hi)} size {fmt_v(hi - lo)}")
    print(f"  LOGO.stone location {fmt_v(logo.location)}, size {fmt_v(logo.dimensions)}")
    print(f"  CAM.hero location {fmt_v(cam.location)}, lens {cam.data.lens:.0f} mm, f/{cam.data.dof.aperture_fstop:.1f}, focus {cam.data.dof.focus_distance:.2f} m")
    print(f"  lights: key {key.data.energy:.0f} W, fill {fill.data.energy:.0f} W, rim {rim.data.energy:.0f} W, founder {founder_light.data.energy:.0f} W (hidden)")
    print(f"  output: {path} ({dt:.1f} s)")
    print("=================================")


main()
