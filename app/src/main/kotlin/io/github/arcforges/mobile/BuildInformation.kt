// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Typeface
import android.widget.ScrollView
import android.widget.TextView
import java.security.MessageDigest
import org.json.JSONObject

/**
 * Read the installed artifact, without contacting a server or consulting build environment
 * variables.
 */
internal fun showBuildInformation(activity: Activity) {
    val bytes = activity.assets.open("build-identity.json").use { it.readBytes() }
    val report = JSONObject(bytes.toString(Charsets.UTF_8))
    val artifact = report.getJSONObject("artifact")
    val build = report.getJSONObject("build")
    check(report.getString("schema") == "arcforges.build-identity.v1")
    check(report.getString("owner") == "Mobile")
    check(artifact.getString("version") == BuildConfig.VERSION_NAME)
    check(
        report.getJSONObject("packaging").getInt("androidVersionCode") == BuildConfig.VERSION_CODE
    )
    check(build.getString("sourceCommit") == BuildConfig.SOURCE_COMMIT)
    check(build.getString("buildId") == BuildConfig.BUILD_ID)
    val digest =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    val text = buildString {
        appendLine("ArcForges ${artifact.getString("version")}")
        appendLine("Android versionCode: ${BuildConfig.VERSION_CODE}")
        appendLine("Source: ${build.getString("sourceCommit")}")
        appendLine("Build: ${build.getString("buildId")}")
        appendLine("Kind: ${build.getString("kind")}; dirty: ${build.getBoolean("dirty")}")
        appendLine("Source UTC epoch: ${build.getLong("sourceDateEpoch")}")
        appendLine("Pipeline: ${build.optString("pipelineRun", "local")}")
        appendLine("Report SHA-256: $digest")
        val axes = report.getJSONObject("axes")
        for (name in axes.keys()) {
            val axis = axes.getJSONObject(name)
            appendLine()
            appendLine("$name: ${axis.getString("status")}")
            if (axis.has("values")) {
                val values = axis.getJSONArray("values")
                if (name == "PackageVersion") {
                    appendLine(
                        "${values.length()} locked runtime packages; full inventory in build-identity.json."
                    )
                } else {
                    for (index in 0 until values.length()) {
                        val value = values.getJSONObject(index)
                        appendLine("${value.getString("subject")}: ${value.getString("version")}")
                    }
                }
            } else {
                appendLine(axis.getString("reason"))
                if (axis.has("producer")) appendLine("Producer: ${axis.getString("producer")}")
            }
        }
    }
    val view =
        TextView(activity).apply {
            this.text = text
            typeface = Typeface.MONOSPACE
            setTextIsSelectable(true)
            setPadding(24, 16, 24, 16)
        }
    AlertDialog.Builder(activity)
        .setTitle("Build information")
        .setView(ScrollView(activity).apply { addView(view) })
        .setPositiveButton("Close", null)
        .show()
}
