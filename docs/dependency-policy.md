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

Gradle, Kotlin and Maven admissions from before AND.40 PR B stay as immutable history:
their files remain under `eng/policy/dependency-reviews` and are listed in the policy's
`retiredReviews`. Their Kotlin app, KMP module, Gradle build and the Python validator
`eng/dependency_policy.py` are retired.

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
its filename to the policy's ordered `reviews`. Retain all previous files unchanged:
a successor review supersedes a retained review and never rewrites it. Record the
reviewed source commit, complete current input hashes (UTF-8/LF), exact catalog
versions, maintenance assessment and each evidence disposition. Do not regenerate an
admission automatically from a failed build. Review the new closure, licence/source
evidence and affected notices first.

What `eng/maui_identity.py` `check_dependency_policy` enforces (re-homed from the
retired `eng/dependency_policy.py`, AND.40 PR B):

- the publisher is exactly the policy's `publisher` (ArcForges/Mobile, `ci.yml`,
  environment `android-release`, ref `refs/heads/main`, event `push`), and the publish
  job of `ci.yml` still carries those conditions;
- every review file is listed exactly once, in `reviews` or `retiredReviews`; a file
  missing from the policy, or a listed file missing from the directory, is refused;
- in a git checkout, no review ever added to history is deleted, and no retained review
  differs from the bytes of its first addition.

The checker does not validate the content of a review: its evidence, input hashes,
maintenance assessment and any Architecture Owner assessment of a framework major
change are human review obligations.

A framework major change requires an Architecture Owner assessment covering
Kotlin/ART/R8, native modules, transport and actual local coverage. Required
Windows/Linux compilation, static/security and packaging remain CI gates. Local
runtime/performance/migration work is affected-scope and existing-environment only;
record missing observations without inventing a pass. No empty cache, device rerun,
SDK installation or public archive download is an automatic upgrade prerequisite.

Negative fixtures in `eng/tests/test_maui_identity.py` exercise a wrong publisher, a publish
job without its environment, a dropped review, a deleted review and a rewritten review,
and show that a successor review is accepted. They establish policy refusal, not runtime,
store or commercial acceptance.

The `spotless-8-10-3` review admits the formatter plugin patch and its build-only
closure after required release lint detected the new version. Explicit ktfmt 0.64,
Android locks and redistributed dependencies are unchanged. Superseding resource
profile r9 preserves all archive expectations and binds the updated catalog and
checksum metadata; Windows/Linux CI remains required.
