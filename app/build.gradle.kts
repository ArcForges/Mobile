// SPDX-License-Identifier: Apache-2.0
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.compose.compiler)
}

val releaseCode = providers.gradleProperty("releaseVersionCode").orElse("1").get().toInt()
val releaseName = providers.gradleProperty("releaseVersionName").orElse("0.1.0-local").get()

require(releaseCode in 1..2_100_000_000) { "Invalid Android versionCode" }

require(releaseName.matches(Regex("[0-9]+\\.[0-9]+\\.[0-9]+(?:-[A-Za-z0-9.]+)?"))) {
    "Invalid versionName"
}

android {
    namespace = "io.github.arcforges.mobile"
    compileSdk = 37
    buildToolsVersion = "37.0.0"
    defaultConfig {
        applicationId = "io.github.arcforges.mobile"
        minSdk = 26
        targetSdk = 37
        versionCode = releaseCode
        versionName = releaseName
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "CONTRACTS_VERSION", "\"${libs.versions.contracts.get()}\"")
    }
    buildTypes {
        debug { applicationIdSuffix = ".debug" }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            // CI signs the verified unsigned candidate in a separate, protected job.
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    // Each Contracts JAR has its own SBOM. Concatenating them would produce invalid JSON.
    packaging.resources.excludes +=
        setOf("META-INF/INDEX.LIST", "META-INF/DEPENDENCIES", "sbom.cdx.json", "source.json")
    packaging.resources.merges +=
        setOf("README.md", "LICENSE", "NOTICE", "META-INF/LICENSE*", "META-INF/NOTICE*")
    lint {
        abortOnError = true
        warningsAsErrors = true
    }
}

val licenceDirectory =
    objects.directoryProperty().apply {
        set(rootProject.layout.buildDirectory.dir("generated/licence-assets"))
    }
val licenceTask = tasks.named("verifyAndroidLicences")

androidComponents.onVariants { variant ->
    variant.sources.assets?.addGeneratedSourceDirectory(licenceTask) { licenceDirectory }
    variant.androidTest?.sources?.assets?.addGeneratedSourceDirectory(licenceTask) {
        licenceDirectory
    }
}

kotlin {
    jvmToolchain(21)
    compilerOptions { jvmTarget.set(JvmTarget.JVM_21) }
}

dependencies {
    implementation(project(":shared"))
    implementation(libs.activity.compose)
    implementation(libs.compose.runtime)
    implementation(libs.compose.ui)
    implementation(libs.contracts.client)
    implementation(libs.connect.okhttp)
    implementation(libs.connect.javalite)
    implementation(libs.coroutines.core)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.compose.ui.test.junit4)
    debugImplementation(libs.compose.ui.tooling)
}

// Project licence metadata is verified independently of the root LICENSE.
extra["spdxLicense"] = "Apache-2.0"

extra["licenceBoundary"] = "Apache"
