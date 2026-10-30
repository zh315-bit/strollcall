# Every logged rejection of a Muse Spark answer, classified

Scope: answers Muse Spark *gave* that StrollCall's honesty checks then refused (negotiation, ranking). Calls that
never reached the model (the 404 `model_not_found` period on 2026-10-28/29, the budget guard) are not rejections and
are left out; so are the place-intro checks, which have their own report (2026-10-29-poi-intros.md).

Sources: Render logs from 2026-10-01 to 2026-10-30 15:00 ET (all rejection warnings), the ablation reports of
2026-10-28, and local reproductions with the live-flow inputs (benchmarks/2026-10-30-fallback-repro.md). Until
today the warnings did not record the rejected text. Where it is missing, the row says so. From commit 9e7ee17
(ranking) and this commit (negotiation) on, the text is logged.

| # | When | Step | Checker's reason | Text | Verdict |
|---|---|---|---|---|---|
| 1 | 10-28 ablation, p2 | negotiation | unsupported_feature | not logged | cannot classify |
| 2 | 10-28 conflict ablation | ranking | invented_number | not logged | cannot classify (probably the place-name digits fixed the same day; not provable) |
| 3 | 10-30 14:36 live | negotiation | unverifiable claim 'quiet' | not logged | **genuine overclaim, most likely**: "quiet" was used without being tied to a person's wish (the rule fires only then). Not reproduced in 13 runs with the same inputs |
| 4 | 10-30 14:36 live | ranking | number 5 not in facts | "…1 min shorter than Think Coffee via 5th Ave plan…" | **checker false positive**: "5th Ave" is a shortened place name (fixed in 21eaf89) |
| 5 | 10-30 14:37 live | ranking | feature 'bakery' for c3 | not logged | **checker false positive, most likely**: same inputs reproduce #9/#10 |
| 6 | 10-30 14:37 live | ranking | feature 'bakery' for c3 | not logged | same as #5 |
| 7 | 10-30 14:46 live | negotiation | unverifiable claim 'quiet' | not logged | as #3 |
| 8 | 10-30 14:46 live | ranking | feature 'bakery' for c4 | not logged | as #5 |
| 9 | 10-30 repro run 4 | ranking | feature 'bakery' for c3 | "…same as Dominique Ansel Bakery from 5th Ave but shorter than Broadway bakery plan, end at Think Coffee for A" | **checker false positive**: "Broadway bakery plan" is another option (Broadway & E 9th St → Dominique Ansel Bakery) |
| 10 | 10-30 repro run 7 | ranking | feature 'bakery' for c3 | "…end at Think Coffee for A, same time as bakery via 5th Ave plan" | **checker false positive**: another option described by its own feature |

Fixes for the false positives (each with tests in backend/tests/test_negotiation_ranking.py):
- 21eaf89: other options' full names, and shortened street ordinals that appear in them, are not claims or numbers.
- This commit: a short "… plan" / "… option" phrase that describes other options by a feature some other option
  really has is not a claim about this option. A feature that no option has is still rejected, plan phrase or not.
  So is a feature claimed for this option itself.

Not relaxed: features stated as fact without data (#3, #7) and invented numbers.
