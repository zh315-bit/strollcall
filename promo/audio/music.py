"""Original background music, synthesised here from scratch (no samples, nothing downloaded): a warm, slow pad with
soft sine notes on top. Every note fades in, so there is no plucked or struck attack, and everything is low-passed.
Released under CC0 (see CREDITS.md).   python music.py"""
import subprocess, wave
from pathlib import Path
import numpy as np
SR = 44100; DUR = 81.0; BAR = 7.2                     # one chord every 7.2 s
rng = np.random.default_rng(11)
N = int(SR * (DUR + 8)); L = np.zeros(N); R = np.zeros(N)
hz = lambda n: 440 * 2 ** ((n - 69) / 12)
def env(n, a, r):
    t = np.arange(n) / SR; d = n / SR
    return np.sin(np.minimum(1, t / a) * np.pi / 2) ** 2 * np.sin(np.minimum(1, (d - t) / r) * np.pi / 2) ** 2
def put(x, at, g, pan=0.):
    i = int(at * SR); x = x[:N - i]; L[i:i + len(x)] += x * g * (1 - pan) ** .5; R[i:i + len(x)] += x * g * (1 + pan) ** .5
def pad(n, dur):
    t = np.arange(int(SR * dur)) / SR; f = hz(n)
    s = sum(np.sin(2 * np.pi * f * (1 + d) * t + rng.uniform(0, 6)) for d in (-.0016, 0, .0016)) / 3 + .1 * np.sin(2 * np.pi * 2 * f * t)
    return s * env(len(t), 2.4, 3.0) * (1 + .12 * np.sin(2 * np.pi * rng.uniform(.06, .14) * t))
def soft(n, dur=4.5):
    t = np.arange(int(SR * dur)) / SR
    return (np.sin(2 * np.pi * hz(n) * t) + .08 * np.sin(2 * np.pi * 2 * hz(n) * t)) * env(len(t), .35, 3.2)
CH = [(36, [48, 55, 59, 64]), (33, [45, 52, 55, 60]), (29, [41, 48, 52, 57]), (31, [43, 50, 55, 59])]   # Cmaj7 Am7 Fmaj7 G
TUNE = [[(0, 67), (3.6, 64)], [(0, 64), (3.6, 60)], [(0, 65), (3.6, 69)], [(0, 67), (3.6, 62)],
        [(0, 72), (3.6, 67)], [(0, 69), (3.6, 64)], [(0, 65), (3.6, 60)], [(0, 62), (3.6, 67)]]
bars = int(76 / BAR) + 1
for b in range(bars):
    root, notes = CH[b % 4]; t0 = b * BAR
    put(pad(root + 12, BAR + 3.5), t0, .07)
    for i, n in enumerate(notes): put(pad(n, BAR + 3.5), t0, .085, (i - 1.5) * .22)
    if b >= 1:
        for dt, n in TUNE[b % 8]: put(soft(n), t0 + dt, .17, rng.uniform(-.25, .25))
ir = rng.normal(0, 1, int(SR * 3)) * np.exp(-np.arange(int(SR * 3)) / (SR * .8)); ir /= np.sqrt((ir ** 2).sum())
def finish(x):
    n = 1 << int(np.ceil(np.log2(len(x) + len(ir)))); X = np.fft.rfft(x, n); f = np.fft.rfftfreq(n, 1 / SR)
    lp = 1 / (1 + (f / 1800) ** 4)                     # nothing bright gets through
    return np.fft.irfft(X * lp * (1 + .3 * np.fft.rfft(ir, n)), n)[:len(x)]
s = np.stack([finish(L), finish(R)], 1)[:int(SR * DUR)]
fade = np.ones(len(s)); fl = int(SR * 3.5); fade[-fl:] = np.cos(np.linspace(0, np.pi / 2, fl)) ** 2; s *= fade[:, None]
s = s / np.abs(s).max() * .7
out = Path(__file__).resolve().parents[1] / "public" / "audio"; w = out / "_music.wav"
with wave.open(str(w), "wb") as f:
    f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR); f.writeframes((s * 32767).astype("<i2").tobytes())
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(w), "-b:a", "192k", str(out / "music.mp3")], check=True); w.unlink()
print("music ok", round(len(s) / SR, 1), "chords", bars)
