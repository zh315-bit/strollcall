// My walks and How it works sit on Home's hillside scene (home.css: body.scene): the still plate, fixed
// behind the page, with the same looping video over it, and Home's top bar with "Plan my walk".
// Same rules as Home (home.js): no video under prefers-reduced-motion, none while the page is prerendered,
// and the loop rests in a background tab.

(() => {
  const PLATE = "/static/media/hero-plate.jpg", VIDEO = "/static/media/hero-loop.mp4";
  const frame = el("div", { class: "scene-frame" }, el("img", { class: "hero-plate", src: PLATE, alt: "", decoding: "async" }));
  document.body.prepend(el("div", { class: "page-scene", "aria-hidden": "true" }, frame));
  document.querySelector(".site-bar")?.append(el("a", { class: "pill pill-white hero-join", href: "/new" }, "Plan my walk"));
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

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
    frame.append(video);
    const play = () => video.play().catch(() => {}); // autoplay refused: the still stays
    play();
    document.addEventListener("visibilitychange", () => (document.hidden ? video.pause() : play()));
  }
  if (document.prerendering) document.addEventListener("prerenderingchange", addVideo, { once: true });
  else addVideo();
})();
