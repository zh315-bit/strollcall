// "More options": what a parsed wish pre-checks (frontend/js/options.js).
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const fs = require("node:fs");

const { optionsFromWish, withCustom, cleanCustom, OPTION_DEFAULTS } = require(path.join(__dirname, "../../../frontend/js/options.js"));
const intent = (o = {}) => ({ duration_min: 25, vibes: [], avoid: [], hard_constraints: [], endpoint_type: null, ...o });

test("a wish pre-checks only what it says", () => {
  assert.deepEqual(optionsFromWish(intent(), "25 minutes, coffee at the end"), {});
  assert.deepEqual(optionsFromWish(intent({ endpoint_type: "cafe" }),
    "a slow loop past the river and some murals, two stops, no stairs please"),
    { shape: "loop", pace: "relaxed", pass_kinds: ["waterfront", "public_art"], stops: 2, avoid: ["stairs"] });
  assert.deepEqual(optionsFromWish(intent({ vibes: ["green"], avoid: ["crowds", "traffic"], hard_constraints: ["must be open now"] }),
    "brisk walk"), { pace: "brisk", pass_kinds: ["parks"], avoid: ["busy_avenues", "transit_hubs"], must_be_open: true });
});

test("ending at a park is not passing one", () => {
  assert.deepEqual(optionsFromWish(intent({ endpoint_type: "park" }), "end at a park"), {});
});

test("only options with data behind them: nothing for safety, lighting, crowds, hills or weather", () => {
  assert.deepEqual(Object.keys(OPTION_DEFAULTS).sort(), ["avoid", "custom", "must_be_open", "pace", "pass_kinds", "shape", "stops"]);
  const src = fs.readFileSync(path.join(__dirname, "../../../frontend/js/options.js"), "utf8");
  for (const word of ["Safe", "Lit ", "Lighting", "Crowd level", "Hills", "Weather"]) assert.ok(!src.includes(`"${word}`), word);
  assert.ok(src.includes("Based on map data"), "the Avoid note must say it is based on map data");
});

test("typed items join what the planner gets: kinds, places by id, stops of the kinds named", () => {
  const item = (text, kinds, places = [], count = 0) => ({ text, kinds, places, labels: [], count });
  const v = withCustom({ ...OPTION_DEFAULTS, pass_kinds: ["parks"], avoid: ["stairs"], stops: 0, custom: {
    pass: [item("bridges and a view", ["bridges", "viewpoints"]), item("the High Line", [], [{ id: "r/1", name: "The High Line" }])],
    avoid: [item("Times Square, traffic", ["busy_avenues"], [{ id: "w/2", name: "Times Square" }])],
    stops: [item("two coffees", ["cafes"], [], 2), item("Strand", [], [{ id: "n/3", name: "Strand" }])] } });
  assert.deepEqual(v.pass_kinds, ["parks", "bridges", "viewpoints"]);
  assert.deepEqual(v.avoid, ["stairs", "busy_avenues"]);
  assert.deepEqual(v.pass_place_ids, ["r/1", "n/3"]);  // a named place to stop at is passed by
  assert.deepEqual(v.avoid_place_ids, ["w/2"]);
  assert.deepEqual(v.stop_kinds, ["cafes"]);
  assert.equal(v.stops, 2);  // with Stops on the way left at 0, as many as typed
  assert.equal(withCustom({ ...OPTION_DEFAULTS, stops: 1, custom: { pass: [], avoid: [], stops: [item("two coffees", ["cafes"], [], 2)] } }).stops, 1);
  assert.ok(!("custom" in v));
  assert.equal(withCustom({ ...OPTION_DEFAULTS }).stops, 0);
});

test("a remembered typed item of the wrong shape is dropped", () => {
  assert.deepEqual(cleanCustom({ pass: [{ text: "x" }, { text: "y", kinds: [], places: [], labels: [] }], avoid: "no" }),
    { pass: [{ text: "y", kinds: [], places: [], labels: [] }], avoid: [], stops: [] });
  assert.deepEqual(cleanCustom(null), { pass: [], avoid: [], stops: [] });
});
