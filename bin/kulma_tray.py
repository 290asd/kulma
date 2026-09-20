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
  - Tietoja (versio, kirjastot, linkki GitHubiin)
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
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kulma_index as idx  # noqa: E402  (overrides.json ja HEIC-tuki)
import kulma_wallpaper as wp  # noqa: E402  (jakaa polut, lokin ja valintalogiikan)
import kulma_i18n as i18n  # noqa: E402  (käyttöliittymän kieli)
from kulma_i18n import t as tr  # noqa: E402

__version__ = "1.0.0"
GITHUB_URL = "https://github.com/290asd/kulma"
DEFAULT_INTERVAL_MIN = 30
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
CREATE_NO_WINDOW = 0x08000000
INDEX_SCRIPT = Path(__file__).resolve().with_name("kulma_index.py")
PLACES_PATH = wp.CONFIG_PATH.with_name("places.json")  # paikannimien välimuisti
# Kuvake (📐☀️), jonka windows/make_icon.py luo asennuksessa; jos puuttuu, piirretään oletuskuvake.
ICON_PNG = Path(os.environ.get("LOCALAPPDATA", "")) / "Kulma" / "icon" / "kulma.png"

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


def set_window_icon(root):
    """Kulman kuvake tkinter-ikkunaan ja tehtäväpalkkiin (jos kuvake on luotu)."""
    try:
        from PIL import Image, ImageTk
        root._kulma_icon = ImageTk.PhotoImage(Image.open(ICON_PNG))  # viite pidettävä
        root.iconphoto(True, root._kulma_icon)
    except Exception:
        pass


# --- Asetusikkuna (ajetaan omana prosessinaan: tkinter ei tykkää säikeistä) ---

def system_language() -> str:
    """Ensikäynnistyksen oletuskieli: suomi jos Windowsin käyttöliittymä on suomea, muuten englanti."""
    try:
        return "fi" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x0B else "en"
    except Exception:
        return "en"


def settings_window():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    cfg = {**DEFAULTS, **load_config()}
    # Vanhoissa asetuksissa kieltä ei ole tallennettu: silloin sovellus on ollut suomeksi.
    cfg_lang = load_config().get("language") or ("fi" if wp.CONFIG_PATH.exists() else system_language())
    root = tk.Tk()
    set_window_icon(root)
    root.title(tr("set.title"))
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=12)
    frm.grid()

    fields = [
        ("photo_dir", tr("set.photo_dir")),
        ("latitude", tr("set.lat")),
        ("longitude", tr("set.lon")),
        ("timezone", tr("set.tz")),
        ("interval_minutes", tr("set.interval")),
    ]
    vars_ = {}
    for row, (key, label) in enumerate(fields):
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=3)
        vars_[key] = tk.StringVar(value=str(cfg[key]))
        ttk.Entry(frm, textvariable=vars_[key], width=42).grid(row=row, column=1, pady=3, padx=6)

    lang_var = tk.StringVar(value=i18n.LANGUAGES.get(cfg_lang, i18n.LANGUAGES["fi"]))
    ttk.Label(frm, text=tr("set.language")).grid(row=len(fields), column=0, sticky="w", pady=3)
    ttk.Combobox(frm, textvariable=lang_var, values=list(i18n.LANGUAGES.values()), state="readonly",
                 width=20).grid(row=len(fields), column=1, sticky="w", pady=3, padx=6)

    def browse():
        d = filedialog.askdirectory(initialdir=vars_["photo_dir"].get() or None)
        if d:
            vars_["photo_dir"].set(d)

    ttk.Button(frm, text=tr("set.browse"), command=browse).grid(row=0, column=2)

    def save():
        try:
            new = {
                "photo_dir": vars_["photo_dir"].get().strip().replace("\\", "/"),
                "latitude": float(vars_["latitude"].get().replace(",", ".")),
                "longitude": float(vars_["longitude"].get().replace(",", ".")),
                "timezone": vars_["timezone"].get().strip(),
                "interval_minutes": max(1, int(vars_["interval_minutes"].get())),
                "language": next(k for k, v in i18n.LANGUAGES.items() if v == lang_var.get()),
            }
            ZoneInfo(new["timezone"])
            if not Path(new["photo_dir"]).is_dir():
                raise ValueError(tr("set.nofolder", path=new["photo_dir"]))
        except Exception as e:
            messagebox.showerror("Kulma", tr("set.check", err=e))
            return
        old = load_config()
        wp.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(wp.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({**old, **new}, f, indent=2, ensure_ascii=False)
        i18n.reload()  # viestit heti uudella kielellä
        # Uusi kuvakansio (tai puuttuva indeksi) -> indeksoidaan taustalla.
        if old.get("photo_dir") != new["photo_dir"] or not wp.INDEX_PATH.exists():
            reindex()
            messagebox.showinfo("Kulma", tr("set.saved_reindex"))
        else:
            messagebox.showinfo("Kulma", tr("set.saved"))
        root.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=len(fields) + 1, column=0, columnspan=3, pady=(10, 0), sticky="e")
    ttk.Button(btns, text=tr("set.save"), command=save).pack(side="left", padx=4)
    ttk.Button(btns, text=tr("set.cancel"), command=root.destroy).pack(side="left")
    root.mainloop()


