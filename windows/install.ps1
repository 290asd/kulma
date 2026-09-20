<#
.SYNOPSIS
    Kulma - Windows-asennusskripti

.DESCRIPTION
    Kopioi skriptit paikoilleen, asentaa riippuvuudet, kaynnistaa tray-sovelluksen
    (kulma_tray.py, aurinkokuvake ilmoitusalueella) ja lisaa sen Windowsin
    kaynnistykseen. Tray-sovellus vaihtaa taustakuvan ajastetusti ja tarjoaa
    asetusikkunan. Lisaksi rekisteroidaan Task Scheduler -tehtava:

      Kulma-Reindex   - paivittaa kuvaindeksin joka yo klo 03:30

    Vanha "Kulma"-ajastettu tehtava (taustakuvan vaihto) poistetaan, koska
    tray-sovellus korvaa sen.

.NOTES
    Ei vaadi järjestelmänvalvojan oikeuksia - tehtävät rekisteröidään
    nykyiselle käyttäjälle (Register-ScheduledTask ilman -User-parametria
    käyttää oletuksena suorittavaa käyttäjää suorittaessaan interaktiivisena).
#>

$ErrorActionPreference = "Stop"

Write-Host "Kulma - Windows-asennus"
Write-Host "======================="

# --- Polut -----------------------------------------------------------------

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir

$BinDir    = Join-Path $env:LOCALAPPDATA "Kulma\bin"
$ConfigDir = Join-Path $env:APPDATA "Kulma"

New-Item -ItemType Directory -Force -Path $BinDir    | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

# --- Python-tulkin etsintä ---------------------------------------------------
# pythonw.exe ajaa skriptin ilman että konsoli-ikkuna välähtää näkyviin joka
# 30 min - se on samassa kansiossa kuin python.exe normaalisti (venv tai
# python.org-asennus). Jos sitä ei löydy, käytetään python.exe:tä (toimii
# yhtä lailla, mutta Task Schedulerin ajossa saattaa näkyä hetken konsoli).

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "python.exe ei löydy PATH:sta. Asenna Python (python.org) ja varmista 'Add python.exe to PATH' asennuksen aikana, tai avaa uusi PowerShell-ikkuna asennuksen jälkeen."
    exit 1
}
$pythonExe  = $pythonCmd.Source
$pythonwExe = Join-Path (Split-Path $pythonExe) "pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    $pythonwExe = $pythonExe
}
Write-Host "-> Python-tulkki: $pythonwExe"

# --- Tiedostojen kopiointi ---------------------------------------------------

Copy-Item (Join-Path $RepoRoot "bin\kulma_index.py")     $BinDir -Force
Copy-Item (Join-Path $RepoRoot "bin\kulma_wallpaper.py") $BinDir -Force
Copy-Item (Join-Path $RepoRoot "bin\kulma_tray.py")      $BinDir -Force
Write-Host "-> Skriptit kopioitu: $BinDir"

$configPath = Join-Path $ConfigDir "config.json"
if (Test-Path $configPath) {
    Write-Host "-> config.json on jo olemassa, ei ylikirjoiteta ($configPath)"
}
# Jos config.json puuttuu, tray-sovellus avaa asetusikkunan ensikaynnistyksessa.

# --- Riippuvuudet -------------------------------------------------------------

Write-Host ""
Write-Host "-> Asennetaan/varmistetaan Python-riippuvuudet (astral, Pillow, pillow-heif, pystray)..."
& $pythonExe -m pip install --quiet astral Pillow pillow-heif pystray
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pip install epaonnistui - asenna riippuvuudet manuaalisesti: $pythonExe -m pip install astral Pillow pillow-heif pystray"
}

# --- Task Scheduler -----------------------------------------------------------

$reindexScript   = Join-Path $BinDir "kulma_index.py"

# Kulma: taustakuvan vaihdon hoitaa tray-sovellus (kulma_tray.py), joka
# kaynnistyy Windowsin mukana (HKCU Run). Vanha "Kulma"-ajastettu tehtava
# poistetaan, ettei taustakuva vaihtuisi kahteen kertaan.
if (Get-ScheduledTask -TaskName "Kulma" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "Kulma" -Confirm:$false
    Write-Host "-> Vanha Task Scheduler -tehtava 'Kulma' poistettu (tray korvaa sen)"
}

$trayScript = Join-Path $BinDir "kulma_tray.py"
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Kulma" `
    -Value "`"$pythonwExe`" `"$trayScript`""
Write-Host "-> Tray-sovellus kaynnistyy Windowsin mukana"

# Uudelleenasennuksessa vanha tray-instanssi pitaa sulkea ennen kuin uusi kaynnistetaan.
Get-CimInstance Win32_Process -Filter "Name LIKE 'pythonw%'" |
    Where-Object { $_.CommandLine -like "*kulma_tray.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Process $pythonwExe -ArgumentList "`"$trayScript`""
Write-Host "-> Tray-sovellus kaynnistetty (aurinkokuvake ilmoitusalueella)"

# Kulma-Reindex: kuvaindeksin paivitys joka yo klo 03:30.
$reindexAction  = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$reindexScript`""
$reindexTrigger = New-ScheduledTaskTrigger -Daily -At "03:30"
$reindexSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Kulma-Reindex" `
    -Action $reindexAction -Trigger $reindexTrigger -Settings $reindexSettings `
    -Description "Paivittaa Kulman kuvaindeksin (aurinkokulmat) joka yo." `
    -Force | Out-Null
Write-Host "-> Task Scheduler -tehtava 'Kulma-Reindex' rekisteroity (paivittain 03:30)"

Write-Host ""
Write-Host "Seuraavaksi:"
Write-Host "  1. Etsi aurinkokuvake ilmoitusalueelta (voi olla piilotettujen kuvakkeiden ^-listassa)."
Write-Host "  2. Jos config.json puuttui, asetusikkuna avautui itsestaan - tayta kuvakansio ja sijainti."
Write-Host "     Tallennus kaynnistaa indeksoinnin taustalla. Muuten: kuvake -> Asetukset."
Write-Host "  3. Vasen klikkaus kuvakkeeseen vaihtaa taustakuvan heti."
