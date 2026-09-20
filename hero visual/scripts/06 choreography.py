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
from mathutils import Vector, Euler, Matrix
from bpy_extras.object_utils import world_to_camera_view

SCRIPT = "06 choreography"

HATS = ["socials", "content", "website", "branding"]     # flight order

# ---------------------------------------------------------------- timing
FPS = 24
INTRO_HOLD = 8
FLIGHT = 40           # moving frames per hat: lift, climb, descent (the apex hold is extra)
APEX_HOLD = 6         # frames the hat hangs square at the apex: a quarter second, a noticeable beat and no more
LAUNCH_EVERY = 18 + APEX_HOLD   # hat N+1 launches as hat N leaves its apex hold and starts to descend
APEX_BOB = 0.008      # metres of gentle float during the hold so it never looks frozen
REVEAL = 16           # founder light ramp after the last absorption
DISSOLVE_FRAMES = 7
APEX_AT = 0.45        # fraction of the flight where the apex sits
SEPARATE_AT = 0.20    # fraction of the flight spent lifting clear of the stack, tilting forward
LIFT_TILT_DEG = 22.0  # forward tilt reached by the end of the lift
SEPARATE_LIFT = Vector((0.25, -0.90, 0.16))  # up, well forward, a little right: enough to cancel the perspective drift, no more

# ---------------------------------------------------------------- the arc
# the apex is placed by where it lands on screen and how near the camera it comes, so the
# hat reads large: at APEX_CLOSENESS 3 it sits a third of the stack's camera distance away,
# which makes it about three times bigger on screen than it is in the stack
APEX_SCREEN = (0.15, 0.56)   # frame fractions, x from the left, y from the bottom: above the stack, left of the O
APEX_CLOSENESS = 2.5         # launch to camera distance divided by this is the apex to camera distance
# the hat never covers the O on screen: on every frame its projected right edge is held
# left of the ring's left edge by this margin (frame fraction), shifting the hat left if needed
O_EDGE_MARGIN = 0.008
# the ring's reaction: a faint ripple running out from the contact point across the stone
RIPPLE_FRAMES = 14
RIPPLE_REACH = 0.45          # metres the ripple front travels, a little more than the ring's diameter
RIPPLE_WIDTH = 0.035         # metres, thickness of the ripple band
RIPPLE_EMISSION = 0.30       # faint warm glow in the band, just visible
RIPPLE_HEIGHT = 0.0012       # metres of real displacement in the band
O_RADIUS_HINT = 0.20                        # outer radius of the ring from 04
ENTRY_GAP = 0.03                            # metres the hat's centre sits in front of the ring's front face at contact
APEX_SCALE = 1.0      # size comes from being nearer the camera, not from scaling
CONTACT_SCALE = 0.40                        # hat width 0.28 m times this is about 28 percent of the O, so it fits the ring's stroke
APEX_TILT_DEG = 7.0
APEX_LIGHT_OFFSET = Vector((-1.3, -0.5, 1.5))   # metres from the apex: high, to the left, a little toward the camera, so the crown shades
APEX_LIGHT_SPREAD_DEG = 35.0                     # narrow enough that the stack and logo stay as lit in the still
APEX_LIGHT_GAIN = 0.10      # black fabric near the lens needs far less than the inverse square of the key suggests: a tenth keeps it black with the word readable
LATERAL_JITTER = (0.00, 0.03, -0.02, 0.04)  # metres, per hat, same path not identical path
APEX_HEIGHT_JITTER = (0.00, -0.03, 0.04, -0.02)

# spin on the climb: the hat tumbles as soon as it leaves the stack and unwinds to
# square on at the apex, where the word gets its read. (turns X, turns Z)
# One steady forward roll from lift off to apex, at constant pace, completing whole
# turns so the hat lands square for the read. (turns X, turns Z)
CLIMB_SPIN = {
    "socials":  (1.0, 0.0),
    "content":  (1.0, 0.0),
    "website":  (1.0, 0.0),
    "branding": (1.0, 0.0),
}

