// Animated background behind the page, built on React Bits components (https://reactbits.dev, MIT + Commons Clause):
// - GridMotion (js/gridmotion.js): a full-page wall of the Muse Image invite illustrations drifting past,
//   under a theme-colored wash so the cards on top stay readable. It replaces the CSS clouds and hills.
// - Light Rays: its WebGL2 shader, trimmed (no cursor shadow, click pulses or intro) and aimed from the sun in the
//   top-right corner. Sunbeams by day (its light-background mode), pale moonlight by night.
// - Particles: redone as a small 2D canvas: pollen drifting in the light by day, twinkling fireflies by night.
// Colors come from CSS variables (--rays, --rays-opacity, --mote), so the theme stays in style.css.
// Decoration only: aria-hidden, paused while the tab is hidden, a single still frame under reduced motion.

(() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  function rgb(color) { // any CSS color -> [r, g, b] in 0..1
    const ctx = document.createElement("canvas").getContext("2d");
    ctx.fillStyle = color || "#fff";
    const hex = /^#([0-9a-f]{6})$/i.exec(ctx.fillStyle);
    if (hex) { const v = parseInt(hex[1], 16); return [(v >> 16) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255]; }
    const m = /\(([^)]+)\)/.exec(ctx.fillStyle);
    return m ? m[1].split(",").slice(0, 3).map((x) => parseFloat(x) / 255) : [1, 1, 1];
  }

  // ---- Light Rays ----

  const VERTEX = `#version 300 es
const vec2 corners[3] = vec2[3](vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
void main() { gl_Position = vec4(corners[gl_VertexID], 0.0, 1.0); }`;

  // The original fragment shader with the cursor-shadow, pulse and intro branches removed.
  const FRAGMENT = `#version 300 es
precision highp float;
uniform vec2 uResolution;
uniform float uScale;
uniform float uTime;
uniform vec2 uSource;
uniform vec2 uAim;
uniform float uReach;
uniform vec3 uColor;
uniform float uSpread;
uniform float uLength;
uniform float uFade;
uniform float uDensity;
uniform float uSharpness;
uniform float uGlow;
uniform float uHaze;
uniform float uAtmosphere;
uniform float uOpacity;
uniform float uLight;
uniform float uIntensity;
out vec4 fragColor;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float valueNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = p - i;
  vec2 w = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), w.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), w.x), w.y);
}
float shape(float strength, float width) {
  float edge = max(mix(0.5, 0.08, uSharpness), width);
  return mix(strength, smoothstep(0.62 - edge, 0.62 + edge, strength), uSharpness);
}

void main() {
  vec2 coord = vec2(gl_FragCoord.x, uResolution.y - gl_FragCoord.y) / uScale;
  vec2 delta = coord - uSource;
  float distance = length(delta);
  vec2 dir = delta / max(distance, 1e-4);
  float cosAngle = dot(dir, uAim);
  float angle = cosAngle;
  float slope = fwidth(angle);
  float depth = distance / uReach;

  float source = exp(-depth * depth * 9.0) * 0.9 + exp(-depth * 3.2) * 0.25;
  float glowLight = uGlow * source * smoothstep(-0.2, 0.6, cosAngle);
  float spread = pow(max(angle, 0.0), 1.0 / uSpread);
  float lengthFalloff = clamp(1.0 - distance / (uReach * uLength), 0.0, 1.0);
  float fadeFalloff = clamp(1.0 - distance / (uReach * uFade), 0.5, 1.0);
  float envelope = spread * lengthFalloff * fadeFalloff;
  if (envelope * 1.6 + glowLight < 0.0015) { fragColor = vec4(0.0); return; }

  float phaseA = angle * 36.2214 * uDensity + uTime * 1.5;
  float phaseB = -angle * 21.11349 * uDensity + uTime * 1.5;
  float phaseC = angle * 22.3991 * uDensity + uTime * 1.1;
  float phaseD = -angle * 18.0234 * uDensity + uTime * 1.1;
  float strengthA = clamp(0.75 + 0.15 * sin(phaseA) + 0.2 * cos(phaseB), 0.0, 1.0);
  float strengthB = clamp(0.75 + 0.15 * sin(phaseC) + 0.2 * cos(phaseD), 0.0, 1.0);
  float widthA = abs(0.15 * 36.2214 * cos(phaseA) + 0.2 * 21.11349 * sin(phaseB)) * uDensity * slope;
  float widthB = abs(0.15 * 22.3991 * cos(phaseC) + 0.2 * 18.0234 * sin(phaseD)) * uDensity * slope;
  float rayLight = envelope * (0.5 * shape(strengthA, widthA) + 0.4 * shape(strengthB, widthB));

  if (uHaze > 0.0) {
    float around = atan(uAim.x * dir.y - uAim.y * dir.x, cosAngle);
    vec2 drift = vec2(around * 2.2 + uTime * 0.035, depth * 2.6 - uTime * 0.11);
    float fog = 0.65 * valueNoise(drift * vec2(3.0, 1.0)) + 0.35 * valueNoise(drift * vec2(7.0, 2.3) + 4.1);
    rayLight *= mix(1.0, 0.25 + 1.2 * fog, uHaze);
  }
  float light = (rayLight + glowLight) * uIntensity;

  float near = clamp(1.2 - distance / (uResolution.y / uScale), 0.0, 1.0);
  vec3 tint = mix(vec3(0.9), vec3(0.1, 0.3, 0.5) + near * vec3(0.8, 0.6, 0.5), uAtmosphere);
  vec3 hue = max(tint, 0.0) * uColor;

  float grain = (fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5) / 255.0;
  if (uLight > 0.5) { // light backgrounds: the light is drawn as tinted color rather than added brightness
    vec3 color = hue * light;
    float energy = max(color.r, max(color.g, color.b));
    vec3 tone = clamp(1.0 - (1.0 - hue / max(max(hue.r, max(hue.g, hue.b)), 1e-4)) * 1.8, 0.0, 1.0);
    float warm = clamp((min(tone.r, tone.g) - tone.b) * 2.0, 0.0, 1.0);
    vec3 ink = tone * (mix(0.66, 0.94, warm) - 0.1 * smoothstep(0.4, 1.2, energy));
    float density = clamp(0.82 * (1.0 - exp(-1.5 * energy * energy)) * uOpacity + grain, 0.0, 1.0);
    fragColor = vec4(ink * density, density);
    return;
  }
  float level = light < 0.75 ? light : 0.75 + 0.25 * (1.0 - exp(-(light - 0.75) / 0.25));
  float top = max(hue.r, max(hue.g, hue.b));
  hue = mix(hue, vec3(top), smoothstep(0.8, 1.0, level) * 0.45);
  vec3 shown = clamp(hue * level, 0.0, 1.0) * level;
  fragColor = vec4(clamp(shown + grain, 0.0, level) * uOpacity, level * uOpacity);
}`;

  // Our settings for the original props: the sun sits in the top-right, rays lean down and to the left.
  const RAYS = { anchor: [0.9, -0.15], tiltDeg: 32, speed: 0.35, spread: 1.1, length: 3, fade: 1.6,
                 density: 0.8, sharpness: 0.3, glow: 0.45, haze: 0.35, atmosphere: 0.2, follow: 0.04, scale: 0.5,
                 intensity: { light: 1.3, dark: 1 } };

  function lightRays(sky) {
    const canvas = document.createElement("canvas");
    canvas.className = "sky-rays";
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: true, antialias: false });
    if (!gl) return null; // no WebGL2: the CSS sky is enough
    const compile = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const program = gl.createProgram();
    try {
      gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    } catch (e) { console.warn("sky rays disabled:", e.message); return null; }
    const u = {};
    for (let i = 0; i < gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS); i++) {
      const name = gl.getActiveUniform(program, i).name;
      u[name] = gl.getUniformLocation(program, name);
    }
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    const vao = gl.createVertexArray();
    sky.prepend(canvas);

    let width = 0, height = 0, color = [1, 1, 1], opacity = 0.5, aimX = 0, aimY = 1, mouseX = 0.5, light = false;
    const resize = () => {
      width = innerWidth; height = innerHeight;
      canvas.width = Math.ceil(width * RAYS.scale); canvas.height = Math.ceil(height * RAYS.scale);
    };
    const theme = () => {
      color = rgb(cssVar("--rays")); opacity = parseFloat(cssVar("--rays-opacity")) || 0.5; light = !dark.matches;
    };
    resize(); theme();
    addEventListener("resize", resize);
    dark.addEventListener("change", theme);
    addEventListener("pointermove", (e) => { mouseX = e.clientX / innerWidth; }, { passive: true });

    return (t) => {
      // Aim: the tilted base direction, nudged a little toward the pointer (Light Rays' followMouse).
      const tilt = (RAYS.tiltDeg + (mouseX - 0.5) * 2 * RAYS.follow * 90) * Math.PI / 180;
      const tx = -Math.sin(tilt), ty = Math.cos(tilt);
      aimX += (tx - aimX) * 0.05; aimY += (ty - aimY) * 0.05;
      const len = Math.hypot(aimX, aimY) || 1;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(program);
      gl.bindVertexArray(vao);
      gl.uniform2f(u.uResolution, canvas.width, canvas.height);
      gl.uniform1f(u.uScale, RAYS.scale);
      gl.uniform1f(u.uTime, t * RAYS.speed);
      gl.uniform2f(u.uSource, RAYS.anchor[0] * width, RAYS.anchor[1] * height);
      gl.uniform2f(u.uAim, aimX / len, aimY / len);
      gl.uniform1f(u.uReach, Math.max(width, height));
      gl.uniform3f(u.uColor, color[0], color[1], color[2]);
      gl.uniform1f(u.uSpread, RAYS.spread);
      gl.uniform1f(u.uLength, RAYS.length);
      gl.uniform1f(u.uFade, RAYS.fade);
      gl.uniform1f(u.uDensity, RAYS.density);
      gl.uniform1f(u.uSharpness, RAYS.sharpness);
      gl.uniform1f(u.uGlow, RAYS.glow);
      gl.uniform1f(u.uHaze, RAYS.haze);
      gl.uniform1f(u.uAtmosphere, RAYS.atmosphere);
      gl.uniform1f(u.uOpacity, opacity);
      gl.uniform1f(u.uLight, light ? 1 : 0);
      gl.uniform1f(u.uIntensity, light ? RAYS.intensity.light : RAYS.intensity.dark);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
  }

  // ---- Particles: pollen by day, fireflies by night ----

  function motes(sky) {
    const canvas = document.createElement("canvas");
    canvas.className = "sky-motes";
    const ctx = canvas.getContext("2d");
    sky.append(canvas);
    const count = () => Math.round(Math.min(46, (innerWidth * innerHeight) / 26000));
    const spawn = (anywhere) => ({
      x: Math.random() * innerWidth, y: anywhere ? Math.random() * innerHeight : innerHeight + 10,
      r: 1 + Math.random() * 2.2, vx: (Math.random() - 0.5) * 6, vy: -(4 + Math.random() * 10),
      phase: Math.random() * Math.PI * 2, twinkle: 0.6 + Math.random() * 1.4,
    });
    let list = [], color = "#fff", night = dark.matches;
    const resize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      list = Array.from({ length: count() }, () => spawn(true));
    };
    const theme = () => { color = cssVar("--mote") || "#fff"; night = dark.matches; };
    resize(); theme();
    addEventListener("resize", resize);
    dark.addEventListener("change", theme);

    let last = 0;
    return (t) => {
      const dt = last ? Math.min(0.05, t - last) : 0;
      last = t;
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      for (let i = 0; i < list.length; i++) {
        const p = list[i];
        p.x += (p.vx + Math.sin(t * 0.6 + p.phase) * 8) * dt;
        p.y += p.vy * dt;
        if (p.y < -10 || p.x < -10 || p.x > innerWidth + 10) { list[i] = spawn(false); continue; }
        // Fireflies blink in and out; pollen only shimmers a little.
        const wave = 0.5 + 0.5 * Math.sin(t * p.twinkle + p.phase);
        ctx.globalAlpha = night ? Math.pow(wave, 3) : 0.35 + 0.4 * wave;
        ctx.shadowBlur = night ? 10 : 6;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };
  }

  // ---- Photo wall: the Muse Image illustrations drifting across the whole page ----
  // thumbs/ holds 360 px copies of illustrations/ (sips -Z 360, JPEG quality 72): the tiles never need more.

  // The wall's order and row offsets, saved when leaving a page so the next page continues the same wall.
  const WALL_KEY = "strollcall:wall";
  function readWall() {
    try {
      const w = JSON.parse(sessionStorage.getItem(WALL_KEY));
      return w && Array.isArray(w.order) && Array.isArray(w.offsets) && Date.now() - w.at < 60000 ? w : null;
    } catch (err) { return null; }
  }

  function photoWall(sky) {
    if (!window.gridMotion) return;
    const wall = document.createElement("div");
    wall.className = "photo-wall";
    const wash = document.createElement("div");
    wash.className = "photo-wash";
    sky.prepend(wall, wash); // under the rays and motes
    fetch("/static/illustrations/manifest.json").then((r) => r.json()).then(({ pictures }) => {
      // A new visit gets a fresh mix; moving between pages keeps the order and the drift (see WALL_KEY).
      const files = Object.keys(pictures);
      const saved = readWall();
      const order = saved && saved.order.length === files.length && saved.order.every((f) => f in pictures)
        ? saved.order : files.map((f) => [f, Math.random()]).sort((a, b) => a[1] - b[1]).map(([f]) => f);
      const items = order.map((file) => ({ src: `/static/illustrations/thumbs/${file}`, alt: "" }));
      sky.classList.add("has-wall");
      const wallMotion = gridMotion(wall, { items, rows: innerHeight > innerWidth ? 5 : 4, aspectRatio: 1.5, gap: 18, radius: 22,
        angle: -12, speed: 28, parallax: 0, spotlight: 0, dim: 0.25, // drifts on its own, ignores the pointer
        fade: 0.06, theme: "light",
        tileColor: "var(--soft-line)", resume: saved });
      const save = () => {
        try { sessionStorage.setItem(WALL_KEY, JSON.stringify({ order, ...wallMotion.state() })); } catch (err) { /* fine */ }
      };
      addEventListener("pageswap", save);
      addEventListener("pagehide", save);
    }).catch(() => { wall.remove(); wash.remove(); }); // no pictures: the plain sky stays
  }

  // ---- Loop ----

  function init() {
    const sky = document.querySelector(".sky");
    if (!sky) return;
    const layers = [lightRays(sky), motes(sky)].filter(Boolean);
    photoWall(sky); // GridMotion runs its own frame loop
    const frame = () => { const t = (Date.now() % 1e7) / 1000; layers.forEach((draw) => draw(t)); }; // wall-clock: same phase across pages
    if (reduced) { frame(4000); return; } // one still frame
    let raf = 0;
    const loop = (now) => { frame(now); raf = requestAnimationFrame(loop); };
    // Paused while the tab is hidden, and during a walk: the walking screen covers the page
    // (style.css also hides .sky then, which stops the photo wall's own loop).
    const run = () => {
      cancelAnimationFrame(raf); raf = 0;
      if (!document.hidden && !document.body.classList.contains("walking")) raf = requestAnimationFrame(loop);
    };
    document.addEventListener("visibilitychange", run);
    new MutationObserver(run).observe(document.body, { attributes: true, attributeFilter: ["class"] });
    run();
  }

  // common.js builds the .sky on DOMContentLoaded; this listener is added later, so it runs after.
  document.addEventListener("DOMContentLoaded", init);
})();
