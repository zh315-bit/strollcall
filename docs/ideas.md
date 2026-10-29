# Ideas (parked during the feature freeze)

**Feature freeze from 2026-10-29.** Only bugs found in real-world tests get fixed. Anything new
goes on this list instead of into the code. Each entry: what, why, and a rough cost.

## How we work during the freeze

- Bug fixes only, each with a test that fails before the fix and passes after it.
- Parallel work happens on a separate branch or git worktree, and is merged into `main` only
  after the backend suite passes (`cd backend && ../.venv/bin/python -m pytest -q`, which also
  runs the Node walk tests). Two sessions never edit the same files on the same branch.
- Every merge to `main` deploys (Render autoDeploy), so `main` stays releasable.

## Parked ideas

| Idea | Why | Rough cost |
| --- | --- | --- |
| Speak the place intros on walks (opt-in, after the turn prompts) | hands-free walks | small: reuse `say()`, skip during turns |
| "Uptown / downtown" wording on Manhattan's grid instead of compass words | how New Yorkers give directions; the grid is rotated 29° | small, in `directions.py` |
| Share live progress with the other walker ("2 min away") | the arrival gap is the most common worry | large: needs a relay and consent; privacy review |
| Background tracking via a native wrapper (PWA cannot) | screen must stay on today | large; out of scope for a web app |
| Rebuild the place snapshot keeping `wikipedia`/`wikidata` tags | intros for meetup and destination places too, not only POIs | medium: one build run + re-run intros |
| Smarter sentence splitting in the intro fact check ("p.m.", "Times Up!") | a few good intros are dropped | small |
| Muse Glimmer privacy mode (DEV_DOC) | on-device-style text for location-sensitive parts | medium; needs a host |
| iOS Safari runs in the Simulator in CI-like checks | real WebKit, not Chromium emulation | small once Xcode is selected and its license accepted |
| Turn-by-turn for the ORS fallback legs | outside the local map there are no steps today | medium |
