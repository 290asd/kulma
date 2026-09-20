#!/usr/bin/env python3
"""
kulma_wallpaper.py

Calculates the sun elevation RIGHT NOW (for the location in config.json) and
picks, from the photo index, a photo whose stored sun angle (at the moment the
photo was taken) is closest to the current one. Works fully automatically, no
manual tuning is needed during use.

Selection principle:
  1. Calculate the current sun elevation and azimuth.
  2. Take all photos whose elevation is within the tolerance of the current
     one. The tolerance is stricter ("twilight_elevation_tolerance") near the
     horizon (within "twilight_band" degrees of zero), because the light
     intensity changes quickly per degree there - without this, clearly
     brighter daytime photos could be chosen at night even though the
     numeric difference is small.
  3. Choose among these randomly, weighted so that photos closer to the
     current elevation (and azimuth) are more likely. The weighting is
     quadratic (not linear), so more distant photos that are still within
     the tolerance are chosen only rarely - this prevents the choice from
     feeling "random" even though technically valid but clearly worse
     candidates are in the pool.
  4. If no photo falls within the tolerance (e.g. a small collection), the
     nearest candidates are used as a fallback - something changes every
     time, the choice never ends up empty.
  5. Candidates are cycled: photos already shown are excluded until all
     current candidates have been gone through, after which a new round
     starts. The previous photo cannot come twice in a row; if the only
     candidate is already in use, the nearest other photos are used so that
     changing always succeeds.

On Windows the same photo is also set as the lock screen image (unless
"lock_screen": false in config.json).

Run on a schedule: on Linux through a systemd timer (see systemd/kulma.timer),
on Windows by the tray app (see windows/README_WINDOWS.md).
"""

import base64
import ctypes
import json
import os
import random
import subprocess
import sys
import threading
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
    """Kulma's settings folder - depends on the operating system.

    Linux/macOS: ~/.config/kulma
    Windows:     %APPDATA%\\Kulma
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Kulma"
    return Path.home() / ".config" / "kulma"


def _cache_root() -> Path:
    """Kulma's cache folder (HEIC->JPEG conversions) - depends on the operating system.

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
FALLBACK_CANDIDATE_COUNT = 3  # if no photo falls within the tolerance
HISTORY_LIMIT = 500           # maximum length of the round history


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
    """Photos already shown in the current "round" (see main())."""
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
    """Smallest difference between two azimuth angles (on a 0-360 scale)."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def get_display_path(path: Path) -> Path:
    """Returns a path the operating system can use as a wallpaper.

    Neither GNOME's wallpaper rendering (gdk-pixbuf) nor Windows'
    SystemParametersInfoW support the HEIC/HEIF format (on Linux it is
    missing from the default install for patent reasons, on Windows the API
    does not support it at all), even though this script itself can read the
    EXIF data of HEIC files through pillow-heif. If a HEIC path were given
    directly, the command would "succeed" but the desktop would show nothing
    new - it would stay stuck on the old photo.

    Therefore HEIC/HEIF photos are converted into a JPEG cache before being
    set as the wallpaper. The conversion is done only once per photo (the
    cache file is named after the original) - later runs use the already
    converted file.
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
    """Sets the GNOME wallpaper and forces a redraw.

    A known GNOME Shell quirk: a plain "gsettings set picture-uri" does not
    always make the visible wallpaper update immediately - GNOME Shell may
    keep showing the old, already drawn wallpaper until some other event
    (e.g. switching virtual desktops) forces it to rebuild the background
    actor. The cause is probably that "picture-options" keeps the same value
    on every run ("zoom" -> "zoom"), so dconf does not emit a change signal
    for it and GNOME Shell does not always reconstruct the background just
    because of a URI change.

    The fix is to force picture-options to switch to another value and back
    on every run - this triggers a real "changed" signal and makes GNOME
    Shell rebuild the background more reliably.
    """
    uri = f"file://{path}"
    bg = "org.gnome.desktop.background"

    # Force a real change signal by first switching options to another
    # value - if the previous run already left it at "none", that does no
    # harm, the following lines set the final value in any case.
    subprocess.run(["gsettings", "set", bg, "picture-options", "none"], check=False)
    subprocess.run(["gsettings", "set", bg, "picture-uri", uri], check=True)
    subprocess.run(["gsettings", "set", bg, "picture-uri-dark", uri], check=False)
    subprocess.run(["gsettings", "set", bg, "picture-options", "zoom"], check=False)


