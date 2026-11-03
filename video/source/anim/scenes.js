// The illustrated scenes. Each: { dur, draw(t) -> SVG markup for a 1920x1080 stage }. Beat times follow the
// voiceover's word timings (video/assets/vo_tts/words.json); see the comments at each beat.
// Data scenes read window.DATA (video/assets/data/fairness_example.json etc.).

const SCENES = {};

function birds(t, x0, y0) {
  return [0, 1, 2].map((i) => {
    const x = (x0 + t * 70 + i * 60) % 2100 - 90, y = y0 + i * 18 + 6 * Math.sin(t * 3 + i), f = 8 * Math.sin(t * 9 + i);
    return `<path d="M${x - 14} ${y - f * 0.4} q7 ${-6 - f * 0.3} 14 0 q7 ${-6 - f * 0.3} 14 0" fill="none" stroke="${C.ink}" stroke-width="3" stroke-linecap="round" opacity=".55"/>`;
  }).join("");
}
function swayTree(x, y, s, tone, t, ph = 0) {
  return `<g transform="rotate(${1.4 * Math.sin(t * 1.3 + ph)} ${x} ${y})">${tree(x, y, s, tone)}</g>`;
}

// ---- Scene 1: cold open. VO 1a at 0.5: "I'm Chris." 0.6 · "…want to go outside," 2.3-3.6 ·
// "but I don't know where to go." 3.9-5.3. Title at 0:03; the route draws as the answer from 5.4.
SCENES.s1 = {
  dur: 8,
  draw(t) {
    const W = 1920, H = 1080, ground = 820;
    let s = `<rect width="${W}" height="${H}" fill="url(#sky)"/>`;
    s += `<circle cx="1660" cy="150" r="${70 + 4 * Math.sin(t * 2)}" fill="#FFF3B8" opacity=".9"/><circle cx="1660" cy="150" r="110" fill="#FFF3B8" opacity=".25"/>`;
    s += cloud(260 + t * 14, 170, 1.1) + cloud(1220 + t * 9, 110, 0.9, 0.9) + cloud(1660 + t * 16, 320, 0.7, 0.85);
    s += birds(t, 200, 250);
    s += `<g fill="#9CC7F2" opacity=".75">${[[60, 380], [220, 300], [330, 420], [520, 340], [1240, 360], [1400, 280], [1560, 400], [1740, 320]]
      .map(([x, h]) => `<rect x="${x}" y="${ground - 40 - h}" width="150" height="${h}" rx="10"/>`).join("")}</g>`;
    s += brownstone(120, ground, 300, 470, "#C97B5A") + brownstone(420, ground, 300, 540, "#B86B4E", { door: true })
      + brownstone(720, ground, 290, 450, "#D28B66") + brownstone(1010, ground, 300, 500, "#C27455");
    s += `<rect x="1330" y="${ground - 330}" width="440" height="330" rx="12" fill="#FBEBD3" stroke="${C.ink}" stroke-width="4"/>
      <rect x="1370" y="${ground - 210}" width="200" height="150" rx="10" fill="#FFF7E6" stroke="${C.ink}" stroke-width="3"/>
      <rect x="1600" y="${ground - 230}" width="110" height="230" rx="10" fill="#8FB6E8" stroke="${C.ink}" stroke-width="3"/>
      ${Array.from({ length: 8 }, (_, i) => `<path d="M${1330 + i * 55} ${ground - 300} h55 v${46 + 3 * Math.sin(t * 2 + i)} q-27.5 22 -55 0 z" fill="${i % 2 ? C.cream : C.yellow}" stroke="${C.ink}" stroke-width="3"/>`).join("")}
      ${text(1550, ground - 316, "CAFE", { size: 34, fill: C.ink })}`;
    const doorX = 570, doorY = ground - 20;
    const open = prog(t, 1.9, 2.6);
    s += `<rect x="${doorX - 46}" y="${doorY - 150}" width="92" height="150" rx="40" fill="#5A2E22" stroke="${C.ink}" stroke-width="4"/>
      <rect x="${doorX - 46}" y="${doorY - 150}" width="${92 * (1 - open * 0.85)}" height="150" rx="40" fill="#7A3E2C" stroke="${C.ink}" stroke-width="4"/>
      <rect x="${doorX - 80}" y="${doorY}" width="160" height="22" rx="6" fill="#C9B9A6" stroke="${C.ink}" stroke-width="3"/>`;
    s += `<rect x="0" y="${ground}" width="${W}" height="70" fill="#EFE5D6"/><rect x="0" y="${ground + 70}" width="${W}" height="${H - ground - 70}" fill="#AAB4BE"/>
      <path d="M0 ${ground + 70} H${W}" stroke="${C.ink}" stroke-width="4"/>
      ${Array.from({ length: 9 }, (_, i) => `<rect x="${(i * 260 + 60 - t * 40) % 2200 - 140}" y="${ground + 150}" width="120" height="12" rx="6" fill="#fff" opacity=".8"/>`).join("")}`;
    s += swayTree(1230, ground + 4, 1.05, 0, t) + swayTree(60, ground + 4, 0.95, 1, t, 1) + swayTree(1840, ground + 4, 1, 2, t, 2);
    // the green route: the answer to "where to go", drawn along the sidewalk
    const route = [[doorX + 40, ground + 40], [900, ground + 40], [1250, ground + 40], [1480, ground + 40]];
    s += drawLine(route, prog(t, 5.4, 7.6, easeInOut), `stroke="${C.green}" stroke-width="16" stroke-linecap="round" opacity=".95"`);
    if (t > 5.4) { const hp = pointAt(route, prog(t, 5.4, 7.6, easeInOut)); s += `<circle cx="${hp[0]}" cy="${hp[1]}" r="${12 + 3 * Math.sin(t * 8)}" fill="${C.green}" stroke="#fff" stroke-width="5"/>`; }
    if (t < 2.4) {
      // at the window, looking out
      const peek = prog(t, 0.1, 0.8);
      s += `<g>${mascotA({ x: 570, y: ground - 540 + 46 + 90 + 70 - peek * 30, s: 0.55, feet: false, look: 5 * Math.sin(t * 2.4), blink: blinkAt(t, 2.2) })}</g>`;
    } else {
      const step = springIn(t, 2.5, 0.5);
      const walk = prog(t, 5.6, 8, easeInOut);
      const h = walk > 0 && walk < 1 ? hop(t, 9) : { b: 0, sx: 1, sy: 1 };
      const confused = t > 3.9 && t < 5.4;
      const look = confused ? 7 * Math.sign(Math.sin((t - 3.9) * 4)) : 0;
      const x = doorX + walk * 420;
      s += mascotA({ x, y: doorY - 60 + (1 - clamp(step)) * 30 + 26, s: 0.9 + 0.1 * step, blink: blinkAt(t, 2.6, 0.7),
        expr: walk > 0 ? "open" : confused ? "o" : "smile", look, bounce: h.b, sx: h.sx, sy: h.sy });
      const q = springIn(t, 4.0, 0.4) * (1 - prog(t, 5.2, 5.5));
      if (q > 0.01) s += `<g transform="translate(${x + 70} ${doorY - 190}) scale(${q})"><circle r="38" fill="#fff" stroke="${C.ink}" stroke-width="4"/>
        <circle cx="-30" cy="44" r="8" fill="#fff" stroke="${C.ink}" stroke-width="3"/>${text(0, 16, "?", { size: 50 })}</g>`;
    }
    // "Step outside." at 0:03, word by word (fade + rise, no bounce)
    const w1 = prog(t, 2.9, 3.3), w2 = prog(t, 3.3, 3.7);
    s += `<g font-family="Fredoka" font-weight="700" font-size="150" fill="#fff" style="paint-order: stroke" stroke="${C.ink}" stroke-opacity=".12" stroke-width="10">
      <text x="905" y="${215 + (1 - w1) * 24}" opacity="${w1}" text-anchor="end">Step</text><text x="945" y="${215 + (1 - w2) * 24}" opacity="${w2}" text-anchor="start">outside.</text></g>`;
    return s;
  },
};

