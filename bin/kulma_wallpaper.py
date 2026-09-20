#!/usr/bin/env python3
"""
kulma_wallpaper.py

Laskee auringon korkeuskulman JUURI NYT (config.jsonin sijainnille), ja
valitsee kuvaindeksistä kuvan jonka tallennettu aurinkokulma (kuvan
ottohetkellä) on lähimpänä nykyistä. Toimii täysin automaattisesti, ei
vaadi manuaalista säätöä käytön aikana.

Valintaperiaate:
  1. Lasketaan nykyinen aurinkokulma (elevation) ja atsimuutti (azimuth).
  2. Otetaan kaikki kuvat, joiden elevation on toleranssin sisällä
     nykyisestä. Toleranssi on tiukempi ("twilight_elevation_tolerance")
     kun ollaan lähellä horisonttia ("twilight_band" astetta nollasta),
     koska valon voimakkuus muuttuu siellä nopeasti asteen kohden -
     ilman tätä yöllä saattaisi valikoitua selvästi kirkkaampia
     päiväkuvia vaikka numeerinen ero olisi pieni.
  3. Näistä valitaan satunnaisesti painotettuna niin, että lähempänä
     nykyistä kulmaa (ja atsimuuttia) olevat kuvat ovat todennäköisempiä.
     Painotus on neliöllinen (ei lineaarinen), joten kaukaisemmat mutta
     silti toleranssin sisällä olevat kuvat valikoituvat vain harvoin -
     tämä estää sen että valinta tuntuisi "satunnaiselta" vaikka teknisesti
     kelvollisia mutta selvästi huonompia ehdokkaita olisi joukossa.
  4. Jos yksikään kuva ei osu toleranssin sisään (esim. harva kuvamäärä),
     otetaan lähimmät ehdokkaat varajärjestelmänä - jokin kuva vaihtuu
     joka kerta, valinta ei koskaan jää tyhjäksi.
  5. Ehdokkaita kierrätetään: jo näytetyt kuvat suljetaan pois kunnes kaikki
     nykyiset ehdokkaat on käyty läpi, minkä jälkeen alkaa uusi kierros.
     Edellinen kuva ei voi tulla kahdesti peräkkäin; jos ainoa ehdokas on jo
     käytössä, haetaan lähimmät muut kuvat, jotta vaihto onnistuu aina.

Ajetaan ajastettuna: Linuxilla systemd-timerin kautta (katso
systemd/kulma.timer), Windowsilla Task Schedulerin kautta (katso
windows/install.ps1).
"""

import ctypes
import json
import os
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

from astral import Observer
from astral.sun import elevation, azimuth

from kulma_i18n import t as tr

def _config_root() -> Path:
    """Kulman asetuskansio - käyttöjärjestelmäkohtainen.

    Linux/macOS: ~/.config/kulma
    Windows:     %APPDATA%\\Kulma
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Kulma"
    return Path.home() / ".config" / "kulma"


def _cache_root() -> Path:
    """Kulman välimuistikansio (HEIC->JPEG-muunnokset) - käyttöjärjestelmäkohtainen.

    Linux/macOS: ~/.cache/kulma
    Windows:     %LOCALAPPDATA%\\Kulma\\cache
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Kulma" / "cache"
    return Path.home() / ".cache" / "kulma"


CONFIG_PATH = _config_root() / "config.json"
INDEX_PATH = _config_root() / "index.json"
LOG_PATH = _config_root() / "kulma.log"
LAST_CHOICE_PATH = _config_root() / "last_choice.json"
CONVERTED_CACHE_DIR = _cache_root() / "converted"

HEIC_EXTENSIONS = {".heic", ".heif"}
FALLBACK_CANDIDATE_COUNT = 3  # jos mikään kuva ei osu toleranssiin
HISTORY_LIMIT = 500           # kierroshistorian enimmäispituus


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


def read_history() -> list[str]:
    """Nykyisellä "kierroksella" jo näytetyt kuvat (ks. main())."""
    try:
        with open(LAST_CHOICE_PATH, "r", encoding="utf-8") as f:
            return list(json.load(f).get("history", []))
    except Exception:
        return []


