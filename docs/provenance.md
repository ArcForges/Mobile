# Reuse and Android resource provenance (WP00.03)

The [accepted Design profile](https://github.com/ArcForges/ArcForges-Design/blob/f7966d9953a4c5dc9b59b321fdae4940bb7babb8/docs/assurance/reference-coverage-and-provenance.md#31-current-repository-implementation-profile)
governs this Apache owner. The retired initialization repository is not an input.
The inventory covers tracked files and nonignored additions. The .NET MAUI sources,
the Hello transport, the host and policy tests, the eng tooling and the release
configuration are first-party work. Legal texts and the Apache Contracts checker and
build-identity ports have individual bindings. Builds import no sibling source checkout.
The Kotlin application's reviewed inputs remain as immutable history (AND.40 PR B).

## Admission and accountability

Use `eng/provenance/template.json`; save each unique revision at
`eng/provenance/records/<lowercase-id>-r<N>.json`. Complete all ten subjects:
source repository, immutable commit, exact paths, file-level licence evidence,
attribution, targets, disposition, independent oracle, NOTICE and lifetime.
Generated records also identify each generator/input, its licence and the command.
Legal documents require their own copying permission and cannot admit incompatible
implementation. The template itself is never an approval.

The Licensing and Provenance Owner reviews the actual material and all ten subjects
before first use, recording reviewer, date, rationale and exact target hashes. A
maintainer-authorized implementation review may exercise this role. Architecture
ownership questions go to the Architecture Owner; product decisions remain with
the Product Owner. Compatible reuse within the table needs no new product decision.

All five decisions are closed data in `eng/policy/reuse-policy.json`. Unknown
expressions and table changes fail. Register conflicts at
`eng/provenance/conflicts/<id>.json` with material, evidence, boundary, owner,
required decision and blocking status. Do not accept affected material while
unresolved. Resolve through an accepted formal decision and an admissible record,
or remove the material. Never silently add exceptions or remove accepted products.

Used records are immutable. Keep retired records; introduce a new revision with
`supersedes` and move the exact active bindings. Temporary material names an owner
and observable removal trigger. Initial records reconcile pre-existing material
against `69155c7c3c2eda592270eeb354677c0537af55ec` without claiming historical
pre-admission. Canonical Apache text identifies a verified template rather than
inventing a download history. The SLF4J attribution correction retains revision 1.

```sh
python eng/check_provenance.py --owner Mobile --write-notice
python eng/mobile.py check
python -m unittest discover -s eng/tests -v
```

Review new files, then update their explicit bindings in `eng/provenance/files.json`.
Do not automatically classify unexplained material as first-party. The deterministic
`eng/provenance/NOTICE.txt` supplements full legal documents. PR/push/merge-group
checks compare records to the event's trusted base; local checks use fetched
`origin/main`, or committed HEAD on main. Missing history fails. CI fetches history.
Review reuse introduced inside an already inventoried authored file as well.

## Android release evidence (MAUI)

Each MAUI release is an APK with `THIRD_PARTY_NOTICES.txt`, `licence-closure.json`,
`mapping.txt`, `build-identity.json` and `maui-archive.json`, plus `release.json` and
`SHA256SUMS`. The NuGet closure is admitted package by package in
`eng/policy/nuget-admission.json`, and `eng/licences.py maui` and `eng/maui_notices.py`
check it against the lock. Each APK is checked by `eng/maui_identity.py`: its identity,
its embedded `build-identity.json`, its 16 KB alignment, the persistent certificate and
the absence of any gnu/binutils member. `maui-archive.json` is derived from the signed
APK and binds its digest and signer. The release gate fails closed while any notice
escalation is open in `eng/policy/maui-notices.json`.

The `build-identity.json` of a build is the CI-derived identity of its nine axes. Its
ContractSet source text is the reviewed Contracts producer source in
`eng/policy/contracts-source.json`, pinned by digest in `eng/build_identity.py`.

## Retired Kotlin resource profile

The Kotlin resource profile (`eng/provenance/artifact-profiles/android-resources-r1`
to `r14`, the records `android-packaged-resources-r1` to `r14`) bound the Kotlin
APK/AAB members and their 122 resolved inputs. It is immutable history. The active
artifact record `android-packaged-resources-r14` retired with the Kotlin baseline in
AND.40 PR B: the inventory lists it under `retired`, which keeps the record and its
profile tracked and unchanged without binding any notice, and only an artifact that was
active in the previous inventory may retire. The verifier for that profile was removed
with the Kotlin app.
