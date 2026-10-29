// JellyRadio from React Bits (https://reactbits.dev, MIT + Commons Clause), ported from the React
// JS + CSS variant to plain DOM. Instead of rendering its own chips it upgrades an existing
// role="radiogroup" of role="radio" buttons, so the page keeps its own click handlers and state:
// whenever a button's aria-checked changes, the row reacts with the jelly motion.
// `motion` is replaced by a small spring solver using the original's stiffness, damping and stagger.
// Usage: jellyRadio(groupEl, { size: "lg", gap: 8, radius: 22, … }). Returns a destroy() function.

(() => {
  const SIZES = { sm: [28, 12, 12], md: [36, 13, 16], lg: [44, 14, 20] };

  // Same parameterisation as the original spring(): damping from the bounce (1 - damping ratio).
  const spring = (k, m, bounce) => ({ k, m, c: 2 * Math.sqrt(k * m) * (1 - bounce) });

  // One animated number. animate() retargets from the current position and velocity, like motion's animate().
  function springValue(initial, onChange) {
    let x = initial, v = 0, target = initial, cfg = null, startAt = 0, raf = 0, last = 0;
    const step = (now) => {
      raf = 0;
      if (now < startAt) { last = now; raf = requestAnimationFrame(step); return; }
      let dt = Math.min(0.064, (now - (last || now)) / 1000);
      last = now;
      for (; dt > 0; dt -= 0.004) { // small fixed substeps keep stiff springs stable
        const h = Math.min(0.004, dt);
        v += ((-cfg.k * (x - target) - cfg.c * v) / cfg.m) * h;
        x += v * h;
      }
      if (Math.abs(x - target) < 1e-4 && Math.abs(v) < 1e-3) { x = target; v = 0; }
      else raf = requestAnimationFrame(step);
      onChange();
    };
    return {
      get: () => x,
      isAnimating: () => raf !== 0,
      jump(to) { cancelAnimationFrame(raf); raf = 0; x = target = to; v = 0; onChange(); },
      animate(to, options, delayS = 0) {
        target = to; cfg = options;
        startAt = performance.now() + delayS * 1000; last = 0;
        if (!raf) raf = requestAnimationFrame(step);
      },
    };
  }

  function jellyRadio(group, {
    chipColor = "#27272a", activeColor = "#f5f5f5", textColor = "#f5f5f5", activeTextColor = "#18181b",
    size = "md", gap = 8, radius = 18, swell = 0.2, barge = 6, shrink = 0.05, jelly = 1, bounce = 0.25,
    stagger = 22, stiffness = 580,
  } = {}) {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const chips = [...group.querySelectorAll('[role="radio"]')];
    const [h, font, px] = SIZES[size] ?? SIZES.md;
    group.classList.add("jelly-radio");
    Object.entries({
      "--jr-chip": chipColor, "--jr-active": activeColor, "--jr-text": textColor, "--jr-active-text": activeTextColor,
      "--jr-gap": `${gap}px`, "--jr-radius": `${radius}px`, "--jr-h": `${h}px`, "--jr-font": `${font}px`, "--jr-px": `${px}px`,
    }).forEach(([k, v]) => group.style.setProperty(k, v));

    // Each button's content moves into a "skin" span, as in the original's markup.
    const mvs = chips.map((chip) => {
      chip.classList.add("jelly-radio__chip");
      const skin = document.createElement("span");
      skin.className = "jelly-radio__skin";
      skin.append(...chip.childNodes);
      chip.append(skin);
      const mv = {};
      const paint = () => { chip.style.transform = `translateX(${mv.x.get()}px) scale(${mv.sx.get()}, ${mv.sy.get()})`; };
      mv.x = springValue(0, paint); mv.sx = springValue(1, paint); mv.sy = springValue(1, paint);
      return mv;
    });
    let widths = [];
    const selected = () => Math.max(0, chips.findIndex((c) => c.getAttribute("aria-checked") === "true"));
    let applied = selected();

    function apply(sel, instant) {
      const rtl = getComputedStyle(group).direction === "rtl";
      const push = ((widths[sel] ?? 0) * swell) / 2 + barge;
      chips.forEach((chip, i) => {
        const mv = mvs[i];
        const on = i === sel, far = Math.abs(i - sel);
        const x = Math.sign(i - sel) * (rtl ? -1 : 1) * push;
        const s = on ? 1 + swell : 1 - shrink;
        chip.dataset.on = String(on);
        chip.tabIndex = on ? 0 : -1;
        if (instant || reduce) { mv.x.jump(x); mv.sx.jump(s); mv.sy.jump(s); return; }
        const k = stiffness * (1 - 0.12 * Math.min(far, 3));
        const inFlight = mv.x.isAnimating() || mv.sx.isAnimating() || mv.sy.isAnimating();
        const delay = inFlight ? 0 : (far * stagger) / 1000;
        mv.x.animate(x, spring(k, 0.9, bounce), delay);
        // Wide before tall: the horizontal scale is stiffer and bouncier, the vertical one lags behind.
        mv.sx.animate(s, spring(k * (1 + 0.24 * jelly), 0.9 - 0.1 * jelly, Math.min(0.85, bounce + 0.3 * jelly)), delay);
        mv.sy.animate(s, spring(k * (1 - 0.14 * jelly), 0.9 + 0.05 * jelly, bounce), delay + 0.05 * jelly);
      });
    }

    // Room for the swollen chip and the shoved neighbours, measured from the real chip sizes.
    function measure() {
      widths = chips.map((c) => c.offsetWidth);
      const maxW = Math.max(0, ...widths);
      group.style.setProperty("--jr-pad-x", `${Math.ceil((maxW * swell * 1.3) / 2 + barge) + 2}px`);
      group.style.setProperty("--jr-pad-y", `${Math.ceil(((chips[0]?.offsetHeight ?? 0) * swell) / 2) + 2}px`);
    }
    const settle = () => { measure(); apply(applied, true); };
    settle();
    const resize = new ResizeObserver(settle);
    resize.observe(group);
    document.fonts?.ready.then(settle);

    // The page changes aria-checked (its own click handlers): animate to the new choice.
    const watch = new MutationObserver(() => {
      const sel = selected();
      if (sel === applied) return;
      applied = sel;
      apply(sel, false);
    });
    chips.forEach((c) => watch.observe(c, { attributes: true, attributeFilter: ["aria-checked"] }));

    // Radio-group keyboard: arrows, Home and End move the choice (by clicking, so the page's handlers run).
    const onKey = (e) => {
      const i = chips.indexOf(e.target.closest('[role="radio"]'));
      if (i < 0) return;
      const n = chips.length;
      const stepFrom = (from, dir) => {
        let j = from;
        for (let t = 0; t < n; t++) { j = (j + dir + n) % n; if (!chips[j].disabled) return j; }
        return from;
      };
      let next = null;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") next = stepFrom(i, 1);
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = stepFrom(i, -1);
      else if (e.key === "Home") next = stepFrom(-1, 1);
      else if (e.key === "End") next = stepFrom(n, -1);
      if (next === null) return;
      e.preventDefault();
      chips[next].click();
      chips[next].focus();
    };
    group.addEventListener("keydown", onKey);

    return () => { resize.disconnect(); watch.disconnect(); group.removeEventListener("keydown", onKey); };
  }

  window.jellyRadio = jellyRadio;
})();
