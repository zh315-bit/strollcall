# StrollCall

*Less planning. More meeting.*

A invites B to a 20–30 minute walk with a link. StrollCall finds a meetup point that is fair in
**walking time** for both, and a shared walk to a destination they both like. Meta models read and
reconcile both people's preferences; a deterministic planner checks that every plan is real and
feasible.

Built for the Meta Global AI Developer Hackathon (Oct 28 – Nov 4, 2026). All code in this
repository was written during the event; no code from earlier projects was reused.

## Status

Backend and planner in progress; frontend not started. See `docs/DEV_DOC.md` for scope and plan,
and `benchmarks/` for measured planner results.

## How Meta models are used

| Job | Model | Output | Deterministic check |
| --- | --- | --- | --- |
| Parse a walk description | Muse Spark (`muse-spark-1.3`) | `WalkIntent` | JSON schema + Pydantic; default on failure |
| Reconcile A's and B's preferences | Muse Spark | `JointPreference` + trade-off | shared vibes must come from both people; never changes time or hard constraints |
| Rank the planner's top 6 | Muse Spark | order + reasons | only the supplied candidates; every number must be a measured fact |
| Speech to text | Muse Voice Transcribe | transcript | WAV format check; user edits before parsing |
| Invite card illustration | Muse Image (24 pictures made ahead of time, picked by theme) | image | model and prompt per file in `frontend/illustrations/manifest.json` |
| Intros of places passed on a walk | Muse Spark (ahead of time, `scripts/make_poi_intros.py`) | at most 2 sentences | only from the place's Wikipedia summary; every number, name, feature and evaluative word must be in that text, else dropped |

Every Meta call goes through a spend guard with a daily cap (`DAILY_BUDGET_USD`); past the cap the
app switches to clearly labelled mock data. API responses say whether data is `meta`, `mock` or
`default`.

## Setup

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # then fill in MODEL_API_KEY (and ORS_API_KEY for the ORS fallback)
```

### Build the local map data (once)

Routing and places run on a local OpenStreetMap snapshot, so the app does not depend on a daily
API quota. Build it once (needs network, a few minutes):

```bash
uv pip install --python .venv/bin/python -r requirements-build.txt
.venv/bin/python scripts/build_graph.py
```

This writes `data/nyc_graph.npz` (walking graph) and `data/nyc_places.json.gz` (places) for
Manhattan, northern Brooklyn, Long Island City and the New Jersey side of the Hudson (Jersey City,
Hoboken and their neighbors). `data/` is not committed.

**Walking speed.** Walking times assume **80 m/min (4.8 km/h)**, deliberately a little slower than
typical routing engines (openrouteservice uses about 5 km/h), to leave room for street crossings and
traffic lights that the graph does not model. Checked against 442 recorded openrouteservice walking
times for the same point pairs (`scripts/validate_local_routing.py`): median absolute difference
**0.83 min**, 90th percentile 1.76 min; local times are about 6% longer, as intended.

Street-corner meetup points ("E 81st St & East End Ave") are named from the drive network, because
New York sidewalks are mapped as separate, unnamed footways.

**Walking guidance.** "Start walking" follows the route in the browser (Geolocation API, screen
Wake Lock): live position, remaining time, the next turn ("In 150 m: Turn left onto E 20th St",
from street names along the graph path), a new route from where you are after 15 s more than 50 m
off it, an arrival card within 40 m, and cards for parks, historic sites, artworks, memorials and
landmarks within ~40 m of the route. The track stays in the phone; only a re-plan sends the
current position, which the server neither stores nor logs. The map-app link stays as a fallback.

### Run

```bash
cd backend && ../.venv/bin/uvicorn app.main:app --reload
```

### Deploy (Render)

The deployed app reads the committed map data in `deploy/data/` (ODbL, see its README).
Web service settings:

- Build: `pip install -r requirements.txt`
- Start: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment: `PYTHON_VERSION=3.11.11`, `GRAPH_PATH=deploy/data/nyc_graph.npz`,
  `PLACES_SNAPSHOT_PATH=deploy/data/nyc_places.json.gz`, `DAILY_BUDGET_USD`, and the secret
  `MODEL_API_KEY` (set it in the dashboard, never in the repo). `ORS_API_KEY` is optional
  (only for start points outside the local map).
- Persistent state: Render free web services have an ephemeral filesystem, so set the secret
  `DATABASE_URL` to a Neon Postgres **pooled** connection string with `sslmode=require`. Tables are
  created on startup. Without `DATABASE_URL` the app uses a local SQLite file (development, tests).

### Tests (offline)

```bash
.venv/bin/python -m pytest
```

Tests run with `USE_MOCKS=true` against recorded fixtures and cannot open network connections.

### Scripts

| Script | What it does |
| --- | --- |
| `scripts/smoke_test.py` | one live call to each external service, prints the recorded Meta spend |
| `scripts/build_graph.py` | builds the local walking graph and place snapshot |
| `scripts/benchmark.py` | runs the planner on the benchmark pairs and writes `benchmarks/<date>.md` |
| `scripts/capture_fixtures.py` | records real API responses into `fixtures/` for offline tests |
| `scripts/warm_cache.py` | pre-fetches Overpass tiles (only needed with `PLACES_PROVIDER=overpass`) |
| `scripts/add_street_names.py` | adds every graph node's nearby street names (turn instructions) |
| `scripts/build_route_pois.py` | points of interest for walks -> `deploy/data/nyc_pois.json.gz` |
| `scripts/make_poi_intros.py` | Wikipedia-sourced, fact-checked intros -> `frontend/data/poi_intros.json` |
| `scripts/make_illustrations.py` | the 24 invite-card illustrations (Muse Image) |
| `scripts/user_test_report.py` | user-test funnel, survey answers, predicted vs actual walk time |

## Data and attribution

Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under
the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/). The walking graph
and places are derived from OpenStreetMap via OSMnx and the Overpass API. Walking times from the
optional ORS fallback come from [openrouteservice](https://openrouteservice.org/) (HeiGIT).

Place intros on walks are shortened from English Wikipedia article summaries (text under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)); each card links its source
article, and the intros are shared under the same license.

Opening hours are shown as OSM lists them, "as of" the snapshot date; StrollCall never claims a
place is open, safe or quiet beyond what the data says.
