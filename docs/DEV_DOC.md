# StrollCall Development Doc

Oct 28, 2026 · @xiaohutongxue

Final execution version. It merges StrollCall 2.0 (two-sided negotiation, clear time semantics, honest fallbacks, ablation) with a scope cut for one developer in 8 days. Tagline: *Less planning. More meeting.*

## 1. Overview

StrollCall turns "we should hang out sometime" into a real walk. A proposes a walk in one sentence and shares a link; B accepts with one tap, and StrollCall finds a fair meetup point and a shared walk to a destination with a reward.

**Core innovation:** socially aware two-sided negotiation combined with walk-time-fair meetup optimization. Meta models interpret and reconcile human preferences and explain trade-offs; a deterministic engine checks geography, timing and constraints.

**Problems we solve**

- Friends want to meet but stall in the group chat deciding where and when.
- Homebodies lack a reason to go out; an invite from a friend is the strongest one, so accepting must be nearly effortless.
- A geographic midpoint is not a fair walking-time midpoint.
- Typical route tools optimize for one person, not two.

**Target users**: college students and young professionals in walkable neighborhoods; test area New York City. Two people, two origins, one shared route.

**Success definition**: on two phones, A creates an invite → B opens and accepts → both see the same feasible plan → each opens their leg in a map app. No hardcoded routes or faked results.

| Item | Detail |
| --- | --- |
| Event | Meta Global AI Developer Hackathon |
| Track / theme | Indie developer · Build for Your World |
| Deadline | 2026-11-04 21:00 ET, no late entries (internal target 18:00) |
| Stage 1 (pass / fail) | Fits a theme + reasonable use of Meta Model API / open-weights models |
| Stage 2 (scored) | Impact 30% · Meta tool use 25% · Technical depth and execution 20% · Demo 25% |
| Finals | Top 5 per track; judging Nov 5–8, Top 10 announced Nov 9 at noon |
| Submission | Project on the Cerebral Valley portal + 3-minute demo video + public repo; all participants listed |

**Scoring strategy**: Impact (30%) is the largest weight, so the project needs evidence from real users, not only a story. Meta tool use (25%) rewards several Meta models used where each one clearly belongs; decorative use is avoided. StrollCall is framed as a social and lifestyle product, never as a health or mental-health intervention, because AI medical advice is a banned category.

## 2. Scope

P0 is one complete two-person flow; P1 starts only after P0 passes an end-to-end test on two phones.

**P0: must ship**

- [ ] Mobile web page where A describes a walk by typing or speaking (Muse Voice Transcribe) and picks a start point.
- [ ] Meta model parses A's text into a validated `WalkIntent`; A can edit the parsed chips.
- [ ] Share link with a random token and expiry, plus an invite card: short Meta-generated text and a Muse Image illustration (template fallback for both).
- [ ] B opens the link, shares location in one tap; preference is optional, typed or spoken.
- [ ] Meta model reconciles A's and B's preferences into a `JointPreference` and states the trade-offs.
- [ ] Real POIs (Overpass) and real walking legs (ORS); 3 feasible candidate plans scored for fairness + shared interest.
- [ ] Plan view: both legs, meetup point, shared leg, destination, walking times, and why it was chosen.
- [ ] Map-app links for each leg; a clear message when no feasible plan exists.
- [ ] A's page polls invite status and updates when B accepts and the plan is ready.
- [ ] Spend guard: a per-day budget cap on Meta calls that switches to mocks when reached.

**P1: only after P0 works end to end**

- [ ] Switch between the 3 candidates ("quieter", "shorter", "more coffee").
- [ ] Privacy mode: parse location-bearing text with the open-weights Muse Glimmer on our own server, so coordinates never leave it.
- [ ] One-sentence route story.
- [ ] Secret destination revealed at the meetup point.

**Out of scope**: native apps, accounts, friend lists, 3+ people, live GPS tracking, weather nudges, photo check-in / SAM, payments, turn-by-turn navigation, encrypted storage, rate limiting.

## 3. User flows

B's path must take one tap plus location permission; everything else is optional, because B is often the one who would rather stay home.

**Flow A: create the invite**

