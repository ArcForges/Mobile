# PRF.10 implementation and acceptance

The activity owns one transport. Unary calls and generated stream consumers register their coroutine jobs under the same close fence. Close is idempotent, rejects new calls/openers, cancels owned calls and performs socket cleanup away from the Android caller thread. Redirects, cookies and automatic connection retries remain disabled.

`consumeGeneratedStream` accepts a published generated service opener, sends the typed request once, delivers messages in order and preserves server refusals and metadata. A completed receive channel is insufficient: one exact `grpc-status: 0` trailer is mandatory. Missing/duplicate completion status is refused as data loss; errors already surfaced by Connect retain their code and metadata. Open, consumption, callback and trailer arrival share the configured bounded deadline. Callback failure and caller/activity cancellation close the receive side without replay. No handwritten production service or MethodSpec is introduced.

CI now executes `:app:testDebugUnitTest` on both retained runners instead of only compiling these tests. The immutable `prf10-ci-r1` admission binds that one workflow input change, with every dependency coordinate/hash, Android redistribution closure, signing identity, runner and app prerelease channel preserved.

## Component evidence

The retained local build-slot run used cached JDK21.0.11 and Gradle9.8.0 offline. spotlessApply and :app:testDebugUnitTest passed22/22 tests (9 unary/lifecycle and13 stream cases). Repository text, immutable dependency admission and source provenance checks passed. Hosted pinned JDK21.0.12 CI remains required.

Local tests use the actual pinned Connect-Kotlin/OkHttp/Java-lite transport and generated Hello messages against a loopback HTTP binary gRPC-Web server. The unavailable Cloud stream endpoint alone is replaced by the existing explicitly fixture-only MethodSpec. Tests cover ordered frames, successful/error metadata, permission/session/revision refusals, missing/duplicate/malformed status, deadline, loss without replay, concurrent calls/close, new-call refusal, callback failure and cleanup. These are client component tests, not deployed service or device evidence. The fixture supports real concurrent requests and releases its executor at teardown.

## Deferred acceptance and owners

CON.27 owns the deliberate immutable Maven Events/Execution producer and its publication evidence. PRF.10 will consume the exact published producer through reviewed admission, then bind its actual generated opener. Current foundation dependency remains the previously admitted Hello candidate until that publication; no mutable SNAPSHOT or unpublished artifact is admitted.

CLOUD.19/.21/.22/.29/.32/.34 own actual authenticated API/stream/status/fallback/lifecycle producers. PRF.10 owns their leased opt-in Android/emulator/device integration once available, including scope/permission, stale targets/revisions, session expiry, loss, terminal snapshots and Keystore/lifecycle. Existing production and proof infrastructure, credentials and toolchains were inspected; no absent-account claim is made. Existing AVDs are available, with no currently attached physical device. Whole-series acceptance and real OS/device isolation remain distinct from this implementation delivery. No production route/data change or deployment occurred in this Mobile follow-up.
