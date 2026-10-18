# Repository guidance

- The current product target is Android: the .NET MAUI application under `src/ArcForges.Mobile`. The Kotlin application, its KMP module and its Gradle build are retired (AND.40 PR B). Do not add desktop, iOS or macOS product distribution.
- Shipped projects target `net10.0-android` only; host-run test, policy and architecture projects target `net10.0`. Product logic is C#. Kotlin and Java product code is not allowed. The JDK 21.0.12 pin in `ci.yml` is Android platform tooling only.
- Consume published `ArcForges.Contracts.*` NuGet packages with exact versions. No submodules, neighboring source dependencies, copied generated contracts or local NuGet publishing shortcuts.
- Plan changes before implementation, finish collecting related issues before fixing them, and keep verification proportional to the change.
- Keep documentation and code comments in English. Never commit SDK paths, signing material, APKs, AABs or build caches.
- Preserve the release dependency chain: the PR's verification (the owner's pre-push verification or the full PR CI), the main-push candidate build, protected signing of that candidate, publication. PRs must not use release secrets.
- Run the scoped offline checks from `docs/development.md`; runtime checks require explicit local opt-in. Distinguish compilation, local runtime observations and publication.
- NuGet updates must update the affected `packages.lock.json` files and carry an admission record. Do not weaken locked restores to avoid maintaining those files.
- Apache-2.0 applies to original code and tooling. Respect dependency licenses and retained notices.

## Flagship role

