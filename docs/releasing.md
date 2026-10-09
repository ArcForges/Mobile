# Android releases

This procedure describes the repository's current Android-only release channel: the .NET MAUI application. The [platform and distribution matrix](../README.md#platform-and-distribution-matrix) is authoritative for what is delivered.

## Pipeline and immutable candidate

`CI` runs on PRs, main pushes and manual validation. The `maui` job runs on Windows and Linux: it installs the pinned workload set, restores the projects with locked restores into a clean `NUGET_PACKAGES` folder, builds the Debug and Release (Mono AOT, R8) APKs, runs the host and policy tests and checks the notice closure. On Linux it also runs the repository and eng checks, the licence evidence, and stages the MAUI candidate: the release APK with its mapping, notices, licence closure and build identity. `security` runs the dependency review, the secret scan and CodeQL. `workflow-lint` runs actionlint. `Verify` requires `maui`, `security` and `workflow-lint`; it has no emulator, live Cloud or public-install dependency.

Only a main push enters `android-release`. The `publish` job binds the sealed MAUI candidate to its source and run, signs its APK with the persistent key (`zipalign -P 16`, `apksigner`), checks the certificate and the host-only notice proof, and seals `release.json` and `SHA256SUMS`. It does not rebuild the application. GitHub receives the signed APK and its companions. Checksums are distribution metadata, not a demand for repeated downloads.

Successful release creation is the publication boundary. No anonymous download, install, emulator, upgrade or live Cloud test follows it. PR and manual CI never publish. Green build or publication status does not claim physical-device, store or full commercial acceptance.

## One-time GitHub configuration

In `ArcForges/Mobile`, the repository environment **android-release** allows only the `main` branch, without a required manual reviewer if unattended main publishing is intended. GitHub environments belong to a repository; a same-named environment elsewhere is not shared automatically.

| Environment setting | Kind | Value |
| --- | --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Secret | Base64 of the dedicated persistent JKS keystore |
| `ANDROID_KEYSTORE_PASSWORD` | Secret | Keystore password |
| `ANDROID_KEY_ALIAS` | Secret | Alias in that keystore |
| `ANDROID_KEY_PASSWORD` | Secret | Private-key password |
| `ANDROID_SIGNING_CERT_SHA256` | Variable | Public certificate SHA-256 fingerprint, without colons |

Use a dedicated RSA 3072-bit or stronger Android release key with a long validity period. Store its keystore and password backup outside Git and retain them securely: future APKs need that identity to update existing installations. Do not generate a fresh key on every CI run. `eng/mobile.py maui-sign` receives passwords through environment variables rather than command-line values, creates only a temporary keystore and checks the output certificate against the pinned fingerprint in `eng/policy/dotnet-toolchain.json`.

The workflow uses GitHub's short-lived `GITHUB_TOKEN` with `contents: write` only in the publish job. No PAT, NuGet account or Maven signing key is needed. GitHub release distribution needs no Play Console account, and this repository does not configure Play publishing or Play App Signing. Any store channel requires separate approval and implementation.

Protect `main` with PR review and merge rules, and require the aggregate `Verify` status. Enable private vulnerability reporting and Dependabot alerts. Keep third-party Actions pinned to commit hashes and let Dependabot propose updates.

## Versions and installation

The workflow derives `versionName = 0.1.0-ci.<run_number>.<run_attempt>` and `versionCode = run_number * 100 + run_attempt`. Attempts are limited to 1..99; the resulting code must remain below Android's 2,100,000,000 ceiling. No commit is pushed merely to bump a version. Keep the workflow's run-number history; if replacing it or importing already released builds, establish a higher version-code baseline first.

Release tags are `android-<versionName>`. They are development prereleases in the repository's Releases list. The signed APK is directly installable on Android 8.0 or newer (minimum API 26). The MAUI application targets API 36.1 under D-016 (see [maui-toolchain.md](maui-toolchain.md)). The MAUI path produces no AAB, and the release is not submitted to any store. PRs and manual runs validate only and do not publish.

The release tag and title are `android-VERSION` and `Android VERSION (.NET MAUI)`, with `release.json` track `maui`. The AND.40 PR A prereleases under `android-maui-VERSION` remain as published history, and the Kotlin prereleases published before AND.40 PR B stay immutable on the Releases list. Nothing is deleted or unpublished.

## Failures, retries and recovery

- A failed build or security check prevents signing and publishing. Inspect the first failed job.
- Missing signing settings cause a clear publish-job failure; configure them before the first main merge.
- Diagnose the failure before any rerun. If a rerun is necessary, rerun **all jobs**, not only publication: a new run attempt has a new version and candidate artifact name. This prevents combining candidates from different attempts.
- If a release creation partially succeeded, inspect the existing tag, release and recorded asset hashes. Do not overwrite immutable published assets. Fix forward with a new main commit and therefore a new version.
- Do not rerun an older commit after newer builds have shipped to try to downgrade users. Android normally rejects lower version codes. Revert the source change in a new commit and ship it with a higher version code, using the same certificate.
- Preserve the R8 mapping for each exact version for crash deobfuscation. `release.json` maps release hashes back to the candidate, commit and certificate.

A successful PR proves candidate validation, not the main-only publish job. A locally signed install proves the key and APK work together, not that GitHub has published them. After merge, record the expected merge SHA, the required main publish status and a clean primary fast-forward. Do not start a public download or install verification cycle.

Build identity and independent version sources are described in [build-identity.md](build-identity.md). The `build-identity.json` of each MAUI build is embedded in the APK and published beside it.

## Application identity change to com.arcforges.mobile (AND.01)

The permanent Android applicationId is `com.arcforges.mobile` (IRD-23; P2-021 item 3). The Kotlin development prereleases published under `io.github.arcforges.mobile` (and `io.github.arcforges.mobile.debug`) hold no production user data, so the disposition is reinstall guidance with no data migration.

- Android treats `com.arcforges.mobile` as a different application. Installing it does not upgrade an `io.github.arcforges.mobile` build and does not carry its data across.
- To move a device: uninstall the `io.github.arcforges.mobile` build first. That discards its local data, including its Kotlin secure-storage data, which is expected for development builds. Then install the `com.arcforges.mobile` build. No migration is provided or required.
- A device that holds a debug-signed `com.arcforges.mobile` build must uninstall it before installing a release-signed build.
- The Kotlin prereleases stay immutable on the Releases list and receive no further updates. The Kotlin application, its KMP module and its Gradle build retired with AND.40 PR B.
- The persistent android-release signing identity is kept (certificate SHA-256 `7a8b3b14…`, recorded in `eng/published.py` and `eng/policy/dotnet-toolchain.json`). Keeping it does not avoid the reinstall, because the applicationId itself changed.
- The MAUI project at `src/ArcForges.Mobile` is the application: the Hello screen and its view model, with `android.permission.INTERNET` as its only permission and one launchable activity, `MainActivity`. The identity and toolchain pins are checked offline by `python eng/maui_identity.py` (and by `python eng/mobile.py check`). See [maui-toolchain.md](maui-toolchain.md).

## Local opt-in verification

`python eng/published.py maui-prepare --directory <new folder> --candidate <sealed candidate folder>` verifies an anonymously downloaded MAUI prerelease against its sealed candidate: the seal, every member digest, the persistent signature, the release archive re-derived from the public APK and the binutils proof. It is local opt-in only and is refused in CI. Any device check is local only.
