"""03 lettering.py

OVM Hat Hero, phase one, step 1C.

Embroidered lettering on the front two panels of HAT.base. One object per
word, STITCH.letters.<name>, each a satin stitch fill built from real thread
geometry, wrapped onto the curve of the crown, with underlay puff and a few
percent of irregularity. Bone thread for the four role words, gold for
FOUNDER. Metalness stays at zero everywhere.

All five words sit at one point size. Widths differ, that is intended.

Renders one 800 px preview per hat plus one tight crop on the gold at
raking light.

Idempotent. Removes and rebuilds the five lettering objects by name.
"""
import bpy
import bmesh
import math
import os
import random
import time
from mathutils import Vector

SCRIPT = "03 lettering"

WORDS = [
    ("socials", "SOCIALS", "MAT.thread bone"),
    ("content", "CONTENT", "MAT.thread bone"),
    ("website", "WEBSITE", "MAT.thread bone"),
    ("branding", "BRANDING", "MAT.thread bone"),
    ("founder", "FOUNDER", "MAT.thread gold"),
]

# ---------------------------------------------------------------- parameters
CAP_HEIGHT = 0.022          # metres, letter height on the panel
TRACKING = 1.06             # a little extra letter spacing, embroidery needs air
LETTER_Z = 0.150            # centre height of the word on the crown (the purchased cap's crown is 0.27 m tall)
STITCH_ANGLE = math.radians(12.0)   # satin fill direction, from horizontal
PITCH = 0.00046             # thread to thread spacing
THREAD_WIDTH = 0.00050
THREAD_HEIGHT = 0.00036
LIFT = 0.00055              # underlay, thread centre above the fabric
PUFF = 0.00040              # extra height in the middle of each stroke
SATIN_MAX = 0.0075          # split longer spans, as a machine does
MIN_RUN = 0.00035
JITTER_PITCH = 0.06         # fraction of pitch
JITTER_HEIGHT = 0.05
RINGS = 7
RING_SEGMENTS = 6
SEED = 11

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\ARIALBD.TTF",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

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


def require_material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        raise RuntimeError(f"{SCRIPT}: required material '{name}' is missing. Run 02 fabric and seams first.")
    return mat


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


# ---------------------------------------------------------------- text fill
def load_font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            font = bpy.data.fonts.load(path, check_existing=True)
            return font, path
    return bpy.data.fonts.get("Bfont Regular") or bpy.data.fonts[0], "Blender built in font"


def text_triangles(word, font):
    """Flat 2D triangles (lists of 3 Vectors) of the filled word, centred at the origin."""
    curve = bpy.data.curves.new(f"TMP.text.{word}", "FONT")
    curve.body = word
    curve.font = font
    curve.size = CAP_HEIGHT             # rescaled to the measured height below
    curve.space_character = TRACKING
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.fill_mode = "FRONT"
    ob = bpy.data.objects.new(f"TMP.text.{word}", curve)
    bpy.context.scene.collection.objects.link(ob)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(depsgraph)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    verts = [Vector((v.co.x, v.co.y)) for v in me.vertices]
    tris = [[verts[i] for i in tri.vertices] for tri in me.loop_triangles]
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(curve)
    # measure, then scale so the capitals are exactly CAP_HEIGHT tall, and
    # recentre on the true bounds so every word shares one centre line
    xs = [p.x for t in tris for p in t]
    ys = [p.y for t in tris for p in t]
    measured = max(ys) - min(ys)
    k = CAP_HEIGHT / measured
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    tris = [[Vector(((p.x - cx) * k, (p.y - cy) * k)) for p in t] for t in tris]
    return tris, ((max(xs) - min(xs)) * k, measured * k)


