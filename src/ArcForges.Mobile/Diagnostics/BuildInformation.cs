// SPDX-License-Identifier: Apache-2.0
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;

namespace ArcForges.Mobile.Diagnostics;

/// <summary>
/// Build information from the embedded build-identity.json (AND.40 decision 7; WP02.04). Read on the device only:
/// no server is contacted and no build environment variable is consulted. The report is shown as the Kotlin
/// Build information dialog shows it.
/// </summary>
internal static class BuildInformation
{
    internal const string ResourceName = "build-identity.json";
    private const string Schema = "arcforges.build-identity.v1";
    private const string Owner = "Mobile";
    private const string NotEmbedded = "No build identity is embedded in this build. Release builds embed build-identity.json.";
    private const string Unreadable = "The embedded build identity could not be read.";

    /// <summary>The text of the embedded report, or a plain statement when none is embedded or it cannot be read.</summary>
    public static string Load()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(ResourceName);
        if (stream is null)
        {
            return NotEmbedded;
        }

        using var buffer = new MemoryStream();
        stream.CopyTo(buffer);
        return Describe(buffer.ToArray());
    }

    /// <summary>Formats a build-identity.json document. Malformed or foreign documents yield the unreadable text.</summary>
    public static string Describe(byte[] report)
    {
        try
        {
            using var document = JsonDocument.Parse(report);
            var root = document.RootElement;
            if (root.GetProperty("schema").GetString() != Schema || root.GetProperty("owner").GetString() != Owner)
            {
                return Unreadable;
            }

            return Format(root, Convert.ToHexString(SHA256.HashData(report)).ToLowerInvariant());
        }
        catch (Exception failure) when (failure is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            return Unreadable;
        }
    }

    private static string Format(JsonElement root, string reportSha256)
    {
        var artifact = root.GetProperty("artifact");
        var build = root.GetProperty("build");
        var lines = new List<string>
        {
            $"ArcForges {artifact.GetProperty("version").GetString()}",
            $"Android versionCode: {root.GetProperty("packaging").GetProperty("androidVersionCode").GetInt32()}",
            $"Source: {build.GetProperty("sourceCommit").GetString()}",
            $"Build: {build.GetProperty("buildId").GetString()}",
            $"Kind: {build.GetProperty("kind").GetString()}; dirty: {(build.GetProperty("dirty").GetBoolean() ? "true" : "false")}",
            $"Source UTC epoch: {build.GetProperty("sourceDateEpoch").GetInt64()}",
            $"Pipeline: {PipelineText(build)}",
            $"Report SHA-256: {reportSha256}",
        };

        foreach (var axis in root.GetProperty("axes").EnumerateObject())
        {
            lines.Add(string.Empty);
            lines.Add($"{axis.Name}: {axis.Value.GetProperty("status").GetString()}");
            if (axis.Value.TryGetProperty("values", out var values))
            {
                if (axis.Name == "PackageVersion")
                {
                    lines.Add($"{values.GetArrayLength()} locked runtime packages; full inventory in build-identity.json.");
                }
                else
                {
                    foreach (var value in values.EnumerateArray())
                    {
                        lines.Add($"{value.GetProperty("subject").GetString()}: {value.GetProperty("version").GetString()}");
                    }
                }
            }
            else
            {
                lines.Add(axis.Value.GetProperty("reason").GetString() ?? string.Empty);
                if (axis.Value.TryGetProperty("producer", out var producer))
                {
                    lines.Add($"Producer: {producer.GetString()}");
                }
            }
        }

        return string.Join('\n', lines);
    }

    private static string PipelineText(JsonElement build)
    {
        return build.TryGetProperty("pipelineRun", out var run) && run.ValueKind == JsonValueKind.String
            ? run.GetString() ?? "local"
            : "local";
    }
}
