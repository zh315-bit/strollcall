# Meta ablation 2026-10-28

- Run: 2026-10-28 16:33 ET; local OSM engine; 4 pre-registered A-vs-B conflict cases (fixtures/conflict_cases.json, committed before this run; evaluation rules in its _rule field).
- Hard constraints are identical in every arm: the shorter time budget, gap <= 5 min, both avoid lists.
- (a) structured: rule-based merge of both parsed preferences, deterministic ranking.
- (a') keywords: (a) plus wishes a plain keyword matcher finds in the free text.
- (b) Meta: Muse Spark negotiation, Muse Spark wishes (menu-limited, each backed by a quote from the person's text) in the fit term and destination shortlist, Muse Spark ranking of the top 3. Model text failing the grounding checks is replaced by deterministic text (marked below).
- Reference: expected_wishes, written by hand before the run. 'Unknown' means OpenStreetMap has no tag for it at that place; it is never counted as met.

## Summary

| Metric | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Reference wishes met by the top pick (of 0) | 0 | 0 | 0 |
| … unknown / not met | 0 / 0 | 0 / 0 | 0 / 0 |
| Wishes extracted correctly (of 0) / false extra | – | 0 / 2 | 0 / 2 |
| Top pick differs from (a) | – | 1/4 | 1/4 |
| Top pick differs from (a') | – | – | 0/4 |
| Arrival gap, median | 0.8 min | 0.8 min | 0.8 min |
| Time-budget error, median | 0.8 min | 0.8 min | 0.9 min |
| Hard constraints met for both people | 4/4 | 4/4 | 4/4 |
| Checkable preferences met, A · B | 3/3 · 3/4 | 3/3 · 3/4 | 3/3 · 3/4 |
| Ungrounded crowd-level words in Meta text | – | – | 0 |
| Meta spend for this run | – | – | $0.1172 |

## Cases

### c1: Bryant Park ↔ Madison Square Park

- A typed: “A quiet walk, 30 minutes, somewhere calm to end up”
- B typed: “Something lively, 30 minutes, I want a bit of buzz”
- Reference wishes: 
- Keyword wishes: none
- Muse Spark wishes: none
- Muse Spark negotiation (meta): Balancing A's preference for quiet with B's preference for lively.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | No. 2 Penn Plaza Entrance → Starbucks | No. 2 Penn Plaza Entrance → Starbucks | No. 2 Penn Plaza Entrance → Starbucks |
| Reference wishes | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met |
| Gap / time error | 0.3 min / 0.4 min | 0.3 min / 0.4 min | 0.3 min / 0.4 min |
| Why this one | Meet at No. 2 Penn Plaza Entrance (park gate, for A (quiet)): A walks about 14 min, B about 14 min (gap 0.3 min). Then 16 min together to Starbucks (cafe, for B (lively), open when you arrive (per OSM)). | Meet at No. 2 Penn Plaza Entrance (park gate, for A (quiet)): A walks about 14 min, B about 14 min (gap 0.3 min). Then 16 min together to Starbucks (cafe, for B (lively), open when you arrive (per OSM)). | Meet at No. 2 Penn Plaza Entrance (park gate, for A (quiet)): A walks about 14 min, B about 14 min (gap 0.3 min). Then 16 min together to Starbucks (cafe, for B (lively), open when you arrive (per OSM)). |
| Ranking | deterministic | deterministic | default (invented_number) |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | yes | yes | yes |
| A's / B's checkable preferences met | 1/1 · 1/1 | 1/1 · 1/1 | 1/1 · 1/1 |

### c2: Christopher Street-Stonewall station ↔ 14th Street-Union Square station

- A typed: “30 minutes, coffee at the end”
- B typed: “30 minutes, let's end up in a park”
- Reference wishes: 
- Keyword wishes: B:green_meetup
- Muse Spark wishes: B:green_meetup (“let's end up in a park”)
- Muse Spark negotiation (meta): Balancing A's cafe preference with B's park preference.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Washington Square Park gate → Starbucks | Washington Square Park gate → Starbucks | Washington Square Park gate → Starbucks |
| Reference wishes | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met |
| Gap / time error | 2.1 min / 1.4 min | 2.1 min / 1.4 min | 2.1 min / 1.4 min |
| Why this one | Meet at Washington Square Park gate (park gate, for B (park)): A walks about 8 min, B about 11 min (gap 2.1 min). Then 18 min together to Starbucks (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Washington Square Park gate (park gate, for B (park)): A walks about 8 min, B about 11 min (gap 2.1 min). Then 18 min together to Starbucks (cafe, for A (cafe), open when you arrive (per OSM)). | meet at park gate for B, end at cafe for A, with 18 min together and B's park wish met. |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | yes | yes | yes |
| A's / B's checkable preferences met | 1/1 · 0/1 | 1/1 · 0/1 | 1/1 · 0/1 |

### c3: West 4th Street-Washington Square station ↔ Astor Place station

- A typed: “I only have 20 minutes, coffee at the end”
- B typed: “I have about 40 minutes, something green”
- Reference wishes: 
- Keyword wishes: B:green_meetup
- Muse Spark wishes: B:green_meetup (“something green”)
- Muse Spark negotiation (meta): Honor A's cafe ending while keeping B's green feel.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Washington Square Park gate → Dominique Ansel Bakery | Washington Square Park gate → Starbucks | Washington Square Park gate → Starbucks |
| Reference wishes | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met |
| Gap / time error | 1.2 min / 0.5 min | 1.2 min / 0.5 min | 1.2 min / 0.5 min |
| Why this one | Meet at Washington Square Park gate (park gate, for B (green)): A walks about 6 min, B about 7 min (gap 1.2 min). Then 13 min together to Dominique Ansel Bakery (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Washington Square Park gate (park gate, for B (green)): A walks about 6 min, B about 7 min (gap 1.2 min). Then 13 min together to Starbucks (cafe, for A (cafe), open when you arrive (per OSM)). | meet at Washington Square Park gate for B green, end at Starbucks cafe for A |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | yes, no | yes, no |
| Within the shorter budget, no tolerance (added after pre-registration) | yes | yes | yes |
| A's / B's checkable preferences met | 1/1 · 1/1 | 1/1 · 1/1 | 1/1 · 1/1 |

### c4: Madison Square Park ↔ 8th Street-NYU station

- A typed: “30 minutes, I'd rather avoid crowds”
- B typed: “30 minutes, somewhere good for people-watching”
- Reference wishes: 
- Keyword wishes: none
- Muse Spark wishes: none
- Muse Spark negotiation (meta): The walk balances A's wish to avoid crowds with B's wish for a lively vibe.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Union Square Park gate → Gold Coffee | Union Square Park gate → Gold Coffee | Union Square Park gate → Gold Coffee |
| Reference wishes | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met |
| Gap / time error | 0.1 min / 1.1 min | 0.1 min / 1.1 min | 0.0 min / 1.9 min |
| Why this one | Meet at Union Square Park gate (park gate): A walks about 10 min, B about 10 min (gap 0.1 min). Then 21 min together to Gold Coffee (cafe, for B (lively), open when you arrive (per OSM)). | Meet at Union Square Park gate (park gate): A walks about 10 min, B about 10 min (gap 0.1 min). Then 21 min together to Gold Coffee (cafe, for B (lively), open when you arrive (per OSM)). | Meet at Union Square Park gate for neither A nor B, end at Gold Coffee for B lively; no match for A avoid crowds, 22 together, 32 total. |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | We can't check crowd levels; we avoided major transit hubs and large plazas. | We can't check crowd levels; we avoided major transit hubs and large plazas. | We can't check crowd levels; we avoided major transit hubs and large plazas. |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | no | no | no |
| A's / B's checkable preferences met | 0/0 · 1/1 | 0/0 · 1/1 | 0/0 · 1/1 |

## For human review

For each case: which top pick would A and B choose, and is the Meta explanation accurate?

## Notes added after the run (not part of the pre-registered metrics)

- This is the second run on these cases, after the split-plan, strict-duration and crowd changes.
  Picks are compared by place name.
- c2 (coffee vs park): every arm now picks a split plan, meeting at a Washington Square Park
  gate for B and ending at a cafe for A. The change is in the planner, so all arms benefit.
- c3 (20 vs 40 min): keywords and Muse Spark both read "I only have 20 minutes" as strict;
  every arm's plan fits inside 20 minutes, and each meets at the park gate for B's "green".
- c4 (avoid crowds): the note is shown in every arm, but all arms still meet at Union Square.
  The hub rule (>= 6 named subway entrances within 150 m) misses Union Square because OSM names
  few of its entrances; the snapshot only keeps named ones. The plan also runs 1 min over the
  30-minute budget, within the +3 min tolerance (A did not say the limit was strict).
- With the planner now handling these conflicts, Muse Spark's pick differs from the structured
  arm in 1 of 4 cases (c3: a different cafe) and from keywords in none.
