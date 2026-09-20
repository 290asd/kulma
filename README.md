# Kulma

Your desktop wallpaper changes automatically to a photo that was taken in
sunlight as similar as possible to the sunlight you have right now at your
location. Works on Ubuntu/GNOME (systemd timers) and on Windows (tray app).

The idea: the time of day alone does not tell what the light looks like —
4 pm in November and 4 pm in June look completely different. The **sun
elevation**, on the other hand, tells the quality of the light directly,
regardless of the season, so Kulma calculates it for each of your photos
(based on their EXIF data) and compares it with the current sun elevation
when choosing the wallpaper.

## How it works

1. **`kulma_index.py`** walks through your photo folder (recursively), reads
   the EXIF capture time and the possible GPS location of each photo, and uses
   the `astral` library to calculate the sun elevation and azimuth at the
   moment the photo was taken. The result is saved to `index.json`.
2. **`kulma_wallpaper.py`** calculates the sun elevation *right now* and
   picks from the index a photo whose stored angle is closest — using a
   weighted random choice, so that the choice varies but is not completely
   arbitrary. Candidates are cycled (every candidate is shown once before any
   repeats) and the same photo can never come twice in a row.
   Only photos that have a location (GPS) and a capture time are considered;
   the others are left out, because their sun angle would be a guess.
3. Two systemd timers run these automatically: the wallpaper changes once an
   hour by default, and the index is updated at night to pick up new photos.

Everything happens locally — your photos stay on your machine, no cloud
services.

**Windows user?** See [`windows/README_WINDOWS.md`](windows/README_WINDOWS.md) —
the same `kulma_index.py`/`kulma_wallpaper.py` scripts work as they are, but
setting the wallpaper and the scheduling are handled by Windows' own
mechanisms (a tray app and Task Scheduler instead of systemd timers).

## Dependencies

- Python 3.9+ (zoneinfo support)
- GNOME desktop (`gsettings`-based wallpaper setting)
- systemd (user-level timers)

Python packages:
```bash
pip install astral pillow-heif --break-system-packages
```
(`pillow-heif` is needed if your photos are in `.HEIC`/`.HEIF` format, e.g.
the default format of iPhones — without it the EXIF capture time and GPS
of those photos cannot be read, and the system has to fall back to the
inaccurate file modification time.)

Pillow (`PIL`) usually comes preinstalled on Ubuntu. If not:
```bash
pip install Pillow --break-system-packages
```

## Installation

```bash
git clone https://github.com/290asd/kulma.git kulma
cd kulma
./install.sh
```

The script copies the files into place (`~/.local/bin/`, `~/.config/kulma/`,
`~/.config/systemd/user/`) but does not enable anything automatically,
because the configuration has to be edited first.

### 1. Edit config.json

```bash
nano ~/.config/kulma/config.json
```

**Do not use sudo** to edit this file — it is in your own user's directory,
not root's. Editing with sudo changes the file's owner to root and breaks
the timers later.

```json
{
  "photo_dir": "/home/you/Pictures/Wallpapers",
  "latitude": 60.1699,
  "longitude": 24.9384,
  "timezone": "Europe/Helsinki",
  "elevation_tolerance": 6.0,
  "twilight_elevation_tolerance": 3.0,
  "twilight_band": 12.0,
  "azimuth_weight": 0.05
}
```

| Field | Description |
|---|---|
| `photo_dir` | Photo folder, walked through recursively including subfolders. **Not** the script folder. |
| `language` | Language of the texts: `fi` (default) or `en`. Affects the log and the indexing output (in the Windows tray app also the menu and windows). The texts are in `bin/kulma_i18n.py`. |
| `latitude` / `longitude` | Your location. Used to calculate the current sun elevation, and by default for photos that have no GPS EXIF of their own. |
| `timezone` | IANA time zone (e.g. `Europe/Helsinki`). EXIF does not contain a time zone, so this is used to interpret the capture times of the photos correctly. |
| `elevation_tolerance` | How many degrees a photo's sun angle may differ from the current one normally (far from the horizon, e.g. midday or deep night). 5-8° is a good starting point. |
| `twilight_elevation_tolerance` | A stricter tolerance used near the horizon (see `twilight_band`), because the light intensity changes quickly per degree there - without it, clearly brighter dawn/dusk photos could be chosen at night. 2-4° is a good starting point. |
| `twilight_band` | Within how many degrees of the horizon (0°) the stricter `twilight_elevation_tolerance` is used instead of `elevation_tolerance`. 10-15° is a good starting point. |
| `azimuth_weight` | How much weight is given to the direction of the sun (not just the elevation). 0 = don't care, 0.05-0.1 = a light effect. |

