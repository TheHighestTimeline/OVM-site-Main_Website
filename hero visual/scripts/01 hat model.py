"""01 hat model.py

OVM Hat Hero, phase one, step 1A.

Builds HAT.base, a structured six panel baseball cap at real world scale,
with a flat grey placeholder material, CAM.hero at 85mm and a basic three
point rig (LIGHT.key, LIGHT.fill, LIGHT.rim). No stitching, no lettering.

Idempotent. Removes and rebuilds every object it owns by name.

Path decision: no downloaded cap is used. The build is fully procedural so
the topology is guaranteed quads, the six panel seams are guaranteed edge
loops (they are generated as such and tagged in the vertex group "seam"),
the front two panels are tagged in the vertex group "front panels", and
there is no licence question on a commercial hero.

Runs inside Blender (Text Editor, Run Script) or through the bpy module.
"""
import bpy
import bmesh
import math
import os
import time
from mathutils import Vector

SCRIPT = "01 hat model"

# ---------------------------------------------------------------- parameters
# All lengths in metres.
CROWN_WIDTH = 0.28          # side to side across the opening, per handbook
CROWN_DEPTH_RATIO = 1.06    # front to back is a little longer than side to side
CROWN_HEIGHT = 0.158
PANELS = 6
# Angular offsets inside one 60 degree panel, in degrees, starting at the seam.
# The tight 2 degree loops either side of the seam are what make the seam
# crease crisp under subdivision.
PANEL_OFFSETS = [0.0, 2.0, 8.0, 15.0, 22.5, 30.0, 37.5, 45.0, 52.0, 58.0]
SEAM_INSET = 0.0016         # seam crease depth
PANEL_BULGE = 0.005         # panel puff between seams, fraction of radius
BACK_SHIFT = 0.032          # the top of the crown sits this far behind the opening centre
BRIM_LENGTH = 0.088         # at the centre front
BRIM_TIP_LENGTH = 0.005     # where the brim runs out at the sides
BRIM_HALF_ANGLE = math.radians(64)
BRIM_ROOT_TILT = math.radians(9)    # the brim leaves the crown angled down
BRIM_DROOP = 0.028          # extra curve down toward the front edge
BRIM_CURL = 0.060           # pre curved brim, the side edges drop this much below the centre line
BRIM_RADIAL_STEPS = 9
FABRIC_THICKNESS = 0.0015
BRIM_THICKNESS = 0.0032
BUTTON_RADIUS = 0.013
EYELET_ZF = 0.70            # eyelet height as a fraction of crown height, one per panel
EYELET_RADIUS = 0.0045
EYELET_THICKNESS = 0.0012

# Crown profile, revolved. (radius as a fraction of half width, z as a
# fraction of crown height). The last entry is the pole.
# A relaxed, rounded dome after the reference cap: smooth from band to
# button, no flat top, the back sloping lower than the front.
PROFILE = [
    (1.000, 0.000), (1.003, 0.100), (0.996, 0.215), (0.978, 0.330),
    (0.948, 0.445), (0.902, 0.555), (0.838, 0.660), (0.752, 0.755),
    (0.645, 0.838), (0.515, 0.905), (0.365, 0.955), (0.200, 0.987),
    (0.080, 0.999), (0.000, 1.000),
]
ANGLES = [math.radians(60.0 * p + o) for p in range(PANELS) for o in PANEL_OFFSETS]
SEGMENTS = len(ANGLES)

CAMERA_LENS = 85.0
PREVIEW_WIDTH = 800
PREVIEW_HEIGHT = 457
PREVIEW_SAMPLES = 64
SKIP_RENDERS = os.environ.get("HATHERO_SKIP_RENDERS") == "1"


# ------------------------------------------------------------ shared helpers
def workdir():
    """Locate the Hat Hero working folder, the one that contains scripts."""
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


def remove_object(name):
    ob = bpy.data.objects.get(name)
    if ob is None:
        return
    data = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Camera):
            bpy.data.cameras.remove(data)
        elif isinstance(data, bpy.types.Light):
            bpy.data.lights.remove(data)


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


def enable_gpu(scene):
    """Use a GPU if Blender exposes one, otherwise CPU. Returns the device type used."""
    scene.render.engine = "CYCLES"
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is None:
        scene.cycles.device = "CPU"
        return "CPU"
    prefs = addon.preferences
    for device_type in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = device_type
        except TypeError:
            continue
        try:
            prefs.get_devices()
        except Exception:
            pass
        gpus = [d for d in prefs.devices if d.type == device_type]
        if gpus:
            for d in prefs.devices:
                d.use = d.type in (device_type, "CPU")
            scene.cycles.device = "GPU"
            return device_type
    scene.cycles.device = "CPU"
    return "CPU"


