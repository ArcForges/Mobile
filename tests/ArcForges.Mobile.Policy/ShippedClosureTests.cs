// SPDX-License-Identifier: Apache-2.0
namespace ArcForges.Mobile.Policy;

// AND.40 unit 4, F-023-class re-proof: the shipped MAUI closure holds no build-only or test-only package and no AGPL or
// DesktopPlatform package. The closure listing is written by eng/maui_notices.py closure (artifacts/evidence/maui-closure.json).
public sealed class ShippedClosureTests
{
    private static readonly IReadOnlyList<LockedPackage> Locked =
        Closure.LockedPackages(Repository.ReadText(Repository.AppLock), Repository.ReviewedTargetFramework);

    private static readonly IReadOnlyList<AdmittedPackage> Admitted =
        Closure.AdmittedPackages(Repository.ReadText(Repository.Admission));

    private static readonly IReadOnlyDictionary<string, string> Classes =
        ShippedClosure.Classes(Repository.ReadText(Repository.Distribution));

    private static readonly IReadOnlySet<string> TestOnly = TestScopeIds();

    [Fact]
    public void EveryLockedPackageHasOneReviewedClass()
    {
        var findings = ShippedClosure.Violations(Locked, Classes, TestOnly, Admitted);
        Assert.DoesNotContain(findings, finding => finding.StartsWith("unclassified", StringComparison.Ordinal));
        Assert.DoesNotContain(findings, finding => finding.StartsWith("classified but not locked", StringComparison.Ordinal));
        Assert.Equal(Locked.Count, Classes.Count);
    }

    [Fact]
    public void TheBuildOnlyClassIsExactlyTheReviewedTasks()
    {
        var buildOnly = Classes.Where(entry => entry.Value == ShippedClosure.BuildOnly).Select(entry => entry.Key).Order(StringComparer.Ordinal).ToArray();

        Assert.Equal(ShippedClosure.ReviewedBuildOnly.Order(StringComparer.Ordinal).ToArray(), buildOnly);
    }

    [Fact]
    public void TheShippedClosureHasNoBuildOnlyTestOnlyOrDesktopPlatformPackage()
    {
        Assert.Empty(ShippedClosure.Violations(Locked, Classes, TestOnly, Admitted));
    }

    [Fact]
    public void AShippedTestPackageIsRefused()
    {
        var locked = Locked.Append(new LockedPackage("xunit", "2.9.3", "AAAA", "direct")).ToArray();
        var classes = new Dictionary<string, string>(Classes, StringComparer.Ordinal) { ["xunit"] = ShippedClosure.Shipped };

        var findings = ShippedClosure.Violations(locked, classes, TestOnly, Admitted);

        Assert.Contains("test-only package in the shipped closure: xunit", findings);
    }

    [Fact]
    public void ABuildTaskClassifiedAsShippedIsRefused()
    {
        var classes = new Dictionary<string, string>(Classes, StringComparer.Ordinal) { ["Microsoft.NET.ILLink.Tasks"] = ShippedClosure.Shipped };

        var findings = ShippedClosure.Violations(Locked, classes, TestOnly, Admitted);

        Assert.Contains("build-only package classified as shipped: Microsoft.NET.ILLink.Tasks", findings);
    }

    [Fact]
    public void AnAgplDesktopPlatformPackageIsRefused()
    {
        var locked = Locked.Append(new LockedPackage("ArcForges.DesktopPlatform.Core", "1.0.0", "AAAA", "transitive")).ToArray();
        var admitted = Admitted.Append(new AdmittedPackage("ArcForges.DesktopPlatform.Core", "1.0.0", "AAAA", "transitive", "AGPL-3.0-only")).ToArray();
        var classes = new Dictionary<string, string>(Classes, StringComparer.Ordinal) { ["ArcForges.DesktopPlatform.Core"] = ShippedClosure.Shipped };

        var findings = ShippedClosure.Violations(locked, classes, TestOnly, admitted);

        Assert.Contains("forbidden first-party package in the shipped closure: ArcForges.DesktopPlatform.Core", findings);
        Assert.Contains("shipped package with a forbidden licence: ArcForges.DesktopPlatform.Core (AGPL-3.0-only)", findings);
    }

    [Fact]
    public void AnUnclassifiedLockedPackageIsRefused()
    {
        var locked = Locked.Append(new LockedPackage("Fixture.Unclassified", "1.0.0", "AAAA", "transitive")).ToArray();

        var findings = ShippedClosure.Violations(locked, Classes, TestOnly, Admitted);

        Assert.Contains("unclassified locked package: Fixture.Unclassified", findings);
    }

    private static IReadOnlySet<string> TestScopeIds()
    {
        using var document = Repository.ReadJson(Repository.TestAdmission);
        return document.RootElement.GetProperty("packages").EnumerateArray()
            .Select(item => item.GetProperty("id").GetString() ?? string.Empty)
            .ToHashSet(StringComparer.Ordinal);
    }
}
