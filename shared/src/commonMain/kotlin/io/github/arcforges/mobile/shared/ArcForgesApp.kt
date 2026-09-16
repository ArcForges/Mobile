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
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
fun ArcForgesApp(
    greet: suspend (String) -> String = { hello(it) },
    initialMessage: String = "Hello, World!",
    serviceLabel: String = "Local preview · Works offline",
) {
    var name by rememberSaveable { mutableStateOf("World") }
    var greeting by rememberSaveable { mutableStateOf(initialMessage) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
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
                            if (loading) "Connecting..." else greeting,
                            Modifier.testTag("greeting"),
                            style = MaterialTheme.typography.headlineSmall,
                        )
                        OutlinedTextField(
                            value = name,
                            onValueChange = { name = it },
                            modifier = Modifier.fillMaxWidth().testTag("name"),
                            label = { Text("Your name") },
                            singleLine = true,
                            enabled = !loading,
                            isError = name.length > 256,
                            supportingText = { Text("${name.length}/256") },
                        )
                        error?.let {
                            Text(it, Modifier.testTag("error"), color = colors.error)
                        }
                        Button(
                            onClick = {
                                loading = true
                                error = null
                                scope.launch {
                                    try {
                                        greeting = greet(name)
                                    } catch (canceled: CancellationException) {
                                        throw canceled
                                    } catch (failure: GreetingFailure) {
                                        error = failure.message
                                    } catch (_: Exception) {
                                        error = "Could not complete the request. Please try again."
                                    } finally {
                                        loading = false
                                    }
                                }
                            },
                            enabled = !loading && name.length in 1..256,
                            modifier = Modifier.fillMaxWidth().testTag("say-hello"),
                        ) {
                            Text(if (loading) "Connecting..." else "Say hello")
                        }
                    }
                }
                Text(
                    serviceLabel,
                    style = MaterialTheme.typography.labelMedium,
                    color = colors.onSurfaceVariant,
                )
            }
        }
    }
}
