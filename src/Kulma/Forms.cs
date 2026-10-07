using System.Diagnostics;
using System.Globalization;

namespace Kulma;

/// <summary>Shared look: fixed-size dialog with the Kulma icon, sized to its content.</summary>
class KulmaForm : Form
{
    protected KulmaForm(string title)
    {
        Text = title;
        Icon = Tray.AppIcon;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = false;
        AutoSize = true;
        AutoSizeMode = AutoSizeMode.GrowAndShrink;
        StartPosition = FormStartPosition.CenterScreen;
        Padding = new Padding(12);  // AutoSize adds it to the right and bottom of the content
    }

    protected void Content(Control grid)
    {
        grid.Location = new Point(12, 12);
        Controls.Add(grid);
    }

    protected static TableLayoutPanel Grid(int columns) =>
        new() { ColumnCount = columns, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink };

    protected static Label Lbl(string text, int wrap = 0, bool bold = false, Color? color = null)
    {
        var label = new Label
        {
            Text = text, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(3, 4, 3, 4),
            MaximumSize = new Size(wrap, 0), ForeColor = color ?? SystemColors.ControlText,
        };
        if (bold) label.Font = new Font(label.Font, FontStyle.Bold);
        return label;
    }

    protected static Button Btn(string text, Action click)
    {
        var b = new Button { Text = text, AutoSize = true, Margin = new Padding(4, 10, 0, 0) };
        b.Click += (_, _) => click();
        return b;
    }

    protected static FlowLayoutPanel Buttons(params Button[] buttons)
    {
        var row = new FlowLayoutPanel { AutoSize = true, Anchor = AnchorStyles.Right };
        row.Controls.AddRange(buttons);
        return row;
    }

    protected static void Error(string text) => MessageBox.Show(text, "Kulma", MessageBoxButtons.OK, MessageBoxIcon.Error);
    protected static void Info(string text) => MessageBox.Show(text, "Kulma", MessageBoxButtons.OK, MessageBoxIcon.Information);
}

/// <summary>Photo folder, home location, time zone, interval, language, clock alignment and lock screen.</summary>
sealed class SettingsForm : KulmaForm
{
    public SettingsForm(Action<bool> saved) : base(S.T("set.title"))
    {
        var cfg = Config.Load();
        // Old settings have no stored language: the app has then been in Finnish.
        var lang = cfg.Text("language") ?? (Config.Exists ? "fi" : CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "fi" ? "fi" : "en");
        var grid = Grid(3);
        TextBox Field(int row, string label, string value)
        {
            grid.Controls.Add(Lbl(label), 0, row);
            var box = new TextBox { Text = value, Width = 340 };
            grid.Controls.Add(box, 1, row);
            return box;
        }

        var dir = Field(0, S.T("set.photo_dir"), cfg.PhotoDir is "" ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyPictures), "Wallpapers").Replace('\\', '/') : cfg.PhotoDir);
        var lat = Field(1, S.T("set.lat"), cfg.Latitude.ToString(CultureInfo.InvariantCulture));
        var lon = Field(2, S.T("set.lon"), cfg.Longitude.ToString(CultureInfo.InvariantCulture));
        var tz = Field(3, S.T("set.tz"), cfg.Text("timezone") ?? "Europe/Helsinki");
        var interval = Field(4, S.T("set.interval"), cfg.IntervalMinutes.ToString(CultureInfo.InvariantCulture));
        grid.Controls.Add(Btn(S.T("set.browse"), () =>
        {
            using var pick = new FolderBrowserDialog { InitialDirectory = dir.Text };
            if (pick.ShowDialog(this) == DialogResult.OK) dir.Text = pick.SelectedPath.Replace('\\', '/');
        }), 2, 0);

        grid.Controls.Add(Lbl(S.T("set.language")), 0, 5);
        var language = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 160 };
        language.Items.AddRange(S.Languages.Values.ToArray());
        language.SelectedItem = S.Languages.GetValueOrDefault(lang, S.Languages["fi"]);
        grid.Controls.Add(language, 1, 5);
        var align = new CheckBox { Text = S.T("set.align"), Checked = cfg.AlignToClock, AutoSize = true };
        var lockScreen = new CheckBox { Text = S.T("set.lockscreen"), Checked = cfg.LockScreen, AutoSize = true };
        grid.Controls.Add(align, 0, 6);
        grid.SetColumnSpan(align, 3);
        grid.Controls.Add(lockScreen, 0, 7);
        grid.SetColumnSpan(lockScreen, 3);

        var buttons = Buttons(Btn(S.T("set.save"), Save), Btn(S.T("set.cancel"), Close));
        grid.Controls.Add(buttons, 0, 8);
        grid.SetColumnSpan(buttons, 3);
        Content(grid);

        void Save()
        {
            var photoDir = dir.Text.Trim().Replace('\\', '/');
            double latitude, longitude;
            int minutes;
            try
            {
                latitude = double.Parse(lat.Text.Trim().Replace(',', '.'), CultureInfo.InvariantCulture);
                longitude = double.Parse(lon.Text.Trim().Replace(',', '.'), CultureInfo.InvariantCulture);
                minutes = Math.Max(1, int.Parse(interval.Text.Trim(), CultureInfo.InvariantCulture));
                TimeZoneInfo.FindSystemTimeZoneById(tz.Text.Trim());
                if (!Directory.Exists(photoDir)) throw new DirectoryNotFoundException(S.T("set.nofolder", ("path", photoDir)));
            }
            catch (Exception e)
            {
                Error(S.T("set.check", ("err", e.Message)));
                return;
            }
            var config = Config.Load();
            bool reindex = config.Text("photo_dir") != photoDir || !File.Exists(Store.IndexPath);
            config.Raw["photo_dir"] = photoDir;
            config.Raw["latitude"] = latitude;
            config.Raw["longitude"] = longitude;
            config.Raw["timezone"] = tz.Text.Trim();
            config.Raw["interval_minutes"] = minutes;
            config.Raw["language"] = S.Languages.First(l => l.Value == (string?)language.SelectedItem).Key;
            config.Raw["align_to_clock"] = align.Checked;
            config.Raw["lock_screen"] = lockScreen.Checked;
            config.Save();
            S.Reload();  // messages immediately in the new language
            Info(S.T(reindex ? "set.saved_reindex" : "set.saved"));
            Close();
            saved(reindex);
        }
    }
}

