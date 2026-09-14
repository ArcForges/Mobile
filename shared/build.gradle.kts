// SPDX-License-Identifier: Apache-2.0
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.android.kmp)
    alias(libs.plugins.compose)
    alias(libs.plugins.compose.compiler)
    alias(libs.plugins.hot.reload)
}

val previewPlatform =
    providers
        .gradleProperty("previewPlatform")
        .orElse(
            if (System.getProperty("os.name").startsWith("Windows")) "windows-x64" else "linux-x64"
        )
        .get()

require(previewPlatform in setOf("windows-x64", "linux-x64")) { "Unsupported preview platform" }

// Hot Reload also adds host-specific dev-tool artifacts. Keep cross-host lock generation
// consistent with the selected preview platform, including those plugin-owned graphs.
configurations.configureEach {
    resolutionStrategy.eachDependency {
        val module =
            when {
                requested.group == "org.jetbrains.compose.desktop" &&
                    requested.name.startsWith("desktop-jvm-") -> "desktop-jvm-$previewPlatform"
                requested.group == "org.jetbrains.skiko" &&
                    requested.name.startsWith("skiko-awt-runtime-") ->
                    "skiko-awt-runtime-$previewPlatform"
                else -> null
            }
        if (module != null && module != requested.name) {
            useTarget("${requested.group}:$module:${requested.version}")
        }
    }
}

dependencyLocking {
    lockFile.set(
        rootProject.layout.projectDirectory.file("gradle/locks/shared-$previewPlatform.lockfile")
    )
}

kotlin {
    jvmToolchain(21)
    android {
        namespace = "io.github.arcforges.mobile.shared"
        compileSdk = 37
        minSdk = 26
        withHostTest {}
        compilerOptions { jvmTarget.set(JvmTarget.JVM_21) }
    }
    jvm("desktop") {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_21) }
    }
    sourceSets {
        commonMain.dependencies {
            implementation(libs.compose.runtime)
            implementation(libs.compose.foundation)
            implementation(libs.compose.ui)
            implementation(libs.material3)
        }
        commonTest.dependencies { implementation(kotlin("test")) }
        getByName("desktopMain") {
            dependencies {
                implementation(
                    "org.jetbrains.compose.desktop:desktop-jvm-$previewPlatform:${libs.versions.compose.get()}"
                )
            }
        }
    }
}

// Development sandbox only. There are no desktop distribution tasks configured.
compose.desktop { application { mainClass = "io.github.arcforges.mobile.preview.MainKt" } }