// ---- Scene 7 (animation part): the fair meeting point, from fairness_example.json (real streets, routes, minutes).
// Left runs first (A at 6.0 min, B at 10.8 min -> "4.8 min apart" when VO says "4.8"), right after it
// (9.9 / 9.3 min -> "0.6 min apart" with "within a minute"), then the dashed shared walk to Abingdon Square.
const S7 = { T0L: 1.0, T0R: 5.9, SEC: 0.52, dash: [11.4, 13.2], endLine: 14.0 };
SCENES.s7 = {
  dur: 16,
  draw(t) {
    const d = window.DATA.fair;
    const [S, Wb, N, Eb] = d.bbox;
    const panelW = 820, panelH = 640, top = 190;
    const panels = [{ x: 110, title: "Halfway on the map", T0: S7.T0L }, { x: 990, title: "Halfway by walking time", T0: S7.T0R }];
    const k = Math.cos(((S + N) / 2) * Math.PI / 180);
    const sx = panelW / ((Eb - Wb) * k), sy = panelH / (N - S), sc = Math.min(sx, sy) * 0.92;
    const proj = (px) => ([lat, lon]) => [px + panelW / 2 + ((lon - (Wb + Eb) / 2) * k) * sc, top + panelH / 2 - (lat - (S + N) / 2) * sc];
    let s = `<rect width="1920" height="1080" fill="${C.cream}"/>` + ambient(t, ["#FFF1D6", "#E8F1FF", "#E3F5E8", "#FFE9DF"]);
    s += `<g opacity="${prog(t, 0, 0.5)}">${text(960, 108, "Two friends, one meeting point", { size: 54 })}</g>`;
    panels.forEach((p, i) => {
      const P = proj(p.x);
      const legs = i === 0 ? d.midpoint : d.meeting;
      const minA = legs.a_min, minB = legs.b_min;
      const aPts = legs.a_route.map(P), bPts = legs.b_route.map(P);
      const ta = clamp((t - p.T0) / (minA * S7.SEC)), tb = clamp((t - p.T0) / (minB * S7.SEC));
      const shown = springIn(t, 0.15 + i * 0.2, 0.55), op = clamp(shown);
      const cxp = p.x + panelW / 2, cyp = top + panelH / 2;
      const focus = i === 0 ? 1 - 0.04 * prog(t, S7.T0R - 0.4, S7.T0R) : 1 + 0.03 * prog(t, S7.T0R - 0.4, S7.T0R) * (1 - prog(t, S7.endLine, S7.endLine + 0.6));
      s += `<g opacity="${op}" transform="translate(${cxp} ${cyp + floatY(t, 3, 5, i * 0.3)}) scale(${(0.92 + 0.08 * shown) * focus}) translate(${-cxp} ${-cyp})">
        <rect x="${p.x}" y="${top}" width="${panelW}" height="${panelH}" rx="34" fill="#F3EDE2" stroke="${C.ink}" stroke-opacity=".12" stroke-width="3" filter="url(#shadow)"/>
        <clipPath id="clip${i}"><rect x="${p.x}" y="${top}" width="${panelW}" height="${panelH}" rx="34"/></clipPath>
        <g clip-path="url(#clip${i})">
          <path d="${d.streets.map((seg) => pathD(seg.map(P))).join(" ")}" fill="none" stroke="#D9CDBA" stroke-width="5" stroke-linecap="round"/>
          ${i === 1 ? `<circle cx="${P([d.destination.lat, d.destination.lon])[0]}" cy="${P([d.destination.lat, d.destination.lon])[1]}" r="34" fill="#BFE6C9"/>` : ""}
        </g>
        ${text(p.x + 40, top - 22, p.title, { size: 40, anchor: "start" })}
        ${drawLine(aPts, ta, `stroke="${C.blue}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"`)}
        ${drawLine(bPts, tb, `stroke="${C.orange}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"`)}`;
      const end = aPts[aPts.length - 1];
      s += `<circle cx="${end[0]}" cy="${end[1]}" r="${14 + 3 * pulse(t, p.T0 + Math.max(minA, minB) * S7.SEC, 0.6)}" fill="${i ? C.green : "#fff"}" stroke="${C.ink}" stroke-width="5"/>`;
      const pa = pointAt(aPts, ta), pb = pointAt(bPts, tb);
      const waitingA = ta >= 1 && tb < 1;
      const ha = ta > 0 && ta < 1 ? hop(t, 6) : { b: waitingA ? Math.abs(Math.sin(t * 10)) * 5 : 0, sx: 1, sy: 1 };
      const hb = tb > 0 && tb < 1 ? hop(t + 0.2, 6) : { b: 0, sx: 1, sy: 1 };
      const both = ta >= 1 && tb >= 1;
      s += mascotA({ x: pa[0] - (ta >= 1 ? 26 : 0), y: pa[1] - 40, s: 0.42, bounce: ha.b, sx: ha.sx, sy: ha.sy,
        expr: both && i ? "happy" : waitingA ? "o" : "smile", blink: blinkAt(t, 2.8) });
      s += mascotB({ x: pb[0] + (tb >= 1 ? 26 : 0), y: pb[1] - 38, s: 0.42, bounce: hb.b, sx: hb.sx, sy: hb.sy, expr: "happy" });
      if (waitingA && i === 0) s += `<g transform="translate(${pa[0] - 70} ${pa[1] - 92})" opacity="${prog(t, p.T0 + minA * S7.SEC, p.T0 + minA * S7.SEC + 0.3)}">
        <circle r="18" fill="#fff" stroke="${C.ink}" stroke-width="3"/><path d="M0 -10 V0 L${7 * Math.cos(t * 4)} ${7 * Math.sin(t * 4)}" stroke="${C.ink}" stroke-width="3" fill="none" stroke-linecap="round"/></g>`;
      // timers
      const ma = Math.min(minA, Math.max(0, (t - p.T0) / S7.SEC)), mb = Math.min(minB, Math.max(0, (t - p.T0) / S7.SEC));
      const ty = top + panelH + 64;
      s += `<g opacity="${op}">
        <rect x="${p.x + 30}" y="${ty - 40}" width="220" height="58" rx="29" fill="#fff" stroke="${C.blue}" stroke-width="4"/>
        ${text(p.x + 140, ty, `You · ${ma.toFixed(1)} min`, { size: 30, family: "Nunito", weight: 800, fill: C.blue })}
        <rect x="${p.x + 270}" y="${ty - 40}" width="250" height="58" rx="29" fill="#fff" stroke="${C.orange}" stroke-width="4"/>
        ${text(p.x + 395, ty, `Friend · ${mb.toFixed(1)} min`, { size: 30, family: "Nunito", weight: 800, fill: "#C9672F" })}</g>`;
      if (both) {
        const gap = Math.abs(minA - minB), tDone = p.T0 + Math.max(minA, minB) * S7.SEC;
        const g = springIn(t, tDone, 0.45), good = gap < 1;
        s += `<g opacity="${clamp(g)}" transform="translate(${p.x + 665} ${ty - 11}) scale(${0.8 + 0.2 * g})">
          <rect x="${-125}" y="-29" width="250" height="58" rx="29" fill="${good ? "#D6F2DF" : "#FFE1CF"}"/>
          ${text(0, 11, `${gap.toFixed(1)} min apart`, { size: 30, family: "Nunito", weight: 800, fill: good ? "#17733F" : "#B5471B" })}</g>`;
        if (good) {
          const sp = prog(t, tDone, tDone + 0.8);
          s += `<g transform="translate(${end[0]} ${end[1] - 90})" opacity="${1 - Math.max(0, sp - 0.7) / 0.3}">
            ${[0, 60, 120, 180, 240, 300].map((a) => `<path d="M0 0 l${Math.cos(a * Math.PI / 180) * 38 * sp} ${Math.sin(a * Math.PI / 180) * 38 * sp}" stroke="${C.yellow}" stroke-width="7" stroke-linecap="round"/>`).join("")}</g>`;
          const dd = prog(t, S7.dash[0], S7.dash[1], easeInOut);
          const dPts = d.destination.route.map(P), len = polyLen(dPts);
          s += `<mask id="reveal" maskUnits="userSpaceOnUse" x="0" y="0" width="1920" height="1080"><path d="${pathD(dPts)}" fill="none"
              stroke="#fff" stroke-width="18" stroke-dasharray="${len} ${len}" stroke-dashoffset="${len * (1 - dd)}"/></mask>
            <path d="${pathD(dPts)}" mask="url(#reveal)" fill="none" stroke="${C.ink}" stroke-width="7" stroke-dasharray="14 12" stroke-linecap="round" opacity=".8"/>`;
          if (dd > 0 && dd < 1) {  // both walk on together along the dashed line
            const q = pointAt(dPts, dd), h = hop(t, 5);
            s += mascotA({ x: q[0] - 18, y: q[1] - 40, s: 0.36, bounce: h.b, sx: h.sx, sy: h.sy, expr: "open" }) + mascotB({ x: q[0] + 18, y: q[1] - 38, s: 0.36, bounce: hop(t + 0.2, 5).b });
          }
          const de = dPts[dPts.length - 1], dl = springIn(t, S7.dash[1] - 0.2, 0.45);
          s += `<g opacity="${clamp(dl)}" transform="translate(${de[0]} ${de[1] - 64}) scale(${0.85 + 0.15 * dl})"><rect x="-150" y="-28" width="300" height="56" rx="28" fill="#fff" stroke="${C.ink}" stroke-width="3"/>
            ${text(0, 10, `${d.destination.name}`, { size: 28, family: "Nunito", weight: 800 })}</g>`;
          s += `<g opacity="${clamp(dl)}">${text(p.x + 400, ty + 64, `Together · ${d.destination.shared_min.toFixed(1)} min to ${d.destination.name}`, { size: 28, family: "Nunito", weight: 700, fill: C.ink })}</g>`;
          s += `<g opacity="${clamp(g)}"><rect x="${end[0] - 120}" y="${end[1] + 24}" width="240" height="48" rx="24" fill="#fff" stroke="${C.green}" stroke-width="3"/>
            ${text(end[0], end[1] + 57, d.meeting.name, { size: 26, family: "Nunito", weight: 800, fill: "#17733F" })}</g>`;
        } else {
          s += `<g opacity="${clamp(g)}"><circle cx="${end[0]}" cy="${end[1]}" r="${22 + 4 * Math.sin(t * 5)}" fill="none" stroke="${C.orange}" stroke-width="4" stroke-dasharray="6 6"/></g>`;
        }
      }
      s += `</g>`;
    });
    const endLine = prog(t, S7.endLine, S7.endLine + 0.6);
    s += `<g opacity="${endLine}" transform="translate(0 ${(1 - endLine) * 14})">${text(960, 1040, "Halfway by walking time, not by distance.", { size: 46 })}</g>`;
    s += text(1880, 40, "Route data © OpenStreetMap contributors · measured on our walking graph (fairness_example.json)", { size: 18, family: "Nunito", weight: 600, anchor: "end", fill: "#6B6380" });
    return s;
  },
};

