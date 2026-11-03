// The whole demo: scenes on one timeline, recordings placed as <video> layers, captions from the voiceover.
// Each scene's draw(t) returns { bg, fg, videos: [{ clip, t, x, y, w, h, r, scale, ox, oy, opacity }] } where
// t is the time inside the scene. Clips are the real recordings (video/assets/screen|phone, transcoded for
// seeking by build_clips.py). Every number drawn here comes from DATA (video/assets/data) or the edit plan.

const PH = { w: 397, h: 860 };            // phone screen on stage (css 390x844 scaled by 1.018)
const PS = PH.w / 390;                     // css px -> stage px inside the phone
const phoneAt = (x, y) => ({ x, y, w: PH.w, h: PH.h });
const cssToStage = (ph, cx, cy, scale = 1) => {
  const cxs = ph.x + PH.w / 2, cys = ph.y + PH.h / 2;
  return [cxs + (cx * PS - PH.w / 2) * scale, cys + (cy * PS - PH.h / 2) * scale];
};

function phoneFrame(p, { color = C.ink, glow = null, scale = 1 } = {}) {
  const cx = p.x + PH.w / 2, cy = p.y + PH.h / 2;
  const g = glow ? `<rect x="-18" y="-18" width="${PH.w + 36}" height="${PH.h + 36}" rx="70" fill="none" stroke="${glow}" stroke-width="10"/>` : "";
  return `<g transform="translate(${cx} ${cy}) scale(${scale}) translate(${-PH.w / 2} ${-PH.h / 2})">${g}
    <rect x="-12" y="-12" width="${PH.w + 24}" height="${PH.h + 24}" rx="62" fill="none" stroke="${color}" stroke-width="16"/>
    <rect x="${PH.w / 2 - 60}" y="-4" width="120" height="22" rx="11" fill="${color}"/></g>`;
}
function phoneShadow(p, scale = 1) {
  const cx = p.x + PH.w / 2, cy = p.y + PH.h / 2;
  return `<g transform="translate(${cx} ${cy}) scale(${scale}) translate(${-PH.w / 2} ${-PH.h / 2})"><rect x="-12" y="-12" width="${PH.w + 24}" height="${PH.h + 24}" rx="62" fill="${C.ink}" filter="url(#shadow)"/></g>`;
}
function browserFrame(x, y, w, h, url) {
  return `<g filter="url(#shadow)"><rect x="${x}" y="${y - 52}" width="${w}" height="${h + 52}" rx="22" fill="#fff"/></g>
    <rect x="${x}" y="${y - 52}" width="${w}" height="52" rx="22" fill="#EEE7DA"/><rect x="${x}" y="${y - 20}" width="${w}" height="20" fill="#EEE7DA"/>
    <circle cx="${x + 30}" cy="${y - 26}" r="8" fill="#FF6B6B"/><circle cx="${x + 56}" cy="${y - 26}" r="8" fill="${C.yellow}"/><circle cx="${x + 82}" cy="${y - 26}" r="8" fill="${C.green}"/>
    <rect x="${x + 120}" y="${y - 40}" width="${w - 240}" height="28" rx="14" fill="#fff"/>
    ${text(x + w / 2, y - 19, url, { size: 18, family: "Nunito", weight: 700, fill: "#6B6380" })}`;
}

// a rounded label with a thin leader line drawing toward (tx, ty)
function callout(tx, ty, lx, ly, label, p, { color = C.ink, bg = "#fff", size = 28 } = {}) {
  if (p <= 0) return "";
  const w = label.length * size * 0.55 + 44, h = size + 26;
  const line = drawLine([[lx, ly], [tx, ty]], prog(p, 0, 0.6), `stroke="${color}" stroke-width="3.5" stroke-linecap="round"`);
  const show = prog(p, 0.35, 0.8);
  return `<g>${line}<circle cx="${tx}" cy="${ty}" r="${9 * prog(p, 0.5, 0.9)}" fill="${C.yellow}" stroke="${color}" stroke-width="3"/>
    <g opacity="${show}" transform="translate(${lx} ${ly + (1 - show) * 8})"><rect x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}" rx="${h / 2}" fill="${bg}" stroke="${color}" stroke-width="3"/>
    ${text(0, size * 0.36, label, { size, family: "Nunito", weight: 800, fill: color })}</g></g>`;
}
function chip(x, y, label, p, { bg = C.yellow, fg = C.ink, size = 26 } = {}) {
  if (p <= 0) return "";
  const w = label.length * size * 0.55 + 40, h = size + 22, s = 0.85 + 0.15 * easeOut(p);
  return `<g opacity="${clamp(p * 2)}" transform="translate(${x} ${y}) scale(${s})"><rect x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}" rx="${h / 2}" fill="${bg}" stroke="${C.ink}" stroke-width="3"/>
    ${text(0, size * 0.36, label, { size, family: "Nunito", weight: 800, fill: fg })}</g>`;
}
function tag(x, y, label, { bg = "#FFF3C4", anchor = "start" } = {}) {
  const w = label.length * 11 + 30;
  const x0 = anchor === "start" ? x : x - w;
  return `<g><rect x="${x0}" y="${y - 22}" width="${w}" height="34" rx="17" fill="${bg}" stroke="${C.ink}" stroke-width="2" opacity=".95"/>
    ${text(x0 + w / 2, y + 2, label, { size: 19, family: "Nunito", weight: 800 })}</g>`;
}
function softBg(colorTop = "#EAF4FF", colorBottom = C.cream) {
  return `<defs><linearGradient id="bgg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${colorTop}"/><stop offset="1" stop-color="${colorBottom}"/></linearGradient></defs>
    <rect width="1920" height="1080" fill="url(#bgg)"/>`;
}
function bigTitle(x, y, str, p, size = 64, anchor = "start") {
  return `<g opacity="${p}" transform="translate(0 ${(1 - p) * 14})">${text(x, y, str, { size, anchor })}</g>`;
}