def photo_library_stats() -> dict | None:
    """Kuvakirjaston tilastot indeksistä: määrät, puuttuvat tiedot ja 3 yleisintä sijaintia."""
    try:
        with open(wp.INDEX_PATH, "r", encoding="utf-8") as f:
            records = json.load(f)
    except Exception:
        return None
    clusters = []  # [lat, lon, kuvia] - alle 30 km päässä toisistaan olevat samaan ryhmään
    for r in records:
        if "lat" not in r:
            continue
        for c in clusters:
            if math.hypot((r["lat"] - c[0]) * 111, (r["lon"] - c[1]) * 111 * math.cos(math.radians(c[0]))) <= 30:
                c[2] += 1
                break
        else:
            clusters.append([r["lat"], r["lon"], 1])
    return {
        "total": len(records),
        "located": sum(1 for r in records if r.get("gps")),
        "no_time": sum(1 for r in records if r.get("time_source") == "mtime_fallback"),
        "missing": len(missing_records(records)),
        "top": sorted(clusters, key=lambda c: -c[2])[:3],
    }


def about_window():
    """Tietoja-ikkuna: kuvake, versio, kirjastot, kuvakirjaston tilastot ja linkki GitHubiin."""
    import platform
    import tkinter as tk
    import webbrowser
    from importlib.metadata import PackageNotFoundError, version
    from tkinter import ttk

    root = tk.Tk()
    set_window_icon(root)
    root.title(tr("about.title"))
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=(24, 16))
    frm.grid()
    row = iter(range(100))
    bold = ("Segoe UI", 10, "bold")

    try:  # kuvake ylimpänä
        from PIL import Image, ImageTk
        root._logo = ImageTk.PhotoImage(Image.open(ICON_PNG).resize((96, 96), Image.LANCZOS))
        ttk.Label(frm, image=root._logo).grid(row=next(row), column=0, pady=(0, 6))
    except Exception:
        pass
    ttk.Label(frm, text="Kulma", font=("Segoe UI", 16, "bold")).grid(row=next(row), column=0)
    ttk.Label(frm, text=tr("about.version", v=__version__)).grid(row=next(row), column=0)
    ttk.Label(frm, justify="center", wraplength=380, text=tr("about.desc")).grid(
        row=next(row), column=0, pady=(8, 10))

    def section(title, pairs):
        ttk.Separator(frm).grid(row=next(row), column=0, sticky="ew")
        ttk.Label(frm, text=title, font=bold).grid(row=next(row), column=0, sticky="w", pady=(8, 2))
        table = ttk.Frame(frm)
        table.grid(row=next(row), column=0, sticky="w")
        for i, (a, b, c) in enumerate(pairs):
            ttk.Label(table, text=a).grid(row=i, column=0, sticky="w")
            ttk.Label(table, text=b).grid(row=i, column=1, sticky="w", padx=12)
            ttk.Label(table, text=c, foreground="gray").grid(row=i, column=2, sticky="w")

    def ver(pkg):
        try:
            return version(pkg)
        except PackageNotFoundError:
            return "-"

    section(tr("about.libs"), [
        ("Python", platform.python_version(), tr("about.lib_python")),
        ("astral", ver("astral"), tr("about.lib_astral")),
        ("Pillow", ver("Pillow"), tr("about.lib_pillow")),
        ("pillow-heif", ver("pillow-heif"), tr("about.lib_heif")),
        ("pystray", ver("pystray"), tr("about.lib_pystray")),
        ("tkinter", str(tk.TkVersion), tr("about.lib_tk")),
    ])

    st = photo_library_stats()
    if not st or not st["total"]:
        section(tr("about.library"), [(tr("about.noindex"), "", "")])
    else:
        total = st["total"]
        pct = lambda n: f"{100 * n // total} %"
        section(tr("about.library"), [
            (tr("about.photos"), str(total), load_config().get("photo_dir", "")),
            (tr("about.located"), f"{st['located']}", pct(st["located"])),
            (tr("about.nolocation"), f"{total - st['located']}", pct(total - st["located"])),
            (tr("about.notime"), f"{st['no_time']}", pct(st["no_time"])),
            (tr("about.incomplete"), f"{st['missing']}", tr("about.excluded")),
        ])
        ttk.Label(frm, text=tr("about.toplocs"), font=bold).grid(row=next(row), column=0, sticky="w", pady=(8, 2))
        place_labels = []
        for lat, lon, n in st["top"]:
            lab = ttk.Label(frm)
            lab.grid(row=next(row), column=0, sticky="w")
            place_labels.append((lab, lat, lon, n))

        def render():
            for lab, lat, lon, n in place_labels:
                name = place_name(lat, lon) or f"{lat:.2f}°, {lon:.2f}°"
                lab.configure(text=tr("about.place_n", name=name, n=n, pct=pct(n)))

        def lookup():  # paikannimet taustalla, korkeintaan 1 pyyntö/s (Nominatimin käyttöehdot)
            for lat, lon, _ in st["top"]:
                if place_name(lat, lon) is None:
                    place_name(lat, lon, fetch=True)
                    time.sleep(1.1)

        worker = threading.Thread(target=lookup, daemon=True)
        worker.start()

        def poll():
            alive = worker.is_alive()
            render()
            if alive:
                root.after(500, poll)

        poll()

    ttk.Label(frm, foreground="gray", wraplength=380, text=tr("about.credits")).grid(
        row=next(row), column=0, sticky="w", pady=(8, 0))

    link = ttk.Label(frm, text=GITHUB_URL, foreground="#0a58ca", cursor="hand2",
                     font=("Segoe UI", 9, "underline"))
    link.grid(row=next(row), column=0, pady=(12, 8))
    link.bind("<Button-1>", lambda _: webbrowser.open(GITHUB_URL))
    ttk.Button(frm, text=tr("about.close"), command=root.destroy).grid(row=next(row), column=0)
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
        return messagebox.showerror(tr("err.index_failed"), (p.stderr or p.stdout)[-600:])
    review_window()


