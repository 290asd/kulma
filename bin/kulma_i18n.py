#!/usr/bin/env python3
"""
kulma_i18n.py - Kulman käyttöliittymätekstit suomeksi ja englanniksi.

Kieli luetaan config.jsonin avaimesta "language" ("fi" tai "en"). Jos avainta ei
ole, käytetään suomea (vanhat asennukset pysyvät entisellään).

Käyttö:
    from kulma_i18n import t
    t("menu.quit")                    # -> "Lopeta" / "Quit"
    t("status.sun", elev=28.6, name="x.jpg")

Tekstit ovat str.format-muotoisia ({nimi}-paikkamerkit). Puuttuva englanninkielinen
teksti korvautuu suomenkielisellä. Koodin kommentit ja docstringit ovat suomeksi.
"""

import json
import os
import sys
from pathlib import Path

LANGUAGES = {"fi": "Suomi", "en": "English"}
DEFAULT_LANGUAGE = "fi"


def _config_path() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Kulma" / "config.json"
    return Path.home() / ".config" / "kulma" / "config.json"


_lang: str | None = None


def reload() -> str:
    """Lukee kielen config.jsonista uudelleen (kutsu kun asetukset ovat voineet muuttua)."""
    global _lang
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            code = json.load(f).get("language", DEFAULT_LANGUAGE)
    except Exception:
        code = DEFAULT_LANGUAGE
    _lang = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _lang


def language() -> str:
    return _lang or reload()


def t(key: str, **kw) -> str:
    text = STRINGS.get(language(), {}).get(key) or STRINGS["fi"][key]
    return text.format(**kw) if kw else text


