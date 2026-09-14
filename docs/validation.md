# Bootstrap validation

The initial bootstrap was checked on Windows with Temurin 21.0.11, Gradle 9.7.1, AGP 9.4.0 and the committed Kotlin/Compose versions. Evidence files produced during local checks are kept in the ignored `artifacts` directory, not distributed as source.

- Android debug APK, instrumented test APK, R8-minified release APK and release AAB built successfully. Android lint passed with warnings treated as errors.
- Published Contracts serialization and in-process coroutine gRPC success/error tests passed. Shared greeting tests passed on JVM desktop and Android host test targets.
- The bytecode guard inspected authored Android/shared classes and verified class major 65 (JVM 21).
- Two instrumentation tests passed on the Android SDK API 36 x86_64 emulator, including interaction, empty-name handling and Activity recreation/state restoration. A separate install/launch check observed `Hello, World!` through Android's UI hierarchy.
- Compose Hot Reload 1.2.0 ran the shared UI on a provisioned JetBrains Runtime 21. A source edit and its reversal updated the same running application (unchanged process ID). The Hot Reload MCP status reported `successfulReloads: 2`, `failedReloads: 0`, `reloadState: ok`; the semantic tree confirmed the changed and restored text.
- Repository checks, release version/tampering guard tests and actionlint 1.7.12 passed. Windows and Linux dependency graphs have separate preview lockfiles and shared checksum verification. A full Linux execution remains a CI check, distinct from resolving its artifacts on Windows.

The persistent Android signing identity and the `android-release` GitHub environment were provisioned. PRs cannot execute the main-only release job. Local signing/install results and GitHub CI results must be assessed separately from actual main-branch publication; a PR build does not prove a GitHub Release or Play deployment. No physical-device, Play Console or production backend validation is claimed.
