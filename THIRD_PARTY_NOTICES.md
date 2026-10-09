# Third-party notices

The [source and artifact provenance process](docs/provenance.md) records exact
sources, target hashes and responsibility. Every archive embeds
`source-provenance.json`; releases retain archive-member and signing-preservation
receipts. The current coroutines NOTICE is retained separately from the older
AndroidX concurrent NOTICE. Unused MPL suffix data and JUnit images are excluded
under the accepted Design remediation.

Original ArcForges Mobile code and tooling use Apache-2.0. The Gradle wrapper is distributed under Apache-2.0 and comes from the same verified Gradle 9.7.1 wrapper used by ArcForges Contracts; its distribution checksum is pinned in the wrapper properties.

The application consumes published artifacts, including ArcForges Contracts, Kotlin, AndroidX/Compose, Protocol Buffers, Connect-Kotlin, OkHttp/Okio and their transitive dependencies. Each dependency retains its own license and notices. Gradle lockfiles and checksum metadata enumerate the resolved artifacts. Runtime license/notice resources are retained or merged during Android packaging, including the notices in Contracts JARs.

Contracts JARs each contain their own root `sbom.cdx.json` and `source.json`. These per-artifact documents stay available in the original Maven artifacts and are excluded from APK resources: concatenating them at the same path would produce invalid JSON. They are not license notices. The application release manifest records the application source and hashes separately.

The JVM development preview additionally uses Compose Desktop, Skiko and a JetBrains Runtime. Those preview dependencies are not packaged as a desktop product or included solely for the preview in the Android release. Build, test and security tools retain their upstream licenses.

The reviewed Android inventory is [android-licences.json](eng/policy/android-licences.json); complete retained texts are in [third-party/notices](third-party/notices). APKs/AABs embed `assets/THIRD_PARTY_NOTICES.txt` and `assets/licence-closure.json` (under `base` in the AAB). Signed releases also publish both files separately with verified hashes. The inventory includes instrumentation-only licences with their explicit scope. AndroidX Graphics Path's native source/compiler attributions are retained as described in the [licence gate](docs/licence-boundary.md).

When adding or replacing a dependency, review its license and required redistribution notices, then update the frozen graph/hashes/texts before packaging. The GPL-family core-library desugaring implementation is excluded under D-004; normal D8/R8 language desugaring remains enabled. This file is a provenance guide, not a replacement for the actual notices supplied with an artifact.

## MAUI Android app (AND.40)

<!-- maui-notices:begin -->
The MAUI Android app (AND.40) is redistributed under the NuGet closure in
[eng/policy/nuget-admission.json](eng/policy/nuget-admission.json). Its licence texts are retained in
[third-party/notices](third-party/notices) and listed here by digest. The machine-checked data is
[eng/policy/maui-notices.json](eng/policy/maui-notices.json). The resolved closure with sources is in
`artifacts/evidence/maui-closure.json`, written by `python -I eng/maui_notices.py closure`.

### Packages whose nupkg carries no licence file

| Package | Licence | Retained notice (SHA-256) |
| --- | --- | --- |
| Google.Protobuf 3.36.1 | BSD-3-Clause | `6e5e117324afd944` |
| Grpc.Core.Api 2.84.0 | Apache-2.0 | `cfc7749b96f63bd3` |
| Grpc.Net.Client 2.84.0 | Apache-2.0 | `cfc7749b96f63bd3` |
| Grpc.Net.Client.Web 2.84.0 | Apache-2.0 | `cfc7749b96f63bd3` |
| Grpc.Net.Common 2.84.0 | Apache-2.0 | `cfc7749b96f63bd3` |
| Xamarin.Android.Glide 4.16.0.14 | MIT AND BSD-2-Clause AND Apache-2.0 | `6aa4d810bff33bd6`, `679ccd0507abc677`, `4c1e46c8e72eb32b` |
| Xamarin.Android.Glide.Annotations 4.16.0.14 | MIT AND BSD-2-Clause AND Apache-2.0 | `6aa4d810bff33bd6`, `679ccd0507abc677`, `4c1e46c8e72eb32b` |
| Xamarin.Android.Glide.DiskLruCache 4.16.0.14 | MIT AND BSD-2-Clause AND Apache-2.0 | `6aa4d810bff33bd6`, `679ccd0507abc677`, `4c1e46c8e72eb32b` |
| Xamarin.Android.Glide.GifDecoder 4.16.0.14 | MIT AND BSD-2-Clause AND Apache-2.0 | `6aa4d810bff33bd6`, `679ccd0507abc677`, `4c1e46c8e72eb32b` |

### Workload packs admitted for the Android build

| Pack | Version | Retained notices |
| --- | --- | --- |
| Microsoft.Android.Sdk.Windows | 36.1.69 | `cfc21f5e8bd655ae` |
| Microsoft.Maui.Sdk | 10.0.20 | `cfc21f5e8bd655ae`, `c0a274fea4b590fb` |

### Open notice obligations

- THIRD-PARTY-NOTICES.TXT of Microsoft.Android.Sdk.Windows 36.1.69, Microsoft.NETCore.App.Runtime.Mono.android-arm64 10.0.12 and the AOT Cross 10.0.12 packs contain BSD-2-Clause text. Their licence families need a compound SPDX expression that the Contracts-ported provenance table does not admit, so they are not yet carried. The provenance checker was not changed in unit 4.
- Pending (AND.40 unit 5): Microsoft.Android.Sdk.Linux and the linux-x64 and linux-arm64 Cross pack aliases (hosted Linux run). Licence statements of Microsoft.NET.Runtime.MonoAOTCompiler.Task and Microsoft.NET.Runtime.MonoTargets.Sdk (THIRD-PARTY-NOTICES.TXT only; no LICENSE.TXT).
<!-- maui-notices:end -->
