# Development and validation

## Requirements

Use JDK 21, Python 3.14.7 and the committed Gradle wrapper. Use the existing Android SDK `platforms;android-37.0`, `build-tools;37.0.0` and platform-tools through Android Studio. Set `ANDROID_HOME` or use an untracked `local.properties` for Gradle; the Python device/signing helpers use `ANDROID_HOME`. A device/emulator is needed for installation and instrumentation. No emulator runs in CI and no validation task provisions one.

No Node, npm, CMake, NDK or neighboring source checkout is required for this bootstrap. Android libraries may contain their own published native runtime components.

## Layout and commands

- `app/src/main`: Android entry point and published Connect-Kotlin gRPC-Web adapter.
- `shared/src/commonMain`: the same UI and greeting behavior used by Android and the development preview.
- `shared/src/desktopMain`: a JVM window hosting that UI. No desktop installer or native distribution is published.
- `app/src/test`: published client interoperability with a loopback HTTP fixture, application/HTTP errors, deadlines and coroutine cancellation. No live service is required for unit tests.
- `app/src/androidTest`: UI progress/error/retry/disposal checks, real Cloud greeting/recreation and direct Android HTTPS protocol verification.
- `eng`: repository, bytecode, candidate, signing and device checks.

```sh
python eng/mobile.py hooks
python eng/mobile.py check
./gradlew spotlessApply
./gradlew spotlessCheck :shared:desktopTest :shared:testAndroidHostTest :app:compileDebugUnitTestKotlin :app:lintRelease
./gradlew :app:assembleRelease :app:bundleRelease
python eng/mobile.py bytecode
```

Use `gradlew.bat` on Windows. Both hooks check whitespace only; they never restore, compile or run tests. Run relevant checks once with existing caches. Do not add macOS or hosted runtime validation.

The bytecode check inspects application/shared `.class` files for JVM 21 before D8/R8 converts Android code to DEX. Dependency JARs such as Contracts may target an older JVM; that does not change this application's compiler target or its minimum Android API.

Kotlin compilation, Gradle deprecations and release lint fail on warnings. There are no authored-code diagnostic debt waivers. Generated and third-party inputs retain their separately reviewed provenance; do not suppress warnings in application code to pass validation.

## Shared UI hot reload

Run `./gradlew :shared:hotRunDesktop` from Windows x64 or Linux x64. Edit a composable in `shared/src/commonMain` and save; Compose Hot Reload recompiles shared JVM code and updates the running preview. It uses a JetBrains Runtime with enhanced class redefinition, provisioned through the Foojay resolver. Keep Java/Kotlin bytecode at 21. This task requires the development runtime and a graphical session; building an APK does not require running the preview.

Stop the preview before cleaning or rebuilding its outputs from another Gradle process. Use a separate worktree if a preview and an independent clean validation must run simultaneously.

The JVM preview uses the shared local greeting function and is explicitly labeled offline. Android supplies `CloudHelloClient.greet`, a suspending operation backed by the published Connect client. Launch and recomposition send no requests. One button press makes one RPC; the input/button are disabled while pending. A disposed composition cancels its coroutine; Activity destruction closes the owned HTTP transport. Name and completed result are saveable, pending work is not resumed after recreation, and failures allow manual retry. The Hello limit is 1..256 UTF-16 code units and text is preserved verbatim.