// ---------------- scenes ----------------
const T = []; // { id, dur, draw }

// 1 · cold open (scenes.js)
T.push({ id: "s1", dur: 8, draw: (t) => ({ bg: SCENES.s1.draw(t) }) });

// 2 · the problem: a staged group chat (made-up names), a calendar flip, the orange mascot on a sofa
T.push({ id: "s2", dur: 8, draw(t) {
  let s = softBg("#F3ECFF", C.cream);
  const grey = prog(t, 5.0, 6.0);
  const px = 560, py = 110, pw = 520, ph = 820;
  s += `<g filter="url(#shadow)"><rect x="${px}" y="${py}" width="${pw}" height="${ph}" rx="56" fill="#fff"/></g>
    <rect x="${px}" y="${py}" width="${pw}" height="${ph}" rx="56" fill="none" stroke="${C.ink}" stroke-width="12"/>
    <rect x="${px + 20}" y="${py + 30}" width="${pw - 40}" height="80" rx="24" fill="#F4F0FA"/>
    ${text(px + pw / 2, py + 82, "Weekend crew 🌤", { size: 32, family: "Nunito", weight: 800 })}`;
  const msgs = [
    { at: 0.3, who: "Sam", txt: "we should hang out sometime", me: false },
    { at: 1.2, who: "Jo", txt: "yes!!", me: false },
    { at: 2.0, who: "Riley", txt: "let's plan it", me: true },
  ];
  msgs.forEach((m, i) => {
    const p = prog(t, m.at, m.at + 0.35);
    if (p <= 0) return;
    const w = m.txt.length * 17 + 50, y = py + 190 + i * 120;
    const x = m.me ? px + pw - 40 - w : px + 40;
    s += `<g opacity="${p}" transform="translate(${x} ${y + (1 - p) * 16})">
      ${m.me ? "" : text(10, -14, m.who, { size: 20, family: "Nunito", weight: 700, anchor: "start", fill: "#8A82A0" })}
      <rect width="${w}" height="64" rx="32" fill="${m.me ? C.blue : "#EFE9F7"}"/>
      ${text(w / 2, 42, m.txt, { size: 28, family: "Nunito", weight: 700, fill: m.me ? "#fff" : C.ink })}</g>`;
  });
  // typing dots that fade
  const dp = prog(t, 2.8, 3.1) * (1 - prog(t, 4.0, 4.6));
  if (dp > 0) s += `<g opacity="${dp}" transform="translate(${px + 40} ${py + 560})"><rect width="110" height="56" rx="28" fill="#EFE9F7"/>
    ${[0, 1, 2].map((k) => `<circle cx="${30 + k * 25}" cy="${28 - Math.max(0, Math.sin((t * 6) - k)) * 5}" r="7" fill="#8A82A0"/>`).join("")}</g>`;
  if (grey > 0) s += `<rect x="${px}" y="${py}" width="${pw}" height="${ph}" rx="56" fill="#F1EEF6" opacity="${grey * 0.7}"/>`;
  // calendar flip: "3 weeks later…"
  const cp = prog(t, 4.2, 4.8);
  if (cp > 0) {
    const flip = Math.min(3, Math.floor(prog(t, 4.6, 5.6, (x) => x) * 4));
    s += `<g opacity="${cp}" transform="translate(1180 200)"><g filter="url(#shadow)"><rect width="280" height="300" rx="30" fill="#fff"/></g>
      <rect width="280" height="80" rx="30" fill="${C.orange}"/><rect y="50" width="280" height="30" fill="${C.orange}"/>
      ${text(140, 58, "WEEK", { size: 30, fill: "#fff" })}${text(140, 220, String(1 + flip), { size: 130 })}</g>
      <g opacity="${prog(t, 5.6, 6.0)}">${text(1320, 580, "3 weeks later…", { size: 46 })}</g>`;
  }
  // inset: the orange mascot on a sofa under a blanket, looking at its phone
  const ip = prog(t, 5.6, 6.3);
  if (ip > 0) {
    s += `<g opacity="${ip}" transform="translate(240 ${640 + (1 - ip) * 20})">
      <g filter="url(#shadow)"><rect x="-190" y="-170" width="380" height="330" rx="40" fill="#FFF6EA"/></g>
      <rect x="-150" y="10" width="300" height="90" rx="30" fill="#B07A9E" stroke="${C.ink}" stroke-width="4"/>
      <rect x="-165" y="-40" width="50" height="140" rx="22" fill="#B07A9E" stroke="${C.ink}" stroke-width="4"/>
      <rect x="115" y="-40" width="50" height="140" rx="22" fill="#B07A9E" stroke="${C.ink}" stroke-width="4"/>
      ${mascotB({ x: 0, y: -10, s: 0.95, expr: "sleepy", feet: false })}
      <path d="M-120 20 q120 -40 240 0 v60 h-240 z" fill="#8FB6E8" stroke="${C.ink}" stroke-width="4"/>
      <rect x="18" y="0" width="34" height="56" rx="8" fill="${C.ink}" transform="rotate(-12 35 28)"/>
      <rect x="22" y="5" width="26" height="42" rx="5" fill="#BFE3FF" transform="rotate(-12 35 28)"/></g>`;
  }
  return { bg: s };
}});

