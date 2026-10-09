// SPDX-License-Identifier: Apache-2.0
using System.Text;
using Android.OS;
using Android.Security.Keystore;
using Java.Security;
using Javax.Crypto;
using Javax.Crypto.Spec;

namespace ArcForges.Mobile.Security;

/// <summary>
/// The Android Keystore probe over Java interop (AND.40 decision 11): a test-only device harness, run locally as
/// opt-in under PRF.12. It generates an AES-GCM key in the Android Keystore, seals and opens a test-only record
/// bound to realm, user and installation, rejects a changed binding and a flipped bit, and checks that the key
/// cannot be exported and is gone once deleted. It persists no secret and never writes a plaintext fallback.
/// </summary>
public static class AndroidKeystoreProbe
{
    private const string Provider = "AndroidKeyStore";
    private const string Transformation = "AES/GCM/NoPadding";
    private const int TagBits = 128;

    /// <summary>Runs every check on the device and returns the record. The probe key is always deleted.</summary>
    public static KeystoreProbeRecord Run()
    {
        var alias = "arcforges.probe.keystore." + Guid.NewGuid().ToString("N");
        var keyStore = KeyStore.GetInstance(Provider) ?? throw new InvalidOperationException("The Android Keystore is unavailable.");
        keyStore.Load(null, null);
        var outcomes = new List<KeystoreProbeOutcome>();
        int? level = null;
        try
        {
            var key = GenerateKey(alias);
            var aad = Encoding.UTF8.GetBytes("realm-1|user-1|inst-1");
            var plain = Encoding.UTF8.GetBytes("test-only credential record");

            level = ReportedLevel(key);
            outcomes.Add(Check("key is AES-256 in the Keystore", () => IsAes256(alias, key)));
            outcomes.Add(Check("key material cannot be exported", () => key.GetEncoded() is null));

            var (iv, cipherText) = Seal(key, aad, plain);
            outcomes.Add(Check("record round-trips under its binding", () => Open(key, aad, iv, cipherText).AsSpan().SequenceEqual(plain)));
            outcomes.Add(Check("changed binding is rejected", () => OpenFails(key, Encoding.UTF8.GetBytes("realm-2|user-1|inst-1"), iv, cipherText)));

            var flipped = (byte[])cipherText.Clone();
            flipped[0] ^= 1;
            outcomes.Add(Check("flipped ciphertext bit is rejected", () => OpenFails(key, aad, iv, flipped)));

            var (secondIv, _) = Seal(key, aad, plain);
            outcomes.Add(Check("each record gets a fresh IV", () => !iv.AsSpan().SequenceEqual(secondIv)));

            keyStore.DeleteEntry(alias);
            outcomes.Add(Check("deleted key is gone from the Keystore", () => !keyStore.ContainsAlias(alias) && keyStore.GetKey(alias, null) is null));
        }
        finally
        {
            if (keyStore.ContainsAlias(alias))
            {
                keyStore.DeleteEntry(alias);
            }
        }

        return new KeystoreProbeRecord((int)Build.VERSION.SdkInt, level, outcomes);
    }

    private static KeystoreProbeOutcome Check(string name, Func<bool> held)
    {
        try
        {
            return new KeystoreProbeOutcome(name, held());
        }
        catch (Java.Lang.Exception)
        {
            return new KeystoreProbeOutcome(name, false);
        }
    }

    private static ISecretKey GenerateKey(string alias)
    {
        var generator = KeyGenerator.GetInstance(KeyProperties.KeyAlgorithmAes, Provider)
            ?? throw new InvalidOperationException("AES key generation is unavailable.");
        var spec = new KeyGenParameterSpec.Builder(alias, KeyStorePurpose.Encrypt | KeyStorePurpose.Decrypt)
            .SetBlockModes(KeyProperties.BlockModeGcm)
            .SetEncryptionPaddings(KeyProperties.EncryptionPaddingNone)
            .SetKeySize(256)
            .SetRandomizedEncryptionRequired(true)
            .Build();
        generator.Init(spec);
        return generator.GenerateKey() ?? throw new InvalidOperationException("The Keystore returned no key.");
    }

    private static KeyInfo KeyInfoOf(ISecretKey key)
    {
        var factory = SecretKeyFactory.GetInstance(key.Algorithm ?? string.Empty, Provider)
            ?? throw new InvalidOperationException("The key factory is unavailable.");
        var spec = factory.GetKeySpec(key, Java.Lang.Class.FromType(typeof(KeyInfo)))
            ?? throw new InvalidOperationException("The Keystore returned no key information.");
        return (KeyInfo)spec;
    }

    private static bool IsAes256(string alias, ISecretKey key)
    {
        var info = KeyInfoOf(key);
        return info.KeySize == 256 && info.KeystoreAlias == alias;
    }

    // The platform's report, read only where the API defines it; below API 31 the record says so. The guard uses the
    // literal level, which the platform analyzer evaluates (KeystoreProbeRecord.SecurityLevelApi is 31).
    private static int? ReportedLevel(ISecretKey key)
    {
        if (OperatingSystem.IsAndroidVersionAtLeast(31))
        {
            return KeyInfoOf(key).SecurityLevel;
        }

        return null;
    }

    private static (byte[] Iv, byte[] CipherText) Seal(ISecretKey key, byte[] aad, byte[] plain)
    {
        var cipher = Cipher.GetInstance(Transformation) ?? throw new InvalidOperationException("AES-GCM is unavailable.");
        cipher.Init(CipherMode.EncryptMode, key);
        cipher.UpdateAAD(aad);
        var cipherText = cipher.DoFinal(plain) ?? throw new InvalidOperationException("The cipher returned no record.");
        return (cipher.GetIV() ?? throw new InvalidOperationException("The cipher returned no IV."), cipherText);
    }

    private static byte[] Open(ISecretKey key, byte[] aad, byte[] iv, byte[] cipherText)
    {
        var cipher = Cipher.GetInstance(Transformation) ?? throw new InvalidOperationException("AES-GCM is unavailable.");
        cipher.Init(CipherMode.DecryptMode, key, new GCMParameterSpec(TagBits, iv));
        cipher.UpdateAAD(aad);
        return cipher.DoFinal(cipherText) ?? throw new InvalidOperationException("The cipher returned no plaintext.");
    }

    private static bool OpenFails(ISecretKey key, byte[] aad, byte[] iv, byte[] cipherText)
    {
        try
        {
            Open(key, aad, iv, cipherText);
            return false;
        }
        catch (Java.Lang.Exception)
        {
            return true;
        }
    }
}
