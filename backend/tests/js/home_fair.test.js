// Home's "Meet halfway, fairly" (frontend/js/fairness.js): real measured numbers from one benchmark
// pair (scripts/build_fairness_example.py), hidden without them, labelled in words, no planning at load.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "../../..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const home = read("frontend/home.html");
const js = read("frontend/js/fairness.js");
const data = JSON.parse(read("frontend/data/fairness_example.json"));

test("the example is one benchmark pair of public places, dated, with measured routes", () => {
  const pair = JSON.parse(read("fixtures/nyc_origins.json")).pairs.find((p) => p.id === data.pair);
  assert.ok(pair, `pair ${data.pair} is in fixtures/nyc_origins.json`);
  assert.equal(data.a.name, pair.a.name);
  assert.equal(data.b.name, pair.b.name);
  assert.match(data.generated, /^\d{4}-\d{2}-\d{2}$/);
  assert.ok(data._note.includes(data.pair) && data._note.includes("OpenStreetMap"));
  for (const r of [data.midpoint.a_route, data.midpoint.b_route, data.meeting.a_route, data.meeting.b_route, data.destination.route]) {
    assert.ok(r.length > 1);
  }
  // The point of the section: the map midpoint is uneven, ours is close to even.
  const gap = (x) => Math.abs(x.a_min - x.b_min);
  assert.ok(gap(data.midpoint) > 3 && gap(data.meeting) <= 2, "midpoint uneven, meeting point fair");
  assert.ok(data.destination.name && data.destination.shared_min > 0);
});

test("the section is hidden until the file loads, and the page plans nothing", () => {
  assert.match(home, /<section class="fair" id="fair" aria-labelledby="fair-title" hidden>/);
  assert.ok(home.indexOf('id="fair"') < home.indexOf('class="steps"'), "above How to use");
  assert.ok(home.indexOf('class="hero-copy"') < home.indexOf('id="fair"'), "below the hero copy");
  assert.equal((js.match(/fetch\(/g) || []).length, 1);
  assert.ok(js.includes('fetch("/static/data/fairness_example.json")') && !/\/api\//.test(js));
  assert.ok(js.includes("if (!valid(d)) { ready(); return; }") && js.includes("section.hidden = false"));
});

test("maps are images with the numbers in words; text is HTML; the link opens New walk with a friend", () => {
  assert.equal((home.match(/<svg class="fair-svg" role="img"/g) || []).length, 2);
  assert.ok(js.includes('setAttribute("aria-label"') && js.includes("minutes(m.a_min)") && js.includes("minutes(g.b_min)"));
  for (const t of ["Meet halfway, fairly", "Halfway on the map", "Halfway by walking time",
    "Halfway by walking time, not by distance.", "A real example from our tests in New York. Route data © OpenStreetMap contributors."]) {
    assert.ok(home.includes(t), t);
  }
  assert.match(home, /<a class="fair-try" href="\/new\?mode=pair">Try it/);
});

test("drawn once when in view, all walks at one speed; still under reduced motion", () => {
  assert.ok(js.includes("IntersectionObserver") && js.includes("io.disconnect()"));
  assert.ok(js.includes("prefers-reduced-motion: reduce") && js.includes('easing: "linear"'));
  assert.ok(/duration: ms\(t\)/.test(js), "a walk's drawing time is its walking time");
});

test("scroll reveals: each block below the fold rises in once, measured after the section settles; none under reduced motion", () => {
  const homeJs = read("frontend/js/home.js"), css = read("frontend/home.css");
  assert.ok(homeJs.indexOf("if (reduce) return;") < homeJs.indexOf("function reveals()"), "reduced motion: no reveals");
  for (const sel of [".fair-card", ".steps-title", ".step", ".hero-foot"]) assert.ok(homeJs.includes(sel), sel);
  assert.ok(homeJs.includes("io.unobserve(e.target)"), "once only");
  assert.ok(homeJs.includes('"fair:ready"') && homeJs.includes("fair.dataset.ready"));
  // fairness.js says it is ready on every path: shown, no data, or a failed fetch.
  assert.equal((js.match(/ready\(\)/g) || []).length, 3);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{[^}]*\}\s*\.sr \{ opacity: 1; translate: none; scale: none; \}/);
});
