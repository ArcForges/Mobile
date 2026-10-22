# Development and validation

## Requirements

Use the .NET SDK 10.0.400 that [global.json](../global.json) pins (`rollForward` disabled), the workload set 10.0.401 (Android 36.1.69 and MAUI Android 10.0.20), Python 3.14.7 and the Android SDK components `platforms;android-36.1` and `build-tools;36.1.0`. Install the workloads with `dotnet workload install android maui-android --version 10.0.401`. Set `ANDROID_HOME` to the SDK. The CI maui job also pins Temurin JDK 21.0.12 for Android platform tooling; no Java or Kotlin product code exists.

Local Android builds use the SDK root that `DOTNET_ROOT` names (on this workstation the user root `C:\Users\<user>\.dotnet`, which holds SDK 10.0.400 and the android and maui-android workloads) once it has workload set 10.0.401. The host verification checks this before it builds and names the exact command for a gap. See [maui-toolchain.md](maui-toolchain.md) for the pins.

Android is this repository's sole product and release target. There is no desktop, iOS or macOS target; see the [platform and distribution matrix](../README.md#platform-and-distribution-matrix).

## Layout and commands

- `src/ArcForges.Mobile`: the .NET MAUI application (`net10.0-android`): the Hello page, its view model, the build information view and the Android platform code. `ArcForges.Mobile.csproj` embeds the `build-identity.json` of the build.
- `src/core/ArcForges.Mobile.Network`: the Hello transport (binary gRPC-Web through `Grpc.Net.Client.Web`) and the streaming consumer. Both are platform-neutral and also targeted at `net10.0` for host tests.
- `src/core/ArcForges.Mobile.Security`: the Keystore probe, a test-only device harness that reports the platform security level without claiming hardware backing.
- `tests/ArcForges.Mobile.Tests`: host-run transport, streaming and view-model tests (`net10.0`, no emulator).
- `tests/ArcForges.Mobile.Policy`: the C# policy suite: layering, licence boundary, forbidden terms (the Contracts policy package, verified by digest) and the seven Mobile-owned BAN-* rules with negative fixtures (`net10.0`).
- `eng`: repository, candidate, signing, notice and provenance tooling, with its own unit tests in `eng/tests`.

```sh
python eng/verify.py install
python eng/mobile.py check
python -m unittest discover -s eng/tests -v
dotnet build src/ArcForges.Mobile/ArcForges.Mobile.csproj -f net10.0-android -c Debug --no-restore
dotnet test tests/ArcForges.Mobile.Policy/ArcForges.Mobile.Policy.csproj -c Release --no-restore
dotnet test tests/ArcForges.Mobile.Tests/ArcForges.Mobile.Tests.csproj -c Release --no-restore
```

Restore each project first with `dotnet restore <project> --locked-mode` into a clean `NUGET_PACKAGES` folder, so that no machine-wide package cache is used (AND.40 decision 17). The pre-commit hook checks whitespace only. After the push, each verification host runs `python eng/verify.py run-and-report` in a worktree at the pushed commit, which verifies it with the full profile of `eng/verify_steps.py`: the MAUI leg with the candidate staging on Windows, the repository and tooling checks and the host and policy tests on a native Linux host (the two legs and their pass records), the whitespace check and the secret scan. The Linux Android build is not run locally (the user's decision of 2026-10-17); it runs in the main-push candidate job and in the CI of every other pull request ([AGENTS.md](../AGENTS.md), Local verification). While iterating, run the relevant checks once with existing caches. Do not add macOS or hosted runtime validation.

The release build is `dotnet build ... -f net10.0-android -c Release`: Mono AOT and R8 trimming (`AndroidLinkTool=r8`). `python eng/maui_identity.py --apk <apk> --configuration Release` checks the APK identity, and `python eng/mobile.py maui-stage` seals the candidate (`--local` seals a local candidate with the version `0.1.0-local`, which can never be signed). The host verification runs these on Windows for every pull request; hosted CI runs them on Windows and Linux runners for every other pull request and a manual run, and on Linux for the main-push candidate.

## Cloud protocol and device verification

The Hello transport uses `Grpc.Net.Client.Web` 2.84.0 with binary gRPC-Web against `https://arcforges.com/api`. No cookies are sent, redirects are not followed and connection retry is disabled. The RPC deadline is at most five seconds and the call timeout is ten seconds. A name is 1..256 UTF-16 code units and is sent verbatim. The streaming consumer keeps frames in order, requires exactly one OK trailer (a missing trailer is `DATA_LOSS`), stays bounded and closes the stream on cancellation even when the caller is cancelled.

Host tests run these rules against loopback fixtures. They are test-only characterisation of the stream shape: the published generated client and the real stream producer confirm it before AND.40 completes (its completion edges CON.11 and CLOUD.29).

Device, emulator and live Cloud checks are **local opt-in only** and are not run by CI. The MAUI upgrade and identity proof on an installed device is not in place until PRF.12 and AND.13 run. The Kotlin device smoke and upgrade helpers are retired.

## Dependency maintenance

[Dependency admission](dependency-policy.md) requires an admission record for every NuGet update. Locks are committed as `packages.lock.json` in each project. Dependabot proposes NuGet updates weekly on Mondays for the directories in `.github/dependabot.yml`; it never auto-merges. A changed lock is accepted only with its admission record, a locked restore into a clean `NUGET_PACKAGES` folder and a regenerated closure and notice set (`python -I eng/maui_notices.py closure`, `reproof`, `check` and `distribution`).

The pinned SDK, workload set and MAUI packs are recorded in `eng/policy/dotnet-toolchain.json` and `eng/policy/workload-admission.json`. A toolchain change is a reviewed upgrade, not a floating version.

## Security tooling

The security workflow runs dependency review on pull requests, a gitleaks history scan, CodeQL for Python and Actions, and CodeQL for C# with a manual Release build of the host-run projects. CI calls it for every pull request except the owner's and for a manual run; it also runs weekly. The owner's pushes run the gitleaks scan over the pushed range locally instead. The Kotlin CodeQL category (`java-kotlin`) and its pinned nightly bundle are retired with the Kotlin baseline. The workflow lint job runs actionlint 1.7.12 on `ci.yml` and `security.yml`.

## Evidence boundaries

Host tests establish shared behaviour and transport rules against local fixtures. The offline policy suite establishes the layering, licence, naming and banned-API rules. The PR's verification establishes the builds and the notice set: on Windows for every pull request (the host verification after the push), and also on Windows and Linux for other authors' pull requests (hosted CI); the main-push run establishes the signed candidate identity. Device, emulator, live Cloud and store behaviour require separate evidence, and none is implied by a green build.