STRINGS = {
    "fi": {
        # --- tray-valikko ---
        "menu.change": "Vaihda taustakuva nyt",
        "menu.pause": "Tauko",
        "menu.reindex": "Päivitä indeksi",
        "menu.settings": "Asetukset…",
        "menu.log": "Avaa loki",
        "menu.autostart": "Käynnistä Windowsin mukana",
        "menu.about": "Tietoja…",
        "menu.quit": "Lopeta",
        # --- tila- ja tietorivit ---
        "status.sun": "Aurinko {elev:.1f}° · {name}",
        "status.none": "ei vielä valintaa",
        "status.nosettings": "Kulma - asetukset puuttuvat",
        "loc.line": "Sijainti: {loc}",
        "loc.missing": "puuttuu - päivitä indeksi ja anna sijainti",
        "time.line": "Otettu: {when}",
        "time.estimate": " (arvio: muokkausaika)",
        "time.fmt": "%d.%m.%Y klo %H:%M",
        # --- asetusikkuna ---
        "set.title": "Kulma - asetukset",
        "set.photo_dir": "Kuvakansio",
        "set.lat": "Leveysaste",
        "set.lon": "Pituusaste",
        "set.tz": "Aikavyöhyke",
        "set.interval": "Vaihtoväli (min)",
        "set.language": "Kieli",
        "set.browse": "Selaa…",
        "set.save": "Tallenna",
        "set.cancel": "Peruuta",
        "set.check": "Tarkista arvot:\n{err}",
        "set.nofolder": "Kuvakansiota ei löydy: {path}",
        "set.saved": "Tallennettu.",
        "set.saved_reindex": "Tallennettu. Indeksi päivittyy taustalla, ja puuttuvat tiedot kysytään sen jälkeen.",
        # --- tietoja-ikkuna ---
        "about.title": "Kulma - tietoja",
        "about.version": "Versio {v}",
        "about.desc": "Vaihtaa työpöydän taustakuvan kuvaan, joka on otettu samanlaisessa auringonvalossa kuin juuri nyt.",
        "about.libs": "Kirjastot",
        "about.lib_python": "ohjelmointikieli",
        "about.lib_astral": "auringon korkeuskulma ja suunta",
        "about.lib_pillow": "kuvat ja EXIF-tiedot",
        "about.lib_heif": "HEIC/HEIF-kuvat",
        "about.lib_pystray": "ilmoitusalueen kuvake",
        "about.lib_tk": "ikkunat",
        "about.library": "Kuvakirjasto",
        "about.noindex": "Ei indeksoituja kuvia",
        "about.photos": "Kuvia",
        "about.located": "Sijainti tiedossa",
        "about.nolocation": "Sijainti puuttuu",
        "about.notime": "Ottoaika puuttuu",
        "about.incomplete": "Puutteellisia",
        "about.excluded": "ei mukana taustakuvavalinnassa",
        "about.toplocs": "Yleisimmät sijainnit",
        "about.place_n": "{name}: {n} kuvaa ({pct})",
        "about.credits": "Paikannimet: OpenStreetMap Nominatim. Kuvake: kulmaviivain ja aurinko, Applen emoji-kuvista.",
        "about.close": "Sulje",
        # --- puuttuvien tietojen ikkuna ---
        "rev.title": "Kulma - puuttuvat sijainti- ja aikatiedot",
        "rev.updating": "Kulma - päivitetään indeksiä…",
        "rev.intro": (
            "Jokaisella kuvalla pitää olla sijainti ja ottoaika, jotta aurinkokulma lasketaan oikein ja tiedot "
            "voidaan näyttää. {n} kuvalta ne puuttuvat kokonaan tai osittain, ja ne jätetään pois "
            "taustakuvavalinnasta kunnes tiedot on annettu. "
            "Valitse kuvia (Ctrl/Shift), anna sijainti ja/tai aika ja paina «{apply}». "
            "Kuvatiedostoja ei muokata."),
        "rev.col_photo": "Kuva",
        "rev.col_loc": "Sijainti",
        "rev.col_time": "Ottoaika",
        "rev.select": "Valitse kuva",
        "rev.missing": "puuttuu",
        "rev.time_missing": "puuttuu (muokattu {t})",
        "rev.nopreview": "(esikatselu ei onnistu)",
        "rev.lbl_place": "Sijainti (paikannimi tai lat, lon)",
        "rev.lbl_time": "Ottoaika (VVVV-KK-PP HH:MM)",
        "rev.apply": "Käytä valituille",
        "rev.done": "Valmis",
        "rev.pick_first": "Valitse ensin kuvia listasta.",
        "rev.enter_something": "Anna sijainti ja/tai ottoaika.",
        "rev.bad_time": "Ottoajan muoto: 2019-12-25 13:30 tai 25.12.2019 13:30",
        "rev.close_q": (
            "{n} kuvalta puuttuu vielä sijainti tai ottoaika. Jokaisella kuvalla pitää olla molemmat.\n\n"
            "Suljetaanko silti? Ne jätetään pois taustakuvavalinnasta, kunnes tiedot on annettu."),
        "rev.all_ok": "Indeksi päivitetty ({n} kuvaa). Kaikilla kuvilla on sijainti ja ottoaika.",
        # --- virheet ---
        "err.index_failed": "Kulma - indeksointi epäonnistui",
        "err.coords_range": "Koordinaatit ovat alueen ulkopuolella",
        "err.place_not_found": "Paikkaa ei löytynyt: {text}",
        "err.tray": "Tray: virhe taustakuvan vaihdossa: {e}",
        # --- kulma_wallpaper.py (loki) ---
        "wp.err_config": "Virhe: config-tiedostoa ei löydy ({path}).",
        "wp.err_index": "Virhe: indeksiä ei löydy ({path}). Aja ensin kulma_index.py.",
        "wp.no_photos": "Indeksissä ei ole yhtään olemassa olevaa kuvaa. Aja kulma_index.py uudelleen.",
        "wp.reason_twilight": "hämärävyöhyke (|{elev:.1f}°| <= {band}°)",
        "wp.reason_normal": "normaali",
        "wp.mode_tol": "toleranssin sisällä ({reason}, {tol}°)",
        "wp.mode_fallback": "fallback (lähimmät ehdokkaat, {reason} toleranssi {tol}° ei riittänyt)",
        "wp.mode_widened": ", laajennettu (ainoa ehdokas oli jo käytössä)",
        "wp.conv_note": " (näytetään JPEG-muunnoksena: {name})",
        "wp.chosen": (
            "Aurinkokulma nyt: {elev:.1f}° (atsimuutti {az:.1f}°) | "
            "valittu kuva: {name}{conv} (kuvan kulma {photo_elev:.1f}°, "
            "ero {diff:.1f}°) | {mode}, {n} ehdokasta"),
        "wp.err_set": "Virhe asetettaessa taustakuvaa: {e}",
        # --- kulma_index.py (tuloste) ---
        "idx.warn_heif": (
            "HUOM: pillow-heif ei ole asennettu - HEIC/HEIF-kuvien EXIF-data "
            "(ottoaika, GPS) ei ole luettavissa. Asenna: pip install pillow-heif "
            "--break-system-packages"),
        "idx.err_config": "Virhe: config-tiedostoa ei löydy: {path}",
        "idx.err_config_hint": "Kopioi config.example.json paikoilleen ja muokkaa sitä ensin.",
        "idx.err_folder": "Virhe: kansiota ei löydy: {path}",
        "idx.found": "Löytyi {n} kuvaa kansiosta {dir}",
        "idx.progress": "  ...käsitelty {i}/{n}",
        "idx.done": "Valmis. Indeksi tallennettu: {path}",
        "idx.indexed": "Kuvia indeksoitu: {n} ({skipped} ohitettu virheiden vuoksi)",
        "idx.gps_count": "Kuvia joissa oli GPS-data: {gps} / {n}",
        "idx.range": "Aurinkokulmien vaihteluväli: {lo:.1f}° ... {hi:.1f}°",
        "idx.warn_mtime": (
            "HUOM: {n} kuvasta ei saatu luettua EXIF-ottoaikaa "
            "(kuva ei avautunut tai EXIF puuttui). Näille käytettiin TIEDOSTON "
            "MUOKKAUSAIKAA, joka voi poiketa merkittävästi todellisesta ottohetkestä "
            "(esim. jos kuva on kopioitu/siirretty myöhemmin) - aurinkokulma näille "
            "kuville on siis todennäköisesti VÄÄRIN LASKETTU."),
        "idx.examples": "Ensimmäiset esimerkit:",
        "idx.and_more": "  ... ja {n} muuta",
        "idx.heif_hint": (
            "Jos nämä ovat HEIC/HEIF-kuvia, varmista että 'pillow-heif' on "
            "asennettu: pip install pillow-heif --break-system-packages"),
    },
    "en": {
        # --- tray menu ---
        "menu.change": "Change wallpaper now",
        "menu.pause": "Pause",
        "menu.reindex": "Update index",
        "menu.settings": "Settings…",
        "menu.log": "Open log",
        "menu.autostart": "Start with Windows",
        "menu.about": "About…",
        "menu.quit": "Quit",
        # --- status lines ---
        "status.sun": "Sun {elev:.1f}° · {name}",
        "status.none": "no photo chosen yet",
        "status.nosettings": "Kulma - settings missing",
        "loc.line": "Location: {loc}",
        "loc.missing": "missing - update the index and enter a location",
        "time.line": "Taken: {when}",
        "time.estimate": " (estimate: file modified time)",
        "time.fmt": "%d %b %Y, %H:%M",
        # --- settings window ---
        "set.title": "Kulma - settings",
        "set.photo_dir": "Photo folder",
        "set.lat": "Latitude",
        "set.lon": "Longitude",
        "set.tz": "Time zone",
        "set.interval": "Change interval (min)",
        "set.language": "Language",
        "set.browse": "Browse…",
        "set.save": "Save",
        "set.cancel": "Cancel",
        "set.check": "Check the values:\n{err}",
        "set.nofolder": "Photo folder not found: {path}",
        "set.saved": "Saved.",
        "set.saved_reindex": "Saved. The index is updating in the background; missing details will be asked afterwards.",
        # --- about window ---
        "about.title": "Kulma - about",
        "about.version": "Version {v}",
        "about.desc": "Changes the desktop wallpaper to a photo taken in similar sunlight to the sun right now.",
        "about.libs": "Libraries",
        "about.lib_python": "programming language",
        "about.lib_astral": "sun elevation and direction",
        "about.lib_pillow": "images and EXIF data",
        "about.lib_heif": "HEIC/HEIF images",
        "about.lib_pystray": "notification area icon",
        "about.lib_tk": "windows",
        "about.library": "Photo library",
        "about.noindex": "No indexed photos",
        "about.photos": "Photos",
        "about.located": "Location known",
        "about.nolocation": "Location missing",
        "about.notime": "Capture time missing",
        "about.incomplete": "Incomplete",
        "about.excluded": "excluded from wallpaper selection",
        "about.toplocs": "Top locations",
        "about.place_n": "{name}: {n} photos ({pct})",
        "about.credits": "Place names: OpenStreetMap Nominatim. Icon: set square and sun, from Apple's emoji images.",
        "about.close": "Close",
        # --- missing details window ---
        "rev.title": "Kulma - missing location and time details",
        "rev.updating": "Kulma - updating the index…",
        "rev.intro": (
            "Every photo needs a location and a capture time so that the sun angle is calculated correctly and "
            "the details can be shown. {n} photos are missing them completely or partly, and they are left out of "
            "the wallpaper selection until the details are entered. "
            "Select photos (Ctrl/Shift), enter a location and/or time and press «{apply}». "
            "The photo files are not modified."),
        "rev.col_photo": "Photo",
        "rev.col_loc": "Location",
        "rev.col_time": "Capture time",
        "rev.select": "Select a photo",
        "rev.missing": "missing",
        "rev.time_missing": "missing (modified {t})",
        "rev.nopreview": "(preview not available)",
        "rev.lbl_place": "Location (place name or lat, lon)",
        "rev.lbl_time": "Capture time (YYYY-MM-DD HH:MM)",
        "rev.apply": "Apply to selected",
        "rev.done": "Done",
        "rev.pick_first": "Select photos from the list first.",
        "rev.enter_something": "Enter a location and/or a capture time.",
        "rev.bad_time": "Time format: 2019-12-25 13:30 or 25.12.2019 13:30",
        "rev.close_q": (
            "{n} photos are still missing a location or capture time. Every photo needs both.\n\n"
            "Close anyway? They will be left out of the wallpaper selection until the details are entered."),
        "rev.all_ok": "Index updated ({n} photos). All photos have a location and a capture time.",
        # --- errors ---
        "err.index_failed": "Kulma - indexing failed",
        "err.coords_range": "Coordinates are out of range",
        "err.place_not_found": "Place not found: {text}",
        "err.tray": "Tray: error while changing the wallpaper: {e}",
        # --- kulma_wallpaper.py (log) ---
        "wp.err_config": "Error: config file not found ({path}).",
        "wp.err_index": "Error: index not found ({path}). Run kulma_index.py first.",
        "wp.no_photos": "The index has no existing photos. Run kulma_index.py again.",
        "wp.reason_twilight": "twilight zone (|{elev:.1f}°| <= {band}°)",
        "wp.reason_normal": "normal",
        "wp.mode_tol": "within tolerance ({reason}, {tol}°)",
        "wp.mode_fallback": "fallback (nearest candidates, {reason} tolerance {tol}° was not enough)",
        "wp.mode_widened": ", widened (the only candidate was already in use)",
        "wp.conv_note": " (shown as JPEG conversion: {name})",
        "wp.chosen": (
            "Sun elevation now: {elev:.1f}° (azimuth {az:.1f}°) | "
            "chosen photo: {name}{conv} (photo elevation {photo_elev:.1f}°, "
            "diff {diff:.1f}°) | {mode}, {n} candidates"),
        "wp.err_set": "Error setting the wallpaper: {e}",
        # --- kulma_index.py (output) ---
        "idx.warn_heif": (
            "NOTE: pillow-heif is not installed - the EXIF data (capture time, GPS) of "
            "HEIC/HEIF photos cannot be read. Install: pip install pillow-heif "
            "--break-system-packages"),
        "idx.err_config": "Error: config file not found: {path}",
        "idx.err_config_hint": "Copy config.example.json into place and edit it first.",
        "idx.err_folder": "Error: folder not found: {path}",
        "idx.found": "Found {n} photos in {dir}",
        "idx.progress": "  ...processed {i}/{n}",
        "idx.done": "Done. Index saved: {path}",
        "idx.indexed": "Photos indexed: {n} ({skipped} skipped because of errors)",
        "idx.gps_count": "Photos with GPS data: {gps} / {n}",
        "idx.range": "Sun elevation range: {lo:.1f}° ... {hi:.1f}°",
        "idx.warn_mtime": (
            "NOTE: the EXIF capture time could not be read for {n} photos "
            "(the photo did not open or EXIF was missing). The FILE MODIFICATION TIME "
            "was used for them, which may differ considerably from the real capture time "
            "(e.g. if the photo was copied/moved later) - the sun angle for these "
            "photos is therefore probably CALCULATED WRONG."),
        "idx.examples": "First examples:",
        "idx.and_more": "  ... and {n} more",
        "idx.heif_hint": (
            "If these are HEIC/HEIF photos, make sure 'pillow-heif' is "
            "installed: pip install pillow-heif --break-system-packages"),
    },
}