def configure_scene(scene):
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    device = enable_gpu(scene)
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    return device


def render_preview(scene, name, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT, samples=PREVIEW_SAMPLES):
    """Render to renders/<name>.png and return (path, seconds)."""
    path = os.path.join(WORK, "renders", name + ".png")
    if SKIP_RENDERS:
        print(f"  render skipped (HATHERO_SKIP_RENDERS=1): {path}")
        return path, 0.0
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.cycles.samples = samples
    scene.render.filepath = path
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    dt = time.time() - t0
    print(f"  rendered {name}: {width}x{height}, {samples} samples, {dt:.1f} s -> {path}")
    return path, dt


def world_bbox(objects):
    pts = []
    for ob in objects:
        for corner in ob.bound_box:
            pts.append(ob.matrix_world @ Vector(corner))
    if not pts:
        return None
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def fmt_v(v):
    return f"({v.x:.3f}, {v.y:.3f}, {v.z:.3f})"


# ------------------------------------------------------------------ the cap
def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def build_hat_bmesh():
    """Return (bmesh, groups) where groups maps vertex group name -> list of vertex indices."""
    bm = bmesh.new()
    R = CROWN_WIDTH / 2.0
    seam_step = len(PANEL_OFFSETS)
    groups = {"seam": [], "front panels": [], "brim": [], "brim edge": [], "button": []}

    def ring_point(rf, zf, i):
        phi = ANGLES[i]                               # phi 0 is the centre front (-Y)
        r = rf * R
        # Panels puff between the seams. Zero at each seam, most in the middle
        # of each panel, fading out at the band and at the pole.
        bulge = PANEL_BULGE * (math.sin(PANELS * phi / 2.0) ** 2)
        bulge *= smoothstep(0.05, 0.30, zf) * (1.0 - smoothstep(0.85, 1.0, zf))
        r *= 1.0 + bulge
        if i % seam_step == 0 and zf > 0.05:
            r -= SEAM_INSET * smoothstep(0.05, 0.25, zf) * (1.0 - smoothstep(0.90, 1.0, zf))
        x = r * math.sin(phi)
        y = -r * math.cos(phi) * CROWN_DEPTH_RATIO + BACK_SHIFT * zf ** 1.6
        return Vector((x, y, zf * CROWN_HEIGHT))

    rings = []
    for (rf, zf) in PROFILE[:-1]:
        ring = [bm.verts.new(ring_point(rf, zf, i)) for i in range(SEGMENTS)]
        rings.append(ring)
    pole = bm.verts.new((0.0, BACK_SHIFT, CROWN_HEIGHT))

    for j in range(len(rings) - 1):
        a, b = rings[j], rings[j + 1]
        for i in range(SEGMENTS):
            k = (i + 1) % SEGMENTS
            bm.faces.new((a[i], a[k], b[k], b[i]))
    top = rings[-1]
    for i in range(SEGMENTS):
        k = (i + 1) % SEGMENTS
        bm.faces.new((top[i], top[k], pole))

    # vertex groups on the crown
    for j, (rf, zf) in enumerate(PROFILE[:-1]):
        for i in range(SEGMENTS):
            v = rings[j][i]
            phi = ANGLES[i]
            phi_s = phi if phi <= math.pi else phi - 2.0 * math.pi
            if i % seam_step == 0:
                groups["seam"].append(v)
            if abs(phi_s) < math.radians(60) and 0.12 < zf < 0.92:
                groups["front panels"].append(v)
    groups["seam"].append(pole)

    # brim, grown from the base ring across the front
    base = rings[0]
    root_ids = []
    def signed(i):
        phi = ANGLES[i]
        return phi if phi <= math.pi else phi - 2.0 * math.pi
    for i in range(SEGMENTS):
        if abs(signed(i)) <= BRIM_HALF_ANGLE + 1e-9:
            root_ids.append(i)
    root_ids.sort(key=signed)

    def brim_length(phi_s):
        c = math.cos(phi_s * (math.pi / 2.0) / BRIM_HALF_ANGLE)
        return BRIM_TIP_LENGTH + (BRIM_LENGTH - BRIM_TIP_LENGTH) * max(0.0, c) ** 0.8

    rows = [[base[i] for i in root_ids]]
    for k in range(1, BRIM_RADIAL_STEPS + 1):
        t = k / BRIM_RADIAL_STEPS
        row = []
        for i in root_ids:
            phi_s = signed(i)
            root = base[i].co
            outward = Vector((root.x, root.y, 0.0)).normalized()
            d = t * brim_length(phi_s)
            # lateral position across the brim drives the curl, so the sides bend down
            lateral = abs((root + outward * d).x) / (R + BRIM_LENGTH)
            z = (-d * math.tan(BRIM_ROOT_TILT)
                 - BRIM_DROOP * (d / BRIM_LENGTH) ** 2
                 - BRIM_CURL * lateral ** 2.2 * (d / BRIM_LENGTH) ** 0.6)
            v = bm.verts.new(root + outward * d + Vector((0.0, 0.0, z)))
            row.append(v)
            groups["brim"].append(v)
            if k == BRIM_RADIAL_STEPS:
                groups["brim edge"].append(v)
        rows.append(row)
    for k in range(len(rows) - 1):
        a, b = rows[k], rows[k + 1]
        for i in range(len(a) - 1):
            bm.faces.new((a[i], b[i], b[i + 1], a[i + 1]))

    # top button
    before = set(bm.verts)
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=BUTTON_RADIUS)
    new_verts = [v for v in bm.verts if v not in before]
    for v in new_verts:
        v.co.z *= 0.55
        v.co.z += CROWN_HEIGHT - 0.0025
        v.co.y += BACK_SHIFT
        groups["button"].append(v)

    # eyelets, one per panel, a small grommet ring sitting on the surface
    groups["eyelet"] = []
    eyelet_faces = []
    for p in range(PANELS):
        phi = math.radians(60.0 * p + 30.0)
        # surface point and normal from the analytic profile at EYELET_ZF
        zf = EYELET_ZF
        rf = 0.0
        for (r0, z0), (r1, z1) in zip(PROFILE, PROFILE[1:]):
            if z0 <= zf <= z1:
                rf = r0 + (r1 - r0) * (zf - z0) / (z1 - z0)
                break
        centre = ring_point(rf, zf, 0)
        # rebuild for this angle
        r = rf * R * (1.0 + PANEL_BULGE)
        centre = Vector((r * math.sin(phi), -r * math.cos(phi) * CROWN_DEPTH_RATIO + BACK_SHIFT * zf ** 1.6, zf * CROWN_HEIGHT))
        # approximate normal: outward radial tilted up by the profile slope
        slope = 0.0
        for (r0, z0), (r1, z1) in zip(PROFILE, PROFILE[1:]):
            if z0 <= zf <= z1:
                slope = ((r1 - r0) * R) / ((z1 - z0) * CROWN_HEIGHT)
                break
        radial = Vector((math.sin(phi), -math.cos(phi), 0.0))
        normal = (radial + Vector((0.0, 0.0, -slope))).normalized()
        before = set(bm.faces)
        bmesh.ops.create_cone(bm, cap_ends=False, segments=24,
                              radius1=EYELET_RADIUS, radius2=EYELET_RADIUS,
                              depth=EYELET_THICKNESS)
        new_faces = [f for f in bm.faces if f not in before]
        ring_verts = {v for f in new_faces for v in f.verts}
        # thicken the tube into a grommet: inner wall plus rims
        geom = bmesh.ops.solidify(bm, geom=new_faces, thickness=-EYELET_THICKNESS * 0.9)
        grommet_faces = [f for f in bm.faces if f not in before]
        grommet_verts = {v for f in grommet_faces for v in f.verts}
        rot = normal.to_track_quat("Z", "Y").to_matrix().to_4x4()
        for v in grommet_verts:
            v.co = rot @ v.co + centre + normal * (EYELET_THICKNESS * 0.35)
            groups["eyelet"].append(v)
        eyelet_faces.extend(grommet_faces)
    for f in eyelet_faces:
        f.material_index = 1

    bm.verts.index_update()
    groups = {name: [v.index for v in verts] for name, verts in groups.items()}
    return bm, groups


