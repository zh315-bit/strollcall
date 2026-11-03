"""Painterly scene backgrounds for the demo video's illustrated scenes, made with Meta Muse Image (the same model
that draws the app's invite cards). No people, animals or characters: the two mascots are composited on top.

    python make_backgrounds.py            # missing pictures only
    python make_backgrounds.py --only s1_street

Each call goes through the app's spend guard (MetaProvider). Saves video/assets/art/<name>.png and records the
model, prompt, time, size and SHA-256 in video/assets/art/manifest.json.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["USE_MOCKS"] = "false"
os.chdir(ROOT / "backend")

from app.core.config import get_settings  # noqa: E402
from app.providers.meta import MetaProvider  # noqa: E402

OUT = ROOT / "video" / "assets" / "art"
STYLE = ("Richly detailed hand-painted anime background art, like a frame from a gentle animated film: soft painterly "
         "brushwork, warm natural light, gentle colours, clean shapes, depth and atmosphere. Wide 16:9 landscape "
         "composition. Absolutely no people, no animals, no characters, no text, no letters, no numbers, no logos, "
         "no signs with writing.")
PROMPTS = {
    "s1_street": "A sunny morning on a quiet New York brownstone street, seen from across the street at eye level. "
                 "A row of brownstones with stoops, cornices and window boxes; one green front door at street level "
                 "near the left third; street trees; a small corner cafe with a striped yellow awning on the right. "
                 "The empty sidewalk runs straight across the lower third of the picture. Blue sky with soft clouds.",
    "s2_room": "A cozy small apartment living room in the late afternoon, seen straight on. A soft lilac sofa with a "
               "folded blue blanket and cushions in the centre, facing the viewer, empty. A window behind it with a "
               "view of city rooftops, a floor lamp, a plant, a rug, warm light.",
    "s10_park": "Golden hour in a Manhattan park: a wide paved path runs straight across the lower third of the "
                "picture, lined with autumn trees, benches and old lamp posts; the city skyline glows beyond the "
                "trees; long soft shadows, falling leaves.",
    "s10_corner": "Golden hour at a quiet New York street corner seen from the middle of the street: two sidewalks meet "
                  "at a corner with a crosswalk in the foreground, brownstones and a corner building with warm windows, "
                  "street trees with autumn leaves, long soft shadows.",
    "s10_cafe": "Golden hour at a small sidewalk cafe terrace in New York: one small round table in the centre "
                "foreground with two coffee cups on it, two empty chairs on either side, a cafe window and striped "
                "awning behind, string lights, flower pots, warm glow.",
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*")
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    man_path = OUT / "manifest.json"
    man = json.loads(man_path.read_text()) if man_path.exists() else {"pictures": {}}
    man["note"] = "Backgrounds for the StrollCall demo video, generated with Meta Muse Image; no people or characters."
    meta = MetaProvider()
    for name, scene in PROMPTS.items():
        if args.only and name not in args.only:
            continue
        if not args.only and name in man["pictures"] and (OUT / f"{name}.png").exists():
            continue
        prompt = f"{scene} {STYLE}"
        raw = meta.generate_image(prompt)
        tmp = OUT / f"{name}.webp"
        tmp.write_bytes(raw)
        png = OUT / f"{name}.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(tmp), str(png)], check=True)
        tmp.unlink()
        dims = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(png)],
                              capture_output=True, text=True).stdout.strip()
        data = png.read_bytes()
        man["pictures"][name] = {"model": get_settings().image_model_id, "prompt": prompt, "size": dims,
                                 "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "sha256": hashlib.sha256(data).hexdigest()}
        man_path.write_text(json.dumps(man, indent=1))
        print(name, dims)
    return 0


if __name__ == "__main__":
    sys.exit(main())
