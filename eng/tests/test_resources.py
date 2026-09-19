# SPDX-License-Identifier: Apache-2.0
"""Adversarial resource tests use synthetic bytes and a real admitted Git fixture."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import resources
import check_provenance as provenance
import test_provenance as fixtures


def dex():
    data = bytearray(112)
    data[:8] = b'dex\n039\0'
    struct.pack_into('<I', data, 32, len(data))
    data[12:32] = hashlib.sha1(data[32:]).digest()
    struct.pack_into('<I', data, 8, zlib.adler32(data[12:]) & 0xffffffff)
    return bytes(data)


class ResourceGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mobile-resources-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {'GITHUB_EVENT_PATH': '', 'GITHUB_EVENT_NAME': ''})
        environment.start()
        self.addCleanup(environment.stop)
        self.fixture = fixtures.Fixture(self.root)
        self.fixture.write('.gitignore', b'output/\n')
        self.directory = self.root / 'output'
        self.id = 'synthetic-android-resources-r1'
        self.profile_path = 'eng/provenance/artifact-profiles/resources-r1.json'
        self.expected = {'schemaVersion': 1, 'recordId': self.id, 'ownedInputs': {}, 'inputs': {},
                         'excludedNames': ['forbidden.list'], 'excludedSha256': [resources.sha(b'excluded bytes')], 'archives': {}}
        self.payloads = {}
        for name in resources.ARCHIVES:
            prefix = 'base/' if name.endswith('.aab') else ''
            entries = {prefix + 'assets/' + asset: {'kind': 'receipt-asset'} for asset in resources.ASSETS}
            entries[prefix + 'fixed.txt'] = {'kind': 'fixed', 'sha256': resources.sha(b'reviewed')}
            contents = {prefix + 'fixed.txt': b'reviewed'}
            if name in resources.ARCHIVES[:2]:
                paths = (['base/dex/classes.dex', 'BUNDLE-METADATA/com.android.tools.build.profiles/baseline.prof',
                          'BUNDLE-METADATA/com.android.tools.build.profiles/baseline.profm'] if prefix else
                         ['classes.dex', 'assets/dexopt/baseline.prof', 'assets/dexopt/baseline.profm'])
                for path, data, kind in zip(paths, [dex(), b'pro\x00010\x00fixture', b'prm\x00002\x00fixture'], ['dex', 'art-profile', 'art-profile']):
                    entries[path] = {'kind': kind}
                    contents[path] = data
            self.expected['archives'][name] = {'members': entries, 'services': {}}
            self.payloads[name] = contents
        self.fixture.put(self.profile_path, self.expected)
        artifact = copy.deepcopy(self.fixture.value)
        artifact.update(id=self.id, kind='generated', targets=[], artifactTargets=[{
            'project': ':app', 'package': name, 'kind': 'android-archive', 'profile': self.profile_path,
            'sha256': resources.sha((self.root / self.profile_path).read_bytes())} for name in resources.ARCHIVES])
        source = {'repository': 'https://example.org/synthetic/resources', 'commit': 'a' * 40,
                  'paths': ['fixture.txt'], 'spdx': 'MIT', 'evidence': artifact['licence']['evidence']}
        artifact['generation'] = {'generators': [source], 'inputs': [source], 'command': 'Synthetic fixture only.', 'outputSpdx': 'MIT'}
        self.fixture.put(provenance.STORE + self.id + '.json', artifact)
        self.fixture.inventory()
        inventory = self.fixture.get(provenance.INVENTORY)
        inventory['artifacts'] = [self.id]
        self.fixture.put(provenance.INVENTORY, inventory)
        self.fixture.write(provenance.SUMMARY, provenance.render({self.id: artifact, self.fixture.value['id']: self.fixture.value},
                                                                {self.id, self.fixture.value['id']}))
        self.commit = self.fixture.commit()
        self.directory.mkdir()
        self.info = {'commit': self.commit, 'version_code': 101, 'version_name': '0.1.0-ci.1.1'}
        resources.save(self.directory / 'source-provenance.json', resources.source_receipt(self.root))
        (self.directory / 'licence-closure.json').write_bytes(b'{}\n')
        (self.directory / 'THIRD_PARTY_NOTICES.txt').write_text(provenance.package_notice(self.root), encoding='utf-8')
        (self.directory / 'mapping.txt').write_bytes(b'Example -> a:\n')
        for name in resources.ARCHIVES:
            prefix = 'base/' if name.endswith('.aab') else ''
            for asset in resources.ASSETS:
                self.payloads[name][prefix + 'assets/' + asset] = (self.directory / asset).read_bytes()
            self.write_archive(name)

    def write_archive(self, name):
        with zipfile.ZipFile(self.directory / name, 'w') as archive:
            for path, data in self.payloads[name].items():
                archive.writestr(path, data)

    def verify(self):
        return resources.verify_archives(self.directory, self.info, self.root)

    def test_all_real_members_have_source_bound_receipts(self):
        result = self.verify()
        self.assertEqual(self.commit, result['commit'])
        self.assertEqual(set(resources.ARCHIVES), set(result['archives']))
        for name, archive in result['archives'].items():
            self.assertEqual(set(self.payloads[name]), set(archive['members']))

    def test_recomputing_outer_hash_cannot_approve_changed_or_renamed_resources(self):
        for value in [b'changed after review', b'excluded bytes']:
            self.payloads['app-debug.apk']['fixed.txt'] = value
            self.write_archive('app-debug.apk')
            with self.assertRaisesRegex(ValueError, 'Changed reviewed resource|renamed excluded bytes'):
                self.verify()

    def test_unknown_and_missing_members_fail_closed(self):
        self.payloads['app-debug.apk']['unreviewed.js'] = b'unknown asset'
        self.write_archive('app-debug.apk')
        with self.assertRaisesRegex(ValueError, 'Unclassified or missing'):
            self.verify()
        del self.payloads['app-debug.apk']['unreviewed.js']
        del self.payloads['app-debug.apk']['fixed.txt']
        self.write_archive('app-debug.apk')
        with self.assertRaisesRegex(ValueError, 'Unclassified or missing'):
            self.verify()

    def test_archive_duplicates_collisions_and_traversal_fail(self):
        for path in ['fixed.txt', 'FIXED.txt', '../outside', '/outside']:
            self.write_archive('app-debug.apk')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with zipfile.ZipFile(self.directory / 'app-debug.apk', 'a') as archive:
                    archive.writestr(path, b'reviewed')
            with self.assertRaises(ValueError):
                self.verify()

    def test_stripped_source_and_notice_assets_fail(self):
        for asset in resources.ASSETS:
            path = 'assets/' + asset
            original = self.payloads['app-debug.apk'][path]
            self.payloads['app-debug.apk'][path] = b'stripped'
            self.write_archive('app-debug.apk')
            with self.assertRaisesRegex(ValueError, 'Changed source/notice asset'):
                self.verify()
            self.payloads['app-debug.apk'][path] = original

    def test_wrong_commit_and_modified_profile_or_used_record_fail(self):
        self.info['commit'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'clean source'):
            self.verify()
        self.info['commit'] = self.commit
        self.expected['ownedInputs'] = {'unreviewed': '0' * 64}
        self.fixture.put(self.profile_path, self.expected)
        with self.assertRaisesRegex(ValueError, 'Changed Android resource profile'):
            self.verify()

    def test_dex_replacement_and_inconsistent_companions_fail(self):
        self.payloads['app-release-unsigned.apk']['classes.dex'] = b'not a DEX file'
        self.write_archive('app-release-unsigned.apk')
        with self.assertRaisesRegex(ValueError, 'DEX header'):
            self.verify()
        data = bytearray(dex())
        data[90] = 1
        with self.assertRaisesRegex(ValueError, 'DEX payload'):
            resources.verify_dex(data)

    def test_signing_may_only_add_signature_members(self):
        candidate = self.directory / 'app-debug.apk'
        signed = self.directory / 'signed.apk'
        signed.write_bytes(candidate.read_bytes())
        with zipfile.ZipFile(signed, 'a') as archive:
            archive.writestr('META-INF/TEST.SF', b'synthetic signing metadata')
        result = resources.signed_payload(candidate, signed)
        self.assertEqual(['META-INF/TEST.SF'], result['signatureMembers'])
        with zipfile.ZipFile(signed, 'a') as archive:
            archive.writestr('assets/surprise', b'not signing metadata')
        with self.assertRaisesRegex(ValueError, 'Unexpected signed'):
            resources.signed_payload(candidate, signed)

    def test_hook_git_selection_cannot_change_source_repository(self):
        with patch.dict(os.environ, {'GIT_DIR': str(self.directory / 'missing'), 'GIT_WORK_TREE': str(self.directory),
                                    'GIT_INDEX_FILE': str(self.directory / 'wrong-index')}):
            self.assertEqual('passed', self.verify()['result'])

    def test_legal_label_cannot_hide_code_or_mismatched_content_name(self):
        value = copy.deepcopy(self.fixture.value)
        value['kind'] = 'legal-text'
        value['licence']['copyingPermission'] = 'Synthetic legal-text test permission.'
        for path in ['vendor/notices/implementation.txt', 'third-party/notices/' + '0' * 64 + '.txt', 'src/notice_helper.py']:
            value['targets'][0]['path'] = path
            with self.assertRaises(ValueError):
                provenance.record(value, 'Apache')
        for licence in ['MPL-2.0', 'EPL-1.0']:
            value = copy.deepcopy(self.fixture.value)
            value['licence'].update(spdx=licence, category=provenance.LICENCES[licence])
            with self.assertRaisesRegex(ValueError, 'Prohibited implementation'):
                provenance.record(value, 'Apache')


if __name__ == '__main__':
    unittest.main()
