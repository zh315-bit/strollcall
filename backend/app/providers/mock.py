"""Offline twins of the Meta, Overpass and ORS providers. They only read fixtures/.

Places and routes in fixtures/ were captured from real API calls; a query that has no
captured answer raises an error instead of inventing one.
"""

import base64
import json
from pathlib import Path

from app.core.config import FIXTURES_DIR
from app.core.errors import ProviderError
from app.core.geo import coord_key, haversine_m
from app.models.schemas import Place, RouteLeg
from app.providers.meta import MetaError, check_wav

# 1x1 transparent PNG, so mock mode never pretends to have a Muse Image illustration.
PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _load(fixtures_dir: Path, name: str):
    path = fixtures_dir / name
    if not path.exists():
        raise ProviderError("fixture_missing", f"fixture {name} not found")
    return json.loads(path.read_text())


class MockMeta:
    name = "mock"

    def __init__(self, fixtures_dir: Path = FIXTURES_DIR):
        self.fixtures_dir = fixtures_dir

    def structured_json(self, system: str, user: str, schema: dict, name: str = "result") -> dict:
        data = _load(self.fixtures_dir, "mock_meta.json")
        if name not in data:
            raise MetaError(f"no mock response for {name}")
        return data[name]

    def generate_image(self, prompt: str) -> bytes:
        return PLACEHOLDER_PNG

    def transcribe(self, audio_bytes: bytes, mime: str) -> str:
        check_wav(audio_bytes, mime)
        return _load(self.fixtures_dir, "mock_meta.json")["transcript"]


class MockOverpass:
    name = "mock"

    def __init__(self, fixtures_dir: Path = FIXTURES_DIR):
        self.fixtures_dir = fixtures_dir

    def places_near(
        self, lat: float, lon: float, radius_m: float, categories: list[str] | None = None
    ) -> list[Place]:
        places = [Place.model_validate(p) for p in _load(self.fixtures_dir, "sample_places.json")]
        return [
            p
            for p in places
            if haversine_m(lat, lon, p.lat, p.lon) <= radius_m
            and (categories is None or p.category in categories)
        ]


class MockORS:
    name = "mock"

    def __init__(self, fixtures_dir: Path = FIXTURES_DIR):
        self.fixtures_dir = fixtures_dir

    def walk(self, start: tuple[float, float], end: tuple[float, float]) -> RouteLeg:
        key = f"{coord_key(*start)}|{coord_key(*end)}"
        for route in _load(self.fixtures_dir, "sample_routes.json"):
            if route["key"] == key:
                return RouteLeg.model_validate(route["leg"])
        raise ProviderError("routing_unavailable", "no captured route for this pair in mock mode")
