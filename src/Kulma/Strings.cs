using System.Globalization;
using System.Text.RegularExpressions;

namespace Kulma;

/// <summary>
/// User interface texts in Finnish and English. The language comes from the "language" key of
/// config.json; a missing key means Finnish (old installs stay as they were).
/// Placeholders: {name} or {name:F1}. A missing English text falls back to the Finnish one.
/// </summary>
static class S
{
    public static readonly Dictionary<string, string> Languages = new() { ["fi"] = "Suomi", ["en"] = "English" };
    public static string Lang { get; private set; } = Read();

    /// <summary>Re-reads the language (call when the settings may have changed).</summary>
    public static void Reload() => Lang = Read();

    static string Read() => Config.Load().Text("language") is { } l && Languages.ContainsKey(l) ? l : "fi";

    static readonly Regex Placeholder = new(@"\{(\w+)(?::(\w+))?\}");

    public static string T(string key, params (string Name, object Value)[] args)
    {
        var text = Texts[Lang].GetValueOrDefault(key) ?? Texts["fi"][key];
        return args.Length == 0 ? text : Placeholder.Replace(text, m =>
        {
            var value = args.First(a => a.Name == m.Groups[1].Value).Value;
            return m.Groups[2].Success && value is IFormattable f
                ? f.ToString(m.Groups[2].Value, CultureInfo.InvariantCulture)
                : Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";
        });
    }