1. A types or says "25 minutes, quiet streets, coffee at the end" (speech goes through Muse Voice Transcribe) and picks a start point on the map.
2. The Meta model extracts preferences; A can edit the chips.
3. A gets a share link with an invite card (text + Muse Image illustration) and sends it. No two-person route is shown yet, since B's origin is unknown.
4. A's page shows "Waiting for B" and polls the invite status every 5 seconds.

**Flow B: accept the invite**

1. B opens the link in a phone browser and sees A's walk preferences (not A's exact origin) and a privacy note.
2. B taps "I'm in" and allows location; an optional text or voice input takes a preference such as "prefer a park, avoid busy streets".
3. Planning starts automatically; both pages show the chosen plan, the trade-off explanation and walking times.
4. Either person confirms and opens their leg in a map app.

**States**: `pending → planning → proposed → confirmed → expired`. Errors: `location_missing`, `no_feasible_plan`, `routing_unavailable`, `model_unavailable`. "Accepted" never means "route ready".

**Example explanation**: "Meet at the east entrance of the park: A walks about 8 min, B about 9 min. The shared 14-minute walk favors green space (B) and ends at a quiet cafe (A). It was the fairest of 3 walkable candidates."

## 4. Architecture and tech stack

A mobile web frontend talks to one FastAPI backend; planner.py decides what is feasible, and intent.py / explain.py are the only places a Meta model is called.

&#91;embedded content: System architecture · six backend modules, three external services\]

Every external service sits behind a provider with a mock twin, so planner work never blocks on an API outage.

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | Python 3.11 + FastAPI + Pydantic v2 + httpx | Familiar; schema validation for model output |
| LLM client | OpenAI Python SDK, base URL and model IDs from env | Meta Model API is OpenAI-compatible |
| Voice | Browser MediaRecorder → Muse Voice Transcribe | Speaking is easier than typing on a phone |
| Storage | SQLite | Enough at demo scale |
| Frontend | Plain HTML/JS + Leaflet + OSM tiles | No build step; opens in a phone browser |
| Tests | pytest + fixtures for NYC origins, places, routes | Offline development and repeatable metrics |
| Coding agent | Muse Code | Meta's own tool; counts toward Meta tool use |
| Deploy | Render or Modal, HTTPS | Submission needs a public link |

**Project structure**

```text
strollcall/
├── backend/app/
│   ├── main.py
│   ├── api/{intents,invites}.py
│   ├── models/{schemas,db}.py
│   ├── services/{intent,places,routing,planner,explain}.py
│   └── providers/{meta,overpass,ors,mock}.py
├── backend/tests/
├── frontend/{index,invite,plan}.html + js/
├── fixtures/{nyc_origins,sample_places,sample_routes}.json
├── scripts/{smoke_test,benchmark}.py
├── .env.example
└── README.md
```

## 5. Meta model usage

Meta tool use is 25% of the score, so StrollCall uses four Meta models plus Muse Code, each where it clearly belongs. Two-person negotiation remains the core job: reconciling two people's free-text preferences and explaining the compromise is something a deterministic scorer cannot do.

| Function | Meta tool | Output | Deterministic check | Priority |
| --- | --- | --- | --- | --- |
| Intent parsing | Muse Spark | `WalkIntent` JSON from free text | Pydantic schema, bounds, defaults | P0 |
| Two-person negotiation | Muse Spark | `JointPreference` + trade-off text | Never overrides a hard constraint | P0 |
| Candidate ranking | Muse Spark | Ranked IDs + rationale | Only supplied candidates; no invented POIs or times | P0 |
| Voice input | Muse Voice Transcribe | Transcript of A's or B's spoken preference | Shown to the user for editing before parsing | P0 |
| Invite card | Muse Spark (text) + Muse Image (illustration) | Card text + image | Length check; template fallback | P0 |
| Privacy mode | Muse Glimmer (open weights, self-hosted) | `WalkIntent` parsed without sending coordinates out | Same schema as the API path | P1 |
| Development | Muse Code | The codebase itself | Noted in the README | Throughout |

SAM 3.1 and Muse Wonder are not used: they have no natural role in StrollCall, and forcing them in would read as decorative.

**Integration**

