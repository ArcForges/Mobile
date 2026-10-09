// SPDX-License-Identifier: Apache-2.0
using System.Text;

namespace ArcForges.Mobile.Policy;

// AND.40 unit 4, WP-05.02 (AND.40 decision 18): the forbidden-term scanner over every tracked file. The names are read only from the
// pinned test-only package (NamingPolicy), verified before use, and no tracked copy of the policy is exempt from the scan.
public sealed class ForbiddenTermsTests
{
    [Fact]
    public void ThePackagedNamingPolicyHasTheSixReviewedForbiddenNames()
    {
        var names = ForbiddenNames.Names(NamingPolicy.Verified);

        Assert.Equal(6, names.Count);
        Assert.Equal(names.Count, names.Distinct(StringComparer.OrdinalIgnoreCase).Count());
    }

    [Fact]
    public void TheVerifiedPackageIsLoadedAgainTheSamePinnedBytes()
    {
        Assert.Equal(NamingPolicy.Verified, NamingPolicy.Load(NamingPolicy.PackageRoot));
    }

    [Fact]
    public void NoTrackedCopyOfTheNamingPolicyIsKept()
    {
        var copies = Repository.InventoryFiles()
            .Where(path => path.EndsWith("product-names.json", StringComparison.Ordinal))
            .ToArray();

        Assert.Empty(copies);
    }

    [Fact]
    public void NoApplicationProjectReferencesTheNamingPolicy()
    {
        var projects = Repository.InventoryFiles()
            .Where(path => path.EndsWith(".csproj", StringComparison.Ordinal)
                && (path.StartsWith("src/", StringComparison.Ordinal) || path.StartsWith("tests/ArcForges.Mobile.Tests/", StringComparison.Ordinal)))
            .ToArray();

        Assert.NotEmpty(projects);
        foreach (var project in projects)
        {
            Assert.DoesNotContain(NamingPolicy.PackageId, Repository.ReadText(project), StringComparison.Ordinal);
        }
    }

    [Fact]
    public void NoTrackedFileOrPathContainsAForbiddenName()
    {
        var names = ForbiddenNames.Names(NamingPolicy.Verified);
        var findings = new List<string>();
        foreach (var path in Repository.InventoryFiles())
        {
            findings.AddRange(ForbiddenNames.Findings(path + " (path)", Encoding.UTF8.GetBytes(path), names));
            var full = Repository.Path(path);
            if (!File.Exists(full))
            {
                findings.Add(path + ": tracked file is missing from the working tree");
                continue;
            }

            findings.AddRange(ForbiddenNames.Findings(path, File.ReadAllBytes(full), names));
        }

        Assert.Empty(findings);
    }

    [Fact]
    public void AnAlteredPolicyByteIsRefusedBeforeUse()
    {
        var (archive, sidecar, source, policy) = PackageFiles();
        var altered = (byte[])policy.Clone();
        altered[^1] ^= 0x20;

        var findings = NamingPolicy.VerifyPackage(archive, sidecar, source, altered);

        Assert.Contains(findings, finding => finding.Contains("policy", StringComparison.Ordinal));
    }

    [Fact]
    public void AnAlteredArchiveOrSidecarOrSourceCommitIsRefused()
    {
        var (archive, sidecar, source, policy) = PackageFiles();
        var alteredArchive = (byte[])archive.Clone();
        alteredArchive[^1] ^= 0x01;

        Assert.Contains(NamingPolicy.VerifyPackage(alteredArchive, sidecar, source, policy), finding => finding.Contains("archive SHA512", StringComparison.Ordinal));
        Assert.Contains(NamingPolicy.VerifyPackage(archive, "unknown", source, policy), finding => finding.Contains("sidecar", StringComparison.Ordinal));
        Assert.Contains(NamingPolicy.VerifyPackage(archive, sidecar, Encoding.UTF8.GetBytes("{\"commit\":\"main\"}"), policy), finding => finding.Contains("source commit", StringComparison.Ordinal));
        Assert.Contains(NamingPolicy.VerifyPackage(archive, sidecar, Encoding.UTF8.GetBytes("not json"), policy), finding => finding.Contains("not valid JSON", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("ArcForges.Contracts.Validation", "1.0.0-ci.205.2")]
    [InlineData("ArcForges.Contracts.Validation", "1.0.0-ci.129.1")]
    [InlineData("ArcForges.Contracts.Validation", "1.0.0-ci.287.1")]
    [InlineData("ArcForges.Contracts.Events", "1.0.0-ci.205.1")]
    public void AWrongVersionOrPackageIsRefusedAtIdentity(string packageId, string version)
    {
        Assert.NotEmpty(NamingPolicy.VerifyIdentity(packageId, version));
    }

    [Fact]
    public void AMissingPackageFailsClosedAndNeverFallsBackToACopy()
    {
        Assert.NotEmpty(NamingPolicy.VerifyPackage(null, null, null, null));

        var missing = Path.Combine(NamingPolicy.PackageRoot, "missing-" + Guid.NewGuid().ToString("N"));
        Assert.Throws<InvalidOperationException>(() => NamingPolicy.Load(missing));
    }

    [Fact]
    public void AFixtureWithAForbiddenNameIsRefused()
    {
        var names = ForbiddenNames.Names(NamingPolicy.Verified);
        var fixture = "class Probe { string label = \"" + names[0] + "\"; }";

        Assert.NotEmpty(ForbiddenNames.Findings("fixture", Encoding.UTF8.GetBytes(fixture), names));
    }

    [Fact]
    public void AUtf16FixtureWithAForbiddenNameIsRefused()
    {
        var names = ForbiddenNames.Names(NamingPolicy.Verified);
        var fixture = "class Probe { string label = \"" + names[^1] + "\"; }";

        var findings = ForbiddenNames.Findings("fixture", Encoding.Unicode.GetBytes(fixture), names);

        Assert.Contains(findings, finding => finding.EndsWith("(utf-16-le)", StringComparison.Ordinal));
    }

    [Fact]
    public void TheTwoCompatibilityTokensAreAdmittedAndNotFindings()
    {
        var names = ForbiddenNames.Names(NamingPolicy.Verified);
        var fixture = "const string Token = \"" + "Arc" + "ImageNative" + "\"; const string Abi = \"" + "arc" + "image-abi" + "\";";

        Assert.Empty(ForbiddenNames.Findings("fixture", Encoding.UTF8.GetBytes(fixture), names));
    }

    /// <summary>The four packaged inputs of the pinned candidate, read from the restored package folder.</summary>
    private static (byte[] Archive, string Sidecar, byte[] Source, byte[] Policy) PackageFiles()
    {
        var root = NamingPolicy.PackageRoot;
        return (
            File.ReadAllBytes(Path.Combine(root, NamingPolicy.PackageId.ToLowerInvariant() + "." + NamingPolicy.Version + ".nupkg")),
            File.ReadAllText(Path.Combine(root, NamingPolicy.PackageId.ToLowerInvariant() + "." + NamingPolicy.Version + ".nupkg.sha512")),
            File.ReadAllBytes(Path.Combine(root, "source.json")),
            File.ReadAllBytes(Path.Combine(root, NamingPolicy.PolicyPath.Replace('/', Path.DirectorySeparatorChar))));
    }
}