# rotation on the descent, per the handbook table: (turns X, turns Y, turns Z, wobble amplitude deg)
ROTATION = {
    "socials":  (1.25, 0.0, 0.0, 6.0),      # forward tumble, brim leads, light Y sway
    "content":  (0.0, 0.0, 1.75, 3.0),      # flat frisbee spin, slight drift
    "website":  (1.0, 0.0, 1.0, 10.0),      # corkscrew, pronounced irregular wobble
    "branding": (0.0, 0.0, 0.5, 1.0),       # lazy and heavy
}

FOUNDER_LIGHT_ENERGY = 260.0
PULSE_ENERGY = 45.0

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


def add_ripple(mat, origin):
    """Faint expanding band of glow and displacement, driven by the object property 'ripple' (0 to 1)."""
    nt = mat.node_tree
    if nt is None:
        return False
    out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output), None)
    if out is None or not out.inputs["Surface"].is_linked:
        return False
    if nt.nodes.get("Ripple band") is not None:
        # rebuild so a moved contact point is picked up: restore the original links, drop the ripple nodes
        add_node = nt.nodes.get("Ripple add")
        if add_node is not None and add_node.inputs[0].is_linked:
            nt.links.new(add_node.inputs[0].links[0].from_socket, out.inputs["Surface"])
        height = nt.nodes.get("Ripple height")
        disp0 = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeDisplacement" and not n.name.startswith("Ripple ")), None)
        if height is not None and disp0 is not None and height.inputs[0].is_linked:
            nt.links.new(height.inputs[0].links[0].from_socket, disp0.inputs["Height"])
        for n in [n for n in nt.nodes if n.name.startswith("Ripple ")]:
            nt.nodes.remove(n)
    x0, y0 = out.location.x - 1400, out.location.y - 900

    def mk(kind, name, loc, **kw):
        n = nt.nodes.new(kind)
        n.name = n.label = name
        n.location = loc
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def math(op, a, b, name, loc):
        n = mk("ShaderNodeMath", name, loc, operation=op)
        for i, val in enumerate((a, b)):
            if isinstance(val, (int, float)):
                n.inputs[i].default_value = val
            else:
                nt.links.new(val, n.inputs[i])
        return n.outputs[0]

    geo = mk("ShaderNodeNewGeometry", "Ripple geometry", (x0, y0))
    org = mk("ShaderNodeCombineXYZ", "Ripple origin", (x0, y0 - 200))
    org.inputs[0].default_value, org.inputs[1].default_value, org.inputs[2].default_value = origin.x, origin.y, origin.z
    dist = mk("ShaderNodeVectorMath", "Ripple distance", (x0 + 200, y0), operation="DISTANCE")
    nt.links.new(geo.outputs["Position"], dist.inputs[0])
    nt.links.new(org.outputs["Vector"], dist.inputs[1])
    attr = mk("ShaderNodeAttribute", "Ripple attribute", (x0, y0 - 400), attribute_type="OBJECT", attribute_name="ripple")
    t = attr.outputs["Fac"]
    front = math("MULTIPLY", t, RIPPLE_REACH, "Ripple front", (x0 + 200, y0 - 400))
    off = math("SUBTRACT", dist.outputs["Value"], front, "Ripple offset", (x0 + 400, y0 - 200))
    off = math("DIVIDE", off, RIPPLE_WIDTH, "Ripple offset scaled", (x0 + 600, y0 - 200))
    sq = math("MULTIPLY", off, off, "Ripple square", (x0 + 800, y0 - 200))
    neg = math("MULTIPLY", sq, -1.0, "Ripple negate", (x0 + 1000, y0 - 200))
    band = math("EXPONENT", neg, 0.0, "Ripple gauss", (x0 + 1200, y0 - 200))
    gate = math("MINIMUM", math("MULTIPLY", t, 25.0, "Ripple gate raw", (x0 + 200, y0 - 600)), 1.0, "Ripple gate", (x0 + 400, y0 - 600))
    fade = math("SUBTRACT", 1.0, t, "Ripple fade", (x0 + 400, y0 - 800))
    amp = math("MULTIPLY", gate, fade, "Ripple amplitude", (x0 + 600, y0 - 700))
    band = math("MULTIPLY", band, amp, "Ripple band", (x0 + 1400, y0 - 400))

    # glow: add an emission to whatever the surface was
    src = out.inputs["Surface"].links[0].from_socket
    emis = mk("ShaderNodeEmission", "Ripple emission", (out.location.x - 500, out.location.y - 300))
    emis.inputs["Color"].default_value = (1.0, 0.90, 0.78, 1.0)
    nt.links.new(math("MULTIPLY", band, RIPPLE_EMISSION, "Ripple glow", (x0 + 1600, y0 - 400)), emis.inputs["Strength"])
    add = mk("ShaderNodeAddShader", "Ripple add", (out.location.x - 250, out.location.y - 100))
    nt.links.new(src, add.inputs[0])
    nt.links.new(emis.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])

    # bump: add to the existing displacement height, or make one if the material has none
    disp = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeDisplacement"), None)
    lift = math("MULTIPLY", band, RIPPLE_HEIGHT, "Ripple lift", (x0 + 1600, y0 - 600))
    if disp is None:
        disp = mk("ShaderNodeDisplacement", "Ripple displacement", (out.location.x - 250, out.location.y - 500))
        disp.inputs["Midlevel"].default_value = 0.0
        nt.links.new(lift, disp.inputs["Height"])
        nt.links.new(disp.outputs["Displacement"], out.inputs["Displacement"])
    elif disp.inputs["Height"].is_linked:
        prev = disp.inputs["Height"].links[0].from_socket
        nt.links.new(math("ADD", prev, lift, "Ripple height", (disp.location.x - 200, disp.location.y - 200)), disp.inputs["Height"])
    else:
        nt.links.new(lift, disp.inputs["Height"])
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
def apex_for(launch_pos, cam, scene):
    """World position of the apex: the camera ray through APEX_SCREEN, at a fraction of the launch distance."""
    cam_pos = cam.matrix_world.translation
    depth = (launch_pos - cam_pos).length / APEX_CLOSENESS
    aspect = scene.render.resolution_x / scene.render.resolution_y
    half_w = cam.data.sensor_width / cam.data.lens / 2.0     # half frame width at unit depth, sensor fit on the wide side
    if aspect < 1.0:
        half_w *= aspect
    x = (APEX_SCREEN[0] - 0.5) * 2.0 * half_w
    y = (APEX_SCREEN[1] - 0.5) * 2.0 * half_w / aspect
    local = Vector((x, y, -1.0)) * depth
    return cam.matrix_world @ local


