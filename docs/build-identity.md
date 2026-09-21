# Android build and version identity (WP02.04)

The installed app exposes **Build information** above the greeting. It reads the
packaged `build-identity.json` offline and compares its source commit, build ID,
app version and Android versionCode to compiled BuildConfig constants. Opening
and closing it does not invoke Cloud or reset the greeting. The view shows the
complete commit, run/attempt, UTC source epoch, local/CI and dirty state, every
version axis and the SHA-256 of the actual embedded report. The complete runtime
package inventory is retained in that report and its published companion.

`eng/version-sources.json` declares exactly nine independent sources. AppVersion
comes from the allocated release name; Android versionCode remains a separate
monotonic packaging value. ContractSet comes from the schema namespace and
descriptor digest in the actual checksum-verified published Contracts JAR's
`source.json`. PackageVersion enumerates only `releaseRuntimeClasspath` entries
in `app/gradle.lockfile`, excluding instrumentation/test-only versions. Neither
Maven release numbers nor Android ABI labels are substituted for protocol or
first-party C ABI versions. Unimplemented axes name their future producer;
NativeAbiVersion is not applicable to this owner's first-party boundary.

The generator compares the actual restored Contracts receipt with the immutable
reviewed resource profile. Verification derives expectations from checked-out
source, the trusted GitHub run, committed locks and that reviewed producer
receipt, independently of candidate JSON. Aliases, missing axes, duplicate
subjects, dirty CI, wrong commits and resealed report tampering fail. Local
build IDs include the complete source SHA and explicitly report dirty state.

The release APK/AAB carry identical report bytes. Candidate sealing and protected permanent signing preserve the companion. CI does not install the candidate or download/reinstall public releases. The report contains no credentials, machine paths or developer identity.

Apache Contracts resolver reuse is admitted by `contracts-build-identity-r1`. Resource profile r6 retains r5's independent expectations and all historical debug/test admissions, but only release APK/AAB enter the CI candidate. Its verifier recipe enumerates those two promoted archives. Old admissions remain immutable. Dependency versions, app behavior, signing identity and public version ordering are unchanged.

CodeQL runs once for a PR through the reusable security workflow. Scheduled/manual analysis uses explicit matching categories; obsolete duplicate standalone categories are retired. Both compilation entry points allocate the actual CI version before generating metadata. See [development.md](development.md) for local runtime opt-in and [releasing.md](releasing.md) for the reduced publication boundary.
