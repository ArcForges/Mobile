// SPDX-License-Identifier: Apache-2.0
using System.Text.Json;

namespace ArcForges.Mobile.Policy;

// AND.40 unit 4, WP-05.04: the seven BAN-* rules over the application and core C# sources, each with a negative fixture.
public sealed class BannedApiTests
{
    private static readonly IReadOnlyList<string> Providers = ProviderNames();

    [Fact]
    public void TheSevenReviewedRulesAreTheCatalogue()
    {
        Assert.Equal(
            new[] { "BAN-REFLECTION", "BAN-CODEGEN", "BAN-BLOCKING", "BAN-PROVIDER", "BAN-LOGGING", "BAN-MONEY", "BAN-POINTER" },
            BannedApi.RuleIds);
    }

    [Fact]
    public void TheApplicationAndCoreSourcesViolateNoRule()
    {
        var findings = new List<string>();
        foreach (var path in Repository.CSharpSources("src/"))
        {
            findings.AddRange(BannedApi.Scan(path, Repository.ReadText(path), Providers).Select(rule => path + ": " + rule));
        }

        Assert.NotEmpty(Repository.CSharpSources("src/"));
        Assert.Empty(findings);
    }

    [Theory]
    [InlineData(BannedApi.Reflection, "src/ArcForges.Mobile/Probe.cs", "var type = Type.GetType(\"Probe\");")]
    [InlineData(BannedApi.Reflection, "src/ArcForges.Mobile/Probe.cs", "var made = Activator.CreateInstance(type);")]
    [InlineData(BannedApi.Reflection, "src/ArcForges.Mobile/Probe.cs", "var field = type.GetField(\"value\");")]
    [InlineData(BannedApi.Codegen, "src/ArcForges.Mobile/Probe.cs", "var method = new DynamicMethod(\"x\", typeof(void), null);")]
    [InlineData(BannedApi.Codegen, "src/ArcForges.Mobile/Probe.cs", "var source = CSharpScript.EvaluateAsync(\"1\");")]
    [InlineData(BannedApi.Blocking, "src/ArcForges.Mobile/Probe.cs", "var value = FetchAsync().Result;")]
    [InlineData(BannedApi.Blocking, "src/ArcForges.Mobile/Probe.cs", "task.Wait();")]
    [InlineData(BannedApi.Blocking, "src/ArcForges.Mobile/Probe.cs", "Thread.Sleep(10);")]
    [InlineData(BannedApi.Provider, "src/ArcForges.Mobile/Probe.cs", "using Paddle.Client;")]
    [InlineData(BannedApi.Provider, "src/ArcForges.Mobile/Probe.cs", "var checkout = Payoneer.Checkout();")]
    [InlineData(BannedApi.Logging, "src/ArcForges.Mobile/Probe.cs", "Console.WriteLine(token);")]
    [InlineData(BannedApi.Logging, "src/ArcForges.Mobile/Probe.cs", "logger.LogInformation(\"ok\"); Log.Debug(\"tag\", message);")]
    [InlineData(BannedApi.Money, "src/ArcForges.Mobile/Billing/Balance.cs", "var amount = 1.25;")]
    [InlineData(BannedApi.Pointer, "src/ArcForges.Mobile/Probe.cs", "unsafe { var p = stackalloc byte[4]; }")]
    public void EachRuleRefusesItsNegativeFixture(string rule, string path, string source)
    {
        Assert.Contains(rule, BannedApi.Scan(path, source, Providers));
    }

    [Theory]
    [InlineData("src/ArcForges.Mobile/Probe.cs", "var value = await FetchAsync();")]
    [InlineData("src/ArcForges.Mobile/Probe.cs", "await Task.Delay(1);")]
    [InlineData("src/ArcForges.Mobile/Diagnostics/BuildInformation.cs", "using System.Reflection;")]
    [InlineData("src/ArcForges.Mobile/Probe.cs", "var list = new List<int>();")]
    [InlineData("src/ArcForges.Mobile/Probe.cs", "var amount = 125;")]
    [InlineData("src/ArcForges.Mobile/Diagnostics/Build.cs", "var amount = 1.25;")]
    [InlineData("src/ArcForges.Mobile/Probe.cs", "Console.WriteLine(\"ready\");")]
    [InlineData("src/ArcForges.Mobile/Probe.cs", "// Paddle is the merchant of record.")]
    [InlineData("src/core/ArcForges.Mobile.Network/adapter/Paddle.cs", "using Paddle.Client;")]
    [InlineData("src/core/ArcForges.Mobile.Security/native-adapter/Probe.cs", "unsafe { var p = stackalloc byte[4]; }")]
    public void BenignSourceIsAccepted(string path, string source)
    {
        Assert.Empty(BannedApi.Scan(path, source, Providers));
    }

    private static IReadOnlyList<string> ProviderNames()
    {
        using var document = JsonDocument.Parse(NamingPolicy.Verified);
        return document.RootElement.GetProperty("providers").EnumerateArray()
            .Select(row => row.GetProperty("name").GetString() ?? string.Empty)
            .ToArray();
    }
}
