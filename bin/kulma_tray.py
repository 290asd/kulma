#!/usr/bin/env python3
"""
Kulma - Windowsin ilmoitusalueen (tray) sovellus.

Korvaa Task Scheduler -tehtävän "Kulma": sovellus pyörii taustalla,
vaihtaa taustakuvan config.jsonin `interval_minutes`-välein (oletus 30 min)
ja tarjoaa kuvakkeen valikon:

  - vasen klikkaus / "Vaihda taustakuva nyt"
  - Tauko / jatka automaattista vaihtoa
  - Päivitä indeksi (kysyy puuttuvat GPS-sijainnit ja ottoajat)
  - Asetukset (tkinter-ikkuna)
  - Avaa loki
  - Käynnistä Windowsin mukana
  - Lopeta

Käynnistys: pythonw kulma_tray.py   (asetusikkuna: kulma_tray.py --settings)
Riippuvuus: pip install pystray
"""

import ctypes
import json
import math
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kulma_index as idx  # noqa: E402  (overrides.json ja HEIC-tuki)
import kulma_wallpaper as wp  # noqa: E402  (jakaa polut, lokin ja valintalogiikan)

DEFAULT_INTERVAL_MIN = 30
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
CREATE_NO_WINDOW = 0x08000000
INDEX_SCRIPT = Path(__file__).resolve().with_name("kulma_index.py")
PLACES_PATH = wp.CONFIG_PATH.with_name("places.json")  # paikannimien välimuisti

# Asetusikkunan oletusarvot ensikäynnistykseen (config.example.json:n kaltaiset).
DEFAULTS = {
    "photo_dir": str(Path.home() / "Pictures" / "Taustakuvat").replace("\\", "/"),
    "latitude": 60.1699,
    "longitude": 24.9384,
    "timezone": "Europe/Helsinki",
    "interval_minutes": DEFAULT_INTERVAL_MIN,
}


def load_config() -> dict:
    try:
        with open(wp.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# --- Asetusikkuna (ajetaan omana prosessinaan: tkinter ei tykkää säikeistä) ---

def settings_window():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    cfg = {**DEFAULTS, **load_config()}
    root = tk.Tk()
    root.title("Kulma - asetukset")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=12)
    frm.grid()

    fields = [
        ("photo_dir", "Kuvakansio"),
        ("latitude", "Leveysaste"),
        ("longitude", "Pituusaste"),
        ("timezone", "Aikavyöhyke"),
        ("interval_minutes", "Vaihtoväli (min)"),
    ]
    vars_ = {}
    for row, (key, label) in enumerate(fields):
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=3)
        vars_[key] = tk.StringVar(value=str(cfg[key]))
        ttk.Entry(frm, textvariable=vars_[key], width=42).grid(row=row, column=1, pady=3, padx=6)

    def browse():
        d = filedialog.askdirectory(initialdir=vars_["photo_dir"].get() or None)
        if d:
            vars_["photo_dir"].set(d)

    ttk.Button(frm, text="Selaa…", command=browse).grid(row=0, column=2)

    def save():
        try:
            new = {
                "photo_dir": vars_["photo_dir"].get().strip().replace("\\", "/"),
                "latitude": float(vars_["latitude"].get().replace(",", ".")),
                "longitude": float(vars_["longitude"].get().replace(",", ".")),
                "timezone": vars_["timezone"].get().strip(),
                "interval_minutes": max(1, int(vars_["interval_minutes"].get())),
            }
            ZoneInfo(new["timezone"])
            if not Path(new["photo_dir"]).is_dir():
                raise ValueError(f"Kuvakansiota ei löydy: {new['photo_dir']}")
        except Exception as e:
            messagebox.showerror("Kulma", f"Tarkista arvot:\n{e}")
            return
        old = load_config()
        wp.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(wp.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({**old, **new}, f, indent=2, ensure_ascii=False)
        # Uusi kuvakansio (tai puuttuva indeksi) -> indeksoidaan taustalla.
        if old.get("photo_dir") != new["photo_dir"] or not wp.INDEX_PATH.exists():
            reindex()
            messagebox.showinfo("Kulma", "Tallennettu. Indeksi päivittyy taustalla, ja puuttuvat tiedot kysytään sen jälkeen.")
        else:
            messagebox.showinfo("Kulma", "Tallennettu.")
        root.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=len(fields), column=0, columnspan=3, pady=(10, 0), sticky="e")
    ttk.Button(btns, text="Tallenna", command=save).pack(side="left", padx=4)
    ttk.Button(btns, text="Peruuta", command=root.destroy).pack(side="left")
    root.mainloop()


