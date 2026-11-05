"""Real UI captures from the LOCAL app for the promo (390x844 at 2x). Start points are public places around
Washington Square Park. Writes clips, stills and map data to promo/public/ui/.   python record.py [solo walk pair]"""
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from harness import ROOT, SITE, Recorder, launch

UI = ROOT / "promo" / "public" / "ui"; UI.mkdir(parents=True, exist_ok=True)
WAV = ROOT / "promo" / "assets" / "wav"
ARCH = (40.7312, -73.9973); UNION = (40.7359, -73.9906)
PHONE = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
             user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
only = set(sys.argv[1:]) or {"solo", "walk", "pair"}
log = {}

def ctx(b, where):
    c = b.new_context(**PHONE, geolocation={"latitude": where[0], "longitude": where[1], "accuracy": 10}, permissions=["geolocation", "microphone"])
    c.add_init_script("try { localStorage.setItem('strollcall:voice', 'off'); } catch (e) {}")
    return c

def scroll_el(page, sel, top):
    page.evaluate("([s,t]) => window.scrollBy(0, document.querySelector(s).getBoundingClientRect().top - t)", [sel, top]); time.sleep(.8)

ROUTE_JS = """() => [...document.querySelectorAll('#map path.leaflet-interactive')].map(p => { const m = p.getScreenCTM(), n = p.getTotalLength(), pts = [];
  for (let i = 0; i <= 160; i++) { const q = p.getPointAtLength(n * i / 160); pts.push([+(q.x * m.a + m.e).toFixed(1), +(q.y * m.d + m.f).toFixed(1)]); }
  return { color: p.getAttribute('stroke'), pts }; })"""
HIDE = "#map .leaflet-overlay-pane{visibility:hidden!important}"

def solo_form(page, wish):
    page.fill("#text", wish); page.click("#parse"); page.wait_for_selector("#intent:not([hidden])", timeout=40000)
    page.click("#locate"); page.wait_for_function("!document.querySelector('#create').disabled", timeout=30000)
    page.click("#create"); page.wait_for_selector(".start-walk", timeout=120000); time.sleep(3)

