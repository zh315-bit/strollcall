// CircularGallery from React Bits (https://reactbits.dev, MIT + Commons Clause), ported from the React
// JS + CSS variant to plain DOM. Cards sit on a gentle arc in one WebGL2 canvas; drag, swipe, horizontal
// wheel or the arrow keys move them, and the gallery settles on the nearest card.
// Trimmed for StrollCall: no "open a card to full size" mode, no auto-scroll, no font loading (the page's
// fonts are already loaded), and a vertical wheel scrolls the page instead of the gallery.
// Usage: circularGallery(el, { items: [{ image, text, alt }], onActiveChange(i) {…}, … })
// returns { focus(index), destroy() }. Returns null without WebGL2; the caller keeps its own fallback.

(() => {
  const SEGMENTS_X = 32;
  const SEGMENTS_Y = 24;
  const INTRO_SECONDS = 1.4;
  const WORLD_HEIGHT = 16.57;
  const STEPS = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

  const VERTEX = `#version 300 es
in vec2 aPosition;
uniform vec2 uResolution;
uniform vec2 uCenter;
uniform vec2 uSize;
uniform float uAngle;
uniform float uPad;
uniform float uWave;
uniform float uWaveTime;
uniform float uFocal;
out vec2 vLocal;
void main() {
  vec2 local = aPosition * (uSize + 2.0 * uPad);
  vec2 unit = local / max(uSize, vec2(1.0));
  float z = uWave * (sin(unit.x * 4.0 + uWaveTime) + cos(unit.y * 2.0 + uWaveTime)) * 0.5;
  float depth = uFocal / max(uFocal - z, 1.0);
  float c = cos(uAngle);
  float s = sin(uAngle);
  vec2 turned = vec2(c * local.x - s * local.y, s * local.x + c * local.y);
  vLocal = local;
  gl_Position = vec4((uCenter + turned * depth) / (uResolution * 0.5), 0.0, 1.0);
}`;

  const FRAGMENT = `#version 300 es
precision highp float;
uniform sampler2D uTexture;
uniform vec2 uResolution;
uniform vec2 uSize;
uniform float uRadius;
uniform float uImageAspect;
uniform float uReady;
uniform vec3 uPlaceholder;
uniform float uDim;
uniform float uAlpha;
uniform float uRing;
uniform vec3 uRingColor;
uniform float uRingWidth;
uniform float uRingGap;
uniform float uFade;
uniform float uShadow;
uniform float uBlur;
uniform vec2 uShadowOffset;
in vec2 vLocal;
out vec4 outColor;

float roundBox(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

float smoother(float x) {
  x = clamp(x, 0.0, 1.0);
  return x * x * x * (x * (x * 6.0 - 15.0) + 10.0);
}

float edgeFade() {
  if (uFade <= 0.0) return 1.0;
  float u = gl_FragCoord.x / uResolution.x;
  return smoother(u / uFade) * smoother((1.0 - u) / uFade);
}

void main() {
  vec2 extent = uSize * 0.5;
  if (uShadow > 0.0) {
    float d = roundBox(vLocal - uShadowOffset, extent, uRadius);
    float a = uShadow * (1.0 - smoothstep(-uBlur, uBlur, d)) * uAlpha * edgeFade();
    outColor = vec4(0.0, 0.0, 0.0, a);
    return;
  }
  float d = roundBox(vLocal, extent, uRadius);
  float pixel = max(length(vec2(dFdx(d), dFdy(d))), 1e-4);
  float cover = clamp(0.5 - d / pixel, 0.0, 1.0);
  vec2 uv = vLocal / uSize + 0.5;
  float aspect = uSize.x / uSize.y;
  vec2 crop = aspect > uImageAspect ? vec2(1.0, uImageAspect / aspect) : vec2(aspect / uImageAspect, 1.0);
  vec3 image = texture(uTexture, (uv - 0.5) * crop + 0.5).rgb;
  vec3 color = mix(uPlaceholder, image, uReady) * (1.0 - uDim);
  float body = cover * mix(0.08, 1.0, uReady);
  float band = abs(d - uRingGap - uRingWidth * 0.5) - uRingWidth * 0.5;
  float ring = clamp(0.5 - band / pixel, 0.0, 1.0) * uRing;
  vec4 card = vec4(color * body, body);
  vec4 outline = vec4(uRingColor * ring, ring);
  outColor = (card + outline * (1.0 - card.a)) * uAlpha * edgeFade();
}`;

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const mix = (a, b, t) => a + (b - a) * t;
  const ease = (value) => value * value * (3 - 2 * value);
  const wrap = (value, length) => ((value % length) + length) % length;
  const fontScale = (font) => {
    const match = String(font).match(/(\d+(?:\.\d+)?)px/);
    return match ? parseFloat(match[1]) / 30 : 1;
  };

  const compile = (gl, type, source) => {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return shader;
    gl.deleteShader(shader);
    return null;
  };

  const link = (gl) => {
    const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX);
    const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
    const program = gl.createProgram();
    if (!vertex || !fragment || !program) return null;
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.bindAttribLocation(program, 0, "aPosition");
    gl.linkProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) { gl.deleteProgram(program); return null; }
    const uniforms = {};
    const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < count; i++) {
      const info = gl.getActiveUniform(program, i);
      if (info) uniforms[info.name] = gl.getUniformLocation(program, info.name);
    }
    return { program, uniforms };
  };

  function circularGallery(container, {
    items = [], bend = 3, textColor = "#ffffff", borderRadius = 0.05, font = "bold 30px sans-serif",
    scrollSpeed = 2, scrollEase = 0.05, itemSize = 1, itemAspect = 0.78, gap = 0.26, wave = 1,
    fadeEdges = 0.12, shadow = 0.25, showTitles = true, snap = true, intro = true, start = 0,
    label = "Image gallery", onItemClick, onActiveChange, dpr,
  } = {}) {
    if (!items.length) return null;
    const s = {
      bend, textColor, font, showTitles, snap, dpr,
      borderRadius: clamp(borderRadius, 0, 0.5), scrollSpeed: Math.max(0, scrollSpeed),
      scrollEase: clamp(scrollEase, 0.001, 1), itemSize: clamp(itemSize, 0.2, 2),
      itemAspect: clamp(itemAspect, 0.2, 5), gap: Math.max(0, gap), wave: Math.max(0, wave),
      fadeEdges: clamp(fadeEdges, 0, 0.5), shadow: clamp(shadow, 0, 1),
    };
    const count = items.length;

    container.classList.add("circular-gallery");
    container.setAttribute("role", "region");
    container.setAttribute("aria-roledescription", "carousel");
    container.setAttribute("aria-label", label);
    container.style.color = textColor;
    const canvas = document.createElement("canvas");
    canvas.className = "circular-gallery-canvas";
    canvas.setAttribute("aria-hidden", "true");
    const labelLayer = document.createElement("div");
    labelLayer.className = "circular-gallery-labels";
    labelLayer.setAttribute("aria-hidden", "true");
    const gl = canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false });
    const program = gl && link(gl);
    if (!program) { container.classList.remove("circular-gallery"); return null; }
    const u = program.uniforms;

    // Screen readers and the keyboard get a plain list of buttons, one per card.
    const list = document.createElement("ul");
    list.className = "circular-gallery-hidden";
    list.dataset.galleryList = "";
    const buttons = items.map((item, index) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.text || item.alt || `Image ${index + 1}`;
      button.setAttribute("aria-label", `${item.text || item.alt || "Image"}, ${index + 1} of ${count}`);
      button.addEventListener("focus", () => setSlot(slotFor(index)));
      li.append(button);
      list.append(li);
      return button;
    });
    container.replaceChildren(canvas, labelLayer, list);

    const vertices = [];
    for (let y = 0; y <= SEGMENTS_Y; y++) {
      for (let x = 0; x <= SEGMENTS_X; x++) vertices.push(x / SEGMENTS_X - 0.5, y / SEGMENTS_Y - 0.5);
    }
    const indices = [];
    for (let y = 0; y < SEGMENTS_Y; y++) {
      for (let x = 0; x < SEGMENTS_X; x++) {
        const a = y * (SEGMENTS_X + 1) + x, b = a + 1, c = a + SEGMENTS_X + 1, d = c + 1;
        indices.push(a, b, d, a, d, c);
      }
    }
    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const vertexBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    const indexBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);

    const anisotropy = gl.getExtension("EXT_texture_filter_anisotropic");
    const blank = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, blank);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([0, 0, 0, 0]));

    // textColor may be a CSS variable: read the colour the container actually resolves to.
    const probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
    const colorCache = new Map();
    const parse = (value) => {
      const key = String(value);
      if (colorCache.has(key)) return colorCache.get(key);
      let rgb = [1, 1, 1];
      if (probe) {
        probe.clearRect(0, 0, 1, 1);
        probe.fillStyle = "#ffffff";
        probe.fillStyle = key;
        probe.fillRect(0, 0, 1, 1);
        const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
        rgb = [r / 255, g / 255, b / 255];
      }
      colorCache.set(key, rgb);
      return rgb;
    };

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const textures = new Map();
    const view = { width: 1, height: 1, ratio: 1 };
    const state = {
      scroll: 0, target: 0, velocity: 0, intro: intro && !reduce ? 0 : 1, waveTime: 0, ring: 0,
      keyboard: false, hovered: null, hover: new Map(), drag: null, lastInput: 0, active: 0, spacing: 1,
    };
    let cards = [];
    let pool = [];
    let raf = 0;
    let last = 0;
    let visible = true;
    let snapTimer = 0;
    let typing = false;
    let alive = true;

    const textureFor = (url) => {
      const existing = textures.get(url);
      if (existing) return existing;
      const entry = { texture: null, aspect: 1, ready: 0, loaded: false };
      textures.set(url, entry);
      const image = new Image();
      image.crossOrigin = "anonymous";
      image.decoding = "async";
      image.onload = () => {
        if (!alive) return;
        const texture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
        gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        if (anisotropy) {
          const max = gl.getParameter(anisotropy.MAX_TEXTURE_MAX_ANISOTROPY_EXT);
          gl.texParameterf(gl.TEXTURE_2D, anisotropy.TEXTURE_MAX_ANISOTROPY_EXT, Math.min(8, max));
        }
        entry.texture = texture;
        entry.aspect = image.naturalWidth / Math.max(1, image.naturalHeight);
        entry.loaded = true;
        wake();
      };
      image.src = url;
      return entry;
    };

    const measure = () => {
      const height = 0.6 * view.height * s.itemSize;
      const width = height * s.itemAspect;
      const scale = Math.min(1, (view.width * 0.82) / width);
      return { w: width * scale, h: height * scale, spacing: width * scale * (1 + s.gap) };
    };

    const arcOf = (x) => {
      if (!s.bend) return { y: 0, angle: 0 };
      const depth = (Math.abs(s.bend) * view.height) / WORLD_HEIGHT;
      const half = Math.max(view.width, view.height * 1.9) / 2;
      const radius = (half * half + depth * depth) / (2 * depth);
      const reach = Math.min(Math.abs(x), half, radius * 0.999);
      const arc = radius - Math.sqrt(radius * radius - reach * reach);
      const angle = Math.sign(x) * Math.asin(reach / radius);
      return s.bend > 0 ? { y: -arc, angle: -angle } : { y: arc, angle };
    };

    const ensurePool = (spacing) => {
      const size = Math.ceil(view.width / Math.max(spacing, 1)) + 8;
      if (pool.length === size) return;
      labelLayer.replaceChildren();
      pool = Array.from({ length: size }, () => {
        const el = document.createElement("span");
        el.className = "circular-gallery-label";
        el.style.opacity = "0";
        labelLayer.append(el);
        return { el, slot: null, font: "", text: "" };
      });
    };

    const layout = () => {
      const { w, h, spacing } = measure();
      state.spacing = spacing;
      const introEase = 1 - Math.pow(1 - state.intro, 3);
      const scroll = state.scroll + (1 - introEase) * spacing * 1.6;
      const first = Math.floor((scroll - view.width / 2 - spacing * 2) / spacing);
      const lastSlot = Math.ceil((scroll + view.width / 2 + spacing * 2) / spacing);
      const next = [];
      for (let slot = first; slot <= lastSlot; slot++) {
        const index = wrap(slot, count);
        const item = items[index];
        const x = slot * spacing - scroll;
        const arc = arcOf(x);
        const order = Math.abs(slot * spacing - state.scroll) / spacing;
        const shown = ease(clamp(state.intro * 2.2 - order * 0.22, 0, 1));
        const lift = 1 + (state.hover.get(slot) || 0) * 0.04;
        next.push({
          slot, index, item, entry: textureFor(item.image), x,
          y: arc.y - (1 - shown) * h * 0.18, angle: arc.angle, w: w * lift, h: h * lift,
          radius: s.borderRadius * Math.min(w, h), alpha: shown,
        });
      }
      next.sort((a, b) => Math.abs(b.x) - Math.abs(a.x));
      cards = next;
      return { w, h, spacing };
    };

    const draw = (metrics) => {
      const ratio = view.ratio;
      const color = parse(getComputedStyle(container).color);
      const speed = Math.min(Math.abs(state.velocity) / Math.max(metrics.spacing * 4, 1), 1);
      const wavePx = reduce ? 0 : s.wave * speed * view.height * 0.08 * ratio;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.useProgram(program.program);
      gl.bindVertexArray(vao);
      gl.uniform2f(u.uResolution, canvas.width, canvas.height);
      gl.uniform1f(u.uFocal, view.height * 1.207 * ratio);
      gl.uniform1f(u.uWaveTime, state.waveTime);
      gl.uniform1f(u.uFade, s.fadeEdges);
      gl.uniform3fv(u.uPlaceholder, color);
      gl.uniform3fv(u.uRingColor, color);
      gl.uniform1f(u.uRingWidth, 2 * ratio);
      gl.uniform1f(u.uRingGap, 5 * ratio);
      gl.uniform1f(u.uDim, 0);
      gl.activeTexture(gl.TEXTURE0);
      gl.uniform1i(u.uTexture, 0);
      const vertexCount = SEGMENTS_X * SEGMENTS_Y * 6;
      const blur = Math.max(10, metrics.h * 0.09) * ratio;
      const place = (card) => {
        gl.uniform2f(u.uCenter, card.x * ratio, card.y * ratio);
        gl.uniform2f(u.uSize, card.w * ratio, card.h * ratio);
        gl.uniform1f(u.uAngle, card.angle);
        gl.uniform1f(u.uRadius, Math.min(card.radius, card.w / 2, card.h / 2) * ratio);
        gl.uniform1f(u.uWave, wavePx);
        gl.uniform1f(u.uAlpha, card.alpha);
      };
      if (s.shadow > 0) {
        gl.uniform1f(u.uShadow, s.shadow);
        gl.uniform1f(u.uBlur, blur);
        gl.uniform2f(u.uShadowOffset, 0, -blur * 0.45);
        gl.uniform1f(u.uPad, blur * 1.6);
        gl.bindTexture(gl.TEXTURE_2D, blank);
        cards.forEach((card) => { place(card); gl.drawElements(gl.TRIANGLES, vertexCount, gl.UNSIGNED_SHORT, 0); });
      }
      gl.uniform1f(u.uShadow, 0);
      gl.uniform1f(u.uPad, 10 * ratio);
      cards.forEach((card) => {
        place(card);
        gl.bindTexture(gl.TEXTURE_2D, card.entry.texture || blank);
        gl.uniform1f(u.uImageAspect, card.entry.aspect);
        gl.uniform1f(u.uReady, card.entry.ready);
        gl.uniform1f(u.uRing, card.slot === state.active ? state.ring : 0);
        gl.drawElements(gl.TRIANGLES, vertexCount, gl.UNSIGNED_SHORT, 0);
      });
    };

    const placeLabels = (metrics) => {
      ensurePool(metrics.spacing);
      const used = new Set();
      const fade = (value) => {
        if (s.fadeEdges <= 0) return 1;
        const t = clamp(value / s.fadeEdges, 0, 1);
        return t * t * t * (t * (t * 6 - 15) + 10);
      };
      const size = metrics.h * 0.072 * fontScale(s.font);
      if (s.showTitles) {
        cards.forEach((card) => {
          if (!card.item.text) return;
          const entry = pool[wrap(card.slot, pool.length)];
          used.add(entry);
          if (entry.slot !== card.slot || entry.text !== card.item.text) {
            entry.slot = card.slot;
            entry.text = card.item.text;
            entry.el.textContent = card.item.text;
          }
          if (entry.font !== s.font) { entry.font = s.font; entry.el.style.font = s.font; }
          const offset = card.h / 2 + size * 1.1;
          const x = card.x + Math.sin(card.angle) * offset;
          const y = card.y - Math.cos(card.angle) * offset;
          const cssX = view.width / 2 + x;
          const cssY = view.height / 2 - y;
          entry.el.style.fontSize = `${size}px`;
          entry.el.style.transform = `translate(${cssX}px, ${cssY}px) translate(-50%, -50%) rotate(${-card.angle}rad)`;
          entry.el.style.opacity = String(card.alpha * fade(cssX / view.width) * fade(1 - cssX / view.width));
        });
      }
      pool.forEach((entry) => { if (!used.has(entry) && entry.el.style.opacity !== "0") entry.el.style.opacity = "0"; });
    };

    const markActive = (index) => buttons.forEach((b, i) => {
      b.tabIndex = i === index ? 0 : -1;
      if (i === index) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
    });

    const nearest = () => Math.round(state.target / Math.max(state.spacing, 1));

    const setSlot = (slot, announce = true) => {
      state.target = slot * state.spacing;
      if (slot !== state.active) {
        state.active = slot;
        const index = wrap(slot, count);
        markActive(index);
        if (announce) onActiveChange?.(index);
      }
      wake();
    };

    const frame = (now) => {
      raf = 0;
      if (!visible || document.hidden) return;
      const dt = last ? clamp((now - last) / 1000, 0.0005, 0.05) : 1 / 60;
      last = now;
      const follow = reduce ? 1 : 1 - Math.pow(1 - s.scrollEase, dt * 60);
      const before = state.scroll;
      state.scroll += (state.target - state.scroll) * follow;
      if (Math.abs(state.target - state.scroll) < 0.05) state.scroll = state.target;
      const velocity = (state.scroll - before) / dt;
      state.velocity += (velocity - state.velocity) * (1 - Math.exp(-dt / 0.08));
      if (Math.abs(state.velocity) < 0.5) state.velocity = 0;
      state.waveTime += dt * 2.4;
      state.ring += ((state.keyboard ? 1 : 0) - state.ring) * (1 - Math.exp(-dt / 0.1));
      if (Math.abs((state.keyboard ? 1 : 0) - state.ring) < 0.002) state.ring = state.keyboard ? 1 : 0;
      if (state.intro < 1) state.intro = Math.min(1, state.intro + dt / INTRO_SECONDS);
      let settling = false;
      state.hover.forEach((value, slot) => {
        const goal = slot === state.hovered ? 1 : 0;
        const next = value + (goal - value) * (1 - Math.exp(-dt / 0.12));
        if (Math.abs(goal - next) < 0.002) {
          if (goal === 0) state.hover.delete(slot); else state.hover.set(slot, 1);
        } else { state.hover.set(slot, next); settling = true; }
      });
      textures.forEach((entry) => {
        if (!entry.loaded || entry.ready >= 1) return;
        entry.ready = reduce ? 1 : Math.min(1, entry.ready + dt / 0.45);
        settling = true;
      });
      const slot = nearest();
      if (slot !== state.active && !state.drag) {
        state.active = slot;
        const index = wrap(slot, count);
        markActive(index);
        onActiveChange?.(index);
      }
      const metrics = layout();
      draw(metrics);
      placeLabels(metrics);
      const moving = state.scroll !== state.target || state.velocity !== 0 || state.intro < 1
        || (state.ring !== 0 && state.ring !== 1) || settling;
      if (moving) raf = requestAnimationFrame(frame);
      else last = 0;
    };

    function wake() {
      if (alive && !raf && visible && !document.hidden) raf = requestAnimationFrame(frame);
    }

    const resize = () => {
      view.width = Math.max(1, container.clientWidth);
      view.height = Math.max(1, container.clientHeight);
      view.ratio = Math.min(s.dpr || window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(view.width * view.ratio));
      canvas.height = Math.max(1, Math.round(view.height * view.ratio));
      const before = state.spacing;
      const { spacing } = measure();
      if (before > 1 && spacing !== before) {
        state.scroll = (state.scroll / before) * spacing;
        state.target = (state.target / before) * spacing;
      }
      state.spacing = spacing;
      wake();
    };

    const point = (event) => {
      const rect = container.getBoundingClientRect();
      return { x: event.clientX - rect.left - rect.width / 2, y: rect.height / 2 - (event.clientY - rect.top) };
    };

    const hit = ({ x, y }) => {
      for (let i = cards.length - 1; i >= 0; i--) {
        const card = cards[i];
        if (card.alpha < 0.05) continue;
        const dx = x - card.x, dy = y - card.y;
        const c = Math.cos(-card.angle), sn = Math.sin(-card.angle);
        const lx = c * dx - sn * dy, ly = sn * dx + c * dy;
        if (Math.abs(lx) <= card.w / 2 && Math.abs(ly) <= card.h / 2) return card;
      }
      return null;
    };

    const setPointer = (card) => {
      const slot = card ? card.slot : null;
      if (slot !== state.hovered) {
        state.hovered = slot;
        if (slot !== null && !state.hover.has(slot)) state.hover.set(slot, 0);
        wake();
      }
      if (card) container.setAttribute("data-pointer", ""); else container.removeAttribute("data-pointer");
    };

    const snapNow = () => { if (s.snap) setSlot(nearest()); };

    const onPointerDown = (event) => {
      if (event.button !== 0) return;
      state.drag = { id: event.pointerId, x0: event.clientX, y0: event.clientY, start: state.target,
                     moved: false, samples: [], p: point(event) };
      state.lastInput = performance.now();
      wake();
    };

    const onPointerMove = (event) => {
      const drag = state.drag;
      if (drag && drag.id === event.pointerId) {
        const dx = event.clientX - drag.x0, dy = event.clientY - drag.y0;
        if (!drag.moved && Math.hypot(dx, dy) > 6) {
          // A mostly vertical swipe on a touch screen is a page scroll, not a gallery drag.
          if (Math.abs(dy) > Math.abs(dx) && event.pointerType !== "mouse") { state.drag = null; return; }
          drag.moved = true;
          container.setPointerCapture?.(event.pointerId);
          container.setAttribute("data-dragging", "");
          setPointer(null);
        }
        if (drag.moved) {
          state.target = drag.start - dx * (s.scrollSpeed / 2);
          drag.samples.push({ x: event.clientX, t: performance.now() });
          if (drag.samples.length > 6) drag.samples.shift();
          state.lastInput = performance.now();
          wake();
        }
        return;
      }
      if (event.pointerType === "mouse") setPointer(hit(point(event)));
    };

    const onPointerUp = (event) => {
      const drag = state.drag;
      if (!drag || drag.id !== event.pointerId) return;
      state.drag = null;
      container.removeAttribute("data-dragging");
      if (container.hasPointerCapture?.(event.pointerId)) container.releasePointerCapture(event.pointerId);
      if (drag.moved) {
        const samples = drag.samples;
        if (samples.length > 1) {
          const a = samples[0], b = samples[samples.length - 1];
          const span = Math.max(b.t - a.t, 16);
          state.target -= ((b.x - a.x) / span) * 1000 * 0.18 * (s.scrollSpeed / 2);
        }
        snapNow();
        return;
      }
      // A click centres the card it lands on.
      const card = hit(drag.p);
      if (!card) return;
      onItemClick?.(card.item, card.index);
      setSlot(card.slot);
    };

    const onPointerCancel = (event) => {
      if (state.drag && state.drag.id === event.pointerId) {
        state.drag = null;
        container.removeAttribute("data-dragging");
        snapNow();
      }
    };

    const onPointerLeave = () => setPointer(null);

    // Only a sideways wheel (trackpad swipe, shift+wheel) moves the gallery; an up/down wheel keeps scrolling the page.
    const onWheel = (event) => {
      if (Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? view.height : 1;
      event.preventDefault();
      state.target += event.deltaX * unit * (s.scrollSpeed / 2);
      state.lastInput = performance.now();
      clearTimeout(snapTimer);
      snapTimer = setTimeout(snapNow, 140);
      wake();
    };

    const onKeyDown = (event) => {
      const step = STEPS[event.key];
      state.lastInput = performance.now();
      if (step) {
        event.preventDefault();
        if (container.contains(document.activeElement)) state.keyboard = true;
        setSlot(nearest() + step);
        if (container.contains(document.activeElement)) buttons[wrap(state.active, count)].focus({ preventScroll: true });
        return;
      }
      if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        const base = nearest() - wrap(nearest(), count);
        setSlot(event.key === "Home" ? base : base + count - 1);
      }
    };

    const onFocusIn = (event) => {
      if (!event.target.closest("[data-gallery-list]")) return;
      state.keyboard = typing || event.target.matches(":focus-visible");
      wake();
    };
    const onAnyKey = (event) => { if (event.key === "Tab" || event.key.startsWith("Arrow")) typing = true; };
    const onAnyPointer = () => { typing = false; };
    const onFocusOut = (event) => {
      if (container.contains(event.relatedTarget)) return;
      state.keyboard = false;
      wake();
    };
    const onVisibility = () => { last = 0; wake(); };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);
    const intersection = new IntersectionObserver((entries) => {
      visible = entries.some((entry) => entry.isIntersecting);
      if (visible) { last = 0; wake(); }
    });
    intersection.observe(container);
    container.addEventListener("pointerdown", onPointerDown);
    container.addEventListener("pointermove", onPointerMove);
    container.addEventListener("pointerup", onPointerUp);
    container.addEventListener("pointercancel", onPointerCancel);
    container.addEventListener("pointerleave", onPointerLeave);
    container.addEventListener("wheel", onWheel, { passive: false });
    container.addEventListener("keydown", onKeyDown);
    container.addEventListener("focusin", onFocusIn);
    container.addEventListener("focusout", onFocusOut);
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("keydown", onAnyKey, true);
    document.addEventListener("pointerdown", onAnyPointer, true);
    items.forEach((item) => textureFor(item.image));
    resize();
    state.active = clamp(Math.round(start), 0, count - 1);
    state.scroll = state.target = state.active * state.spacing;
    markActive(state.active);

    const slotFor = (index) => {
      const slot = nearest();
      const base = slot - wrap(slot, count) + index;
      return [base - count, base, base + count].reduce((best, value) =>
        (Math.abs(value - slot) < Math.abs(best - slot) ? value : best));
    };

    return {
      // Centre a card from outside (the page's own choice); does not call onActiveChange back.
      focus(index) { if (wrap(state.active, count) !== index) setSlot(slotFor(index), false); },
      destroy() {
        alive = false;
        cancelAnimationFrame(raf);
        clearTimeout(snapTimer);
        resizeObserver.disconnect();
        intersection.disconnect();
        container.removeEventListener("pointerdown", onPointerDown);
        container.removeEventListener("pointermove", onPointerMove);
        container.removeEventListener("pointerup", onPointerUp);
        container.removeEventListener("pointercancel", onPointerCancel);
        container.removeEventListener("pointerleave", onPointerLeave);
        container.removeEventListener("wheel", onWheel);
        container.removeEventListener("keydown", onKeyDown);
        container.removeEventListener("focusin", onFocusIn);
        container.removeEventListener("focusout", onFocusOut);
        document.removeEventListener("visibilitychange", onVisibility);
        document.removeEventListener("keydown", onAnyKey, true);
        document.removeEventListener("pointerdown", onAnyPointer, true);
        textures.forEach((entry) => entry.texture && gl.deleteTexture(entry.texture));
        gl.deleteTexture(blank);
        gl.deleteProgram(program.program);
        gl.deleteBuffer(vertexBuffer);
        gl.deleteBuffer(indexBuffer);
        gl.deleteVertexArray(vao);
        gl.getExtension("WEBGL_lose_context")?.loseContext();
        container.replaceChildren();
      },
    };
  }

  // ---- Route options as a carousel: one card per plan, the centred card is the chosen plan ----
  // Each card shows the illustration for where that walk ends. The page re-renders its plan card on every
  // choice, so the gallery element is kept and handed back for the same set of plans.

  const ENDINGS = ["cafe", "bakery", "bookstore", "ice_cream", "landmark", "park"];
  const SCENES = ["park", "quiet", "lively", "historic"];
  let current = null; // { key, el, gallery, onChoose }

  // plans: [{ id, title, category }]; returns the element to place in the card, or null (no WebGL2:
  // the page keeps its tabs).
  function planCarousel(plans, chosen, onChoose) {
    const key = plans.map((p) => p.id).join("|");
    if (!current || current.key !== key) {
      current?.gallery.destroy();
      current = null;
      const el = document.createElement("div");
      el.className = "plan-gallery";
      const gallery = circularGallery(el, {
        items: plans.map((p, i) => ({
          image: `/static/illustrations/thumbs/${SCENES[i % SCENES.length]}-${ENDINGS.includes(p.category) ? p.category : "landmark"}.jpg`,
          text: p.title, alt: p.title,
        })),
        start: chosen, label: "Walk options", textColor: "var(--ink)", font: '700 44px "M PLUS Rounded 1c", sans-serif',
        bend: 2.4, itemSize: 0.92, itemAspect: 1.3, gap: 0.18, borderRadius: 0.1, fadeEdges: 0.1, shadow: 0.18,
        scrollEase: 0.08, onActiveChange: (i) => current?.onChoose(i),
      });
      if (!gallery) return null;
      current = { key, el, gallery };
    }
    current.onChoose = onChoose; // the latest page closure (it may hold a newer copy of the plans)
    current.gallery.focus(chosen);
    return current.el;
  }

  window.circularGallery = circularGallery;
  window.planCarousel = planCarousel;
})();
