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

    ors_api_key: SecretStr = SecretStr("")
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    daily_budget_usd: float = 15.0
    use_mocks: bool = False
    db_path: Path = ROOT_DIR / "data" / "strollcall.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
