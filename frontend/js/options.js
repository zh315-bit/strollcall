// "More options ▾" on the New walk page: only what the planner can honor with map data
// (backend/app/services/options.py). Collapsed by default; set options show as chips on the bar.
// Each option is the user's own choice, a guess from the wish ("from your wish"), or the default.
// The user's own choices win over the wish and are remembered on this device.

const OPTION_DEFAULTS = { shape: "one_way", pace: "normal", pass_kinds: [], avoid: [], stops: 0, must_be_open: false };
const PACE_M_PER_MIN = { relaxed: 65, normal: 80, brisk: 95 };
const PASS_KINDS = [["parks", "Parks"], ["waterfront", "Waterfront"], ["landmarks", "Landmarks"],
                    ["public_art", "Public art"], ["bookstores", "Bookstores"], ["markets", "Markets"]];
const AVOIDS = [["stairs", "Stairs"], ["busy_avenues", "Busy avenues"], ["transit_hubs", "Major transit hubs"]];
const OPTIONS_KEY = "strollcall:options";

// What the wish says about each option, or nothing. The parsed intent (Muse Spark) gives vibes,
// avoid and hard constraints; pace, loop and stops are read from the words themselves.
function optionsFromWish(intent, text) {
  const t = (text || "").toLowerCase(), out = {};
  const words = (re) => re.test(t);
  const avoid = (intent.avoid || []).join(" ").toLowerCase();
  const vibes = (intent.vibes || []).join(" ").toLowerCase();
  const ends = intent.endpoint_type || "";
  if (words(/\b(loop|round trip|circle back|back (to )?(where i|my|the) start|back home|come back)\b/)) out.shape = "loop";
  if (words(/\b(slow(ly)?|leisurely|relaxed|easy pace|take it easy|no rush)\b/)) out.pace = "relaxed";
  else if (words(/\b(brisk(ly)?|fast|quick pace|power walk|exercise|workout)\b/)) out.pace = "brisk";
  const kinds = [];
  if ((words(/\bparks?\b|\bgreen\b|\btrees\b/) || /green/.test(vibes)) && ends !== "park") kinds.push("parks");
  if (words(/\b(water(front)?|river|harbou?r|pier|esplanade|seaside|by the water)\b/)) kinds.push("waterfront");
  if ((words(/\b(landmarks?|historic|monuments?|architecture|old buildings)\b/) || /historic/.test(vibes)) && ends !== "landmark") kinds.push("landmarks");
  if (words(/\b(public art|murals?|sculptures?|street art|statues?)\b/)) kinds.push("public_art");
  if (words(/\b(book ?stores?|bookshops?)\b/) && ends !== "bookstore") kinds.push("bookstores");
  if (words(/\b(markets?|farmers'? market|greenmarket)\b/)) kinds.push("markets");
  if (kinds.length) out.pass_kinds = kinds;
  const av = [];
  if (/stair|steps/.test(avoid) || words(/\bno (stairs|steps)\b/)) av.push("stairs");
  if (/traffic|busy|avenue|car|loud|noise/.test(avoid)) av.push("busy_avenues");
  if (/crowd|tourist|transit|station/.test(avoid)) av.push("transit_hubs");
  if (av.length) out.avoid = av;
  const n = t.match(/\b(one|two|three|1|2|3) stops?\b/);
  if (n) out.stops = { one: 1, two: 2, three: 3 }[n[1]] || +n[1];
  if ((intent.hard_constraints || []).some((c) => /open/i.test(c))) out.must_be_open = true;
  return out;
}

function moreOptions(container) {
  const value = { ...OPTION_DEFAULTS }, source = {};
  let mode = "solo";
  try {
    const saved = JSON.parse(localStorage.getItem(OPTIONS_KEY) || "{}");
    for (const [k, v] of Object.entries(saved)) if (k in OPTION_DEFAULTS) { value[k] = v; source[k] = "user"; }
  } catch (e) { /* nothing remembered */ }

  const save = () => {
    const mine = Object.fromEntries(Object.keys(OPTION_DEFAULTS).filter((k) => source[k] === "user").map((k) => [k, value[k]]));
    try { localStorage.setItem(OPTIONS_KEY, JSON.stringify(mine)); } catch (e) { /* fine without it */ }
  };
  const setByUser = (k, v) => {
    const a = document.activeElement, focus = a && a.name ? `input[name="${a.name}"][value="${a.value}"]` : null;
    value[k] = v; source[k] = "user"; save(); render();
    if (focus) { const again = body.querySelector(focus); if (again) again.focus(); }  // the panel was redrawn
  };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  const details = el("details", { class: "more-options" });
  const chipsEl = el("span", { class: "opt-chips" });
  const body = el("div", { class: "opt-body" });
  details.append(el("summary", {}, el("span", { class: "opt-title" }, "More options ", el("span", { class: "opt-caret", "aria-hidden": "true" }, "▾")), chipsEl), body);
  container.replaceChildren(details);

  const tag = (k) => (source[k] === "wish" ? el("span", { class: "opt-wish" }, "from your wish") : null);
  const radios = (k, name, choices) => el("div", { class: "opt-choices", role: "radiogroup", "aria-label": name },
    choices.map(([v, label]) => el("label", { class: "opt-pill" + (same(value[k], v) ? " on" : "") },
      el("input", { type: "radio", name: `opt-${k}`, value: String(v), checked: same(value[k], v) ? "" : null,
        onchange: () => setByUser(k, v) }), label)));
  const checks = (k, choices) => el("div", { class: "opt-choices" },
    choices.map(([v, label]) => el("label", { class: "opt-pill" + (value[k].includes(v) ? " on" : "") },
      el("input", { type: "checkbox", name: `opt-${k}`, value: v, checked: value[k].includes(v) ? "" : null,
        onchange: (e) => setByUser(k, e.target.checked ? [...value[k], v] : value[k].filter((x) => x !== v)) }), label)));
  const group = (k, title, control, note) => el("fieldset", { class: "opt-group" },
    el("legend", {}, title, tag(k)), control, note ? el("p", { class: "muted small" }, note) : null);

  function chips() {
    const out = [];
    if (mode === "solo" && value.shape === "loop") out.push("Loop");
    if (value.pace !== "normal") out.push(`${value.pace[0].toUpperCase()}${value.pace.slice(1)} pace`);
    if (value.pass_kinds.length) out.push("Pass " + value.pass_kinds.map((k) => PASS_KINDS.find((p) => p[0] === k)[1].toLowerCase()).join(", "));
    for (const a of value.avoid) out.push(`Avoid ${AVOIDS.find((x) => x[0] === a)[1].toLowerCase()}`);
    if (value.stops) out.push(`${value.stops} stop${value.stops > 1 ? "s" : ""}`);
    if (value.must_be_open) out.push("Open on arrival");
    return out.map((t) => el("span", { class: "chip opt-chip" }, t));
  }

  function render() {
    chipsEl.replaceChildren(...chips());
    const any = Object.keys(OPTION_DEFAULTS).some((k) => source[k] === "user");
    body.replaceChildren(...[
      mode === "solo" ? group("shape", "Route shape", radios("shape", "Route shape",
        [["loop", "Loop back to start"], ["one_way", "End somewhere else"]])) : null,
      group("pace", "Pace", radios("pace", "Pace", [["relaxed", "Relaxed"], ["normal", "Normal"], ["brisk", "Brisk"]]),
        `Walking times use ${PACE_M_PER_MIN[value.pace]} m a minute.`),
      group("pass_kinds", "Pass by", checks("pass_kinds", PASS_KINDS), "A wish, not a must: walks that pass more of these come first."),
      group("avoid", "Avoid", checks("avoid", AVOIDS),
        "Based on map data, which can be incomplete: we can't promise a step-free or accessible route."),
      group("stops", "Stops on the way", radios("stops", "Stops on the way", [[0, "0"], [1, "1"], [2, "2"], [3, "3"]]),
        "Places right on the route, so no detour."),
      el("fieldset", { class: "opt-group" }, el("label", { class: "opt-check" },
        el("input", { type: "checkbox", name: "opt-must_be_open", value: "1", checked: value.must_be_open ? "" : null, onchange: (e) => setByUser("must_be_open", e.target.checked) }),
        " Destination must be open", tag("must_be_open")),
        el("p", { class: "muted small" }, "Only places whose OpenStreetMap opening hours say open when you arrive.")),
      mode === "pair" ? el("p", { class: "muted small" }, "With a friend these apply to your side of the walk.") : null,
      any ? el("button", { type: "button", class: "opt-reset", onclick: () => {
        for (const k of Object.keys(OPTION_DEFAULTS)) if (source[k] === "user") { value[k] = OPTION_DEFAULTS[k]; delete source[k]; }
        save(); render();
      } }, "Reset my choices") : null].filter(Boolean));
  }

  render();
  return {
    // The parsed wish: options it implies, unless the user set them by hand. Earlier guesses the
    // new wish no longer implies go back to the default.
    fromWish(intent, text) {
      const guess = optionsFromWish(intent, text);
      for (const k of Object.keys(OPTION_DEFAULTS)) {
        if (source[k] === "user") continue;
        if (k in guess && !same(guess[k], OPTION_DEFAULTS[k])) { value[k] = guess[k]; source[k] = "wish"; }
        else if (source[k] === "wish") { value[k] = OPTION_DEFAULTS[k]; delete source[k]; }
      }
      if (Object.values(source).includes("wish")) details.open = true;
      render();
    },
    setMode(m) { mode = m; render(); },
    // What the planner gets: no route shape with a friend.
    value() { return { ...value, shape: mode === "solo" ? value.shape : "one_way",
                       pass_kinds: [...value.pass_kinds], avoid: [...value.avoid] }; },
    mPerMin() { return PACE_M_PER_MIN[value.pace]; },
  };
}

if (typeof module !== "undefined") module.exports = { optionsFromWish, OPTION_DEFAULTS };
