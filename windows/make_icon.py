#!/usr/bin/env python3
"""
Creates Kulma's icon (kulma.png + kulma.ico) by combining the emojis 📐 and ☀️.

The emoji images are downloaded from Apple's emoji image library (npm package
emoji-datasource-apple@16.0.0, jsDelivr CDN). The images are copyrighted by
Apple, so they are NOT in this repository: they are downloaded only by this
script (at install time) onto the user's own machine, and the result is
stored outside the repo: %LOCALAPPDATA%\\Kulma\\icon\\.

The download is limited to two fixed files, and their SHA-256 is verified.
The same icon serves as both the tray icon and the shortcut icon.

Usage:  python make_icon.py
"""

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

from PIL import Image

BASE = "https://cdn.jsdelivr.net/npm/emoji-datasource-apple@16.0.0/img/apple/64/"
FILES = {  # file -> SHA-256 (makes sure exactly this image is downloaded)
    "1f4d0.png": "76b51ced659432675b8b85f8a25c78355a87b29937e4dead2e40a688834d766f",       # 📐
    "2600-fe0f.png": "861c678f805c77cfd22af8424bb5e1a894f0ba303574706d09ae734eec6da1c3",     # ☀️
}
OUT = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Kulma" / "icon"
SIZE = 256


def fetch(name: str) -> Image.Image:
    path = OUT / name
    if not path.exists():
        req = urllib.request.Request(BASE + name, headers={"User-Agent": "Kulma-icon/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read(200_000)  # the images are ~5 kB; upper limit for safety
        digest = hashlib.sha256(data).hexdigest()
        if digest != FILES[name]:
            raise RuntimeError(f"{name}: unexpected file (sha256 {digest})")
        path.write_bytes(data)
    return Image.open(path).convert("RGBA")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ruler = fetch("1f4d0.png").resize((int(SIZE * 0.82),) * 2, Image.LANCZOS)
    sun = fetch("2600-fe0f.png").resize((int(SIZE * 0.66),) * 2, Image.LANCZOS)

    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.alpha_composite(sun, (SIZE - sun.width, 0))            # sun in the top right corner (behind)
    icon.alpha_composite(ruler, (0, SIZE - ruler.height))       # set square in the bottom left corner (in front)

    icon.save(OUT / "kulma.png")
    icon.save(OUT / "kulma.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print(f"Icon created: {OUT / 'kulma.ico'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Creating the icon failed: {e}", file=sys.stderr)
        sys.exit(1)
