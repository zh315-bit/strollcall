// Guards the walking screen against style or page changes: the pages load walk.js after its
// helpers, every class walk.js renders has a CSS rule, the screen covers the viewport above the map
// and nothing hides its key parts. Run: node --test backend/tests/js/
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const FRONT = path.join(__dirname, "../../../frontend");
const read = (p) => fs.readFileSync(path.join(FRONT, p), "utf8");
const css = (read("style.css") + "\n" + (fs.existsSync(path.join(FRONT, "bits.css")) ? read("bits.css") : ""))
  .replace(/\/\*[\s\S]*?\*\//g, "");  // comments would read as part of the next selector
const walk = read("js/walk.js");
const common = read("js/common.js");

// All declarations for a selector, merged in source order (later rules win), ignoring @media blocks' conditions.
function rule(selector) {
  const out = {};
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(css))) {
    const sels = m[1].split(",").map((s) => s.trim().replace(/^@[^{]*$/, ""));
    if (!sels.includes(selector)) continue;
    for (const decl of m[2].split(";")) {
      const i = decl.indexOf(":");
      if (i > 0) out[decl.slice(0, i).trim()] = decl.slice(i + 1).trim();
    }
  }
  return out;
}

// Some rule mentions the class (".walk-notice.warn p" counts for .walk-notice).
const styled = (c) => new RegExp(`\\.${c}(?![\\w-])[^{}]*\\{`).test(css);

// Classes the walking view and its cards render (class: "a b" in el(...) calls after the view starts).
const viewSource = walk.slice(walk.indexOf("// ---- The walking view"));
const rendered = new Set();
for (const m of viewSource.matchAll(/class(?:Name)?:\s*[`"]([^`"$]+)/g)) m[1].split(/\s+/).filter(Boolean).forEach((c) => rendered.add(c));

const KEY = ["walk-screen", "walk-step", "walk-map", "walk-stats", "walk-notice", "walk-poi", "poi-card", "poi-pin",
             "voice-toggle", "walk-actions"];

test("both pages load Leaflet, then common.js, then walk.js, and offer Start walking", () => {
  for (const page of ["index.html", "invite.html"]) {
    const html = read(page);
    const at = (s) => html.indexOf(s);
    assert.ok(at("leaflet") > 0 && at("/static/js/common.js") > at("leaflet"), `${page}: Leaflet before common.js`);
    assert.ok(at("/static/js/walk.js") > at("/static/js/common.js"), `${page}: walk.js after common.js`);
    assert.match(html, /start-walk[^]*Start walking/, `${page}: a Start walking button`);
  }
});

test("walk.js only relies on helpers common.js still defines", () => {
  for (const name of ["function el(", "async function api(", "function mapsLink(", "const OSM_ATTRIBUTION"]) {
    assert.ok(common.includes(name), `common.js must keep ${name}`);
  }
});

test("every key class the walking screen renders has a CSS rule", () => {
  for (const c of KEY) {
    assert.ok(rendered.has(c), `walk.js no longer renders .${c}: update this test with the change`);
    assert.ok(styled(c), `style.css has no rule for .${c}`);
  }
  assert.ok(styled("start-walk"), "style.css has no rule for .start-walk");
  assert.ok(styled("survey"), "the after-walk survey lost its styles");
});

test("the walking screen covers the viewport above the map and its map can grow", () => {
  const s = rule(".walk-screen");
  assert.equal(s.position, "fixed");
  assert.ok(s.inset === "0" || (s.top === "0" && s.bottom === "0"), "covers the whole viewport");
  assert.ok(parseInt(s["z-index"], 10) >= 1000, "above Leaflet's panes and controls (z-index up to 1000)");
  assert.match(s.display || "", /flex/);
  assert.ok(s.background || s["background-color"], "opaque: the page must not show through");
  assert.ok(["auto", "scroll"].includes(s["overflow-y"]), "scrollable: End walk must stay reachable on short phones");
  const mapRule = rule(".walk-map");
  assert.ok(/1/.test(mapRule.flex || mapRule["flex-grow"] || ""), "the map takes the free height");
  assert.ok(parseInt(mapRule["min-height"], 10) >= 150, "the map keeps a usable height on 320x640");
});

test("nothing hides the key parts (only an empty POI area may collapse)", () => {
  for (const c of KEY) {
    const r = rule(`.${c}`);
    assert.notEqual(r.display, "none", `.${c} is hidden`);
    assert.notEqual(r.visibility, "hidden", `.${c} is hidden`);
    assert.ok(!r.opacity || parseFloat(r.opacity) > 0.5, `.${c} is nearly transparent`);
  }
  assert.equal(rule(".walk-poi:empty").display, "none");
});

test("touch targets in the walking screen are at least 44 px tall", () => {
  for (const sel of [".walk-actions button", ".voice-toggle", ".poi-close", ".walk-recenter"]) {
    const r = rule(sel);
    const h = parseInt(r["min-height"], 10);
    assert.ok(h >= 36, `${sel} min-height ${r["min-height"]}`);
  }
});

test("click handlers use currentTarget: buttons hold a canvas and a label (specular.js)", () => {
  for (const file of ["index.html", "invite.html", "js/walk.js", "js/common.js"]) {
    const src = read(file);
    assert.ok(!/\be\.target\b/.test(src), `${file}: use e.currentTarget, e.target may be the label inside a button`);
  }
});

test("the typing tagline's source line stays transparent on every page head", () => {
  // .page-head.lead-only .tagline sets a colour; the typing copy's source must win over it.
  const hide = rule(".page-head .tt .tt-source.tagline");
  assert.equal(hide.color, "transparent");
});

test("ten taglines per mode, each short enough for one line at 320 px", () => {
  const src = read("index.html").match(/const TAGLINES = (\{[\s\S]*?\});/)[1];
  const T = Function(`return (${src})`)();
  for (const mode of ["pair", "solo"]) {
    assert.equal(T[mode].length, 10, mode);
    assert.equal(new Set(T[mode]).size, 10, `${mode}: no repeats`);
    // 29 characters was the longest line measured to fit one line in the title font at 320 px.
    for (const t of T[mode]) assert.ok(t.length <= 29, `${mode}: "${t}" may wrap`);
  }
});