- Base URL `https://api.meta.ai/v1` (documented by Meta), Bearer auth with `MODEL_API_KEY` passed explicitly to the OpenAI SDK. API calls require a card on file.
- Model IDs from env. Verify `muse-spark-1.3`, the Muse Image ID and the Voice Transcribe endpoint in the console docs (dev.meta.ai/docs/models) before relying on them; fall back to `muse-spark-1.2`.
- The Billing page's Spend Limit only sends an alert, it does not stop calls. The adapter therefore counts cost per call and enforces its own daily cap (default $15); past the cap it switches to mocks and logs it.
- No precise user locations go to the `-contributor` training tier. Send place features, not raw coordinates, wherever possible.

**Prompt rules**

- Extract only what the user said; mark stated vs inferred preferences.
- Never invent opening hours, safety, accessibility or crowd levels.
- Score only the candidates provided; return JSON with confidence / unknown fields.
- Hard constraints always beat narrative appeal.

## 6. Planning algorithm

The planner enumerates a small bounded set of candidates and scores them; the time budget covers the whole outing from simultaneous departure to arrival at the destination.

**6.1 Time semantics** (meetup point m, destination e; MVP assumes A and B leave at the same time)

- tA = walk(A, m), tB = walk(B, m), tShared = walk(m, e)
- elapsed = max(tA, tB) + tShared
- gap = |tA − tB|

**6.2 Candidate generation**

1. Take both origins (browser location with permission, or a picked point).
2. Pull meetup candidates (intersections, park entrances, landmarks) around the walking-time middle between A and B, plus destination candidates (cafes, bookstores, parks) from Overpass.
3. Drop duplicates, unsuitable categories and destinations known to be closed.
4. Bound the set: 5–10 meetup points × 2–4 destinations. No 40 × 40 matrix until the ORS quota is verified.
5. Compute tA, tB and tShared with ORS for that set.
6. Hard constraints: route exists; elapsed ≤ duration + 3 min; gap ≤ 5 min; no forbidden destination; open status confirmed when the user requires it.
7. Score feasible candidates, keep the top 3, and let the Meta model rank and explain them.

**6.3 Score** (all terms normalized to 0–1 before weighting)

```latex
\text{score}(c) = w_1\,\text{fit}(c) - w_2\,\text{gap}(c) - w_3\,\text{timeDev}(c) - w_4\,\text{detour}(c) - w_5\,\text{uncertainty}(c)
```

- fit: preference fit from POI features and the joint preference.
- uncertainty: penalizes unknown opening hours and unverified attributes.
- Fairness (gap) is measured in minutes, not described by the model.
- Deterministic tie-breaking; cache legs by rounded coordinates + profile.

**6.4 Fallback ladder**

1. Full planning with Meta negotiation and ranking.
2. Deterministic ranking only, if the Meta call fails.
3. One fixed meetup point (park entrance nearest the walking-time middle) + one destination, if optimization times out.
4. If routing is unavailable: show "Unable to verify walking route" and an external map search. Never draw a fabricated route.

## 7. API and data model

Five invite endpoints cover the whole flow; accepting an invite triggers planning, so there is no separate plan call.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /api/intents/parse | Parse A's or B's text into `WalkIntent` |
| POST | /api/invites | Create a pending invite + invite text, return share link |
| GET | /api/invites/{token} | Invite view; A polls this for status and plan |
| POST | /api/invites/{token}/accept | Store B's origin + optional preference, start planning |
| POST | /api/invites/{token}/confirm | Choose a candidate (default: top one) and confirm |
| GET | /health | Status of each provider |

**Security (minimal, enough for a demo)**: random unguessable token, 24-hour expiry, server-side validation, keys in env only. The invite view never shows A's exact origin. Origins are deleted when the invite expires and never logged.

**Data model**

```python
class WalkIntent(BaseModel):
    duration_min: int = Field(ge=15, le=60)
    vibes: list[str] = []
    endpoint_type: str | None = None
    avoid: list[str] = []
    hard_constraints: list[str] = []

class JointPreference(BaseModel):
    shared_vibes: list[str]
    a_priorities: list[str]
    b_priorities: list[str]
    compromises: list[str]

class RouteLeg(BaseModel):
    geometry: list[tuple[float, float]]
    distance_m: float
    duration_min: float

class MeetupCandidate(BaseModel):
    id: str
    meeting_place_id: str
    endpoint_place_id: str
    a_leg: RouteLeg
    b_leg: RouteLeg
    shared_leg: RouteLeg
    arrival_gap_min: float
    total_elapsed_min: float
    score: float
    rationale: str

class Invite(BaseModel):
    token: str
    status: str            # pending / planning / proposed / confirmed / expired
    expires_at: datetime
    invite_text: str
    a_intent: WalkIntent
    b_intent: WalkIntent | None = None
    candidates: list[MeetupCandidate] = []
    selected_id: str | None = None
    error: str | None = None
```

