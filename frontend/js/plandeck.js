// Walk options as pages: each whole option (name, times, buttons) is one page, and the pages sit on a
// gentle arc, the motion of React Bits' CircularGallery (https://reactbits.dev) applied to real DOM
// panels instead of WebGL image cards. Swipe, drag, a sideways wheel, the arrow keys, the dots or a tap
// on a side page turn to another option. Only the centred page can be used; the others are inert.
// Three or more pages close into a ring: after the last option comes the first again.
// Usage: planDeck([pageEl, …], { start, labels, onChange(i) }) returns { el, go(i), destroy() }.

(() => {
  const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

  function planDeck(pages, { start = 0, labels = [], onChange } = {}) {
    const n = pages.length;
    const loop = n >= 3;
    const mod = (v) => ((v % n) + n) % n;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const root = document.createElement("div");
    root.className = "plan-deck";
    root.setAttribute("role", "region");
    root.setAttribute("aria-roledescription", "carousel");
    root.setAttribute("aria-label", "Walk options");
    const track = document.createElement("div");
    track.className = "plan-deck-track";
    pages.forEach((page, i) => {
      page.classList.add("plan-page");
      page.setAttribute("role", "group");
      page.setAttribute("aria-roledescription", "slide");
      page.setAttribute("aria-label", `${labels[i] || `Option ${i + 1}`}, ${i + 1} of ${n}`);
      track.append(page);
    });
    const dots = document.createElement("div");
    dots.className = "plan-deck-dots";
    const dotEls = pages.map((_, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-label", labels[i] || `Option ${i + 1}`);
      b.addEventListener("click", () => go(i));
      dots.append(b);
      return b;
    });
    root.append(track, dots);

    let active = clamp(Math.round(start), 0, n - 1);
    let pos = active, target = active;
    let width = 1, raf = 0, last = 0, drag = null, alive = true;

    // The arc: pages further from the centre drop and turn along a wide circle, like the gallery's bend.
    function place() {
      const w = pages[0].offsetWidth || width * 0.82;
      const spacing = w * 1.04;
      const R = w * 5;
      pages.forEach((page, i) => {
        // On the ring each page sits at its shortest way round from the centre, in [-n/2, n/2).
        const off = loop ? mod(i - pos + n / 2) - n / 2 : i - pos;
        const x = off * spacing;
        const reach = Math.min(Math.abs(x), R * 0.999);
        const drop = R - Math.sqrt(R * R - reach * reach);
        const angle = Math.sign(x) * Math.asin(reach / R);
        const far = Math.min(Math.abs(off), 1);
        page.style.transform = `translateX(-50%) translate(${x}px, ${drop}px) rotate(${angle}rad) scale(${1 - 0.06 * far})`;
        // Pages more than two away fade out, so the one passing behind the ring is never seen jumping sides.
        const fade = clamp(1 - (Math.abs(off) - 2) / 0.5, 0, 1);
        page.style.opacity = String((1 - 0.4 * far) * fade);
        page.style.visibility = fade ? "" : "hidden";
        page.style.zIndex = String(100 - Math.round(Math.abs(off) * 10));
      });
    }

    // The deck is as tall as the page in front, and grows or shrinks with it.
    function fit() { track.style.height = `${pages[active].offsetHeight + 26}px`; }

    function setActive(i, announce) {
      if (i === active) return;
      active = i;
      mark();
      fit();
      if (announce) onChange?.(i);
    }

    function mark() {
      pages.forEach((page, i) => {
        page.inert = i !== active;
        page.classList.toggle("is-active", i === active);
      });
      dotEls.forEach((b, i) => {
        if (i === active) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
      });
    }

    function frame(now) {
      raf = 0;
      if (!alive) return;
      const dt = last ? clamp((now - last) / 1000, 0.0005, 0.05) : 1 / 60;
      last = now;
      if (!drag) {
        const follow = reduce ? 1 : 1 - Math.pow(1 - 0.14, dt * 60);
        pos += (target - pos) * follow;
        if (Math.abs(target - pos) < 0.001) pos = target;
      }
      place();
      if (drag || pos !== target) raf = requestAnimationFrame(frame);
      else last = 0;
    }
    function wake() { if (alive && !raf) raf = requestAnimationFrame(frame); }

    // On the ring the target is unbounded (it counts whole turns), so the deck always turns the way it was moved.
    function turnTo(t, announce = true) {
      target = loop ? t : clamp(t, 0, n - 1);
      setActive(loop ? mod(target) : target, announce);
      wake();
    }
    // Option i, the short way round.
    function go(i, announce = true) {
      if (!loop) return turnTo(i, announce);
      const cur = Math.round(target);
      let d = mod(i - cur);
      if (d > n / 2) d -= n;
      turnTo(cur + d, announce);
    }

    // Dragging: past the first or last page the deck only gives a little (rubber band); a ring has no ends.
    const rubber = (p) => (loop ? p : p < 0 ? p * 0.3 : p > n - 1 ? n - 1 + (p - n + 1) * 0.3 : p);

    const onPointerDown = (e) => {
      if (e.button !== 0) return;
      drag = { id: e.pointerId, x0: e.clientX, y0: e.clientY, start: pos, moved: false, samples: [] };
    };
    const onPointerMove = (e) => {
      if (!drag || drag.id !== e.pointerId) return;
      const dx = e.clientX - drag.x0, dy = e.clientY - drag.y0;
      if (!drag.moved) {
        if (Math.hypot(dx, dy) < 8) return;
        // Mostly up/down: the page scrolls, the deck stays.
        if (Math.abs(dy) > Math.abs(dx)) { drag = null; return; }
        drag.moved = true;
        root.setPointerCapture?.(e.pointerId);
        root.classList.add("dragging");
      }
      const w = pages[0].offsetWidth * 1.04;
      pos = rubber(drag.start - dx / w);
      drag.samples.push({ x: e.clientX, t: performance.now() });
      if (drag.samples.length > 6) drag.samples.shift();
      wake();
    };
    const endDrag = (e) => {
      if (!drag || drag.id !== e.pointerId) return;
      const d = drag;
      drag = null;
      root.classList.remove("dragging");
      if (!d.moved) return;
      let fling = 0;
      if (d.samples.length > 1) {
        const a = d.samples[0], b = d.samples[d.samples.length - 1];
        fling = -((b.x - a.x) / Math.max(b.t - a.t, 16)) * 1000 / (pages[0].offsetWidth * 1.04); // pages per second
      }
      const aim = pos + clamp(fling * 0.25, -1, 1);
      // A short quick flick still turns one page.
      const near = Math.round(d.start);
      const step = Math.abs(aim - near) > 0.25 && Math.round(aim) === near ? Math.sign(aim - near) : 0;
      turnTo(Math.round(aim) + step);
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 0);
    };
    // The click that ends a drag must not press a button under the finger.
    let suppressClick = false;
    const onClickCapture = (e) => {
      if (suppressClick) { e.preventDefault(); e.stopPropagation(); return; }
      // A tap on a side page (inert, so the tap lands on the deck) turns to it.
      if (e.target === root || e.target === track) {
        // The page in front wins; pages faded out behind the ring never catch a tap.
        let hit = -1;
        pages.forEach((p, i) => {
          if (i === active || p.style.visibility === "hidden") return;
          const r = p.getBoundingClientRect();
          if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom &&
              (hit < 0 || +p.style.zIndex > +pages[hit].style.zIndex)) hit = i;
        });
        if (hit >= 0) go(hit);
      }
    };
    const onWheel = (e) => {
      if (Math.abs(e.deltaX) <= Math.abs(e.deltaY) || Math.abs(e.deltaX) < 4) return;
      e.preventDefault();
      if (wheelLock) return;
      wheelLock = true;
      setTimeout(() => { wheelLock = false; }, 450);
      go(active + Math.sign(e.deltaX));
    };
    let wheelLock = false;
    const onKey = (e) => {
      if (e.target.closest("input, textarea, select")) return;
      if (e.key === "ArrowRight") { e.preventDefault(); go(active + 1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(active - 1); }
    };

    root.addEventListener("pointerdown", onPointerDown);
    root.addEventListener("pointermove", onPointerMove);
    root.addEventListener("pointerup", endDrag);
    root.addEventListener("pointercancel", endDrag);
    root.addEventListener("click", onClickCapture, true);
    root.addEventListener("wheel", onWheel, { passive: false });
    root.addEventListener("keydown", onKey);
    const sizes = new ResizeObserver(() => { width = root.clientWidth || width; fit(); place(); });
    sizes.observe(root);
    pages.forEach((p) => sizes.observe(p));

    mark();
    place();
    requestAnimationFrame(() => { fit(); place(); });

    return {
      el: root,
      go: (i) => go(i, false),
      destroy() { alive = false; cancelAnimationFrame(raf); sizes.disconnect(); },
    };
  }

  window.planDeck = planDeck;
})();
