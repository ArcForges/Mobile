// SPDX-License-Identifier: Apache-2.0
using ArcForges.Mobile.Security;

namespace ArcForges.Mobile.Tests;

// AND.40 unit 3: the platform-neutral record rules of the Keystore probe. The Java interop probe needs a device and
// runs only as local opt-in (PRF.12); these tests check what the record says for any reported value.
public sealed class KeystoreProbeRecordTests
{
    [Fact]
    public void LevelIsNotReportedBelowApi31()
    {
        Assert.Equal("unreported below API 31", KeystoreProbeRecord.FormatSecurityLevel(30, 1));
        Assert.Equal("unreported below API 31", KeystoreProbeRecord.FormatSecurityLevel(26, null));
    }

    [Theory]
    [InlineData(0, "0 (SOFTWARE)")]
    [InlineData(1, "1 (TRUSTED_ENVIRONMENT)")]
    [InlineData(2, "2 (STRONGBOX)")]
    [InlineData(3, "3 (UNRECOGNISED)")]
    [InlineData(-1, "-1 (UNRECOGNISED)")]
    public void ReportedLevelKeepsItsNumberAndIsNeverUpgraded(int reported, string expected)
    {
        Assert.Equal(expected, KeystoreProbeRecord.FormatSecurityLevel(36, reported));
    }

    [Fact]
    public void MissingLevelAtApi31IsUnreportedRatherThanSoftware()
    {
        Assert.Equal("unreported", KeystoreProbeRecord.FormatSecurityLevel(33, null));
    }

    [Fact]
    public void RecordTextStatesThePlatformReportAndClaimsNoHardwareBacking()
    {
        var record = new KeystoreProbeRecord(36, 0, [new KeystoreProbeOutcome("record round-trips", true)]);

        var text = record.ToText();

        Assert.StartsWith(KeystoreProbeRecord.Header, text, StringComparison.Ordinal);
        Assert.Contains("api=36 securityLevel=0 (SOFTWARE)", text, StringComparison.Ordinal);
        Assert.Contains("The probe does not attest it.", text, StringComparison.Ordinal);
        Assert.DoesNotContain("hardware-backed", text, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("hardware backed", text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void AFailedCheckFailsTheWholeRecord()
    {
        var record = new KeystoreProbeRecord(
            33,
            1,
            [new KeystoreProbeOutcome("record round-trips", true), new KeystoreProbeOutcome("changed binding is rejected", false)]);

        Assert.False(record.AllPassed);
        Assert.Contains("FAIL changed binding is rejected", record.ToText(), StringComparison.Ordinal);
        Assert.Contains("result=failed", record.ToText(), StringComparison.Ordinal);
    }

    [Fact]
    public void AllChecksHoldingPassesTheRecord()
    {
        var record = new KeystoreProbeRecord(
            33,
            1,
            [new KeystoreProbeOutcome("key material cannot be exported", true), new KeystoreProbeOutcome("each record gets a fresh IV", true)]);

        Assert.True(record.AllPassed);
        Assert.Contains("result=passed", record.ToText(), StringComparison.Ordinal);
        Assert.Equal("1 (TRUSTED_ENVIRONMENT)", record.SecurityLevelText);
    }

    [Fact]
    public void RecordNeedsAtLeastOneCheck()
    {
        Assert.Throws<ArgumentException>(() => new KeystoreProbeRecord(36, 1, []));
    }

    [Fact]
    public void ApiLevelMustBePositive()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new KeystoreProbeRecord(0, null, [new KeystoreProbeOutcome("check", true)]));
    }
}
