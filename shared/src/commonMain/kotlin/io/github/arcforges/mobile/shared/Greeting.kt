// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile.shared

/** Local development preview only; the Android application supplies its Cloud operation. */
fun hello(name: String): String {
    require(name.length in 1..256) { "Use a name with 1 to 256 characters." }
    return "Hello, $name!"
}

/** A bounded, user-facing failure message supplied by the platform's transport adapter. */
class GreetingFailure(message: String) : Exception(message)
