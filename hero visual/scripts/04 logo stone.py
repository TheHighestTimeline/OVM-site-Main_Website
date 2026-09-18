"""04 logo stone.py

OVM Hat Hero, phase one, step 1D.

Builds LOGO.stone, the OVM mark carved in stone. The O is the ornamental
ring from the OneVibeMedia wordmark (raised inner and outer lips with a
Greek key meander carved in the channel between them), followed by VM in a
bold serif. Every part is a closed solid so a hat passing into the ring is
occluded by the stone's thickness.

Source check: the repository has no SVG and no model from the 3D printed
ring project, only the wordmark PNG (copied to reference/OVM wordmark
black.png). The ring proportions were measured from that PNG: inner radius
0.667 of the outer, inner lip to 0.74, channel to 0.93, outer lip to 1.0.

Stone material: cool grey cast (chosen so the gold reveal is the only warm
thing in frame), two scale displacement, pointiness driven cavity darkening
with roughness inverse to cavity, a little subsurface, chipping along the
bevel edges, no mirror reflection.

Reports the O's outer diameter and ring stroke thickness in metres, both
measured from the built mesh. Renders two 800 px previews, straight on and
at raking light.

Idempotent.
"""
import bpy
import bmesh
import math
import os
import random
import time
from mathutils import Vector, Matrix

SCRIPT = "04 logo stone"

# ---------------------------------------------------------------- parameters
O_DIAMETER = 0.36            # outer diameter of the ring, metres
DEPTH = 0.10                 # stone thickness, along the view axis
R_INNER = 0.667              # fractions of the outer radius, measured from the PNG
R_LIP_IN = 0.740
R_LIP_OUT = 0.930
CHANNEL_DEPTH = 0.009        # channel recessed below the lips
BLOCK_HEIGHT = 0.0065        # meander blocks rise this much from the channel floor
BLOCK_MARGIN = 0.0012        # clearance from the lips
MOTIFS = 20                  # meander repeats around the ring
ANGULAR_SEGMENTS = 240
LETTERS = "VM"
LETTER_CAP_HEIGHT = 0.56     # fraction of the O diameter
LETTER_GAP = 0.04            # metres between the O and the V
LETTER_TRACKING = 0.98
BEVEL_WIDTH = 0.0045
BEVEL_SEGMENTS = 3
SEED = 4

# Greek key, one motif, 5 rows (inner to outer) by 6 columns (around). The
# top rail (last row) is continuous from motif to motif.
MEANDER = [
    "XXX.X.",
    "X.X.X.",
    "X.XXX.",
    "X.....",
    "XXXXXX",
]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\timesbd.ttf",
    r"C:\Windows\Fonts\georgiab.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/Library/Fonts/Times New Roman Bold.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
]

PLACE = Vector((0.95, 0.0, 0.30))   # look dev position, beside the hat. 05 moves it.

PREVIEW_WIDTH = 800
PREVIEW_HEIGHT = 457
PREVIEW_SAMPLES = 96
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


def remove_object(name):
    ob = bpy.data.objects.get(name)
    if ob is None:
        return
    data = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Curve):
            bpy.data.curves.remove(data)


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


def render_preview(scene, name, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT, samples=PREVIEW_SAMPLES):
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


def new_material(name):
    old = bpy.data.materials.get(name)
    if old is not None:
        bpy.data.materials.remove(old)
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    return mat


def node(nt, kind, location=(0, 0), **props):
    n = nt.nodes.new(kind)
    n.location = location
    for k, v in props.items():
        setattr(n, k, v)
    return n


def set_input(n, name, value):
    if isinstance(name, int):
        n.inputs[name].default_value = value
        return
    if name not in n.inputs:
        raise RuntimeError(f"{SCRIPT}: node {n.bl_idname} has no input '{name}'. Inputs: {[i.name for i in n.inputs]}")
    n.inputs[name].default_value = value


