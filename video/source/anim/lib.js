// Shared drawing helpers for the demo video's animated scenes (SVG strings, 1920x1080 stage).
// Brand: sky #3B7BEA (A, blue mascot), orange #F08A4B (B), grass #22A35A, yellow #FFD970, ink #2B2340, cream #FBF7EF.

const C = { blue: "#3B7BEA", orange: "#F08A4B", green: "#22A35A", yellow: "#FFD970", ink: "#2B2340", cream: "#FBF7EF",
  blush: "#FF9EB0", pink: "#FFB3C1", sky1: "#5EA8F2", sky2: "#BFE3FF" };

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const easeOut = (t) => 1 - Math.pow(1 - clamp(t), 3);
const easeIn = (t) => Math.pow(clamp(t), 3);
const easeInOut = (t) => (t = clamp(t), t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
// progress of t within [a, b], eased
const prog = (t, a, b, ease = easeOut) => ease(clamp((t - a) / (b - a)));

// ---- mascots ----
// A: the round blue one with the antenna (also the walking buddy). Drawn around (0,0), body radius ~52.
function mascotA({ x = 0, y = 0, s = 1, expr = "smile", blink = false, feet = true, look = 0, bounce = 0, flip = false, sx = 1, sy = 1, rot = 0 } = {}) {
  const eyeRy = blink ? 1.2 : 7.5;
  const eyes = expr === "happy"
    ? `<path d="M-24 -6 q8 -9 16 0 M8 -6 q8 -9 16 0" fill="none" stroke="${C.ink}" stroke-width="5" stroke-linecap="round"/>`
    : `<ellipse cx="${-15 + look}" cy="-4" rx="6" ry="${eyeRy}" fill="${C.ink}"/><ellipse cx="${15 + look}" cy="-4" rx="6" ry="${eyeRy}" fill="${C.ink}"/>
       ${blink ? "" : `<circle cx="${-13 + look}" cy="-7.5" r="2.4" fill="#fff"/><circle cx="${17 + look}" cy="-7.5" r="2.4" fill="#fff"/>`}`;
  const mouth = expr === "open" || expr === "happy"
    ? `<path d="M-12 12 q12 16 24 0 z" fill="${C.ink}"/><ellipse cx="0" cy="18" rx="6" ry="2.6" fill="#FF7A93"/>`
    : expr === "o" ? `<ellipse cx="0" cy="15" rx="5" ry="6" fill="${C.ink}"/>`
    : `<path d="M-10 12 q10 10 20 0" fill="none" stroke="${C.ink}" stroke-width="4.5" stroke-linecap="round"/>`;
  const f = feet ? `<ellipse cx="-18" cy="50" rx="13" ry="7" fill="#2E5FC0" stroke="${C.ink}" stroke-width="3.5"/>
    <ellipse cx="18" cy="50" rx="13" ry="7" fill="#2E5FC0" stroke="${C.ink}" stroke-width="3.5"/>` : "";
  return `<g transform="translate(${x} ${y - bounce}) rotate(${rot}) scale(${(flip ? -s : s) * sx} ${s * sy})">${f}
    <path d="M2 -48 q-4 -22 14 -30" fill="none" stroke="${C.ink}" stroke-width="5" stroke-linecap="round"/>
    <circle cx="17" cy="-80" r="8" fill="${C.pink}" stroke="${C.ink}" stroke-width="3.5"/>
    <ellipse cx="0" cy="0" rx="54" ry="50" fill="${C.blue}" stroke="${C.ink}" stroke-width="5"/>
    <ellipse cx="-22" cy="-24" rx="14" ry="8" fill="#fff" opacity=".28" transform="rotate(-30 -22 -24)"/>
    <ellipse cx="-31" cy="10" rx="9" ry="5.5" fill="${C.blush}" opacity=".85"/><ellipse cx="31" cy="10" rx="9" ry="5.5" fill="${C.blush}" opacity=".85"/>
    ${eyes}${mouth}</g>`;
}

// B: the orange one with ears. Same scale as A.
function mascotB({ x = 0, y = 0, s = 1, expr = "happy", blink = false, feet = true, bounce = 0, flip = false, sx = 1, sy = 1, rot = 0 } = {}) {
  const eyes = expr === "happy"
    ? `<path d="M-24 -4 q7 -9 14 0 M10 -4 q7 -9 14 0" fill="none" stroke="${C.ink}" stroke-width="5" stroke-linecap="round"/>`
    : `<ellipse cx="-15" cy="-4" rx="6" ry="${blink ? 1.2 : 7.5}" fill="${C.ink}"/><ellipse cx="15" cy="-4" rx="6" ry="${blink ? 1.2 : 7.5}" fill="${C.ink}"/>
       ${blink ? "" : `<circle cx="-13" cy="-7.5" r="2.4" fill="#fff"/><circle cx="17" cy="-7.5" r="2.4" fill="#fff"/>`}`;
  const mouth = expr === "sleepy" ? `<path d="M-6 14 h12" stroke="${C.ink}" stroke-width="4" stroke-linecap="round"/>`
    : `<path d="M-10 10 q10 14 20 0 z" fill="${C.ink}"/>`;
  const f = feet ? `<ellipse cx="-17" cy="46" rx="12" ry="7" fill="#C9672F" stroke="${C.ink}" stroke-width="3.5"/>
    <ellipse cx="17" cy="46" rx="12" ry="7" fill="#C9672F" stroke="${C.ink}" stroke-width="3.5"/>` : "";
  return `<g transform="translate(${x} ${y - bounce}) rotate(${rot}) scale(${(flip ? -s : s) * sx} ${s * sy})">${f}
    <path d="M-34 -30 l-12 -24 l26 8 z M34 -30 l12 -24 l-26 8 z" fill="${C.orange}" stroke="${C.ink}" stroke-width="5" stroke-linejoin="round"/>
    <ellipse cx="0" cy="0" rx="50" ry="46" fill="${C.orange}" stroke="${C.ink}" stroke-width="5"/>
    <ellipse cx="-20" cy="-22" rx="13" ry="7" fill="#fff" opacity=".25" transform="rotate(-30 -20 -22)"/>
    <ellipse cx="-30" cy="10" rx="9" ry="5.5" fill="${C.yellow}" opacity=".9"/><ellipse cx="30" cy="10" rx="9" ry="5.5" fill="${C.yellow}" opacity=".9"/>
    ${eyes}${mouth}</g>`;
}

// a small walking bounce: |sin| so feet "land"
const walkBounce = (t, h = 7, hz = 2.2) => Math.abs(Math.sin(t * Math.PI * hz)) * h;

// ---- scenery ----
function cloud(x, y, s = 1, o = 0.95) {
  return `<g transform="translate(${x} ${y}) scale(${s})" opacity="${o}" filter="url(#soft)">
    <ellipse cx="0" cy="0" rx="120" ry="48" fill="#fff"/><ellipse cx="-70" cy="10" rx="80" ry="38" fill="#fff"/>
    <ellipse cx="60" cy="-18" rx="78" ry="54" fill="#fff"/><ellipse cx="120" cy="12" rx="70" ry="34" fill="#fff"/></g>`;
}

function tree(x, y, s = 1, tone = 0) {
  const g = ["#2FB866", "#22A35A", "#4CC27A"][tone % 3];
  return `<g transform="translate(${x} ${y}) scale(${s})">
    <rect x="-7" y="-10" width="14" height="60" rx="6" fill="#8A5A3C"/>
    <circle cx="0" cy="-52" r="44" fill="${g}"/><circle cx="-30" cy="-30" r="30" fill="${g}"/><circle cx="30" cy="-28" r="32" fill="${g}"/>
    <circle cx="-12" cy="-66" r="16" fill="#fff" opacity=".18"/></g>`;
}

// a brownstone facade: x,y = bottom-left, w,h; windows grid; optional door
function brownstone(x, y, w, h, color, { door = false, windowsLit = [] } = {}) {
  let wins = "";
  const cols = 3, rows = Math.max(2, Math.floor((h - 120) / 90));
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    if (door && r === rows - 1 && c === 1) continue;
    const wx = x + 28 + c * ((w - 56) / cols) + 10, wy = y - h + 46 + r * 90;
    const ww = (w - 56) / cols - 20;
    wins += `<rect x="${wx}" y="${wy}" width="${ww}" height="58" rx="12" fill="#FFF3D6" stroke="${C.ink}" stroke-width="3"/>
      <path d="M${wx} ${wy + 29} h${ww} M${wx + ww / 2} ${wy} v58" stroke="${C.ink}" stroke-width="2" opacity=".35"/>`;
  }
  return `<g><rect x="${x}" y="${y - h}" width="${w}" height="${h}" rx="10" fill="${color}" stroke="${C.ink}" stroke-width="4"/>
    <rect x="${x - 8}" y="${y - h - 14}" width="${w + 16}" height="20" rx="8" fill="#7A3E2C" stroke="${C.ink}" stroke-width="4"/>${wins}</g>`;
}

