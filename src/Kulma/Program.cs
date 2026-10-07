using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace Kulma;

static class Program
{
    public const string GitHubUrl = "https://github.com/290asd/kulma";

    [STAThread]
    static int Main(string[] args)
    {
        // Numbers and dates in a fixed format (dot decimals) whatever the regional settings are.
        CultureInfo.DefaultThreadCurrentCulture = CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        if (args.Contains("--selftest")) return SelfTest();
        if (args.Contains("--index")) { Indexer.Run(); return 0; }

        using var mutex = new Mutex(true, "Kulma-Tray", out bool first);  // one tray at a time
        if (!first) return 0;
        ApplicationConfiguration.Initialize();
        Application.ThreadException += (_, e) => Store.Log(e.Exception.ToString());
        Application.Run(new Tray());
        return 0;
    }

    /// <summary>Checks the sun formula against the stored index (made with astral) and the change timing.</summary>
    static int SelfTest()
    {
        var cfg = Config.Load();
        var records = Store.Read<List<PhotoRecord>>(Store.IndexPath) ?? [];
        double worst = 0;
        foreach (var r in records)
        {
            var (elev, az) = Sun.Position(DateTimeOffset.Parse(r.CaptureTime), r.Lat ?? cfg.Latitude, r.Lon ?? cfg.Longitude);
            worst = Math.Max(worst, Math.Max(Math.Abs(elev - r.SunElevation), Picker.CircularDiff(az, r.SunAzimuth)));
        }
        Console.WriteLine($"sun: {records.Count} records, largest difference {worst:F4}°");

        var aligned = new Config(new() { ["interval_minutes"] = 30 });
        var plain = new Config(new() { ["interval_minutes"] = 30, ["align_to_clock"] = false });
        var at = new DateTime(2026, 10, 7, 10, 7, 0);
        bool ok = worst < 0.02
            && Tray.SecondsUntilNextChange(aligned, at) == 23 * 60 + 0.5
            && Tray.SecondsUntilNextChange(plain, at) == 30 * 60
            && Tray.ChangeIsDue(aligned, at.AddMinutes(-8), at)        // 9:59 -> the 10:00 change was missed
            && !Tray.ChangeIsDue(aligned, at.AddMinutes(-6), at)       // 10:01 -> next one is 10:30
            && Tray.ChangeIsDue(plain, at.AddMinutes(-30), at)
            && !Tray.ChangeIsDue(plain, at.AddMinutes(-29), at);
        Console.WriteLine(ok ? "OK" : "FAILED");
        return ok ? 0 : 1;
    }
}

/// <summary>The notification area icon, its menu and the wallpaper change timer.</summary>
sealed class Tray : ApplicationContext
{
    const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    public static readonly Icon AppIcon = MakeIcon(grey: false);
    static readonly Icon PausedIcon = MakeIcon(grey: true);

    readonly NotifyIcon icon = new() { Icon = AppIcon, Text = "Kulma" };
    readonly ToolStripMenuItem status = new() { Enabled = false }, location = new() { Enabled = false }, taken = new() { Enabled = false };
    readonly ToolStripMenuItem change = new(), pause = new(), reindex = new(), settings = new(), log = new(),
                               autostart = new(), about = new(), quit = new();
    readonly SemaphoreSlim busy = new(1, 1);
    readonly Dictionary<Type, Form> windows = [];
    readonly PowerWatcher power;
    CancellationTokenSource wake = new();  // cancelled = change right away
    DateTime lastChange = DateTime.Now;
    bool paused, quitting;

    public Tray()
    {
        change.Font = new Font(change.Font, FontStyle.Bold);  // the left-click action
        change.Click += (_, _) => _ = ChangeNowAsync();
        pause.Click += async (_, _) => { paused = !paused; await RefreshAsync(); };
        reindex.Click += async (_, _) => await ReindexAndReviewAsync();
        settings.Click += (_, _) => ShowSettings();
        log.Click += (_, _) => Open(Store.LogPath);
        autostart.Click += (_, _) => SetAutostart(!AutostartEnabled);
        about.Click += (_, _) => Show(() => new AboutForm());
        quit.Click += (_, _) => Quit();

        var menu = new ContextMenuStrip();
        menu.Items.AddRange([status, location, taken, new ToolStripSeparator(), change, pause, reindex,
                             new ToolStripSeparator(), settings, log, autostart, about, new ToolStripSeparator(), quit]);
        menu.Opening += (_, _) => UpdateMenu();
        icon.ContextMenuStrip = menu;
        icon.MouseClick += (_, e) => { if (e.Button == MouseButtons.Left) _ = ChangeNowAsync(); };
        icon.Visible = true;

        Boost();
        power = new PowerWatcher(OnWake);
        if (!Config.Exists) ShowSettings();  // first start: ask for the settings
        _ = LoopAsync();
    }

