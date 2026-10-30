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
  STEP_NOW_M: 20,       // "Now: turn left ..." this close to a turn
  POI_NEAR_M: 40,       // a point of interest this close (plus a little GPS slack) gets its card
  POI_SLACK_M: 15,
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

// Turn instructions (from the server's route) relative to how far along the route we are:
// the step we are on and the next one, with the distance to it.
function stepInfo(steps, along, targetName) {
  if (!steps || !steps.length) return null;
  let i = 0;
  while (i + 1 < steps.length && steps[i + 1].along_m <= along + WALK.STEP_NOW_M) i++;
  const next = steps[i + 1];
  return { current: steps[i], index: i, next: next || null, toNextM: next ? Math.max(0, next.along_m - along) : null,
           finalText: `Arrive at ${targetName}` };
}

function formatStep(info) {
  if (!info) return null;
  if (info.next && info.toNextM <= WALK.STEP_NOW_M * 2) return `Now: ${info.next.text}`;
  if (info.index === 0 && info.current.kind === "depart" && (!info.next || info.toNextM > 60)) {
    return info.next ? `${info.current.text}, then in ${roundDist(info.toNextM)}: ${info.next.text}` : info.current.text;
  }
  return info.next ? `In ${roundDist(info.toNextM)}: ${info.next.text}` : info.finalText;
}

// ---- Spoken prompts (P2): what to say, decided here; speaking is the browser's speech synthesis ----

const SPEAK_AHEAD_M = 120;  // announce a turn once when it is this close ...
const SPEAK_NOW_M = 40;     // ... and again at the corner

// Street abbreviations read badly aloud ("E 20th St"): spell them out for speech only.
const SPOKEN = [[/\bE (?=\d)/g, "East "], [/\bW (?=\d)/g, "West "], [/\bN (?=\d)/g, "North "], [/\bS (?=\d)/g, "South "],
                [/\bSt\b(?!\.? [A-Z])/g, "Street"], [/\bAve\b/g, "Avenue"], [/\bPl\b/g, "Place"], [/\bBlvd\b/g, "Boulevard"],
                [/\bDr\b/g, "Drive"], [/\bRd\b/g, "Road"], [/\bPkwy\b/g, "Parkway"], [/\bLn\b/g, "Lane"], [/\bSq\b/g, "Square"]];
function spokenText(text) {
  return SPOKEN.reduce((t, [re, word]) => t.replace(re, word), text);
}

// The prompt to speak for this event, at most once each (keys remembered in `said`), or null.
function promptFor(ev, said) {
  const once = (key, text) => (said.has(key) ? null : (said.add(key), spokenText(text)));
  if (ev.type === "arrived") return once(`arrived:${ev.leg}`, ev.legKind === "meetup" ? "You're at the meeting point." : "You've arrived.");
  if (ev.type === "replan") return once(`replan:${ev.leg}:${Math.round(ev.from[0] * 1e4)}`, "You seem to be off the route. Finding a way from here.");
  const info = ev.step;
  if (!info || ev.type !== "on_route") return null;
  if (info.index === 0 && info.current.kind === "depart" && !said.has(`depart:${ev.leg}`)) {
    return once(`depart:${ev.leg}`, info.current.text);
  }
  if (!info.next) return null;
  const key = `${ev.leg}:${info.next.along_m}`;
  if (info.toNextM <= SPEAK_NOW_M) return once(`now:${key}`, `Now, ${info.next.text.charAt(0).toLowerCase()}${info.next.text.slice(1)}.`);
  if (info.toNextM <= SPEAK_AHEAD_M) return once(`ahead:${key}`, `In about ${roundDist(info.toNextM).replace(" m", " meters")}, ${info.next.text.charAt(0).toLowerCase()}${info.next.text.slice(1)}.`);
  return null;
}

function roundDist(m) {
  const r = m < 95 ? Math.max(10, Math.round(m / 10) * 10) : Math.round(m / 50) * 50;
  return r < 1000 ? `${r} m` : `${(m / 1000).toFixed(1)} km`;
}

