# ArcForges Mobile

[![CI](https://github.com/ArcForges/Mobile/actions/workflows/ci.yml/badge.svg)](https://github.com/ArcForges/Mobile/actions/workflows/ci.yml)

A native .NET MAUI Android app that calls the Cloud Hello API at `https://arcforges.com/api`. Android is the only product platform and release target in this repository. The Kotlin/Compose app, its Kotlin Multiplatform module and its Gradle build were retired in AND.40 PR B; they remain in the git history and in the historical Kotlin releases. No desktop product, iOS or macOS app is delivered or claimed. Production ArcChat services, accounts and synchronization are future work.

| Component | Pinned version / purpose |
| --- | --- |
| .NET SDK | 10.0.400 with `rollForward` disabled ([global.json](global.json)) |
| Workload set | `dotnet workload install android maui-android --version 10.0.401` (Android 36.1.69, MAUI Android 10.0.20) |
| Target framework | `net10.0-android` for the shipped app; host-run test projects use `net10.0` |
| Android SDK | Compile 36.1, target API 36.1 (D-016), Build-Tools 36.1.0, minimum Android 8.0 (API 26) |
| Runtime | Mono with AOT for Release, R8 trimming (`UseMonoRuntime` and `AndroidLinkTool=r8`) |
| Contracts | `ArcForges.Contracts.Events` and `ArcForges.Contracts.PublicApi` 1.0.0-ci.324.1 from NuGet |
| Transport | `Grpc.Net.Client.Web` 2.84.0, binary gRPC-Web over platform-validated HTTPS |
| Application ID | `com.arcforges.mobile` |

The shipped projects live under `src/`: `ArcForges.Mobile` (the app), `ArcForges.Mobile.Network` (the Hello transport and streaming consumer) and `ArcForges.Mobile.Security` (the Keystore probe). The host-run tests live under `tests/`. Locked restores use `packages.lock.json` into a clean `NUGET_PACKAGES` folder.

Enter a name and press **Say hello** to call Cloud. The app shows progress, the server's greeting or a recoverable error. The call has a five-second RPC deadline and a ten-second call timeout, and it never retries automatically. The anonymous Hello needs no login, API token or Cloudflare account.

```sh
python eng/mobile.py hooks
python eng/mobile.py check
dotnet build src/ArcForges.Mobile/ArcForges.Mobile.csproj -f net10.0-android -c Debug
dotnet test tests/ArcForges.Mobile.Tests/ArcForges.Mobile.Tests.csproj -c Release
```

Install the workload set and the Android SDK components from the table above before building. Set `ANDROID_HOME` to an SDK that contains them. See [development.md](docs/development.md) for the checks and [maui-toolchain.md](docs/maui-toolchain.md) for the pinned toolchain and its local gaps.

Main-branch pushes build and test the MAUI candidate on Windows and Linux. After the required gates pass, the protected `android-release` environment signs the candidate and publishes it to [GitHub Releases](https://github.com/ArcForges/Mobile/releases) as an Android prerelease tagged `android-VERSION`. The release is a signed APK with its companions, and it is directly installable on Android 8.0 or newer. No AAB is produced by the MAUI path; the Play channel is out of scope. Pull requests and manual validation runs do not publish. See the [release procedure](docs/releasing.md) for the exact boundary.

## Platform and distribution matrix

| Surface or channel | Current status | Boundary |
| --- | --- | --- |
| Android application | Sole product and release target | .NET MAUI, application ID `com.arcforges.mobile`, minimum API 26 and target API 36.1. This is the artifact's declared OS range, not a claim that every device or profile has been physically validated. |
| GitHub Releases | Development-prerelease distribution | After a successful main-branch candidate and the protected signing job, releases publish a signed APK with its companions under `android-VERSION`. Pull requests and manual validation runs do not publish. |
| Google Play or another app store | No current listing, submission or deployment | No store listing, Play App Signing or store availability is claimed. A store channel would need a separate approved task and release evidence. |
| Desktop | Not a product target | The Kotlin desktop JVM preview is retired with the Kotlin baseline. No desktop product, installer or release is published. |
| iOS / macOS | Out of scope | There is no iOS or macOS app, target or support claim. |

Device, emulator, store and complete-product acceptance require their own evidence. A successful build, a signed candidate or a GitHub prerelease does not establish physical-device coverage, store publication or support on a platform outside the Android product target. The installed-device upgrade proof of the MAUI app is not in place until PRF.12 and AND.13 run; the Kotlin upgrade baseline is retired.

Reinstalling is required from the Kotlin application: the applicationId changed from `io.github.arcforges.mobile` to `com.arcforges.mobile`, so the installed Kotlin app is a separate package. No data migration is provided. A device that holds a debug-signed build must uninstall it before installing a release-signed build.

Original application code and repository tooling are licensed under [Apache-2.0](LICENSE). Dependencies retain their own licences; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The [licence gates](docs/licence-boundary.md) check the NuGet closure and the .NET project inventory, and the MAUI notice gates embed the reviewed notices before packaging. CI has no device, emulator, live Cloud or public-install gates. Runtime tools are local opt-in; green CI does not claim device or full product acceptance.

Build identity and independent version sources are described in [docs/build-identity.md](docs/build-identity.md). The `build-identity.json` of each MAUI build is embedded in the APK.