    async Task LoopAsync()
    {
        while (!quitting)
        {
            if (!paused) await ChangeNowAsync();
            try { await Task.Delay(TimeSpan.FromSeconds(SecondsUntilNextChange(Config.Load(), DateTime.Now)), wake.Token); }
            catch (TaskCanceledException) { }
            if (wake.IsCancellationRequested) wake = new();
        }
    }

    /// <summary>Changes the wallpaper in the background (the menu never waits for it).</summary>
    async Task ChangeNowAsync()
    {
        if (!await busy.WaitAsync(0)) return;  // a change is already running
        try
        {
            lastChange = DateTime.Now;
            await Task.Run(async () =>
            {
                await Picker.ChangeAsync();
                // Replaces the old nightly Task Scheduler reindex: keep the index at most a day old.
                if (File.Exists(Store.IndexPath) && File.GetLastWriteTime(Store.IndexPath) < DateTime.Now.AddDays(-1))
                    Indexer.Run();
            });
        }
        catch (Exception e) { Store.Log(S.T("err.tray", ("e", e.Message))); }
        finally { busy.Release(); }
        await RefreshAsync();
    }

    /// <summary>The screen turned on or the system resumed: if a change was missed while asleep, do it now.</summary>
    void OnWake()
    {
        if (paused || busy.CurrentCount == 0 || wake.IsCancellationRequested || !ChangeIsDue(Config.Load(), lastChange, DateTime.Now)) return;
        Store.Log(S.T("tray.resumed", ("sec", (int)(DateTime.Now - lastChange).TotalSeconds)));
        wake.Cancel();
    }

    /// <summary>With "align_to_clock" (default) the change happens on clock boundaries counted from
    /// midnight, e.g. at :00 and :30 with a 30 min interval; otherwise a full interval after the last.</summary>
    public static double SecondsUntilNextChange(Config cfg, DateTime now)
    {
        double step = cfg.IntervalMinutes * 60;
        return cfg.AlignToClock ? step - now.TimeOfDay.TotalSeconds % step + 0.5 : step;  // just after the boundary
    }

    /// <summary>True if a change should already have happened since lastChange (used after waking up).</summary>
    public static bool ChangeIsDue(Config cfg, DateTime lastChange, DateTime now)
    {
        double step = cfg.IntervalMinutes * 60;
        return cfg.AlignToClock
            ? lastChange < now.AddSeconds(-(now.TimeOfDay.TotalSeconds % step))  // a boundary has passed since
            : (now - lastChange).TotalSeconds >= step;
    }