def right_edge_ndc(hat, pos, rot, scale, cam, scene):
    """Projected right edge (frame fraction) of the hat's bounding box at this pose, and its depth."""
    m = Matrix.Translation(pos) @ rot.to_matrix().to_4x4() @ Matrix.Diagonal((scale, scale, scale, 1.0))
    best, depth = -1e9, None
    for corner in hat.bound_box:
        v = world_to_camera_view(scene, cam, m @ Vector(corner))
        if v.x > best:
            best, depth = v.x, v.z
    return best, depth


def keep_left_of_o(hat, pos, rot, scale, cam, scene, limit):
    """Shift the hat left along the camera's x axis until its right edge sits at or left of `limit`."""
    aspect = scene.render.resolution_x / scene.render.resolution_y
    half_w = cam.data.sensor_width / cam.data.lens / 2.0 * (aspect if aspect < 1.0 else 1.0)
    cam_x = cam.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0))
    for _ in range(3):
        edge, depth = right_edge_ndc(hat, pos, rot, scale, cam, scene)
        excess = edge - limit
        if excess <= 0.0:
            break
        pos = pos - cam_x * (excess * 2.0 * half_w * depth)
    return pos


def flight_keys(hat, index, launch_pos, entry, cam, base_yaw, o_limit):
    """Keyframe one hat's flight starting at frame `start`."""
    start = INTRO_HOLD + index * LAUNCH_EVERY
    end = start + FLIGHT + APEX_HOLD
    apex_frame = int(round(FLIGHT * APEX_AT))
    apex = apex_for(launch_pos, cam, bpy.context.scene) + Vector((LATERAL_JITTER[index], 0.0, APEX_HEIGHT_JITTER[index]))
    key = hat.name.split(".")[-1]
    turns_x, turns_y, turns_z, wobble = ROTATION[key]
    objs = family(hat)
    for ob in objs:
        ob["dissolve"] = 0.0
    tilt = math.radians(APEX_TILT_DEG * (1.0 if index % 2 == 0 else -1.0))

    for f in range(start, end + 1):
        rel = f - start
        # the hold sits between climb and descent; time before it and after it is measured on the moving clock
        holding = apex_frame < rel <= apex_frame + APEX_HOLD
        t = rel / FLIGHT if rel <= apex_frame else (rel - APEX_HOLD) / FLIGHT
        clear_pos = launch_pos + SEPARATE_LIFT
        if holding:
            # apex hold: square on, level, a slow float so the word gets its read
            h = (rel - apex_frame) / APEX_HOLD
            cx, cz = CLIMB_SPIN[key]
            pos = apex + Vector((0.0, 0.0, APEX_BOB * math.sin(h * math.pi)))
            scale = APEX_SCALE
            rot = Euler((tilt + cx * 2.0 * math.pi, 0.0, cz * 2.0 * math.pi), "XYZ")
            dissolve = 0.0
        elif t <= SEPARATE_AT:
            # separation: lift straight off the stack, no rotation, until fully clear
            u = t / SEPARATE_AT
            # height comes first so nothing below is touched, forward motion follows
            rise = 1.0 - (1.0 - u) ** 2
            fwd = u ** 1.6
            pos = launch_pos + Vector((SEPARATE_LIFT.x * fwd, SEPARATE_LIFT.y * fwd, SEPARATE_LIFT.z * rise))
            scale = 1.0
            # the roll begins as it lifts, at the same steady pace it keeps to the apex
            cx, cz = CLIMB_SPIN[key]
            progress = t / APEX_AT                       # 0 at launch, 1 at the apex
            rot = Euler((cx * 2.0 * math.pi * progress, 0.0, base_yaw), "XYZ")
            dissolve = 0.0
        elif t <= APEX_AT:
            u = (t - SEPARATE_AT) / (APEX_AT - SEPARATE_AT)
            # climb: clear point to apex, gentle curve toward camera
            c1 = clear_pos + (apex - clear_pos) * 0.25 + Vector((0.0, 0.0, 0.15))
            c2 = apex + (clear_pos - apex) * 0.25 + Vector((0.0, 0.0, 0.05))
            pos = bezier(clear_pos, c1, c2, apex, smoothstep(u))
            scale = 1.0 + (APEX_SCALE - 1.0) * smoothstep(u)
            # spin starts now, and unwinds to zero at the apex so the hat settles square
            cx, cz = CLIMB_SPIN[key]
            # constant pace, eased only over the final few frames so it settles rather than stops dead
            progress = t / APEX_AT
            settle = 1.0 - (1.0 - u) ** 3 if u > 0.75 else None
            angle = cx * 2.0 * math.pi * progress
            if settle is not None:
                target = cx * 2.0 * math.pi
                angle = angle + (target - angle) * ((u - 0.75) / 0.25) ** 2
            rot = Euler((tilt * smoothstep(u) + angle,
                         0.0,
                         base_yaw * (1.0 - smoothstep(u)) + cz * 2.0 * math.pi * progress), "XYZ")
            dissolve = 0.0
        else:
            u = (t - APEX_AT) / (1.0 - APEX_AT)
            c1 = apex + (entry - apex) * 0.30 + Vector((0.0, 0.0, 0.04))
            c2 = entry + (apex - entry) * 0.30                                # falls away to the O's left side, never across it
            pos = bezier(apex, c1, c2, entry, smoothstep(u))
            # shrink hard, most of it in the middle of the descent
            scale = APEX_SCALE + (CONTACT_SCALE - APEX_SCALE) * ease_in(u, 1.4)
            spin = u ** 1.25                                     # spins out of the hold straight away, only a touch of ease
            wob = math.radians(wobble) * math.sin(u * math.pi * 3.0) * (1.0 - u)
            cx, cz = CLIMB_SPIN[key]                             # carry the climb's whole turns so no frame jumps
            rot = Euler((tilt + (cx + turns_x * spin) * 2.0 * math.pi + wob,
                         turns_y * 2.0 * math.pi * spin + wob * 0.5,
                         (cz + turns_z * spin) * 2.0 * math.pi), "XYZ")
            dissolve = smoothstep((f - (end - DISSOLVE_FRAMES)) / (DISSOLVE_FRAMES - 1)) if f > end - DISSOLVE_FRAMES else 0.0
        pos = keep_left_of_o(hat, pos, rot, scale, cam, bpy.context.scene, o_limit)
        hat.location = pos
        hat.rotation_euler = rot
        hat.scale = (scale, scale, scale)
        hat.keyframe_insert("location", frame=f)
        hat.keyframe_insert("rotation_euler", frame=f)
        hat.keyframe_insert("scale", frame=f)
        for ob in objs:
            ob["dissolve"] = dissolve
            ob.keyframe_insert('["dissolve"]', frame=f)
    # after the flight the hat is gone for good: fully dissolved, then hidden from
    # render so four transparent caps never stack up at the entry point
    for ob in objs:
        ob["dissolve"] = 1.0
        ob.keyframe_insert('["dissolve"]', frame=end + 1)
        ob.hide_render = False
        ob.keyframe_insert("hide_render", frame=1)
        ob.keyframe_insert("hide_render", frame=end)
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=end + 1)
        ob.hide_render = False
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

    # the ring's real extent, from its faces (material slot 1 is the ring): the hat's contact
    # point is the outer left side of the O, and its screen edge is the line no hat may cross
    mw = logo.matrix_world
    ring_verts = set()
    for poly in logo.data.polygons:
        if poly.material_index == 1:
            ring_verts.update(poly.vertices)
    if not ring_verts:
        raise RuntimeError(f"{SCRIPT}: LOGO.stone has no faces in material slot 1 (the ring). Run 04 first.")
    ring_pts = [mw @ logo.data.vertices[i].co for i in ring_verts]
    ring_min_x = min(v.x for v in ring_pts)
    ring_front_y = min(v.y for v in ring_pts)
    ring_z = (min(v.z for v in ring_pts) + max(v.z for v in ring_pts)) * 0.5
    o_left_ndc = max(world_to_camera_view(scene, cam, v).x for v in ring_pts if v.x < ring_min_x + 0.005)
    o_limit = o_left_ndc - O_EDGE_MARGIN
    hat_half_w = hats[0].dimensions.x * 0.5 * CONTACT_SCALE
    contact = Vector((ring_min_x, ring_front_y, ring_z))                 # where the ripple starts
    entry = Vector((ring_min_x - hat_half_w, ring_front_y - ENTRY_GAP, ring_z))

    # rest state and stack positions come from 05. Frame 1 always holds the stack, whether
    # or not an earlier run left animation behind, so read it there and not on whatever
    # frame the file was last saved on
    scene.frame_set(1)
    rest = {h: (h.location.copy(), h.rotation_euler.copy(), h.scale.copy()) for h in hats}
    for h in hats:
        clear_animation(h)
        for c in family(h):
            clear_animation(c)
    clear_animation(founder_light)
    for ob in family(founder):
        ob["dissolve"] = 0.0

    scene.cycles.transparent_max_bounces = 32
    scene.frame_start = 1
    total = INTRO_HOLD + (len(HATS) - 1) * LAUNCH_EVERY + FLIGHT + APEX_HOLD + REVEAL
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
        s, e = flight_keys(h, i, loc.copy(), entry, cam, rot.z, o_limit)
        windows.append((h.name, s, e))

    # stone reaction: a warm light pulse in the crevices at each contact
    pulse = bpy.data.objects.get("LIGHT.absorb")
    if pulse is None:
        data = bpy.data.lights.new("LIGHT.absorb", "POINT")
        pulse = bpy.data.objects.new("LIGHT.absorb", data)
        (bpy.data.collections.get("Camera and Lights") or scene.collection).objects.link(pulse)
    pulse.data.color = (1.0, 0.92, 0.80)
    pulse.data.shadow_soft_size = 0.03
    pulse.location = contact + Vector((-0.02, -0.03, 0.0))   # just in front of the ring's left side
    clear_animation(pulse)
    pulse.data.animation_data_clear()
    pulse.data.energy = 0.0
    pulse.data.keyframe_insert("energy", frame=1)
    for _, s, e in windows:
        for f, v in ((e - 4, 0.0), (e - 1, PULSE_ENERGY), (e + 6, 0.0)):
            pulse.data.energy = v
            pulse.data.keyframe_insert("energy", frame=f)

    # the apex light: the flying hat comes far nearer the camera than the key light reaches,
    # so a soft area light covers the apex. Its power is scaled from the key by inverse square
    # so the hat is lit as it is in the stack, and its spread is narrowed so the rest of the
    # scene stays as the approved still
    key_light = require("LIGHT.key")
    apex_ref = apex_for(rest[hats[0]][0].copy(), cam, scene)
    key_dist = (key_light.matrix_world.translation - rest[hats[0]][0]).length
    apex_light = bpy.data.objects.get("LIGHT.apex")
    if apex_light is None:
        data = bpy.data.lights.new("LIGHT.apex", "AREA")
        apex_light = bpy.data.objects.new("LIGHT.apex", data)
        (bpy.data.collections.get("Camera and Lights") or scene.collection).objects.link(apex_light)
    apex_light.data.shape = "SQUARE"
    apex_light.data.size = 1.2
    apex_light.data.spread = math.radians(APEX_LIGHT_SPREAD_DEG)
    apex_light.data.color = key_light.data.color
    apex_light.location = apex_ref + APEX_LIGHT_OFFSET
    look_at(apex_light, apex_ref)
    apex_dist = (apex_light.location - apex_ref).length
    apex_light.data.energy = key_light.data.energy * (apex_dist / key_dist) ** 2 * APEX_LIGHT_GAIN
    apex_light.hide_render = False

    # no depth of field in the animation: the frames are scrubbed and paused anywhere on the
    # site, so hat, stack and logo all stay sharp at once. A soft logo on a paused frame reads
    # as a bad image, not as an effect. The still from 05 keeps its own setting if rendered alone.
    cam.data.animation_data_clear()
    cam.data.dof.use_dof = False

    # the ring's ripple: a faint band of glow and real displacement runs out from the contact
    # point over RIPPLE_FRAMES after each hat is taken in
    ring_mat = bpy.data.materials.get("MAT.stone ring")
    if ring_mat is None:
        raise RuntimeError(f"{SCRIPT}: material 'MAT.stone ring' is missing. Run 04 first.")
    add_ripple(ring_mat, contact)
    logo["ripple"] = 0.0
    if logo.animation_data:
        for fc in list(logo.animation_data.action.fcurves) if logo.animation_data.action and hasattr(logo.animation_data.action, "fcurves") else []:
            if fc.data_path == '["ripple"]':
                logo.animation_data.action.fcurves.remove(fc)
    logo.keyframe_insert('["ripple"]', frame=1)
    for _, s, e in windows:
        for f, v in ((e - 1, 0.0), (e, 0.02), (e + RIPPLE_FRAMES, 1.0), (e + RIPPLE_FRAMES + 1, 0.0)):
            logo["ripple"] = v
            logo.keyframe_insert('["ripple"]', frame=f)
    logo["ripple"] = 0.0

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
                 windows[0][1] + int(FLIGHT * APEX_AT) + APEX_HOLD // 2,
                 windows[1][1] + int(FLIGHT * APEX_AT) + APEX_HOLD // 2,
                 windows[2][1] + APEX_HOLD + int(FLIGHT * 0.8),
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
        print(f"  {name}: launch {s}, apex {s + int(FLIGHT * APEX_AT)}, hold to {s + int(FLIGHT * APEX_AT) + APEX_HOLD}, contact {e}")
    print(f"  contact point on the O's left side: {tuple(round(c, 3) for c in contact)}; hat centre at contact {tuple(round(c, 3) for c in entry)}")
    print(f"  O left edge at {o_left_ndc:.3f} of frame width; hats held left of {o_limit:.3f} on every frame")
    print(f"  ripple: {RIPPLE_FRAMES} frames, reach {RIPPLE_REACH} m, glow {RIPPLE_EMISSION}, lift {RIPPLE_HEIGHT * 1000:.1f} mm")
    print(f"  apex scale {APEX_SCALE}, contact scale {CONTACT_SCALE}: hat width at contact {0.28 * CONTACT_SCALE:.3f} m vs O diameter 0.200 m")
    print(f"  dissolve added to materials: {touched or 'already present'}")
    print(f"  founder light ramps {last_end} to {last_end + REVEAL}, {FOUNDER_LIGHT_ENERGY:.0f} W")
    for f, path, dt in renders:
        print(f"  key frame {f}: {dt:.1f} s -> {path}")
    print("=================================")


main()