// route geometry helpers
function pathD(pts) { return pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" "); }
function polyLen(pts) { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L; }
function pointAt(pts, f) {
  const total = polyLen(pts); let want = clamp(f) * total;
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (want <= d) { const k = d ? want / d : 0; return [lerp(pts[i - 1][0], pts[i][0], k), lerp(pts[i - 1][1], pts[i][1], k)]; }
    want -= d;
  }
  return pts[pts.length - 1];
}
// a polyline drawn up to fraction f (stroke-dasharray trick)
function drawLine(pts, f, attrs) {
  const L = polyLen(pts);
  return `<path d="${pathD(pts)}" fill="none" stroke-dasharray="${L} ${L}" stroke-dashoffset="${L * (1 - clamp(f))}" ${attrs}/>`;
}

const DEFS = `<defs>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="6"/></filter>
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#2B2340" flood-opacity=".18"/></filter>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4E9BF0"/><stop offset=".65" stop-color="#A9D7FF"/><stop offset="1" stop-color="#DDF0FF"/></linearGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F7B267"/><stop offset=".6" stop-color="#FFD9A0"/><stop offset="1" stop-color="#FFEBC9"/></linearGradient>
</defs>`;

function text(x, y, str, { size = 40, weight = 700, fill = C.ink, family = "Fredoka", anchor = "middle", opacity = 1, extra = "" } = {}) {
  return `<text x="${x}" y="${y}" font-family="${family}" font-weight="${weight}" font-size="${size}" fill="${fill}"
    text-anchor="${anchor}" opacity="${opacity}" style="font-variant-numeric: tabular-nums" ${extra}>${str}</text>`;
}

