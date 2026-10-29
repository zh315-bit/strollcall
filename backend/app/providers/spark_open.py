"""Muse Spark Open (Meta's open-weight Muse Spark) on a hosted partner, for the text jobs.

Off by default (TEXT_PROVIDER=meta). Built against mocks and unit tests only; switch it on with
TEXT_PROVIDER=spark_open once the account owner has a key with the provider and has set its
per-token prices (docs/fallback_open_weights.md). Muse Image and Muse Voice Transcribe have no
open-weight equivalent: they stay on the Meta Model API (see providers.get_meta).

Same interface as MetaProvider.structured_json, so every caller (intent, negotiation, wishes,
ranking, invite text) and every validation step after it is unchanged. Differences handled here:
- reasoning is always on; our "minimal" effort maps to "low", the lowest this model accepts;
- reasoning comes back in `reasoning_content`, which is ignored;
- if the provider does not accept response_format json_schema for this model, set
  SPARK_OPEN_JSON_MODE=prompt: the schema goes into the prompt and the reply is parsed
  (a ```json fence is tolerated); Pydantic validation downstream is the same either way;
- the spend guard uses this provider's prices, which must be configured (no guessing).
Results are labelled "spark_open", never "meta". At most one retry per call.
"""

import json
import logging
import re
import time

import openai
from openai import OpenAI

from app.core.budget import SpendGuard, token_cost
from app.core.config import Settings, forbid_live_client_in_tests, get_settings, reasoning_override
from app.core.errors import ProviderError
from app.providers.meta import TRANSIENT_ERRORS, _create_logged, _describe

log = logging.getLogger(__name__)

EFFORTS = ("low", "medium", "high", "xhigh")  # what the open model accepts
RETRY_WAIT_S = 1.5
FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class SparkOpenError(ProviderError):
    def __init__(self, message: str):
        super().__init__("model_unavailable", message)


def map_effort(effort: str | None) -> str:
    """Our efforts onto the open model's: minimal (and anything unknown) -> low."""
    return effort if effort in EFFORTS else "low"


def parse_json_object(content: str) -> dict:
    m = FENCE.match(content or "")
    data = json.loads(m.group(1) if m else content)
    if not isinstance(data, dict):
        raise ValueError("top-level JSON is not an object")
    return data


class SparkOpenProvider:
    name = "spark_open"

    def __init__(self, settings: Settings | None = None, guard: SpendGuard | None = None,
                 client: OpenAI | None = None):
        self.settings = s = settings or get_settings()
        self.guard = guard or SpendGuard()
        if s.spark_open_input_per_m <= 0 or s.spark_open_output_per_m <= 0:
            raise SparkOpenError("set SPARK_OPEN_INPUT_PER_M and SPARK_OPEN_OUTPUT_PER_M from the provider's "
                                 "model page; the spend guard needs them")
        api_key = s.spark_open_api_key.get_secret_value()
        if client is None and not api_key:
            raise SparkOpenError("SPARK_OPEN_API_KEY is not set")
        if client is None:
            forbid_live_client_in_tests("SparkOpenProvider")
        self.client = client or OpenAI(base_url=s.spark_open_base_url, api_key=api_key,
                                       timeout=s.meta_timeout_s, max_retries=0)

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        s = self.settings
        return token_cost(input_tokens, output_tokens, s.spark_open_input_per_m, s.spark_open_output_per_m)

    def structured_json(self, system: str, user: str, schema: dict, name: str = "result") -> dict:
        s = self.settings
        model, max_tokens = s.spark_open_model, s.meta_max_output_tokens
        request = {
            "model": model,
            "reasoning_effort": map_effort(reasoning_override.get() or s.reasoning_effort),
            "max_completion_tokens": max_tokens,
        }
        if s.spark_open_json_mode == "prompt":
            system = (f"{system}\n\nReply with one JSON object only, no other text, matching this JSON schema:\n"
                      f"{json.dumps(schema)}")
        else:
            request["response_format"] = {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}
        request["messages"] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        est_input = (len(system) + len(user) + len(json.dumps(schema))) // 3 + 50

        last_error: SparkOpenError | None = None
        for attempt in range(2):
            self.guard.check(self._cost(est_input, max_tokens))
            try:
                resp = _create_logged(self.client.chat.completions, "Muse Spark Open", **request)
            except openai.APIError as e:
                if isinstance(e, TRANSIENT_ERRORS):
                    last_error = SparkOpenError(f"Muse Spark Open: {_describe(e)}")
                    log.warning("Muse Spark Open attempt %d failed: %s", attempt + 1, _describe(e))
                    if attempt == 0:
                        time.sleep(RETRY_WAIT_S)
                    continue
                raise SparkOpenError(f"Muse Spark Open request rejected: {_describe(e)}") from e

            usage = resp.usage
            cost = self._cost(usage.prompt_tokens, usage.completion_tokens) if usage else self._cost(0, max_tokens)
            self.guard.record("text", model, cost, f"{name} via spark_open"
                              + (f" in={usage.prompt_tokens} out={usage.completion_tokens}" if usage else " (no usage)"))
            choice = resp.choices[0]
            if getattr(choice, "finish_reason", None) == "length":
                last_error = SparkOpenError(f"Muse Spark Open output truncated at {max_tokens} tokens")
                continue
            try:
                return parse_json_object(choice.message.content or "")  # reasoning_content is ignored
            except ValueError:
                last_error = SparkOpenError(f"Muse Spark Open returned invalid JSON for {name}")
                log.warning("Muse Spark Open attempt %d returned invalid JSON for %s", attempt + 1, name)

        assert last_error is not None
        raise last_error

    def generate_image(self, prompt: str) -> bytes:
        raise SparkOpenError("no open-weight image model; images stay on the Meta Model API")

    def transcribe(self, audio_bytes: bytes, mime: str) -> str:
        raise SparkOpenError("no open-weight transcription model; voice stays on the Meta Model API")