// 3 · what it is: logo build, route wipe, the home page in a browser frame (A1)
T.push({ id: "s3", dur: 12, draw(t) {
  if (t < 4.2) {
    let s = `<rect width="1920" height="1080" fill="${C.cream}"/>`;
    const a = prog(t, 0.1, 1.0), b = prog(t, 0.3, 1.2);
    s += mascotA({ x: lerp(-200, 820, a), y: 470, s: 1.1, bounce: a < 1 ? walkBounce(t, 12) : 0 });
    s += mascotB({ x: lerp(2120, 1000, b), y: 474, s: 1.05, bounce: b < 1 ? walkBounce(t + .2, 12) : 0 });
    const typed = "StrollCall".slice(0, Math.floor(prog(t, 1.3, 2.4, (x) => x) * 10));
    s += text(960, 720, typed, { size: 140 });
    return { bg: s };
  }
  const tt = t - 4.2; // A1 from clip 0.8 ->
  const clipT = 0.8 + tt;
  const push = 1 + 0.05 * prog(tt, 0, 7.8, easeInOut);
  const bx = 210, by = 150, bw = 1500, bh = 844;
  let fg = "";
  const click = 5.82; // the "Plan my walk" click in the clip
  const gp = prog(clipT, click - 1.6, click - 0.6) * (1 - prog(clipT, click + 0.3, click + 0.9));
  if (gp > 0) fg += `<ellipse cx="960" cy="${by + bh * 0.66}" rx="${150 * push}" ry="${60 * push}" fill="none" stroke="${C.yellow}" stroke-width="14" opacity="${gp}"/>`;
  return {
    bg: `<rect width="1920" height="1080" fill="${C.cream}"/>` + browserFrame(bx, by, bw, bh, "strollcall.onrender.com"),
    videos: [{ clip: "a1", t: clipT, x: bx, y: by, w: bw, h: bh, r: 0, scale: push, oy: 0.35 }],
    fg,
  };
}});

// 4 · solo by voice: A2 (Speak -> transcript -> Glimmer label), then Find my walk -> route
T.push({ id: "s4", dur: 22, draw(t) {
  const ph = phoneAt(300, 70);
  // the chips come in at clip 11.6 and the page scrolls the "Read by" line into view by 14.0; the second part
  // starts just before "Find my walk" (26.19) and keeps the real wait for the plan
  const seg1 = t < 15;
  const clipT = seg1 ? 1.5 + t : 25.7 + (t - 15);
  const push = seg1 ? 1 + 0.04 * prog(t, 13.2, 14.6, easeInOut) : 1;
  let fg = phoneFrame(ph, { scale: push });
  // waveform beside the mic while speaking (clip 2.45 -> ~8.3)
  const speaking = clipT > 2.6 && clipT < 8.4;
  if (speaking) {
    const [mx, my] = cssToStage(ph, 80, 471, push);
    fg += `<g transform="translate(${ph.x + PH.w + 40} ${my})">${Array.from({ length: 14 }, (_, i) => {
      const h = 12 + 40 * Math.abs(Math.sin(t * 7 + i * 0.9)) * Math.abs(Math.sin(t * 2.3 + i));
      return `<rect x="${i * 16}" y="${-h / 2}" width="9" height="${h}" rx="4.5" fill="${C.yellow}" stroke="${C.ink}" stroke-width="2"/>`;
    }).join("")}</g>` + callout(mx + 30, my, ph.x + PH.w + 160, my - 90, "Speaking…", prog(clipT, 2.6, 3.4));
  }
  const tr = prog(clipT, 9.8, 10.4) * (1 - prog(clipT, 12.2, 12.6)) * (seg1 ? 1 : 0);
  if (tr > 0) { const [x, y] = cssToStage(ph, 340, 277, push); fg += callout(x, y, 1100, 300, "Muse Voice Transcribe", tr); }
  const gl = prog(clipT, 14.7, 15.3) * (seg1 ? 1 : 0);
  if (gl > 0) {
    const [x, y] = cssToStage(ph, 300, 356, push); // where the line settles after the page's scroll (clip 15.0)
    fg += callout(x, y, 1170, 560, "Read by Muse Glimmer: open weights, on Modal", gl, { color: C.ink, bg: "#E4F0FF" });
    const bp = prog(clipT, 15.3, 15.8);
    fg += chip(1170, 660, "0.55 s median · evaluation run 1", bp, { bg: C.yellow });
  }
  if (!seg1) {
    const [x, y] = cssToStage(ph, 330, 336);
    fg += callout(x, y, 1120, 470, "Find my walk", prog(t, 15.0, 15.5) * (1 - prog(t, 16.8, 17.2)));
    fg += chip(1120, 640, "real wait: about 3 s", prog(t, 16.0, 16.5) * (1 - prog(t, 18.4, 18.8)), { bg: "#fff" });
    const [rx, ry] = cssToStage(ph, 300, 230);
    fg += callout(rx, ry, 1150, 280, "a real route on our walking graph", prog(t, 20.4, 21.0));
  }
  return { bg: softBg() + phoneShadow(ph, push), videos: [{ clip: "a2", t: clipT, ...ph, r: 52, scale: push }], fg };
}});

