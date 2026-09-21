# Android Cloud Hello integration

Historical implementation/evidence record. Former hosted device/live/public-download requirements below are superseded by Design P2-017 and the current development/releasing policy; they are not commands to repeat.

## Scope and collected gaps

Base: Mobile `65e9547a209839b6cb6c8983eb8b6ffd22423554`. The deployed Cloud health endpoint reports Native AOT at `6554400c04817491fe68d5e6319434034c5dc356`. Contracts CI published Maven release `1.0.0-ci.36.1`, including `contracts-connect-client`.

The review covered the application entry point, shared UI/preview, transport, Android manifest, R8 rules, unit/device checks, dependency verification and candidate publication before implementation:

1. Android renders a local protobuf round trip. Its unused native gRPC adapter cannot call the current Worker gRPC-Web ingress.
2. Contracts is pinned to `1.0.0-ci.25.1`; neither the Connect client nor its Android HTTP/serialization adapters are present.
3. The synchronous UI has no request progress, recoverable errors, cancellation or pending-request recreation policy. Its offline label would misrepresent a connected screen.
4. Existing tests verify local messages/in-process native gRPC and offline rendering. Neither Android TLS/networking nor the R8-minified client's actual Cloud call is a release gate.

The installed JDK 21, SDK 37/Build-Tools 37 and API 36 emulator are sufficient. Keep Java/Kotlin bytecode at 21. No new Cloudflare credential, domain, product API, account flow or signing identity is needed.

## Unified implementation

1. Consume the exact published Connect client `1.0.0-ci.36.1`, Connect-Kotlin OkHttp and Google Java-lite adapters `0.9.0`. Remove the obsolete native gRPC adapter/dependencies from this app. Update strict locks/checksums and dependency automation; do not modify Contracts or Cloud.
2. Android owns a reusable transport per Activity. Use binary `NetworkProtocol.GRPC_WEB`, normal platform TLS validation and the fixed `https://arcforges.com/api` base. The SDK adds the method path once. Use a five-second RPC deadline, bounded HTTP calls, no automatic retry/redirect, no embedded credential and no offline success fallback. Close the transport when its owner is destroyed.
3. Make the shared screen accept a suspending greeting operation. Only an explicit button press sends a request. Disable duplicate submission while pending, preserve name and completed result through recreation, and cancel pending work when the composition is disposed. A recreated screen allows a fresh manual request; it never resumes/replays a canceled request. Preserve text verbatim and validate the Hello name's 1..256 UTF-16-unit limit. Show useful bounded error messages and allow manual retry. Keep the JVM Hot Reload preview explicitly local and offline.
4. Replace native in-process unit tests with gRPC-Web success/status/deadline/cancellation checks against a local HTTP fixture using the published messages and client. Add device UI checks for progress, failure/retry and disposal, alongside real online success/recreation and input validation. A separate Android integration test checks actual HTTPS path, media type, deadline, success/Unicode and gRPC application errors against Cloud, recording the observed deployment identity.
5. Extend the device smoke to press the real button in the R8 release APK and require the actual Cloud greeting. CI must pass this and Android instrumentation before protected signing/publication of the same candidate. Preserve protocol/device evidence. Update usage and validation documentation without claiming physical-device, account, Play Store or complete product acceptance.

## Execution and closure

Implement dependencies/transport, then shared UI/lifecycle, tests/device tooling, CI and documentation. Validate strict dependency restoration, formatting, unit tests, lint, JVM 21 output, debug and minified APK/AAB builds. Run the installed API 36 emulator locally, then both OS builds and the mandatory CI device gate. Review the final diff and open a PR from the isolated worktree. Fix concrete validation failures only within this scope; do not expand into product API design.

No merge or main release is claimed by a PR check. Current Cloud calls are real anonymous Hello requests. Local HTTP fixtures, emulator operation, physical devices and publication remain distinct evidence categories.

## Local validation record (2026-09-16)

- JDK 21, SDK/Build-Tools 37 and an isolated read-only API 36 x86_64 emulator were used. Application/shared class files target JVM 21. Strict restoration with an empty Gradle cache passed; both preview-platform lock graphs were refreshed without weakening checksum verification.
- Formatting, repository checks, actionlint, strict release lint, four transport unit tests, both shared JVM/Android host test suites and three existing release guard tests passed. Debug APK/test APK, R8 release APK and release AAB built successfully.
- All five Android instrumentation tests passed. Eight real SDK RPCs verified binary media types, the single `/api` prefix, deadline metadata, Unicode/whitespace/boundary input, and gRPC statuses `INVALID_ARGUMENT`, `RESOURCE_EXHAUSTED` and `DEADLINE_EXCEEDED`. Observed Cloud Worker/Native AOT revision: `6554400c04817491fe68d5e6319434034c5dc356`; Contracts: `1.0.0-ci.36.1`.
- The actual Android screen called Cloud and retained the response across recreation. Controlled UI failures covered progress, duplicate submission, manual retry and cancellation without replay. A separately installed, minified release APK made one button-triggered live call and displayed `Hello, World!`.
- Validation exposed two concrete runtime defects, both fixed and retested: TLS socket cleanup on Activity destruction needed a background thread, and R8 removed the generated `getDefaultInstance()` used reflectively by the SDK's deserializer. StrictMode, code shrinking and real online release checks remain enabled.
- Local logs, protocol JSON, UI hierarchy and screenshot are under ignored `artifacts/`; CI preserves corresponding evidence as workflow artifacts. A disposable local key signed the test release APK. This is emulator evidence, not a physical-device test, new main publication, Play submission or full product acceptance. The PR must still pass both OS builds and its CI device gate before merge.
- The first PR CI run passed both OS builds, security scans and all eight direct Android SDK calls, but its UI success wait timed out without recording the screen's error state. The UI test now scrolls the button into view and reports the actual semantics tree on failure; CI saves logcat/protocol evidence before enforcing success. All five tests also passed locally at CI's 320x640/dpi160 dimensions with animations disabled. The first timeout was not reproduced locally; this does not establish a network or server defect, and neither application deadlines nor retry policy was relaxed.

## References

- [Contracts Kotlin client consumption](https://github.com/ArcForges/Contracts/blob/main/docs/consuming.md)
- [Connect-Kotlin client setup](https://connectrpc.com/docs/kotlin/getting-started/)
- [Connect-Kotlin errors](https://connectrpc.com/docs/kotlin/errors/)
- [Compose effects and coroutine lifecycle](https://developer.android.com/develop/ui/compose/side-effects)
