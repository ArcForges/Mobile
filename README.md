# ArcForges Mobile

[![CI](https://github.com/ArcForges/Mobile/actions/workflows/ci.yml/badge.svg)](https://github.com/ArcForges/Mobile/actions/workflows/ci.yml)

A native Kotlin Android Hello World app, with a shared Compose UI and a JVM development preview. Android is the only product delivered by this repository. The current screen works offline; production ArcChat services, accounts and synchronization are future work.

| Component | Pinned version / purpose |
| --- | --- |
| JDK / Java and Kotlin bytecode | JDK 21 / JVM 21 (class major 65) |
| Gradle / Android Gradle Plugin | 9.7.1 / 9.4.0 |
| Kotlin / Compose Multiplatform | 2.4.20 / 1.12.0 |
| Compose Hot Reload | 1.2.0; JVM development sandbox only |
| Android SDK | compile/target 37, Build-Tools 37.0.0, minimum Android 8.0 (API 26) |
| Contracts | `io.github.arcforges:contracts-client:1.0.0-ci.25.1` from Maven Central |

`app` owns Android lifecycle, published Contracts integration and APK/AAB packaging. `shared` owns the greeting behavior and Compose UI, reused by Android and the `desktop` JVM preview target. Contracts source generation stays in the [Contracts repository](https://github.com/ArcForges/Contracts); this build uses released Maven artifacts and needs no adjacent checkout.

```sh
python eng/mobile.py hooks
./gradlew :app:installDebug
./gradlew :shared:hotRunDesktop
```

On Windows, use `gradlew.bat`. Set `JAVA_HOME` to JDK 21 and `ANDROID_HOME` to an SDK containing the components above. The preview task provisions a compatible JetBrains Runtime separately from the Gradle JDK. See [development.md](docs/development.md) for checks, dependency updates and Android Studio Live Edit.

Every main-branch push builds, checks and tests an immutable candidate, then signs and publishes its APK and AAB to [GitHub Releases](https://github.com/ArcForges/Mobile/releases). Versions advance automatically. PR and manual runs validate only. These are development prereleases, not Google Play submissions. [releasing.md](docs/releasing.md) documents the persistent signing identity, GitHub configuration, versioning and recovery.

Original application code and repository tooling are licensed under [Apache-2.0](LICENSE). Dependencies retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