// 5 · walking (A4, simulated location) and the buddy adding a coffee stop (A5)
T.push({ id: "s5", dur: 15, draw(t) {
  const ph = phoneAt(300, 70);
  const a4 = t < 6;
  const clipT = a4 ? 10.5 + t : 1.2 + (t - 6);
  let fg = phoneFrame(ph) + tag(ph.x + PH.w + 40, 120, "simulated location");
  if (a4) {
    const [tx, ty] = cssToStage(ph, 330, 40);
    fg += callout(tx, ty, 1180, 170, "next turn", prog(t, 0.6, 1.3));
    const [mx, my] = cssToStage(ph, 60, 790);
    fg += callout(mx + 40, my, 1180, 760, "minutes left", prog(t, 1.6, 2.3));
  } else {
    const tt = t - 6;
    // the tool chain builds while the buddy thinks (A5: hold 1.76-5.08, reply 8.95)
    const steps = [["Muse Spark", 4.3], ["add_stop", 5.4], ["planner", 6.4], ["real, open place", 7.6]];
    steps.forEach(([lab, at], i) => {
      const p = prog(clipT, at, at + 0.4);
      const y = 300 + i * 120;
      if (i) fg += drawLine([[1260, y - 120 + 30], [1260, y - 30]], prog(clipT, at - 0.3, at), `stroke="${C.ink}" stroke-width="4" stroke-linecap="round"`);
      fg += chip(1260, y, lab, p, { bg: i === 0 ? "#E4F0FF" : i === 3 ? "#D6F2DF" : "#fff", size: 30 });
    });
    const [ux, uy] = cssToStage(ph, 128, 623);
    fg += callout(ux, uy, 1060, 860, "Undo", prog(clipT, 9.6, 10.3));
    if (tt < 0.6) fg += tag(ph.x + PH.w + 40, 170, "hold to talk: “add a coffee stop”", { bg: "#fff" });
  }
  return { bg: softBg("#E9F7EE", C.cream) + phoneShadow(ph), videos: [{ clip: a4 ? "a4" : "a5", t: clipT, ...ph, r: 52 }], fg };
}});

// 6 · with a friend: A sends, B joins, the plan arrives on both
T.push({ id: "s6", dur: 20, draw(t) {
  const pa = phoneAt(330, 110), pb = phoneAt(1190, 110);
  const sA = 0.94, sB = 0.94;
  let bg = softBg("#FFF1E6", C.cream) + phoneShadow(pa, sA) + phoneShadow(pb, sB);
  bg += mascotA({ x: pa.x + PH.w / 2, y: 52, s: 0.42 }) + mascotB({ x: pb.x + PH.w / 2, y: 54, s: 0.42, expr: t > 6 ? "happy" : "sleepy" });
  const after = t >= 16.5;
  // A: "Invite a friend" -> the card (clip 26.45 at t 3.95), then A waits; B opens the link only after it arrives
  const aClip = after ? { clip: "a8a", t: t - 16.5 } : { clip: "a6", t: Math.min(22.5 + t, 31.7) };
  const bClip = after ? { clip: "a8b", t: t - 16.5 } : t < 6 ? null : { clip: "a7", t: Math.min(3.5 + (t - 6), 16.8) };
  const videos = [{ ...aClip, ...pa, r: 52, scale: sA }];
  if (bClip) videos.push({ ...bClip, ...pb, r: 52, scale: sB });
  else bg += `<g transform="translate(${pb.x + PH.w / 2} ${pb.y + PH.h / 2})"><rect x="${-PH.w / 2 * sB}" y="${-PH.h / 2 * sB}" width="${PH.w * sB}" height="${PH.h * sB}" rx="50" fill="#F4EEE6"/>
    ${text(0, 0, "your friend's phone", { size: 28, family: "Nunito", weight: 700, fill: "#8A82A0" })}</g>`;
  let fg = phoneFrame(pa, { color: C.blue, scale: sA }) + phoneFrame(pb, { color: C.orange, scale: sB });
  // the invite card flies from A to B like a paper plane
  const fly = prog(t, 4.3, 5.9, easeInOut);
  if (fly > 0 && fly < 1) {
    const x = lerp(pa.x + PH.w, pb.x, fly), y = 420 - Math.sin(fly * Math.PI) * 220;
    fg += `<g transform="translate(${x} ${y}) rotate(${-15 + fly * 30})"><path d="M-40 0 L40 -22 L10 26 Z" fill="#fff" stroke="${C.ink}" stroke-width="4" stroke-linejoin="round"/>
      <path d="M-40 0 L10 0 L10 26" fill="none" stroke="${C.ink}" stroke-width="3"/></g>`;
  }
  fg += chip(960, 300, "Illustration by Muse Image", prog(t, 3.9, 4.5) * (1 - prog(t, 9.5, 10)), { bg: "#FFF3C4" });
  fg += chip(960, 760, "one link · no app · no account", prog(t, 6.2, 6.8) * (1 - prog(t, 10.4, 10.8)), { bg: "#fff" });
  // B taps "I'm in": ripple (clip 13.43 -> scene 6 + 9.93)
  const rp = prog(t, 15.8, 16.45, (x) => x);
  if (rp > 0 && rp < 1) { const [x, y] = cssToStage(pb, 52, 382, sB); fg += `<circle cx="${x}" cy="${y}" r="${20 + rp * 60}" fill="none" stroke="${C.orange}" stroke-width="6" opacity="${1 - rp}"/>`; }
  if (t > 16.0 && t < 16.5) fg += chip(960, 540, "a few seconds later…", 1, { bg: "#fff" });
  fg += chip(960, 540, "a few seconds later: the plan on both phones", prog(t, 16.6, 17.2), { bg: "#D6F2DF" });
  return { bg, videos, fg };
}});

