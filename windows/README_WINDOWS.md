# Kulma on Windows

The same idea as in the Linux version - the wallpaper changes according to the
sun elevation, not the time of day. Two differences to the Linux version:

- The wallpaper is set with Windows' `SystemParametersInfoW` API (the
  counterpart of `gsettings`), no separate program is needed.
- Instead of systemd timers, the wallpaper is changed by a **tray app** (a sun
  icon in the notification area), and the index update is handled by Windows'
  Task Scheduler.

`kulma_index.py` and `kulma_wallpaper.py` are the same files as on the Linux
side (in the `bin/` folder) - they detect the operating system automatically
(`sys.platform`) and use the right paths/API calls. So the same repo can be
used on both operating systems.

## Dependencies

1. **Python 3.9+** from [python.org](https://www.python.org/downloads/) -
   remember to tick **"Add python.exe to PATH"** during setup.
2. Open PowerShell and install the libraries (the install script also does this
   automatically, but you can run it by hand):
   ```powershell
   pip install astral Pillow pillow-heif pystray
   ```

## Installation

```powershell
cd path\to\kulma\windows
powershell -ExecutionPolicy Bypass -File install.ps1
```

(`-ExecutionPolicy Bypass` is needed because the scripts are not signed -
it only affects this one run and does not change the system's settings.)

The script:
- copies the scripts to `%LOCALAPPDATA%\Kulma\bin\`
- installs the Python dependencies (including `pystray`)
- creates the app icon (see below)
- starts the tray app (`kulma_tray.py`) and adds it to Windows startup
  (`HKCU\...\Run`) and the Start Menu (a shortcut called "Kulma")
- registers the Task Scheduler task **Kulma-Reindex** (index update, every
  night at 03:30)
- removes the old **Kulma** scheduled task if there is one (the tray app
  replaces it, so that the wallpaper does not change twice)

## Icon

The app icon combines the emojis 📐 and ☀️. `install.ps1` creates it by running
`make_icon.py`, which downloads two images from Apple's emoji image library
(`emoji-datasource-apple@16.0.0`, jsDelivr; the SHA-256 of the files is
verified) and combines them. The icon is stored in the files
`%LOCALAPPDATA%\Kulma\icon\kulma.ico` and `kulma.png`, and it is used as the
tray icon, in the Start Menu shortcut and in the app's windows. While paused,
the tray icon is grey.

**Apple's emoji images are copyrighted by Apple, so they are not in this
repo** - they are downloaded only onto your own machine. If the download fails
(no network), the tray app uses a drawn fallback icon; you can retry with
`python windows\make_icon.py` and restart the app.

## Usage: the tray app

Find the sun icon in the notification area (in Windows 11 it may be in the
hidden-icons `^` list; you can drag it into view). The tooltip of the icon and
the three top rows of the menu show the sun elevation, the current photo, and
the place and time it was taken.

**Capture location:** the place name (e.g. "Helsinki, Finland") is looked up
from the GPS coordinates of the photo using OpenStreetMap's Nominatim service.
Only a location rounded to ~1 km accuracy is sent to the service, and the
result is stored in a cache (`%APPDATA%\Kulma\places.json`), so the same place
is looked up only once. Place names are fetched in the selected UI language. If
there is no network, the coordinates are shown; if the photo has no location,
the menu says it is missing.

| Action | What it does |
|---|---|
| Left click / **Change wallpaper now** | Chooses and sets a wallpaper right away. Changing can be continued endlessly: photos are cycled (all current candidates are gone through before any repeats) and a new round starts by itself |
| **Pause** | Pauses the automatic change (the icon turns grey), another click resumes |
| **Update index** | Runs `kulma_index.py` in the background (new photos included) and afterwards asks for the missing details, see below |
| **Settings…** | Photo folder, location, time zone, change interval and **language** (Suomi / English). A language change takes effect as soon as the settings window is closed |
| **Open log** | Opens `kulma.log` |
| **Start with Windows** | Turns automatic startup on/off |
| **About…** | A window with the icon, the version number, the versions of the libraries used, photo library statistics (number of photos, location known / missing, capture time missing, number of incomplete photos and the 3 most common locations) and a link to GitHub. The version is `__version__` in `kulma_tray.py`. The names of the most common locations are looked up from Nominatim when needed (max 3 lookups, cached) |
| **Quit** | Closes the app. Restart it from the Start Menu (search for "Kulma"); the shortcut is created at install time |

On the first start (when `config.json` is missing) the settings window opens by
itself. Saving indexes the photos in the background when the photo folder is
new. The app reads the settings at every change, so changes take effect without
a restart (a change of the interval after the next change).

### Missing location and time details

When the index is updated from the tray menu (or for the first time after
saving the settings) and a photo lacks a GPS location or an EXIF capture time,
a window opens that lists the photos with a preview. Select photos
(Ctrl/Shift), type a **location** (a place name, e.g. `Turku`, or coordinates
`60.45, 22.27`) and/or a **capture time** (`2019-06-16 03:57` or
`16.06.2019 03:57`) and press *Apply to selected*. *Done* runs the indexing
again with the new details, so that the sun angle is calculated for the right
place and time.

**Every photo must have a location and a capture time.** Photos that lack them
are automatically left out of the wallpaper selection until the details have
been entered. If you close the window while details are still missing, the app
warns you. The window opens only at the first indexing and whenever the index
update is run by hand from the menu; starting the app or the nightly indexing
does not ask anything. The capture location and time of the current photo are
shown in the tray menu and in the tooltip of the icon.

The details are saved to the file `%APPDATA%\Kulma\overrides.json` - **the photo
files are not modified**. The place name search uses OpenStreetMap's Nominatim
service (only the search text you typed is sent). The nightly scheduled
indexing uses the same details but does not open a window.

### Advanced settings (config.json)

The settings window covers the basics. Finer adjustments are made directly in
the file:

```powershell
notepad "$env:APPDATA\Kulma\config.json"
```

```json
{
  "photo_dir": "C:/Users/you/Pictures/Wallpapers",
  "latitude": 60.1699,
  "longitude": 24.9384,
  "timezone": "Europe/Helsinki",
  "interval_minutes": 30,
  "language": "en",
  "elevation_tolerance": 6.0,
  "twilight_elevation_tolerance": 3.0,
  "twilight_band": 12.0,
  "azimuth_weight": 0.05
}
```

The explanations of the fields are the same as in the main project README.
`interval_minutes` is the change interval of the tray app (default 30).
`language` is the language of the user interface, `"fi"` (default when the key
is missing) or `"en"`; the language choice in the settings window saves it. All
the texts of the app (tray menu, windows, log and indexing output) are in
`bin/kulma_i18n.py`. `photo_dir` can be written with forward slashes
(`C:/Users/...`) - Python handles it correctly on Windows too.

## On the command line

The scripts also work without the tray app:

```powershell
python "$env:LOCALAPPDATA\Kulma\bin\kulma_index.py"       # indexing
python "$env:LOCALAPPDATA\Kulma\bin\kulma_wallpaper.py"   # change the wallpaper once
Start-ScheduledTask -TaskName "Kulma-Reindex"                # indexing via the scheduled task
Get-Content "$env:APPDATA\Kulma\kulma.log" -Tail 20 -Wait   # log
```

**Removing everything (closes the tray app, removes autostart, the shortcut and the tasks):**
```powershell
cd path\to\kulma\windows
powershell -ExecutionPolicy Bypass -File uninstall.ps1
```

## File layout after installation

```
%LOCALAPPDATA%\Kulma\bin\
  kulma_index.py
  kulma_wallpaper.py
  kulma_tray.py
  kulma_i18n.py           # UI texts (fi/en)
%LOCALAPPDATA%\Kulma\cache\converted\
  <photo name>.jpg        # JPEG conversions made from HEIC/HEIF photos
%LOCALAPPDATA%\Kulma\icon\
  kulma.ico, kulma.png    # the app icon (set square + sun)
%APPDATA%\Kulma\
  config.json             # settings
  index.json              # photo index
  last_choice.json        # previous choice and round history
  overrides.json          # locations and capture times entered by hand
  places.json             # place name cache
  kulma.log               # log file
```

## Known differences to the Linux version

- **Works only while logged in** (there is no counterpart to Linux's
  `loginctl enable-linger`): the tray app and the indexing task run only when
  the user is logged in.
- **The stretch mode (`WallpaperStyle`)** is hard-coded to "Fill" (10), because
  it corresponds most closely to the `zoom` setting on the Linux side. You can
  change it by hand in the registry (`HKCU\Control Panel\Desktop\WallpaperStyle`)
  if you want another one (e.g. "Fit" = 6, "Stretch" = 2, "Tile" =
  0/`TileWallpaper`=1).
- **`pythonw.exe`** is used for running so that a console window does not flash
  up - if it is not found in the same folder as `python.exe` on PATH,
  `python.exe` is used (works, but a window may flash).
