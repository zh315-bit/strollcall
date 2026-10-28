import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def load_origins() -> dict:
    return json.loads((ROOT / "fixtures" / "nyc_origins.json").read_text())


def point(p: dict) -> tuple[float, float]:
    return (p["lat"], p["lon"])


def load_cases() -> list[dict]:
    """Benchmark cases joined with their origin pairs: [{id, a, b, intent, depart_at}]."""
    from datetime import datetime

    from app.models.schemas import WalkIntent

    pairs = {p["id"]: p for p in load_origins()["pairs"]}
    data = json.loads((ROOT / "fixtures" / "benchmark_cases.json").read_text())
    depart_at = datetime.fromisoformat(data["depart_at"])
    return [
        {
            "id": c["pair"],
            "pair": pairs[c["pair"]],
            "a": point(pairs[c["pair"]]["a"]),
            "b": point(pairs[c["pair"]]["b"]),
            "intent": WalkIntent.model_validate(c["intent"]),
            "depart_at": depart_at,
        }
        for c in data["cases"]
    ]