    public async Task ReindexAndReviewAsync()
    {
        List<PhotoRecord> records;
        try { records = await Task.Run(Indexer.Run); }
        catch (Exception e)
        {
            MessageBox.Show(e.Message, S.T("err.index_failed"), MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        if (ReviewForm.Missing(records).Count == 0)
            MessageBox.Show(S.T("rev.all_ok", ("n", records.Count)), "Kulma");
        else
            Show(() => new ReviewForm());
    }

    void ShowSettings() => Show(() => new SettingsForm(async reindexNeeded =>
    {
        await RefreshAsync();  // e.g. a changed language
        if (reindexNeeded) await ReindexAndReviewAsync();
        else await SyncLockScreenAsync();
    }));

    /// <summary>Makes the lock screen match the current photo (it may have just been switched on).</summary>
    static async Task SyncLockScreenAsync()
    {
        if (Store.Read<LastChoice>(Store.LastChoicePath)?.Path is not { } last || !Config.Load().LockScreen) return;
        try { await Wallpaper.SetLockScreenAsync(await Wallpaper.DisplayPathAsync(last)); }
        catch (Exception e) { Store.Log(S.T("wp.err_lock", ("e", e.Message))); }
    }

    void Show<T>(Func<T> make) where T : Form
    {
        if (!windows.TryGetValue(typeof(T), out var form) || form.IsDisposed)
        {
            windows[typeof(T)] = form = make();
            form.Show();
        }
        form.Activate();
    }

    async Task RefreshAsync()
    {
        S.Reload();  // the language may have changed in the settings
        if (CurrentRecord() is { Lat: { } lat, Lon: { } lon }) await Geo.PlaceAsync(lat, lon);  // fills the place name cache
        icon.Icon = paused ? PausedIcon : AppIcon;
        var tip = string.Join("\n", new[] { StatusText(), LocationLine(), TimeLine() }.OfType<string>());
        icon.Text = tip.Length > 127 ? tip[..127] : tip;
    }

    void UpdateMenu()
    {
        status.Text = StatusText();
        location.Text = LocationLine() ?? "";
        location.Visible = location.Text != "";
        taken.Text = TimeLine() ?? "";
        taken.Visible = taken.Text != "";
        change.Text = S.T("menu.change");
        pause.Text = S.T("menu.pause");
        pause.Checked = paused;
        reindex.Text = S.T("menu.reindex");
        settings.Text = S.T("menu.settings");
        log.Text = S.T("menu.log");
        autostart.Text = S.T("menu.autostart");
        autostart.Checked = AutostartEnabled;
        about.Text = S.T("menu.about");
        quit.Text = S.T("menu.quit");
    }

    /// <summary>E.g. "Sun 28.6° · IMG_7377.HEIC".</summary>
    static string StatusText()
    {
        if (!Config.Exists) return S.T("status.nosettings");
        var cfg = Config.Load();
        var (elev, _) = Sun.Position(DateTimeOffset.Now, cfg.Latitude, cfg.Longitude);
        var last = Store.Read<LastChoice>(Store.LastChoicePath)?.Path;
        return S.T("status.sun", ("elev", elev), ("name", last is null ? S.T("status.none") : Path.GetFileName(last)));
    }

    static PhotoRecord? CurrentRecord() =>
        Store.Read<LastChoice>(Store.LastChoicePath)?.Path is { } last
            ? Store.Read<List<PhotoRecord>>(Store.IndexPath)?.FirstOrDefault(r => r.Path == last)
            : null;

    static string? LocationLine()
    {
        if (CurrentRecord() is not { } rec) return null;
        var loc = rec is { Lat: { } lat, Lon: { } lon } ? Geo.CachedPlace(lat, lon) ?? $"{lat:F2}°, {lon:F2}°" : S.T("loc.missing");
        return S.T("loc.line", ("loc", loc));
    }

    static string? TimeLine()
    {
        if (CurrentRecord() is not { } rec) return null;
        var when = DateTimeOffset.Parse(rec.CaptureTime).ToString(S.T("time.fmt"))
                   + (rec.TimeSource == "mtime_fallback" ? S.T("time.estimate") : "");
        return S.T("time.line", ("when", when));
    }

    /// <summary>On only if it starts this exe (not e.g. the old Python version).</summary>
    static bool AutostartEnabled
    {
        get
        {
            using var key = Registry.CurrentUser.OpenSubKey(RunKey);
            return key?.GetValue("Kulma") is string cmd && cmd.Contains(Environment.ProcessPath!, StringComparison.OrdinalIgnoreCase);
        }
    }

    /// <summary>Start with Windows on/off. Turning it on also adds a Start Menu shortcut, so that the
    /// app can be started again after "Quit" without logging out and in.</summary>
    static void SetAutostart(bool on)
    {
        using var key = Registry.CurrentUser.CreateSubKey(RunKey);
        if (!on) { key.DeleteValue("Kulma", throwOnMissingValue: false); return; }
        key.SetValue("Kulma", $"\"{Environment.ProcessPath}\"");
        try
        {
            dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell")!)!;
            var lnk = shell.CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Kulma.lnk"));
            lnk.TargetPath = Environment.ProcessPath;
            lnk.Description = S.T("about.desc");
            if (File.Exists(Store.IconIco)) lnk.IconLocation = Store.IconIco + ",0";
            lnk.Save();
        }
        catch (Exception e) { Store.Log(e.Message); }
    }

    static void Open(string path)
    {
        try { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); }
        catch (Exception e) { Store.Log(e.Message); }
    }

    void Quit()
    {
        quitting = true;
        wake.Cancel();
        power.DestroyHandle();
        icon.Visible = false;
        Application.Exit();
    }

    /// <summary>Keeps the tray responsive right after waking up: slightly higher priority and no
    /// EcoQoS power throttling (Windows may otherwise slow down background processes).</summary>
    static void Boost()
    {
        try
        {
            using var me = Process.GetCurrentProcess();
            me.PriorityClass = ProcessPriorityClass.AboveNormal;
            var state = new PowerThrottlingState { Version = 1, ControlMask = 1, StateMask = 0 };  // execution speed throttling off
            SetProcessInformation(me.Handle, 4 /* ProcessPowerThrottling */, ref state, (uint)Marshal.SizeOf<PowerThrottlingState>());
        }
        catch { }
    }

    /// <summary>The icon made at install time by the old installer (set square + sun, from Apple's emoji
    /// images, which may not be distributed), or a drawn sun if it is missing. Paused = grey.</summary>
    static Icon MakeIcon(bool grey)
    {
        using var bitmap = new Bitmap(32, 32);
        using (var g = Graphics.FromImage(bitmap))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.InterpolationMode = InterpolationMode.HighQualityBicubic;
            using var attributes = new ImageAttributes();
            if (grey) attributes.SetColorMatrix(new ColorMatrix([[.3f, .3f, .3f, 0, 0], [.59f, .59f, .59f, 0, 0],
                                                                 [.11f, .11f, .11f, 0, 0], [0, 0, 0, 1, 0], [0, 0, 0, 0, 1]]));
            if (File.Exists(Store.IconPng))
            {
                using var source = Image.FromFile(Store.IconPng);
                g.DrawImage(source, new Rectangle(0, 0, 32, 32), 0, 0, source.Width, source.Height, GraphicsUnit.Pixel, attributes);
            }
            else
            {
                var color = grey ? Color.FromArgb(150, 150, 150) : Color.FromArgb(255, 196, 40);
                using var brush = new SolidBrush(color);
                using var pen = new Pen(color, 2);
                g.FillEllipse(brush, 9, 9, 14, 14);
                for (int a = 0; a < 8; a++)  // rays
                {
                    float dx = MathF.Cos(a * MathF.PI / 4), dy = MathF.Sin(a * MathF.PI / 4);
                    g.DrawLine(pen, 16 + 10 * dx, 16 + 10 * dy, 16 + 14.5f * dx, 16 + 14.5f * dy);
                }
            }
        }
        return Icon.FromHandle(bitmap.GetHicon());
    }

