"""Spend guard for Meta Model API calls.

The Billing page's Spend Limit only alerts, so we enforce our own daily cap.
Prices are Standard mode, from dev.meta.ai/docs/pricing-rate-limits (checked 2026-10-28).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.models.db import db

log = logging.getLogger(__name__)

# USD per 1M tokens (Muse Spark, Standard mode). Reasoning tokens are billed as output.
SPARK_INPUT_PER_M = 1.25
SPARK_CACHED_INPUT_PER_M = 0.15
SPARK_OUTPUT_PER_M = 4.25
IMAGE_PER_IMAGE = 0.01
VOICE_PER_HOUR = 0.18


class BudgetExceeded(Exception):
    pass


def text_cost(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    uncached = max(input_tokens - cached_tokens, 0)
    return (
        uncached * SPARK_INPUT_PER_M
        + cached_tokens * SPARK_CACHED_INPUT_PER_M
        + output_tokens * SPARK_OUTPUT_PER_M
    ) / 1_000_000


def image_cost(n_images: int) -> float:
    return n_images * IMAGE_PER_IMAGE


def voice_cost(audio_ms: int) -> float:
    # Billed in whole seconds, rounded down.
    return (audio_ms // 1000) * VOICE_PER_HOUR / 3600


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class SpendGuard:
    def __init__(self, daily_cap_usd: float | None = None, db_path: Path | None = None):
        settings = get_settings()
        self.daily_cap = settings.daily_budget_usd if daily_cap_usd is None else daily_cap_usd
        self.db_path = db_path or settings.db_path

    def today_total(self) -> float:
        rows = db(self.db_path).query(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM meta_spend WHERE day = ?", (_today(),)
        )
        return float(rows[0]["total"])

    def can_spend(self, estimate_usd: float) -> bool:
        return self.today_total() + estimate_usd <= self.daily_cap

    def check(self, estimate_usd: float) -> None:
        """Raise BudgetExceeded if this call could push today's spend past the cap."""
        total = self.today_total()
        if total + estimate_usd > self.daily_cap:
            raise BudgetExceeded(
                f"daily Meta budget ${self.daily_cap:.2f} reached "
                f"(spent ${total:.4f}, next call up to ${estimate_usd:.4f})"
            )

    def record(self, kind: str, model: str, cost_usd: float, detail: str = "") -> None:
        now = datetime.now(timezone.utc)
        db(self.db_path).run(
            "INSERT INTO meta_spend (day, created_at, kind, model, cost_usd, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (now.date().isoformat(), now.isoformat(), kind, model, cost_usd, detail),
        )
        log.info("meta spend: %s %s $%.6f (%s)", kind, model, cost_usd, detail)
