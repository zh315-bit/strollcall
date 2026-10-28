# Meta ablation 2026-10-28

- Run: 2026-10-28 16:07 ET; local OSM engine; 4 pre-registered A-vs-B conflict cases (fixtures/conflict_cases.json, committed before this run; evaluation rules in its _rule field).
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
| Top pick differs from (a) | – | 1/4 | 3/4 |
| Top pick differs from (a') | – | – | 2/4 |
| Arrival gap, median | 0.2 min | 0.2 min | 0.2 min |
| Time-budget error, median | 0.4 min | 0.8 min | 1.7 min |
| Hard constraints met for both people | 4/4 | 4/4 | 4/4 |
| Checkable preferences met, A · B | 2/3 · 4/4 | 3/3 · 3/4 | 3/3 · 3/4 |
| Ungrounded crowd-level words in Meta text | – | – | 0 |
| Meta spend for this run | – | – | $0.0693 |

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
| Why this one | Meet at No. 2 Penn Plaza Entrance: A walks about 14 min, B about 14 min (gap 0.3 min). Then 16 min together to Starbucks (cafe, open when you arrive (per OSM)). | Meet at No. 2 Penn Plaza Entrance: A walks about 14 min, B about 14 min (gap 0.3 min). Then 16 min together to Starbucks (cafe, open when you arrive (per OSM)). | Total 30 meets A's and B's duration with hours listed in OpenStreetMap, though neither A's quiet nor B's lively is shared. |
| Ranking | deterministic | deterministic | meta |
| Hard constraints, both people | ok | ok | ok |
| A's / B's checkable preferences met | 1/1 · 1/1 | 1/1 · 1/1 | 1/1 · 1/1 |

### c2: Christopher Street-Stonewall station ↔ 14th Street-Union Square station

- A typed: “30 minutes, coffee at the end”
- B typed: “30 minutes, let's end up in a park”
- Reference wishes: 
- Keyword wishes: B:green_meetup
- Muse Spark wishes: B:green_meetup (“let's end up in a park”)
- Muse Spark negotiation (meta): Honor A's cafe preference and B's park preference equally.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | University Pl & Washington Square East → Washington Commons | University Pl & Washington Square East → Oasis Cafe | University Pl & Washington Square East → Oasis Cafe |
| Reference wishes | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met |
| Gap / time error | 0.0 min / 0.2 min | 0.0 min / 1.4 min | 0.0 min / 1.4 min |
| Why this one | Meet at University Pl & Washington Square East: A walks about 9 min, B about 9 min (gap 0.0 min). Then 20 min together to Washington Commons (park, opening hours unknown). | Meet at University Pl & Washington Square East: A walks about 9 min, B about 9 min (gap 0.0 min). Then 22 min together to Oasis Cafe (cafe, opening hours unknown). | Supports A's cafe endpoint with listed hours and respects B's accepted cafe compromise with 9 minute walks. |
| Ranking | deterministic | deterministic | meta |
| Hard constraints, both people | ok | ok | ok |
| A's / B's checkable preferences met | 0/1 · 1/1 | 1/1 · 0/1 | 1/1 · 0/1 |

### c3: West 4th Street-Washington Square station ↔ Astor Place station

- A typed: “I only have 20 minutes, coffee at the end”
- B typed: “I have about 40 minutes, something green”
- Reference wishes: 
- Keyword wishes: B:green_meetup
- Muse Spark wishes: B:green_meetup (“something green”)
- Muse Spark negotiation (meta): Respect A's cafe ending and B's green vibe while accommodating both minimum walk lengths.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Washington Square Park gate → Starbucks | Washington Square Park gate → Starbucks | Washington Square Park gate → Setsugekka |
| Reference wishes | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met |
| Gap / time error | 1.2 min / 0.5 min | 1.2 min / 0.5 min | 1.2 min / 2.0 min |
| Why this one | Meet at Washington Square Park gate: A walks about 6 min, B about 7 min (gap 1.2 min). Then 13 min together to Starbucks (cafe, open when you arrive (per OSM)). | Meet at Washington Square Park gate: A walks about 6 min, B about 7 min (gap 1.2 min). Then 13 min together to Starbucks (cafe, open when you arrive (per OSM)). | Cafe meets A's wish with total 22 and 15 together, longest toward B's minimum and meets B's park wish. |
| Ranking | deterministic | deterministic | meta |
| Hard constraints, both people | ok | ok | ok |
| A's / B's checkable preferences met | 1/1 · 1/1 | 1/1 · 1/1 | 1/1 · 1/1 |

### c4: Madison Square Park ↔ 8th Street-NYU station

- A typed: “30 minutes, I'd rather avoid crowds”
- B typed: “30 minutes, somewhere good for people-watching”
- Reference wishes: 
- Keyword wishes: none
- Muse Spark wishes: none
- Muse Spark negotiation (meta): Balance A's wish to avoid crowds with B's wish for a lively vibe.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Union Square Park gate → Gold Coffee | Union Square Park gate → Gold Coffee | Union Square Park gate → Gold Coffee |
| Reference wishes | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met | 0 met, 0 unknown, 0 not met |
| Gap / time error | 0.1 min / 1.1 min | 0.1 min / 1.1 min | 0.0 min / 1.9 min |
| Why this one | Meet at Union Square Park gate: A walks about 10 min, B about 10 min (gap 0.1 min). Then 21 min together to Gold Coffee (cafe, open when you arrive (per OSM)). | Meet at Union Square Park gate: A walks about 10 min, B about 10 min (gap 0.1 min). Then 21 min together to Gold Coffee (cafe, open when you arrive (per OSM)). | Total 32 with 22 together and gap 0.0 best supports A's and B's duration needs while navigating avoid-crowds versus lively tension. |
| Ranking | deterministic | deterministic | meta |
| Hard constraints, both people | ok | ok | ok |
| A's / B's checkable preferences met | 0/0 · 1/1 | 0/0 · 1/1 | 0/0 · 1/1 |

## For human review

For each case: which top pick would A and B choose, and is the Meta explanation accurate?

## Notes added after the run (not part of the pre-registered metrics)

- "Top pick differs" compares place ids. In c1 and c4 the Meta pick differs only by which
  same-named place it uses (another Starbucks branch; another gate of Union Square Park, gap
  0.0 instead of 0.1 min). Counting only picks with a different place name, Meta differs from
  (a) in 2/4 cases (c2, c3) and from (a') in 1/4 (c3).
- c2 (coffee vs park): only one destination is possible, so every arm satisfies one person's
  ending; (a) picked B's park, (a') and (b) A's cafe. No arm found the both-sided compromise
  "meet at a park, end at a cafe": the best meetup points here are street corners.
- c3 (20 vs 40 min): every arm respects the shorter budget within the planner's +3 min slack,
  but Meta chose a 22-minute plan ("longest") for B's benefit. A said "I only have 20
  minutes"; the +3 min slack may be wrong when someone states a strict limit.
- c4 (avoid crowds vs people-watching): no text claims crowd levels, as required, but all arms
  meet at Union Square, which is usually busy. We have no crowd data, so A's wish cannot be
  honoured or checked; the UI should say so instead of implying it was.
