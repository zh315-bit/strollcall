"""Render the demo frame by frame in headless Chrome, in parallel, then assemble with ffmpeg.

    python render.py stills 3.5 30 52 ...      # single frames -> video/renders/stills/t_<sec>.jpg (1920x1080)
    python render.py video 720 [workers]       # all frames -> video/renders/frames720/ -> silent_720.mp4
    python render.py video 1080 [workers]
"""

import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

VIDEO = Path(__file__).resolve().parents[2]
REN = VIDEO / "renders"
FPS = 30


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(VIDEO)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def open_page(p, port, height):
    scale = height / 1080
    b = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    page = b.new_page(viewport={"width": round(1920 * scale), "height": height})
    page.on("pageerror", lambda e: print("pageerror", e))
    page.goto(f"http://127.0.0.1:{port}/source/anim/compose.html")
    info = page.evaluate("window.ready")
    if scale != 1:
        page.evaluate(f"document.getElementById('stage').style.transform = 'scale({scale})'")
    return b, page, info


def worker(port, height, frames, outdir):
    with sync_playwright() as p:
        b, page, _ = open_page(p, port, height)
        for i in frames:
            page.evaluate(f"renderFrame({i / FPS})")
            page.screenshot(path=outdir / f"{i:06d}.jpg", type="jpeg", quality=92)
        b.close()


if __name__ == "__main__":
    srv = serve()
    port = srv.server_port
    if sys.argv[1] == "stills":
        out = REN / "stills"
        out.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            b, page, info = open_page(p, port, 1080)
            for s in sys.argv[2:]:
                sid = page.evaluate(f"renderFrame({float(s)})")
                page.screenshot(path=out / f"t_{float(s):06.2f}.jpg", type="jpeg", quality=90)
                print(s, sid)
            b.close()
    else:
        height = int(sys.argv[2])
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
        with sync_playwright() as p:
            b, page, info = open_page(p, port, 360)
            b.close()
        total = info["total"]
        (VIDEO / "renders" / "captions.json").write_text(json.dumps(info["caps"], indent=1))
        nframes = round(total * FPS)
        outdir = REN / f"frames{height}"
        outdir.mkdir(parents=True, exist_ok=True)
        todo = [i for i in range(nframes) if not (outdir / f"{i:06d}.jpg").exists()]
        chunks = [todo[k::n] for k in range(n)]
        print(f"{total:.2f} s, {nframes} frames, {len(todo)} to render with {n} workers")
        with ThreadPoolExecutor(n) as ex:
            list(ex.map(lambda c: worker(port, height, c, outdir), chunks))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(outdir / "%06d.jpg"),
                        "-vf", "scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                        str(REN / f"silent_{height}.mp4")], check=True)
        print(REN / f"silent_{height}.mp4")
    srv.shutdown()
