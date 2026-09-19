"""02 fabric and seams.py

OVM Hat Hero, phase one, step 1B.

Operates on the existing HAT.base. Builds:
  MAT.fabric black   black cotton twill, sheen layer, weave micro bump
  MAT.thread bone    embroidery and topstitch thread for the four role hats
  MAT.thread gold    embroidery and topstitch thread for the founder hat
  STITCH.seam        real topstitch geometry along the six panel seams and
                     the brim edge, parented to HAT.base

Renders three 800 px previews: full hat, tight crop on a panel seam, and a
raking light shot that shows the weave. Reports render time for each.

Idempotent. Removes and rebuilds every object and material it owns by name.
"""
import bpy
import bmesh
import math
import os
import random
import time
from mathutils import Vector

SCRIPT = "02 fabric and seams"

# ---------------------------------------------------------------- parameters
FABRIC_BASE = (0.016, 0.0155, 0.015)   # linear, not pure black
FABRIC_ROUGH_MIN = 0.72
FABRIC_ROUGH_MAX = 0.86
SHEEN_WEIGHT = 0.18
SHEEN_ROUGHNESS = 0.30
SHEEN_TINT = (1.0, 0.96, 0.90, 1.0)    # very slightly warm
WEAVE_PERIOD = 0.0005                   # metres per thread, about 20 threads per cm
WEAVE_BUMP_STRENGTH = 0.07   # kept low, the weave is sub pixel at hero distance and a strong bump moires

BONE = (0.760, 0.700, 0.580, 1.0)       # linear, about #E3DAC9 in sRGB
GOLD = (0.640, 0.360, 0.045, 1.0)       # linear, warm rayon gold, not a metal

STITCH_LENGTH = 0.0032                  # one stitch, thread visible on top
STITCH_GAP = 0.0008                     # thread goes under the fabric here
THREAD_WIDTH = 0.00062                  # a little flattened
THREAD_HEIGHT = 0.00042
THREAD_LIFT = 0.00060                   # centre of the thread above the fabric
SEAM_ROW_OFFSET = 0.0027                # two rows straddle each seam
SEAM_Z_START = 0.014                    # above the band
SEAM_TOP_STOP = 0.008                   # stop just short of the button
BRIM_ROWS = [0.005 + 0.0055 * i for i in range(4)]  # four topstitch rows in from the brim edge
JITTER_SPACING = 0.10                   # fraction of stitch length
JITTER_HEIGHT = 0.12
JITTER_SIDE = 0.00012                   # metres
RING_SEGMENTS = 6
RINGS_PER_STITCH = 5
SEED = 7

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
    if data is not None and data.users == 0 and isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)


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


def look_at(ob, target):
    direction = Vector(target) - ob.location
    ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


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


