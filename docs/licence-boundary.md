# Project and Android distribution licences (WP00.02)

The accepted [Design declaration profile](https://github.com/ArcForges/ArcForges-Design/blob/3825a24fd7530cb51c3fb30b757e644ebab33459/docs/architecture/01-solution-and-project-layout.md#41-project-declaration-and-verification-profile)
assigns all three Mobile Gradle scopes to `Apache-2.0` / `Apache`. Each build file
declares its own metadata. `eng/policy/licence-boundary.json` records the complete
inventory; `eng/licences.py projects` discovers actual tracked/nonignored manifests
and rejects missing declarations, other build systems and unpublished/unknown
first-party inputs. Original Mobile tooling is Apache-2.0 and imports no AGPL checker.

`eng/licences.gradle.kts` checks effective Gradle project properties and references
after evaluation. The app's `verifyAndroidLicences` task resolves release, debug,
instrumentation and core-library-desugaring configurations inside the owning Gradle
project. The closed inventory in `eng/policy/android-licences.json` identifies each
resolved component, exact distributable artifact hashes, licence evidence and
retained notice hashes. Ordinary builds keep strict Gradle locking and checksum
verification; unknown graph nodes, changed bytes, unreviewed native payloads or
missing notice text fail before compilation/packaging.

The audited Android closure includes Kotlin/AndroidX/Compose, Contracts, Connect,
OkHttp/Okio, protobuf and test dependencies. Apache-2.0, BSD-3-Clause and MIT apply to
the reviewed libraries. JUnit's EPL-1.0 applies only to instrumentation, never an
application runtime. Complete upstream notices live under `third-party/notices`,
deduplicated by their normalized UTF-8/LF SHA-256. Each component retains its own
attribution and evidence links; this does not relicense any dependency.

AndroidX `graphics-path:1.0.1` contributes the four reviewed ABI-specific native
libraries. Its [release source](https://android.googlesource.com/platform/frameworks/support/+/8a05a22af450d589ef911d772a001a49dcb05b71/graphics/graphics-path/)
and CMake inputs were checked, including the Apache-2.0 math headers and their
copyright notices. ELF dependencies are only platform `libc`, `libdl` and `libm`;
the build uses `-nostdlib++`. The compiler-rt licence, including its LLVM exception
and MIT sections, is retained from the compiler revision identified in those ELF
files. The policy preserves source URLs/hashes, native hashes and system dependencies.

The [accepted remediation](https://github.com/ArcForges/ArcForges-Design/blob/3825a24fd7530cb51c3fb30b757e644ebab33459/docs/architecture/01-solution-and-project-layout.md#42-current-android-dependency-conflict-and-remediation)
removes the optional `desugar_jdk_libs:2.1.5` implementation because its published
GPL-2.0 with Classpath exception conflicts with D-004's explicit GPL-family exclusion.
The core-library configuration must remain empty. Normal D8/R8 language desugaring,
JVM 21, API 26 minimum, app IDs and signing identity remain unchanged. API 26 and 36
both run debug instrumentation and the same minified release candidate against the
real Cloud service; successful source/fixture checks cannot replace these device gates.

The generated `THIRD_PARTY_NOTICES.txt` and `licence-closure.json` are registered as
Android generated assets with an explicit task dependency. Release/debug/test APKs
and the AAB retain them. Candidate staging rejects a dirty/wrong-commit receipt,
changed policy/locks, stripped assets or unexpected native files. Candidate hashes
cover both companion files. Signing re-verifies that candidate and publishes the
same companions with hashes in `release.json` and `SHA256SUMS`; it never rebuilds code.

## Maintenance and evidence

```sh
python eng/licences.py projects
python -m unittest discover -s eng/tests -v
./gradlew :app:verifyAndroidLicences
```

For a dependency update, first resolve the proposed graphs with the documented
Gradle lock/checksum maintenance commands. Inspect `android-resolved.json`, the
published POM/parent licence declarations, every delivered JAR/AAR (including nested
JAR notices), and native source/compiler dependencies. Review and update the closed
policy and retained texts before packaging; never accept an unknown licence or hash
automatically. Re-run ordinary strict builds and both device APIs, including with an
empty Gradle cache when tool/plugin metadata changes. CI retains source/effective
project reports and the resolved closure alongside the immutable candidate.

On 2026-09-18, required lint found AGP 9.4.1 and Contracts 1.0.0-ci.44.1 available.
The official Google Maven AGP POM and Contracts' three-registry publication were
verified before updating exact catalog/lock/checksum inputs. These are compatible
patch/producer updates under Mobile architecture section 3; no product rule changes.

Gitleaks' generic API-key rule also matched the public SLF4J JAR checksum because
its filename contains `api`. `.gitleaks.toml` retains all default rules and excludes
only that exact reviewed checksum line in the Android policy file. The checksum
was verified against Maven Central; changed values and other paths remain scanned.

This evidence covers the current Android candidate, not a future dependency graph,
Play approval, physical devices, full ArcChat behavior or the JVM development runtime
as a shipped product. F-023 closes only with this actual distribution closure and
its required runtime/publication evidence, never from the first-party metadata alone.
