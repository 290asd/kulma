namespace Kulma;

/// <summary>
/// Picks the photo whose sun angle (when it was taken) is closest to the sun right now:
///   1. Photos within the elevation tolerance; stricter near the horizon ("twilight_band"), where the
///      light changes quickly per degree - otherwise bright daytime photos could come at night.
///   2. If none is within the tolerance, the nearest few (something always changes).
///   3. Cycling: every candidate is shown once before any repeats, never the same photo twice in a row.
///   4. Weighted random choice, quadratic so that the nearest matches are strongly favoured.
/// </summary>
static class Picker
{
    const int FallbackCount = 3;
    const int HistoryLimit = 500;

    public static async Task ChangeAsync()
    {
        if (!Config.Exists) { Store.Log(S.T("wp.err_config", ("path", Store.ConfigPath))); return; }
        if (Store.Read<List<PhotoRecord>>(Store.IndexPath) is not { } all) { Store.Log(S.T("wp.err_index", ("path", Store.IndexPath))); return; }
        var cfg = Config.Load();

        var (elev, az) = Sun.Position(DateTimeOffset.Now, cfg.Latitude, cfg.Longitude);
        double band = cfg.Num("twilight_band", 12.0), tolerance;
        string reason;
        if (Math.Abs(elev) <= band)
        {
            tolerance = cfg.Num("twilight_elevation_tolerance", 3.0);
            reason = S.T("wp.reason_twilight", ("elev", elev), ("band", band));
        }
        else
        {
            tolerance = cfg.Num("elevation_tolerance", 6.0);
            reason = S.T("wp.reason_normal");
        }

        var records = all.Where(r => File.Exists(r.Path)).ToList();
        if (records.Count == 0) { Store.Log(S.T("wp.no_photos")); return; }
        // Only photos with a real location and capture time - unless none has them.
        if (records.Where(r => r.Complete).ToList() is { Count: > 0 } complete) records = complete;

        double azWeight = cfg.Num("azimuth_weight", 0.05);
        var scored = records.Select(r =>
        {
            double diff = Math.Abs(r.SunElevation - elev);
            return (Record: r, Score: diff + azWeight * CircularDiff(r.SunAzimuth, az), Diff: diff);
        }).ToList();

        var candidates = scored.Where(t => t.Diff <= tolerance).ToList();
        string mode;
        if (candidates.Count > 0)
            mode = S.T("wp.mode_tol", ("reason", reason), ("tol", tolerance));
        else
        {
            candidates = scored.OrderBy(t => t.Score).Take(FallbackCount).ToList();
            mode = S.T("wp.mode_fallback", ("reason", reason), ("tol", tolerance));
        }

        var last = Store.Read<LastChoice>(Store.LastChoicePath);
        var history = last?.History ?? [];
        var unseen = candidates.Where(t => !history.Contains(t.Record.Path) && t.Record.Path != last?.Path).ToList();
        if (unseen.Count == 0)
        {
            history = [];  // round completed -> new round
            unseen = candidates.Where(t => t.Record.Path != last?.Path).ToList();
        }
        if (unseen.Count == 0)
        {
            // The only candidate is already the wallpaper: widen to the nearest other photos.
            unseen = scored.Where(t => t.Record.Path != last?.Path).OrderBy(t => t.Score).Take(FallbackCount).ToList();
            mode += S.T("wp.mode_widened");
        }
        if (unseen.Count > 0) candidates = unseen;

        var chosen = WeightedPick(candidates, t => 1.0 / Math.Pow(t.Score + 0.3, 2));
        var display = await Wallpaper.DisplayPathAsync(chosen.Record.Path);
        Wallpaper.SetDesktop(display);
        if (cfg.LockScreen)
        {
            try { await Wallpaper.SetLockScreenAsync(display); }  // the lock screen always matches the desktop
            catch (Exception e) { Store.Log(S.T("wp.err_lock", ("e", e.Message))); }
        }

        history.Add(chosen.Record.Path);
        Store.Write(Store.LastChoicePath, new LastChoice(chosen.Record.Path, history.TakeLast(HistoryLimit).ToList()));
        var conv = display != chosen.Record.Path ? S.T("wp.conv_note", ("name", Path.GetFileName(display))) : "";
        Store.Log(S.T("wp.chosen", ("elev", elev), ("az", az), ("name", Path.GetFileName(chosen.Record.Path)), ("conv", conv),
                      ("photo_elev", chosen.Record.SunElevation), ("diff", chosen.Diff), ("mode", mode), ("n", candidates.Count)));
    }

    /// <summary>Smallest difference between two azimuth angles (0-360).</summary>
    public static double CircularDiff(double a, double b)
    {
        double d = Math.Abs(a - b) % 360;
        return Math.Min(d, 360 - d);
    }

    static T WeightedPick<T>(List<T> items, Func<T, double> weight)
    {
        var weights = items.Select(weight).ToList();
        double x = Random.Shared.NextDouble() * weights.Sum();
        for (int i = 0; i < items.Count; i++)
            if ((x -= weights[i]) < 0) return items[i];
        return items[^1];
    }
}
