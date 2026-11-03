// The animated scenes. Each scene: { dur, draw(t) -> SVG markup for a 1920x1080 stage }.
// Data scenes read window.DATA (video/assets/data/fairness_example.json etc.), set by stage.html.

const SCENES = {};

// ---- Scene 1: cold open. A sunny street; the blue mascot at a window, then out of the door. ----
SCENES.s1 = {
  dur: 8,
  draw(t) {
    const W = 1920, H = 1080, ground = 820;
    const drift = t * 6;
    let s = `<rect width="${W}" height="${H}" fill="url(#sky)"/>`;
    s += cloud(260 + drift, 170, 1.1) + cloud(1320 + drift * 0.7, 120, 0.9, 0.9) + cloud(1700 + drift, 300, 0.7, 0.85);
    // far skyline, soft
    s += `<g fill="#9CC7F2" opacity=".75">${[[60, 380], [220, 300], [330, 420], [520, 340], [1240, 360], [1400, 280], [1560, 400], [1740, 320]]
      .map(([x, h]) => `<rect x="${x}" y="${ground - 40 - h}" width="150" height="${h}" rx="10"/>`).join("")}</g>`;
    // brownstones
    s += brownstone(120, ground, 300, 470, "#C97B5A") + brownstone(420, ground, 300, 540, "#B86B4E", { door: true })
      + brownstone(720, ground, 290, 450, "#D28B66") + brownstone(1010, ground, 300, 500, "#C27455");
    // cafe with awning, right
    s += `<rect x="1330" y="${ground - 330}" width="440" height="330" rx="12" fill="#FBEBD3" stroke="${C.ink}" stroke-width="4"/>
      <rect x="1370" y="${ground - 210}" width="200" height="150" rx="10" fill="#FFF7E6" stroke="${C.ink}" stroke-width="3"/>
      <rect x="1600" y="${ground - 230}" width="110" height="230" rx="10" fill="#8FB6E8" stroke="${C.ink}" stroke-width="3"/>
      ${Array.from({ length: 8 }, (_, i) => `<path d="M${1330 + i * 55} ${ground - 300} h55 v46 q-27.5 22 -55 0 z" fill="${i % 2 ? C.cream : C.yellow}" stroke="${C.ink}" stroke-width="3"/>`).join("")}
      ${text(1550, ground - 316, "CAFE", { size: 34, fill: C.ink })}`;
    // the door of the middle brownstone, stoop
    const doorX = 570, doorY = ground - 20;
    const open = prog(t, 2.2, 2.9);
    s += `<rect x="${doorX - 46}" y="${doorY - 150}" width="92" height="150" rx="40" fill="#5A2E22" stroke="${C.ink}" stroke-width="4"/>
      <rect x="${doorX - 46}" y="${doorY - 150}" width="${92 * (1 - open * 0.85)}" height="150" rx="40" fill="#7A3E2C" stroke="${C.ink}" stroke-width="4"/>
      <rect x="${doorX - 80}" y="${doorY}" width="160" height="22" rx="6" fill="#C9B9A6" stroke="${C.ink}" stroke-width="3"/>`;
    // sidewalk, street, trees
    s += `<rect x="0" y="${ground}" width="${W}" height="70" fill="#EFE5D6"/><rect x="0" y="${ground + 70}" width="${W}" height="${H - ground - 70}" fill="#AAB4BE"/>
      <path d="M0 ${ground + 70} H${W}" stroke="${C.ink}" stroke-width="4"/>
      ${Array.from({ length: 8 }, (_, i) => `<rect x="${i * 260 + 60}" y="${ground + 150}" width="120" height="12" rx="6" fill="#fff" opacity=".8"/>`).join("")}`;
    s += tree(1230, ground + 4, 1.05, 0) + tree(60, ground + 4, 0.95, 1) + tree(1840, ground + 4, 1, 2);
    // the mascot: in the upper window (0-2.2 s), then at the door, then out on the step blinking (3.2-3.6)
    if (t < 2.2) {
      const peek = prog(t, 0.3, 1.2);
      s += `<clipPath id="win"><rect x="${648}" y="${ground - 540 + 46 + 90}" width="${48}" height="58" rx="12"/></clipPath>`;
      s += `<g>${mascotA({ x: 570, y: ground - 540 + 46 + 90 + 70 - peek * 30, s: 0.55, feet: false, look: 4 * Math.sin(t * 2) })}</g>`;
    } else {
      const step = prog(t, 2.6, 3.4);
      const blink = t > 3.5 && t < 3.68 || t > 3.9 && t < 4.05;
      const walk = prog(t, 4.6, 8, easeInOut);
      const x = doorX + walk * 380;
      s += mascotA({ x, y: doorY - 60 + (1 - step) * 30 + 26, s: 0.9 + 0.1 * step, blink, expr: t > 4.1 ? "open" : "smile",
        bounce: walk > 0 && walk < 1 ? walkBounce(t) : 0 });
    }
    // the green route drawing along the sidewalk
    const route = [[doorX, ground + 40], [900, ground + 40], [1250, ground + 40], [1480, ground + 40]];
    s += drawLine(route, prog(t, 3.0, 7.6, easeInOut), `stroke="${C.green}" stroke-width="14" stroke-linecap="round" opacity=".95"`);
    // "Step outside." word by word
    const w1 = prog(t, 3.0, 3.45), w2 = prog(t, 3.45, 3.9);
    s += `<g font-family="Fredoka" font-weight="700" font-size="150" fill="#fff" text-anchor="middle" style="paint-order: stroke" stroke="${C.ink}" stroke-opacity=".12" stroke-width="10">
      <text x="905" y="${215 + (1 - w1) * 24}" opacity="${w1}" text-anchor="end">Step</text><text x="945" y="${215 + (1 - w2) * 24}" opacity="${w2}" text-anchor="start">outside.</text></g>`;
    return s;
  },
};