Mobile is an **active** repository of the ArcForges flagship ([AD-0001](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0001-flagship-pivot.md)); the design authority is [ArcForges-Design](https://github.com/ArcForges/ArcForges-Design). Per [architecture 01 §5](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/architecture/01-system-overview.md#5-repository-and-project-map), [architecture 12 §6](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/architecture/12-client-applications.md) and the [reuse classification](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/reuse/inventory-and-classification.md#5-mobile), it reuses the MAUI app shell, the AOT/R8 release configuration, the gRPC-Web network layer (`ArcForges.Mobile.Network`) and the Keystore wrapper (`ArcForges.Mobile.Security`). The flagship adds the Android companion: sign-in, QR pairing, fleet and node views, actions and approvals, push notifications and Play Billing subscriptions ([Android experience](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/experience/android.md)).

## Delivery (serial, ArcForges/Plan)

Tasks for this repository come from the [Plan delivery graph](https://github.com/ArcForges/Plan/blob/main/delivery-graph.json) and are delivered under the Plan [execution policy](https://github.com/ArcForges/Plan/blob/main/execution-policy.md) and [delivery procedure](https://github.com/ArcForges/Plan/blob/main/delivery-procedure.md) ([AD-0014](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0014-delivery-method.md)). They are binding. The historical P2-018 model (delivery lanes, adoption slices, `delivery.py` claims and handoffs, parallel or independent owner agents, integration-owner roles, the build slot and the launcher) is retired and never resumed.

- One task is active at a time. Work only inside its write scope, in a worktree `.worktree/<task-id-lower>` on branch `task/<task-id-lower>`, never in the primary checkout.
- Delegated workers and reviewers work locally. Only the coordinator pushes (through the pre-push verification), opens pull requests, merges (at the reviewed head, after the merge gate: the verification's PASS line for the owner's PRs, hosted CI for external PRs) and publishes.
- Title pull requests `[<TASK-ID>] <summary>`.
- Shared files: dependency additions carry admission records, and lock files are regenerated after rebase, never hand-merged. Signing identities and store listings are used only by release work through protected CI environments.
- Implemented baseline: the .NET MAUI Android application (AND.40), which replaced the retired Kotlin application, with the WP02 build, dependency and provenance baselines carried forward.
- Earlier dated bootstrap and provenance records under `docs/` describe their original scope; they are evidence, not execution instructions. Where older documents prefix a command with `delivery.py build-slot run … --` or assign a step to an integration owner, that is historical: run the wrapped command directly, and leave pushing and merging to the coordinator.

## CI and execution restrictions (P2-017)

Authority: the historical [CI and local validation policy](https://github.com/ArcForges/ArcForges-Design-Parallel/blob/64173614f2c41543bfff8f6df8d5a9e41207eb0a/docs/assurance/ci-and-local-validation-policy.md) (ArcForges-Design-Parallel at `64173614`), which stays in force for this repository except its rule 9 (parallel delivery), which AD-0014 supersedes. Where it differs from the Plan execution policy, the Plan governs.

- No macOS runner/matrix, including self-hosted, scheduled or manual CI.
- No hosted physical-device/emulator, desktop GUI, browser E2E, live service/RPC/inference, installed-package consumer or public-release install/upgrade execution. Remove hidden invocations and obsolete dependencies as well as jobs.
- Keep necessary Windows/Linux builds, packaging, targeted offline/static/security checks and required dependency locks, signing and licence/provenance boundaries. Stage the release candidate once and check its sealed identity only at the signing handoff.
- Runtime helpers are explicit local opt-in using existing tools, once for affected behavior. Do not provision/reinstall SDKs, emulators, vcpkg or toolchains for validation. Do not routinely download public artifacts or repeat archive/hash/consumer checks.
- Use retained worktrees. The pre-push verification (Local verification below) is the one place the full build, tests and candidate run before an owner PR merges; the pre-commit hook checks only whitespace.
- Use the normal network and never change proxy or network configuration. Diagnose a failure before any rerun, retry transient failures with bounded backoff, inspect remote state before retrying a write, and report the exact operation when a failure persists. Linux opt-in checks run in the local WSL2 Debian distribution (P2-024); installs inside it are the user's, and there is no SSH.
- Every pull request gets an independent review of its complete latest head; findings are fixed, and the coordinator merges only at the reviewed head after the merge gate at that head (Hosted CI below). Post-merge checks are the merge SHA, required build/publish/deploy status and clean primary fast-forward only. Preserve branches/worktrees and report untested runtime coverage honestly.

## Local verification (AD-0016)

The owner's (`deku2026`) PRs are verified by the repository's pre-push hook, not by hosted CI ([AD-0016](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0016-local-first-verification.md)). The cross-repository rules are the Plan [AGENTS.md](https://github.com/ArcForges/Plan/blob/main/AGENTS.md) rules 6 and 7.

- **Install** once per clone, from the main checkout on `main`: `python eng/verify.py install`. It copies `.githooks/*` (the pre-push verification and the whitespace pre-commit check) into the clone's common hooks directory, so every worktree runs them, and removes any `core.hooksPath`, including per-worktree values left by older scripts (this repository's retired `python eng/mobile.py hooks` set one), and refuses while one remains elsewhere. Re-run it when `.githooks/` changes.
- `python eng/verify.py list` shows the profile and steps. `python eng/verify.py run` verifies `HEAD` now; the push reuses that pass for the identical commit, step set, scripts and tools (the secret scan and the clone identity bind it to the exact base and head commits).
- **What runs.** Each pushed commit, never the working tree, as listed in `eng/verify_steps.py`: every validation job of `ci.yml` and the secret scan of `security.yml`, each on the host the hosted job used, except the Linux Android build (below). Every change runs the full profile (the forbidden-name scan, the provenance inventory and the repository text checks read Markdown too).
  - Lane `win`, in `<main checkout>/.worktree/_verify`, `MAUI (windows-latest)`: the toolchain preflight, the five locked restores into an emptied NuGet folder, the build identity, the Debug and Release (Mono AOT, R8) builds, the Release APK identity gate, the offline host and policy tests, `eng/maui_notices.py` `closure`, `reproof`, `check` and `distribution`, and `python eng/mobile.py maui-stage --local`, which seals a local candidate the way the main-push job seals the one `publish` signs.
  - Lane `wsl`, in the WSL Debian clone `~/.cache/arcforges-verify/Mobile`, the steps of `MAUI (ubuntu-latest)` that need no Android toolchain: `clone-identity` (HEAD a local branch at the pushed commit, `origin/main` the merge base, which the provenance check compares against), `python eng/mobile.py check`, `python -m unittest discover -s eng/tests -v`, and the locked restore and run of the offline host and policy tests (`net10.0`).
  - **Not verified locally (gap):** The Linux Android build (Debug and Release), its APK identity gate and notice set, the Linux workload licence evidence and the Linux-built candidate are not verified locally: the user decided on 2026-10-17 to run the Android build on Windows only ("Option A, my recommendation: run the full Android build only on Windows locally."; "windows is enough for android"), and WSL Debian has no Android toolchain. They run in the main-push candidate job and in the CI of every other PR; the hook prints this on every run.
  - Lane `scan`: `git diff --check` over the pushed range and the pinned gitleaks image over the pushed range with `.gitleaks.toml`, without network. `actionlint` when `.github/workflows/**` changed.
  - The local version is `0.1.0-local` (versionCode 1) and the build identity `local.<commit>`; a local candidate can never be signed. `CI` and `GITHUB_*` are not set; the MSBuild properties that `CI=true` selects (`RestoreLockedMode`, `ContinuousIntegrationBuild`) are set directly. Both lanes start without `artifacts/` and `build/`. Nothing is uploaded, signed or published. Not reproduced: dependency review and CodeQL (GitHub services; external PRs, dispatch and the weekly schedule keep them).
- **Prerequisites** (installs are the user's; the hook installs nothing). The Windows leg starts with a read-only preflight that names the exact command for a gap.
  - Windows: `DOTNET_ROOT` naming the SDK root (Env.md: the user-local `C:\Users\J7Rdm\.dotnet`; the Windows steps put it first on `PATH` whichever shell pushes, and the fingerprint records it) with the SDK that `global.json` pins (10.0.400) and workload set 10.0.401 (android 36.1.69, maui-android 10.0.20, Mono toolchain 10.0.112). From set 10.0.400 the command is `& "C:\Users\J7Rdm\.dotnet\dotnet.exe" workload update --version 10.0.401`. Also `ANDROID_HOME` with `platform-tools`, `platforms;android-36.1` and `build-tools;36.1.0`, `JAVA_HOME` naming a JDK 21, Python 3.14, PowerShell 7 and Git.
  - WSL Debian: the SDK that `global.json` pins, with an Android workload manifest for its band (the restore of the host test projects evaluates the `net10.0-android` target of the libraries they reference; nothing Android is built, and no Android SDK or JDK is needed), Python 3.14 and a running Docker Engine with the pinned gitleaks image. Network access to nuget.org.
- **Failures.** A failed, timed-out or unrunnable step rejects the push and prints the step, the last log lines and the log path (`<git common dir>/arcforges-verify/logs/`). Read the log, fix the cause, push again.
- AI agents must never use `git push --no-verify` to bypass required validation.
- They must also never disable, remove, modify, or otherwise circumvent the hooks merely to allow a push.
- If validation fails, investigate and fix the underlying issue.
- If a required local test cannot run, do not silently skip it or claim successful verification.
- Changing `eng/verify*.py` or `.githooks/` as reviewed engineering work is allowed; changing them to get a push through is not.

## Efficient execution

The Plan's rule 7 applies. In this repository:

- Use the SDK root that `DOTNET_ROOT` names (`& "$env:DOTNET_ROOT\dotnet.exe"` where a shell resolves `C:\Program Files\dotnet` first). Restore once with `dotnet restore <project> --locked-mode` into a scratch `NUGET_PACKAGES` folder outside the repository, then build incrementally with `--no-restore`.
- While iterating, run only the affected checks: the changed test project (`dotnet test tests/ArcForges.Mobile.Tests/ArcForges.Mobile.Tests.csproj -c Release --no-restore`, or the policy suite; then `--no-build`, with `--filter` for one class), one tooling test module (`python -m unittest discover -s eng/tests -p "test_mobile.py"`), `python eng/mobile.py check`, `python eng/maui_notices.py check` after a notice or lock change, and the Debug build of the app. Build the Release configuration (Mono AOT, R8) only when release, trimming or AOT inputs change.
- The full profile (the Windows MAUI leg with the candidate staging, the WSL checks and tests, and the scans) runs once, through `python eng/verify.py run` before handover, so that the push reuses the pass.

## Hosted CI

- **Owner PRs:** no hosted validation or security analysis; `Workflow lint`, `MAUI`, `Security` and `Verify` show as skipped. `Verify` is the required check (ruleset); a skipped `Verify` satisfies it.
- **External PRs** (Dependabot included) and manual dispatches: the full CI as before: `Workflow lint`, `MAUI (ubuntu-latest)` and `MAUI (windows-latest)`, and `security.yml` called as `Security` (dependency review on PRs, the full-history secret scan, CodeQL for Python, Actions and C#), with `Verify` requiring every one of them.
- **Main pushes:** delivery only. `MAUI (ubuntu-latest)` builds the Release APK, runs its identity gate, the closure and notice checks and the Linux licence evidence, and stages the candidate; the Windows leg, the Debug build, the host and policy tests and the repository checks are skipped, because the PR was verified before merge. For an owner PR this is the first Linux Android build of that code (the local gap above). `publish` then signs and publishes that candidate, with its environment, secrets and steps unchanged; it needs the candidate job, not `Verify`, which does not run on a push.
- **Schedule** (weekly, `security.yml`): the secret scan and CodeQL. No build.
