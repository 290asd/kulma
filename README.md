# Kulma

Ubuntu-työpöydän taustakuva vaihtuu automaattisesti kuvaan, joka on otettu
mahdollisimman samanlaisessa auringonvalossa kuin mikä juuri nyt vallitsee
omalla sijainnillasi.

Idea: pelkkä kellonaika ei kerro miltä valo näyttää — marraskuun klo 16 ja
kesäkuun klo 16 näyttävät täysin erilaisilta. **Auringon korkeuskulma**
sen sijaan kertoo suoraan valon laadun vuodenajasta riippumatta, joten
Kulma laskee sen jokaiselle kuvallesi (EXIF-datan perusteella) ja
vertaa sitä nykyiseen aurinkokulmaan valitessaan taustakuvaa.

## Miten se toimii

1. **`kulma_index.py`** käy kuvakansiosi läpi (rekursiivisesti), lukee
   jokaisesta kuvasta EXIF:n ottoajan ja mahdollisen GPS-sijainnin, ja
   laskee `astral`-kirjastolla mikä oli auringon korkeuskulma ja atsimuutti
   sillä hetkellä kun kuva otettiin. Tulos tallennetaan `index.json`:iin.
2. **`kulma_wallpaper.py`** laskee auringon korkeuskulman *juuri nyt*, ja
   valitsee indeksistä kuvan jonka tallennettu kulma on lähimpänä —
   painotetulla satunnaisvalinnalla, jotta valinta vaihtelee muttei ole
   täysin sattumanvarainen. Sama kuva ei voi tulla kahdesti peräkkäin.
   Valintaan otetaan vain kuvat joilla on sijainti (GPS) ja ottoaika;
   muut jätetään pois, koska niiden aurinkokulma olisi arvaus.
3. Kaksi systemd-timeria ajaa nämä automaattisesti: taustakuva vaihtuu
   oletuksena kerran tunnissa, ja indeksi päivittyy öisin uusien kuvien
   varalta.

Kaikki tapahtuu paikallisesti — kuvat pysyvät koneellasi, ei pilvipalveluita.

**Windows-käyttäjä?** Katso [`windows/README_WINDOWS.md`](windows/README_WINDOWS.md) —
samat `kulma_index.py`/`kulma_wallpaper.py`-skriptit toimivat sellaisenaan,
mutta taustakuvan asetus ja ajastus hoidetaan Windowsin omilla mekanismeilla
(systemd-timerien sijaan tray-sovellus ja Task Scheduler).

## Riippuvuudet

- Python 3.9+ (zoneinfo-tuki)
- GNOME-työpöytä (`gsettings`-pohjainen taustakuvan asetus)
- systemd (user-tason timerit)

Python-paketit:
```bash
pip install astral pillow-heif --break-system-packages
```
(`pillow-heif` tarvitaan jos kuvasi ovat `.HEIC`/`.HEIF`-muodossa, esim.
iPhonen oletusformaatti — ilman sitä näiden kuvien EXIF-ottoaikaa ja
GPS:ää ei voida lukea, ja järjestelmä joutuu turvautumaan epätarkkaan
tiedoston muokkausaikaan.)

Pillow (`PIL`) tulee yleensä valmiiksi asennettuna Ubuntussa. Jos ei:
```bash
pip install Pillow --break-system-packages
```

## Asennus

```bash
git clone <tämän repon osoite> kulma
cd kulma
./install.sh
```

Skripti kopioi tiedostot paikoilleen (`~/.local/bin/`, `~/.config/kulma/`,
`~/.config/systemd/user/`) mutta ei ota mitään käyttöön automaattisesti,
koska ensin pitää muokata konfiguraatio.

### 1. Muokkaa config.json

```bash
nano ~/.config/kulma/config.json
```

**Älä käytä sudoa** tämän tiedoston muokkaamiseen — se on oman
käyttäjätunnuksesi hakemisto, ei roottia varten. Sudo-muokkaus vaihtaa
tiedoston omistajaksi rootin ja rikkoo timerien toiminnan myöhemmin.