// legs: [{ name, kind: "meetup" | "destination", target: [lat, lon], geometry: [[lat, lon], ...], steps? }]
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
    this.seenPois = new Set();
  }

  // The first point of interest of this leg we are near for the first time, or null.
  _nearPoi(pos, accuracy) {
    const reach = this.opts.POI_NEAR_M + Math.min(accuracy || 0, this.opts.POI_SLACK_M);
    for (const p of this.current.pois || []) {
      if (!this.seenPois.has(p.id) && distanceM(pos, [p.lat, p.lon]) <= reach) {
        this.seenPois.add(p.id);
        return p;
      }
    }
    return null;
  }

  get current() { return this.legs[this.leg]; }

  // fix: { lat, lon, accuracy (m), t (s) } -> an event describing the state now:
  // { type: weak_signal | on_route | off_route | replan | arrived, ... }
  update(fix) {
    const o = this.opts, leg = this.current, pos = [fix.lat, fix.lon];
    const p = projectOnRoute(leg.geometry, pos);
    const toTarget = distanceM(pos, leg.target);
    const remainingM = Math.max(p.total - p.along, 0) + (p.dist > o.OFF_ROUTE_M ? p.dist : 0);
    const base = { leg: this.leg, legKind: leg.kind, distToRoute: p.dist, toTarget, remainingM, along: p.along,
                   remainingMin: remainingM / o.M_PER_MIN, accuracy: fix.accuracy,
                   step: stepInfo(leg.steps, p.along, leg.name) };
    this.last = base;
    if (this.arrived) return { type: "arrived", ...base };
    if (!(fix.accuracy <= o.WEAK_ACCURACY_M)) return { type: "weak_signal", ...base };
    base.poi = this._nearPoi(pos, fix.accuracy);

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
  setRoute(geometry, steps, pois) {
    this.replanning = false;
    if (geometry && geometry.length) {
      this.current.geometry = geometry;
      this.current.steps = steps || [];
      this.current.pois = pois || [];
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
  const r50 = Math.max(50, Math.round(m / 50) * 50);
  const dist = r50 < 1000 ? `${r50} m` : `${(m / 1000).toFixed(1)} km`;
  return { min, dist };
}

// Compass bearing (degrees clockwise from north) from a to b.
function bearingDeg(a, b) {
  const [ax, ay] = _xy(a[0], a[1], a[0]), [bx, by] = _xy(b[0], b[1], a[0]);
  return (Math.atan2(bx - ax, by - ay) * 180 / Math.PI + 360) % 360;
}

// Which way the walker faces, for the arrow. Only measured directions, never the route's:
// 1. the phone's compass while it reports (fresh within COMPASS_FRESH_S),
// 2. the GPS heading while moving,
// 3. the direction between fixes once the walker has moved clearly more than the GPS error.
// heading() is null until one of these is known; the map then shows a plain dot.
class HeadingTracker {
  constructor() {
    this.compass = null; this.compassT = -Infinity;
    this.moved = null; this.anchor = null;
  }
  onCompass(deg, t) {
    if (!Number.isFinite(deg)) return;
    this.compass = ((deg % 360) + 360) % 360; this.compassT = t;
  }
  onFix(fix) {
    const { lat, lon, accuracy, heading, speed, t } = fix;
    if (Number.isFinite(heading) && Number.isFinite(speed) && speed >= HeadingTracker.MOVING_MPS) {
      this.moved = heading; this.anchor = { p: [lat, lon], t };
      return;
    }
    if (!this.anchor) { this.anchor = { p: [lat, lon], t }; return; }
    const d = distanceM(this.anchor.p, [lat, lon]);
    if (d >= Math.max(HeadingTracker.MOVE_M, (accuracy || 0) / 2)) {
      this.moved = bearingDeg(this.anchor.p, [lat, lon]); this.anchor = { p: [lat, lon], t };
    }
  }
  heading(t) {
    if (this.compass !== null && t - this.compassT <= HeadingTracker.COMPASS_FRESH_S) return this.compass;
    return this.moved;
  }
}
HeadingTracker.MOVING_MPS = 0.5;     // GPS heading is noise when standing still
HeadingTracker.MOVE_M = 8;           // ... and so is the step between two close fixes
HeadingTracker.COMPASS_FRESH_S = 3;

// A compass reading from a deviceorientation event, corrected for screen rotation; null if none.
function compassFrom(e, screenAngle = 0) {
  if (Number.isFinite(e.webkitCompassHeading)) return (e.webkitCompassHeading + screenAngle) % 360;  // iPhone
  if (e.absolute && Number.isFinite(e.alpha)) return ((360 - e.alpha + screenAngle) % 360 + 360) % 360;
  return null;
}

if (typeof module !== "undefined") {
  module.exports = { WALK, WalkFollower, projectOnRoute, distanceM, formatRemaining, stepInfo, formatStep,
                     promptFor, spokenText, settle, bearingDeg, HeadingTracker, compassFrom };
}

// ---- The walking view (browser only) ----

// Where the last tap landed, so the walking screen can open from the "Start walking" button.
let lastTap = null;
if (typeof window !== "undefined") {
  window.addEventListener("pointerdown", (e) => { lastTap = { x: e.clientX, y: e.clientY, t: Date.now() }; },
    { capture: true, passive: true });
}

function tapOrigin() {
  return lastTap && Date.now() - lastTap.t < 2000 ? lastTap : { x: innerWidth / 2, y: innerHeight - 80 };
}

// Opening: a circle grows from the tap until it covers the screen, the map settles in, then the
// instruction bar, stats and buttons slide up. Closing plays it back toward the last tap.
// Reduced motion: a short fade. Without the Web Animations API: no animation at all.
const WALK_OPEN_MS = 560, WALK_CLOSE_MS = 380;

function circleTo(screen, from, opening) {
  const r = Math.hypot(Math.max(from.x, innerWidth - from.x), Math.max(from.y, innerHeight - from.y));
  const small = `circle(22px at ${from.x}px ${from.y}px)`, big = `circle(${Math.ceil(r)}px at ${from.x}px ${from.y}px)`;
  return screen.animate([{ clipPath: opening ? small : big }, { clipPath: opening ? big : small }],
    { duration: opening ? WALK_OPEN_MS : WALK_CLOSE_MS, easing: opening ? "cubic-bezier(.2,.8,.2,1)" : "cubic-bezier(.4,0,.8,.4)", fill: "both" });
}

// An animation whose clock stops (tab hidden, page not painting) must not leave the screen stuck:
// settle after its duration plus a margin either way, then end it.
function settle(anim, ms) {
  return Promise.race([anim.finished.catch(() => {}), new Promise((r) => setTimeout(r, ms + 200))])
    .then(() => { try { anim.finish(); } catch (e) { /* already done or cancelled */ } return anim; });
}

function playWalkOpen(screen, parts) {
  if (!screen.animate) return Promise.resolve();
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return settle(screen.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160, easing: "ease-out" }), 160);
  }
  const grow = circleTo(screen, tapOrigin(), true);
  parts.map.animate([{ opacity: 0, transform: "scale(.96)" }, { opacity: 1, transform: "none" }],
    { duration: 480, delay: 120, easing: "cubic-bezier(.2,.8,.2,1)", fill: "backwards" });
  parts.slide.forEach((node, i) => node.animate(
    [{ opacity: 0, transform: "translateY(14px)" }, { opacity: 1, transform: "none" }],
    { duration: 360, delay: 220 + i * 60, easing: "cubic-bezier(.2,.8,.2,1)", fill: "backwards" }));
  return settle(grow, WALK_OPEN_MS).then(() => grow.cancel());  // cancel: drop the clip once covered
}

