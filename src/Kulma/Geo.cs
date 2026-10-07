using System.Globalization;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Kulma;

/// <summary>Place names and searches through OpenStreetMap's Nominatim service.</summary>
static class Geo
{
    static readonly HttpClient Http = new()
    {
        Timeout = TimeSpan.FromSeconds(8),
        DefaultRequestHeaders = { { "User-Agent", "Kulma/2.0 (github.com/290asd/kulma)" } },
    };
    static readonly object CacheGate = new();
    static readonly Regex Coords = new(@"^\s*(-?\d+(?:[.,]\d+)?)\s*[,; ]\s*(-?\d+(?:[.,]\d+)?)\s*$");

    // Coordinates are rounded to two decimals (~1 km) both in the cache key and in the
    // request, so no exact location is sent to the service. The cache is per language.
    static string Round(double v) => Math.Round(v, 2).ToString(CultureInfo.InvariantCulture);
    static string Key(double lat, double lon) => $"{Round(lat)},{Round(lon)}" + (S.Lang == "fi" ? "" : "|" + S.Lang);

    /// <summary>Place name from places.json, e.g. "Helsinki, Suomi" (never touches the network).</summary>
    public static string? CachedPlace(double lat, double lon) =>
        Store.Read<Dictionary<string, string>>(Store.PlacesPath)?.GetValueOrDefault(Key(lat, lon));

    /// <summary>Place name, looked up from Nominatim (and cached) if needed; null without network.</summary>
    public static async Task<string?> PlaceAsync(double lat, double lon)
    {
        if (CachedPlace(lat, lon) is { } hit) return hit;
        try
        {
            var url = $"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={Round(lat)}&lon={Round(lon)}&zoom=10&accept-language={S.Lang}";
            var a = JsonNode.Parse(await Http.GetStringAsync(url))?["address"];
            string? Get(string k) => a?[k]?.GetValue<string>() is { Length: > 0 } s ? s : null;
            var name = string.Join(", ", new[] {
                Get("city") ?? Get("town") ?? Get("village") ?? Get("municipality") ?? Get("county"), Get("country"),
            }.OfType<string>());
            if (name == "") return null;
            lock (CacheGate)
            {
                var cache = Store.Read<Dictionary<string, string>>(Store.PlacesPath) ?? [];
                cache[Key(lat, lon)] = name;
                Store.Write(Store.PlacesPath, cache);
            }
            return name;
        }
        catch { return null; }  // no network etc. - try again at the next change
    }

    /// <summary>Location from text: "60.17, 24.94" or a place name (Nominatim search).</summary>
    public static async Task<(double Lat, double Lon, string Place)> GeocodeAsync(string text)
    {
        if (Coords.Match(text) is { Success: true } m)
        {
            double lat = Parse(m.Groups[1].Value), lon = Parse(m.Groups[2].Value);
            if (lat is < -90 or > 90 || lon is < -180 or > 180) throw new ArgumentException(S.T("err.coords_range"));
            return (lat, lon, $"{lat:F4}, {lon:F4}");
        }
        var url = $"https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&accept-language={S.Lang}&q={Uri.EscapeDataString(text)}";
        var found = JsonNode.Parse(await Http.GetStringAsync(url))?.AsArray();
        if (found is not [{ } first, ..]) throw new ArgumentException(S.T("err.place_not_found", ("text", text)));
        return (Parse(first["lat"]!.GetValue<string>()), Parse(first["lon"]!.GetValue<string>()),
                first["display_name"]!.GetValue<string>().Split(',')[0]);
    }

    static double Parse(string s) => double.Parse(s.Replace(',', '.'), CultureInfo.InvariantCulture);
}