def run_index() -> subprocess.CompletedProcess:
    """Ajaa kulma_index.py:n ja odottaa (ei konsoli-ikkunaa)."""
    return subprocess.run([sys.executable, str(INDEX_SCRIPT)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                          creationflags=CREATE_NO_WINDOW)


def reindex_and_review():
    p = run_index()
    if p.returncode:
        import tkinter as tk
        from tkinter import messagebox
        tk.Tk().withdraw()
        return messagebox.showerror("Kulma - indeksointi epäonnistui", (p.stderr or p.stdout)[-600:])
    review_window()


def geocode(text: str) -> tuple[float, float, str]:
    """Sijainti tekstistä: "60.17, 24.94" tai paikannimi (Nominatim-haku)."""
    m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*[,; ]\s*(-?\d+(?:[.,]\d+)?)\s*", text)
    if m:
        lat, lon = (float(g.replace(",", ".")) for g in m.groups())
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Koordinaatit ovat alueen ulkopuolella")
        return lat, lon, f"{lat:.4f}, {lon:.4f}"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"format": "jsonv2", "q": text, "limit": 1, "accept-language": "fi"})
    req = urllib.request.Request(url, headers={"User-Agent": "Kulma/1.0 (github.com/290asd/kulma)"})
    with urllib.request.urlopen(req, timeout=8) as r:
        found = json.load(r)
    if not found:
        raise ValueError(f"Paikkaa ei löytynyt: {text}")
    return float(found[0]["lat"]), float(found[0]["lon"]), found[0]["display_name"].split(",")[0]


def missing_records(records: list) -> list:
    """Kuvat joilta puuttuu sijainti (GPS) tai EXIF-ottoaika.

    Jokaisella kuvalla pitää olla molemmat, jotta aurinkokulma lasketaan
    oikeaan paikkaan ja aikaan ja tiedot voidaan näyttää."""
    return [r for r in records if not r.get("gps") or r.get("time_source") == "mtime_fallback"]


