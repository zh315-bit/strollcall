# Prompt change: unverifiable qualities only as a person's wish (before / after)

Change (commit 7fe0698): the negotiation and ranking prompts now say that qualities the data cannot verify
(quiet, lively, safe, crowded, scenic) may appear only as someone's wish ("for B's wish for a quiet walk"), never
as a fact about a place or route. The ranking prompt's "2-3 candidates" became "2-6".

Measured with `scripts/fallback_rate.py --runs 2` on all 14 pre-registered cases (10 wish cases, 4 conflict
cases; fixtures committed 2026-10-28, before any of this). The checker was the same in both runs (6abeebe). A
fallback counts only when Meta answered and the answer was rejected.

| | Negotiation rejected | Ranking rejected | Meta spend |
|---|---|---|---|
| Before (old prompts) | 0 of 28 | 0 of 28 | $0.276 |
| After (new prompts) | 0 of 28 | 1 of 28 | $0.242 |

Details: [before](2026-10-30-fallback-before.md), [after](2026-10-30-fallback-after.md).

Reading it honestly:
- On these cases the old prompts were never rejected, so this run cannot show an improvement. The two "quiet"
  rejections in the live flow (rejections #3 and #7) used different inputs, and 13 reproductions of those
  inputs did not bring them back. One more rejection in 28 is within noise; it is not evidence that the change
  made things worse.
- The one rejection after the change was a checker false positive, not an overclaim. Case w3 said "…better than
  Dun-Well Doughnuts from park": "from park" names another option, which meets at a park. A fix with tests
  followed the run (this commit). The after-number above is left as measured: no re-run.
- As agreed, there is no further prompt tuning against these 14 cases.

Rejection #11 for the list in 2026-10-30-rejections.md: after-run 2, w3, ranking, 'park', "…better than Dun-Well
Doughnuts from park…": **checker false positive**, fixed.
