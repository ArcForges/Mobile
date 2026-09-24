# Repository guidance

- The current product target is Android. `shared` also hosts a JVM Compose Hot Reload preview used only for development. Do not add desktop or iOS product distribution.
- Keep Kotlin and Java compiler targets at JVM 21. The JDK running Gradle and the JetBrains Runtime running Hot Reload are separate choices.
- Consume published Contracts artifacts with exact Maven versions. No submodules, neighboring source dependencies, copied generated contracts or local Maven publishing shortcuts.
- Plan changes before implementation, finish collecting related issues before fixing them, and keep verification proportional to the change.
- Keep documentation and code comments in English. Never commit SDK paths, signing material, APKs, AABs or build caches.
- Preserve the release dependency chain: candidate build, all required checks, protected signing of that candidate, publication. PRs must not use release secrets.
- Run the scoped offline checks from `docs/development.md`; runtime checks require explicit local opt-in. Distinguish compilation, local runtime observations and publication.
- Dependabot updates must also update affected locks and checksum metadata. Do not weaken verification to avoid maintaining those files.
- Apache-2.0 applies to original code and tooling. Respect dependency licenses and retained notices.

## Delivery model (P2-018)

Work is scheduled as delivery tasks in the [delivery graph](https://github.com/ArcForges/ArcForges-Design-B/blob/fd16c5f285de0bda2d0320cdff4d52c34c9098ed/docs/planning/delivery/README.md) and executed through the [Plan execution entry](https://github.com/ArcForges/Plan-B/blob/0cb637d1bfbf64d7db22a96a2b7370a409a25d8e/arcforges-implementation.md). There is no Current task, numbered substep order or single main context.

- Baseline: The accepted bootstrap is the Android application with its development package identity, the preview-only shared module and the transport probe client, with the WP02 build, dependency and provenance baselines. Every Android companion capability is an open task. This repository's tasks are in the [android](https://github.com/ArcForges/ArcForges-Design-B/blob/fd16c5f285de0bda2d0320cdff4d52c34c9098ed/docs/planning/delivery/lanes/android.md) lane and parts of the governance, release and runtime-proof lanes.
- Start only a task that Plan-B's `python tools/delivery.py ready --claims` lists and whose `claims/<task-id>` branch you hold. A task here becomes ready only after the adoption slice for its lane (`ADOPT.10.<lane>`) is recorded.
- Several workers may work here at once, each on a different claimed task in its own retained worktree and `task/<task-id>` branch, inside the task's write scope. After the module skeleton task, each feature task edits only its own module, so storage, security, network and screen work proceed in parallel.
- Shared files follow their [declared protocols](https://github.com/ArcForges/ArcForges-Design-B/blob/fd16c5f285de0bda2d0320cdff4d52c34c9098ed/docs/planning/delivery/shared-resources.md): the module skeleton task registers all modules once and later tasks edit only their module; version catalog entries are appended and locks and verification metadata regenerated after rebase; dependency additions carry admission receipts; signing identities and store listings are used only by release tasks through protected CI environments. The Mobile integration owner orders merges and merges only pull requests of the claimant at the current claim epoch.
- Title pull requests `[<TASK-ID>] <summary>`; a bundle of compatible ready tasks lists each ID, and planning alignment uses `[P2-018]`.
- Earlier dated bootstrap and provenance records under `docs/` describe their original scope; they are evidence, not execution instructions.

## CI and execution restrictions (Design P2-017)

- No macOS runner/matrix, including self-hosted, scheduled or manual CI.
- No hosted physical-device/emulator, desktop GUI, browser E2E, live service/RPC/inference, installed-package consumer or public-release install/upgrade execution. Remove hidden invocations and obsolete dependencies as well as jobs.
- Keep necessary Windows/Linux builds, packaging, targeted offline/static/security checks and required dependency locks, signing and licence/provenance boundaries. Stage the release candidate once and check its sealed identity only at the signing handoff.
- Runtime helpers are explicit local opt-in using existing tools, once for affected behavior. Do not provision/reinstall SDKs, emulators, vcpkg or toolchains for validation. Do not routinely download public artifacts or repeat archive/hash/consumer checks.
- Hooks must not build/test implicitly. Independent owner agents are allowed; serialize CPU-heavy local builds. Use retained worktrees and append to related open PRs.
- Use normal networking, no explicit proxy or wsl.exe wrapper. Stop and report a failed network operation; do not retry or reconfigure networking.
- Review complete PRs, fix findings and merge after retained applicable latest-head CI passes. Post-merge checks are the merge SHA, required build/publish/deploy status and clean primary fast-forward only. Preserve branches/worktrees and report untested runtime coverage honestly.

Authority: [CI and local validation policy](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/assurance/ci-and-local-validation-policy.md).
