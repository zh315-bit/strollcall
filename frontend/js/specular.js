// SpecularButton from React Bits (https://reactbits.dev, MIT + Commons Clause), ported from the React
// JS + CSS variant to plain DOM: a light that runs along the button's rounded edge and slides toward the cursor.
// Differences from the original:
// - It upgrades existing <button>s instead of rendering its own: every button on the page except the
//   friend / solo switch and the small "×" inside chips, including buttons the page scripts add later.
// - One shared WebGL2 context draws the original shader for all buttons and copies each frame into the
//   button's own 2D canvas (browsers keep only ~16 WebGL contexts alive, and a page can have more buttons).
// - Colors and corner radius come from CSS (--sb-line, --sb-base, border-radius), so they follow the theme.
// - When a page script rewrites a button's content (textContent, replaceChildren), the layers are put back.

(() => {
  const PAD = 24;
  const SKIP = ".mode-switch button, .chip button, .near-refresh, .walk-recenter, .plan-deck-dots button";
  // The original props, as one shared setting for every button.
  const S = { intensity: 1, idleIntensity: 0.35, shineSize: 10, shineFade: 34, thickness: 1.2, glow: 1,
              followMouse: true, proximity: 250 };

  const VERTEX = `#version 300 es
in vec2 aPosition;
void main() {
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`;

  // The original fragment shader, unchanged.
  const FRAGMENT = `#version 300 es
precision highp float;
uniform vec2 uCenter;
uniform vec2 uHalf;
uniform float uRadius;
uniform float uPx;
uniform float uSpot;
uniform vec2 uEntry;
uniform vec3 uLineColor;
uniform vec3 uBaseColor;
uniform float uIntensity;
uniform vec2 uWindow;
uniform float uThickness;
uniform float uGlow;
out vec4 outColor;

float roundedBox(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

float loopPosition(vec2 p, vec2 b, float r) {
  vec2 inner = b - r;
  float arc = 1.5707963 * r;
  float quarter = inner.x + inner.y + arc;
  vec2 a = abs(p);
  vec2 q = a - inner;
  float s = q.x > 0.0 && q.y > 0.0
    ? inner.y + atan(q.y, q.x) * r
    : (q.x > q.y ? min(a.y, inner.y) : inner.y + arc + inner.x - min(a.x, inner.x));
  if (p.x < 0.0) s = p.y >= 0.0 ? 2.0 * quarter - s : 2.0 * quarter + s;
  else if (p.y < 0.0) s = 4.0 * quarter - s;
  return s / max(4.0 * quarter, 0.0001);
}

float lobe(float position, float center) {
  float gap = abs(fract(position - center + 0.5) - 0.5);
  return 1.0 - smoothstep(uWindow.x, uWindow.x + uWindow.y, gap);
}

void main() {
  vec2 p = gl_FragCoord.xy - uCenter;
  float d = roundedBox(p, uHalf, uRadius);
  float position = loopPosition(p, uHalf, uRadius);
  float key = lobe(position, uSpot);
  float back = lobe(position, uSpot + 0.5);
  float streak = key + back * 0.45;
  float width = max(uThickness * uPx * mix(1.0, max(key, back), 0.6), 0.35);
  float band = smoothstep(-width - 0.6, -width + 0.6, d) * (1.0 - smoothstep(-0.6, 0.6, d));
  float hair = smoothstep(-uPx - 0.6, -uPx + 0.6, d) * (1.0 - smoothstep(-0.6, 0.6, d));
  float inside = 1.0 - smoothstep(-0.6, 0.6, d);
  vec2 pool = (p - uEntry) / (uHalf.y * vec2(1.6, 1.1));
  float glow = streak * 0.2 * exp(-abs(d + width * 0.5) / (5.0 * uPx)) + inside * 0.08 * exp(-dot(pool, pool));
  float light = clamp((band * streak + glow * uGlow) * uIntensity, 0.0, 1.0);
  vec4 base = vec4(uBaseColor, 1.0) * hair * 0.6;
  outColor = vec4(uLineColor, 1.0) * light + base * (1.0 - light);
}`;

  const UNIFORMS = ["uCenter", "uHalf", "uRadius", "uPx", "uSpot", "uEntry", "uLineColor", "uBaseColor",
                    "uIntensity", "uWindow", "uThickness", "uGlow"];
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const wrap = (value) => value - Math.floor(value);

  // Position (0..1) around the rounded rectangle's edge, and back: same as the original.
  const loopPosition = (x, y, halfX, halfY, r) => {
    const innerX = halfX - r, innerY = halfY - r, arc = (Math.PI / 2) * r, quarter = innerX + innerY + arc;
    const ax = Math.abs(x), ay = Math.abs(y), qx = ax - innerX, qy = ay - innerY;
    let s;
    if (qx > 0 && qy > 0) s = innerY + Math.atan2(qy, qx) * r;
    else if (qx > qy) s = Math.min(ay, innerY);
    else s = innerY + arc + innerX - Math.min(ax, innerX);
    if (x < 0) s = y >= 0 ? 2 * quarter - s : 2 * quarter + s;
    else if (y < 0) s = 4 * quarter - s;
    return wrap(s / Math.max(4 * quarter, 0.0001));
  };
  const rimPoint = (position, halfX, halfY, r) => {
    const innerX = halfX - r, innerY = halfY - r, arc = (Math.PI / 2) * r, quarter = innerX + innerY + arc;
    let s = wrap(position) * 4 * quarter, signX = 1, signY = 1;
    if (s > 3 * quarter) { s = 4 * quarter - s; signY = -1; }
    else if (s > 2 * quarter) { s -= 2 * quarter; signX = -1; signY = -1; }
    else if (s > quarter) { s = 2 * quarter - s; signX = -1; }
    let x = innerX - (s - innerY - arc), y = halfY;
    if (s <= innerY) { x = halfX; y = s; }
    else if (s <= innerY + arc) {
      const angle = (s - innerY) / Math.max(r, 0.0001);
      x = innerX + Math.cos(angle) * r; y = innerY + Math.sin(angle) * r;
    }
    return [x * signX, y * signY];
  };

  // ---- The shared renderer ----

  const glCanvas = document.createElement("canvas");
  const gl = glCanvas.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: false, depth: false,
                                             stencil: false, preserveDrawingBuffer: true });
  let program = null, vao = null;
  const uniforms = {};
  if (gl) {
    const compile = (type, source) => {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source); gl.compileShader(shader);
      return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
    };
    const vertex = compile(gl.VERTEX_SHADER, VERTEX), fragment = compile(gl.FRAGMENT_SHADER, FRAGMENT);
    if (vertex && fragment) {
      program = gl.createProgram();
      gl.attachShader(program, vertex); gl.attachShader(program, fragment);
      gl.bindAttribLocation(program, 0, "aPosition");
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) program = null;
    }
    if (program) {
      for (const name of UNIFORMS) uniforms[name] = gl.getUniformLocation(program, name);
      vao = gl.createVertexArray();
      gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.bindVertexArray(null);
    }
  }

  const probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  const colors = new Map();
  const toRgb = (value) => {
    if (colors.has(value)) return colors.get(value);
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = "#000000"; probe.fillStyle = value;
    probe.fillRect(0, 0, 1, 1);
    const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
    const rgb = [r / 255, g / 255, b / 255];
    colors.set(value, rgb);
    return rgb;
  };

  // ---- One entry per upgraded button ----

  const entries = new Map(); // button -> entry
  const pointer = { x: 0, y: 0, known: false };
  let raf = 0, last = 0;
  const walking = () => document.body.classList.contains("walking");

  const cornerRadius = (e) => Math.min(e.radius, e.view.width / 2, e.view.height / 2);
  const restSpot = (e) => {
    const r = cornerRadius(e), inset = r * (1 - Math.SQRT1_2);
    return loopPosition(inset - e.view.width / 2, e.view.height / 2 - inset, e.view.width / 2, e.view.height / 2, r);
  };

  function aim(e) {
    if (!S.followMouse || e.button.disabled || !pointer.known) return null;
    const rect = e.button.getBoundingClientRect();
    const scale = rect.width / e.view.width || 1;
    const halfX = e.view.width / 2, halfY = e.view.height / 2;
    const x = (pointer.x - rect.left - rect.width / 2) / scale;
    const y = (rect.top + rect.height / 2 - pointer.y) / scale;
    const distance = Math.hypot(Math.max(Math.abs(x) - halfX, 0), Math.max(Math.abs(y) - halfY, 0));
    const t = clamp(1 - distance / S.proximity, 0, 1);
    const near = t * t * (3 - 2 * t);
    const nearest = loopPosition(x, y, halfX, halfY, cornerRadius(e));
    if (distance > 0) return { spot: nearest, near };
    const depth = clamp(Math.min(halfX - Math.abs(x), halfY - Math.abs(y)) / (halfY * 0.8), 0, 1);
    const sway = restSpot(e) - (x / halfX) * 0.06 - (y / halfY) * 0.02;
    const offset = sway - nearest - Math.round(sway - nearest);
    return { spot: wrap(nearest + offset * depth * depth * (3 - 2 * depth)), near };
  }

  function draw(e) {
    const { width, height, ratio } = e.view, out = e.canvas;
    if (!program || !width || !height) return;
    if (glCanvas.width < out.width || glCanvas.height < out.height) { // grow the shared canvas as needed
      glCanvas.width = Math.max(glCanvas.width, out.width); glCanvas.height = Math.max(glCanvas.height, out.height);
    }
    const scaleX = out.width / (width + PAD * 2), scaleY = out.height / (height + PAD * 2);
    gl.viewport(0, 0, out.width, out.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(program);
    gl.uniform2f(uniforms.uCenter, (PAD + width / 2) * scaleX, (PAD + height / 2) * scaleY);
    gl.uniform2f(uniforms.uHalf, (width / 2) * scaleX, (height / 2) * scaleY);
    gl.uniform1f(uniforms.uRadius, cornerRadius(e) * scaleX);
    gl.uniform1f(uniforms.uPx, ratio);
    const r = cornerRadius(e);
    const [rimX, rimY] = rimPoint(e.state.spot, width / 2, height / 2, r);
    const pull = 1 - Math.min(0.35 * (height / 2), Math.hypot(rimX, rimY)) / Math.max(Math.hypot(rimX, rimY), 0.0001);
    gl.uniform1f(uniforms.uSpot, e.state.spot);
    gl.uniform2f(uniforms.uEntry, rimX * pull * scaleX, rimY * pull * scaleY);
    gl.uniform3fv(uniforms.uLineColor, toRgb(e.line));
    gl.uniform3fv(uniforms.uBaseColor, toRgb(e.base));
    gl.uniform1f(uniforms.uIntensity, S.intensity * e.boost * (e.state.level + e.state.press * 0.8));
    gl.uniform2f(uniforms.uWindow, S.shineSize / 360 + e.state.press * 0.06, S.shineFade / 360 + 0.0001);
    gl.uniform1f(uniforms.uThickness, S.thickness);
    gl.uniform1f(uniforms.uGlow, S.glow);
    gl.bindVertexArray(vao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);
    // WebGL's origin is bottom-left: the frame sits in the bottom-left corner of the shared canvas.
    e.ctx.clearRect(0, 0, out.width, out.height);
    e.ctx.drawImage(glCanvas, 0, glCanvas.height - out.height, out.width, out.height, 0, 0, out.width, out.height);
  }

  // Advance one button (the original frame()); returns whether it is still moving.
  function step(e, dt) {
    if (!e.view.width || !e.view.height) return false; // hidden for now: measure() wakes it when it shows
    const target = aim(e);
    const steering = !!target && target.near > 0;
    if (!e.state.ready) { e.state.spot = restSpot(e); e.state.level = S.idleIntensity; e.state.ready = true; }
    let diff = (steering ? target.spot : restSpot(e)) - e.state.spot;
    diff -= Math.round(diff);
    e.state.spot = wrap(e.state.spot + diff * (1 - Math.exp(-dt * 8)));
    const level = S.idleIntensity + (1 - S.idleIntensity) * (target ? target.near : 0);
    e.state.level += (level - e.state.level) * (1 - Math.exp(-dt * 7));
    e.state.press *= Math.exp(-dt * 5);
    draw(e);
    return Math.abs(diff) > 0.0002 || Math.abs(level - e.state.level) > 0.001 || e.state.press > 0.002;
  }

  function frame(now) {
    raf = 0;
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 1 / 60;
    last = now;
    let moving = false;
    for (const [button, e] of entries) {
      if (!button.isConnected) { forget(button); continue; }
      if (!e.visible || !e.awake) continue;
      if (walking() && !button.closest(".walk-screen")) continue; // covered by the walking screen
      e.awake = step(e, dt);
      moving ||= e.awake;
    }
    if (moving) raf = requestAnimationFrame(frame);
    else last = 0;
  }
  const wake = (e) => {
    if (e) e.awake = true; else entries.forEach((x) => (x.awake = true));
    if (!raf) raf = requestAnimationFrame(frame);
  };

  // Theme colors and shape from CSS: re-read on resize and when the color scheme changes.
  function readStyle(e) {
    const cs = getComputedStyle(e.button);
    e.line = cs.getPropertyValue("--sb-line").trim() || "#ffffff";
    e.base = cs.getPropertyValue("--sb-base").trim() || "#525252";
    e.boost = parseFloat(cs.getPropertyValue("--sb-boost")) || 1;
    e.radius = parseFloat(cs.borderTopLeftRadius) || 0;
  }
  function measure(e) {
    readStyle(e);
    e.view.width = e.button.offsetWidth; e.view.height = e.button.offsetHeight;
    e.view.ratio = Math.min(window.devicePixelRatio || 1, 3);
    e.canvas.width = Math.max(1, Math.round((e.view.width + PAD * 2) * e.view.ratio));
    e.canvas.height = Math.max(1, Math.round((e.view.height + PAD * 2) * e.view.ratio));
    wake(e);
  }

  const resize = new ResizeObserver((list) => list.forEach((r) => { const e = entries.get(r.target); if (e) measure(e); }));
  const seen = new IntersectionObserver((list) => list.forEach((r) => {
    const e = entries.get(r.target);
    if (e) { e.visible = r.isIntersecting; if (e.visible) wake(e); }
  }));

  function forget(button) {
    entries.delete(button);
    resize.unobserve(button); seen.unobserve(button);
  }

  // Wrap the button's content as the original's markup: light canvas + label span.
  function dress(button, e) {
    // A label the page took out (textContent = …, replaceChildren) still holds the old content: empty it.
    if (e.label.parentNode !== button) e.label.replaceChildren();
    const loose = [...button.childNodes].filter((n) => n !== e.canvas && n !== e.label);
    e.label.append(...loose);
    if (e.canvas.parentNode !== button || e.label.parentNode !== button) button.replaceChildren(e.canvas, e.label);
  }

  function upgrade(button) {
    if (entries.has(button) || button.matches(SKIP)) return;
    const canvas = document.createElement("canvas");
    canvas.className = "specular-button__light";
    canvas.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.className = "specular-button__label";
    const e = { button, canvas, ctx: canvas.getContext("2d"), label, view: { width: 0, height: 0, ratio: 1 },
                state: { spot: 0, level: 0, press: 0, ready: false }, visible: true, awake: true };
    entries.set(button, e);
    button.classList.add("specular-button");
    dress(button, e);
    button.addEventListener("pointerdown", (ev) => {
      pointer.x = ev.clientX; pointer.y = ev.clientY; pointer.known = true;
      if (!button.disabled) e.state.press = 1;
      wake(e);
    });
    resize.observe(button); seen.observe(button);
    measure(e); // right away rather than on the observer's first callback
  }

  function scan(root) {
    if (!(root instanceof Element)) return;
    if (root.matches("button")) upgrade(root);
    root.querySelectorAll("button").forEach(upgrade);
  }

  function init() {
    if (!program) return; // no WebGL2: the buttons keep the plain style
    document.documentElement.classList.add("has-specular");
    scan(document.body);
    new MutationObserver((records) => records.forEach((r) => {
      const host = r.target.closest?.(".specular-button");
      const e = host && entries.get(host);
      if (e) dress(host, e); // a page script rewrote this button's content
      r.addedNodes.forEach(scan);
    })).observe(document.body, { childList: true, subtree: true });

    addEventListener("pointermove", (ev) => { pointer.x = ev.clientX; pointer.y = ev.clientY; pointer.known = true; wake(); },
                     { passive: true });
    const end = (ev) => { if (ev.pointerType === "mouse") return; pointer.known = false; wake(); };
    addEventListener("pointerup", end, { passive: true });
    addEventListener("pointercancel", end, { passive: true });
    document.documentElement.addEventListener("pointerleave", () => { pointer.known = false; wake(); });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => entries.forEach(measure));
  }

  document.addEventListener("DOMContentLoaded", init);
})();
