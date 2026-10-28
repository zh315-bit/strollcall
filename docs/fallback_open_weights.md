# Plan: compliant fallback on Meta open-weight models (not built)

Status: plan only, written 2026-10-28. Build it only if the hosted Meta Model API stays unusable from
the deployed server. The 404 `model_not_found` seen on 2026-10-28 also happened locally and cleared
within minutes, so it may not be needed (see "When to switch").

## Why this is compliant

- The hackathon's stage-1 rule accepts "Meta Model API / open-weights models"; Muse Spark Open and
  Muse Glimmer are Meta's open-weight models.
- Hosting them on a partner platform is the documented path (dev.meta.ai/docs/muse-spark-open/deploy,
  "Hosted providers"); no proxy, VPN or routing through anyone's computer, and no attempt to
  bypass the Model API's geographic controls.

## Options

| | A (recommended): Muse Spark Open | B: Muse Glimmer |
| --- | --- | --- |
| What | 816B MoE, open weights of Muse Spark | 30B dense, distilled from Muse Spark, Apache 2.0 |
| Where | Fireworks serverless (also Together, Baseten, Groq, Nebius, Modal, OpenRouter) | Fireworks, Together or OpenRouter (launch partners) |
| API | OpenAI-compatible; Fireworks base URL `https://api.fireworks.ai/inference/v1`, model `accounts/fireworks/models/muse-spark-open` | OpenAI-compatible, model string per provider |
| Reasoning | always on; `reasoning_effort` low / medium / high / xhigh (no "minimal"); reasoning in `reasoning_content` | step-by-step reasoning |
| Fit for our jobs | closest to today's Muse Spark behaviour | cheaper and faster, weaker on long prompts; needs re-validation |

Jobs that would move: intent parsing, B's parse, negotiation, wish reading, ranking, invite text.

Jobs with no open-weight equivalent: **Muse Image** (card illustration) and **Muse Voice
Transcribe**. Under the fallback they follow the existing kill switches in DEV_DOC: text-only card
(template) and typed input only, clearly labelled. If the Model API works for these two from the
server while text fails, keep them on the Model API.

## Code changes (estimate: 2-3 hours including tests)

1. Config: `TEXT_PROVIDER = meta | open_weights`, plus `OPEN_WEIGHTS_BASE_URL`, `OPEN_WEIGHTS_MODEL`,
   `OPEN_WEIGHTS_API_KEY` (secret, set by the account owner in Render).
2. `providers/meta.py`: the adapter already uses the OpenAI SDK; make base URL / model / key come
   from the selected provider. Map our `minimal` effort to `low`. Ignore `reasoning_content`.
3. Structured output: confirm the provider accepts `response_format: json_schema` for this model; if
   it does not, ask for JSON in the prompt and keep the existing one-retry-on-invalid-JSON path
   (Pydantic validation is unchanged either way).
4. Spend guard: add the provider's per-token prices (from its model page) to `core/budget.py`, keyed
   by provider, so the daily cap still holds.
5. Sources: label results `open_weights` (a new value) so pages and reports never present them as
   Model API output; README "How Meta models are used" gets a row per model actually used.

## What must be re-tested

- Offline pytest (mock provider path unchanged; add tests for provider selection and price table).
- Live smoke test against the provider (one parse, one negotiation, one ranking).
- Pre-registered evaluations, run again as **new, separately labelled reports** (no prompt changes):
  the 10 wish cases and the 4 conflict cases. Compare extraction (10/10 today), reference wishes
  met (7/10 today), and grounding rejection rate against the Muse Spark runs.
- Latency after B accepts (7.6 s median today with `minimal`; `low` is the floor on Fireworks and
  was 3-8 s per call on the Model API), and cost per invite.
- Grounding: rejection rate of negotiation and ranking text (the checks are model-independent).

## When to switch

Switch only if, after the retry for transient `model_not_found` (commit 9149d7f), live invites
still fall back for most Meta calls over a day, or Meta confirms the Model API is not available from
cloud hosts. Until then the site stays on the Model API with the rule-based fallback labelled.

## Needs from the account owner

- An account and API key with the chosen provider (I do not create accounts or handle the key).
- Approval of the provider's per-token cost against the daily budget.
