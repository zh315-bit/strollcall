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

function mapsLink(lat, lon) {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}&travelmode=walking`;
}
