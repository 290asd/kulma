using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32;
using Windows.Graphics.Imaging;
using Windows.Storage;
using Windows.Storage.Streams;
using Windows.System.UserProfile;

namespace Kulma;

/// <summary>Desktop and lock screen images, and image decoding through Windows' own codecs (WIC).</summary>
static class Wallpaper
{
    static readonly HashSet<string> Heic = new(StringComparer.OrdinalIgnoreCase) { ".heic", ".heif" };

    /// <summary>
    /// Sets the desktop wallpaper (the same mechanism the Settings app uses) in "Fill" mode. The
    /// WM_SETTINGCHANGE broadcast is sent with a timeout instead of SPIF_SENDCHANGE, which waits for
    /// every top-level window and would hang forever on a single unresponsive one.
    /// </summary>
    public static void SetDesktop(string path)
    {
        using (var key = Registry.CurrentUser.OpenSubKey(@"Control Panel\Desktop", writable: true))
        {
            key?.SetValue("WallpaperStyle", "10");  // 10 = Fill
            key?.SetValue("TileWallpaper", "0");
        }
        if (!SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, Path.GetFullPath(path), SPIF_UPDATEINIFILE))
            throw new Win32Exception();
        SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, SPI_SETDESKWALLPAPER, 0, SMTO_ABORTIFHUNG, 5000, out _);
    }

    /// <summary>Sets the lock screen image (also switches it from "Windows Spotlight" to "Picture").</summary>
    public static async Task SetLockScreenAsync(string path) =>
        await LockScreen.SetImageFileAsync(await StorageFile.GetFileFromPathAsync(Path.GetFullPath(path)));

    /// <summary>
    /// A path Windows can use as a wallpaper. Windows has no HEIC support in the wallpaper setting
    /// (the call "succeeds" but the desktop does not change), so HEIC/HEIF photos are converted once
    /// into a JPEG cache named after the original.
    /// </summary>
    public static async Task<string> DisplayPathAsync(string path)
    {
        if (!Heic.Contains(Path.GetExtension(path))) return path;
        var cached = Path.Combine(Store.CacheDir, Path.GetFileNameWithoutExtension(path) + ".jpg");
        if (File.Exists(cached) && File.GetLastWriteTimeUtc(cached) >= File.GetLastWriteTimeUtc(path)) return cached;

        Directory.CreateDirectory(Store.CacheDir);
        using var bitmap = await DecodeAsync(path, 0);
        var folder = await StorageFolder.GetFolderFromPathAsync(Store.CacheDir);
        var file = await folder.CreateFileAsync(Path.GetFileName(cached), CreationCollisionOption.ReplaceExisting);
        using (var stream = await file.OpenAsync(FileAccessMode.ReadWrite))
        {
            var quality = new BitmapPropertySet { ["ImageQuality"] = new BitmapTypedValue(0.92f, Windows.Foundation.PropertyType.Single) };
            var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.JpegEncoderId, stream, quality);
            encoder.SetSoftwareBitmap(bitmap);
            await encoder.FlushAsync();
        }
        return cached;
    }

    /// <summary>A preview image (rotated upright), at most maxSize pixels on its longer side.</summary>
    public static async Task<Bitmap> ThumbnailAsync(string path, uint maxSize)
    {
        using var bitmap = await DecodeAsync(path, maxSize);
        using var png = new InMemoryRandomAccessStream();
        var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, png);
        encoder.SetSoftwareBitmap(bitmap);
        await encoder.FlushAsync();
        png.Seek(0);
        using var image = Image.FromStream(png.AsStreamForRead());
        return new Bitmap(image);  // a copy that does not need the stream
    }

    /// <summary>
    /// Decodes JPEG/PNG/TIFF and HEIC (HEIC needs the "HEIF Image Extensions" and "HEVC Video Extensions"
    /// from the Microsoft Store), turned upright by the EXIF orientation. maxSize 0 = full size.
    /// </summary>
    static async Task<SoftwareBitmap> DecodeAsync(string path, uint maxSize)
    {
        var file = await StorageFile.GetFileFromPathAsync(Path.GetFullPath(path));
        using var stream = await file.OpenReadAsync();
        var decoder = await BitmapDecoder.CreateAsync(stream);
        var transform = new BitmapTransform { InterpolationMode = BitmapInterpolationMode.Fant };
        double scale = maxSize == 0 ? 1 : Math.Min(1, (double)maxSize / Math.Max(decoder.PixelWidth, decoder.PixelHeight));
        transform.ScaledWidth = (uint)Math.Max(1, decoder.PixelWidth * scale);
        transform.ScaledHeight = (uint)Math.Max(1, decoder.PixelHeight * scale);
        return await decoder.GetSoftwareBitmapAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore, transform,
                                                    ExifOrientationMode.RespectExifOrientation, ColorManagementMode.DoNotColorManage);
    }

    const uint SPI_SETDESKWALLPAPER = 20, SPIF_UPDATEINIFILE = 0x01, WM_SETTINGCHANGE = 0x001A, SMTO_ABORTIFHUNG = 0x0002;
    static readonly IntPtr HWND_BROADCAST = 0xFFFF;

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool SystemParametersInfoW(uint action, uint param, string value, uint winIni);

    [DllImport("user32.dll")]
    static extern IntPtr SendMessageTimeoutW(IntPtr hWnd, uint msg, nuint wParam, nint lParam, uint flags, uint timeout, out nuint result);
}
