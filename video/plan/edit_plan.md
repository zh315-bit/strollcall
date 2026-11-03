# StrollCall demo video: edit plan (B1)

Target runtime **2:54.4** (2:45–2:55 allowed; revision 3). 1920×1080, 30 fps. Times are in the final video; clip in/out
times are seconds into the recorded file (marks from each recording's `.json`). Recordings: `video/assets/screen/`
(desktop, 1920×1080) and `video/assets/phone/` (1170×2532, shown in a phone frame at about 860 px tall).

Rules carried into every scene: OSM attribution stays visible on every map (it is in the recordings' map
corner; animated maps carry "Route data © OpenStreetMap contributors"); simulated movement carries a
"simulated location" tag; any sped-up span carries "sped up N×"; captions always on (bottom centre, cream pill).

## Numbers used, with sources

| # | Shown / spoken | Value | Source |
|---|---|---|---|
| N1 | Glimmer wish reading, median | 0.55 s ("about half a second") | `benchmarks/2026-10-31-open-weights-run1.md:14` |
| N2 | Muse Spark wish reading, median (same run) | 3.58 s; Glimmer is 3.58 / 0.55 = 6.5× faster ("six and a half times faster than the API") | `benchmarks/2026-10-31-open-weights-run1.md:14` |
| N3 | Map midpoint: minutes for A / B | 6.0 / 10.8 → 4.8 min apart | `video/assets/data/fairness_example.json` → `midpoint.a_min`, `midpoint.b_min` (one-line JSON) |
| N4 | Our meeting point: minutes for A / B | 9.9 / 9.3 → 0.6 min apart; 4.8 / 0.6 = 8 ("an eight-times smaller gap") | same file → `meeting.a_min`, `meeting.b_min`, `meeting.name` = Emma Lazarus |
| N5 | Shared walk on | 14.9 min to Abingdon Square | same file → `destination.shared_min`, `destination.name` |
| N6 | Walking graph size | 139,106 nodes | `benchmarks/2026-10-31-local.md:3` (and `deploy/data/nyc_graph.npz`, 139,106 entries) |
| N7 | Planning time, median (first run) | 0.029 s ("about 29 milliseconds") | `benchmarks/2026-10-31-local.md:16` |
| N8 | Right outcome | 12 of 12 test pairs | `benchmarks/2026-10-31-local.md:13` |
| N9 | Wishes read correctly: Muse Spark vs keyword rules | 10 of 10 vs 7 of 10 | `benchmarks/2026-10-28-ablation-wishes.md:16` |
| N10 | Rejected claim reason (Scene 9) | "unverifiable claim 'quiet'" | `benchmarks/2026-10-30-rejections.md:15` (row 3; the sentence itself was not logged) |
| N11 | Cold start / wish check in A3 | 199 s / 0.76 s | `video/assets/data/glimmer_warm_terminal.jsonl` lines 4–5 (the script's own output) |

Not used: user-test results (none in the repo or data), so Scene 10 has no result cards and VO 9 is cut.

## Voiceover text (filled; revision 3)

Confident, but every claim is in the product or the data. The contrasts are generic ("map apps", "a typical
chatbot") and say only what is true of the category; no competitor is named.

- VO 1a: "I'm Chris. Some afternoons I want to get outside, but I never know where to go."
- VO 1b: "And my friends? Total homebodies. 'We should hang out' never becomes a plan."
- VO 2: "So I built StrollCall. Map apps need a destination. StrollCall starts from how you feel: tell it how long you have and what you're in the mood for, and it plans a walk worth taking, solo or with a friend."
- VO 3: "I just say it. Muse Voice transcribes it, and Muse Glimmer, Meta's open-weights model running on my own H200 on Modal, reads it in about half a second, six and a half times faster than the API. And my location never goes to any model." (N1, N2; H200 from N11's terminal; the start point stays on the server: the page says "Only used to plan this walk. It is not stored.")
- VO 4: "And it doesn't stop at directions. While I walk, the map fills the screen, and my buddy listens. Mid-walk, I ask for a coffee stop: Muse Spark calls a tool, the planner re-routes, and only real, open places come back."
- VO 5: "Walking is better together. One link, no app, no sign-up. My friend taps once, and says what they'd like too."
- VO 6: "Muse Spark balances both of our wishes and explains the trade-off. Splitting the distance isn't fair: the map's midpoint leaves us **4.8** minutes apart. StrollCall splits the walking time instead: just **0.6** minutes apart, an **eight-times** smaller gap." (N3, N4)
- VO 7: "Under the hood, our own walking graph of New York: **139,106** points from OpenStreetMap, planning a walk in about **29** milliseconds. Four Meta models do the human side: Muse Glimmer reads wishes, Muse Spark negotiates and ranks, Muse Image draws the invite, Muse Voice listens." (N6, N7)
- VO 8: "And unlike a typical chatbot, it's built not to make things up. Every evaluation is pre-registered. **12 out of 12** test pairs, all correct. Meta's reading caught every wish, **10 of 10**, where keyword rules caught **7**. And a checker throws out any claim our data can't back up." (N8, N9, N10)
- VO 9: cut (no user-test data).
- VO 10: "StrollCall. Less planning. More walking."

## Timeline

| Time | Scene | Picture | Source clips (in → out) | Animation built | VO |
|---|---|---|---|---|---|
| 0:00–0:08 | 1 Cold open | Illustrated sunny street; blue mascot at a window, then out of a door, blinks; "Step outside." builds word by word at 0:03; green route draws along the sidewalk | – | Scene 1 (style frame `style_scene1.png`) | 1a |
| 0:08–0:16 | 2 Problem | Staged chat (made-up names "Sam", "Jo", "Riley"): "we should hang out sometime" → "yes!!" → "let's plan it" → typing dots fade; calendar flips "3 weeks later…", chat greys; inset: orange mascot under a blanket with a phone | – | chat + calendar + sofa inset | 1b |
| 0:16–0:28 | 3 What it is | Mascots bounce into the logo, "StrollCall" types in (0:16–0:20); green route wipe; desktop browser frame with A1, slow push on the hero; yellow glow on "Plan my walk" as it is clicked | `screen/01_home.mp4` 0.8 → 8.6 (click at 5.82) | logo build, route wipe, browser frame, glow | 2 |
| 0:28–0:50 | 4 Solo by voice | Phone frame: Speak (waveform beside the mic) → transcript (chip "Muse Voice Transcribe") → chips + callout on "Read by Muse Glimmer (open weights, on Modal)" → badge "0.55 s median (evaluation run 1)" → Find my walk → route draws, pins | `phone/02_solo_voice_glimmer.mp4` 1.5 → 23.5, cut to 25.6 → 35.6 (the wait for the plan, 26.2 → 29.0, stays in at real speed) | waveform, chips, callout, badge | 3 |
| 0:50–1:05 | 5 Walking + buddy | `04_walking` 9.5 → 21.0 at 1× (prompts on; tag "simulated location"), callouts on the turn card and minutes left; then `05_buddy_add_stop` 1.0 → 13.0: hold mic, buddy listening → thinking → reply; overlay builds "Muse Spark → add_stop → planner → real, open place"; callout on Undo | `phone/04_walking.mp4` 9.5 → 13.0; `phone/05_buddy_add_stop.mp4` 1.0 → 12.5 | callouts, tool-chain overlay, tag | 4 |
| 1:05–1:25 | 6 With a friend | Split screen: A (blue outline) `06_invite_A` invite card; card flies to B as a paper plane; chip "Illustration by Muse Image"; B (orange) `07_accept_B`: Use my location, Speak, I'm in (ripple); "a few seconds later" tag; the plan arrives on both | `phone/06_invite_A.mp4` 16.5 → 31.7; `phone/07_accept_B.mp4` 0.5 → 16.8; `phone/08_plan_B.mp4` 0.0 → 4.0 | split frame, paper plane, ripple, chips | 5 |
| 1:25–1:45 | 7 Fair meeting point | Two illustrated top-down maps from the real streets and routes: left, both walk to the map midpoint at the same speed, timers to 6.0 and 10.8 min, A taps its foot, bracket "4.8 min apart"; right, both reach Emma Lazarus at 9.9 / 9.3 min, sparkle, then a dashed line to Abingdon Square (14.9 min); at 1:38 cut to `08_plan_B` with callout "Muse Spark balances both wishes" on the trade-off line; end line "Halfway by walking time, not by distance." | `phone/08_plan_B.mp4` 7.0 → 14.0 | Scene 7 (style frame `style_scene7.png`), data-driven | 6 |
| 1:45–2:05 | 8 Under the hood | 1:45 the real Manhattan walking graph (123,160 street segments from `walking_graph_manhattan.json`) draws in green on ink, zooms to one route; 1:52 architecture builds: phone web app → FastAPI → planner on the walking graph; "Meta models" column, four cards in turn; blue mascot points; 2:00 A3 with a highlight sweep on the BF16 / H200 line | `screen/03_terminal_glimmer.mp4` 10.5 → 15.5 (READY line appears; the "sped up 20x" tag of the cold start is in the clip) | graph draw, architecture, sweep | 7 |
| 2:05–2:20 | 9 Honest evaluation | Stamp "Pre-registered: cases committed before each run"; stat cards count up: 12/12 right outcome; bars 10/10 vs 7/10 (Muse Spark vs keyword rules); 0.55 s vs 3.58 s (Glimmer vs Muse Spark); honesty check: an illustrative sentence "This street is quiet." struck through, tag "rejected: unverifiable claim 'quiet'" (the real checker reason), replaced by "Quiet, as you asked." (the rule allows "quiet" only when tied to a person's wish); label "illustration of a real rule"; glimpse of `10_reports_1` | `screen/10_reports_1.mp4` 3.0 → 6.0 | stamp, counters, bars, strike-through | 8 |
| 2:20–2:42 | 10 Out in the city | Golden-hour illustrated city: blue mascot walks past a park with its phone; the two arrive at a corner from opposite streets and wave; walk together; a cafe table with two cups. Music only (no result cards: no data) | – | montage | – |
| 2:42–2:52 | 11 End card | Cream; mascots walk in, meet, the logo forms; "Less planning. More walking."; strollcall.onrender.com and github.com/zh315-bit/strollcall; "Built with Muse Spark · Muse Glimmer (open weights) · Muse Image · Muse Voice"; hold 3 s, fade to cream | – | Scene 11 (style frame `style_scene11.png`) | 10 |

## Sound

- VO: ElevenLabs TTS (`eleven_v4`) in the narrator's own cloned voice, at the narrator's request (revision 2 onward).
- Music: one light acoustic track at about 12% under the voice, ducked on key lines, a small lift in the last 8 s. Suggestion: generate it with ElevenLabs Music (our key has the scope) so it is cleared for use; or you supply a royalty-free track.
- UI sounds: soft clicks on taps and a chime on "plan arrived", synthesized locally.
- The app's own spoken prompts (captured MP3s from `04_walking`, `05_buddy_add_stop`) play under Scene 5, ducked under the VO.

## Build (B3)

HTML/SVG scenes in `video/source/anim/` driven by a time variable, rendered frame by frame in headless Chrome
(Playwright), recordings composited in the same page as `<video>` elements seeked per frame, then muxed with
the audio by ffmpeg. Data scenes read `video/assets/data/` directly.

## Revision 2 (after the first preview): picture follows the words

Feedback: the picture felt stiff, and several moments did not match the voice. Changes:

- **Word-level sync.** ElevenLabs forced alignment gives every voiceover word's start and end
  (`video/assets/vo_tts/words.json`, `source/audio/align.py`). Each voiceover file is cut into phrases between
  words and each phrase is placed on its picture beat (`source/anim/beats.json`, shared by the picture, the
  captions and the mix). Examples: "Muse Voice transcribes it" lands as the transcript appears; "Muse Glimmer"
  as the chips come in; "4.8 minutes apart" as the 4.8 pill appears; each Meta model card as its name is said;
  "12 of 12" as the counter lands. Captions now follow the spoken words phrase by phrase.
- **The real voices in the shots.** The wish heard in the Speak shots is the WAV Chrome's fake microphone played
  into the app's real Speak button; the app's own spoken lines ("Voice prompts on.", the turn prompt, the
  buddy's reply about the coffee stop) were re-captured from `/api/voice/speak` in a new take of A4/A5
  (the first take's audio files were empty). They play at the moments the app played them.
- **Motion.** Devices float and push in on the beats; callouts pulse a ring on their target, draw a leader
  line and lift their label; chips spring in; drifting pastel shapes behind every product shot; mascots blink,
  squash and stretch, react (listening, thinking, happy) and a small blue guide sits beside the phone; scenes
  push into each other with a green route line (white dashed centre, a pin) along the seam.
- **Timeline** (2:51.7): s1 8 · s2 8 · s3 12 · s4 23.6 · s5 25.3 · s6 18.5 · s7 20 · s8 20.8 · s9 15 · s10 11 · s11 9.5.
  Scene 2 now opens on the orange homebody (with "And my friends? Mostly homebodies"), then the chat
  (with "'We should hang out'"). Scene 3 underlines the page's own "Tell us how long you have…" as it is said,
  clicks "Plan my walk" on "worth taking", and points at "Just me" / "With a friend" as they are said.
  Scene 8 shows the real terminal (A3) beside the Muse Glimmer card instead of after the cards.
  Scene 10 is shorter (no data to show) with parallax, falling leaves and the two mascots meeting.

## Revision 3: the copy says what no one else does

New voiceover (above), re-generated in the cloned voice and re-aligned word by word; every phrase placed on its
beat again (`beats.json`). Timeline (2:54.4): s1 8 · s2 8 · s3 15.2 · s4 23.4 · s5 24 · s6 18.8 · s7 19.6 · s8 21.1 ·
s9 18.8 · s10 9 · s11 8.5. Picture changes that go with it:

- Scene 3 opens with two cards, "Map apps: Where to? · start from a destination" vs "StrollCall: '30 quiet
  minutes, coffee at the end' · start from how you feel", on "Map apps need a destination. StrollCall starts from
  how you feel".
- Scene 4 adds "6.5x faster than Muse Spark via the API (3.58 s)" and "your start point stays on our server:
  never sent to a model". The "Find my walk" callout follows the button when the tap folds "Near you" away.
- Scene 6: "one link · no app · no sign-up" on "One link".
- Scene 7: the 4.8 and 0.6 pills are in as each number is said; "8x smaller gap: 4.8 min vs 0.6 min" replaces the
  title on "eight-times".
- Scene 8: the OSM credit moves to the top right (clear of the captions); the terminal inset is a little smaller
  so its "sped up 20x" tag clears the captions.
- Scene 9 opens with "A typical chatbot: can make up places · can make up numbers · sounds sure either way" vs
  "StrollCall: places: OpenStreetMap · numbers: measured · claims: checked first", then the stamp, the report
  (whole page, then the zoom and ring on "12 out of 12"), the counters on their numbers and the checker.
- The buddy's spoken reply is cut after "…per OpenStreetMap." (a whole sentence) to keep the runtime.