### 2. First indexing

```bash
python3 ~/.local/bin/kulma_index.py
```

The output tells how many photos were found, how many contained GPS data, and
what the range of sun angles in your collection is. **If the output warns about
`mtime_fallback` photos**, their EXIF capture time could not be read (the most
common cause: HEIC without `pillow-heif`) — the sun angle of these photos is
probably calculated wrong until the cause is fixed.

### 3. Enable the timers

```bash
systemctl --user daemon-reload
systemctl --user enable --now kulma.timer
systemctl --user enable --now kulma-reindex.timer
```

If you want the wallpaper to change also while you are not logged in
(e.g. behind the lock screen):
```bash
loginctl enable-linger $USER
```

After this everything happens by itself: just add photos to the
`photo_dir` folder, and they are picked up in the next night's indexing.

## Commands for daily use

**Status:**
```bash
systemctl --user list-timers                    # when it runs next
systemctl --user status kulma.service            # the latest run
```

**Manual runs:**
```bash
systemctl --user start kulma.service             # change the wallpaper now
systemctl --user start kulma-reindex.service      # update the index now
```

**Logs:**
```bash
tail -f ~/.config/kulma/kulma.log                # own log file
journalctl --user -u kulma.service -f             # systemd's log
```

**Stopping / disabling:**
```bash
systemctl --user disable --now kulma.timer
systemctl --user disable --now kulma-reindex.timer
```

**More frequent changing** (e.g. 15 min instead of an hour) — edit
`~/.config/systemd/user/kulma.timer`:
```ini
[Timer]
OnCalendar=*:0/15
```
and then:
```bash
systemctl --user daemon-reload
systemctl --user restart kulma.timer
```

## File layout after installation

```
~/.local/bin/
  kulma_index.py
  kulma_wallpaper.py
  kulma_i18n.py         # texts (fi/en)
~/.config/kulma/
  config.json           # settings
  index.json            # photo index (created automatically)
  last_choice.json      # previous choice and round history, prevents repeats
  overrides.json        # locations/capture times entered by hand (optional)
  kulma.log             # log file
~/.config/systemd/user/
  kulma.service
  kulma.timer
  kulma-reindex.service
  kulma-reindex.timer
~/.cache/kulma/converted/
  <photo name>.jpg      # JPEG conversions made automatically from HEIC/HEIF photos
```

## HEIC/HEIF photos and displaying the wallpaper

GNOME's own wallpaper rendering (`gdk-pixbuf`) does not support the HEIC/HEIF
format at all on most Linux distributions (it is missing by default for
patent reasons), even though Kulma itself can read the EXIF data of HEIC files
through `pillow-heif` in the indexing phase. If a HEIC photo were set directly
as the wallpaper, the `gsettings` command would "succeed" but the desktop
would show nothing new.

For this reason `kulma_wallpaper.py` converts the chosen HEIC/HEIF photo to
JPEG in the `~/.cache/kulma/converted/` folder before setting it as the
wallpaper. The conversion is done only once per photo - later runs use the
already converted file. The folder can be emptied at any time, it is rebuilt
automatically when needed:
```bash
rm -rf ~/.cache/kulma/converted
```

## Known limitations

- On Linux only GNOME (`gsettings`-based). For other desktop environments the
  `set_gnome_wallpaper()` function has to be replaced with a corresponding
  command. Windows has its own implementation, see `windows/README_WINDOWS.md`.
- The photo collection should be large enough and cover different seasons, so
  that sun angles are found evenly around the clock and the year. With a small
  collection many runs fall back to the fallback logic (the nearest candidates
  from outside the tolerance).
- GPS EXIF is missing from many photos (e.g. if the location data was removed
  when sharing). Such photos (and photos that lack an EXIF capture time) are
  left out of the wallpaper selection until the location and time are entered
  by hand: on Windows the tray app asks for them, on Linux add them to the file
  `~/.config/kulma/overrides.json`
  (`{"<photo path>": {"lat": 60.17, "lon": 24.94, "capture_time": "2019-06-16T03:57:00"}}`)
  and run `kulma_index.py` again. If no photo has the details, all photos are
  used (with the default location from config.json as the location).

## License

MIT
