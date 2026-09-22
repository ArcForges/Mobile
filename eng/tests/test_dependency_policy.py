# SPDX-License-Identifier: Apache-2.0
"""Independent offline failure cases for dependency admission."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dependency_policy as policy


class DependencyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.admission = {'candidateExceptions': [], 'runtimeLicences': ['Apache-2.0', 'BSD-3-Clause', 'MIT']}
        self.closure = {'components': [{'id': 'example:library:1.2.3', 'spdxLicense': 'Apache-2.0',
                         'configurations': ['releaseRuntimeClasspath'], 'artifacts': {'library.jar': 'a' * 64},
                         'evidence': [{'url': 'https://example.invalid/source.pom', 'sha256': 'b' * 64}],
                         'notices': ['c' * 64]}], 'nativeFiles': {'native.so': 'd' * 64},
                        'nativeSourceEvidence': [{'url': 'https://example.invalid/+/{}'.format('e' * 40) + '/source.cpp',
                                                  'sha256': 'f' * 64}]}
        self.review = {'schemaVersion': 1, 'sourceCommit': '1' * 40, 'owner': 'Release Engineering Owner',
                       'maintenanceAssessment': 'Reviewed fixture only', 'versions': {'kotlin': '2.4.20'},
                       'inputs': {'lock': '2' * 64}, 'evidence': {key: {'status': 'not-applicable',
                       'reason': 'Synthetic fixture'} for key in policy.REQUIRED}}

    def test_admitted_fixture(self):
        policy.validate_android(self.closure, self.admission)

    def test_forbidden_license(self):
        self.closure['components'][0]['spdxLicense'] = 'GPL-3.0-only'
        with self.assertRaisesRegex(ValueError, 'Forbidden Android licence'):
            policy.validate_android(self.closure, self.admission)

    def test_instrumentation_license_cannot_enter_runtime(self):
        self.closure['components'][0]['spdxLicense'] = 'EPL-1.0'
        with self.assertRaisesRegex(ValueError, 'Forbidden Android licence'):
            policy.validate_android(self.closure, self.admission)

    def test_floating_tag_and_range(self):
        for version in ('latest', '1.+', '[1,2)', 'main', '1.0-SNAPSHOT'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                policy.exact_version(version)

    def test_wrong_publisher(self):
        with self.assertRaisesRegex(ValueError, 'Wrong publisher'):
            policy.validate_publisher({'repository': 'attacker/Mobile'})

    def test_wrong_repository_cannot_be_readmitted(self):
        settings = '''pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
        dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
        repositories { google(); mavenCentral() } }'''.replace(';', '')
        policy.validate_feeds(settings)
        with self.assertRaisesRegex(ValueError, 'Untrusted Gradle feed'):
            policy.validate_feeds(settings.replace('mavenCentral()', 'maven { url = uri("https://attacker.invalid") }', 1))

    def test_mutable_version_checksum(self):
        with self.assertRaisesRegex(ValueError, 'mutable version bytes'):
            policy.validate_review(self.review, self.review['versions'], {'lock': '9' * 64})

    def test_successor_cannot_reapprove_changed_bytes(self):
        previous = copy.deepcopy(self.closure)
        self.closure['components'][0]['artifacts']['library.jar'] = '9' * 64
        with self.assertRaisesRegex(ValueError, 'Immutable coordinate'):
            policy.validate_immutable(previous, self.closure)

    def test_new_coordinate_can_have_new_bytes(self):
        previous = copy.deepcopy(self.closure)
        self.closure['components'][0]['id'] = 'example:library:1.2.4'
        self.closure['components'][0]['artifacts']['library.jar'] = '9' * 64
        policy.validate_immutable(previous, self.closure)

    def test_successor_cannot_rename_immutable_payload(self):
        previous = copy.deepcopy(self.closure)
        self.closure['components'][0]['artifacts'] = {'replacement.jar': '9' * 64}
        with self.assertRaisesRegex(ValueError, 'Immutable coordinate'):
            policy.validate_immutable(previous, self.closure)

    def test_missing_upgrade_evidence(self):
        del self.review['evidence']['security']
        with self.assertRaisesRegex(ValueError, 'Missing upgrade evidence'):
            policy.validate_review(self.review, self.review['versions'], self.review['inputs'])

    def test_framework_major_requires_posture(self):
        previous = copy.deepcopy(self.review)
        self.review['versions']['kotlin'] = '3.0.0'
        with self.assertRaisesRegex(ValueError, 'framework major'):
            policy.validate_review(self.review, self.review['versions'], self.review['inputs'], previous)
        self.review['frameworkMajorReview'] = {'changed': ['kotlin'], 'owner': 'Architecture Owner',
            'kotlinArtR8': 'Fixture assessment', 'nativeModules': 'Fixture assessment',
            'transport': 'Fixture assessment', 'localCoverage': 'Not run; fixture only'}
        policy.validate_review(self.review, self.review['versions'], self.review['inputs'], previous)

    def test_internal_contract_is_not_public(self):
        self.closure['components'][0]['id'] = 'io.github.arcforges:ai-internal:1.2.3'
        with self.assertRaisesRegex(ValueError, 'Non-public Contracts'):
            policy.validate_android(self.closure, self.admission)

    def test_native_source_requires_commit(self):
        self.closure['nativeSourceEvidence'][0]['url'] = 'https://example.invalid/+/main/source.cpp'
        with self.assertRaisesRegex(ValueError, 'Floating native source'):
            policy.validate_android(self.closure, self.admission)


if __name__ == '__main__':
    unittest.main()
