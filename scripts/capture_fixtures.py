"""Capture real Overpass places and ORS legs into fixtures/ for mock mode.

Usage: python scripts/capture_fixtures.py [--places] [--routes]
Overpass is often at capacity, so each query gets up to 3 attempts with backoff.
Only public origins from fixtures/nyc_origins.json are queried.
"""

import argparse
import json
import time

from _common import ROOT, load_origins, point

from app.core.errors import ProviderError
from app.providers.ors import ORSProvider, route_key
from app.providers.overpass import OverpassProvider

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
    overpass = OverpassProvider()
    centers = [point(origins["smoke"]["center"])]
    for pair in origins["pairs"]:
        (la, oa), (lb, ob) = point(pair["a"]), point(pair["b"])
        centers.append(((la + lb) / 2, (oa + ob) / 2))
    places = {}
    for i, (lat, lon) in enumerate(centers):
        print(f"overpass area {i + 1}/{len(centers)}")
        for p in with_backoff(lambda: overpass.places_near(lat, lon, PLACES_RADIUS_M)):
            places[p.id] = p.model_dump()
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--places", action="store_true")
    parser.add_argument("--routes", action="store_true")
    args = parser.parse_args()
    origins = load_origins()
    if args.places or not args.routes:
        capture_places(origins)
    if args.routes or not args.places:
        capture_routes(origins)
