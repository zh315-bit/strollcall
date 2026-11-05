"""Spoken test phrases for Chrome's fake microphone (the app's real mic path runs on them). Key from .env, never printed."""
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import os
from elevenlabs import ElevenLabs
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)
OUT = ROOT / "promo" / "assets" / "wav"
LINES = {"wish": "Twenty minutes, quiet streets, coffee at the end.", "coffee": "Can we stop for a coffee?",
         "shorter": "Can we make it shorter?", "nearby": "What's nearby?"}
c = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
for k, t in LINES.items():
    mp3 = OUT / f"{k}.mp3"
    mp3.write_bytes(b"".join(c.text_to_speech.convert("cgSgspJ2msm6clMCkdW9", text=t, model_id="eleven_multilingual_v2", output_format="mp3_44100_128")))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-af", "adelay=300,apad=pad_dur=0.8", "-ar", "48000", "-ac", "1", str(OUT / f"{k}.wav")], check=True)
    mp3.unlink()
    print(k, "ok")
