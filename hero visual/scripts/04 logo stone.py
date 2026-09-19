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
O_DIAMETER = 0.40            # outer diameter of the ring, metres. The mark is about 6 times this wide.
DEPTH = 0.22                 # stone thickness along the view axis, ring and letters alike
RING_FILE = os.path.join("reference", "OVM ring.blend")
RING_OBJECT = "MayanRingDebossedBoth"
LETTERS = "neVibeMedia"
LETTER_CAP_HEIGHT = 0.61     # capital height as a fraction of the O diameter, measured from the reference
SMALL_CAPS_SCALE = 0.64      # small capitals as a fraction of the capitals, measured from the official close up
LETTER_BASELINE = -0.45      # baseline below the O centre, as a fraction of the O diameter
LETTER_GAP = 0.0             # the n starts right at the ring's edge
LETTER_TRACKING = 1.0
# Per glyph horizontal offsets in em, applied to that glyph and everything after it.
# Blender's own kerning field barely moves glyphs, so placement is done by hand.
OFFSETS_EM = {2: -0.09, 3: -0.115}  # V pulled over the e, i pulled under the V   # pull these letters toward the one before them, in em
VOXEL_LETTERS = 0.0009   # remesh size for the letters, metres. Dense geometry so the stone displaces for real
EROSION_SMOOTH = 0       # smoothing passes that round the letter edges into worn boulders
HEWN_LARGE = 0.0         # metres, low frequency lumps baked into the letter geometry
HEWN_SMALL = 0.0         # metres, mid frequency lumps
VOXEL_RING = 0.0005      # remesh size for the ring, fine enough to keep the engraving
RING_DEPTH_SCALE = 2.5   # the ring is scaled uniformly (so the engraving keeps the designer's proportions), then its depth is multiplied by this
BEVEL_WIDTH = 0.004
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


def remesh(me, voxel):
    """Voxel remesh a mesh datablock through a temporary object. Returns a new dense mesh."""
    tmp = bpy.data.objects.new("TMP.remesh", me)
    bpy.context.scene.collection.objects.link(tmp)
    mod = tmp.modifiers.new("Remesh", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = voxel
    mod.adaptivity = 0.0
    mod.use_smooth_shade = True
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    dense = bpy.data.meshes.new_from_object(tmp.evaluated_get(depsgraph))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.meshes.remove(me)
    return dense


def hew(me, smooth_passes, large, small, seed_offset):
    """Round the edges and push the surface around with noise, so the silhouette is hand cut.

    Off by default (all zero): Tanner wants sharp corners, the eroded look read as bubbly."""
    if not smooth_passes and not large and not small:
        return me
    from mathutils import noise
    bm = bmesh.new()
    bm.from_mesh(me)
    if smooth_passes:
        for _ in range(smooth_passes):
            bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    off = Vector((seed_offset, seed_offset * 0.7, seed_offset * 1.3))
    for v in bm.verts:
        p = v.co + off
        d = large * noise.noise(p * 9.0) + small * noise.noise(p * 34.0)
        v.co += v.normal * d
    bm.to_mesh(me)
    bm.free()
    return me


def ring_into(bm):
    """Scale the appended ring to O_DIAMETER and DEPTH, stand it upright facing -Y, add to bm."""
    me = append_ring()
    # the source ring is not centred on its origin: recentre on its bounds first
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2.0, -(min(ys) + max(ys)) / 2.0, 0.0)))
    radii = [math.hypot(v.co.x, v.co.y) for v in me.vertices]
    r_out_src = (max(xs) - min(xs)) / 2.0
    depth_src = max(zs) - min(zs)
    k = (O_DIAMETER / 2.0) / r_out_src
    kz = DEPTH / depth_src        # the ring is as deep as the letters, so a hat can vanish into its side
    # source ring lies in XY with its axis on Z. Stand it up: axis to +Y, front face at y = 0.
    scale = Matrix.Diagonal((k, k, kz, 1.0))
    upright = Matrix.Rotation(math.radians(-90.0), 4, "X")     # z -> +y, y -> -z... then recentre
    xform = upright @ scale
    me.transform(xform)
    ys = [v.co.y for v in me.vertices]
    me.transform(Matrix.Translation((0.0, -min(ys), 0.0)))     # front face at y = 0, body toward +y
    me = remesh(me, VOXEL_RING)
    me = hew(me, 0, 0.0, 0.0, 3.0)   # never eroded, the engraving stays exact
    for p in me.polygons:
        p.use_smooth = True
    before = set(bm.faces)
    bm.from_mesh(me)
    for f in bm.faces:
        if f not in before:
            f.material_index = 1      # MAT.stone ring, the polished chiselled variant
    r_in_src = min(radii)
    bpy.data.meshes.remove(me)
    return r_in_src * k, r_out_src * k


