"""Points of interest for walking guidance: parks, historic sites, artworks, memorials, landmarks.

    python scripts/build_route_pois.py            # writes deploy/data/nyc_pois.json.gz

Reads the OpenStreetMap responses cached by scripts/build_graph.py (cache/osmnx) and, if the
public Overpass server answers (at most 3 tries with exponential backoff), adds artworks and
historic sites the original build did not ask for. Each POI keeps its name, category, a
representative point, sample points along its outline (every ~25 m, so a route passing a park's
edge finds it), and its wikipedia / wikidata tags for scripts/make_poi_intros.py.
Map data © OpenStreetMap contributors, ODbL.
"""

import glob
import gzip
import json
import math
import time
from datetime import datetime, timezone

import httpx
from _common import ROOT
from build_graph import DEFAULT_BBOX

OUT = ROOT / "deploy" / "data" / "nyc_pois.json.gz"
SAMPLE_M = 25.0
OVERPASS = "https://overpass-api.de/api/interpreter"
EXTRA_QUERY = """[out:json][timeout:180];
(nwr["tourism"="artwork"]["name"]({s},{w},{n},{e}); nwr["historic"]["name"]({s},{w},{n},{e}););
out body; >; out skel qt;"""
USER_AGENT = "StrollCall/0.1 (Meta AI hackathon prototype; one-off POI build)"


def category(tags: dict) -> str | None:
    if tags.get("tourism") == "artwork":
        return "artwork"
    if tags.get("historic") == "memorial" or tags.get("memorial"):
        return "memorial"
    if tags.get("historic"):
        return "historic site"
    if tags.get("leisure") == "park":
        return "park"
    if tags.get("tourism") in ("museum", "attraction", "viewpoint"):
        return "landmark"
    return None


def cached_elements() -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(ROOT / "cache" / "osmnx" / "*.json"))):
        try:
            d = json.load(open(f))
        except ValueError:
            continue
        if isinstance(d, dict):
            out += d.get("elements", [])
    return out


def extra_elements(bbox) -> list[dict]:
    s, w, n, e = bbox
    query = EXTRA_QUERY.format(s=s, w=w, n=n, e=e)
    for attempt in range(3):
        try:
            r = httpx.post(OVERPASS, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=240)
            if r.status_code == 200:
                return r.json().get("elements", [])
            print(f"overpass attempt {attempt + 1}: HTTP {r.status_code}")
        except (httpx.HTTPError, ValueError) as ex:
            print(f"overpass attempt {attempt + 1}: {type(ex).__name__}")
        time.sleep(30 * 2 ** attempt)
    print("overpass unavailable: artworks and other historic sites come only from the cache")
    return []


def densify(pts: list[tuple[float, float]]) -> list[list[float]]:
    out = []
    for a, b in zip(pts, pts[1:]):
        dy = (b[0] - a[0]) * 111_320
        dx = (b[1] - a[1]) * 111_320 * math.cos(math.radians(a[0]))
        k = max(1, int(math.hypot(dx, dy) // SAMPLE_M))
        out += [[round(a[0] + (b[0] - a[0]) * i / k, 6), round(a[1] + (b[1] - a[1]) * i / k, 6)] for i in range(k)]
    if pts:
        out.append([round(pts[-1][0], 6), round(pts[-1][1], 6)])
    return out


def main() -> int:
    bbox = DEFAULT_BBOX
    elements = cached_elements()
    n_cached = len(elements)
    elements += extra_elements(bbox)
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in elements if e["type"] == "node" and "lat" in e}
    ways = {e["id"]: e.get("nodes", []) for e in elements if e["type"] == "way"}

    pois: dict[str, dict] = {}
    for e in elements:
        tags = e.get("tags") or {}
        cat = category(tags)
        if not cat or not tags.get("name"):
            continue
        if e["type"] == "node":
            pts = [[e["lat"], e["lon"]]] if "lat" in e else []
        elif e["type"] == "way":
            pts = densify([nodes[n] for n in ways.get(e["id"], []) if n in nodes])
        else:  # relation: the outer ways
            pts = []
            for m in e.get("members", []):
                if m.get("type") == "way" and m.get("role") in ("outer", ""):
                    pts += densify([nodes[n] for n in ways.get(m["ref"], []) if n in nodes])
        if not pts:
            continue
        lat = sum(p[0] for p in pts) / len(pts)
        lon = sum(p[1] for p in pts) / len(pts)
        s, w, n, east = bbox
        if not (s <= lat <= n and w <= lon <= east):
            continue
        pid = f"{e['type']}/{e['id']}"
        pois[pid] = {
            "id": pid, "name": tags["name"], "category": cat, "lat": round(lat, 6), "lon": round(lon, 6),
            "pts": pts, "wikipedia": tags.get("wikipedia"), "wikidata": tags.get("wikidata"),
        }
    data = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "attribution": "© OpenStreetMap contributors, ODbL",
        "pois": sorted(pois.values(), key=lambda p: p["id"]),
    }
    with gzip.open(OUT, "wt") as f:
        json.dump(data, f, separators=(",", ":"))
    counts: dict[str, int] = {}
    for p in pois.values():
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    wiki = sum(bool(p["wikipedia"] or p["wikidata"]) for p in pois.values())
    print(f"{n_cached} cached + {len(elements) - n_cached} fetched elements -> {len(pois)} POIs {counts}, "
          f"{wiki} with wikipedia/wikidata; {OUT.relative_to(ROOT)} {OUT.stat().st_size / 1e3:.0f} kB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
