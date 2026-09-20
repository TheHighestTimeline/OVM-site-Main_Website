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

  const frames = new Array(frameCount);
  let current = -1;
  function draw(i) {
    const img = frames[i];
    if (!img || !img.complete || current === i) return;
    current = i;
    if (canvas.width !== img.naturalWidth) { canvas.width = img.naturalWidth; canvas.height = img.naturalHeight; }
    ctx.clearRect(0, 0, canvas.width, canvas.height);   // frames carry alpha, never smear
    ctx.drawImage(img, 0, 0);
  }
  function load(i) {
    return new Promise((resolve) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = img.onerror = () => resolve(img);
      img.src = src(i);
      frames[i] = img;
    });
  }

  if (reduced) {
    // a single final frame, no scroll section
    load(frameCount - 1).then(() => draw(frameCount - 1));
    canvas.style.display = "block";
    return;
  }

  // frame one first so the hero is never empty, then the rest in the background
  load(0).then(() => draw(0));
  let loaded = 1;
  const ready = new Promise((resolve) => {
    for (let i = 1; i < frameCount; i++) {
      load(i).then(() => { loaded++; if (loaded >= Math.ceil(frameCount * 0.6)) resolve(); });
    }
  });

  ready.then(() => {
    gsap.registerPlugin(ScrollTrigger);
    const state = { frame: 0 };
    gsap.to(state, {
      frame: frameCount - 1,
      ease: "none",
      scrollTrigger: { trigger: section, start: "top top", end: "bottom bottom", scrub: true },
      onUpdate: () => draw(Math.round(state.frame)),
    });
  });
})();