// 7 · the fair meeting point: A8 trade-off line first, then the data-driven animation (scenes.js)
T.push({ id: "s7", dur: 20, draw(t) {
  if (t < 4) {
    // B's plan page holds still from clip 11.4 to 14.2; the last 1.2 s hold that frame
    const ph = phoneAt(300, 70), clipT = Math.min(11.4 + t, 14.2);
    let fg = phoneFrame(ph);
    const [x1, y1] = cssToStage(ph, 330, 336), [x2, y2] = cssToStage(ph, 330, 412);
    fg += callout(x1, y1, 1150, 420, "Muse Spark balances both wishes", prog(t, 0.4, 1.1));
    fg += callout(x2, y2, 1150, 640, "Wishes read by Muse Glimmer", prog(t, 1.8, 2.5), { bg: "#E4F0FF" });
    return { bg: softBg("#FFF1E6", C.cream) + phoneShadow(ph), videos: [{ clip: "a8b", t: clipT, ...ph, r: 52 }], fg };
  }
  return { bg: SCENES.s7.draw(t - 4) };
}});

// 8 · under the hood: the real walking graph, the architecture, A3
T.push({ id: "s8", dur: 21, draw(t) {
  if (t < 7) {
    let s = `<rect width="1920" height="1080" fill="${C.ink}"/>`;
    const g = window.DATA.graph;
    const reveal = prog(t, 0.2, 4.2, easeInOut);
    const zoom = 1 + 1.6 * prog(t, 4.6, 6.8, easeInOut);
    const fx = lerp(960, g.focus[0], prog(t, 4.6, 6.8, easeInOut)), fy = lerp(540, g.focus[1], prog(t, 4.6, 6.8, easeInOut));
    s += `<g transform="translate(960 540) scale(${zoom}) translate(${-fx} ${-fy})"><image href="${g.png}" x="0" y="0" width="1920" height="1080" opacity="${reveal}"/>
      ${drawLine(g.route, prog(t, 3.8, 5.6), `stroke="${C.yellow}" stroke-width="${6 / zoom}" stroke-linecap="round" stroke-linejoin="round"`)}</g>`;
    s += `<g opacity="${prog(t, 1.0, 1.6)}">${text(120, 140, "Our walking graph of New York", { size: 54, anchor: "start", fill: "#fff" })}
      ${text(120, 200, `${g.nodes_total.toLocaleString("en-US")} nodes · built from OpenStreetMap · Manhattan shown`, { size: 30, family: "Nunito", weight: 700, anchor: "start", fill: "#CFE9D8" })}</g>`;
    s += text(1880, 1060, "© OpenStreetMap contributors (ODbL)", { size: 18, family: "Nunito", weight: 600, anchor: "end", fill: "#B9B2CC" });
    s += `<g opacity="${prog(t, 5.0, 5.6)}">${chip(1500, 900, "plans in 0.029 s (median)", 1, { bg: C.yellow })}</g>`;
    return { bg: s };
  }
  if (t < 15) {
    const tt = t - 7;
    let s = softBg("#EAF4FF", C.cream);
    const box = (x, y, w, h, title, sub, p, color = "#fff") => p <= 0 ? "" : `<g opacity="${p}" transform="translate(0 ${(1 - p) * 14})">
      <g filter="url(#shadow)"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="26" fill="${color}"/></g>
      <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="26" fill="none" stroke="${C.ink}" stroke-width="3"/>
      ${text(x + w / 2, y + 52, title, { size: 32 })}${text(x + w / 2, y + 92, sub, { size: 22, family: "Nunito", weight: 700, fill: "#6B6380" })}</g>`;
    const arrow = (x1, x2, y, p) => drawLine([[x1, y], [x2, y]], p, `stroke="${C.ink}" stroke-width="4" stroke-linecap="round"`)
      + (p >= 1 ? `<path d="M${x2 - 14} ${y - 10} L${x2} ${y} L${x2 - 14} ${y + 10}" fill="none" stroke="${C.ink}" stroke-width="4" stroke-linecap="round"/>` : "");
    s += box(90, 300, 300, 130, "Phone web app", "no install, no account", prog(tt, 0.1, 0.5));
    s += arrow(400, 500, 365, prog(tt, 0.5, 0.9));
    s += box(510, 300, 300, 130, "FastAPI", "Render", prog(tt, 0.8, 1.2));
    s += arrow(820, 920, 365, prog(tt, 1.2, 1.6));
    s += box(930, 300, 380, 130, "Planner", "on our walking graph", prog(tt, 1.5, 1.9), "#E9F7EE");
    const models = [["Muse Glimmer", "reads wishes (open weights, Modal)", "#E4F0FF"], ["Muse Spark", "negotiates, ranks, calls tools", "#fff"],
      ["Muse Image", "draws the invite", "#FFF3C4"], ["Muse Voice", "listens", "#FFE7D9"]];
    s += `<g opacity="${prog(tt, 2.0, 2.4)}">${text(1610, 250, "Meta models", { size: 40 })}</g>`;
    models.forEach(([n, j, c], i) => {
      const at = 2.4 + i * 1.1;
      s += box(1400, 290 + i * 160, 420, 130, n, j, prog(tt, at, at + 0.4), c);
    });
    const point = Math.min(3, Math.max(0, Math.floor((tt - 2.4) / 1.1)));
    s += mascotA({ x: 1270, y: 360 + point * 160 + 0 * Math.sin(tt * 3), s: 0.5, expr: "open", bounce: walkBounce(tt, 4) });
    s += drawLine([[1310, 355 + point * 160], [1390, 355 + point * 160]], prog(tt, 2.4, 2.8), `stroke="${C.blue}" stroke-width="6" stroke-linecap="round"`);
    s += drawLine([[1120, 440], [1120, 620], [1390, 620]], prog(tt, 3, 4), `stroke="${C.ink}" stroke-width="3" stroke-dasharray="8 8" opacity=".4"`);
    return { bg: s };
  }
  const tt = t - 15;
  const sweep = prog(tt, 1.6, 3.2, easeInOut);
  // the READY line in the terminal recording (desktop 1920x1080 recording placed full frame)
  // highlight sweep over the READY line (model, BF16, H200); the clip's own "sped up 20x" tag stays visible
  const fg = tt > 2.2 ? `<rect x="120" y="398" width="${1700 * prog(tt, 2.2, 3.6, easeInOut)}" height="62" fill="${C.yellow}" opacity=".32" rx="8"/>` : "";
  return { bg: `<rect width="1920" height="1080" fill="${C.cream}"/>`, videos: [{ clip: "a3", t: 10.5 + tt, x: 0, y: 0, w: 1920, h: 1080, r: 0, scale: 1 }], fg };
}});

