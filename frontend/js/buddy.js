// The walking buddy: the blue character from the StrollCall logo, bottom left on the walking screen,
// with a speech bubble. Five states match what the companion is doing (design: Walking buddy · states):
//   walking   gentle bounce in step with the walk
//   listening while the mic button is held
//   thinking  while Muse Spark picks a tool and the route updates
//   speaking  while a reply shows (and is read out, when voice is on)
//   arrived   at the meetup point or the end of the walk
// The character is decorative (aria-hidden); the bubble's text is a live region, so screen readers
// hear every reply. The animations are CSS and stop under prefers-reduced-motion.

const BUDDY_STATES = ["walking", "listening", "thinking", "speaking", "arrived"];

// One drawing, always smiling; each state shows its own eyes, mouth and extras (data-s lists the states a
// part is in). The eyes blink while walking and speaking.
const BUDDY_SVG = `<svg viewBox="0 0 100 100" focusable="false">
<g class="b-body">
  <path d="M50 20q-3-10 5-13" fill="none" stroke="#3B7BEA" stroke-width="4" stroke-linecap="round"/>
  <circle cx="57" cy="7" r="5" fill="#FFB3C1"/>
  <circle cx="50" cy="58" r="38" fill="#3B7BEA"/>
  <ellipse cx="33" cy="37" rx="9" ry="5" fill="#fff" fill-opacity=".3" transform="rotate(-35 33 37)"/>
  <ellipse cx="25" cy="64" rx="7" ry="4.5" fill="#FF9EB0" fill-opacity=".8"/><ellipse cx="75" cy="64" rx="7" ry="4.5" fill="#FF9EB0" fill-opacity=".8"/>
  <g data-s="walking speaking" class="b-eyes"><ellipse cx="37" cy="51" rx="4.5" ry="6" fill="#1F1B3A"/><ellipse cx="63" cy="51" rx="4.5" ry="6" fill="#1F1B3A"/>
    <circle cx="38.6" cy="48.4" r="1.8" fill="#fff"/><circle cx="64.6" cy="48.4" r="1.8" fill="#fff"/></g>
  <g data-s="listening"><ellipse cx="37" cy="50" rx="5.5" ry="7.5" fill="#1F1B3A"/><ellipse cx="63" cy="50" rx="5.5" ry="7.5" fill="#1F1B3A"/>
    <circle cx="39" cy="46.8" r="2.2" fill="#fff"/><circle cx="65" cy="46.8" r="2.2" fill="#fff"/></g>
  <g data-s="thinking"><ellipse cx="40" cy="48" rx="4.5" ry="6" fill="#1F1B3A"/><ellipse cx="66" cy="48" rx="4.5" ry="6" fill="#1F1B3A"/>
    <circle cx="42" cy="45.5" r="1.8" fill="#fff"/><circle cx="68" cy="45.5" r="1.8" fill="#fff"/></g>
  <path data-s="arrived" d="M31 52q6-7 12 0M57 52q6-7 12 0" fill="none" stroke="#1F1B3A" stroke-width="3.5" stroke-linecap="round"/>
  <g data-s="walking"><path d="M38 62q12 14 24 0z" fill="#1F1B3A" stroke="#1F1B3A" stroke-width="2" stroke-linejoin="round"/>
    <ellipse cx="50" cy="67.6" rx="5" ry="2.2" fill="#FF7A93"/></g>
  <path data-s="listening" d="M44 66q6 5 12 0" fill="none" stroke="#1F1B3A" stroke-width="3" stroke-linecap="round"/>
  <path data-s="thinking" d="M44 68q7 3 13-3" fill="none" stroke="#1F1B3A" stroke-width="3" stroke-linecap="round"/>
  <g data-s="speaking" class="b-talk"><path d="M39 62q11 15 22 0z" fill="#1F1B3A" stroke="#1F1B3A" stroke-width="2" stroke-linejoin="round"/>
    <ellipse cx="50" cy="68" rx="5" ry="2.4" fill="#FF7A93"/></g>
  <g data-s="arrived"><path d="M37 62q13 17 26 0z" fill="#1F1B3A" stroke="#1F1B3A" stroke-width="2" stroke-linejoin="round"/>
    <ellipse cx="50" cy="69" rx="6" ry="2.8" fill="#FF7A93"/></g>
</g>
<g data-s="listening" class="b-waves" fill="none" stroke="#E9B53A" stroke-width="3" stroke-linecap="round">
  <path d="M86 50q3 8 0 16"/><path d="M92 46q5 12 0 24"/>
</g>
<g data-s="thinking" class="b-dots" fill="#B9B2CC"><circle cx="80" cy="18" r="3.5"/><circle cx="89" cy="14" r="3.5"/><circle cx="97" cy="10" r="3"/></g>
<g data-s="arrived" class="b-confetti">
  <rect x="10" y="20" width="6" height="6" rx="1" fill="#FFD970"/><rect x="84" y="28" width="6" height="6" rx="1" fill="#FF9EB0"/>
  <circle cx="20" cy="36" r="3" fill="#22A35A"/><circle cx="90" cy="44" r="3" fill="#FFD970"/>
</g>
</svg>`;

