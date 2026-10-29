// In-app walking guidance. Two parts:
// - WalkFollower: pure logic (no DOM), fed one GPS fix at a time; tested in Node (backend/tests/js).
// - startWalk(): the full-screen walking view (map, live position, remaining time, notices).
// Positions stay in the browser. Only a re-plan sends the current position (and the target) to the
// server, which neither stores nor logs it. The track is never saved.

const WALK = {
  OFF_ROUTE_M: 50,      // farther than this from the route ...
  OFF_ROUTE_S: 15,      // ... for this long -> re-plan from here
  ARRIVE_M: 40,         // this close to the meetup point or destination -> arrived
  WEAK_ACCURACY_M: 100, // fixes worse than this are shown but not used to judge route or arrival
  REPLAN_RETRY_S: 30,
  M_PER_MIN: 80,        // the planner's walking speed
};

const M_PER_DEG = 111320;

function _xy(lat, lon, lat0) {
  return [lon * M_PER_DEG * Math.cos(lat0 * Math.PI / 180), lat * M_PER_DEG];
}

function distanceM(a, b) {
  const [ax, ay] = _xy(a[0], a[1], a[0]), [bx, by] = _xy(b[0], b[1], a[0]);
  return Math.hypot(ax - bx, ay - by);
}

// Nearest point of a polyline [[lat, lon], ...] to pos: distance to it, meters along the line
// up to it, and the line's total length.
function projectOnRoute(route, pos) {
  const lat0 = pos[0];
  const [px, py] = _xy(pos[0], pos[1], lat0);
  let best = { dist: Infinity, along: 0, index: 0 }, walked = 0;
  for (let i = 1; i < route.length; i++) {
    const [ax, ay] = _xy(route[i - 1][0], route[i - 1][1], lat0), [bx, by] = _xy(route[i][0], route[i][1], lat0);
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy, len = Math.sqrt(len2);
    const t = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
    const d = Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
    if (d < best.dist) best = { dist: d, along: walked + t * len, index: i - 1 };
    walked += len;
  }
  if (route.length === 1) best = { dist: distanceM(route[0], pos), along: 0, index: 0 };
  return { ...best, total: walked };
}

// legs: [{ name, kind: "meetup" | "destination", target: [lat, lon], geometry: [[lat, lon], ...] }]
class WalkFollower {
  constructor(legs, opts = {}) {
    this.legs = legs.map((l) => ({ ...l }));
    this.opts = { ...WALK, ...opts };
    this.leg = 0;
    this.offSince = null;     // time (s) the walker first looked off the route
    this.replanning = false;
    this.lastReplanAt = -Infinity;
    this.arrived = false;
    this.last = null;
  }

  get current() { return this.legs[this.leg]; }

  // fix: { lat, lon, accuracy (m), t (s) } -> an event describing the state now:
  // { type: weak_signal | on_route | off_route | replan | arrived, ... }
  update(fix) {
    const o = this.opts, leg = this.current, pos = [fix.lat, fix.lon];
    const p = projectOnRoute(leg.geometry, pos);
    const toTarget = distanceM(pos, leg.target);
    const remainingM = Math.max(p.total - p.along, 0) + (p.dist > o.OFF_ROUTE_M ? p.dist : 0);
    const base = { leg: this.leg, distToRoute: p.dist, toTarget, remainingM,
                   remainingMin: remainingM / o.M_PER_MIN, accuracy: fix.accuracy };
    this.last = base;
    if (this.arrived) return { type: "arrived", ...base };
    if (!(fix.accuracy <= o.WEAK_ACCURACY_M)) return { type: "weak_signal", ...base };

    if (toTarget <= o.ARRIVE_M) {
      this.arrived = true;
      this.offSince = null;
      return { type: "arrived", ...base };
    }
    // A fix off by its own accuracy is not evidence of being off the route.
    if (p.dist > Math.max(o.OFF_ROUTE_M, fix.accuracy)) {
      if (this.offSince === null) this.offSince = fix.t;
      const offFor = fix.t - this.offSince;
      if (offFor >= o.OFF_ROUTE_S && !this.replanning && fix.t - this.lastReplanAt >= o.REPLAN_RETRY_S) {
        this.replanning = true;
        this.lastReplanAt = fix.t;
        return { type: "replan", offFor, from: pos, target: leg.target, ...base };
      }
      return { type: "off_route", offFor, ...base };
    }
    this.offSince = null;
    return { type: "on_route", ...base };
  }

