from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.errors import ProviderError
from app.providers.mock import MockOverpass
from app.providers.overpass import (
    DiskCache, OverpassProvider, destination_key, destination_query, meetup_query, parse_meetups,
)

ELEMENTS = {
    "elements": [
        {"type": "node", "id": 1, "lat": 40.731, "lon": -73.997,
         "tags": {"amenity": "cafe", "name": "Cafe One", "opening_hours": "Mo-Su 08:00-18:00",
                  "outdoor_seating": "yes", "addr:street": "dropped"}},
        {"type": "way", "id": 2, "center": {"lat": 40.7308, "lon": -73.9973},
         "tags": {"leisure": "park", "name": "Washington Square Park"}},
        {"type": "node", "id": 3, "lat": 40.73, "lon": -73.99, "tags": {"amenity": "cafe"}},
        {"type": "node", "id": 4, "lat": 40.732, "lon": -73.996,
         "tags": {"shop": "bakery", "name": "Bread"}},
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


def test_destinations_normalized_with_tags_and_fetch_time():
    overpass, _ = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    by_id = {p.id: p for p in overpass.destination_candidates(40.7308, -73.9973, 600)}
    assert set(by_id) == {"node/1", "way/2", "node/4"}  # unnamed cafe dropped
    assert by_id["way/2"].category == "park" and by_id["way/2"].lat == 40.7308
    assert by_id["node/4"].category == "bakery"
    assert by_id["node/1"].opening_hours == "Mo-Su 08:00-18:00"
    assert by_id["node/1"].tags == {"amenity": "cafe", "outdoor_seating": "yes"}
    assert by_id["node/1"].fetched_at is not None


def test_meetups_name_gates_after_their_park():
    places = {p.id: p for p in parse_meetups(MEETUP_ELEMENTS, datetime.now(timezone.utc))}
    assert places["way/10"].category == "park"
    assert places["node/11"].name == "Christopher Park gate"
    assert places["node/11"].category == "park_gate"
    assert places["node/12"].category == "subway_entrance"
    assert places["way/13"].category == "plaza"
    assert "node/14" not in places  # unnamed landmark


def test_disk_cache_survives_a_new_provider():
    first, _ = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    places = first.destination_candidates(40.7308, -73.9973, 600)
    second, calls2 = provider_with(lambda r: httpx.Response(500))
    assert second.destination_candidates(40.73081, -73.99731, 600) == places
    assert calls2 == []


def test_cache_key_includes_query_type():
    overpass, calls = provider_with(lambda r: httpx.Response(200, json={"elements": MEETUP_ELEMENTS}))
    overpass.meetup_candidates(40.73, -73.99, 600)
    overpass.destination_candidates(40.73, -73.99, 600, ["cafe"])
    overpass.destination_candidates(40.73, -73.99, 600, ["park"])
    assert len(calls) == 3


def test_expired_cache_is_refetched(monkeypatch):
    overpass, calls = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    overpass.destination_candidates(40.73, -73.99, 600)
    overpass.cache.ttl = timedelta(0)
    overpass.destination_candidates(40.73, -73.99, 600)
    assert len(calls) == 2


def test_mirror_tried_once_after_main_fails():
    overpass, calls = provider_with(
        lambda r: httpx.Response(502) if r.url.host == MAIN else httpx.Response(200, json=ELEMENTS)
    )
    assert len(overpass.destination_candidates(40.73, -73.99, 600)) == 3
    assert calls == [MAIN, MIRROR]


def test_both_servers_down_is_explicit():
    overpass, calls = provider_with(lambda r: httpx.Response(504))
    with pytest.raises(ProviderError) as e:
        overpass.meetup_candidates(40.73, -73.99, 600)
    assert e.value.code == "places_unavailable"
    assert calls == [MAIN, MIRROR]


def test_timeout_falls_through_to_mirror_then_fails():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    overpass, calls = provider_with(timeout)
    with pytest.raises(ProviderError):
        overpass.destination_candidates(40.73, -73.99, 600)
    assert calls == [MAIN, MIRROR]


def test_user_facing_timeout_is_15s():
    assert OverpassProvider().http.timeout.read == 15.0


def test_unknown_destination_type_rejected():
    overpass, _ = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    with pytest.raises(ValueError):
        overpass.destination_candidates(40.73, -73.99, 600, ["bar"])


def test_queries():
    q = destination_query(40.73, -73.99, 500, ["ice_cream"])
    assert "[timeout:25]" in q and '"amenity"="ice_cream"' in q and '"shop"="ice_cream"' in q
    assert "leisure" not in q
    m = meetup_query(40.73, -73.99, 500)
    assert "foreach.parks" in m and "subway_entrance" in m


def test_mock_replays_recorded_query(tmp_path):
    key = destination_key(40.73, -73.99, 600, ["cafe"])
    overpass, _ = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    places = overpass.destination_candidates(40.73, -73.99, 600, ["cafe"])
    DiskCache(tmp_path).put(key, places, datetime(2026, 10, 28, tzinfo=timezone.utc))
    mock = MockOverpass(tmp_path)
    assert mock.destination_candidates(40.73, -73.99, 600, ["cafe"]) == places
    with pytest.raises(ProviderError):
        mock.meetup_candidates(40.73, -73.99, 600)
