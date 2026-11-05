# StrollCall promo video (16:9)

An 80-second promo for new users. Remotion (React), 1920×1080, 30 fps. Not the hackathon video.

## Re-render
Everything (captions, `captions.srt`, `script.md`, QR, audio mix, both MP4s, `stills/`) comes from one command:

```bash
cd promo && npm install && npm run render
```

Needs Node and ffmpeg. No API key is needed unless the voiceover changes.

## Change the link and QR
Set `shortLink` in `src/config.json`, then re-render. The QR is generated from it and the "QR placeholder" label goes away. To use your own QR, keep the link and replace the `QRCode.toFile` step in `scripts/build.mjs`.

## Change the copy
- On-screen text: `src/scenes/`.
- Voiceover: edit `vo` and `caps` in `src/script.json` (joined `caps` must equal `vo`), run this from the repo root, then re-render. It reads `ELEVENLABS_API_KEY` from `.env`:

```bash
.venv/bin/python promo/audio/vo.py final
```

Scene animations follow the voiceover's word timings, so they move with it.

## Re-record the UI
Start the app locally on port 8770 with `DATABASE_URL` empty, `DB_PATH` on a scratch file and `OPEN_WEIGHTS_API_KEY` empty, then, from `promo/record/`:

```bash
uv run --no-project --with playwright python record.py
```

`feature_test.py` runs every feature the video shows against the local app. Nothing here touches production.

Rendered MP4s, `node_modules/`, `out/` and `assets/` stay out of git.