// 9 · honest evaluation
T.push({ id: "s9", dur: 15, draw(t) {
  let s = softBg("#EEF6EF", C.cream);
  const stamp = prog(t, 0.2, 0.7);
  s += `<g opacity="${stamp}" transform="translate(960 150) rotate(-3) scale(${1.2 - 0.2 * stamp})">
    <rect x="-520" y="-48" width="1040" height="96" rx="20" fill="none" stroke="${C.green}" stroke-width="6"/>
    ${text(0, 16, "Pre-registered: cases committed before each run", { size: 42, fill: C.green })}</g>`;
  const card = (x, title, val, sub, p) => p <= 0 ? "" : `<g opacity="${p}" transform="translate(${x} ${300 + (1 - p) * 20})">
    <g filter="url(#shadow)"><rect width="520" height="300" rx="32" fill="#fff"/></g>
    ${text(260, 70, title, { size: 30, family: "Nunito", weight: 800, fill: "#6B6380" })}${val}${text(260, 268, sub, { size: 20, family: "Nunito", weight: 700, fill: "#8A82A0" })}</g>`;
  // 12 of 12 right outcomes (benchmarks/2026-10-31-local.md:13)
  const c1 = prog(t, 2.0, 3.2, (x) => x);
  s += card(110, "test pairs, right outcome", text(260, 190, `${Math.round(12 * c1)} / 12`, { size: 96, fill: C.green }), "benchmarks/2026-10-31-local.md", prog(t, 1.8, 2.2));
  // wishes read correctly: Muse Spark 10/10 vs keyword rules 7/10 (benchmarks/2026-10-28-ablation-wishes.md:16)
  const bp = prog(t, 5.0, 6.4);
  const bars = `<g transform="translate(60 120)">${text(0, 22, "Muse Spark", { size: 24, family: "Nunito", weight: 800, anchor: "start" })}
    <rect x="0" y="34" width="${360 * bp}" height="30" rx="15" fill="${C.blue}"/>${text(380 * 1, 58, `${Math.round(10 * bp)}/10`, { size: 26, family: "Nunito", weight: 800, anchor: "start" })}
    ${text(0, 104, "keyword rules", { size: 24, family: "Nunito", weight: 800, anchor: "start" })}
    <rect x="0" y="116" width="${252 * bp}" height="30" rx="15" fill="#B9B2CC"/>${text(270, 140, `${Math.round(7 * bp)}/10`, { size: 26, family: "Nunito", weight: 800, anchor: "start" })}</g>`;
  s += card(700, "wishes read correctly", bars, "benchmarks/2026-10-28-ablation-wishes.md", prog(t, 4.8, 5.2));
  // Glimmer vs Muse Spark median wish reading (benchmarks/2026-10-31-open-weights-run1.md:14)
  const lp = prog(t, 6.6, 7.6, (x) => x);
  s += card(1290, "reading a wish, median", `${text(260, 160, `${(0.55 * lp).toFixed(2)} s`, { size: 72, fill: C.blue })}${text(260, 218, `Muse Glimmer · Muse Spark ${(3.58 * lp).toFixed(2)} s`, { size: 24, family: "Nunito", weight: 800 })}`, "benchmarks/2026-10-31-open-weights-run1.md", prog(t, 6.4, 6.8));
  // honesty check (the reason is real, benchmarks/2026-10-30-rejections.md:15; the sentence is illustrative)
  const hp = prog(t, 9.6, 10.1);
  if (hp > 0) {
    const strike = prog(t, 10.6, 11.2);
    const repl = prog(t, 12.0, 12.5);
    s += `<g opacity="${hp}" transform="translate(360 700)"><g filter="url(#shadow)"><rect width="1200" height="230" rx="30" fill="#fff"/></g>
      ${text(60, 80, "“This street is quiet.”", { size: 44, family: "Nunito", weight: 800, anchor: "start" })}
      <line x1="56" y1="66" x2="${56 + 470 * strike}" y2="66" stroke="#E0484D" stroke-width="7" stroke-linecap="round"/>
      <g opacity="${strike}">${tag(600, 72, "rejected: unverifiable claim ‘quiet’ (not in our data)", { bg: "#FFE1E1" })}</g>
      <g opacity="${repl}">${text(60, 170, "“Quiet, as B asked.”", { size: 44, family: "Nunito", weight: 800, anchor: "start", fill: C.green })}</g>
      ${text(1170, 214, "illustration of a real rule · reason from benchmarks/2026-10-30-rejections.md", { size: 18, family: "Nunito", weight: 700, anchor: "end", fill: "#8A82A0" })}</g>`;
    s += mascotA({ x: 1700, y: 830, s: 0.7, expr: repl > 0.5 ? "happy" : "smile", bounce: repl > 0 && repl < 1 ? Math.sin(repl * Math.PI) * 14 : 0 });
  }
  // a glimpse of the real report on GitHub (A10), first 1.8 s
  const videos = [];
  if (t < 1.9) videos.push({ clip: "a10", t: 3 + t, x: 1310, y: 640, w: 520, h: 293, r: 18, opacity: 1 - prog(t, 1.5, 1.9) });
  return { bg: s, videos };
}});

