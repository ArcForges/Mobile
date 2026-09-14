// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import io.github.arcforges.mobile.shared.ArcForgesApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { ArcForgesApp(greet = ::localContractGreeting) }
    }
}
