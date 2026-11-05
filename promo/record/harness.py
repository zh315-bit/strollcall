"""Recording harness for the demo video: real screen recordings of the live site.

Frames come from Chrome's own screencast (CDP Page.startScreencast, JPEG q90 at device pixels), each with
its timestamp, and are assembled into a constant 30 fps H.264 file with ffmpeg (a frame is held until the
next one arrives, so timing is real). Audio the app plays (the buddy's voice, /api/voice/speak) is saved
with its time offset next to the video, for the edit.
"""

import json
import random
import shutil
import subprocess
import time
from base64 import b64decode
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "promo" / "assets"
SITE = "http://127.0.0.1:8770"  # the local app only, never production

# Public places inside the coverage (never anyone's home).
BRYANT_PARK = (40.7536, -73.9832)  # Bryant Park, 6th Ave entrance area
UNION_SQ_STATION = (40.7359, -73.9906)  # 14 St-Union Square subway station
MADISON_SQ_PARK = (40.7420, -73.9880)

# Playwright's sync API delivers Chrome's screencast frames only while it is called, so a plain time.sleep()
# would freeze the recording. While a Recorder runs, sleeping waits inside the page instead.
_real_sleep = time.sleep
_active = []


def _sleep(seconds):
    if _active and seconds > 0:
        _active[-1].page.wait_for_timeout(seconds * 1000)
    else:
        _real_sleep(seconds)


time.sleep = _sleep

PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True,
             user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                         "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"))
DESKTOP = dict(viewport={"width": 1536, "height": 864}, device_scale_factor=1.25)  # 125% of 1920x1080


def launch(p, wav: Path | None = None, dsf: float = 1):
    """Chrome with a fake microphone (playing `wav` once) and frames at device pixels (dsf)."""
    args = [f"--force-device-scale-factor={dsf}", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"]
    if wav:
        args.append(f"--use-file-for-fake-audio-capture={wav}%noloop")
    return p.chromium.launch(channel="chrome", headless=True, args=args)


def pause(a=1.5, b=2.0):
    time.sleep(random.uniform(a, b))


def human_type(page, selector, text):
    page.click(selector)
    for ch in text:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.05, 0.12))


def smooth_scroll(page, dy, steps=None, step_px=6, target=None):
    """Scroll by dy pixels in small steps (about 360 px/s)."""
    steps = steps or max(1, abs(int(dy / step_px)))
    sel = json.dumps(target) if target else "null"
    for _ in range(steps):
        page.evaluate(f"(() => {{ const t = {sel} ? document.querySelector({sel}) : null; "
                      f"(t || window).scrollBy(0, {dy / steps}); }})()")
        time.sleep(1 / 60)


class Recorder:
    """Screencast one page into `out` (.mp4). start() ... stop()."""

    def __init__(self, page, out: Path, max_size=(1920, 2600)):
        self.page, self.out, self.max_size = page, Path(out), max_size
        self.frames_dir = ASSETS / "frames" / self.out.stem
        self.audio_log, self.frames, self.cdp, self.t0, self.stopped = [], [], None, None, False

    def _on_frame(self, params):
        if self.stopped:  # a frame that arrives after stop() belongs to no recording
            return
        i = len(self.frames)
        f = self.frames_dir / f"{i:06d}.jpg"
        f.write_bytes(b64decode(params["data"]))
        self.frames.append((params["metadata"]["timestamp"], f))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:  # noqa: BLE001 - the page may be closing
            pass

    def _on_speak(self, route):
        """The app's spoken lines (/api/voice/speak): fetched on the page's behalf, saved with their time, and
        handed to the page unchanged (reading resp.body() afterwards returns nothing for media)."""
        resp = route.fetch()
        body = resp.body()
        if self.t0 and not self.stopped and resp.ok and body:
            n = len([e for e in self.audio_log if "file" in e])
            f = self.out.with_name(f"{self.out.stem}_voice{n:02d}.mp3")
            f.write_bytes(body)
            req = route.request.post_data_json or {}
            self.audio_log.append({"file": f.name, "t": round(time.time() - self.t0, 2), "text": req.get("text", "")})
        route.fulfill(response=resp, body=body)

    def start(self):
        shutil.rmtree(self.frames_dir, ignore_errors=True)
        self.frames_dir.mkdir(parents=True)
        self.cdp = self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.page.route("**/api/voice/speak", self._on_speak)
        self.t0 = time.time()
        _active.append(self)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": self.max_size[0],
                                               "maxHeight": self.max_size[1], "everyNthFrame": 1})
        return self

    def mark(self, label):
        """A named moment (seconds from start), for the edit plan."""
        self.audio_log.append({"mark": label, "t": round(time.time() - self.t0, 2)})

    def stop(self):
        time.sleep(0.3)
        self.cdp.send("Page.stopScreencast")
        end = time.time()
        _active.remove(self)
        self.stopped = True
        time.sleep(0.3)
        self.page.unroute("**/api/voice/speak", self._on_speak)
        if not self.frames:
            raise RuntimeError(f"{self.out.name}: no frames")
        # concat list: each frame held until the next one (wall-clock timestamps from Chrome)
        lst = self.frames_dir / "list.txt"
        lines = []
        for (t, f), nxt in zip(self.frames, self.frames[1:] + [(end, None)]):
            lines += [f"file '{f}'", f"duration {max(nxt[0] - t, 0.001):.4f}"]
        lines.append(f"file '{self.frames[-1][1]}'")
        lst.write_text("\n".join(lines))
        self.out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264",
                        "-preset", "medium", "-crf", "16", "-movflags", "+faststart", str(self.out)], check=True)
        meta = {"start_wall": self.t0, "duration_s": round(end - self.t0, 2), "frames": len(self.frames),
                "events": self.audio_log}
        self.out.with_suffix(".json").write_text(json.dumps(meta, indent=1))
        shutil.rmtree(self.frames_dir, ignore_errors=True)
        return meta


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)
