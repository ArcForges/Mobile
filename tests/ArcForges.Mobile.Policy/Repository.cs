// SPDX-License-Identifier: Apache-2.0
using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace ArcForges.Mobile.Policy;

/// <summary>Repository access for the policy tests: the Mobile root, its Git inventory and the reviewed data files.</summary>
internal static class Repository
{
    public const string AppProject = "src/ArcForges.Mobile/ArcForges.Mobile.csproj";
    public const string AppLock = "src/ArcForges.Mobile/packages.lock.json";
    public const string Admission = "eng/policy/nuget-admission.json";
    public const string TestAdmission = "eng/policy/nuget-test-admission.json";
    public const string Distribution = "eng/policy/maui-distribution.json";
    public const string ReviewedTargetFramework = "net10.0-android36.1";

    private static readonly Lazy<string> RootPath = new(FindRoot);

    /// <summary>The Mobile repository root: the directory that holds ArcForges.Mobile.slnx.</summary>
    public static string Root => RootPath.Value;

    /// <summary>A repository-relative path as a native path under the root.</summary>
    public static string Path(string relative) => System.IO.Path.Combine(Root, relative.Replace('/', System.IO.Path.DirectorySeparatorChar));

    /// <summary>Reads a repository file as UTF-8 text. Line endings are kept as stored.</summary>
    public static string ReadText(string relative) => File.ReadAllText(Path(relative), Encoding.UTF8);

    /// <summary>Parses a repository JSON file.</summary>
    public static JsonDocument ReadJson(string relative) => JsonDocument.Parse(ReadText(relative));

    /// <summary>Every tracked, unignored file, as repository-relative forward-slash paths. Fails closed if Git cannot list them.</summary>
    public static IReadOnlyList<string> InventoryFiles()
    {
        var output = RunGit("ls-files", "-z", "--cached", "--others", "--exclude-standard");
        return output.Split('\0', StringSplitOptions.RemoveEmptyEntries)
            .Select(name => name.Replace('\\', '/'))
            .Order(StringComparer.Ordinal)
            .ToArray();
    }

    /// <summary>Every tracked, unignored C# source under a repository prefix, excluding build output.</summary>
    public static IReadOnlyList<string> CSharpSources(string prefix) =>
        InventoryFiles()
            .Where(name => name.StartsWith(prefix, StringComparison.Ordinal) && name.EndsWith(".cs", StringComparison.Ordinal))
            .Where(name => !name.Split('/').Any(part => part is "bin" or "obj"))
            .ToArray();

    private static string FindRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(System.IO.Path.Combine(directory.FullName, "ArcForges.Mobile.slnx")))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        throw new InvalidOperationException("ArcForges.Mobile.slnx was not found above the test output directory.");
    }

    private static string RunGit(params string[] arguments)
    {
        var start = new ProcessStartInfo("git")
        {
            WorkingDirectory = Root,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            StandardOutputEncoding = Encoding.UTF8,
        };
        foreach (var argument in arguments)
        {
            start.ArgumentList.Add(argument);
        }

        using var process = Process.Start(start) ?? throw new InvalidOperationException("git could not be started.");
        var output = process.StandardOutput.ReadToEnd();
        var error = process.StandardError.ReadToEnd();
        process.WaitForExit();
        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException("git " + string.Join(' ', arguments) + " failed: " + error);
        }

        return output;
    }
}
