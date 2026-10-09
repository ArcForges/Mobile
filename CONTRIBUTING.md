# Contributing

Read [development.md](docs/development.md), install the .NET SDK 10.0.400 that `global.json` pins together with the workload set 10.0.401 and the listed Android SDK components, and enable the local hooks with `python eng/mobile.py hooks`. Python 3.14.7 (see `.python-version`) runs the repository tools.

Use a branch or worktree and open a pull request. Keep changes within their requested scope. Hooks only check whitespace. CI builds on Windows and Linux, runs the offline host and policy tests, the eng tests, the workflow lint, the dependency review, the secret scan and CodeQL, then signs and publishes the MAUI candidate from main. Device, emulator and live Cloud tests are local opt-in; they are not hosted gates. Follow the restrictions in AGENTS.md.

Restore with `--locked-mode` into a clean `NUGET_PACKAGES` folder, and commit each `packages.lock.json` that a change affects. A NuGet update needs an admission record under `eng/policy/dependency-reviews`, a locked restore and a human review before it merges; see [dependency-policy.md](docs/dependency-policy.md). Do not relax the lock or the admission to make an update pass.

Changes to signing, release versions or CI must explain their effect on installed-app upgrades and the order of validation and publication. Repository code and scripts are Apache-2.0; retain applicable third-party notices. Never copy incompatible source into this repository.
