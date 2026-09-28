// SPDX-License-Identifier: Apache-2.0
import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import java.net.HttpURLConnection
import java.net.URI
import java.nio.charset.Charset
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.security.MessageDigest
import java.util.Locale
import java.util.zip.ZipFile
import org.gradle.api.GradleException
import org.gradle.api.Project
import org.gradle.api.artifacts.ProjectDependency
import org.gradle.api.artifacts.component.ModuleComponentIdentifier

private fun gov12Require(condition: Boolean, message: String) {
    if (!condition) throw GradleException(message)
}

private fun gov12Object(file: File): Map<*, *> =
    JsonSlurper().parse(file) as? Map<*, *>
        ?: throw GradleException("Expected JSON object: ${file.name}")

private fun gov12String(value: Map<*, *>, key: String): String =
    value[key] as? String ?: throw GradleException("Missing string field: $key")

private fun gov12Sha256(bytes: ByteArray): String =
    MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

private fun gov12Sha256(file: File): String = gov12Sha256(file.readBytes())

private fun gov12AssetRows(file: File): List<Map<*, *>> {
    val pins = gov12Object(file)
    gov12Require(pins["schemaVersion"] == 1, "Unsupported GOV.12 asset-pin schema")
    val rows = pins["assets"] as? List<*> ?: throw GradleException("Missing policy asset pins")
    return rows.map { it as? Map<*, *> ?: throw GradleException("Invalid policy asset pin") }
}

private fun gov12ArchiveMembersMatch(
    candidateMembers: Map<String, String>,
    downloadedMembers: Map<String, String>,
    repositorySigned: Boolean,
): Boolean {
    if (candidateMembers.containsKey(".signature.p7s")) return false
    val payloadMembers = downloadedMembers.toMutableMap()
    val signatureDigest = payloadMembers.remove(".signature.p7s")
    return (signatureDigest != null) == repositorySigned && payloadMembers == candidateMembers
}

private fun gov12PackageMemberHashes(file: File): Map<String, String> {
    val hashes = linkedMapOf<String, String>()
    ZipFile(file).use { archive ->
        val entries = archive.entries()
        while (entries.hasMoreElements()) {
            val entry = entries.nextElement()
            gov12Require(
                !entry.isDirectory,
                "Unexpected directory entry in policy package: ${entry.name}",
            )
            gov12Require(
                !entry.name.startsWith("/") &&
                    !entry.name.contains('\\') &&
                    entry.name.split('/').all { it.isNotEmpty() && it != "." && it != ".." },
                "Unsafe ZIP member path in policy package: ${entry.name}",
            )
            gov12Require(
                !hashes.containsKey(entry.name),
                "Duplicate ZIP member in policy package: ${entry.name}",
            )
            val bytes = archive.getInputStream(entry).use { it.readBytes() }
            hashes[entry.name] = gov12Sha256(bytes)
        }
    }
    return hashes
}

private fun gov12ValidatePin(pin: Map<*, *>) {
    val id = gov12String(pin, "id")
    val repository = gov12String(pin, "repository")
    val packageId = gov12String(pin, "packageId")
    val version = gov12String(pin, "version")
    val sourceCommit = gov12String(pin, "sourceCommit")
    val url = gov12String(pin, "nugetUrl")
    val packageSha = gov12String(pin, "packageSha256")
    val candidate =
        pin["candidate"] as? Map<*, *> ?: throw GradleException("Missing candidate identity: $id")
    val candidateName = gov12String(candidate, "artifactName")
    val candidatePackageSha = gov12String(candidate, "packageSha256")
    val candidateArchiveMembers =
        candidate["archiveMembers"] as? List<*>
            ?: throw GradleException("Missing candidate archive member manifest: $id")
    val members =
        pin["members"] as? List<*> ?: throw GradleException("Missing package members: $id")
    val normalizedId = packageId.lowercase(Locale.ROOT)
    val expectedUrl =
        "https://api.nuget.org/v3-flatcontainer/$normalizedId/${version.lowercase(Locale.ROOT)}/$normalizedId.${version.lowercase(Locale.ROOT)}.nupkg"
    gov12Require(
        url == expectedUrl,
        "Policy asset URL is not the exact NuGet flat-container URL: $id",
    )
    gov12Require(
        repository in setOf("ArcForges/Contracts", "ArcForges/DesktopPlatform"),
        "Unapproved policy asset owner: $id",
    )
    gov12Require(sourceCommit.matches(Regex("[0-9a-f]{40}")), "Invalid producer commit: $id")
    gov12Require(packageSha.matches(Regex("[0-9a-f]{64}")), "Invalid package checksum: $id")
    gov12Require(
        candidatePackageSha.matches(Regex("[0-9a-f]{64}")) && candidatePackageSha != packageSha,
        "Invalid or ambiguous candidate package checksum: $id",
    )
    gov12Require(candidateArchiveMembers.isNotEmpty(), "Empty candidate archive manifest: $id")
    val memberPaths = mutableSetOf<String>()
    val foldedMemberPaths = mutableSetOf<String>()
    candidateArchiveMembers.forEach { row ->
        val member =
            row as? Map<*, *> ?: throw GradleException("Invalid candidate archive member: $id")
        val path = gov12String(member, "path")
        gov12Require(
            !path.startsWith("/") &&
                !path.contains('\\') &&
                path.split('/').all { it.isNotEmpty() && it != "." && it != ".." },
            "Unsafe candidate ZIP member path: $path",
        )
        gov12Require(
            memberPaths.add(path) && foldedMemberPaths.add(path.lowercase(Locale.ROOT)),
            "Duplicate or case-colliding candidate ZIP member: $path",
        )
        gov12Require(
            gov12String(member, "sha256").matches(Regex("[0-9a-f]{64}")),
            "Invalid candidate ZIP member checksum: $path",
        )
    }
    gov12Require(
        ".signature.p7s" !in memberPaths,
        "Unsigned candidate manifest must not contain a NuGet repository signature: $id",
    )
    gov12Require(
        gov12String(candidate, "artifactDigest").matches(Regex("sha256:[0-9a-f]{64}")),
        "Invalid CI artifact digest: $id",
    )
    gov12Require(
        gov12String(candidate, "artifactId").matches(Regex("[0-9]+")),
        "Invalid CI artifact ID: $id",
    )
    gov12Require(candidateName.matches(Regex("[a-z0-9-]+")), "Invalid CI artifact name: $id")
    gov12Require(candidate["runId"] is Number, "Invalid CI run ID: $id")
    if (id == "contracts-naming") {
        val evidence =
            pin["sourceEvidence"] as? Map<*, *>
                ?: throw GradleException("Missing naming-source evidence artifact")
        gov12Require(
            evidence["runId"] == candidate["runId"],
            "Naming-source evidence belongs to another CI run",
        )
        gov12Require(
            gov12String(evidence, "artifactId").matches(Regex("[0-9]+")),
            "Invalid naming-source evidence ID",
        )
        gov12Require(
            gov12String(evidence, "artifactName").matches(Regex("[a-z0-9-]+")),
            "Invalid naming-source evidence name",
        )
        gov12Require(
            gov12String(evidence, "artifactDigest").matches(Regex("sha256:[0-9a-f]{64}")),
            "Invalid naming-source evidence digest",
        )
    } else {
        gov12Require(pin["sourceEvidence"] == null, "Unexpected source evidence artifact: $id")
    }
    gov12Require(members.isNotEmpty(), "Empty policy asset members: $id")
    members.forEach { row ->
        val member = row as? Map<*, *> ?: throw GradleException("Invalid package member: $id")
        val path = gov12String(member, "path")
        val fileName = gov12String(member, "file")
        gov12Require(
            path.startsWith("tools/") && !path.contains(".."),
            "Unsafe package member path: $path",
        )
        gov12Require(
            fileName.matches(Regex("[a-z0-9][a-z0-9.-]*")),
            "Unsafe cached member name: $fileName",
        )
        gov12Require(
            gov12String(member, "sha256").matches(Regex("[0-9a-f]{64}")),
            "Invalid member checksum: $path",
        )
    }
}

