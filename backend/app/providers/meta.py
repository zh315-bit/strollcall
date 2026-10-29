"""Meta Model API adapter: Muse Spark (structured JSON), Muse Image, Muse Voice Transcribe.

Formats checked against dev.meta.ai/docs on 2026-10-28:
- Spark: OpenAI-compatible Chat Completions with response_format json_schema.
- Image: OpenAI-compatible /v1/images/generations, base64 image in data[].b64_json.
- Voice: NOT OpenAI-compatible. POST /v1/asr/transcribe, multipart `request` (JSON) +
  `audio` (mono 16-bit PCM WAV at 16 or 24 kHz, max 10 min). The browser converts to WAV.

Every call goes through the SpendGuard. Each call is retried at most once.
"""

import base64
import io
import json
import logging
import time
import wave

import httpx
import openai
from openai import OpenAI

from app.core.budget import SpendGuard, image_cost, text_cost, voice_cost
from app.core.config import Settings, forbid_live_client_in_tests, get_settings, reasoning_override
from app.core.errors import ProviderError

log = logging.getLogger(__name__)

WAV_MIME_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}
MAX_AUDIO_SECONDS = 600

TRANSIENT_ERRORS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)
RETRY_WAIT_S = 1.5
# After a call fails twice with model_not_found, later calls for that model skip the request for
# this long and fall back at once (labelled), instead of each spending ~2 s on a 404 and a retry.
NOT_FOUND_PAUSE_S = 120.0
_not_found_until: dict[str, float] = {}


def _is_not_found(e: Exception) -> bool:
    body = getattr(e, "body", None)
    code = (body.get("code") or (body.get("error") or {}).get("code")) if isinstance(body, dict) else None
    return isinstance(e, openai.NotFoundError) and code == "model_not_found"


def _transient(e: Exception) -> bool:
    """Timeouts, 429, 5xx, and the intermittent 404 model_not_found seen on 2026-10-28 for a model
    the same key can list (it cleared within minutes, locally and on the server alike)."""
    return isinstance(e, TRANSIENT_ERRORS) or _is_not_found(e)


class MetaError(ProviderError):
    def __init__(self, message: str):
        super().__init__("model_unavailable", message)


class MetaInvalidJSON(MetaError):
    pass


_clients: dict[tuple, OpenAI] = {}


def _shared_client(base_url: str, api_key: str, timeout: float) -> OpenAI:
    """One client (and connection pool) per process: building one costs ~0.3 s on the free plan."""
    k = (base_url, api_key, timeout)
    if k not in _clients:
        _clients[k] = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)
    return _clients[k]