```json
{
  "photo_dir": "/home/sinä/Kuvat/Taustakuvat",
  "latitude": 60.1699,
  "longitude": 24.9384,
  "timezone": "Europe/Helsinki",
  "elevation_tolerance": 6.0,
  "twilight_elevation_tolerance": 3.0,
  "twilight_band": 12.0,
  "azimuth_weight": 0.05
}
```

| Kenttä | Selitys |
|---|---|
| `photo_dir` | Kuvakansio, käydään läpi rekursiivisesti alikansioineen. **Ei** skriptikansio. |
| `language` | Käyttöliittymän kieli: `fi` (oletus) tai `en`. Vaikuttaa lokiin ja indeksointitulosteeseen (Windowsin tray-sovelluksessa myös valikkoon ja ikkunoihin). Tekstit ovat tiedostossa `bin/kulma_i18n.py`. |
| `latitude` / `longitude` | Sijaintisi. Käytetään nykyisen aurinkokulman laskentaan, ja oletuksena kuville joilla ei ole omaa GPS-EXIF:iä. |
| `timezone` | IANA-aikavyöhyke (esim. `Europe/Helsinki`). EXIF ei sisällä aikavyöhykettä, joten tätä käytetään tulkitsemaan kuvien ottoajat oikein. |
| `elevation_tolerance` | Kuinka monta astetta kuvan aurinkokulma saa poiketa nykyisestä normaalisti (kaukana horisontista, esim. keskipäivä tai syvä yö). 5-8° on hyvä lähtökohta. |
| `twilight_elevation_tolerance` | Tiukempi toleranssi jota käytetään horisontin tuntumassa (ks. `twilight_band`), koska valon voimakkuus muuttuu siellä nopeasti asteen kohden - ilman tätä yöllä saattaisi valikoitua selvästi kirkkaampia sarastus/hämäräkuvia. 2-4° on hyvä lähtökohta. |
| `twilight_band` | Kuinka monen asteen sisällä horisontista (0°) tiukempaa `twilight_elevation_tolerance`-arvoa käytetään `elevation_tolerance`-arvon sijaan. 10-15° on hyvä lähtökohta. |
| `azimuth_weight` | Kuinka paljon painoarvoa annetaan auringon suunnalle (ei pelkkä korkeus). 0 = ei väliä, 0.05-0.1 = kevyt vaikutus. |

### 2. Ensimmäinen indeksointi

```bash
python3 ~/.local/bin/kulma_index.py
```

Tuloste kertoo montako kuvaa löytyi, montako sisälsi GPS-dataa, ja mikä on
aurinkokulmien vaihteluväli kokoelmassasi. **Jos tuloste varoittaa
`mtime_fallback`-kuvista**, niiden EXIF-ottoaikaa ei saatu luettua (yleisin
syy: HEIC ilman `pillow-heif`:iä) — näiden kuvien aurinkokulma on
todennäköisesti väärin laskettu, kunnes syy korjataan.

### 3. Ota timerit käyttöön

```bash
systemctl --user daemon-reload
systemctl --user enable --now kulma.timer
systemctl --user enable --now kulma-reindex.timer
```

Jos haluat taustakuvan vaihtuvan myös silloin kun et ole kirjautuneena
(esim. lock screenin takana):
```bash
loginctl enable-linger $USER
```

Tämän jälkeen kaikki tapahtuu itsestään: lisää vain kuvia
`photo_dir`-kansioon, niin ne poimitaan mukaan seuraavassa yön
indeksoinnissa.

## Käytön aikaiset komennot

**Tila:**
```bash
systemctl --user list-timers                    # milloin seuraavaksi ajetaan
systemctl --user status kulma.service            # viimeisin ajo
```

**Manuaaliset ajot:**
```bash
systemctl --user start kulma.service             # vaihda taustakuva heti
systemctl --user start kulma-reindex.service      # päivitä indeksi heti
```

