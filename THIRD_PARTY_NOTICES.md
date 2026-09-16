# Third-party notices

Original ArcForges Mobile code and tooling use Apache-2.0. The Gradle wrapper is distributed under Apache-2.0 and comes from the same verified Gradle 9.7.1 wrapper used by ArcForges Contracts; its distribution checksum is pinned in the wrapper properties.

The application consumes published artifacts, including ArcForges Contracts, Kotlin, AndroidX/Compose, Protocol Buffers, Connect-Kotlin, OkHttp/Okio and their transitive dependencies. Each dependency retains its own license and notices. Gradle lockfiles and checksum metadata enumerate the resolved artifacts. Runtime license/notice resources are retained or merged during Android packaging, including the notices in Contracts JARs.

Contracts JARs each contain their own root `sbom.cdx.json` and `source.json`. These per-artifact documents stay available in the original Maven artifacts and are excluded from APK resources: concatenating them at the same path would produce invalid JSON. They are not license notices. The application release manifest records the application source and hashes separately.

The JVM development preview additionally uses Compose Desktop, Skiko and a JetBrains Runtime. Those preview dependencies are not packaged as a desktop product or included solely for the preview in the Android release. Build, test and security tools retain their upstream licenses.

When adding or replacing a dependency, review its license and required redistribution notices. This file is a provenance guide, not a replacement for the actual notices supplied with an artifact.