def build_hat_base(col):
    remove_object("HAT.base")
    old = bpy.data.meshes.get("HAT.base")
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)

    bm, groups = build_hat_bmesh()
    me = bpy.data.meshes.new("HAT.base")
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()

    ob = bpy.data.objects.new("HAT.base", me)
    link(ob, col)
    for name, ids in groups.items():
        vg = ob.vertex_groups.new(name=name)
        if ids:
            vg.add(ids, 1.0, "REPLACE")

    # fabric thickness, brim thicker than the crown
    sol = ob.modifiers.new("Fabric thickness", "SOLIDIFY")
    sol.thickness = BRIM_THICKNESS
    sol.offset = -1.0
    sol.use_even_offset = True
    sol.vertex_group = "brim"
    sol.thickness_vertex_group = FABRIC_THICKNESS / BRIM_THICKNESS
    sub = ob.modifiers.new("Smooth", "SUBSURF")
    sub.levels = 2
    sub.render_levels = 3

    mat = bpy.data.materials.get("MAT.placeholder grey")
    if mat is None:
        mat = bpy.data.materials.new("MAT.placeholder grey")
        if mat.node_tree is None:
            mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.35, 0.35, 0.35, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.6
    if not me.materials:
        me.materials.append(mat)
    metal = bpy.data.materials.get("MAT.eyelet black")
    if metal is None:
        metal = bpy.data.materials.new("MAT.eyelet black")
        if metal.node_tree is None:
            metal.use_nodes = True
        b = metal.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1.0)
        b.inputs["Metallic"].default_value = 0.9
        b.inputs["Roughness"].default_value = 0.28
    if len(me.materials) < 2:
        me.materials.append(metal)
    return ob


