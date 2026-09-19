"""06 choreography.py

OVM Hat Hero, phase two, the motion.

Keyframes the four role hats along one shared arc: lift off the top of
the stack, forward and up to the apex where the word is square to camera,
then descend right, shrink hard and pass into the left side of the O.
Each hat launches when the one before crosses its apex. Rotation is all
on the descent, per the handbook table. The hat never changes material:
absorption is geometric occlusion plus a short alpha dissolve over the
last frames, with a light pulse in the stone at contact. Once BRANDING is
gone, LIGHT.founder comes up on the founder hat.

Adds a per object "dissolve" property read by the fabric, thread and
eyelet materials through an Attribute node. Zero is opaque.

Idempotent: clears its own keyframes and rebuilds them. Renders six key
frames at 800 px into renders, named after this script.

Runs on the saved hero still scene (05 must have run).
"""
import bpy
import math
import os
import time
from mathutils import Vector, Euler

SCRIPT = "06 choreography"

HATS = ["socials", "content", "website", "branding"]     # flight order

# ---------------------------------------------------------------- timing
FPS = 24
INTRO_HOLD = 8
FLIGHT = 40           # frames per hat
LAUNCH_EVERY = 18     # hat N+1 launches when hat N is near its apex
REVEAL = 16           # founder light ramp after the last absorption
DISSOLVE_FRAMES = 6
APEX_AT = 0.45        # fraction of the flight where the apex sits

# ---------------------------------------------------------------- the arc
APEX_OFFSET = Vector((0.12, -0.70, 0.62))   # from the launch point: right, toward camera, up
ENTRY_INSET = 0.02                          # how far past the O's left edge the hat travels before it is gone
APEX_SCALE = 1.12
CONTACT_SCALE = 0.42                        # hat width 0.28 m times this is about 60 percent of the O's 0.20 m
APEX_TILT_DEG = 7.0
LATERAL_JITTER = (0.00, 0.03, -0.02, 0.04)  # metres, per hat, same path not identical path
APEX_HEIGHT_JITTER = (0.00, -0.03, 0.04, -0.02)

# rotation on the descent, per the handbook table: (turns X, turns Y, turns Z, wobble amplitude deg)
ROTATION = {
    "socials":  (1.25, 0.0, 0.0, 6.0),      # forward tumble, brim leads, light Y sway
    "content":  (0.0, 0.0, 1.75, 3.0),      # flat frisbee spin, slight drift
    "website":  (1.0, 0.0, 1.0, 10.0),      # corkscrew, pronounced irregular wobble
    "branding": (0.0, 0.0, 0.5, 1.0),       # lazy and heavy
}

FOUNDER_LIGHT_ENERGY = 260.0
PULSE_ENERGY = 900.0

KEY_FRAMES_TO_RENDER = 6
PREVIEW_WIDTH = 800
PREVIEW_HEIGHT = 450
PREVIEW_SAMPLES = 64
SKIP_RENDERS = os.environ.get("HATHERO_SKIP_RENDERS") == "1"


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


def look_at(ob, target):
    direction = Vector(target) - ob.location
    ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def ease_in(t, p=2.2):
    return max(0.0, min(1.0, t)) ** p


def bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    return p0 * (u ** 3) + p1 * (3 * u * u * t) + p2 * (3 * u * t * t) + p3 * (t ** 3)


def clear_animation(ob):
    ob.animation_data_clear()


