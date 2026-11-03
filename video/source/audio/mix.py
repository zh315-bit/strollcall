"""Mix the soundtrack and write the captions, then mux with the rendered picture.

    python mix.py 720     # renders/silent_720.mp4 -> renders/preview_720.mp4
    python mix.py 1080    # renders/silent_1080.mp4 -> renders/strollcall_demo.mp4 + .srt

Every placement comes from source/anim/beats.json (the same file the picture and captions use):
- voiceover phrases, cut from the generated files between words (vo_tts/words.json) and placed so each phrase's
  first word lands at its beat;
- the other speech: the wishes Chrome's fake microphone played into the app's real Speak button, and the app's
  own spoken lines captured from /api/voice/speak during the recordings, at the moments they played;
- music under all of it, ducked by the speech (sidechain), with a small lift in the last 8 s and a fade out;
- soft UI clicks on the real taps and a chime when the plan arrives.
"""

import json
import subprocess
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[2]
A, R = V / "assets", V / "renders"
BEATS = json.loads((V / "source" / "anim" / "beats.json").read_text())
WORDS = json.loads((A / "vo_tts" / "words.json").read_text())


def dur(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout)


def vo_segments():
    """(file, seg_start, seg_end, abs_start) for every placed phrase."""
    out = []
    for p in BEATS["vo"]:
        ws, f = WORDS[p["vo"]], A / "vo_tts" / f"{p['vo']}.mp3"
        a, b = p["from"], len(ws) - 1 if p["to"] == "end" else p["to"]
        s0 = 0.0 if a == 0 else (ws[a - 1]["e"] + ws[a]["s"]) / 2
        s1 = dur(f) if b == len(ws) - 1 else (ws[b]["e"] + ws[b + 1]["s"]) / 2
        out.append((f, s0, s1, p["word_at"] - (ws[a]["s"] - s0)))
    return out


def srt_time(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    ms = int(round((s - int(s)) * 1000))
    return f"{h:02d}:{m:02d}:{int(s):02d},{min(ms, 999):03d}"


def write_srt(out):
    caps = json.loads((R / "captions.json").read_text())
    lines = []
    for i, c in enumerate(caps, 1):
        lines += [str(i), f"{srt_time(max(0, c['start']))} --> {srt_time(c['end'])}", *c["lines"], ""]
    out.write_text("\n".join(lines))


def mix(total, out):
    inputs, f, speech = [], [], []
    n = 0
    for (src, s0, s1, at) in vo_segments():
        inputs += ["-i", str(src)]
        ms = int(round(at * 1000))
        f.append(f"[{n}:a]atrim={s0:.3f}:{s1:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
                 f"afade=t=in:d=0.02,afade=t=out:st={max(0, s1 - s0 - 0.04):.3f}:d=0.04,adelay={ms}|{ms}[s{n}]")
        speech.append(f"[s{n}]")
        n += 1
    for s in BEATS["sounds"]:
        inputs += ["-i", str(A / s["file"])]
        ms = int(round(s["at"] * 1000))
        g = s.get("gain", 1.0)
        if "duck_until" in s:  # heard softly under the voiceover, then in full once it ends
            d = s["duck_until"] - s["at"]
            vol = f"volume='{g}*(0.16+0.84*clip((t-{d - 0.3:.3f})/0.3,0,1))':eval=frame"
        else:
            vol = f"volume={g}"
        f.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,{vol},adelay={ms}|{ms}[s{n}]")
        speech.append(f"[s{n}]")
        n += 1
    f.append(f"{''.join(speech)}amix=inputs={len(speech)}:normalize=0,apad=whole_dur={total}[sp]")
    f.append("[sp]asplit=2[sp1][key]")
    inputs += ["-i", str(A / "audio" / "music.mp3")]
    lift = total - 8
    f.append(f"[{n}:a]atrim=0:{total},aresample=48000,volume='0.30*(1+0.35*clip((t-{lift})/2,0,1))':eval=frame,"
             f"afade=t=in:d=1.2,afade=t=out:st={total - 2.5}:d=2.5[mus]")
    f.append("[mus][key]sidechaincompress=threshold=0.015:ratio=7:attack=25:release=450:makeup=1[duck]")
    sfx = []
    for j, t in enumerate(BEATS["clicks"]):
        f.append(f"aevalsrc='0.22*sin(2*PI*1100*t)*exp(-t*45)':s=48000:d=0.12,aformat=channel_layouts=stereo,adelay={int(t * 1000)}|{int(t * 1000)}[c{j}]")
        sfx.append(f"[c{j}]")
    for j, t in enumerate(BEATS["chimes"]):
        f.append(f"aevalsrc='0.16*(sin(2*PI*880*t)*exp(-t*6)+sin(2*PI*1320*max(t-0.12,0))*exp(-max(t-0.12,0)*6)*gte(t,0.12))':s=48000:d=0.8,"
                 f"aformat=channel_layouts=stereo,adelay={int(t * 1000)}|{int(t * 1000)}[h{j}]")
        sfx.append(f"[h{j}]")
    f.append(f"{''.join(sfx)}amix=inputs={len(sfx)}:normalize=0,apad=whole_dur={total}[sfx]")
    f.append(f"[sp1][duck][sfx]amix=inputs=3:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.9,atrim=0:{total}[out]")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(f), "-map", "[out]",
                    "-ar", "48000", str(out)], check=True)


if __name__ == "__main__":
    height = sys.argv[1]
    silent = R / f"silent_{height}.mp4"
    total = dur(silent)
    wav = R / "soundtrack.wav"
    mix(total, wav)
    write_srt(R / "strollcall_demo.srt")
    if height == "720":
        out = R / "preview_720.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "30", "-i", str(R / "frames720" / "%06d.jpg"), "-i", str(wav),
                        "-c:v", "libx264", "-crf", "21", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", str(out)], check=True)
    else:
        out = R / "strollcall_demo.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(silent), "-i", str(wav), "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print(out, f"{total:.2f} s")