/// <summary>
/// Shows the photos that lack a GPS location or an EXIF capture time and asks for them. The answers go
/// to overrides.json (the photo files are not modified) and the index is updated when done.
/// </summary>
sealed class ReviewForm : KulmaForm
{
    readonly List<PhotoRecord> todo = Missing(Store.Read<List<PhotoRecord>>(Store.IndexPath) ?? []);
    readonly Dictionary<string, Override> overrides = Store.Read<Dictionary<string, Override>>(Store.OverridesPath) ?? [];
    readonly ListView list = new() { View = View.Details, FullRowSelect = true, HideSelection = false, Size = new Size(600, 340) };
    readonly Label preview = new() { Size = new Size(380, 340), TextAlign = ContentAlignment.MiddleCenter, BorderStyle = BorderStyle.FixedSingle };
    readonly TextBox place = new() { Width = 320 }, time = new() { Width = 320 };
    int shown = -1;
    bool dirty, done;

    /// <summary>Every photo needs both, so that the sun angle is calculated for the right place and time.</summary>
    public static List<PhotoRecord> Missing(IEnumerable<PhotoRecord> records) => records.Where(r => !r.Complete).ToList();

    public ReviewForm() : base(S.T("rev.title"))
    {
        var grid = Grid(2);
        var intro = Lbl(S.T("rev.intro", ("n", todo.Count), ("apply", S.T("rev.apply"))), wrap: 980);
        grid.Controls.Add(intro, 0, 0);
        grid.SetColumnSpan(intro, 2);

        list.Columns.Add(S.T("rev.col_photo"), 220);
        list.Columns.Add(S.T("rev.col_loc"), 170);
        list.Columns.Add(S.T("rev.col_time"), 200);
        list.Items.AddRange(todo.Select(r => new ListViewItem(Row(r))).ToArray());
        list.SelectedIndexChanged += (_, _) => ShowPreview();
        grid.Controls.Add(list, 0, 1);
        preview.Text = S.T("rev.select");
        grid.Controls.Add(preview, 1, 1);

        var form = Grid(2);
        form.Controls.Add(Lbl(S.T("rev.lbl_place")), 0, 0);
        form.Controls.Add(place, 1, 0);
        form.Controls.Add(Lbl(S.T("rev.lbl_time")), 0, 1);
        form.Controls.Add(time, 1, 1);
        grid.Controls.Add(form, 0, 2);

        var buttons = Buttons(Btn(S.T("rev.apply"), Apply), Btn(S.T("rev.done"), Close));
        grid.Controls.Add(buttons, 1, 2);
        Content(grid);
        FormClosing += OnClosing;
    }