// ---- Scene 11: end card. VO 10 at 1.5: "StrollCall." 1.64 · "Less planning." 2.7 · "More walking." 3.86.
SCENES.s11 = {
  dur: 9.5,
  draw(t) {
    let s = `<rect width="1920" height="1080" fill="${C.cream}"/>` + ambient(t * 0.6, ["#FFF1D6", "#E8F1FF", "#E3F5E8", "#FFE9DF"]);
    const meet = prog(t, 0.1, 1.5, easeInOut);
    const ax = lerp(-150, 870, meet), bx = lerp(2070, 1050, meet);
    const walking = meet > 0 && meet < 1;
    const ha = walking ? hop(t, 11) : { b: Math.max(0, Math.sin((t - 1.5) * 9)) * 14 * Math.max(0, 1 - (t - 1.5) / 0.7), sx: 1, sy: 1 };
    const hb = walking ? hop(t + 0.25, 11) : ha;
    const glow = springIn(t, 1.4, 0.6);
    s += `<circle cx="960" cy="400" r="${190 * clamp(glow) + 6 * Math.sin(t * 2)}" fill="${C.yellow}" opacity=".55"/>`;
    s += mascotA({ x: ax, y: 400 + floatY(t, 3, 3), s: 1.25, bounce: ha.b, sx: ha.sx, sy: ha.sy, expr: meet >= 1 ? "open" : "smile", blink: blinkAt(t, 3.1, 0.4) });
    s += mascotB({ x: bx, y: 404 + floatY(t, 3, 3, 0.5), s: 1.2, bounce: hb.b, sx: hb.sx, sy: hb.sy, expr: "happy" });
    const heart = springIn(t, 1.5, 0.5);
    s += `<path transform="translate(960 ${230 + floatY(t, 4, 2.2)}) scale(${1.6 * clamp(heart, 0, 1.3)})" d="M0 10 c-6 -12 -22 -6 -16 6 l16 16 l16 -16 c6 -12 -10 -18 -16 -6 z" fill="${C.yellow}" stroke="${C.ink}" stroke-width="3"/>`;
    const name = prog(t, 1.6, 2.1);
    s += `<g opacity="${name}" transform="translate(0 ${(1 - name) * 16})">${text(960, 660, "StrollCall", { size: 150 })}</g>`;
    const t1 = prog(t, 2.65, 3.1), t2 = prog(t, 3.8, 4.25);
    s += `<g font-family="Nunito" font-weight="800" font-size="54" fill="${C.green}">
      <text x="955" y="${740 + (1 - t1) * 12}" text-anchor="end" opacity="${t1}">Less planning.</text>
      <text x="975" y="${740 + (1 - t2) * 12}" text-anchor="start" opacity="${t2}">More walking.</text></g>`;
    const links = prog(t, 4.6, 5.1), built = prog(t, 5.1, 5.6);
    s += `<g opacity="${links}">${text(960, 840, "strollcall.onrender.com", { size: 40, family: "Nunito", weight: 800, fill: C.blue })}
      ${text(960, 892, "github.com/zh315-bit/strollcall", { size: 34, family: "Nunito", weight: 700, fill: "#6B6380" })}</g>
      <g opacity="${built}">${text(960, 990, "Built with Muse Spark · Muse Glimmer (open weights) · Muse Image · Muse Voice", { size: 30, family: "Nunito", weight: 700 })}</g>`;
    const fade = prog(t, 8.7, 9.5, easeIn);
    if (fade > 0) s += `<rect width="1920" height="1080" fill="${C.cream}" opacity="${fade}"/>`;
    return s;
  },
};
