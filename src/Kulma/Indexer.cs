using System.Globalization;
using MetadataExtractor;
using MetadataExtractor.Formats.Exif;
using Directory = System.IO.Directory;

namespace Kulma;

/// <summary>
/// Walks through the photo folder (recursively) and stores, for every photo, the sun elevation and
/// azimuth at the moment it was taken. Location: GPS EXIF, otherwise the location from config.json.
/// The EXIF time is interpreted in the config time zone. overrides.json takes precedence over EXIF.
/// </summary>
static class Indexer
{
    static readonly HashSet<string> Extensions = new(StringComparer.OrdinalIgnoreCase)
        { ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif" };
    static readonly object Gate = new();  // one indexing at a time

    public static List<PhotoRecord> Run()
    {
        lock (Gate)
        {
            if (!Config.Exists) throw new InvalidOperationException(S.T("wp.err_config", ("path", Store.ConfigPath)));
            var cfg = Config.Load();
            var dir = Path.GetFullPath(cfg.PhotoDir);
            if (cfg.PhotoDir == "" || !Directory.Exists(dir)) throw new DirectoryNotFoundException(S.T("idx.err_folder", ("path", dir)));
            var tz = cfg.TimeZone;
            var overrides = Store.Read<Dictionary<string, Override>>(Store.OverridesPath) ?? [];

            var records = new List<PhotoRecord>();
            int skipped = 0, mtime = 0;
            foreach (var path in Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories))
            {
                if (!Extensions.Contains(Path.GetExtension(path))) continue;
                try
                {
                    var (taken, lat, lon) = ReadExif(path);
                    var ov = overrides.GetValueOrDefault(path);
                    if (ov is { Lat: { } oLat, Lon: { } oLon }) (lat, lon) = (oLat, oLon);

                    var source = "exif";
                    if (ov?.CaptureTime is { } ct)
                        (taken, source) = (DateTimeOffset.Parse(ct, CultureInfo.InvariantCulture).DateTime, "manual");  // wall time as written
                    if (taken is null)
                    {
                        // No EXIF time: the file modification time does NOT match the capture moment,
                        // so it is marked, and the photo is left out of the selection until fixed.
                        taken = File.GetLastWriteTime(path);
                        source = "mtime_fallback";
                        mtime++;
                    }

                    var local = DateTime.SpecifyKind(taken.Value.AddTicks(-(taken.Value.Ticks % TimeSpan.TicksPerSecond)), DateTimeKind.Unspecified);
                    var at = new DateTimeOffset(local, tz.GetUtcOffset(local));
                    bool gps = lat is not null && lon is not null;
                    var (elev, az) = Sun.Position(at, lat ?? cfg.Latitude, lon ?? cfg.Longitude);
                    records.Add(new(path, at.ToString("yyyy-MM-dd'T'HH:mm:sszzz", CultureInfo.InvariantCulture), at.Hour,
                                    Math.Round(elev, 2), Math.Round(az, 2), gps,
                                    gps ? Math.Round(lat!.Value, 5) : null, gps ? Math.Round(lon!.Value, 5) : null, source));
                }
                catch { skipped++; }
            }

            Store.Write(Store.IndexPath, records);
            Store.Log(S.T("idx.done", ("n", records.Count), ("skipped", skipped), ("gps", records.Count(r => r.Gps)), ("mtime", mtime)));
            return records;
        }
    }

    /// <summary>Capture time (DateTimeOriginal, else DateTime) and GPS location, or nulls.</summary>
    static (DateTime? Taken, double? Lat, double? Lon) ReadExif(string path)
    {
        try
        {
            var dirs = ImageMetadataReader.ReadMetadata(path);
            var exif = dirs.OfType<ExifSubIfdDirectory>().FirstOrDefault();
            var ifd0 = dirs.OfType<ExifIfd0Directory>().FirstOrDefault();
            // Some cameras (e.g. some Android phones) only store the generic DateTime tag.
            var taken = Time(exif, ExifDirectoryBase.TagDateTimeOriginal) ?? Time(ifd0, ExifDirectoryBase.TagDateTimeOriginal)
                        ?? Time(ifd0, ExifDirectoryBase.TagDateTime);
            var geo = dirs.OfType<GpsDirectory>().FirstOrDefault()?.GetGeoLocation();
            return (taken, geo?.Latitude, geo?.Longitude);
        }
        catch { return (null, null, null); }
    }

    static DateTime? Time(MetadataExtractor.Directory? dir, int tag) =>
        dir?.GetString(tag) is { } s && DateTime.TryParseExact(s.Trim('\0', ' '), "yyyy:MM:dd HH:mm:ss",
            CultureInfo.InvariantCulture, DateTimeStyles.None, out var t) ? t : null;
}
