# Reuse and Android resource provenance (WP00.03)

The [accepted Design profile](https://github.com/ArcForges/ArcForges-Design/blob/f7966d9953a4c5dc9b59b321fdae4940bb7babb8/docs/assurance/reference-coverage-and-provenance.md#31-current-repository-implementation-profile)
governs this Apache owner. The retired initialization repository is not an input.
The inventory covers tracked files and nonignored additions. Original Kotlin
UI/transport/tests, the authored launcher vector, configuration and release tooling
were reviewed as first-party work. Wrappers, legal texts and the Apache Contracts
checker port have individual bindings. Builds import no sibling source checkout.

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

## Actual Android resources

The immutable profile independently covers release APK/AAB, debug APK and test APK.
It binds the exact 122 resolved JAR/AAR inputs, source resource paths, copied bytes,
compiled resource expectations, service rewriting and notices. Source/input checks
run before compilation and packaging. The separate 195-component dependency gate
verifies library licences, strict checksums, four native ABI payloads and notices.
JUnit remains an instrumentation-only EPL-1.0 dependency with full terms and exact
source availability; this does not authorize porting EPL code into authored files.

The [resolved conflict](../eng/provenance/conflicts/okhttp-public-suffix-data.json)
removes unused MPL suffix data, source-only annotation resources and legacy JUnit
runner images. Every archive rejects their names and renamed copies by hash.
`CookieJar.NO_COOKIES` is explicit and tested against unsolicited `Set-Cookie`.
Native bearer sessions and system-browser authentication retain their Design rules.
A future cookie/suffix feature requires a compatible audited input before use;
there is no empty replacement database.

Fixed resources match upstream/package bytes. The compiled-resource oracle was
established before the replacement candidate with independent Windows builds and
the actual Linux ci.9.1 candidate; fresh debug compilation reproduced all 41 members.
APK resources use exact hashes. AAB tables preserve every semantic byte and the
complete normalized source-path list; only transform cache identities and generated
source-root indices vary across hosts. Actual APK/AAB manifests are decoded by
AAPT2; only the validated candidate version is substituted. R8 service entries are
derived from original provider names and the actual mapping. The one known
coroutines service-interface merge is bound to the sole Android implementation,
independently observed in ci.9.1; unknown missing types fail. AGP's explicit
`NO_VALID_GIT_FOUND` metadata is accepted only in a local Git worktree, where the
independent Git receipt binds the actual clean commit; CI requires AGP's exact
revision as well. No verifier learns or
refreshes an admission profile from its candidate.

Every archive embeds `source-provenance.json` with the source commit, active record
digests and profile identity. `resource-provenance.json` records each actual archive
member, hash, classification and matched record. Full legal terms and source
attribution remain in `THIRD_PARTY_NOTICES.txt`. Both CI host builds verify actual
archives. Device/signing jobs recheck the candidate against the checked-out profile.
Signing proves all candidate payload members remain unchanged and writes
`signed-resource-provenance.json`. These gates supplement API 26/36 live Cloud,
minified-release, persistent-signature and actual publication checks.

For changed input, resource, recipe, licence or notice scope, inspect the proposed
sources and outputs, establish an independent oracle, and admit a new profile and
superseding record before accepting its candidate. Preserve prior profiles, records
and immutable release identities. Source/fixture passes alone do not close F-023.
