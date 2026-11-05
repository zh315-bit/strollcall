"""Runs every feature the promo shows against the LOCAL app (never production), start points in public places."""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[2]; WAV = ROOT / "promo" / "assets" / "wav"; SITE = "http://127.0.0.1:8770"
ARCH = (40.7312, -73.9973)      # Washington Square Arch
ASTOR = (40.7301, -73.9910)     # Astor Place subway plaza
UNION = (40.7359, -73.9906)     # Union Square station
PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
R = {}
def launch(p, wav):
    return p.chromium.launch(channel="chrome", headless=True, args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required", f"--use-file-for-fake-audio-capture={wav}%noloop"])
def ctx(b, where):
    c = b.new_context(**PHONE, geolocation={"latitude": where[0], "longitude": where[1], "accuracy": 10}, permissions=["geolocation", "microphone"])
    return c
def check(name, fn):
    try:
        R[name] = {"ok": True, "detail": fn()}
    except Exception as e:
        R[name] = {"ok": False, "detail": str(e)[:300]}
    print(name, R[name], flush=True)
def hold(page, s):
    m = page.locator(".walk-mic"); m.scroll_into_view_if_needed(); bx = m.bounding_box()
    page.mouse.move(bx["x"] + bx["width"] / 2, bx["y"] + bx["height"] / 2); page.mouse.down(); time.sleep(s); page.mouse.up()
def solo(page, wish, typed=True):
    page.goto(SITE + "/new", wait_until="networkidle"); page.click("#mode-solo")
    if typed: page.fill("#text", wish)
    else:
        mic = page.get_by_role("button", name="Speak instead of typing"); mic.click(); time.sleep(4.5); mic.click()
        page.wait_for_function("document.querySelector('#text').value.length > 5", timeout=60000)
    tx = page.input_value("#text"); page.click("#parse"); page.wait_for_selector("#intent:not([hidden])", timeout=40000)
    page.click("#locate"); page.wait_for_function("!document.querySelector('#create').disabled", timeout=30000)
    page.click("#create"); page.wait_for_selector(".start-walk", timeout=120000)
    return tx
which = set(sys.argv[1:])
with sync_playwright() as p:
    if not which or "solo" in which:
        b = launch(p, WAV / "wish.wav"); c = ctx(b, ARCH); pg = c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        check("speak a wish (mic -> transcript)", lambda: solo(pg, "", typed=False))
        def plan():
            cand = pg.evaluate("(()=>{const c=state.solo.candidates[state.chosen];const d=state.solo.places[c.destination_place_id];return {min:c.total_min,stops:(c.stops||[]).map(s=>s.name+' ('+s.category+')'),dest:d.name,cat:d.category,rat:c.rationale}})()")
            return cand
        check("route with time and stops", plan)
        pg.screenshot(path="/tmp/x.png") if False else None
        def start():
            pg.click(".start-walk"); pg.wait_for_selector(".walk-screen", timeout=30000); time.sleep(6)
            return {"bubble": pg.inner_text(".buddy-text"), "mic": pg.locator(".walk-mic").count(), "turn": pg.inner_text(".walk-screen")[:120]}
        check("start walking screen", start)
        print("errs", errs); b.close()
    if not which or "buddy" in which:
        for wavname, secs, key in (("coffee", 2.6, "coffee stop by voice"), ("shorter", 2.4, "shorter route by voice"), ("nearby", 2.0, "what's nearby by voice")):
            b = launch(p, WAV / f"{wavname}.wav"); c = ctx(b, ARCH); pg = c.new_page()
            def run():
                solo(pg, "30 minutes, quiet streets, ending at a park"); pg.click(".start-walk"); pg.wait_for_selector(".walk-screen", timeout=30000); time.sleep(6)
                before = pg.inner_text(".walk-screen")
                if pg.locator(".voice-toggle").count(): pg.click(".voice-toggle"); time.sleep(.5)
                hold(pg, secs)
                pg.wait_for_function("document.querySelector('.buddy-text').textContent.includes('“')||document.querySelector('.buddy-text').textContent.length>70", timeout=45000); time.sleep(5)
                return {"reply": pg.inner_text(".buddy-text"), "undo": pg.get_by_role("button", name="Undo").count(), "bar": pg.inner_text(".walk-screen")[-60:]}
            check(key, run); b.close()
    if not which or "pair" in which:
        b = launch(p, WAV / "wish.wav"); a = ctx(b, ARCH); pa = a.new_page()
        tok = {}
        def inv():
            pa.goto(SITE + "/new", wait_until="networkidle"); pa.click("#mode-pair"); pa.fill("#text", "30 minutes, coffee at the end"); pa.click("#parse")
            pa.wait_for_selector("#intent:not([hidden])", timeout=40000); pa.click("#locate"); pa.wait_for_function("!document.querySelector('#create').disabled", timeout=30000)
            lbl = pa.inner_text("#create"); pa.click("#create"); pa.wait_for_url("**/i/**", timeout=120000); tok["t"] = pa.url.split("/i/")[1].split("#")[0]
            return {"button": lbl, "url_shape": "/i/<token>"}
        check("invite link", inv)
        bb = ctx(b, UNION); pb = bb.new_page()
        def accept():
            pb.goto(f"{SITE}/i/{tok['t']}", wait_until="networkidle"); pb.get_by_role("button", name="Use my location").click(); time.sleep(1.5)
            pb.locator("textarea").first.fill("quiet streets"); pb.get_by_role("button", name="I'm in").click()
            pb.wait_for_function("document.querySelectorAll('#map path.leaflet-interactive').length >= 3", timeout=240000); time.sleep(3)
            return pb.inner_text("main")[:600]
        check("friend I'm in, no account", accept)
        def api():
            import urllib.request
            return json.loads(urllib.request.urlopen(f"{SITE}/api/invites/{tok['t']}").read())
        def fair():
            v = api(); Path("/private/tmp/claude-501/-Users-huzhuoyang-Desktop-meta-hacking/e23c59ac-91bd-4f79-be38-d001ca357176/scratchpad/invite_view.json").write_text(json.dumps(v)[:200000])
            return {"keys": list(v.keys())[:20]}
        check("fair meeting point data", fair)
        b.close()
print(json.dumps({k: v["ok"] for k, v in R.items()}, indent=1))