// parts: strings, and {b: "text"} for a bold name. chips: [{label, onclick, primary?}].
function makeBuddy() {
  const face = el("div", { class: "buddy", "data-state": "walking", "aria-hidden": "true" });
  face.innerHTML = BUDDY_SVG;
  const text = el("p", { class: "buddy-text", role: "status", "aria-live": "polite" });
  const chips = el("div", { class: "buddy-chips" });
  const bubble = el("div", { class: "buddy-bubble" }, text, chips);
  const root = el("div", { class: "walk-buddy" }, face, bubble);
  let chipsShown = [];
  return {
    el: root,
    get state() { return face.dataset.state; },
    set(state) { if (BUDDY_STATES.includes(state)) face.dataset.state = state; },
    say(parts, newChips) {
      text.replaceChildren(...[].concat(parts || []).map((p) => (p && p.b ? el("strong", {}, p.b) : String(p))));
      if (newChips) this.chips(newChips);
    },
    chips(list) {
      chipsShown = list || [];
      chips.replaceChildren(...chipsShown.map((c) => el("button", { type: "button", class: `buddy-chip${c.primary ? " primary" : ""}`,
        onclick: c.onclick }, c.label)));
    },
    busy(on) { chips.querySelectorAll("button").forEach((b) => { b.disabled = on; }); },
  };
}

// Hold to talk records raw samples with Web Audio instead of MediaRecorder: there is no compressed
// recording to decode afterwards, a step iPhone Safari failed on ("Decoding failed"). The audio
// context starts inside the press, so iPhone lets it run. Returns a 16 kHz mono WAV and its length.
async function recordPcm(stopSignal) {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const chunks = [];
  let stream = null, src = null, proc = null;
  try {
    ctx.resume().catch(() => {});
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    src = ctx.createMediaStreamSource(stream);
    proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    src.connect(proc);
    proc.connect(ctx.destination);  // a processor only runs while connected; it outputs silence
    // iPhone can leave the context suspended (or "interrupted") once the microphone opens: wake it.
    if (ctx.state !== "running") await ctx.resume().catch(() => {});
    await stopSignal;
  } finally {
    if (proc) proc.disconnect();
    if (src) src.disconnect();
    if (stream) stream.getTracks().forEach((t) => t.stop());
  }
  const rate = ctx.sampleRate;
  ctx.close().catch(() => {});
  const all = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  chunks.reduce((o, c) => (all.set(c, o), o + c.length), 0);
  const out = 16000, len = Math.floor(all.length * out / rate), pcm = new Float32Array(len);
  for (let i = 0; i < len; i++) {  // linear resampling is plenty for speech
    const x = i * rate / out, j = Math.floor(x), f = x - j;
    pcm[i] = (all[j] || 0) * (1 - f) + (all[j + 1] || 0) * f;
  }
  return { wav: encodeWav(pcm, out), seconds: len / out, state: ctx.state };
}