# ------------------------------------------------------------------ the ring
def polar(r, y, a):
    """Ring lies in the XZ plane, revolved around Y (the view axis). Front face at y = 0."""
    return Vector((r * math.cos(a), y, r * math.sin(a)))


def build_ring(bm):
    R = O_DIAMETER / 2.0
    r_in, r_li, r_lo = R * R_INNER, R * R_LIP_IN, R * R_LIP_OUT
    c = CHANNEL_DEPTH
    # closed profile in (radius, depth), walked so the revolved faces point outward
    profile = [
        (r_in, DEPTH), (r_in, 0.0), (r_li, 0.0), (r_li, c),
        (r_lo, c), (r_lo, 0.0), (R, 0.0), (R, DEPTH),
    ]
    rings = []
    for i in range(ANGULAR_SEGMENTS):
        a = 2.0 * math.pi * i / ANGULAR_SEGMENTS
        rings.append([bm.verts.new(polar(r, y, a)) for (r, y) in profile])
    n = len(profile)
    for i in range(ANGULAR_SEGMENTS):
        a, b = rings[i], rings[(i + 1) % ANGULAR_SEGMENTS]
        for j in range(n):
            k = (j + 1) % n
            bm.faces.new((a[j], b[j], b[k], a[k]))
    return r_in, r_li, r_lo, R


def build_meander(bm, r_li, r_lo):
    rows = len(MEANDER)
    cols = len(MEANDER[0])
    inner = r_li + BLOCK_MARGIN
    outer = r_lo - BLOCK_MARGIN
    cell_r = (outer - inner) / rows
    cell_a = 2.0 * math.pi / (MOTIFS * cols)
    y_top = CHANNEL_DEPTH - BLOCK_HEIGHT
    y_bottom = CHANNEL_DEPTH + 0.002      # sunk into the floor so no faces are coplanar
    count = 0
    for m in range(MOTIFS):
        for row in range(rows):
            for col in range(cols):
                if MEANDER[row][col] != "X":
                    continue
                r0 = inner + row * cell_r
                r1 = r0 + cell_r
                a0 = (m * cols + col) * cell_a
                a1 = a0 + cell_a
                # merge horizontally adjacent cells would be cleaner, but separate
                # blocks give the meander its slightly hand cut look once bevelled
                v = [bm.verts.new(polar(r, y, a)) for (r, y, a) in (
                    (r0, y_bottom, a0), (r1, y_bottom, a0), (r1, y_bottom, a1), (r0, y_bottom, a1),
                    (r0, y_top, a0), (r1, y_top, a0), (r1, y_top, a1), (r0, y_top, a1))]
                bm.faces.new((v[0], v[3], v[2], v[1]))   # bottom (faces +y, into the stone)
                bm.faces.new((v[4], v[5], v[6], v[7]))   # top, faces the viewer (-y)
                bm.faces.new((v[0], v[1], v[5], v[4]))
                bm.faces.new((v[1], v[2], v[6], v[5]))
                bm.faces.new((v[2], v[3], v[7], v[6]))
                bm.faces.new((v[3], v[0], v[4], v[7]))
                count += 1
    return count


def load_font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return bpy.data.fonts.load(path, check_existing=True), path
    return bpy.data.fonts.get("Bfont Regular") or bpy.data.fonts[0], "Blender built in font"


