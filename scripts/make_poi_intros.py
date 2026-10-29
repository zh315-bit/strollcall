"""Sourced intros for points of interest on walks (run locally, ahead of time; no Meta calls at runtime).

    python scripts/make_poi_intros.py              # all POIs with a wikipedia/wikidata tag, resumable
    python scripts/make_poi_intros.py --limit 20   # a sample

For each POI in deploy/data/nyc_pois.json.gz with an OSM wikipedia or wikidata tag:
1. find its English Wikipedia article (the wikipedia tag, or the wikidata item's enwiki link) and
   fetch the article summary (REST API; cached in cache/wikipedia/);
2. skip it when the article title shares no word with the place's name (the tag may point at the
   person a statue depicts, not the statue);
3. ask Muse Spark to rewrite the summary in at most 2 sentences using only facts in it;
4. drop the intro if the fact check (services/grounding.intro_problems) finds anything not in the
   source: a number, a name, a place feature, praise, an unverifiable claim.
Places without a source show only their name and category. Output: frontend/data/poi_intros.json
with the model, the exact prompt, and per intro the source title, URL, revision and license
(Wikipedia text is CC BY-SA 4.0; the rewrites are shared under the same license). A report of
kept and dropped intros goes to benchmarks/.
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

os.environ["USE_MOCKS"] = "false"

import gzip  # noqa: E402

import httpx  # noqa: E402
from _common import ROOT  # noqa: E402

from app.core.budget import SpendGuard  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.errors import ProviderError  # noqa: E402
from app.providers.meta import MetaProvider  # noqa: E402
from app.services.grounding import intro_problems  # noqa: E402

POIS = ROOT / "deploy" / "data" / "nyc_pois.json.gz"
OUT = ROOT / "frontend" / "data" / "poi_intros.json"
CACHE = ROOT / "cache" / "wikipedia"
# Wikimedia's User-Agent policy wants a way to reach the operator: the project's public repo.
UA = {"User-Agent": "StrollCall/0.1 (https://github.com/zh315-bit/strollcall; hackathon prototype, one-off intro build)"}
LICENSE = {"name": "CC BY-SA 4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/"}
STOP = {"the", "of", "and", "park", "new", "york", "city", "a", "at", "in", "on", "memorial", "st", "street"}

PROMPT = """You write a short introduction to a place for someone walking past it, from a source text.

Rules:
- At most 2 short sentences and at most 280 characters, in English.
- Use only facts stated in the source text. Add nothing: no opinions or praise, no directions,
  nothing about what it looks like today, opening hours, safety, crowds or noise.
- Keep names, dates and numbers exactly as written in the source.
- If the source is not about this place, return an empty string.
Return only JSON matching the schema."""
SCHEMA = {"type": "object", "properties": {"intro": {"type": "string"}}, "required": ["intro"],
          "additionalProperties": False}


def get_json(url: str, cache_name: str | None = None) -> dict | None:
    if cache_name:
        path = CACHE / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', cache_name)[:150]}.json"
        if path.exists():
            return json.loads(path.read_text())
    for attempt in range(3):
        try:
            r = httpx.get(url, headers=UA, timeout=30, follow_redirects=True)
            if r.status_code == 404:
                data = None
                break
            if r.status_code == 200:
                data = r.json()
                break
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(2 * 2 ** attempt)
    else:
        return None
    if cache_name:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    return data


def enwiki_titles(pois: list[dict]) -> dict[str, str]:
    """POI id -> English Wikipedia title."""
    titles, need = {}, {}
    for p in pois:
        tag = p.get("wikipedia") or ""
        if tag.startswith("en:"):
            titles[p["id"]] = tag[3:]
        elif p.get("wikidata"):
            need.setdefault(p["wikidata"], []).append(p["id"])
    qids = list(need)
    for i in range(0, len(qids), 50):
        batch = "|".join(qids[i:i + 50])
        d = get_json(f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={batch}&props=sitelinks"
                     f"&sitefilter=enwiki&format=json", f"wd_{qids[i]}_{len(qids[i:i + 50])}") or {}
        for qid, ent in d.get("entities", {}).items():
            title = ent.get("sitelinks", {}).get("enwiki", {}).get("title")
            if title:
                for pid in need.get(qid, []):
                    titles[pid] = title
    return titles


def summary(title: str) -> dict | None:
    return get_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe='')}",
                    f"sum_{title}")


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) > 2}


def make_one(meta: MetaProvider, p: dict, title: str) -> tuple[str, dict]:
    """('kept' | reason, record)."""
    s = summary(title)
    if not s or s.get("type") == "disambiguation" or not s.get("extract"):
        return "no usable summary", {}
    if not words(p["name"]) & words(s.get("title", "")) and not words(p["name"]) & words(s["extract"][:200]):
        return "article may not be about this place", {"source_title": s.get("title")}
    user = json.dumps({"place": p["name"], "category": p["category"], "source_text": s["extract"]})
    try:
        intro = str(meta.structured_json(PROMPT, user, SCHEMA, name="poi_intro").get("intro", "")).strip()
    except ProviderError as e:
        return f"model error: {e.code}", {}
    rec = {"intro": intro, "source_title": s.get("title"),
           "source_url": (s.get("content_urls") or {}).get("desktop", {}).get("page"),
           "revision": s.get("revision"), "source_timestamp": s.get("timestamp"),
           "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not intro:
        return "model said the source is not about this place", rec
    problems = intro_problems(intro, s["extract"], p["name"])
    if problems:
        return "fact check: " + "; ".join(problems), rec
    return "kept", rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    with gzip.open(POIS, "rt") as f:
        pois = [p for p in json.load(f)["pois"] if p.get("wikipedia") or p.get("wikidata")]
    out = json.loads(OUT.read_text()) if OUT.exists() else {"intros": {}, "dropped": {}}
    out.update({"model": get_settings().model_id, "prompt": PROMPT, "license": LICENSE,
                "note": "Rewritten by Meta Muse Spark from the English Wikipedia summary of each place, using only "
                        "facts in that text, then fact-checked; intros that failed the check were dropped."})
    titles = enwiki_titles(pois)
    todo = [p for p in pois if p["id"] in titles and p["id"] not in out["intros"]
            and not str(out["dropped"].get(p["id"], {}).get("reason", "")).startswith(("fact check", "article", "model said"))]
    if args.limit:
        todo = todo[:args.limit]
    guard = SpendGuard()
    spent0 = guard.today_total()
    print(f"{len(pois)} POIs with a tag, {len(titles)} with an English article, {len(todo)} to do; "
          f"spend today ${spent0:.4f} of ${guard.daily_cap:.2f}")
    meta = MetaProvider()
    stats: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for p, (status, rec) in zip(todo, ex.map(lambda p: make_one(meta, p, titles[p["id"]]), todo)):
            key = status.split(":")[0]
            stats[key] = stats.get(key, 0) + 1
            if status == "kept":
                out["intros"][p["id"]] = {"name": p["name"], **rec}
                out["dropped"].pop(p["id"], None)
            else:
                out["dropped"][p["id"]] = {"name": p["name"], "reason": status, **rec}
    out["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"this run: {stats}; total kept {len(out['intros'])}, dropped {len(out['dropped'])}; "
          f"Meta spend ${guard.today_total() - spent0:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
