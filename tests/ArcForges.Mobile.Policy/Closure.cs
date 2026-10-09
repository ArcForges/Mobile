// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ArcForges.Mobile.Policy;

/// <summary>A package of the locked NuGet closure of the Android app.</summary>
internal sealed record LockedPackage(string Id, string Version, string ContentHash, string Kind);

/// <summary>A package admitted by a NuGet admission record.</summary>
internal sealed record AdmittedPackage(string Id, string Version, string ContentHash, string Kind, string Licence);

/// <summary>
/// The locked closure of the Android app, read from its packages.lock.json and checked against the NuGet admission record.
/// Every function takes text, so the negative fixtures run the same code as the repository tests.
/// </summary>
internal static class Closure
{
    /// <summary>The only SPDX expressions a shipped package may carry (eng/policy/nuget-admission.json admittedLicences).</summary>
    public static readonly IReadOnlyList<string> AdmittedLicences = ["Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MIT"];

    /// <summary>Licence families that never enter the Apache boundary: AGPL, GPL, SSPL, BUSL, proprietary or unlicensed.</summary>
    public static readonly Regex ForbiddenLicence = new("AGPL|GPL|SSPL|BUSL|Proprietary|UNLICENSED", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex Operators = new(@"\s+(?:AND|OR|WITH)\s+|[()]", RegexOptions.CultureInvariant);

    /// <summary>The target keys of a lock file: the framework targets, then one entry per runtime-specific target.</summary>
    public static IReadOnlyList<string> TargetKeys(string lockJson)
    {
        using var document = JsonDocument.Parse(lockJson);
        return document.RootElement.GetProperty("dependencies").EnumerateObject().Select(property => property.Name).ToArray();
    }

    /// <summary>The packages of one framework target, excluding project references. Fails if the target is absent.</summary>
    public static IReadOnlyList<LockedPackage> LockedPackages(string lockJson, string target)
    {
        using var document = JsonDocument.Parse(lockJson);
        var dependencies = document.RootElement.GetProperty("dependencies");
        if (!dependencies.TryGetProperty(target, out var entries))
        {
            throw new InvalidDataException("The lock file has no target " + target + ".");
        }

        var packages = new List<LockedPackage>();
        foreach (var entry in entries.EnumerateObject())
        {
            var type = entry.Value.GetProperty("type").GetString();
            if (type == "Project")
            {
                continue;
            }

            packages.Add(new LockedPackage(
                entry.Name,
                entry.Value.GetProperty("resolved").GetString() ?? string.Empty,
                entry.Value.GetProperty("contentHash").GetString() ?? string.Empty,
                type == "Direct" ? "direct" : "transitive"));
        }

        return packages;
    }

    /// <summary>The project references locked under one target (the Hello transport, by its lower-case lock key).</summary>
    public static IReadOnlyList<string> LockedProjects(string lockJson, string target)
    {
        using var document = JsonDocument.Parse(lockJson);
        var entries = document.RootElement.GetProperty("dependencies").GetProperty(target);
        return entries.EnumerateObject()
            .Where(entry => entry.Value.GetProperty("type").GetString() == "Project")
            .Select(entry => entry.Name)
            .ToArray();
    }

    /// <summary>The packages of a NuGet admission record.</summary>
    public static IReadOnlyList<AdmittedPackage> AdmittedPackages(string admissionJson)
    {
        using var document = JsonDocument.Parse(admissionJson);
        return document.RootElement.GetProperty("packages").EnumerateArray()
            .Select(item => new AdmittedPackage(
                item.GetProperty("id").GetString() ?? string.Empty,
                item.GetProperty("version").GetString() ?? string.Empty,
                item.GetProperty("contentHash").GetString() ?? string.Empty,
                item.GetProperty("kind").GetString() ?? string.Empty,
                item.GetProperty("licence").GetString() ?? string.Empty))
            .ToArray();
    }

    /// <summary>The SPDX tokens of a licence expression, without operators or parentheses.</summary>
    public static IReadOnlyList<string> LicenceTokens(string expression) =>
        Operators.Split(expression).Select(token => token.Trim()).Where(token => token.Length > 0).ToArray();

    /// <summary>
    /// The licence violations of one package: a forbidden family, or any token outside the admitted set. Empty when admitted.
    /// </summary>
    public static IReadOnlyList<string> LicenceViolations(string id, string expression)
    {
        var findings = new List<string>();
        if (ForbiddenLicence.IsMatch(expression))
        {
            findings.Add(id + ": forbidden licence family in '" + expression + "'");
        }

        var tokens = LicenceTokens(expression);
        if (tokens.Count == 0)
        {
            findings.Add(id + ": empty licence expression");
        }

        foreach (var token in tokens.Where(token => !AdmittedLicences.Contains(token, StringComparer.Ordinal)))
        {
            findings.Add(id + ": licence token '" + token + "' is not admitted");
        }

        return findings;
    }

    /// <summary>The differences between the locked closure and the admission record, by id, version, hash and kind.</summary>
    public static IReadOnlyList<string> AdmissionViolations(IEnumerable<LockedPackage> locked, IEnumerable<AdmittedPackage> admitted)
    {
        var lockedSet = locked.Select(item => (item.Id, item.Version, item.ContentHash, item.Kind)).ToHashSet();
        var admittedSet = admitted.Select(item => (item.Id, item.Version, item.ContentHash, item.Kind)).ToHashSet();
        var findings = new List<string>();
        foreach (var item in lockedSet.Except(admittedSet))
        {
            findings.Add("locked but not admitted: " + item.Id + " " + item.Version);
        }

        foreach (var item in admittedSet.Except(lockedSet))
        {
            findings.Add("admitted but not locked: " + item.Id + " " + item.Version);
        }

        if (lockedSet.Count != locked.Count() || admittedSet.Count != admitted.Count())
        {
            findings.Add("duplicate package id, version or hash in the closure");
        }

        return findings;
    }
}
