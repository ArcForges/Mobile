# Contributing

Read [development.md](docs/development.md), install JDK 21 and the listed Android SDK components, and enable the local hooks with `python eng/mobile.py hooks`.

Use a branch or worktree and open a pull request. Keep changes within their requested scope. Run `./gradlew spotlessApply` before committing Kotlin changes. Hooks only check whitespace. CI builds on Windows/Linux, runs offline shared unit checks, formatting, lint and security, then signs/publishes the original release candidate on main. Device, transport-fixture and live Cloud tests are local opt-in; they are not hosted gates. Follow the restrictions in AGENTS.md.

Commit Gradle lockfiles and `gradle/verification-metadata.xml`. Review dependency changes before regenerating checksums; a newly downloaded checksum is not independent proof of origin. See the dependency update procedure in [development.md](docs/development.md). Do not disable strict verification or allow failing checks to make a dependency update pass.

Changes to signing, release versions or CI must explain their effect on installed-app upgrades and the order of validation and publication. Repository code and scripts are Apache-2.0; retain applicable third-party notices. Never copy incompatible source into this repository.
