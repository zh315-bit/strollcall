# Open-weights model: Muse Glimmer on Modal (wish reading)

StrollCall reads the wish ("a quiet 25 minutes, coffee at the end") with **Muse Glimmer**, Meta's
open-weights model, running on our own **Modal** endpoint, whenever that endpoint is warm. Otherwise,
and whenever Glimmer doesn't answer within 3 seconds, Muse Spark (`muse-spark-1.3`) on the Meta Model API
reads it. The page says which one did. Every other text job (wish menu, balancing two people, ranking,
invite line) and voice and images stay on the Meta Model API.

Eligibility: the organizers confirmed that Muse Glimmer on our own Modal account counts for "Best Build
on Meta Open Weight Models" (screenshot in `docs/`, added by the account owner).

## Deployment

| | |
| --- | --- |
| Model | `meta-models/Muse-Glimmer-30B` at revision `f84ecc3a0ea984a4c04542a84269e3d065350a6e` |
| Precision | BF16 (the full published weights; no quantization) |
| Host | Modal Dedicated Endpoint `strollcall-glimmer`, id `ep-ez0BAxZPNiSL3x40VCpbFi`, app `ap-SSWutUjD554fxv7EW23t1z`, region us-west |
| Server | SGLang (Modal-managed), with Meta's `Muse-Glimmer-30B-assistant` draft model for speculative decoding |
| Hardware | 1x H200, 4 CPU cores, 16 GiB memory |
| Scaling | min 0, max 1 container, scale-down after 120 s idle: nothing runs, or bills, between windows |
| Cold start | 199 s measured (Modal's container startup stat, 2026-10-31) |
| Cost while warm | $4.86/h: H200 $4.54 + CPU about $0.19 + memory about $0.13 (modal.com/pricing, 2026-10-31) |
| Auth | Modal proxy token (`OPEN_WEIGHTS_API_KEY`), sent as a Bearer token; never in the repo or logs |

Why this option: the published 4-bit builds would fit cheaper GPUs, but either run on llama.cpp (Meta's
GGUF files) or have no published quality numbers (Red Hat's FP8 and W4A16), and the slower GPUs would miss
the 3-second limit. The NVFP4 build needs a B200, which the Starter plan doesn't allow. BF16 on one H200
was the option already measured, at full precision. The comparison is in the session notes summarised
in the commit history (2026-10-31).

### How it was created

```bash
.venv/bin/modal token new                                  # log in (opens the browser)
.venv/bin/modal endpoint create --name strollcall-glimmer --model meta-models/Muse-Glimmer-30B
.venv/bin/modal endpoint info strollcall-glimmer --json    # URL, server id; requires proxy auth
.venv/bin/modal server autoscaler update fu-FDrX0bgShYn0SFK2Uh8qxJ --scaledown-window 120 --max-containers 1
```

The proxy token was created in the Modal dashboard (Settings > Proxy Auth Tokens) and saved to `.env`
as `OPEN_WEIGHTS_API_KEY`. On Render, the account owner sets `OPEN_WEIGHTS_API_KEY` (secret) and
`TEXT_PROVIDER_PARSE=open_weights`.

## Reasoning off

Glimmer reasons before answering by default. Its model card documents only a system-prompt line,
`Reasoning strength: <low|medium|high|xhigh>`. On a made-up wish (not an evaluation case), "low" still
used about 800 tokens and 5 s, and "none", "off" or "minimal" were no better. Glimmer's chat template ends the
generation prompt at `<|start|>assistant` and the model then chooses its reasoning channel (`to=self`)
or the answer (`to=user`). We therefore build the template's prompt and start the answer channel
ourselves (`providers/glimmer.answer_prompt`), call `/v1/completions`, and let SGLang constrain the answer
to the JSON schema (`json_schema`, every list bounded with `maxItems`). Result: 0 reasoning tokens, about
50-100 output tokens, 0.5 s per wish. Temperature 0: it is extraction, not writing.

## How it runs in the app

1. About 4 minutes before a test, the owner runs the warm-up script. It checks Modal's bill against the
   $20 stop, wakes the endpoint, prints the model, precision, GPU and ready time, reads one made-up wish
   so SGLang compiles the JSON grammar, and opens a window on the live site:

   ```bash
   .venv/bin/python scripts/glimmer_warm.py --minutes 15      # user test
   .venv/bin/python scripts/glimmer_warm.py --minutes 45      # demo recording
   .venv/bin/python scripts/glimmer_warm.py --no-site --minutes 10   # evaluation
   ```

   It pings once a minute to keep the container up, and on exit (or Ctrl-C) closes the window. Two
   minutes later the endpoint is at zero.
2. Inside a window (`POST /api/open-weights/window`, authorized with the same Modal token, stored in the
   database), `/api/intents/parse` tries Glimmer once with a 3 s timeout. Any error, timeout or answer
   that fails the app's own `WalkIntent` validation goes to Muse Spark, and the result carries
   `fallback_from: "glimmer"`. Outside a window Glimmer is never called, so a stray request never
   starts a GPU.
3. Labels and records: the parse result has `source` (`glimmer` or `meta`) and `read_by` (model,
   repo@revision, precision, host, GPU, endpoint id). The New walk page shows "Read by Muse Glimmer (open
   weights, on Modal)"; an invite stores who read A's and B's wishes and shows it under the plan.
   `/health` shows `open_weights`: the deployment and the window.
4. Guesses are never hard rules (`services/intent.ground_in_text`, for every model): each listed item
   is checked against the person's own words. An item with none of their words is a guess: a dashed chip
   they can remove (`inferred_items`). A hard constraint stays hard only if all its words are theirs;
   otherwise it becomes a soft vibe. An `avoid` with a crowd word (the planner would drop crowded
   meeting points) that they didn't say becomes a soft "avoid ..." vibe. The planner enforces only
   "open" hard constraints and crowd avoids; everything else only changes the score.
5. Run log: each Glimmer call writes one line, to the server log and the spend log, with no user text:
   `muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.44s in=383 out=51 est=$0.00060`.

## Budget

Modal's Starter plan includes $30 a month; the workspace limit in the dashboard is $25, and the warm-up
script refuses to start a window that could take the month past **$20** (it reads `modal billing report`).
Each call records its share of the warm GPU (latency x $4.86/h) in the spend guard. A window costs the
cold start (about 3.3 min, $0.27), its length, and 2 idle minutes ($0.16).

| Window | Warm time | About $ |
| --- | --- | --- |
| Evaluation, runs 1 and 2 (done 2026-10-31) | ~15 min | ~0.8 |
| Demo recording | 45 min | 4.1 |
| User tests: about 15 min each (warm-up 4 min before the invite) | 15 min each | ~1.6 each |
| Reserve (judging, retries) | rest up to $20 | |

Spent by 2026-10-31 15:05 ET (Modal's report): $1.46, including the first deployment.

## Evaluation

Pre-registered: `scripts/eval_open_weights.py` (cases from `fixtures/wish_cases.json`, expected values and
scoring) was committed before the first run.

```bash
.venv/bin/python scripts/glimmer_warm.py --no-site --minutes 10    # terminal 1
.venv/bin/python scripts/eval_open_weights.py --run 3              # terminal 2; never overwrites a run
.venv/bin/python scripts/compare_open_weights.py 1 2 3             # side by side; run 2 listed as void
```

Output: `benchmarks/<date>-open-weights-run<N>.md` and `sample_outputs/open_weights/run<N>/`: per text
and per case, each model's raw output next to the validated result, and `run_log.txt` (one line per
Glimmer call).

Run 1 (2026-10-31, the baseline, reported as is):

| | Muse Glimmer (Modal) | muse-spark-1.3 (Meta API) |
| --- | --- | --- |
| Valid WalkIntent | 10/12 | 12/12 |
| Duration / ending right | 10/10, 5/5 | 12/12, 6/6 |
| Latency median / max | 0.55 s / 6.84 s | 3.58 s / 5.64 s |
| Within 3 s | 10/12 | 3/12 |
| Cost per parse | $0.0022 (GPU share) | $0.0042 |
| Wish recognition: expected found / extra | 9/10 / 3 | 10/10 / 0 |

The 2 invalid answers were the two wheelchair texts: Glimmer repeated `"duration_min"` in
`inferred_fields` until the 1,536-token cap. In the app these would have timed out at 3 s and fallen
back to Muse Spark. The fix bounds every list in the schema Glimmer decodes against (`maxItems`); it
changes no prompt. Run 2 was meant to measure the fix but is void: SGLang's grammar engine (xgrammar)
rejected the `uniqueItems` keyword it also added, so every Glimmer wish-reading request got HTTP 400. Run 2
is committed as is; the corrected fix (`maxItems` only) was checked on made-up texts only. Another run
(run 3) needs the owner's approval.

On wish recognition (a second job, which stays on Muse Spark in the app), Glimmer missed "not
Starbucks" as not-a-chain and added 3 wishes no one asked for; Muse Spark matched all 10.
