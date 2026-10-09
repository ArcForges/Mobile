# SPDX-License-Identifier: Apache-2.0
"""AND.40 unit 5 review fixes (offline): the MAUI sign and public-verify round trip, the binutils refusal at each
sealing point and the release-ready gate. The Android build tools are replaced by a fake that writes the files a real
run writes; the signing key itself is never created or read."""

import base64
import contextlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ENG = Path(__file__).resolve().parents[1]
ROOT = ENG.parent
sys.path.insert(0, str(ENG))

import build_identity  # noqa: E402
import maui_notices  # noqa: E402
import mobile  # noqa: E402
import published  # noqa: E402
import resources  # noqa: E402

COMMIT = "c" * 40
SIGNING = json.loads((ROOT / "eng/policy/dotnet-toolchain.json").read_text(encoding="utf-8"))["signing"]["certificateSha256"]
CLEAN = {"classes.dex": b"dex\n035\0", "AndroidManifest.xml": b"manifest", "lib/arm64-v8a/libmonosgen-2.0.so": b"mono"}
ENVIRONMENT = {
    "GITHUB_SHA": COMMIT, "GITHUB_RUN_NUMBER": "1", "GITHUB_RUN_ATTEMPT": "1",
    "ANDROID_KEYSTORE_BASE64": base64.b64encode(b"fixture keystore bytes").decode("ascii"),
    "ANDROID_KEYSTORE_PASSWORD": "fixture-store", "ANDROID_KEY_ALIAS": "fixture-alias",
    "ANDROID_KEY_PASSWORD": "fixture-key", "ANDROID_SIGNING_CERT_SHA256": SIGNING,
}


def write_apk(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


class BuildTools:
    """Stands in for zipalign and apksigner. It writes what a real run writes and verifies with the persistent certificate."""

    def __init__(self, signed=CLEAN):
        self.signed = signed

    def __call__(self, *args, capture=False, **kwargs):
        command = [str(arg) for arg in args]
        tool = Path(command[0]).name
        if tool == "zipalign":
            if "-c" not in command:
                shutil.copyfile(command[-2], command[-1])
            return ""
        if tool == "apksigner" and command[1] == "sign":
            write_apk(Path(command[command.index("--out") + 1]), self.signed)
            return ""
        if tool == "apksigner" and command[1] == "verify":
            return f"Number of signers: 1\nSigner #1 certificate SHA-256 digest: {SIGNING}\n"
        raise AssertionError("Unexpected build tool call: " + " ".join(command))


def sealed_candidate(directory):
    """A candidate as maui_stage seals it: the unsigned APK, its companions and candidate.json."""
    write_apk(directory / mobile.MAUI_UNSIGNED, CLEAN)
    (directory / "mapping.txt").write_bytes(b"mapping\n")
    (directory / "THIRD_PARTY_NOTICES.txt").write_bytes(b"notices\n")
    (directory / "licence-closure.json").write_text("{}\n", encoding="utf-8")
    (directory / "build-identity.json").write_text(json.dumps({"toolchain": {"sdk": {"observed": "10.0.400"}}}) + "\n",
                                                   encoding="utf-8")
    (directory / "maui-archive.json").write_text('{"release": false}\n', encoding="utf-8")
    info = {"version_code": 101, "version_name": "0.1.0-ci.1.1", "commit": COMMIT, "package": mobile.MAUI_PACKAGE,
            "track": mobile.MAUI_TRACK,
            "sha256": {name: mobile.sha256(directory / name) for name in sorted(mobile.MAUI_CANDIDATE_FILES)}}
    (directory / "candidate.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")


def archive_of(apk, identity, root=None, release=False, assemblies_root=None):
    """The archive names the APK digest, so the public copy must be derived again from the public APK."""
    return {"release": release, "apkSha256": mobile.sha256(Path(apk))}


@contextlib.contextmanager
def signing_environment(tools):
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, ENVIRONMENT))
        stack.enter_context(patch.object(mobile, "run", new=tools))
        stack.enter_context(patch.object(mobile, "maui_sdk_tool", new=lambda name: Path(name)))
        stack.enter_context(patch.object(build_identity, "verify_maui_report", new=lambda *args, **kwargs: None))
        stack.enter_context(patch.object(mobile.maui_identity, "inspect_apk",
                                         new=lambda *args, **kwargs: {"identity": {"versionCode": "101", "versionName": "0.1.0-ci.1.1"}}))
        stack.enter_context(patch.object(resources, "maui_archive", new=archive_of))
        yield


class MauiSealTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix="maui-seal-test-"))
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.candidate = self.directory / "candidate"
        self.candidate.mkdir()
        sealed_candidate(self.candidate)

    def sign(self, tools):
        with signing_environment(tools):
            mobile.maui_sign(self.candidate, self.directory / "release")
        return self.directory / "release"

    def test_the_signed_release_seal_lists_every_member_and_public_verification_reads_it(self):
        release = self.sign(BuildTools())
        seal = json.loads((release / "release.json").read_text(encoding="utf-8"))
        self.assertEqual(seal["track"], "maui")
        self.assertEqual(seal["tag"], "android-0.1.0-ci.1.1")
        self.assertEqual(set(seal["sha256"]), published.maui_release_names("0.1.0-ci.1.1"))
        self.assertNotIn("release.json", seal["sha256"])
        for name, digest in seal["sha256"].items():
            self.assertEqual(mobile.sha256(release / name), digest, name)
        with signing_environment(BuildTools()):
            verified = published.maui_verify(release, self.candidate, expected_certificate=SIGNING)
        self.assertEqual(verified["certificate_sha256"], SIGNING)
        self.assertEqual(verified["public_sha256"], seal["sha256"])

    def test_the_release_archive_is_the_one_derived_from_the_signed_apk(self):
        release = self.sign(BuildTools())
        archive = json.loads((release / "maui-archive.json").read_text(encoding="utf-8"))
        self.assertEqual(archive, {"release": True, "apkSha256": mobile.sha256(release / "ArcForges-0.1.0-ci.1.1.apk")})
        self.assertNotEqual((release / "maui-archive.json").read_bytes(), (self.candidate / "maui-archive.json").read_bytes())

    def test_a_signed_apk_carrying_binutils_is_never_released(self):
        with self.assertRaisesRegex(ValueError, "binutils is inside the APK"):
            self.sign(BuildTools(signed={**CLEAN, "lib/arm64-v8a/ld": b"ELF"}))
        self.assertFalse((self.directory / "release" / "release.json").exists())


class HostOnlyTests(unittest.TestCase):
    def apk(self, entries):
        directory = Path(tempfile.mkdtemp(prefix="maui-host-only-"))
        self.addCleanup(shutil.rmtree, directory, True)
        return write_apk(directory / "app.apk", entries)

    def test_a_clean_apk_is_host_only_clean(self):
        self.assertEqual(maui_notices.apk_host_only(self.apk(CLEAN)), {"entries": 3, "binutilsMembers": 0})

    def test_a_binutils_member_name_is_refused(self):
        with self.assertRaisesRegex(ValueError, "binutils is inside the APK"):
            maui_notices.apk_host_only(self.apk({**CLEAN, "lib/x86/libbfd-2.42.so": b"ELF"}))

    def test_a_binutils_content_signature_is_refused(self):
        with self.assertRaisesRegex(ValueError, "binutils is inside the APK"):
            maui_notices.apk_host_only(self.apk({**CLEAN, "assets/notes.bin": b"GNU ld (GNU Binutils) 2.42"}))

    def test_a_missing_apk_is_refused(self):
        with self.assertRaisesRegex(ValueError, "APK missing"):
            maui_notices.apk_host_only(Path("does-not-exist.apk"))


class ReleaseReadyTests(unittest.TestCase):
    def test_the_repository_release_is_ready_with_no_open_escalation(self):
        self.assertEqual(maui_notices.release_ready(ROOT), {"result": "ready", "openEscalations": 0})

    def test_an_open_escalation_blocks_the_release(self):
        directory = Path(tempfile.mkdtemp(prefix="maui-ready-"))
        self.addCleanup(shutil.rmtree, directory, True)
        data = json.loads((ROOT / maui_notices.NOTICE_DATA).read_text(encoding="utf-8"))
        for item in data["escalated"]:
            item["status"] = "open"
        target = directory / maui_notices.NOTICE_DATA
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Open notice escalations block the MAUI release"):
            maui_notices.release_ready(directory)


if __name__ == "__main__":
    unittest.main()
