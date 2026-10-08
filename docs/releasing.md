# Android releases

This procedure describes the repository's current Android-only release channel. The [platform and distribution matrix](../README.md#platform-and-distribution-matrix) is authoritative for what is delivered: implementation source reuse and the JVM preview do not create a desktop, iOS or cross-platform product commitment.

## Pipeline and immutable candidate

`CI` runs on PRs, main pushes and manual validation. Windows/Linux compile the app, run offline shared unit tests, formatting, release lint and bytecode checks. App transport tests are compiled but run only by explicit local opt-in. Security runs once through the reusable workflow; scheduled/manual security analyses share the same CodeQL categories.

The Linux producer stages release APK/AAB, R8 mapping, build identity and legal/provenance companions. It checks actual release archive resources once against the reviewed profile. Debug/instrumentation APKs are not promoted. `Verify` requires build and security success; it has no emulator, live Cloud or public-install dependency.

Only a main push enters `android-release`. The publisher binds the original candidate's closed file set and hashes to the source/run, then aligns/signs its APK and signs its AAB with the persistent key. Required certificate/signature and signing-preservation checks remain. Application code is not rebuilt, and the full provenance archive scan is not repeated. GitHub Releases receives APK/AAB, mapping, notices, identity/provenance, `release.json` and `SHA256SUMS`. Checksums remain useful distribution metadata, not a demand for repeated downloads.

Successful release creation is the publication boundary. No anonymous download, install, emulator, upgrade or live Cloud test follows it. PR/manual CI never publishes. Green build/publication status does not claim physical-device, store or full commercial acceptance. Design P2-017 governs this reduced pipeline.

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

The workflow uses GitHub's short-lived `GITHUB_TOKEN` with `contents: write` only in the release job; no PAT, NuGet account, npm token or Maven signing key is needed. GitHub release distribution needs no Play Console account. This repository does not currently configure Play publishing, a Play listing or Play App Signing. Any store channel requires separate approval and implementation; this release path makes no store-availability promise.

Protect `main` with PR review/merge rules and require the aggregate `Verify` status after the first PR establishes its check name. Enable private vulnerability reporting and Dependabot alerts. Keep third-party Actions pinned to commit hashes and let Dependabot propose updates.

## Versions and installation

The workflow derives `versionName = 0.1.0-ci.<run_number>.<run_attempt>` and `versionCode = run_number * 100 + run_attempt`. Attempts are limited to 1..99; the resulting code must remain below Android's 2,100,000,000 ceiling. No commit is pushed merely to bump a version. Keep the workflow's run-number history; if replacing it or importing already released builds, establish a higher version-code baseline first.

Release tags are `android-<versionName>`. They are development prereleases, available in the repository's Releases list. The signed APK is directly installable on Android 8.0 or newer (minimum API 26); the signed AAB is an upload bundle, not an installable file, and the current workflow does not submit it to a store. Debug builds use `io.github.arcforges.mobile.debug`, allowing development and release installs to coexist. Release builds use `io.github.arcforges.mobile` (target API 37). PRs and manual runs validate only and do not publish.

## Failures, retries and recovery

- A failed build/security check prevents signing and publishing. Inspect the first failed job.
- Missing signing settings cause a clear release-job failure; configure them before the first main merge.
- Diagnose the failure before any rerun. If a rerun is necessary, rerun **all jobs**, not only publication: a new run attempt has a new version and candidate artifact name. This prevents combining candidates from different attempts.
- If a release creation partially succeeded, inspect the existing tag, release and recorded asset hashes. Do not overwrite immutable published assets. Fix forward with a new main commit and therefore a new version.
- Do not rerun an older commit after newer builds have shipped to try to downgrade users. Android normally rejects lower version codes. Revert the source change in a new commit and ship it with a higher version code, using the same certificate.
- Preserve the R8 mapping for each exact version for crash deobfuscation. `release.json` maps release hashes back to the candidate, commit and certificate.

A successful PR proves candidate validation, not the main-only release job. A locally signed install proves the key and APK work together, not that GitHub has published them. After merge, record the expected merge SHA, required main build/publish status and clean primary fast-forward. Do not start a public download/install verification cycle.

Build identity and independent version sources are described in [build-identity.md](build-identity.md). The published `build-identity.json` is also embedded in every Android archive and read by the installed app.

## Application identity change to com.arcforges.mobile (AND.01)

The permanent Android applicationId is `com.arcforges.mobile` (IRD-23; P2-021 item 3). The development prereleases published under `io.github.arcforges.mobile` (and `io.github.arcforges.mobile.debug`) hold no production user data, so the disposition is reinstall guidance with no data migration.

- Android treats `com.arcforges.mobile` as a different application. Installing it does not upgrade an `io.github.arcforges.mobile` prerelease and does not carry its data across.
- To move a device: uninstall the `io.github.arcforges.mobile` prerelease first. That discards its local data, including its Kotlin secure-storage data, which is expected for development builds. Then install the `com.arcforges.mobile` build. No migration is provided or required.
- The development prereleases stay immutable on the Releases list. They receive no further updates.
- The persistent android-release signing identity is kept (certificate SHA-256 `7a8b3b14…`, recorded in `eng/published.py`). The same key is intended for the MAUI release channel. Keeping it does not avoid the reinstall, because the applicationId itself changes.
- No release may claim `com.arcforges.mobile` until its release channel is published (AND.40 for the MAUI application). The Gradle/Kotlin application still builds `io.github.arcforges.mobile` as the frozen baseline until then.
- The identity and toolchain pins are checked offline by `python eng/maui_identity.py` (and by `python eng/mobile.py check`). See [maui-toolchain.md](maui-toolchain.md).
