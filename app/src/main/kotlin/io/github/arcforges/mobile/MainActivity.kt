// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import io.github.arcforges.mobile.shared.ArcForgesApp

class MainActivity : ComponentActivity() {
    private val cloud = CloudHelloClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ArcForgesApp(
                greet = cloud::greet,
                initialMessage = "Ready to connect.",
                serviceLabel = "Cloud Hello · arcforges.com",
            )
        }
    }

    override fun onDestroy() {
        cloud.close()
        super.onDestroy()
    }
}
