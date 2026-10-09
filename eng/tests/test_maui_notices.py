# SPDX-License-Identifier: Apache-2.0
"""AND.40 unit 4: the MAUI closure listing, the F-023-class re-proof, the notice gate and the MAUI licence audit."""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ENG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENG))

import licences  # noqa: E402
import maui_notices  # noqa: E402

ROOT = ENG.parent
FILES = [
    maui_notices.LOCK,
    maui_notices.ADMISSION,
    maui_notices.TEST_ADMISSION,
    maui_notices.DISTRIBUTION,
    maui_notices.NOTICE_DATA,
    maui_notices.TOOLCHAIN,
    maui_notices.WORKLOADS,
    maui_notices.MARKDOWN,
]


class FixtureRoot:
    """A temporary copy of the reviewed MAUI records, so each negative test mutates one file only."""

    def __init__(self):
        self.directory = Path(tempfile.mkdtemp(prefix="maui-notices-"))
        for relative in FILES:
            target = self.directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        shutil.copytree(ROOT / "third-party" / "notices", self.directory / "third-party" / "notices")

    def path(self, relative):
        return self.directory / relative

    def edit_json(self, relative, mutate):
        target = self.path(relative)
        value = json.loads(target.read_text(encoding="utf-8"))
        mutate(value)
        target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")

    def close(self):
        shutil.rmtree(self.directory, ignore_errors=True)


class MauiClosureTests(unittest.TestCase):
    def test_the_repository_closure_and_reproof_pass(self):
        report = maui_notices.closure(ROOT)
        proof = maui_notices.reproof(ROOT)

        self.assertEqual(report["lockedPackages"], 121)
        self.assertEqual(report["buildOnly"], sorted(maui_notices.BUILD_ONLY))
        self.assertEqual(proof["result"], "passed")
        self.assertEqual(proof["shipped"], 118)
        self.assertEqual(proof["testOnlyInShipped"], [])
        self.assertEqual(proof["agplInShipped"], [])

    def test_every_locked_package_is_listed_with_licence_and_source(self):
        rows = maui_notices.closure(ROOT)["rows"]
        packages = [row for row in rows if row["kind"] != "project"]

        self.assertEqual(len(packages), 121)
        self.assertTrue(all(row["licence"] and row["source"] == maui_notices.NUGET_SOURCE for row in packages))
        self.assertEqual([row["id"] for row in rows if row["kind"] == "project"], ["arcforges.mobile.network"])

    def test_a_build_task_classified_as_shipped_is_refused(self):
        fixture = FixtureRoot()
        try:
            fixture.edit_json(maui_notices.DISTRIBUTION, lambda value: value["packages"][
                [item["id"] for item in value["packages"]].index("Microsoft.NET.ILLink.Tasks")].update({"class": "shipped"}))

            with self.assertRaisesRegex(ValueError, "build-only"):
                maui_notices.reproof(fixture.directory)
        finally:
            fixture.close()

    def test_a_test_only_package_in_the_closure_is_refused(self):
        fixture = FixtureRoot()
        try:
            fixture.edit_json(maui_notices.TEST_ADMISSION, lambda value: value["packages"].append(
                {"id": "Xamarin.AndroidX.Core", "version": "1.16.0.3", "kind": "transitive", "licence": "MIT AND Apache-2.0"}))

            with self.assertRaisesRegex(ValueError, "test-only package in the shipped closure: Xamarin.AndroidX.Core"):
                maui_notices.reproof(fixture.directory)
        finally:
            fixture.close()

    def test_a_test_only_package_without_a_classification_is_refused(self):
        fixture = FixtureRoot()
        try:
            fixture.edit_json(maui_notices.DISTRIBUTION, lambda value: value.update(
                testOnly=[item for item in value["testOnly"] if item["id"] != "ArcForges.Contracts.Validation"]))

            with self.assertRaisesRegex(ValueError, "unclassified test-only package: ArcForges.Contracts.Validation"):
                maui_notices.reproof(fixture.directory)
        finally:
            fixture.close()

    def test_the_naming_policy_package_is_test_only_and_never_shipped(self):
        report = maui_notices.closure(ROOT)
        test_only = {row["id"]: row for row in report["testOnly"]}
        shipped = {row["id"] for row in report["rows"] if row.get("distribution") == "shipped"}

        self.assertEqual(test_only["ArcForges.Contracts.Validation"]["distribution"], "test-only")
        self.assertEqual(test_only["ArcForges.Contracts.Validation"]["version"], "1.0.0-ci.205.1")
        self.assertEqual(test_only["ArcForges.Sdk.Contracts"]["distribution"], "test-only")
        self.assertNotIn("ArcForges.Contracts.Validation", shipped)
        self.assertNotIn("ArcForges.Sdk.Contracts", shipped)
        self.assertEqual(maui_notices.reproof(ROOT)["testOnlyInShipped"], [])

    def test_a_desktop_platform_package_is_refused(self):
        fixture = FixtureRoot()
        try:
            fixture.edit_json(maui_notices.DISTRIBUTION, lambda value: value["packages"].append(
                {"id": "ArcForges.DesktopPlatform.Core", "class": "shipped", "reason": "Fixture."}))

            with self.assertRaisesRegex(ValueError, "classified but not locked|DesktopPlatform"):
                maui_notices.reproof(fixture.directory)
        finally:
            fixture.close()


