// Home: "Meet halfway, fairly". Two small maps from one real benchmark pair, measured once on our
// walking graph (scripts/build_fairness_example.py -> frontend/data/fairness_example.json):
//   left   both walks to the geographic midpoint, and how far apart the two arrive
//   right  both walks to our planner's meeting point, then the walk together to the destination
// Nothing is planned here. The section stays hidden unless that file loads and holds sane numbers.
// Drawn once when it scrolls into view, every walk at the same speed (so on the left one person
// visibly arrives first), then the walk together; under prefers-reduced-motion, the final state.

(() => {
  const section = document.getElementById("fair");
  if (!section) return;
  const NS = "http://www.w3.org/2000/svg";
  const SEC_PER_MIN = 0.105;  // drawing speed: the slowest pair plus the walk together is about 2.6 s
  const W = 1000;

  const svgEl = (tag, attrs = {}) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };
  const min = (m) => Math.max(1, Math.round(m));
  const minutes = (m) => `${min(m)} minute${min(m) === 1 ? "" : "s"}`;
  const gapText = (a, b, long = false) => {
    const d = Math.abs(min(a) - min(b));
    return d === 0 ? "less than a minute apart" : long ? `${minutes(d)} apart` : `${d} min apart`;
  };
  const finite = (...xs) => xs.every((x) => typeof x === "number" && Number.isFinite(x) && x > 0);
  const route = (r) => Array.isArray(r) && r.length > 1 && r.every((p) => Array.isArray(p) && finite(Math.abs(p[0]), Math.abs(p[1])));

  function valid(d) {
    return d && Array.isArray(d.bbox) && d.bbox.length === 4 && d.midpoint && d.meeting && d.destination &&
      finite(d.midpoint.a_min, d.midpoint.b_min, d.meeting.a_min, d.meeting.b_min, d.destination.shared_min) &&
      [d.midpoint.a_route, d.midpoint.b_route, d.meeting.a_route, d.meeting.b_route, d.destination.route].every(route) &&
      typeof d.destination.name === "string" && Array.isArray(d.streets);
  }

  // Lat/lon to the viewBox: equirectangular at the box's latitude, north up.
  function projector(bbox) {
    const [s, w, n, e] = bbox, k = Math.cos(((s + n) / 2) * Math.PI / 180);
    const scale = W / ((e - w) * k), H = Math.round((n - s) * scale);
    return { H, xy: ([la, lo]) => [((lo - w) * k * scale).toFixed(1), ((n - la) * scale).toFixed(1)] };
  }
  const pathD = (pts, xy) => pts.map((p, i) => (i ? "L" : "M") + xy(p).join(" ")).join("");

  function drawMap(svg, d, which, P) {
    svg.setAttribute("viewBox", `0 0 ${W} ${P.H}`);
    svg.append(svgEl("rect", { class: "fm-bg", width: W, height: P.H }),
      svgEl("path", { class: "fm-streets", d: d.streets.map((s) => pathD(s, P.xy)).join("") }));
    const lines = {};
    const line = (cls, pts) => svgEl("path", { class: `fm-route ${cls}`, d: pathD(pts, P.xy), pathLength: "1" });
    const dot = (cls, p, r) => { const [x, y] = P.xy(p); return svgEl("circle", { class: cls, cx: x, cy: y, r }); };
    const g = which === "mid" ? d.midpoint : d.meeting;
    if (which === "meet") {
      // The walk together is dashed, so it draws through a mask: a solid copy that grows along it.
      const id = "fm-shared-mask", dd = pathD(d.destination.route, P.xy), mask = svgEl("mask", { id, maskUnits: "userSpaceOnUse" });
      mask.append(lines.shared = svgEl("path", { class: "fm-mask-path", d: dd, pathLength: "1" }));
      svg.append(svgEl("defs"), svgEl("path", { class: "fm-route fm-shared", d: dd, mask: `url(#${id})` }));
      svg.lastChild.previousSibling.append(mask);
    }
    svg.append(lines.a = line("fm-a", g.a_route), lines.b = line("fm-b", g.b_route));
    svg.append(dot("fm-start fm-a-dot", g.a_route[0], 13), dot("fm-start fm-b-dot", g.b_route[0], 13));
    const target = g.a_route[g.a_route.length - 1];
    svg.append(lines.pin = dot(which === "mid" ? "fm-pin fm-mid" : "fm-pin fm-meet", target, 15));
    if (which === "meet") {
      const end = d.destination.route[d.destination.route.length - 1];
      svg.append(lines.end = dot("fm-pin fm-end", end, 15));
    }
    return lines;
  }

  function legendItem(cls, text, extra) {
    const li = document.createElement("li");
    li.className = cls;
    const key = document.createElement("span");
    key.className = "fl-key";
    key.setAttribute("aria-hidden", "true");
    li.append(key, text);
    if (extra) li.append(" ", extra);
    return li;
  }

  function build(d) {
    const P = projector(d.bbox);
    const mid = section.querySelector('[data-map="mid"]'), meet = section.querySelector('[data-map="meet"]');
    const m = d.midpoint, g = d.meeting, dest = d.destination;
    const midSvg = mid.querySelector("svg"), meetSvg = meet.querySelector("svg");
    midSvg.setAttribute("aria-label", `Halfway on the map: to the point halfway between the two start points, you walk ` +
      `${minutes(m.a_min)} and your friend walks ${minutes(m.b_min)}, so you arrive ${gapText(m.a_min, m.b_min, true)}.`);
    meetSvg.setAttribute("aria-label", `Halfway by walking time: you walk ${minutes(g.a_min)} and your friend walks ` +
      `${minutes(g.b_min)} to meet at ${g.name}, arriving ${gapText(g.a_min, g.b_min, true)}, then you walk ` +
      `${minutes(dest.shared_min)} together to ${dest.name}.`);
    const left = drawMap(midSvg, d, "mid", P), right = drawMap(meetSvg, d, "meet", P);

    const gap = Object.assign(document.createElement("span"), { className: "fl-gap", textContent: gapText(m.a_min, m.b_min) });
    mid.querySelector(".fair-legend").append(
      legendItem("fl-a", `You · ${min(m.a_min)} min`), legendItem("fl-b", `Friend · ${min(m.b_min)} min`, gap));
    const even = Object.assign(document.createElement("span"), { className: "fl-even", textContent: gapText(g.a_min, g.b_min) });
    meet.querySelector(".fair-legend").append(
      legendItem("fl-a", `You · ${min(g.a_min)} min`), legendItem("fl-b", `Friend · ${min(g.b_min)} min`, even),
      legendItem("fl-shared", `Together · ${min(dest.shared_min)} min to ${dest.name}`));
    section.hidden = false;
    return { left, right, gap, even };
  }

  // Every walk at the same speed: a walk of t minutes draws in t * SEC_PER_MIN seconds.
  function animate({ left, right, gap, even }, d) {
    const ms = (t) => Math.round(t * SEC_PER_MIN * 1000);
    const draw = (path, t, delay = 0) => path.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }],
      { duration: ms(t), delay, easing: "linear", fill: "backwards" });
    const appear = (node, delay) => node.animate([{ opacity: 0, transform: "scale(.4)" }, { opacity: 1, transform: "none" }],
      { duration: 260, delay, easing: "cubic-bezier(.3,1.5,.5,1)", fill: "backwards" });
    const m = d.midpoint, g = d.meeting;
    draw(left.a, m.a_min); draw(left.b, m.b_min);
    draw(right.a, g.a_min); draw(right.b, g.b_min);
    appear(left.pin, ms(Math.min(m.a_min, m.b_min)));  // the first to arrive waits there
    appear(gap, ms(Math.max(m.a_min, m.b_min)));
    const met = ms(Math.max(g.a_min, g.b_min));
    appear(right.pin, met); appear(even, met);
    draw(right.shared, d.destination.shared_min, met);
    appear(right.end, met + ms(d.destination.shared_min));
  }

  fetch("/static/data/fairness_example.json").then((r) => (r.ok ? r.json() : null)).then((d) => {
    if (!valid(d)) return;  // never made-up numbers: no file, no section
    const parts = build(d);
    const still = !document.body.animate || matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still || typeof IntersectionObserver === "undefined") return;
    section.classList.add("fair-waiting");  // routes undrawn until the section is in view
    const io = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      io.disconnect();
      section.classList.remove("fair-waiting");
      animate(parts, d);
    }, { threshold: 0.4 });
    io.observe(section.querySelector(".fair-maps"));
  }).catch(() => { /* the section stays hidden */ });
})();
