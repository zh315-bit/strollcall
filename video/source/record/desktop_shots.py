"""A1 (home), A9 (How it works), A10 (reports on GitHub): desktop, 1920x1080 at 125%."""

import sys
import time

from playwright.sync_api import sync_playwright

from harness import ASSETS, DESKTOP, SITE, Recorder, launch, pause, smooth_scroll

REPO = "https://github.com/zh315-bit/strollcall/blob/main"
REPORTS = [  # (file, text to scroll to)
    ("benchmarks/2026-10-31-local.md", None),
    ("benchmarks/2026-10-28-ablation-wishes.md", None),
    ("benchmarks/2026-10-31-open-weights-run1.md", None),
]
only = set(sys.argv[1:])
SCREEN = ASSETS / "screen"

with sync_playwright() as p:
    browser = launch(p, dsf=1.25)
    ctx = browser.new_context(**DESKTOP)
    page = ctx.new_page()

    if not only or "A1" in only:
        page.goto(SITE + "/", wait_until="networkidle")
        time.sleep(3)
        rec = Recorder(page, SCREEN / "01_home.mp4").start()
        time.sleep(4)
        btn = page.get_by_role("link", name="Plan my walk").first
        btn.hover()
        pause()
        rec.mark("click Plan my walk")
        btn.click()
        page.wait_for_load_state("networkidle")
        time.sleep(4)
        print("A1", rec.stop()["duration_s"])

        page.goto(SITE + "/", wait_until="networkidle")
        time.sleep(3)
        rec = Recorder(page, SCREEN / "01b_home_fair.mp4").start()
        time.sleep(2)
        top = page.evaluate("document.querySelector('#fair').getBoundingClientRect().top")
        smooth_scroll(page, top - 60)
        rec.mark("fair section in view")
        time.sleep(14)
        print("A1b", rec.stop()["duration_s"])

    if not only or "A9" in only:
        page.goto(SITE + "/how", wait_until="networkidle")
        time.sleep(2)
        rec = Recorder(page, SCREEN / "09_how_it_works.mp4").start()
        time.sleep(2)
        height = page.evaluate("document.documentElement.scrollHeight - innerHeight")
        smooth_scroll(page, height, step_px=3)
        time.sleep(2)
        print("A9", rec.stop()["duration_s"])

    if not only or "A10" in only:
        big = launch(p, dsf=1.875)  # GitHub at 1024x576 CSS px = 1920x1080: numbers large enough to read
        gh = big.new_context(viewport={"width": 1024, "height": 576}, device_scale_factor=1.875)
        gp = gh.new_page()
        for i, (f, _) in enumerate(REPORTS):
            gp.goto(f"{REPO}/{f}", wait_until="domcontentloaded")
            gp.wait_for_selector("article", timeout=30000)
            time.sleep(2)
            gp.evaluate("document.querySelector('article').scrollIntoView({block: 'start'})")
            time.sleep(1)
            rec = Recorder(gp, SCREEN / f"10_reports_{i + 1}.mp4").start()
            time.sleep(2)
            smooth_scroll(gp, 900, step_px=2)
            time.sleep(2)
            print("A10", f, rec.stop()["duration_s"])
        gh.close()
        big.close()
    browser.close()
