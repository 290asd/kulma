#!/usr/bin/env python3
"""
kulma_index.py

Walks through the photo folder (recursively) and calculates, for every photo,
the sun elevation and azimuth at the moment the photo was taken (EXIF
DateTimeOriginal).

Location of a photo:
  1. If the photo has GPS EXIF (GPSLatitude/GPSLongitude), that is used.
  2. Otherwise the default location from config.json is used.

The time is interpreted in the time zone from config.json (EXIF normally
does not contain a time zone).

Values entered by hand (overrides.json, see load_overrides) take precedence
over EXIF data.

The result is saved as a flat list in a JSON file (index.json):
[
  {
    "path": "/path/photo1.jpg",
    "capture_time": "2024-06-01T14:32:00+03:00",
    "hour": 14,
    "sun_elevation": 23.41,
    "sun_azimuth": 210.07,
    "gps": true,
    "lat": 60.17,
    "lon": 24.94,
    "time_source": "exif"        # "exif", "manual" or "mtime_fallback"
  },
  ...
]

Usage:
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

# IFD pointers ("get_ifd" keys) - the EXIF and GPS data are packed under these
# in Pillow's current API (applies to both JPEG and, via pillow-heif,
# HEIC/HEIF). The old private _getexif() does not work with HEIC at all.
EXIF_IFD_POINTER = 0x8769   # "Exif IFD"
GPS_IFD_POINTER = 0x8825    # "GPS IFD"

def _config_root() -> Path:
    """Kulma's settings folder - depends on the operating system.

    Linux/macOS: ~/.config/kulma  (XDG convention)
    Windows:     %APPDATA%\\Kulma  (e.g. C:\\Users\\name\\AppData\\Roaming\\Kulma)
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Kulma"
    return Path.home() / ".config" / "kulma"


DEFAULT_CONFIG_PATH = _config_root() / "config.json"
DEFAULT_INDEX_PATH = _config_root() / "index.json"
OVERRIDES_PATH = _config_root() / "overrides.json"


def load_overrides() -> dict:
    """Details entered by hand for photos that lack EXIF data.

    Format: {photo path: {"lat": .., "lon": .., "capture_time": "YYYY-MM-DDTHH:MM:SS"}}
    The photo files themselves are never modified.
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
    """Returns (capture_dt: datetime|None, lat: float|None, lon: float|None).

    Uses Pillow's public getexif()/get_ifd() API, which works the same way
    for both JPEG and HEIC/HEIF photos.
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

            # Sometimes the capture time is only found in the "top level" IFD
            # (tag 306, "DateTime") in HEIC files that have no separate Exif IFD
            if capture_dt is None and DATETIME_ORIGINAL_TAG in exif:
                raw = exif[DATETIME_ORIGINAL_TAG]
                try:
                    capture_dt = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass

            # Some cameras (e.g. some Android phones) do not store the
            # "DateTimeOriginal" tag at all, only the generic "DateTime" tag
            # (306) in the top-level IFD. Use it as a last attempt before
            # falling back to the file modification time.
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
    parser = argparse.ArgumentParser(description="Index photos by sun angle (Kulma)")
    parser.add_argument("photo_dir", type=str, nargs="?", default=None,
                         help="Photo folder (default: photo_dir from config.json)")
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
            # No EXIF time (or the photo could not be opened) -> fall back to
            # the file modification time. This does NOT match the capture
            # moment, so it is marked clearly and a warning is printed at the end.
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