private fun gov12Download(url: String, destination: File) {
    var lastFailure: java.io.IOException? = null
    for (attempt in 1..3) {
        val connection = URI.create(url).toURL().openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 30_000
            connection.readTimeout = 60_000
            connection.instanceFollowRedirects = true
            connection.setRequestProperty("Accept", "application/octet-stream")
            val response = connection.responseCode
            if (response in 500..599) throw java.io.IOException("NuGet returned HTTP $response")
            gov12Require(
                response == HttpURLConnection.HTTP_OK,
                "NuGet download failed with HTTP $response",
            )
            val finalUrl = connection.url
            gov12Require(
                finalUrl.protocol == "https" &&
                    (finalUrl.host == "nuget.org" || finalUrl.host.endsWith(".nuget.org")),
                "NuGet redirected outside its HTTPS domain",
            )
            destination.parentFile.mkdirs()
            val partial = File(destination.parentFile, destination.name + ".part")
            connection.inputStream.use { input ->
                partial.outputStream().use { output -> input.copyTo(output) }
            }
            Files.move(
                partial.toPath(),
                destination.toPath(),
                java.nio.file.StandardCopyOption.REPLACE_EXISTING,
            )
            lastFailure = null
            break
        } catch (failure: java.io.IOException) {
            lastFailure = failure
            if (attempt < 3) Thread.sleep(500L * attempt)
        } finally {
            connection.disconnect()
        }
    }
    if (lastFailure != null)
        throw GradleException(
            "Unable to fetch pinned NuGet policy asset after three bounded attempts",
            lastFailure,
        )
}

private fun gov12VerifyAndExtract(pin: Map<*, *>, root: Project, outputRoot: File) {
    gov12ValidatePin(pin)
    val id = gov12String(pin, "id")
    val packageSha = gov12String(pin, "packageSha256")
    val candidate = pin["candidate"] as Map<*, *>
    val candidatePackageSha = gov12String(candidate, "packageSha256")
    val packageFile = File(outputRoot, "$id/package.nupkg")
    val overrideProperty =
        when (id) {
            "contracts-naming" -> "gov12.contractsPackage"
            "build-policy-catalog" -> "gov12.buildPolicyPackage"
            else -> throw GradleException("Unexpected GOV.12 package pin: $id")
        }
    val overridePath = root.providers.gradleProperty(overrideProperty).orNull
    if (overridePath != null) {
        val source = File(overridePath)
        gov12Require(
            source.isFile,
            "Local GOV.12 package override does not exist: $overrideProperty",
        )
        packageFile.parentFile.mkdirs()
        Files.copy(
            source.toPath(),
            packageFile.toPath(),
            java.nio.file.StandardCopyOption.REPLACE_EXISTING,
        )
    } else if (!packageFile.isFile || gov12Sha256(packageFile) != packageSha) {
        gov12Download(gov12String(pin, "nugetUrl"), packageFile)
    }
    val packageDigest = gov12Sha256(packageFile)
    val isCandidatePackage = packageDigest == candidatePackageSha
    val isPublishedPackage = packageDigest == packageSha
    gov12Require(
        isPublishedPackage || (overridePath != null && isCandidatePackage),
        "Package SHA-256 matches neither the producer candidate nor pinned NuGet package: $id",
    )
    val candidateRows = candidate["archiveMembers"] as List<*>
    val candidateMembers = candidateRows.associate { row ->
        val member = row as Map<*, *>
        gov12String(member, "path") to gov12String(member, "sha256")
    }
    val packageMembers = gov12PackageMemberHashes(packageFile)
    gov12Require(
        gov12ArchiveMembersMatch(candidateMembers, packageMembers, isPublishedPackage),
        "NuGet package members differ from the producer candidate or signature state: $id",
    )
    val members = pin["members"] as List<*>
    ZipFile(packageFile).use { archive ->
        members.forEach { row ->
            val member = row as Map<*, *>
            val memberPath = gov12String(member, "path")
            val entry =
                archive.getEntry(memberPath)
                    ?: throw GradleException("Pinned package member is missing: $memberPath")
            val bytes = archive.getInputStream(entry).use { it.readBytes() }
            gov12Require(
                gov12Sha256(bytes) == gov12String(member, "sha256"),
                "Pinned package member SHA-256 mismatch: $memberPath",
            )
            val extracted = File(outputRoot, "$id/${gov12String(member, "file")}")
            extracted.parentFile.mkdirs()
            extracted.writeBytes(bytes)
        }
    }
}

