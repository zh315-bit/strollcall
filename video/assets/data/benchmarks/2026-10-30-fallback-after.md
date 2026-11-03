# Fallback rate of Muse Spark's negotiation and ranking: after

Run 2026-10-30 11:23 ET, `scripts/fallback_rate.py --label after --runs 2`, model muse-spark-1.3 at `minimal` reasoning effort (as after an invite is accepted), local walking graph and place snapshot, up to six options per plan. Cases: every pre-registered wish case (fixtures/wish_cases.json) and conflict case (fixtures/conflict_cases.json) with B's preference and free text; written before any prompt change.

A fallback counts only when Meta answered and the honesty checks (or the schema) rejected the answer.

- **Negotiation rejected: 0 of 28** (0%)
- **Ranking rejected: 1 of 28** (4%)
- Meta spend for this run: $0.242

| Run | Case | Options | Negotiation | Ranking |
| --- | --- | --- | --- | --- |
| 1 | w1 | 6 | meta | meta |
| 1 | w2 | 6 | meta | meta |
| 1 | w3 | 6 | meta | meta |
| 1 | w4 | 6 | meta | meta |
| 1 | w5 | 6 | meta | meta |
| 1 | w6 | 6 | meta | meta |
| 1 | w7 | 6 | meta | meta |
| 1 | w8 | 6 | meta | meta |
| 1 | w9 | 6 | meta | meta |
| 1 | w10 | 6 | meta | meta |
| 1 | c1 | 6 | meta | meta |
| 1 | c2 | 6 | meta | meta |
| 1 | c3 | 6 | meta | meta |
| 1 | c4 | 6 | meta | meta |
| 2 | w1 | 6 | meta | meta |
| 2 | w2 | 6 | meta | meta |
| 2 | w3 | 6 | meta | rejected (unsupported_feature) |
| 2 | w4 | 6 | meta | meta |
| 2 | w5 | 6 | meta | meta |
| 2 | w6 | 6 | meta | meta |
| 2 | w7 | 6 | meta | meta |
| 2 | w8 | 6 | meta | meta |
| 2 | w9 | 6 | meta | meta |
| 2 | w10 | 6 | meta | meta |
| 2 | c1 | 6 | meta | meta |
| 2 | c2 | 6 | meta | meta |
| 2 | c3 | 6 | meta | meta |
| 2 | c4 | 6 | meta | meta |

## Rejected texts

- run 2 w3: explain: ranking reason for c5 rejected: feature not in data: park in '14 min together and 30 min total matches target better than Dun-Well Doughnuts from park, end at Dun-Well Doughnuts for A: cafe'
- run 2 w3: explain: ranking fell back to deterministic order: unsupported_feature
