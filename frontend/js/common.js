// Shared helpers: API calls, source labels, voice recording (WAV), map rendering.

const SOURCE_LABELS = {
  mock: "demo data", default: "rule-based", meta: null, local: null, snapshot: null,
  pending: null, keywords: "keywords", ors: null, overpass: null,
};

async function api(path, options = {}) {
  const resp = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    body: options.body && typeof options.body !== "string" && !(options.body instanceof FormData)
      ? JSON.stringify(options.body) : options.body,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

// A small badge next to anything that is not live Meta / live data.
function sourceBadge(source) {
  const label = SOURCE_LABELS[source];
  return label ? el("span", { class: "badge", title: `source: ${source}` }, label) : null;
}

// Banner listing every part that is mock or template data. Never present it as live.
function demoBanner(sources) {
  const parts = Object.entries(sources || {}).filter(([, v]) => v === "mock" || v === "default");
  if (!parts.length) return null;
  // "default" means a rule-based fallback replaced the AI output (template text, deterministic order).
  const names = parts.map(([k, v]) => `${k.replace(/_/g, " ")} (${v === "mock" ? "demo data" : "rule-based fallback"})`);
  return el("div", { class: "demo-banner", role: "status" },
    el("b", {}, "Demo data: "), "parts of this page are not live AI output: ", names.join(", "), ".");
}

function prettyType(t) {
  return t ? t.replace(/_/g, " ") : "anywhere";
}

// ---- Voice: record, convert to 24 kHz mono 16-bit WAV in the browser, transcribe ----

async function recordToWav(stopSignal) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const recorder = new MediaRecorder(stream);
  const chunks = [];
  recorder.ondataavailable = (e) => chunks.push(e.data);
  const stopped = new Promise((resolve) => (recorder.onstop = resolve));
  recorder.start();
  await stopSignal;
  recorder.stop();
  await stopped;
  stream.getTracks().forEach((t) => t.stop());
  const blob = new Blob(chunks, { type: recorder.mimeType });
  const ctx = new AudioContext();
  const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  ctx.close();
  const rate = 24000;
  const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * rate), rate);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  const pcm = (await offline.startRendering()).getChannelData(0);
  return encodeWav(pcm, rate);
}

function encodeWav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buffer);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Blob([buffer], { type: "audio/wav" });
}

// A mic button that fills `textarea` with the transcript (the user can edit it before parsing).
function micButton(textarea, onSource) {
  let stop = null;
  const btn = el("button", { type: "button", "aria-label": "Speak instead of typing" }, "🎙 Speak");
  btn.addEventListener("click", async () => {
    if (stop) { stop(); return; }
    let resolveStop;
    const signal = new Promise((r) => (resolveStop = r));
    stop = () => { resolveStop(); stop = null; btn.classList.remove("recording"); btn.textContent = "…"; btn.disabled = true; };
    btn.classList.add("recording");
    btn.textContent = "■ Stop";
    try {
      const wav = await recordToWav(signal);
      const form = new FormData();
      form.append("audio", wav, "speech.wav");
      const resp = await fetch("/api/voice/transcribe", { method: "POST", body: form });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "transcription failed");
      textarea.value = data.transcript;
      onSource && onSource(data.source);
    } catch (e) {
      alert(`Voice input did not work: ${e.message}. You can type instead.`);
    } finally {
      stop = null;
      btn.disabled = false;
      btn.classList.remove("recording");
      btn.textContent = "🎙 Speak";
    }
  });
  if (!navigator.mediaDevices || !window.MediaRecorder) btn.disabled = true;
  return btn;
}

// ---- Map ----

const OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors (ODbL)';

function makeMap(id, center = [40.7308, -73.9973], zoom = 14) {
  const map = L.map(id).setView(center, zoom);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);
  return map;
}

// The area our walking map covers: drawn on the map, and checked before a start point is used.
let coverageData = null;
async function loadCoverage() {
  if (coverageData === null) {
    try { coverageData = await api("/api/coverage"); } catch (e) { coverageData = { bbox: null }; }
  }
  return coverageData;
}

// true / false, or null when the server has no fixed area (demo mode).
function inCoverage(lat, lon) {
  const c = coverageData;
  if (!c || !c.bbox) return null;
  const [s, w, n, e] = c.bbox;
  if (lat < s || lat > n || lon < w || lon > e) return false;
  const r = Math.floor((lat - s) / c.cell_deg[0]), col = Math.floor((lon - w) / c.cell_deg[1]);
  return c.covered[Math.min(r, c.rows - 1) * c.cols + Math.min(col, c.cols - 1)] === "1";
}

