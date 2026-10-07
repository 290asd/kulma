# Kulma

Your Windows desktop wallpaper (and lock screen) changes automatically to a
photo that was taken in sunlight as similar as possible to the sunlight you
have right now at your location.

The idea: the time of day alone does not tell what the light looks like -
4 pm in November and 4 pm in June look completely different. The **sun
elevation**, on the other hand, tells the quality of the light directly,
regardless of the season, so Kulma calculates it for each of your photos
(from their EXIF capture time and GPS location) and compares it with the
current sun elevation when choosing the wallpaper.

Everything happens locally - your photos stay on your machine. The only
network use is looking up place names from OpenStreetMap (see below).

## How it works

1. **Indexing** walks through your photo folder (recursively), reads the EXIF
   capture time and GPS location of each photo, and calculates the sun
   elevation and azimuth at the moment it was taken (NOAA solar equations).
   The result is saved to `index.json`. The index is updated from the menu, and
   automatically when it is more than a day old.
2. **Choosing** calculates the sun elevation *right now* and picks a photo
   whose stored angle is closest, with a weighted random choice so that the
   choice varies but is not arbitrary. Near the horizon a stricter tolerance is
   used, because the light changes quickly per degree there. Candidates are
   cycled (every candidate is shown once before any repeats) and the same photo
   never comes twice in a row. Only photos that have a location and a capture
   time are considered; the others would have a guessed sun angle.
3. A **tray app** (sun icon in the notification area) changes the wallpaper on
   the clock, by default at :00 and :30, and right after the computer wakes up
   if a change was missed while it slept.

## Installation

Requires Windows 10 2004 or newer and the
[.NET 10 Desktop Runtime](https://dotnet.microsoft.com/download/dotnet/10.0).
HEIC/HEIF photos (the iPhone default) additionally need the "HEIF Image
Extensions" and "HEVC Video Extensions" from the Microsoft Store (often
preinstalled).

Build the app (needs the .NET 10 SDK):

```powershell
dotnet publish src/Kulma -c Release -o publish
```

Copy `publish\Kulma.exe` to e.g. `%LOCALAPPDATA%\Kulma\Kulma.exe` and start it.
On the first start the settings window opens; saving indexes the photos. Then
tick **Start with Windows** in the tray menu - it also adds a "Kulma" shortcut
to the Start Menu.

To uninstall: untick **Start with Windows**, choose **Quit**, and delete
`%LOCALAPPDATA%\Kulma`, `%APPDATA%\Kulma` and the Start Menu shortcut.

## Usage

Find the sun icon in the notification area (in Windows 11 it may be in the
hidden-icons `^` list; you can drag it into view). The tooltip and the top rows
of the menu show the sun elevation, the current photo, and where and when it was
taken.

| Action | What it does |
|---|---|
| Left click / **Change wallpaper now** | Chooses and sets a wallpaper right away |
| **Pause** | Pauses the automatic change (the icon turns grey) |
| **Update index** | Indexes the photos (new photos included) and then asks for missing details, see below |
| **Settings…** | Photo folder, home location, time zone, interval, clock alignment, language (Suomi / English), lock screen |
| **Open log** | Opens `kulma.log` |
| **Start with Windows** | Automatic startup on/off |
| **About…** | Version, libraries, photo library statistics and the 3 most common locations |
| **Quit** | Closes the app (restart it from the Start Menu) |

**Missing location and time:** after **Update index**, photos that lack a GPS
location or an EXIF capture time are listed with a preview. Select photos
(Ctrl/Shift), type a location (a place name like `Turku`, or `60.45, 22.27`)
and/or a capture time (`2019-06-16 03:57` or `16.6.2019 03:57`) and press
**Apply to selected**. The answers are saved to `overrides.json`; the photo
files are never modified.

**Place names** are looked up from OpenStreetMap's Nominatim service. Only a
location rounded to ~1 km is sent, and the results are cached in `places.json`,
so each place is looked up only once.

**Lock screen:** by default it shows the same photo as the desktop. The first
time, Windows switches the lock screen from "Windows Spotlight" to "Picture".

## Settings (`%APPDATA%\Kulma\config.json`)

The settings window covers the common ones; the rest can be edited by hand
(the app reads the file at every change). See `config.example.json`.

| Field | Description |
|---|---|
| `photo_dir` | Photo folder, walked through recursively |
| `latitude` / `longitude` | Your location: the current sun elevation, and the location of photos without GPS |
| `timezone` | IANA time zone (e.g. `Europe/Helsinki`), used to interpret EXIF capture times |
| `interval_minutes` | Change interval (default 30) |
| `align_to_clock` | Change on clock boundaries (default `true`), otherwise a full interval after the previous change |
| `lock_screen` | Also set the lock screen image (default `true`) |
| `language` | `fi` (default) or `en` |
| `elevation_tolerance` | How many degrees a photo's sun angle may differ normally (default 6) |
| `twilight_elevation_tolerance` | Stricter tolerance near the horizon (default 3) |
| `twilight_band` | Within how many degrees of the horizon the stricter tolerance is used (default 12) |
| `azimuth_weight` | Weight of the sun's direction in the choice (default 0.05, 0 = ignore) |

## Files

```
%LOCALAPPDATA%\Kulma\
  Kulma.exe
  cache\converted\      # JPEG conversions of HEIC photos (Windows cannot show HEIC as a wallpaper)
  icon\kulma.png, .ico  # optional own icon; without it a sun is drawn
%APPDATA%\Kulma\
  config.json           # settings
  index.json            # photo index
  overrides.json        # locations/capture times entered by hand
  places.json           # place name cache
  last_choice.json      # current photo and the round history
  kulma.log
```

## Development

The code is in `src/Kulma` (C#, WinForms). `Kulma.exe --selftest` checks the
sun formula against the stored index and the change timing; `Kulma.exe --index`
updates the index without the tray.

## License

MIT
