"""A3: the warm-up script's real terminal output (video/assets/data/glimmer_warm_terminal.jsonl, each line with
the wall-clock time it was printed), replayed in a terminal window and recorded at 1920x1080.

Gaps longer than 3 s (the cold start) play 20x faster with a visible "sped up 20x" tag and an elapsed-time
counter, so the wait is shortened but never hidden. Text is the script's output, unchanged.
"""

import html
import json
import time

from playwright.sync_api import sync_playwright

from harness import ASSETS, DESKTOP, Recorder, launch

SPEED, GAP = 20, 3.0
rows = [json.loads(line) for line in (ASSETS / "data" / "glimmer_warm_terminal.jsonl").read_text().splitlines()]
# up to the second "warm" ping after the window opened
keep, warm = [], 0
for r in rows:
    keep.append(r)
    warm += " warm (" in r["line"]
    if warm >= 2:
        break
events, t, prev = [], 1.5, rows[0]["t"]
for r in keep:
    gap = r["t"] - prev
    fast = gap > GAP
    if fast:
        events.append({"at": t, "fast_from": round(gap, 1)})
        t += gap / SPEED
    else:
        t += gap
    events.append({"at": round(t, 2), "line": r["line"], "real_gap": round(gap, 1)})
    prev = r["t"]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#FBF7EF;display:grid;place-items:center;height:100vh;font-family:Menlo,monospace}
.win{width:1360px;height:700px;background:#1f1b2e;border-radius:18px;box-shadow:0 30px 60px rgba(43,35,64,.35);overflow:hidden}
.bar{height:44px;background:#2b2340;display:flex;align-items:center;gap:10px;padding:0 18px;color:#b9b2cc;font-size:15px}
.dot{width:13px;height:13px;border-radius:50%}
pre{margin:0;padding:26px 30px;color:#e9e6f2;font-size:21px;line-height:1.55;white-space:pre-wrap}
.cmd{color:#FFD970}.ok{color:#7be0a3}.tag{position:absolute;right:300px;bottom:150px;background:#FFD970;color:#2B2340;
font:700 18px system-ui;padding:8px 14px;border-radius:999px;display:none}
</style></head><body><div class="win"><div class="bar"><span class="dot" style="background:#ff6b6b"></span>
<span class="dot" style="background:#FFD970"></span><span class="dot" style="background:#22A35A"></span>
<span style="margin-left:12px">strollcall - zsh</span></div><pre id="out"><span class="cmd">$ python scripts/glimmer_warm.py --minutes 20</span>
</pre></div><div class="tag" id="tag"></div><script>
const EV = __EVENTS__; const out = document.getElementById('out'), tag = document.getElementById('tag');
let t0 = null, i = 0, fast = null; window.go = () => { t0 = performance.now(); };
function tick(){ if (t0 === null) return; const now = (performance.now() - t0) / 1000;
  while (i < EV.length && EV[i].at <= now) { const e = EV[i++];
    if (e.fast_from) { fast = {start: now, real: e.fast_from}; continue; }
    fast = null; tag.style.display = 'none';
    const s = document.createElement('span'); if (/READY|valid JSON|window open/.test(e.line)) s.className = 'ok';
    s.textContent = e.line + '\\n'; out.appendChild(s); }
  if (fast) { const el = Math.min((now - fast.start) * __SPEED__, fast.real);
    tag.style.display = 'block'; tag.textContent = 'sped up __SPEED__x · waiting ' + Math.floor(el) + ' s'; }
  }
setInterval(tick, 33);
</script></body></html>"""

page_html = PAGE.replace("__EVENTS__", json.dumps(events)).replace("__SPEED__", str(SPEED))
src = ASSETS / "data" / "terminal_replay.html"
src.write_text(page_html)

with sync_playwright() as p:
    br = launch(p, dsf=1.25)
    pg = br.new_context(**DESKTOP).new_page()
    pg.goto(src.as_uri())  # navigate first: a new origin would end the screencast
    time.sleep(1)
    rec = Recorder(pg, ASSETS / "screen" / "03_terminal_glimmer.mp4").start()
    pg.evaluate("go()")
    time.sleep(events[-1]["at"] + 3)
    print("A3", rec.stop()["duration_s"], "events", len(events))
    br.close()
print(html.escape(json.dumps([e for e in events if "line" in e], indent=0))[:1500])
