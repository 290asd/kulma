#!/usr/bin/env python3
"""
kulma_index.py

Käy läpi kuvakansion (rekursiivisesti) ja laskee jokaiselle kuvalle
auringon korkeuskulman (elevation) ja atsimuutin (azimuth) sillä hetkellä
kun kuva on otettu (EXIF DateTimeOriginal).

Sijainti kuvalle:
  1. Jos kuvassa on GPS-EXIF (GPSLatitude/GPSLongitude), käytetään sitä.
  2. Muuten käytetään config.jsonin oletussijaintia.

Kellonaika tulkitaan config.jsonin aikavyöhykkeen mukaan (EXIF ei
yleensä sisällä aikavyöhykettä).

Tulos tallennetaan JSON-tiedostoon (index.json) litteänä listana:
[
  {
    "path": "/polku/kuva1.jpg",
    "capture_time": "2024-06-01T14:32:00+03:00",
    "hour": 14,
    "sun_elevation": 23.41,
    "sun_azimuth": 210.07,
    "gps": true,
    "time_source": "exif"
  },
  ...
]

Käyttö:
    python3 kulma_index.py [--config ~/.config/kulma/config.json]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from astral import Observer
from astral.sun import elevation, azimuth

from kulma_i18n import t as tr

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    print(tr("idx.warn_heif"), file=sys.stderr)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif"}

DATETIME_ORIGINAL_TAG = next((k for k, v in TAGS.items() if v == "DateTimeOriginal"), None)
DATETIME_TAG = next((k for k, v in TAGS.items() if v == "DateTime"), None)

# IFD-pointterit ("get_ifd"-avaimet) - näiden alle EXIF- ja GPS-tiedot on
# pakattu Pillow'n nykyisessä rajapinnassa (koskee sekä JPEG:iä että
# HEIC/HEIF:iä pillow-heif:in kautta). Vanha yksityinen _getexif() ei
# toimi HEIC:in kanssa lainkaan.
EXIF_IFD_POINTER = 0x8769   # "Exif IFD"
GPS_IFD_POINTER = 0x8825    # "GPS IFD"

def _config_root() -> Path:
    """Kulman asetuskansio - käyttöjärjestelmäkohtainen.

    Linux/macOS: ~/.config/kulma  (XDG-käytäntö)
    Windows:     %APPDATA%\\Kulma  (esim. C:\\Users\\nimi\\AppData\\Roaming\\Kulma)
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Kulma"
    return Path.home() / ".config" / "kulma"


DEFAULT_CONFIG_PATH = _config_root() / "config.json"
DEFAULT_INDEX_PATH = _config_root() / "index.json"
OVERRIDES_PATH = _config_root() / "overrides.json"


