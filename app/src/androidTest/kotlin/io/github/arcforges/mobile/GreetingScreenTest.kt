// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextReplacement
import org.junit.Rule
import org.junit.Test

class GreetingScreenTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun greetsAndRestoresAcrossActivityRecreation() {
        compose.onNodeWithTag("greeting").assertTextEquals("Hello, World!")
        compose.onNodeWithTag("name").performTextReplacement("Android")
        compose.onNodeWithTag("say-hello").performClick()
        compose.onNodeWithTag("greeting").assertTextEquals("Hello, Android!")
        compose.activityRule.scenario.recreate()
        compose.onNodeWithTag("greeting").assertTextEquals("Hello, Android!")
        compose.onNodeWithTag("name").assertTextEquals("Your name", "Android")
    }

    @Test
    fun emptyNameCannotBeSubmitted() {
        compose.onNodeWithTag("name").performTextReplacement("")
        compose.onNodeWithTag("say-hello").assertIsNotEnabled()
    }
}