private fun gov12Bytes(data: ByteArray, token: ByteArray, ignoreAsciiCase: Boolean): List<Int> {
    if (token.isEmpty() || data.size < token.size) return emptyList()
    val found = mutableListOf<Int>()
    for (start in 0..(data.size - token.size)) {
        var matches = true
        for (offset in token.indices) {
            val left = data[start + offset].toInt() and 0xff
            val right = token[offset].toInt() and 0xff
            val normalizedLeft = if (ignoreAsciiCase && left in 65..90) left + 32 else left
            val normalizedRight = if (ignoreAsciiCase && right in 65..90) right + 32 else right
            if (normalizedLeft != normalizedRight) {
                matches = false
                break
            }
        }
        if (matches) found += start
    }
    return found
}

private fun gov12AsciiWordByte(value: Int): Boolean =
    value in 48..57 || value in 65..90 || value in 97..122 || value == 95

private fun gov12AdmittedSpans(data: ByteArray, encoding: Charset, unit: Int): List<IntRange> {
    val tokens = listOf("Arc" + "ImageNative", "arc" + "image-abi")
    val littleEndian = encoding.name().equals("UTF-16LE", ignoreCase = true)
    fun codeUnit(offset: Int): Int =
        when {
            offset < 0 || offset + unit > data.size -> -1
            unit == 1 -> data[offset].toInt() and 0xff
            littleEndian -> data[offset].toInt() and 0xff
            else -> data[offset + 1].toInt() and 0xff
        }
    val spans = mutableListOf<IntRange>()
    tokens.forEach { token ->
        val bytes = token.toByteArray(encoding)
        gov12Bytes(data, bytes, ignoreAsciiCase = false).forEach { start ->
            val endExclusive = start + bytes.size
            val before = codeUnit(start - unit)
            val after = codeUnit(endExclusive)
            val beforeWord =
                if (unit == 1) gov12AsciiWordByte(before)
                else
                    before in 0x30..0x39 ||
                        before in 0x41..0x5a ||
                        before in 0x61..0x7a ||
                        before == 0x5f
            val afterWord =
                if (unit == 1) gov12AsciiWordByte(after)
                else
                    after in 0x30..0x39 ||
                        after in 0x41..0x5a ||
                        after in 0x61..0x7a ||
                        after == 0x5f
            if (!beforeWord && !afterWord) spans += start until endExclusive
        }
    }
    return spans
}

private fun gov12NameFindings(data: ByteArray, names: List<String>): List<String> {
    val encodings =
        listOf(
            Triple(StandardCharsets.UTF_8, 1, "utf-8"),
            Triple(Charset.forName("UTF-16LE"), 2, "utf-16-le"),
            Triple(Charset.forName("UTF-16BE"), 2, "utf-16-be"),
        )
    val findings = mutableListOf<String>()
    encodings.forEach { (charset, unit, label) ->
        val admitted = gov12AdmittedSpans(data, charset, unit)
        names.forEach { name ->
            val token = name.toByteArray(charset)
            gov12Bytes(data, token, ignoreAsciiCase = true).forEach { start ->
                val endExclusive = start + token.size
                if (admitted.none { start >= it.first && endExclusive <= it.last + 1 }) {
                    findings += "$name@$label:$start"
                }
            }
        }
    }
    return findings
}

private fun gov12Git(root: File, vararg args: String): ByteArray {
    val process = ProcessBuilder(listOf("git", "-C", root.absolutePath) + args).start()
    val stdout = process.inputStream.readBytes()
    val stderr = process.errorStream.readBytes()
    val exit = process.waitFor()
    gov12Require(
        exit == 0,
        "Git inventory command failed: ${stderr.toString(Charsets.UTF_8).take(300)}",
    )
    return stdout
}

private fun gov12BoundaryCheck(
    boundary: String,
    license: String,
    allowlist: Set<String>,
    configuration: String,
): Boolean =
    boundary == "Apache" &&
        (license in allowlist ||
            (license == "EPL-1.0" && configuration == "debugAndroidTestRuntimeClasspath"))

private fun gov12LayeringCheck(graph: Map<String, Set<String>>): Boolean =
    graph.keys == setOf(":app", ":shared") &&
        graph[":app"] == setOf(":shared") &&
        graph[":shared"].isNullOrEmpty()

private fun gov12CrossProjectDependencies(
    projectPath: String,
    dependencies: Set<String>,
): Set<String> = dependencies.filterTo(mutableSetOf()) { it != projectPath }

