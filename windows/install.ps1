<#
.SYNOPSIS
    Kulma - Windows-asennusskripti

.DESCRIPTION
    Kopioi kulma_index.py ja kulma_wallpaper.py paikoilleen, luo config.json:in
    (jos ei jo ole), ja rekisteröi kaksi Task Scheduler -tehtävää jotka vastaavat
    Linux-puolen systemd-timereitä:

      Kulma           - vaihtaa taustakuvan 30 min välein
      Kulma-Reindex   - päivittää kuvaindeksin joka yö klo 03:30

    EI ota tehtäviä käyttöön ennen kuin config.json on muokattu (sama periaate
    kuin Linux-puolen install.sh:ssä) - tehtävät rekisteröidään mutta niiden
    ensimmäinen ajo tapahtuu vasta seuraavan aikataulun mukaan, joten ehdit
    muokata configin ja ajaa ensimmäisen indeksoinnin manuaalisesti ensin.

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
Write-Host "-> Skriptit kopioitu: $BinDir"

$configPath = Join-Path $ConfigDir "config.json"
if (Test-Path $configPath) {
    Write-Host "-> config.json on jo olemassa, ei ylikirjoiteta ($configPath)"
} else {
    Copy-Item (Join-Path $ScriptDir "config.example.json") $configPath
    Write-Host "-> config.json luotu: $configPath"
}

# --- Riippuvuudet -------------------------------------------------------------

Write-Host ""
Write-Host "-> Asennetaan/varmistetaan Python-riippuvuudet (astral, Pillow, pillow-heif)..."
& $pythonExe -m pip install --quiet astral Pillow pillow-heif
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pip install epaonnistui - asenna riippuvuudet manuaalisesti: $pythonExe -m pip install astral Pillow pillow-heif"
}

# --- Task Scheduler -----------------------------------------------------------

$wallpaperScript = Join-Path $BinDir "kulma_wallpaper.py"
$reindexScript   = Join-Path $BinDir "kulma_index.py"

# Kulma: taustakuvan vaihto 30 min valein, jatkuu loputtomiin.
# HUOM: -RepetitionDuration jatetaan tarkoituksella pois. Jos sita ei anneta,
# Task Scheduler toistaa laukaisinta loputtomiin - [TimeSpan]::MaxValue
# taas muuntuu XML:ssa muotoon P99999999DT23H59M59S, joka ylittaa Task
# Schedulerin skeeman sallitun kestoarvon ja aiheuttaa
# "task XML contains a value which is incorrectly formatted or out of range".
$wallpaperAction  = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$wallpaperScript`""
$wallpaperTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 30)
$wallpaperSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Kulma" `
    -Action $wallpaperAction -Trigger $wallpaperTrigger -Settings $wallpaperSettings `
    -Description "Vaihtaa tyopoydan taustakuvan auringon korkeuskulman mukaan." `
    -Force | Out-Null
Write-Host "-> Task Scheduler -tehtava 'Kulma' rekisteroity (30 min valein)"

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
Write-Host "  1. Muokkaa $configPath (kuvakansio, sijainti, aikavyohyke)."
Write-Host "  2. Aja ensimmainen indeksointi:"
Write-Host "       & `"$pythonExe`" `"$reindexScript`""
Write-Host "  3. Testaa taustakuvan vaihto heti (ei tarvitse odottaa 30 min):"
Write-Host "       Start-ScheduledTask -TaskName 'Kulma'"
Write-Host "  4. Tehtavat on jo rekisteroity ja ajastettu - mitaan erikseen"
Write-Host "     kayttoonottoa ei tarvita, kunhan config.json ja indeksi ovat kunnossa."