def build_letters(bm, R):
    """Extruded VM to the right of the ring, same depth, returned as its width."""
    font, font_path = load_font()
    curve = bpy.data.curves.new("TMP.logo letters", "FONT")
    curve.body = LETTERS
    curve.font = font
    curve.size = 1.0
    curve.space_character = LETTER_TRACKING
    curve.extrude = DEPTH / 2.0
    curve.fill_mode = "BOTH"
    curve.align_x = "LEFT"
    curve.align_y = "BOTTOM_BASELINE"
    ob = bpy.data.objects.new("TMP.logo letters", curve)
    bpy.context.scene.collection.objects.link(ob)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(depsgraph))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(curve)
    if font.users == 0 and font.name != "Bfont Regular":
        bpy.data.fonts.remove(font)

    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    measured_cap = max(ys) - min(ys)
    k = (O_DIAMETER * LETTER_CAP_HEIGHT) / measured_cap
    # text is built in XY with extrusion along Z. Rotate so it stands in XZ
    # and extrudes along +Y (into the stone), bottom aligned to the ring's bottom
    # of the letters sitting on the ring's centre line minus half the cap height.
    to_upright = Matrix.Rotation(math.radians(90.0), 4, "X")   # y -> z, z -> -y
    flip_depth = Matrix.Scale(-1.0, 4, Vector((0.0, 1.0, 0.0)))  # extrude toward +y
    x_start = R + LETTER_GAP - min(xs) * k
    z_base = -(O_DIAMETER * LETTER_CAP_HEIGHT) / 2.0 - min(ys) * k
    place = Matrix.Translation((x_start, DEPTH / 2.0, z_base))
    scale = Matrix.Scale(k, 4)
    xform = place @ flip_depth @ to_upright @ scale
    me.transform(xform)
    bm.from_mesh(me)
    width = (max(xs) - min(xs)) * k
    bpy.data.meshes.remove(me)
    return width, font_path


