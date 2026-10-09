// SPDX-License-Identifier: Apache-2.0
using System.Text;

namespace ArcForges.Mobile.Security;

/// <summary>One named check of the Keystore probe and whether it held on the device it ran on.</summary>
public sealed record KeystoreProbeOutcome(string Check, bool Passed);

/// <summary>
/// The Keystore probe record (AND.40 decision 11), in the same record rules as the Kotlin probe: the platform's
/// reported security level is written as reported and is never upgraded. Below API 31 the level is not reported.
/// The record makes no hardware claim: it states the platform's report for the probe key only.
/// </summary>
public sealed class KeystoreProbeRecord
{
    /// <summary>The first API level whose Keystore reports a security level.</summary>
    public const int SecurityLevelApi = 31;

    /// <summary>The header of every record; it marks the probe as a test-only harness.</summary>
    public const string Header = "ArcForges Keystore probe (test-only device harness, not a product diagnostic)";

    /// <summary>Text for a device below <see cref="SecurityLevelApi"/>, which does not report a level.</summary>
    public const string UnreportedBelowApi31 = "unreported below API 31";

    /// <summary>Creates a record. The reported level is null only when the platform did not report one.</summary>
    /// <exception cref="ArgumentOutOfRangeException">The API level is not positive.</exception>
    /// <exception cref="ArgumentException">The record has no outcome.</exception>
    public KeystoreProbeRecord(int apiLevel, int? reportedSecurityLevel, IEnumerable<KeystoreProbeOutcome> outcomes)
    {
        ArgumentNullException.ThrowIfNull(outcomes);
        if (apiLevel < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(apiLevel), "The API level must be positive.");
        }

        var list = outcomes.ToArray();
        if (list.Length == 0)
        {
            throw new ArgumentException("A probe record needs at least one outcome.", nameof(outcomes));
        }

        ApiLevel = apiLevel;
        ReportedSecurityLevel = reportedSecurityLevel;
        Outcomes = list;
    }

    /// <summary>The API level of the device the probe ran on.</summary>
    public int ApiLevel { get; }

    /// <summary>The security level the platform reported for the probe key, or null when none was reported.</summary>
    public int? ReportedSecurityLevel { get; }

    /// <summary>The checks, in the order they ran.</summary>
    public IReadOnlyList<KeystoreProbeOutcome> Outcomes { get; }

    /// <summary>True when every check held.</summary>
    public bool AllPassed => Outcomes.All(outcome => outcome.Passed);

    /// <summary>The security level as the record writes it.</summary>
    public string SecurityLevelText => FormatSecurityLevel(ApiLevel, ReportedSecurityLevel);

    /// <summary>
    /// Formats a reported level. The number is kept as reported; its name is added only for the three values the
    /// platform defines. Unknown numbers are marked UNRECOGNISED, never mapped to a stronger level.
    /// </summary>
    public static string FormatSecurityLevel(int apiLevel, int? reportedSecurityLevel)
    {
        if (apiLevel < SecurityLevelApi)
        {
            return UnreportedBelowApi31;
        }

        if (reportedSecurityLevel is not int level)
        {
            return "unreported";
        }

        return level switch
        {
            0 => "0 (SOFTWARE)",
            1 => "1 (TRUSTED_ENVIRONMENT)",
            2 => "2 (STRONGBOX)",
            _ => FormattableString.Invariant($"{level} (UNRECOGNISED)"),
        };
    }

    /// <summary>The record as text: header, api and level, the platform-report statement, each check, and the result.</summary>
    public string ToText()
    {
        var text = new StringBuilder();
        text.AppendLine(Header);
        text.AppendLine(FormattableString.Invariant($"api={ApiLevel} securityLevel={SecurityLevelText}"));
        text.AppendLine("The level is the platform's report for the probe key. The probe does not attest it.");
        foreach (var outcome in Outcomes)
        {
            text.AppendLine(FormattableString.Invariant($"{(outcome.Passed ? "pass" : "FAIL")} {outcome.Check}"));
        }

        text.AppendLine(AllPassed ? "result=passed" : "result=failed");
        return text.ToString();
    }
}