def satin_runs(tris, angle, pitch, rng):
    """Scan the filled shape with parallel lines. Returns list of (start, end) 2D points."""
    d = Vector((math.cos(angle), math.sin(angle)))
    n = Vector((-d.y, d.x))
    offsets = [(p.dot(n)) for t in tris for p in t]
    lo, hi = min(offsets), max(offsets)
    runs = []
    o = lo + pitch * 0.5
    while o < hi:
        oj = o + rng.uniform(-JITTER_PITCH, JITTER_PITCH) * pitch
        intervals = []
        for t in tris:
            s = [(p.dot(n) - oj) for p in t]
            if (s[0] > 0 and s[1] > 0 and s[2] > 0) or (s[0] < 0 and s[1] < 0 and s[2] < 0):
                continue
            ts = []
            for i in range(3):
                a, b = t[i], t[(i + 1) % 3]
                sa, sb = s[i], s[(i + 1) % 3]
                if (sa <= 0 < sb) or (sb <= 0 < sa):
                    f = sa / (sa - sb)
                    x = a.lerp(b, f)
                    ts.append(x.dot(d))
            if len(ts) >= 2:
                intervals.append((min(ts), max(ts)))
        if intervals:
            intervals.sort()
            merged = [list(intervals[0])]
            for a, b in intervals[1:]:
                if a <= merged[-1][1] + 1e-6:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            for a, b in merged:
                length = b - a
                if length < MIN_RUN:
                    continue
                pieces = max(1, int(math.ceil(length / SATIN_MAX)))
                step = length / pieces
                for k in range(pieces):
                    pa = a + k * step + (0.00008 if k > 0 else 0.0)
                    pb = a + (k + 1) * step - (0.00008 if k < pieces - 1 else 0.0)
                    runs.append((n * oj + d * pa, n * oj + d * pb))
        o += pitch
    return runs


# ----------------------------------------------------------- wrap on crown
class CrownMapper:
    """Maps flat word coordinates (u across, v up) onto the front of the evaluated HAT.base."""

    def __init__(self, hat):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        self.ob = hat.evaluated_get(depsgraph)
        # reference radius at the lettering height, found by casting at the centre front
        r = self.cast(0.0, LETTER_Z)
        if r is None:
            raise RuntimeError(f"{SCRIPT}: cannot find the crown surface at the lettering height")
        p, _ = r
        self.radius = math.hypot(p.x, p.y)

    def cast(self, phi, z):
        d = Vector((math.sin(phi), -math.cos(phi), 0.0))
        origin = Vector((0.0, 0.0, z)) + d * 0.5
        hit, loc, normal, _ = self.ob.ray_cast(origin, -d, distance=0.5)
        if not hit:
            return None
        return loc.copy(), normal.copy()

    def map(self, u, v):
        return self.cast(u / self.radius, LETTER_Z + v)


class ThreadMesh:
    def __init__(self, seed):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.rng = random.Random(seed)
        self.count = 0
        self.skipped = 0

    def add_thread(self, a, b, mapper):
        rng = self.rng
        pts = []
        for k in range(RINGS):
            t = k / (RINGS - 1)
            q = a.lerp(b, t)
            r = mapper.map(q.x, q.y)
            if r is None:
                self.skipped += 1
                return
            pts.append((t, r[0], r[1]))
        hscale = 1.0 + rng.uniform(-JITTER_HEIGHT, JITTER_HEIGHT)
        rings = []
        for i, (t, p, n) in enumerate(pts):
            nxt = pts[min(i + 1, len(pts) - 1)][1]
            prv = pts[max(i - 1, 0)][1]
            along = (nxt - prv).normalized()
            side = n.cross(along).normalized()
            lift = -0.00010 + (LIFT + 0.00010) * (math.sin(math.pi * t) ** 0.5) * hscale + PUFF * 4.0 * t * (1.0 - t)
            centre = p + n * lift
            ring = []
            for m in range(RING_SEGMENTS):
                ang = 2.0 * math.pi * m / RING_SEGMENTS
                off = side * (math.cos(ang) * THREAD_WIDTH * 0.5) + n * (math.sin(ang) * THREAD_HEIGHT * 0.5)
                ring.append((self.bm.verts.new(centre + off), t, m / RING_SEGMENTS))
            rings.append(ring)
        for r0, r1 in zip(rings, rings[1:]):
            for m in range(RING_SEGMENTS):
                k = (m + 1) % RING_SEGMENTS
                f = self.bm.faces.new((r0[m][0], r0[k][0], r1[k][0], r1[m][0]))
                for loop, (_, t, v) in zip(f.loops, (r0[m], r0[k], r1[k], r1[m])):
                    loop[self.uv].uv = (t, v)
        for ring, flip in ((rings[0], True), (rings[-1], False)):
            verts = [r[0] for r in ring]
            if flip:
                verts.reverse()
            f = self.bm.faces.new(verts)
            for loop in f.loops:
                loop[self.uv].uv = (ring[0][1], 0.5)
        self.count += 1

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


