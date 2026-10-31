import os
from contextvars import ContextVar
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
    # After B accepts, both people are waiting: these calls run at this effort (about 1-2 s each
    # instead of 3-8 s at "low"; measured 2026-10-28).
    accept_reasoning_effort: str = "minimal"
    meta_timeout_s: float = 45.0
    # Text jobs: meta (Meta Model API) or spark_open (Muse Spark Open on a hosted partner;
    # off until credits or a fix arrive, see docs/fallback_open_weights.md). Image and voice
    # always use the Meta Model API.
    text_provider: str = "meta"
    spark_open_base_url: str = "https://api.fireworks.ai/inference/v1"
    spark_open_model: str = "accounts/fireworks/models/muse-spark-open"
    spark_open_api_key: SecretStr = SecretStr("")
    spark_open_input_per_m: float = 0.0  # USD per 1M tokens, from the provider's model page; required
    spark_open_output_per_m: float = 0.0
    spark_open_json_mode: str = "json_schema"  # or "prompt" if the provider rejects json_schema
    # Wish reading (intent parsing only) on Muse Glimmer, Meta's open-weights model, on our own
    # Modal Dedicated Endpoint (docs/open_weights.md). TEXT_PROVIDER_PARSE=open_weights turns it on;
    # it is used only inside a warm window opened by scripts/glimmer_warm.py, and falls back to
    # the Meta API after open_weights_timeout_s. Every other text job stays on text_provider.
    text_provider_parse: str = "meta"  # meta / open_weights
    open_weights_api_key: SecretStr = SecretStr("")  # Modal proxy token, sent as a Bearer token
    open_weights_base_url: str = "https://zh3782--ep-strollcall-glimmer-server.us-west.modal.direct/v1"
    open_weights_model: str = "strollcall-glimmer"  # the endpoint's served model name
    open_weights_repo: str = "meta-models/Muse-Glimmer-30B"
    open_weights_revision: str = "f84ecc3a0ea984a4c04542a84269e3d065350a6e"
    open_weights_precision: str = "BF16"
    open_weights_gpu: str = "H200"
    open_weights_deployment: str = "ep-ez0BAxZPNiSL3x40VCpbFi"  # Modal endpoint id
    # H200 $4.54/h + 4 CPU cores + 16 GiB (modal.com/pricing, 2026-10-31): billed per second warm.
    open_weights_usd_per_hour: float = 4.86
    open_weights_timeout_s: float = 3.0
    # Cap on output tokens per Spark call, reasoning included. Truncation is logged.
    meta_max_output_tokens: int = 4096  # 2048 truncated 3 of 10 live intent calls (2026-10-28)
    # Intent parsing at minimal effort used 561-884 output tokens (2026-10-30); room for about twice that.
    parse_max_output_tokens: int = 1536
    # The invite line at minimal effort used 223-529 output tokens locally, up to 844 live (2026-10-30).
    card_max_output_tokens: int = 1536

    # Routing and places run on local OSM data by default (no daily quota); see build_graph.py.
    routing_provider: str = "local"  # local / ors / mock
    places_provider: str = "snapshot"  # snapshot / overpass / mock
    graph_path: Path = ROOT_DIR / "data" / "nyc_graph.npz"
    places_snapshot_path: Path = ROOT_DIR / "data" / "nyc_places.json.gz"
    route_pois_path: Path = ROOT_DIR / "deploy" / "data" / "nyc_pois.json.gz"  # build_route_pois.py

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
    planner_w_pass_by: float = 0.25  # a place the walker asked to pass by: soft, never a constraint

    debug: bool = False  # enables /api/dev/*
    meta_diag: bool = False  # enables /api/dev/meta_diag only, for a support ticket; switch off afterwards
    use_mocks: bool = False
    db_path: Path = ROOT_DIR / "data" / "strollcall.db"  # SQLite, when DATABASE_URL is not set
    database_url: SecretStr = SecretStr("")  # Postgres (Neon pooled URL, sslmode=require) when deployed


@lru_cache
def get_settings() -> Settings:
    return Settings()


def forbid_live_client_in_tests(what: str) -> None:
    """Tests must never reach a real API: creating a live client under pytest is a bug."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError(f"{what}: live API client created inside pytest (use the mocks)")


# Set for a block of work (e.g. planning after B accepts) to override Settings.reasoning_effort.
reasoning_override: ContextVar[str | None] = ContextVar("reasoning_override", default=None)
# Set around one kind of call to override Settings.meta_max_output_tokens (e.g. intent parsing).
output_cap_override: ContextVar[int | None] = ContextVar("output_cap_override", default=None)