class MetaProvider:
    name = "meta"

    def __init__(
        self,
        settings: Settings | None = None,
        guard: SpendGuard | None = None,
        client: OpenAI | None = None,
        http: httpx.Client | None = None,
    ):
        self.settings = settings or get_settings()
        self.guard = guard or SpendGuard()
        api_key = self.settings.model_api_key.get_secret_value()
        if client is None and not api_key:
            raise MetaError("MODEL_API_KEY is not set")
        if client is None:
            forbid_live_client_in_tests("MetaProvider")
        # The OpenAI SDK does not read MODEL_API_KEY on its own, so pass it explicitly.
        # Retries are ours (at most one), not the SDK's.
        self.client = client or _shared_client(self.settings.model_base_url, api_key, self.settings.meta_timeout_s)
        self._http = http  # created on first transcribe
        self._api_key = api_key

    def structured_json(self, system: str, user: str, schema: dict, name: str = "result") -> dict:
        model = self.settings.model_id
        max_tokens = self.settings.meta_max_output_tokens
        # Upper bound: ~3 chars per input token, and the full output allowance.
        est_input = (len(system) + len(user) + len(json.dumps(schema))) // 3 + 50
        estimate = text_cost(est_input, max_tokens)
        if time.monotonic() < _not_found_until.get(model, 0.0):
            raise MetaError(f"Muse Spark skipped: {model} returned model_not_found in the last "
                            f"{NOT_FOUND_PAUSE_S:.0f} s")

        last_error: MetaError | None = None
        not_found = 0
        for attempt in range(2):
            self.guard.check(estimate)
            try:
                resp = _create_logged(self.client.chat.completions, "Muse Spark",
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": name, "schema": schema},
                    },
                    reasoning_effort=reasoning_override.get() or self.settings.reasoning_effort,
                    max_completion_tokens=max_tokens,
                )
            except openai.APIError as e:
                if _transient(e):
                    last_error = MetaError(f"Muse Spark: {_describe(e)}")
                    log.warning("Muse Spark attempt %d failed: %s", attempt + 1, _describe(e))
                    not_found += _is_not_found(e)
                    if not_found == 2:
                        _not_found_until[model] = time.monotonic() + NOT_FOUND_PAUSE_S
                        log.warning("Muse Spark: pausing %s for %.0f s after model_not_found twice",
                                    model, NOT_FOUND_PAUSE_S)
                    if attempt == 0:
                        time.sleep(RETRY_WAIT_S)
                    continue
                raise MetaError(f"Muse Spark request rejected: {_describe(e)}") from e

            _not_found_until.pop(model, None)
            self._record_text(resp, model, name)
            choice = resp.choices[0]
            if getattr(choice, "finish_reason", None) == "length":
                # Output (reasoning included) hit max_completion_tokens; the JSON is cut off.
                last_error = MetaInvalidJSON(f"Muse Spark output truncated at {max_tokens} tokens")
                log.warning("Muse Spark attempt %d truncated at %d tokens", attempt + 1, max_tokens)
                continue
            content = choice.message.content or ""
            try:
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("top-level JSON is not an object")
                return data
            except ValueError:
                last_error = MetaInvalidJSON(f"Muse Spark returned invalid JSON for {name}")
                log.warning("Muse Spark attempt %d returned invalid JSON for %s", attempt + 1, name)

        assert last_error is not None
        raise last_error

    def _record_text(self, resp, model: str, name: str) -> None:
        usage = resp.usage
        if usage is None:
            # No usage reported: record the worst case rather than nothing.
            self.guard.record("text", model, text_cost(0, self.settings.meta_max_output_tokens), f"{name} (no usage)")
            return
        details = getattr(usage, "prompt_tokens_details", None)
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        cost = text_cost(usage.prompt_tokens, usage.completion_tokens, cached)
        self.guard.record(
            "text", model, cost, f"{name} in={usage.prompt_tokens} out={usage.completion_tokens} "
            f"finish={getattr(resp.choices[0], 'finish_reason', None)}"
        )

    def generate_image(self, prompt: str) -> bytes:
        """Return the generated image as bytes (webp)."""
        model = self.settings.image_model_id
        last_error: MetaError | None = None
        for attempt in range(2):
            self.guard.check(image_cost(1))
            try:
                resp = _create_logged(self.client.images, "Muse Image", method="generate",
                    model=model,
                    prompt=prompt,
                    n=1,
                    # Meta extensions: an illustration needs no web lookups, and one pass is enough.
                    extra_body={
                        "reasoning_strength": "low",
                        "tool_enablement": {"enable_web_search": False, "enable_shell": False},
                    },
                )
            except openai.APIError as e:
                if _transient(e):
                    last_error = MetaError(f"Muse Image: {_describe(e)}")
                    log.warning("Muse Image attempt %d failed: %s", attempt + 1, _describe(e))
                    if attempt == 0:
                        time.sleep(RETRY_WAIT_S)
                    continue
                raise MetaError(f"Muse Image request rejected: {_describe(e)}") from e

            images = [d.b64_json for d in (resp.data or []) if d.b64_json]
            self.guard.record("image", model, image_cost(len(images)), "invite card")
            if not images:
                raise MetaError("Muse Image returned no image")
            return base64.b64decode(images[0])

        assert last_error is not None
        raise last_error

    def _voice_http(self) -> httpx.Client:
        if self._http is None:
            forbid_live_client_in_tests("MetaProvider voice client")
            self._http = httpx.Client(timeout=self.settings.meta_timeout_s)
        return self._http

    def transcribe(self, audio_bytes: bytes, mime: str) -> str:
        duration_ms = check_wav(audio_bytes, mime)
        model = self.settings.voice_model_id
        url = self.settings.model_base_url.rstrip("/") + "/asr/transcribe"
        request = {"model": model, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}

        last_error: MetaError | None = None
        for attempt in range(2):
            self.guard.check(voice_cost(duration_ms))
            try:
                resp = self._voice_http().post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Accept": "application/json",
                    },
                    files={
                        "request": (None, json.dumps(request), "application/json"),
                        "audio": ("audio.wav", audio_bytes, "audio/wav"),
                    },
                )
            except httpx.HTTPError as e:
                last_error = MetaError(f"{type(e).__name__} from Muse Voice Transcribe")
                log.warning("Voice attempt %d failed: %s", attempt + 1, type(e).__name__)
                continue

            log.info("Muse Voice call model=%s status=%s request_id=%s", model, resp.status_code,
                     request_id(resp.headers))
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = MetaError(f"Muse Voice Transcribe HTTP {resp.status_code}")
                log.warning("Voice attempt %d got HTTP %d", attempt + 1, resp.status_code)
                continue
            if resp.status_code != 200:
                raise MetaError(f"Muse Voice Transcribe rejected the audio: HTTP {resp.status_code}")

            body = resp.json()
            billed_ms = int(body.get("audioDurationMs") or duration_ms)
            self.guard.record("voice", model, voice_cost(billed_ms), f"{billed_ms} ms")
            return (body.get("transcript") or "").strip()

        assert last_error is not None
        raise last_error


