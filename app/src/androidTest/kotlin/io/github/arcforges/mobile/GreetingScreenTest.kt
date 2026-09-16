// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import androidx.activity.compose.setContent
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextReplacement
import io.github.arcforges.mobile.shared.ArcForgesApp
import io.github.arcforges.mobile.shared.GreetingFailure
import kotlinx.coroutines.CompletableDeferred
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class GreetingScreenTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun greetsAndRestoresAcrossActivityRecreation() {
        cloudHealth()
        compose.onNodeWithTag("greeting").assertTextEquals("Ready to connect.")
        compose.onNodeWithTag("name").performTextReplacement("Android")
        compose.onNodeWithTag("say-hello").performClick()
        compose.waitUntil(15000) {
            compose.onAllNodes(hasText("Hello, Android!")).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("greeting").assertTextEquals("Hello, Android!")
        compose.activityRule.scenario.recreate()
        compose.onNodeWithTag("greeting").assertTextEquals("Hello, Android!")
        compose.onNodeWithTag("name").assertTextContains("Android")
    }

    @Test
    fun emptyNameCannotBeSubmitted() {
        compose.onNodeWithTag("name").performTextReplacement("")
        compose.onNodeWithTag("say-hello").assertIsNotEnabled()
        compose.onNodeWithTag("name").performTextReplacement("x".repeat(257))
        compose.onNodeWithTag("say-hello").assertIsNotEnabled()
    }

    @Test
    fun pendingRequestDisablesDuplicateSubmissionAndFailureAllowsManualRetry() {
        val result = CompletableDeferred<String>()
        var calls = 0
        compose.activityRule.scenario.onActivity { activity ->
            activity.setContent {
                ArcForgesApp(
                    greet = {
                        calls++
                        if (calls == 1) result.await() else "Hello, World!"
                    },
                    initialMessage = "Ready to connect.",
                )
            }
        }
        compose.onNodeWithTag("say-hello").performClick()
        compose.onNodeWithTag("greeting").assertTextEquals("Connecting...")
        compose.onNodeWithTag("say-hello").assertIsNotEnabled()
        compose.onNodeWithTag("name").assertIsNotEnabled()
        compose.runOnIdle { result.completeExceptionally(GreetingFailure("Cloud is unavailable.")) }
        compose.onNodeWithTag("error").assertTextEquals("Cloud is unavailable.")
        compose.onNodeWithTag("say-hello").assertIsEnabled().performClick()
        compose.onNodeWithTag("greeting").assertTextEquals("Hello, World!")
        compose.onNodeWithTag("error").assertDoesNotExist()
        compose.runOnIdle { assertEquals(2, calls) }
    }

    @Test
    fun recreationCancelsPendingWorkWithoutReplayingIt() {
        val pending = CompletableDeferred<String>()
        var canceled = false
        var calls = 0
        compose.activityRule.scenario.onActivity { activity ->
            activity.setContent {
                ArcForgesApp(
                    greet = {
                        calls++
                        try {
                            pending.await()
                        } finally {
                            canceled = true
                        }
                    },
                    initialMessage = "Ready to connect.",
                )
            }
        }
        compose.onNodeWithTag("say-hello").performClick()
        compose.onNodeWithTag("greeting").assertTextEquals("Connecting...")
        compose.activityRule.scenario.recreate()
        compose.onNodeWithTag("greeting").assertTextEquals("Ready to connect.")
        compose.onNodeWithTag("say-hello").assertIsEnabled()
        compose.runOnIdle {
            assertTrue(canceled)
            assertEquals(1, calls)
        }
    }
}
