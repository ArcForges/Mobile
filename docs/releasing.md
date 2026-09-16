# Android releases

## Pipeline and immutable candidate

`CI` runs on PRs, pushes to `main`, and manual validation requests. Both Windows and Linux build from the same commit with JDK/JVM 21. Unit tests, formatting, lint and bytecode verification must pass. The Linux build uploads unsigned release APK/AAB, debug/test APKs, the R8 mapping and `candidate.json` with SHA-256 hashes and source/version metadata.

The emulator job downloads that candidate, verifies its hashes, runs debug instrumentation including real Cloud gRPC-Web calls, and invokes Hello from its minified release APK with a disposable test signature. Security scans run in parallel. The aggregate `Verify` check succeeds only when both OS builds, device checks and security checks succeed. No Cloudflare deployment credential is needed for the anonymous Hello gate; the currently deployed service must be available. Saved Android evidence records its observed revision, protocol outcomes and the release UI response.

Only a `push` to `main` then enters `android-release`. It downloads and re-verifies the same candidate, aligns/signs its APK, signs its AAB and verifies the signatures and persistent certificate. It does not rebuild application code. GitHub Releases receives the signed APK/AAB, R8 mapping, `release.json` and `SHA256SUMS`. The development JVM preview is never released. PRs and manual validation runs never publish.

## One-time GitHub configuration

In `ArcForges/Mobile`, create the repository environment **android-release**. Allow only the `main` branch, without a required manual reviewer if unattended main publishing is intended. GitHub environments belong to a repository; a same-named environment elsewhere is not shared automatically.

| Environment setting | Kind | Value |
| --- | --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Secret | Base64 of the dedicated persistent JKS keystore |
| `ANDROID_KEYSTORE_PASSWORD` | Secret | Keystore password |
| `ANDROID_KEY_ALIAS` | Secret | Alias in that keystore |
| `ANDROID_KEY_PASSWORD` | Secret | Private-key password |
| `ANDROID_SIGNING_CERT_SHA256` | Variable | Public certificate SHA-256 fingerprint, without colons |

Use a dedicated RSA 3072-bit or stronger Android release key with a long validity period. Store its keystore and password backup outside Git and retain them securely: future APKs need that identity to update existing installations. Do not generate a fresh key on every CI run. `eng/mobile.py sign` receives passwords through environment variables rather than command-line values, creates only a temporary keystore and checks the output certificate against the configured fingerprint.

The workflow uses GitHub's short-lived `GITHUB_TOKEN` with `contents: write` only in the release job; no PAT, NuGet account, npm token or Maven signing key is needed. GitHub release distribution needs no Play Console account. Play publishing and Play App Signing are separate future setup steps.

Protect `main` with PR review/merge rules and require the aggregate `Verify` status after the first PR establishes its check name. Enable private vulnerability reporting and Dependabot alerts. Keep third-party Actions pinned to commit hashes and let Dependabot propose updates.

## Versions and installation

The workflow derives `versionName = 0.1.0-ci.<run_number>.<run_attempt>` and `versionCode = run_number * 100 + run_attempt`. Attempts are limited to 1..99; the resulting code must remain below Android's 2,100,000,000 ceiling. No commit is pushed merely to bump a version. Keep the workflow's run-number history; if replacing it or importing already released builds, establish a higher version-code baseline first.

Release tags are `android-<versionName>`. They are development prereleases, available in the repository's Releases list. The APK is directly installable on Android 8.0 or newer; the AAB is an upload bundle, not an installable file. Debug builds use `io.github.arcforges.mobile.debug`, allowing development and release installs to coexist. Release builds use `io.github.arcforges.mobile`.

## Failures, retries and recovery

- A failed build/device/security check prevents signing and publishing. Inspect the first failed job.
- Missing signing settings cause a clear release-job failure; configure them before the first main merge.
- Rerun **all jobs**, not only a failed publication job: a new run attempt has a new version and candidate artifact name. This prevents combining candidates from different attempts.
- If a release creation partially succeeded, inspect the existing tag, release and recorded asset hashes. Do not overwrite immutable published assets. Fix forward with a new main commit and therefore a new version.
- Do not rerun an older commit after newer builds have shipped to try to downgrade users. Android normally rejects lower version codes. Revert the source change in a new commit and ship it with a higher version code, using the same certificate.
- Preserve the R8 mapping for each exact version for crash deobfuscation. `release.json` maps release hashes back to the candidate, commit and certificate.

A successful PR proves candidate validation, not the main-only release job. A locally signed install proves the key and APK work together, not that GitHub has published them. Record the first successful main release and download/install check separately after merge.
