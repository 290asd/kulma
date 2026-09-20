# Kulma Windowsilla

Sama idea kuin Linux-versiossa - taustakuva vaihtuu auringon korkeuskulman
mukaan, ei kellonajan. Kaksi eroa Linux-versioon:

- Taustakuva asetetaan Windowsin `SystemParametersInfoW`-rajapinnalla
  (`gsettings`-vastine), ei erillistä ohjelmaa tarvita.
- systemd-timerien sijaan taustakuvan vaihtaa **tray-sovellus** (aurinkokuvake
  ilmoitusalueella) ja indeksin päivityksen hoitaa Windowsin Task Scheduler.

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
- asentaa Python-riippuvuudet (mm. `pystray`)
- käynnistää tray-sovelluksen (`kulma_tray.py`) ja lisää sen Windowsin
  käynnistykseen (`HKCU\...\Run`)
- rekisteröi Task Scheduler -tehtävän **Kulma-Reindex** (indeksin päivitys,
  joka yö klo 03:30)
- poistaa vanhan **Kulma**-ajastetun tehtävän, jos sellainen on (tray korvaa
  sen, jottei taustakuva vaihtuisi kahteen kertaan)

## Käyttö: tray-sovellus

Etsi aurinkokuvake ilmoitusalueelta (Windows 11:ssä se voi olla piilotettujen
kuvakkeiden `^`-listassa; voit raahata sen näkyviin). Kuvakkeen päällä oleva
vihjeteksti ja valikon kolme ylintä riviä näyttävät auringon korkeuskulman, nykyisen kuvan sekä sen ottopaikan ja ottoajan.

**Ottopaikka:** paikannimi (esim. "Helsinki, Suomi") haetaan kuvan GPS-koordinaateista OpenStreetMapin Nominatim-palvelusta. Palveluun lähetetään vain ~1 km tarkkuuteen pyöristetty sijainti, ja tulos tallennetaan välimuistiin (`%APPDATA%\Kulma\places.json`), joten sama paikka haetaan vain kerran. Jos verkkoa ei ole, näytetään koordinaatit; jos kuvassa ei ole GPS-dataa, näytetään "ei GPS-tietoa".

| Toiminto | Mitä tekee |
|---|---|
| Vasen klikkaus / **Vaihda taustakuva nyt** | Valitsee ja asettaa taustakuvan heti |
| **Tauko** | Keskeyttää automaattisen vaihdon (kuvake harmaaksi), uusi klikkaus jatkaa |
| **Päivitä indeksi** | Ajaa `kulma_index.py`:n taustalla (uudet kuvat mukaan) ja kysyy sen jälkeen puuttuvat tiedot, ks. alla |
| **Asetukset…** | Kuvakansio, sijainti, aikavyöhyke ja vaihtoväli |
| **Avaa loki** | Avaa `kulma.log`in |
| **Käynnistä Windowsin mukana** | Kytkee automaattikäynnistyksen päälle/pois |
| **Lopeta** | Sulkee sovelluksen |

Ensimmäisellä käynnistyksellä (kun `config.json` puuttuu) asetusikkuna
avautuu itsestään. Tallennus indeksoi kuvat taustalla, kun kuvakansio on
uusi. Sovellus lukee asetukset joka vaihdolla, joten muutokset tulevat
voimaan ilman uudelleenkäynnistystä (vaihtovälin muutos seuraavan vaihdon
jälkeen).

### Puuttuvat sijainti- ja aikatiedot

Kun indeksi päivitetään tray-valikosta (tai ensimmäisen kerran asetusten
tallennuksen jälkeen) ja joltakin kuvalta puuttuu GPS-sijainti tai
EXIF-ottoaika, avautuu ikkuna, jossa kuvat on listattu esikatselun kanssa.
Valitse kuvia (Ctrl/Shift), kirjoita **sijainti** (paikannimi, esim. `Turku`,
tai koordinaatit `60.45, 22.27`) ja/tai **ottoaika** (`2019-06-16 03:57` tai
`16.06.2019 03:57`) ja paina *Käytä valituille*. *Valmis* ajaa indeksoinnin
uudelleen uusilla tiedoilla, jolloin aurinkokulma lasketaan oikeaan paikkaan
ja aikaan.

