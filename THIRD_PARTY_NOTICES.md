# Third-party notices

Original ArcForges Mobile code and tooling use Apache-2.0. The Gradle wrapper is distributed under Apache-2.0 and comes from the same verified Gradle 9.7.1 wrapper used by ArcForges Contracts; its distribution checksum is pinned in the wrapper properties.

The application consumes published artifacts, including ArcForges Contracts, Kotlin, AndroidX/Compose, Protocol Buffers, Connect-Kotlin, OkHttp/Okio and their transitive dependencies. Each dependency retains its own license and notices. Gradle lockfiles and checksum metadata enumerate the resolved artifacts. Runtime license/notice resources are retained or merged during Android packaging, including the notices in Contracts JARs.

Contracts JARs each contain their own root `sbom.cdx.json` and `source.json`. These per-artifact documents stay available in the original Maven artifacts and are excluded from APK resources: concatenating them at the same path would produce invalid JSON. They are not license notices. The application release manifest records the application source and hashes separately.

The JVM development preview additionally uses Compose Desktop, Skiko and a JetBrains Runtime. Those preview dependencies are not packaged as a desktop product or included solely for the preview in the Android release. Build, test and security tools retain their upstream licenses.

The reviewed Android inventory is [android-licences.json](eng/policy/android-licences.json); complete retained texts are in [third-party/notices](third-party/notices). APKs/AABs embed `assets/THIRD_PARTY_NOTICES.txt` and `assets/licence-closure.json` (under `base` in the AAB). Signed releases also publish both files separately with verified hashes. The inventory includes instrumentation-only licences with their explicit scope. AndroidX Graphics Path's native source/compiler attributions are retained as described in the [licence gate](docs/licence-boundary.md).

When adding or replacing a dependency, review its license and required redistribution notices, then update the frozen graph/hashes/texts before packaging. The GPL-family core-library desugaring implementation is excluded under D-004; normal D8/R8 language desugaring remains enabled. This file is a provenance guide, not a replacement for the actual notices supplied with an artifact.
