# Kulma Windowsilla

Sama idea kuin Linux-versiossa - taustakuva vaihtuu auringon korkeuskulman
mukaan, ei kellonajan. Kaksi eroa Linux-versioon:

- Taustakuva asetetaan Windowsin `SystemParametersInfoW`-rajapinnalla
  (`gsettings`-vastine), ei erillistä ohjelmaa tarvita.
- systemd-timerien sijaan käytetään Windowsin Task Scheduleria.

`kulma_index.py` ja `kulma_wallpaper.py` ovat samat tiedostot kuin
Linux-puolella (`bin/`-kansiossa) - ne tunnistavat käyttöjärjestelmän
automaattisesti (`sys.platform`) ja käyttävät oikeita polkuja/API-kutsuja.
Samaa repoa voi siis käyttää molemmilla käyttöjärjestelmillä.

## Riippuvuudet

1. **Python 3.9+** [python.org](https://www.python.org/downloads/) -
   asennuksessa muista rastittaa **"Add python.exe to PATH"**.
2. Avaa PowerShell ja asenna kirjastot (asennusskripti tekee tämän myös
   automaattisesti, mutta voit ajaa käsin):
   ```powershell
   pip install astral Pillow pillow-heif
   ```

## Asennus

```powershell
cd polku\kulma\windows
powershell -ExecutionPolicy Bypass -File install.ps1
```

(`-ExecutionPolicy Bypass` tarvitaan koska skriptejä ei ole allekirjoitettu -
vaikuttaa vain tähän yhteen ajokertaan, ei muuta järjestelmän asetuksia.)

Skripti:
- kopioi skriptit kansioon `%LOCALAPPDATA%\Kulma\bin\`
- luo `config.json`:in kansioon `%APPDATA%\Kulma\` (jos ei jo ole)
- asentaa Python-riippuvuudet
- rekisteröi kaksi Task Scheduler -tehtävää: **Kulma** (taustakuva, 30 min
  välein) ja **Kulma-Reindex** (indeksin päivitys, joka yö klo 03:30)

Tehtävät ovat rekisteröinnin jälkeen heti aktiivisia aikataulussaan, joten
tee seuraavat kaksi asiaa ennen kuin ensimmäinen ajo osuu kohdalle:

### 1. Muokkaa config.json

```powershell
notepad "$env:APPDATA\Kulma\config.json"
```

```json
{
  "photo_dir": "C:/Users/sinä/Pictures/Taustakuvat",
  "latitude": 60.1699,
  "longitude": 24.9384,
  "timezone": "Europe/Helsinki",
  "elevation_tolerance": 6.0,
  "twilight_elevation_tolerance": 3.0,
  "twilight_band": 12.0,
  "azimuth_weight": 0.05
}
```

Kenttien selitykset ovat samat kuin pääprojektin READMEssä. `photo_dir`
voidaan kirjoittaa kauttaviivoilla (`C:/Users/...`) - Python käsittelee
sen oikein myös Windowsilla.

### 2. Ensimmäinen indeksointi

```powershell
python "$env:LOCALAPPDATA\Kulma\bin\kulma_index.py"
```

### 3. Testaa heti (valinnainen)

Ei tarvitse odottaa 30 minuuttia - tehtävän voi käynnistää käsin:

```powershell
Start-ScheduledTask -TaskName "Kulma"
```

## Käytön aikaiset komennot

**Tila:**
```powershell
Get-ScheduledTaskInfo -TaskName "Kulma"
Get-ScheduledTaskInfo -TaskName "Kulma-Reindex"
```

**Manuaaliset ajot:**
```powershell
Start-ScheduledTask -TaskName "Kulma"
Start-ScheduledTask -TaskName "Kulma-Reindex"
```

**Lokit:**
```powershell
Get-Content "$env:APPDATA\Kulma\kulma.log" -Tail 20 -Wait
```

**Pysäytys / poisto käytöstä (jättää skriptit ja asetukset paikoilleen):**
```powershell
Disable-ScheduledTask -TaskName "Kulma"
Disable-ScheduledTask -TaskName "Kulma-Reindex"
```

**Kokonaan pois (myös tehtävät poistuvat):**
```powershell
cd polku\kulma\windows
powershell -ExecutionPolicy Bypass -File uninstall.ps1
```

## Tiedostorakenne asennuksen jälkeen

```
%LOCALAPPDATA%\Kulma\bin\
  kulma_index.py
  kulma_wallpaper.py
%LOCALAPPDATA%\Kulma\cache\converted\
  <kuvanimi>.jpg        # HEIC/HEIF-kuvista tehdyt JPEG-muunnokset
%APPDATA%\Kulma\
  config.json            # asetukset
  index.json              # kuvaindeksi
  last_choice.json        # edellinen valinta
  kulma.log               # lokitiedosto
```

## Tunnetut erot Linux-versioon

- **Ei tue jatkuvaa taustaprosessia offline-tilassa** samalla tavalla kuin
  `loginctl enable-linger` - Windowsin Task Scheduler ajaa tehtävät vain kun
  käyttäjä on kirjautuneena (paitsi jos tehtävä erikseen konfiguroidaan
  ajamaan kirjautumatta, mikä vaatii tallennetun salasanan - ei oletuksena
  käytössä tässä asennusskriptissä).
- **Venytystapa (`WallpaperStyle`)** on kovakoodattu "Fill"iin (10), koska
  se vastaa lähinnä Linux-puolen `zoom`-asetusta. Voit vaihtaa sen käsin
  rekisteristä (`HKCU\Control Panel\Desktop\WallpaperStyle`) jos haluat
  jonkin muun (esim. "Fit" = 6, "Stretch" = 2, "Tile" = 0/`TileWallpaper`=1).
- **`pythonw.exe`** käytetään ajossa jotta konsoli-ikkuna ei välähdä
  näkyviin joka 30 min - jos sitä ei löydy PATH:sta samasta kansiosta kuin
  `python.exe`, käytetään `python.exe`:tä (toimii, mutta ikkuna voi välähtää).
