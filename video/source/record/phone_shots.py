"""Phone shots on the live site (iPhone 14 size, frames at 3x): A2 solo by voice with Muse Glimmer, A4 walking
with simulated movement and a detour, A5 the buddy adding a coffee stop, A6-A8 an invite from A to B.

Start points are public places. The microphone is Chrome's fake device playing a TTS WAV (video/assets/wav),
so the app's real Speak button and the real Muse Voice Transcribe call run. Positions during the walk are
simulated along the real planned route (labelled "simulated location" in the edit).
"""

import json
import math
import sys
import time

from playwright.sync_api import sync_playwright

from harness import (ASSETS, BRYANT_PARK, PHONE, SITE, UNION_SQ_STATION, Recorder, human_type, launch, pause,
                     smooth_scroll)

WAV = ASSETS / "wav"
OUT = ASSETS / "phone"
only = set(sys.argv[1:])
log = {}


def ctx_at(browser, where):
    c = browser.new_context(**PHONE, geolocation={"latitude": where[0], "longitude": where[1], "accuracy": 10},
                            permissions=["geolocation", "microphone"])
    c.add_init_script("try { localStorage.setItem('strollcall:voice', 'off'); } catch (e) {}")
    return c


def scroll_to(page, selector, offset=120):
    top = page.evaluate(f"document.querySelector({json.dumps(selector)}).getBoundingClientRect().top")
    smooth_scroll(page, top - offset)


def speak(page, button, seconds):
    """Tap Speak, let the fake microphone play the WAV, tap Stop, wait for the transcript."""
    button.click()
    time.sleep(seconds + 0.6)
    button.click()


def wait_glimmer(page, timeout=30):
    page.wait_for_selector("#intent:not([hidden])", timeout=timeout * 1000)
    return page.inner_text("#intent-source")


def plan_solo(page, wish):
    page.goto(SITE + "/new", wait_until="networkidle")
    page.click("#mode-solo")
    page.fill("#text", wish)
    page.click("#parse")
    src = wait_glimmer(page)
    page.click("#locate")
    page.wait_for_function("!document.querySelector('#create').disabled", timeout=30000)
    page.click("#create")
    page.wait_for_selector(".start-walk", timeout=120000)
    return src


def walk_path(page, pts, speed_mps, every_s=0.5, rec=None, label=None):
    """Move the simulated position along pts [(lat, lon)...] at speed_mps."""
    if label and rec:
        rec.mark(label)
    for (a, b) in zip(pts, pts[1:]):
        d = haversine(a, b)
        n = max(1, int(d / (speed_mps * every_s)))
        for i in range(1, n + 1):
            lat, lon = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
            page.context.set_geolocation({"latitude": lat, "longitude": lon, "accuracy": 10})
            time.sleep(every_s)


def haversine(a, b):
    r = 6371000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def along(pts, meters):
    """The route up to `meters` from its start, ending exactly there."""
    out, done = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:]):
        d = haversine(a, b)
        if done + d >= meters:
            f = (meters - done) / d
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            return out
        out.append(b)
        done += d
    return out


def offset_point(a, b, meters):
    """A point `meters` to the left of the direction a->b, from b."""
    dy, dx = b[0] - a[0], (b[1] - a[1]) * math.cos(math.radians(b[0]))
    n = math.hypot(dx, dy) or 1
    ny, nx = dx / n, -dy / n  # left normal
    deg = meters / 111320
    return (b[0] + ny * deg, b[1] + nx * deg / math.cos(math.radians(b[0])))