class MauiNoticeGateTests(unittest.TestCase):
    def test_the_repository_notice_gate_passes(self):
        result = maui_notices.check(ROOT)

        self.assertEqual(result["result"], "passed")
        self.assertIn("linux-licence-evidence", result["pending"])
        self.assertEqual(result["escalated"], ["workload-bundles-bsd-2-clause"])

    def test_a_changed_retained_notice_is_refused(self):
        fixture = FixtureRoot()
        try:
            retained = json.loads((fixture.directory / maui_notices.NOTICE_DATA).read_text(encoding="utf-8"))["notices"][0]
            notice = fixture.path(retained["path"])
            notice.write_bytes(notice.read_bytes() + b"x\n")

            with self.assertRaisesRegex(ValueError, "Retained notice changed|does not match its digest"):
                maui_notices.check(fixture.directory)
        finally:
            fixture.close()

    def test_a_package_without_a_licence_file_needs_its_retained_notice(self):
        fixture = FixtureRoot()
        try:
            fixture.edit_json(maui_notices.NOTICE_DATA, lambda value: value["packages"].pop("Google.Protobuf"))

            with self.assertRaisesRegex(ValueError, "Google.Protobuf|no retained notice|deferral"):
                maui_notices.check(fixture.directory)
        finally:
            fixture.close()

    def test_the_linux_licence_evidence_cannot_be_dropped(self):
        fixture = FixtureRoot()
        try:
            fixture.edit_json(maui_notices.NOTICE_DATA, lambda value: value.update({"pending": []}))

            with self.assertRaisesRegex(ValueError, "Linux licence evidence"):
                maui_notices.check(fixture.directory)
        finally:
            fixture.close()

    def test_a_stale_markdown_block_is_refused(self):
        fixture = FixtureRoot()
        try:
            markdown = fixture.path(maui_notices.MARKDOWN)
            markdown.write_text(markdown.read_text(encoding="utf-8").replace("Open notice obligations", "Obligations"), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "stale"):
                maui_notices.check(fixture.directory)
        finally:
            fixture.close()

    def test_the_rendered_block_is_deterministic(self):
        self.assertEqual(maui_notices.render(ROOT), maui_notices.render(ROOT))


class MauiLicenceAuditTests(unittest.TestCase):
    def test_the_repository_maui_closure_is_admitted(self):
        report = licences.maui_closure_audit(ROOT)

        self.assertEqual(report["result"], "passed")
        self.assertEqual(report["packages"], 121)
        self.assertEqual(report["target"], "net10.0-android36.1")

    def test_a_second_target_is_refused(self):
        fixture = FixtureRoot()
        try:
            lock = fixture.path(maui_notices.LOCK)
            value = json.loads(lock.read_text(encoding="utf-8"))
            value["dependencies"]["net10.0"] = {}
            lock.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")

            with self.assertRaisesRegex(ValueError, "net10.0-android only"):
                licences.maui_closure_audit(fixture.directory)
        finally:
            fixture.close()

    def test_a_forbidden_licence_is_refused(self):
        fixture = FixtureRoot()
        try:
            fixture.edit_json(maui_notices.ADMISSION, lambda value: value["packages"][0].update({"licence": "AGPL-3.0-only"}))

            with self.assertRaisesRegex(ValueError, "Forbidden MAUI licence|differs|Unadmitted"):
                licences.maui_closure_audit(fixture.directory)
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
