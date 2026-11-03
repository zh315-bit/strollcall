# StrollCall demo video: edit plan (B1)

Target runtime **2:52** (2:45–2:55 allowed). 1920×1080, 30 fps. Times are in the final video; clip in/out
times are seconds into the recorded file (marks from each recording's `.json`). Recordings: `video/assets/screen/`
(desktop, 1920×1080) and `video/assets/phone/` (1170×2532, shown in a phone frame at about 860 px tall).

Rules carried into every scene: OSM attribution stays visible on every map (it is in the recordings' map
corner; animated maps carry "Route data © OpenStreetMap contributors"); simulated movement carries a
"simulated location" tag; any sped-up span carries "sped up N×"; captions always on (bottom centre, cream pill).

## Numbers used, with sources

| # | Shown / spoken | Value | Source |
|---|---|---|---|
| N1 | Glimmer wish reading, median | 0.55 s ("about half a second") | `benchmarks/2026-10-31-open-weights-run1.md:14` |
| N2 | Muse Spark wish reading, median (same run) | 3.58 s | `benchmarks/2026-10-31-open-weights-run1.md:14` |
| N3 | Map midpoint: minutes for A / B | 6.0 / 10.8 → 4.8 min apart | `video/assets/data/fairness_example.json` → `midpoint.a_min`, `midpoint.b_min` (one-line JSON) |
| N4 | Our meeting point: minutes for A / B | 9.9 / 9.3 → 0.6 min apart ("within a minute") | same file → `meeting.a_min`, `meeting.b_min`, `meeting.name` = Emma Lazarus |
| N5 | Shared walk on | 14.9 min to Abingdon Square | same file → `destination.shared_min`, `destination.name` |
| N6 | Walking graph size | 139,106 nodes | `benchmarks/2026-10-31-local.md:3` (and `deploy/data/nyc_graph.npz`, 139,106 entries) |
| N7 | Planning time, median (first run) | 0.029 s ("milliseconds") | `benchmarks/2026-10-31-local.md:16` |
| N8 | Right outcome | 12 of 12 test pairs | `benchmarks/2026-10-31-local.md:13` |
| N9 | Wishes read correctly: Muse Spark vs keyword rules | 10 of 10 vs 7 of 10 | `benchmarks/2026-10-28-ablation-wishes.md:16` |
| N10 | Rejected claim reason (Scene 9) | "unverifiable claim 'quiet'" | `benchmarks/2026-10-30-rejections.md:15` (row 3; the sentence itself was not logged) |
| N11 | Cold start / wish check in A3 | 199 s / 0.76 s | `video/assets/data/glimmer_warm_terminal.jsonl` lines 4–5 (the script's own output) |

Not used: user-test results (none in the repo or data), so Scene 10 has no result cards and VO 9 is cut.

## Voiceover text (filled)

- VO 1a: "I'm Chris. Some afternoons I want to go outside, but I don't know where to go."
- VO 1b: "And my friends? Mostly homebodies. 'We should hang out' never turns into a plan."
- VO 2: "So I built StrollCall. Tell it how long you have and what you feel like, and it plans a short walk worth taking: on your own, or with a friend."
- VO 3: "I just say what I want. Muse Voice transcribes it, and Muse Glimmer, an open-weights model I host on Modal, turns it into a plan the route engine understands, in about half a second." (N1: 0.55 s median)
- VO 4: "While I walk, the map fills the screen, and my walking buddy listens. When I ask for a coffee stop, Muse Spark picks a tool, the planner re-routes, and only real, open places come back."
- VO 5: "Walking is better with someone. I send one link. My friend doesn't need an app: one tap, and they can say what they'd like too."
- VO 6: "Muse Spark balances both of our wishes and explains the trade-off. And the meeting point is fair by walking time, not by distance on a map: here, the map's midpoint leaves us **4.8** minutes apart; ours gets us there within a minute." (N3, N4)
- VO 7: "Under the hood: a walking graph of New York with **139,106** intersections, built from OpenStreetMap, plans in milliseconds. Meta models handle the human side: Muse Glimmer reads wishes, Muse Spark negotiates and ranks, Muse Image draws the invite, Muse Voice listens." (N6, N7) **Open question:** the graph has 139,106 *nodes*; not all are intersections. Suggested: "…with 139,106 points…", your call.
- VO 8: "Every evaluation was committed before it ran. **12 of 12** test pairs got the right outcome. Meta's reading caught **10 of 10** wishes, against **7** for keyword rules. And a checker throws out any claim our data can't back up." (N8, N9)
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
| 2:05–2:20 | 9 Honest evaluation | Stamp "Pre-registered: cases committed before each run"; stat cards count up: 12/12 right outcome; bars 10/10 vs 7/10 (Muse Spark vs keyword rules); 0.55 s vs 3.58 s (Glimmer vs Muse Spark); honesty check: an illustrative sentence "This street is quiet." struck through, tag "rejected: unverifiable claim 'quiet'" (the real checker reason), replaced by "Quiet, as B asked."; label "illustration of a real rule"; glimpse of `10_reports_1` | `screen/10_reports_1.mp4` 3.0 → 6.0 | stamp, counters, bars, strike-through | 8 |
| 2:20–2:42 | 10 Out in the city | Golden-hour illustrated city: blue mascot walks past a park with its phone; the two arrive at a corner from opposite streets and wave; walk together; a cafe table with two cups. Music only (no result cards: no data) | – | montage | – |
| 2:42–2:52 | 11 End card | Cream; mascots walk in, meet, the logo forms; "Less planning. More walking."; strollcall.onrender.com and github.com/zh315-bit/strollcall; "Built with Muse Spark · Muse Glimmer (open weights) · Muse Image · Muse Voice"; hold 3 s, fade to cream | – | Scene 11 (style frame `style_scene11.png`) | 10 |

## Sound

- VO: TTS (ElevenLabs, a premade warm English voice, never a clone), only with your OK.
- Music: one light acoustic track at about 12% under the voice, ducked on key lines, a small lift in the last 8 s. Suggestion: generate it with ElevenLabs Music (our key has the scope) so it is cleared for use; or you supply a royalty-free track.
- UI sounds: soft clicks on taps and a chime on "plan arrived", synthesized locally.
- The app's own spoken prompts (captured MP3s from `04_walking`, `05_buddy_add_stop`) play under Scene 5, ducked under the VO.

## Build (B3)

HTML/SVG scenes in `video/source/anim/` driven by a time variable, rendered frame by frame in headless Chrome
(Playwright), recordings composited in the same page as `<video>` elements seeked per frame, then muxed with
the audio by ffmpeg. Data scenes read `video/assets/data/` directly.
