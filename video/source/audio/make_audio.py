"""Voiceover (ElevenLabs text to speech, a premade voice, never a clone) and one instrumental music track
(ElevenLabs Music) for the demo video. The key comes from .env (ELEVENLABS_API_KEY); nothing is printed.

    python make_audio.py vo        # video/assets/vo_tts/vo_*.mp3 (+ durations.json)
    python make_audio.py music     # video/assets/audio/music.mp3

VO text is the approved script (video/plan/edit_plan.md) with the bracketed numbers filled from data.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs import ElevenLabs, VoiceSettings

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env", override=True)
VO_DIR = ROOT / "video" / "assets" / "vo_tts"
AUDIO = ROOT / "video" / "assets" / "audio"
VOICE = "iP95p4xoKVk53GoZ742B"  # premade "Chris - Charming, Down-to-Earth" (American, conversational)
MODEL = "eleven_v4"

VO = {
    "vo_01a": "I'm Chris. Some afternoons I want to go outside, but I don't know where to go.",
    "vo_01b": "And my friends? Mostly homebodies. 'We should hang out' never turns into a plan.",
    "vo_02": "So I built StrollCall. Tell it how long you have and what you feel like, and it plans a short walk worth taking: on your own, or with a friend.",
    "vo_03": "I just say what I want. Muse Voice transcribes it, and Muse Glimmer, an open-weights model I host on Modal, turns it into a plan the route engine understands, in about half a second.",
    "vo_04": "While I walk, the map fills the screen, and my walking buddy listens. When I ask for a coffee stop, Muse Spark picks a tool, the planner re-routes, and only real, open places come back.",
    "vo_05": "Walking is better with someone. I send one link. My friend doesn't need an app: one tap, and they can say what they'd like too.",
    "vo_06": "Muse Spark balances both of our wishes and explains the trade-off. And the meeting point is fair by walking time, not by distance on a map: here, the map's midpoint leaves us 4.8 minutes apart; ours gets us there within a minute.",
    "vo_07": "Under the hood: a walking graph of New York with 139,106 points, built from OpenStreetMap, plans in milliseconds. Meta models handle the human side: Muse Glimmer reads wishes, Muse Spark negotiates and ranks, Muse Image draws the invite, Muse Voice listens.",
    "vo_08": "Every evaluation was committed before it ran. 12 of 12 test pairs got the right outcome. Meta's reading caught 10 of 10 wishes, against 7 for keyword rules. And a checker throws out any claim our data can't back up.",
    "vo_10": "StrollCall. Less planning. More walking.",
}

MUSIC_PROMPT = ("Light, upbeat acoustic instrumental for a friendly app demo: warm fingerpicked acoustic guitar, "
                "soft ukulele, gentle glockenspiel and light brushed percussion, a sunny afternoon walk in the city, "
                "around 100 BPM, steady and unobtrusive under a voiceover, no vocals, a small lift and a clean ending "
                "in the last 10 seconds.")


def duration(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip())


def make_vo(client, only=None):
    VO_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for k, text in VO.items():
        if only and k not in only:
            continue
        audio = client.text_to_speech.convert(VOICE, text=text, model_id=MODEL, output_format="mp3_44100_128",
                                              voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.75),
                                              apply_text_normalization="on")
        f = VO_DIR / f"{k}.mp3"
        f.write_bytes(b"".join(audio))
        out[k] = {"text": text, "seconds": round(duration(f), 2)}
        print(k, out[k]["seconds"])
    meta = VO_DIR / "durations.json"
    old = json.loads(meta.read_text()) if meta.exists() else {}
    old.update(out)
    meta.write_text(json.dumps(old, indent=1))


def make_music(client):
    AUDIO.mkdir(parents=True, exist_ok=True)
    audio = client.music.compose(prompt=MUSIC_PROMPT, music_length_ms=178000, model_id="music_v2_5",
                                 force_instrumental=True)
    f = AUDIO / "music.mp3"
    f.write_bytes(b"".join(audio))
    print("music", round(duration(f), 1))


if __name__ == "__main__":
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"], timeout=300)
    what = sys.argv[1]
    if what == "vo":
        make_vo(client, set(sys.argv[2:]) or None)
    elif what == "music":
        make_music(client)