Android devices do not run this JVM preview. Use [Android Studio Live Edit](https://developer.android.com/develop/ui/compose/tooling/iterative-development) for supported Android edits, or reinstall the debug APK. See [Compose Hot Reload](https://kotlinlang.org/docs/multiplatform/compose-hot-reload.html) for changes requiring a restart and runtime requirements.

## Cloud protocol and device verification

`CloudHelloClient` uses `contracts-connect-client:1.0.0-ci.60.1`, the matching lite messages, and Connect-Kotlin OkHttp/Google Java-lite adapters 0.9.0. It explicitly selects `NetworkProtocol.GRPC_WEB` against `https://arcforges.com/api`; the SDK appends `/arcforges.hello.v1.HelloService/SayHello` once. Public native gRPC and Connect's default protocol are not used at this Worker ingress. INTERNET permission and the platform TLS trust store are sufficient. Cleartext traffic remains disabled, and no credential, custom trust manager or certificate bypass is added.

The RPC deadline is five seconds and the HTTP call limit is ten seconds. Redirects and connection-failure retries are disabled. gRPC status errors produce bounded user-facing messages; there is no local-success fallback. In-flight disposal does not replay the request. Transport cleanup runs off the Activity's main thread because closing a TLS connection can perform network I/O. A future authenticated API must define its own session rules; this anonymous Hello is not an authentication template.

Keep R8 enabled. The Google Java-lite strategy obtains response prototypes through `Internal.getDefaultInstance(Class)`, which reflects the generated static `getDefaultInstance()` method. The app's ProGuard rules preserve that method and protobuf-lite message fields; keeping fields alone builds successfully but breaks response decoding in a minified APK. An explicit local minified-device check can cover this runtime behavior when that behavior changes; CI does not execute it.

`connectedDebugAndroidTest` includes real anonymous requests to the currently deployed Cloud service and requires Internet access. `CloudHelloIntegrationTest` waits for health separately, records the observed Native AOT/Worker revision, then sends eight SDK calls without retry: four successful names, empty and oversized names, expired timeout and malformed timeout. It checks `/api`, binary Content-Type, SDK timeout metadata and decoded gRPC statuses. A separate UI test presses the actual Android button and verifies the result across Activity recreation. Fault/UI-state fixtures remain separate evidence from those live calls.

These commands and the loopback transport fixture are **local opt-in only**:

```sh
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest
./gradlew :app:connectedDebugAndroidTest
./gradlew :app:installDebug
```

Use an already available device/emulator for an affected behavior once. The existing device smoke, installed identity and public upgrade helpers reject CI. Public-download/upgrade diagnostics require a concrete publication/integrity defect or an explicit request; they are not a routine validation or post-merge step. No screenshots, API 26/36 evidence or successful Cloud availability are publication prerequisites.

## Licence checks

The [licence gate](licence-boundary.md) verifies project declarations and the actual Android dependency closure before packaging. The [provenance gate](provenance.md) also checks the complete source inventory, immutable admissions and actual APK/AAB resources. Resolved binaries, notices, native provenance, strict checksums and policy must agree. Every archive retains the source-bound notice/closure/provenance assets. Changed dependencies or resources require a reviewed policy and superseding profile before candidate acceptance.

## Dependency maintenance

[Dependency admission](dependency-policy.md) requires a reviewed input record before
changed locks or toolchains are accepted.

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

Reuse the existing cache. If a dependency update exposes a specific missing POM/BOM checksum, review that exact upstream artifact and repair its metadata; do not create empty caches or repeat restoration just to expand validation.

## Security tooling compatibility

CodeQL scans Java/Kotlin, Python and Actions. Kotlin 2.4.20 requires the same temporary, date-pinned and checksum-verified CodeQL bundle used by Contracts: `codeql-bundle-20260913`. Stable CLI 2.27.0 misses the Kotlin extraction fix in [github/codeql#22404](https://github.com/github/codeql/pull/22404). Remove the override once the action's recommended stable CLI is at least 2.27.1 and includes that fix. The scanner override does not change the app's stable compiler or runtime dependencies.

## Evidence boundaries

Unit tests establish shared behavior and generated API interoperability with local fixtures. Emulator tests establish Android UI/lifecycle, real HTTPS calls to the recorded deployment and the minified release client's operation on that image. Hot Reload requires a running preview and an observed edit/reload. Physical devices, accounts, full product behavior, Play submission and real user operation require separate evidence; none is implied by a green build.

## Reproducible Java selection

CI selects the reviewed Temurin patch from `.java-version`, rather than a moving major-version selector. Keep the existing JVM bytecode target and strict Gradle locks/checksum verification. Local checks record the actual installed JDK; only the matching pinned hosted producer run establishes the candidate toolchain identity. There is no redundant offline-resolution pass after a successful build. Missing required cache/dependency inputs are reported, without toolchain reinstalls or network workarounds.
