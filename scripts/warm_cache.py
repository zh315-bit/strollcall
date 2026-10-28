"""Pre-fetch Overpass places for the demo neighborhoods into the disk cache (cache/, 7 days).

    python scripts/warm_cache.py

Run it before a demo so user requests hit the cache instead of a busy Overpass server.
Queries run one at a time with a pause, as the Overpass usage policy asks.
"""

import time

from _common import load_origins, point

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.providers.overpass import OverpassProvider

RADIUS_M = 900
# Public reference points (park centers), read from OpenStreetMap.
NEIGHBORHOODS = {
    "Washington Square": (40.73089, -73.99759),
    "Union Square": (40.73576, -73.99065),
    "East Village (Tompkins Square)": (40.72647, -73.98169),
    "Flatiron (Madison Square)": (40.74219, -73.98787),
}


def demo_points() -> dict[str, tuple[float, float]]:
    points = dict(NEIGHBORHOODS)
    for pair in load_origins()["pairs"]:
        (la, oa), (lb, ob) = point(pair["a"]), point(pair["b"])
        points[f"pair {pair['id']} midpoint"] = ((la + lb) / 2, (oa + ob) / 2)
    return points


def main() -> int:
    settings = get_settings().model_copy(update={"overpass_timeout_s": 60.0})
    overpass = OverpassProvider(settings=settings)
    failed = 0
    for name, (lat, lon) in demo_points().items():
        started = time.monotonic()
        try:
            places = overpass.places_near(lat, lon, RADIUS_M)
            print(f"  ok    {name}: {len(places)} places ({time.monotonic() - started:.1f} s)")
        except ProviderError as e:
            failed += 1
            print(f"  FAIL  {name}: {e.message}")
        time.sleep(2)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