def build_logo(col):
    remove_object("LOGO.stone")
    old = bpy.data.meshes.get("LOGO.stone")
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)
    bm = bmesh.new()
    r_in, r_li, r_lo, R = build_ring(bm)
    blocks = build_meander(bm, r_li, r_lo)
    letters_width, font_path = build_letters(bm, R)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("LOGO.stone")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("LOGO.stone", me)
    link(ob, col)
    ob.location = PLACE

    bevel = ob.modifiers.new("Carved edge", "BEVEL")
    bevel.width = BEVEL_WIDTH
    bevel.segments = BEVEL_SEGMENTS
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = math.radians(30.0)
    bevel.harden_normals = False
    sub = ob.modifiers.new("Displacement density", "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = 1
    sub.render_levels = 2
    me.shade_smooth_by_angle(angle=math.radians(35.0)) if hasattr(me, "shade_smooth_by_angle") else me.shade_smooth()
    return ob, (r_in, r_li, r_lo, R), blocks, letters_width, font_path


# --------------------------------------------------------------- material
def build_stone_material():
    mat = new_material("MAT.stone")
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", (1500, 0))
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", (1200, 0))
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    set_input(bsdf, "Metallic", 0.0)
    set_input(bsdf, "Specular IOR Level", 0.3)
    set_input(bsdf, "Subsurface Weight", 0.05)
    set_input(bsdf, "Subsurface Radius", (0.012, 0.010, 0.009))
    set_input(bsdf, "Subsurface Scale", 0.02)

    coords = node(nt, "ShaderNodeTexCoord", (-1200, 0))
    geo = node(nt, "ShaderNodeNewGeometry", (-1200, -500))

    # cavity from pointiness. Around 0.5 is flat, lower is concave, higher is convex.
    cavity = node(nt, "ShaderNodeMapRange", (-900, -500))
    set_input(cavity, "From Min", 0.40)
    set_input(cavity, "From Max", 0.50)
    set_input(cavity, "To Min", 1.0)
    set_input(cavity, "To Max", 0.0)
    cavity.clamp = True
    nt.links.new(geo.outputs["Pointiness"], cavity.inputs["Value"])
    edge = node(nt, "ShaderNodeMapRange", (-900, -750))
    set_input(edge, "From Min", 0.52)
    set_input(edge, "From Max", 0.62)
    set_input(edge, "To Min", 0.0)
    set_input(edge, "To Max", 1.0)
    edge.clamp = True
    nt.links.new(geo.outputs["Pointiness"], edge.inputs["Value"])

    # colour: cool grey stone with mottling, darker and dirtier in the recesses
    mottle = node(nt, "ShaderNodeTexNoise", (-900, 300))
    set_input(mottle, "Scale", 14.0)
    set_input(mottle, "Detail", 6.0)
    set_input(mottle, "Roughness", 0.55)
    nt.links.new(coords.outputs["Object"], mottle.inputs["Vector"])
    ramp = node(nt, "ShaderNodeValToRGB", (-650, 300))
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.095, 0.102, 0.120, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.215, 0.225, 0.245, 1.0)
    nt.links.new(mottle.outputs["Fac"], ramp.inputs["Fac"])
    dirt = node(nt, "ShaderNodeMix", (-300, 300), data_type="RGBA", blend_type="MIX")
    set_input(dirt, "B", (0.035, 0.032, 0.030, 1.0))
    nt.links.new(ramp.outputs["Color"], dirt.inputs["A"])
    cav_amount = node(nt, "ShaderNodeMath", (-500, 100), operation="MULTIPLY")
    set_input(cav_amount, 1, 0.75)
    nt.links.new(cavity.outputs["Result"], cav_amount.inputs[0])
    nt.links.new(cav_amount.outputs["Value"], dirt.inputs["Factor"])
    # high points a touch lighter
    lift = node(nt, "ShaderNodeMix", (0, 300), data_type="RGBA", blend_type="MIX")
    set_input(lift, "B", (0.28, 0.29, 0.31, 1.0))
    nt.links.new(dirt.outputs["Result"], lift.inputs["A"])
    edge_amount = node(nt, "ShaderNodeMath", (-500, -100), operation="MULTIPLY")
    set_input(edge_amount, 1, 0.35)
    nt.links.new(edge.outputs["Result"], edge_amount.inputs[0])
    nt.links.new(edge_amount.outputs["Value"], lift.inputs["Factor"])
    nt.links.new(lift.outputs["Result"], bsdf.inputs["Base Color"])

    # roughness inverse to cavity: recesses rough, high points slightly polished
    rough = node(nt, "ShaderNodeMapRange", (300, 100))
    set_input(rough, "From Min", 0.0)
    set_input(rough, "From Max", 1.0)
    set_input(rough, "To Min", 0.62)
    set_input(rough, "To Max", 0.92)
    nt.links.new(cavity.outputs["Result"], rough.inputs["Value"])
    polish = node(nt, "ShaderNodeMath", (600, 100), operation="SUBTRACT")
    nt.links.new(rough.outputs["Result"], polish.inputs[0])
    polish_amt = node(nt, "ShaderNodeMath", (300, -100), operation="MULTIPLY")
    set_input(polish_amt, 1, 0.18)
    nt.links.new(edge.outputs["Result"], polish_amt.inputs[0])
    nt.links.new(polish_amt.outputs["Value"], polish.inputs[1])
    nt.links.new(polish.outputs["Value"], bsdf.inputs["Roughness"])

    # displacement at two scales, plus chipping along the bevel edges
    broad = node(nt, "ShaderNodeTexNoise", (-900, -1000))
    set_input(broad, "Scale", 7.0)
    set_input(broad, "Detail", 3.0)
    nt.links.new(coords.outputs["Object"], broad.inputs["Vector"])
    grain = node(nt, "ShaderNodeTexNoise", (-900, -1250))
    set_input(grain, "Scale", 220.0)
    set_input(grain, "Detail", 2.0)
    nt.links.new(coords.outputs["Object"], grain.inputs["Vector"])
    broad_c = node(nt, "ShaderNodeMath", (-600, -1000), operation="SUBTRACT")
    set_input(broad_c, 1, 0.5)
    nt.links.new(broad.outputs["Fac"], broad_c.inputs[0])
    broad_s = node(nt, "ShaderNodeMath", (-400, -1000), operation="MULTIPLY")
    set_input(broad_s, 1, 0.0030)
    nt.links.new(broad_c.outputs["Value"], broad_s.inputs[0])
    grain_c = node(nt, "ShaderNodeMath", (-600, -1250), operation="SUBTRACT")
    set_input(grain_c, 1, 0.5)
    nt.links.new(grain.outputs["Fac"], grain_c.inputs[0])
    grain_s = node(nt, "ShaderNodeMath", (-400, -1250), operation="MULTIPLY")
    set_input(grain_s, 1, 0.0006)
    nt.links.new(grain_c.outputs["Value"], grain_s.inputs[0])
    # chips: cells of a voronoi, only where the surface is convex, only some cells
    chip_cells = node(nt, "ShaderNodeTexVoronoi", (-900, -1500), feature="F1")
    set_input(chip_cells, "Scale", 90.0)
    set_input(chip_cells, "Randomness", 1.0)
    nt.links.new(coords.outputs["Object"], chip_cells.inputs["Vector"])
    chip_pick = node(nt, "ShaderNodeMath", (-600, -1500), operation="GREATER_THAN")
    set_input(chip_pick, 1, 0.72)                        # about a quarter of cells chip
    nt.links.new(chip_cells.outputs["Distance"], chip_pick.inputs[0])
    chip_edge = node(nt, "ShaderNodeMath", (-400, -1500), operation="MULTIPLY")
    nt.links.new(chip_pick.outputs["Value"], chip_edge.inputs[0])
    nt.links.new(edge.outputs["Result"], chip_edge.inputs[1])
    chip_s = node(nt, "ShaderNodeMath", (-200, -1500), operation="MULTIPLY")
    set_input(chip_s, 1, -0.0035)
    nt.links.new(chip_edge.outputs["Value"], chip_s.inputs[0])
    sum1 = node(nt, "ShaderNodeMath", (0, -1100), operation="ADD")
    nt.links.new(broad_s.outputs["Value"], sum1.inputs[0])
    nt.links.new(grain_s.outputs["Value"], sum1.inputs[1])
    sum2 = node(nt, "ShaderNodeMath", (200, -1100), operation="ADD")
    nt.links.new(sum1.outputs["Value"], sum2.inputs[0])
    nt.links.new(chip_s.outputs["Value"], sum2.inputs[1])
    disp = node(nt, "ShaderNodeDisplacement", (900, -700))
    set_input(disp, "Midlevel", 0.0)
    set_input(disp, "Scale", 1.0)
    nt.links.new(sum2.outputs["Value"], disp.inputs["Height"])
    nt.links.new(disp.outputs["Displacement"], out.inputs["Displacement"])
    mat.displacement_method = "BOTH"
    return mat


