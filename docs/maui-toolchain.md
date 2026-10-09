# .NET MAUI Android identity and toolchain pins (AND.01)

The Android companion moves to .NET MAUI for `net10.0-android` only, using the Mono runtime (P2-021 items 3 and 4). This page records the pinned tuple, where each pin lives and how it is checked. It does not port the app; that is AND.40. The Gradle/Kotlin application stays the frozen release baseline until AND.40 retires it.

## Pinned tuple

| Item | Pin | Where it is enforced |
| --- | --- | --- |
| .NET SDK | `10.0.400`, `rollForward: disable` | `global.json`; `eng/policy/dotnet-toolchain.json` |
| Target framework | `net10.0-android` only, `UseMonoRuntime=true` explicit | `src/ArcForges.Mobile/ArcForges.Mobile.csproj` |
| Linker | `AndroidLinkTool=r8`, Release configuration only | the project (scoped to Release) |
| Android workloads | `android` 36.1.69 and `maui-android` 10.0.20 manifests, with the Mono runtime and AOT manifest 10.0.112 they extend (Windows) | `eng/policy/dotnet-toolchain.json` (`workloads`); `eng/policy/workload-admission.json` |
| MAUI | `Microsoft.Maui.Controls` 10.0.20 | `Directory.Packages.props` |
| Trimmer | `Microsoft.NET.ILLink.Tasks` 10.0.11 | `Directory.Packages.props` (see below) |
| Contracts client | `ArcForges.Contracts.PublicApi` 1.0.0-ci.324.1 (Apache-2.0; generated `ArcForges.Contracts.Hello.V1` client; `ArcForges.Contracts.Foundation` 1.0.0-ci.324.1 transitively), published from Contracts main `330e46bd` (CI run 37388554007) | `Directory.Packages.props`; `eng/policy/nuget-admission.json` |
| NuGet source | `nuget.org` only, every package mapped to it | `NuGet.config` |
| Restore | locked (`packages.lock.json`), SDK implicit libraries disabled | `Directory.Build.props` |
| Application identity | `com.arcforges.mobile`, Android minSdk 26 (carried from the Kotlin baseline) | project; `eng/policy/dotnet-toolchain.json` |
| Permissions and components | none declared by the project; the manifest removes the SDK's Debug `INTERNET`; `AndroidEnableProfiler=false`; the only APK permission is the AndroidX-merged signature permission | `src/ArcForges.Mobile/`; `eng/maui_identity.py` (`check_identity_only_shape`, `check_apk`) |
| Namespace | `ArcForges.Mobile` (root namespace; every source namespace under `src/ArcForges.Mobile` starts with it) | project (`RootNamespace`); `eng/maui_identity.py` |
| Target API | `36.1` compile/target platform, the coordinator's D-016 decision of 2026-10-08 | project (`TargetPlatformVersion`); `eng/policy/dotnet-toolchain.json` (`targetPlatformDecision`) |
| Build tools | `36.1.0` | project (`AndroidSdkBuildToolsVersion`) |
| JDK | 21 (`JAVA_HOME`, mapped to `JavaSdkDirectory` by the environment) | environment; checked by the release job, not committed |
| Release certificate | SHA-256 `7a8b3b14…` (persistent key, `eng/published.py`) | `eng/published.py`; `eng/policy/dotnet-toolchain.json` |

Why these values:

- Target API 36.1 is the coordinator's decision under D-016 (2026-10-08, migration brief section 10). The Android workload and MAUI packages installed on the Windows machine (`maui-android` 10.0.20) accept compile/target platforms 36.0 and 36.1 only, and `TargetPlatformVersion` 37.0 is rejected (NETSDK1140), so 36.1 is the only value in this tuple. Raising the target follows the workload and needs a new reviewed D-016 record.
- The minimum API stays 26, carried from the Kotlin baseline. The D-016 minimum-API review stays open; this pin does not change it.
- The SDK adds the trimmer package implicitly at its own patch version: 10.0.11 in SDK 10.0.400 (the committed pin, WSL2) and 10.0.12 in SDK 10.0.401 (the Windows adapter). The explicit central pin of 10.0.11 gives one lock for both.
- The SDK's library-packs folder holds copies of several MAUI 10.0.20 packages (for example `Microsoft.Maui.Controls.Build.Tasks` and `Microsoft.Maui.Resizetizer`) whose NuGet content hashes differ from the nuget.org packages. `DisableImplicitLibraryPacksFolder` makes restore use only the declared nuget.org source, so every lock hash comes from nuget.org.

