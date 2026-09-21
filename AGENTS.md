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

## CI and execution restrictions (Design P2-017)

- No macOS runner/matrix, including self-hosted, scheduled or manual CI.
- No hosted physical-device/emulator, desktop GUI, browser E2E, live service/RPC/inference, installed-package consumer or public-release install/upgrade execution. Remove hidden invocations and obsolete dependencies as well as jobs.
- Keep necessary Windows/Linux builds, packaging, targeted offline/static/security checks and required dependency locks, signing and licence/provenance boundaries. Stage the release candidate once and check its sealed identity only at the signing handoff.
- Runtime helpers are explicit local opt-in using existing tools, once for affected behavior. Do not provision/reinstall SDKs, emulators, vcpkg or toolchains for validation. Do not routinely download public artifacts or repeat archive/hash/consumer checks.
- Hooks must not build/test implicitly. Independent owner agents are allowed; serialize CPU-heavy local builds. Use retained worktrees and append to related open PRs.
- Use normal networking, no explicit proxy or wsl.exe wrapper. Stop and report a failed network operation; do not retry or reconfigure networking.
- Review complete PRs, fix findings and merge after retained applicable latest-head CI passes. Post-merge checks are the merge SHA, required build/publish/deploy status and clean primary fast-forward only. Preserve branches/worktrees and report untested runtime coverage honestly.

Authority: [CI and local validation policy](https://github.com/ArcForges/ArcForges-Design/blob/main/docs/assurance/ci-and-local-validation-policy.md).
