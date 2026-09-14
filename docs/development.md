# Development and validation

## Requirements

Use JDK 21, Python 3.14.7 and the committed Gradle wrapper. Install Android SDK `platforms;android-37.0`, `build-tools;37.0.0` and platform-tools through Android Studio. Set `ANDROID_HOME` or use an untracked `local.properties` for Gradle; the Python device/signing helpers use `ANDROID_HOME`. A device/emulator is needed for installation and instrumentation. The standard CI emulator is API 36 x86_64 with Google APIs.

No Node, npm, CMake, NDK or neighboring source checkout is required for this bootstrap. Android libraries may contain their own published native runtime components.

## Layout and commands

- `app/src/main`: Android entry point and published protobuf/native gRPC adapter.
- `shared/src/commonMain`: the same UI and greeting behavior used by Android and the development preview.
- `shared/src/desktopMain`: a JVM window hosting that UI. No desktop installer or native distribution is published.
- `app/src/test`: public Contracts serialization and real in-process gRPC success/status tests.
- `app/src/androidTest`: device UI interaction and Activity recreation tests.
- `eng`: repository, bytecode, candidate, signing and device checks.

```sh
python eng/mobile.py hooks
python eng/mobile.py check
./gradlew spotlessApply
./gradlew spotlessCheck :shared:desktopTest :app:testDebugUnitTest :app:lintRelease
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:assembleRelease :app:bundleRelease
python eng/mobile.py bytecode
./gradlew :app:connectedDebugAndroidTest
./gradlew :app:installDebug
```

Use `gradlew.bat` on Windows. The pre-commit hook checks text/structured files and whitespace; the pre-push hook checks Kotlin formatting and unit tests. CI remains authoritative, including when a local hook is unavailable.

The bytecode check inspects application/shared `.class` files for JVM 21 before D8/R8 converts Android code to DEX. Dependency JARs such as Contracts may target an older JVM; that does not change this application's compiler target or its minimum Android API.

## Shared UI hot reload

Run `./gradlew :shared:hotRunDesktop` from Windows x64 or Linux x64. Edit a composable in `shared/src/commonMain` and save; Compose Hot Reload recompiles shared JVM code and updates the running preview. It uses a JetBrains Runtime with enhanced class redefinition, provisioned through the Foojay resolver. Keep Java/Kotlin bytecode at 21. This task requires the development runtime and a graphical session; building an APK does not require running the preview.

The JVM preview uses the shared greeting function. Android wraps that same behavior in a local protobuf round trip to exercise the published Contracts message types under R8. The app does not claim to contact a backend. `HelloClient` demonstrates the published coroutine RPC stub with a deadline; the caller must own a TLS channel and its lifecycle before using it in a future connected screen.

Android devices do not run this JVM preview. Use [Android Studio Live Edit](https://developer.android.com/develop/ui/compose/tooling/iterative-development) for supported Android edits, or reinstall the debug APK. See [Compose Hot Reload](https://kotlinlang.org/docs/multiplatform/compose-hot-reload.html) for changes requiring a restart and runtime requirements.

## Dependency maintenance

Direct versions live in `gradle/libs.versions.toml`; Gradle and its distribution checksum live in `gradle/wrapper/gradle-wrapper.properties`. Do not use dynamic Maven versions or `mavenLocal()`. APK consumers do not generate `.proto` files themselves.

Strict Gradle locking and SHA-256 verification apply in ordinary builds and CI. Windows and Linux preview runtimes have separate shared-module lockfiles under `gradle/locks`, because their native Skiko artifacts differ. Android dependencies remain in `app/gradle.lockfile`. A checksum file records the exact artifacts; review new artifacts and their upstream origin before accepting it.

After selecting an update, regenerate the affected graphs and checksum metadata, then run normal strict verification again:

```sh
./gradlew --write-locks --write-verification-metadata sha256 :shared:hotRunDesktopArgfile resolveDependencies
./gradlew -PpreviewPlatform=linux-x64 --write-locks --write-verification-metadata sha256 :shared:hotRunDesktopArgfile resolveDependencies
./gradlew -PpreviewPlatform=windows-x64 --write-locks --write-verification-metadata sha256 :shared:hotRunDesktopArgfile resolveDependencies
./gradlew --write-locks --write-verification-metadata sha256 spotlessCheck :shared:desktopTest :app:testDebugUnitTest :app:lintRelease :app:assembleDebugAndroidTest :app:assembleRelease :app:bundleRelease
```

The cross-platform resolution commands download the other preview runtime without executing it. A full Windows and Linux CI build is still required. Commit all affected locks and `gradle/verification-metadata.xml`; run `git diff --check` and inspect the diff. Dependabot proposes updates but may need these generated files refreshed in its PR, particularly for Gradle/plugin changes. A failed dependency update is not fixed by floating versions, deleting locks or weakening checksum verification.

## Security tooling compatibility

CodeQL scans Java/Kotlin, Python and Actions. Kotlin 2.4.20 requires the same temporary, date-pinned and checksum-verified CodeQL bundle used by Contracts: `codeql-bundle-20260913`. Stable CLI 2.27.0 misses the Kotlin extraction fix in [github/codeql#22404](https://github.com/github/codeql/pull/22404). Remove the override once the action's recommended stable CLI is at least 2.27.1 and includes that fix. The scanner override does not change the app's stable compiler or runtime dependencies.

## Evidence boundaries

Unit tests establish shared behavior and generated API interoperability. Emulator tests establish rendered UI, state restoration and release APK startup on that image. Hot Reload requires a running preview and an observed edit/reload. Physical devices, production backend integration, Play submission and real user operation require separate evidence; none is implied by a green documentation or build check.
