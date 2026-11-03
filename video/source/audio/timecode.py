"""Draw HH:MM:SS:FF (30 fps) in the top-right corner of every frame: python timecode.py IN_DIR OUT_DIR"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.mkdir(exist_ok=True)
font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
for f in sorted(src.glob("*.jpg")):
    i = int(f.stem)
    s = i // 30
    tc = f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{i % 30:02d}"
    im = Image.open(f).convert("RGB")
    d = ImageDraw.Draw(im)
    w = d.textlength(tc, font=font)
    d.rectangle([im.width - w - 28, 8, im.width - 8, 42], fill=(20, 18, 30))
    d.text((im.width - w - 18, 12), tc, font=font, fill=(255, 255, 255))
    im.save(dst / f.name, quality=92)
