// Home: the looping video over the painted plate, and the entrance (one Web Animations timeline, once).
// Under prefers-reduced-motion there is no video (the still plate stays) and nothing animates.
// The entrance plays when someone lands on Home; coming back from another page of the site (New walk
// closes into it, style.css: conceal) Home is simply there.
// New walk prerenders Home on hover: until it is actually shown, Home loads no video and plays nothing.

(() => {
  const VIDEO = "/static/media/hero-loop.mp4"; // 1920², the boy and the dog from the sharp still (frontend/media/README.md)
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (sel) => document.querySelector(sel);
  if (reduce) return;

  // ---- The scene's motion: the same plate as a 5 s loop (first frame = last frame), laid over the still ----
  function addVideo() {
    const video = document.createElement("video");
    video.className = "hero-video";
    video.setAttribute("aria-hidden", "true");
    for (const a of ["muted", "loop", "playsinline", "autoplay"]) video.setAttribute(a, "");
    video.muted = true;
    video.disablePictureInPicture = true;
    video.preload = "auto";
    video.src = VIDEO;
    video.addEventListener("playing", () => video.classList.add("playing"), { once: true });
    $(".scene-frame").append(video);
    const play = () => video.play().catch(() => {}); // autoplay refused (data saver, low power): the still stays
    play();
    // Off screen or in a background tab, the loop rests.
    new IntersectionObserver(([e]) => (e.isIntersecting && !document.hidden ? play() : video.pause())).observe(video);
    document.addEventListener("visibilitychange", () => (document.hidden ? video.pause() : play()));
  }

  // ---- Entrance ----
  function entrance() {
    if (!document.body.animate) return;
    const SPRING = "cubic-bezier(.34, 1.56, .64, 1)", OUT = "cubic-bezier(.22, 1, .36, 1)";
    const run = (el, frames, delay, duration = 700, easing = OUT) =>
      el && el.animate(frames, { delay, duration, easing, fill: "backwards" });
    const drop = [{ opacity: 0, translate: "0 -18px" }, { opacity: 1, translate: "0 0" }];
    const rise = [{ opacity: 0, translate: "0 26px" }, { opacity: 1, translate: "0 0" }];

    run($(".brand"), drop, 0, 650);
    run($(".topnav"), drop, 80, 650);
    run($(".hero-join"), drop, 160, 650);
    run($(".hero-kicker"), [{ opacity: 0, filter: "blur(12px)" }, { opacity: 1, filter: "blur(0)" }], 240, 800);
    document.querySelectorAll(".hero-title span").forEach((line, i) =>
      run(line, [{ opacity: 0, translate: "0 48px", scale: ".94", filter: "blur(14px)" },
                 { opacity: 1, translate: "0 0", scale: "1", filter: "blur(0)" }], 380 + i * 160, 950, SPRING));
    const later = [".hero-sub", ".hero-actions .pill-white", ".hero-actions .pill-mint", ".steps-title", ".steps-link",
                   ...[...document.querySelectorAll(".step")]];
    later.forEach((sel, i) => run(typeof sel === "string" ? $(sel) : sel, rise, 820 + i * 90, 750));
  }

  // A prerendered Home learns where the visitor came from only when it is shown.
  const fromSite = () => {
    if (window.navigation?.activation?.navigationType === "reload") return false; // a reload is a fresh landing
    const from = window.navigation?.activation?.from?.url;
    if (from) return new URL(from).origin === location.origin;
    return typeof ARRIVED_IN_SITE !== "undefined" && !!ARRIVED_IN_SITE;
  };
  const start = () => { addVideo(); if (!fromSite()) entrance(); };
  if (document.prerendering) document.addEventListener("prerenderingchange", start, { once: true });
  else start();
})();