def geocode(text: str) -> tuple[float, float, str]:
    """Sijainti tekstistä: "60.17, 24.94" tai paikannimi (Nominatim-haku)."""
    m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*[,; ]\s*(-?\d+(?:[.,]\d+)?)\s*", text)
    if m:
        lat, lon = (float(g.replace(",", ".")) for g in m.groups())
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(tr("err.coords_range"))
        return lat, lon, f"{lat:.4f}, {lon:.4f}"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"format": "jsonv2", "q": text, "limit": 1, "accept-language": i18n.language()})
    req = urllib.request.Request(url, headers={"User-Agent": "Kulma/1.0 (github.com/290asd/kulma)"})
    with urllib.request.urlopen(req, timeout=8) as r:
        found = json.load(r)
    if not found:
        raise ValueError(tr("err.place_not_found", text=text))
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
    set_window_icon(root)
    if not todo:
        root.withdraw()
        messagebox.showinfo("Kulma", tr("rev.all_ok", n=len(records)))
        return
    root.title(tr("rev.title"))

    def remaining() -> int:
        """Montako kuvaa on yhä ilman sijaintia tai ottoaikaa."""
        def complete(r):
            ov = overrides.get(r["path"], {})
            return (r.get("gps") or "lat" in ov) and (r.get("time_source") != "mtime_fallback" or "capture_time" in ov)
        return sum(not complete(r) for r in todo)

    def finish():
        left = remaining()
        if left and not messagebox.askyesno("Kulma", tr("rev.close_q", n=left)):
            return
        if dirty:
            root.title(tr("rev.updating"))
            root.update()
            run_index()
        root.destroy()

    dirty = False
    root.protocol("WM_DELETE_WINDOW", finish)
    frm = ttk.Frame(root, padding=10)
    frm.grid()
    ttk.Label(frm, wraplength=820, justify="left", text=tr("rev.intro", n=len(todo), apply=tr("rev.apply"))).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

    tree = ttk.Treeview(frm, columns=("file", "loc", "time"), show="headings", height=14, selectmode="extended")
    for col, title, w in (("file", tr("rev.col_photo"), 200), ("loc", tr("rev.col_loc"), 170),
                          ("time", tr("rev.col_time"), 210)):
        tree.heading(col, text=title)
        tree.column(col, width=w)
    tree.grid(row=1, column=0, sticky="nsew")
    preview = ttk.Label(frm, text=tr("rev.select"), anchor="center", width=45)
    preview.grid(row=1, column=1, padx=(10, 0), sticky="nsew")

    def row_values(r):
        ov = overrides.get(r["path"], {})
        loc = ov.get("place") or ("GPS" if r.get("gps") else tr("rev.missing"))
        if "capture_time" in ov:
            when = ov["capture_time"][:16].replace("T", " ")
        elif r.get("time_source") == "mtime_fallback":
            when = tr("rev.time_missing", t=r["capture_time"][:16].replace("T", " "))
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
            preview.configure(image="", text=tr("rev.nopreview"))

    tree.bind("<<TreeviewSelect>>", show)

    form = ttk.Frame(frm)
    form.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    place_var, time_var = tk.StringVar(), tk.StringVar()
    ttk.Label(form, text=tr("rev.lbl_place")).grid(row=0, column=0, sticky="w")
    ttk.Entry(form, textvariable=place_var, width=36).grid(row=0, column=1, padx=6, pady=2)
    ttk.Label(form, text=tr("rev.lbl_time")).grid(row=1, column=0, sticky="w")
    ttk.Entry(form, textvariable=time_var, width=36).grid(row=1, column=1, padx=6, pady=2)

    def apply():
        nonlocal dirty
        sel = tree.selection()
        if not sel:
            return messagebox.showinfo("Kulma", tr("rev.pick_first"))
        place, when = place_var.get().strip(), time_var.get().strip()
        if not place and not when:
            return messagebox.showinfo("Kulma", tr("rev.enter_something"))
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
                    raise ValueError(tr("rev.bad_time"))
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
    ttk.Button(btns, text=tr("rev.apply"), command=apply).pack(side="left", padx=4)
    ttk.Button(btns, text=tr("rev.done"), command=finish).pack(side="left")
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
    key = f"{lat},{lon}" + ("" if i18n.language() == "fi" else f"|{i18n.language()}")  # välimuisti kielikohtainen
    try:
        with open(PLACES_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    if key in cache or not fetch:
        return cache.get(key)
    try:
        url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
            {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "accept-language": i18n.language()})
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
        return tr("loc.missing")
    return place_name(rec["lat"], rec["lon"], fetch) or f"{rec['lat']:.2f}°, {rec['lon']:.2f}°"


