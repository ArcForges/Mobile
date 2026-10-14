# Repository guidance

- The current product target is Android: the .NET MAUI application under `src/ArcForges.Mobile`. The Kotlin application, its KMP module and its Gradle build are retired (AND.40 PR B). Do not add desktop, iOS or macOS product distribution.
- Shipped projects target `net10.0-android` only; host-run test, policy and architecture projects target `net10.0`. Product logic is C#. Kotlin and Java product code is not allowed. The JDK 21.0.12 pin in `ci.yml` is Android platform tooling only.
- Consume published `ArcForges.Contracts.*` NuGet packages with exact versions. No submodules, neighboring source dependencies, copied generated contracts or local NuGet publishing shortcuts.
- Plan changes before implementation, finish collecting related issues before fixing them, and keep verification proportional to the change.
- Keep documentation and code comments in English. Never commit SDK paths, signing material, APKs, AABs or build caches.
- Preserve the release dependency chain: candidate build, all required checks, protected signing of that candidate, publication. PRs must not use release secrets.
- Run the scoped offline checks from `docs/development.md`; runtime checks require explicit local opt-in. Distinguish compilation, local runtime observations and publication.
- NuGet updates must update the affected `packages.lock.json` files and carry an admission record. Do not weaken locked restores to avoid maintaining those files.
- Apache-2.0 applies to original code and tooling. Respect dependency licenses and retained notices.

## Flagship role

Mobile is an **active** repository of the ArcForges flagship ([AD-0001](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0001-flagship-pivot.md)); the design authority is [ArcForges-Design](https://github.com/ArcForges/ArcForges-Design). Per [architecture 01 §5](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/architecture/01-system-overview.md#5-repository-and-project-map), [architecture 12 §6](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/architecture/12-client-applications.md) and the [reuse classification](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/reuse/inventory-and-classification.md#5-mobile), it reuses the MAUI app shell, the AOT/R8 release configuration, the gRPC-Web network layer (`ArcForges.Mobile.Network`) and the Keystore wrapper (`ArcForges.Mobile.Security`). The flagship adds the Android companion: sign-in, QR pairing, fleet and node views, actions and approvals, push notifications and Play Billing subscriptions ([Android experience](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/experience/android.md)).

## Delivery (serial, ArcForges/Plan)

Tasks for this repository come from the [Plan delivery graph](https://github.com/ArcForges/Plan/blob/main/delivery-graph.json) and are delivered under the Plan [execution policy](https://github.com/ArcForges/Plan/blob/main/execution-policy.md) and [delivery procedure](https://github.com/ArcForges/Plan/blob/main/delivery-procedure.md) ([AD-0014](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/decisions/AD-0014-delivery-method.md)). They are binding. The historical P2-018 model (delivery lanes, adoption slices, `delivery.py` claims and handoffs, parallel or independent owner agents, integration-owner roles, the build slot and the launcher) is retired and never resumed.

- One task is active at a time. Work only inside its write scope, in a worktree `.worktree/<task-id-lower>` on branch `task/<task-id-lower>`, never in the primary checkout.
- Delegated workers and reviewers work locally. Only the coordinator pushes, opens pull requests, merges (at the reviewed head, after hosted CI passes) and publishes.
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
- Hooks must not build/test implicitly. Use retained worktrees.
- Use the normal network and never change proxy or network configuration. Diagnose a failure before any rerun, retry transient failures with bounded backoff, inspect remote state before retrying a write, and report the exact operation when a failure persists. Linux opt-in checks run in the local WSL2 Debian distribution (P2-024); installs inside it are the user's, and there is no SSH.
- Every pull request gets an independent review of its complete latest head; findings are fixed, and the coordinator merges only at the reviewed head after applicable latest-head CI passes. Post-merge checks are the merge SHA, required build/publish/deploy status and clean primary fast-forward only. Preserve branches/worktrees and report untested runtime coverage honestly.
