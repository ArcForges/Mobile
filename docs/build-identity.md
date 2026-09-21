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

All four APK/AAB archives carry identical report bytes. Candidate sealing,
protected persistent signing and anonymous public verification retain and check
the same companion. API 26/36 device checks read the installed minified APK's
native diagnostic view before the single real Cloud greeting. Public upgrade
checks repeat this after installing the actual publicly downloaded signed APK.
The report contains no credentials, machine paths or developer identity.

Apache Contracts resolver reuse is admitted by `contracts-build-identity-r1`.
Resource profile r5 retains all r4 resource/dependency expectations, adding only
the reviewed metadata producer and independently verified identity asset rule.
Old admissions remain immutable. Dependency versions, signing identity and
public release ordering are unchanged; this does not claim store deployment.

The standalone Security workflow also runs on pull requests. Its scheduled main
analyses have distinct GitHub CodeQL configuration identities from the reusable
CI invocation; PRs must cover both existing sets for a complete comparison.
The reusable CI security dependency still gates publication. Both compilation
entry points allocate the actual CI version before generating Android metadata.
See [GitHub's analysis-category documentation](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options).