// ---- Scene 7: the fair meeting point, from fairness_example.json (real streets, routes and minutes). ----
SCENES.s7 = {
  dur: 13,
  draw(t) {
    const d = window.DATA.fair;
    const [S, Wb, N, Eb] = d.bbox;
    const panelW = 820, panelH = 640, top = 190;
    const panels = [{ x: 110, title: "Halfway on the map" }, { x: 990, title: "Halfway by walking time" }];
    const k = Math.cos(((S + N) / 2) * Math.PI / 180);
    const sx = panelW / ((Eb - Wb) * k), sy = panelH / (N - S), sc = Math.min(sx, sy) * 0.92;
    const proj = (px) => ([lat, lon]) => [px + panelW / 2 + ((lon - (Wb + Eb) / 2) * k) * sc, top + panelH / 2 - (lat - (S + N) / 2) * sc];
    const SEC_PER_MIN = 0.55; // animation seconds per walking minute; both mascots walk at the same speed
    const T0 = 1.6;           // walking starts
    let s = `<rect width="1920" height="1080" fill="${C.cream}"/>`;
    s += text(960, 108, "Two friends, one meeting point", { size: 54 });
    panels.forEach((p, i) => {
      const P = proj(p.x);
      const legs = i === 0 ? d.midpoint : d.meeting;
      const minA = legs.a_min, minB = legs.b_min;
      const aPts = legs.a_route.map(P), bPts = legs.b_route.map(P);
      const ta = clamp((t - T0) / (minA * SEC_PER_MIN)), tb = clamp((t - T0) / (minB * SEC_PER_MIN));
      const shown = prog(t, 0.2 + i * 0.25, 0.9 + i * 0.25);
      s += `<g opacity="${shown}" transform="translate(0 ${(1 - shown) * 20})">
        <rect x="${p.x}" y="${top}" width="${panelW}" height="${panelH}" rx="34" fill="#F3EDE2" stroke="${C.ink}" stroke-opacity=".12" stroke-width="3" filter="url(#shadow)"/>
        <clipPath id="clip${i}"><rect x="${p.x}" y="${top}" width="${panelW}" height="${panelH}" rx="34"/></clipPath>
        <g clip-path="url(#clip${i})">
          <path d="${d.streets.map((seg) => pathD(seg.map(P))).join(" ")}" fill="none" stroke="#D9CDBA" stroke-width="5" stroke-linecap="round"/>
          ${i === 1 ? `<circle cx="${P([d.destination.lat, d.destination.lon])[0]}" cy="${P([d.destination.lat, d.destination.lon])[1]}" r="34" fill="#BFE6C9"/>` : ""}
        </g>
        ${text(p.x + 40, top - 22, p.title, { size: 40, anchor: "start" })}
        ${drawLine(aPts, ta, `stroke="${C.blue}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"`)}
        ${drawLine(bPts, tb, `stroke="${C.orange}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"`)}
      </g>`;
      if (shown < 0.05) return;
      const end = aPts[aPts.length - 1];
      s += `<circle cx="${end[0]}" cy="${end[1]}" r="14" fill="${i ? C.green : "#fff"}" stroke="${C.ink}" stroke-width="5"/>`;
      const pa = pointAt(aPts, ta), pb = pointAt(bPts, tb);
      const tap = ta >= 1 && tb < 1 ? Math.abs(Math.sin(t * 9)) * 6 : 0;
      s += mascotA({ x: pa[0] - (ta >= 1 ? 26 : 0), y: pa[1] - 40, s: 0.42, bounce: ta < 1 && ta > 0 ? walkBounce(t, 5) : tap, expr: ta >= 1 && tb >= 1 && i ? "happy" : "smile" });
      s += mascotB({ x: pb[0] + (tb >= 1 ? 26 : 0), y: pb[1] - 38, s: 0.42, bounce: tb < 1 && tb > 0 ? walkBounce(t + 0.2, 5) : 0, expr: "happy" });
      // timers
      const ma = Math.min(minA, Math.max(0, (t - T0) / SEC_PER_MIN)), mb = Math.min(minB, Math.max(0, (t - T0) / SEC_PER_MIN));
      const ty = top + panelH + 64;
      s += `<g opacity="${shown}">
        <rect x="${p.x + 30}" y="${ty - 40}" width="220" height="58" rx="29" fill="#fff" stroke="${C.blue}" stroke-width="4"/>
        ${text(p.x + 140, ty, `You · ${ma.toFixed(1)} min`, { size: 30, family: "Nunito", weight: 800, fill: C.blue })}
        <rect x="${p.x + 270}" y="${ty - 40}" width="250" height="58" rx="29" fill="#fff" stroke="${C.orange}" stroke-width="4"/>
        ${text(p.x + 395, ty, `Friend · ${mb.toFixed(1)} min`, { size: 30, family: "Nunito", weight: 800, fill: "#C9672F" })}</g>`;
      const done = ta >= 1 && tb >= 1;
      if (done) {
        const gap = Math.abs(minA - minB);
        const g = prog(t, T0 + Math.max(minA, minB) * SEC_PER_MIN, T0 + Math.max(minA, minB) * SEC_PER_MIN + 0.5);
        const good = gap < 1;
        s += `<g opacity="${g}" transform="translate(${p.x + 540} ${ty - 40})">
          <rect width="${good ? 250 : 260}" height="58" rx="29" fill="${good ? "#D6F2DF" : "#FFE1CF"}"/>
          ${text(good ? 125 : 130, 40, `${gap.toFixed(1)} min apart`, { size: 30, family: "Nunito", weight: 800, fill: good ? "#17733F" : "#B5471B" })}</g>`;
        if (good) {
          const sp = prog(t, T0 + minA * SEC_PER_MIN + 0.1, T0 + minA * SEC_PER_MIN + 0.9);
          s += `<g transform="translate(${end[0]} ${end[1] - 90})" opacity="${1 - Math.max(0, sp - 0.7) / 0.3}">
            ${[0, 60, 120, 180, 240, 300].map((a) => `<path d="M0 0 l${Math.cos(a * Math.PI / 180) * 34 * sp} ${Math.sin(a * Math.PI / 180) * 34 * sp}" stroke="${C.yellow}" stroke-width="7" stroke-linecap="round"/>`).join("")}</g>`;
          const dd = prog(t, T0 + 6.6, T0 + 8.8, easeInOut);
          const dPts = d.destination.route.map(P);
          // a dashed line, revealed along its length by a mask
          const len = polyLen(dPts);
          s += `<mask id="reveal" maskUnits="userSpaceOnUse" x="0" y="0" width="1920" height="1080"><path d="${pathD(dPts)}" fill="none"
              stroke="#fff" stroke-width="18" stroke-dasharray="${len} ${len}" stroke-dashoffset="${len * (1 - dd)}"/></mask>
            <path d="${pathD(dPts)}" mask="url(#reveal)" fill="none" stroke="${C.ink}" stroke-width="7" stroke-dasharray="14 12" stroke-linecap="round" opacity=".8"/>`;
          const de = dPts[dPts.length - 1], dl = prog(t, T0 + 8.4, T0 + 9);
          s += `<g opacity="${dl}"><rect x="${de[0] - 150}" y="${de[1] - 92}" width="300" height="56" rx="28" fill="#fff" stroke="${C.ink}" stroke-width="3"/>
            ${text(de[0], de[1] - 54, `${d.destination.name}`, { size: 28, family: "Nunito", weight: 800 })}</g>`;
          s += `<g opacity="${dl}">${text(p.x + 400, ty + 64, `Together · ${d.destination.shared_min.toFixed(1)} min to ${d.destination.name}`, { size: 28, family: "Nunito", weight: 700, fill: C.ink })}</g>`;
          s += `<g opacity="${g}"><rect x="${end[0] - 120}" y="${end[1] + 24}" width="240" height="48" rx="24" fill="#fff" stroke="${C.green}" stroke-width="3"/>
            ${text(end[0], end[1] + 57, d.meeting.name, { size: 26, family: "Nunito", weight: 800, fill: "#17733F" })}</g>`;
        } else {
          // bracket between the two arrival times
          s += `<g opacity="${g}"><circle cx="${end[0]}" cy="${end[1]}" r="20" fill="none" stroke="${C.orange}" stroke-width="4" stroke-dasharray="6 6"/></g>`;
        }
      }
    });
    const endLine = prog(t, 11.4, 12.2);
    s += `<g opacity="${endLine}">${text(960, 1040, "Halfway by walking time, not by distance.", { size: 46 })}</g>`;
    s += text(1880, 40, "Route data © OpenStreetMap contributors · measured on our walking graph (fairness_example.json)", { size: 18, family: "Nunito", weight: 600, anchor: "end", fill: "#6B6380" });
    return s;
  },
};

