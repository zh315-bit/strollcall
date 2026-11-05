"""Voiceover, one file per scene, from ElevenLabs with character timings (the captions are built from them).
The key comes from .env and is never printed.    python vo.py samples | python vo.py final"""
import base64, json, os, subprocess, sys
from pathlib import Path
from dotenv import load_dotenv
from elevenlabs import ElevenLabs, VoiceSettings
ROOT = Path(__file__).resolve().parents[2]; P = ROOT / "promo"
load_dotenv(ROOT / ".env", override=True)
SCRIPT = json.loads((P / "src" / "script.json").read_text())
CANDIDATES = {"Will": "bIHbv24MWmeRgasZH58o", "Jessica": "cgSgspJ2msm6clMCkdW9", "Sarah": "EXAVITQu4vr4xnSDxMaL"}
VOICE = "Will"
MODEL = "eleven_multilingual_v2"
c = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
def tts(voice, text, out):
    r = c.text_to_speech.convert_with_timestamps(voice, text=text, model_id=MODEL, output_format="mp3_44100_128",
        voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.8, style=0.15, speed=0.88))
    out.write_bytes(base64.b64decode(r.audio_base_64))
    a = r.alignment
    return {"chars": a.characters, "start": a.character_start_times_seconds, "end": a.character_end_times_seconds}
if sys.argv[1] == "samples":
    for name, vid in CANDIDATES.items():
        for sid in ("s3", "s1"):
            t = next(s for s in SCRIPT if s["id"] == sid)["vo"]
            al = tts(vid, t, P / "assets" / "vo_samples" / f"{name}_{sid}.mp3")
            print(name, sid, "words", len(t.split()), "secs", round(al["end"][-1], 2), "wpm", round(len(t.split()) / al["end"][-1] * 60))
else:
    out = {}
    for s in SCRIPT:
        if sys.argv[2:] and s["id"] not in sys.argv[2:]: continue
        out[s["id"]] = tts(CANDIDATES[VOICE], s["vo"], P / "public" / "audio" / f"vo_{s['id']}.mp3"); print(s["id"], round(out[s["id"]]["end"][-1], 2))
    f = P / "public" / "audio" / "vo_align.json"; old = json.loads(f.read_text()) if f.exists() else {}; old.update(out); f.write_text(json.dumps(old))