function playWalkClose(screen) {
  if (!screen.animate) return Promise.resolve();
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return settle(screen.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 140, fill: "forwards" }), 140);
  }
  return settle(circleTo(screen, tapOrigin(), false), WALK_CLOSE_MS);
}

// Intros written ahead of time (scripts/make_poi_intros.py); loaded once, no model call here.
let poiIntros = null;
async function loadPoiIntros() {
  if (poiIntros === null) {
    try { poiIntros = (await api("/static/data/poi_intros.json")).intros || {}; } catch (e) { poiIntros = {}; }
  }
  return poiIntros;
}

const POI_ICONS = { park: "🌳", "historic site": "🏛️", artwork: "🎨", memorial: "🕊️", landmark: "📍" };

function introBlock(intro) {
  if (!intro) return null;
  return el("div", { class: "poi-intro" }, el("p", {}, intro.intro),
    el("p", { class: "muted small" }, "Source: Wikipedia, ",
      el("a", { href: intro.source_url, target: "_blank", rel: "noopener" }, `“${intro.source_title}”`),
      " (", el("a", { href: "https://creativecommons.org/licenses/by-sa/4.0/", target: "_blank", rel: "noopener" }, "CC BY-SA 4.0"),
      "), shortened by Muse Spark using only that text."));
}