def load_font():
    for rel in FONT_CANDIDATES:
        path = rel if os.path.isabs(rel) else os.path.join(WORK, rel)
        if os.path.exists(path):
            return bpy.data.fonts.load(path, check_existing=True), path
    return bpy.data.fonts.get("Bfont Regular") or bpy.data.fonts[0], "Blender built in font"


def glyph_mesh(text, font, extrude, small_caps_flags):
    """Flat or extruded mesh of a string with per character small caps, at size 1."""
    curve = bpy.data.curves.new("TMP.glyph", "FONT")
    curve.body = text
    curve.font = font
    curve.size = 1.0
    curve.space_character = LETTER_TRACKING
    curve.small_caps_scale = SMALL_CAPS_SCALE
    curve.extrude = extrude
    curve.fill_mode = "BOTH"
    curve.align_x = "LEFT"
    curve.align_y = "BOTTOM_BASELINE"
    ob = bpy.data.objects.new("TMP.glyph", curve)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    for i, flag in enumerate(small_caps_flags):
        curve.body_format[i].use_small_caps = flag
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(depsgraph))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(curve)
    return me


def letters_into(bm, r_out):
    """Extruded neVibeMedia with small caps, each glyph placed by hand. Returns (width, font path)."""
    font, font_path = load_font()
    flags = [ch.islower() for ch in LETTERS]
    # advances: the pen position after each prefix of the word, from flat meshes
    advances = [0.0]
    cap = None
    for n in range(1, len(LETTERS) + 1):
        me = glyph_mesh(LETTERS[:n], font, 0.0, flags[:n])
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        if cap is None or max(ys) > cap:
            cap = max(ys)
        advances.append(max(xs))
        bpy.data.meshes.remove(me)
    k = (O_DIAMETER * LETTER_CAP_HEIGHT) / cap
    extrude = DEPTH / (2.0 * k)
    to_upright = Matrix.Rotation(math.radians(90.0), 4, "X")
    flip_depth = Matrix.Scale(-1.0, 4, Vector((0.0, 1.0, 0.0)))
    z_base = LETTER_BASELINE * O_DIAMETER
    shift = 0.0
    right_edge = 0.0
    x_start = r_out + LETTER_GAP * O_DIAMETER
    for i, ch in enumerate(LETTERS):
        shift += OFFSETS_EM.get(i, 0.0)
        me = glyph_mesh(ch, font, extrude, [flags[i]])
        # the single glyph mesh already includes its own left bearing from the origin,
        # so placing its origin at the word's pen position reproduces the word layout
        pen_x = advances[i] + shift
        place = Matrix.Translation((x_start + pen_x * k, DEPTH / 2.0, z_base))
        xform = place @ flip_depth @ to_upright @ Matrix.Scale(k, 4)
        me.transform(xform)
        for p in me.polygons:
            p.material_index = 0
        right_edge = max(right_edge, max(v.co.x for v in me.vertices))
        dense = remesh(me, VOXEL_LETTERS)
        dense = hew(dense, EROSION_SMOOTH, HEWN_LARGE, HEWN_SMALL, 11.0 + i)
        for p in dense.polygons:
            p.material_index = 0
            p.use_smooth = True
        bm.from_mesh(dense)
        bpy.data.meshes.remove(dense)
    if font.users == 0 and font.name != "Bfont Regular":
        bpy.data.fonts.remove(font)
    width = right_edge - x_start
    return width, font_path