    static readonly Dictionary<string, Dictionary<string, string>> Texts = new()
    {
        ["fi"] = new()
        {
            // --- tray menu ---
            ["menu.change"] = "Vaihda taustakuva nyt",
            ["menu.pause"] = "Tauko",
            ["menu.reindex"] = "Päivitä indeksi",
            ["menu.settings"] = "Asetukset…",
            ["menu.log"] = "Avaa loki",
            ["menu.autostart"] = "Käynnistä Windowsin mukana",
            ["menu.about"] = "Tietoja…",
            ["menu.quit"] = "Lopeta",
            // --- status and info lines ---
            ["status.sun"] = "Aurinko {elev:F1}° · {name}",
            ["status.none"] = "ei vielä valintaa",
            ["status.nosettings"] = "Kulma - asetukset puuttuvat",
            ["loc.line"] = "Sijainti: {loc}",
            ["loc.missing"] = "puuttuu - päivitä indeksi ja anna sijainti",
            ["time.line"] = "Otettu: {when}",
            ["time.estimate"] = " (arvio: muokkausaika)",
            ["time.fmt"] = "dd.MM.yyyy 'klo' HH:mm",
            // --- settings window ---
            ["set.title"] = "Kulma - asetukset",
            ["set.photo_dir"] = "Kuvakansio",
            ["set.lat"] = "Leveysaste",
            ["set.lon"] = "Pituusaste",
            ["set.tz"] = "Aikavyöhyke",
            ["set.interval"] = "Vaihtoväli (min)",
            ["set.language"] = "Kieli",
            ["set.lockscreen"] = "Päivitä myös lukitusruutu (sama kuva kuin työpöydällä)",
            ["set.align"] = "Vaihda tasalta kellonajalta (esim. tasan ja puoli, kun väli on 30 min)",
            ["set.browse"] = "Selaa…",
            ["set.save"] = "Tallenna",
            ["set.cancel"] = "Peruuta",
            ["set.check"] = "Tarkista arvot:\n{err}",
            ["set.nofolder"] = "Kuvakansiota ei löydy: {path}",
            ["set.saved"] = "Tallennettu.",
            ["set.saved_reindex"] = "Tallennettu. Indeksi päivittyy taustalla, ja puuttuvat tiedot kysytään sen jälkeen.",
            // --- about window ---
            ["about.title"] = "Kulma - tietoja",
            ["about.version"] = "Versio {v}",
            ["about.desc"] = "Vaihtaa työpöydän taustakuvan kuvaan, joka on otettu samanlaisessa auringonvalossa kuin juuri nyt.",
            ["about.libs"] = "Kirjastot",
            ["about.lib_dotnet"] = "ohjelmointialusta, ikkunat ja ilmoitusalueen kuvake",
            ["about.lib_mdx"] = "EXIF-tiedot (ottoaika, GPS)",
            ["about.lib_wic"] = "kuvien luku ja HEIC-muunnos",
            ["about.lib_sun"] = "auringon korkeuskulma ja suunta",
            ["about.library"] = "Kuvakirjasto",
            ["about.noindex"] = "Ei indeksoituja kuvia",
            ["about.photos"] = "Kuvia",
            ["about.located"] = "Sijainti tiedossa",
            ["about.nolocation"] = "Sijainti puuttuu",
            ["about.notime"] = "Ottoaika puuttuu",
            ["about.incomplete"] = "Puutteellisia",
            ["about.excluded"] = "ei mukana taustakuvavalinnassa",
            ["about.toplocs"] = "Yleisimmät sijainnit",
            ["about.place_n"] = "{name}: {n} kuvaa ({pct})",
            ["about.credits"] = "Paikannimet: OpenStreetMap Nominatim. Kuvake: kulmaviivain ja aurinko, Applen emoji-kuvista.",
            ["about.close"] = "Sulje",
            // --- missing details window ---
            ["rev.title"] = "Kulma - puuttuvat sijainti- ja aikatiedot",
            ["rev.updating"] = "Kulma - päivitetään indeksiä…",
            ["rev.intro"] =
                "Jokaisella kuvalla pitää olla sijainti ja ottoaika, jotta aurinkokulma lasketaan oikein ja tiedot "
                + "voidaan näyttää. {n} kuvalta ne puuttuvat kokonaan tai osittain, ja ne jätetään pois "
                + "taustakuvavalinnasta kunnes tiedot on annettu. "
                + "Valitse kuvia (Ctrl/Shift), anna sijainti ja/tai aika ja paina «{apply}». "
                + "Kuvatiedostoja ei muokata.",
            ["rev.col_photo"] = "Kuva",
            ["rev.col_loc"] = "Sijainti",
            ["rev.col_time"] = "Ottoaika",
            ["rev.select"] = "Valitse kuva",
            ["rev.missing"] = "puuttuu",
            ["rev.time_missing"] = "puuttuu (muokattu {t})",
            ["rev.nopreview"] = "(esikatselu ei onnistu)",
            ["rev.lbl_place"] = "Sijainti (paikannimi tai lat, lon)",
            ["rev.lbl_time"] = "Ottoaika (VVVV-KK-PP HH:MM)",
            ["rev.apply"] = "Käytä valituille",
            ["rev.done"] = "Valmis",
            ["rev.pick_first"] = "Valitse ensin kuvia listasta.",
            ["rev.enter_something"] = "Anna sijainti ja/tai ottoaika.",
            ["rev.bad_time"] = "Ottoajan muoto: 2019-12-25 13:30 tai 25.12.2019 13:30",
            ["rev.close_q"] =
                "{n} kuvalta puuttuu vielä sijainti tai ottoaika. Jokaisella kuvalla pitää olla molemmat.\n\n"
                + "Suljetaanko silti? Ne jätetään pois taustakuvavalinnasta, kunnes tiedot on annettu.",
            ["rev.all_ok"] = "Indeksi päivitetty ({n} kuvaa). Kaikilla kuvilla on sijainti ja ottoaika.",
            // --- errors ---
            ["err.index_failed"] = "Kulma - indeksointi epäonnistui",
            ["err.coords_range"] = "Koordinaatit ovat alueen ulkopuolella",
            ["err.place_not_found"] = "Paikkaa ei löytynyt: {text}",
            ["err.tray"] = "Tray: virhe taustakuvan vaihdossa: {e}",
            ["tray.resumed"] = "Herätty lepotilasta tai näyttö päälle ({sec} s edellisestä vaihdosta) - vaihdetaan taustakuva heti",
            // --- wallpaper change (log) ---
            ["wp.err_config"] = "Virhe: config-tiedostoa ei löydy ({path}).",
            ["wp.err_index"] = "Virhe: indeksiä ei löydy ({path}). Valitse valikosta «Päivitä indeksi».",
            ["wp.no_photos"] = "Indeksissä ei ole yhtään olemassa olevaa kuvaa. Päivitä indeksi.",
            ["wp.reason_twilight"] = "hämärävyöhyke (|{elev:F1}°| <= {band}°)",
            ["wp.reason_normal"] = "normaali",
            ["wp.mode_tol"] = "toleranssin sisällä ({reason}, {tol}°)",
            ["wp.mode_fallback"] = "fallback (lähimmät ehdokkaat, {reason} toleranssi {tol}° ei riittänyt)",
            ["wp.mode_widened"] = ", laajennettu (ainoa ehdokas oli jo käytössä)",
            ["wp.conv_note"] = " (näytetään JPEG-muunnoksena: {name})",
            ["wp.chosen"] =
                "Aurinkokulma nyt: {elev:F1}° (atsimuutti {az:F1}°) | "
                + "valittu kuva: {name}{conv} (kuvan kulma {photo_elev:F1}°, "
                + "ero {diff:F1}°) | {mode}, {n} ehdokasta",
            ["wp.err_lock"] = "Lukitusruudun päivitys epäonnistui: {e}",
            // --- indexing ---
            ["idx.err_folder"] = "Virhe: kansiota ei löydy: {path}",
            ["idx.done"] =
                "Indeksi päivitetty: {n} kuvaa ({skipped} ohitettu virheiden vuoksi), GPS-sijainti {gps} kuvalla, "
                + "ottoaika arvioitu tiedoston muokkausajasta {mtime} kuvalle",
        },
        ["en"] = new()
        {
            // --- tray menu ---
            ["menu.change"] = "Change wallpaper now",
            ["menu.pause"] = "Pause",
            ["menu.reindex"] = "Update index",
            ["menu.settings"] = "Settings…",
            ["menu.log"] = "Open log",
            ["menu.autostart"] = "Start with Windows",
            ["menu.about"] = "About…",
            ["menu.quit"] = "Quit",
            // --- status lines ---
            ["status.sun"] = "Sun {elev:F1}° · {name}",
            ["status.none"] = "no photo chosen yet",
            ["status.nosettings"] = "Kulma - settings missing",
            ["loc.line"] = "Location: {loc}",
            ["loc.missing"] = "missing - update the index and enter a location",
            ["time.line"] = "Taken: {when}",
            ["time.estimate"] = " (estimate: file modified time)",
            ["time.fmt"] = "dd MMM yyyy, HH:mm",
            // --- settings window ---
            ["set.title"] = "Kulma - settings",
            ["set.photo_dir"] = "Photo folder",
            ["set.lat"] = "Latitude",
            ["set.lon"] = "Longitude",
            ["set.tz"] = "Time zone",
            ["set.interval"] = "Change interval (min)",
            ["set.language"] = "Language",
            ["set.lockscreen"] = "Also update the lock screen (same photo as the desktop)",
            ["set.align"] = "Change on the clock (e.g. on the hour and half hour with a 30 min interval)",
            ["set.browse"] = "Browse…",
            ["set.save"] = "Save",
            ["set.cancel"] = "Cancel",
            ["set.check"] = "Check the values:\n{err}",
            ["set.nofolder"] = "Photo folder not found: {path}",
            ["set.saved"] = "Saved.",
            ["set.saved_reindex"] = "Saved. The index is updating in the background; missing details will be asked afterwards.",
            // --- about window ---
            ["about.title"] = "Kulma - about",
            ["about.version"] = "Version {v}",
            ["about.desc"] = "Changes the desktop wallpaper to a photo taken in similar sunlight to the sun right now.",
            ["about.libs"] = "Libraries",
            ["about.lib_dotnet"] = "programming platform, windows and notification area icon",
            ["about.lib_mdx"] = "EXIF data (capture time, GPS)",
            ["about.lib_wic"] = "reading images and HEIC conversion",
            ["about.lib_sun"] = "sun elevation and direction",
            ["about.library"] = "Photo library",
            ["about.noindex"] = "No indexed photos",
            ["about.photos"] = "Photos",
            ["about.located"] = "Location known",
            ["about.nolocation"] = "Location missing",
            ["about.notime"] = "Capture time missing",
            ["about.incomplete"] = "Incomplete",
            ["about.excluded"] = "excluded from wallpaper selection",
            ["about.toplocs"] = "Top locations",
            ["about.place_n"] = "{name}: {n} photos ({pct})",
            ["about.credits"] = "Place names: OpenStreetMap Nominatim. Icon: set square and sun, from Apple's emoji images.",
            ["about.close"] = "Close",
            // --- missing details window ---
            ["rev.title"] = "Kulma - missing location and time details",
            ["rev.updating"] = "Kulma - updating the index…",
            ["rev.intro"] =
                "Every photo needs a location and a capture time so that the sun angle is calculated correctly and "
                + "the details can be shown. {n} photos are missing them completely or partly, and they are left out of "
                + "the wallpaper selection until the details are entered. "
                + "Select photos (Ctrl/Shift), enter a location and/or time and press «{apply}». "
                + "The photo files are not modified.",
            ["rev.col_photo"] = "Photo",
            ["rev.col_loc"] = "Location",
            ["rev.col_time"] = "Capture time",
            ["rev.select"] = "Select a photo",
            ["rev.missing"] = "missing",
            ["rev.time_missing"] = "missing (modified {t})",
            ["rev.nopreview"] = "(preview not available)",
            ["rev.lbl_place"] = "Location (place name or lat, lon)",
            ["rev.lbl_time"] = "Capture time (YYYY-MM-DD HH:MM)",
            ["rev.apply"] = "Apply to selected",
            ["rev.done"] = "Done",
            ["rev.pick_first"] = "Select photos from the list first.",
            ["rev.enter_something"] = "Enter a location and/or a capture time.",
            ["rev.bad_time"] = "Time format: 2019-12-25 13:30 or 25.12.2019 13:30",
            ["rev.close_q"] =
                "{n} photos are still missing a location or capture time. Every photo needs both.\n\n"
                + "Close anyway? They will be left out of the wallpaper selection until the details are entered.",
            ["rev.all_ok"] = "Index updated ({n} photos). All photos have a location and a capture time.",
            // --- errors ---
            ["err.index_failed"] = "Kulma - indexing failed",
            ["err.coords_range"] = "Coordinates are out of range",
            ["err.place_not_found"] = "Place not found: {text}",
            ["err.tray"] = "Tray: error while changing the wallpaper: {e}",
            ["tray.resumed"] = "Woke up from sleep or screen turned on ({sec} s since the last change) - changing the wallpaper right away",
            // --- wallpaper change (log) ---
            ["wp.err_config"] = "Error: config file not found ({path}).",
            ["wp.err_index"] = "Error: index not found ({path}). Choose «Update index» from the menu.",
            ["wp.no_photos"] = "The index has no existing photos. Update the index.",
            ["wp.reason_twilight"] = "twilight zone (|{elev:F1}°| <= {band}°)",
            ["wp.reason_normal"] = "normal",
            ["wp.mode_tol"] = "within tolerance ({reason}, {tol}°)",
            ["wp.mode_fallback"] = "fallback (nearest candidates, {reason} tolerance {tol}° was not enough)",
            ["wp.mode_widened"] = ", widened (the only candidate was already in use)",
            ["wp.conv_note"] = " (shown as JPEG conversion: {name})",
            ["wp.chosen"] =
                "Sun elevation now: {elev:F1}° (azimuth {az:F1}°) | "
                + "chosen photo: {name}{conv} (photo elevation {photo_elev:F1}°, "
                + "diff {diff:F1}°) | {mode}, {n} candidates",
            ["wp.err_lock"] = "Updating the lock screen failed: {e}",
            // --- indexing ---
            ["idx.err_folder"] = "Error: folder not found: {path}",
            ["idx.done"] =
                "Index updated: {n} photos ({skipped} skipped because of errors), GPS location for {gps}, "
                + "capture time estimated from the file modified time for {mtime}",
        },
    };
}
