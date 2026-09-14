# Repository guidance

- The current product target is Android. `shared` also hosts a JVM Compose Hot Reload preview used only for development. Do not add desktop or iOS product distribution.
- Keep Kotlin and Java compiler targets at JVM 21. The JDK running Gradle and the JetBrains Runtime running Hot Reload are separate choices.
- Consume published Contracts artifacts with exact Maven versions. No submodules, neighboring source dependencies, copied generated contracts or local Maven publishing shortcuts.
- Plan changes before implementation, finish collecting related issues before fixing them, and keep verification proportional to the change.
- Keep documentation and code comments in English. Never commit SDK paths, signing material, APKs, AABs or build caches.
- Preserve the release dependency chain: candidate build, all required checks, protected signing of that candidate, publication. PRs must not use release secrets.
- Run relevant checks from `docs/development.md`. Distinguish JVM tests, emulator evidence, physical-device evidence and actual publication.
- Dependabot updates must also update affected locks and checksum metadata. Do not weaken verification to avoid maintaining those files.
- Apache-2.0 applies to original code and tooling. Respect dependency licenses and retained notices.
