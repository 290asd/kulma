#!/usr/bin/env python3
"""
kulma_wallpaper.py

Laskee auringon korkeuskulman JUURI NYT (config.jsonin sijainnille), ja
valitsee kuvaindeksistä kuvan jonka tallennettu aurinkokulma (kuvan
ottohetkellä) on lähimpänä nykyistä. Toimii täysin automaattisesti, ei
vaadi manuaalista säätöä käytön aikana.

Valintaperiaate:
  1. Lasketaan nykyinen aurinkokulma (elevation) ja atsimuutti (azimuth).
  2. Otetaan kaikki kuvat, joiden elevation on config.jsonin
     "elevation_tolerance"-arvon sisällä nykyisestä.
  3. Näistä valitaan satunnaisesti painotettuna niin, että lähempänä
     nykyistä kulmaa (ja atsimuuttia) olevat kuvat ovat todennäköisempiä.
  4. Jos yksikään kuva ei osu toleranssin sisään (esim. harva kuvamäärä),
     otetaan lähimmät ehdokkaat varajärjestelmänä - jokin kuva vaihtuu
     joka kerta, valinta ei koskaan jää tyhjäksi.
  5. Edellinen valinta suljetaan pois ehdokkaista ennen arvontaa, joten
     sama kuva ei voi tulla kahdesti peräkkäin - paitsi jos se on ainoa
     kelvollinen ehdokas.

Ajetaan systemd-timerin kautta (katso systemd/kulma.timer).
"""

import json
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import elevation, azimuth

CONFIG_PATH = Path.home() / ".config" / "kulma" / "config.json"
INDEX_PATH = Path.home() / ".config" / "kulma" / "index.json"
LOG_PATH = Path.home() / ".config" / "kulma" / "kulma.log"
LAST_CHOICE_PATH = Path.home() / ".config" / "kulma" / "last_choice.json"

FALLBACK_CANDIDATE_COUNT = 3  # jos mikään kuva ei osu toleranssiin


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_last_choice() -> str | None:
    try:
        with open(LAST_CHOICE_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("path")
    except Exception:
        return None


def write_last_choice(path: str):
    try:
        LAST_CHOICE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LAST_CHOICE_PATH, "w", encoding="utf-8") as f:
            json.dump({"path": path}, f)
    except Exception:
        pass


def circular_diff(a: float, b: float) -> float:
    """Pienin ero kahden atsimuuttikulman välillä (0-360 -asteikolla)."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def set_gnome_wallpaper(path: Path):
    uri = f"file://{path}"
    subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                     "picture-uri", uri], check=True)
    subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                     "picture-uri-dark", uri], check=False)
    subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                     "picture-options", "zoom"], check=False)


def main():
    if not CONFIG_PATH.exists():
        log(f"Virhe: config-tiedostoa ei löydy ({CONFIG_PATH}).")
        sys.exit(1)
    if not INDEX_PATH.exists():
        log(f"Virhe: indeksiä ei löydy ({INDEX_PATH}). Aja ensin kulma_index.py.")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    tz = ZoneInfo(config["timezone"])
    tolerance = config.get("elevation_tolerance", 6.0)
    az_weight = config.get("azimuth_weight", 0.05)

    now = datetime.now(tz)
    obs = Observer(latitude=config["latitude"], longitude=config["longitude"])
    current_elev = elevation(obs, now)
    current_az = azimuth(obs, now)

    # Vain kuvat jotka löytyvät levyltä
    records = [r for r in records if Path(r["path"]).exists()]
    if not records:
        log("Indeksissä ei ole yhtään olemassa olevaa kuvaa. Aja kulma_index.py uudelleen.")
        return

    def score(r):
        elev_diff = abs(r["sun_elevation"] - current_elev)
        az_diff = circular_diff(r["sun_azimuth"], current_az)
        return elev_diff + az_weight * az_diff, elev_diff

    scored = [(r, *score(r)) for r in records]
    # scored: (record, combined_score, elev_diff)

    within_tolerance = [t for t in scored if t[2] <= tolerance]

    if within_tolerance:
        candidates = within_tolerance
        mode = "toleranssin sisällä"
    else:
        # Varajärjestelmä: otetaan N lähintä koko indeksistä
        scored.sort(key=lambda t: t[1])
        candidates = scored[:FALLBACK_CANDIDATE_COUNT]
        mode = "fallback (lähimmät ehdokkaat)"

    # Estetään sama kuva kahdesti peräkkäin - suodatetaan edellinen valinta
    # pois, mutta vain jos jäljelle jää vielä vaihtoehtoja.
    last_choice = read_last_choice()
    if last_choice is not None:
        filtered = [t for t in candidates if t[0]["path"] != last_choice]
        if filtered:
            candidates = filtered
        else:
            log("Kaikki ehdokkaat olisivat sama kuin edellinen valinta - ei suodatettu pois.")

    # Painotettu satunnaisvalinta: mitä lähempänä, sitä todennäköisempi
    weights = [1.0 / (t[1] + 0.5) for t in candidates]
    chosen_record, chosen_score, chosen_elev_diff = random.choices(candidates, weights=weights, k=1)[0]
    chosen_path = Path(chosen_record["path"])

    try:
        set_gnome_wallpaper(chosen_path)
        write_last_choice(str(chosen_path))
        log(
            f"Aurinkokulma nyt: {current_elev:.1f}° (atsimuutti {current_az:.1f}°) | "
            f"valittu kuva: {chosen_path.name} (kuvan kulma {chosen_record['sun_elevation']:.1f}°, "
            f"ero {chosen_elev_diff:.1f}°) | {mode}, {len(candidates)} ehdokasta"
        )
    except subprocess.CalledProcessError as e:
        log(f"Virhe asetettaessa taustakuvaa: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
