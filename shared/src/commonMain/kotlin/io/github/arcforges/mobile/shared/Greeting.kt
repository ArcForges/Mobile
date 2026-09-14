// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile.shared

/** The Contracts Hello World sample rejects an empty name and preserves all other text. */
fun hello(name: String): String {
    require(name.isNotEmpty()) { "Enter a name to say hello." }
    return "Hello, $name!"
}