def set_windows_wallpaper(path: Path):
    """Sets the Windows wallpaper with the SystemParametersInfoW Win32 call.

    This is Windows' official way of changing the wallpaper (the same
    mechanism the Settings app uses) - no separate daemon or command-line
    program is needed, unlike in GNOME's gsettings model.

    SPI_SETDESKWALLPAPER (20) combined with SPIF_UPDATEINIFILE (1) also
    writes the path to the user profile so that the choice survives a
    restart, and SPIF_SENDCHANGE (2) sends a WM_SETTINGCHANGE message that
    makes the desktop redraw immediately (without it the change would only
    show at the next login).

    Windows natively supports JPEG/PNG/BMP wallpapers, so HEIC/HEIF must be
    converted first here too (see get_display_path) - Windows has no HEIC
    support whatsoever in the wallpaper setting.

    The registry is also set to the "Fill" stretch mode (WallpaperStyle=10),
    which corresponds to GNOME's "zoom" setting.
    """
    if sys.platform != "win32":
        raise RuntimeError("set_windows_wallpaper() requires Windows")

    import winreg  # only available on Windows, hence imported here and not at the top of the file

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10")  # 10 = Fill
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
        winreg.CloseKey(key)
    except OSError:
        # Not critical - the wallpaper changes anyway, only the stretch mode
        # may stay as it was if the registry key cannot be opened for some reason.
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
            f"SystemParametersInfoW failed (GetLastError={ctypes.GetLastError()})"
        )


