# Map data for the deployed app

- `nyc_graph.npz`: walking graph (Manhattan, northern Brooklyn, Long Island City), built by
  `scripts/build_graph.py` from OpenStreetMap via OSMnx.
- `nyc_places.json.gz`: places snapshot from the same build, with `fetched_at`.
- `nyc_pois.json.gz`: parks, historic sites, artworks, memorials and landmarks for walking
  guidance, from `scripts/build_route_pois.py` (the build's cached OSM data plus one Overpass query).

Both are derived from OpenStreetMap data, © OpenStreetMap contributors, and are made available
under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Rebuild with `python scripts/build_graph.py` and copy the files from `data/`.
