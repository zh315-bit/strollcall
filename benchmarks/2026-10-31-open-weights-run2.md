# Open-weights evaluation, run 2: Muse Glimmer vs muse-spark-1.3 (2026-10-31)

- Glimmer: `meta-models/Muse-Glimmer-30B@f84ecc3`, BF16, Modal Dedicated Endpoint `ep-ez0BAxZPNiSL3x40VCpbFi` (SGLang), 1x H200, reasoning off (answer channel), temperature 0.
- Muse Spark: `muse-spark-1.3` on the Meta Model API, reasoning effort `minimal`.
- Cases: fixtures/wish_cases.json (pre-registered); scoring and expected values in scripts/eval_open_weights.py, committed before this run. Production prompts, unchanged.
- One request at a time; the Glimmer endpoint was warm (scripts/glimmer_warm.py).

| | Muse Glimmer (open weights, Modal) | muse-spark-1.3 (Meta API) |
| --- | --- | --- |
| Wish reading: JSON valid | 0/12 | 12/12 |
| Wish reading: valid WalkIntent | 0/12 | 12/12 |
| Duration right | 0/0 | 12/12 |
| Ending right (scored texts) | 0/0 | 6/6 |
| Latency, median / max | 0.19 s / 0.56 s | 3.09 s / 5.10 s |
| Within the 3 s fallback limit | 12/12 | 5/12 |
| Cost per parse | $0.00000 | $0.00393 |
| Wish recognition: expected found | 9/10 | 10/10 |
| Wish recognition: extra wishes | 3 | 0 |
| Wish recognition: answered (not fallback) | 10/10 | 10/10 |
| Cost per wish recognition | $0.00063 | $0.00144 |

Glimmer's cost per parse is its share of the warm GPU (latency x $4.86/h). A warm window also bills the cold start (~3.3 min, ~$0.27) and 2 idle minutes after the last call (~$0.16).

## Per text (wish reading)

| Text | Glimmer | Spark |
| --- | --- | --- |
| It's warm out, let's get a coffee we can drink sitting outside | 0.56s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 5.08s, 25 min, cafe, vibes [], avoid [], hard [] |
| Somewhere nice, about 30 minutes | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 3.24s, 30 min, None, vibes ['nice'], avoid [], hard [] |
| Coffee at the end, about 30 minutes | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 3.01s, 30 min, cafe, vibes [], avoid [], hard [] |
| A coffee on a patio in the sun would be perfect | 0.18s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 3.97s, 25 min, cafe, vibes ['sunny'], avoid [], hard [] |
| Some little local place please, not a big chain | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 2.35s, 25 min, None, vibes [], avoid ['big chain'], hard [] |
| Anywhere for coffee as long as it's not Starbucks | 0.18s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 1.91s, 25 min, cafe, vibes [], avoid ['starbucks'], hard [] |
| I need to answer a few emails on my laptop afterwards | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 2.85s, 25 min, None, vibes [], avoid [], hard [] |
| I'll want to get online for a bit once we sit down | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 5.10s, 25 min, None, vibes [], avoid [], hard [] |
| I use a wheelchair, so the cafe has to work for that | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 2.95s, 25 min, cafe, vibes [], avoid [], hard ['wheelchair accessible cafe'] |
| I'm in a wheelchair this month after my knee surgery | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 3.09s, 25 min, None, vibes [], avoid [], hard [] |
| I'm plant-based, so somewhere with vegan options | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 4.11s, 25 min, None, vibes [], avoid [], hard ['vegan options'] |
| I don't eat dairy, eggs or any other animal products | 0.19s, invalid (model_unavailable: Muse Glimmer: BadRequestError, HTTP 400, Failed to compile json grammar: JSON Schema at #/properties/inferred_fields is not supported by xgrammar: keyword(s) uniqueItems would be ignored) | 2.88s, 25 min, None, vibes [], avoid ['dairy', 'eggs', 'animal products'], hard [] |

## Glimmer run log

```
2026-10-31T15:00:55 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.45s in=375 out=40 est=$0.00060
2026-10-31T15:00:56 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.59s in=374 out=68 est=$0.00079
2026-10-31T15:00:56 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.41s in=372 out=36 est=$0.00055
2026-10-31T15:00:56 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.26s in=373 out=7 est=$0.00035
2026-10-31T15:00:57 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.40s in=373 out=35 est=$0.00054
2026-10-31T15:00:57 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.40s in=375 out=36 est=$0.00055
2026-10-31T15:00:58 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.53s in=375 out=63 est=$0.00072
2026-10-31T15:00:58 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.40s in=373 out=36 est=$0.00055
2026-10-31T15:00:59 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.68s in=371 out=35 est=$0.00091
2026-10-31T15:00:59 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.56s in=374 out=64 est=$0.00076
```
