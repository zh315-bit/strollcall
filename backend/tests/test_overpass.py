from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.errors import ProviderError
from app.providers.mock import MockOverpass
from app.providers.overpass import (
    TileCache, OverpassProvider, destination_query, meetup_query, parse_meetups, tile_of,
    tiles_bbox, tiles_for_circle,
)

CENTER = (40.7308, -73.9973)
ELEMENTS = {
    "elements": [
        {"type": "node", "id": 1, "lat": 40.7310, "lon": -73.9970,
         "tags": {"amenity": "cafe", "name": "Cafe One", "opening_hours": "Mo-Su 08:00-18:00",
                  "outdoor_seating": "yes", "addr:street": "dropped"}},
        {"type": "way", "id": 2, "center": {"lat": 40.7308, "lon": -73.9973},
         "tags": {"leisure": "park", "name": "Washington Square Park"}},
        {"type": "node", "id": 3, "lat": 40.7300, "lon": -73.9900, "tags": {"amenity": "cafe"}},
        {"type": "node", "id": 4, "lat": 40.7320, "lon": -73.9960,
         "tags": {"shop": "bakery", "name": "Bread"}},
        {"type": "node", "id": 5, "lat": 40.7500, "lon": -73.9800,  # ~2.4 km away
         "tags": {"amenity": "cafe", "name": "Far Cafe"}},
    ]
}
MEETUP_ELEMENTS = [
    {"type": "way", "id": 10, "center": {"lat": 40.7334, "lon": -74.0021},
     "tags": {"leisure": "park", "name": "Christopher Park"}},
    {"type": "node", "id": 11, "lat": 40.7333, "lon": -74.0020, "tags": {"barrier": "gate"}},
    {"type": "node", "id": 12, "lat": 40.7310, "lon": -73.9990,
     "tags": {"railway": "subway_entrance", "name": "W 4 St (NE corner)"}},
    {"type": "way", "id": 13, "center": {"lat": 40.729, "lon": -73.999},
     "tags": {"highway": "pedestrian", "area": "yes", "name": "Gould Plaza"}},
    {"type": "node", "id": 14, "lat": 40.731, "lon": -73.997, "tags": {"historic": "memorial"}},
]
MAIN = "overpass-api.de"
MIRROR = "maps.mail.ru"


def provider_with(handler):
    calls = []

    def wrapped(request):
        calls.append(request.url.host)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(wrapped))
    return OverpassProvider(http=http), calls


def ok(json=ELEMENTS):
    return lambda r: httpx.Response(200, json=json)


def test_destinations_filtered_locally_with_tags_and_fetch_time():
    overpass, calls = provider_with(ok())
    by_id = {p.id: p for p in overpass.destination_candidates(*CENTER, 600)}
    assert set(by_id) == {"node/1", "way/2", "node/4"}  # unnamed and far cafes dropped
    assert by_id["way/2"].category == "park"
    assert by_id["node/4"].category == "bakery"
    assert by_id["node/1"].tags == {"amenity": "cafe", "outdoor_seating": "yes"}
    assert by_id["node/1"].fetched_at is not None
    assert [p.id for p in overpass.destination_candidates(*CENTER, 600, ["cafe"])] == ["node/1"]
    assert len(calls) == 1  # the type filter is local too


def test_meetups_keep_gate_coordinates_and_name_them_after_their_park():
    places = {p.id: p for p in parse_meetups(MEETUP_ELEMENTS, datetime.now(timezone.utc))}
    assert places["way/10"].category == "park"
    assert places["node/11"].name == "Christopher Park gate"
    assert (places["node/11"].lat, places["node/11"].category) == (40.7333, "park_gate")
    assert places["node/12"].category == "subway_entrance"
    assert places["way/13"].category == "plaza"
    assert "node/14" not in places  # unnamed landmark


