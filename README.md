# ArcForges Mobile

[![CI](https://github.com/ArcForges/Mobile/actions/workflows/ci.yml/badge.svg)](https://github.com/ArcForges/Mobile/actions/workflows/ci.yml)

A native Kotlin Android app that calls the real Cloud Hello API at `https://arcforges.com/api`, with a shared Compose UI and an offline JVM development preview. Android is the only product platform and release target in this repository. Kotlin Multiplatform and Compose Multiplatform are implementation technologies for source reuse; the desktop JVM target is only a local, offline development preview. No desktop product, iOS/Swift app or cross-platform UI product is delivered or claimed. Production ArcChat services, accounts and synchronization are future work.

| Component | Pinned version / purpose |
| --- | --- |
| JDK / Java and Kotlin bytecode | JDK 21 / JVM 21 (class major 65) |
| Gradle / Android Gradle Plugin | 9.8.0 / 9.4.1 |
| Kotlin / Compose Multiplatform implementation | 2.4.20 / 1.12.1; source reuse does not imply other product platforms |
| Compose Hot Reload | 1.2.0; JVM development sandbox only |
| Android SDK | compile/target 37, Build-Tools 37.0.0, minimum Android 8.0 (API 26) |
| Contracts | `io.github.arcforges:contracts-connect-client:1.0.0-ci.60.1` from Maven Central |
| Transport | Connect-Kotlin 0.9.0, binary gRPC-Web over platform-validated HTTPS |

`app` owns Android lifecycle, published Contracts integration and APK/AAB packaging. `shared` owns the greeting behavior and Compose UI source reused by Android and the `desktop` JVM preview target; that preview is development-only, not a desktop product or release. Contracts source generation stays in the [Contracts repository](https://github.com/ArcForges/Contracts); this build uses released Maven artifacts and needs no adjacent checkout.

Enter a name and press **Say hello** to call Cloud. The app shows progress, the server's greeting or a recoverable error. It has a five-second RPC deadline and never retries automatically. Recreating the Activity preserves the name and completed result, cancels pending work and allows a fresh manual request. The anonymous Hello needs no login, API token or Cloudflare account. The preview is labeled **Local preview · Works offline** and makes no Cloud calls.

```sh
python eng/mobile.py hooks
./gradlew :app:installDebug
./gradlew :shared:hotRunDesktop
```

On Windows, use `gradlew.bat`. Set `JAVA_HOME` to JDK 21 and `ANDROID_HOME` to an SDK containing the components above. The preview task provisions a compatible JetBrains Runtime separately from the Gradle JDK. See [development.md](docs/development.md) for checks, dependency updates and Android Studio Live Edit.

Main-branch pushes build, check and test an immutable candidate; after required gates pass, the workflow signs and publishes its APK and AAB to [GitHub Releases](https://github.com/ArcForges/Mobile/releases) as development prereleases. The APK is directly installable on Android 8.0 or newer; the AAB is a signed upload bundle, not an installable file. PR and manual runs validate only. No Google Play listing, submission or deployment is currently configured or claimed. See the platform and distribution matrix below and the [release procedure](docs/releasing.md) for the exact boundary.

## Platform and distribution matrix

| Surface or channel | Current status | Boundary |
| --- | --- | --- |
| Android application | Sole product and release target | Release application ID `io.github.arcforges.mobile`; minimum API 26 and target API 37. This is the artifact's declared OS range, not a claim that every device/profile has been physically validated. |
| GitHub Releases | Current development-prerelease distribution | After a successful main-branch candidate and protected signing workflow, releases publish a signed APK and AAB. The APK is directly installable on Android 8.0 or newer; the AAB is an upload bundle and is not directly installable. Pull requests and manual validation runs do not publish. |
| Google Play or another app store | No current listing, submission or deployment | The AAB is not submitted by this repository's workflow. No Play listing, Play App Signing or store availability is claimed. A store channel would require a separate approved task and release evidence; this document does not promise one. |
| Desktop JVM | Development preview only | `:shared:hotRunDesktop` starts a local, offline preview for development. It is not an end-user desktop product and no desktop installer or release is published. |
| iOS / Swift | Outside the current delivery | There is no iOS app or Swift target in this product scope, and no iOS artifact or support claim. |
| KMP / cross-platform UI product | Not a product commitment | Kotlin Multiplatform and Compose Multiplatform are implementation technologies for shared source. They do not imply desktop or iOS product support, a cross-platform UI promise, or any additional delivery/completion gate. |

Device, store and complete-product acceptance require their own evidence. A successful build, signed candidate or GitHub prerelease does not establish physical-device coverage, store publication or support on a platform not listed as the Android product target.

Original application code and repository tooling are licensed under [Apache-2.0](LICENSE). Dependencies retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The [project and Android licence gate](docs/licence-boundary.md) verifies actual resolved artifacts and embeds the reviewed notices before packaging. CI has no device/emulator, live Cloud or public-install gates. Runtime tools are local opt-in; green CI does not claim device or full product acceptance.

Build identity and independent version sources are described in [docs/build-identity.md](docs/build-identity.md). The published `build-identity.json` is also embedded in every Android archive and read by the installed app.
