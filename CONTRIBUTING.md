# Contributing

Read [development.md](docs/development.md), install the .NET SDK 10.0.400 that `global.json` pins together with the workload set 10.0.401 and the listed Android SDK components, and, for the maintainer's own pushes, install the local verification hooks once with `python eng/verify.py install` ([AGENTS.md](AGENTS.md), Local verification). External contributors need no local hook. Python 3.14.7 (see `.python-version`) runs the repository tools.

Use a branch or worktree and open a pull request. Keep changes within their requested scope. The pre-commit hook checks whitespace; the pre-push hook runs the full local verification. For pull requests from anyone but the maintainer, CI builds on Windows and Linux, runs the offline host and policy tests, the eng tests, the workflow lint, the dependency review, the secret scan and CodeQL. A main push builds the MAUI candidate on Linux, then signs and publishes it. Device, emulator and live Cloud tests are local opt-in; they are not hosted gates. Follow the restrictions in AGENTS.md.

Restore with `--locked-mode` into a clean `NUGET_PACKAGES` folder, and commit each `packages.lock.json` that a change affects. A NuGet update needs an admission record under `eng/policy/dependency-reviews`, a locked restore and a human review before it merges; see [dependency-policy.md](docs/dependency-policy.md). Do not relax the lock or the admission to make an update pass.

Changes to signing, release versions or CI must explain their effect on installed-app upgrades and the order of validation and publication. Repository code and scripts are Apache-2.0; retain applicable third-party notices. Never copy incompatible source into this repository.
