// "More options": what a parsed wish pre-checks (frontend/js/options.js).
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const fs = require("node:fs");

const { optionsFromWish, OPTION_DEFAULTS } = require(path.join(__dirname, "../../../frontend/js/options.js"));
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
  assert.deepEqual(Object.keys(OPTION_DEFAULTS).sort(), ["avoid", "must_be_open", "pace", "pass_kinds", "shape", "stops"]);
  const src = fs.readFileSync(path.join(__dirname, "../../../frontend/js/options.js"), "utf8");
  for (const word of ["Safe", "Lit ", "Lighting", "Crowd level", "Hills", "Weather"]) assert.ok(!src.includes(`"${word}`), word);
  assert.ok(src.includes("Based on map data"), "the Avoid note must say it is based on map data");
});