# ------------------------------------------------------------------ measure
def measure(ob):
    """Outer diameter and stroke thickness of the O, from the built mesh, in metres."""
    R = O_DIAMETER / 2.0
    radii = []
    for v in ob.data.vertices:
        if v.co.x > R * 1.05:
            continue           # letters
        radii.append(math.hypot(v.co.x, v.co.z))
    r_out = max(radii)
    r_in = min(radii)
    return 2.0 * r_out, r_out - r_in


def render_set(scene, cam, logo, key):
    results = {}
    scene.camera = cam
    saved_cam = (cam.location.copy(), cam.rotation_euler.copy(), cam.data.lens,
                 cam.data.dof.focus_distance, cam.data.dof.aperture_fstop)
    centre = logo.matrix_world @ Vector((0.0, 0.0, 0.0))
    lo = min((logo.matrix_world @ Vector(c)).x for c in logo.bound_box)
    hi = max((logo.matrix_world @ Vector(c)).x for c in logo.bound_box)
    width = hi - lo
    target = Vector(((lo + hi) / 2.0, centre.y, centre.z))
    dist = width * 1.25 * cam.data.lens / cam.data.sensor_width
    cam.location = target + Vector((0.0, -dist, 0.0))
    look_at(cam, target)
    cam.data.dof.aperture_fstop = 11.0
    cam.data.dof.focus_distance = dist
    saved_lights = {}
    for name in ("LIGHT.key", "LIGHT.fill", "LIGHT.rim"):
        l = bpy.data.objects.get(name)
        if l:
            saved_lights[name] = (l.location.copy(), l.rotation_euler.copy(), l.data.energy)
    key.location = target + Vector((-1.2, -1.4, 1.3))
    look_at(key, target)
    key.data.energy = 140.0
    fill = bpy.data.objects.get("LIGHT.fill")
    rim = bpy.data.objects.get("LIGHT.rim")
    if fill:
        fill.location = target + Vector((1.6, -1.6, 0.2))
        look_at(fill, target)
        fill.data.energy = 25.0
    if rim:
        rim.location = target + Vector((1.0, 1.4, 1.2))
        look_at(rim, target)
        rim.data.energy = 260.0
    results["straight on"] = render_preview(scene, "04 logo straight on")
    # raking light across the face
    key.location = target + Vector((-width * 1.3, -0.35, 0.25))
    look_at(key, target)
    key.data.energy = 110.0
    if fill:
        fill.data.energy = 8.0
    results["raking"] = render_preview(scene, "04 logo raking light")
    for name, (loc, rot, e) in saved_lights.items():
        l = bpy.data.objects[name]
        l.location, l.rotation_euler, l.data.energy = loc, rot, e
    (cam.location, cam.rotation_euler, cam.data.lens,
     cam.data.dof.focus_distance, cam.data.dof.aperture_fstop) = saved_cam
    return results