with sync_playwright() as p:
    if not only or "A2" in only:
        br = launch(p, WAV / "voice1.wav", dsf=3)
        c = ctx_at(br, BRYANT_PARK)
        page = c.new_page()
        page.goto(SITE + "/new", wait_until="networkidle")
        page.click("#mode-solo")
        time.sleep(2)
        rec = Recorder(page, OUT / "02_solo_voice_glimmer.mp4").start()
        pause(2, 2.5)
        mic = page.get_by_role("button", name="Speak instead of typing")
        rec.mark("tap Speak")
        speak(page, mic, 5.1)
        page.wait_for_function("document.querySelector('#text').value.length > 5", timeout=90000)
        rec.mark("transcript")
        log["A2_transcript"] = page.input_value("#text")
        pause()
        rec.mark("tap Read my wish")
        page.click("#parse")
        log["A2_read_by"] = wait_glimmer(page)
        rec.mark("chips + read-by label")
        time.sleep(1.2)
        scroll_to(page, "#intent", 40)  # the chips and the "Read by" line together in view
        time.sleep(3.5)
        scroll_to(page, "#locate", 160)
        pause()
        page.click("#locate")
        pause()
        scroll_to(page, "#create", 300)
        pause()
        rec.mark("tap Find my walk")
        page.click("#create")
        page.wait_for_selector(".start-walk", timeout=120000)
        rec.mark("plan shown")
        time.sleep(2)
        scroll_to(page, "#map", 100)
        rec.mark("route on map")
        time.sleep(4)
        meta = rec.stop()
        log["A2"] = meta["duration_s"]
        br.close()

    if not only or "A4" in only or "A5" in only:
        br = launch(p, WAV / "voice3.wav", dsf=3)
        c = ctx_at(br, BRYANT_PARK)
        page = c.new_page()
        log["A4_read_by"] = plan_solo(page, "A 25 minute walk to a park, quiet streets")
        geom = page.evaluate("state.solo.candidates[state.chosen].leg.geometry")
        log["A4_dest"] = page.evaluate("state.solo.places[state.solo.candidates[state.chosen].destination_place_id].name")
        scroll_to(page, ".start-walk", 300)
        time.sleep(1.5)
        rec = Recorder(page, OUT / "04_walking.mp4").start()
        pause()
        rec.mark("tap Start walking")
        page.click(".start-walk")
        page.wait_for_selector(".walk-screen", timeout=30000)
        time.sleep(7)  # the "Let's go!" opening plays
        pause()
        rec.mark("Voice on")
        page.click(".voice-toggle")
        time.sleep(3)
        first = along(geom, 220)
        walk_path(page, first, 8.0, rec=rec, label="walking (simulated, about 6x)")
        # detour: step off the route to the left and wait there until the app re-plans
        off = offset_point(first[-2], first[-1], 90)
        walk_path(page, [first[-1], off], 3.0, rec=rec, label="detour off the route")
        rec.mark("waiting off route (15 s rule)")
        for i in range(24):  # standing a little restlessly: a new fix each second, as a phone would send
            j = (i % 2) * 2e-5
            page.context.set_geolocation({"latitude": off[0] + j, "longitude": off[1], "accuracy": 10})
            time.sleep(1)
        rec.mark("re-planned from here")
        time.sleep(5)
        log["A4"] = rec.stop()["duration_s"]
        log["A4_voice_lines"] = len([e for e in json.loads((OUT / "04_walking.json").read_text())["events"] if "file" in e])

        rec = Recorder(page, OUT / "05_buddy_add_stop.mp4").start()
        pause()
        mic = page.locator(".walk-mic")
        box = mic.bounding_box()
        rec.mark("hold mic: add a coffee stop")
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        time.sleep(2.7 + 0.6)
        page.mouse.up()
        rec.mark("let go")
        try:
            page.get_by_role("button", name="Undo").wait_for(timeout=45000)
            rec.mark("Undo visible")
            log["A5_reply"] = page.inner_text(".buddy-text")
        except Exception as e:  # noqa: BLE001
            log["A5_reply"] = f"no Undo: {page.inner_text('.buddy-text') if page.locator('.buddy-text').count() else e}"
        time.sleep(5)
        log["A5"] = rec.stop()["duration_s"]
        br.close()

    if not only or "A6" in only or "A6only" in only:
        br = launch(p, WAV / "voice2.wav", dsf=3)
        a = ctx_at(br, BRYANT_PARK)
        pa = a.new_page()
        pa.goto(SITE + "/new", wait_until="networkidle")
        time.sleep(1.5)
        rec = Recorder(pa, OUT / "06_invite_A.mp4").start()
        pause()
        rec.mark("With a friend")
        pa.click("#mode-pair")
        pause()
        human_type(pa, "#text", "30 minutes, coffee at the end")
        pause()
        pa.click("#parse")
        log["A6_read_by"] = wait_glimmer(pa)
        time.sleep(2.5)
        scroll_to(pa, "#locate", 160)
        pa.click("#locate")
        pause()
        scroll_to(pa, "#create", 300)
        pause()
        rec.mark("tap Invite a friend")
        pa.click("#create")
        pa.wait_for_url("**/i/**", timeout=120000)
        pa.wait_for_selector(".card-image", timeout=60000)
        time.sleep(1.5)
        scroll_to(pa, ".card-image", 90)
        rec.mark("invite card")
        time.sleep(5)
        log["A6"] = rec.stop()["duration_s"]
        token = pa.url.split("/i/")[1].split("#")[0]
        log["invite_token"] = token
        (ASSETS / "data" / "demo_invites.local.json").write_text(json.dumps(
            {"note": "invites made for the demo video; leave out of the user-test report", "tokens": [token],
             "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1))

        if "A6only" in only:
            br.close()
            raise SystemExit(print(json.dumps(log, indent=1)))
        # A7: B opens the link on another phone
        b = ctx_at(br, UNION_SQ_STATION)
        pb = b.new_page()
        pb.goto(f"{SITE}/i/{token}", wait_until="networkidle")
        time.sleep(1.5)
        rec = Recorder(pb, OUT / "07_accept_B.mp4").start()
        pause()
        pb.get_by_role("button", name="Use my location").click()
        pause()
        mic = pb.get_by_role("button", name="Speak instead of typing")
        scroll_to(pb, "textarea", 260)
        pause()
        rec.mark("B speaks")
        speak(pb, mic, 3.6)
        pb.wait_for_function("document.querySelector('textarea').value.length > 3", timeout=30000)
        log["A7_transcript"] = pb.input_value("textarea")
        pause()
        rec.mark("tap I'm in")
        pb.get_by_role("button", name="I'm in").click()
        time.sleep(3)
        log["A7"] = rec.stop()["duration_s"]

        # A8: the plan on both phones
        rec = Recorder(pb, OUT / "08_plan_B.mp4").start()
        pb.wait_for_function("document.querySelectorAll('#map path.leaflet-interactive').length >= 3", timeout=240000)
        rec.mark("plan arrived")
        try:
            pb.wait_for_function("!document.querySelector('.spinner')", timeout=90000)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
        smooth_scroll(pb, 500)
        time.sleep(3)
        log["A8_read_by"] = pb.evaluate("[...document.querySelectorAll('p')].map(p => p.textContent).find(t => t.startsWith('Wishes read by')) || ''")
        smooth_scroll(pb, 700)
        time.sleep(3)
        log["A8_B"] = rec.stop()["duration_s"]

        pa.reload(wait_until="networkidle")
        pa.wait_for_function("document.querySelectorAll('#map path.leaflet-interactive').length >= 3", timeout=120000)
        time.sleep(2)
        rec = Recorder(pa, OUT / "08_plan_A.mp4").start()
        time.sleep(2.5)
        smooth_scroll(pa, 500)
        time.sleep(3)
        smooth_scroll(pa, 700)
        time.sleep(3)
        log["A8_A"] = rec.stop()["duration_s"]
        br.close()

(ASSETS / "data" / f"record_log_{int(time.time())}.local.json").write_text(json.dumps(log, indent=1))
print(json.dumps(log, indent=1))