// 10 · out in the city at golden hour (no data: music only)
T.push({ id: "s10", dur: 22, draw(t) {
  const shot = Math.min(3, Math.floor(t / 5.5)), tt = t - shot * 5.5;
  let s = `<rect width="1920" height="1080" fill="url(#gold)"/>` + cloud(300 + t * 8, 160, 1, 0.7) + cloud(1400 + t * 6, 120, 0.8, 0.6);
  const ground = 820;
  s += `<circle cx="1500" cy="300" r="110" fill="#FFE7A8" opacity=".9"/>`;
  s += `<rect x="0" y="${ground}" width="1920" height="260" fill="#E9D9BF"/><rect x="0" y="${ground + 80}" width="1920" height="200" fill="#C9B79E"/>`;
  if (shot === 0) { // past a park with a phone
    s += `<rect x="0" y="${ground - 260}" width="1920" height="260" fill="#9BD6A6"/>` + tree(200, ground, 1.2, 0) + tree(620, ground, 1.0, 2) + tree(1100, ground, 1.3, 1) + tree(1600, ground, 1.1, 0);
    s += `<path d="M0 ${ground - 60} H1920" stroke="#7E6A54" stroke-width="10" stroke-dasharray="4 26" stroke-linecap="round"/>`;
    const x = lerp(-100, 1100, tt / 5.5);
    s += mascotA({ x, y: ground + 10, s: 1.0, bounce: walkBounce(t, 10) }) + `<rect x="${x + 40}" y="${ground - 20}" width="34" height="56" rx="8" fill="${C.ink}" transform="rotate(10 ${x + 57} ${ground + 8})"/>`;
  } else if (shot === 1) { // arrive at a corner from opposite streets and wave
    s += brownstone(80, ground, 520, 560, "#D9926E") + brownstone(1320, ground, 520, 600, "#C97B5A");
    s += `<rect x="760" y="${ground - 40}" width="400" height="40" rx="10" fill="#fff" opacity=".6"/>`;
    const a = prog(tt, 0, 3.4, easeInOut), b = prog(tt, 0.3, 3.6, easeInOut);
    const wave = tt > 3.6 ? Math.sin(tt * 12) * 0.25 : 0;
    s += mascotA({ x: lerp(-100, 840, a), y: ground + 10, s: 1.0, bounce: a < 1 ? walkBounce(t, 10) : 0, expr: a >= 1 ? "open" : "smile" });
    s += mascotB({ x: lerp(2020, 1080, b), y: ground + 14, s: 0.95, bounce: b < 1 ? walkBounce(t + 0.3, 10) : 0 });
    if (tt > 3.6) s += `<g transform="rotate(${wave * 60} 900 ${ground - 60})"><ellipse cx="900" cy="${ground - 90}" rx="14" ry="22" fill="${C.blue}" stroke="${C.ink}" stroke-width="4"/></g>`;
  } else if (shot === 2) { // walking together
    s += tree(300, ground, 1.1, 1) + tree(900, ground, 1.0, 0) + tree(1500, ground, 1.2, 2);
    const x = lerp(200, 1200, tt / 5.5);
    s += mascotA({ x, y: ground + 10, s: 1.0, bounce: walkBounce(t, 10), expr: "open" }) + mascotB({ x: x + 150, y: ground + 14, s: 0.95, bounce: walkBounce(t + 0.25, 10) });
    s += `<path d="M${x - 300} ${ground + 50} H${x + 260}" stroke="${C.green}" stroke-width="12" stroke-linecap="round" opacity=".8"/>`;
  } else { // a cafe table with two cups
    s += `<rect x="560" y="${ground - 420}" width="800" height="420" rx="14" fill="#FBEBD3" stroke="${C.ink}" stroke-width="4"/>
      ${Array.from({ length: 8 }, (_, i) => `<path d="M${560 + i * 100} ${ground - 400} h100 v60 q-50 30 -100 0 z" fill="${i % 2 ? C.cream : C.yellow}" stroke="${C.ink}" stroke-width="3"/>`).join("")}
      <rect x="760" y="${ground - 90}" width="400" height="22" rx="10" fill="#8A5A3C" stroke="${C.ink}" stroke-width="3"/><rect x="950" y="${ground - 70}" width="20" height="80" fill="#8A5A3C"/>`;
    s += mascotA({ x: 700, y: ground - 60, s: 0.9, expr: "happy", feet: false }) + mascotB({ x: 1220, y: ground - 56, s: 0.88, feet: false });
    s += `<rect x="830" y="${ground - 130}" width="46" height="42" rx="8" fill="#fff" stroke="${C.ink}" stroke-width="3"/><rect x="1040" y="${ground - 130}" width="46" height="42" rx="8" fill="#fff" stroke="${C.ink}" stroke-width="3"/>
      ${[0, 1].map((k) => `<path d="M${853 + k * 210} ${ground - 150 - (tt * 20 % 20)} q8 -12 0 -24" fill="none" stroke="#fff" stroke-width="4" opacity=".8"/>`).join("")}`;
  }
  return { bg: s };
}});

