"""04 logo stone.py

OVM Hat Hero, phase one, step 1D.

Builds LOGO.stone, the OneVibeMedia wordmark carved in stone, after the
stone reference render (reference/OneVibeMediaGroup stone reference.webp,
without the Group). The O is the engraved ring from the 3D printed ring
project, appended from reference/OVM ring.blend (object
MayanRingDebossedBoth, a closed solid). The letters neVibeMedia follow in
Cinzel with small capitals, extruded to the same depth. Every part is a
closed solid so a hat passing into the ring is occluded by the stone.

Stone material: light, slightly cool grey so it reads against a dark page
and leaves gold as the only warm note. Two scale relief as bump, crackle
lines, pointiness driven cavity darkening with roughness inverse to cavity,
a little subsurface, chipping along the bevel edges, no mirror reflection.

Reports the O's outer diameter and ring stroke thickness in metres, both
measured from the built mesh, plus the whole mark's width. Renders two
800 px previews, straight on and at raking light.

Idempotent.
"""
import bpy
import bmesh
import math
import os
import time
from mathutils import Vector, Matrix

SCRIPT = "04 logo stone"

# ---------------------------------------------------------------- parameters
O_DIAMETER = 0.20            # outer diameter of the ring, metres. The mark is about 7 times this wide.
DEPTH = 0.055                # stone thickness along the view axis, ring and letters alike
RING_FILE = os.path.join("reference", "OVM ring.blend")
RING_OBJECT = "MayanRingDebossedBoth"
LETTERS = "neVibeMedia"
LETTER_CAP_HEIGHT = 0.61     # capital height as a fraction of the O diameter, measured from the reference
SMALL_CAPS_SCALE = 0.70      # small capitals as a fraction of the capitals, measured from the reference
LETTER_BASELINE = -0.46      # baseline below the O centre, as a fraction of the O diameter
LETTER_GAP = 0.06            # gap between the ring and the n, as a fraction of the O diameter
LETTER_TRACKING = 1.0
BEVEL_WIDTH = 0.0025
BEVEL_SEGMENTS = 3

