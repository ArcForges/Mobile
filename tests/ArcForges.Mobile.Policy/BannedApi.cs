// SPDX-License-Identifier: Apache-2.0
using System.Text.RegularExpressions;

namespace ArcForges.Mobile.Policy;

/// <summary>
/// The seven BAN-* rules of GOV.12 (WP-05.04), authored in Mobile for the C# application sources. The rule identifiers and
/// intent are those of the Kotlin policy this replaces (gradle/policy/mobile-policy.gradle.kts), expressed for C#: reflection,
/// runtime code generation, blocking waits, provider SDK use outside adapters, logging of sensitive values, binary floating point
/// for money, and raw pointers. The scanned sources are the C# files under src/ (never tests), so the fixtures in the tests
/// may name the banned APIs.
/// </summary>
internal static class BannedApi
{
    public const string Reflection = "BAN-REFLECTION";
    public const string Codegen = "BAN-CODEGEN";
    public const string Blocking = "BAN-BLOCKING";
    public const string Provider = "BAN-PROVIDER";
    public const string Logging = "BAN-LOGGING";
    public const string Money = "BAN-MONEY";
    public const string Pointer = "BAN-POINTER";

    /// <summary>The rule identifiers, in catalogue order.</summary>
    public static readonly IReadOnlyList<string> RuleIds =
        [Reflection, Codegen, Blocking, Provider, Logging, Money, Pointer];

    private const RegexOptions Options = RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.Singleline;

    private static readonly Regex ReflectionPattern = new(
        @"\bActivator\s*\.\s*CreateInstance\b|\bType\s*\.\s*GetType\s*\(|\bAssembly\s*\.\s*Load(?:From|File)?\s*\(|\.\s*Get(?:Declared)?(?:Method|Field|Constructor)\s*\(",
        Options);

    private static readonly Regex CodegenPattern = new(
        @"\bSystem\.Reflection\.Emit\b|\bDynamicMethod\b|\bAssemblyBuilder\b|\bILGenerator\b|\bCSharpScript\b|\bMicrosoft\.CodeAnalysis\.CSharp\.Scripting\b|\bCSharpCodeProvider\b|\bCodeDom\b|\bExpression\s*\.\s*Lambda\b[^;]*\.\s*Compile\s*\(",
        Options);

    private static readonly Regex BlockingPattern = new(
        @"\.\s*Result\b|\.\s*Wait\s*\(|\bGetAwaiter\s*\(\s*\)\s*\.\s*GetResult\s*\(|\bThread\s*\.\s*Sleep\s*\(|\bTask\s*\.\s*Wait(?:All|Any)\s*\(",
        Options);

    private static readonly Regex LoggingPattern = new(
        @"\b(?:Console\s*\.\s*Write(?:Line)?|Debug\s*\.\s*Write(?:Line)?|Trace\s*\.\s*Write(?:Line)?|Log\s*\.\s*(?:Verbose|Debug|Info|Warn|Error|Write)|\.\s*Log(?:Trace|Debug|Information|Warning|Error|Critical)|System\s*\.\s*out\s*\.\s*print(?:ln)?)\s*\([^)]*\b(?:password|token|secret|credential|authorization|message|content)\b",
        Options);

    private static readonly Regex MoneyPathPattern = new("money|credit|price|balance|payment|payout", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex MoneyPattern = new(@"\b(?:float|double|single)\b|\b[0-9]+\.[0-9]+\b", Options);

    private static readonly Regex PointerPattern = new(
        @"\bunsafe\b|\bstackalloc\b|\bfixed\s*\(|\bMarshal\s*\.\s*(?:AllocHGlobal|FreeHGlobal|ReadIntPtr|WriteIntPtr|PtrToStructure|StructureToPtr)\b",
        Options);

    /// <summary>
    /// The rules a C# source violates. <paramref name="providers"/> are the provider names of the naming policy. Returns the
    /// violated rule identifiers in catalogue order; empty when the source is clean.
    /// </summary>
    public static IReadOnlyList<string> Scan(string path, string source, IReadOnlyList<string> providers)
    {
        var normalizedPath = path.Replace('\\', '/').ToLowerInvariant();
        var violations = new List<string>();
        if (ReflectionPattern.IsMatch(source))
        {
            violations.Add(Reflection);
        }

        if (CodegenPattern.IsMatch(source))
        {
            violations.Add(Codegen);
        }

        if (BlockingPattern.IsMatch(source))
        {
            violations.Add(Blocking);
        }

        if (ProviderViolation(normalizedPath, source, providers))
        {
            violations.Add(Provider);
        }

        if (LoggingPattern.IsMatch(source))
        {
            violations.Add(Logging);
        }

        if (MoneyPathPattern.IsMatch(normalizedPath) && MoneyPattern.IsMatch(source))
        {
            violations.Add(Money);
        }

        if (!normalizedPath.Contains("/native-adapter/", StringComparison.Ordinal) && PointerPattern.IsMatch(source))
        {
            violations.Add(Pointer);
        }

        return violations;
    }

    private static bool ProviderViolation(string normalizedPath, string source, IReadOnlyList<string> providers)
    {
        if (normalizedPath.Contains("/adapter/", StringComparison.Ordinal) || normalizedPath.Contains("/adapters/", StringComparison.Ordinal))
        {
            return false;
        }

        return providers.Any(provider =>
        {
            var escaped = Regex.Escape(provider);
            var pattern = new Regex(
                @"(?im)(?:\b" + escaped + @"\b[^\r\n]*(?:sdk|client|checkout|payment)\b|\b(?:sdk|client|checkout|payment)[^\r\n]*\b" + escaped + @"\b)",
                RegexOptions.CultureInvariant);
            return pattern.IsMatch(source);
        });
    }
}