def load_overrides() -> dict:
    """Käyttäjän käsin antamat tiedot kuville, joilta EXIF puuttuu.

    Muoto: {kuvan polku: {"lat": .., "lon": .., "capture_time": "VVVV-KK-PPTHH:MM:SS"}}
    Kuvatiedostoja ei muokata.
    """
    try:
        with open(OVERRIDES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        print(tr("idx.err_config", path=config_path), file=sys.stderr)
        print(tr("idx.err_config_hint"), file=sys.stderr)
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _dms_to_decimal(dms, ref) -> float:
    degrees, minutes, seconds = dms
    value = float(degrees) + float(minutes) / 60.0 + float(seconds) / 3600.0
    if ref in ("S", "W"):
        value = -value
    return value


def get_exif_data(path: Path):
    """Palauttaa (capture_dt: datetime|None, lat: float|None, lon: float|None).

    Käyttää Pillow'n julkista getexif()/get_ifd()-rajapintaa, joka toimii
    yhtenäisesti sekä JPEG- että HEIC/HEIF-kuville.
    """
    capture_dt = None
    lat = lon = None
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None, None, None

            exif_ifd = exif.get_ifd(EXIF_IFD_POINTER)
            if DATETIME_ORIGINAL_TAG in exif_ifd:
                raw = exif_ifd[DATETIME_ORIGINAL_TAG]
                try:
                    capture_dt = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass

            # Joskus ottoaika löytyy vain "top level" IFD:stä (tag 306,
            # "DateTime") HEIC:eissä joissa ei ole erillistä Exif-IFD:tä
            if capture_dt is None and DATETIME_ORIGINAL_TAG in exif:
                raw = exif[DATETIME_ORIGINAL_TAG]
                try:
                    capture_dt = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass

            # Jotkin kamerat (esim. osa Android-puhelimista) eivät tallenna
            # "DateTimeOriginal"-tagia lainkaan, vain yleisen "DateTime"-tagin
            # (306) top-level IFD:ssä. Käytetään sitä viimeisenä yrityksenä
            # ennen tiedoston muokkausaikaan turvautumista.
            if capture_dt is None and DATETIME_TAG in exif:
                raw = exif[DATETIME_TAG]
                try:
                    capture_dt = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass

            gps_ifd = exif.get_ifd(GPS_IFD_POINTER)
            if gps_ifd:
                gps = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
                try:
                    if "GPSLatitude" in gps and "GPSLongitude" in gps:
                        lat = _dms_to_decimal(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
                        lon = _dms_to_decimal(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))
                except Exception:
                    lat = lon = None
    except Exception:
        pass
    return capture_dt, lat, lon


def main():
    parser = argparse.ArgumentParser(description="Indeksoi kuvat aurinkokulman mukaan (Kulma)")
    parser.add_argument("photo_dir", type=str, nargs="?", default=None,
                         help="Kuvakansio (oletus: config.jsonin photo_dir)")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--out", type=str, default=str(DEFAULT_INDEX_PATH))
    args = parser.parse_args()

    config = load_config(Path(args.config).expanduser())
    photo_dir = Path(args.photo_dir or config["photo_dir"]).expanduser().resolve()
    if not photo_dir.is_dir():
        print(tr("idx.err_folder", path=photo_dir), file=sys.stderr)
        sys.exit(1)

    tz = ZoneInfo(config["timezone"])
    default_lat = config["latitude"]
    default_lon = config["longitude"]

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = [p for p in photo_dir.rglob("*") if p.suffix.lower() in IMAGE_EXTENSIONS]
    print(tr("idx.found", n=len(files), dir=photo_dir))

    records = []
    skipped = 0
    mtime_fallback_files = []
    overrides = load_overrides()

    for i, path in enumerate(files, 1):
        capture_dt, lat, lon = get_exif_data(path)
        ov = overrides.get(str(path), {})
        if "lat" in ov and "lon" in ov:
            lat, lon = ov["lat"], ov["lon"]

        exif_source = "exif"
        if "capture_time" in ov:
            capture_dt, exif_source = datetime.fromisoformat(ov["capture_time"]), "manual"
        if capture_dt is None:
            # Ei EXIF-aikaa (tai kuvaa ei voitu avata) -> käytetään
            # tiedoston muokkausaikaa varalla. Tämä EI vastaa ottohetkeä,
            # joten merkitään selvästi ja varoitetaan lopuksi.
            capture_dt = datetime.fromtimestamp(path.stat().st_mtime)
            exif_source = "mtime_fallback"
            mtime_fallback_files.append(path)

        has_gps = lat is not None and lon is not None
        if not has_gps:
            lat, lon = default_lat, default_lon

        capture_dt_local = capture_dt.replace(tzinfo=tz)

        try:
            obs = Observer(latitude=lat, longitude=lon)
            elev = elevation(obs, capture_dt_local)
            az = azimuth(obs, capture_dt_local)
        except Exception:
            skipped += 1
            continue

        records.append({
            "path": str(path),
            "capture_time": capture_dt_local.isoformat(),
            "hour": capture_dt_local.hour,
            "sun_elevation": round(elev, 2),
            "sun_azimuth": round(az, 2),
            "gps": has_gps,
            **({"lat": round(lat, 5), "lon": round(lon, 5)} if has_gps else {}),
            "time_source": exif_source,
        })

        if i % 200 == 0:
            print(tr("idx.progress", i=i, n=len(files)))

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print("\n" + tr("idx.done", path=out_path))
    print(tr("idx.indexed", n=len(records), skipped=skipped))
    gps_count = sum(1 for r in records if r["gps"])
    print(tr("idx.gps_count", gps=gps_count, n=len(records)))
    if records:
        elevations = [r["sun_elevation"] for r in records]
        print(tr("idx.range", lo=min(elevations), hi=max(elevations)))

    if mtime_fallback_files:
        print("\n" + tr("idx.warn_mtime", n=len(mtime_fallback_files)))
        print(tr("idx.examples"))
        for p in mtime_fallback_files[:10]:
            print(f"  - {p}")
        if len(mtime_fallback_files) > 10:
            print(tr("idx.and_more", n=len(mtime_fallback_files) - 10))
        print(tr("idx.heif_hint"))


if __name__ == "__main__":
    main()