# --------------------------------------------------------------- camera, rig
def build_camera(col):
    remove_object("CAM.hero")
    cam_data = bpy.data.cameras.new("CAM.hero")
    cam_data.lens = CAMERA_LENS
    cam_data.sensor_width = 36.0
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 5.6
    cam = bpy.data.objects.new("CAM.hero", cam_data)
    link(cam, col)
    # look dev framing for a single hat: three quarter view, a little above
    cam.location = Vector((0.78, -1.30, 0.42))
    target = Vector((0.0, -0.04, 0.055))
    look_at(cam, target)
    cam_data.dof.focus_distance = (target - cam.location).length
    bpy.context.scene.camera = cam
    return cam


def area_light(name, col, location, target, power, size, size_y=None, color=(1.0, 1.0, 1.0)):
    remove_object(name)
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.shape = "RECTANGLE" if size_y else "SQUARE"
    data.size = size
    if size_y:
        data.size_y = size_y
    data.color = color
    ob = bpy.data.objects.new(name, data)
    link(ob, col)
    ob.location = Vector(location)
    look_at(ob, target)
    return ob


def build_rig(col):
    target = (0.0, 0.0, 0.08)
    key = area_light("LIGHT.key", col, (-0.75, -0.85, 0.95), target, 45.0, 0.7, color=(1.0, 0.98, 0.95))
    fill = area_light("LIGHT.fill", col, (1.3, -1.1, 0.35), target, 10.0, 1.6, color=(0.92, 0.95, 1.0))
    rim = area_light("LIGHT.rim", col, (0.55, 1.15, 0.85), target, 90.0, 0.45, color=(1.0, 1.0, 1.0))
    return key, fill, rim


def clear_startup_objects():
    """Remove Blender's default startup objects if they are still around."""
    for name in ("Cube", "Light", "Camera"):
        ob = bpy.data.objects.get(name)
        if ob is not None:
            print(f"  removing default startup object '{name}'")
            remove_object(name)


def set_world(scene):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.012, 0.012, 0.014, 1.0)
        bg.inputs["Strength"].default_value = 1.0


# ------------------------------------------------------------------- report
def report(scene, hat, cam, device, render_path, render_time):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hat_eval = hat.evaluated_get(depsgraph)
    me_eval = hat_eval.to_mesh()
    eval_verts = len(me_eval.vertices)
    eval_faces = len(me_eval.polygons)
    hat_eval.to_mesh_clear()
    lo, hi = world_bbox([hat])
    size = hi - lo
    quads = sum(1 for p in hat.data.polygons if len(p.vertices) == 4)
    print("")
    print(f"==== {SCRIPT} runtime report ====")
    print(f"  Blender {bpy.app.version_string}, render device {device}")
    print(f"  scene objects: {len(scene.objects)}")
    print(f"  HAT.base base mesh: {len(hat.data.vertices)} verts, {len(hat.data.polygons)} faces, {quads} quads, {len(hat.data.polygons) - quads} non quads")
    print(f"  HAT.base evaluated (solidify + subsurf level {hat.modifiers['Smooth'].levels}): {eval_verts} verts, {eval_faces} faces")
    for vg in hat.vertex_groups:
        count = sum(1 for v in hat.data.vertices if any(g.group == vg.index for g in v.groups))
        print(f"  vertex group '{vg.name}': {count} verts")
    print(f"  HAT.base world bounding box: min {fmt_v(lo)} max {fmt_v(hi)} size {fmt_v(size)}")
    print(f"  CAM.hero location {fmt_v(cam.location)}, lens {cam.data.lens:.1f} mm, f/{cam.data.dof.aperture_fstop:.1f}, focus {cam.data.dof.focus_distance:.3f} m")
    print(f"  preview: {render_path} ({render_time:.1f} s)")
    print("=================================")


def main():
    global WORK
    WORK = workdir()
    scene = bpy.context.scene
    print(f"\n[{SCRIPT}] working folder: {WORK}")
    clear_startup_objects()
    device = configure_scene(scene)
    set_world(scene)
    hats_col = collection("Hats")
    rig_col = collection("Camera and Lights")
    hat = build_hat_base(hats_col)
    cam = build_camera(rig_col)
    build_rig(rig_col)
    path, dt = render_preview(scene, SCRIPT)
    report(scene, hat, cam, device, path, dt)


main()