with sync_playwright() as p:
    if "solo" in only:
        for take in range(1, 7):  # Chrome's fake mic plays once per launch, and a take can come back with a word doubled
            b = launch(p, WAV / "wish.wav", dsf=2); c = ctx(b, ARCH); pg = c.new_page()
            pg.goto(SITE + "/new", wait_until="networkidle"); pg.click("#mode-solo"); time.sleep(2)
            pg.screenshot(path=UI / "s3_new.png")
            rec = Recorder(pg, UI / "s3_speak.mp4").start(); time.sleep(1)
            mic = pg.get_by_role("button", name="Speak instead of typing"); rec.mark("tap"); mic.click(); time.sleep(4.2); mic.click(); rec.mark("stop")
            pg.wait_for_function("document.querySelector('#text').value.length > 5", timeout=60000); rec.mark("transcript"); time.sleep(2); rec.stop()
            log["transcript"] = pg.input_value("#text"); log["transcript_take"] = take; print(take, log["transcript"], flush=True)
            if re.fullmatch(r"(?i)(20|twenty) minutes,? quiet streets,? coffee at the end\.?", log["transcript"].strip()): break
            b.close()
        pg.screenshot(path=UI / "s3_typed.png")
        solo_form(pg, pg.input_value("#text"))
        log["solo"] = pg.evaluate("(()=>{const c=state.solo.candidates[state.chosen],d=state.solo.places[c.destination_place_id];return {min:c.total_min,km:c.leg?c.leg.distance_m/1000:null,dest:d.name,cat:d.category,stops:c.stops}})()")
        scroll_el(pg, "#map", 70)
        pg.screenshot(path=UI / "s3_plan.png")
        routes = pg.evaluate(ROUTE_JS)
        card = pg.locator(".start-walk").first.evaluate("e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
        st = pg.add_style_tag(content=HIDE); time.sleep(.3); pg.screenshot(path=UI / "s3_plan_noroute.png"); st.evaluate("e => e.remove()")
        (UI / "s3_plan.json").write_text(json.dumps({"routes": routes, "start_btn": card}))
        scroll_el(pg, ".start-walk", 560); time.sleep(.5)
        rec = Recorder(pg, UI / "s3_start.mp4").start(); time.sleep(1.2); rec.mark("tap"); pg.click(".start-walk")
        pg.wait_for_selector(".walk-screen", timeout=30000); time.sleep(5); rec.stop(); b.close()
    if "walk" in only:
        for take in range(1, 6):
            b = launch(p, WAV / "coffee.wav", dsf=2); c = ctx(b, ARCH); pg = c.new_page()
            pg.goto(SITE + "/new", wait_until="networkidle"); pg.click("#mode-solo"); solo_form(pg, "30 minutes, quiet streets, ending at a park")
            pg.click(".start-walk"); pg.wait_for_selector(".walk-screen", timeout=30000); time.sleep(11)
            pg.screenshot(path=UI / "s5_before.png")
            rec = Recorder(pg, UI / "s5_buddy.mp4").start(); time.sleep(1.5)
            bx = pg.locator(".walk-mic").bounding_box(); pos = [bx["x"] + bx["width"] / 2, bx["y"] + bx["height"] / 2]
            rec.mark("hold"); pg.mouse.move(*pos); pg.mouse.down(); time.sleep(2.6); pg.mouse.up(); rec.mark("let go")
            pg.get_by_role("button", name="Undo").wait_for(timeout=45000); rec.mark("reply"); time.sleep(5); meta = rec.stop()
            reply = pg.inner_text(".buddy-text"); pg.screenshot(path=UI / "s5_after.png")
            log["buddy"] = {"take": take, "reply": reply, "events": meta["events"], "mic": pos}; b.close()
            print(take, reply, flush=True)
            if "“Can we stop for a coffee?”" in reply: break
    if "pair" in only:
        b = launch(p, WAV / "wish.wav", dsf=2); a = ctx(b, ARCH); pa = a.new_page()
        pa.goto(SITE + "/new", wait_until="networkidle"); pa.click("#mode-pair"); pa.fill("#text", "30 minutes, coffee at the end"); pa.click("#parse")
        pa.wait_for_selector("#intent:not([hidden])", timeout=40000); pa.click("#locate"); pa.wait_for_function("!document.querySelector('#create').disabled", timeout=30000)
        scroll_el(pa, "#create", 620); pa.screenshot(path=UI / "s4_a_form.png")
        r = pa.locator("#create").evaluate("e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }"); log["invite_btn"] = r
        pa.click("#create"); pa.wait_for_url("**/i/**", timeout=120000); time.sleep(4); pa.evaluate("window.scrollTo(0,0)"); time.sleep(.5); pa.screenshot(path=UI / "s4_a_link.png")
        log["a_link_box"] = pa.evaluate("""() => { const t = [...document.querySelectorAll('*')].filter(e => e.children.length === 0 && /\\/i\\//.test(e.textContent || e.value || '')); const e = t[0] || document.querySelector('input,textarea'); const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }""")
        tok = pa.url.split("/i/")[1].split("#")[0]
        bb = ctx(b, UNION); pb = bb.new_page(); pb.goto(f"{SITE}/i/{tok}", wait_until="networkidle"); time.sleep(2)
        pb.screenshot(path=UI / "s4_b_join.png")
        pb.get_by_role("button", name="Use my location").click(); time.sleep(1.5); pb.locator("textarea").first.fill("quiet streets"); time.sleep(.5)
        pb.evaluate("window.scrollTo(0,0)"); time.sleep(.5); pb.screenshot(path=UI / "s4_b_ready.png")
        log["im_in_btn"] = pb.get_by_role("button", name="I'm in").evaluate("e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
        pb.get_by_role("button", name="I'm in").click()
        pb.wait_for_function("document.querySelectorAll('#map path.leaflet-interactive').length >= 3", timeout=240000); time.sleep(6)
        pb.evaluate("window.scrollTo(0,0)"); time.sleep(.5); pb.screenshot(path=UI / "s4_b_plan.png")
        v = pb.evaluate("fetch(location.pathname.replace('/i/','/api/invites/')).then(r=>r.json())"); cnd = v["candidates"][0]; pl = v["places"]
        log["pair"] = {"a": cnd["a_leg"]["duration_min"], "b": cnd["b_leg"]["duration_min"], "gap": cnd["arrival_gap_min"], "shared": cnd["shared_leg"]["duration_min"], "meet": pl[cnd["meeting_place_id"]]["name"], "dest": pl[cnd["endpoint_place_id"]]["name"]}
        # the same plan's real map, wide enough for the split screen: tiles only, the legs come out as pixels
        pb.set_viewport_size({"width": 860, "height": 700}); time.sleep(1)
        pb.add_style_tag(content="header,nav,.site-bar,.topbar,footer{display:none!important}")
        pb.evaluate("""([a,b,s]) => { const m = document.getElementById('map'); m.style.cssText += ';position:fixed;left:0;top:0;width:860px;height:700px;z-index:9999;margin:0;border-radius:0';
          map.invalidateSize(); map.fitBounds(L.latLngBounds([...a,...b,...s]), {padding:[50,50]}); }""", [cnd["a_leg"]["geometry"], cnd["b_leg"]["geometry"], cnd["shared_leg"]["geometry"]])
        time.sleep(4)
        px = pb.evaluate("""(ls) => ls.map(l => l.map(q => { const r = map.latLngToContainerPoint(q); return [+r.x.toFixed(1), +r.y.toFixed(1)]; }))""", [cnd["a_leg"]["geometry"], cnd["b_leg"]["geometry"], cnd["shared_leg"]["geometry"]])
        pb.add_style_tag(content="#map .leaflet-overlay-pane,#map .leaflet-marker-pane,#map .leaflet-shadow-pane,#map .leaflet-control-zoom{visibility:hidden!important}"); time.sleep(.4)
        pb.locator("#map").screenshot(path=UI / "s4_map.png")
        (UI / "s4_map.json").write_text(json.dumps({"size": [860, 700], "a": px[0], "b": px[1], "shared": px[2]}))
        b.close()
old = json.loads((UI / "record_log.json").read_text()) if (UI / "record_log.json").exists() else {}
old.update(log); log = old
(UI / "record_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
print(json.dumps(log, indent=1, ensure_ascii=False)[:1800])
