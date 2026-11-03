"""Transcode the recordings the video uses for frame-accurate seeking in the compositor (short GOP, sized for
how large they appear): video/assets/{screen,phone}/X.mp4 -> video/assets/clips/X.mp4."""

import subprocess
from pathlib import Path

A = Path(__file__).resolve().parents[2] / "assets"
CLIPS = ["screen/01_home", "phone/02_solo_voice_glimmer", "screen/03_terminal_glimmer", "phone/04_walking",
         "phone/05_buddy_add_stop", "phone/06_invite_A", "phone/07_accept_B", "phone/08_plan_A", "phone/08_plan_B",
         "screen/10_reports_1"]
(A / "clips").mkdir(exist_ok=True)
for c in CLIPS:
    src, out = A / f"{c}.mp4", A / "clips" / f"{c.split('/')[1]}.mp4"
    scale = "scale=832:-2" if c.startswith("phone") else "scale=1920:-2"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vf", scale, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-g", "6", "-pix_fmt", "yuv420p", "-an", str(out)], check=True)
    print(out.name)