def photo_time() -> str | None:
    """Nykyisen kuvan ottoaika tekstinä (esim. "16.06.2019 klo 03:57"), tai None."""
    rec = photo_record()
    if not rec:
        return None
    when = datetime.fromisoformat(rec["capture_time"]).strftime(tr("time.fmt"))
    return when + (tr("time.estimate") if rec.get("time_source") == "mtime_fallback" else "")


def status_text() -> str:
    """Esim. "Aurinko 28.6° · IMG_7377.HEIC"."""
    try:
        cfg = load_config()
        from astral import Observer
        from astral.sun import elevation
        elev = elevation(Observer(cfg["latitude"], cfg["longitude"]),
                         datetime.now(ZoneInfo(cfg["timezone"])))
        last = wp.read_last_choice()
        return tr("status.sun", elev=elev, name=Path(last).name if last else tr("status.none"))
    except Exception:
        return tr("status.nosettings")


def main():
    try:  # tehtäväpalkki ryhmittelee ikkunat Kulmaksi eikä pythonw:ksi
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Kulma.Tray")
    except Exception:
        pass
    if "--settings" in sys.argv:
        return settings_window()
    if "--about" in sys.argv:
        return about_window()
    if "--reindex-review" in sys.argv:
        return reindex_and_review()

    # Vain yksi tray-instanssi kerrallaan.
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW(None, False, "Kulma-Tray")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return

    import pystray
    from PIL import Image, ImageDraw

    def drawn_icon(active: bool) -> Image.Image:
        """Oletuskuvake (piirretty aurinko) jos kuvaketta ei ole luotu."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        color = (255, 196, 40, 255) if active else (150, 150, 150, 255)
        d.ellipse((18, 18, 46, 46), fill=color)
        for a in range(8):  # säteet
            dx, dy = math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)
            d.line((32 + 20 * dx, 32 + 20 * dy, 32 + 29 * dx, 32 + 29 * dy), fill=color, width=4)
        return img

    def make_icon(active: bool) -> Image.Image:
        try:
            img = Image.open(ICON_PNG).convert("RGBA")
        except Exception:
            return drawn_icon(active)
        if not active:  # tauolla: harmaa
            grey = img.convert("L").convert("RGBA")
            grey.putalpha(img.getchannel("A"))
            return grey
        return img

    lock = threading.Lock()
    state = {"paused": False}
    wake = threading.Event()  # herättää ajastimen kesken odotuksen

    def location_line() -> str | None:
        loc = photo_location()
        return tr("loc.line", loc=loc) if loc else None

    def time_line() -> str | None:
        try:
            when = photo_time()
        except Exception:
            return None
        return tr("time.line", when=when) if when else None

    def refresh():
        i18n.reload()  # kieli voi olla vaihtunut asetuksissa
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
                wp.log(tr("err.tray", e=e))
        refresh()

    def toggle_pause(*_):
        state["paused"] = not state["paused"]
        refresh()

    def toggle_autostart(*_):
        set_autostart(not autostart_enabled())
        icon.update_menu()

    def open_about(*_):
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--about"])

    def open_settings(*_):
        p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--settings"])
        # Kun asetusikkuna sulkeutuu, päivitetään valikko ja vihjeteksti (esim. vaihdettu kieli).
        threading.Thread(target=lambda: (p.wait(), refresh()), daemon=True).start()

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
            pystray.MenuItem(lambda _: tr("menu.change"), change_now, default=True),
            pystray.MenuItem(lambda _: tr("menu.pause"), toggle_pause, checked=lambda _: state["paused"]),
            pystray.MenuItem(lambda _: tr("menu.reindex"), lambda *_: reindex()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: tr("menu.settings"), open_settings),
            pystray.MenuItem(lambda _: tr("menu.log"), lambda *_: os.startfile(wp.LOG_PATH)),
            pystray.MenuItem(lambda _: tr("menu.autostart"), toggle_autostart,
                             checked=lambda _: autostart_enabled()),
            pystray.MenuItem(lambda _: tr("menu.about"), open_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: tr("menu.quit"), quit_app),
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
