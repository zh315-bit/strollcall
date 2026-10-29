# Meta Model API support ticket: `model_not_found` from cloud egress

- **Team ID:** `<TEAM_ID>`
- **Project:** StrollCall (Meta Global AI Developer Hackathon)
- **Base URL:** `https://api.meta.ai/v1` (OpenAI-compatible, `openai` Python SDK 1.82.0)
- **Model:** `muse-spark-1.3` (also used: `muse-image-1.0`, `muse-voice-transcribe-1.0`)
- **API key:** the same key on every host below (not included here; identical SHA-256 fingerprint prefix on all hosts).

## Summary

The same key and the same request body succeed from a residential connection in New York and fail
from a Render server in Ashburn, Virginia (AWS). On the server, `GET /v1/models` returns 200 but the
number of listed models changes between calls (6, 9, 6), and every `POST /v1/chat/completions` with
`muse-spark-1.3` returns 404 `model_not_found`. From a second Render server in Boardman, Oregon
(AWS), `/v1/models` returns an empty list and chat fails the same way. No proxy, VPN or relay is involved; each host calls
the API directly.

## Exact error

```
HTTP 404
code: model_not_found
message: The requested model was not found.
```

## Test calls

Each run makes 3× `GET /v1/models`, then 3× `POST /v1/chat/completions` with `model=muse-spark-1.3`,
one short user message, `max_completion_tokens=64`. Timestamps are UTC, from the calling host.

### Render server, Virginia (production host): fails

Egress (ipinfo.io and ipapi.co agree): IP `74.220.49.18`, Ashburn, Virginia, US, AS14618 Amazon.com, Inc.

| UTC | Endpoint | Model | HTTP | Error | Request ID |
|---|---|---|---|---|---|
| 2026-10-29T16:16:56Z | GET /v1/models | – | 200 (6 models listed) | – | `5b0d4144-2157-465d-acfb-e9c6f13c7231` |
| 2026-10-29T16:16:58Z | GET /v1/models | – | 200 (9 models listed) | – | `221882ce-6440-45fd-80f0-0ee3b6683fef` |
| 2026-10-29T16:16:59Z | GET /v1/models | – | 200 (6 models listed) | – | `c3da139f-098a-484b-88ee-fdf7a0d703bd` |
| 2026-10-29T16:16:59Z | POST /v1/chat/completions | muse-spark-1.3 | 404 | model_not_found: The requested model was not found. | `bc8f8a26-c07e-4908-bc09-bcb988b0a894` |
| 2026-10-29T16:17:01Z | POST /v1/chat/completions | muse-spark-1.3 | 404 | model_not_found: The requested model was not found. | `9145ff54-1c4e-4731-9680-240672051623` |
| 2026-10-29T16:17:01Z | POST /v1/chat/completions | muse-spark-1.3 | 404 | model_not_found: The requested model was not found. | `5aaca296-9686-4fba-aac2-7e4d13a8ed49` |

### Residential connection, New York (comparison): succeeds

Egress: New York City, New York, US, AS701 Verizon Business (IP withheld: a home connection).

| UTC | Endpoint | Model | HTTP | Request ID |
|---|---|---|---|---|
| 2026-10-29T16:13:55Z | GET /v1/models | – | 200 (9 models listed) | `fd6050cf-92d0-44a8-a1e0-4b0cf1f6b763` |
| 2026-10-29T16:13:57Z | GET /v1/models | – | 200 (9 models listed) | `fe82f725-6e19-42d5-98d4-234639577578` |
| 2026-10-29T16:13:57Z | GET /v1/models | – | 200 (9 models listed) | `624a6ec2-29e0-41f2-bfd3-ed226c22707d` |
| 2026-10-29T16:13:58Z | POST /v1/chat/completions | muse-spark-1.3 | 200 | `8637e25a-8d40-4d29-9142-3d69055a836f` |
| 2026-10-29T16:13:58Z | POST /v1/chat/completions | muse-spark-1.3 | 200 | `d4ba5d06-3456-456d-b7fe-bd38e2c8f36c` |
| 2026-10-29T16:13:59Z | POST /v1/chat/completions | muse-spark-1.3 | 200 | `e1a4cc5a-2d6b-4329-adac-2f0bffd364d5` |

The same 404 has also appeared intermittently from the New York connection (for example request ID
`00684a19-df8d-4b7f-9ddf-22bcbc530580`, 2026-10-28 around 22:05 UTC), so this may be entitlement
caching rather than region alone. It happened again locally on 2026-10-29 at 16:58:44Z and 16:58:45Z
(request IDs `c179ebe0-c4b2-40d8-97d4-f8b8e44c9589`, `20b7074d-3458-4ce6-8923-4063646cc485`), while
`muse-image-1.0` image generation from the same machine succeeded 24 times between 17:02Z and 17:08Z.

### Render server, Oregon (temporary test service)

Egress: IP `74.220.48.143`, Boardman, Oregon, US, AS16509 Amazon.com, Inc.

Same key (same fingerprint as Virginia). Here `/v1/models` returns 200 with an **empty** list, and
every chat call returns 404.

| UTC | Endpoint | Model | HTTP | Error | Request ID |
|---|---|---|---|---|---|
| 2026-10-29T16:30:02Z | GET /v1/models | – | 200 (0 models listed) | – | `b4e33d6f-8f92-4d38-83da-525c033ad7bb` |
| 2026-10-29T16:30:04Z | GET /v1/models | – | 200 (0 models listed) | – | `cf60c850-2838-4d20-aeb1-9606df7c1a05` |
| 2026-10-29T16:30:04Z | GET /v1/models | – | 200 (0 models listed) | – | `e98adedb-8d5d-481e-aa4a-24d0d8a54bfc` |
| 2026-10-29T16:30:05Z | POST /v1/chat/completions | muse-spark-1.3 | 404 | model_not_found: The requested model was not found. | `546a7f9c-1617-4447-9aeb-aba9652f14ea` |
| 2026-10-29T16:30:05Z | POST /v1/chat/completions | muse-spark-1.3 | 404 | model_not_found: The requested model was not found. | `b497817a-9062-4e8a-9483-b14027db082b` |
| 2026-10-29T16:30:05Z | POST /v1/chat/completions | muse-spark-1.3 | 404 | model_not_found: The requested model was not found. | `3db5887b-1d60-4fb1-948b-b861ae873ca5` |

The Oregon service was temporary, for this test only.

## Questions

1. Is AWS egress from Ashburn, Virginia (AS14618) or Boardman, Oregon (AS16509) treated as an
   unsupported region for this key?
2. If it is entitlement caching, can the cache be refreshed for our team, given that `/v1/models`
   returns different lists on consecutive calls?
