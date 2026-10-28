"""Capture real Overpass and ORS responses into fixtures/ for mock mode.

Usage: python scripts/capture_fixtures.py [--places] [--routes] [--planner]
  --planner  runs the planner on every case in fixtures/benchmark_cases.json against the
             real APIs and records exactly what it fetched: Overpass responses under
             fixtures/overpass/, ORS matrix entries in ors_matrix_elements.json and ORS
             legs in sample_routes.json. Then USE_MOCKS=true replays the same plans.
Overpass is often at capacity, so each query gets up to 3 attempts with backoff.
Only public origins from fixtures/nyc_origins.json are queried.
"""

import argparse
import json
import time

from _common import ROOT, load_cases, load_origins, point

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.providers.ors import ORSProvider, route_key
from app.providers.overpass import OverpassProvider
from app.services.planner import plan_walk

FIXTURES = ROOT / "fixtures"
PLACES_RADIUS_M = 900


def with_backoff(fn, attempts=3, first_wait_s=10):
    for i in range(attempts):
        try:
            return fn()
        except ProviderError as e:
            if i == attempts - 1:
                raise
            wait = first_wait_s * 2**i
            print(f"  {e.message}; retrying in {wait}s")
            time.sleep(wait)


def capture_places(origins: dict) -> None:
    # Scripts may wait for a busy Overpass queue; the app itself gives up after 15 s.
    overpass = OverpassProvider(settings=get_settings().model_copy(update={"overpass_timeout_s": 60.0}))
    centers = [point(origins["smoke"]["center"])]
    for pair in origins["pairs"]:
        (la, oa), (lb, ob) = point(pair["a"]), point(pair["b"])
        centers.append(((la + lb) / 2, (oa + ob) / 2))
    places = {}
    for i, (lat, lon) in enumerate(centers):
        print(f"overpass area {i + 1}/{len(centers)}")
        for p in with_backoff(lambda: overpass.places_near(lat, lon, PLACES_RADIUS_M)):
            places[p.id] = p.model_dump(mode="json")
        time.sleep(2)
    out = sorted(places.values(), key=lambda p: p["id"])
    (FIXTURES / "sample_places.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {len(out)} places")


def capture_routes(origins: dict) -> None:
    ors = ORSProvider()
    pairs = [(point(origins["smoke"]["center"]), point(origins["smoke"]["route_to"]))]
    pairs += [(point(p["a"]), point(p["b"])) for p in origins["pairs"]]
    routes = []
    for start, end in pairs:
        leg = ors.walk(start, end)
        routes.append({"key": route_key(start, end), "leg": leg.model_dump()})
        print(f"  leg {leg.distance_m:.0f} m, {leg.duration_min:.1f} min")
        time.sleep(1.6)  # ORS free tier: 40 directions requests per minute
    (FIXTURES / "sample_routes.json").write_text(json.dumps(routes) + "\n")
    print(f"wrote {len(routes)} routes")


def _merge_json(path, new: dict) -> dict:
    data = json.loads(path.read_text()) if path.exists() else {}
    data.update(new)
    path.write_text(json.dumps(dict(sorted(data.items()))) + "\n")
    return data


def capture_planner() -> None:
    settings = get_settings().model_copy(
        update={"overpass_timeout_s": 60.0, "cache_dir": FIXTURES}  # writes fixtures/overpass/
    )
    overpass, ors = OverpassProvider(settings=settings), ORSProvider()
    for case in load_cases():
        for attempt in range(3):
            result = plan_walk(case["a"], case["b"], case["intent"], overpass, ors, case["depart_at"])
            if result.status != "places_unavailable":
                break
            print(f"  {case['id']}: Overpass unavailable, waiting {30 * (attempt + 1)}s")
            time.sleep(30 * (attempt + 1))
        print(f"{case['id']}: {result.status}, {len(result.candidates)} candidates")

    elements = {k: (None if v is None else list(v)) for k, v in ors.elements.items()}
    total = _merge_json(FIXTURES / "ors_matrix_elements.json", elements)
    print(f"ors matrix elements: {len(elements)} recorded, {len(total)} in fixture")

    routes_path = FIXTURES / "sample_routes.json"
    routes = {r["key"]: r for r in json.loads(routes_path.read_text())}
    for key, leg in ors.legs.items():
        routes[key] = {"key": key, "leg": leg.model_dump()}
    routes_path.write_text(json.dumps([routes[k] for k in sorted(routes)]) + "\n")
    print(f"ors legs: {len(ors.legs)} recorded, {len(routes)} in fixture")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--places", action="store_true")
    parser.add_argument("--routes", action="store_true")
    parser.add_argument("--planner", action="store_true")
    args = parser.parse_args()
    origins = load_origins()
    if args.places:
        capture_places(origins)
    if args.routes:
        capture_routes(origins)
    if args.planner:
        capture_planner()
