// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;

namespace ArcForges.Mobile.Policy;

/// <summary>
/// The F-023-class closure re-proof for the MAUI distribution (AND.40 unit 4). Every locked package is classified in
/// eng/policy/maui-distribution.json as shipped or build-only. The shipped closure must hold no build-only package (the three
/// build tasks are pinned here, so a change needs a reviewed edit), no test-only package and no AGPL or DesktopPlatform package.
/// </summary>
internal static class ShippedClosure
{
    public const string Shipped = "shipped";
    public const string BuildOnly = "build-only";

    /// <summary>The build tasks of the locked closure. They compile or trim the app and are never packaged into the APK.</summary>
    public static readonly IReadOnlyList<string> ReviewedBuildOnly =
        ["Microsoft.Maui.Controls.Build.Tasks", "Microsoft.Maui.Resizetizer", "Microsoft.NET.ILLink.Tasks"];

    /// <summary>The classification of each locked package, from the distribution record.</summary>
    public static IReadOnlyDictionary<string, string> Classes(string distributionJson)
    {
        using var document = JsonDocument.Parse(distributionJson);
        var classes = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var item in document.RootElement.GetProperty("packages").EnumerateArray())
        {
            var id = item.GetProperty("id").GetString() ?? string.Empty;
            if (!classes.TryAdd(id, item.GetProperty("class").GetString() ?? string.Empty))
            {
                throw new InvalidDataException("Duplicate distribution class for " + id + ".");
            }
        }

        return classes;
    }

    /// <summary>The re-proof findings for a locked closure, its classes, its test-only ids and its admitted licences.</summary>
    public static IReadOnlyList<string> Violations(
        IReadOnlyList<LockedPackage> locked,
        IReadOnlyDictionary<string, string> classes,
        IReadOnlySet<string> testOnly,
        IReadOnlyList<AdmittedPackage> admitted)
    {
        var findings = new List<string>();
        var lockedIds = locked.Select(package => package.Id).ToHashSet(StringComparer.Ordinal);
        foreach (var id in lockedIds.Where(id => !classes.ContainsKey(id)))
        {
            findings.Add("unclassified locked package: " + id);
        }

        foreach (var id in classes.Keys.Where(id => !lockedIds.Contains(id)))
        {
            findings.Add("classified but not locked: " + id);
        }

        foreach (var (id, value) in classes.Where(entry => entry.Value is not (Shipped or BuildOnly)))
        {
            findings.Add("unknown distribution class '" + value + "' for " + id);
        }

        var shipped = locked.Where(package => classes.GetValueOrDefault(package.Id) == Shipped).ToArray();
        foreach (var package in shipped)
        {
            if (ReviewedBuildOnly.Contains(package.Id, StringComparer.Ordinal))
            {
                findings.Add("build-only package classified as shipped: " + package.Id);
            }

            if (testOnly.Contains(package.Id))
            {
                findings.Add("test-only package in the shipped closure: " + package.Id);
            }

            if (package.Id.Contains("DesktopPlatform", StringComparison.OrdinalIgnoreCase) ||
                package.Id.Contains("Build.Policy", StringComparison.OrdinalIgnoreCase))
            {
                findings.Add("forbidden first-party package in the shipped closure: " + package.Id);
            }
        }

        foreach (var package in admitted.Where(item => classes.GetValueOrDefault(item.Id) == Shipped))
        {
            if (Closure.ForbiddenLicence.IsMatch(package.Licence))
            {
                findings.Add("shipped package with a forbidden licence: " + package.Id + " (" + package.Licence + ")");
            }
        }

        return findings;
    }
}