const OUTSIDE_MESSAGE = (label) => `That spot is outside the area StrollCall can plan walks in (${label}), or too far from a street we have mapped. Pick a start point inside the dashed box.`;

async function drawCoverage(map) {
  const c = await loadCoverage();
  if (!c.bbox) return;
  const [s, w, n, e] = c.bbox;
  L.rectangle([[s, w], [n, e]], { color: getComputedStyle(document.documentElement).getPropertyValue("--accent-2").trim() || "#4aa8ff",
    weight: 2, dashArray: "6 6", fill: false, interactive: false }).addTo(map);
}

function mapsLink(lat, lon) {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}&travelmode=walking`;
}

// ---- Decoration: sky (clouds, petals) and the header mascots. Purely visual, hidden from screen readers. ----

const MASCOTS_SVG = `<svg viewBox="0 0 116 88" aria-hidden="true">
  <g class="bob-a"><ellipse cx="32" cy="58" rx="27" ry="25" fill="var(--a)" stroke="var(--line)" stroke-width="3"/>
    <ellipse cx="24" cy="54" rx="3.2" ry="4.4" fill="#2b2340"/><ellipse cx="40" cy="54" rx="3.2" ry="4.4" fill="#2b2340"/>
    <circle cx="25" cy="52.5" r="1.2" fill="#fff"/><circle cx="41" cy="52.5" r="1.2" fill="#fff"/>
    <ellipse cx="17" cy="62" rx="4" ry="2.4" fill="#ff9fc0"/><ellipse cx="47" cy="62" rx="4" ry="2.4" fill="#ff9fc0"/>
    <path d="M28 63 q4 4 8 0" fill="none" stroke="#2b2340" stroke-width="2.4" stroke-linecap="round"/>
    <path d="M30 34 q-2 -10 6 -14" fill="none" stroke="var(--line)" stroke-width="3" stroke-linecap="round"/></g>
  <g class="bob-b"><ellipse cx="86" cy="60" rx="25" ry="23" fill="var(--b)" stroke="var(--line)" stroke-width="3"/>
    <path d="M76 56 q3 -4 6 0 M90 56 q3 -4 6 0" fill="none" stroke="#2b2340" stroke-width="2.6" stroke-linecap="round"/>
    <ellipse cx="72" cy="64" rx="4" ry="2.4" fill="#ff9fc0"/><ellipse cx="100" cy="64" rx="4" ry="2.4" fill="#ff9fc0"/>
    <path d="M82 64 q4 5 8 0 z" fill="#2b2340"/>
    <path d="M70 42 l-6 -10 l12 4 z M102 42 l6 -10 l-12 4 z" fill="var(--b)" stroke="var(--line)" stroke-width="3" stroke-linejoin="round"/></g>
  <path d="M59 22 c-3 -6 -11 -3 -8 3 l8 8 l8 -8 c3 -6 -5 -9 -8 -3 z" fill="var(--accent)" stroke="var(--line)" stroke-width="2.4"/>
</svg>`;

function decorate() {
  const sky = el("div", { class: "sky", "aria-hidden": "true" },
    el("div", { class: "cloud c1" }), el("div", { class: "cloud c2" }), el("div", { class: "cloud c3" }));
  for (let i = 0; i < 14; i++) {
    sky.append(el("div", { class: "petal", style:
      `left:${Math.random() * 100}%;animation-duration:${9 + Math.random() * 9}s;animation-delay:${-Math.random() * 18}s;`
      + `transform:scale(${0.6 + Math.random() * 0.7})` }));
  }
  document.body.prepend(sky);

  // Wrap the page's <h1> (and .tagline, if any) into the mascot header with a speech bubble.
  const h1 = document.querySelector("main > h1");
  if (!h1) return;
  const tagline = document.querySelector("main > .tagline");
  const mascots = el("div", { class: "mascots" });
  mascots.innerHTML = MASCOTS_SVG;
  h1.append(" ", el("span", { class: "sparkle", "aria-hidden": "true" }, "✦"));
  const text = el("div", {}, h1, el("div", { class: "bubble" }, tagline || el("p", { class: "tagline" }, "Less planning. More meeting.")));
  document.querySelector("main").prepend(el("header", { class: "hero" }, mascots, text));
}

document.addEventListener("DOMContentLoaded", decorate);