// ---- motion helpers (liveliness) ----
const easeOutBack = (t, k = 1.7) => { t = clamp(t); const c = k + 1; return 1 + c * Math.pow(t - 1, 3) + k * Math.pow(t - 1, 2); };
const springIn = (t, a, d = 0.45) => easeOutBack((t - a) / d);           // 0 -> 1 with a small overshoot (shapes only)
const pulse = (t, a, d = 0.9) => { const p = (t - a) / d; return p < 0 || p > 1 ? 0 : Math.sin(p * Math.PI); };
// a gentle idle float for devices and cards
const floatY = (t, amp = 5, period = 4.2, ph = 0) => amp * Math.sin((t / period + ph) * 2 * Math.PI);
const floatR = (t, amp = 0.35, period = 5.3, ph = 0) => amp * Math.sin((t / period + ph) * 2 * Math.PI);
// periodic blink: true for ~0.12 s every few seconds
const blinkAt = (t, every = 3.4, off = 0) => ((t + off) % every) < 0.12;
// squash & stretch for a hop of height h (returns {b, sx, sy})
function hop(t, h = 10, hz = 2.2) {
  const ph = (t * hz) % 1, b = Math.sin(ph * Math.PI) * h;
  const land = ph < 0.12 || ph > 0.92 ? 1 : 0;
  return { b, sx: land ? 1.06 : 0.97, sy: land ? 0.93 : 1.04 };
}
// drifting pastel shapes behind product shots, so the frame never sits still
function ambient(t, cols = ["#FFE7A8", "#CFE6FF", "#D6F2DF", "#FFD9C7"]) {
  const blobs = [[260, 220, 210, 0], [1650, 260, 240, 1], [1500, 860, 200, 2], [420, 880, 230, 3], [980, 120, 150, 1]];
  let s = "";
  blobs.forEach(([x, y, r, c], i) => {
    const dx = 30 * Math.sin(t / (6 + i) + i), dy = 22 * Math.cos(t / (7 + i) + i * 2);
    s += `<circle cx="${x + dx}" cy="${y + dy}" r="${r}" fill="${cols[c % cols.length]}" opacity=".55" filter="url(#soft)"/>`;
  });
  for (let i = 0; i < 14; i++) {  // tiny floating dots
    const x = (i * 263 + t * (8 + i % 5)) % 1960 - 20, y = 140 + (i * 157) % 820 + 10 * Math.sin(t + i);
    s += `<circle cx="${x}" cy="${y}" r="${3 + i % 3}" fill="${i % 2 ? C.yellow : "#BFE3C9"}" opacity=".7"/>`;
  }
  return s;
}