## 8. 8-day plan

The planner comes first (Oct 29–31) because it is the riskiest part; the invite flow, Muse Image card and voice input land on Nov 1; real users test it Nov 2–3 to give Impact (30%) real evidence.

&#91;embedded content: 8-day plan · 1 checkpoint, 1 deadline\]

**Done criteria per day**

- [ ] Oct 28: repo + `.env.example`; one Meta call returns valid `WalkIntent` JSON; one real NYC walking leg from ORS; mock providers and fixtures; **spend guard with a daily cap** in the Meta adapter; check Muse Image and Voice Transcribe endpoints in the docs.
- [ ] Oct 29–30: on 3 NYC origin pairs, the planner returns a feasible candidate or an honest no-solution; `benchmark.py` runs. Oct 30: Muse Image go / no-go.
- [ ] Oct 31: conflicting preferences visibly change the ranking; no invented place data. **Checkpoint**: 6 pairs, median gap ≤ 3 min; otherwise switch to fallback rung 3.
- [ ] Nov 1: two browser sessions complete create → accept → plan; A's page updates by polling; invite card with Muse Image; voice input via Muse Voice Transcribe on A's and B's pages.
- [ ] Nov 2: on a phone, map shows both legs, meetup point and shared leg with map-app links; that evening, first real walk with a friend, filmed. Feature freeze.
- [ ] Nov 3: public HTTPS deployment tested in a private window and on mobile; 3–5 friend pairs use it for real and answer 3 short questions; demo recorded.
- [ ] Nov 4: final benchmark numbers and user-test results, README, video edit, submitted by 18:00 ET with all links checked in a private window.

**Kill switches**

- Muse Image not working by Oct 30 → drop it; the invite card stays text-only.
- Voice Transcribe not working by end of Nov 1 → drop it; typed input only.
- Meetup planner unstable by Oct 31 → fixed meetup point (fallback rung 3).
- No Google Places → OSM only, opening hours shown as unknown.
- Privacy mode (Muse Glimmer) only if every P0 item is done by Nov 2.
- No new features after Nov 2.

## 9. Testing and metrics

A fixed benchmark of 6 NYC origin pairs and 3 preference-conflict scenarios runs by script every day from Oct 30; the README reports the real numbers, unsolved cases included.

**Functional tests (pytest)**

- Parsing explicit and conflicting preferences; rejecting malformed model JSON and invalid durations.
- Invite expiry and duplicate acceptance.
- Location permission denied.
- Routing timeout, rate limit and empty result.
- No feasible plan within the time budget.

**Metrics**

| Metric | Definition |
| --- | --- |
| Feasibility rate | Share of the 6 pairs that yield a valid plan |
| Fairness | Median and max of the gap between A's and B's walking times, in minutes |
| Time-budget error | Absolute difference between elapsed and target, in minutes |
| Planning latency | Median, cold and cached reported separately |
| End-to-end completion | Invite created → B accepted → plan shown |
| Meta ablation | Same candidates ranked with and without Meta negotiation; how often the top pick changes and which one testers prefer |
| Meta cost per plan | Average Meta API cost of one full invite → plan, from the spend guard's log |

**Real-user test (Impact evidence, Nov 2–3)**

- 3–5 pairs of friends, at least some of whom rarely go out, each use StrollCall once for real.
- Record: time from invite sent to accepted; whether they actually walked; actual vs. planned arrival gap.
- Three questions afterward: Would you have gone out without the invite? Did the meetup point feel fair? Would you use it again?
- Ask permission before filming or quoting anyone; use first names or no names in the video.

The ablation is the evidence for Meta tool use and the user test is the evidence for Impact; show both in the video.

## 10. Risks, compliance and demo

The biggest risks are an unstable planner and API quotas; both have a fallback that still produces an honest, working demo.

