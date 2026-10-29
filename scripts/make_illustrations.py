"""Generate the 24 invite-card illustrations with Muse Image (run once, locally).

    python scripts/make_illustrations.py            # missing pictures only
    python scripts/make_illustrations.py --dry-run  # print the prompts, no calls

One picture per theme (4 scenes x 6 endings, app/services/invite_card.py). Each call goes through
the spend guard. The image is shrunk to 768 px JPEG with macOS `sips` and saved to
frontend/illustrations/<scene>-<ending>.jpg; frontend/illustrations/manifest.json records the
model, the exact prompt, the time, and the file's size and SHA-256. Stops after 3 failures in a row.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

os.environ["USE_MOCKS"] = "false"

from _common import ROOT  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.errors import ProviderError  # noqa: E402
from app.providers.meta import MetaProvider  # noqa: E402
from app.services.invite_card import ENDINGS, ILLUSTRATIONS_DIR, SCENES, illustration_file, theme_prompt  # noqa: E402

MANIFEST = ILLUSTRATIONS_DIR / "manifest.json"
MAX_SIDE = 768


def shrink(raw: bytes, out_path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.img")
        with open(src, "wb") as f:
            f.write(raw)
        subprocess.run(["sips", "-Z", str(MAX_SIDE), "-s", "format", "jpeg", "-s", "formatOptions", "82",
                        src, "--out", str(out_path)], check=True, capture_output=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    ILLUSTRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"pictures": {}}
    manifest["note"] = ("Invite-card illustrations generated with Meta Muse Image for StrollCall; "
                        "one per theme, picked by app/services/invite_card.py.")
    model = get_settings().image_model_id
    meta = None if args.dry_run else MetaProvider()
    failures = 0
    for scene in SCENES:
        for ending in ENDINGS:
            name = illustration_file(scene, ending)
            if name in manifest["pictures"] and (ILLUSTRATIONS_DIR / name).exists():
                continue
            prompt = theme_prompt(scene, ending)
            if args.dry_run:
                print(f"{name}: {prompt}")
                continue
            try:
                raw = meta.generate_image(prompt)
            except ProviderError as e:
                failures += 1
                print(f"FAIL {name}: {e.message}")
                if failures >= 3:
                    print("3 failures in a row; stopping")
                    break
                continue
            failures = 0
            shrink(raw, ILLUSTRATIONS_DIR / name)
            data = (ILLUSTRATIONS_DIR / name).read_bytes()
            manifest["pictures"][name] = {
                "scene": scene, "ending": ending, "model": model, "prompt": prompt,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "processing": f"resized to max {MAX_SIDE} px, JPEG quality 82 (sips)",
            }
            MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")  # after each picture
            print(f"ok   {name} ({len(raw)} -> {len(data)} bytes)")
        else:
            continue
        break
    done = sum((ILLUSTRATIONS_DIR / illustration_file(s, e)).exists() for s in SCENES for e in ENDINGS)
    print(f"{done}/24 pictures present")
    return 0 if done == 24 or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
