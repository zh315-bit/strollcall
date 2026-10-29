// Simulated GPS walk along a real fixture route (pair p1 on the local OSM graph), including a
// detour off the route, a re-plan and both arrivals. Run: node --test backend/tests/js/
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const fs = require("node:fs");

const { WALK, WalkFollower, projectOnRoute, distanceM, formatRemaining, stepInfo, formatStep } =
  require(path.join(__dirname, "../../../frontend/js/walk.js"));
const fx = JSON.parse(fs.readFileSync(path.join(__dirname, "../../../fixtures/walk_track_p1.json"), "utf8"));

// Deterministic "urban GPS": up to ~12 m of jitter around the true position.
let seed = 42;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31) - 0.5;
const jitter = ([lat, lon], m = 12) => [lat + (rand() * 2 * m) / 111320, lon + (rand() * 2 * m) / (111320 * Math.cos(lat * Math.PI / 180))];

// Points every `step` meters along a polyline, from `fromM` to `toM` meters.
function along(line, fromM, toM, step = 4) {
  const out = [];
  let walked = 0;
  for (let i = 1; i < line.length; i++) {
    const seg = distanceM(line[i - 1], line[i]);
    for (let d = Math.max(0, Math.ceil((fromM - walked) / step) * step); walked + d <= Math.min(toM, walked + seg) && seg > 0; d += step) {
      const t = d / seg;
      out.push([line[i - 1][0] + t * (line[i][0] - line[i - 1][0]), line[i - 1][1] + t * (line[i][1] - line[i - 1][1])]);
    }
    walked += seg;
  }
  return out;
}
const lengthOf = (line) => projectOnRoute(line, line[0]).total;
const legs = () => [
  { name: fx.meetup.name, kind: "meetup", target: [fx.meetup.lat, fx.meetup.lon], geometry: fx.a_leg, steps: fx.a_steps },
  { name: fx.destination.name, kind: "destination", target: [fx.destination.lat, fx.destination.lon], geometry: fx.shared_leg, steps: fx.shared_steps },
];

test("a full walk: on route, detour, re-plan, meetup, destination", () => {
  const f = new WalkFollower(legs());
  let t = 0;
  const feed = (p, accuracy = 15) => f.update({ lat: p[0], lon: p[1], accuracy, t: (t += 3) });

  // 1. On the route with GPS jitter for 40% of A's leg (3 s per ~4 m, about walking pace): never off route.
  const aLen = lengthOf(fx.a_leg);
  let prevRemaining = Infinity;
  for (const p of along(fx.a_leg, 0, 0.4 * aLen)) {
    const ev = feed(jitter(p));
    assert.equal(ev.type, "on_route", `false off-route at t=${t}`);
    assert.ok(ev.remainingM <= prevRemaining + 30, "remaining distance only shrinks (allowing jitter)");
    prevRemaining = ev.remainingM;
  }

  // 2. A weak fix is shown but never judged.
  assert.equal(feed(jitter(fx.detour_point), 150).type, "weak_signal");

  // 3. Walk off to the real detour point and stay: off_route first, re-plan after 15 s off route.
  const pivot = along(fx.a_leg, 0.4 * aLen, 0.4 * aLen + 1)[0];
  const types = [];
  let replan = null;
  const track = [...along([pivot, fx.detour_point], 0, distanceM(pivot, fx.detour_point)), ...Array(10).fill(fx.detour_point)];
  for (const p of track) {
    const ev = feed(jitter(p, 5));
    types.push(ev.type);
    if (ev.type === "replan") { replan = ev; break; }
  }
  assert.ok(types.includes("off_route"), "noticed being off the route before re-planning");
  assert.ok(replan, "asked for a re-plan");
  assert.ok(replan.offFor >= WALK.OFF_ROUTE_S && replan.distToRoute > WALK.OFF_ROUTE_M);
  assert.deepEqual(replan.target, [fx.meetup.lat, fx.meetup.lon], "re-plan goes to the same meetup point");
  assert.equal(feed(jitter(fx.detour_point, 5)).type, "off_route", "only one re-plan request at a time");

  // 4. The server's new route (from the fixture, the same endpoint's output) is followed to the meetup.
  f.setRoute(fx.replan_leg, fx.replan_steps);
  let arrived = null;
  for (const p of along(fx.replan_leg, 0, lengthOf(fx.replan_leg))) {
    const ev = feed(jitter(p));
    assert.notEqual(ev.type, "replan", "no re-plan on the new route");
    if (ev.type === "arrived") { arrived = ev; break; }
  }
  assert.ok(arrived, "arrived at the meetup point");
  assert.ok(arrived.toTarget <= WALK.ARRIVE_M && arrived.leg === 0);

  // 5. On together to the destination.
  assert.ok(f.nextLeg());
  arrived = null;
  for (const p of along(fx.shared_leg, 0, lengthOf(fx.shared_leg))) {
    const ev = feed(jitter(p));
    assert.notEqual(ev.type, "replan");
    if (ev.type === "arrived") { arrived = ev; break; }
  }
  assert.ok(arrived && arrived.leg === 1, "arrived at the destination");
  assert.equal(f.nextLeg(), false, "no more legs");
});

test("a fix off the route by less than its own accuracy is not off route", () => {
  const f = new WalkFollower(legs());
  const p = along(fx.a_leg, 0, 100)[20];
  const off = [p[0] + 70 / 111320, p[1]];  // ~70 m north
  for (let t = 0; t <= 30; t += 3) assert.equal(f.update({ lat: off[0], lon: off[1], accuracy: 90, t }).type, "on_route");
});

test("a failed re-plan is retried after a pause", () => {
  const f = new WalkFollower(legs());
  const [lat, lon] = fx.detour_point;
  const seen = [];
  for (let t = 0; t <= 60; t += 3) {
    const ev = f.update({ lat, lon, accuracy: 10, t });
    if (ev.type === "replan") { seen.push(t); f.setRoute(null); }
  }
  assert.deepEqual(seen, [15, 45]);
});

test("remaining time is rounded honestly", () => {
  assert.deepEqual(formatRemaining(10), { min: 1, dist: "50 m" });
  assert.deepEqual(formatRemaining(1234), { min: 15, dist: "1.2 km" });
});

test("the next instruction follows the walker along the real shared leg", () => {
  const f = new WalkFollower(legs());
  f.nextLeg();
  const shown = [];
  for (const p of along(fx.shared_leg, 0, lengthOf(fx.shared_leg), 10)) {
    const ev = f.update({ lat: p[0], lon: p[1], accuracy: 10, t: shown.length * 3 });
    const text = ev.type === "arrived" ? null : formatStep(ev.step);
    if (text && text !== shown[shown.length - 1]) shown.push(text);
  }
  const turns = fx.shared_steps.slice(1).map((s) => s.text);
  // Every turn is announced ahead ("In ... m: ...") and then at the corner ("Now: ..."), in order.
  for (const t of turns) {
    const ahead = shown.findIndex((x) => x.endsWith(`: ${t}`) && !x.startsWith("Now"));
    const now = shown.indexOf(`Now: ${t}`);
    assert.ok(ahead >= 0 && now > ahead, `announced ${t}: ${JSON.stringify(shown)}`);
  }
  assert.ok(shown[0].startsWith(fx.shared_steps[0].text), "starts with the departure step");
});

test("step distances are rounded, never more precise than the map", () => {
  const info = stepInfo(fx.shared_steps, 50, "x");
  assert.equal(info.index, 0);
  assert.match(formatStep(info), /then in 150 m: /);
  assert.equal(stepInfo([], 0, "x"), null);
});
