# Live latency on Render (free plan, Virginia): before and after the speedups

Measured 2026-10-29 with `scripts/profile_live.py --runs 3` against https://strollcall.onrender.com, pair p1 from
fixtures/nyc_origins.json (public places), A's text "25 minutes, quiet streets, coffee at the end", B's text
"somewhere green on the way would be nice". Polling every 0.5 s, so *plan visible* has up to 0.5 s of polling slack.

**Important context:** during all three runs the Meta Model API answered `404 model_not_found` from the server
(docs/meta_support_ticket.md), so every Muse Spark step fell back to the labelled rule-based path. Much of the
*before* time is Meta 404s and their retries; the numbers below are not what a working Meta API would give.
With Meta working, the Meta calls dominate (about 1-2 s each at `minimal` effort, measured 2026-10-28).

| Run | A creates invite (s) | B accepts (s) | B accepts -> plan visible (s) | Server: accept -> done (s) |
|---|---|---|---|---|
| Before (commit 07da44a) run 1 | 4.87 | 0.27 | 14.94 | 14.42 |
|  run 2 | 1.89 | 0.26 | 6.3 | 5.97 |
|  run 3 | 2.09 | 0.2 | 6.48 | 5.91 |
| Step A: bounded Dijkstra, in-memory progress, model_not_found pause (635a674 + 0ec0182) run 1 | 4.04 | 0.51 | 8.78 | 7.29 |
|  run 2 | 0.27 | 0.29 | 2.08 | 1.08 |
|  run 3 | 0.24 | 0.29 | 1.89 | 0.96 |
| Step B: + map data preloaded at startup, one Meta client per process (c89ea49, 2c5fda8) run 1 | 4.11 | 0.12 | 1.3 | 0.68 |
|  run 2 | 0.08 | 0.1 | 0.28 | 0.05 |
|  run 3 | 0.08 | 0.09 | 0.88 | 0.08 |

Medians of the warm runs (2 and 3):

- Before (commit 07da44a): create 1.99 s, plan visible 6.39 s, server 5.94 s
- Step A: bounded Dijkstra, in-memory progress, model_not_found pause (635a674 + 0ec0182): create 0.26 s, plan visible 1.98 s, server 1.02 s
- Step B: + map data preloaded at startup, one Meta client per process (c89ea49, 2c5fda8): create 0.08 s, plan visible 0.58 s, server 0.07 s

Stage timings reported by the server (seconds, first run / warm run), step B:

- run 1: parse_b 0.0, wishes 0.0, routing_search 0.085, negotiate 0.0, plan 0.597, rank 0.0
- run 2: parse_b 0.0, wishes 0.0, routing_search 0.001, negotiate 0.0, plan 0.043, rank 0.0

Step A's first run (right after a deploy) spent ~5.8 s before any stage: loading the walking graph and place
snapshot on first use. Step B loads them in a background thread at startup. Step A's warm stage timings showed
0.2-0.5 s per (failing) Meta call building a new API client; step B keeps one per process.

## Database

Neon region: aws us-east-1; server egress in Ashburn, Virginia (AWS us-east-1). Same region.
`SELECT 1` round trip from the server: 6.2 ms (median of 3, /health). Planning progress
no longer writes to the database at each step (kept in memory, saved once with the plan).

## Planner CPU (local machine, 12 benchmark pairs, no Meta)

| | Median per plan | Total in Dijkstra |
|---|---|---|
| 40-minute bound on every search | 32 ms | 282 ms |
| Bound from the caller (meetup share, or walk + slack) | 24 ms | 210 ms |

Plans are identical before and after (benchmarks/2026-10-29-local.md); p8 now counts one meetup point as over
the time share instead of no route, because it lies beyond the bounded search.

The first run after a deploy also includes Render waking the service (first /health: 43.6 s before, the
service was asleep; 0.2 s and 2.2 s in the later passes). Free-plan services sleep after 15 minutes idle.
