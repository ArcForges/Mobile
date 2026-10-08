# SPDX-License-Identifier: Apache-2.0
"""AND.01 identity, toolchain pin and NuGet admission tests; no device or emulator claims."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import maui_identity as identity

ROOT = Path(__file__).resolve().parents[2]
PERSISTENT = "7a8b3b1402e77c3ec78e7a0b9f99d5358adc321d0e8d2a319c838d1cda181e9c"
DEBUG_SIGNER = "c7fe83cf58735ac8485ae10afc1ce40be679ee5878543fa4861c3a10b35c1b0d"
BADGING = """package: name='com.arcforges.mobile' versionCode='1' versionName='0.1.0' platformBuildVersionName='16' platformBuildVersionCode='36' compileSdkVersion='36' compileSdkVersionCodename='16'
minSdkVersion:'26'
targetSdkVersion:'36'
uses-permission: name='android.permission.INTERNET'
application-label:'ArcForges'
"""
CERTIFICATES = f"""Signer #1 certificate DN: CN=Android Debug, O=Android, C=US
Signer #1 certificate SHA-256 digest: {DEBUG_SIGNER}
Signer #1 certificate SHA-1 digest: 8d53ba7b2ed2d8a4fe57a047c0ddb445a6964bd1
"""
PAYLOAD = [
    "global.json",
    "Directory.Build.props",
    "Directory.Packages.props",
    "NuGet.config",
    "eng/published.py",
    "eng/policy/dotnet-toolchain.json",
    "eng/policy/nuget-admission.json",
    "eng/policy/workload-admission.json",
    "src/ArcForges.Mobile/ArcForges.Mobile.csproj",
    "src/ArcForges.Mobile/packages.lock.json",
    "src/ArcForges.Mobile/Platforms/Android/AndroidManifest.xml",
    "src/ArcForges.Mobile/App.cs",
    "src/ArcForges.Mobile/MainPage.cs",
    "src/ArcForges.Mobile/MauiProgram.cs",
    "src/ArcForges.Mobile/Compatibility/ContractsClientCompatibility.cs",
    "src/ArcForges.Mobile/Platforms/Android/MainActivity.cs",
]


def workload(doc, alias):
    return next(item for item in doc["workloads"] if item["alias"] == alias)


def admitted_pack(doc, alias, pack_id):
    return next(item for item in workload(doc, alias)["admittedPacks"] if item["id"] == pack_id)


class MauiIdentityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in PAYLOAD:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, name, old, new, count=1):
        path = self.root / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture text missing in {name}")
        path.write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")

    def refused(self):
        with self.assertRaises(ValueError):
            identity.check_maui(self.root)

    def test_repository_state_passes_the_gate(self):
        report = identity.check_maui(ROOT)
        self.assertEqual(report["applicationId"], "com.arcforges.mobile")
        self.assertEqual(report["targetFramework"], "net10.0-android")
        self.assertEqual(report["sdk"], "10.0.400")
        self.assertEqual(report["certificateSha256"], PERSISTENT)
        self.assertEqual(report["namespace"], "ArcForges.Mobile")
        self.assertEqual(report["targetPlatformVersion"], "36.1")

    def test_fixture_copy_passes_before_mutation(self):
        self.assertEqual(identity.check_maui(self.root)["applicationId"], "com.arcforges.mobile")

    def test_uncommitted_local_sdk_adapter_is_refused(self):
        self.edit("global.json", '"rollForward": "disable"', '"rollForward": "latestPatch"')
        self.refused()

    def test_sdk_pin_drift_is_refused(self):
        self.edit("global.json", '"10.0.400"', '"10.0.401"')
        self.refused()

    def test_development_identifier_is_refused(self):
        self.edit("src/ArcForges.Mobile/ArcForges.Mobile.csproj",
                  "<ApplicationId>com.arcforges.mobile</ApplicationId>",
                  "<ApplicationId>io.github.arcforges.mobile</ApplicationId>")
        self.refused()

    def test_manifest_package_attribute_is_refused(self):
        self.edit("src/ArcForges.Mobile/Platforms/Android/AndroidManifest.xml",
                  '<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
                  '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example">')
        self.refused()

    def test_unscoped_r8_linker_is_refused(self):
        self.edit("src/ArcForges.Mobile/ArcForges.Mobile.csproj",
                  "<PropertyGroup Condition=\"'$(Configuration)' == 'Release'\">\n    <AndroidLinkTool>",
                  "<PropertyGroup>\n    <AndroidLinkTool>")
        self.refused()

    def test_mono_runtime_must_be_explicit(self):
        self.edit("src/ArcForges.Mobile/ArcForges.Mobile.csproj",
                  "<UseMonoRuntime>true</UseMonoRuntime>", "<UseMonoRuntime>false</UseMonoRuntime>")
        self.refused()

    def test_trimmer_version_drift_is_refused(self):
        self.edit("Directory.Packages.props", 'Version="10.0.11"', 'Version="10.0.12"')
        self.refused()

    def test_inline_package_version_is_refused(self):
        self.edit("src/ArcForges.Mobile/ArcForges.Mobile.csproj",
                  '<PackageReference Include="Microsoft.Maui.Controls" />',
                  '<PackageReference Include="Microsoft.Maui.Controls" Version="10.0.20" />')
        self.refused()

    def test_signing_configuration_in_the_build_is_refused(self):
        self.edit("src/ArcForges.Mobile/ArcForges.Mobile.csproj",
                  '  <ItemGroup>\n    <PackageReference Include="Microsoft.Maui.Controls" />',
                  '  <PropertyGroup>\n    <AndroidKeyStore>true</AndroidKeyStore>\n'
                  '    <AndroidSigningStorePass>hunter2</AndroidSigningStorePass>\n  </PropertyGroup>\n\n'
                  '  <ItemGroup>\n    <PackageReference Include="Microsoft.Maui.Controls" />')
        self.refused()

    def test_additional_package_source_is_refused(self):
        self.edit("NuGet.config",
                  '<add key="nuget.org" value="https://api.nuget.org/v3/index.json" />',
                  '<add key="nuget.org" value="https://api.nuget.org/v3/index.json" />\n'
                  '    <add key="internal" value="https://packages.example.invalid/v3/index.json" />')
        self.refused()

    def test_central_version_drift_is_refused(self):
        self.edit("Directory.Packages.props", 'Version="10.0.20"', 'Version="10.0.30"')
        self.refused()

    def test_changed_persistent_certificate_is_refused(self):
        self.edit("eng/published.py", PERSISTENT, "0" * 64)
        self.refused()

    def test_lock_change_without_new_admission_is_refused(self):
        lock = json.loads((self.root / "src/ArcForges.Mobile/packages.lock.json").read_text(encoding="utf-8"))
        target = [key for key in lock["dependencies"] if "/" not in key][0]
        del lock["dependencies"][target]["Google.Protobuf"]
        (self.root / "src/ArcForges.Mobile/packages.lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
        self.refused()

    def test_checksum_drift_under_the_same_version_is_refused(self):
        lock = json.loads((self.root / "src/ArcForges.Mobile/packages.lock.json").read_text(encoding="utf-8"))
        target = [key for key in lock["dependencies"] if "/" not in key][0]
        lock["dependencies"][target]["Google.Protobuf"]["contentHash"] = "A" * 86 + "=="
        (self.root / "src/ArcForges.Mobile/packages.lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
        self.refused()

    def test_agpl_licence_is_refused_even_with_a_matching_lock(self):
        admission = json.loads((self.root / "eng/policy/nuget-admission.json").read_text(encoding="utf-8"))
        admission["packages"][0]["licence"] = "AGPL-3.0-only"
        (self.root / "eng/policy/nuget-admission.json").write_text(json.dumps(admission, indent=2), encoding="utf-8")
        self.refused()

    def test_unadmitted_permissive_looking_licence_is_refused(self):
        admission = json.loads((self.root / "eng/policy/nuget-admission.json").read_text(encoding="utf-8"))
        admission["packages"][0]["licence"] = "Custom-Terms"
        (self.root / "eng/policy/nuget-admission.json").write_text(json.dumps(admission, indent=2), encoding="utf-8")
        self.refused()

    def test_first_party_package_outside_the_contracts_client_is_refused(self):
        admission = json.loads((self.root / "eng/policy/nuget-admission.json").read_text(encoding="utf-8"))
        admission["packages"][0]["id"] = "ArcForges.Build.Policy"
        (self.root / "eng/policy/nuget-admission.json").write_text(json.dumps(admission, indent=2), encoding="utf-8")
        self.refused()

    def rewrite_json(self, name, mutate):
        path = self.root / name
        document = json.loads(path.read_text(encoding="utf-8"))
        mutate(document)
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    def test_target_api_decision_drift_is_refused(self):
        self.edit("eng/policy/dotnet-toolchain.json", '"value": "36.1"', '"value": "37.0"')
        self.refused()

    def test_root_namespace_drift_is_refused(self):
        self.edit("src/ArcForges.Mobile/ArcForges.Mobile.csproj",
                  "<RootNamespace>ArcForges.Mobile</RootNamespace>",
                  "<RootNamespace>Example.Mobile</RootNamespace>")
        self.refused()

    def test_source_namespace_outside_the_mobile_namespace_is_refused(self):
        self.edit("src/ArcForges.Mobile/App.cs", "namespace ArcForges.Mobile;", "namespace Example.Mobile;")
        self.refused()

    def test_deferral_without_an_owner_is_refused(self):
        self.rewrite_json("eng/policy/dotnet-toolchain.json", lambda doc: doc["deferrals"][0].pop("owner"))
        self.refused()

    def test_missing_linux_android_deferral_is_refused(self):
        self.rewrite_json("eng/policy/dotnet-toolchain.json",
                          lambda doc: doc.update(deferrals=[item for item in doc["deferrals"]
                                                            if item["id"] != "linux-android-build-proof"]))
        self.refused()

    def test_glide_exception_without_its_notice_obligation_is_refused(self):
        self.rewrite_json("eng/policy/nuget-admission.json",
                          lambda doc: doc["licenceExceptions"].update({"BSD-2-Clause": "Admitted as permissive."}))
        self.refused()

    def test_packaged_notice_deferral_removal_is_refused(self):
        self.rewrite_json("eng/policy/dotnet-toolchain.json",
                          lambda doc: doc.update(deferrals=[item for item in doc["deferrals"]
                                                            if item["id"] != "nuget-notice-grpc-core-api-2-84-0"]))
        self.refused()

    def test_packaged_notice_deferral_version_drift_is_refused(self):
        self.edit("eng/policy/dotnet-toolchain.json", '"version": "3.36.1"', '"version": "3.36.2"')
        self.refused()

    def test_stale_notice_deferral_is_refused(self):
        def add(doc):
            doc["deferrals"].append({"id": "nuget-notice-maui-core", "package": "Microsoft.Maui.Core",
                                     "version": "10.0.20", "licence": "MIT", "owner": "AND.40",
                                     "trigger": "The first MAUI Android release candidate.",
                                     "consequence": "No candidate is published without the notice."})
        self.rewrite_json("eng/policy/dotnet-toolchain.json", add)
        self.refused()

    def test_unnoticed_package_without_licence_files_is_refused(self):
        def drop_licence_files(doc):
            next(item for item in doc["packages"] if item["id"] == "Microsoft.Maui.Core")["licenceFiles"] = []
        self.rewrite_json("eng/policy/nuget-admission.json", drop_licence_files)
        self.refused()

    def test_workload_pin_drift_is_refused(self):
        self.edit("eng/policy/dotnet-toolchain.json", '"manifestVersion": "36.1.69"', '"manifestVersion": "36.1.70"')
        self.refused()

    def test_workload_record_missing_a_pinned_workload_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: doc.update(workloads=[item for item in doc["workloads"]
                                                            if item["alias"] != "mono-toolchain"]))
        self.refused()

    def test_workload_pack_version_drift_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: admitted_pack(doc, "android", "Microsoft.Android.Ref.36").update(version="36.1.70"))
        self.refused()

    def test_unpartitioned_workload_pack_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: workload(doc, "android")["excludedPacks"].pop(0))
        self.refused()

    def test_excluded_workload_pack_without_reason_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: workload(doc, "android")["excludedPacks"][0].update(reason=""))
        self.refused()

    def test_admitted_workload_pack_without_licence_evidence_is_refused(self):
        def strip_evidence(doc):
            pack = admitted_pack(doc, "android", "Microsoft.Android.Ref.36")
            pack["licence"] = None
            pack.pop("licenceFile")
        self.rewrite_json("eng/policy/workload-admission.json", strip_evidence)
        self.refused()

    def test_unadmitted_workload_licence_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: admitted_pack(doc, "maui-android", "Microsoft.Maui.Sdk.net10").update(
                              licence="Custom-Terms"))
        self.refused()

    def test_workload_licence_file_without_hash_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: admitted_pack(doc, "android", "Microsoft.Android.Ref.36")["licenceFile"].pop("sha256"))
        self.refused()

    def test_maui_library_outside_the_nuget_closure_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: admitted_pack(doc, "maui-android", "Microsoft.Maui.Core").update(version="10.0.30"))
        self.refused()

    def test_unverified_host_alias_without_its_deferral_is_refused(self):
        self.rewrite_json("eng/policy/dotnet-toolchain.json",
                          lambda doc: doc.update(deferrals=[item for item in doc["deferrals"]
                                                            if item["id"] != "workload-licence-evidence"]))
        self.refused()

    def test_manifest_without_a_hash_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: workload(doc, "android")["manifestFiles"].pop("WorkloadManifest.json"))
        self.refused()

    def test_sdk_pin_mismatch_in_workload_record_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: doc["reviewedHost"].update(sdkPinned="10.0.401"))
        self.refused()

    def test_excluded_manifest_without_reason_is_refused(self):
        self.rewrite_json("eng/policy/workload-admission.json",
                          lambda doc: doc["excludedManifests"][0].update(reason=""))
        self.refused()


class ApkIdentityTests(unittest.TestCase):
    def test_badging_identity_is_parsed(self):
        parsed = identity.parse_badging(BADGING)
        self.assertEqual(parsed, {"package": "com.arcforges.mobile", "versionCode": "1", "versionName": "0.1.0",
                                  "minSdk": 26, "targetSdk": 36})

    def test_badging_without_identity_is_refused(self):
        with self.assertRaises(ValueError):
            identity.parse_badging("application-label:'ArcForges'\n")

    def test_debug_signed_apk_is_identity_checked_but_not_a_release(self):
        report = identity.check_apk(BADGING, CERTIFICATES, ROOT, release=False)
        self.assertEqual(report["signerSha256"], DEBUG_SIGNER)
        with self.assertRaises(ValueError):
            identity.check_apk(BADGING, CERTIFICATES, ROOT, release=True)

    def test_release_apk_needs_the_persistent_certificate(self):
        persistent = CERTIFICATES.replace(DEBUG_SIGNER, PERSISTENT)
        self.assertEqual(identity.check_apk(BADGING, persistent, ROOT, release=True)["signerSha256"], PERSISTENT)

    def test_wrong_application_identifier_is_refused(self):
        wrong = BADGING.replace("com.arcforges.mobile", "io.github.arcforges.mobile", 1)
        with self.assertRaises(ValueError):
            identity.check_apk(wrong, CERTIFICATES, ROOT)

    def test_two_signers_are_refused(self):
        with self.assertRaises(ValueError):
            identity.check_apk(BADGING, CERTIFICATES + CERTIFICATES.replace("Signer #1", "Signer #2"), ROOT)


if __name__ == "__main__":
    unittest.main()