// ---- The companion: chips and hold-to-talk -> /api/companion/ask -> a reply, maybe a new route ----
// walk: what the walking screen offers it:
//   state()          -> the WalkState the server expects (position, current leg, minutes left...)
//   apply(answer)    -> follows the new legs; returns an undo function
//   mark(places)     -> shows "What's nearby?" places on the map (an empty list clears them)
//   speak(text)      -> reads a reply out when voice prompts are on
//   talkSlot         -> where the mic button goes (the bottom bar)
// Returns { stop() } for when the walk ends. Nothing here is stored.
function startCompanion(buddy, walk) {
  let undo = null, busy = false, rest = null, stopped = false;
  const canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && (window.AudioContext || window.webkitAudioContext));
  const textOf = (parts) => parts.map((p) => (p && p.b ? p.b : String(p))).join("");

  function settle(state, ms = 5000) {
    clearTimeout(rest);
    buddy.set(state);
    if (state === "speaking") rest = setTimeout(() => { if (buddy.state === "speaking") buddy.set("walking"); }, ms);
  }

  function chipsFor(list) {
    return list.map((c) => ({ label: c.label, onclick: () => tool(c.tool, c.args || {}) }));
  }
  const defaults = () => chipsFor([{ label: "I have 10 min", tool: "set_time_left", args: { minutes: 10 } },
                                   { label: "What's nearby?", tool: "whats_nearby" }]);

  async function send(body, heard) {
    if (busy || stopped) return;
    busy = true;
    buddy.busy(true);
    settle("thinking");
    buddy.say(heard ? [`“${heard}” `, "Let me check…"] : "Let me check…");
    try {
      const a = await api("/api/companion/ask", { method: "POST", body: { ...body, walk: walk.state() } });
      if (stopped) return;
      walk.mark(a.places || []);
      let chips = a.chips && a.chips.length ? chipsFor(a.chips) : defaults();
      if (a.legs && a.legs.length) {
        undo = walk.apply(a);
        chips = [{ label: "Undo", onclick: () => takeBack() }, ...chips];
      }
      buddy.say(a.heard ? [`“${a.heard}” `, ...a.parts] : a.parts, chips);
      walk.speak(textOf(a.parts));
      settle("speaking", Math.min(9000, 2500 + textOf(a.parts).length * 45));
    } catch (e) {
      buddy.say(`I couldn't do that just now (${e.message}). Your route is unchanged.`, defaults());
      settle("walking");
    } finally {
      busy = false;
      buddy.busy(false);
    }
  }

  function tool(name, args) { return send({ tool: name, args }); }

  function takeBack() {
    if (!undo) return;
    undo();
    undo = null;
    walk.mark([]);
    buddy.say("Back to your earlier route.", defaults());
    walk.speak("Back to your earlier route.");
    settle("speaking", 2500);
  }

  // Hold to talk: record while the button is held (pointer or Space/Enter), then transcribe and ask.
  const mic = el("button", { type: "button", class: "walk-mic", "aria-label": "Hold to talk to your walking buddy" });
  mic.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" '
    + 'stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/>'
    + '<path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
  let release = null;
  async function hold() {
    if (release || busy || stopped) return;
    let done;
    const signal = new Promise((r) => (done = r));
    release = done;
    mic.classList.add("held");
    settle("listening");
    buddy.say("Listening… let go when you're done.");
    const pressed = Date.now();
    try {
      const { wav, seconds } = await recordPcm(signal);
      // No audio after a real press: the browser opened the microphone but gave us no samples.
      if (seconds < 0.5 && Date.now() - pressed > 1500) throw new Error("no audio from the microphone");
      // Under half a second: a tap, or the first press that only brought up the microphone question.
      if (seconds < 0.5) throw new Error("short");
      settle("thinking");
      buddy.say("Let me check…");
      const form = new FormData();
      form.append("audio", wav, "speech.wav");
      const resp = await fetch("/api/voice/transcribe", { method: "POST", body: form });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "transcription failed");
      const heard = (data.transcript || "").trim();
      if (!heard) throw new Error("silent");
      await send({ text: heard.slice(0, 300) }, heard);
    } catch (e) {
      buddy.say(e.message === "short" ? "I didn't catch that. Hold the button while you talk, then let go."
        : e.message === "silent" ? "I couldn't hear any words. Try again a little closer to the phone, or tap below."
        : e.name === "NotAllowedError" ? "I can't hear you: the microphone isn't allowed for this page. The buttons below still work."
          : `Voice didn't work just now (${e.message}). The buttons below still work.`, defaults());
      settle("walking");
    } finally {
      release = null;
      mic.classList.remove("held");
    }
  }
  const letGo = () => { if (release) release(); };
  mic.addEventListener("pointerdown", (e) => { e.preventDefault(); mic.setPointerCapture?.(e.pointerId); hold(); });
  mic.addEventListener("pointerup", letGo);
  mic.addEventListener("pointercancel", letGo);
  mic.addEventListener("contextmenu", (e) => e.preventDefault());  // a long press must not open a menu
  mic.addEventListener("keydown", (e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); hold(); } });
  mic.addEventListener("keyup", (e) => { if (e.key === " " || e.key === "Enter") letGo(); });
  if (walk.voice && canRecord) walk.talkSlot.append(mic);

  buddy.say(walk.voice && canRecord ? "Hi, I'm walking with you. Hold the mic to ask me something, or tap below."
    : "Hi, I'm walking with you. Tap below if you need me.", defaults());
  return {
    stop() { stopped = true; letGo(); clearTimeout(rest); },
    arrived() { clearTimeout(rest); buddy.set("arrived"); },
  };
}
