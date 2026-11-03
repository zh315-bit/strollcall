# "More options": the defaults change nothing

Run 2026-10-31 12:24 ET, `scripts/benchmark.py` (local OSM walking graph + place snapshot, 12 pre-registered
pair cases, planner only, no Meta calls), twice:

- **before**: commit `53ae020`, with its data (walking graph without edge flags);
- **after**: the "More options" change (pace, avoid via edge flags, loop, pass by, stops, open destination), with the
  rebuilt graph (`edge_flags` from `scripts/add_edge_flags.py`) and route POIs (markets, shoreline), default options.

The two reports (`benchmarks/2026-10-31-local.md` is the "after" one) differ only in timing columns and memory
(+49 vs +48 MB RSS). Every case has the same status, meetup, destination, arrival gap and elapsed time:
feasibility 11/12, correct outcome 12/12, gap median 0.2 / max 1.2 min, time-budget error median 0.4 min.

Default options take the same code path as before: `LocalRouting.view()` with pace 80 m/min and nothing to avoid
returns the engine itself (tests/test_options.py::test_default_options_change_nothing also checks a solo plan is
identical with and without `WalkOptions()`).
