// The whole demo on one timeline. Scene lengths and every spoken placement live in beats.json (shared with the
// captions and the mix); the beat times inside each scene below are the words' real times from
// vo_tts/words.json (noted next to each beat). Recordings are the real Part A clips, placed as <video> layers.
// Each scene's draw(t) returns { bg, fg, videos } with t the time inside the scene.

// ---------- devices: one transform shared by the frame, the video layer and callout targets ----------
// cw: the recording's own width in its pixels (phone: 390 CSS px; desktop/terminal: 1920 px).
function dev(o) { return { s: 1, rot: 0, dx: 0, dy: 0, z: 1, zx: 0.5, zy: 0.5, r: 0, ...o }; }
function devPt(d, px, py) {
  const k = d.w / d.cw;
  let lx = px * k, ly = py * k;
  lx = d.zx * d.w + (lx - d.zx * d.w) * d.z; ly = d.zy * d.h + (ly - d.zy * d.h) * d.z;
  const rx = lx - d.w / 2, ry = ly - d.h / 2, th = d.rot * Math.PI / 180;
  const cx = d.x + d.w / 2 + d.dx, cy = d.y + d.h / 2 + d.dy;
  return [cx + d.s * (rx * Math.cos(th) - ry * Math.sin(th)), cy + d.s * (rx * Math.sin(th) + ry * Math.cos(th))];
}
function devGroup(d, inner) {
  const cx = d.x + d.w / 2 + d.dx, cy = d.y + d.h / 2 + d.dy;
  return `<g transform="translate(${cx} ${cy}) rotate(${d.rot}) scale(${d.s}) translate(${-d.w / 2} ${-d.h / 2})">${inner}</g>`;
}
const devVideo = (d, clip, t, extra = {}) => ({ clip, t, x: d.x, y: d.y, w: d.w, h: d.h, r: d.r, s: d.s, rot: d.rot, dx: d.dx, dy: d.dy, z: d.z, zx: d.zx, zy: d.zy, ...extra });
const PHONE = { w: 397, h: 860, cw: 390, r: 52 };
function phoneDev(x, y, t, o = {}) { return dev({ ...PHONE, x, y, dy: floatY(t, 5, 4.4, o.ph || 0), rot: floatR(t, 0.4, 5.6, o.ph || 0), ...o }); }
function phoneFrame(d, color = C.ink) {
  return devGroup(d, `<rect x="-12" y="-12" width="${d.w + 24}" height="${d.h + 24}" rx="62" fill="none" stroke="${color}" stroke-width="16"/>
    <rect x="${d.w / 2 - 60}" y="-4" width="120" height="22" rx="11" fill="${color}"/>`);
}
function devShadow(d, rx = 62) { return devGroup(d, `<rect x="-12" y="-12" width="${d.w + 24}" height="${d.h + 24}" rx="${rx}" fill="${C.ink}" filter="url(#shadow)"/>`); }
function browserChrome(d, url) {
  return devGroup(d, `<rect x="0" y="-52" width="${d.w}" height="${d.h + 52}" rx="22" fill="#fff" filter="url(#shadow)"/>
    <rect x="0" y="-52" width="${d.w}" height="52" rx="22" fill="#EEE7DA"/><rect x="0" y="-20" width="${d.w}" height="20" fill="#EEE7DA"/>
    <circle cx="30" cy="-26" r="8" fill="#FF6B6B"/><circle cx="56" cy="-26" r="8" fill="${C.yellow}"/><circle cx="82" cy="-26" r="8" fill="${C.green}"/>
    <rect x="120" y="-40" width="${d.w - 240}" height="28" rx="14" fill="#fff"/>${text(d.w / 2, -19, url, { size: 18, family: "Nunito", weight: 700, fill: "#6B6380" })}`);
}

