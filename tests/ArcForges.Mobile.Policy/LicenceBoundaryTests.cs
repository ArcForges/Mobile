// SPDX-License-Identifier: Apache-2.0
using System.Text.RegularExpressions;

namespace ArcForges.Mobile.Policy;

// AND.40 unit 4, WP-05.01: the licence boundary over the resolved NuGet closure of the MAUI app, and the Android target.
public sealed class LicenceBoundaryTests
{
    private static readonly Regex BuildPolicyForm = new(
        @"arcforges\.build\.policy|build[\.\-_ ]?policy", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly string[] ClosureSources =
    [
        Repository.AppProject,
        Repository.AppLock,
        Repository.Admission,
        Repository.TestAdmission,
        Repository.Distribution,
        "Directory.Packages.props",
        "Directory.Build.props",
        "NuGet.config",
        "src/ArcForges.Mobile/MauiProgram.cs",
    ];

    [Fact]
    public void EveryAdmittedLicenceIsInTheAllowedSet()
    {
        var admitted = Closure.AdmittedPackages(Repository.ReadText(Repository.Admission));

        var findings = admitted.SelectMany(package => Closure.LicenceViolations(package.Id, package.Licence)).ToArray();

        Assert.Empty(findings);
    }

    [Fact]
    public void NoLockedPackageHasAGplOrAgplOrProprietaryLicence()
    {
        var admitted = Closure.AdmittedPackages(Repository.ReadText(Repository.Admission));

        Assert.DoesNotContain(admitted, package => Closure.ForbiddenLicence.IsMatch(package.Licence));
    }

    [Fact]
    public void TheLockedClosureIsExactlyTheAdmittedClosure()
    {
        var lockJson = Repository.ReadText(Repository.AppLock);
        var locked = Closure.LockedPackages(lockJson, Repository.ReviewedTargetFramework);
        var admitted = Closure.AdmittedPackages(Repository.ReadText(Repository.Admission));

        Assert.Empty(Closure.AdmissionViolations(locked, admitted));
        Assert.Equal(locked.Count, admitted.Count);
    }

    [Fact]
    public void NoBuildPolicyPackageAppearsInAnyFormInTheClosureSources()
    {
        var findings = ClosureSources
            .Where(File.Exists)
            .Select(Repository.Path)
            .SelectMany(path => BuildPolicyForm.Matches(File.ReadAllText(path)).Select(match => Path.GetFileName(path) + ": " + match.Value))
            .ToArray();

        Assert.Empty(findings);
    }

    [Fact]
    public void AGplBuildPolicyFormIsRefused()
    {
        var fixture = "<PackageReference Include=\"ArcForges" + ".Build.Policy\" Version=\"1.0.0\" />";

        Assert.Matches(BuildPolicyForm, fixture);
    }

    [Fact]
    public void ANonAdmittedLicenceIsRefused()
    {
        var findings = Closure.LicenceViolations("Fixture.Package", "AGPL-3.0-only");

        Assert.Contains(findings, finding => finding.Contains("forbidden licence family", StringComparison.Ordinal));
        Assert.Contains("Fixture.Package: licence token 'AGPL-3.0-only' is not admitted", findings);
    }

    [Fact]
    public void AnAdmittedCompoundLicenceIsAccepted()
    {
        Assert.Empty(Closure.LicenceViolations("Xamarin.AndroidX.Core", "MIT AND Apache-2.0"));
        Assert.Empty(Closure.LicenceViolations("Xamarin.Android.Glide", "MIT AND BSD-2-Clause AND Apache-2.0"));
    }

    [Fact]
    public void AnUnlistedLockedPackageIsRefused()
    {
        var lockJson = """
            {"version":2,"dependencies":{"net10.0-android36.1":{
              "Fixture.Extra":{"type":"Transitive","resolved":"1.0.0","contentHash":"AAAA"}}}}
            """;
        var locked = Closure.LockedPackages(lockJson, Repository.ReviewedTargetFramework);
        var admitted = Closure.AdmittedPackages(Repository.ReadText(Repository.Admission));

        var findings = Closure.AdmissionViolations(locked, admitted);

        Assert.Contains("locked but not admitted: Fixture.Extra 1.0.0", findings);
    }

    [Fact]
    public void TheAppTargetsNet10AndroidOnly()
    {
        var project = System.Xml.Linq.XDocument.Load(Repository.Path(Repository.AppProject));
        var frameworks = project.Descendants("TargetFrameworks").Select(item => item.Value.Trim()).ToArray();

        Assert.Equal(new[] { "net10.0-android" }, frameworks);
    }

    [Fact]
    public void TheLockedAppClosureTargetsNet10AndroidOnly()
    {
        var keys = Closure.TargetKeys(Repository.ReadText(Repository.AppLock));

        var frameworkTargets = keys.Where(key => !key.Contains('/', StringComparison.Ordinal)).ToArray();
        Assert.Equal(new[] { Repository.ReviewedTargetFramework }, frameworkTargets);
        Assert.All(keys.Where(key => key.Contains('/', StringComparison.Ordinal)), key =>
            Assert.StartsWith(Repository.ReviewedTargetFramework + "/", key, StringComparison.Ordinal));
    }

    [Fact]
    public void AClosureWithANet10TargetIsRefused()
    {
        var keys = Closure.TargetKeys("""{"version":2,"dependencies":{"net10.0-android36.1":{},"net10.0":{}}}""");

        var frameworkTargets = keys.Where(key => !key.Contains('/', StringComparison.Ordinal)).ToArray();

        Assert.NotEqual(new[] { Repository.ReviewedTargetFramework }, frameworkTargets);
    }
}
