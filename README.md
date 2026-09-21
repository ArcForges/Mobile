# ArcForges Mobile

[![CI](https://github.com/ArcForges/Mobile/actions/workflows/ci.yml/badge.svg)](https://github.com/ArcForges/Mobile/actions/workflows/ci.yml)

A native Kotlin Android app that calls the real Cloud Hello API at `https://arcforges.com/api`, with a shared Compose UI and an offline JVM development preview. Android is the only product delivered by this repository. Production ArcChat services, accounts and synchronization are future work.

| Component | Pinned version / purpose |
| --- | --- |
| JDK / Java and Kotlin bytecode | JDK 21 / JVM 21 (class major 65) |
| Gradle / Android Gradle Plugin | 9.7.1 / 9.4.1 |
| Kotlin / Compose Multiplatform | 2.4.20 / 1.12.0 |
| Compose Hot Reload | 1.2.0; JVM development sandbox only |
| Android SDK | compile/target 37, Build-Tools 37.0.0, minimum Android 8.0 (API 26) |
| Contracts | `io.github.arcforges:contracts-connect-client:1.0.0-ci.60.1` from Maven Central |
| Transport | Connect-Kotlin 0.9.0, binary gRPC-Web over platform-validated HTTPS |

`app` owns Android lifecycle, published Contracts integration and APK/AAB packaging. `shared` owns the greeting behavior and Compose UI, reused by Android and the `desktop` JVM preview target. Contracts source generation stays in the [Contracts repository](https://github.com/ArcForges/Contracts); this build uses released Maven artifacts and needs no adjacent checkout.

Enter a name and press **Say hello** to call Cloud. The app shows progress, the server's greeting or a recoverable error. It has a five-second RPC deadline and never retries automatically. Recreating the Activity preserves the name and completed result, cancels pending work and allows a fresh manual request. The anonymous Hello needs no login, API token or Cloudflare account. The preview is labeled **Local preview Â· Works offline** and makes no Cloud calls.

```sh
python eng/mobile.py hooks
./gradlew :app:installDebug
./gradlew :shared:hotRunDesktop
```

On Windows, use `gradlew.bat`. Set `JAVA_HOME` to JDK 21 and `ANDROID_HOME` to an SDK containing the components above. The preview task provisions a compatible JetBrains Runtime separately from the Gradle JDK. See [development.md](docs/development.md) for checks, dependency updates and Android Studio Live Edit.

Every main-branch push builds, checks and tests an immutable candidate, then signs and publishes its APK and AAB to [GitHub Releases](https://github.com/ArcForges/Mobile/releases). Versions advance automatically. PR and manual runs validate only. These are development prereleases, not Google Play submissions. [releasing.md](docs/releasing.md) documents the persistent signing identity, GitHub configuration, versioning and recovery.

Original application code and repository tooling are licensed under [Apache-2.0](LICENSE). Dependencies retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The [project and Android licence gate](docs/licence-boundary.md) verifies actual resolved artifacts and embeds the reviewed notices before packaging. Both minimum API 26 and API 36 device tests precede signing.

Build identity and independent version sources are described in [docs/build-identity.md](docs/build-identity.md). The published `build-identity.json` is also embedded in every Android archive and read by the installed app.
