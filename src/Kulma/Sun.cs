namespace Kulma;

/// <summary>
/// Sun position from the NOAA solar calculator equations (the same ones the Python
/// version's astral library uses), elevation corrected for atmospheric refraction.
/// </summary>
static class Sun
{
    static readonly DateTime J2000 = new(2000, 1, 1, 12, 0, 0, DateTimeKind.Utc);

    public static (double Elevation, double Azimuth) Position(DateTimeOffset at, double lat, double lon)
    {
        lat = Math.Clamp(lat, -89.8, 89.8);
        var utc = at.UtcDateTime;
        double jc = (utc - J2000).TotalDays / 36525.0;  // Julian centuries since J2000

        double l0 = 280.46646 + jc * (36000.76983 + 0.0003032 * jc);  // mean longitude
        double m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc);    // mean anomaly
        double e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc);
        double center = Sin(m) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
                        + Sin(2 * m) * (0.019993 - 0.000101 * jc) + Sin(3 * m) * 0.000289;
        double omega = 125.04 - 1934.136 * jc;
        double apparentLong = l0 + center - 0.00569 - 0.00478 * Sin(omega);
        double meanObliquity = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0;
        double obliquity = meanObliquity + 0.00256 * Cos(omega);
        double decl = Deg(Math.Asin(Sin(obliquity) * Sin(apparentLong)));

        double y = Math.Pow(Math.Tan(Rad(obliquity) / 2), 2);
        double eqOfTime = 4 * Deg(y * Sin(2 * l0) - 2 * e * Sin(m) + 4 * e * y * Sin(m) * Cos(2 * l0)
                                  - 0.5 * y * y * Sin(4 * l0) - 1.25 * e * e * Sin(2 * m));  // minutes

        double trueSolarTime = ((utc.TimeOfDay.TotalMinutes + eqOfTime + 4 * lon) % 1440 + 1440) % 1440;
        double hourAngle = trueSolarTime / 4 - 180;

        double cosZenith = Math.Clamp(Sin(lat) * Sin(decl) + Cos(lat) * Cos(decl) * Cos(hourAngle), -1, 1);
        double zenith = Deg(Math.Acos(cosZenith));

        double azimuth;
        double azDenom = Cos(lat) * Sin(zenith);
        if (Math.Abs(azDenom) > 0.001)
        {
            double azRad = Math.Clamp((Sin(lat) * Cos(zenith) - Sin(decl)) / azDenom, -1, 1);
            azimuth = 180 - Deg(Math.Acos(azRad));
            if (hourAngle > 0) azimuth = -azimuth;
        }
        else
        {
            azimuth = lat > 0 ? 180 : 0;
        }
        if (azimuth < 0) azimuth += 360;

        return (90 - zenith + Refraction(90 - zenith), azimuth);
    }

    /// <summary>Atmospheric refraction in degrees at the given geometric elevation (NOAA approximation).</summary>
    static double Refraction(double elevation)
    {
        if (elevation >= 85) return 0;
        double te = Math.Tan(Rad(elevation));
        double arcsec = elevation > 5 ? 58.1 / te - 0.07 / Math.Pow(te, 3) + 0.000086 / Math.Pow(te, 5)
            : elevation > -0.575 ? 1735 + elevation * (-518.2 + elevation * (103.4 + elevation * (-12.79 + elevation * 0.711)))
            : -20.774 / te;
        return arcsec / 3600;
    }

    static double Rad(double deg) => deg * Math.PI / 180;
    static double Deg(double rad) => rad * 180 / Math.PI;
    static double Sin(double deg) => Math.Sin(Rad(deg));
    static double Cos(double deg) => Math.Cos(Rad(deg));
}