def main():
    global WORK
    WORK = workdir()
    scene = bpy.context.scene
    print(f"\n[{SCRIPT}] working folder: {WORK}")
    cam = require("CAM.hero")
    key = require("LIGHT.key")
    col = collection("Logo")
    t0 = time.time()
    logo, radii, blocks, letters_width, font_path = build_logo(col)
    mat = build_stone_material()
    logo.data.materials.clear()
    logo.data.materials.append(mat)
    build_time = time.time() - t0
    diameter, stroke = measure(logo)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = logo.evaluated_get(depsgraph).to_mesh()
    eval_counts = (len(ev.vertices), len(ev.polygons))
    logo.evaluated_get(depsgraph).to_mesh_clear()

    results = render_set(scene, cam, logo, key)
    dims = logo.dimensions

    print("")
    print(f"==== {SCRIPT} runtime report ====")
    print(f"  scene objects: {len(scene.objects)}")
    print(f"  LOGO.stone: {len(logo.data.vertices)} verts, {len(logo.data.polygons)} faces base, "
          f"{eval_counts[0]} verts, {eval_counts[1]} faces evaluated (bevel + simple subdivision level {logo.modifiers['Displacement density'].levels}), built in {build_time:.1f} s")
    print(f"  O outer diameter: {diameter:.4f} m")
    print(f"  O ring stroke thickness: {stroke:.4f} m (inner radius {radii[0]:.4f} m, outer radius {radii[3]:.4f} m)")
    print(f"  channel depth {CHANNEL_DEPTH * 1000:.1f} mm, meander blocks {blocks}, block height {BLOCK_HEIGHT * 1000:.1f} mm")
    print(f"  letters '{LETTERS}' width {letters_width:.4f} m, font {font_path}")
    print(f"  stone depth {DEPTH:.3f} m, whole mark {dims.x:.3f} x {dims.z:.3f} m, location {tuple(round(c, 3) for c in logo.location)}")
    print(f"  stone cast: cool, blue grey. Base colour range (linear) 0.095 to 0.245")
    for k, (path, dt) in results.items():
        print(f"  render {k}: {dt:.1f} s -> {path}")
    print("=================================")


main()
