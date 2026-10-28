import os
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
FIXTURES_DIR = ROOT_DIR / "fixtures"


class Settings(BaseSettings):
    """All runtime settings come from the environment (or a local .env file).

    Keys are SecretStr so they never show up in reprs or logs.
    """

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    model_api_key: SecretStr = SecretStr("")
    model_base_url: str = "https://api.meta.ai/v1"
    model_id: str = "muse-spark-1.3"
    image_model_id: str = "muse-image-1.0"
    voice_model_id: str = "muse-voice-transcribe-1.0"
    # Muse Spark 1.3 reasons by default and reasoning tokens are billed as output.
    reasoning_effort: str = "low"
    meta_timeout_s: float = 45.0
    # Cap on output tokens per Spark call, reasoning included. Truncation is logged.
    meta_max_output_tokens: int = 4096  # 2048 truncated 3 of 10 live intent calls (2026-10-28)

    # Routing and places run on local OSM data by default (no daily quota); see build_graph.py.
    routing_provider: str = "local"  # local / ors / mock
    places_provider: str = "snapshot"  # snapshot / overpass / mock
    graph_path: Path = ROOT_DIR / "data" / "nyc_graph.npz"
    places_snapshot_path: Path = ROOT_DIR / "data" / "nyc_places.json.gz"

    ors_api_key: SecretStr = SecretStr("")
    # Own ORS budget, counted over a rolling 24 h like the ORS quota itself. Our key's real
    # quota is lower than the published plan (directions reported 200/day), so the caps
    # below are a backstop and the x-ratelimit-remaining header is honoured as well.
    ors_matrix_soft_cap: int = 300
    ors_directions_soft_cap: int = 1800
    ors_quota_reserve: int = 5  # stop when the header says this many requests are left
    ors_cache_days: int = 30
    # Who is calling (app / capture_fixtures / benchmark / smoke_test / warm_cache), for usage logs.
    strollcall_caller: str = "app"

    overpass_url: str = "https://overpass-api.de/api/interpreter"
    overpass_mirror_url: str = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    # User-facing requests fail fast; scripts/capture_fixtures.py raises this to 60 s.
    overpass_timeout_s: float = 15.0
    cache_dir: Path = ROOT_DIR / "cache"

    daily_budget_usd: float = 15.0

    # Planner score weights; every term is normalized to 0-1 (DEV_DOC 6.3).
    planner_w_fit: float = 1.0
    planner_w_gap: float = 0.8
    planner_w_time_dev: float = 0.6
    planner_w_detour: float = 0.4
    planner_w_uncertainty: float = 0.3
    planner_w_named_place: float = 0.1  # named POI beats an equally good street corner

    debug: bool = False  # enables /api/dev/*
    use_mocks: bool = False
    db_path: Path = ROOT_DIR / "data" / "strollcall.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def forbid_live_client_in_tests(what: str) -> None:
    """Tests must never reach a real API: creating a live client under pytest is a bug."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError(f"{what}: live API client created inside pytest (use the mocks)")
