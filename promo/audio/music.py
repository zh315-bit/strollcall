"""Original background music, synthesised here from scratch (no samples, nothing downloaded): plucked Karplus-Strong
guitar arpeggios, soft bass, a warm pad and a light shaker, 84 BPM. Released under CC0 (see CREDITS.md).   python music.py"""
import subprocess, wave
from pathlib import Path
import numpy as np
SR = 44100; BPM = 84; BEAT = 60 / BPM; DUR = 81.0
rng = np.random.default_rng(7)
def note(n): return 440 * 2 ** ((n - 69) / 12)
def pluck(f, dur, bright=.5):
    n = int(SR * dur); p = int(SR / f); buf = rng.uniform(-1, 1, p)
    buf = np.convolve(buf, np.ones(3) / 3, "same") * (0.6 + bright * .4)
    out = np.zeros(n); d = 0.4985
    for i in range(0, n, p):                      # vectorised per period
        m = min(p, n - i); out[i:i + m] = buf[:m]
        buf = d * (buf + np.roll(buf, 1))
    return out * np.exp(-np.arange(n) / (SR * dur * .45))
def pad(notes, dur):
    t = np.arange(int(SR * dur)) / SR; s = sum(np.sin(2 * np.pi * note(n) * t) + .3 * np.sin(2 * np.pi * note(n) * 2.003 * t) for n in notes)
    return s * np.minimum(1, t / .6) * np.minimum(1, (dur - t) / .8) / len(notes)
L = np.zeros(int(SR * (DUR + 4))); Rr = L.copy()
def put(x, at, gain, pan=0):
    i = max(0, int(at * SR)); x = x[:len(L) - i]
    L[i:i + len(x)] += x * gain * (1 - pan) ** .5 * .8; Rr[i:i + len(x)] += x * gain * (1 + pan) ** .5 * .8
CH = [([48, 55, 64, 67, 71, 72], 36), ([45, 52, 60, 64, 67, 72], 33), ([41, 48, 57, 60, 64, 69], 29), ([43, 50, 59, 62, 67, 71], 31)]
PAT = [0, 2, 3, 4, 5, 4, 3, 2]; bars = int(79 / (4 * BEAT))
for b in range(bars):
    ch, bass = CH[b % 4]; t0 = b * 4 * BEAT; full = b >= 2
    put(pad(ch[1:4], 4 * BEAT + .6), t0, .05, 0)
    for k, ix in enumerate(PAT):
        sw = .018 if k % 2 else 0
        put(pluck(note(ch[ix]), 1.8, .5), t0 + k * BEAT / 2 + sw + rng.uniform(-.006, .006), (.3 if k % 4 == 0 else .22) * rng.uniform(.85, 1), (ix - 3) * .1)
    if full:
        put(pluck(note(bass), 2.2, .2), t0, .34); put(pluck(note(bass + 7), 1.6, .2), t0 + 2 * BEAT, .22)
    if b >= 4:
        for k in range(8):
            n = rng.normal(0, 1, int(SR * .05)) * np.exp(-np.arange(int(SR * .05)) / (SR * .012))
            n = np.diff(n, prepend=0); put(n, t0 + k * BEAT / 2, .028 if k % 2 else .014, .3)
end = bars * 4 * BEAT
for n, d in zip((48, 55, 64, 67, 72), (0, .05, .1, .15, .2)): put(pluck(note(n), 3.5, .5), end + d, .3, 0)
ir = rng.normal(0, 1, int(SR * 1.4)) * np.exp(-np.arange(int(SR * 1.4)) / (SR * .35)); ir /= np.sqrt((ir ** 2).sum())
def rev(x):
    n = 1 << int(np.ceil(np.log2(len(x) + len(ir)))); y = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[:len(x)]; return x + .22 * y
s = np.stack([rev(L), rev(Rr)], 1)[:int(SR * DUR)]
fade = np.ones(len(s)); fl = int(SR * 2.0); fade[-fl:] = np.linspace(1, 0, fl) ** 1.5; s *= fade[:, None]
s = s / np.abs(s).max() * .7
out = Path(__file__).resolve().parents[1] / "public" / "audio"; w = out / "_music.wav"
with wave.open(str(w), "wb") as f:
    f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR); f.writeframes((s * 32767).astype("<i2").tobytes())
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(w), "-b:a", "192k", str(out / "music.mp3")], check=True); w.unlink()
print("music ok", round(len(s) / SR, 1), "bars", bars, "ends", round(end, 1))
