# SPDX-License-Identifier: Apache-2.0
"""Offline tests for the MAUI path of eng/build_identity.py (AND.40 decision 14)."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ENG = Path(__file__).resolve().parents[1]
ROOT = ENG.parent
sys.path.insert(0, str(ENG))

import build_identity  # noqa: E402

LOCAL = {"sourceCommit": "a" * 40, "dirty": False, "kind": "local", "buildId": "local." + "a" * 40,
         "runId": None, "runAttempt": None, "pipelineRun": None, "sourceDateEpoch": 1700000000}
CI = {"sourceCommit": "b" * 40, "dirty": False, "kind": "ci", "buildId": "123.2",
      "runId": "123", "runAttempt": 2, "pipelineRun": "https://github.com/ArcForges/Mobile/actions/runs/123",
      "sourceDateEpoch": 1700000000}

LOCK = {
    "version": 2,
    "dependencies": {
        build_identity.MAUI_LOCK_TARGET: {
            "Microsoft.Maui.Controls": {"type": "Direct", "requested": "[10.0.20, )", "resolved": "10.0.20",
                                         "contentHash": "x"},
            "Grpc.Core.Api": {"type": "Transitive", "resolved": "2.84.0", "contentHash": "x"},
            "arcforges.mobile.network": {"type": "Project"},
        },
    },
}


class MauiPackagesTests(unittest.TestCase):
    def make_root(self, lock):
        root = Path(tempfile.mkdtemp(prefix="maui-identity-test-"))
        lock_path = root / build_identity.MAUI_LOCK
        lock_path.parent.mkdir(parents=True)
        lock_path.write_bytes(json.dumps(lock, indent=2).replace("\n", "\r\n").encode("utf-8"))
        return root

    def test_closure_lists_resolved_packages_only_and_is_sorted(self):
        root = self.make_root(LOCK)
        packages = build_identity.maui_packages(root)
        self.assertEqual([item["subject"] for item in packages], ["Grpc.Core.Api", "Microsoft.Maui.Controls"])
        self.assertEqual({item["subject"]: item["version"] for item in packages},
                         {"Microsoft.Maui.Controls": "10.0.20", "Grpc.Core.Api": "2.84.0"})

    def test_lock_source_is_bound_over_lf_bytes(self):
        root = self.make_root(LOCK)
        packages = build_identity.maui_packages(root)
        evidence = packages[0]["source"]
        self.assertEqual(evidence["path"], build_identity.MAUI_LOCK)
        content = (root / build_identity.MAUI_LOCK).read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(evidence["sha256"], build_identity.hashlib.sha256(content).hexdigest())

    def test_missing_android_closure_is_refused(self):
        root = self.make_root({"version": 2, "dependencies": {"net10.0": {"A": {"type": "Direct", "resolved": "1.0.0"}}}})
        with self.assertRaisesRegex(ValueError, "no net10.0-android36.1 closure"):
            build_identity.maui_packages(root)

    def test_closure_without_resolved_packages_is_refused(self):
        root = self.make_root({"version": 2, "dependencies": {build_identity.MAUI_LOCK_TARGET: {"P": {"type": "Project"}}}})
        with self.assertRaisesRegex(ValueError, "no resolved package"):
            build_identity.maui_packages(root)

    def test_malformed_locked_version_is_refused(self):
        root = self.make_root({"version": 2, "dependencies": {build_identity.MAUI_LOCK_TARGET: {
            "P": {"type": "Direct", "resolved": "1.0.0 beta"}}}})
        with self.assertRaisesRegex(ValueError, "Malformed locked version"):
            build_identity.maui_packages(root)


class MauiReportTests(unittest.TestCase):
    def report(self, identity=None, observed="10.0.400", environment=None, version="0.1.0-ci.123.2", code=12302):
        return build_identity.maui_report(version, code, ROOT, environment=environment,
                                          identity=identity if identity is not None else LOCAL,
                                          observed_sdk=observed)

    def test_report_has_the_fields_the_build_information_view_reads(self):
        data = self.report()
        self.assertEqual(data["schema"], "arcforges.build-identity.v1")
        self.assertEqual(data["owner"], "Mobile")
        self.assertEqual(data["artifact"], {"id": "com.arcforges.mobile", "version": "0.1.0-ci.123.2"})
        self.assertEqual(data["packaging"], {"androidVersionCode": 12302})
        for key in ("sourceCommit", "buildId", "kind", "dirty", "sourceDateEpoch", "pipelineRun"):
            self.assertIn(key, data["build"])
        for name, axis in data["axes"].items():
            self.assertIn(axis["status"], {"present", "not-applicable", "not-produced"}, name)
            self.assertTrue("values" in axis or "reason" in axis, name)

    def test_package_axis_is_the_nuget_closure_not_the_kotlin_lock(self):
        values = self.report()["axes"]["PackageVersion"]
        self.assertEqual(values["status"], "present")
        subjects = {item["subject"] for item in values["values"]}
        self.assertIn("Microsoft.Maui.Controls", subjects)
        self.assertNotIn("app/gradle.lockfile", json.dumps(values))
        self.assertTrue(all(item["source"]["path"] == build_identity.MAUI_LOCK for item in values["values"]))

    def test_toolchain_records_pins_and_source_inputs(self):
        toolchain = self.report()["toolchain"]
        self.assertEqual(toolchain["sdk"], {"pinned": "10.0.400", "rollForward": "disable", "observed": "10.0.400"})
        self.assertEqual(toolchain["workloads"]["android"]["manifestVersion"], "36.1.69")
        self.assertEqual(toolchain["workloads"]["maui-android"]["manifestVersion"], "10.0.20")
        self.assertEqual(toolchain["android"]["applicationId"], "com.arcforges.mobile")
        self.assertEqual(toolchain["android"]["targetPlatformVersion"], "36.1")
        self.assertEqual(toolchain["maui"]["linkToolCondition"], "Release")
        paths = [item["path"] for item in toolchain["sourceInputs"]]
        self.assertEqual(paths, list(build_identity.MAUI_SOURCE_INPUTS))
        for item in toolchain["sourceInputs"]:
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
        sdk_input = [item for item in toolchain["sourceInputs"] if item["path"] == "global.json"][0]
        self.assertEqual(sdk_input["source"], "HEAD")  # the committed pin, independent of the local SDK adapter

    def test_ci_build_must_run_the_pinned_sdk(self):
        env = {"GITHUB_RUN_NUMBER": "123", "GITHUB_RUN_ATTEMPT": "2"}
        with self.assertRaisesRegex(ValueError, "pinned SDK"):
            self.report(identity=CI, observed="10.0.401", environment=env)
        self.assertEqual(self.report(identity=CI, observed="10.0.400", environment=env)["build"]["kind"], "ci")

    def test_ci_version_must_match_the_allocated_run(self):
        env = {"GITHUB_RUN_NUMBER": "123", "GITHUB_RUN_ATTEMPT": "2"}
        with self.assertRaisesRegex(ValueError, "allocated CI version"):
            self.report(identity=CI, observed="10.0.400", environment=env, version="0.1.0-ci.124.2")
        with self.assertRaisesRegex(ValueError, "allocated CI version"):
            self.report(identity=CI, observed="10.0.400", environment=env, code=12301)

    def test_local_build_may_run_the_windows_adapter_sdk(self):
        data = self.report(observed="10.0.401")
        self.assertEqual(data["toolchain"]["sdk"]["observed"], "10.0.401")
        self.assertEqual(data["toolchain"]["sdk"]["pinned"], "10.0.400")

    def test_malformed_identity_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Malformed"):
            self.report(identity=dict(LOCAL, sourceCommit="xyz"))

    def test_packaged_identity_must_equal_the_checkout(self):
        data = self.report()
        raw = (json.dumps(data, indent=2) + "\n").encode("utf-8")
        info = {"version_name": "0.1.0-ci.123.2", "version_code": 12302, "commit": "a" * 40}
        with self.assertRaisesRegex(ValueError, "differs from the checkout"):
            build_identity.verify_maui_report(raw, info, ROOT, observed_sdk="10.0.401")
        tampered = dict(data, packaging={"androidVersionCode": 1})
        with self.assertRaisesRegex(ValueError, "differs from the checkout"):
            build_identity.verify_maui_report((json.dumps(tampered) + "\n").encode("utf-8"),
                                              dict(info, version_code=1), ROOT, observed_sdk="10.0.401")


class BuildInformationContractTests(unittest.TestCase):
    def test_the_csharp_view_names_the_same_schema_and_owner(self):
        source = (ROOT / "src/ArcForges.Mobile/Diagnostics/BuildInformation.cs").read_text(encoding="utf-8")
        self.assertIn('Schema = "arcforges.build-identity.v1"', source)
        self.assertIn('Owner = "Mobile"', source)
        self.assertIn('ResourceName = "build-identity.json"', source)

    def test_no_embedded_text_is_only_for_debug(self):
        source = (ROOT / "src/ArcForges.Mobile/Diagnostics/BuildInformation.cs").read_text(encoding="utf-8")
        self.assertIn("#if DEBUG", source)
        debug_branch = source.split("#if DEBUG", 1)[1].split("#else", 1)[0]
        release_branch = source.split("#else", 1)[1].split("#endif", 1)[0]
        self.assertIn("NotEmbeddedDebug", debug_branch)
        self.assertIn("ReleaseMissing", release_branch)
        self.assertNotIn("No build identity is embedded", release_branch)


if __name__ == "__main__":
    unittest.main()
