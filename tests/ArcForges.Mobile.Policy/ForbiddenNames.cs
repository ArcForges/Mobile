// SPDX-License-Identifier: Apache-2.0
using System.Text;
using System.Text.Json;

namespace ArcForges.Mobile.Policy;

/// <summary>
/// The forbidden-term scanner (WP-05.02). The names come from the canonical naming policy of the pinned test-only package, verified
/// by NamingPolicy before use (AND.40 decision 18). Every tracked file is scanned by path and by
/// content, in UTF-8, UTF-16LE and UTF-16BE, as the Kotlin GOV.12 scanner did. Only the two compatibility tokens of that scanner
/// are admitted, and only as whole matches of the admitted spans.
/// </summary>
internal static class ForbiddenNames
{
    /// <summary>The canonical scanner compatibility tokens, admitted by GOV.12 (spelled apart so this file never contains them).</summary>
    private static readonly string[] AdmittedTokens = ["Arc" + "ImageNative", "arc" + "image-abi"];

    /// <summary>The forbidden names of the copied naming policy, as written.</summary>
    public static IReadOnlyList<string> Names(string productNamesJson)
    {
        using var document = JsonDocument.Parse(productNamesJson);
        return document.RootElement.GetProperty("forbiddenNames").EnumerateArray()
            .Select(row => row.GetProperty("name").GetString() ?? string.Empty)
            .ToArray();
    }

    /// <summary>The findings of one byte array: each forbidden name occurrence outside an admitted span, by encoding.</summary>
    public static IReadOnlyList<string> Findings(string label, byte[] data, IReadOnlyList<string> names)
    {
        var findings = new List<string>();
        foreach (var (encoding, encodingName) in new[]
                 {
                     (Encoding.UTF8, "utf-8"),
                     (Encoding.Unicode, "utf-16-le"),
                     (Encoding.BigEndianUnicode, "utf-16-be"),
                 })
        {
            var text = encoding.GetString(data);
            var admitted = AdmittedSpans(text);
            foreach (var name in names)
            {
                foreach (var start in Occurrences(text, name))
                {
                    if (!admitted.Any(span => start >= span.Start && start + name.Length <= span.End))
                    {
                        findings.Add(label + ": " + name + " at " + start + " (" + encodingName + ")");
                    }
                }
            }
        }

        return findings;
    }

    private static IEnumerable<int> Occurrences(string text, string name)
    {
        if (name.Length == 0)
        {
            yield break;
        }

        var index = text.IndexOf(name, StringComparison.OrdinalIgnoreCase);
        while (index >= 0)
        {
            yield return index;
            index = text.IndexOf(name, index + 1, StringComparison.OrdinalIgnoreCase);
        }
    }

    private static IEnumerable<(int Start, int End)> AdmittedSpans(string text)
    {
        foreach (var token in AdmittedTokens)
        {
            foreach (var start in Occurrences(text, token))
            {
                yield return (start, start + token.Length);
            }
        }
    }
}