# --------------------------------------------------------------- materials
def build_fabric_material():
    mat = new_material("MAT.fabric black")
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", (900, 0))
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", (600, 0))
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    set_input(bsdf, "Base Color", (*FABRIC_BASE, 1.0))
    set_input(bsdf, "Metallic", 0.0)
    set_input(bsdf, "Specular IOR Level", 0.35)
    set_input(bsdf, "Sheen Weight", SHEEN_WEIGHT)
    set_input(bsdf, "Sheen Roughness", SHEEN_ROUGHNESS)
    set_input(bsdf, "Sheen Tint", SHEEN_TINT)

    coords = node(nt, "ShaderNodeTexCoord", (-900, 0))

    # roughness variation at a scale that survives render distance (a few cm)
    rough_noise = node(nt, "ShaderNodeTexNoise", (-500, 300))
    set_input(rough_noise, "Scale", 35.0)
    set_input(rough_noise, "Detail", 4.0)
    set_input(rough_noise, "Roughness", 0.6)
    nt.links.new(coords.outputs["Object"], rough_noise.inputs["Vector"])
    rough_map = node(nt, "ShaderNodeMapRange", (-200, 300))
    set_input(rough_map, "From Min", 0.35)
    set_input(rough_map, "From Max", 0.65)
    set_input(rough_map, "To Min", FABRIC_ROUGH_MIN)
    set_input(rough_map, "To Max", FABRIC_ROUGH_MAX)
    nt.links.new(rough_noise.outputs["Fac"], rough_map.inputs["Value"])
    nt.links.new(rough_map.outputs["Result"], bsdf.inputs["Roughness"])

    # subtle base colour variation, keeps the black from going flat
    col_map = node(nt, "ShaderNodeMapRange", (-200, 520))
    set_input(col_map, "From Min", 0.3)
    set_input(col_map, "From Max", 0.7)
    set_input(col_map, "To Min", 0.85)
    set_input(col_map, "To Max", 1.15)
    nt.links.new(rough_noise.outputs["Fac"], col_map.inputs["Value"])
    col_mix = node(nt, "ShaderNodeMix", (150, 520), data_type="RGBA", blend_type="MULTIPLY")
    set_input(col_mix, "Factor", 1.0)
    set_input(col_mix, "A", (*FABRIC_BASE, 1.0))
    nt.links.new(col_map.outputs["Result"], col_mix.inputs["B"])
    nt.links.new(col_mix.outputs["Result"], bsdf.inputs["Base Color"])

    # weave, two wave textures crossed at 90 degrees, as a micro bump
    wave_scale = (2.0 * math.pi / 10.0) / WEAVE_PERIOD
    wave_a = node(nt, "ShaderNodeTexWave", (-500, -100), wave_type="BANDS", bands_direction="X")
    wave_b = node(nt, "ShaderNodeTexWave", (-500, -400), wave_type="BANDS", bands_direction="Y")
    for w in (wave_a, wave_b):
        set_input(w, "Scale", wave_scale)
        set_input(w, "Distortion", 1.5)
        set_input(w, "Detail", 1.0)
        nt.links.new(coords.outputs["Object"], w.inputs["Vector"])
    weave = node(nt, "ShaderNodeMath", (-200, -250), operation="ADD")
    nt.links.new(wave_a.outputs["Fac"], weave.inputs[0])
    nt.links.new(wave_b.outputs["Fac"], weave.inputs[1])
    weave_half = node(nt, "ShaderNodeMath", (0, -250), operation="MULTIPLY")
    set_input(weave_half, 1, 0.5)
    nt.links.new(weave.outputs["Value"], weave_half.inputs[0])
    # broader fabric wrinkle relief so the surface is not a perfect solid
    wrinkle = node(nt, "ShaderNodeTexNoise", (-500, -650))
    set_input(wrinkle, "Scale", 9.0)
    set_input(wrinkle, "Detail", 3.0)
    nt.links.new(coords.outputs["Object"], wrinkle.inputs["Vector"])
    relief = node(nt, "ShaderNodeMath", (150, -400), operation="ADD")
    nt.links.new(weave_half.outputs["Value"], relief.inputs[0])
    nt.links.new(wrinkle.outputs["Fac"], relief.inputs[1])
    bump = node(nt, "ShaderNodeBump", (350, -250))
    set_input(bump, "Strength", WEAVE_BUMP_STRENGTH)
    set_input(bump, "Distance", 0.0004)
    nt.links.new(relief.outputs["Value"], bump.inputs["Height"])

    # the purchased cap ships a twill diffuse and normal map. Use the normal
    # map for the weave relief and the diffuse (desaturated, low contrast) as
    # tone variation. The colour stays our black, nothing painted shows.
    normal_img = bpy.data.images.get("baseball_cap_texture_NORM.jpg")
    diffuse_img = bpy.data.images.get("baseball_cap_texture.jpg")
    if normal_img is not None:
        uv = node(nt, "ShaderNodeUVMap", (-900, -900), uv_map="UVMap")
        ntex = node(nt, "ShaderNodeTexImage", (-650, -900))
        ntex.image = normal_img
        normal_img.colorspace_settings.name = "Non-Color"
        nt.links.new(uv.outputs["UV"], ntex.inputs["Vector"])
        nmap = node(nt, "ShaderNodeNormalMap", (-350, -900), uv_map="UVMap")
        set_input(nmap, "Strength", 0.20)
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bump.inputs["Normal"])
    if diffuse_img is not None:
        uv2 = node(nt, "ShaderNodeUVMap", (-900, 750), uv_map="UVMap")
        dtex = node(nt, "ShaderNodeTexImage", (-650, 750))
        dtex.image = diffuse_img
        nt.links.new(uv2.outputs["UV"], dtex.inputs["Vector"])
        tone = node(nt, "ShaderNodeMapRange", (-400, 750))
        set_input(tone, "From Min", 0.25)
        set_input(tone, "From Max", 0.75)
        set_input(tone, "To Min", 0.96)
        set_input(tone, "To Max", 1.04)
        nt.links.new(dtex.outputs["Color"], tone.inputs["Value"])
        tone_mix = node(nt, "ShaderNodeMix", (400, 600), data_type="RGBA", blend_type="MULTIPLY")
        set_input(tone_mix, "Factor", 1.0)
        nt.links.new(col_mix.outputs["Result"], tone_mix.inputs["A"])
        tone_rgb = node(nt, "ShaderNodeCombineColor", (200, 700))
        for i in range(3):
            nt.links.new(tone.outputs["Result"], tone_rgb.inputs[i])
        nt.links.new(tone_rgb.outputs["Color"], tone_mix.inputs["B"])
        nt.links.new(tone_mix.outputs["Result"], bsdf.inputs["Base Color"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mat.displacement_method = "BUMP"
    return mat


def build_thread_material(name, color, roughness, specular, coat):
    mat = new_material(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", (700, 0))
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", (400, 0))
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    set_input(bsdf, "Base Color", color)
    set_input(bsdf, "Metallic", 0.0)               # never a metal, rayon thread
    set_input(bsdf, "Roughness", roughness)
    set_input(bsdf, "Specular IOR Level", specular)
    set_input(bsdf, "Anisotropic", 0.75)          # sheen runs along the thread
    set_input(bsdf, "Anisotropic Rotation", 0.0)
    set_input(bsdf, "Sheen Weight", 0.35)
    set_input(bsdf, "Sheen Roughness", 0.25)
    set_input(bsdf, "Coat Weight", coat)
    set_input(bsdf, "Coat Roughness", 0.15)
    tangent = node(nt, "ShaderNodeTangent", (100, -300), direction_type="UV_MAP", uv_map="UVMap")
    nt.links.new(tangent.outputs["Tangent"], bsdf.inputs["Tangent"])
    # filaments, a fine stripe along the thread as a bump
    uv = node(nt, "ShaderNodeUVMap", (-500, -100), uv_map="UVMap")
    wave = node(nt, "ShaderNodeTexWave", (-250, -100), wave_type="BANDS", bands_direction="Y")
    set_input(wave, "Scale", 3.0)
    set_input(wave, "Distortion", 0.4)
    nt.links.new(uv.outputs["UV"], wave.inputs["Vector"])
    bump = node(nt, "ShaderNodeBump", (50, -100))
    set_input(bump, "Strength", 0.25)
    set_input(bump, "Distance", 0.0001)
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# ------------------------------------------------------------ stitch builder
class Snapper:
    """Ray casts against the evaluated HAT.base so stitches sit on the real surface."""

    def __init__(self, hat):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        self.ob = hat.evaluated_get(depsgraph)
        self.centre = Vector((0.0, 0.0, 0.04))

    def from_outside(self, point, normal=None):
        """Cast onto the outer surface from a little way out along the given outward normal.

        Without a normal, falls back to the direction from the crown centre."""
        if normal is None:
            d = (Vector(point) - self.centre).normalized()
        else:
            d = Vector(normal).normalized()
        origin = Vector(point) + d * 0.03
        hit, loc, normal_out, _ = self.ob.ray_cast(origin, -d, distance=0.09)
        if not hit:
            return None
        return loc.copy(), normal_out.copy()

    def along(self, point, direction, back=0.02):
        """Cast along a direction from a little behind the point."""
        d = Vector(direction).normalized()
        origin = Vector(point) - d * back
        hit, loc, normal, _ = self.ob.ray_cast(origin, d, distance=max(back * 3.0, 0.4))
        if not hit:
            return None
        return loc.copy(), normal.copy()


def resample(points, step, extra=None):
    """Uniform arc length resample of a polyline.

    Returns the resampled positions, or (positions, extras) when extra is a
    matching list of vectors to interpolate alongside, such as normals."""
    if len(points) < 2:
        return ([], []) if extra is not None else []
    lengths = [0.0]
    for a, b in zip(points, points[1:]):
        lengths.append(lengths[-1] + (b - a).length)
    total = lengths[-1]
    out = []
    out_extra = []
    s = 0.0
    j = 0
    while s <= total:
        while j < len(lengths) - 2 and lengths[j + 1] < s:
            j += 1
        seg = lengths[j + 1] - lengths[j]
        f = 0.0 if seg == 0 else (s - lengths[j]) / seg
        out.append(points[j].lerp(points[j + 1], f))
        if extra is not None:
            out_extra.append(extra[j].lerp(extra[j + 1], f).normalized())
        s += step
    return (out, out_extra) if extra is not None else out


class StitchMesh:
    def __init__(self, seed):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.rng = random.Random(seed)
        self.count = 0

    def add_stitch(self, p0, n0, p1, n1, side0, side1):
        """One stitch from p0 to p1 on the surface. Sides are the across thread directions."""
        rng = self.rng
        height_scale = 1.0 + rng.uniform(-JITTER_HEIGHT, JITTER_HEIGHT)
        rings = []
        for k in range(RINGS_PER_STITCH):
            t = k / (RINGS_PER_STITCH - 1)
            p = p0.lerp(p1, t)
            n = n0.lerp(n1, t).normalized()
            side = side0.lerp(side1, t).normalized()
            # ends dip into the fabric, the middle rides on top
            lift = -0.00012 + (THREAD_LIFT + 0.00012) * (math.sin(math.pi * t) ** 0.55) * height_scale
            centre = p + n * lift
            ring = []
            for m in range(RING_SEGMENTS):
                a = 2.0 * math.pi * m / RING_SEGMENTS
                offset = side * (math.cos(a) * THREAD_WIDTH * 0.5) + n * (math.sin(a) * THREAD_HEIGHT * 0.5)
                ring.append((self.bm.verts.new(centre + offset), t, m / RING_SEGMENTS))
            rings.append(ring)
        for a, b in zip(rings, rings[1:]):
            for m in range(RING_SEGMENTS):
                k = (m + 1) % RING_SEGMENTS
                f = self.bm.faces.new((a[m][0], a[k][0], b[k][0], b[m][0]))
                for loop, (_, t, v) in zip(f.loops, (a[m], a[k], b[k], b[m])):
                    loop[self.uv].uv = (t, v)
        for ring, flip in ((rings[0], True), (rings[-1], False)):
            verts = [r[0] for r in ring]
            if flip:
                verts.reverse()
            f = self.bm.faces.new(verts)
            for loop in f.loops:
                loop[self.uv].uv = (ring[0][1], 0.5)
        self.count += 1

    def add_row(self, samples, snap, snap_dir=None, normals=None):
        """samples: list of surface positions along a row. Places stitches along it.

        normals: optional outward normals matching samples, used for the snap cast."""
        pitch = STITCH_LENGTH + STITCH_GAP
        if normals:
            pts, nrm = resample(samples, 0.0005, extra=normals)
        else:
            pts, nrm = resample(samples, 0.0005), None
        if len(pts) < 4:
            return 0
        snapped = []
        for i, p in enumerate(pts):
            if snap_dir is not None:
                r = snap.along(p, snap_dir)
            else:
                r = snap.from_outside(p, nrm[i] if nrm and i < len(nrm) else None)
            snapped.append(r)
        s = self.rng.uniform(0.0, pitch)
        placed = 0
        i = 0
        total = 0.0005 * (len(pts) - 1)
        while s + STITCH_LENGTH < total:
            jitter = self.rng.uniform(-JITTER_SPACING, JITTER_SPACING) * STITCH_LENGTH
            a = s + jitter * 0.5
            b = a + STITCH_LENGTH * (1.0 + self.rng.uniform(-0.06, 0.06))
            ia = min(len(pts) - 1, max(0, int(round(a / 0.0005))))
            ib = min(len(pts) - 1, max(0, int(round(b / 0.0005))))
            if ia != ib and snapped[ia] and snapped[ib]:
                (pa, na), (pb, nb) = snapped[ia], snapped[ib]
                along = (pb - pa).normalized()
                side_a = na.cross(along).normalized()
                side_b = nb.cross(along).normalized()
                wobble = self.rng.uniform(-JITTER_SIDE, JITTER_SIDE)
                self.add_stitch(pa + side_a * wobble, na, pb + side_b * wobble, nb, side_a, side_b)
                placed += 1
            s += pitch
        return placed

    def to_object(self, name, col, material):
        remove_object(name)
        old = bpy.data.meshes.get(name)
        if old is not None and old.users == 0:
            bpy.data.meshes.remove(old)
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        me.shade_smooth()
        me.materials.append(material)
        ob = bpy.data.objects.new(name, me)
        link(ob, col)
        return ob


def group_vertices(ob, group_name):
    vg = ob.vertex_groups.get(group_name)
    if vg is None:
        raise RuntimeError(f"{SCRIPT}: HAT.base has no vertex group '{group_name}'")
    return [v for v in ob.data.vertices if any(g.group == vg.index for g in v.groups)]


def seam_paths(hat, group_name="seam"):
    """Walk the marked seam edges among a vertex group into polylines.

    Returns a list of paths, each a list of (position, normal) in object space,
    split at junctions so every path is a single run of stitching."""
    me = hat.data
    vg = hat.vertex_groups[group_name]
    in_group = {v.index for v in me.vertices if any(g.group == vg.index for g in v.groups)}
    adj = {}
    for e in me.edges:
        a, b = e.vertices
        if e.use_seam and a in in_group and b in in_group:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    if not adj:
        # procedural cap: no marked seams, fall back to grouping by angle around the crown
        return None
    used = set()
    paths = []
    ends = [v for v, n in adj.items() if len(n) != 2] or [next(iter(adj))]
    for start in ends:
        for nxt in adj[start]:
            edge = (min(start, nxt), max(start, nxt))
            if edge in used:
                continue
            path = [start, nxt]
            used.add(edge)
            prev, cur = start, nxt
            while len(adj[cur]) == 2:
                a, b = adj[cur]
                following = a if b == prev else b
                edge = (min(cur, following), max(cur, following))
                if edge in used:
                    break
                used.add(edge)
                path.append(following)
                prev, cur = cur, following
            paths.append([(me.vertices[i].co.copy(), me.vertices[i].normal.copy()) for i in path])
    return paths


def build_seam_stitches(hat, col, material):
    snap = Snapper(hat)
    stitches = StitchMesh(SEED)
    top_z = max(v.co.z for v in hat.data.vertices)
    placed = 0
    rows = 0
    paths = seam_paths(hat)
    if paths is not None:
        # no stitching up the centre front: drop any path that runs there
        def is_centre_front(path):
            xs = sorted(abs(p.x) for p, _ in path)
            return xs[len(xs) // 2] < 0.012 and min(p.y for p, _ in path) < -0.05
        paths = [path for path in paths if not is_centre_front(path)]
        # the model's marked seams on the two front side panels start part way up.
        # Extend any tall seam that begins above the band down to the band.
        me = hat.data
        band = [v.co for v in me.vertices if math.hypot(v.co.x, v.co.y) < 0.155 and v.co.z < 0.03]
        cx = sum(c.x for c in band) / len(band)
        cy = sum(c.y for c in band) / len(band)
        rb = sum(math.hypot(c.x - cx, c.y - cy) for c in band) / len(band)
        extended = []
        for path in paths:
            zs = [p.z for p, _ in path]
            if max(zs) > 0.15 and min(zs) > 0.03:
                path = sorted(path, key=lambda pn: pn[0].z)
                p0, n0 = path[0]
                ang = math.atan2(p0.x - cx, -(p0.y - cy))
                base = Vector((cx + rb * math.sin(ang), cy - rb * math.cos(ang), SEAM_Z_START))
                steps = max(2, int((p0 - base).length / 0.01))
                prefix = [(base.lerp(p0, k / steps), n0) for k in range(steps)]
                path = prefix + path
            extended.append(path)
        paths = extended
    if paths is None:
        seam_verts = group_vertices(hat, "seam")
        seams = {}
        pole_z = max(v.co.z for v in seam_verts)
        for v in seam_verts:
            co = v.co
            if co.z >= pole_z - 1e-6:
                continue
            ang = math.degrees(math.atan2(co.x, -co.y)) % 360.0
            key = int(round(ang / 60.0)) % 6
            seams.setdefault(key, []).append((co.copy(), v.normal.copy()))
        paths = [sorted(seams[k], key=lambda c: c[0].z) for k in sorted(seams)]
        paths = [[(p, n) for (p, n) in path if SEAM_Z_START <= p.z <= top_z - SEAM_TOP_STOP] for path in paths]
    for pts in paths:
        length = sum((b[0] - a[0]).length for a, b in zip(pts, pts[1:]))
        if length < 0.025:
            continue
        # stop short of the button on paths that reach the top
        pts = [(p, n) for (p, n) in pts if p.z <= top_z - SEAM_TOP_STOP]
        if len(pts) < 2:
            continue
        # snap the seam polyline to the outer surface
        surface = []
        for p, n in pts:
            r = snap.from_outside(p, n)
            if r:
                surface.append(r)
        if len(surface) < 2:
            continue
        # a level path (the band seam) gets one row, a panel seam gets two
        zs = [p.z for p, _ in surface]
        signs = (0.0,) if (max(zs) - min(zs)) < 0.02 else (-1.0, 1.0)
        for sign in signs:
            row = []
            row_n = []
            for i, (p, n) in enumerate(surface):
                nxt = surface[min(i + 1, len(surface) - 1)][0]
                prv = surface[max(i - 1, 0)][0]
                along = (nxt - prv).normalized()
                side = n.cross(along).normalized()
                row.append(p + side * SEAM_ROW_OFFSET * sign)
                row_n.append(n)
            placed += stitches.add_row(row, snap, normals=row_n)
            rows += 1
    # brim topstitch rows, measured in from the brim edge. The outline comes from
    # the cap's own marked brim seam, walked in order, and each row is inset
    # along the outline's in plane normal so it follows the real shape.
    brim_rows = 0
    outline_paths = seam_paths(hat, "brim edge")
    if outline_paths:
        outline = max(outline_paths, key=lambda p: sum((b[0] - a[0]).length for a, b in zip(p, p[1:])))
        pts = [p for p, _ in outline]
        # drop points sitting on the crown itself
        pts = [p for p in pts if math.hypot(p.x, p.y) > 0.150]
    else:
        edge = group_vertices(hat, "brim edge")
        pts = sorted((v.co.copy() for v in edge), key=lambda c: math.atan2(c.x, -c.y))
    if len(pts) > 3:
        brim_top = max(p.z for p in pts) + 0.05
        # the crown footprint at the brim root, per angle, so rows can be clipped where the brim runs out
        me = hat.data
        root = [v.co for v in me.vertices if v.co.z < 0.02 and 0.10 < math.hypot(v.co.x, v.co.y) < 0.165]
        def crown_radius_at(ang):
            near = [math.hypot(c.x, c.y) for c in root if abs((math.atan2(c.x, -c.y) - ang + math.pi) % (2 * math.pi) - math.pi) < 0.12]
            return max(near) if near else 0.150
        # outer curve only: the front facing points, dropped where the brim is nearly zero width
        outer = []
        for p in pts:
            ang = math.atan2(p.x, -p.y)
            if abs(ang) < math.radians(95) and math.hypot(p.x, p.y) - crown_radius_at(ang) > 0.004:
                outer.append(p)
        outer.sort(key=lambda c: math.atan2(c.x, -c.y))
        for inset in BRIM_ROWS:
            row = []
            for i, p in enumerate(outer):
                nxt = outer[min(i + 1, len(outer) - 1)]
                prv = outer[max(i - 1, 0)]
                along = Vector((nxt.x - prv.x, nxt.y - prv.y, 0.0))
                if along.length < 1e-9:
                    continue
                along.normalize()
                normal = Vector((-along.y, along.x, 0.0))
                if normal.dot(Vector((-p.x, -p.y, 0.0))) < 0.0:
                    normal = -normal          # point toward the crown axis
                q = p + normal * inset
                # clip: the row stops where the brim is not wide enough for this inset
                if math.hypot(q.x, q.y) - crown_radius_at(math.atan2(q.x, -q.y)) < 0.005:
                    continue
                row.append(q)
            if len(row) < 4:
                continue
            dense = resample(row, 0.0005)
            surface = []
            for p in dense:
                r = snap.along(Vector((p.x, p.y, brim_top)), (0.0, 0.0, -1.0), back=0.0)
                if r and r[1].z > 0.35 and math.hypot(r[0].x, r[0].y) > 0.150:
                    surface.append(r[0])
            if len(surface) > 3:
                placed += stitches.add_row(surface, snap, snap_dir=(0.0, 0.0, -1.0))
                brim_rows += 1
    ob = stitches.to_object("STITCH.seam", col, material)
    ob.parent = hat
    ob.matrix_parent_inverse = hat.matrix_world.inverted()
    return ob, placed, rows, brim_rows


# ------------------------------------------------------------------ renders
def pixel_footprint(scene, cam, hat):
    """Metres per pixel on the hat at the current preview size, computed from the camera."""
    dist = (cam.location - hat.matrix_world.translation).length
    frame_width_m = dist * cam.data.sensor_width / cam.data.lens
    return frame_width_m / PREVIEW_WIDTH


def render_set(scene, cam, hat, key):
    results = {}
    scene.camera = cam
    results["full"] = render_preview(scene, "02 fabric full hat")

    # tight crop on a panel seam
    saved = (cam.location.copy(), cam.rotation_euler.copy(), cam.data.lens, cam.data.dof.focus_distance)
    cam.location = Vector((0.22, -0.46, 0.34))
    target = Vector((0.0, -0.13, 0.16))
    look_at(cam, target)
    cam.data.lens = 100.0
    fstop_saved = cam.data.dof.aperture_fstop
    cam.data.dof.aperture_fstop = 11.0
    cam.data.dof.focus_distance = (target - cam.location).length
    results["seam"] = render_preview(scene, "02 fabric seam crop")

    # raking light on the weave, key swung low and to the side, others down
    key_saved = (key.location.copy(), key.rotation_euler.copy(), key.data.energy)
    fill = bpy.data.objects.get("LIGHT.fill")
    rim = bpy.data.objects.get("LIGHT.rim")
    others = [(o, o.data.energy) for o in (fill, rim) if o]
    for o, _ in others:
        o.data.energy *= 0.15
    key.location = Vector((0.95, -0.30, 0.22))
    look_at(key, target)
    key.data.energy = key_saved[2] * 1.5
    results["raking"] = render_preview(scene, "02 fabric raking light")

    key.location, key.rotation_euler, key.data.energy = key_saved
    for o, e in others:
        o.data.energy = e
    cam.location, cam.rotation_euler, cam.data.lens, cam.data.dof.focus_distance = saved
    cam.data.dof.aperture_fstop = fstop_saved
    return results


def main():
    global WORK
    WORK = workdir()
    scene = bpy.context.scene
    print(f"\n[{SCRIPT}] working folder: {WORK}")
    hat = require("HAT.base")
    cam = require("CAM.hero")
    key = require("LIGHT.key")

    fabric = build_fabric_material()
    bone = build_thread_material("MAT.thread bone", BONE, roughness=0.32, specular=0.65, coat=0.15)
    gold = build_thread_material("MAT.thread gold", GOLD, roughness=0.22, specular=0.85, coat=0.35)
    metal = bpy.data.materials.get("MAT.eyelet black")
    hat.data.materials.clear()
    hat.data.materials.append(fabric)
    if metal is not None:
        hat.data.materials.append(metal)     # slot 1, the eyelet grommets

    # black fabric needs more light than the grey placeholder did
    key.data.energy = 9.0
    fill = bpy.data.objects.get("LIGHT.fill")
    rim = bpy.data.objects.get("LIGHT.rim")
    if fill:
        fill.data.energy = 3.0
    if rim:
        rim.data.energy = 110.0

    t0 = time.time()
    stitch, placed, rows, brim_rows = build_seam_stitches(hat, collection("Hats"), bone)
    build_time = time.time() - t0
    results = render_set(scene, cam, hat, key)

    footprint = pixel_footprint(scene, cam, hat)
    print("")
    print(f"==== {SCRIPT} runtime report ====")
    print(f"  scene objects: {len(scene.objects)}")
    print(f"  STITCH.seam: {placed} stitches in {rows} seam rows and {brim_rows} brim rows, "
          f"{len(stitch.data.vertices)} verts, {len(stitch.data.polygons)} faces, built in {build_time:.1f} s")
    print(f"  HAT.base material: {hat.data.materials[0].name}")
    print(f"  weave period {WEAVE_PERIOD * 1000:.2f} mm, pixel footprint on the hat at {PREVIEW_WIDTH} px: {footprint * 1000:.2f} mm per px, "
          f"{'weave is sub pixel, bump only' if WEAVE_PERIOD < footprint else 'weave is resolvable'}")
    for k, (path, dt) in results.items():
        print(f"  render {k}: {dt:.1f} s -> {path}")
    print("=================================")


main()
