# Place intros for walking guidance (2026-10-29)

Built with `scripts/build_route_pois.py` and `scripts/make_poi_intros.py`, locally, ahead of time.

## Places

2241 points of interest in the covered area (OpenStreetMap): park 925, historic site 366, artwork 349, memorial 336, landmark 265.
1021 have a `wikipedia` or `wikidata` tag; 582 of those resolve to an English Wikipedia article.
(Updated 2026-10-29 evening when the map grew to Jersey City, Hoboken and their neighbors: the 25 new
places with an article went through the same script, prompt and fact check; nothing earlier was redone.)

## Intros

Model: `muse-spark-1.3` (Muse Spark), one call per place, exact prompt in `frontend/data/poi_intros.json`.
Kept: **525** (park 142, historic site 118, landmark 104, memorial 84, artwork 77).
Dropped: model said the source is not about this place 28, article may not be about this place 25, fact check 2, no usable summary 2.

- *article may not be about this place*: the article title and opening share no word with the OSM name
  (for example a statue tagged with the article about the person it depicts).
- *model said the source is not about this place*: the model returned an empty intro, as the prompt allows.
- *fact check*: `intro_problems` found a number, a capitalised name, a place feature, an evaluative or
  unverifiable word or a route claim that is not in the source text, or more than 2 sentences.

Places without a kept intro show only their name and category. Every card links its source article
and the CC BY-SA 4.0 license. Meta spend: about $2.44 for the first run and $0.11 for the New Jersey places (spend guard log).

## Limits

- The fact check is lexical: it catches added numbers, names, features and praise, not every
  paraphrase that shifts meaning. A random sample of 6 kept intros was read against its sources
  on 2026-10-29: all 6 only restated or shortened the source.
- Wikipedia summaries can be out of date or wrong; the card says where the text comes from.
