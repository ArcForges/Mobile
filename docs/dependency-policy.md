# Dependency admission (WP02.05)

Dependencies are NuGet packages. Every project restores with `--locked-mode` against
its committed `packages.lock.json`, into a clean `NUGET_PACKAGES` folder, so that no
package is taken from a machine-wide cache (AND.40 decision 17). `python eng/mobile.py
check` runs the offline repository gates, and the MAUI identity and closure gates
(`eng/maui_identity.py`, `eng/maui_notices.py`) check the shipped closure.

Dependabot opens NuGet update pull requests weekly on Mondays for the directories listed
in `.github/dependabot.yml`. A NuGet update is not merged until it has:

- an admission record: a JSON review appended under `eng/policy/dependency-reviews`
  and named in the policy's ordered `reviews`, naming the package, exact version,
  source commit, input hashes and the licence and source evidence;
- a locked restore into a clean `NUGET_PACKAGES` folder, with the closure listing and
  notices regenerated and checked; and
- a human review. Auto-merge is not enabled for any NuGet update.

Dependabot never regenerates a lock file or admission by itself. A failed build is
not a reason to regenerate an admission: review the new closure, licence evidence and
affected notices first.

Gradle, Kotlin and Maven admissions from before AND.40 PR B stay in the policy as
immutable history. Their Kotlin app, KMP module and Gradle build are retired.

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

The `spotless-8-10-3` review admits the formatter plugin patch and its build-only
closure after required release lint detected the new version. Explicit ktfmt 0.64,
Android locks and redistributed dependencies are unchanged. Superseding resource
profile r9 preserves all archive expectations and binds the updated catalog and
checksum metadata; Windows/Linux CI remains required.
