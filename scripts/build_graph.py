"""Build the local walking graph and POI snapshot (run once, needs network; app then runs offline).

    pip install -r requirements-build.txt
    python scripts/build_graph.py                       # default area, see DEFAULT_BBOX
    python scripts/build_graph.py --bbox 40.70,-74.02,40.76,-73.97 --name test

Writes to data/ (gitignored):
  data/<name>_graph.npz      walking graph: CSR adjacency (edge weight = minutes at 80 m/min),
                             node coordinates and per-edge geometry
  data/<name>_places.json.gz meetup and destination places with fetched_at

Map data © OpenStreetMap contributors, available under the Open Database License (ODbL).
"""

import argparse
import gzip
import json
import time
from datetime import datetime, timezone

import numpy as np
import osmnx as ox
from _common import ROOT

from app.providers.overpass import DESTINATION_TYPES, KEPT_TAGS, destination_type, meetup_type

WALK_M_PER_MIN = 80.0
GATE_TO_PARK_M = 15.0
# (south, west, north, east): Manhattan, northern Brooklyn (to Bed-Stuy/Bushwick) and Long Island City.
DEFAULT_BBOX = (40.675, -74.025, 40.882, -73.905)
POI_TAGS = {
    "leisure": ["park"],
    "place": ["square"],
    "highway": ["pedestrian"],
    "railway": ["subway_entrance"],
    "barrier": ["gate"],
    "tourism": ["attraction", "viewpoint", "museum"],
    "historic": ["monument", "memorial"],
    "amenity": ["cafe", "ice_cream"],
    "shop": ["books", "bakery", "ice_cream"],
}


def build_graph(bbox, out_path) -> None:
    south, west, north, east = bbox
    t = time.monotonic()
    G = ox.graph_from_bbox((west, south, east, north), network_type="walk", simplify=True)
    print(f"downloaded walk graph: {len(G.nodes)} nodes, {len(G.edges)} edges ({time.monotonic() - t:.0f} s)")

    node_ids = list(G.nodes)
    index = {n: i for i, n in enumerate(node_ids)}
    lat = np.array([G.nodes[n]["y"] for n in node_ids], dtype=np.float64)
    lon = np.array([G.nodes[n]["x"] for n in node_ids], dtype=np.float64)

    # Keep the shortest of parallel edges between two nodes.
    best: dict[tuple[int, int], tuple[float, list]] = {}
    for u, v, data in G.edges(data=True):
        i, j = index[u], index[v]
        if i == j:
            continue
        length = float(data.get("length", 0.0))
        if (i, j) in best and best[(i, j)][0] <= length:
            continue
        inner = []
        geom = data.get("geometry")
        if geom is not None:
            coords = list(geom.coords)  # (lon, lat)
            # Orient from u to v, then keep only the points between the two nodes.
            if (coords[0][0] - lon[i]) ** 2 + (coords[0][1] - lat[i]) ** 2 > \
               (coords[-1][0] - lon[i]) ** 2 + (coords[-1][1] - lat[i]) ** 2:
                coords.reverse()
            inner = coords[1:-1]
        best[(i, j)] = (length, inner)

    keys = sorted(best)  # row-major order = CSR order
    rows = np.array([k[0] for k in keys], dtype=np.int32)
    cols = np.array([k[1] for k in keys], dtype=np.int32)
    minutes = np.array([best[k][0] / WALK_M_PER_MIN for k in keys], dtype=np.float32)
    indptr = np.zeros(len(node_ids) + 1, dtype=np.int64)
    np.add.at(indptr, rows + 1, 1)
    indptr = np.cumsum(indptr)

    geom_ptr = np.zeros(len(keys) + 1, dtype=np.int64)
    geom_ptr[1:] = np.cumsum([len(best[k][1]) for k in keys])
    flat = [pt for k in keys for pt in best[k][1]]
    geom_lon = np.array([p[0] for p in flat], dtype=np.float32)
    geom_lat = np.array([p[1] for p in flat], dtype=np.float32)

    np.savez_compressed(
        out_path,
        lat=lat, lon=lon, indptr=indptr, indices=cols, minutes=minutes,
        geom_ptr=geom_ptr, geom_lat=geom_lat, geom_lon=geom_lon,
        bbox=np.array(bbox), built_at=np.array(datetime.now(timezone.utc).isoformat()),
        walk_m_per_min=np.array(WALK_M_PER_MIN),
    )
    print(f"wrote {out_path.relative_to(ROOT)}: {len(node_ids)} nodes, {len(keys)} edges, "
          f"{len(flat)} geometry points, {out_path.stat().st_size / 1e6:.1f} MB")


def _tags(row) -> dict:
    out = {}
    for key, value in row.items():
        if key in ("geometry",) or value is None or (isinstance(value, float) and np.isnan(value)):
            continue
        out[str(key)] = str(value)
    return out


