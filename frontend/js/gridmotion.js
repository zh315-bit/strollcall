// GridMotion from React Bits (https://reactbits.dev, MIT + Commons Clause), ported from the React
// JS + CSS variant to plain DOM. Same props (as an options object) and the same layout, drift, parallax,
// spotlight and edge-fade math. Image tiles only (plus text), since there is no JSX here.
// Usage: gridMotion(container, { items: ["/a.jpg", { src: "/b.jpg", alt: "…" }, "text"], rows: 2, … })
// Returns a destroy() function; destroy.state() gives { offsets, at } to pass back as `resume` on the
// next page, so the wall carries on from where it was (offsets advance by the time in between).

(() => {
  const THEMES = {
    dark: { tile: "#1b1922", text: "rgba(255, 255, 255, 0.78)", border: "rgba(255, 255, 255, 0.07)" },
    light: { tile: "#f4f4f5", text: "#3f3f46", border: "rgba(24, 24, 27, 0.08)" },
  };
  const DIRECTIONS = ["alternate", "left", "right"];
  const IMAGE = /^(https?:\/\/|\/\/|\/|\.\.?\/|data:image\/|blob:)|\.(avif|gif|jpe?g|png|svg|webp)(\?.*)?$/i;
  const INERTIA = [0.42, 0.32, 0.26, 0.22];
  const PACE = [1, 0.86, 1.12, 0.94];

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const wrap = (value, total) => ((value % total) + total) % total;
  const smoothstep = (edge0, edge1, value) => {
    const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
    return t * t * (3 - 2 * t);
  };

  const feather = (side, zone) => {
    const stops = [];
    for (let i = 0; i <= 12; i++) {
      const t = i / 12;
      const alpha = t * t * t * (t * (t * 6 - 15) + 10);
      stops.push(`rgba(0, 0, 0, ${alpha.toFixed(4)}) ${(t * zone).toFixed(2)}%`);
    }
    const mirrored = stops.map((_, i) => {
      const t = (12 - i) / 12;
      const alpha = t * t * t * (t * (t * 6 - 15) + 10);
      return `rgba(0, 0, 0, ${alpha.toFixed(4)}) ${(100 - t * zone).toFixed(2)}%`;
    });
    return `linear-gradient(${side}, ${stops.join(", ")}, ${mirrored.join(", ")})`;
  };

  const toTile = (item) => {
    if (item === null || item === undefined || item === false) return { kind: "empty" };
    if (typeof item === "object" && typeof item.src === "string") return { kind: "image", src: item.src, alt: item.alt ?? "" };
    const text = String(item).trim();
    return IMAGE.test(text) ? { kind: "image", src: text, alt: "" } : { kind: "text", text };
  };

  function tileEl(tile) {
    const div = document.createElement("div");
    div.className = "grid-motion__tile";
    if (tile.kind === "image") {
      const img = document.createElement("img");
      img.src = tile.src; img.alt = tile.alt; img.draggable = false; img.decoding = "async";
      div.append(img);
    } else if (tile.kind === "text") {
      const span = document.createElement("span");
      span.className = "grid-motion__text";
      span.textContent = tile.text;
      div.append(span);
    }
    return div;
  }

  function gridMotion(root, {
    items = [], rows = 4, aspectRatio = 1.33, gap = 16, radius = 14, angle = -12, tilt = 0, speed = 24,
    direction = "alternate", parallax = 0.5, spotlight = 0.6, dim = 0.35, grayscale = false, fade = 0.5,
    tileColor, textColor, theme = "dark", resume = null,
  } = {}) {
    const palette = THEMES[theme] ?? THEMES.dark;
    const s = {
      rows: clamp(Math.round(rows), 1, 12), aspect: clamp(aspectRatio, 0.3, 4), gap: Math.max(0, gap), angle,
      tilt: clamp(tilt, 0, 75), speed, direction: DIRECTIONS.includes(direction) ? direction : "alternate",
      parallax: clamp(parallax, 0, 1), spotlight: clamp(spotlight, 0, 1), dim: clamp(dim, 0, 1), fade: clamp(fade, 0, 1),
    };
    const tiles = items.map(toTile);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const motion = { offsets: [], shifts: [], intro: resume ? 1 : 0, pointer: { x: 0, y: 0, active: false } };
    const resumeGap = resume ? Math.min(5, Math.max(0, (Date.now() - resume.at) / 1000)) : 0;

    root.classList.add("grid-motion");
    if (grayscale) root.classList.add("grid-motion--gray");
    root.style.setProperty("--gm-tile", tileColor ?? palette.tile);
    root.style.setProperty("--gm-text", textColor ?? palette.text);
    root.style.setProperty("--gm-border", palette.border);
    root.style.setProperty("--gm-radius", `${Math.max(0, radius)}px`);
    root.style.setProperty("--gm-dim", s.dim);
    if (s.fade > 0) {
      const mask = `${feather("to right", s.fade * 34)}, ${feather("to bottom", s.fade * 44)}`;
      root.style.maskImage = mask; root.style.webkitMaskImage = mask;
      root.style.maskComposite = "intersect"; root.style.webkitMaskComposite = "source-in";
    }

    let layout = null, plane = null, rowEls = [], tileEls = [], spots = [], written = [];
    let raf = 0, last = performance.now(), visible = true, alive = true, size = { width: 0, height: 0 };

    // Same geometry as the original's useMemo(layout).
    function measure() {
      const { width, height } = size;
      if (!width || !height) return null;
      const turn = (s.angle * Math.PI) / 180, lean = (s.tilt * Math.PI) / 180;
      const cos = Math.abs(Math.cos(turn)), sin = Math.abs(Math.sin(turn));
      const planeHeight = ((width * sin + height * cos) / Math.max(0.3, Math.cos(lean))) * 1.12;
      const planeWidth = (width * cos + height * sin) * (1 + Math.sin(lean) * 0.9) * 1.12;
      const tileHeight = Math.max(16, (planeHeight - s.gap * (s.rows - 1)) / s.rows);
      const tileWidth = tileHeight * s.aspect;
      const step = tileWidth + s.gap;
      const perRow = Math.ceil(planeWidth / step) + 1;
      const period = perRow * step;
      return {
        planeWidth, planeHeight, tileWidth, tileHeight, step, perRow, period,
        copies: Math.ceil(planeWidth / period) + 2,
        top: (planeHeight - s.rows * tileHeight - (s.rows - 1) * s.gap) / 2,
        perspective: Math.max(width, height) * 1.5,
      };
    }

    // Rebuild the tile DOM whenever the layout changes (the original re-renders).
    function build() {
      layout = measure();
      plane?.remove();
      if (!layout) return;
      root.style.perspective = s.tilt > 0 ? `${layout.perspective}px` : "";
      plane = document.createElement("div");
      plane.className = "grid-motion__plane";
      plane.setAttribute("aria-hidden", "true");
      Object.assign(plane.style, {
        width: `${layout.planeWidth}px`, height: `${layout.planeHeight}px`,
        transform: `translate(-50%, -50%) rotateX(${s.tilt}deg) rotateZ(${s.angle}deg)`,
      });
      plane.style.setProperty("--gm-gap", `${s.gap}px`);
      plane.style.setProperty("--gm-tile-w", `${layout.tileWidth}px`);
      plane.style.setProperty("--gm-tile-h", `${layout.tileHeight}px`);
      plane.style.setProperty("--gm-font", `${clamp(layout.tileHeight * 0.12, 12, 32)}px`);
      for (let r = 0; r < s.rows; r++) {
        const row = document.createElement("div");
        row.className = "grid-motion__row";
        row.style.top = `${layout.top + r * (layout.tileHeight + s.gap)}px`;
        const sequence = Array.from({ length: layout.perRow }, (_, j) =>
          tiles.length ? tiles[(r * layout.perRow + j) % tiles.length] : { kind: "empty" });
        for (let k = 0; k < layout.copies * layout.perRow; k++) row.append(tileEl(sequence[k % layout.perRow]));
        plane.append(row);
      }
      root.append(plane);
      if (motion.intro >= 1) plane.style.opacity = "1";
      rowEls = Array.from(plane.children);
      tileEls = rowEls.map((row) => Array.from(row.children));
      spots = tileEls.map((list) => new Float32Array(list.length));
      written = tileEls.map((list) => new Float32Array(list.length));
      schedule();
    }

    function frame(now) {
      raf = 0;
      if (!alive || !layout) return;
      const dt = Math.min(0.05, Math.max(0.001, (now - last) / 1000));
      last = now;

      if (motion.intro < 1) {
        motion.intro = Math.min(1, motion.intro + dt / 0.9);
        plane.style.opacity = String(1 - (1 - motion.intro) ** 3);
      }

      const rect = root.getBoundingClientRect();
      const scale = rect.width ? root.clientWidth / rect.width : 1;
      const halfWidth = root.clientWidth / 2 || 1;
      const halfHeight = root.clientHeight / 2 || 1;
      const px = (motion.pointer.x - rect.left) * scale - halfWidth;
      const py = (motion.pointer.y - rect.top) * scale - halfHeight;
      const inside = motion.pointer.active && Math.abs(px) <= halfWidth && Math.abs(py) <= halfHeight;
      const lean = (s.tilt * Math.PI) / 180, turn = (s.angle * Math.PI) / 180, depth = layout.perspective;
      let flatY = py, flatX = px;
      if (lean > 0.0001) {
        flatY = (py * depth) / (depth * Math.cos(lean) + py * Math.sin(lean));
        flatX = (px * (depth - flatY * Math.sin(lean))) / depth;
      }
      const planeX = flatX * Math.cos(turn) + flatY * Math.sin(turn);
      const planeY = -flatX * Math.sin(turn) + flatY * Math.cos(turn);
      const nudge = motion.pointer.active ? clamp(px / halfWidth, -1, 1) : 0;
      const reach = (0.6 + 2.2 * s.spotlight) * Math.max(layout.tileWidth, layout.tileHeight);
      const settle = 1 - Math.exp(-dt / 0.22);

      rowEls.forEach((row, r) => {
        const drift = s.direction === "left" ? -1 : s.direction === "right" ? 1 : r % 2 ? 1 : -1;
        if (motion.offsets[r] === undefined) {
          const saved = resume?.offsets?.[r];
          motion.offsets[r] = typeof saved === "number"
            ? saved + (reduce ? 0 : s.speed * drift * PACE[r % PACE.length] * resumeGap)
            : r * layout.step * 0.37;
          motion.shifts[r] = 0;
        }
        if (!reduce) motion.offsets[r] += s.speed * drift * PACE[r % PACE.length] * dt;
        const target = reduce ? 0 : s.parallax * layout.tileWidth * 1.2 * nudge * (r % 2 ? -1 : 1);
        motion.shifts[r] += (target - motion.shifts[r]) * (1 - Math.exp(-dt / INERTIA[r % INERTIA.length]));
        const x = -layout.period + wrap(motion.offsets[r] + motion.shifts[r], layout.period);
        row.style.transform = `translate3d(${x.toFixed(2)}px, 0, 0)`;

        const rowY = layout.top + r * (layout.tileHeight + s.gap) + layout.tileHeight / 2 - layout.planeHeight / 2;
        const left = x - layout.planeWidth / 2 + layout.tileWidth / 2;
        const list = tileEls[r], values = spots[r], marks = written[r];
        for (let k = 0; k < list.length; k++) {
          let wanted = 0;
          if (inside && s.spotlight > 0) {
            const distance = Math.hypot(left + k * layout.step - planeX, rowY - planeY) / reach;
            wanted = 1 - smoothstep(0.25, 1, distance);
          }
          values[k] += (wanted - values[k]) * settle;
          if (Math.abs(values[k] - marks[k]) > 0.004 || (wanted === 0 && values[k] < 0.004 && marks[k] !== 0)) {
            marks[k] = values[k] < 0.004 ? 0 : values[k];
            list[k].style.setProperty("--spot", marks[k].toFixed(3));
          }
        }
      });

      if (visible) raf = requestAnimationFrame(frame);
    }
    const schedule = () => { if (!raf && visible) { last = performance.now(); raf = requestAnimationFrame(frame); } };

    const onMove = (e) => { motion.pointer.x = e.clientX; motion.pointer.y = e.clientY; motion.pointer.active = true; };
    const onUp = (e) => { if (e.pointerType === "touch") motion.pointer.active = false; };
    const onLeave = () => { motion.pointer.active = false; };
    addEventListener("pointermove", onMove, { passive: true });
    addEventListener("pointerdown", onMove, { passive: true });
    addEventListener("pointerup", onUp);
    addEventListener("blur", onLeave);
    document.documentElement.addEventListener("pointerleave", onLeave);

    const onResize = () => {
      const width = Math.round(root.clientWidth), height = Math.round(root.clientHeight);
      if (width === size.width && height === size.height) return;
      size = { width, height };
      build();
    };
    const resize = new ResizeObserver(onResize);
    resize.observe(root);
    onResize(); // lay out right away instead of waiting for the observer's first callback
    // Paused while scrolled out of view or while the tab is hidden.
    const seen = new IntersectionObserver((entries) => { visible = entries.some((e) => e.isIntersecting); schedule(); });
    seen.observe(root);

    const destroy = () => {
      alive = false;
      cancelAnimationFrame(raf);
      resize.disconnect(); seen.disconnect();
      removeEventListener("pointermove", onMove); removeEventListener("pointerdown", onMove);
      removeEventListener("pointerup", onUp); removeEventListener("blur", onLeave);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      plane?.remove();
    };
    destroy.state = () => ({ offsets: motion.offsets.slice(), at: Date.now() });
    return destroy;
  }

  window.gridMotion = gridMotion;
})();