// ---- Scene 11: end card. ----
SCENES.s11 = {
  dur: 10,
  draw(t) {
    let s = `<rect width="1920" height="1080" fill="${C.cream}"/>`;
    const meet = prog(t, 0.2, 2.2, easeInOut);
    const ax = lerp(-150, 870, meet), bx = lerp(2070, 1050, meet);
    const walking = meet > 0 && meet < 1;
    const hop = meet >= 1 ? Math.abs(Math.sin((t - 2.2) * 6)) * 10 * Math.max(0, 1 - (t - 2.2) / 0.8) : 0;
    s += `<circle cx="960" cy="400" r="${190 * prog(t, 2.0, 2.8)}" fill="${C.yellow}" opacity=".55"/>`;
    s += mascotA({ x: ax, y: 400, s: 1.25, bounce: walking ? walkBounce(t, 10) : hop, expr: meet >= 1 ? "open" : "smile" });
    s += mascotB({ x: bx, y: 404, s: 1.2, bounce: walking ? walkBounce(t + 0.25, 10) : hop, expr: "happy", flip: false });
    const heart = prog(t, 2.4, 2.9);
    s += `<path transform="translate(960 230) scale(${1.6 * heart})" d="M0 10 c-6 -12 -22 -6 -16 6 l16 16 l16 -16 c6 -12 -10 -18 -16 -6 z" fill="${C.yellow}" stroke="${C.ink}" stroke-width="3"/>`;
    const name = prog(t, 2.6, 3.2);
    s += `<g opacity="${name}" transform="translate(0 ${(1 - name) * 16})">${text(960, 660, "StrollCall", { size: 150 })}</g>`;
    const tag = prog(t, 3.2, 3.8);
    s += `<g opacity="${tag}">${text(960, 740, "Less planning. More walking.", { size: 54, family: "Nunito", weight: 800, fill: C.green })}</g>`;
    const links = prog(t, 3.8, 4.4);
    s += `<g opacity="${links}">${text(960, 840, "strollcall.onrender.com", { size: 40, family: "Nunito", weight: 800, fill: C.blue })}
      ${text(960, 892, "github.com/zh315-bit/strollcall", { size: 34, family: "Nunito", weight: 700, fill: "#6B6380" })}
      ${text(960, 990, "Built with Muse Spark · Muse Glimmer (open weights) · Muse Image · Muse Voice", { size: 30, family: "Nunito", weight: 700 })}</g>`;
    const fade = prog(t, 9.2, 10, easeIn);
    if (fade > 0) s += `<rect width="1920" height="1080" fill="${C.cream}" opacity="${fade}"/>`;
    return s;
  },
};