private fun gov12PolicyMatches(
    categoryId: String,
    path: String,
    source: String,
    providers: List<String>,
): Boolean {
    val normalizedPath = path.replace('\\', '/').lowercase(Locale.ROOT)
    return when (categoryId) {
        "BAN-REFLECTION" ->
            Regex(
                    """(?i)\b(?:java\.lang\.reflect\.|Class\.forName\s*\(|(?:getDeclared(?:Method|Field|Constructor)|getMethod|getField|getConstructor)\s*\(|[A-Za-z_]\w*\.invoke\s*\()"""
                )
                .containsMatchIn(source)
        "BAN-CODEGEN" ->
            Regex(
                    """(?i)\b(?:MethodHandles\s*\.\s*Lookup\s*\.\s*define(?:Hidden)?Class\s*\(|MethodHandles\s*\.\s*lookup\s*\(\s*\)\s*\.\s*define(?:Hidden)?Class\s*\(|JavaCompiler\b|javax\.tools\.ToolProvider\b|kotlin\.script\.|net\.bytebuddy\.|org\.objectweb\.asm\.|ClassWriter\b|GroovyShell\b|ScriptEngineManager\b)"""
                )
                .containsMatchIn(source)
        "BAN-BLOCKING" -> {
            val typedFutureVariables =
                Regex(
                        """(?im)\b(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*(?:(?:java\.util\.concurrent)\.)?(?:CompletableFuture|Future)\s*<[^>\r\n]+>|\b(?:(?:java\.util\.concurrent)\.)?(?:CompletableFuture|Future)\s*<[^>\r\n]+>\s+([A-Za-z_]\w*)"""
                    )
                    .findAll(source)
                    .mapNotNull { match -> match.groups[1]?.value ?: match.groups[2]?.value }
                    .toSet()
            val inferredFutureVariables =
                Regex(
                        """(?im)\b(?:val|var)\s+([A-Za-z_]\w*)\s*=\s*(?:(?:java\.util\.concurrent)\.)?CompletableFuture\s*\.\s*(?:completedFuture|supplyAsync|runAsync|allOf|anyOf)\s*\("""
                    )
                    .findAll(source)
                    .map { it.groupValues[1] }
                    .toSet()
            val futureVariables = typedFutureVariables + inferredFutureVariables
            val typedLatchVariables =
                Regex(
                        """(?im)\b(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*(?:(?:java\.util\.concurrent)\.)?CountDownLatch\b|\b(?:(?:java\.util\.concurrent)\.)?CountDownLatch\s+([A-Za-z_]\w*)"""
                    )
                    .findAll(source)
                    .mapNotNull { match -> match.groups[1]?.value ?: match.groups[2]?.value }
                    .toSet()
            val inferredLatchVariables =
                Regex(
                        """(?im)\b(?:val|var)\s+([A-Za-z_]\w*)\s*=\s*(?:(?:java\.util\.concurrent)\.)?CountDownLatch\s*\("""
                    )
                    .findAll(source)
                    .map { it.groupValues[1] }
                    .toSet()
            val latchVariables = typedLatchVariables + inferredLatchVariables
            val blockingContext =
                Regex("""(?is)\bsuspend\s+fun\b|\b(?:async|launch)\s*(?:\([^)]*\))?\s*\{""")
                    .containsMatchIn(source) || futureVariables.isNotEmpty()
            val futureWait = futureVariables.any { variable ->
                Regex("""(?is)\b${Regex.escape(variable)}\s*\.\s*(?:get|join)\s*\(""")
                    .containsMatchIn(source)
            }
            val directFutureWait =
                Regex(
                        """(?is)\b(?:(?:java\.util\.concurrent)\.)?CompletableFuture\s*\.\s*(?:completedFuture|supplyAsync|runAsync|allOf|anyOf)\s*\([^;{}]*?\)\s*\.\s*(?:get|join)\s*\("""
                    )
                    .containsMatchIn(source)
            val latchWait = latchVariables.any { variable ->
                Regex("""(?is)\b${Regex.escape(variable)}\s*\.\s*await\s*\(""")
                    .containsMatchIn(source)
            }
            val blockingWait =
                Regex(
                        """(?is)\b(?:runBlocking\s*(?:\([^)]*\))?\s*\{|Thread\s*\.\s*sleep\s*\(|\bblockingGet\s*\()"""
                    )
                    .containsMatchIn(source) || futureWait || directFutureWait || latchWait
            Regex("""(?is)\brunBlocking\s*(?:\([^)]*\))?\s*\{""").containsMatchIn(source) ||
                (blockingContext && blockingWait)
        }
        "BAN-PROVIDER" ->
            !normalizedPath.contains("/adapter/") &&
                !normalizedPath.contains("/adapters/") &&
                providers.any { provider ->
                    val escaped = Regex.escape(provider)
                    Regex(
                            "(?im)(?:\\b$escaped\\b[^\\r\\n]*(?:sdk|client|checkout|payment)\\b|\\b(?:sdk|client|checkout|payment)[^\\r\\n]*\\b$escaped\\b)"
                        )
                        .containsMatchIn(source)
                }
        "BAN-LOGGING" ->
            Regex(
                    "(?is)\\b(?:Log\\.[vdiew]|logger\\.(?:trace|debug|info|warn|error)|System\\.out\\.print(?:ln)?)\\s*\\([^)]*\\b(?:password|token|secret|credential|authorization|message|content)\\b"
                )
                .containsMatchIn(source)
        "BAN-MONEY" ->
            Regex("(?i)(?:money|credit|price|balance|payment|payout)").containsMatchIn(path) &&
                Regex("(?i)\\b(?:Float|Double)\\b|\\b[0-9]+\\.[0-9]+\\b").containsMatchIn(source)
        "BAN-POINTER" ->
            !normalizedPath.contains("/native-adapter/") &&
                Regex(
                        """(?i)\b(?:val|var)\s+[A-Za-z_]\w*\s*:\s*(?:(?:kotlinx\.cinterop\.)?(?:CPointer|COpaquePointer)\s*<|com\.sun\.jna\.Pointer\b)"""
                    )
                    .containsMatchIn(source)
        else ->
            throw GradleException(
                "No Mobile implementation is registered for catalog category $categoryId"
            )
    }
}

val gov12PinFile = rootProject.file("gradle/policy/asset-pins.json")
val gov12CacheRoot = rootProject.layout.buildDirectory.dir("gov12-policy-assets").get().asFile
val gov12Pins = gov12AssetRows(gov12PinFile)

gov12Pins.forEach(::gov12ValidatePin)

gov12Require(
    gov12Pins.map { gov12String(it, "id") }.toSet() ==
        setOf("contracts-naming", "build-policy-catalog"),
    "GOV.12 must pin exactly its two reviewed build-only policy assets",
)

val prepareGov12PolicyAssets =
    rootProject.tasks.register("prepareGov12PolicyAssets") {
        group = "verification"
        description =
            "Fetch or stage the two exact build-only GOV.12 policy packages and verify their pinned bytes."
        inputs.file(gov12PinFile)
        doLast {
            gov12Pins.forEach { gov12VerifyAndExtract(it, rootProject, gov12CacheRoot) }
            logger.lifecycle(
                "Prepared and SHA-256 verified ${gov12Pins.size} pinned GOV.12 policy packages."
            )
        }
    }

rootProject.tasks.named("resolveDependencies") {
    dependsOn(prepareGov12PolicyAssets)
}

