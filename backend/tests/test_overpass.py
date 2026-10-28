import httpx
import pytest

from app.core.errors import ProviderError
from app.providers.overpass import OverpassProvider, build_query

ELEMENTS = {
    "elements": [
        {"type": "node", "id": 1, "lat": 40.731, "lon": -73.997,
         "tags": {"amenity": "cafe", "name": "Cafe One", "opening_hours": "Mo-Su 08:00-18:00"}},
        {"type": "way", "id": 2, "center": {"lat": 40.7308, "lon": -73.9973},
         "tags": {"leisure": "park", "name": "Washington Square Park"}},
        {"type": "node", "id": 3, "lat": 40.73, "lon": -73.99, "tags": {"amenity": "cafe"}},
        {"type": "node", "id": 4, "lat": 40.732, "lon": -73.996,
         "tags": {"historic": "memorial", "name": "Arch"}},
    ]
}
MAIN = "overpass-api.de"
MIRROR = "overpass.private.coffee"


def provider_with(handler):
    calls = []

    def wrapped(request):
        calls.append(request.url.host)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(wrapped))
    return OverpassProvider(http=http), calls


def test_normalizes_and_stamps_fetch_time():
    overpass, _ = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    by_id = {p.id: p for p in overpass.places_near(40.7308, -73.9973, 600)}
    assert set(by_id) == {"node/1", "way/2", "node/4"}  # unnamed cafe dropped
    assert by_id["way/2"].category == "park" and by_id["way/2"].lat == 40.7308
    assert by_id["node/1"].opening_hours == "Mo-Su 08:00-18:00"
    assert by_id["node/4"].category == "landmark" and by_id["node/4"].opening_hours is None
    assert by_id["node/1"].fetched_at is not None


def test_disk_cache_survives_a_new_provider():
    first, calls = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    places = first.places_near(40.7308, -73.9973, 600)
    second, calls2 = provider_with(lambda r: httpx.Response(500))
    again = second.places_near(40.73081, -73.99731, 600)
    assert calls2 == [] and again == places


def test_expired_cache_is_refetched(monkeypatch):
    overpass, calls = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    overpass.places_near(40.73, -73.99, 600)
    monkeypatch.setattr("app.providers.overpass.CACHE_TTL", __import__("datetime").timedelta(0))
    overpass.places_near(40.73, -73.99, 600)
    assert len(calls) == 2


def test_mirror_tried_once_after_main_fails():
    overpass, calls = provider_with(
        lambda r: httpx.Response(502) if r.url.host == MAIN else httpx.Response(200, json=ELEMENTS)
    )
    assert len(overpass.places_near(40.73, -73.99, 600)) == 3
    assert calls == [MAIN, MIRROR]


def test_both_servers_down_is_explicit():
    overpass, calls = provider_with(lambda r: httpx.Response(504))
    with pytest.raises(ProviderError) as e:
        overpass.places_near(40.73, -73.99, 600)
    assert e.value.code == "places_unavailable"
    assert calls == [MAIN, MIRROR]


def test_timeout_falls_through_to_mirror_then_fails():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    overpass, calls = provider_with(timeout)
    with pytest.raises(ProviderError):
        overpass.places_near(40.73, -73.99, 600)
    assert calls == [MAIN, MIRROR]


def test_user_facing_timeout_is_15s():
    assert OverpassProvider().http.timeout.read == 15.0


def test_query_has_timeout_and_requested_categories():
    q = build_query(40.73, -73.99, 500, ["cafe"])
    assert "[timeout:25]" in q and '"amenity"="cafe"' in q and "leisure" not in q
