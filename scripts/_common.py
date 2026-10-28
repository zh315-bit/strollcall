import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def load_origins() -> dict:
    return json.loads((ROOT / "fixtures" / "nyc_origins.json").read_text())


def point(p: dict) -> tuple[float, float]:
    return (p["lat"], p["lon"])