FONT_CANDIDATES = [
    os.path.join("reference", "fonts", "Cinzel Bold.ttf"),   # static instance, overlaps removed. The variable file breaks Blender text fill.
    r"C:\Windows\Fonts\timesbd.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
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
def append_ring():
    """Append the ring project mesh. Returns a fresh Mesh datablock, or fails loudly."""
    path = os.path.join(WORK, RING_FILE)
    if not os.path.exists(path):
        raise RuntimeError(f"{SCRIPT}: ring model not found at {path}")
    for old in [o for o in bpy.data.objects if o.name.startswith("TMP.ring")]:
        bpy.data.objects.remove(old, do_unlink=True)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        if RING_OBJECT not in src.objects:
            raise RuntimeError(f"{SCRIPT}: {RING_FILE} has no object {RING_OBJECT}. It has {list(src.objects)}")
        dst.objects = [RING_OBJECT]
    ob = dst.objects[0]
    ob.name = "TMP.ring"
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    return me


def ring_into(bm):
    """Scale the appended ring to O_DIAMETER and DEPTH, stand it upright facing -Y, add to bm."""
    me = append_ring()
    radii = [math.hypot(v.co.x, v.co.y) for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    r_out_src = max(radii)
    depth_src = max(zs) - min(zs)
    k = (O_DIAMETER / 2.0) / r_out_src
    kz = DEPTH / depth_src
    # source ring lies in XY with its axis on Z. Stand it up: axis to +Y, front face at y = 0.
    scale = Matrix.Diagonal((k, k, kz, 1.0))
    upright = Matrix.Rotation(math.radians(-90.0), 4, "X")     # z -> +y, y -> -z... then recentre
    xform = upright @ scale
    me.transform(xform)
    ys = [v.co.y for v in me.vertices]
    me.transform(Matrix.Translation((0.0, -min(ys), 0.0)))     # front face at y = 0, body toward +y
    for p in me.polygons:
        p.material_index = 0
        p.use_smooth = True
    bm.from_mesh(me)
    r_in_src = min(radii)
    bpy.data.meshes.remove(me)
    return r_in_src * k, r_out_src * k


def load_font():
    for rel in FONT_CANDIDATES:
        path = rel if os.path.isabs(rel) else os.path.join(WORK, rel)
        if os.path.exists(path):
            return bpy.data.fonts.load(path, check_existing=True), path
    return bpy.data.fonts.get("Bfont Regular") or bpy.data.fonts[0], "Blender built in font"


def letters_into(bm, r_out):
    """Extruded neVibeMedia with small caps to the right of the ring. Returns (width, font path)."""
    font, font_path = load_font()
    curve = bpy.data.curves.new("TMP.logo letters", "FONT")
    curve.body = LETTERS
    curve.font = font
    curve.size = 1.0
    curve.space_character = LETTER_TRACKING
    curve.small_caps_scale = SMALL_CAPS_SCALE
    curve.fill_mode = "BOTH"
    curve.align_x = "LEFT"
    curve.align_y = "BOTTOM_BASELINE"
    ob = bpy.data.objects.new("TMP.logo letters", curve)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    for i, ch in enumerate(LETTERS):
        curve.body_format[i].use_small_caps = ch.islower()
    # pass one, flat, to measure the capital height at size 1
    depsgraph = bpy.context.evaluated_depsgraph_get()
    flat = bpy.data.meshes.new_from_object(ob.evaluated_get(depsgraph))
    measured_cap = max(v.co.y for v in flat.vertices)
    bpy.data.meshes.remove(flat)
    k = (O_DIAMETER * LETTER_CAP_HEIGHT) / measured_cap
    # pass two, extruded so that after scaling by k the letters are exactly DEPTH thick
    curve.extrude = DEPTH / (2.0 * k)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(depsgraph))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(curve)
    if font.users == 0 and font.name != "Bfont Regular":
        bpy.data.fonts.remove(font)

    xs = [v.co.x for v in me.vertices]
    to_upright = Matrix.Rotation(math.radians(90.0), 4, "X")          # y -> z, extrusion z -> -y
    flip_depth = Matrix.Scale(-1.0, 4, Vector((0.0, 1.0, 0.0)))        # extrusion toward +y
    x_start = r_out + LETTER_GAP * O_DIAMETER - min(xs) * k
    z_base = LETTER_BASELINE * O_DIAMETER
    place = Matrix.Translation((x_start, DEPTH / 2.0, z_base))
    xform = place @ flip_depth @ to_upright @ Matrix.Scale(k, 4)
    me.transform(xform)
    for p in me.polygons:
        p.material_index = 0
    before = set(bm.faces)
    bm.from_mesh(me)
    # text fills are big n-gons, triangulate them so bevel and shading behave
    letter_faces = [f for f in bm.faces if f not in before]
    result = bmesh.ops.triangulate(bm, faces=letter_faces, quad_method="BEAUTY", ngon_method="BEAUTY")
    # letters shade flat: their front triangles reach across the whole glyph, so
    # smooth normals would bend visibly. The bevel modifier rounds the edges.
    for f in result["faces"]:
        f.smooth = False
    width = (max(xs) - min(xs)) * k
    bpy.data.meshes.remove(me)
    return width, font_path


def build_logo(col):
    remove_object("LOGO.stone")
    old = bpy.data.meshes.get("LOGO.stone")
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)
    bm = bmesh.new()
    r_in, r_out = ring_into(bm)
    letters_width, font_path = letters_into(bm, r_out)
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
    bevel.harden_normals = True
    return ob, (r_in, r_out), letters_width, font_path


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
    ramp.color_ramp.elements[0].color = (0.24, 0.25, 0.28, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.50, 0.51, 0.54, 1.0)
    nt.links.new(mottle.outputs["Fac"], ramp.inputs["Fac"])
    dirt = node(nt, "ShaderNodeMix", (-300, 300), data_type="RGBA", blend_type="MIX")
    set_input(dirt, "B", (0.06, 0.055, 0.05, 1.0))
    nt.links.new(ramp.outputs["Color"], dirt.inputs["A"])
    cav_amount = node(nt, "ShaderNodeMath", (-500, 100), operation="MULTIPLY")
    set_input(cav_amount, 1, 0.75)
    nt.links.new(cavity.outputs["Result"], cav_amount.inputs[0])
    nt.links.new(cav_amount.outputs["Value"], dirt.inputs["Factor"])
    # high points a touch lighter
    lift = node(nt, "ShaderNodeMix", (0, 300), data_type="RGBA", blend_type="MIX")
    set_input(lift, "B", (0.62, 0.63, 0.65, 1.0))
    nt.links.new(dirt.outputs["Result"], lift.inputs["A"])
    edge_amount = node(nt, "ShaderNodeMath", (-500, -100), operation="MULTIPLY")
    set_input(edge_amount, 1, 0.35)
    nt.links.new(edge.outputs["Result"], edge_amount.inputs[0])
    nt.links.new(edge_amount.outputs["Value"], lift.inputs["Factor"])
    # crackle, thin dark lines like the reference stone, from the edges of voronoi cells
    crack_cells = node(nt, "ShaderNodeTexVoronoi", (-900, 700), feature="DISTANCE_TO_EDGE")
    set_input(crack_cells, "Scale", 28.0)
    set_input(crack_cells, "Randomness", 1.0)
    nt.links.new(coords.outputs["Object"], crack_cells.inputs["Vector"])
    crack_mask = node(nt, "ShaderNodeMapRange", (-650, 700))
    set_input(crack_mask, "From Min", 0.0025)
    set_input(crack_mask, "From Max", 0.0)
    set_input(crack_mask, "To Min", 0.0)
    set_input(crack_mask, "To Max", 1.0)
    crack_mask.clamp = True
    nt.links.new(crack_cells.outputs["Distance"], crack_mask.inputs["Value"])
    # only some cell edges crack, gated by a second noise
    crack_gate = node(nt, "ShaderNodeTexNoise", (-900, 950))
    set_input(crack_gate, "Scale", 6.0)
    nt.links.new(coords.outputs["Object"], crack_gate.inputs["Vector"])
    gate = node(nt, "ShaderNodeMath", (-650, 950), operation="GREATER_THAN")
    set_input(gate, 1, 0.45)
    nt.links.new(crack_gate.outputs["Fac"], gate.inputs[0])
    crack = node(nt, "ShaderNodeMath", (-400, 800), operation="MULTIPLY")
    nt.links.new(crack_mask.outputs["Result"], crack.inputs[0])
    nt.links.new(gate.outputs["Value"], crack.inputs[1])
    cracked = node(nt, "ShaderNodeMix", (250, 400), data_type="RGBA", blend_type="MIX")
    set_input(cracked, "B", (0.04, 0.038, 0.036, 1.0))
    nt.links.new(lift.outputs["Result"], cracked.inputs["A"])
    crack_amt = node(nt, "ShaderNodeMath", (0, 800), operation="MULTIPLY")
    set_input(crack_amt, 1, 0.85)
    nt.links.new(crack.outputs["Value"], crack_amt.inputs[0])
    nt.links.new(crack_amt.outputs["Value"], cracked.inputs["Factor"])
    nt.links.new(cracked.outputs["Result"], bsdf.inputs["Base Color"])

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
    set_input(broad_s, 1, 0.0018)
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
    set_input(chip_s, 1, -0.0020)
    nt.links.new(chip_edge.outputs["Value"], chip_s.inputs[0])
    sum1 = node(nt, "ShaderNodeMath", (0, -1100), operation="ADD")
    nt.links.new(broad_s.outputs["Value"], sum1.inputs[0])
    nt.links.new(grain_s.outputs["Value"], sum1.inputs[1])
    sum2 = node(nt, "ShaderNodeMath", (200, -1100), operation="ADD")
    nt.links.new(sum1.outputs["Value"], sum2.inputs[0])
    nt.links.new(chip_s.outputs["Value"], sum2.inputs[1])
    # cracks cut into the surface a little
    crack_disp = node(nt, "ShaderNodeMath", (200, -1350), operation="MULTIPLY")
    set_input(crack_disp, 1, -0.0012)
    nt.links.new(crack.outputs["Value"], crack_disp.inputs[0])
    sum3 = node(nt, "ShaderNodeMath", (400, -1100), operation="ADD")
    nt.links.new(sum2.outputs["Value"], sum3.inputs[0])
    nt.links.new(crack_disp.outputs["Value"], sum3.inputs[1])
    disp = node(nt, "ShaderNodeDisplacement", (900, -700))
    set_input(disp, "Midlevel", 0.0)
    set_input(disp, "Scale", 1.0)
    nt.links.new(sum3.outputs["Value"], disp.inputs["Height"])
    nt.links.new(disp.outputs["Displacement"], out.inputs["Displacement"])
    # bump only: the letter meshes are too sparse for true displacement, which
    # turned their faces into facets. The bevel carries the edge shape.
    mat.displacement_method = "BUMP"
    return mat


