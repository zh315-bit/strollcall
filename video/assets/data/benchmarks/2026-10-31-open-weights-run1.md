# Open-weights evaluation, run 1: Muse Glimmer vs muse-spark-1.3 (2026-10-31)

- Glimmer: `meta-models/Muse-Glimmer-30B@f84ecc3`, BF16, Modal Dedicated Endpoint `ep-ez0BAxZPNiSL3x40VCpbFi` (SGLang), 1x H200, reasoning off (answer channel), temperature 0.
- Muse Spark: `muse-spark-1.3` on the Meta Model API, reasoning effort `minimal`.
- Cases: fixtures/wish_cases.json (pre-registered); scoring and expected values in scripts/eval_open_weights.py, committed before this run. Production prompts, unchanged.
- One request at a time; the Glimmer endpoint was warm (scripts/glimmer_warm.py).

| | Muse Glimmer (open weights, Modal) | muse-spark-1.3 (Meta API) |
| --- | --- | --- |
| Wish reading: JSON valid | 10/12 | 12/12 |
| Wish reading: valid WalkIntent | 10/12 | 12/12 |
| Duration right | 10/10 | 12/12 |
| Ending right (scored texts) | 5/5 | 6/6 |
| Latency, median / max | 0.55 s / 6.84 s | 3.58 s / 5.64 s |
| Within the 3 s fallback limit | 10/12 | 3/12 |
| Cost per parse | $0.00222 | $0.00416 |
| Wish recognition: expected found | 9/10 | 10/10 |
| Wish recognition: extra wishes | 3 | 0 |
| Wish recognition: answered (not fallback) | 10/10 | 10/10 |
| Cost per wish recognition | $0.00058 | $0.00160 |

Glimmer's cost per parse is its share of the warm GPU (latency x $4.86/h). A warm window also bills the cold start (~3.3 min, ~$0.27) and 2 idle minutes after the last call (~$0.16).

## Per text (wish reading)

| Text | Glimmer | Spark |
| --- | --- | --- |
| It's warm out, let's get a coffee we can drink sitting outside | 1.28s, 25 min, cafe, vibes ['warm', 'outdoor seating'], avoid [], hard [] | 5.64s, 25 min, cafe, vibes [], avoid [], hard ['outdoor seating'] |
| Somewhere nice, about 30 minutes | 0.45s, 30 min, None, vibes [], avoid [], hard [] | 3.38s, 30 min, None, vibes [], avoid [], hard [] |
| Coffee at the end, about 30 minutes | 0.46s, 30 min, cafe, vibes [], avoid [], hard [] | 1.61s, 30 min, cafe, vibes [], avoid [], hard [] |
| A coffee on a patio in the sun would be perfect | 0.89s, 25 min, cafe, vibes ['sunny', 'outdoor'], avoid [], hard [] | 4.07s, 25 min, cafe, vibes [], avoid [], hard [] |
| Some little local place please, not a big chain | 0.51s, 25 min, None, vibes [], avoid ['big chain'], hard [] | 3.25s, 25 min, None, vibes [], avoid ['big chain'], hard [] |
| Anywhere for coffee as long as it's not Starbucks | 0.53s, 25 min, cafe, vibes [], avoid ['starbucks'], hard [] | 2.58s, 25 min, cafe, vibes [], avoid ['starbucks'], hard [] |
| I need to answer a few emails on my laptop afterwards | 0.52s, 25 min, None, vibes [], avoid [], hard [] | 3.59s, 25 min, None, vibes [], avoid [], hard [] |
| I'll want to get online for a bit once we sit down | 0.50s, 25 min, None, vibes [], avoid [], hard [] | 4.11s, 25 min, None, vibes [], avoid [], hard [] |
| I use a wheelchair, so the cafe has to work for that | 6.66s, invalid (model_unavailable: Muse Glimmer output truncated at 1536 tokens) | 3.58s, 25 min, cafe, vibes [], avoid [], hard [] |
| I'm in a wheelchair this month after my knee surgery | 6.84s, invalid (model_unavailable: Muse Glimmer output truncated at 1536 tokens) | 3.44s, 25 min, None, vibes [], avoid [], hard [] |
| I'm plant-based, so somewhere with vegan options | 0.62s, 25 min, None, vibes [], avoid [], hard ['plant-based', 'vegan options'] | 3.00s, 25 min, None, vibes [], avoid [], hard ['vegan options'] |
| I don't eat dairy, eggs or any other animal products | 0.55s, 25 min, None, vibes [], avoid ['dairy', 'eggs', 'animal products'], hard [] | 4.30s, 25 min, None, vibes [], avoid [], hard [] |

## Glimmer run log

```
2026-10-31T14:59:05 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=1.28s in=388 out=102 est=$0.00173
2026-10-31T14:59:05 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.44s in=383 out=51 est=$0.00060
2026-10-31T14:59:06 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.46s in=384 out=52 est=$0.00062
2026-10-31T14:59:07 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.88s in=386 out=88 est=$0.00119
2026-10-31T14:59:07 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.51s in=385 out=61 est=$0.00069
2026-10-31T14:59:08 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.53s in=385 out=62 est=$0.00071
2026-10-31T14:59:08 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.52s in=386 out=63 est=$0.00070
2026-10-31T14:59:09 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.50s in=387 out=63 est=$0.00067
2026-10-31T14:59:15 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=6.65s in=388 out=1536 est=$0.00898
2026-10-31T14:59:22 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=6.84s in=385 out=1536 est=$0.00923
2026-10-31T14:59:23 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.62s in=384 out=76 est=$0.00084
2026-10-31T14:59:23 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=walk_intent ok latency=0.55s in=386 out=69 est=$0.00074
2026-10-31T14:59:24 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.45s in=375 out=40 est=$0.00060
2026-10-31T14:59:24 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.59s in=374 out=68 est=$0.00080
2026-10-31T14:59:25 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.39s in=372 out=36 est=$0.00053
2026-10-31T14:59:25 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.23s in=373 out=7 est=$0.00031
2026-10-31T14:59:26 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.39s in=373 out=35 est=$0.00053
2026-10-31T14:59:26 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.39s in=375 out=36 est=$0.00053
2026-10-31T14:59:26 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.53s in=375 out=63 est=$0.00071
2026-10-31T14:59:27 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.41s in=373 out=36 est=$0.00055
2026-10-31T14:59:27 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.37s in=371 out=35 est=$0.00050
2026-10-31T14:59:28 muse-glimmer, BF16, Modal, H200 | meta-models/Muse-Glimmer-30B@f84ecc3 deployment=ep-ez0BAxZPNiSL3x40VCpbFi | job=wishes ok latency=0.55s in=374 out=64 est=$0.00075
```
