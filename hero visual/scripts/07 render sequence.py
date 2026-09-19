"""07 render sequence.py

OVM Hat Hero, phase two, the frames.

Renders the choreographed scene to a numbered PNG sequence with alpha in
frames, converts to WebP, and reports the payload against the 7 MB budget.
Never a video, never a baked background.

Desktop set: FULL_WIDTH wide, every frame.
Mobile set: MOBILE_WIDTH wide, every MOBILE_STEP th frame, into frames/mobile.

Before rendering, prints an estimate of frame count, time and payload, and
stops there if HATHERO_ESTIMATE_ONLY=1. Renders one frame first to time
it and then extrapolates, so the estimate is measured, not guessed.

Engine: Cycles by default. Set HATHERO_ENGINE=EEVEE to test EEVEE Next.

Idempotent: overwrites frames in place.
"""
import bpy
import os
import time

SCRIPT = "07 render sequence"

FULL_WIDTH = 1600
FULL_HEIGHT = 900
SAMPLES = 256
MOBILE_WIDTH = 1000
MOBILE_STEP = 2
WEBP_QUALITY = 82
BUDGET_MB = 7.0
ESTIMATE_ONLY = os.environ.get("HATHERO_ESTIMATE_ONLY") == "1"
ENGINE = os.environ.get("HATHERO_ENGINE", "CYCLES").upper()


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


def setup(scene, width, height):
    scene.render.engine = "BLENDER_EEVEE_NEXT" if ENGINE.startswith("EEVEE") else "CYCLES"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = SAMPLES
        scene.cycles.use_denoising = True


def render_frame(scene, frame, path):
    scene.frame_set(frame)
    scene.render.filepath = path
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    return time.time() - t0


def to_webp(png_path, webp_path):
    from PIL import Image
    im = Image.open(png_path).convert("RGBA")
    im.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
    return os.path.getsize(webp_path)


def main():
    work = workdir()
    scene = bpy.context.scene
    if scene.frame_end <= 1 or not any(o.animation_data for o in scene.objects if o.name.startswith("HAT.")):
        raise RuntimeError(f"{SCRIPT}: the scene is not choreographed. Run 06 choreography first.")
    frames_dir = os.path.join(work, "frames")
    mobile_dir = os.path.join(frames_dir, "mobile")
    os.makedirs(mobile_dir, exist_ok=True)
    total = scene.frame_end - scene.frame_start + 1
    mobile_total = len(range(scene.frame_start, scene.frame_end + 1, MOBILE_STEP))
    print(f"\n[{SCRIPT}] engine {scene.render.engine if False else ENGINE}, {total} frames at {FULL_WIDTH} px, {mobile_total} mobile frames at {MOBILE_WIDTH} px")

    # measure one frame, then estimate
    setup(scene, FULL_WIDTH, FULL_HEIGHT)
    probe_frame = scene.frame_start + total // 2
    probe_png = os.path.join(frames_dir, "probe.png")
    dt = render_frame(scene, probe_frame, probe_png)
    probe_webp = os.path.join(frames_dir, "probe.webp")
    size = to_webp(probe_png, probe_webp)
    est_mb = size * total / 1e6
    est_mobile_mb = size * (MOBILE_WIDTH / FULL_WIDTH) ** 2 * mobile_total / 1e6
    print(f"  probe frame {probe_frame}: {dt:.1f} s, WebP {size / 1e3:.0f} KB")
    print(f"  estimate: desktop {total} frames about {dt * total / 60:.0f} min, {est_mb:.1f} MB "
          f"({'clears' if est_mb <= BUDGET_MB else 'OVER'} the {BUDGET_MB:.0f} MB budget)")
    print(f"  estimate: mobile {mobile_total} frames about {dt * (MOBILE_WIDTH / FULL_WIDTH) ** 2 * mobile_total / 60:.0f} min, {est_mobile_mb:.1f} MB")
    if est_mb > BUDGET_MB:
        needed = int(BUDGET_MB * 1e6 / size)
        print(f"  to clear the budget at this width: {needed} frames, or a narrower render. I would drop frames before width.")
    for p in (probe_png, probe_webp):
        os.remove(p)
    if ESTIMATE_ONLY:
        print("  HATHERO_ESTIMATE_ONLY=1, stopping before the sequence")
        return

    # desktop set
    t0 = time.time()
    total_bytes = 0
    for f in range(scene.frame_start, scene.frame_end + 1):
        png = os.path.join(frames_dir, f"frame_{f - scene.frame_start:04d}.png")
        render_frame(scene, f, png)
        total_bytes += to_webp(png, png[:-4] + ".webp")
    desktop_time = time.time() - t0
    # mobile set
    setup(scene, MOBILE_WIDTH, int(MOBILE_WIDTH * FULL_HEIGHT / FULL_WIDTH))
    t1 = time.time()
    mobile_bytes = 0
    for i, f in enumerate(range(scene.frame_start, scene.frame_end + 1, MOBILE_STEP)):
        png = os.path.join(mobile_dir, f"frame_{i:04d}.png")
        render_frame(scene, f, png)
        mobile_bytes += to_webp(png, png[:-4] + ".webp")
    mobile_time = time.time() - t1
    setup(scene, FULL_WIDTH, FULL_HEIGHT)
    scene.frame_set(scene.frame_start)

    print("")
    print(f"==== {SCRIPT} runtime report ====")
    print(f"  desktop: {total} frames, {FULL_WIDTH}x{FULL_HEIGHT}, {desktop_time / 60:.1f} min, WebP payload {total_bytes / 1e6:.2f} MB "
          f"({'clears' if total_bytes / 1e6 <= BUDGET_MB else 'OVER'} budget)")
    print(f"  mobile: {mobile_total} frames, {MOBILE_WIDTH} px wide, {mobile_time / 60:.1f} min, WebP payload {mobile_bytes / 1e6:.2f} MB")
    print(f"  frames in {frames_dir} and {mobile_dir}, pattern frame_NNNN.webp")
    print("=================================")


main()