val verifyMobilePolicy =
    rootProject.tasks.register("verifyMobilePolicy") {
        group = "verification"
        description =
            "Run Mobile's Gradle-native layering, licence, naming and banned-API parity fixtures."
        dependsOn(rootProject.tasks.named("resolveDependencies"))
        doLast {
            val reportRows = mutableListOf<Map<String, String>>()
            fun record(rule: String, test: String, result: Boolean, detail: String) {
                gov12Require(result, "$rule failed: $test ($detail)")
                reportRows +=
                    mapOf("rule" to rule, "test" to test, "result" to "passed", "detail" to detail)
            }
            fun expect(
                rule: String,
                test: String,
                expectedViolation: Boolean,
                actualViolation: Boolean,
            ) {
                record(
                    rule,
                    test,
                    expectedViolation == actualViolation,
                    if (expectedViolation) "negative fixture was rejected"
                    else "positive fixture was accepted",
                )
            }

            val reviewPolicy = gov12Object(rootProject.file("eng/policy/dependency-policy.json"))
            val reviewNames =
                reviewPolicy["reviews"] as? List<*>
                    ?: throw GradleException("Missing dependency review pointer")
            val reviewName =
                reviewNames.lastOrNull() as? String
                    ?: throw GradleException("Empty dependency review chain")
            val review = gov12Object(rootProject.file("eng/policy/dependency-reviews/$reviewName"))
            gov12Require(
                review["assetPinsSha256"] == gov12Sha256(gov12PinFile),
                "Immutable dependency review does not bind current asset pins",
            )

            val verifiedFiles = mutableMapOf<String, File>()
            gov12Pins.forEach { pin ->
                val id = gov12String(pin, "id")
                val packageFile = File(gov12CacheRoot, "$id/package.nupkg")
                val candidate = pin["candidate"] as Map<*, *>
                val packageDigest = if (packageFile.isFile) gov12Sha256(packageFile) else ""
                val overrideProperty =
                    if (id == "contracts-naming") "gov12.contractsPackage"
                    else "gov12.buildPolicyPackage"
                val localOverride =
                    rootProject.providers.gradleProperty(overrideProperty).orNull != null
                gov12Require(
                    packageFile.isFile &&
                        (packageDigest == gov12String(pin, "packageSha256") ||
                            (localOverride &&
                                packageDigest == gov12String(candidate, "packageSha256"))),
                    "Prepared package is missing or changed: $id",
                )
                val members = pin["members"] as List<*>
                members.forEach { row ->
                    val member = row as Map<*, *>
                    val file = File(gov12CacheRoot, "$id/${gov12String(member, "file")}")
                    gov12Require(
                        file.isFile && gov12Sha256(file) == gov12String(member, "sha256"),
                        "Prepared policy member is missing or changed: ${member["path"]}",
                    )
                    verifiedFiles["$id/${gov12String(member, "file")}"] = file
                }
            }

            val namingPolicyFile =
                verifiedFiles["contracts-naming/product-names.json"]
                    ?: throw GradleException("Canonical naming policy asset was not prepared")
            val categoryFile =
                verifiedFiles["build-policy-catalog/banned-api-categories.json"]
                    ?: throw GradleException("Canonical BAN-* catalog was not prepared")
            val namingPolicy = gov12Object(namingPolicyFile)
            gov12Require(
                namingPolicy["schemaVersion"] == 2 && namingPolicy["license"] == "Apache-2.0",
                "Unsupported canonical naming policy data",
            )
            val forbiddenRows =
                namingPolicy["forbiddenNames"] as? List<*>
                    ?: throw GradleException("Missing canonical forbidden-name data")
            val forbiddenNames = forbiddenRows.map { row ->
                gov12String(
                    row as? Map<*, *> ?: throw GradleException("Invalid forbidden-name row"),
                    "name",
                )
            }
            gov12Require(
                forbiddenNames.size == 6 &&
                    forbiddenNames.distinctBy { it.lowercase(Locale.ROOT) }.size ==
                        forbiddenNames.size,
                "Canonical forbidden-name set is incomplete or ambiguous",
            )
            val providerRows =
                namingPolicy["providers"] as? List<*>
                    ?: throw GradleException("Missing provider role data")
            val providerNames = providerRows.map { row ->
                gov12String(
                    row as? Map<*, *> ?: throw GradleException("Invalid provider row"),
                    "name",
                )
            }

            val categoryPolicy = gov12Object(categoryFile)
            gov12Require(categoryPolicy["schemaVersion"] == 1, "Unsupported BAN-* catalog schema")
            val categoryRows =
                categoryPolicy["categories"] as? List<*>
                    ?: throw GradleException("Missing BAN-* categories")
            val categories = categoryRows.map { row ->
                row as? Map<*, *> ?: throw GradleException("Invalid BAN-* category")
            }
            val categoryIds = categories.map { gov12String(it, "id") }
            val expectedCategoryIds =
                listOf(
                    "BAN-REFLECTION",
                    "BAN-CODEGEN",
                    "BAN-BLOCKING",
                    "BAN-PROVIDER",
                    "BAN-LOGGING",
                    "BAN-MONEY",
                    "BAN-POINTER",
                )
            gov12Require(
                categoryIds == expectedCategoryIds,
                "Canonical BAN-* catalog is incomplete or duplicated",
            )
            categories.forEach {
                gov12Require(
                    gov12String(it, "name").isNotBlank() &&
                        gov12String(it, "description").isNotBlank(),
                    "BAN-* catalog entry has no portable semantic description",
                )
            }

            val repositoryRoot = rootProject.projectDir.toPath().toRealPath()
            val inventoryBefore = gov12Git(rootProject.projectDir, "status", "--porcelain=v1", "-z")
            val inventoryBytes =
                gov12Git(
                    rootProject.projectDir,
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                    "-z",
                )
            val inventoryPaths =
                inventoryBytes
                    .toString(Charsets.UTF_8)
                    .split('\u0000')
                    .filter { it.isNotEmpty() }
                    .sorted()
            gov12Require(inventoryPaths.isNotEmpty(), "Mobile source inventory is empty")
            val namingFindings = mutableListOf<String>()
            val inventoryDigest = MessageDigest.getInstance("SHA-256")
            inventoryPaths.forEach { path ->
                val target = rootProject.file(path).toPath().normalize()
                gov12Require(
                    target.startsWith(repositoryRoot) && !Files.isSymbolicLink(target),
                    "Unsupported source inventory path: $path",
                )
                val realTarget = target.toRealPath()
                gov12Require(
                    realTarget.startsWith(repositoryRoot),
                    "Source inventory path escapes Mobile: $path",
                )
                gov12Require(Files.isRegularFile(target), "Unreadable source inventory file: $path")
                val bytes = Files.readAllBytes(target)
                inventoryDigest.update(path.toByteArray(StandardCharsets.UTF_8))
                inventoryDigest.update(0.toByte())
                inventoryDigest.update(MessageDigest.getInstance("SHA-256").digest(bytes))
                namingFindings +=
                    gov12NameFindings(path.toByteArray(StandardCharsets.UTF_8), forbiddenNames)
                        .map { "$path:path:$it" }
                namingFindings += gov12NameFindings(bytes, forbiddenNames).map { "$path:$it" }
            }
            gov12Require(
                inventoryBefore.contentEquals(
                    gov12Git(rootProject.projectDir, "status", "--porcelain=v1", "-z")
                ),
                "Mobile source inventory changed during policy scan",
            )
            val inventorySha256 = inventoryDigest.digest().joinToString("") { "%02x".format(it) }
            record(
                "WP-05.02",
                "current Git inventory",
                namingFindings.isEmpty(),
                "${inventoryPaths.size} source, identifier, resource and documentation files; ${namingFindings.size} findings; inventory SHA-256 $inventorySha256",
            )
            forbiddenNames.forEach { name ->
                val expected =
                    gov12NameFindings(
                            "fixture $name".toByteArray(StandardCharsets.UTF_8),
                            forbiddenNames,
                        )
                        .isNotEmpty()
                expect("WP-05.02", "canonical-name negative fixture", true, expected)
            }
            val admittedImageToken = "Arc" + "ImageNative"
            expect(
                "WP-05.02",
                "canonical scanner compatibility exception",
                false,
                gov12NameFindings(
                        admittedImageToken.toByteArray(StandardCharsets.UTF_8),
                        forbiddenNames,
                    )
                    .isNotEmpty(),
            )
            val admittedAbiToken = "arc" + "image-abi"
            expect(
                "WP-05.02",
                "canonical scanner compatibility alias",
                false,
                gov12NameFindings(
                        admittedAbiToken.toByteArray(StandardCharsets.UTF_8),
                        forbiddenNames,
                    )
                    .isNotEmpty(),
            )
            val candidateArchiveFixture =
                mapOf("member-a" to "a".repeat(64), "member-b" to "b".repeat(64))
            val signedArchiveFixture =
                candidateArchiveFixture + (".signature.p7s" to "c".repeat(64))
            expect(
                "WP-05.02",
                "producer candidate archive manifest fixture",
                false,
                !gov12ArchiveMembersMatch(
                    candidateArchiveFixture,
                    candidateArchiveFixture,
                    repositorySigned = false,
                ),
            )
            expect(
                "WP-05.02",
                "NuGet repository signature preserves candidate member manifest fixture",
                false,
                !gov12ArchiveMembersMatch(
                    candidateArchiveFixture,
                    signedArchiveFixture,
                    repositorySigned = true,
                ),
            )
            expect(
                "WP-05.02",
                "unsigned candidate rejects unexpected NuGet signature fixture",
                true,
                !gov12ArchiveMembersMatch(
                    candidateArchiveFixture,
                    signedArchiveFixture,
                    repositorySigned = false,
                ),
            )
            expect(
                "WP-05.02",
                "signed NuGet package rejects missing signature fixture",
                true,
                !gov12ArchiveMembersMatch(
                    candidateArchiveFixture,
                    candidateArchiveFixture,
                    repositorySigned = true,
                ),
            )
            expect(
                "WP-05.02",
                "signed NuGet package rejects extra member fixture",
                true,
                !gov12ArchiveMembersMatch(
                    candidateArchiveFixture,
                    signedArchiveFixture + ("extra" to "d".repeat(64)),
                    repositorySigned = true,
                ),
            )
            expect(
                "WP-05.02",
                "signed NuGet package rejects missing member fixture",
                true,
                !gov12ArchiveMembersMatch(
                    candidateArchiveFixture,
                    signedArchiveFixture - "member-b",
                    repositorySigned = true,
                ),
            )
            expect(
                "WP-05.02",
                "signed NuGet package rejects changed member fixture",
                true,
                !gov12ArchiveMembersMatch(
                    candidateArchiveFixture,
                    signedArchiveFixture + ("member-a" to "e".repeat(64)),
                    repositorySigned = true,
                ),
            )

            fun projectGraphIsAllowed(graph: Map<String, Set<String>>) = gov12LayeringCheck(graph)
            val modulePaths = rootProject.allprojects.map { it.path }.filter { it != ":" }.toSet()
            record(
                "WP-05.00",
                "registered Android project set",
                modulePaths == setOf(":app", ":shared"),
                "registered projects ${modulePaths.sorted()}",
            )
            val directProjectGraph: Map<String, Set<String>> =
                rootProject.allprojects
                    .filter { it.path in setOf(":app", ":shared") }
                    .associate { project ->
                        project.path to
                            gov12CrossProjectDependencies(
                                project.path,
                                project.configurations
                                    .flatMap { configuration ->
                                        configuration.dependencies
                                            .withType<ProjectDependency>()
                                            .map {
                                                it.path
                                            }
                                    }
                                    .toSet(),
                            )
                    }
            record(
                "WP-05.00",
                "actual Gradle project dependency graph",
                projectGraphIsAllowed(directProjectGraph),
                directProjectGraph.toSortedMap().toString(),
            )
            expect(
                "WP-05.00",
                "app-to-shared positive fixture",
                false,
                !projectGraphIsAllowed(mapOf(":app" to setOf(":shared"), ":shared" to emptySet())),
            )
            expect(
                "WP-05.00",
                "reverse project edge negative fixture",
                true,
                !projectGraphIsAllowed(
                    mapOf(":app" to setOf(":shared"), ":shared" to setOf(":app"))
                ),
            )
            expect(
                "WP-05.00",
                "self-project edges omitted from actual graph projection",
                false,
                !projectGraphIsAllowed(
                    mapOf(
                        ":app" to gov12CrossProjectDependencies(":app", setOf(":app", ":shared")),
                        ":shared" to gov12CrossProjectDependencies(":shared", setOf(":shared")),
                    )
                ),
            )
            expect(
                "WP-05.00",
                "missing app-to-shared cross-project edge negative fixture",
                true,
                !projectGraphIsAllowed(mapOf(":app" to emptySet(), ":shared" to emptySet())),
            )

            val boundary = gov12Object(rootProject.file("eng/policy/licence-boundary.json"))
            val dependencyPolicy =
                gov12Object(rootProject.file("eng/policy/dependency-policy.json"))
            val closure = gov12Object(rootProject.file("eng/policy/android-licences.json"))
            val boundaryProjects =
                boundary["projects"] as? List<*>
                    ?: throw GradleException("Missing project boundary roster")
            val expectedBoundaryPaths =
                setOf("build.gradle.kts", "app/build.gradle.kts", "shared/build.gradle.kts")
            gov12Require(
                boundary["spdxLicense"] == "Apache-2.0" &&
                    boundary["licenceBoundary"] == "Apache" &&
                    boundaryProjects.size == expectedBoundaryPaths.size &&
                    boundaryProjects.map { gov12String(it as Map<*, *>, "path") }.toSet() ==
                        expectedBoundaryPaths,
                "Apache project boundary roster differs from its canonical inventory",
            )
            val projectByBuildPath =
                mapOf(
                    "build.gradle.kts" to rootProject,
                    "app/build.gradle.kts" to rootProject.project(":app"),
                    "shared/build.gradle.kts" to rootProject.project(":shared"),
                )
            boundaryProjects.forEach { row ->
                val data = row as Map<*, *>
                val buildPath = gov12String(data, "path")
                gov12Require(
                    data["kind"] == "gradle",
                    "Unexpected project declaration kind: $buildPath",
                )
                val project =
                    projectByBuildPath[buildPath]
                        ?: throw GradleException("Unmapped project declaration: $buildPath")
                val extra = project.extensions.extraProperties
                gov12Require(
                    extra.has("spdxLicense") &&
                        extra.get("spdxLicense") == "Apache-2.0" &&
                        extra.has("licenceBoundary") &&
                        extra.get("licenceBoundary") == "Apache",
                    "Missing Apache declaration: $buildPath",
                )
            }
            record(
                "WP-05.01",
                "project SPDX and boundary declarations",
                true,
                "${boundaryProjects.size} projects declare Apache-2.0 / Apache",
            )

            val allowedLicences =
                (dependencyPolicy["runtimeLicences"] as? List<*>)
                    ?.map { it as? String ?: "" }
                    ?.toSet() ?: throw GradleException("Missing runtime licence allowlist")
            fun allowedLicence(license: String, configuration: String) =
                gov12BoundaryCheck("Apache", license, allowedLicences, configuration)
            expect(
                "WP-05.01",
                "Apache runtime positive fixture",
                false,
                !allowedLicence("Apache-2.0", "releaseRuntimeClasspath"),
            )
            expect(
                "WP-05.01",
                "AGPL dependency negative fixture",
                true,
                !allowedLicence("AGPL-3.0-only", "releaseRuntimeClasspath"),
            )
            expect(
                "WP-05.01",
                "EPL instrumentation-only fixture",
                false,
                !allowedLicence("EPL-1.0", "debugAndroidTestRuntimeClasspath"),
            )
            expect(
                "WP-05.01",
                "EPL release negative fixture",
                true,
                !allowedLicence("EPL-1.0", "releaseRuntimeClasspath"),
            )

            val componentRows =
                closure["components"] as? List<*>
                    ?: throw GradleException("Missing pinned Android component closure")
            val app = rootProject.project(":app")
            val configurations =
                componentRows
                    .flatMap { row ->
                        (row as Map<*, *>)["configurations"] as? List<*>
                            ?: throw GradleException("Missing dependency configuration roster")
                    }
                    .map { it as? String ?: throw GradleException("Invalid Android configuration") }
                    .toSet()
                    .sorted()
            val publicPackages =
                (dependencyPolicy["publicPackages"] as? List<*>)
                    ?.map { it as? String ?: "" }
                    ?.toSet() ?: throw GradleException("Missing first-party package allowlist")
            configurations.forEach { configurationName ->
                val expectedRows =
                    componentRows
                        .map { it as Map<*, *> }
                        .filter { row ->
                            (row["configurations"] as List<*>).contains(configurationName)
                        }
                val expectedIds = expectedRows.map { gov12String(it, "id") }.toSet()
                val configuration =
                    app.configurations.findByName(configurationName)
                        ?: throw GradleException(
                            "Pinned licence configuration is missing: $configurationName"
                        )
                val resolved = configuration.incoming.resolutionResult.allComponents
                val actualIds =
                    resolved
                        .mapNotNull { component ->
                            (component.id as? ModuleComponentIdentifier)?.displayName
                        }
                        .toSet()
                gov12Require(
                    actualIds == expectedIds,
                    "$configurationName differs from the reviewed Android dependency allowlist",
                )
                expectedRows.forEach { row ->
                    val id = gov12String(row, "id")
                    val license = gov12String(row, "spdxLicense")
                    gov12Require(
                        allowedLicence(license, configurationName),
                        "Disallowed $license dependency $id in $configurationName",
                    )
                    if (id.startsWith("io.github.arcforges:")) {
                        val coordinate = id.split(':').take(2).joinToString(":")
                        gov12Require(
                            coordinate in publicPackages,
                            "Private first-party package entered Android closure: $id",
                        )
                    }
                }
            }
            record(
                "WP-05.01",
                "resolved Android dependency closures",
                true,
                "${configurations.size} Gradle configurations match ${componentRows.size} immutable component/licence rows",
            )

            val actualSourcePaths = inventoryPaths.filter { path ->
                (path.startsWith("app/src/main/") || path.startsWith("shared/src/")) &&
                    (path.endsWith(".kt") || path.endsWith(".java")) &&
                    !path.contains("/test/") &&
                    !path.contains("/androidTest/")
            }
            val sourceFindings = mutableListOf<String>()
            val categoryTestSources =
                mapOf(
                    "BAN-REFLECTION" to "fun unsafe() = Class.forName(\"sample.Type\")",
                    "BAN-CODEGEN" to "val generated = MethodHandles.Lookup.defineClass(bytes)",
                    "BAN-BLOCKING" to
                        """suspend fun unsafe() {
                            val pending: CompletableFuture<Int> = TODO()
                            pending.join()
                        }""",
                    "BAN-PROVIDER" to
                        "import com.${providerNames.first().lowercase(Locale.ROOT)}.sdk.ProviderClient",
                    "BAN-LOGGING" to "fun unsafe(token: String) { Log.d(\"tag\", token) }",
                    "BAN-MONEY" to "val amount: Double = 1.25",
                    "BAN-POINTER" to
                        "class UnsafeHandle { val pointer: kotlinx.cinterop.CPointer<ByteVar> = TODO() }",
                )
            val additionalCategoryNegativeFixtures =
                mapOf(
                    "BAN-CODEGEN" to
                        listOf(
                            "val generated = MethodHandles.lookup().defineClass(bytes)",
                            "val generated = MethodHandles.lookup().defineHiddenClass(bytes, true)",
                        ),
                    "BAN-BLOCKING" to
                        listOf(
                            """suspend fun unsafe() {
                                val pending: java.util.concurrent.CompletableFuture<Int> = TODO()
                                doOtherWork()
                                pending.join()
                            }""",
                            """suspend fun unsafe() {
                                val pending = CompletableFuture.completedFuture(1)
                                doOtherWork()
                                pending.join()
                            }""",
                            "suspend fun unsafe() = CompletableFuture.completedFuture(1).join()",
                            """suspend fun unsafe() = CompletableFuture.completedFuture(
                                1
                            ).join()""",
                            """suspend fun unsafe() {
                                val gate: CountDownLatch = CountDownLatch(1)
                                doOtherWork()
                                gate.await()
                            }""",
                            """suspend fun unsafe() {
                                val gate = CountDownLatch(1)
                                doOtherWork()
                                gate.await()
                            }""",
                            "launch(Dispatchers.IO) { Thread.sleep(1) }",
                            "runBlocking(Dispatchers.IO) { Thread.sleep(1) }",
                        ),
                )
            val additionalCategoryPositiveFixtures =
                mapOf(
                    "BAN-BLOCKING" to
                        listOf(
                            """suspend fun allowed() {
                                val pending: CompletableFuture<Int> = TODO()
                                consumeLater(pending)
                            }""",
                            """suspend fun allowed() {
                                val job: Job = TODO()
                                job.join()
                            }""",
                            """suspend fun allowed() {
                                val gate: CountDownLatch = CountDownLatch(1)
                                event.await()
                            }""",
                            """fun ordinary() {
                                operation.join()
                                event.await()
                            }""",
                            """launch(Dispatchers.IO) {
                                unrelated.await()
                            }""",
                        )
                )
            val categoryFixturePaths =
                mapOf("BAN-MONEY" to "app/src/main/kotlin/payment/Balance.kt")
            categories.forEach { category ->
                val id = gov12String(category, "id")
                val fixture =
                    categoryTestSources[id]
                        ?: throw GradleException("No category fixture was authored for $id")
                val fixturePath = categoryFixturePaths[id] ?: "app/src/main/kotlin/Fixture.kt"
                (listOf(fixture) + additionalCategoryNegativeFixtures[id].orEmpty())
                    .forEachIndexed { index, negativeFixture ->
                        expect(
                            "WP-05.04",
                            "$id negative fixture ${index + 1}",
                            true,
                            gov12PolicyMatches(id, fixturePath, negativeFixture, providerNames),
                        )
                    }
                expect(
                    "WP-05.04",
                    "$id positive fixture",
                    false,
                    gov12PolicyMatches(
                        id,
                        "app/src/main/kotlin/Allowed.kt",
                        "package sample\nclass Allowed { suspend fun run() {} }",
                        providerNames,
                    ),
                )
                additionalCategoryPositiveFixtures[id].orEmpty().forEachIndexed {
                    index,
                    positiveFixture ->
                    expect(
                        "WP-05.04",
                        "$id positive fixture ${index + 2}",
                        false,
                        gov12PolicyMatches(id, fixturePath, positiveFixture, providerNames),
                    )
                }
            }
            gov12Require(
                categoryTestSources.keys == expectedCategoryIds.toSet(),
                "Mobile category fixture roster differs from the exact canonical category IDs",
            )
            actualSourcePaths.forEach { path ->
                val source = rootProject.file(path).readText(Charsets.UTF_8)
                categories.forEach { category ->
                    val id = gov12String(category, "id")
                    if (gov12PolicyMatches(id, path, source, providerNames))
                        sourceFindings += "$id:$path"
                }
            }
            record(
                "WP-05.04",
                "current production source",
                sourceFindings.isEmpty(),
                "${actualSourcePaths.size} Kotlin/Java production files; ${sourceFindings.size} findings; catalog IDs ${categoryIds.joinToString()}",
            )
            val nativeAdapterPositive =
                "class NativeHandle { val pointer: kotlinx.cinterop.CPointer<ByteVar> = TODO() }"
            expect(
                "WP-05.04",
                "native lifetime adapter positive fixture",
                false,
                gov12PolicyMatches(
                    "BAN-POINTER",
                    "shared/src/native-adapter/Handle.kt",
                    nativeAdapterPositive,
                    providerNames,
                ),
            )

            val report =
                mapOf(
                    "schemaVersion" to 1,
                    "repository" to "Mobile",
                    "result" to "passed",
                    "evidenceClass" to "gradle-policy-fixtures-and-resolved-graph",
                    "assetPinSha256" to gov12Sha256(gov12PinFile),
                    "namingPackage" to
                        gov12Pins
                            .first { gov12String(it, "id") == "contracts-naming" }
                            .let {
                                "${gov12String(it, "packageId")}/${gov12String(it, "version")}"
                            },
                    "catalogPackage" to
                        gov12Pins
                            .first { gov12String(it, "id") == "build-policy-catalog" }
                            .let {
                                "${gov12String(it, "packageId")}/${gov12String(it, "version")}"
                            },
                    "sourceInventorySha256" to inventorySha256,
                    "results" to reportRows,
                )
            val reportFile =
                rootProject.layout.buildDirectory
                    .file("reports/gov12-mobile-policy.json")
                    .get()
                    .asFile
            reportFile.parentFile.mkdirs()
            reportFile.writeText(
                JsonOutput.prettyPrint(JsonOutput.toJson(report)) + "\n",
                Charsets.UTF_8,
            )
            logger.lifecycle(
                "Mobile GOV.12 policy report: ${reportFile.relativeTo(rootProject.projectDir)}"
            )
            reportRows.forEach {
                logger.lifecycle("${it["rule"]} | ${it["test"]} | ${it["result"]}")
            }
        }
    }

rootProject.tasks.named("spotlessCheck") {
    dependsOn(verifyMobilePolicy)
}