    [StructLayout(LayoutKind.Sequential)]
    struct PowerThrottlingState { public uint Version, ControlMask, StateMask; }

    [DllImport("kernel32.dll")]
    static extern bool SetProcessInformation(IntPtr process, int infoClass, ref PowerThrottlingState info, uint size);
}

/// <summary>A hidden window that reports power events: the display turning on (this is how a wake from
/// Modern Standby shows up) and the classic resume-from-sleep messages.</summary>
sealed class PowerWatcher : NativeWindow
{
    static Guid displayState = new("6FE69556-704A-47A0-8F24-C28D936FDA47");  // GUID_CONSOLE_DISPLAY_STATE
    const int WM_POWERBROADCAST = 0x218, PBT_APMRESUMESUSPEND = 0x7, PBT_APMRESUMEAUTOMATIC = 0x12, PBT_POWERSETTINGCHANGE = 0x8013;
    readonly Action onWake;

    public PowerWatcher(Action onWake)
    {
        this.onWake = onWake;
        CreateHandle(new CreateParams());  // a top-level window: message-only windows get no broadcasts
        RegisterPowerSettingNotification(Handle, ref displayState, 0 /* DEVICE_NOTIFY_WINDOW_HANDLE */);
    }

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == WM_POWERBROADCAST)
        {
            try
            {
                if ((int)m.WParam is PBT_APMRESUMESUSPEND or PBT_APMRESUMEAUTOMATIC) onWake();
                else if ((int)m.WParam == PBT_POWERSETTINGCHANGE && m.LParam != 0
                         && Marshal.PtrToStructure<PowerBroadcastSetting>(m.LParam) is { Data: 1 } s  // 1 = display on
                         && s.PowerSetting == displayState)
                    onWake();
            }
            catch (Exception e) { Store.Log(e.Message); }  // a message handler must never throw
            m.Result = 1;
            return;
        }
        base.WndProc(ref m);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct PowerBroadcastSetting { public Guid PowerSetting; public uint DataLength; public byte Data; }

    [DllImport("user32.dll")]
    static extern IntPtr RegisterPowerSettingNotification(IntPtr recipient, ref Guid powerSettingGuid, int flags);
}
