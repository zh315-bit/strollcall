# Fallback rate of Muse Spark's negotiation and ranking: repro

Run 2026-10-30 11:14 ET, `scripts/fallback_rate.py --label repro --runs 8 --live-pair`, model muse-spark-1.3 at `minimal` reasoning effort (as after an invite is accepted), local walking graph and place snapshot, up to six options per plan. Inputs: the 2026-10-30 live-flow pair (Union Square Park ↔ Washington Square Arch).

A fallback counts only when Meta answered and the honesty checks (or the schema) rejected the answer.

- **Negotiation rejected: 0 of 8** (0%)
- **Ranking rejected: 1 of 8** (12%)
- Meta spend for this run: $0.121

| Run | Case | Options | Negotiation | Ranking |
| --- | --- | --- | --- | --- |
| 1 | live | 6 | meta | meta |
| 2 | live | 6 | meta | meta |
| 3 | live | 6 | meta | meta |
| 4 | live | 6 | meta | meta |
| 5 | live | 6 | meta | meta |
| 6 | live | 6 | meta | meta |
| 7 | live | 6 | meta | rejected (unsupported_feature) |
| 8 | live | 6 | meta | meta |

## Rejected texts

- run 7 live: explain: ranking reason for c3 rejected: feature not in data: bakery in '24 total with 17 together and 6 walks, end at Think Coffee for A, same time as bakery via 5th Ave plan'
- run 7 live: explain: ranking fell back to deterministic order: unsupported_feature
