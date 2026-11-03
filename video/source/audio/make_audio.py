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
# The narrator's own voice, cloned by the user in their ElevenLabs account ("个人声音", instant voice clone).
# Earlier takes used the premade "Chris - Charming, Down-to-Earth" (iP95p4xoKVk53GoZ742B); kept in vo_tts/premade_chris/.
VOICE = os.environ.get("VO_VOICE_ID", "8vqmfub9vtiy1qBBmHeb")
MODEL = "eleven_v4"

# Final script (revision 3): confident, contrastive, every number from the repo:
# 6.5x = 3.58 s / 0.55 s median wish reading (benchmarks/2026-10-31-open-weights-run1.md:14); 29 ms median planning
# (benchmarks/2026-10-31-local.md:16); 139,106 nodes (local.md:3); 4.8 vs 0.6 min apart, 8x = 4.8 / 0.6
# (fairness_example.json); 12 of 12 (local.md:13); 10 of 10 vs 7 (2026-10-28-ablation-wishes.md:16).
VO = {
    "vo_01a": "I'm Chris. Some afternoons I want to get outside, but I never know where to go.",
    "vo_01b": "And my friends? Total homebodies. 'We should hang out' never becomes a plan.",
    "vo_02": "So I built StrollCall. Map apps need a destination. StrollCall starts from how you feel: tell it how long you have and what you're in the mood for, and it plans a walk worth taking, solo or with a friend.",
    "vo_03": "I just say it. Muse Voice transcribes it, and Muse Glimmer, Meta's open-weights model running on my own H200 on Modal, reads it in about half a second, six and a half times faster than the API. And my location never goes to any model.",
    "vo_04": "And it doesn't stop at directions. While I walk, the map fills the screen, and my buddy listens. Mid-walk, I ask for a coffee stop: Muse Spark calls a tool, the planner re-routes, and only real, open places come back.",
    "vo_05": "Walking is better together. One link, no app, no sign-up. My friend taps once, and says what they'd like too.",
    "vo_06": "Muse Spark balances both of our wishes and explains the trade-off. Splitting the distance isn't fair: the map's midpoint leaves us 4.8 minutes apart. StrollCall splits the walking time instead: just 0.6 minutes apart, an eight-times smaller gap.",
    "vo_07": "Under the hood, our own walking graph of New York: 139,106 points from OpenStreetMap, planning a walk in about 29 milliseconds. Four Meta models do the human side: Muse Glimmer reads wishes, Muse Spark negotiates and ranks, Muse Image draws the invite, Muse Voice listens.",
    "vo_08": "And unlike a typical chatbot, it's built not to make things up. Every evaluation is pre-registered. 12 out of 12 test pairs, all correct. Meta's reading caught every wish, 10 of 10, where keyword rules caught 7. And a checker throws out any claim our data can't back up.",
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
                                              voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.85),
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