**Lokit:**
```bash
tail -f ~/.config/kulma/kulma.log                # oma lokitiedosto
journalctl --user -u kulma.service -f             # systemdin loki
```

**Pysäytys / poisto käytöstä:**
```bash
systemctl --user disable --now kulma.timer
systemctl --user disable --now kulma-reindex.timer
```

**Vaihtoväli tiheämmäksi** (esim. 15 min tunnin sijaan) — muokkaa
`~/.config/systemd/user/kulma.timer`:
```ini
[Timer]
OnCalendar=*:0/15
```
ja sen jälkeen:
```bash
systemctl --user daemon-reload
systemctl --user restart kulma.timer
```

## Tiedostorakenne asennuksen jälkeen

```
~/.local/bin/
  kulma_index.py
  kulma_wallpaper.py
~/.config/kulma/
  config.json          # asetukset
  index.json           # kuvaindeksi (luodaan automaattisesti)
  last_choice.json      # edellinen valinta, estää peräkkäisen toiston
  kulma.log             # lokitiedosto
~/.config/systemd/user/
  kulma.service
  kulma.timer
  kulma-reindex.service
  kulma-reindex.timer
~/.cache/kulma/converted/
  <kuvanimi>.jpg       # HEIC/HEIF-kuvista automaattisesti tehdyt JPEG-muunnokset
```

## HEIC/HEIF-kuvat ja taustakuvan näyttö

GNOME:n oma taustakuvan renderöinti (`gdk-pixbuf`) ei useimmilla
Linux-jakeluilla tue HEIC/HEIF-formaattia lainkaan (puuttuu oletuksena
patenttisyistä), vaikka Kulma itse pystyy lukemaan HEIC-tiedostojen
EXIF-datan `pillow-heif`:in kautta indeksointivaiheessa. Jos HEIC-kuva
asetettaisiin suoraan taustakuvaksi, `gsettings`-komento "onnistuisi"
mutta työpöytä ei näyttäisi mitään uutta.

Tämän vuoksi `kulma_wallpaper.py` muuntaa valitun HEIC/HEIF-kuvan
JPEG:ksi `~/.cache/kulma/converted/`-kansioon ennen taustakuvaksi
asettamista. Muunnos tehdään vain kerran per kuva - toistuvilla ajoilla
käytetään jo valmiiksi muunnettua tiedostoa. Kansion voi tyhjentää
milloin tahansa, se rakentuu automaattisesti uudelleen tarvittaessa:
```bash
rm -rf ~/.cache/kulma/converted
```

## Tunnetut rajoitukset

- Linuxilla vain GNOME (`gsettings`-pohjainen). Muille työpöytäympäristöille
  `set_gnome_wallpaper()`-funktio pitää korvata vastaavalla komennolla.
  Windowsille on oma toteutus, ks. `windows/README_WINDOWS.md`.
- Kuvakokoelma kannattaa olla riittävän laaja ja eri vuodenajoilta, jotta
  aurinkokulmia löytyy tasaisesti ympäri vuorokauden ja vuoden. Pienellä
  kokoelmalla moni ajo turvautuu varajärjestelmään (lähimmät ehdokkaat
  toleranssin ulkopuolelta).
- GPS-EXIF puuttuu monista kuvista (esim. jos sijaintitiedot on
  poistettu jakamisen yhteydessä). Tällaiset kuvat (ja kuvat joilta puuttuu
  EXIF-ottoaika) jätetään pois taustakuvavalinnasta, kunnes sijainti ja aika
  on annettu käsin: Windowsissa tray-sovellus kysyy ne, Linuxissa lisää ne
  tiedostoon `~/.config/kulma/overrides.json`
  (`{"<kuvan polku>": {"lat": 60.17, "lon": 24.94, "capture_time": "2019-06-16T03:57:00"}}`)
  ja aja `kulma_index.py` uudelleen. Jos yhdelläkään kuvalla ei ole tietoja,
  käytetään kaikkia kuvia (sijaintina config.jsonin oletussijainti).

## Lisenssi

MIT