    string[] Row(PhotoRecord r)
    {
        var ov = overrides.GetValueOrDefault(r.Path);
        static string Short(string iso) => iso[..16].Replace('T', ' ');
        var loc = ov?.Place ?? (r.Gps ? "GPS" : S.T("rev.missing"));
        var when = ov?.CaptureTime is { } ct ? Short(ct)
            : r.TimeSource == "mtime_fallback" ? S.T("rev.time_missing", ("t", Short(r.CaptureTime)))
            : Short(r.CaptureTime);
        return [Path.GetFileName(r.Path), loc, when];
    }

    async void ShowPreview()
    {
        if (list.SelectedIndices.Count == 0 || list.SelectedIndices[0] == shown) return;
        int index = shown = list.SelectedIndices[0];
        try
        {
            var image = await Wallpaper.ThumbnailAsync(todo[index].Path, 380);
            if (index != shown || IsDisposed) { image.Dispose(); return; }
            preview.Image?.Dispose();
            preview.Image = image;
            preview.Text = "";
        }
        catch
        {
            if (index != shown || IsDisposed) return;
            preview.Image = null;
            preview.Text = S.T("rev.nopreview");
        }
    }

    async void Apply()
    {
        if (list.SelectedIndices.Count == 0) { Info(S.T("rev.pick_first")); return; }
        string where = place.Text.Trim(), when = time.Text.Trim();
        if (where == "" && when == "") { Info(S.T("rev.enter_something")); return; }
        var selected = list.SelectedIndices.Cast<int>().ToList();
        var update = new Override();
        try
        {
            if (when != "")
                update.CaptureTime = DateTime.TryParseExact(when, new[] { "yyyy-M-d H:mm", "d.M.yyyy H:mm" }, CultureInfo.InvariantCulture,
                                                            DateTimeStyles.None, out var t)
                    ? t.ToString("yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture)
                    : throw new FormatException(S.T("rev.bad_time"));
            if (where != "")
            {
                UseWaitCursor = true;
                (update.Lat, update.Lon, update.Place) = await Geo.GeocodeAsync(where);
            }
        }
        catch (Exception e) { Error(e.Message); return; }
        finally { UseWaitCursor = false; }

        foreach (var i in selected)
        {
            var r = todo[i];
            if (!overrides.TryGetValue(r.Path, out var ov)) overrides[r.Path] = ov = new();
            if (update.Lat is not null) (ov.Lat, ov.Lon, ov.Place) = (update.Lat, update.Lon, update.Place);
            if (update.CaptureTime is not null) ov.CaptureTime = update.CaptureTime;
            var row = Row(r);
            for (int c = 0; c < row.Length; c++) list.Items[i].SubItems[c].Text = row[c];
        }
        Store.Write(Store.OverridesPath, overrides);
        dirty = true;
    }

    /// <summary>How many photos are still without a location or a capture time.</summary>
    int Remaining() => todo.Count(r =>
    {
        var ov = overrides.GetValueOrDefault(r.Path);
        return !((r.Gps || ov?.Lat is not null) && (r.TimeSource != "mtime_fallback" || ov?.CaptureTime is not null));
    });

    async void OnClosing(object? sender, FormClosingEventArgs e)
    {
        if (done || e.CloseReason != CloseReason.UserClosing) return;
        e.Cancel = true;
        int left = Remaining();
        if (left > 0 && MessageBox.Show(S.T("rev.close_q", ("n", left)), "Kulma", MessageBoxButtons.YesNo,
                                        MessageBoxIcon.Question) != DialogResult.Yes) return;
        if (dirty)
        {
            Text = S.T("rev.updating");
            Enabled = false;
            try { await Task.Run(() => Indexer.Run()); }
            catch (Exception ex) { Store.Log(ex.Message); }
        }
        done = true;
        Close();
    }
}

/// <summary>Icon, version, libraries, photo library statistics and the GitHub link.</summary>
sealed class AboutForm : KulmaForm
{
    public AboutForm() : base(S.T("about.title"))
    {
        var grid = Grid(1);
        void Add(Control c) => grid.Controls.Add(c);
        void Section(string title, IEnumerable<(string, string, string)> rows)
        {
            Add(new Label { BorderStyle = BorderStyle.Fixed3D, Height = 2, Width = 400, Margin = new Padding(3, 8, 3, 0) });
            Add(Lbl(title, bold: true));
            var table = Grid(3);
            foreach (var (a, b, c) in rows)
                table.Controls.AddRange([Lbl(a), Lbl(b), Lbl(c, color: SystemColors.GrayText)]);
            Add(table);
        }

        if (File.Exists(Store.IconPng))
            Add(new PictureBox { Image = Image.FromFile(Store.IconPng), SizeMode = PictureBoxSizeMode.Zoom, Size = new Size(96, 96), Anchor = AnchorStyles.None });
        var name = Lbl("Kulma");
        name.Font = new Font(SystemFonts.MessageBoxFont!.FontFamily, 16, FontStyle.Bold);
        name.Anchor = AnchorStyles.None;
        Add(name);
        var version = Lbl(S.T("about.version", ("v", typeof(AboutForm).Assembly.GetName().Version!.ToString(3))));
        version.Anchor = AnchorStyles.None;
        Add(version);
        Add(Lbl(S.T("about.desc"), wrap: 400));

        Section(S.T("about.libs"), [
            (".NET", Environment.Version.ToString(), S.T("about.lib_dotnet")),
            ("MetadataExtractor", typeof(MetadataExtractor.ImageMetadataReader).Assembly.GetName().Version?.ToString(3) ?? "-", S.T("about.lib_mdx")),
            ("Windows Imaging", "", S.T("about.lib_wic")),
            ("NOAA", "", S.T("about.lib_sun")),
        ]);

        var records = Store.Read<List<PhotoRecord>>(Store.IndexPath) ?? [];
        if (records.Count == 0)
            Section(S.T("about.library"), [(S.T("about.noindex"), "", "")]);
        else
        {
            int total = records.Count, located = records.Count(r => r.Gps), noTime = records.Count(r => r.TimeSource == "mtime_fallback");
            string Pct(int n) => $"{100 * n / total} %";
            Section(S.T("about.library"), [
                (S.T("about.photos"), $"{total}", Config.Load().PhotoDir),
                (S.T("about.located"), $"{located}", Pct(located)),
                (S.T("about.nolocation"), $"{total - located}", Pct(total - located)),
                (S.T("about.notime"), $"{noTime}", Pct(noTime)),
                (S.T("about.incomplete"), $"{ReviewForm.Missing(records).Count}", S.T("about.excluded")),
            ]);
            Add(Lbl(S.T("about.toplocs"), bold: true));
            var top = TopLocations(records).Select(t => (t.Lat, t.Lon, t.N, Label: Lbl(""))).ToList();
            void Render()
            {
                foreach (var (lat, lon, n, label) in top)
                    label.Text = S.T("about.place_n", ("name", Geo.CachedPlace(lat, lon) ?? $"{lat:F2}°, {lon:F2}°"), ("n", n), ("pct", Pct(n)));
            }
            top.ForEach(t => Add(t.Label));
            Render();
            Load += async (_, _) =>
            {
                foreach (var (lat, lon, _, _) in top)  // at most 1 request/s (Nominatim usage policy)
                {
                    if (Geo.CachedPlace(lat, lon) is not null) continue;
                    await Geo.PlaceAsync(lat, lon);
                    if (IsDisposed) return;
                    Render();
                    await Task.Delay(1100);
                }
            };
        }

        Add(Lbl(S.T("about.credits"), wrap: 400, color: SystemColors.GrayText));
        var link = new LinkLabel { Text = Program.GitHubUrl, AutoSize = true, Anchor = AnchorStyles.None, Margin = new Padding(3, 12, 3, 0) };
        link.LinkClicked += (_, _) => Process.Start(new ProcessStartInfo(Program.GitHubUrl) { UseShellExecute = true });
        Add(link);
        var close = Btn(S.T("about.close"), Close);
        close.Anchor = AnchorStyles.None;
        Add(close);
        Content(grid);
    }

    /// <summary>The 3 most common locations: photos less than 30 km apart go into the same group.</summary>
    static IEnumerable<(double Lat, double Lon, int N)> TopLocations(List<PhotoRecord> records)
    {
        var clusters = new List<(double Lat, double Lon, int N)>();
        foreach (var r in records)
        {
            if (r is not { Lat: { } lat, Lon: { } lon }) continue;
            int i = clusters.FindIndex(c => Math.Sqrt(Math.Pow((lat - c.Lat) * 111, 2)
                                                      + Math.Pow((lon - c.Lon) * 111 * Math.Cos(c.Lat * Math.PI / 180), 2)) <= 30);
            if (i >= 0) clusters[i] = clusters[i] with { N = clusters[i].N + 1 };
            else clusters.Add((lat, lon, 1));
        }
        return clusters.OrderByDescending(c => c.N).Take(3);
    }
}