// ---------- attention: callouts, rings, chips, tags ----------
// a ring that pulses once on the target, a leader line that draws toward it, then the label rises in
function callout(tgt, lab, label, t, t0, t1 = 99, o = {}) {
  const p = t - t0, out = prog(t, t1, t1 + 0.35);
  if (p <= 0 || out >= 1) return "";
  const { color = C.ink, bg = "#fff", size = 28 } = o;
  const [tx, ty] = tgt, [lx, ly] = lab;
  const w = label.length * size * 0.53 + 46, h = size + 26;
  const fade = 1 - out;
  const ring = pulse(t, t0 + 0.1, 0.9);
  const line = drawLine([[lx, ly], [tx, ty]], prog(p, 0, 0.35), `stroke="${color}" stroke-width="3.5" stroke-linecap="round"`);
  const show = prog(p, 0.2, 0.55), dot = springIn(t, t0 + 0.25, 0.35);
  return `<g opacity="${fade}">${line}
    <circle cx="${tx}" cy="${ty}" r="${10 + 34 * ring}" fill="none" stroke="${C.yellow}" stroke-width="${6 * (1 - ring) + 1}" opacity="${ring > 0 ? 1 - ring * 0.6 : 0}"/>
    <circle cx="${tx}" cy="${ty}" r="${9 * clamp(dot, 0, 1.3)}" fill="${C.yellow}" stroke="${color}" stroke-width="3"/>
    <g opacity="${show}" transform="translate(${lx} ${ly + (1 - show) * 10 + floatY(t, 2, 3)})"><rect x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}" rx="${h / 2}" fill="${bg}" stroke="${color}" stroke-width="3"/>
    ${text(0, size * 0.36, label, { size, family: "Nunito", weight: 800, fill: color })}</g></g>`;
}
function ripple(pt, t, t0) {
  const p = (t - t0) / 0.6;
  if (p < 0 || p > 1) return "";
  return `<circle cx="${pt[0]}" cy="${pt[1]}" r="${16 + p * 46}" fill="${C.yellow}" fill-opacity="${0.35 * (1 - p)}" stroke="${C.ink}" stroke-width="3" stroke-opacity="${1 - p}"/>`;
}
function chip(x, y, label, t, t0, t1 = 99, o = {}) {
  const { bg = C.yellow, fg = C.ink, size = 26 } = o;
  const p = springIn(t, t0, 0.45), out = prog(t, t1, t1 + 0.3);
  if (t < t0 || out >= 1) return "";
  const w = label.length * size * 0.54 + 44, h = size + 24;
  return `<g opacity="${clamp(p * 2) * (1 - out)}" transform="translate(${x} ${y + floatY(t, 2, 3.4)}) scale(${0.9 + 0.1 * clamp(p, 0, 1.15)})"><rect x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}" rx="${h / 2}" fill="${bg}" stroke="${C.ink}" stroke-width="3"/>
    ${text(0, size * 0.36, label, { size, family: "Nunito", weight: 800, fill: fg })}</g>`;
}
function tag(x, y, label, { bg = "#FFF3C4", anchor = "start" } = {}) {
  const w = label.length * 11 + 30, x0 = anchor === "start" ? x : x - w;
  return `<g><rect x="${x0}" y="${y - 22}" width="${w}" height="34" rx="17" fill="${bg}" stroke="${C.ink}" stroke-width="2" opacity=".95"/>
    ${text(x0 + w / 2, y + 2, label, { size: 19, family: "Nunito", weight: 800 })}</g>`;
}
function waveform(x, y, t, n = 14, color = C.yellow) {
  return `<g transform="translate(${x} ${y})">${Array.from({ length: n }, (_, i) => {
    const h = 10 + 46 * Math.abs(Math.sin(t * 8 + i * 0.9)) * (0.4 + 0.6 * Math.abs(Math.sin(t * 2.3 + i)));
    return `<rect x="${i * 15}" y="${-h / 2}" width="9" height="${h}" rx="4.5" fill="${color}" stroke="${C.ink}" stroke-width="2"/>`;
  }).join("")}</g>`;
}
const _bgIds = {};
function softBg(t, top = "#EAF4FF", bottom = C.cream, cols) {
  const id = "bg" + (top + bottom).replace(/#/g, "");
  return `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${top}"/><stop offset="1" stop-color="${bottom}"/></linearGradient></defs>
    <rect width="1920" height="1080" fill="url(#${id})"/>` + ambient(t, cols);
}
// the small blue guide mascot that reacts beside the phone
function guide(x, y, t, expr = "smile", lively = true, s = 0.55) {
  const h = lively ? { b: Math.abs(Math.sin(t * 2.6)) * 6, sx: 1, sy: 1 + 0.03 * Math.sin(t * 5.2) } : { b: 0, sx: 1, sy: 1 };
  return mascotA({ x, y, s, expr, bounce: h.b, sx: h.sx, sy: h.sy, blink: blinkAt(t, 3.0, 0.5), rot: 4 * Math.sin(t * 1.3) });
}

// ---------- scenes ----------
const BEATS = window.BEATS;
const T = [];
const add = (id, draw) => { const [, dur] = BEATS.scenes.find(([s]) => s === id); T.push({ id, dur, draw }); };

// 1 · cold open (scenes.js)
add("s1", (t) => ({ bg: SCENES.s1.draw(t) }));

// 2 · the problem. VO 1b at 8.3: "And my friends?" 0.3-0.7 · "Mostly homebodies." 1.5-2.3 ·
// "'We should hang out'" 2.5-3.9 · "never turns into a plan." 4.3-5.6
add("s2", (t) => {
  let s = softBg(t, "#F3ECFF", C.cream, ["#EDE4FF", "#FFE7D9", "#E8F1FF", "#FFF1D6"]);
  // the orange mascot at home on the sofa (with "friends?" / "homebodies")
  const sofa = springIn(t, 0.2, 0.55);
  if (sofa > 0) {
    const breathe = 1 + 0.03 * Math.sin(t * 2.4);
    s += `<g opacity="${clamp(sofa * 2)}" transform="translate(470 ${600 + floatY(t, 4, 4)}) scale(${0.85 + 0.15 * clamp(sofa, 0, 1.1)})">
      <g filter="url(#shadow)"><rect x="-260" y="-230" width="520" height="440" rx="48" fill="#FFF6EA"/></g>
      <rect x="-230" y="-200" width="160" height="120" rx="16" fill="#CFE6FF" stroke="${C.ink}" stroke-width="3"/>
      <path d="M-230 -140 h160 M-150 -200 v120" stroke="${C.ink}" stroke-width="3"/>
      <rect x="-200" y="30" width="400" height="110" rx="34" fill="#B07A9E" stroke="${C.ink}" stroke-width="4"/>
      <rect x="-222" y="-30" width="64" height="170" rx="26" fill="#B07A9E" stroke="${C.ink}" stroke-width="4"/>
      <rect x="158" y="-30" width="64" height="170" rx="26" fill="#B07A9E" stroke="${C.ink}" stroke-width="4"/>
      ${mascotB({ x: 0, y: 4, s: 1.15, expr: "sleepy", feet: false, sy: breathe })}
      <path d="M-150 40 q150 -50 300 0 v80 h-300 z" fill="#8FB6E8" stroke="${C.ink}" stroke-width="4"/>
      <g transform="rotate(-12 50 30)"><rect x="30" y="0" width="42" height="68" rx="9" fill="${C.ink}"/><rect x="35" y="6" width="32" height="52" rx="6" fill="#BFE3FF"/></g>
      ${[0, 1, 2].map((i) => { const zt = (t * 0.6 + i / 3) % 1; return t > 1.4 ? `<text x="${70 + zt * 60 + i * 6}" y="${-90 - zt * 90}" font-family="Fredoka" font-weight="700" font-size="${26 + i * 6}" fill="#8A82A0" opacity="${(1 - zt) * prog(t, 1.4, 1.8)}">z</text>` : ""; }).join("")}
    </g>`;
  }
  // the group chat (staged, made-up names), from "We should hang out"
  const chat = springIn(t, 2.35, 0.55);
  if (chat > 0) {
    const px = 860, py = 120, pw = 500, ph = 800, grey = prog(t, 5.6, 6.3);
    s += `<g opacity="${clamp(chat * 2)}" transform="translate(${px + pw / 2} ${py + ph / 2 + floatY(t, 4, 4.6, 0.4) + (1 - clamp(chat)) * 60}) rotate(${floatR(t, 0.6, 5)}) translate(${-pw / 2} ${-ph / 2})">
      <g filter="url(#shadow)"><rect width="${pw}" height="${ph}" rx="56" fill="#fff"/></g>
      <rect width="${pw}" height="${ph}" rx="56" fill="none" stroke="${C.ink}" stroke-width="12"/>
      <rect x="20" y="30" width="${pw - 40}" height="80" rx="24" fill="#F4F0FA"/>
      ${text(pw / 2, 82, "Weekend crew", { size: 32, family: "Nunito", weight: 800 })}`;
    const msgs = [{ at: 2.55, who: "Sam", txt: "we should hang out sometime" }, { at: 3.2, who: "Jo", txt: "yes!!" }, { at: 3.75, who: "Riley", txt: "let's plan it", me: true }];
    msgs.forEach((m, i) => {
      const p = springIn(t, m.at, 0.4);
      if (p <= 0) return;
      const w = m.txt.length * 16.5 + 50, y = 190 + i * 120, x = m.me ? pw - 40 - w : 40;
      s += `<g opacity="${clamp(p * 2)}" transform="translate(${x + (m.me ? w : 0)} ${y + 32}) scale(${clamp(p, 0, 1.12)}) translate(${m.me ? -w : 0} -32)">
        ${m.me ? "" : text(10, -14, m.who, { size: 20, family: "Nunito", weight: 700, anchor: "start", fill: "#8A82A0" })}
        <rect width="${w}" height="64" rx="32" fill="${m.me ? C.blue : "#EFE9F7"}"/>
        ${text(w / 2, 42, m.txt, { size: 27, family: "Nunito", weight: 700, fill: m.me ? "#fff" : C.ink })}</g>`;
    });
    const dp = prog(t, 4.2, 4.5) * (1 - prog(t, 5.2, 5.7));
    if (dp > 0) s += `<g opacity="${dp}" transform="translate(40 560)"><rect width="110" height="56" rx="28" fill="#EFE9F7"/>
      ${[0, 1, 2].map((k) => `<circle cx="${30 + k * 25}" cy="${28 - Math.max(0, Math.sin(t * 7 - k)) * 6}" r="7" fill="#8A82A0"/>`).join("")}</g>`;
    if (grey > 0) s += `<rect width="${pw}" height="${ph}" rx="56" fill="#F1EEF6" opacity="${grey * 0.72}"/>`;
    s += `</g>`;
  }
  // calendar pages flip: "3 weeks later…" (after "never turns into a plan")
  const cp = springIn(t, 5.2, 0.5);
  if (cp > 0) {
    const flips = prog(t, 5.5, 6.9, (x) => x) * 3, week = 1 + Math.floor(flips), ph = flips % 1;
    const sq = week < 4 ? Math.abs(Math.cos(ph * Math.PI)) : 1;
    s += `<g opacity="${clamp(cp * 2)}" transform="translate(1600 ${330 + floatY(t, 4, 3.6)}) scale(${clamp(cp, 0, 1.1)})"><g filter="url(#shadow)"><rect x="-140" y="-150" width="280" height="300" rx="30" fill="#fff"/></g>
      <rect x="-140" y="-150" width="280" height="80" rx="30" fill="${C.orange}"/><rect x="-140" y="-100" width="280" height="30" fill="${C.orange}"/>
      ${text(0, -92, "WEEK", { size: 30, fill: "#fff" })}<g transform="translate(0 30) scale(1 ${sq})">${text(0, 40, String(Math.min(4, week)), { size: 130 })}</g></g>
      <g opacity="${prog(t, 6.4, 6.9)}">${text(1600, 560, "3 weeks later…", { size: 46 })}</g>`;
  }
  return { bg: s };
});

// 3 · what it is. VO 2 at 16.36: "So I built StrollCall." 0.4-1.6 ("StrollCall" 1.3) · "Tell it how long you have
// and what you feel like," 2.4-4.6 · "and it plans a short walk worth taking:" 4.8-6.6 · "on your own," 7.1-7.8 ·
// "or with a friend." 8.0-8.8. A1: click on "Plan my walk" at clip 5.82 lands at t 6.0.
add("s3", (t) => {
  let s = `<rect width="1920" height="1080" fill="${C.cream}"/>` + ambient(t, ["#FFF1D6", "#E8F1FF", "#E3F5E8", "#FFE9DF"]);
  const up = prog(t, 1.9, 2.6, easeInOut);  // the logo rises away as the browser comes up
  const a = prog(t, 0.0, 0.85), b = prog(t, 0.15, 1.0);
  const ly = lerp(0, -560, up), ls = lerp(1, 0.5, up);
  if (up < 1) {
    const ha = a < 1 ? hop(t, 12) : { b: Math.max(0, Math.sin((t - 0.85) * 8)) * 12 * Math.max(0, 1 - (t - 0.85) / 0.6), sx: 1, sy: 1 };
    const hb = b < 1 ? hop(t + 0.2, 12) : ha;
    s += `<g transform="translate(960 ${540 + ly}) scale(${ls}) translate(-960 -540)" opacity="${1 - up}">
      ${mascotA({ x: lerp(-200, 840, a), y: 430, s: 1.1, bounce: ha.b, sx: ha.sx, sy: ha.sy, expr: "open", blink: blinkAt(t, 2.5) })}
      ${mascotB({ x: lerp(2120, 1080, b), y: 434, s: 1.05, bounce: hb.b, sx: hb.sx, sy: hb.sy })}
      <path transform="translate(960 300) scale(${1.4 * clamp(springIn(t, 1.0, 0.4), 0, 1.3)})" d="M0 10 c-6 -12 -22 -6 -16 6 l16 16 l16 -16 c6 -12 -10 -18 -16 -6 z" fill="${C.yellow}" stroke="${C.ink}" stroke-width="3"/>
      <g opacity="${prog(t, 1.2, 1.6)}" transform="translate(0 ${(1 - prog(t, 1.2, 1.6)) * 16})">${text(960, 680, "StrollCall", { size: 150 })}</g></g>`;
  }
  if (t < 1.85) return { bg: s };
  // the live site in a browser, rising in
  const rise = springIn(t, 1.9, 0.6);
  const clipT = 5.82 + (t - 6.0);
  const after = clipT > 6.8;  // New walk page
  const zIn = after ? 1 + 0.28 * prog(t, 7.0, 7.6, easeInOut) : 1 + 0.035 * prog(t, 2.2, 5.6, easeInOut);
  const d = dev({ x: 210, y: 160, w: 1500, h: 844, cw: 1920, dy: (1 - clamp(rise)) * 700 + floatY(t, 3, 5), rot: floatR(t, 0.2, 6),
    s: 0.94 + 0.06 * clamp(rise, 0, 1.05), z: zIn, zx: after ? 0.17 : 0.5, zy: after ? 0.16 : 0.62 });
  s += browserChrome(d, "strollcall.onrender.com");
  let fg = "";
  // "Tell it how long you have and what you feel like": underline the page's own line as it is said
  const ul = prog(t, 2.4, 4.4, easeInOut) * (1 - prog(t, 5.6, 6.0));
  if (ul > 0) { const p0 = devPt(d, 645, 708), p1 = devPt(d, 1275, 708); fg += `<path d="M${p0[0]} ${p0[1]} L${lerp(p0[0], p1[0], ul)} ${lerp(p0[1], p1[1], ul)}" stroke="${C.yellow}" stroke-width="10" stroke-linecap="round" opacity=".9"/>`; }
  // "and it plans a short walk worth taking": glow on "Plan my walk", then the click
  const gp = prog(t, 4.8, 5.3) * (1 - prog(t, 6.1, 6.4));
  if (gp > 0) { const c = devPt(d, 960, 862); fg += `<ellipse cx="${c[0]}" cy="${c[1]}" rx="${150 + 8 * Math.sin(t * 6)}" ry="${52 + 4 * Math.sin(t * 6)}" fill="none" stroke="${C.yellow}" stroke-width="12" opacity="${gp}"/>`; }
  fg += ripple(devPt(d, 960, 862), t, 6.0);
  // "on your own, or with a friend": the two modes on the New walk page
  fg += callout(devPt(d, 320, 196), [760, 470], "Just me", t, 7.15, 10.8, { bg: "#FFF3C4" });
  fg += callout(devPt(d, 524, 196), [1180, 470], "With a friend", t, 8.0, 10.8, { bg: "#FFE7D9" });
  return { bg: s, videos: [devVideo(d, "a1", clipT)], fg };
});

// 4 · solo by voice (A2). Speak tapped at clip 2.45 -> t 1.85; the wish is heard 2.4-5.9; transcript at clip 9.75 ->
// t 9.15 ("Muse Voice transcribes it" 8.6-9.6); chips at clip 11.6 -> t 11.0 ("Muse Glimmer" 11.0); the "Read by"
// line settles at clip 14.4 -> t 13.8 ("on Modal" 13.4); "turns it into a plan…" 14.2-16.4; "half a second" 17.6.
// Second part from clip 25.7: "Find my walk" (26.19) at t 17.8, the real wait for the plan (to 29.0), the route.
add("s4", (t) => {
  const seg1 = t < 17.3, clipT = seg1 ? 0.6 + t : 25.7 + (t - 17.3);
  const push = seg1 ? 1 + 0.05 * prog(t, 8.9, 9.6, easeInOut) + 0.03 * prog(t, 13.4, 14.2, easeInOut) - 0.08 * prog(t, 16.9, 17.3) : 1 + 0.03 * prog(t, 21.6, 23.0, easeInOut);
  const d = phoneDev(300, 70, t, { s: push });
  let bg = softBg(t, "#EAF4FF", C.cream) + devShadow(d);
  let fg = phoneFrame(d);
  // Speak, and the wish being spoken
  fg += callout(devPt(d, 80, 471), [1000, 560], "Speak", t, 0.9, 2.3);
  fg += ripple(devPt(d, 80, 471), t, 1.85);
  if (t > 2.3 && t < 6.2) { const m = devPt(d, 80, 471); fg += `<g opacity="${prog(t, 2.3, 2.6) * (1 - prog(t, 5.9, 6.2))}">${waveform(d.x + d.w + 60, m[1], t)}</g>`; }
  fg += callout(devPt(d, 340, 277), [1180, 300], "Muse Voice Transcribe", t, 8.8, 12.6, { bg: "#FFE7D9" });
  fg += chip(1180, 470, "Muse Glimmer reads the wish (open weights, our Modal endpoint)", t, 10.9, 13.3, { bg: "#E4F0FF", size: 24 });
  fg += callout(devPt(d, 300, 356), [1180, 560], "Read by Muse Glimmer · open weights, on Modal", t, 13.4, 17.3, { bg: "#E4F0FF" });
  // "turns it into a plan the route engine understands": a bracket over minutes, ending and mood
  const br = prog(t, 14.3, 14.8) * (1 - prog(t, 16.9, 17.3));
  if (br > 0) {
    const a1 = devPt(d, 372, 112), a2 = devPt(d, 372, 318);
    fg += `<g opacity="${br}"><path d="M${a1[0] + 12} ${a1[1]} h22 V${a2[1]} h-22" fill="none" stroke="${C.ink}" stroke-width="4" stroke-linecap="round"/>
      <path d="M${a1[0] + 34} ${(a1[1] + a2[1]) / 2} H${1000}" stroke="${C.ink}" stroke-width="3.5"/></g>`
      + chip(1180, (a1[1] + a2[1]) / 2, "a plan the planner understands: 25 min · end at cafe · quiet", t, 14.4, 17.2, { bg: "#fff", size: 24 });
  }
  fg += chip(1180, 820, "0.55 s median wish reading · evaluation run 1", t, 17.5, 21.0, { bg: C.yellow });
  if (!seg1) {
    fg += callout(devPt(d, 196, 336), [1060, 420], "Find my walk", t, 17.35, 18.9);
    fg += ripple(devPt(d, 196, 336), t, 17.8);
    fg += chip(1120, 600, "the real wait: about 3 s", t, 18.3, 20.6, { bg: "#fff" });
    fg += callout(devPt(d, 300, 230), [1160, 300], "a real route on our walking graph", t, 22.6, 99);
  }
  const ge = t < 2.3 ? "smile" : t < 6 ? "o" : t < 11 ? "smile" : "happy";
  bg += guide(205, 930, t, ge);
  return { bg, videos: [devVideo(d, "a2", clipT)], fg };
});

// 5 · walking + the buddy (A4, A5). "the map fills the screen" 0.9-1.9 as Start walking (clip 1.96 -> t 0.66) opens
// the map; "walking buddy" 2.9 as it lands; the app speaks "Voice prompts on." (t 4.29) and a turn prompt (t 5.46);
// "When I ask for a coffee stop," 9.0-10.3; the wish is held and spoken from t 10.4; let go at 12.88;
// "Muse Spark picks a tool," 13.0 · "the planner re-routes," 14.8 · "and only real, open places come back." 16.6-18.6;
// the buddy's reply appears at 16.68 and its voice from 17.3 (under the VO until 18.75).
add("s5", (t) => {
  let clip, clipT;
  if (t < 4) { clip = "a4"; clipT = 1.5 + t; }
  else if (t < 8.9) { clip = "a4"; clipT = 12.7 + (t - 4); }
  else if (t < 12.77) { clip = "a5"; clipT = 0.13 + (t - 8.9); }
  else { clip = "a5"; clipT = Math.min(4.85 + (t - 12.77), 14.0); }
  const hold = t > 21.9 ? prog(t, 21.9, 25.3, easeInOut) : 0;
  const d = phoneDev(300, 70, t, { s: 1 + 0.03 * prog(t, 9.6, 10.4, easeInOut), z: 1 + 0.32 * hold, zx: 0.5, zy: 0.72 });
  let bg = softBg(t, "#E9F7EE", C.cream, ["#D6F2DF", "#FFF1D6", "#E8F1FF", "#E3F5E8"]) + devShadow(d);
  let fg = phoneFrame(d);
  fg += ripple(devPt(d, 194, 462), t, 0.46);
  fg += callout(devPt(d, 36, 690), [1000, 640], "your walking buddy", t, 3.15, 4.0, { bg: "#E4F0FF" });
  if (t > 4 && t < 9.0) fg += tag(d.x + d.w + 48, 130, "simulated location");
  fg += chip(1180, 250, "the app speaks: “Voice prompts on.”", t, 4.25, 5.4, { bg: "#fff", size: 24 });
  fg += callout(devPt(d, 200, 30), [1180, 200], "next turn, spoken aloud", t, 5.45, 8.8);
  fg += callout(devPt(d, 58, 785), [1120, 760], "minutes left", t, 6.6, 8.8);
  fg += callout(devPt(d, 185, 792), [1060, 900], "hold to talk", t, 9.6, 12.9);
  if (t > 10.5 && t < 12.0) { const m = devPt(d, 185, 792); fg += `<g opacity="${prog(t, 10.5, 10.8) * (1 - prog(t, 11.7, 12.0))}">${waveform(d.x + d.w + 60, m[1] - 120, t)}</g>`; }
  const steps = [["Muse Spark", 13.0, "#E4F0FF"], ["add_stop", 13.9, "#fff"], ["planner", 14.75, "#fff"], ["real, open place", 16.6, "#D6F2DF"]];
  steps.forEach(([lab, at, col], i) => {
    const y = 300 + i * 120;
    if (i) fg += `<g opacity="${1 - prog(t, 21.5, 21.8)}">${drawLine([[1260, y - 90], [1260, y - 30]], prog(t, at - 0.3, at), `stroke="${C.ink}" stroke-width="4" stroke-linecap="round"`)}</g>`;
    fg += chip(1260, y, lab, t, at, 21.5, { bg: col, size: 30 });
  });
  fg += callout(devPt(d, 126, 624), [1000, 860], "Undo", t, 17.6, 21.5, { bg: "#FFF3C4" });
  const ge = t < 9 ? "smile" : t < 12.9 ? "o" : t < 16.7 ? "smile" : "happy";
  bg += guide(205, 930, t, ge);
  return { bg, videos: [devVideo(d, clip, clipT)], fg };
});

// 6 · with a friend. "Walking is better with someone." 0.3-1.7 · card at t 1.45 (A6 clip 26.45) · "I send one link"
// 2.1-2.9 with the paper plane · "My friend doesn't need an app:" 3.8-5.0 as B's phone opens the link ·
// "one tap" 6.0-6.3 = B taps "Use my location" (clip 3.2 -> t 6.2) · "and they can say what they'd like too." 7.0-8.4,
// B speaks from t 8.0 (clip 5.97); "I'm in" at t 15.46 (clip 13.43); the plan on both phones from t 16.0.
add("s6", (t) => {
  const focusB = prog(t, 3.4, 4.1, easeInOut) * (1 - prog(t, 15.8, 16.4, easeInOut));
  const pa = phoneDev(300, 110, t, { s: 0.94 - 0.12 * focusB, dx: -70 * focusB, ph: 0.2 });
  const pb = phoneDev(1220, 110, t, { s: 0.94 + 0.06 * focusB, dx: -150 * focusB, ph: 0.6 });
  const after = t >= 16.0;
  let bg = softBg(t, "#FFF1E6", C.cream, ["#FFE7D9", "#E8F1FF", "#FFF1D6", "#E3F5E8"]) + devShadow(pa) + devShadow(pb);
  const hA = pulse(t, 0.3, 1.2) * 14, hB = pulse(t, 4.0, 1.0) * 16 + (after ? pulse(t, 16.1, 0.8) * 14 : 0);
  bg += mascotA({ x: pa.x + pa.w / 2 + pa.dx, y: 52, s: 0.42, bounce: hA + (after ? pulse(t, 16.1, 0.8) * 14 : 0), blink: blinkAt(t, 2.9), expr: after ? "happy" : "smile" });
  bg += mascotB({ x: pb.x + pb.w / 2 + pb.dx, y: 54, s: 0.42, bounce: hB, expr: t > 3.8 ? "happy" : "sleepy" });
  const videos = [devVideo(pa, after ? "a8a" : "a6", after ? t - 16.0 : Math.min(25.0 + t, 31.7))];
  if (after) videos.push(devVideo(pb, "a8b", t - 16.0));
  else if (t >= 3.6) videos.push(devVideo(pb, "a7", t < 6.8 ? 0.6 + (t - 3.6) : 5.97 + (t - 8.0)));
  else bg += devGroup(pb, `<rect width="${pb.w}" height="${pb.h}" rx="50" fill="#F4EEE6"/>${text(pb.w / 2, pb.h / 2, "your friend's phone", { size: 28, family: "Nunito", weight: 700, fill: "#8A82A0" })}`);
  let fg = phoneFrame(pa, C.blue) + phoneFrame(pb, C.orange);
  fg += chip(960, 300, "Illustration by Muse Image", t, 1.55, 3.4, { bg: "#FFF3C4" });
  const fly = prog(t, 2.3, 3.6, easeInOut);
  if (fly > 0 && fly < 1) {
    const s0 = devPt(pa, 300, 400), s1 = devPt(pb, 120, 300);
    const x = lerp(s0[0], s1[0], fly), y = lerp(s0[1], s1[1], fly) - Math.sin(fly * Math.PI) * 220;
    fg += `<g transform="translate(${x} ${y}) rotate(${-20 + fly * 40}) scale(${1 + 0.3 * Math.sin(fly * Math.PI)})"><path d="M-44 0 L44 -24 L12 28 Z" fill="#fff" stroke="${C.ink}" stroke-width="4" stroke-linejoin="round"/>
      <path d="M-44 0 L12 0 L12 28" fill="none" stroke="${C.ink}" stroke-width="3"/></g>`
      + drawLine([[s0[0], s0[1]], [x, y]], 1, `stroke="${C.ink}" stroke-width="2" stroke-dasharray="6 10" opacity=".3"`);
  }
  fg += chip(800, 250, "one link · no app · no account", t, 4.1, 7.4, { bg: "#fff" });
  fg += ripple(devPt(pb, 111, 345), t, 6.2);
  fg += ripple(devPt(pb, 94, 244), t, 8.0);
  if (t > 8.5 && t < 10.6) { const m = devPt(pb, 94, 244); fg += `<g opacity="${prog(t, 8.5, 8.8) * (1 - prog(t, 10.3, 10.6))}">${waveform(m[0] - 330, m[1] - 70, t, 12, C.orange)}</g>`; }
  fg += callout(devPt(pb, 70, 496), [960, 640], "I'm in", t, 14.7, 16.0, { bg: "#FFE7D9" });
  fg += ripple(devPt(pb, 70, 496), t, 15.46);
  fg += chip(960, 520, "a few seconds later…", t, 15.6, 16.2, { bg: "#fff" });
  fg += chip(960, 520, "the plan, on both phones", t, 16.3, 99, { bg: "#D6F2DF" });
  return { bg, videos, fg };
});

// 7 · the fair meeting point. "Muse Spark balances both of our wishes and explains the trade-off." 0.3-3.5 over B's
// plan (A8, still from clip 11.4 to 14.2); then the data animation from t 4 (scenes.js, S7): "And the meeting
// point is fair by walking time…" 4.0-7.7 · "…leaves us 4.8 minutes apart;" "4.8" at 10.9 = the pill ·
// "ours gets us there within a minute." "within a minute" at 15.3 = the right pill.
add("s7", (t) => {
  if (t < 4.2) {
    const out = prog(t, 3.7, 4.2, easeInOut);
    const d = phoneDev(300, 70, t, { s: 1 - 0.15 * out });
    let bg = softBg(t, "#FFF1E6", C.cream, ["#FFE7D9", "#E8F1FF", "#FFF1D6", "#E3F5E8"]) + `<g opacity="${1 - out}">${devShadow(d)}</g>`;
    let fg = `<g opacity="${1 - out}">${phoneFrame(d)}
      ${callout(devPt(d, 330, 336), [1180, 400], "Muse Spark balances both wishes", t, 0.75, 99)}
      ${callout(devPt(d, 330, 412), [1180, 620], "Wishes read by Muse Glimmer", t, 2.2, 99, { bg: "#E4F0FF" })}</g>`;
    if (out > 0) bg += `<g opacity="${out}">${SCENES.s7.draw(t - 4)}</g>`;
    bg += guide(205, 930, t, t > 1 ? "happy" : "smile");
    return { bg, videos: [devVideo(d, "a8b2", Math.min(11.4 + t, 14.2), { opacity: 1 - out })], fg };
  }
  return { bg: SCENES.s7.draw(t - 4) };
});

// 8 · under the hood. VO 7 at 115.78 (t = word time + 0.3): "Under the hood:" 0.4 · "a walking graph of New York with
// 139,106 points," 1.8-6.0 · "built from OpenStreetMap," 6.7-7.6 · "plans in milliseconds." 8.3-9.4 · "Meta models
// handle the human side:" 10.4-12.0 · Glimmer 12.6 · Spark 14.5 · Image 16.9 · Voice 19.1. The terminal (A3, the
// warm-up script's real output) slides in with "Muse Glimmer reads wishes".
add("s8", (t) => {
  const g = window.DATA.graph;
  const arch = prog(t, 9.9, 10.6, easeInOut);
  let s = `<rect width="1920" height="1080" fill="${C.ink}"/>`;
  if (arch < 1) {
    const reveal = prog(t, 0.0, 3.6, easeInOut);
    const zoom = 1 + 1.5 * prog(t, 7.7, 9.6, easeInOut);
    const fx = lerp(960, g.focus[0], prog(t, 7.7, 9.6, easeInOut)), fy = lerp(540, g.focus[1], prog(t, 7.7, 9.6, easeInOut));
    s += `<g opacity="${1 - arch}"><clipPath id="sweep"><rect x="0" y="0" width="${1920 * reveal}" height="1080"/></clipPath>
      <g transform="translate(960 540) scale(${zoom * (1 + 0.02 * t / 10)}) translate(${-fx} ${-fy})"><image href="${g.png}" x="0" y="0" width="1920" height="1080" clip-path="url(#sweep)"/>
      ${drawLine(g.route, prog(t, 8.1, 9.2), `stroke="${C.yellow}" stroke-width="${7 / zoom}" stroke-linecap="round" stroke-linejoin="round"`)}</g>`;
    const n = Math.round(g.nodes_total * prog(t, 3.4, 4.8, (x) => easeOut(x)));
    s += `<g opacity="${prog(t, 0.3, 0.8)}">${text(120, 140, "Our walking graph of New York", { size: 54, anchor: "start", fill: "#fff" })}
      ${text(120, 205, `${n.toLocaleString("en-US")} nodes`, { size: 40, family: "Nunito", weight: 800, anchor: "start", fill: C.yellow, opacity: prog(t, 3.3, 3.6) })}
      ${text(120 + 30 + `${g.nodes_total.toLocaleString("en-US")} nodes`.length * 21, 205, "· Manhattan shown", { size: 30, family: "Nunito", weight: 700, anchor: "start", fill: "#CFE9D8", opacity: prog(t, 4.6, 5.0) })}</g>`;
    const osm = springIn(t, 6.6, 0.45);
    s += `<g opacity="${clamp(osm)}" transform="translate(1600 1000) scale(${0.9 + 0.1 * clamp(osm, 0, 1.1)})"><rect x="-260" y="-26" width="520" height="52" rx="26" fill="#2F2850" stroke="#CFE9D8" stroke-width="2"/>
      ${text(0, 9, "built from © OpenStreetMap contributors (ODbL)", { size: 22, family: "Nunito", weight: 800, fill: "#CFE9D8" })}</g>`;
    s += chip(1500, 160, "plans in 0.029 s (median)", t, 8.6, 99, { bg: C.yellow }) + `</g>`;
  }
  if (arch > 0) {
    const tt = t;
    let a = `<g opacity="${arch}">` + softBg(t, "#EAF4FF", C.cream);
    const box = (x, y, w, h, title, sub, t0, color = "#fff") => {
      const p = springIn(tt, t0, 0.45);
      if (p <= 0) return "";
      return `<g opacity="${clamp(p * 2)}" transform="translate(${x + w / 2} ${y + h / 2 + floatY(tt, 3, 4, x / 900)}) scale(${0.9 + 0.1 * clamp(p, 0, 1.1)}) translate(${-w / 2} ${-h / 2})">
        <g filter="url(#shadow)"><rect width="${w}" height="${h}" rx="26" fill="${color}"/></g>
        <rect width="${w}" height="${h}" rx="26" fill="none" stroke="${C.ink}" stroke-width="3"/>
        ${text(w / 2, 52, title, { size: 32 })}${text(w / 2, 92, sub, { size: 22, family: "Nunito", weight: 700, fill: "#6B6380" })}</g>`;
    };
    const arrow = (x1, x2, y, t0) => { const p = prog(tt, t0, t0 + 0.35); return drawLine([[x1, y], [x2, y]], p, `stroke="${C.ink}" stroke-width="4" stroke-linecap="round"`)
      + (p >= 1 ? `<path d="M${x2 - 14} ${y - 10} L${x2} ${y} L${x2 - 14} ${y + 10}" fill="none" stroke="${C.ink}" stroke-width="4" stroke-linecap="round"/>` : ""); };
    a += box(90, 180, 300, 130, "Phone web app", "no install, no account", 10.2);
    a += arrow(400, 500, 245, 10.45);
    a += box(510, 180, 300, 130, "FastAPI", "on Render", 10.5);
    a += arrow(820, 920, 245, 10.75);
    a += box(930, 180, 380, 130, "Planner", "on our walking graph", 10.8, "#E9F7EE");
    a += `<g opacity="${prog(tt, 10.8, 11.2)}">${text(1610, 150, "Meta models", { size: 40 })}</g>`;
    const models = [["Muse Glimmer", "reads wishes (open weights, Modal)", "#E4F0FF", 12.6], ["Muse Spark", "negotiates, ranks, calls tools", "#fff", 14.5],
      ["Muse Image", "draws the invite", "#FFF3C4", 16.9], ["Muse Voice", "listens", "#FFE7D9", 19.05]];
    let active = -1;
    models.forEach(([n, j, c, at], i) => { a += box(1400, 190 + i * 160, 420, 130, n, j, at, c); if (tt >= at) active = i; });
    if (active >= 0) {
      const y = 255 + active * 160;
      a += `<rect x="1392" y="${y - 73}" width="436" height="146" rx="30" fill="none" stroke="${C.yellow}" stroke-width="7" opacity="${0.6 + 0.4 * Math.sin(tt * 6)}"/>`;
      a += mascotA({ x: 1300, y: y + 8, s: 0.5, expr: "open", bounce: Math.abs(Math.sin(tt * 3)) * 5, rot: -8, blink: blinkAt(tt, 2.7) });
    }
    // the terminal: the warm-up script's real output (A3), with "Muse Glimmer reads wishes"
    const ti = springIn(tt, 12.3, 0.55), to = prog(tt, 18.6, 19.1);
    if (ti > 0 && to < 1) {
      const d = dev({ x: 90, y: 400, w: 1120, h: 630, cw: 1920, s: 0.92 + 0.08 * clamp(ti, 0, 1.08), dy: (1 - clamp(ti)) * 120 + floatY(tt, 3, 5), rot: floatR(tt, 0.25, 6), z: 1.18, zx: 0.5, zy: 0.33 });
      a += `<g opacity="${clamp(ti * 2) * (1 - to)}">${devShadow(d, 20)}</g>`;
      window._a3 = { d, op: clamp(ti * 2) * (1 - to), clipT: 11.3 + (tt - 12.3) };
      const sw = prog(tt, 13.6, 14.6, easeInOut);
      let over = "";
      if (sw > 0) { const p0 = devPt(d, 120, 398), p1 = devPt(d, 1820, 462); over += `<g opacity="${1 - to}"><rect x="${p0[0]}" y="${p0[1]}" width="${(p1[0] - p0[0]) * sw}" height="${p1[1] - p0[1]}" fill="${C.yellow}" opacity=".38" rx="6"/></g>`; }
      over += `<g opacity="${prog(tt, 13.0, 13.4) * (1 - to)}">${drawLine([[d.x + d.w * 0.96, 470], [1392, 255]], prog(tt, 13.0, 13.4), `stroke="${C.ink}" stroke-width="3" stroke-dasharray="8 8" opacity=".5"`)}</g>`;
      over += chip(650, 380, "Muse Glimmer on our Modal endpoint · BF16 · 1x H200", tt, 13.7, 18.6, { bg: "#E4F0FF", size: 24 });
      window._a3over = over;
    } else { window._a3 = null; window._a3over = ""; }
    s += a + `</g>`;
  }
  const videos = [];
  if (window._a3 && arch >= 1) videos.push(devVideo(window._a3.d, "a3", window._a3.clipT, { opacity: window._a3.op, r: 14 }));
  return { bg: s, videos, fg: arch >= 1 ? window._a3over || "" : "" };
});

// 9 · honest evaluation. VO 8 at 136.6 (t = word time + 0.3): "committed" 1.6 · "12 of 12" 3.5-4.0 · "10 of 10" 7.5-8.0 ·
// "against 7" 9.0-9.7 · "And a checker throws out" 11.2-12.0 · "any claim our data can't back up." 12.3-14.1.
add("s9", (t) => {
  let s = softBg(t, "#EEF6EF", C.cream, ["#D6F2DF", "#FFF1D6", "#E8F1FF", "#E3F5E8"]);
  const st = prog(t, 1.35, 1.65), thump = pulse(t, 1.55, 0.35);
  if (st > 0) s += `<g opacity="${st}" transform="translate(960 150) rotate(-3) scale(${1.25 - 0.25 * st + 0.04 * thump})">
    <rect x="-520" y="-48" width="1040" height="96" rx="20" fill="#fff" fill-opacity=".6" stroke="${C.green}" stroke-width="6"/>
    ${text(0, 16, "Pre-registered: cases committed before each run", { size: 42, fill: C.green })}</g>`;
  const card = (x, title, val, sub, t0) => {
    const p = springIn(t, t0, 0.5);
    if (p <= 0) return "";
    return `<g opacity="${clamp(p * 2)}" transform="translate(${x + 260} ${450 + floatY(t, 3, 4.2, x / 700)}) scale(${0.9 + 0.1 * clamp(p, 0, 1.1)}) translate(-260 -150)">
      <g filter="url(#shadow)"><rect width="520" height="300" rx="32" fill="#fff"/></g>
      ${text(260, 70, title, { size: 30, family: "Nunito", weight: 800, fill: "#6B6380" })}${val}${text(260, 268, sub, { size: 20, family: "Nunito", weight: 700, fill: "#8A82A0" })}</g>`;
  };
  // 12 of 12 right outcomes (benchmarks/2026-10-31-local.md:13): lands on the second "12"
  const c1 = prog(t, 3.0, 4.0, (x) => x);
  s += card(110, "test pairs, right outcome", text(260, 190, `${Math.round(12 * c1)} / 12`, { size: 96, fill: C.green }), "benchmarks/2026-10-31-local.md", 2.8);
  // wishes read correctly, Muse Spark 10/10 vs keyword rules 7/10 (benchmarks/2026-10-28-ablation-wishes.md:16)
  const b1 = prog(t, 7.2, 8.0), b2 = prog(t, 9.1, 9.75);
  const bars = `<g transform="translate(60 100)">${text(0, 22, "Muse Spark", { size: 24, family: "Nunito", weight: 800, anchor: "start" })}
    <rect x="0" y="34" width="${360 * b1}" height="30" rx="15" fill="${C.blue}"/>${text(380, 58, `${Math.round(10 * b1)}/10`, { size: 26, family: "Nunito", weight: 800, anchor: "start" })}
    ${text(0, 104, "keyword rules", { size: 24, family: "Nunito", weight: 800, anchor: "start" })}
    <rect x="0" y="116" width="${252 * b2}" height="30" rx="15" fill="#B9B2CC"/>${text(270, 140, `${Math.round(7 * b2)}/10`, { size: 26, family: "Nunito", weight: 800, anchor: "start" })}</g>`;
  s += card(700, "wishes read correctly", bars, "benchmarks/2026-10-28-ablation-wishes.md", 6.3);
  // wish reading, median: Glimmer 0.55 s vs Muse Spark 3.58 s (benchmarks/2026-10-31-open-weights-run1.md:14)
  const lp = prog(t, 10.0, 10.8, (x) => x);
  s += card(1290, "reading a wish, median", `${text(260, 160, `${(0.55 * lp).toFixed(2)} s`, { size: 72, fill: C.blue })}${text(260, 218, `Muse Glimmer · Muse Spark ${(3.58 * lp).toFixed(2)} s`, { size: 24, family: "Nunito", weight: 800 })}`, "benchmarks/2026-10-31-open-weights-run1.md", 9.8);
  // the honesty check: the reason is real (benchmarks/2026-10-30-rejections.md:15); the sentence is illustrative
  const hp = springIn(t, 10.9, 0.5);
  if (hp > 0) {
    const strike = prog(t, 11.6, 12.1), repl = prog(t, 13.2, 13.7);
    s += `<g opacity="${clamp(hp * 2)}" transform="translate(960 ${818 + (1 - clamp(hp)) * 40}) scale(${0.92 + 0.08 * clamp(hp, 0, 1.08)}) translate(-600 -115)"><g filter="url(#shadow)"><rect width="1200" height="200" rx="30" fill="#fff"/></g>
      ${text(60, 75, "“This street is quiet.”", { size: 42, family: "Nunito", weight: 800, anchor: "start", fill: strike > 0.5 ? "#9C95AE" : C.ink })}
      <line x1="56" y1="62" x2="${56 + 450 * strike}" y2="62" stroke="#E0484D" stroke-width="7" stroke-linecap="round"/>
      <g opacity="${prog(t, 12.0, 12.3)}">${tag(560, 70, "rejected: unverifiable claim ‘quiet’ (not in our data)", { bg: "#FFE1E1" })}</g>
      <g opacity="${repl}" transform="translate(0 ${(1 - repl) * 8})">${text(60, 152, "“Quiet, as B asked.”", { size: 42, family: "Nunito", weight: 800, anchor: "start", fill: C.green })}</g>
      ${text(1170, 188, "illustration of a real rule · reason from benchmarks/2026-10-30-rejections.md", { size: 17, family: "Nunito", weight: 700, anchor: "end", fill: "#8A82A0" })}</g>`;
    const nod = repl > 0 ? Math.sin(prog(t, 13.4, 14.4, (x) => x) * Math.PI * 2) * 6 : 0;
    s += mascotA({ x: 1740, y: 830, s: 0.7, expr: repl > 0.5 ? "happy" : "smile", bounce: Math.abs(nod), rot: nod, blink: blinkAt(t, 2.6) });
  }
  const videos = [];
  if (t < 3.1) {
    const p = springIn(t, 0.25, 0.5), o = 1 - prog(t, 2.7, 3.1);
    const d = dev({ x: 1180, y: 300, w: 640, h: 360, cw: 1920, s: 0.9 + 0.1 * clamp(p, 0, 1.08), r: 16, dy: floatY(t, 3, 4), rot: 1.5 });
    s += `<g opacity="${clamp(p * 2) * o}">${devShadow(d, 18)}</g>`;
    s += `<g opacity="${clamp(p * 2) * o}">${text(1500, 280, "the report, on GitHub", { size: 24, family: "Nunito", weight: 800, fill: "#6B6380" })}</g>`;
    videos.push(devVideo(d, "a10", 3 + t, { opacity: clamp(p * 2) * o }));
  }
  return { bg: s, videos };
});

// 10 · out in the city at golden hour (music only; no user-test data exists to show)
add("s10", (t) => {
  const shotLen = 11 / 3, shot = Math.min(2, Math.floor(t / shotLen)), tt = t - shot * shotLen;
  const ground = 820, pan = tt * 40;
  let s = `<rect width="1920" height="1080" fill="url(#gold)"/>`;
  s += `<circle cx="1500" cy="${300 + tt * 6}" r="110" fill="#FFE7A8" opacity=".95"/><circle cx="1500" cy="${300 + tt * 6}" r="190" fill="#FFE7A8" opacity=".25"/>`;
  s += cloud(300 + t * 12, 160, 1, 0.7) + cloud(1300 + t * 9, 120, 0.8, 0.6) + birds(t, 400 + shot * 300, 220);
  // far skyline (slow), mid trees (faster): parallax as the camera pans with the walkers
  s += `<g fill="#F2B98A" opacity=".55">${[[0, 300], [160, 380], [300, 260], [520, 420], [760, 330], [980, 400], [1220, 300], [1420, 380], [1640, 280], [1820, 360]]
    .map(([x, h]) => `<rect x="${(x - pan * 0.25 + 2000) % 2000 - 80}" y="${ground - h}" width="170" height="${h}" rx="12"/>`).join("")}</g>`;
  s += `<rect x="0" y="${ground}" width="1920" height="80" fill="#EBDCC4"/><rect x="0" y="${ground + 80}" width="1920" height="200" fill="#C9B79E"/>
    <path d="M0 ${ground} H1920" stroke="${C.ink}" stroke-width="3" opacity=".25"/>`;
  for (let i = 0; i < 9; i++) {  // falling leaves
    const lx = (i * 233 + t * 30) % 1960, ly = (i * 97 + t * (60 + i * 7)) % 900, r = t * 90 + i * 40;
    s += `<ellipse cx="${lx}" cy="${ly}" rx="9" ry="5" fill="${i % 2 ? "#E8894B" : "#F2C14E"}" transform="rotate(${r} ${lx} ${ly})" opacity=".85"/>`;
  }
  const fadeIn = prog(tt, 0, 0.35), fadeOut = shot < 2 ? prog(tt, shotLen - 0.3, shotLen) : 0;
  if (shot === 0) {  // the blue one, out past a park, phone in hand
    s += `<rect x="0" y="${ground - 230}" width="1920" height="230" fill="#A7DBA9"/>`;
    [[160, 0], [560, 2], [980, 1], [1380, 0], [1780, 2]].forEach(([x, tone], i) => { s += swayTree((x - pan + 2000) % 2000 - 40, ground, 1.15, tone, t, i); });
    const x = 520 + tt * 120, h = hop(t, 10);
    s += mascotA({ x, y: ground + 8, s: 1.05, bounce: h.b, sx: h.sx, sy: h.sy, expr: "open", blink: blinkAt(t, 2.4) })
      + `<g transform="translate(${x + 54} ${ground - 24 - h.b}) rotate(12)"><rect width="34" height="56" rx="8" fill="${C.ink}"/><rect x="4" y="5" width="26" height="42" rx="5" fill="#BFE3FF"/></g>`;
  } else if (shot === 1) {  // from opposite streets to one corner, a wave
    s += brownstone(40 - pan * 0.5, ground, 520, 560, "#D9926E") + brownstone(1360 - pan * 0.5, ground, 520, 600, "#C97B5A");
    const a = prog(tt, 0, 2.2, easeInOut), b = prog(tt, 0.15, 2.4, easeInOut);
    const ha = a < 1 ? hop(t, 10) : { b: pulse(tt, 2.3, 0.6) * 18, sx: 1, sy: 1 }, hb = b < 1 ? hop(t + 0.3, 10) : { b: pulse(tt, 2.5, 0.6) * 18, sx: 1, sy: 1 };
    s += mascotA({ x: lerp(-100, 830, a), y: ground + 10, s: 1.0, bounce: ha.b, sx: ha.sx, sy: ha.sy, expr: a >= 1 ? "open" : "smile" });
    s += mascotB({ x: lerp(2020, 1090, b), y: ground + 14, s: 0.95, bounce: hb.b, sx: hb.sx, sy: hb.sy });
    if (tt > 2.4) s += `<g transform="rotate(${Math.sin(tt * 14) * 18} 890 ${ground - 50})"><ellipse cx="890" cy="${ground - 92}" rx="14" ry="22" fill="${C.blue}" stroke="${C.ink}" stroke-width="4"/></g>`;
    const hp = springIn(tt, 2.6, 0.4);
    if (hp > 0) s += `<path transform="translate(960 ${ground - 170}) scale(${1.6 * clamp(hp, 0, 1.2)})" d="M0 10 c-6 -12 -22 -6 -16 6 l16 16 l16 -16 c6 -12 -10 -18 -16 -6 z" fill="${C.yellow}" stroke="${C.ink}" stroke-width="3"/>`;
  } else {  // a cafe table, two cups
    s += `<rect x="560" y="${ground - 420}" width="800" height="420" rx="14" fill="#FBEBD3" stroke="${C.ink}" stroke-width="4"/>
      ${Array.from({ length: 8 }, (_, i) => `<path d="M${560 + i * 100} ${ground - 400} h100 v${60 + 4 * Math.sin(t * 2 + i)} q-50 30 -100 0 z" fill="${i % 2 ? C.cream : C.yellow}" stroke="${C.ink}" stroke-width="3"/>`).join("")}
      <rect x="760" y="${ground - 90}" width="400" height="22" rx="10" fill="#8A5A3C" stroke="${C.ink}" stroke-width="3"/><rect x="950" y="${ground - 70}" width="20" height="80" fill="#8A5A3C"/>`;
    const laugh = Math.abs(Math.sin(tt * 4)) * 6;
    s += mascotA({ x: 700, y: ground - 60, s: 0.9, expr: "happy", feet: false, bounce: laugh, rot: 3 * Math.sin(tt * 3) }) + mascotB({ x: 1220, y: ground - 56, s: 0.88, feet: false, bounce: laugh * 0.8, rot: -3 * Math.sin(tt * 3) });
    s += `<rect x="830" y="${ground - 130}" width="46" height="42" rx="8" fill="#fff" stroke="${C.ink}" stroke-width="3"/><rect x="1040" y="${ground - 130}" width="46" height="42" rx="8" fill="#fff" stroke="${C.ink}" stroke-width="3"/>
      ${[0, 1].map((k) => `<path d="M${853 + k * 210} ${ground - 150 - ((tt * 20) % 20)} q8 -12 0 -24" fill="none" stroke="#fff" stroke-width="4" opacity=".8"/>`).join("")}`;
  }
  s += `<rect width="1920" height="1080" fill="#FFE7C2" opacity="${Math.max(1 - fadeIn, fadeOut) * 0.9}"/>`;
  return { bg: s };
});

// 11 · end card (scenes.js)
add("s11", (t) => ({ bg: SCENES.s11.draw(t) }));

let acc = 0;
for (const sc of T) { sc.start = acc; acc += sc.dur; }
const TOTAL = acc;

// ---------- transitions: a route push. The old scene slides out, the new one in, and a green route line with a
// white dashed centre line runs along the seam (the signature motif). 0.7 s around each scene boundary. ----------
const TR = 0.35;
function transitionAt(t) {
  for (let i = 1; i < T.length; i++) {
    const B = T[i].start;
    if (t >= B - TR && t < B + TR) return { i, e: easeInOut((t - (B - TR)) / (2 * TR)) };
  }
  return null;
}
function seam(x, t) {
  const pts = [];
  for (let y = -60; y <= 1140; y += 30) pts.push([x + 46 * Math.sin(y / 170 + t * 3), y]);
  const d = pathD(pts);
  const pin = pts[18];
  return `<path d="${d}" fill="none" stroke="${C.green}" stroke-width="86" stroke-linecap="round"/>
    <path d="${d}" fill="none" stroke="#fff" stroke-width="7" stroke-dasharray="26 22" stroke-linecap="round" opacity=".9"/>
    <g transform="translate(${pin[0]} ${pin[1] - 40})"><path d="M0 34 C-26 4 -26 -22 0 -22 C26 -22 26 4 0 34 Z" fill="${C.yellow}" stroke="${C.ink}" stroke-width="4"/><circle cy="-4" r="8" fill="${C.ink}"/></g>`;
}

// ---------- captions: VO phrases at their real word times, plus the other speech (wish, app, buddy) ----------
function buildCaptions(words, beats) {
  const caps = [];
  const split = (txt) => {
    if (txt.length <= 46) return [txt];
    const w = txt.split(" "); let best = 1, bd = 1e9;
    for (let k = 1; k < w.length; k++) { const a = w.slice(0, k).join(" ").length, b = w.slice(k).join(" ").length; if (Math.max(a, b) < bd) { bd = Math.max(a, b); best = k; } }
    return [w.slice(0, best).join(" "), w.slice(best).join(" ")];
  };
  for (const p of beats.vo) {
    const ws = words[p.vo], to = p.to === "end" ? ws.length - 1 : p.to, shift = p.word_at - ws[p.from].s;
    // within a long phrase, break at commas/colons into captions of at most ~2 lines
    let chunk = [];
    const flush = () => { if (!chunk.length) return; caps.push({ start: chunk[0].s + shift - 0.05, end: chunk[chunk.length - 1].e + shift + 0.3, lines: split(chunk.map((w) => w.w).join(" ")) }); chunk = []; };
    for (let k = p.from; k <= to; k++) {
      chunk.push(ws[k]);
      const len = chunk.map((w) => w.w).join(" ").length;
      const next = k < to ? ws[k + 1].w.length + 1 : 0;
      if ((/[.,:;?]$/.test(ws[k].w) && len >= 10) || len + next > 70) flush();
    }
    flush();
  }
  for (const s of beats.sounds) {
    const start = Math.max(s.at + s.speech[0], s.duck_until || 0) - 0.05;  // a ducked line is captioned once it is heard
    caps.push({ start, end: s.at + s.speech[1] + 0.3, lines: split(s.caption), quote: true });
  }
  caps.sort((a, b) => a.start - b.start);
  for (let i = 0; i < caps.length - 1; i++) caps[i].end = Math.min(caps[i].end, caps[i + 1].start - 0.02);
  return caps;
}
function captionSvg(t) {
  const c = (window.CAPS || []).find((x) => t >= x.start && t < x.end);
  if (!c) return "";
  const p = prog(t, c.start, c.start + 0.18);
  const w = Math.max(...c.lines.map((l) => l.length)) * 16.6 + 70, h = c.lines.length * 44 + 26;
  return `<g opacity="${p}" transform="translate(960 ${1046 - h / 2 + (1 - p) * 6})"><rect x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}" rx="${Math.min(h / 2, 34)}" fill="${c.quote ? "#FFF8E1" : C.cream}" opacity=".95" stroke="${C.ink}" stroke-opacity=".15" stroke-width="2"/>
    ${c.lines.map((l, i) => text(0, -h / 2 + 44 + i * 44, l.replace(/&/g, "&amp;"), { size: 31, family: "Nunito", weight: c.quote ? 800 : 700, fill: c.quote ? "#5A4A12" : C.ink })).join("")}</g>`;
}
