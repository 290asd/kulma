using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Kulma;

/// <summary>One photo in index.json: its sun angle at the moment it was taken.</summary>
record PhotoRecord(string Path, string CaptureTime, int Hour, double SunElevation, double SunAzimuth,
                   bool Gps, double? Lat, double? Lon, string TimeSource)
{
    /// <summary>Has a real location and capture time (the sun angle is not a guess).</summary>
    [JsonIgnore] public bool Complete => Gps && TimeSource != "mtime_fallback";
}

/// <summary>Details entered by hand in overrides.json (the photo files are never modified).</summary>
class Override
{
    public double? Lat { get; set; }
    public double? Lon { get; set; }
    public string? Place { get; set; }
    public string? CaptureTime { get; set; }
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extra { get; set; }  // keeps keys we do not know
}

record LastChoice(string? Path, List<string>? History);

/// <summary>Kulma's files: settings and data in %APPDATA%\Kulma, cache and icon in %LOCALAPPDATA%\Kulma.</summary>
static class Store
{
    // The environment variables (not the known folders) so that tests can point them at a temp folder.
    static readonly string Root = Path.Combine(Environment.GetEnvironmentVariable("APPDATA")
        ?? Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Kulma");
    static readonly string LocalRoot = Path.Combine(Environment.GetEnvironmentVariable("LOCALAPPDATA")
        ?? Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Kulma");

    public static readonly string ConfigPath = Path.Combine(Root, "config.json");
    public static readonly string IndexPath = Path.Combine(Root, "index.json");
    public static readonly string OverridesPath = Path.Combine(Root, "overrides.json");
    public static readonly string PlacesPath = Path.Combine(Root, "places.json");
    public static readonly string LastChoicePath = Path.Combine(Root, "last_choice.json");
    public static readonly string LogPath = Path.Combine(Root, "kulma.log");
    public static readonly string CacheDir = Path.Combine(LocalRoot, "cache", "converted");
    public static readonly string IconPng = Path.Combine(LocalRoot, "icon", "kulma.png");
    public static readonly string IconIco = Path.Combine(LocalRoot, "icon", "kulma.ico");

    public static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,  // "Metsälä", not "Metsälä"
    };

    public static T? Read<T>(string path)
    {
        try { return JsonSerializer.Deserialize<T>(File.ReadAllText(path), Json); }
        catch { return default; }
    }

    /// <summary>Writes through a temp file, so a reader never sees a half-written file.</summary>
    public static void Write<T>(string path, T value) => WriteText(path, JsonSerializer.Serialize(value, Json));

    public static void WriteText(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path + ".tmp", text);  // UTF-8 without BOM
        File.Move(path + ".tmp", path, overwrite: true);
    }

    static readonly object LogGate = new();

    public static void Log(string msg)
    {
        var line = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {msg}";
        Console.WriteLine(line);
        lock (LogGate)
        {
            try
            {
                Directory.CreateDirectory(Root);
                File.AppendAllText(LogPath, line + "\n");
            }
            catch { }
        }
    }
}

/// <summary>config.json. Kept as a JSON object so that keys this version does not know survive a save.</summary>
class Config(JsonObject raw)
{
    public readonly JsonObject Raw = raw;

    public static bool Exists => File.Exists(Store.ConfigPath);

    public static Config Load()
    {
        try { return new(JsonNode.Parse(File.ReadAllText(Store.ConfigPath)) as JsonObject ?? []); }
        catch { return new([]); }
    }

    public void Save() => Store.WriteText(Store.ConfigPath, Raw.ToJsonString(Store.Json));

    public double Num(string key, double fallback) => Raw[key]?.Deserialize<double>() ?? fallback;  // also 30, not only 30.0
    public bool Flag(string key, bool fallback) => Raw[key]?.GetValue<bool>() ?? fallback;
    public string? Text(string key) => Raw[key]?.GetValue<string>();

    public string PhotoDir => Text("photo_dir") ?? "";
    public double Latitude => Num("latitude", 60.1699);
    public double Longitude => Num("longitude", 24.9384);
    public TimeZoneInfo TimeZone => TimeZoneInfo.FindSystemTimeZoneById(Text("timezone") ?? "Europe/Helsinki");
    public int IntervalMinutes => Math.Max(1, (int)Num("interval_minutes", 30));
    public bool AlignToClock => Flag("align_to_clock", true);
    public bool LockScreen => Flag("lock_screen", true);
}
