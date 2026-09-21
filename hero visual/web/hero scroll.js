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
  section.style.setProperty("--scroll-height", (mobile && section.dataset.mobileScrollHeight) || section.dataset.scrollHeight || "400vh");
  if (mobile) {
    // phones: the 16:9 frame is a short strip, so the section that follows (the headline block)
    // rides inside the pinned box beneath it and the first screen is full while the hats play
    const follower = section.nextElementSibling;
    const sticky = section.querySelector(".scroll-hero__sticky");
    if (follower && sticky && follower.classList.contains(section.dataset.mobilePull || "hero")) {
      sticky.appendChild(follower);
      follower.classList.add("scroll-hero__pulled");
    }
  }

  // the scrub starts at data-start-frame so a still intro hold in the sequence costs no scroll
  const startFrame = Math.min(frameCount - 1, Math.max(0, Math.round(
    Number(section.dataset.startFrame || 0) * (mobile ? Number(section.dataset.mobileFrameCount) / Number(section.dataset.frameCount) : 1))));

  // after the last frame the scroll keeps going a little: a hold on the founder, then the caption
  // slides in from the side. Fractions of the section's scroll distance, overridable on the section.
  const caption = section.querySelector(".scroll-hero__caption");
  const holdPart = Number(section.dataset.holdPart || 0.06);
  const captionPart = Number(section.dataset.captionPart || 0.12);
  const framesPart = Math.max(0.5, 1 - holdPart - captionPart);
  const slideFrom = Number(section.dataset.captionSlide || -70);   // px, negative comes in from the left
  function caption_at(t) {
    if (!caption) return;
    const e = t * t * (3 - 2 * t);
    caption.style.opacity = e.toFixed(3);
    caption.style.transform = "translateX(" + ((1 - e) * slideFrom).toFixed(1) + "px)";
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
    caption_at(1);
    return;
  }

  // the first shown frame first so the hero is never empty, then the rest in order
  load(startFrame).then(() => draw(startFrame));
  for (let i = 0; i < frameCount; i++) if (i !== startFrame) load(i);

  // scrub is live from the start; frames that have not arrived yet fall back to the nearest loaded one
  if (!window.gsap || !window.ScrollTrigger) { console.warn("scroll hero: GSAP or ScrollTrigger missing, showing the first frame only"); return; }
  gsap.registerPlugin(ScrollTrigger);
  const state = { frame: startFrame, cap: 0 };
  caption_at(0);
  const tl = gsap.timeline({
    scrollTrigger: { trigger: section, start: "top top", end: "bottom bottom", scrub: true },
    defaults: { ease: "none" },
  });
  tl.to(state, { frame: frameCount - 1, duration: framesPart, onUpdate: () => draw(Math.round(state.frame)) })
    .to({}, { duration: holdPart })                                   // the founder alone, a beat
    .to(state, { cap: 1, duration: captionPart, onUpdate: () => caption_at(state.cap) });
})();