# ------------------------------------------------------------------ measure
def measure(ob):
    """Outer diameter and stroke thickness of the O, from the built mesh, in metres."""
    R = O_DIAMETER / 2.0
    radii = []
    for v in ob.data.vertices:
        if v.co.x > R * 1.02:
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
    logo, radii, letters_width, font_path = build_logo(col)
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
          f"{eval_counts[0]} verts, {eval_counts[1]} faces evaluated (bevel), built in {build_time:.1f} s")
    print(f"  O outer diameter: {diameter:.4f} m")
    print(f"  O ring stroke thickness: {stroke:.4f} m (inner radius {radii[0]:.4f} m, outer radius {radii[1]:.4f} m)")
    print(f"  ring source: {RING_FILE} / {RING_OBJECT}")
    print(f"  letters '{LETTERS}' width {letters_width:.4f} m, font {font_path}")
    print(f"  stone depth {DEPTH:.3f} m, whole mark {dims.x:.3f} x {dims.z:.3f} m, location {tuple(round(c, 3) for c in logo.location)}")
    print(f"  stone cast: cool, blue grey. Base colour range (linear) 0.24 to 0.54")
    for k, (path, dt) in results.items():
        print(f"  render {k}: {dt:.1f} s -> {path}")
    print("=================================")


main()
