# .NET MAUI Android identity and toolchain pins (AND.01)

The Android companion moves to .NET MAUI for `net10.0-android` only, using the Mono runtime (P2-021 items 3 and 4). This page records the pinned tuple, where each pin lives and how it is checked. It does not port the app; that is AND.40. The Gradle/Kotlin application stays the frozen release baseline until AND.40 retires it.

## Pinned tuple

| Item | Pin | Where it is enforced |
| --- | --- | --- |
| .NET SDK | `10.0.400`, `rollForward: disable` | `global.json`; `eng/policy/dotnet-toolchain.json` |
| Target framework | `net10.0-android` only, `UseMonoRuntime=true` explicit | `src/ArcForges.Mobile/ArcForges.Mobile.csproj` |
| Linker | `AndroidLinkTool=r8`, Release configuration only | the project (scoped to Release) |
| Android workloads | `android` 36.1.69 and `maui-android` 10.0.20 manifests (Windows) | `eng/policy/dotnet-toolchain.json` |
| MAUI | `Microsoft.Maui.Controls` 10.0.20 | `Directory.Packages.props` |
| Trimmer | `Microsoft.NET.ILLink.Tasks` 10.0.11 | `Directory.Packages.props` (see below) |
| Contracts client | `ArcForges.Contracts.PublicApi` 1.0.0-ci.350.1 (Apache-2.0; generated `ArcForges.Contracts.Hello.V1` client) | `Directory.Packages.props` |
| NuGet source | `nuget.org` only, every package mapped to it | `NuGet.config` |
| Restore | locked (`packages.lock.json`), SDK implicit libraries disabled | `Directory.Build.props` |
| Application identity | `com.arcforges.mobile`, Android minSdk 26, target platform 36.1 | project; `eng/policy/dotnet-toolchain.json` |
| Build tools | `36.1.0` | project (`AndroidSdkBuildToolsVersion`) |
| JDK | 21 (`JAVA_HOME`, mapped to `JavaSdkDirectory` by the environment) | environment; checked by the release job, not committed |
| Release certificate | SHA-256 `7a8b3b14…` (persistent key, `eng/published.py`) | `eng/published.py`; `eng/policy/dotnet-toolchain.json` |

Why these values:

- The Android workload and MAUI packages installed on the Windows machine (`maui-android` 10.0.20) accept compile/target platforms 36.0 and 36.1 only. `TargetPlatformVersion` 37.0 is rejected (NETSDK1140). D-016 keeps the final compile/target API open for AND.40, so 36.1 is the only buildable value in this tuple.
- The SDK adds the trimmer package implicitly at its own patch version: 10.0.11 in SDK 10.0.400 (the committed pin, WSL2) and 10.0.12 in SDK 10.0.401 (the Windows adapter). The explicit central pin of 10.0.11 gives one lock for both.
- The SDK's library-packs folder holds copies of several MAUI 10.0.20 packages (for example `Microsoft.Maui.Controls.Build.Tasks` and `Microsoft.Maui.Resizetizer`) whose NuGet content hashes differ from the nuget.org packages. `DisableImplicitLibraryPacksFolder` makes restore use only the declared nuget.org source, so every lock hash comes from nuget.org.

## Signing

The project does not configure signing. The persistent release key signs the candidate in the protected release job, outside the build (AGENTS.md: candidate build, required checks, protected signing, publication). MSBuild passes signing passwords to `jarsigner` as arguments, and MAUI 10.0.20 does not resolve `env:` references, so the build must not carry them. The release job signs with `apksigner` and verifies the certificate. `python eng/maui_identity.py --apk <apk> --release` refuses any APK that is not signed by the persistent certificate.

The reinstall guidance for the applicationId change is in [releasing.md](releasing.md#application-identity-change-to-comarcforgesmobile-and-01).

## Local toolchain setup

Windows has SDK 10.0.401 and no 10.0.400. For local builds only, replace `global.json` with this uncommitted adapter, build, and restore the committed file before any commit or check:

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

`eng/policy/nuget-admission.json` records every package in `packages.lock.json` with its exact version, NuGet content hash, nuget.org `nupkg` SHA-512, SPDX licence expression, licence files and notice disposition. A lock change without a new admission record fails the gate. The only admitted licences are Apache-2.0, MIT, BSD-3-Clause and BSD-2-Clause. BSD-2-Clause is admitted only through `Xamarin.Android.Glide`, pulled by MAUI, with its notice carried in the release notices (AND.40).

## Evidence recorded in AND.01

Recorded on 2026-10-08 on Windows (SDK 10.0.401 adapter, locked restore from a clean nuget.org package folder):

- Debug build of the identity project: succeeded, 0 warnings, 0 errors. The APK identity is `com.arcforges.mobile`, minSdk 26, targetSdk 36 (`aapt2 dump badging`). It is signed with the local debug key, which is expected.
- Release build with `AndroidLinkTool=r8` (trimming and R8 ran): succeeded, 0 errors, with two advisories under the adapter only: the SDK's advisory about an explicit trimmer reference (the SDK 10.0.401 bundles 10.0.12), and a `[removal]` warning for `finalize()` in MAUI-generated Java binding code. Neither is in project code. The committed SDK 10.0.400 is the reference for the pin.

Recorded on WSL2 Debian (SDK 10.0.400, committed `global.json`, same lock):

- Locked restore: succeeded.
- Debug build: stopped at XA5300, because the WSL2 image has no Android SDK, and no JDK 21 is installed. Installing them is provisioning, which AGENTS.md forbids for validation, so the Linux build proof is open and reported as blocked.

Not proven by AND.01 and transferred explicitly: the persistent-key signature on a MAUI APK (protected release job), Mono AOT and the 16 KB alignment check (AND.40 CI), the device install and App Link fixture-key tests (PRF.12 local opt-in), the compile/target API floor and .NET 11 posture (D-016).
