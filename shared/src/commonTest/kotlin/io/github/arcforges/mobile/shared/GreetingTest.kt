// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile.shared

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class GreetingTest {
    @Test
    fun preservesUnicodeAndWhitespace() {
        assertEquals("Hello,  世界 👋 !", hello(" 世界 👋 "))
    }

    @Test
    fun rejectsEmptyName() {
        assertFailsWith<IllegalArgumentException> { hello("") }
    }
}