**Jokaisella kuvalla pitää olla sijainti ja ottoaika.** Kuvat, joilta ne puuttuvat,
jätetään automaattisesti pois taustakuvavalinnasta kunnes tiedot on annettu. Jos
ikkunan sulkee kun tietoja vielä puuttuu, sovellus varoittaa. Ikkuna avautuu vain
ensimmäisessä indeksoinnissa ja aina kun indeksin päivitys ajetaan käsin valikosta;
sovelluksen käynnistys tai yöllinen indeksointi ei kysy mitään. Nykyisen kuvan ottopaikka ja ottoaika näkyvät tray-valikossa
ja kuvakkeen vihjetekstissä.

Tiedot tallennetaan tiedostoon `%APPDATA%\Kulma\overrides.json` - **kuvatiedostoja
ei muokata**. Paikannimen haku käyttää OpenStreetMapin Nominatim-palvelua
(lähetetään vain kirjoittamasi hakuteksti). Yöllinen ajastettu indeksointi
käyttää samoja tietoja mutta ei avaa ikkunaa.

### Lisäasetukset (config.json)

Asetusikkuna kattaa perusasiat. Tarkemmat säädöt tehdään suoraan tiedostoon:

```powershell
notepad "$env:APPDATA\Kulma\config.json"
```

```json
{
  "photo_dir": "C:/Users/sinä/Pictures/Taustakuvat",
  "latitude": 60.1699,
  "longitude": 24.9384,
  "timezone": "Europe/Helsinki",
  "interval_minutes": 30,
  "elevation_tolerance": 6.0,
  "twilight_elevation_tolerance": 3.0,
  "twilight_band": 12.0,
  "azimuth_weight": 0.05
}
```

Kenttien selitykset ovat samat kuin pääprojektin READMEssä.
`interval_minutes` on tray-sovelluksen vaihtoväli (oletus 30). `photo_dir`
voidaan kirjoittaa kauttaviivoilla (`C:/Users/...`) - Python käsittelee
sen oikein myös Windowsilla.

## Komentorivillä

Skriptit toimivat myös ilman tray-sovellusta:

```powershell
python "$env:LOCALAPPDATA\Kulma\bin\kulma_index.py"       # indeksointi
python "$env:LOCALAPPDATA\Kulma\bin\kulma_wallpaper.py"   # vaihda taustakuva kerran
Start-ScheduledTask -TaskName "Kulma-Reindex"                # indeksointi ajastetun tehtävän kautta
Get-Content "$env:APPDATA\Kulma\kulma.log" -Tail 20 -Wait   # loki
```

**Kokonaan pois (sulkee tray-sovelluksen, poistaa automaattikäynnistyksen ja tehtävät):**
```powershell
cd polku\kulma\windows
powershell -ExecutionPolicy Bypass -File uninstall.ps1
```

## Tiedostorakenne asennuksen jälkeen

```
%LOCALAPPDATA%\Kulma\bin\
  kulma_index.py
  kulma_wallpaper.py
  kulma_tray.py
%LOCALAPPDATA%\Kulma\cache\converted\
  <kuvanimi>.jpg        # HEIC/HEIF-kuvista tehdyt JPEG-muunnokset
%APPDATA%\Kulma\
  config.json            # asetukset
  index.json              # kuvaindeksi
  last_choice.json        # edellinen valinta
  overrides.json          # käsin annetut sijainnit ja ottoajat
  places.json             # paikannimien välimuisti
  kulma.log               # lokitiedosto
```

## Tunnetut erot Linux-versioon

- **Toimii vain kirjautuneena** (vastaava kuin Linuxin `loginctl enable-linger`
  puuttuu): tray-sovellus ja indeksointitehtävä pyörivät vain kun käyttäjä on
  kirjautuneena.
- **Venytystapa (`WallpaperStyle`)** on kovakoodattu "Fill"iin (10), koska
  se vastaa lähinnä Linux-puolen `zoom`-asetusta. Voit vaihtaa sen käsin
  rekisteristä (`HKCU\Control Panel\Desktop\WallpaperStyle`) jos haluat
  jonkin muun (esim. "Fit" = 6, "Stretch" = 2, "Tile" = 0/`TileWallpaper`=1).
- **`pythonw.exe`** käytetään ajossa jotta konsoli-ikkuna ei välähdä
  näkyviin joka 30 min - jos sitä ei löydy PATH:sta samasta kansiosta kuin
  `python.exe`, käytetään `python.exe`:tä (toimii, mutta ikkuna voi välähtää).
