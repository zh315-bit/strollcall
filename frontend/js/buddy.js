// The walking buddy: the blue character from the StrollCall logo, bottom left on the walking screen,
// with a speech bubble. Five states match what the companion is doing (design: Walking buddy · states):
//   walking   gentle bounce in step with the walk
//   listening while the mic button is held
//   thinking  while Muse Spark picks a tool and the route updates
//   speaking  while a reply shows (and is read out, when voice is on)
//   arrived   at the meetup point or the end of the walk
// The character is decorative (aria-hidden); the bubble's text is a live region, so screen readers
// hear every reply. The animations are CSS and stop under prefers-reduced-motion.

const BUDDY_STATES = ["walking", "listening", "thinking", "speaking", "arrived"];

// One drawing; each state shows its own eyes, mouth and extras (data-s lists the states a part is in).
const BUDDY_SVG = `<svg viewBox="0 0 100 100" focusable="false">
<g class="b-body">
  <path d="M50 20q-3-10 5-13" fill="none" stroke="#3B7BEA" stroke-width="4" stroke-linecap="round"/>
  <circle cx="57" cy="7" r="5" fill="#FFB3C1"/>
  <circle cx="50" cy="58" r="38" fill="#3B7BEA"/>
  <circle cx="28" cy="65" r="6" fill="#FF9EB0" fill-opacity=".75"/><circle cx="72" cy="65" r="6" fill="#FF9EB0" fill-opacity=".75"/>
  <g data-s="walking speaking"><ellipse cx="38" cy="52" rx="4" ry="5.5" fill="#1F1B3A"/><ellipse cx="62" cy="52" rx="4" ry="5.5" fill="#1F1B3A"/></g>
  <g data-s="listening"><ellipse cx="38" cy="50" rx="5" ry="7" fill="#1F1B3A"/><ellipse cx="62" cy="50" rx="5" ry="7" fill="#1F1B3A"/></g>
  <g data-s="thinking"><ellipse cx="40" cy="47" rx="4" ry="5.5" fill="#1F1B3A"/><ellipse cx="64" cy="47" rx="4" ry="5.5" fill="#1F1B3A"/></g>
  <path data-s="arrived" d="M33 52q5-6 10 0M57 52q5-6 10 0" fill="none" stroke="#1F1B3A" stroke-width="3.5" stroke-linecap="round"/>
  <path data-s="walking" d="M43 67q7 6 14 0" fill="none" stroke="#1F1B3A" stroke-width="3" stroke-linecap="round"/>
  <circle data-s="listening" cx="50" cy="69" r="3.5" fill="#1F1B3A"/>
  <path data-s="thinking" d="M44 69h12" stroke="#1F1B3A" stroke-width="3" stroke-linecap="round"/>
  <ellipse data-s="speaking" class="b-talk" cx="50" cy="69" rx="7" ry="5" fill="#1F1B3A"/>
  <path data-s="arrived" d="M40 65q10 12 20 0z" fill="#1F1B3A"/>
</g>
<g data-s="listening" class="b-waves" fill="none" stroke="#E9B53A" stroke-width="3" stroke-linecap="round">
  <path d="M86 50q3 8 0 16"/><path d="M92 46q5 12 0 24"/>
</g>
<g data-s="thinking" class="b-dots" fill="#B9B2CC"><circle cx="80" cy="18" r="3.5"/><circle cx="89" cy="14" r="3.5"/><circle cx="97" cy="10" r="3"/></g>
<g data-s="arrived" class="b-confetti">
  <rect x="10" y="20" width="6" height="6" rx="1" fill="#FFD970"/><rect x="84" y="28" width="6" height="6" rx="1" fill="#FF9EB0"/>
  <circle cx="20" cy="36" r="3" fill="#22A35A"/><circle cx="90" cy="44" r="3" fill="#FFD970"/>
</g>
</svg>`;

// parts: strings, and {b: "text"} for a bold name. chips: [{label, onclick, primary?}].
function makeBuddy() {
  const face = el("div", { class: "buddy", "data-state": "walking", "aria-hidden": "true" });
  face.innerHTML = BUDDY_SVG;
  const text = el("p", { class: "buddy-text", role: "status", "aria-live": "polite" });
  const chips = el("div", { class: "buddy-chips" });
  const bubble = el("div", { class: "buddy-bubble" }, text, chips);
  const root = el("div", { class: "walk-buddy" }, face, bubble);
  let chipsShown = [];
  return {
    el: root,
    get state() { return face.dataset.state; },
    set(state) { if (BUDDY_STATES.includes(state)) face.dataset.state = state; },
    say(parts, newChips) {
      text.replaceChildren(...[].concat(parts || []).map((p) => (p && p.b ? el("strong", {}, p.b) : String(p))));
      if (newChips) this.chips(newChips);
    },
    chips(list) {
      chipsShown = list || [];
      chips.replaceChildren(...chipsShown.map((c) => el("button", { type: "button", class: `buddy-chip${c.primary ? " primary" : ""}`,
        onclick: c.onclick }, c.label)));
    },
    busy(on) { chips.querySelectorAll("button").forEach((b) => { b.disabled = on; }); },
  };
}
