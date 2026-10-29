# Place intros for walking guidance (2026-10-29)

Built with `scripts/build_route_pois.py` and `scripts/make_poi_intros.py`, locally, ahead of time.

## Places

2024 points of interest in the covered area (OpenStreetMap): park 810, artwork 330, historic site 327, memorial 312, landmark 245.
958 have a `wikipedia` or `wikidata` tag; 558 of those resolve to an English Wikipedia article.

## Intros

Model: `muse-spark-1.3` (Muse Spark), one call per place, exact prompt in `frontend/data/poi_intros.json`.
Kept: **502** (park 136, historic site 113, landmark 100, memorial 77, artwork 76).
Dropped: model said the source is not about this place 28, article may not be about this place 25, fact check 2, no usable summary 1.

- *article may not be about this place*: the article title and opening share no word with the OSM name
  (for example a statue tagged with the article about the person it depicts).
- *model said the source is not about this place*: the model returned an empty intro, as the prompt allows.
- *fact check*: `intro_problems` found a number, a capitalised name, a place feature, an evaluative or
  unverifiable word or a route claim that is not in the source text, or more than 2 sentences.

Places without a kept intro show only their name and category. Every card links its source article
and the CC BY-SA 4.0 license. Meta spend for the full run: about $2.44 (spend guard log).

## Limits

- The fact check is lexical: it catches added numbers, names, features and praise, not every
  paraphrase that shifts meaning. A random sample of 6 kept intros was read against its sources
  on 2026-10-29: all 6 only restated or shortened the source.
- Wikipedia summaries can be out of date or wrong; the card says where the text comes from.
