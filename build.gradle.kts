// SPDX-License-Identifier: Apache-2.0
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.kmp) apply false
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.compose.compiler) apply false
    alias(libs.plugins.compose) apply false
    alias(libs.plugins.hot.reload) apply false
    alias(libs.plugins.spotless)
}

spotless {
    kotlin {
        target("app/src/**/*.kt", "shared/src/**/*.kt")
        ktfmt("0.64").kotlinlangStyle()
    }
    kotlinGradle {
        target("*.gradle.kts", "app/*.gradle.kts", "shared/*.gradle.kts")
        ktfmt("0.64").kotlinlangStyle()
    }
}

allprojects {
    dependencyLocking {
        lockAllConfigurations()
        lockMode.set(LockMode.STRICT)
    }

    tasks.register("resolveDependencies") {
        group = "verification"
        description = "Resolve the dependency graphs before reviewing lock and checksum updates."
        notCompatibleWithConfigurationCache(
            "Explicit dependency maintenance accesses configuration models"
        )
        doLast {
            configurations
                .filter { it.isCanBeResolved }
                .forEach { configuration ->
                    // Android project variants expose several artifact types. Resolve external
                    // artifacts here; normal Android build tasks select the project artifacts.
                    configuration.incoming
                        .artifactView {
                            componentFilter {
                                it is org.gradle.api.artifacts.component.ModuleComponentIdentifier
                            }
                        }
                        .files
                        .files
                }
        }
    }
}
