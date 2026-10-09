// SPDX-License-Identifier: Apache-2.0
namespace ArcForges.Mobile.Policy;

// AND.40 unit 4, WP-05.00: the Mobile project layering.
public sealed class LayeringTests
{
    [Fact]
    public void TheAppReferencesOnlyTheHelloTransport()
    {
        Assert.Equal(new[] { Layering.Network }, Layering.ProjectReferences(Layering.App));
    }

    [Fact]
    public void TheKeystoreProbeIsReferencedByNoApp()
    {
        Assert.DoesNotContain(Layering.Security, Layering.ProjectReferences(Layering.App));
        Assert.Empty(Layering.ProjectReferences(Layering.Security));
    }

    [Fact]
    public void TheRepositoryGraphHasNoLayeringViolation()
    {
        var findings = Layering.Violations(Layering.RepositoryGraph());

        Assert.Empty(findings);
    }

    [Fact]
    public void TheAppMayNotReferenceTheKeystoreProbe()
    {
        var graph = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            [Layering.App] = [Layering.Network, Layering.Security],
            [Layering.Network] = [],
            [Layering.Security] = [],
            [Layering.Tests] = [Layering.Network, Layering.Security],
            [Layering.Policy] = [],
        };

        Assert.Contains(Layering.App + " -> " + Layering.Security + " is not an allowed layering edge", Layering.Violations(graph));
    }

    [Fact]
    public void TheCoreLibraryMayNotReferenceTheApp()
    {
        var graph = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            [Layering.App] = [Layering.Network],
            [Layering.Network] = [Layering.App],
            [Layering.Security] = [],
            [Layering.Tests] = [Layering.Network, Layering.Security],
            [Layering.Policy] = [],
        };

        Assert.Contains(Layering.Network + " -> " + Layering.App + " is not an allowed layering edge", Layering.Violations(graph));
    }

    [Fact]
    public void TheSecurityLibraryMayNotReferenceTheNetworkLibrary()
    {
        var graph = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            [Layering.App] = [Layering.Network],
            [Layering.Network] = [],
            [Layering.Security] = [Layering.Network],
            [Layering.Tests] = [Layering.Network, Layering.Security],
            [Layering.Policy] = [],
        };

        Assert.Contains(Layering.Security + " -> " + Layering.Network + " is not an allowed layering edge", Layering.Violations(graph));
    }

    [Fact]
    public void AnUnreviewedProjectIsRefused()
    {
        var graph = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            [Layering.App] = [Layering.Network],
            [Layering.Network] = [],
            [Layering.Security] = [],
            [Layering.Tests] = [Layering.Network, Layering.Security],
            [Layering.Policy] = [],
            ["src/core/ArcForges.Mobile.Extra/ArcForges.Mobile.Extra.csproj"] = [],
        };

        Assert.Contains("unreviewed project src/core/ArcForges.Mobile.Extra/ArcForges.Mobile.Extra.csproj", Layering.Violations(graph));
    }

    [Fact]
    public void AMissingReviewedProjectIsRefused()
    {
        var graph = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
        {
            [Layering.App] = [Layering.Network],
            [Layering.Network] = [],
            [Layering.Tests] = [Layering.Network],
        };

        var findings = Layering.Violations(graph);

        Assert.Contains("reviewed project missing from the graph: " + Layering.Security, findings);
    }
}