// 11 · end card (scenes.js)
T.push({ id: "s11", dur: 10, draw: (t) => ({ bg: SCENES.s11.draw(t) }) });

// start times
let acc = 0;
for (const sc of T) { sc.start = acc; acc += sc.dur; }
const TOTAL = acc;

// green route-line wipe between scenes (signature transition)
const WIPES = ["s2", "s3", "s4", "s6", "s7", "s8", "s10"].map((id) => T.find((s) => s.id === id).start);
function wipe(t) {
  for (const w0 of WIPES) {
    const p = (t - (w0 - 0.35)) / 0.7;
    if (p < 0 || p > 1) continue;
    const pts = [[-200, 1180], [400, 760], [900, 860], [1400, 300], [2120, -100]];
    const head = clamp(p * 1.6), tail = clamp((p - 0.45) * 1.8);
    const L = polyLen(pts);
    return `<path d="${pathD(pts)}" fill="none" stroke="${C.green}" stroke-width="900" stroke-linecap="round" stroke-linejoin="round"
      stroke-dasharray="${L * (head - tail)} ${L * 2}" stroke-dashoffset="${-L * tail}"/>`;
  }
  return "";
}

// captions: VO lines split into short chunks, timed by characters within each line's real duration
const VO_AT = { vo_01a: 0.4, vo_01b: 8.3, vo_02: 16.3, vo_03: 34.5, vo_04: 50.3, vo_05: 65.5, vo_06: 85.4, vo_07: 105.4, vo_08: 126.3, vo_10: 164.6 };
function captionChunks(durations) {
  const out = [];
  for (const [k, at] of Object.entries(VO_AT)) {
    const v = durations[k]; if (!v) continue;
    const words = v.text.split(" "); const chunks = []; let cur = "";
    for (const w of words) { if ((cur + " " + w).trim().length > 46) { chunks.push(cur.trim()); cur = w; } else cur += " " + w; }
    if (cur.trim()) chunks.push(cur.trim());
    // pair chunks into captions of up to 2 lines
    const caps = []; for (let i = 0; i < chunks.length; i += 2) caps.push(chunks.slice(i, i + 2));
    const total = caps.reduce((n, c) => n + c.join(" ").length, 0); let t0 = at;
    for (const c of caps) { const d = v.seconds * c.join(" ").length / total; out.push({ start: t0, end: t0 + d, lines: c }); t0 += d; }
  }
  return out;
}
function captionSvg(t) {
  const c = (window.CAPS || []).find((x) => t >= x.start && t < x.end + 0.15);
  if (!c) return "";
  const w = Math.max(...c.lines.map((l) => l.length)) * 17 + 70, h = c.lines.length * 44 + 26;
  return `<g transform="translate(960 ${1050 - h / 2})"><rect x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}" rx="${Math.min(h / 2, 34)}" fill="${C.cream}" opacity=".94" stroke="${C.ink}" stroke-opacity=".15" stroke-width="2"/>
    ${c.lines.map((l, i) => text(0, -h / 2 + 44 + i * 44, l.replace(/&/g, "&amp;"), { size: 32, family: "Nunito", weight: 700 })).join("")}</g>`;
}
