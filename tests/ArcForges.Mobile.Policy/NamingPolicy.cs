// SPDX-License-Identifier: Apache-2.0
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace ArcForges.Mobile.Policy;

/// <summary>
/// The pinned, test-only NuGet identity of the canonical naming policy (AND.40 decision 18, WP-05.02). The policy is read only from
/// ArcForges.Contracts.Validation 1.0.0-ci.205.1 (Contracts source 696242d, an ancestor of Contracts origin/main; the same pin the
/// HAR.40 architecture host uses). Nothing is copied into the Mobile tree. Every check fails closed: a different identity, archive,
/// sidecar, source commit or policy byte is a finding, and no policy is used while any finding exists.
/// </summary>
internal static class NamingPolicy
{
    public const string PackageId = "ArcForges.Contracts.Validation";
    public const string Version = "1.0.0-ci.205.1";
    public const string SourceCommit = "696242d16034262ce8b7268e8d157cd0e5bee544";
    public const string ArchiveSha512 = "OWvMF30zpN6ms2KlQCtax5P7TACrgK50Vb0drN5zy4iXgk2TZd+5UU+LDGaA2ioowA1EQIZx8ZUyRoayZaHadA==";
    public const string PolicyPath = "tools/naming/eng/policy/product-names.json";
    public const string PolicySha256 = "f5d596298ec50e3b116abc6df1b34efef93045ed52f6235b0a2aaaf97a1f4df5";

    private static readonly string ArchiveFile = PackageId.ToLowerInvariant() + "." + Version + ".nupkg";

    private static readonly Lazy<string> VerifiedPolicy = new(() => Load(PackageRoot));

    /// <summary>The canonical policy JSON, verified against the pinned package. Throws when the restored package is not the candidate.</summary>
    public static string Verified => VerifiedPolicy.Value;

    /// <summary>The restored package folder, bound by GeneratePathProperty in the project file (NamingPackageRoot metadata).</summary>
    public static string PackageRoot
    {
        get
        {
            var root = typeof(NamingPolicy).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
                .Single(attribute => attribute.Key == "NamingPackageRoot")
                .Value;
            return root ?? throw new InvalidOperationException("The naming package root is not bound.");
        }
    }

    /// <summary>Checks the package identity before any file is read: a different id or version is refused.</summary>
    public static IReadOnlyList<string> VerifyIdentity(string packageId, string version) =>
        packageId == PackageId && version == Version ? [] : ["The naming package identity is not the pinned test-only candidate."];

    /// <summary>
    /// Checks the archive, its sidecar digest, the packaged source commit and the packaged policy digest. A missing input is a finding.
    /// </summary>
    public static IReadOnlyList<string> VerifyPackage(byte[]? archive, string? sidecarSha512, byte[]? sourceJson, byte[]? policy)
    {
        var problems = new List<string>();
        if (archive is null)
        {
            problems.Add("The naming package archive is missing.");
        }
        else if (Convert.ToBase64String(SHA512.HashData(archive)) != ArchiveSha512)
        {
            problems.Add("The archive SHA512 differs from the pinned candidate.");
        }

        if (sidecarSha512 is null)
        {
            problems.Add("The archive sidecar digest is missing.");
        }
        else if (sidecarSha512.Trim() != ArchiveSha512)
        {
            problems.Add("The archive sidecar digest differs from the pinned candidate.");
        }

        if (sourceJson is null)
        {
            problems.Add("The packaged source record is missing.");
        }
        else
        {
            try
            {
                using var source = JsonDocument.Parse(sourceJson);
                if (!source.RootElement.TryGetProperty("commit", out var commit) || commit.GetString() != SourceCommit)
                {
                    problems.Add("The packaged source commit differs from the pinned candidate.");
                }
            }
            catch (JsonException)
            {
                problems.Add("The packaged source record is not valid JSON.");
            }
        }

        if (policy is null)
        {
            problems.Add("The packaged naming policy is missing.");
        }
        else if (Convert.ToHexStringLower(SHA256.HashData(policy)) != PolicySha256)
        {
            problems.Add("The packaged naming policy differs from the pinned SHA256.");
        }

        return problems;
    }

    /// <summary>
    /// Reads and verifies the policy of the package at <paramref name="root"/>. Throws with every finding when any check fails,
    /// including a missing package folder, so no caller can fall back to an unverified or copied policy.
    /// </summary>
    public static string Load(string root)
    {
        var archive = ReadIfExists(Path.Combine(root, ArchiveFile));
        var sidecar = ReadIfExists(Path.Combine(root, ArchiveFile + ".sha512"));
        var source = ReadIfExists(Path.Combine(root, "source.json"));
        var policy = ReadIfExists(Path.Combine(root, PolicyPath.Replace('/', Path.DirectorySeparatorChar)));
        var findings = VerifyIdentity(PackageId, Version)
            .Concat(VerifyPackage(archive, sidecar is null ? null : Encoding.UTF8.GetString(sidecar), source, policy))
            .ToArray();
        if (findings.Length > 0 || policy is null)
        {
            throw new InvalidOperationException("The naming policy package failed verification: " + string.Join(" ", findings));
        }

        return Encoding.UTF8.GetString(policy);
    }

    private static byte[]? ReadIfExists(string path) => File.Exists(path) ? File.ReadAllBytes(path) : null;
}
