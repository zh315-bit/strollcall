import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.providers.ors import ORSProvider

GEOJSON = {
    "features": [{
        "geometry": {"coordinates": [[-73.9971, 40.7312], [-73.9935, 40.7330], [-73.9905, 40.7349]]},
        "properties": {"summary": {"distance": 712.4, "duration": 513.0}},
    }]
}


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


@pytest.mark.parametrize("status,code", [(404, "no_route"), (429, "routing_unavailable"), (500, "routing_unavailable")])
def test_errors_are_explicit(status, code):
    ors, _ = provider_with(lambda r: httpx.Response(status, json={"error": {"code": 2099}}))
    with pytest.raises(ProviderError) as e:
        ors.walk((40.73, -73.99), (40.74, -73.98))
    assert e.value.code == code


def test_missing_key():
    with pytest.raises(ProviderError):
        ORSProvider()
