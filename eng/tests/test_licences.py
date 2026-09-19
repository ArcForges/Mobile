# SPDX-License-Identifier: Apache-2.0
"""Reject unreviewed source, resolved binaries, native payloads and stripped notices."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import licences


class LicenceGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mobile-licence-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=self.environment)
        # This fixture exercises the independent dependency gate. Resource/source
        # adversarial tests use complete fixtures in test_resources/test_provenance.
        mock = patch.object(licences.resources, 'check_resolved_inputs', return_value={'result': 'fixture'})
        mock.start()
        self.addCleanup(mock.stop)
        mock = patch.object(licences.check_provenance, 'package_notice', return_value='source notice fixture\n')
        mock.start()
        self.addCleanup(mock.stop)
        self.write('.gitignore', 'artifacts/\nbuild/\n')
        self.write('build.gradle.kts', 'extra["spdxLicense"] = "Apache-2.0"\nextra["licenceBoundary"] = "Apache"\n')
        self.write('eng/policy/licence-boundary.json', {'schemaVersion': 1, 'repository': 'Mobile',
                   'spdxLicense': 'Apache-2.0', 'licenceBoundary': 'Apache',
                   'projects': [{'path': 'build.gradle.kts', 'kind': 'gradle'}]})
        self.write('app/gradle.lockfile', 'example:library:1.0=releaseRuntimeClasspath\n')
        self.write('gradle/libs.versions.toml', '[versions]\nexample="1.0"\n')
        self.notice = 'Copyright Example authors\nApache licence fixture\n'
        self.notice_hash = licences.digest(self.notice.encode())
        self.write('third-party/notices/' + self.notice_hash + '.txt', self.notice)
        self.archive = self.root / 'artifacts/library-1.0.jar'
        self.archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('META-INF/NOTICE', self.notice)
        self.sha = licences.digest(self.archive.read_bytes())
        self.write('gradle/verification-metadata.xml', f'<verification-metadata><sha256 value="{self.sha}" /></verification-metadata>')
        self.policy = {'schemaVersion': 1, 'components': [{'id': 'example:library:1.0',
                       'spdxLicense': 'Apache-2.0', 'configurations': sorted(licences.CONFIGURATIONS - {'coreLibraryDesugaring'}),
                       'artifacts': {self.archive.name: self.sha}, 'evidence': [{'url': 'https://example.invalid/library.pom'}],
                       'notices': [self.notice_hash]}], 'nativeFiles': {}, 'nativeSourceEvidence': [], 'nativeSystemDependencies': []}
        self.write('eng/policy/android-licences.json', self.policy)
        self.write('artifacts/evidence/licence-gradle.json', [{'path': ':', 'spdxLicense': 'Apache-2.0', 'licenceBoundary': 'Apache', 'references': []}])
        self.resolved = [{'configuration': name, 'modules': [] if name == 'coreLibraryDesugaring' else [{'id': 'example:library:1.0', 'dependencies': []}],
                         'artifacts': [] if name == 'coreLibraryDesugaring' else [{'id': 'example:library:1.0', 'file': str(self.archive)}]}
                         for name in sorted(licences.CONFIGURATIONS)]
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True, env=self.environment)
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'reviewed fixture'], cwd=self.root, check=True, env=self.environment)

    def write(self, name, value):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8', newline='\n')

    def verify(self):
        return licences.verify_closure(self.resolved, self.root)

    def test_clean_closure_keeps_notice_and_does_not_modify_resolution(self):
        original = copy.deepcopy(self.resolved)
        result = self.verify()
        self.assertFalse(result['dirty'])
        self.assertEqual(original, self.resolved)
        self.assertIn(self.notice, (self.root / 'build/generated/licence-assets/THIRD_PARTY_NOTICES.txt').read_text())

    def test_new_project_and_missing_declaration_are_rejected(self):
        self.write('new/build.gradle.kts', '// not registered\n')
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            self.verify()
        (self.root / 'new/build.gradle.kts').unlink()
        self.write('build.gradle.kts', 'extra["spdxLicense"] = "Apache-2.0"\n')
        with self.assertRaisesRegex(ValueError, 'licenceBoundary'):
            self.verify()

    def test_wrong_boundary_and_first_party_dependency_are_rejected(self):
        self.write('app/gradle.lockfile', 'io.github.arcforges:desktop-platform:1=releaseRuntimeClasspath\n')
        with self.assertRaisesRegex(ValueError, 'first-party dependency'):
            self.verify()
        self.write('app/gradle.lockfile', '')
        self.write('build.gradle.kts', 'extra["spdxLicense"] = "AGPL-3.0-only"\nextra["licenceBoundary"] = "Apache"\n')
        with self.assertRaisesRegex(ValueError, 'spdxLicense'):
            self.verify()

    def test_effective_override_or_external_project_edge_is_rejected(self):
        for declaration in [{'path': ':', 'spdxLicense': 'AGPL-3.0-only', 'licenceBoundary': 'AGPL', 'references': []},
                            {'path': ':', 'spdxLicense': 'Apache-2.0', 'licenceBoundary': 'Apache', 'references': [':outside']}]:
            self.write('artifacts/evidence/licence-gradle.json', [declaration])
            with self.assertRaisesRegex(ValueError, 'effective Gradle'):
                self.verify()

    def test_gpl_unknown_and_test_only_licences_are_rejected_from_runtime(self):
        for value in ['GPL-2.0-only WITH Classpath-exception-2.0', 'UNKNOWN', 'EPL-1.0']:
            self.policy['components'][0]['spdxLicense'] = value
            self.write('eng/policy/android-licences.json', self.policy)
            with self.assertRaises(ValueError):
                self.verify()

    def test_unknown_closure_and_unresolved_edge_are_rejected(self):
        self.resolved[1]['modules'].append({'id': 'unexpected:dependency:1', 'dependencies': []})
        with self.assertRaisesRegex(ValueError, 'dependency closure'):
            self.verify()
        self.resolved[1]['modules'].pop()
        self.resolved[1]['modules'][0]['dependencies'] = ['unexpected:dependency:1']
        with self.assertRaisesRegex(ValueError, 'dependency edge'):
            self.verify()

    def test_core_library_implementation_remains_excluded_even_if_reviewed(self):
        self.policy['components'][0]['configurations'].append('coreLibraryDesugaring')
        self.write('eng/policy/android-licences.json', self.policy)
        self.resolved[0]['modules'] = copy.deepcopy(self.resolved[1]['modules'])
        self.resolved[0]['artifacts'] = copy.deepcopy(self.resolved[1]['artifacts'])
        with self.assertRaisesRegex(ValueError, 'Excluded core-library implementation'):
            self.verify()

    def test_identical_duplicate_artifact_is_allowed_but_changed_bytes_fail(self):
        self.resolved[1]['artifacts'].append(copy.deepcopy(self.resolved[1]['artifacts'][0]))
        self.verify()
        replacement = self.root / 'artifacts/changed' / self.archive.name
        replacement.parent.mkdir()
        replacement.write_bytes(b'changed bytes')
        self.resolved[1]['artifacts'][-1]['file'] = str(replacement)
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            self.verify()

    def test_missing_binary_checksum_and_notice_are_rejected(self):
        self.write('gradle/verification-metadata.xml', '<verification-metadata />')
        with self.assertRaisesRegex(ValueError, 'strict Gradle checksum'):
            self.verify()
        self.write('gradle/verification-metadata.xml', f'<verification-metadata><sha256 value="{self.sha}" /></verification-metadata>')
        self.write('third-party/notices/' + self.notice_hash + '.txt', 'notice stripped')
        with self.assertRaisesRegex(ValueError, 'notice changed'):
            self.verify()

    def test_unreviewed_native_payload_is_rejected_even_when_jar_hash_matches(self):
        with zipfile.ZipFile(self.archive, 'a') as archive:
            archive.writestr('jni/x86_64/libunexpected.so', b'unreviewed native implementation')
        sha = licences.digest(self.archive.read_bytes())
        self.policy['components'][0]['artifacts'][self.archive.name] = sha
        self.write('eng/policy/android-licences.json', self.policy)
        self.write('gradle/verification-metadata.xml', f'<verification-metadata><sha256 value="{sha}" /></verification-metadata>')
        with self.assertRaisesRegex(ValueError, 'native dependency closure'):
            self.verify()

    def test_candidate_requires_retained_assets_and_original_policy(self):
        report = self.verify()
        directory = self.root / 'build/generated/licence-assets'
        for name in ['app-release-unsigned.apk', 'app-release.aab', 'app-debug.apk', 'app-debug-androidTest.apk']:
            prefix = 'base/' if name.endswith('.aab') else ''
            with zipfile.ZipFile(directory / name, 'w') as archive:
                for asset in ['THIRD_PARTY_NOTICES.txt', 'licence-closure.json']:
                    archive.writestr(prefix + 'assets/' + asset, (directory / asset).read_bytes())
        licences.verify_distribution(directory, report['commit'], self.root)
        with zipfile.ZipFile(directory / 'app-release-unsigned.apk', 'a') as archive:
            archive.writestr('lib/x86_64/unreviewed.so', b'unreviewed implementation')
        with self.assertRaisesRegex(ValueError, 'native payload'):
            licences.verify_distribution(directory, report['commit'], self.root)
        with zipfile.ZipFile(directory / 'app-release-unsigned.apk', 'w') as archive:
            for asset in ['THIRD_PARTY_NOTICES.txt', 'licence-closure.json']:
                archive.writestr('assets/' + asset, (directory / asset).read_bytes())
            archive.writestr('classes.dex', b'fixture with Lj$/util/Optional;')
        with self.assertRaisesRegex(ValueError, 'Excluded core-library'):
            licences.verify_distribution(directory, report['commit'], self.root)
        with zipfile.ZipFile(directory / 'app-release-unsigned.apk', 'w') as archive:
            archive.writestr('assets/THIRD_PARTY_NOTICES.txt', 'notices were stripped')
        with self.assertRaisesRegex(ValueError, 'packaged licence asset'):
            licences.verify_distribution(directory, report['commit'], self.root)
        self.write('app/gradle.lockfile', 'different resolved closure\n')
        with self.assertRaisesRegex(ValueError, 'locks changed'):
            licences.verify_distribution(directory, report['commit'], self.root)

    def test_same_named_native_binary_cannot_be_replaced(self):
        payload = b'reviewed native fixture bytes'
        self.policy['nativeFiles'] = {'example:library:1.0/jni/x86_64/libexample.so': licences.digest(payload)}
        self.write('eng/policy/android-licences.json', self.policy)
        # Construct the distribution receipt from the existing reviewed fixture;
        # this case isolates the final-archive native hash check from resolution.
        report = {'commit': licences.git(self.root, 'rev-parse', 'HEAD'), 'dirty': False, 'result': 'passed',
                  'policySha256': licences.digest(licences.text_bytes(self.root / 'eng/policy/android-licences.json')),
                  'locks': {p: licences.digest(licences.text_bytes(self.root / p)) for p in licences.LOCKS},
                  'artifacts': {'example:library:1.0/' + self.archive.name: self.sha}}
        directory = self.root / 'artifacts/candidate'
        self.write('artifacts/candidate/licence-closure.json', report)
        self.write('artifacts/candidate/THIRD_PARTY_NOTICES.txt', 'example:library:1.0 — Apache-2.0\n' + self.notice)
        for name in ['app-release-unsigned.apk', 'app-release.aab', 'app-debug.apk', 'app-debug-androidTest.apk']:
            prefix = 'base/' if name.endswith('.aab') else ''
            with zipfile.ZipFile(directory / name, 'w') as archive:
                for asset in ['THIRD_PARTY_NOTICES.txt', 'licence-closure.json']:
                    archive.writestr(prefix + 'assets/' + asset, (directory / asset).read_bytes())
                archive.writestr(prefix + 'lib/x86_64/libexample.so', payload)
        licences.verify_distribution(directory, report['commit'], self.root)
        target = directory / 'app-debug.apk'
        with zipfile.ZipFile(target) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        contents['lib/x86_64/libexample.so'] = b'changed under the same file name'
        with zipfile.ZipFile(target, 'w') as archive:
            for name, content in contents.items():
                archive.writestr(name, content)
        with self.assertRaisesRegex(ValueError, 'changed or missing native payload'):
            licences.verify_distribution(directory, report['commit'], self.root)


if __name__ == '__main__':
    unittest.main()