# --- Windows lock screen -----------------------------------------------------
# The lock screen image is set through the WinRT API LockScreen.SetImageFileAsync
# (no admin rights needed; it also switches the lock screen from "Windows
# Spotlight" to "Picture"). The API call itself takes ~0.25 s, but starting
# PowerShell takes ~1 s, so a small PowerShell helper process is kept running
# and fed image paths (base64, one per line) through its stdin. It is started
# on demand (or pre-warmed when the screen turns on, see prewarm_lock_helper)
# and closed again after LOCK_HELPER_IDLE_SECONDS of inactivity.
LOCK_HELPER_IDLE_SECONDS = 60
LOCK_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asOp = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$asAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.System.UserProfile.LockScreen, Windows.System.UserProfile, ContentType = WindowsRuntime]
while (($line = [Console]::In.ReadLine()) -ne $null) {
    try {
        $path = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($line))
        $task = $asOp.MakeGenericMethod([Windows.Storage.StorageFile]).Invoke($null, @([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)))
        $task.Wait(-1) | Out-Null
        $asAction.Invoke($null, @([Windows.System.UserProfile.LockScreen]::SetImageFileAsync($task.Result))).Wait(-1) | Out-Null
    } catch {
        Add-Content -LiteralPath $env:KULMA_LOG -Value ('[{0}] Lock screen update failed: {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $_.Exception.Message)
    }
}
"""
_lock_proc = None
_lock_idle_timer = None
_lock_guard = threading.Lock()


def _ensure_lock_helper():
    """Returns the running PowerShell helper, starting it if needed (call with _lock_guard held)."""
    global _lock_proc
    if _lock_proc is None or _lock_proc.poll() is not None:
        encoded = base64.b64encode(LOCK_SCRIPT.encode("utf-16-le")).decode()
        _lock_proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", encoded],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            env={**os.environ, "KULMA_LOG": str(LOG_PATH)},
        )
    return _lock_proc


def _close_lock_helper():
    global _lock_proc
    with _lock_guard:
        if _lock_proc is not None:
            try:
                _lock_proc.stdin.close()  # EOF: the helper finishes pending work and exits
            except (OSError, ValueError):
                pass
            _lock_proc = None


def _restart_idle_timer():
    global _lock_idle_timer
    if _lock_idle_timer is not None:
        _lock_idle_timer.cancel()
    _lock_idle_timer = threading.Timer(LOCK_HELPER_IDLE_SECONDS, _close_lock_helper)
    _lock_idle_timer.daemon = True  # must not keep a one-shot run alive
    _lock_idle_timer.start()


def prewarm_lock_helper():
    """Starts the PowerShell helper ahead of time so that set_lock_screen() is fast (Windows only)."""
    if sys.platform != "win32":
        return
    with _lock_guard:
        try:
            _ensure_lock_helper()
            _restart_idle_timer()
        except OSError:
            pass


def set_lock_screen(path: Path):
    """Sets the Windows lock screen image (asynchronously; failures are logged by the helper)."""
    global _lock_proc
    if sys.platform != "win32":
        return
    line = base64.b64encode(str(path.resolve()).encode("utf-8")) + b"\n"
    with _lock_guard:
        for attempt in range(2):  # a dead helper (broken pipe) is replaced once
            try:
                proc = _ensure_lock_helper()
                proc.stdin.write(line)
                proc.stdin.flush()
                _restart_idle_timer()
                return
            except (OSError, ValueError):
                _lock_proc = None
        log(tr("wp.err_lock"))


def set_wallpaper(path: Path):
    """Sets the wallpaper in the way that suits the operating system."""
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

    # The sun elevation is not linear with respect to light intensity: the
    # difference between 40° and 45° (midday) is hardly visible, but the
    # difference between -2° and +4° (near the horizon, sunrise/sunset) can
    # change the lighting from dusky to bright. Therefore a stricter
    # tolerance is used near the horizon (within "twilight_band" degrees of
    # zero), so that clearly brighter daytime photos are not chosen at night.
    if abs(current_elev) <= twilight_band:
        effective_tolerance = twilight_tolerance
        tolerance_reason = tr("wp.reason_twilight", elev=current_elev, band=twilight_band)
    else:
        effective_tolerance = tolerance
        tolerance_reason = tr("wp.reason_normal")

    # Only photos that exist on disk
    records = [r for r in records if Path(r["path"]).exists()]
    if not records:
        log(tr("wp.no_photos"))
        return

    # Only photos that have a location and a real capture time (EXIF or entered
    # by hand): otherwise the photo's sun angle is a guess (home location /
    # file modification time). If no photo has them, all photos are used so
    # that the choice does not end up empty.
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
        # Fallback: take the N nearest from the whole index. At night/dusk
        # this can still mean a brighter photo if the collection has no
        # dusky/dark photos - it is logged clearly so that the problem
        # (too few night photos in the collection) is easy to notice.
        scored.sort(key=lambda t: t[1])
        candidates = scored[:FALLBACK_CANDIDATE_COUNT]
        mode = tr("wp.mode_fallback", reason=tolerance_reason, tol=effective_tolerance)


    # Cycling: every candidate is shown once before any repeats. When all
    # current candidates have been gone through, a new round starts, so
    # changing continues endlessly and never ends up in an "options ran out"
    # state. The previous photo never comes twice in a row.
    last_choice = read_last_choice()
    history = read_history()
    unseen = [t for t in candidates if t[0]["path"] not in history and t[0]["path"] != last_choice]
    if not unseen:
        history = []  # round completed -> new round
        unseen = [t for t in candidates if t[0]["path"] != last_choice]
    if not unseen:
        # The only candidate is already the wallpaper: widen to the nearest other
        # photos so that changing succeeds (otherwise "Change now" would do nothing).
        unseen = sorted((t for t in scored if t[0]["path"] != last_choice), key=lambda t: t[1])[:FALLBACK_CANDIDATE_COUNT]
        mode += tr("wp.mode_widened")
    candidates = unseen or candidates

    # Weighted random choice: the closer, the more likely. The quadratic
    # weighting (not linear) strongly favours the nearest matches - this way
    # a more distant candidate (e.g. 5-6° away, allowed if it fits within the
    # tolerance) is chosen only rarely, even though it would technically do.
    weights = [1.0 / ((t[1] + 0.3) ** 2) for t in candidates]
    chosen_record, chosen_score, chosen_elev_diff = random.choices(candidates, weights=weights, k=1)[0]
    chosen_path = Path(chosen_record["path"])
    display_path = get_display_path(chosen_path)

    try:
        set_wallpaper(display_path)
        if sys.platform == "win32" and config.get("lock_screen", True):
            set_lock_screen(display_path)  # the lock screen always matches the desktop
        write_last_choice(str(chosen_path), (history + [chosen_record["path"]])[-HISTORY_LIMIT:])
        conversion_note = tr("wp.conv_note", name=display_path.name) if display_path != chosen_path else ""
        log(tr("wp.chosen", elev=current_elev, az=current_az, name=chosen_path.name, conv=conversion_note,
               photo_elev=chosen_record["sun_elevation"], diff=chosen_elev_diff, mode=mode, n=len(candidates)))
    except (subprocess.CalledProcessError, RuntimeError) as e:
        log(tr("wp.err_set", e=e))
        sys.exit(1)


if __name__ == "__main__":
    main()
