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


def provider_with(handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(wrapped))
    return OverpassProvider(http=http), calls


def test_normalizes_and_caches():
    overpass, calls = provider_with(lambda r: httpx.Response(200, json=ELEMENTS))
    places = overpass.places_near(40.7308, -73.9973, 600)
    by_id = {p.id: p for p in places}
    assert set(by_id) == {"node/1", "way/2", "node/4"}  # unnamed cafe dropped
    assert by_id["way/2"].category == "park" and by_id["way/2"].lat == 40.7308
    assert by_id["node/1"].opening_hours == "Mo-Su 08:00-18:00"
    assert by_id["node/4"].category == "landmark" and by_id["node/4"].opening_hours is None
    overpass.places_near(40.73081, -73.99731, 600)
    assert len(calls) == 1


def test_http_error_is_explicit():
    overpass, _ = provider_with(lambda r: httpx.Response(429))
    with pytest.raises(ProviderError) as e:
        overpass.places_near(40.73, -73.99, 600)
    assert e.value.code == "places_unavailable"


def test_query_has_timeout_and_requested_categories():
    q = build_query(40.73, -73.99, 500, ["cafe"])
    assert "[timeout:25]" in q and '"amenity"="cafe"' in q and "leisure" not in q