| Risk | Mitigation |
| --- | --- |
| Meta model ID or endpoint mismatch | Verify on day 1; configurable adapter + mock provider |
| Meta use looks decorative | Each model has one clear job; negotiation visibly changes the result; ablation numbers in the video |
| Runaway API spend (Spend Limit only alerts) | Own daily cap in the adapter; switch to mocks past it; no unbounded retry loops |
| Planner unstable | Bounded candidates; fallback rung 3 from Oct 31 |
| Muse Image or Voice integration fails | Kill switches on Oct 30 and Nov 1; text-only fallbacks |
| ORS / Overpass quotas | Small candidate set, caching, timeouts, fixture mode |
| Wrong opening hours | Claim only verified hours; otherwise show "unknown" |
| Read as a health product | Social / lifestyle framing only; no claims about loneliness or mental health outcomes |
| B finds accepting too much effort | One tap + location; preference optional, typed or spoken |
| A never learns B accepted | Status polling on A's page |
| Location privacy | Consent prompt, exact origin hidden, deleted on expiry, never logged; Glimmer privacy mode if time allows |
| Unsafe route suggestions | Never claim a route is safe; external map navigation |

**Compliance checklist**

- [ ] Public repo; `.env` in `.gitignore`; no keys or real test-user locations committed.
- [ ] All work done during the event; commit often from day 1 with clear messages. The video shows only features built during the event (otherwise disqualification).
- [ ] Not in a banned category: no medical advice, no basic RAG app, no personality analysis, nothing political.
- [ ] README: where each Meta tool is used (Spark, Image, Voice Transcribe, Glimmer if built, Muse Code) and how outputs are validated; metrics and user-test results with method and limits; a note that no code from earlier projects (e.g. Sous Recall) was reused.
- [ ] Demo link tested in a private window and on mobile.
- [ ] Submit on the Cerebral Valley portal by 18:00 ET Nov 4: project, 3-minute video link and repo link all publicly accessible, all participants listed.

**Demo storyboard (3 minutes)**

| Time | Scene | What it proves | Score it targets |
| --- | --- | --- | --- |
| 0:00–0:20 | "We should hang out" chat that goes nowhere; my friends are homebodies | A real everyday problem | Impact |
| 0:20–0:45 | A says "quiet, coffee, 25 min" into the phone; invite card with a Muse Image illustration | Voice + Spark + Image working together | Meta tool use |
| 0:45–1:05 | B taps "I'm in" and says "green space, avoid traffic" | Low-friction, two-sided input | Impact, Demo |
| 1:05–1:40 | Two legs converge on the map; walking times and gap shown | Geospatial algorithm, measurable fairness | Technical depth |
| 1:40–2:00 | Trade-off explanation; ablation result on screen | Meta negotiation changes the outcome | Meta tool use |
| 2:00–2:40 | Real NYC footage of friends meeting; 2–3 user-test quotes and numbers | It works and people use it | Impact, Demo |
| 2:40–3:00 | Architecture glimpse, metrics, tagline | Technical depth | Technical depth |

**Demo backup**: pre-recorded real walk footage and a clearly labeled fixture mode in case an API is down; fixture output is never presented as live.

**First 6 hours**

1. Create the repo and `.env.example`; open the project in Muse Code.
2. One Meta call with structured output, checked against the console docs.
3. Spend guard: per-call cost log and daily cap in the Meta adapter.
4. Confirm the Muse Image and Voice Transcribe endpoints and pricing in the docs.
5. ORS key + one NYC walking leg.
6. `WalkIntent` and `JointPreference` schemas; mock place and route fixtures.
7. `POST /api/intents/parse` and a stub `POST /api/invites`.
8. Commit.

**Priority rule**: a real two-person walk beats ten unfinished AI features.

## Sources

- [Meta Global AI Developer Hackathon – Cerebral Valley](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)
- [Get started with Meta Model API](https://ai.developer.meta.com/docs)
- [Meta Model API – Models](https://ai.developer.meta.com/docs/models/)
- [Build with Muse Spark (Meta blog)](https://developer.meta.com/ai/resources/blog/build-with-muse-spark/)
- [Participant-compiled rules summary (unofficial)](https://github.com/meta-ai-hackathon/meta-hack)
