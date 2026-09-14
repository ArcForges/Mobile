// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile.shared

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun ArcForgesApp(greet: (String) -> String = ::hello) {
    var name by rememberSaveable { mutableStateOf("World") }
    var greeting by rememberSaveable { mutableStateOf(greet("World")) }
    val colors = lightColorScheme(primary = Color(0xFF305E46), background = Color(0xFFF5F6EF))

    MaterialTheme(colorScheme = colors) {
        Box(
            Modifier.fillMaxSize().background(colors.background).safeDrawingPadding(),
            contentAlignment = Alignment.TopCenter,
        ) {
            Column(
                Modifier.widthIn(max = 520.dp)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(28.dp),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                Spacer(Modifier.height(24.dp))
                Text(
                    "ARCFORGES",
                    style = MaterialTheme.typography.labelLarge,
                    color = colors.primary,
                )
                Text(
                    "A small beginning.",
                    style = MaterialTheme.typography.headlineLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                Text("Your ideas, on the move.", style = MaterialTheme.typography.bodyLarge)
                Spacer(Modifier.height(12.dp))
                Card(
                    Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(24.dp),
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                ) {
                    Column(
                        Modifier.padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(20.dp),
                    ) {
                        Text(
                            greeting,
                            Modifier.testTag("greeting"),
                            style = MaterialTheme.typography.headlineSmall,
                        )
                        OutlinedTextField(
                            value = name,
                            onValueChange = { name = it },
                            modifier = Modifier.fillMaxWidth().testTag("name"),
                            label = { Text("Your name") },
                            singleLine = true,
                        )
                        Button(
                            onClick = { greeting = greet(name) },
                            enabled = name.isNotEmpty(),
                            modifier = Modifier.fillMaxWidth().testTag("say-hello"),
                        ) {
                            Text("Say hello")
                        }
                    }
                }
                Text(
                    "Hello World · Works offline",
                    style = MaterialTheme.typography.labelMedium,
                    color = colors.onSurfaceVariant,
                )
            }
        }
    }
}
