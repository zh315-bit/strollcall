// Small vanilla ports of React Bits effects (https://reactbits.dev, MIT + Commons Clause):
// Click Spark, Text Type, Count Up, Tilted Card, Animated Content.
// Each one attaches itself to elements the pages already render, so the page scripts need no changes.
// Everything is decoration: it is skipped under prefers-reduced-motion and never hides content.

(() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  // After a page switch inside the site the view transition already moves the page in (common.js):
  // the first typing and card pop-ins are skipped then, and only play when someone lands here.
  let quietStart = typeof ARRIVED_IN_SITE !== "undefined" && !!ARRIVED_IN_SITE;

  // ---- Click Spark: four-point star sparks burst from every click ----

  function clickSpark() {
    const canvas = document.createElement("canvas");
    canvas.className = "spark-layer";
    canvas.setAttribute("aria-hidden", "true");
    document.body.append(canvas);
    const ctx = canvas.getContext("2d");
    const bursts = [];
    let raf = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    addEventListener("resize", resize);

    const star = (x, y, r, rot) => {
      const pinch = r * 0.2;
      ctx.beginPath();
      ctx.moveTo(x + Math.cos(rot) * r, y + Math.sin(rot) * r);
      for (let i = 1; i <= 4; i++) {
        const a = rot + (i * Math.PI) / 2, mid = a - Math.PI / 4;
        ctx.quadraticCurveTo(x + Math.cos(mid) * pinch, y + Math.sin(mid) * pinch, x + Math.cos(a) * r, y + Math.sin(a) * r);
      }
      ctx.fill();
    };

    const DURATION = 520, RADIUS = 34, COUNT = 8;
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    const frame = (now) => {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      for (let i = bursts.length - 1; i >= 0; i--) {
        const b = bursts[i], p = (now - b.start) / DURATION;
        if (p >= 1) { bursts.splice(i, 1); continue; }
        ctx.globalAlpha = 1 - Math.max(0, p - 0.6) / 0.4;
        b.sparks.forEach((s) => {
          const d = RADIUS * s.reach * ease(p);
          ctx.fillStyle = s.color;
          star(b.x + Math.cos(s.angle) * d, b.y + Math.sin(s.angle) * d, s.size * (1 - p * 0.7), s.angle + p * 3);
        });
      }
      ctx.globalAlpha = 1;
      raf = bursts.length ? requestAnimationFrame(frame) : 0;
    };

    addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const colors = [cssVar("--accent"), cssVar("--sun"), cssVar("--accent-2")];
      const turn = Math.random() * Math.PI;
      bursts.push({ x: e.clientX, y: e.clientY, start: performance.now(), sparks: Array.from({ length: COUNT }, (_, i) => ({
        angle: turn + (i / COUNT) * Math.PI * 2, reach: 0.8 + Math.random() * 0.4,
        size: 4 + Math.random() * 3, color: colors[i % colors.length] })) });
      if (bursts.length > 24) bursts.shift();
      if (!raf) raf = requestAnimationFrame(frame);
    }, { passive: true });
  }

  // ---- Text Type: the page header's tagline types itself out, with a blinking cursor ----
  // The real tagline stays in place (transparent) so its size is reserved and screen readers read it whole;
  // an aria-hidden copy on top does the typing, and retypes whenever the page changes the tagline.

  function textType() {
    const tagline = document.querySelector(".page-head .tagline");
    if (!tagline) return;
    const wrap = document.createElement("div");
    wrap.className = "tt";
    tagline.replaceWith(wrap);
    const typed = document.createElement("span");
    typed.className = "tt-typed";
    typed.setAttribute("aria-hidden", "true");
    wrap.append(tagline, typed);
    tagline.classList.add("tt-source");

    let timer = 0;
    const type = () => {
      clearTimeout(timer);
      typed.classList.remove("tt-done");
      const full = tagline.textContent;
      let i = 0;
      const step = () => {
        typed.textContent = full.slice(0, ++i);
        if (i < full.length) timer = setTimeout(step, full[i - 1] === "." ? 220 : 26 + Math.random() * 30);
        else timer = setTimeout(() => typed.classList.add("tt-done"), 1200); // the cursor leaves once the line is said
      };
      step();
    };
    if (quietStart) { typed.textContent = tagline.textContent; typed.classList.add("tt-done"); } else type();
    new MutationObserver(type).observe(tagline, { childList: true, characterData: true, subtree: true });
  }

  // ---- Count Up: walking-time numbers roll up from 0 when they first appear or change ----

  const shownTimes = new Map(); // panel label -> value last shown, so re-renders by polling don't replay

  function countUp(b) {
    const target = Number(b.textContent);
    const label = b.parentElement ? b.parentElement.textContent.replace(b.textContent, "").trim() : "";
    if (!Number.isFinite(target) || shownTimes.get(label) === target) return;
    const from = shownTimes.get(label) ?? 0;
    shownTimes.set(label, target);
    const start = performance.now(), duration = 900;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      b.textContent = Math.round(from + (target - from) * (1 - Math.pow(1 - p, 3)));
      if (p < 1 && b.isConnected) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  // ---- Tilted Card: the invite illustration tilts toward the cursor, with a soft glare ----

  function tilt(img) {
    if (img.parentElement.classList.contains("tilt")) return;
    const box = document.createElement("div");
    box.className = "tilt";
    img.replaceWith(box);
    const glare = document.createElement("div");
    glare.className = "tilt-glare";
    box.append(img, glare);
    box.addEventListener("pointermove", (e) => {
      const r = box.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      box.style.transform = `perspective(800px) rotateX(${-y * 12}deg) rotateY(${x * 12}deg) scale(1.03)`;
      glare.style.background = `radial-gradient(circle at ${(x + 0.5) * 100}% ${(y + 0.5) * 100}%, rgba(255,255,255,.45), transparent 55%)`;
      glare.style.opacity = 1;
    });
    box.addEventListener("pointerleave", () => { box.style.transform = ""; glare.style.opacity = 0; });
  }

  // ---- Animated Content: cards bounce in the first time they appear ----

  const seenCards = new Set(); // signature of each card already shown, so polling re-renders stay still

  function animateIn(card) {
    const head = card.querySelector("h2, p, li");
    const sig = `${card.className}|${(head ? head.textContent : card.textContent).trim().slice(0, 40)}`;
    if (seenCards.has(sig)) return;
    seenCards.add(sig);
    if (quietStart) return;
    card.classList.add("pop-in");
    card.style.animationDelay = `${Math.min(seenCards.size, 4) * 60}ms`;
    card.addEventListener("animationend", () => { card.classList.remove("pop-in"); card.style.animationDelay = ""; }, { once: true });
  }

  // ---- Wiring ----

  function scan(root) {
    if (!(root instanceof Element)) return;
    const all = (sel) => (root.matches(sel) ? [root] : []).concat([...root.querySelectorAll(sel)]);
    all(".times b").forEach(countUp);
    if (finePointer) all("img.card-image").forEach(tilt);
    all("main .card").forEach(animateIn);
  }

  function init() {
    if (reduced) return;
    clickSpark();
    textType();
    scan(document.body);
    quietStart = false; // cards added later (plans, polling) still pop in
    new MutationObserver((records) => records.forEach((r) => r.addedNodes.forEach(scan)))
      .observe(document.querySelector("main"), { childList: true, subtree: true });
  }

  // common.js builds the page header on DOMContentLoaded; this listener is added later, so it runs after.
  document.addEventListener("DOMContentLoaded", init);
})();
