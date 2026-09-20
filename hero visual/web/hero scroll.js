/* OVM scroll hero. Frame sequence on a canvas, scrubbed by scroll position.
   Parameterised through data attributes on the section, nothing hardcoded to hats.
   Requires gsap and ScrollTrigger on the page. */
(function () {
  const section = document.querySelector(".scroll-hero");
  if (!section) return;
  const canvas = section.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mobile = window.innerWidth <= Number(section.dataset.mobileMaxWidth || 900);
  const framePath = mobile ? section.dataset.mobileFramePath : section.dataset.framePath;
  const frameCount = Number(mobile ? section.dataset.mobileFrameCount : section.dataset.frameCount);
  const pad = (i) => String(i).padStart(4, "0");
  const src = (i) => framePath.replace("{i}", pad(i));
  section.style.setProperty("--scroll-height", section.dataset.scrollHeight || "400vh");

  // the scrub starts at data-start-frame so a still intro hold in the sequence costs no scroll
  const startFrame = Math.min(frameCount - 1, Math.max(0, Math.round(
    Number(section.dataset.startFrame || 0) * (mobile ? Number(section.dataset.mobileFrameCount) / Number(section.dataset.frameCount) : 1))));

  // the caption fades in from data-reveal-frame over data-reveal-fade frames (desktop frame numbers)
  const caption = section.querySelector(".scroll-hero__caption");
  const ratio = mobile ? Number(section.dataset.mobileFrameCount) / Number(section.dataset.frameCount) : 1;
  const revealFrame = Number(section.dataset.revealFrame || frameCount) * ratio;
  const revealFade = Math.max(1, Number(section.dataset.revealFade || 8) * ratio);
  function caption_at(frame) {
    if (!caption) return;
    const t = Math.min(1, Math.max(0, (frame - revealFrame) / revealFade));
    caption.style.opacity = (t * t * (3 - 2 * t)).toFixed(3);
  }

  const frames = new Array(frameCount);
  let current = -1;
  let wanted = startFrame;
  function ready(i) { const img = frames[i]; return img && img.complete && img.naturalWidth > 0; }
  function draw(i) {
    // the nearest loaded frame at or below the target, so scrubbing works while frames still arrive
    wanted = i;
    let j = i;
    while (j > 0 && !ready(j)) j--;
    if (!ready(j) || current === j) return;
    current = j;
    const img = frames[j];
    if (canvas.width !== img.naturalWidth) { canvas.width = img.naturalWidth; canvas.height = img.naturalHeight; }
    ctx.clearRect(0, 0, canvas.width, canvas.height);   // frames carry alpha, never smear
    ctx.drawImage(img, 0, 0);
  }
  function load(i) {
    return new Promise((resolve) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => { resolve(img); if (i <= wanted) draw(wanted); };   // catch up once the frame lands
      img.onerror = () => resolve(img);
      img.src = src(i);
      frames[i] = img;
    });
  }

  if (reduced) {
    // a single final frame, no scroll section
    load(frameCount - 1).then(() => draw(frameCount - 1));
    canvas.style.display = "block";
    caption_at(frameCount - 1);
    return;
  }

  // the first shown frame first so the hero is never empty, then the rest in order
  load(startFrame).then(() => draw(startFrame));
  for (let i = 0; i < frameCount; i++) if (i !== startFrame) load(i);

  // scrub is live from the start; frames that have not arrived yet fall back to the nearest loaded one
  gsap.registerPlugin(ScrollTrigger);
  const state = { frame: startFrame };
  gsap.to(state, {
    frame: frameCount - 1,
    ease: "none",
    scrollTrigger: { trigger: section, start: "top top", end: "bottom bottom", scrub: true },
    onUpdate: () => { draw(Math.round(state.frame)); caption_at(state.frame); },
  });
})();
