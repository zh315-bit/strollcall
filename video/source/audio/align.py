"""Word timings for each voiceover file (ElevenLabs forced alignment on the generated audio and its text):
video/assets/vo_tts/words.json = {vo_id: [{"w": word, "s": start, "e": end}, ...]}. Used to place picture
beats and captions exactly where the words are spoken."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs import ElevenLabs

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env", override=True)
VO = ROOT / "video" / "assets" / "vo_tts"
client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"], timeout=300)
durs = json.loads((VO / "durations.json").read_text())
out = {}
for k, v in durs.items():
    with open(VO / f"{k}.mp3", "rb") as f:
        r = client.forced_alignment.create(file=f, text=v["text"])
    out[k] = [{"w": w.text, "s": round(w.start, 3), "e": round(w.end, 3)} for w in r.words if w.text.strip()]
    print(k, " ".join(f"{w['w']}@{w['s']:.2f}" for w in out[k]))
(VO / "words.json").write_text(json.dumps(out, indent=1))
