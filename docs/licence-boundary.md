# Project and Android distribution licences (WP00.02)

The accepted [Design declaration profile](https://github.com/ArcForges/ArcForges-Design/blob/3825a24fd7530cb51c3fb30b757e644ebab33459/docs/architecture/01-solution-and-project-layout.md#41-project-declaration-and-verification-profile)
assigns the Mobile projects to `Apache-2.0` / `Apache`. Each project declares its own metadata in its csproj (`PackageLicenseExpression` and `LicenceBoundary`). `eng/policy/dotnet-licence-boundary.json` registers the reviewed .NET projects, and `eng/licences.py projects` audits them against their declarations. The retired Gradle roster in `eng/policy/licence-boundary.json` stays empty: no project is built by Gradle any more (AND.40 PR B). The audit rejects an unregistered project, a build system other than a reviewed `.csproj`, a linked source or a submodule. Original Mobile tooling is Apache-2.0 and imports no AGPL checker.

The MAUI NuGet closure is checked by `eng/licences.py maui`. It requires exactly one Android target (`net10.0-android36.1`), a lock version 2, and that every locked package is admitted in `eng/policy/nuget-admission.json` with the same version and content hash. Only the admitted licences are accepted: Apache-2.0, BSD-2-Clause, BSD-3-Clause, MIT, Zlib and Unicode-3.0. AGPL, GPL, SSPL, BUSL, proprietary and unlicensed packages are refused. Build-only and test-only packages are classified separately and never shipped, and `ArcForges.Build.Policy` is not part of the closure.

The retained notice texts live under `third-party/notices`, named by their normalized UTF-8/LF SHA-256. `python -I eng/maui_notices.py` checks the closure (`closure`), re-proves it against the shipped APK (`reproof`), checks the notice data and retained texts (`check`), derives the distribution notice set (`distribution`) and gates the release (`release-ready`). A package without a licence file in its nupkg needs a retained notice, listed in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Workload packs and the Mono runtime bundles are recorded in `eng/policy/maui-notices.json`; the GPL-3.0 binutils text of the Android SDK bundle covers build-host tools that are not redistributed, and `maui_notices.apk_host_only` proves that from the APK contents (AND.40 decision 20).

The shipped Android closure is Apache-2.0 and permissive, and each retained notice keeps its own attribution. Mobile does not relicense any dependency.

The Kotlin closure (`eng/policy/android-licences.json`, the Gradle licence checks and the JUnit EPL-1.0 test-only dependency) retired with the Kotlin baseline in AND.40 PR B. Its records remain under `eng/provenance` as immutable history.

## Maintenance and evidence

Changing a NuGet package, a workload pack or a retained notice needs an admission record under `eng/policy/nuget-admission.json` or `eng/policy/dependency-reviews`, the regenerated closure and a passing `maui_notices` run before the candidate is sealed. Licence checks run offline in CI on Windows and Linux. A licence gate passing is not a legal opinion; it shows that the reviewed bytes and their notices agree.
