#!/usr/bin/env python3
"""
Luo Kulman kuvakkeen (kulma.png + kulma.ico) yhdistämällä emojit 📐 ja ☀️.

Emojikuvat ladataan Applen emoji-kuvakirjastosta (npm-paketti
emoji-datasource-apple@16.0.0, jsDelivr-CDN). Kuvat ovat Applen tekijänoikeudella
suojattuja, joten niitä EI ole tässä repossa: ne ladataan vasta tässä
skriptissä (asennuksen yhteydessä) käyttäjän omalle koneelle, ja tulos
tallennetaan repon ulkopuolelle: %LOCALAPPDATA%\\Kulma\\icon\\.

Lataus rajoittuu kahteen kiinteään tiedostoon, ja niiden SHA-256 tarkistetaan.
Sama kuvake toimii sekä tray-kuvakkeena että pikakuvakkeen kuvakkeena.

Käyttö:  python make_icon.py
"""

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

from PIL import Image

BASE = "https://cdn.jsdelivr.net/npm/emoji-datasource-apple@16.0.0/img/apple/64/"
FILES = {  # tiedosto -> SHA-256 (varmistaa että ladataan täsmälleen tämä kuva)
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
            data = r.read(200_000)  # kuvat ovat ~5 kt; yläraja varmuuden vuoksi
        digest = hashlib.sha256(data).hexdigest()
        if digest != FILES[name]:
            raise RuntimeError(f"{name}: odottamaton tiedosto (sha256 {digest})")
        path.write_bytes(data)
    return Image.open(path).convert("RGBA")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ruler = fetch("1f4d0.png").resize((int(SIZE * 0.82),) * 2, Image.LANCZOS)
    sun = fetch("2600-fe0f.png").resize((int(SIZE * 0.66),) * 2, Image.LANCZOS)

    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.alpha_composite(sun, (SIZE - sun.width, 0))            # aurinko oikeassa yläkulmassa (taustalla)
    icon.alpha_composite(ruler, (0, SIZE - ruler.height))       # kulmaviivain vasemmassa alakulmassa (edessä)

    icon.save(OUT / "kulma.png")
    icon.save(OUT / "kulma.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print(f"Kuvake luotu: {OUT / 'kulma.ico'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Kuvakkeen luonti epäonnistui: {e}", file=sys.stderr)
        sys.exit(1)
