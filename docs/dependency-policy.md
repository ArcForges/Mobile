# Dependency admission (WP02.05)

`python eng/mobile.py check` runs the offline `eng/dependency_policy.py` gate.
The owner policy binds the 195-component Android licence inventory, public Contracts
imports, exact registry and publisher scope, native source records and reviewed
dependency/toolchain inputs. Existing Gradle licence/resource checks still compare
actual resolved artifacts, notices and native bytes before packaging. Policy does
not replace strict Gradle locks/checksums or claim package signatures where only
checksums are verified. Permanent Android artifact signing remains unchanged.

The initial review preserves the current dependency graph. Android runtime licences
come from the existing file-level/POM/notice records; EPL is instrumentation-only.
JVM preview and build-tool graphs are locked inputs, never Android redistribution
evidence. Qualified tooling versions have exact, explicit exceptions. Public
Contracts CI versions are admitted only for this foundation candidate stage;
SNAPSHOT, dynamic selectors and internal Contracts cannot enter this consumer.
No production stable release is admitted by the candidate policy.
The `compose-1-12-1` review admits the Compose 1.12.0 to 1.12.1 patch upgrade with
superseding resource profile r7; no component is added or removed. The `gradle-9-8-0` review
admits the Gradle 9.8.0 wrapper distribution with superseding resource profile r8; the Android
closure is unchanged, and Gradle deprecations are reported rather than fatal (see development.md).

For an upgrade, append a JSON review under `eng/policy/dependency-reviews` and add
its filename to the policy's ordered `reviews`. Retain all previous files unchanged.
Record the reviewed source commit, complete current input hashes (UTF-8/LF), exact
catalog versions, maintenance assessment and each evidence disposition. The check
fails if actual inputs differ, including changed checksums under the same version.
The source commit must contain the admitted Android closure. Every retained
source closure is compared with the current one so a successor review cannot
authorize different bytes for an already admitted immutable coordinate.
Do not regenerate an admission automatically from a failed build. Review the new
closure, licence/source evidence and affected notices first.

A framework major change requires an Architecture Owner assessment covering
Kotlin/ART/R8, native modules, transport and actual local coverage. Required
Windows/Linux compilation, static/security and packaging remain CI gates. Local
runtime/performance/migration work is affected-scope and existing-environment only;
record missing observations without inventing a pass. No empty cache, device rerun,
SDK installation or public archive download is an automatic upgrade prerequisite.

Negative fixtures exercise forbidden licences, floating versions/source tags,
mutable checksums, wrong publisher, private imports and missing upgrade evidence.
They establish policy refusal, not runtime, store or commercial acceptance.