def build_word(key, word, material, font, hat, mapper, col, seed):
    rng = random.Random(seed)
    tris, (w, h) = text_triangles(word, font)
    runs = satin_runs(tris, STITCH_ANGLE, PITCH, rng)
    mesh = ThreadMesh(seed)
    for a, b in runs:
        mesh.add_thread(a, b, mapper)
    ob = mesh.to_object(f"STITCH.letters.{key}", col, material)
    ob.parent = hat
    ob.matrix_parent_inverse = hat.matrix_world.inverted()
    return ob, len(runs), mesh.count, mesh.skipped, w, h


# ------------------------------------------------------------------ renders
def render_set(scene, cam, objects, key_light):
    results = {}
    scene.camera = cam
    for key, ob in objects.items():
        for other in objects.values():
            other.hide_render = other is not ob
            other.hide_viewport = False
        results[key] = render_preview(scene, f"03 lettering {key}")

    # tight crop on the gold at raking light
    for other in objects.values():
        other.hide_render = other is not objects["founder"]
    saved_cam = (cam.location.copy(), cam.rotation_euler.copy(), cam.data.lens,
                 cam.data.dof.focus_distance, cam.data.dof.aperture_fstop)
    target = Vector((0.0, -0.14, LETTER_Z))
    cam.location = Vector((0.10, -0.50, LETTER_Z + 0.02))
    look_at(cam, target)
    cam.data.lens = 100.0
    cam.data.dof.aperture_fstop = 11.0
    cam.data.dof.focus_distance = (target - cam.location).length
    saved_key = (key_light.location.copy(), key_light.rotation_euler.copy(), key_light.data.energy)
    key_light.location = Vector((0.85, -0.42, 0.11))
    look_at(key_light, target)
    key_light.data.energy = saved_key[2] * 1.5
    results["gold crop"] = render_preview(scene, "03 lettering gold crop")
    key_light.location, key_light.rotation_euler, key_light.data.energy = saved_key
    (cam.location, cam.rotation_euler, cam.data.lens,
     cam.data.dof.focus_distance, cam.data.dof.aperture_fstop) = saved_cam

    # leave the scene showing SOCIALS, the top hat, for the next script
    for key, ob in objects.items():
        ob.hide_render = key != "socials"
    return results


def main():
    global WORK
    WORK = workdir()
    scene = bpy.context.scene
    print(f"\n[{SCRIPT}] working folder: {WORK}")
    hat = require("HAT.base")
    cam = require("CAM.hero")
    key_light = require("LIGHT.key")
    for _, _, mat in WORDS:
        require_material(mat)

    font, font_path = load_font()
    print(f"  font: {font_path}")
    mapper = CrownMapper(hat)
    col = collection("Hats")
    objects = {}
    stats = []
    t0 = time.time()
    for i, (key, word, mat_name) in enumerate(WORDS):
        ob, runs, threads, skipped, w, h = build_word(key, word, require_material(mat_name), font, hat, mapper, col, SEED + i)
        objects[key] = ob
        stats.append((key, word, runs, threads, skipped, w, h, len(ob.data.vertices), len(ob.data.polygons)))
    build_time = time.time() - t0
    # fonts are baked into geometry, the font datablock is not needed in the file
    if font.users == 0 and font.name != "Bfont Regular":
        bpy.data.fonts.remove(font)

    results = render_set(scene, cam, objects, key_light)

    print("")
    print(f"==== {SCRIPT} runtime report ====")
    print(f"  scene objects: {len(scene.objects)}")
    print(f"  crown radius at lettering height: {mapper.radius:.4f} m, cap height {CAP_HEIGHT * 1000:.1f} mm, "
          f"stitch angle {math.degrees(STITCH_ANGLE):.0f} deg, pitch {PITCH * 1000:.2f} mm, built in {build_time:.1f} s")
    for key, word, runs, threads, skipped, w, h, nv, nf in stats:
        arc = math.degrees(w / mapper.radius)
        print(f"  STITCH.letters.{key}: '{word}' flat width {w * 1000:.1f} mm ({arc:.0f} deg of crown), height {h * 1000:.1f} mm, "
              f"{threads} threads ({skipped} skipped), {nv} verts, {nf} faces")
    for k, (path, dt) in results.items():
        print(f"  render {k}: {dt:.1f} s -> {path}")
    print("=================================")


main()
