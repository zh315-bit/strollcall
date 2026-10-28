import json
import time

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.providers.ors import ORSProvider, RateLimiter

GEOJSON = {
    "features": [{
        "geometry": {"coordinates": [[-73.9971, 40.7312], [-73.9935, 40.7330], [-73.9905, 40.7349]]},
        "properties": {"summary": {"distance": 712.4, "duration": 513.0}},
    }]
}
MATRIX = {"durations": [[600.0, None], [300.0, 720.0]], "distances": [[800.0, None], [400.0, 960.0]]}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.providers.ors.time.sleep", lambda s: None)


def provider_with(handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    settings = get_settings().model_copy(update={"ors_api_key": SecretStr("test-key")})
    return ORSProvider(settings=settings, http=httpx.Client(transport=httpx.MockTransport(wrapped))), calls


def test_leg_parsed_and_cached():
    ors, calls = provider_with(lambda r: httpx.Response(200, json=GEOJSON))
    leg = ors.walk((40.73121, -73.99712), (40.73489, -73.99051))
    assert leg.geometry[0] == (40.7312, -73.9971)  # (lat, lon)
    assert leg.distance_m == 712.4 and leg.duration_min == 8.55
    ors.walk((40.73119, -73.99708), (40.73491, -73.99049))  # rounds to the same key
    assert len(calls) == 1
    assert calls[0].headers["Authorization"] == "test-key"


def test_matrix_minutes_meters_and_unreachable():
    ors, calls = provider_with(lambda r: httpx.Response(200, json=MATRIX))
    a, b, m1, m2 = (40.73, -74.0), (40.735, -73.99), (40.732, -73.995), (40.74, -73.98)
    result = ors.matrix([a, b], [m1, m2])
    assert result.durations_min == [[10.0, None], [5.0, 12.0]]
    assert result.distances_m == [[800.0, None], [400.0, 960.0]]
    body = json.loads(calls[0].content)
    assert body["locations"][0] == [-74.0, 40.73]  # [lon, lat]
    assert body["sources"] == [0, 1] and body["destinations"] == [2, 3]
    assert ors.matrix([b], [m1]).durations_min == [[5.0]]  # served from element cache
    assert len(calls) == 1


def test_matrix_rejects_oversized_request():
    ors, _ = provider_with(lambda r: httpx.Response(200, json=MATRIX))
    pts = [(40.7 + i * 0.001, -74.0) for i in range(60)]
    with pytest.raises(ValueError):
        ors.matrix(pts, pts)


def test_transient_error_retried_once():
    responses = iter([httpx.Response(503), httpx.Response(200, json=GEOJSON)])
    ors, calls = provider_with(lambda r: next(responses))
    assert ors.walk((40.73, -73.99), (40.74, -73.98)).duration_min == 8.55
    assert len(calls) == 2


@pytest.mark.parametrize("status,code,attempts", [
    (404, "no_route", 1), (429, "routing_unavailable", 2), (500, "routing_unavailable", 2),
    (403, "routing_unavailable", 1),
])
def test_errors_are_explicit(status, code, attempts):
    ors, calls = provider_with(lambda r: httpx.Response(status, json={"error": {"code": 2099}}))
    with pytest.raises(ProviderError) as e:
        ors.walk((40.73, -73.99), (40.74, -73.98))
    assert e.value.code == code
    assert len(calls) == attempts


def test_rate_limiter_waits_when_window_is_full():
    now = [0.0]
    waits = []

    def sleep(s):
        waits.append(s)
        now[0] += s

    limiter = RateLimiter(3, 60, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        limiter.acquire()
        now[0] += 1
    limiter.acquire()  # 4th call within the minute
    assert waits == [57.0]


def test_missing_key():
    with pytest.raises(ProviderError):
        ORSProvider()


ROUTE_A, ROUTE_B = (40.73, -73.99), (40.74, -73.98)


def test_live_client_refused_inside_pytest():
    settings = get_settings().model_copy(update={"ors_api_key": SecretStr("test-key")})
    with pytest.raises(RuntimeError, match="inside pytest"):
        ORSProvider(settings=settings)


def test_disk_cache_survives_a_new_provider():
    first, calls = provider_with(lambda r: httpx.Response(200, json=GEOJSON))
    leg = first.walk(ROUTE_A, ROUTE_B)
    second, calls2 = provider_with(lambda r: httpx.Response(500))
    assert second.walk(ROUTE_A, ROUTE_B) == leg and calls2 == []


def test_matrix_asks_only_for_missing_rows_and_columns():
    m1 = {"durations": [[600.0], [300.0]], "distances": [[800.0], [400.0]]}
    m2 = {"durations": [[120.0], [180.0]], "distances": [[160.0], [240.0]]}
    responses = iter([httpx.Response(200, json=m1), httpx.Response(200, json=m2)])
    ors, calls = provider_with(lambda r: next(responses))
    a, b, d1, d2 = (40.73, -74.0), (40.735, -73.99), (40.732, -73.995), (40.74, -73.98)
    ors.matrix([a, b], [d1])
    result = ors.matrix([a, b], [d1, d2])  # only the d2 column is new
    body = json.loads(calls[1].content)
    assert len(body["sources"]) == 2 and len(body["destinations"]) == 1
    assert result.durations_min[0][0] == 10.0


def test_request_log_by_endpoint_and_caller():
    ors, _ = provider_with(lambda r: httpx.Response(200, json=GEOJSON))
    ors.walk(ROUTE_A, ROUTE_B)
    assert ors.store.usage_24h() == {"directions": {"app": 1}}


def test_soft_cap_stops_live_calls(caplog):
    ors, calls = provider_with(lambda r: httpx.Response(200, json=GEOJSON))
    ors.caps["directions"] = 1
    ors.walk(ROUTE_A, ROUTE_B)
    with pytest.raises(ProviderError) as e:
        ors.walk((40.70, -74.0), (40.71, -74.0))
    assert "soft cap" in e.value.message and len(calls) == 1
    assert "live calls stopped" in caplog.text


def test_quota_header_stops_before_ors_does():
    headers = {"x-ratelimit-remaining": "3", "x-ratelimit-reset": str(int(time.time()) + 3600)}
    ors, calls = provider_with(lambda r: httpx.Response(200, json=GEOJSON, headers=headers))
    ors.walk(ROUTE_A, ROUTE_B)
    with pytest.raises(ProviderError) as e:
        ors.walk((40.70, -74.0), (40.71, -74.0))
    assert "quota exhausted" in e.value.message and len(calls) == 1


def test_403_quota_exceeded_pauses_live_calls():
    ors, calls = provider_with(lambda r: httpx.Response(403, json={"error": "Quota exceeded"}))
    with pytest.raises(ProviderError) as e:
        ors.walk(ROUTE_A, ROUTE_B)
    assert "quota exceeded" in e.value.message
    with pytest.raises(ProviderError):
        ors.walk((40.70, -74.0), (40.71, -74.0))
    assert len(calls) == 1  # the second call never left
