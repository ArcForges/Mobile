// SPDX-License-Identifier: Apache-2.0
package io.github.arcforges.mobile

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.util.Log
import java.security.GeneralSecurityException
import java.security.InvalidAlgorithmParameterException
import java.security.KeyStore
import java.util.UUID
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Android Keystore behavior behind the mobile credential storage rule (AES-GCM key generated in the
 * Keystore, record bound to realm, user and installation, an invalidated key never falls back to
 * plaintext). This is a proof probe, not the credential store: it models the sealed record with
 * test-only values and no secret, and persists nothing.
 *
 * It needs a device or emulator and is local opt-in only: no CI job runs it. The observed results
 * describe the device it ran on, never every device or security level.
 */
class KeystoreProbeTest {
    private val alias = "arcforges.proof.keystore." + UUID.randomUUID()
    private val keyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }

    private class Sealed(val iv: ByteArray, val bytes: ByteArray)

    private fun newKey(): SecretKey =
        KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER)
            .apply {
                init(
                    KeyGenParameterSpec.Builder(
                            alias,
                            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                        )
                        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                        .setKeySize(256)
                        .setRandomizedEncryptionRequired(true)
                        .build()
                )
            }
            .generateKey()

    /** The stored key, or null once it was deleted: the caller has no plaintext fallback. */
    private fun currentKey(): SecretKey? = keyStore.getKey(alias, null) as SecretKey?

    private fun aad(
        realm: String = "realm-1",
        user: String = "user-1",
        install: String = "inst-1",
    ) = "$realm|$user|$install".toByteArray()

    private fun seal(key: SecretKey, aad: ByteArray, plain: ByteArray): Sealed {
        val cipher = Cipher.getInstance(TRANSFORMATION).apply { init(Cipher.ENCRYPT_MODE, key) }
        cipher.updateAAD(aad)
        return Sealed(cipher.iv, cipher.doFinal(plain))
    }

    private fun open(key: SecretKey, aad: ByteArray, sealed: Sealed): ByteArray {
        val cipher =
            Cipher.getInstance(TRANSFORMATION).apply {
                init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, sealed.iv))
            }
        cipher.updateAAD(aad)
        return cipher.doFinal(sealed.bytes)
    }

    @After
    fun deleteTestKey() {
        if (keyStore.containsAlias(alias)) keyStore.deleteEntry(alias)
    }

    @Test
    fun recordBoundToRealmUserAndInstallationRoundTrips() {
        val key = newKey()
        val plain = "test-only credential record".toByteArray()
        val sealed = seal(key, aad(), plain)
        assertEquals(12, sealed.iv.size)
        assertEquals(plain.size + TAG_BITS / 8, sealed.bytes.size)
        assertArrayEquals(plain, open(currentKey()!!, aad(), sealed))
    }

    @Test
    fun keyMaterialCannotBeExported() {
        val key = newKey()
        assertNull(key.encoded)
        val info =
            SecretKeyFactory.getInstance(key.algorithm, PROVIDER)
                .getKeySpec(key, KeyInfo::class.java) as KeyInfo
        assertEquals(256, info.keySize)
        assertEquals(KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT, info.purposes)
        // Recorded for the evidence, never asserted: it depends on the device. The API 31
        // replacement for the deprecated hardware flag does not exist on API 26 to 30.
        val level =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) info.securityLevel.toString()
            else "unreported below API 31"
        Log.i(TAG, "api=${Build.VERSION.SDK_INT} securityLevel=$level")
    }

    @Test
    fun anyChangedBindingOrCiphertextBitIsRejected() {
        val key = newKey()
        val sealed = seal(key, aad(), "test-only credential record".toByteArray())
        for (wrong in
            listOf(aad(realm = "realm-2"), aad(user = "user-2"), aad(install = "inst-2"))) {
            assertThrows(AEADBadTagException::class.java) { open(key, wrong, sealed) }
        }
        val flipped = sealed.bytes.copyOf().also { it[0] = (it[0].toInt() xor 1).toByte() }
        assertThrows(AEADBadTagException::class.java) {
            open(key, aad(), Sealed(sealed.iv, flipped))
        }
        val truncated = sealed.bytes.copyOf(sealed.bytes.size - 1)
        assertThrows(GeneralSecurityException::class.java) {
            open(key, aad(), Sealed(sealed.iv, truncated))
        }
    }

    @Test
    fun everyRecordGetsAFreshIvAndTheCallerCannotChooseOne() {
        val key = newKey()
        val first = seal(key, aad(), "same".toByteArray())
        val second = seal(key, aad(), "same".toByteArray())
        assertFalse(first.iv.contentEquals(second.iv))
        assertFalse(first.bytes.contentEquals(second.bytes))
        assertThrows(InvalidAlgorithmParameterException::class.java) {
            Cipher.getInstance(TRANSFORMATION)
                .init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(TAG_BITS, ByteArray(12)))
        }
    }

    @Test
    fun deletedKeyLeavesNothingToDecryptWithAndNoPlaintextPath() {
        val key = newKey()
        val sealed = seal(key, aad(), "test-only credential record".toByteArray())
        keyStore.deleteEntry(alias)
        assertNull(currentKey())
        assertFalse(keyStore.containsAlias(alias))
        // A reference obtained before the deletion is no longer usable either.
        assertThrows(GeneralSecurityException::class.java) { open(key, aad(), sealed) }
    }

    @Test
    fun replacementKeyUnderTheSameAliasDoesNotOpenAnOldRecord() {
        val old = newKey()
        val sealed = seal(old, aad(), "test-only credential record".toByteArray())
        keyStore.deleteEntry(alias)
        val replacement = newKey()
        assertNotNull(currentKey())
        assertThrows(AEADBadTagException::class.java) { open(replacement, aad(), sealed) }
        // The replacement works for new records, as rotation requires.
        val fresh = seal(replacement, aad(), "rotated".toByteArray())
        assertArrayEquals("rotated".toByteArray(), open(currentKey()!!, aad(), fresh))
        assertTrue(keyStore.containsAlias(alias))
    }

    private companion object {
        const val PROVIDER = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val TAG_BITS = 128
        const val TAG = "KeystoreProbe"
    }
}