def review_window():
    """Näyttää kuvat joilta puuttuu GPS-sijainti tai EXIF-ottoaika ja kysyy ne
    käyttäjältä. Vastaukset tallennetaan overrides.json:iin (kuvatiedostoja ei
    muokata) ja indeksi ajetaan uudelleen."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    from PIL import Image, ImageOps, ImageTk

    with open(wp.INDEX_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)
    overrides = idx.load_overrides()
    todo = missing_records(records)

    root = tk.Tk()
    if not todo:
        root.withdraw()
        messagebox.showinfo("Kulma", f"Indeksi päivitetty ({len(records)} kuvaa). Kaikilla kuvilla on sijainti ja ottoaika.")
        return
    root.title("Kulma - puuttuvat sijainti- ja aikatiedot")

    def remaining() -> int:
        """Montako kuvaa on yhä ilman sijaintia tai ottoaikaa."""
        def complete(r):
            ov = overrides.get(r["path"], {})
            return (r.get("gps") or "lat" in ov) and (r.get("time_source") != "mtime_fallback" or "capture_time" in ov)
        return sum(not complete(r) for r in todo)

    def finish():
        left = remaining()
        if left and not messagebox.askyesno(
                "Kulma", f"{left} kuvalta puuttuu vielä sijainti tai ottoaika. Jokaisella kuvalla pitää olla molemmat.\n\n"
                "Suljetaanko silti? Ne jätetään pois taustakuvavalinnasta, kunnes tiedot on annettu."):
            return
        if dirty:
            root.title("Kulma - päivitetään indeksiä…")
            root.update()
            run_index()
        root.destroy()

    dirty = False
    root.protocol("WM_DELETE_WINDOW", finish)
    frm = ttk.Frame(root, padding=10)
    frm.grid()
    ttk.Label(frm, wraplength=820, justify="left", text=(
        f"Jokaisella kuvalla pitää olla sijainti ja ottoaika, jotta aurinkokulma lasketaan oikein ja tiedot "
        f"voidaan näyttää. {len(todo)} kuvalta ne puuttuvat kokonaan tai osittain, ja ne jätetään pois "
        "taustakuvavalinnasta kunnes tiedot on annettu. "
        "Valitse kuvia (Ctrl/Shift), anna sijainti ja/tai aika ja paina «Käytä valituille». "
        "Kuvatiedostoja ei muokata.")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

    tree = ttk.Treeview(frm, columns=("file", "loc", "time"), show="headings", height=14, selectmode="extended")
    for col, title, w in (("file", "Kuva", 200), ("loc", "Sijainti", 170), ("time", "Ottoaika", 210)):
        tree.heading(col, text=title)
        tree.column(col, width=w)
    tree.grid(row=1, column=0, sticky="nsew")
    preview = ttk.Label(frm, text="Valitse kuva", anchor="center", width=45)
    preview.grid(row=1, column=1, padx=(10, 0), sticky="nsew")

    def row_values(r):
        ov = overrides.get(r["path"], {})
        loc = ov.get("place") or ("GPS" if r.get("gps") else "puuttuu")
        if "capture_time" in ov:
            when = ov["capture_time"][:16].replace("T", " ")
        elif r.get("time_source") == "mtime_fallback":
            when = f"puuttuu (muokattu {r['capture_time'][:16].replace('T', ' ')})"
        else:
            when = r["capture_time"][:16].replace("T", " ")
        return Path(r["path"]).name, loc, when

    for i, r in enumerate(todo):
        tree.insert("", "end", iid=str(i), values=row_values(r))

    def show(_=None):
        sel = tree.selection()
        if not sel:
            return
        try:
            with Image.open(todo[int(sel[0])]["path"]) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((380, 380))
                photo = ImageTk.PhotoImage(im)
            preview.configure(image=photo, text="")
            preview.image = photo  # viite pidettävä, muuten kuva katoaa
        except Exception:
            preview.configure(image="", text="(esikatselu ei onnistu)")

    tree.bind("<<TreeviewSelect>>", show)

    form = ttk.Frame(frm)
    form.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    place_var, time_var = tk.StringVar(), tk.StringVar()
    ttk.Label(form, text="Sijainti (paikannimi tai lat, lon)").grid(row=0, column=0, sticky="w")
    ttk.Entry(form, textvariable=place_var, width=36).grid(row=0, column=1, padx=6, pady=2)
    ttk.Label(form, text="Ottoaika (VVVV-KK-PP HH:MM)").grid(row=1, column=0, sticky="w")
    ttk.Entry(form, textvariable=time_var, width=36).grid(row=1, column=1, padx=6, pady=2)

    def apply():
        nonlocal dirty
        sel = tree.selection()
        if not sel:
            return messagebox.showinfo("Kulma", "Valitse ensin kuvia listasta.")
        place, when = place_var.get().strip(), time_var.get().strip()
        if not place and not when:
            return messagebox.showinfo("Kulma", "Anna sijainti ja/tai ottoaika.")
        upd = {}
        try:
            if place:
                upd["lat"], upd["lon"], upd["place"] = geocode(place)
            if when:
                for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
                    try:
                        upd["capture_time"] = datetime.strptime(when, fmt).isoformat()
                        break
                    except ValueError:
                        pass
                else:
                    raise ValueError("Ottoajan muoto: 2019-12-25 13:30 tai 25.12.2019 13:30")
        except Exception as e:
            return messagebox.showerror("Kulma", str(e))
        for iid in sel:
            r = todo[int(iid)]
            overrides.setdefault(r["path"], {}).update(upd)
            tree.item(iid, values=row_values(r))
        save_overrides()
        dirty = True

    def save_overrides():
        idx.OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(idx.OVERRIDES_PATH, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)

    btns = ttk.Frame(frm)
    btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
    ttk.Button(btns, text="Käytä valituille", command=apply).pack(side="left", padx=4)
    ttk.Button(btns, text="Valmis", command=finish).pack(side="left")
    root.mainloop()


# --- Toiminnot ---------------------------------------------------------------

def reindex():
    """Indeksoi taustalla ja avaa sen jälkeen puuttuvien tietojen ikkunan (jos tarvitaan)."""
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--reindex-review"],
                     creationflags=CREATE_NO_WINDOW)


def autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "Kulma")
            return True
    except OSError:
        return False


def set_autostart(on: bool):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, "Kulma", 0, winreg.REG_SZ,
                              f'"{sys.executable}" "{Path(__file__).resolve()}"')
        else:
            try:
                winreg.DeleteValue(k, "Kulma")
            except OSError:
                pass


def place_name(lat: float, lon: float, fetch: bool = False) -> str | None:
    """Paikannimi (esim. "Helsinki, Suomi") OpenStreetMapin Nominatim-palvelusta.

    Koordinaatit pyöristetään kahteen desimaaliin (~1 km) sekä välimuistiavaimessa
    että pyynnössä, joten palveluun ei lähde tarkkaa sijaintia. Tulokset
    tallennetaan places.json:iin, eli sama paikka haetaan vain kerran.
    Verkkohaku tehdään vain kun fetch=True (valikkoa rakennettaessa ei haeta).
    """
    lat, lon = round(lat, 2), round(lon, 2)
    key = f"{lat},{lon}"
    try:
        with open(PLACES_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    if key in cache or not fetch:
        return cache.get(key)
    try:
        url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
            {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "accept-language": "fi"})
        req = urllib.request.Request(url, headers={"User-Agent": "Kulma/1.0 (github.com/290asd/kulma)"})
        with urllib.request.urlopen(req, timeout=5) as r:
            a = json.load(r).get("address", {})
    except Exception:
        return None  # ei nettiä tms. - yritetään uudelleen seuraavalla vaihdolla
    name = ", ".join(x for x in (
        a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county"),
        a.get("country")) if x)
    if name:
        cache[key] = name
        try:
            with open(PLACES_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    return name or None


def photo_record() -> dict | None:
    """Nykyisen (viimeksi valitun) kuvan indeksitietue, tai None."""
    last = wp.read_last_choice()
    if not last:
        return None
    try:
        with open(wp.INDEX_PATH, "r", encoding="utf-8") as f:
            return next(r for r in json.load(f) if r["path"] == last)
    except Exception:
        return None


def photo_location(fetch: bool = False) -> str | None:
    """Nykyisen kuvan ottopaikka tekstinä, tai None jos kuvaa ei ole valittu."""
    rec = photo_record()
    if not rec:
        return None
    if "lat" not in rec:
        return "puuttuu - päivitä indeksi ja anna sijainti"
    return place_name(rec["lat"], rec["lon"], fetch) or f"{rec['lat']:.2f}°, {rec['lon']:.2f}°"


def photo_time() -> str | None:
    """Nykyisen kuvan ottoaika tekstinä (esim. "16.06.2019 klo 03:57"), tai None."""
    rec = photo_record()
    if not rec:
        return None
    when = datetime.fromisoformat(rec["capture_time"]).strftime("%d.%m.%Y klo %H:%M")
    return when + (" (arvio: muokkausaika)" if rec.get("time_source") == "mtime_fallback" else "")


def status_text() -> str:
    """Esim. "Aurinko 28.6° · IMG_7377.HEIC"."""
    try:
        cfg = load_config()
        from astral import Observer
        from astral.sun import elevation
        elev = elevation(Observer(cfg["latitude"], cfg["longitude"]),
                         datetime.now(ZoneInfo(cfg["timezone"])))
        last = wp.read_last_choice()
        return f"Aurinko {elev:.1f}° · {Path(last).name if last else 'ei vielä valintaa'}"
    except Exception:
        return "Kulma - asetukset puuttuvat"


def main():
    if "--settings" in sys.argv:
        return settings_window()
    if "--reindex-review" in sys.argv:
        return reindex_and_review()

    # Vain yksi tray-instanssi kerrallaan.
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW(None, False, "Kulma-Tray")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return

    import pystray
    from PIL import Image, ImageDraw

    def make_icon(active: bool) -> Image.Image:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        color = (255, 196, 40, 255) if active else (150, 150, 150, 255)
        d.ellipse((18, 18, 46, 46), fill=color)
        for a in range(8):  # säteet
            dx, dy = math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)
            d.line((32 + 20 * dx, 32 + 20 * dy, 32 + 29 * dx, 32 + 29 * dy), fill=color, width=4)
        return img

    lock = threading.Lock()
    state = {"paused": False}
    wake = threading.Event()  # herättää ajastimen kesken odotuksen

    def location_line() -> str | None:
        loc = photo_location()
        return f"Sijainti: {loc}" if loc else None

    def time_line() -> str | None:
        try:
            when = photo_time()
        except Exception:
            return None
        return f"Otettu: {when}" if when else None

    def refresh():
        photo_location(fetch=True)  # hakee ja välimuistittaa paikannimen (verkko)
        icon.icon = make_icon(not state["paused"])
        icon.title = "\n".join(filter(None, (status_text(), location_line(), time_line())))
        icon.update_menu()

    def change_now(*_):
        with lock:
            try:
                wp.main()
            except SystemExit:
                pass  # virhe on jo lokitettu wp.main():ssa
            except Exception as e:
                wp.log(f"Tray: virhe taustakuvan vaihdossa: {e}")
        refresh()

    def toggle_pause(*_):
        state["paused"] = not state["paused"]
        refresh()

    def toggle_autostart(*_):
        set_autostart(not autostart_enabled())
        icon.update_menu()

    def open_settings(*_):
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--settings"])

    def quit_app(*_):
        wake.set()
        state["quit"] = True
        icon.stop()

    def timer():
        while not state.get("quit"):
            if not state["paused"]:
                change_now()
            wake.wait(max(1, int(load_config().get("interval_minutes", DEFAULT_INTERVAL_MIN))) * 60)
            wake.clear()

    icon = pystray.Icon(
        "Kulma", make_icon(True), "Kulma",
        pystray.Menu(
            pystray.MenuItem(lambda _: status_text(), None, enabled=False),
            pystray.MenuItem(lambda _: location_line() or "", None, enabled=False,
                             visible=lambda _: bool(location_line())),
            pystray.MenuItem(lambda _: time_line() or "", None, enabled=False,
                             visible=lambda _: bool(time_line())),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Vaihda taustakuva nyt", change_now, default=True),
            pystray.MenuItem("Tauko", toggle_pause, checked=lambda _: state["paused"]),
            pystray.MenuItem("Päivitä indeksi", lambda *_: reindex()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Asetukset…", open_settings),
            pystray.MenuItem("Avaa loki", lambda *_: os.startfile(wp.LOG_PATH)),
            pystray.MenuItem("Käynnistä Windowsin mukana", toggle_autostart,
                             checked=lambda _: autostart_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Lopeta", quit_app),
        ),
    )

    def setup(icon):
        icon.visible = True
        if not wp.CONFIG_PATH.exists():
            open_settings()  # ensikäynnistys: kysytään asetukset
        threading.Thread(target=timer, daemon=True).start()

    icon.run(setup)


if __name__ == "__main__":
    main()
