<#
.SYNOPSIS
    Kulma - Windows install script

.DESCRIPTION
    Copies the scripts into place, installs the dependencies, creates the app
    icon, starts the tray app (kulma_tray.py, sun icon in the notification area)
    and adds it to Windows startup plus a Start Menu shortcut. The tray app
    changes the wallpaper on a schedule and provides a settings window.
    A Task Scheduler task is also registered:

      Kulma-Reindex   - updates the photo index every night at 03:30

    The old "Kulma" scheduled task (wallpaper change) is removed, because the
    tray app replaces it.

.NOTES
    Does not require administrator rights - the tasks are registered for the
    current user (Register-ScheduledTask without -User runs as the current
    user, interactively).
#>

$ErrorActionPreference = "Stop"

Write-Host "Kulma - Windows install"
Write-Host "======================="

# --- Paths -------------------------------------------------------------------

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir

$BinDir    = Join-Path $env:LOCALAPPDATA "Kulma\bin"
$ConfigDir = Join-Path $env:APPDATA "Kulma"

New-Item -ItemType Directory -Force -Path $BinDir    | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

# --- Locating the Python interpreter -----------------------------------------
# pythonw.exe runs the script without a console window flashing up. It normally
# sits in the same folder as python.exe (venv or python.org install). If it is
# not found, python.exe is used (works just as well, but a console may flash).

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "python.exe was not found on PATH. Install Python (python.org) and tick 'Add python.exe to PATH' during setup, or open a new PowerShell window after installing."
    exit 1
}
$pythonExe  = $pythonCmd.Source
$pythonwExe = Join-Path (Split-Path $pythonExe) "pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    $pythonwExe = $pythonExe
}
Write-Host "-> Python interpreter: $pythonwExe"

# --- Copying files -----------------------------------------------------------

Copy-Item (Join-Path $RepoRoot "bin\kulma_index.py")     $BinDir -Force
Copy-Item (Join-Path $RepoRoot "bin\kulma_wallpaper.py") $BinDir -Force
Copy-Item (Join-Path $RepoRoot "bin\kulma_tray.py")      $BinDir -Force
Copy-Item (Join-Path $RepoRoot "bin\kulma_i18n.py")      $BinDir -Force
Write-Host "-> Scripts copied: $BinDir"

$configPath = Join-Path $ConfigDir "config.json"
if (Test-Path $configPath) {
    Write-Host "-> config.json already exists, not overwriting ($configPath)"
}
# If config.json is missing, the tray app opens the settings window on first start.

# --- Dependencies ------------------------------------------------------------

Write-Host ""
Write-Host "-> Installing/verifying Python dependencies (astral, Pillow, pillow-heif, pystray)..."
& $pythonExe -m pip install --quiet astral Pillow pillow-heif pystray
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pip install failed - install the dependencies manually: $pythonExe -m pip install astral Pillow pillow-heif pystray"
}

# --- Icon --------------------------------------------------------------------
# The set square + sun icon is created from Apple emoji images (downloaded here,
# not stored in the repo). If the download fails, the tray app uses a drawn
# fallback icon.
& $pythonExe (Join-Path $ScriptDir "make_icon.py")
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Creating the icon failed (no network?) - using the fallback icon. You can retry with: python windows\make_icon.py"
}
$iconPath = Join-Path $env:LOCALAPPDATA "Kulma\icon\kulma.ico"

# --- Task Scheduler ----------------------------------------------------------

$reindexScript   = Join-Path $BinDir "kulma_index.py"

# Kulma: the wallpaper change is handled by the tray app (kulma_tray.py), which
# starts with Windows (HKCU Run). The old "Kulma" scheduled task is removed so
# that the wallpaper does not change twice.
if (Get-ScheduledTask -TaskName "Kulma" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "Kulma" -Confirm:$false
    Write-Host "-> Old Task Scheduler task 'Kulma' removed (the tray app replaces it)"
}

$trayScript = Join-Path $BinDir "kulma_tray.py"
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Kulma" `
    -Value "`"$pythonwExe`" `"$trayScript`""
Write-Host "-> The tray app starts with Windows"

# Start Menu shortcut, so that the app can be restarted (e.g. after choosing
# "Quit" from the menu) without logging out and in again.
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut(
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Kulma.lnk"))
$lnk.TargetPath       = $pythonwExe
$lnk.Arguments        = "`"$trayScript`""
$lnk.WorkingDirectory = $BinDir
$lnk.Description      = "Kulma - wallpaper that follows the sun angle"
if (Test-Path $iconPath) { $lnk.IconLocation = "$iconPath,0" }
$lnk.Save()
Write-Host "-> Shortcut added to the Start Menu (search for 'Kulma')"

# On reinstall, close the old tray instance before starting the new one.
Get-CimInstance Win32_Process -Filter "Name LIKE 'pythonw%'" |
    Where-Object { $_.CommandLine -like "*kulma_tray.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Process $pythonwExe -ArgumentList "`"$trayScript`""
Write-Host "-> Tray app started (sun icon in the notification area)"

# Kulma-Reindex: photo index update every night at 03:30.
$reindexAction  = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$reindexScript`""
$reindexTrigger = New-ScheduledTaskTrigger -Daily -At "03:30"
$reindexSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Kulma-Reindex" `
    -Action $reindexAction -Trigger $reindexTrigger -Settings $reindexSettings `
    -Description "Updates the Kulma photo index (sun angles) every night." `
    -Force | Out-Null
Write-Host "-> Task Scheduler task 'Kulma-Reindex' registered (daily at 03:30)"

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Find the sun icon in the notification area (it may be in the hidden-icons ^ list)."
Write-Host "  2. If config.json was missing, the settings window opened by itself - fill in the photo folder and location."
Write-Host "     Saving starts indexing in the background. Otherwise: icon -> Settings."
Write-Host "  3. Left-click the icon to change the wallpaper right away."