def write_last_choice(path: str, history: list[str] | None = None):
    try:
        LAST_CHOICE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LAST_CHOICE_PATH, "w", encoding="utf-8") as f:
            json.dump({"path": path, "history": history or []}, f)
    except Exception:
        pass


def circular_diff(a: float, b: float) -> float:
    """Pienin ero kahden atsimuuttikulman välillä (0-360 -asteikolla)."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def get_display_path(path: Path) -> Path:
    """Palauttaa polun jota käyttöjärjestelmä voi käyttää taustakuvana.

    Sekä GNOME:n taustakuvan renderöinti (gdk-pixbuf) että Windowsin
    SystemParametersInfoW eivät tue HEIC/HEIF-formaattia (Linuxilla
    puuttuu patenttisyistä oletusasennuksesta, Windowsilla API ei tue
    sitä lainkaan), vaikka tämä skripti itse pystyy lukemaan
    HEIC-tiedostojen EXIF-datan pillow-heif:in kautta. Jos HEIC-polku
    annettaisiin suoraan, komento "onnistuu" mutta työpöytä ei näytä
    mitään uutta - jää vanhaan kuvaan kiinni.

    Siksi HEIC/HEIF-kuvat muunnetaan JPEG-välimuistiin ennen taustakuvaksi
    asettamista. Muunnos tehdään vain kerran per kuva (välimuistitiedosto
    nimetään alkuperäisen mukaan) - toistuvilla ajoilla käytetään jo
    muunnettua tiedostoa.
    """
    if path.suffix.lower() not in HEIC_EXTENSIONS:
        return path

    CONVERTED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CONVERTED_CACHE_DIR / f"{path.stem}.jpg"

    if cached.exists() and cached.stat().st_mtime >= path.stat().st_mtime:
        return cached

    with Image.open(path) as img:
        img.convert("RGB").save(cached, "JPEG", quality=92)

    return cached


def set_gnome_wallpaper(path: Path):
    """Asettaa GNOME-taustakuvan ja pakottaa uudelleenpiirron.

    Tunnettu GNOME Shell -kummallisuus: pelkkä "gsettings set picture-uri"
    ei aina pakota näkyvää taustakuvaa päivittymään heti - GNOME Shell voi
    jäädä näyttämään vanhaa, jo piirrettyä taustakuvaa kunnes jokin muu
    tapahtuma (esim. virtuaalityöpöydän vaihto) pakottaa sen rakentamaan
    taustakuva-actorin uudelleen. Syynä on todennäköisesti se, että
    "picture-options" pysyy samana arvona joka ajolla ("zoom" -> "zoom"),
    jolloin dconf ei laukaise muutossignaalia sille eikä GNOME Shell näin
    ollen aina rekonstruoi taustaa kokonaan pelkän URI-muutoksen takia.

    Korjataan pakottamalla picture-options vaihtumaan välillä eri arvoon
    ja takaisin joka ajolla - tämä laukaisee aidon "changed"-signaalin ja
    saa GNOME Shellin rakentamaan taustan uudelleen luotettavammin.
    """
    uri = f"file://{path}"
    bg = "org.gnome.desktop.background"

    # Pakotetaan aito muutossignaali vaihtamalla options ensin toiseen
    # arvoon - jos edellinen ajo jätti sen jo "none"-tilaan, tämä ei
    # haittaa, seuraava rivi asettaa lopullisen arvon joka tapauksessa.
    subprocess.run(["gsettings", "set", bg, "picture-options", "none"], check=False)
    subprocess.run(["gsettings", "set", bg, "picture-uri", uri], check=True)
    subprocess.run(["gsettings", "set", bg, "picture-uri-dark", uri], check=False)
    subprocess.run(["gsettings", "set", bg, "picture-options", "zoom"], check=False)


def set_windows_wallpaper(path: Path):
    """Asettaa Windows-taustakuvan SystemParametersInfoW-Win32-kutsulla.

    Tämä on Windowsin virallinen tapa vaihtaa taustakuva (sama mekanismi
    jota mm. Asetukset-sovellus käyttää) - ei erillistä daemonia tai
    komentoriviohjelmaa tarvita, toisin kuin GNOME:n gsettings-mallissa.

    SPI_SETDESKWALLPAPER (20) yhdistettynä SPIF_UPDATEINIFILE:iin (1)
    kirjoittaa polun myös käyttäjäprofiiliin, jotta valinta säilyy
    uudelleenkäynnistyksen yli, ja SPIF_SENDCHANGE:lla (2) lähetetään
    WM_SETTINGCHANGE-viesti, joka saa työpöydän piirtymään heti uusiksi
    (ilman tätä muutos näkyisi vasta seuraavassa kirjautumisessa).

    Windows tukee natiivisti JPEG/PNG/BMP-taustakuvia, joten HEIC/HEIF
    on tässäkin muunnettava ensin (ks. get_display_path) - Windowsilla
    ei ole minkäänlaista HEIC-tukea taustakuvan asetuksessa.

    Rekisteriin asetetaan lisäksi "Fill"-venytystapa (WallpaperStyle=10),
    joka vastaa GNOME-puolen "zoom"-asetusta.
    """
    if sys.platform != "win32":
        raise RuntimeError("set_windows_wallpaper() vaatii Windowsin")

    import winreg  # saatavilla vain Windowsilla, siksi tuonti tässä eikä tiedoston alussa

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10")  # 10 = Fill
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
        winreg.CloseKey(key)
    except OSError:
        # Ei kriittinen - taustakuva vaihtuu silti, venytystapa vain saattaa
        # jäädä ennalleen jos rekisteriavainta ei jostain syystä saada auki.
        pass

    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02

    user32 = ctypes.windll.user32
    user32.SystemParametersInfoW.argtypes = [
        ctypes.c_uint, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint,
    ]
    user32.SystemParametersInfoW.restype = ctypes.c_int

    ok = user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, str(path.resolve()), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    )
    if not ok:
        raise RuntimeError(
            f"SystemParametersInfoW epäonnistui (GetLastError={ctypes.GetLastError()})"
        )


def set_wallpaper(path: Path):
    """Asettaa taustakuvan käyttöjärjestelmälle sopivalla tavalla."""
    if sys.platform == "win32":
        set_windows_wallpaper(path)
    else:
        set_gnome_wallpaper(path)


def main():
    if not CONFIG_PATH.exists():
        log(tr("wp.err_config", path=CONFIG_PATH))
        sys.exit(1)
    if not INDEX_PATH.exists():
        log(tr("wp.err_index", path=INDEX_PATH))
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    tz = ZoneInfo(config["timezone"])
    tolerance = config.get("elevation_tolerance", 6.0)
    twilight_tolerance = config.get("twilight_elevation_tolerance", 3.0)
    twilight_band = config.get("twilight_band", 12.0)
    az_weight = config.get("azimuth_weight", 0.05)

    now = datetime.now(tz)
    obs = Observer(latitude=config["latitude"], longitude=config["longitude"])
    current_elev = elevation(obs, now)
    current_az = azimuth(obs, now)

    # Auringon korkeuskulma ei ole lineaarinen valon voimakkuuden suhteen:
    # ero 40° ja 45° välillä (keskipäivä) näkyy tuskin ollenkaan, mutta ero
    # -2° ja +4° välillä (horisontin tuntumassa, auringonnousu/-lasku) voi
    # muuttaa valaistuksen hämärästä kirkkaaksi. Siksi käytetään tiukempaa
    # toleranssia kun ollaan lähellä horisonttia ("twilight_band" astetta
    # nollasta), jotta yöllä ei valikoidu selvästi kirkkaampia päiväkuvia.
    if abs(current_elev) <= twilight_band:
        effective_tolerance = twilight_tolerance
        tolerance_reason = tr("wp.reason_twilight", elev=current_elev, band=twilight_band)
    else:
        effective_tolerance = tolerance
        tolerance_reason = tr("wp.reason_normal")

    # Vain kuvat jotka löytyvät levyltä
    records = [r for r in records if Path(r["path"]).exists()]
    if not records:
        log(tr("wp.no_photos"))
        return

    # Vain kuvat joilla on sijainti ja oikea ottoaika (EXIF tai käsin annettu):
    # muuten kuvan aurinkokulma on arvaus (kotisijainti / tiedoston muokkausaika).
    # Jos yhdelläkään kuvalla ei ole, käytetään kaikkia jotta valinta ei jää tyhjäksi.
    complete = [r for r in records if r.get("gps") and r.get("time_source") != "mtime_fallback"]
    records = complete or records

    def score(r):
        elev_diff = abs(r["sun_elevation"] - current_elev)
        az_diff = circular_diff(r["sun_azimuth"], current_az)
        return elev_diff + az_weight * az_diff, elev_diff

    scored = [(r, *score(r)) for r in records]
    # scored: (record, combined_score, elev_diff)

    within_tolerance = [t for t in scored if t[2] <= effective_tolerance]

    if within_tolerance:
        candidates = within_tolerance
        mode = tr("wp.mode_tol", reason=tolerance_reason, tol=effective_tolerance)
    else:
        # Varajärjestelmä: otetaan N lähintä koko indeksistä. Yöllä/hämärässä
        # tämä voi silti tarkoittaa kirkkaampaa kuvaa jos kokoelmassa ei ole
        # yhtään hämäriä/pimeitä kuvia - lokitetaan selvästi jotta ongelma
        # (liian vähän yökuvia kokoelmassa) on helppo huomata.
        scored.sort(key=lambda t: t[1])
        candidates = scored[:FALLBACK_CANDIDATE_COUNT]
        mode = tr("wp.mode_fallback", reason=tolerance_reason, tol=effective_tolerance)


    # Estetään sama kuva kahdesti peräkkäin - suodatetaan edellinen valinta
    # pois, mutta vain jos jäljelle jää vielä vaihtoehtoja.
    # Kierrätys: jokainen ehdokas näytetään kerran ennen kuin mikään toistuu.
    # Kun kaikki nykyiset ehdokkaat on käyty läpi, aloitetaan uusi kierros, joten
    # vaihto jatkuu loputtomiin eikä lopu "vaihtoehdot loppuivat" -tilaan.
    # Edellinen kuva ei koskaan tule kahdesti peräkkäin.
    last_choice = read_last_choice()
    history = read_history()
    unseen = [t for t in candidates if t[0]["path"] not in history and t[0]["path"] != last_choice]
    if not unseen:
        history = []  # kierros käyty läpi -> uusi kierros
        unseen = [t for t in candidates if t[0]["path"] != last_choice]
    if not unseen:
        # Ainoa ehdokas on jo taustakuvana: laajennetaan lähimpiin muihin kuviin,
        # jotta vaihto onnistuu (muuten "Vaihda nyt" ei tekisi mitään).
        unseen = sorted((t for t in scored if t[0]["path"] != last_choice), key=lambda t: t[1])[:FALLBACK_CANDIDATE_COUNT]
        mode += tr("wp.mode_widened")
    candidates = unseen or candidates

    # Painotettu satunnaisvalinta: mitä lähempänä, sitä todennäköisempi.
    # Neliöllinen painotus (ei lineaarinen) suosii voimakkaasti lähimpiä
    # osumia - näin kaukaisempi ehdokas (esim. 5-6° päässä, sallittu jos
    # se mahtuu toleranssiin) valikoituu vain harvoin, vaikka teknisesti
    # kelpaisikin.
    weights = [1.0 / ((t[1] + 0.3) ** 2) for t in candidates]
    chosen_record, chosen_score, chosen_elev_diff = random.choices(candidates, weights=weights, k=1)[0]
    chosen_path = Path(chosen_record["path"])
    display_path = get_display_path(chosen_path)

    try:
        set_wallpaper(display_path)
        write_last_choice(str(chosen_path), (history + [chosen_record["path"]])[-HISTORY_LIMIT:])
        conversion_note = tr("wp.conv_note", name=display_path.name) if display_path != chosen_path else ""
        log(tr("wp.chosen", elev=current_elev, az=current_az, name=chosen_path.name, conv=conversion_note,
               photo_elev=chosen_record["sun_elevation"], diff=chosen_elev_diff, mode=mode, n=len(candidates)))
    except (subprocess.CalledProcessError, RuntimeError) as e:
        log(tr("wp.err_set", e=e))
        sys.exit(1)


if __name__ == "__main__":
    main()
