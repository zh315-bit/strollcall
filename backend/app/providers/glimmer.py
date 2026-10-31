"""Muse Glimmer (Meta's open-weights model) on our own Modal Dedicated Endpoint, for wish reading.

Only intent parsing uses it (TEXT_PROVIDER_PARSE=open_weights), and only inside a warm window
(services/open_weights.py): the endpoint scales to zero, and a cold start takes about 3 minutes,
so a call outside a window would only wake a GPU and then fall back. One attempt, with a short
timeout (OPEN_WEIGHTS_TIMEOUT_S, 3 s); the caller falls back to the Meta API on any error.

The endpoint is SGLang serving meta-models/Muse-Glimmer-30B in BF16 on one H200
(docs/open_weights.md). Reasoning is off: the prompt opens the answer channel directly
(answer_prompt), and SGLang constrains the answer to the JSON schema.

Cost: Modal bills the GPU per second while a container is up, not per token. Each call records
its share (latency x hourly price) in the spend guard; the warm windows themselves are counted by
scripts/glimmer_warm.py against Modal's own billing report. Every call writes one run-log line
with the model, precision, host, GPU and deployment, never the user's text.
"""

import json
import logging
import time

import openai
from openai import OpenAI

from app.core.budget import SpendGuard
from app.core.config import Settings, forbid_live_client_in_tests, get_settings, output_cap_override
from app.core.errors import ProviderError
from app.providers.meta import _create_logged, _describe
from app.providers.spark_open import parse_json_object

log = logging.getLogger(__name__)

MODEL_LABEL = "muse-glimmer"


MAX_LIST_ITEMS = 8


def bounded(schema: dict) -> dict:
    """The schema with every list bounded, for constrained decoding: a list of choices holds each
    choice at most once, any other list at most MAX_LIST_ITEMS. At temperature 0 under the grammar,
    Glimmer once repeated "duration_min" in inferred_fields until the output cap (evaluation run 1,
    2 of 12 texts). The app's own validation is unchanged."""
    if not isinstance(schema, dict):
        return schema
    out = {k: (bounded(v) if isinstance(v, dict) else v) for k, v in schema.items()}
    if "properties" in out:
        out["properties"] = {k: bounded(v) for k, v in out["properties"].items()}
    if out.get("type") == "array":
        enum = (out.get("items") or {}).get("enum")
        out["maxItems"] = min(out.get("maxItems", MAX_LIST_ITEMS), len(enum) if enum else MAX_LIST_ITEMS)
        if enum:
            out["uniqueItems"] = True
    return out


def answer_prompt(system: str, user: str) -> str:
    """The model's own chat template (chat_template.jinja at the pinned revision) for one system and
    one user message, ending where the assistant writes to the user. The template's generation
    prompt stops at "<|start|>assistant", and the model then picks its reasoning channel
    ("to=self") or the answer ("to=user"); starting the answer channel skips reasoning, which
    "Reasoning strength" cannot (its lowest level, low, still reasoned ~800 tokens, ~5 s).
    The server adds the BOS token itself."""
    return (f"<|start|>system<|message|>{system}\n\n# Valid recipients: \"self\", \"user\".<|eot|>"
            f"<|start|>user<|message|>{user}<|eot|><|start|>assistant to=user<|message|>")


class GlimmerError(ProviderError):
    def __init__(self, message: str):
        super().__init__("model_unavailable", message)


def deployment(s: Settings | None = None) -> dict:
    """What served a parse: for /health, plan records and the page's label."""
    s = s or get_settings()
    return {"model": MODEL_LABEL, "repo": s.open_weights_repo, "revision": s.open_weights_revision[:7],
            "precision": s.open_weights_precision, "host": "Modal", "gpu": s.open_weights_gpu,
            "deployment": s.open_weights_deployment}


def run_log_line(job: str, latency_s: float, usage, cost: float, outcome: str, s: Settings | None = None) -> str:
    s = s or get_settings()
    tokens = f" in={usage.prompt_tokens} out={usage.completion_tokens}" if usage else ""
    return (f"{MODEL_LABEL}, {s.open_weights_precision}, Modal, {s.open_weights_gpu}"
            f" | {s.open_weights_repo}@{s.open_weights_revision[:7]} deployment={s.open_weights_deployment}"
            f" | job={job} {outcome} latency={latency_s:.2f}s{tokens} est=${cost:.5f}")


class GlimmerProvider:
    name = "glimmer"

    def __init__(self, settings: Settings | None = None, guard: SpendGuard | None = None,
                 client: OpenAI | None = None, timeout_s: float | None = None):
        self.settings = s = settings or get_settings()
        self.guard = guard or SpendGuard()
        api_key = s.open_weights_api_key.get_secret_value()
        if client is None and not api_key:
            raise GlimmerError("OPEN_WEIGHTS_API_KEY is not set")
        if client is None:
            forbid_live_client_in_tests("GlimmerProvider")
        self.client = client or OpenAI(base_url=s.open_weights_base_url, api_key=api_key,
                                       timeout=timeout_s or s.open_weights_timeout_s, max_retries=0)
        self.last_call: dict = {}  # raw output, tokens and latency of the last call (evaluation)

    def _cost(self, seconds: float) -> float:
        return seconds * self.settings.open_weights_usd_per_hour / 3600

    def structured_json(self, system: str, user: str, schema: dict, name: str = "result") -> dict:
        s = self.settings
        max_tokens = output_cap_override.get() or s.meta_max_output_tokens
        request = {
            "model": s.open_weights_model,
            "prompt": answer_prompt(system, user),
            "max_tokens": max_tokens,
            "temperature": 0,  # extraction, not writing: the same wish reads the same way
            "stop": ["<|eot|>", "<|eom|>"],
            "extra_body": {"json_schema": json.dumps(bounded(schema))},  # SGLang's constrained decoding
        }
        self.guard.check(self._cost(s.open_weights_timeout_s))
        started = time.monotonic()
        self.last_call = {}
        try:
            resp = _create_logged(self.client.completions, "Muse Glimmer", **request)
        except openai.APIError as e:
            took = time.monotonic() - started
            log.warning("open-weights run log: %s", run_log_line(name, took, None, self._cost(took),
                                                                   f"failed ({type(e).__name__})", s))
            raise GlimmerError(f"Muse Glimmer: {_describe(e)}") from e
        took = time.monotonic() - started
        cost = self._cost(took)
        usage, choice = resp.usage, resp.choices[0]
        content = choice.text or ""
        self.last_call = {"latency_s": took, "content": content,
                          "prompt_tokens": getattr(usage, "prompt_tokens", None),
                          "completion_tokens": getattr(usage, "completion_tokens", None),
                          "finish_reason": getattr(choice, "finish_reason", None), "cost_usd": cost}
        line = run_log_line(name, took, usage, cost, "ok", s)
        self.guard.record("text", MODEL_LABEL, cost, line)
        log.info("open-weights run log: %s", line)
        if getattr(choice, "finish_reason", None) == "length":
            raise GlimmerError(f"Muse Glimmer output truncated at {max_tokens} tokens")
        try:
            return parse_json_object(content)
        except ValueError as e:
            raise GlimmerError(f"Muse Glimmer returned invalid JSON for {name}") from e

    def generate_image(self, prompt: str) -> bytes:
        raise GlimmerError("wish reading only; images stay on the Meta Model API")

    def transcribe(self, audio_bytes: bytes, mime: str) -> str:
        raise GlimmerError("wish reading only; voice stays on the Meta Model API")
