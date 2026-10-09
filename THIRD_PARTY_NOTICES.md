# Third-party notices

Original ArcForges Mobile code and repository tooling use Apache-2.0 ([LICENSE](LICENSE)). Dependencies retain their own licences and notices.

The [source and artifact provenance process](docs/provenance.md) records exact sources, target hashes and responsibility for every reused file and artifact. The generated provenance notice is [eng/provenance/NOTICE.txt](eng/provenance/NOTICE.txt).

The Android application is a .NET MAUI application (AND.40). Its NuGet closure is admitted in [eng/policy/nuget-admission.json](eng/policy/nuget-admission.json), and its retained licence texts are in [third-party/notices](third-party/notices). Each MAUI release publishes `THIRD_PARTY_NOTICES.txt` and `licence-closure.json` beside the APK (see the section below). The Kotlin application, the KMP shared module and the Gradle build retired with AND.40 PR B; the notice texts that only they used are removed, and the retirement is recorded under [eng/provenance/records](eng/provenance/records).

Build, test and security tools retain their upstream licences and are not redistributed in the application.

When adding or replacing a dependency, review its licence and required redistribution notices, then update the admission, the retained texts and the notice data before packaging. This file is a provenance guide, not a replacement for the actual notices supplied with an artifact.

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
| Microsoft.NETCore.App.Runtime.Mono.android-arm64 | 10.0.12 | `66f1d4e449731855`, `aeacdb4777e6e3c6`, `de4a44cff385b182` |
| Microsoft.NETCore.App.Runtime.AOT.win-x64.Cross.android-arm64 | 10.0.12 | `66f1d4e449731855` |

### Open notice obligations

- Pending (AND.40 unit 5): Microsoft.Android.Sdk.Linux licence files, and the THIRD-PARTY-NOTICES.TXT of Microsoft.NET.Runtime.MonoAOTCompiler.Task and Microsoft.NET.Runtime.MonoTargets.Sdk (no LICENSE.TXT ships), from the hosted Linux run (linux-evidence). The Cross pack alias of the hosted runner's host architecture (linux-x64 on the hosted x64 runner, Microsoft.NETCore.App.Runtime.AOT.linux-x64.Cross.android-arm64), from the hosted Linux run; required, and it fails closed when absent. The linux-arm64 Cross alias is not applicable, not missing: it is not a build host, and ArcForges builds Android only on hosted x64 runners.
<!-- maui-notices:end -->