## Signing

The project does not configure signing. The persistent release key signs the candidate in the protected release job, outside the build (AGENTS.md: candidate build, required checks, protected signing, publication). MSBuild passes signing passwords to `jarsigner` as arguments, and MAUI 10.0.20 does not resolve `env:` references, so the build must not carry them. The release job signs with `apksigner` and verifies the certificate. `python eng/maui_identity.py --apk <apk> --release` refuses any APK that is not signed by the persistent certificate.

The reinstall guidance for the applicationId change is in [releasing.md](releasing.md#application-identity-change-to-comarcforgesmobile-and-01).

## Identity-only shape

The identity project has no permission grant, no launchable activity and no UI (P2-021 item 3; the AND.01 follow-up of 2026-10-08). Its files are exactly:

- `src/ArcForges.Mobile/ArcForges.Mobile.csproj` and `packages.lock.json`;
- `Platforms/Android/AndroidManifest.xml`: one `application` element with backup and cleartext restricted, and one `uses-permission` element that only removes `android.permission.INTERNET` (`tools:node="remove"`). It declares no component;
- `Compatibility/ContractsClientCompatibility.cs`: compile-only evidence that the generated `ArcForges.Contracts.Hello.V1` client builds against the MAUI tuple. It carries no behaviour.

`App.cs`, `MainPage.cs`, `MauiProgram.cs`, `Platforms/Android/MainActivity.cs` and `Resources/` were removed. The Windows Debug and Release builds succeed without an `App`, a `MauiProgram` or a `Resources` folder (see the evidence below), so no minimal shim is kept. AND.40 adds the entry point, UI and resources.

Build facts that shaped the manifest and the project:

- The SDK's manifest generator adds `android.permission.INTERNET` to the generated Debug manifest (`obj/Debug/net10.0-android/AndroidManifest.xml`). That manifest carries `android:debuggable="true"` and the permission, while the Release manifest carries neither. The cause inside the generator was not traced to source; the observed correlation with `debuggable` is what the build shows. `tools:node="remove"` on the identity manifest removes the permission from the merged APK, and the rebuilt Debug APK confirms it.
- `AndroidEnableProfiler=false` is set explicitly. When the profiler is enabled, the SDK's `Microsoft.Android.Sdk.DefaultProperties.targets` sets `AndroidNeedsInternetPermission`, so the explicit value keeps that profiler requirement out of the identity build. It is not the cause of the Debug permission above.
- AndroidX Core merges one permission into every application: `com.arcforges.mobile.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`. The application package declares it itself with protection level `signature` (`aapt2 dump xmltree`, protectionLevel 0x2), so it grants no capability to another app. This follow-up does not strip it (that would be a manifest-merge change to AndroidX, not verified here), so the gate allows exactly this permission and nothing else.
- The merged manifest also carries AndroidX library components, such as a profile-installer receiver. These are library-owned and are not declared by this project; the gate refuses only a launchable activity.

`eng/maui_identity.py` enforces the shape: the exact file set (`check_identity_only_shape`), one application element and at most one removal marker for `INTERNET`, `AndroidEnableProfiler=false`, and the built APK's badging (no `uses-permission` other than the merged signature permission, no `uses-implied-permission`, no `launchable-activity`).

## Local toolchain setup

The Windows host has two .NET roots, and only one of them can build the pinned MAUI tuple (correction recorded by AND.40 unit 1, 2026-10-09; migration brief section 10, decision 13):

- `C:\Program Files\dotnet` holds SDK 10.0.401 and the pinned workloads `android` 36.1.69 and `maui-android` 10.0.20. Every MAUI build on this host uses it.
- `C:\Users\J7Rdm\.dotnet` holds SDK 10.0.400, the committed pin, but no `maui-android` workload and no Android or MAUI packs. It reports only the Visual Studio `android` 36.1.2 and `maui-windows` 10.0.0 manifests, so a build there cannot reach the pinned tuple. The 10.0.400 pin is first exercised by hosted CI (AND.40 unit 5).

For local builds only, replace `global.json` with this uncommitted adapter, which selects SDK 10.0.401 under Program Files. Build, and restore the committed file before any commit or check:

```json
{
  "sdk": {
    "version": "10.0.401",
    "rollForward": "latestPatch",
    "allowPrerelease": false
  }
}
```

While the adapter is in place, the offline gate fails by design (`global.json must pin the reviewed SDK exactly`). The committed `global.json` never names 10.0.401.

Use a clean package folder for restores that establish or verify the lock, so the lock is built only from nuget.org downloads:

```powershell
$env:NUGET_PACKAGES = "<a scratch folder outside the repository>"
dotnet restore src/ArcForges.Mobile/ArcForges.Mobile.csproj --locked-mode
dotnet build src/ArcForges.Mobile/ArcForges.Mobile.csproj -f net10.0-android -c Debug --no-restore
```

Set `JAVA_HOME` to a JDK 21 installation and `ANDROID_HOME` to the Android SDK when they are not in the default location. Do not commit either path.

## Offline checks

```text
python eng/mobile.py check                      # includes the MAUI identity, pin and admission gate
python -I eng/maui_identity.py                  # gate only
python -I eng/maui_identity.py --apk <built.apk> [--release]
python -I -m unittest discover -s eng/tests -p "test_maui_identity.py"
```

`eng/policy/nuget-admission.json` records every package in `packages.lock.json` with its exact version, NuGet content hash, nuget.org `nupkg` SHA-512, SPDX licence expression, licence files and notice disposition. A lock change without a new admission record fails the gate. The only admitted licences are Apache-2.0, MIT, BSD-3-Clause and BSD-2-Clause.

BSD-2-Clause is admitted only through `Xamarin.Android.Glide` (four packages), pulled by MAUI. The admission is the coordinator's adjudication of 2026-10-08 (migration brief section 10), recorded as a permissive licence; no separate licence-owner confirmation is recorded. Its copyright notice is an AND.40 obligation: the MAUI release notices must carry it before the first MAUI Android release candidate is published. The gate refuses a BSD-2-Clause exception that does not name AND.40.

## Evidence recorded in AND.01

Recorded on 2026-10-08 on the Windows host, for the identity-only project (the AND.01 follow-up). The Windows host has SDK 10.0.401, so each build used the uncommitted adapter above; `global.json` was restored to the committed 10.0.400 pin before every offline check and before the commit. Restores were `--locked-mode` into a clean `NUGET_PACKAGES` folder outside the repository. JDK 21 (Temurin 21.0.11) was supplied through `JAVA_HOME`, and the Android platform 36.1 and build-tools 36.1.0 were used from `ANDROID_HOME`. The builds ran through the workstation build slot.

- Locked restore of `src/ArcForges.Mobile/ArcForges.Mobile.csproj`: succeeded.
- Debug build (`-c Debug`): succeeded, 0 warnings, 0 errors.
- Release build (`-c Release`, `AndroidLinkTool=r8`): succeeded, 0 errors. R8 ran (`bin/Release/net10.0-android/mapping.txt` is written). It reported 2 warnings, both the same SDK advisory that the explicit `Microsoft.NET.ILLink.Tasks` 10.0.11 reference should be deleted because the 10.0.401 SDK supplies its own trimmer (10.0.12). This was observed only under the 10.0.401 adapter. The committed 10.0.400 pin was not built on this host.
- APK identity, checked with `inspect_apk` (`aapt2 dump badging`, `apksigner verify --print-certs`) on both signed APKs: package `com.arcforges.mobile`, minSdk 26, targetSdk 36, one signer. The only `uses-permission` is the AndroidX-merged `com.arcforges.mobile.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`. There is no `android.permission.INTERNET` and no launchable activity. Both APKs are signed with the local debug key, as expected: the build configures no signing, and the persistent release certificate is applied only by the protected release job. No `--release` proof is claimed here.
- The first Debug APK built from this tree still carried `android.permission.INTERNET`, injected by the SDK's manifest generator into the debuggable manifest. The identity manifest's `tools:node="remove"` marker removes it, and the rebuilt Debug and Release APKs were checked as above.
- Unit tests: `python -I -m unittest discover -s eng/tests -p "test_maui_identity.py"` passes all 60 tests, and the full `eng/tests` suite passes 130 tests.
- Offline gates: `python -I eng/maui_identity.py` passes against the committed pin. `python eng/mobile.py check` passes; it was run as `python -I` with `eng/` on the path, because `-I` alone cannot import the script's sibling modules.

The Linux identity build is not run locally. WSL2 Debian has no Android SDK and no JDK 21, and under P2-024 and brief section 10 the Linux Android build is the hosted Linux CI job that AND.40 adds, so AND.01 does not close on it. No WSL2 build is recorded for this unit.

## Deferred to AND.40

Recorded in `eng/policy/dotnet-toolchain.json` (`deferrals`), with the gate refusing a deferral that lacks its owner, trigger or consequence:

| Deferral | Owner | Trigger | Consequence |
| --- | --- | --- | --- |
| Linux Android build of the MAUI identity project (WSL2 has no Android SDK or JDK 21) | AND.40 | the first AND.40 hosted Linux CI run that builds this project (Debug and Release, locked restore) | a failed Linux build reopens AND.01 and AND.40; the Windows evidence above stands until then |
| BSD-2-Clause notice of `Xamarin.Android.Glide` in the MAUI release notices | AND.40 | the first MAUI Android release candidate, before publication | no candidate is published without the notice; AND.40 stays open |
| BSD-3-Clause licence text of `Google.Protobuf` 3.36.1 (nupkg carries no licence file) | AND.40 | the first MAUI Android release candidate, before publication | the release notices must carry it; no candidate is published without it |
| Apache-2.0 licence text and any notice of `Grpc.Core.Api` 2.84.0 (nupkg carries no licence file) | AND.40 | the first MAUI Android release candidate, before publication | the release notices must carry it; no candidate is published without it |
| MIT licence and notice files of the admitted workload packs (Mono runtime and AOT packs contribute to the APK) | AND.40 | the first MAUI Android release candidate, before publication | the release notices must carry them; no candidate is published without them |
| Licence evidence the Windows host cannot provide: Linux host aliases of the Android SDK and Mono AOT packs, and the licence statement of `Microsoft.NET.Runtime.MonoAOTCompiler.Task` and `Microsoft.NET.Runtime.MonoTargets.Sdk` (notice file only) | AND.40 | the first AND.40 hosted Linux CI run that installs the android workload and builds the MAUI Android project | a licence outside the admitted set or a missing licence file reopens AND.01 and AND.40 |

Each nupkg without a licence file needs one notice deferral naming its package, version and licence; the gate refuses a missing or stale one.

## Workload admission

`eng/policy/workload-admission.json` is the admission record for the workload manifests and packs. It was written offline from the workload folders installed on the Windows host (`sdk-manifests/10.0.100`, `packs`), with no download. Each pinned workload (`android`, `maui-android`, `mono-toolchain`) lists every pack its manifest declares for the Android closure, and each pack is either admitted or excluded with a reason. Admitted packs carry the licence file path and SHA-256 found on the host, or a deferral. MAUI library packs are not repeated here: they must match the NuGet admission at the pinned version. The gate refuses any drift from the pins in `eng/policy/dotnet-toolchain.json` (manifest and pack versions), a declared pack that is neither admitted nor excluded, an excluded pack without a reason, and an admitted pack without licence evidence. The net9 Mono manifest reached through the android workload's net9 extends is recorded as an excluded manifest.

Not proven by AND.01 and transferred explicitly: the persistent-key signature on a MAUI APK (protected release job), Mono AOT and the 16 KB alignment check (AND.40 CI), the Linux Android build (AND.40 hosted Linux CI, above), the device install and App Link fixture-key tests (PRF.12 local opt-in). Target API 36.1 is decided under D-016, but its device behaviour is not proven here. The minimum-API review and the .NET 11 posture stay open under D-016.

## CI, restore hygiene and release notices (AND.40 unit 5)

PR A adds the MAUI jobs beside the Kotlin jobs in `.github/workflows/ci.yml`. The Kotlin jobs, the Kotlin publish and the Gradle path are unchanged until PR B.

### Restore hygiene (AND.40 decision 17)

Every restore uses `--locked-mode` with `NUGET_PACKAGES` pointing at a clean folder outside the repository. A default restore on the Windows host can take `Microsoft.Maui.Controls.Build.Tasks` and `Microsoft.Maui.Resizetizer` 10.0.20 from `C:\Program Files\dotnet\library-packs`, and their hashes differ from nuget.org. The CI maui job restores into `$RUNNER_TEMP/nuget-maui-<run>-<attempt>` and the local gate uses a fresh folder for each run. Lock files are stored as LF, and `lockSha256` is computed over the LF bytes.

### Workloads and the SDK pin (AND.40 decision 3)

The maui job runs `dotnet workload install android maui-android` on the SDK pinned by `global.json` (10.0.400) and then checks that `dotnet workload list` reports `android` 36.1.69 and `maui-android` 10.0.20. If the band does not provide them, the job fails with the decision 3 message. The reviewed fallback is SDK 10.0.401 under a new admission; it is not applied silently. The Windows host builds with the 10.0.401 adapter, because the 36.1.69 and 10.0.20 workloads are installed only under `C:\Program Files\dotnet` (decision 13).

### Actions

`actions/setup-dotnet` is pinned to `a98b56852c35b8e3190ac28c8c2271da59106c68 # v6`, the SHA the ArcForges family already pins in its CI (ArcScope, ArcNotes, ArcSlate) and in the Design publication evidence. The Mobile repository has no separate action admission record; a reviewer confirms the admission at merge.

### Build identity (AND.40 decision 14)

`python eng/build_identity.py --maui --observed-sdk "$(dotnet --version)" --version V --code C` writes `build/generated/licence-assets/build-identity.json` before the builds. It is derived from the NuGet lock of the `net10.0-android36.1` closure (resolved versions only), the pinned toolchain (SDK, workloads, MAUI, Android values), the SDK that built the candidate and the LF-normalised source inputs. The csproj embeds the file in every build that has it. In CI the observed SDK must be the pinned 10.0.400. The Build information view says that no identity is embedded only in a Debug build; a Release build without one says that it must not be distributed.

### CodeQL (AND.40 decision 12)

`codeql-csharp` uses manual build mode with an explicit locked restore and Release build of the host-run projects (`ArcForges.Mobile.Policy` and `ArcForges.Mobile.Tests`). The Android app projects need the Android workload and are covered by the maui job, not by this analysis. `java-kotlin` stays until PR B.

### MAUI candidate and release (PR A)

- `python eng/mobile.py maui-stage` reads the Release APK, checks its identity with `maui_identity.inspect_apk`, checks that it embeds its own `build-identity.json` (`resources.maui_archive`), removes its META-INF signature entries (the MSBuild Release APK is signed with the debug key), aligns it with `zipalign -P 16 -f 4`, checks `zipalign -c -P 16 4`, and seals `candidate.json`.
- The publish-maui job runs on main only, in `android-release`, after `verify`. `python eng/mobile.py maui-sign` verifies the candidate and its build identity against the checkout, refuses to run while any notice escalation is open (`maui_notices.py release-ready`), signs with the persistent identity through `apksigner` (the secrets are the Kotlin secrets, with the same names), verifies the certificate fingerprint `7a8b3b14...`, runs `maui_identity.inspect_apk(..., release=True)`, and writes `release.json` and `SHA256SUMS`.
- The release tag is `android-maui-VERSION`. The track publishes the APK, its companions and `maui-archive.json`. It publishes no AAB: the MAUI release path is APK only in PR A.
- `python eng/published.py maui-prepare` verifies an anonymously downloaded MAUI prerelease. It is local opt-in only.
- Build tools come from `eng/policy/dotnet-toolchain.json` (`36.1.0`), not the Kotlin `37.0.0`.

### Release notices

`python -I eng/maui_notices.py distribution` writes `build/generated/maui-licence-assets/THIRD_PARTY_NOTICES.txt`. It carries the licence files of every shipped package from its restored nupkg, after the nupkg SHA-512 is checked against the admission, and the retained texts recorded for each package. Build-only and test-only packages do not contribute. `python -I eng/maui_notices.py linux-evidence --dotnet-root <root>` writes `artifacts/evidence/linux-licence-evidence.json` from the hosted Linux runner. It records the Android SDK Linux pack, the Linux Cross aliases and the Mono AOT and target SDK notice files.

### Open notice escalation (blocks the MAUI release)

`workload-bundles-bsd-2-clause` stays open in `eng/policy/maui-notices.json`, and `python -I eng/maui_notices.py release-ready` refuses until it is resolved. Two facts block the compound SPDX expressions that decision 19 asks for, so no LICENCES entry is added in PR A:

- The Mono runtime and AOT android-arm64 bundles (10.0.12) contain zlib and Unicode notices. Neither licence is in the MAUI admitted set (Apache-2.0, BSD-2-Clause, BSD-3-Clause, MIT), so the expression would need a new admission.
- The `Microsoft.Android.Sdk.Windows` 36.1.69 bundle contains GNU GPL version 3 text for the `gnu/binutils` component. That is a host build tool, not a packaged APK component, but the coordinator must confirm it is not redistributed in the candidate before any expression is recorded.

The Linux licence evidence (`pending`, `linux-licence-evidence`) is produced by the hosted Linux run and is recorded at that first run.