def build_logo(col):
    remove_object("LOGO.stone")
    old = bpy.data.meshes.get("LOGO.stone")
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)
    bm = bmesh.new()
    r_in, r_out = ring_into(bm)
    letters_width, font_path = letters_into(bm, r_out)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("LOGO.stone")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("LOGO.stone", me)
    link(ob, col)
    ob.location = PLACE

    # the voxel remesh already softens the edges, no bevel modifier needed
    return ob, (r_in, r_out), letters_width, font_path


# --------------------------------------------------------------- material
def build_stone_material(name="MAT.stone", cracks=1.0, veins_amt=1.0, pits_amt=1.0, chips=1.0, grain_amt=1.0, ao=0.0,
                         body_dark=(0.22, 0.225, 0.25), body_light=(0.50, 0.51, 0.54), rough_min=0.74, rough_max=0.92,
                         coat=0.0, specular=0.25, ao_distance=0.02, relief=1.0):
    """Weathered grey stone after the references: grey mineral body, white calcite vein
    network, a few deep cracks with raised lips, pitting, cavity darkening.

    The multipliers scale each feature so the ring can be a cleaner, chiselled variant.
    ao adds ambient occlusion darkening in the grooves, which sells carved depth."""
    mat = new_material(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", (2200, 0))
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", (1900, 0))
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    set_input(bsdf, "Metallic", 0.0)
    set_input(bsdf, "Specular IOR Level", specular)
    set_input(bsdf, "Coat Weight", coat)
    set_input(bsdf, "Coat Roughness", 0.12)
    set_input(bsdf, "Subsurface Weight", 0.04)
    set_input(bsdf, "Subsurface Radius", (0.010, 0.009, 0.008))
    set_input(bsdf, "Subsurface Scale", 0.02)

    coords = node(nt, "ShaderNodeTexCoord", (-1600, 0))
    geo = node(nt, "ShaderNodeNewGeometry", (-1600, -600))

    def math_node(op, a, b, loc):
        n = node(nt, "ShaderNodeMath", loc, operation=op)
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                set_input(n, i, v)
            else:
                nt.links.new(v, n.inputs[i])
        return n.outputs["Value"]

    def map_range(value, a, b, c, d, loc):
        n = node(nt, "ShaderNodeMapRange", loc)
        n.clamp = True
        set_input(n, "From Min", a)
        set_input(n, "From Max", b)
        set_input(n, "To Min", c)
        set_input(n, "To Max", d)
        nt.links.new(value, n.inputs["Value"])
        return n.outputs["Result"]

    def noise_tex(vec, scale, detail, rough, loc, distortion=0.0):
        n = node(nt, "ShaderNodeTexNoise", loc)
        set_input(n, "Scale", scale)
        set_input(n, "Detail", detail)
        set_input(n, "Roughness", rough)
        set_input(n, "Distortion", distortion)
        nt.links.new(vec, n.inputs["Vector"])
        return n.outputs["Fac"]

    def voronoi(vec, scale, feature, loc):
        n = node(nt, "ShaderNodeTexVoronoi", loc, feature=feature)
        set_input(n, "Scale", scale)
        set_input(n, "Randomness", 1.0)
        nt.links.new(vec, n.inputs["Vector"])
        return n.outputs["Distance"]

    obj = coords.outputs["Object"]

    # a wobbled copy of the coordinates so vein and crack lines meander instead of running straight
    wobble = node(nt, "ShaderNodeTexNoise", (-1400, 300))
    set_input(wobble, "Scale", 12.0)
    set_input(wobble, "Detail", 3.0)
    nt.links.new(obj, wobble.inputs["Vector"])
    wob_scale = node(nt, "ShaderNodeVectorMath", (-1200, 300), operation="MULTIPLY_ADD")
    wob_scale.inputs[1].default_value = (0.05, 0.05, 0.05)
    nt.links.new(wobble.outputs["Color"], wob_scale.inputs[0])
    nt.links.new(obj, wob_scale.inputs[2])
    wobbled = wob_scale.outputs["Vector"]

    # cavity and edge from pointiness (the mesh is dense, so both are tight around 0.5)
    cavity = map_range(geo.outputs["Pointiness"], 0.47, 0.50, 1.0, 0.0, (-1300, -600))
    edge = map_range(geo.outputs["Pointiness"], 0.51, 0.55, 0.0, 1.0, (-1300, -800))

    # vein network, two scales, white calcite, gated so it is patchy like the reference
    vein_a = map_range(voronoi(wobbled, 9.0, "DISTANCE_TO_EDGE", (-1000, 600)), 0.0075, 0.0, 0.0, 1.0, (-800, 600))
    vein_b = map_range(voronoi(wobbled, 30.0, "DISTANCE_TO_EDGE", (-1000, 400)), 0.0036, 0.0, 0.0, 1.0, (-800, 400))
    gate_a = math_node("GREATER_THAN", noise_tex(obj, 3.0, 2.0, 0.5, (-1000, 800)), 0.30, (-800, 800))
    gate_b = math_node("GREATER_THAN", noise_tex(obj, 7.0, 2.0, 0.5, (-1000, 200), 0.0), 0.42, (-800, 200))
    veins = math_node("MAXIMUM", math_node("MULTIPLY", vein_a, gate_a, (-600, 700)),
                      math_node("MULTIPLY", vein_b, gate_b, (-600, 300)), (-400, 500))
    veins = math_node("MULTIPLY", veins, veins_amt, (-300, 500))

    # deep cracks with raised lips, sparse
    crack_d = voronoi(wobbled, 4.5, "DISTANCE_TO_EDGE", (-1000, 0))
    crack_core = map_range(crack_d, 0.0085, 0.0, 0.0, 1.0, (-800, 0))
    crack_lip = math_node("MULTIPLY", map_range(crack_d, 0.013, 0.024, 1.0, 0.0, (-800, -150)),
                          map_range(crack_d, 0.0, 0.013, 0.0, 1.0, (-800, -300)), (-600, -200))
    # gate at letter scale, not word scale, so every letter gets a similar share of cracks
    # nearly open gate: every letter carries cracks, as in the official logo. Density comes from the voronoi scale.
    crack_gate = math_node("GREATER_THAN", noise_tex(obj, 7.0, 2.0, 0.5, (-1000, -200)), 0.10, (-800, -420))
    away_from_edge = map_range(edge, 0.0, 0.7, 1.0, 0.0, (-600, -500))
    crack = math_node("MULTIPLY", math_node("MULTIPLY", crack_core, crack_gate, (-400, 0)), cracks, (-300, 0))
    crack = math_node("MULTIPLY", crack, away_from_edge, (-200, 0))
    # a finer crevice network on top: shallower, narrower, but still dark in the floor
    fine_d = voronoi(wobbled, 13.0, "DISTANCE_TO_EDGE", (-1000, -600))
    fine_core = map_range(fine_d, 0.0038, 0.0, 0.0, 1.0, (-800, -600))
    fine_gate = math_node("GREATER_THAN", noise_tex(obj, 9.0, 2.0, 0.5, (-1000, -700)), 0.42, (-800, -700))
    fine = math_node("MULTIPLY", math_node("MULTIPLY", fine_core, fine_gate, (-600, -600)), cracks, (-500, -600))
    fine = math_node("MULTIPLY", fine, away_from_edge, (-400, -600))
    big_crack = crack
    crack = math_node("MAXIMUM", crack, math_node("MULTIPLY", fine, 0.75, (-300, -600)), (-100, 0))
    lip = math_node("MULTIPLY", math_node("MULTIPLY", crack_lip, crack_gate, (-400, -200)), cracks, (-300, -200))
    lip = math_node("MULTIPLY", lip, away_from_edge, (-200, -200))

    # pitting, small dark holes
    pits = map_range(voronoi(obj, 45.0, "F1", (-1000, -1000)), 0.16, 0.09, 0.0, 1.0, (-800, -1000))
    pit_gate = math_node("GREATER_THAN", noise_tex(obj, 5.0, 2.0, 0.5, (-1000, -1200)), 0.45, (-800, -1200))
    pits = math_node("MULTIPLY", math_node("MULTIPLY", pits, pit_gate, (-600, -1000)), pits_amt, (-500, -1000))

    # colour: warm grey mineral body with mottling
    body_fac = noise_tex(obj, 3.0, 6.0, 0.65, (-1000, 1100))
    ramp = node(nt, "ShaderNodeValToRGB", (-800, 1100))
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[0].color = (*body_dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (*body_light, 1.0)
    nt.links.new(body_fac, ramp.inputs["Fac"])
    col = ramp.outputs["Color"]

    def mix_rgb(a, b_col, fac, loc):
        n = node(nt, "ShaderNodeMix", loc, data_type="RGBA", blend_type="MIX")
        nt.links.new(a, n.inputs["A"])
        if isinstance(b_col, tuple):
            set_input(n, "B", b_col)
        else:
            nt.links.new(b_col, n.inputs["B"])
        nt.links.new(fac, n.inputs["Factor"])
        return n.outputs["Result"]

    col = mix_rgb(col, (0.78, 0.78, 0.78, 1.0), veins, (0, 900))
    col = mix_rgb(col, (0.05, 0.045, 0.04, 1.0), math_node("MULTIPLY", crack, 0.9, (-200, 700)), (200, 900))
    col = mix_rgb(col, (0.07, 0.065, 0.06, 1.0), pits, (400, 900))
    col = mix_rgb(col, (0.06, 0.055, 0.05, 1.0), math_node("MULTIPLY", cavity, 0.7, (-200, 500)), (600, 900))
    col = mix_rgb(col, (0.52, 0.51, 0.50, 1.0), math_node("MULTIPLY", edge, 0.35, (-200, 350)), (800, 900))
    if ao > 0.0:
        ao_node = node(nt, "ShaderNodeAmbientOcclusion", (800, 1200))
        ao_node.samples = 8
        ao_node.only_local = True
        set_input(ao_node, "Distance", ao_distance)
        ao_fac = map_range(ao_node.outputs["AO"], 0.0, 1.0, 1.0 - ao, 1.0, (1000, 1200))
        ao_mix = node(nt, "ShaderNodeMix", (1200, 1000), data_type="RGBA", blend_type="MULTIPLY")
        set_input(ao_mix, "Factor", 1.0)
        nt.links.new(col, ao_mix.inputs["A"])
        ao_rgb = node(nt, "ShaderNodeCombineColor", (1100, 1100))
        for i in range(3):
            nt.links.new(ao_fac, ao_rgb.inputs[i])
        nt.links.new(ao_rgb.outputs["Color"], ao_mix.inputs["B"])
        col = ao_mix.outputs["Result"]
    nt.links.new(col, bsdf.inputs["Base Color"])

    # roughness: matte body, recesses rougher, edges and veins a touch smoother
    rough = map_range(cavity, 0.0, 1.0, rough_min, rough_max, (1000, 300))
    rough = math_node("SUBTRACT", rough, math_node("MULTIPLY", edge, 0.12, (1000, 150)), (1200, 300))
    rough = math_node("SUBTRACT", rough, math_node("MULTIPLY", veins, 0.15, (1000, 0)), (1400, 300))
    rough = math_node("ADD", rough, math_node("MULTIPLY", math_node("SUBTRACT", noise_tex(obj, 120.0, 2.0, 0.5, (1000, -200)), 0.5, (1200, -200)), 0.2, (1400, -200)), (1600, 300))
    nt.links.new(rough, bsdf.inputs["Roughness"])

    # displacement: facets and lumps, grain, veins slightly proud, cracks cut with lips, pits sunk
    facets = math_node("MULTIPLY", math_node("SUBTRACT", voronoi(obj, 11.0, "F1", (-1000, -1500)), 0.35, (-800, -1500)), 0.0, (-600, -1500))   # off, read as bubbly
    broad = math_node("MULTIPLY", math_node("SUBTRACT", noise_tex(obj, 6.0, 3.0, 0.5, (-1000, -1700)), 0.5, (-800, -1700)), 0.0007 * relief, (-600, -1700))
    grain = math_node("MULTIPLY", math_node("SUBTRACT", noise_tex(obj, 260.0, 2.0, 0.5, (-1000, -1900)), 0.5, (-800, -1900)), 0.0006, (-600, -1900))
    grain2 = math_node("MULTIPLY", math_node("SUBTRACT", noise_tex(obj, 80.0, 3.0, 0.6, (-1000, -2050)), 0.5, (-800, -2050)), 0.0007, (-600, -2050))
    grain = math_node("ADD", grain, grain2, (-500, -1950))
    grain = math_node("MULTIPLY", grain, grain_amt, (-400, -1950))
    grain = math_node("MULTIPLY", grain, map_range(edge, 0.0, 1.0, 1.0, 0.15, (-500, -2100)), (-300, -1950))
    total = math_node("ADD", facets, broad, (-400, -1600))
    total = math_node("ADD", total, grain, (-200, -1600))
    total = math_node("ADD", total, math_node("MULTIPLY", veins, 0.0007, (-200, -1400)), (0, -1600))
    total = math_node("ADD", total, math_node("MULTIPLY", big_crack, -0.0050, (-200, -1800)), (200, -1600))
    total = math_node("ADD", total, math_node("MULTIPLY", fine, -0.0012, (-200, -1900)), (300, -1600))
    total = math_node("ADD", total, math_node("MULTIPLY", lip, 0.0006, (-200, -2000)), (400, -1600))
    total = math_node("ADD", total, math_node("MULTIPLY", pits, -0.0030, (-200, -2200)), (600, -1600))
    total = math_node("ADD", total, math_node("MULTIPLY", math_node("MULTIPLY", edge, noise_tex(obj, 40.0, 2.0, 0.5, (-1000, -2400)), (-400, -2400)), -0.0045 * chips, (-200, -2400)), (800, -1600))
    disp = node(nt, "ShaderNodeDisplacement", (1600, -700))
    set_input(disp, "Midlevel", 0.0)
    set_input(disp, "Scale", 1.0)
    nt.links.new(total, disp.inputs["Height"])
    nt.links.new(disp.outputs["Displacement"], out.inputs["Displacement"])
    mat.displacement_method = "BOTH"    # the mesh is voxel dense, real displacement works
    return mat


# ------------------------------------------------------------------ measure
def measure(ob):
    """Outer diameter and stroke thickness of the O, from the built mesh, in metres."""
    me = ob.data
    ring_verts = set()
    for p in me.polygons:
        if p.material_index == 1:
            ring_verts.update(p.vertices)
    radii = [math.hypot(me.vertices[i].co.x, me.vertices[i].co.z) for i in ring_verts]
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
    key.data.energy = 95.0
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
    key.data.energy = 80.0
    if fill:
        fill.data.energy = 8.0
    results["raking"] = render_preview(scene, "04 logo raking light")
    # detail crop on the ring and the first letters
    crop_target = Vector((lo + O_DIAMETER * 0.85, centre.y, centre.z - O_DIAMETER * 0.05))
    cam.location = crop_target + Vector((0.12, -O_DIAMETER * 2.6, 0.10))
    look_at(cam, crop_target)
    cam.data.dof.focus_distance = (crop_target - cam.location).length
    results["detail"] = render_preview(scene, "04 logo detail crop")
    # the O straight on, close, lit from upper left so the chisel work shows
    o_centre = Vector((lo + O_DIAMETER / 2.0, centre.y, centre.z))
    cam.location = o_centre + Vector((0.0, -O_DIAMETER * 3.2, 0.0))
    look_at(cam, o_centre)
    cam.data.dof.focus_distance = (o_centre - cam.location).length
    key.location = o_centre + Vector((-0.5, -0.5, 0.6))
    look_at(key, o_centre)
    key.data.energy = 60.0
    results["O chisel"] = render_preview(scene, "04 logo O chisel")
    # the word Media, straight on, to check every letter carries cracks
    m_target = Vector((lo + width * 0.80, centre.y, centre.z - O_DIAMETER * 0.12))
    cam.location = m_target + Vector((0.0, -O_DIAMETER * 3.4, 0.0))
    look_at(cam, m_target)
    cam.data.dof.focus_distance = (m_target - cam.location).length
    key.location = m_target + Vector((-0.6, -0.7, 0.7))
    look_at(key, m_target)
    key.data.energy = 70.0
    results["Media"] = render_preview(scene, "04 logo Media crop")
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
    # letters: stone grey, cracks only (no veins), cracks wide enough to read at hero distance
    mat = build_stone_material("MAT.stone", cracks=1.0, veins_amt=0.0, pits_amt=0.7, chips=0.10, grain_amt=0.5, ao=0.35,
                               body_dark=(0.17, 0.172, 0.18), body_light=(0.46, 0.465, 0.48), rough_min=0.80, rough_max=0.95, specular=0.2)
    # the ring after the client's design render: polished dark grey face, all the depth in the recesses
    ring_mat = build_stone_material("MAT.stone ring", cracks=0.0, veins_amt=0.0, pits_amt=0.0, chips=0.0, grain_amt=0.06, ao=0.9,
                                    body_dark=(0.07, 0.075, 0.085), body_light=(0.20, 0.21, 0.23), rough_min=0.24, rough_max=0.50,
                                    coat=0.35, specular=0.5, ao_distance=0.03, relief=0.0)
    # never clear() here: clearing material slots zeroes every face's material index
    for i, m in enumerate((mat, ring_mat)):
        if len(logo.data.materials) > i:
            logo.data.materials[i] = m
        else:
            logo.data.materials.append(m)
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
          f"{eval_counts[0]} verts, {eval_counts[1]} faces evaluated (voxel remeshed, letters {VOXEL_LETTERS * 1000:.1f} mm, ring {VOXEL_RING * 1000:.1f} mm), built in {build_time:.1f} s")
    print(f"  O outer diameter: {diameter:.4f} m")
    print(f"  O ring stroke thickness: {stroke:.4f} m (inner radius {radii[0]:.4f} m, outer radius {radii[1]:.4f} m)")
    print(f"  ring source: {RING_FILE} / {RING_OBJECT}")
    print(f"  letters '{LETTERS}' width {letters_width:.4f} m, font {font_path}")
    print(f"  stone depth {DEPTH:.3f} m, whole mark {dims.x:.3f} x {dims.z:.3f} m, location {tuple(round(c, 3) for c in logo.location)}")
    print(f"  stone cast: warm grey mineral body (linear 0.16 to 0.40) with white calcite veins, sharp corners, no erosion")
    for k, (path, dt) in results.items():
        print(f"  render {k}: {dt:.1f} s -> {path}")
    print("=================================")


main()