# -------------------------------------------------------------- materials
def add_dissolve(mat):
    """Mix the surface with a Transparent BSDF, driven by the object property 'dissolve'."""
    nt = mat.node_tree
    if nt is None or nt.nodes.get("Dissolve mix") is not None:
        return False
    out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output), None)
    if out is None or not out.inputs["Surface"].is_linked:
        return False
    src = out.inputs["Surface"].links[0].from_socket
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.name = "Dissolve mix"
    mix.location = (out.location.x - 200, out.location.y)
    trans = nt.nodes.new("ShaderNodeBsdfTransparent")
    trans.location = (out.location.x - 450, out.location.y - 200)
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "OBJECT"
    attr.attribute_name = "dissolve"
    attr.location = (out.location.x - 450, out.location.y + 200)
    nt.links.new(src, mix.inputs[1])
    nt.links.new(trans.outputs["BSDF"], mix.inputs[2])
    nt.links.new(attr.outputs["Fac"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    mat.blend_method = "HASHED"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "HASHED"
    return True


def family(hat):
    objs = [hat]
    stack = list(hat.children)
    while stack:
        c = stack.pop()
        objs.append(c)
        stack.extend(c.children)
    return objs


# ------------------------------------------------------------- the flight
def flight_keys(hat, index, launch_pos, entry, cam_pos, base_yaw):
    """Keyframe one hat's flight starting at frame `start`."""
    start = INTRO_HOLD + index * LAUNCH_EVERY
    end = start + FLIGHT
    apex = launch_pos + APEX_OFFSET + Vector((LATERAL_JITTER[index], 0.0, APEX_HEIGHT_JITTER[index]))
    turns_x, turns_y, turns_z, wobble = ROTATION[hat.name.split(".")[-1]]
    objs = family(hat)
    for ob in objs:
        ob["dissolve"] = 0.0
    tilt = math.radians(APEX_TILT_DEG * (1.0 if index % 2 == 0 else -1.0))

    for f in range(start, end + 1):
        t = (f - start) / FLIGHT
        if t <= APEX_AT:
            u = t / APEX_AT
            # climb: launch to apex, gentle curve toward camera
            c1 = launch_pos + Vector((0.0, 0.0, 0.25))
            c2 = apex + Vector((0.0, 0.10, 0.05))
            pos = bezier(launch_pos, c1, c2, apex, smoothstep(u))
            scale = 1.0 + (APEX_SCALE - 1.0) * smoothstep(u)
            rot = Euler((tilt * smoothstep(u), 0.0, base_yaw * (1.0 - smoothstep(u))), "XYZ")
            dissolve = 0.0
        else:
            u = (t - APEX_AT) / (1.0 - APEX_AT)
            c1 = apex + Vector((0.15, -0.05, 0.05))
            c2 = entry + Vector((-0.25, -0.20, 0.15))
            pos = bezier(apex, c1, c2, entry, smoothstep(u))
            # shrink hard, most of it in the middle of the descent
            scale = APEX_SCALE + (CONTACT_SCALE - APEX_SCALE) * ease_in(u, 1.4)
            spin = smoothstep(u)
            wob = math.radians(wobble) * math.sin(u * math.pi * 3.0) * (1.0 - u)
            rot = Euler((tilt + turns_x * 2.0 * math.pi * spin + wob,
                         turns_y * 2.0 * math.pi * spin + wob * 0.5,
                         turns_z * 2.0 * math.pi * spin), "XYZ")
            dissolve = smoothstep((f - (end - DISSOLVE_FRAMES)) / DISSOLVE_FRAMES) if f > end - DISSOLVE_FRAMES else 0.0
        hat.location = pos
        hat.rotation_euler = rot
        hat.scale = (scale, scale, scale)
        hat.keyframe_insert("location", frame=f)
        hat.keyframe_insert("rotation_euler", frame=f)
        hat.keyframe_insert("scale", frame=f)
        for ob in objs:
            ob["dissolve"] = dissolve
            ob.keyframe_insert('["dissolve"]', frame=f)
    # after the flight the hat stays gone
    for ob in objs:
        ob["dissolve"] = 1.0
        ob.keyframe_insert('["dissolve"]', frame=end + 1)
    hat.hide_render = False
    return start, end


def main():
    global WORK
    WORK = workdir()
    scene = bpy.context.scene
    print(f"\n[{SCRIPT}] working folder: {WORK}")
    logo = require("LOGO.stone")
    cam = require("CAM.hero")
    founder = require("HAT.founder")
    founder_light = require("LIGHT.founder")
    hats = [require(f"HAT.{k}") for k in HATS]

    # materials: dissolve mix on everything a hat is made of
    touched = []
    for name in ("MAT.fabric black", "MAT.thread bone", "MAT.thread gold", "MAT.eyelet black"):
        mat = bpy.data.materials.get(name)
        if mat is not None and add_dissolve(mat):
            touched.append(name)

    # the O's left entry point, mid depth of the ring
    o_centre = logo.matrix_world.translation
    ring_depth = logo.dimensions.y
    entry = Vector((o_centre.x - 0.10 - ENTRY_INSET, o_centre.y + ring_depth * 0.5, o_centre.z))

    # rest state and stack positions come from 05
    rest = {h: (h.location.copy(), h.rotation_euler.copy(), h.scale.copy()) for h in hats}
    for h in hats:
        clear_animation(h)
        for c in family(h):
            clear_animation(c)
    clear_animation(founder_light)
    for ob in family(founder):
        ob["dissolve"] = 0.0

    scene.frame_start = 1
    total = INTRO_HOLD + (len(HATS) - 1) * LAUNCH_EVERY + FLIGHT + REVEAL
    scene.frame_end = total
    scene.render.fps = FPS

    windows = []
    for i, h in enumerate(hats):
        loc, rot, scl = rest[h]
        # hold at rest until launch
        h.location, h.rotation_euler, h.scale = loc, rot, scl
        for ob in family(h):
            ob["dissolve"] = 0.0
            ob.keyframe_insert('["dissolve"]', frame=1)
        h.keyframe_insert("location", frame=1)
        h.keyframe_insert("rotation_euler", frame=1)
        h.keyframe_insert("scale", frame=1)
        s, e = flight_keys(h, i, loc.copy(), entry, cam.location, rot.z)
        windows.append((h.name, s, e))

    # stone reaction: a warm light pulse in the crevices at each contact
    pulse = bpy.data.objects.get("LIGHT.absorb")
    if pulse is None:
        data = bpy.data.lights.new("LIGHT.absorb", "POINT")
        pulse = bpy.data.objects.new("LIGHT.absorb", data)
        (bpy.data.collections.get("Camera and Lights") or scene.collection).objects.link(pulse)
    pulse.data.color = (1.0, 0.92, 0.80)
    pulse.data.shadow_soft_size = 0.06
    pulse.location = entry + Vector((0.04, -0.06, 0.0))
    clear_animation(pulse)
    pulse.data.animation_data_clear()
    pulse.data.energy = 0.0
    pulse.data.keyframe_insert("energy", frame=1)
    for _, s, e in windows:
        for f, v in ((e - 4, 0.0), (e - 1, PULSE_ENERGY), (e + 6, 0.0)):
            pulse.data.energy = v
            pulse.data.keyframe_insert("energy", frame=f)

    # the reveal: founder light ramps after the last hat is gone
    last_end = windows[-1][2]
    founder_light.hide_render = False
    founder_light.data.animation_data_clear()
    founder_light.data.energy = 0.0
    founder_light.data.keyframe_insert("energy", frame=last_end)
    founder_light.data.energy = FOUNDER_LIGHT_ENERGY
    founder_light.data.keyframe_insert("energy", frame=last_end + REVEAL)
    target = founder.matrix_world @ Vector((0.0, -0.12, 0.10))
    founder_light.location = target + Vector((-0.9, -1.6, 1.1))
    look_at(founder_light, target)

    # keyframes are inserted per frame, so interpolation between them hardly matters. Blender's default Bezier is fine.

    # key frame renders
    renders = []
    if not SKIP_RENDERS:
        scene.render.resolution_x = PREVIEW_WIDTH
        scene.render.resolution_y = PREVIEW_HEIGHT
        scene.render.resolution_percentage = 100
        scene.cycles.samples = PREVIEW_SAMPLES
        picks = [1,
                 windows[0][1] + int(FLIGHT * APEX_AT),
                 windows[1][1] + int(FLIGHT * APEX_AT),
                 windows[2][1] + int(FLIGHT * 0.8),
                 windows[3][2] - 2,
                 total]
        for f in picks[:KEY_FRAMES_TO_RENDER]:
            scene.frame_set(f)
            path = os.path.join(WORK, "renders", f"06 key frame {f:04d}.png")
            scene.render.filepath = path
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            renders.append((f, path, time.time() - t0))
            print(f"  rendered key frame {f}: {time.time() - t0:.1f} s -> {path}")
        scene.frame_set(1)

    print("")
    print(f"==== {SCRIPT} runtime report ====")
    print(f"  frames: {scene.frame_start} to {scene.frame_end} ({total} total) at {FPS} fps, {total / FPS:.1f} s of scroll")
    for name, s, e in windows:
        print(f"  {name}: launch {s}, apex {s + int(FLIGHT * APEX_AT)}, contact {e}")
    print(f"  entry point (left of O, mid depth): {tuple(round(c, 3) for c in entry)}")
    print(f"  apex scale {APEX_SCALE}, contact scale {CONTACT_SCALE}: hat width at contact {0.28 * CONTACT_SCALE:.3f} m vs O diameter 0.200 m")
    print(f"  dissolve added to materials: {touched or 'already present'}")
    print(f"  founder light ramps {last_end} to {last_end + REVEAL}, {FOUNDER_LIGHT_ENERGY:.0f} W")
    for f, path, dt in renders:
        print(f"  key frame {f}: {dt:.1f} s -> {path}")
    print("=================================")


main()
