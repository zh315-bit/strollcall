# Meta ablation 2026-10-28

- Run: 2026-10-28 16:37 ET; local OSM engine; 10 pre-registered wish cases (fixtures/wish_cases.json, rule in scripts/make_wish_cases.py, committed before this run).
- Hard constraints are identical in every arm: the shorter time budget, gap <= 5 min, both avoid lists.
- (a) structured: rule-based merge of both parsed preferences, deterministic ranking.
- (a') keywords: (a) plus wishes a plain keyword matcher finds in the free text.
- (b) Meta: Muse Spark negotiation, Muse Spark wishes (menu-limited, each backed by a quote from the person's text) in the fit term and destination shortlist, Muse Spark ranking of the top 3. Model text failing the grounding checks is replaced by deterministic text (marked below).
- Reference: expected_wishes, written by hand before the run. 'Unknown' means OpenStreetMap has no tag for it at that place; it is never counted as met.

## Summary

| Metric | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Reference wishes met by the top pick (of 10) | 4 | 6 | 7 |
| … unknown / not met | 6 / 0 | 4 / 0 | 3 / 0 |
| Wishes extracted correctly (of 10) / false extra | – | 7 / 0 | 10 / 0 |
| Top pick differs from (a) | – | 2/10 | 6/10 |
| Top pick differs from (a') | – | – | 4/10 |
| Arrival gap, median | 0.1 min | 0.1 min | 0.1 min |
| Time-budget error, median | 0.5 min | 0.8 min | 0.7 min |
| Hard constraints met for both people | 10/10 | 10/10 | 10/10 |
| Checkable preferences met, A · B | 10/10 · 0/0 | 10/10 · 0/0 | 10/10 · 0/0 |
| Ungrounded crowd-level words in Meta text | – | – | 0 |
| Meta spend for this run | – | – | $0.3185 |

## Cases

### w1: Gantry Plaza State Park ↔ Smiling Hogshead Ranch

- A typed: “It's warm out, let's get a coffee we can drink sitting outside”
- B typed: “Somewhere nice, about 30 minutes”
- Reference wishes: A:outdoor_seating
- Keyword wishes: A:outdoor_seating
- Muse Spark wishes: A:outdoor_seating (“It's warm out, let's get a coffee we can drink sitting outside”)
- Muse Spark negotiation (meta): Respect A's wish to end at a cafe while accommodating B's open preferences.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | 11th St & Jackson Ave → Doughnut Plant | 11th St & Jackson Ave → Joe Coffee | 11th St & Jackson Ave → Joe Coffee |
| Reference wishes | 0 met, 1 unknown, 0 not met | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met |
| Gap / time error | 0.1 min / 0.1 min | 0.1 min / 0.7 min | 0.1 min / 0.7 min |
| Why this one | Meet at 11th St & Jackson Ave (street corner): A walks about 12 min, B about 12 min (gap 0.1 min). Then 18 min together to Doughnut Plant (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at 11th St & Jackson Ave (street corner): A walks about 12 min, B about 12 min (gap 0.1 min). Then 19 min together to Joe Coffee (cafe, for A (cafe), open when you arrive (per OSM)). | Ends at Joe Coffee cafe for A, total 31 with 19 together suits duration for A and B. |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | no | no | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w2: East 116th Street & Lexington Avenue at Southwest Corner ↔ Lafayette Square

- A typed: “Coffee at the end, about 30 minutes”
- B typed: “A coffee on a patio in the sun would be perfect”
- Reference wishes: B:outdoor_seating
- Keyword wishes: B:outdoor_seating
- Muse Spark wishes: B:outdoor_seating (“A coffee on a patio in the sun would be perfect”)
- Muse Spark negotiation (meta): Respect A's wish to end at a cafe while accommodating B's open preferences.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Central Park gate → Hungarian Pastry Shop | Central Park gate → Hungarian Pastry Shop | Central Park gate → Hungarian Pastry Shop |
| Reference wishes | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met |
| Gap / time error | 0.0 min / 1.2 min | 0.0 min / 1.2 min | 0.0 min / 1.2 min |
| Why this one | Meet at Central Park gate (park gate): A walks about 14 min, B about 14 min (gap 0.0 min). Then 17 min together to Hungarian Pastry Shop (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Central Park gate (park gate): A walks about 14 min, B about 14 min (gap 0.0 min). Then 17 min together to Hungarian Pastry Shop (cafe, for A (cafe), open when you arrive (per OSM)). | end at cafe for A with outdoor seating for B, 31 total with 0.0 gap and 17 together |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | no | no | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w3: Ten Eyck Playground ↔ Lafayette Playground

- A typed: “Some little local place please, not a big chain”
- B typed: “Somewhere nice, about 30 minutes”
- Reference wishes: A:not_a_chain
- Keyword wishes: A:not_a_chain
- Muse Spark wishes: A:not_a_chain (“not a big chain”)
- Muse Spark negotiation (meta): Balance A's preference for a cafe endpoint with B's lack of specific endpoint preference.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Beaver Noll Park → Lalin's | Beaver Noll Park → Lalin's | Beaver Noll Park → Win Son Bakery |
| Reference wishes | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met |
| Gap / time error | 0.2 min / 0.8 min | 0.2 min / 0.8 min | 0.2 min / 0.8 min |
| Why this one | Meet at Beaver Noll Park (park): A walks about 15 min, B about 15 min (gap 0.2 min). Then 14 min together to Lalin's (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Beaver Noll Park (park): A walks about 15 min, B about 15 min (gap 0.2 min). Then 14 min together to Lalin's (cafe, for A (cafe), open when you arrive (per OSM)). | Walk together 16 and total 31 for A and B, end at cafe for A. |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | yes | yes | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w4: Lilliann D. Wald Playground ↔ Titanic Memorial Park

- A typed: “Coffee at the end, about 30 minutes”
- B typed: “Anywhere for coffee as long as it's not Starbucks”
- Reference wishes: B:not_a_chain
- Keyword wishes: B:not_a_chain
- Muse Spark wishes: B:not_a_chain (“as long as it's not Starbucks”)
- Muse Spark negotiation (meta): Lean toward A's preference for a cafe ending while honoring B's flexibility on the ending.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Sophie Irene Loeb Playground gate → Ost Cafe | Sophie Irene Loeb Playground gate → Ost Cafe | Tanahey Playground gate → Ost Cafe |
| Reference wishes | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met |
| Gap / time error | 0.1 min / 1.7 min | 0.1 min / 1.7 min | 0.7 min / 0.8 min |
| Why this one | Meet at Sophie Irene Loeb Playground gate (park gate): A walks about 15 min, B about 15 min (gap 0.1 min). Then 13 min together to Ost Cafe (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Sophie Irene Loeb Playground gate (park gate): A walks about 15 min, B about 15 min (gap 0.1 min). Then 13 min together to Ost Cafe (cafe, for A (cafe), open when you arrive (per OSM)). | Ends at Ost Cafe for A (cafe), non-chain for B, 17 min together with 31 min total |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | yes | yes | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w5: Broadway & 157th Street at Northwest Corner ↔ Broadway & 137th Street at Northeast Corner

- A typed: “I need to answer a few emails on my laptop afterwards”
- B typed: “Somewhere nice, about 30 minutes”
- Reference wishes: A:wifi
- Keyword wishes: none
- Muse Spark wishes: A:wifi (“I need to answer a few emails on my laptop afterwards”)
- Muse Spark negotiation (meta): Balance A's preference for a cafe ending with B's openness on how the walk ends.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Saint Nicholas Ave & Saint Nicholas Pl → Semicolon | Saint Nicholas Ave & Saint Nicholas Pl → Semicolon | Saint Nicholas Ave & Saint Nicholas Pl → Semicolon |
| Reference wishes | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met |
| Gap / time error | 0.5 min / 0.1 min | 0.5 min / 0.1 min | 0.5 min / 0.1 min |
| Why this one | Meet at Saint Nicholas Ave & Saint Nicholas Pl (street corner): A walks about 14 min, B about 15 min (gap 0.5 min). Then 15 min together to Semicolon (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Saint Nicholas Ave & Saint Nicholas Pl (street corner): A walks about 14 min, B about 15 min (gap 0.5 min). Then 15 min together to Semicolon (cafe, for A (cafe), open when you arrive (per OSM)). | Ends at Semicolon cafe for A, total 30 for A and B with 15 together for A and B. |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | no | no | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w6: Straus Park ↔ Mandela Garden

- A typed: “Coffee at the end, about 30 minutes”
- B typed: “I'll want to get online for a bit once we sit down”
- Reference wishes: B:wifi
- Keyword wishes: none
- Muse Spark wishes: B:wifi (“I'll want to get online for a bit once we sit down”)
- Muse Spark negotiation (meta): Honor A's preference for a cafe ending while keeping the walk comfortable for B.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Frederick Douglass Blvd & W 112th St → Luckin Coffee | Frederick Douglass Blvd & W 112th St → Luckin Coffee | Morningside Ave & W 114th St → Plowshares Coffee Roasters |
| Reference wishes | 0 met, 1 unknown, 0 not met | 0 met, 1 unknown, 0 not met | 1 met, 0 unknown, 0 not met |
| Gap / time error | 0.0 min / 0.1 min | 0.0 min / 0.1 min | 0.1 min / 1.7 min |
| Why this one | Meet at Frederick Douglass Blvd & W 112th St (street corner): A walks about 16 min, B about 16 min (gap 0.0 min). Then 14 min together to Luckin Coffee (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Frederick Douglass Blvd & W 112th St (street corner): A walks about 16 min, B about 16 min (gap 0.0 min). Then 14 min together to Luckin Coffee (cafe, for A (cafe), open when you arrive (per OSM)). | Ends at cafe for A, wifi for B, 32 total with 16 and 16 walks and 0.1 gap. |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | yes | yes | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w7: Bushwick Inlet Park ↔ Roberto Clemente Ballfield

- A typed: “I use a wheelchair, so the cafe has to work for that”
- B typed: “Somewhere nice, about 30 minutes”
- Reference wishes: A:wheelchair_access
- Keyword wishes: A:wheelchair_access
- Muse Spark wishes: A:wheelchair_access (“I use a wheelchair, so the cafe has to work for that”)
- Muse Spark negotiation (meta): Respect A's preference for a cafe ending while accommodating B's flexibility on the ending.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Kent Ave & S 1st St → The Bean | Kent Ave & S 1st St → The Bean | Kent Ave & S 1st St → The Bean |
| Reference wishes | 0 met, 1 unknown, 0 not met | 0 met, 1 unknown, 0 not met | 0 met, 1 unknown, 0 not met |
| Gap / time error | 0.1 min / 0.2 min | 0.1 min / 0.2 min | 0.1 min / 0.2 min |
| Why this one | Meet at Kent Ave & S 1st St (street corner): A walks about 14 min, B about 14 min (gap 0.1 min). Then 17 min together to The Bean (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Kent Ave & S 1st St (street corner): A walks about 14 min, B about 14 min (gap 0.1 min). Then 17 min together to The Bean (cafe, for A (cafe), open when you arrive (per OSM)). | Ends at cafe for A, 30 total for A and B with 17 together |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | no | no | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w8: Potomac Playground ↔ Charlie's Place

- A typed: “Coffee at the end, about 30 minutes”
- B typed: “I'm in a wheelchair this month after my knee surgery”
- Reference wishes: B:wheelchair_access
- Keyword wishes: B:wheelchair_access
- Muse Spark wishes: B:wheelchair_access (“I'm in a wheelchair this month after my knee surgery”)
- Muse Spark negotiation (meta): Honor A's preference for a cafe ending while keeping the walk comfortable for both.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Lafayette Ave & Tompkins Ave → Martha's Pastries & Cafe | Lafayette Ave & Tompkins Ave → Martha's Pastries & Cafe | Lafayette Ave & Tompkins Ave → Martha's Pastries & Cafe |
| Reference wishes | 0 met, 1 unknown, 0 not met | 0 met, 1 unknown, 0 not met | 0 met, 1 unknown, 0 not met |
| Gap / time error | 0.1 min / 1.8 min | 0.1 min / 1.8 min | 0.1 min / 1.8 min |
| Why this one | Meet at Lafayette Ave & Tompkins Ave (street corner): A walks about 13 min, B about 13 min (gap 0.1 min). Then 19 min together to Martha's Pastries & Cafe (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Lafayette Ave & Tompkins Ave (street corner): A walks about 13 min, B about 13 min (gap 0.1 min). Then 19 min together to Martha's Pastries & Cafe (cafe, for A (cafe), open when you arrive (per OSM)). | End at cafe with listed hours for A, 19 together and 0.1 gap fair for A and B |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | no | no | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w9: East 60th Street & Lexington Avenue at Southwest Corner ↔ Richard Tucker Square

- A typed: “I'm plant-based, so somewhere with vegan options”
- B typed: “Somewhere nice, about 30 minutes”
- Reference wishes: A:vegan_options
- Keyword wishes: A:vegan_options
- Muse Spark wishes: A:vegan_options (“I'm plant-based, so somewhere with vegan options”)
- Muse Spark negotiation (meta): Honor A's wish for a cafe ending while keeping things open for B.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | Literary Walk → Solid State Coffee | Balto → Le Botaniste | Balto → Le Botaniste |
| Reference wishes | 0 met, 1 unknown, 0 not met | 1 met, 0 unknown, 0 not met | 1 met, 0 unknown, 0 not met |
| Gap / time error | 1.1 min / 0.2 min | 1.2 min / 0.2 min | 1.2 min / 0.2 min |
| Why this one | Meet at Literary Walk (plaza): A walks about 15 min, B about 14 min (gap 1.1 min). Then 16 min together to Solid State Coffee (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at Balto (landmark): A walks about 14 min, B about 15 min (gap 1.2 min). Then 15 min together to Le Botaniste (cafe, for A (cafe), open when you arrive (per OSM)). | Ends at Le Botaniste cafe for A, total 30 with 15 together for A and B. |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | no | yes | yes |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

### w10: East River Esplanade ↔ Herald Square

- A typed: “Coffee at the end, about 30 minutes”
- B typed: “I don't eat dairy, eggs or any other animal products”
- Reference wishes: B:vegan_options
- Keyword wishes: none
- Muse Spark wishes: B:vegan_options (“I don't eat dairy, eggs or any other animal products”)
- Muse Spark negotiation (meta): Prioritize A's cafe ending since B expressed no ending preference.

| | (a) structured | (a') keywords | (b) Meta |
| --- | --- | --- | --- |
| Top pick | 3rd Ave & E 29th St → Gregory’s coffee | 3rd Ave & E 29th St → Gregory’s coffee | Strange Days Album Cover Location → Gregory’s coffee |
| Reference wishes | 0 met, 1 unknown, 0 not met | 0 met, 1 unknown, 0 not met | 0 met, 1 unknown, 0 not met |
| Gap / time error | 0.8 min / 0.8 min | 0.8 min / 0.8 min | 2.4 min / 0.5 min |
| Why this one | Meet at 3rd Ave & E 29th St (street corner): A walks about 16 min, B about 16 min (gap 0.8 min). Then 13 min together to Gregory’s coffee (cafe, for A (cafe), open when you arrive (per OSM)). | Meet at 3rd Ave & E 29th St (street corner): A walks about 16 min, B about 16 min (gap 0.8 min). Then 13 min together to Gregory’s coffee (cafe, for A (cafe), open when you arrive (per OSM)). | Ends at cafe for A with 30 total, 17 together for both, B vegan wish unknown |
| Ranking | deterministic | deterministic | meta |
| Notes shown to users | – | – | – |
| Hard constraints, both people | ok | ok | ok |
| Strict time limit detected (A, B) | no, no | no, no | no, no |
| Within the shorter budget, no tolerance (added after pre-registration) | yes | yes | no |
| A's / B's checkable preferences met | 1/1 · 0/0 | 1/1 · 0/0 | 1/1 · 0/0 |

## For human review

For each case: which top pick would A and B choose, and is the Meta explanation accurate?