  // A new route for the current leg (after a re-plan), or null when re-planning failed.
  setRoute(geometry) {
    this.replanning = false;
    if (geometry && geometry.length) {
      this.current.geometry = geometry;
      this.offSince = null;
    }
  }

  // After arriving at the meetup point: on to the destination. Returns false when done.
  nextLeg() {
    if (this.leg + 1 >= this.legs.length) return false;
    this.leg += 1;
    this.arrived = false;
    this.offSince = null;
    return true;
  }
}

// Rounded the way we can stand behind: GPS and our 80 m/min are approximate.
function formatRemaining(m) {
  const min = Math.max(1, Math.round(m / WALK.M_PER_MIN));
  const dist = m < 1000 ? `${Math.max(50, Math.round(m / 50) * 50)} m` : `${(m / 1000).toFixed(1)} km`;
  return { min, dist };
}

if (typeof module !== "undefined") {
  module.exports = { WALK, WalkFollower, projectOnRoute, distanceM, formatRemaining };
}

// ---- The walking view (browser only) ----

function startWalk(legs, opts = {}) {
  const follower = new WalkFollower(legs);
  const color = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  let watchId = null, wakeLock = null, routeLine = null, me = null, meCircle = null, targetMarker = null;

  const stepEl = el("div", { class: "walk-step", role: "status", "aria-live": "polite" });
  const statsEl = el("div", { class: "walk-stats" });
  const noticeEl = el("div", { class: "walk-notice", role: "status", "aria-live": "polite" });
  const mapEl = el("div", { class: "walk-map" });
  const screenNote = el("p", { class: "muted small walk-note" });
  const fallback = el("a", { target: "_blank", rel: "noopener" }, "Open in a map app instead");
  const endBtn = el("button", { type: "button", onclick: () => finish() }, "End walk");
  const screen = el("div", { class: "walk-screen", role: "dialog", "aria-label": "Walking" },
    stepEl, mapEl, statsEl, noticeEl,
    el("div", { class: "row walk-actions" }, endBtn, fallback), screenNote);
  document.body.append(screen);
  document.body.classList.add("walking");

  const map = L.map(mapEl, { zoomControl: true }).setView(legs[0].target, 17);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);
  let follow = true;
  map.on("dragstart", () => { follow = false; });
  // Notices and the arrival card change the map's height: let Leaflet re-measure.
  const resize = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => map.invalidateSize()) : null;
  if (resize) resize.observe(mapEl);

  function showLeg() {
    const leg = follower.current;
    if (routeLine) routeLine.remove();
    if (targetMarker) targetMarker.remove();
    routeLine = L.polyline(leg.geometry, { color: color(leg.kind === "meetup" ? "--a" : "--shared") || "#ff5c8a", weight: 6, opacity: .85 }).addTo(map);
    targetMarker = L.marker(leg.target).addTo(map).bindPopup(leg.name);
    stepEl.textContent = `${leg.kind === "meetup" ? "Walk to the meeting point" : "Walk to"}: ${leg.name}`;
    fallback.href = mapsLink(leg.target[0], leg.target[1]);
    map.invalidateSize();
    map.fitBounds(routeLine.getBounds(), { padding: [30, 30] });
  }

  function stats(m) {
    const r = formatRemaining(m);
    statsEl.replaceChildren(el("div", {}, el("b", {}, `~${r.min}`), "min left"), el("div", {}, el("b", {}, r.dist), "to go"));
  }

  function notice(text, kind = "") {
    noticeEl.className = `walk-notice ${kind}`;
    delete noticeEl.dataset.waiting;
    noticeEl.replaceChildren(text ? el("p", {}, text) : "");
  }

  async function replan(ev) {
    notice("You seem to be off the route. Finding a way from where you are…", "warn");
    try {
      const leg = await api("/api/walk/route", { method: "POST", body: {
        origin: { lat: ev.from[0], lon: ev.from[1] }, target: { lat: ev.target[0], lon: ev.target[1] } } });
      follower.setRoute(leg.geometry);
      showLeg();
      notice("New route from where you are.", "ok");
      if (opts.onReplan) opts.onReplan(leg);
    } catch (e) {
      follower.setRoute(null);
      notice(`Couldn't find a new route (${e.message}). Head back toward the line, or use a map app.`, "warn");
    }
  }

  function arrivedCard() {
    const leg = follower.current, more = follower.leg + 1 < follower.legs.length;
    const acc = follower.last && follower.last.accuracy ? ` (your phone's location is accurate to about ${Math.round(follower.last.accuracy)} m)` : "";
    noticeEl.className = "walk-notice arrived";
    noticeEl.replaceChildren(el("div", { class: "card arrival" },
      el("h2", {}, more ? "You're at the meeting point" : "You've arrived"),
      el("p", {}, `You're within about ${WALK.ARRIVE_M} m of ${leg.name}${acc}.`),
      more ? el("p", { class: "muted" }, "Look around for your friend.") : null,
      el("div", { class: "row" }, more
        ? el("button", { class: "primary", onclick: () => { follower.nextLeg(); showLeg(); notice(""); } }, `Walk on together to ${follower.legs[follower.leg + 1].name}`)
        : el("button", { class: "primary", onclick: () => finish(true) }, "Finish walk"))));
  }

  function onFix(pos) {
    const fix = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy, t: pos.timestamp / 1000 };
    const ll = [fix.lat, fix.lon];
    if (!me) {
      me = L.circleMarker(ll, { radius: 8, color: "#fff", weight: 3, fillColor: color("--accent-2") || "#4aa8ff", fillOpacity: 1 }).addTo(map);
      meCircle = L.circle(ll, { radius: fix.accuracy, weight: 1, opacity: .4, fillOpacity: .1 }).addTo(map);
    } else { me.setLatLng(ll); meCircle.setLatLng(ll).setRadius(fix.accuracy); }
    if (follow) map.panTo(ll);
    const ev = follower.update(fix);
    if (ev.type === "arrived") statsEl.replaceChildren(el("div", {}, el("b", {}, "✓"), "arrived"), el("div", {}, el("b", {}, `~${WALK.ARRIVE_M} m`), "or closer"));
    else stats(ev.remainingM);
    if (ev.type === "weak_signal") notice(`Weak GPS signal (about ${Math.round(fix.accuracy)} m). Times are rough until it improves.`, "warn");
    else if (ev.type === "off_route") notice(ev.offFor > 5 ? "You may be off the route…" : "", ev.offFor > 5 ? "warn" : "");
    else if (ev.type === "replan") replan(ev);
    else if (ev.type === "arrived") { if (!noticeEl.classList.contains("arrived")) arrivedCard(); }
    else if (!follower.replanning && (noticeEl.classList.contains("warn") || noticeEl.dataset.waiting)) notice("");
    if (opts.onEvent) opts.onEvent(ev);
  }

  async function keepAwake() {
    if (!("wakeLock" in navigator)) {
      screenNote.textContent = "Keep your screen on while walking: a web page can't follow you in the background, and this phone can't keep the screen awake for us.";
      return;
    }
    try {
      wakeLock = await navigator.wakeLock.request("screen");
      screenNote.textContent = "Your screen stays on while you walk: a web page can't follow you in the background.";
    } catch (e) {
      screenNote.textContent = "Keep your screen on while walking: a web page can't follow you in the background.";
    }
  }
  const onVisible = () => { if (document.visibilityState === "visible" && watchId !== null) keepAwake(); };
  document.addEventListener("visibilitychange", onVisible);

  function finish(done) {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    if (wakeLock) wakeLock.release().catch(() => {});
    wakeLock = null;
    document.removeEventListener("visibilitychange", onVisible);
    if (resize) resize.disconnect();
    map.remove();
    screen.remove();
    document.body.classList.remove("walking");
    if (opts.onFinish) opts.onFinish(!!done);
  }

  showLeg();
  stats(projectOnRoute(follower.current.geometry, follower.current.geometry[0]).total);
  keepAwake();
  if (!navigator.geolocation) {
    notice("This browser can't share your location. Use a map app instead.", "warn");
  } else {
    notice("Finding your location…");
    noticeEl.dataset.waiting = "1";
    watchId = navigator.geolocation.watchPosition(onFix,
      (e) => notice(e.code === 1 ? "Location permission was denied. Allow it in your browser settings, or use a map app." : "Location unavailable right now. Still trying…", "warn"),
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 });
  }
  return { follower, finish };
}