def request_id(headers) -> str | None:
    """Meta's request ID, for support tickets (never contains anything secret)."""
    if headers is None:
        return None
    return headers.get("x-request-id") or headers.get("request-id") or headers.get("x-fb-trace-id")


def _create_logged(resource, label: str, method: str = "create", **kwargs):
    """resource.<method>(**kwargs), logging status and request ID for every call, ok or not."""
    raw_api = getattr(resource, "with_raw_response", None)
    if raw_api is None:  # test doubles
        return getattr(resource, method)(**kwargs)
    try:
        raw = getattr(raw_api, method)(**kwargs)
    except openai.APIStatusError as e:
        log.warning("%s call model=%s status=%s request_id=%s", label, kwargs.get("model"), e.status_code,
                    request_id(e.response.headers))
        raise
    log.info("%s call model=%s status=%s request_id=%s", label, kwargs.get("model"), raw.http_response.status_code,
             request_id(raw.headers))
    return raw.parse()


def _describe(e: Exception) -> str:
    """Error type, HTTP status, the API's own message and request ID (none contain our key)."""
    status = getattr(e, "status_code", None)
    body = getattr(e, "body", None)
    message = body.get("message") if isinstance(body, dict) else None
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        message = body["error"].get("message") or body["error"].get("code")
    response = getattr(e, "response", None)
    rid = request_id(getattr(response, "headers", None))
    parts = [type(e).__name__] + ([f"HTTP {status}"] if status else []) + ([str(message)[:160]] if message else [])
    return ", ".join(parts + ([f"request_id {rid}"] if rid else []))


def check_wav(audio_bytes: bytes, mime: str) -> int:
    """Validate the upload is the WAV the endpoint accepts; return its duration in ms."""
    if mime.split(";")[0].strip().lower() not in WAV_MIME_TYPES:
        raise MetaError(f"audio must be WAV, got {mime}")
    try:
        with wave.open(io.BytesIO(audio_bytes)) as w:
            channels, width, rate, frames = (
                w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            )
    except (wave.Error, EOFError) as e:
        raise MetaError("audio is not a readable WAV file") from e
    if channels != 1 or width != 2 or rate not in (16000, 24000):
        raise MetaError("WAV must be mono 16-bit PCM at 16 or 24 kHz")
    duration_ms = frames * 1000 // rate
    if duration_ms > MAX_AUDIO_SECONDS * 1000:
        raise MetaError("audio is longer than 10 minutes")
    return duration_ms
