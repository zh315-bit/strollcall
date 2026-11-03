"""Render style frames: python still.py s1:6 s7:12 s11:6  ->  video/renders/style_<scene>.png"""

import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

VIDEO = Path(__file__).resolve().parents[2]
OUT = VIDEO / "renders"


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(VIDEO)))
    srv.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    srv = serve()
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        page.on("pageerror", lambda e: print("pageerror", e))
        page.goto(f"http://127.0.0.1:{srv.server_port}/source/anim/stage.html")
        page.evaluate("window.ready")
        for arg in sys.argv[1:]:
            sid, t = arg.split(":")
            page.evaluate(f"render('{sid}', {float(t)})")
            out = OUT / f"style_{sid}.png"
            page.screenshot(path=out)
            print(out)
        b.close()
    srv.shutdown()
