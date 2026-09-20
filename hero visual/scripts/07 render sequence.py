"""07 render sequence.py

OVM Hat Hero, phase two, the frames.

Renders the choreographed scene to a numbered PNG sequence with alpha in
frames, converts to WebP, and reports the payload against the 7 MB budget.
Never a video, never a baked background.

Desktop set: FULL_WIDTH wide, every frame.
Mobile set: MOBILE_WIDTH wide, every MOBILE_STEP th frame, into frames/mobile.

Runs only when HATHERO_RENDER_SEQUENCE=1, so the build runner skips it.
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
SKIP_PROBE = os.environ.get("HATHERO_SKIP_PROBE") == "1"     # resuming: the estimate is already known
KEEP_PNG = os.environ.get("HATHERO_KEEP_PNG") == "1"         # the PNGs are working files; WebP is what ships
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


def derive_mobile(png_path, mobile_webp):
    """The mobile frame is the desktop render scaled down, not a second render: same samples, fewer pixels."""
    from PIL import Image
    im = Image.open(png_path).convert("RGBA")
    h = round(im.height * MOBILE_WIDTH / im.width)
    im.resize((MOBILE_WIDTH, h), Image.LANCZOS).save(mobile_webp, "WEBP", quality=WEBP_QUALITY, method=6)


def render_set(scene, frames, out_dir, mobile_dir=None):
    """Render each (index, frame) to out_dir as WebP, skipping ones already there, so a stopped run resumes.
    With mobile_dir given, every MOBILE_STEP-th desktop frame is also scaled down into it."""
    total_bytes, done, skipped = 0, 0, 0
    for i, f in frames:
        webp = os.path.join(out_dir, f"frame_{i:04d}.webp")
        if os.path.exists(webp):
            total_bytes += os.path.getsize(webp)
            skipped += 1
            continue
        png = webp[:-5] + ".png"
        dt = render_frame(scene, f, png)
        total_bytes += to_webp(png, webp)
        if mobile_dir is not None and i % MOBILE_STEP == 0:
            derive_mobile(png, os.path.join(mobile_dir, f"frame_{i // MOBILE_STEP:04d}.webp"))
        if not KEEP_PNG:
            os.remove(png)
        done += 1
        print(f"  frame {i:04d} (scene frame {f}) {dt:.0f} s -> {webp}", flush=True)
    return total_bytes, done, skipped


def main():
    if os.environ.get("HATHERO_RENDER_SEQUENCE") != "1":
        print(f"[{SCRIPT}] skipped. Set HATHERO_RENDER_SEQUENCE=1 to render the frame sequence (hours of GPU time).")
        return
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
    if SKIP_PROBE:
        print("  HATHERO_SKIP_PROBE=1, resuming without the estimate")
    probe_frame = scene.frame_start + total // 2
    if not SKIP_PROBE:
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
    desktop = [(f - scene.frame_start, f) for f in range(scene.frame_start, scene.frame_end + 1)]
    total_bytes, d_done, d_skipped = render_set(scene, desktop, frames_dir, mobile_dir)
    desktop_time = time.time() - t0
    # mobile set: anything not already derived from the desktop pass is rendered at mobile width
    setup(scene, MOBILE_WIDTH, int(MOBILE_WIDTH * FULL_HEIGHT / FULL_WIDTH))
    t1 = time.time()
    mobile = list(enumerate(range(scene.frame_start, scene.frame_end + 1, MOBILE_STEP)))
    mobile_bytes, m_done, m_skipped = render_set(scene, mobile, mobile_dir)
    mobile_time = time.time() - t1
    setup(scene, FULL_WIDTH, FULL_HEIGHT)
    scene.frame_set(scene.frame_start)

    print("")
    print(f"==== {SCRIPT} runtime report ====")
    print(f"  desktop: {total} frames ({d_done} rendered, {d_skipped} already there), {FULL_WIDTH}x{FULL_HEIGHT}, {desktop_time / 60:.1f} min, WebP payload {total_bytes / 1e6:.2f} MB "
          f"({'clears' if total_bytes / 1e6 <= BUDGET_MB else 'OVER'} budget)")
    print(f"  mobile: {mobile_total} frames ({m_done} rendered, {m_skipped} already there), {MOBILE_WIDTH} px wide, {mobile_time / 60:.1f} min, WebP payload {mobile_bytes / 1e6:.2f} MB")
    print(f"  frames in {frames_dir} and {mobile_dir}, pattern frame_NNNN.webp")
    print("=================================")


main()
