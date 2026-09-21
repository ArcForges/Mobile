// SPDX-License-Identifier: Apache-2.0
import groovy.json.JsonOutput
import org.gradle.api.artifacts.ProjectDependency
import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult

gradle.projectsEvaluated {
    val declarations =
        rootProject.allprojects
            .sortedBy { it.path }
            .map { owned ->
                require(
                    owned.projectDir.canonicalFile
                        .toPath()
                        .startsWith(rootDir.canonicalFile.toPath())
                ) {
                    "AFL002: project escapes Mobile: ${owned.path}"
                }
                require(
                    owned.extra.has("spdxLicense") &&
                        owned.extra["spdxLicense"] == "Apache-2.0" &&
                        owned.extra.has("licenceBoundary") &&
                        owned.extra["licenceBoundary"] == "Apache"
                ) {
                    "AFL001: missing or incorrect Apache declaration: ${owned.path}"
                }
                val references =
                    owned.configurations
                        .flatMap { configuration ->
                            configuration.dependencies.withType<ProjectDependency>().map { it.path }
                        }
                        .distinct()
                        .sorted()
                references.forEach { reference ->
                    require(rootProject.project(reference).extra["licenceBoundary"] == "Apache") {
                        "AFL003: Apache project references a non-Apache project: $reference"
                    }
                }
                mapOf(
                    "path" to owned.path,
                    "spdxLicense" to owned.extra["spdxLicense"],
                    "licenceBoundary" to owned.extra["licenceBoundary"],
                    "references" to references,
                )
            }
    val output = rootProject.file("artifacts/evidence/licence-gradle.json")
    output.parentFile.mkdirs()
    output.writeText(JsonOutput.prettyPrint(JsonOutput.toJson(declarations)) + "\n")
}

val verifyAndroidLicences =
    project(":app").tasks.register("verifyAndroidLicences") {
        group = "verification"
        description =
            "Verify the reviewed Android distributable dependency and notice closure before packaging."
        notCompatibleWithConfigurationCache(
            "Resolves the current complete Android dependency model"
        )
        outputs.dir(rootProject.layout.buildDirectory.dir("generated/licence-assets"))
        outputs.upToDateWhen {
            false
        } // Recheck Git state, locks and resolved bytes on every build.
        doLast {
            val app = rootProject.project(":app")
            val configurations =
                listOf(
                    "releaseRuntimeClasspath",
                    "debugRuntimeClasspath",
                    "debugAndroidTestRuntimeClasspath",
                    "coreLibraryDesugaring",
                )
            val closure = configurations.map { name ->
                val configuration = app.configurations.getByName(name)
                val components = configuration.incoming.resolutionResult.allComponents
                val modules =
                    components
                        .filter { it.id is ModuleComponentIdentifier }
                        .map { component ->
                            mapOf(
                                "id" to component.id.displayName,
                                "dependencies" to
                                    component.dependencies
                                        .map { dependency ->
                                            require(dependency is ResolvedDependencyResult) {
                                                "Unresolved dependency: $dependency"
                                            }
                                            dependency.selected.id.displayName
                                        }
                                        .distinct()
                                        .sorted(),
                            )
                        }
                        .sortedBy { it["id"].toString() }
                val artifacts =
                    configuration.incoming
                        .artifactView {
                            componentFilter { it is ModuleComponentIdentifier }
                        }
                        .artifacts
                        .artifacts
                        .map { artifact ->
                            mapOf(
                                "id" to artifact.id.componentIdentifier.displayName,
                                "file" to artifact.file.absolutePath,
                            )
                        }
                        .sortedBy { it["id"] }
                mapOf("configuration" to name, "modules" to modules, "artifacts" to artifacts)
            }
            val output = rootProject.file("artifacts/evidence/android-resolved.json")
            output.parentFile.mkdirs()
            output.writeText(JsonOutput.prettyPrint(JsonOutput.toJson(closure)) + "\n")
            providers
                .exec {
                    workingDir(rootDir)
                    commandLine(
                        "python",
                        "eng/licences.py",
                        "closure",
                        "--resolved",
                        output.absolutePath,
                    )
                }
                .result
                .get()
                .assertNormalExitValue()
            providers
                .exec {
                    workingDir(rootDir)
                    commandLine(
                        "python",
                        "eng/build_identity.py",
                        "--resolved",
                        output.absolutePath,
                        "--version",
                        providers.gradleProperty("releaseVersionName").orElse("0.1.0-local").get(),
                        "--code",
                        providers.gradleProperty("releaseVersionCode").orElse("1").get(),
                    )
                }
                .result
                .get()
                .assertNormalExitValue()
        }
    }

project(":app").tasks.configureEach {
    if (name == "preBuild") dependsOn(verifyAndroidLicences)
}