function poiCard(p, onClose) {
  const intro = poiIntros && poiIntros[p.id];
  return el("div", { class: "card poi-card", role: "status" },
    el("button", { type: "button", class: "poi-close", "aria-label": "Close", onclick: onClose }, "×"),
    el("h3", {}, `${POI_ICONS[p.category] || "📍"} ${p.name}`),
    el("p", { class: "muted small" }, `You're passing a ${p.category}.`),
    introBlock(intro));
}

function startWalk(legs, opts = {}) {
  const follower = new WalkFollower(legs);
  const color = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  let watchId = null, wakeLock = null, routeLine = null, me = null, meCircle = null, targetMarker = null;
  // Facing direction for the arrow: the compass if the phone shares it, else the direction walked.
  const facing = new HeadingTracker();
  const compassEvent = "ondeviceorientationabsolute" in window ? "deviceorientationabsolute" : "deviceorientation";
  const onCompass = (e) => {
    const so = window.screen.orientation;  // window.screen: `screen` below is the walking view
    const deg = compassFrom(e, (so && so.angle) || window.orientation || 0);
    if (deg !== null) { facing.onCompass(deg, Date.now() / 1000); pointArrow(); }
  };
  const listenCompass = () => window.addEventListener(compassEvent, onCompass);
  if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
    // iPhone asks once, and only from inside a tap: startWalk runs in the Start walking tap.
    DeviceOrientationEvent.requestPermission().then((s) => { if (s === "granted") listenCompass(); }).catch(() => {});
  } else if (typeof DeviceOrientationEvent !== "undefined") listenCompass();
  function pointArrow() {
    if (!me) return;
    const deg = facing.heading(Date.now() / 1000), node = me.getElement();
    if (!node) return;
    node.classList.toggle("has-heading", deg !== null);
    if (deg === null) return;
    // Turn the short way round (350° -> 10° is +20°, not -340°) so the rotation animates sensibly.
    shown = shown === null ? deg : shown + ((deg - shown % 360 + 540) % 360 - 180);
    node.style.setProperty("--heading", `${Math.round(shown)}deg`);
  }
  let shown = null;

  const stepEl = el("div", { class: "walk-step", role: "status", "aria-live": "polite" });
  const statsEl = el("div", { class: "walk-stats" });
  const noticeEl = el("div", { class: "walk-notice", role: "status", "aria-live": "polite" });
  const poiEl = el("div", { class: "walk-poi" });
  let poiShown = null, poiLayers = [];
  // For the recap: when the walk started and which places' cards came up. No positions are kept.
  const startedAt = Date.now(), passed = [];
  const mapEl = el("div", { class: "walk-map" });
  const screenNote = el("p", { class: "muted small walk-note" });
  const fallback = el("a", { target: "_blank", rel: "noopener" }, "Open in a map app instead");
  const endBtn = el("button", { type: "button", onclick: () => finish() }, "End walk");
  // Voice prompts: off unless the walker turned them on (remembered on this phone only).
  const canSpeak = typeof speechSynthesis !== "undefined" && typeof SpeechSynthesisUtterance !== "undefined";
  let voiceOn = false;
  try { voiceOn = canSpeak && localStorage.getItem("strollcall:voice") === "on"; } catch (e) { /* default off */ }
  const said = new Set();
  function say(text) {
    if (!voiceOn || !text) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    speechSynthesis.cancel();  // never queue stale prompts behind new ones
    speechSynthesis.speak(u);
  }
  const voiceBtn = el("button", { type: "button", class: "voice-toggle", "aria-pressed": String(voiceOn),
    onclick: () => {
      voiceOn = !voiceOn;
      voiceBtn.setAttribute("aria-pressed", String(voiceOn));
      voiceBtn.textContent = voiceOn ? "🔊 Voice on" : "🔇 Voice off";
      try { localStorage.setItem("strollcall:voice", voiceOn ? "on" : "off"); } catch (e) { /* fine */ }
      if (voiceOn) say("Voice prompts on.");  // speaking inside the tap unlocks audio on iPhone
      else speechSynthesis.cancel();
    } }, voiceOn ? "🔊 Voice on" : "🔇 Voice off");
  if (!canSpeak) voiceBtn.hidden = true;
  const screen = el("div", { class: "walk-screen", role: "dialog", "aria-label": "Walking" },
    stepEl, mapEl, poiEl, statsEl, noticeEl,
    el("div", { class: "row walk-actions" }, endBtn, voiceBtn, fallback), screenNote);
  document.body.append(screen);
  // The page (top bar, sky) stays visible under the growing circle; "walking" hides it once covered.
  const opening = playWalkOpen(screen, { map: mapEl, slide: [stepEl, statsEl, screen.querySelector(".walk-actions")] })
    .then(() => { if (!closing) { document.body.classList.add("walking"); map.invalidateSize(); } });
  let closing = false;  // ended during the opening: don't hide the page again

  const map = L.map(mapEl, { zoomControl: true }).setView(legs[0].target, 17);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);
  // Like a map app: once your position is known the map zooms in on you and keeps you in the middle.
  // Dragging the map stops that; the button brings you back.
  const FOLLOW_ZOOM = 17;
  let follow = true;
  const recenter = el("button", { type: "button", class: "walk-recenter", hidden: "", "aria-label": "Back to my position",
    title: "Back to my position", onclick: (e) => {
      L.DomEvent.stopPropagation(e);
      setFollow(true);
      if (me) map.setView(me.getLatLng(), Math.max(map.getZoom(), FOLLOW_ZOOM));
    } }, el("span", { "aria-hidden": "true" }, "◎"));
  const RecenterControl = L.Control.extend({ options: { position: "bottomright" }, onAdd: () => {
    L.DomEvent.disableClickPropagation(recenter);
    return recenter;
  } });
  map.addControl(new RecenterControl());
  function setFollow(on) {
    follow = on;
    recenter.hidden = on || !me;  // nothing to come back to before the first position
  }
  map.on("dragstart", () => setFollow(false));
  // Notices and the arrival card change the map's height: let Leaflet re-measure.
  const resize = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => map.invalidateSize()) : null;
  if (resize) resize.observe(mapEl);

  function showLeg() {
    const leg = follower.current;
    if (routeLine) routeLine.remove();
    if (targetMarker) targetMarker.remove();
    routeLine = L.polyline(leg.geometry, { color: color(leg.kind === "meetup" ? "--a" : "--shared") || "#ff5c8a", weight: 6, opacity: .85 }).addTo(map);
    targetMarker = L.marker(leg.target).addTo(map).bindPopup(leg.name);
    poiLayers.forEach((l) => l.remove());
    poiLayers = (leg.pois || []).map((p) => L.marker([p.lat, p.lon], { icon: L.divIcon({ className: "poi-pin",
      html: POI_ICONS[p.category] || "📍", iconSize: [24, 24] }) }).addTo(map).bindPopup(p.name));
    stepEl.replaceChildren(el("span", { class: "walk-to" }, `${leg.kind === "meetup" ? "To the meeting point" : "To"}: ${leg.name}`),
      el("b", { class: "walk-next" }, formatStep(stepInfo(leg.steps, 0, leg.name)) || ""));
    fallback.href = mapsLink(leg.target[0], leg.target[1]);
    map.invalidateSize();
    // The whole route until we know where you are (and after a new route if you're looking around).
    if (me && follow) map.setView(me.getLatLng(), Math.max(map.getZoom(), FOLLOW_ZOOM));
    else map.fitBounds(routeLine.getBounds(), { padding: [30, 30] });
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
      follower.setRoute(leg.geometry, leg.steps, leg.pois);
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
      leg.id && poiIntros && poiIntros[leg.id] ? introBlock(poiIntros[leg.id]) : null,
      el("div", { class: "row" }, more
        ? el("button", { class: "primary", onclick: () => { follower.nextLeg(); showLeg(); notice(""); } }, `Walk on together to ${follower.legs[follower.leg + 1].name}`)
        : el("button", { class: "primary", onclick: () => finish(true) }, "Finish walk"))));
  }

  function onFix(pos) {
    const fix = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy, t: pos.timestamp / 1000 };
    const ll = [fix.lat, fix.lon];
    facing.onFix({ ...fix, heading: pos.coords.heading, speed: pos.coords.speed });
    const first = !me;
    if (!me) {
      meCircle = L.circle(ll, { radius: fix.accuracy, weight: 1, opacity: .4, fillOpacity: .1 }).addTo(map);
      // A dot until a direction is known, then an arrow pointing the way you face (the map stays north-up).
      me = L.marker(ll, { interactive: false, keyboard: false, zIndexOffset: 1000, icon: L.divIcon({
        className: "walk-me", iconSize: [36, 36], iconAnchor: [18, 18],
        html: '<svg viewBox="-18 -18 36 36" aria-hidden="true"><path class="walk-me-arrow" d="M0 -15 L10 10 L0 4 L-10 10 Z"/>'
            + '<circle class="walk-me-dot" r="8"/></svg>' }) }).addTo(map);
    } else { me.setLatLng(ll); meCircle.setLatLng(ll).setRadius(fix.accuracy); }
    pointArrow();
    if (first) setFollow(follow);  // the button may show from now on
    if (first && follow) map.setView(ll, FOLLOW_ZOOM);  // jump in from the route overview
    else if (follow) map.panTo(ll);
    const ev = follower.update(fix);
    say(promptFor(ev, said));
    const nextText = ev.type === "arrived" ? "" : formatStep(ev.step);
    const nextEl = stepEl.querySelector(".walk-next");
    if (nextEl && nextText !== null && nextEl.textContent !== nextText) nextEl.textContent = nextText;
    if (ev.type === "arrived") statsEl.replaceChildren(el("div", {}, el("b", {}, "✓"), "arrived"), el("div", {}, el("b", {}, `~${WALK.ARRIVE_M} m`), "or closer"));
    else stats(ev.remainingM);
    if (ev.poi) {
      poiShown = ev.poi;
      passed.push({ id: ev.poi.id, name: ev.poi.name, category: ev.poi.category });
      poiEl.replaceChildren(poiCard(ev.poi, () => { poiEl.replaceChildren(); poiShown = null; }));
    } else if (poiShown && distanceM(ll, [poiShown.lat, poiShown.lon]) > 2 * WALK.POI_NEAR_M + WALK.POI_SLACK_M) {
      poiEl.replaceChildren(); poiShown = null;  // walked on
    }
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
    if (canSpeak) speechSynthesis.cancel();
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    if (wakeLock) wakeLock.release().catch(() => {});
    wakeLock = null;
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener(compassEvent, onCompass);
    if (resize) resize.disconnect();
    closing = true;
    document.body.classList.remove("walking");  // the page comes back under the shrinking circle
    screen.querySelectorAll("button").forEach((b) => b.setAttribute("disabled", ""));
    playWalkClose(screen).then(() => { map.remove(); screen.remove(); });
    if (opts.onFinish) opts.onFinish(!!done, {
      minutes: Math.max(1, Math.round((Date.now() - startedAt) / 60000)), places: passed,
      finished_at: new Date().toISOString() });
  }

  loadPoiIntros();
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
  return { follower, finish, opening };
}