def test_any_origin_in_a_warmed_area_hits_the_cache():
    first, _ = provider_with(ok())
    first.destination_candidates(*CENTER, 600)
    second, calls = provider_with(lambda r: httpx.Response(500))
    nearby = second.destination_candidates(40.7312, -73.9968, 450)  # different center and radius
    assert calls == [] and {p.id for p in nearby} == {"node/1", "way/2", "node/4"}


def test_missing_tiles_fetched_in_one_bbox_request():
    overpass, calls = provider_with(ok())
    overpass.destination_candidates(*CENTER, 600)
    tiles = tiles_for_circle(*CENTER, 600)
    assert len(tiles) > 1 and len(calls) == 1
    for t in tiles:
        assert overpass.cache.get("destination", t) is not None
    far_tile = tile_of(40.7500, -73.9800)
    assert far_tile not in tiles_bbox(tiles)[1]  # places outside the box are not cached anywhere


def test_kinds_cached_separately():
    overpass, calls = provider_with(ok({"elements": MEETUP_ELEMENTS}))
    overpass.meetup_candidates(*CENTER, 600)
    overpass.destination_candidates(*CENTER, 600)
    overpass.meetup_candidates(*CENTER, 600)
    assert len(calls) == 2


def test_expired_tile_is_refetched():
    overpass, calls = provider_with(ok())
    overpass.destination_candidates(*CENTER, 600)
    overpass.cache.ttl = timedelta(0)
    overpass.destination_candidates(*CENTER, 600)
    assert len(calls) == 2


def test_mirror_tried_once_after_main_fails():
    overpass, calls = provider_with(
        lambda r: httpx.Response(502) if r.url.host == MAIN else httpx.Response(200, json=ELEMENTS)
    )
    assert len(overpass.destination_candidates(*CENTER, 600)) == 3
    assert calls == [MAIN, MIRROR]


def test_both_servers_down_is_explicit():
    overpass, calls = provider_with(lambda r: httpx.Response(504))
    with pytest.raises(ProviderError) as e:
        overpass.meetup_candidates(*CENTER, 600)
    assert e.value.code == "places_unavailable"
    assert calls == [MAIN, MIRROR]


def test_timeout_falls_through_to_mirror_then_fails():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    overpass, calls = provider_with(timeout)
    with pytest.raises(ProviderError):
        overpass.destination_candidates(*CENTER, 600)
    assert calls == [MAIN, MIRROR]


def test_user_facing_timeout_is_15s():
    assert OverpassProvider().http.timeout.read == 15.0


def test_unknown_destination_type_rejected():
    overpass, _ = provider_with(ok())
    with pytest.raises(ValueError):
        overpass.destination_candidates(*CENTER, 600, ["bar"])


def test_tiles_for_circle():
    tiles = tiles_for_circle(*CENTER, 600)
    assert tile_of(*CENTER) in tiles
    assert 1 < len(tiles) <= 4
    assert len(tiles_for_circle(*CENTER, 1500)) <= 16


def test_queries_use_bbox_and_keep_gate_coordinates():
    bbox = (40.73, -74.0, 40.74, -73.987)
    q = destination_query(bbox)
    assert "[timeout:25]" in q and "(40.7300,-74.0000,40.7400,-73.9870)" in q
    assert '"shop"="ice_cream"' in q and '"leisure"="park"' in q  # every type per tile
    m = meetup_query(bbox)
    assert "foreach.parks" in m and "out;" in m and "subway_entrance" in m


def test_mock_replays_recorded_tiles(tmp_path):
    overpass, _ = provider_with(ok())
    live = overpass.destination_candidates(*CENTER, 600, ["cafe"])
    for t in tiles_for_circle(*CENTER, 600):
        TileCache(tmp_path).put("destination", t, overpass.cache.get("destination", t),
                                datetime(2026, 10, 28, tzinfo=timezone.utc))
    mock = MockOverpass(tmp_path)
    assert mock.destination_candidates(*CENTER, 600, ["cafe"]) == live
    with pytest.raises(ProviderError):
        mock.meetup_candidates(*CENTER, 600)
