"""Mix the soundtrack and write the captions, then mux with the rendered picture.

    python mix.py 720     # renders/silent_720.mp4 -> renders/preview_720.mp4 (burned-in timecode)
    python mix.py 1080    # renders/silent_1080.mp4 -> renders/strollcall_demo.mp4 + .srt

Voiceover at the times in timeline.js (VO_AT); music under it, ducked by the voice (sidechain), a small lift
in the last 8 s and a fade at the end; soft UI clicks on the real taps; a chime when the plan arrives.
"""

import json
import subprocess
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[2]
A, R = V / "assets", V / "renders"
VO_AT = {"vo_01a": 0.4, "vo_01b": 8.3, "vo_02": 16.3, "vo_03": 34.5, "vo_04": 50.3, "vo_05": 65.5, "vo_06": 85.4,
         "vo_07": 105.4, "vo_08": 126.3, "vo_10": 164.6}
CLICKS = [28.95, 37.92, 43.49, 56.56, 80.93]  # Speak, Read my wish, Find my walk, hold to talk, I'm in (scene times of the real taps)
CHIMES = [81.6]                                 # the plan arrives on both phones


def srt_time(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"


def write_srt(out):
    caps = json.loads((R / "captions.json").read_text())
    lines = []
    for i, c in enumerate(caps, 1):
        lines += [str(i), f"{srt_time(c['start'])} --> {srt_time(c['end'] + 0.15)}", *c["lines"], ""]
    out.write_text("\n".join(lines))


def mix(total, out):
    inputs, filters, vo_labels = [], [], []
    for i, (k, at) in enumerate(VO_AT.items()):
        inputs += ["-i", str(A / "vo_tts" / f"{k}.mp3")]
        filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(at * 1000)}|{int(at * 1000)}[v{i}]")
        vo_labels.append(f"[v{i}]")
    n = len(VO_AT)
    filters.append(f"{''.join(vo_labels)}amix=inputs={n}:normalize=0,apad=whole_dur={total}[vo]")
    filters.append("[vo]asplit=2[vo1][vokey]")
    inputs += ["-i", str(A / "audio" / "music.mp3")]
    m = n
    lift = total - 8
    filters.append(f"[{m}:a]atrim=0:{total},aresample=48000,volume='0.30*(1+0.35*clip((t-{lift})/2,0,1))':eval=frame,"
                   f"afade=t=in:d=1.2,afade=t=out:st={total - 2.5}:d=2.5[mus]")
    filters.append("[mus][vokey]sidechaincompress=threshold=0.015:ratio=7:attack=25:release=450:makeup=1[duck]")
    # UI sounds: a soft click and a two-note chime, synthesized
    sfx = []
    for j, t in enumerate(CLICKS):
        filters.append(f"aevalsrc='0.22*sin(2*PI*1100*t)*exp(-t*45)':s=48000:d=0.12,aformat=channel_layouts=stereo,adelay={int(t * 1000)}|{int(t * 1000)}[c{j}]")
        sfx.append(f"[c{j}]")
    for j, t in enumerate(CHIMES):
        filters.append(f"aevalsrc='0.16*(sin(2*PI*880*t)*exp(-t*6)+sin(2*PI*1320*max(t-0.12,0))*exp(-max(t-0.12,0)*6)*gte(t,0.12))':s=48000:d=0.8,"
                       f"aformat=channel_layouts=stereo,adelay={int(t * 1000)}|{int(t * 1000)}[h{j}]")
        sfx.append(f"[h{j}]")
    filters.append(f"{''.join(sfx)}amix=inputs={len(sfx)}:normalize=0,apad=whole_dur={total}[sfx]")
    filters.append("[vo1][duck][sfx]amix=inputs=3:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.9,atrim=0:" + str(total) + "[out]")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
                    "-ar", "48000", str(out)], check=True)


if __name__ == "__main__":
    height = sys.argv[1]
    silent = R / f"silent_{height}.mp4"
    total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(silent)],
                                 capture_output=True, text=True).stdout)
    wav = R / "soundtrack.wav"
    mix(total, wav)
    srt = R / "strollcall_demo.srt"
    write_srt(srt)
    if height == "720":
        # burned-in timecode (HH:MM:SS:FF) drawn on the rendered frames, then encoded with the soundtrack
        tc = R / "frames720_tc"
        subprocess.run(["uv", "run", "-q", "--with", "pillow", "python", str(Path(__file__).with_name("timecode.py")),
                        str(R / "frames720"), str(tc)], check=True)
        out = R / "preview_720.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "30", "-i", str(tc / "%06d.jpg"), "-i", str(wav),
                        "-c:v", "libx264", "-crf", "21", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", str(out)], check=True)
    else:
        out = R / "strollcall_demo.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(wav), "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print(out, f"{total:.2f} s")