def _place(element_id, tags: dict, point, name: str, category: str, fetched_at: str) -> dict:
    return {
        "id": element_id,
        "name": name,
        "lat": round(point.y, 7),
        "lon": round(point.x, 7),
        "category": category,
        "opening_hours": tags.get("opening_hours"),
        "tags": {k: tags[k] for k in KEPT_TAGS if k in tags},
        "fetched_at": fetched_at,
    }


def is_destination(tags: dict) -> bool:
    return bool(tags.get("name")) and (
        tags.get("amenity") in ("cafe", "ice_cream")
        or tags.get("shop") in ("books", "bakery", "ice_cream")
        or tags.get("leisure") == "park"
        or tags.get("tourism") in ("attraction", "museum", "viewpoint")
        or tags.get("historic") in ("monument", "memorial")
    )


def is_meetup(tags: dict, element: str) -> bool:
    if not tags.get("name"):
        return False
    return (
        (tags.get("leisure") == "park" and element in ("way", "relation"))
        or tags.get("place") == "square"
        or (tags.get("highway") == "pedestrian" and tags.get("area") == "yes")
        or (tags.get("railway") == "subway_entrance" and element == "node")
        or tags.get("tourism") in ("attraction", "viewpoint")
        or tags.get("historic") in ("monument", "memorial")
    )


def build_places(bbox, out_path) -> None:
    import geopandas as gpd

    south, west, north, east = bbox
    t = time.monotonic()
    gdf = ox.features_from_bbox((west, south, east, north), POI_TAGS)
    fetched_at = datetime.now(timezone.utc).isoformat()
    print(f"downloaded {len(gdf)} OSM features ({time.monotonic() - t:.0f} s)")

    meetups, destinations = [], []
    parks = []
    for (element, osmid), row in gdf.iterrows():
        tags = _tags(row)
        geom = row.geometry
        point = geom.centroid if geom.geom_type != "Point" else geom
        pid = f"{element}/{osmid}"
        if tags.get("leisure") == "park" and tags.get("name") and geom.geom_type in ("Polygon", "MultiPolygon"):
            parks.append((tags["name"], geom))
        if is_destination(tags):
            destinations.append(_place(pid, tags, point, tags["name"], destination_type(tags), fetched_at))
        if is_meetup(tags, element):
            meetups.append(_place(pid, tags, point, tags["name"], meetup_type(tags), fetched_at))

    # Park gates: unnamed barrier=gate nodes on a named park's edge, named after that park.
    gates = gdf[(gdf.get("barrier") == "gate") & (gdf.geometry.geom_type == "Point")]
    if len(gates) and parks:
        park_gdf = gpd.GeoDataFrame({"park_name": [p[0] for p in parks]}, geometry=[p[1] for p in parks], crs=gdf.crs)
        utm = park_gdf.estimate_utm_crs()
        joined = gpd.sjoin_nearest(gates.to_crs(utm), park_gdf.to_crs(utm), max_distance=GATE_TO_PARK_M,
                                   distance_col="dist")
        seen = set()
        for (element, osmid), row in joined.iterrows():
            if osmid in seen:
                continue
            seen.add(osmid)
            tags = _tags(gdf.loc[(element, osmid)])
            name = tags.get("name") or f"{row['park_name']} gate"
            point = gdf.loc[(element, osmid)].geometry
            meetups.append(_place(f"{element}/{osmid}", tags, point, name, "park_gate", fetched_at))

    snapshot = {
        "fetched_at": fetched_at,
        "bbox": list(bbox),
        "attribution": "© OpenStreetMap contributors, ODbL",
        "destination_types": list(DESTINATION_TYPES),
        "meetup": sorted(meetups, key=lambda p: p["id"]),
        "destination": sorted(destinations, key=lambda p: p["id"]),
    }
    with gzip.open(out_path, "wt") as f:
        json.dump(snapshot, f)
    print(f"wrote {out_path.relative_to(ROOT)}: {len(meetups)} meetup places, "
          f"{len(destinations)} destinations, {out_path.stat().st_size / 1e6:.1f} MB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbox", help="south,west,north,east")
    parser.add_argument("--name", default="nyc")
    parser.add_argument("--overpass-url", default=None, help="e.g. a mirror if the main server is busy")
    parser.add_argument("--skip-graph", action="store_true")
    parser.add_argument("--skip-places", action="store_true")
    args = parser.parse_args()
    bbox = tuple(float(x) for x in args.bbox.split(",")) if args.bbox else DEFAULT_BBOX

    ox.settings.http_user_agent = "StrollCall/0.1 (Meta AI hackathon prototype; one-off graph build)"
    ox.settings.requests_timeout = 300
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(ROOT / "cache" / "osmnx")
    if args.overpass_url:
        ox.settings.overpass_url = args.overpass_url

    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    if not args.skip_graph:
        build_graph(bbox, out_dir / f"{args.name}_graph.npz")
    if not args.skip_places:
        build_places(bbox, out_dir / f"{args.name}_places.json.gz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
