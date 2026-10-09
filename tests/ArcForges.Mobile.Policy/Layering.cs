// SPDX-License-Identifier: Apache-2.0
using System.Xml.Linq;

namespace ArcForges.Mobile.Policy;

/// <summary>
/// The Mobile project layering (WP-05.00): the app references only the Hello transport; the Keystore probe is test-only and
/// referenced by no app; the platform-neutral libraries reference no in-repository project; the host tests reference the
/// libraries they test. Every other project edge is refused.
/// </summary>
internal static class Layering
{
    public const string App = "src/ArcForges.Mobile/ArcForges.Mobile.csproj";
    public const string Network = "src/core/ArcForges.Mobile.Network/ArcForges.Mobile.Network.csproj";
    public const string Security = "src/core/ArcForges.Mobile.Security/ArcForges.Mobile.Security.csproj";
    public const string Tests = "tests/ArcForges.Mobile.Tests/ArcForges.Mobile.Tests.csproj";
    public const string Policy = "tests/ArcForges.Mobile.Policy/ArcForges.Mobile.Policy.csproj";

    private static readonly IReadOnlyDictionary<string, string[]> Allowed = new Dictionary<string, string[]>(StringComparer.Ordinal)
    {
        [App] = [Network],
        [Network] = [],
        [Security] = [],
        [Tests] = [Network, Security],
        [Policy] = [],
    };

    /// <summary>The project edges of one project file, as repository-relative forward-slash paths.</summary>
    public static IReadOnlyList<string> ProjectReferences(string project)
    {
        var document = XDocument.Load(Repository.Path(project));
        var directory = System.IO.Path.GetDirectoryName(Repository.Path(project)) ?? Repository.Root;
        return document.Descendants("ProjectReference")
            .Select(item => item.Attribute("Include")?.Value ?? throw new InvalidDataException("ProjectReference without Include in " + project))
            .Select(include => System.IO.Path.GetFullPath(System.IO.Path.Combine(directory, include.Replace('\\', System.IO.Path.DirectorySeparatorChar))))
            .Select(full => System.IO.Path.GetRelativePath(Repository.Root, full).Replace('\\', '/'))
            .ToArray();
    }

    /// <summary>The project graph of every tracked .csproj in the repository.</summary>
    public static IReadOnlyDictionary<string, IReadOnlyList<string>> RepositoryGraph()
    {
        var graph = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        foreach (var project in Repository.InventoryFiles().Where(name => name.EndsWith(".csproj", StringComparison.Ordinal)))
        {
            graph[project] = ProjectReferences(project);
        }

        return graph;
    }

    /// <summary>The layering violations of a project graph. Empty when every edge is allowed and every project is reviewed.</summary>
    public static IReadOnlyList<string> Violations(IReadOnlyDictionary<string, IReadOnlyList<string>> graph)
    {
        var findings = new List<string>();
        foreach (var (project, references) in graph)
        {
            if (!Allowed.TryGetValue(project, out var permitted))
            {
                findings.Add("unreviewed project " + project);
                continue;
            }

            foreach (var reference in references.Where(reference => !permitted.Contains(reference, StringComparer.Ordinal)))
            {
                findings.Add(project + " -> " + reference + " is not an allowed layering edge");
            }
        }

        foreach (var reviewed in Allowed.Keys.Where(project => !graph.ContainsKey(project)))
        {
            findings.Add("reviewed project missing from the graph: " + reviewed);
        }

        return findings;
    }
}
