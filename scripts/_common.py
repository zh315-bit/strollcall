import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
# ORS request log: record which script made each call.
os.environ.setdefault("STROLLCALL_CALLER", Path(sys.argv[0]).stem or "script")


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
            "expected": c.get("expected", "feasible"),
            "b_intent": WalkIntent.model_validate(c["b_intent"]) if c.get("b_intent") else None,
            "a_text": c.get("a_text", ""),
            "b_text": c.get("b_text", ""),
            "expected_wishes": [tuple(x) for x in c.get("expected_wishes", [])],
        }
        for c in data["cases"]
    ]


def load_wish_cases() -> list[dict]:
    """fixtures/wish_cases.json in the same shape as load_cases()."""
    from datetime import datetime

    from app.models.schemas import WalkIntent

    data = json.loads((ROOT / "fixtures" / "wish_cases.json").read_text())
    depart_at = datetime.fromisoformat(data["depart_at"])
    return [
        {
            "id": c["id"],
            "pair": {"a": c["a"], "b": c["b"]},
            "a": point(c["a"]),
            "b": point(c["b"]),
            "intent": WalkIntent.model_validate(c["intent"]),
            "b_intent": WalkIntent.model_validate(c["b_intent"]),
            "depart_at": depart_at,
            "expected": "feasible",
            "a_text": c["a_text"],
            "b_text": c["b_text"],
            "expected_wishes": [tuple(x) for x in c["expected_wishes"]],
            "requirement": c["requirement"],
        }
        for c in data["cases"]
    ]
