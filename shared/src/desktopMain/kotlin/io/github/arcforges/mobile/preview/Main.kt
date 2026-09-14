// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile.preview

import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import io.github.arcforges.mobile.shared.ArcForgesApp

fun main() = application {
    Window(
        onCloseRequest = ::exitApplication,
        title = "ArcForges · Development preview",
        state = rememberWindowState(width = 440.dp, height = 820.dp),
    ) {
        ArcForgesApp()
    }
}
