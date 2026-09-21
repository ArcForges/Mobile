# SPDX-License-Identifier: Apache-2.0
"""Independent source and adversarial build-report tests; no device claims."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_identity as identity
import resources


class BuildIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'eng').mkdir()
        (self.root / 'app').mkdir()
        self.catalog = json.loads((identity.ROOT / 'eng/version-sources.json').read_text())
        (self.root / 'eng/version-sources.json').write_text(json.dumps(self.catalog))
        (self.root / 'app/gradle.lockfile').write_text('a:b:2.3.4=releaseRuntimeClasspath\na:b:8.0=testRuntimeClasspath\n')
        self.contract = json.dumps({'schema': 'arcforges.hello.v3', 'descriptorSha256': 'a' * 64,
                                    'commit': 'b' * 40, 'dirty': False, 'version': '9.8.7-ci.123.1'})
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.root, text=True,
                env={k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}).strip()
        git('init', '-q')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        self.commit = git('rev-parse', 'HEAD')
        self.ci = {'GITHUB_ACTIONS': 'true', 'GITHUB_SHA': self.commit, 'GITHUB_REPOSITORY': 'ArcForges/Mobile',
                   'GITHUB_SERVER_URL': 'https://github.com', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_NUMBER': '5',
                   'GITHUB_RUN_ATTEMPT': '2'}

    def axes(self, catalog=None):
        return identity.axes('0.1.0-ci.5.2', self.contract, self.root, catalog or self.catalog)

    def test_release_schema_and_packages_are_independent(self):
        axes = self.axes()
        self.assertEqual(set(axes), set(identity.AXES))
        self.assertEqual(axes['AppVersion']['values'][0]['version'], '0.1.0-ci.5.2')
        self.assertEqual(axes['ContractSet']['values'][0]['version'], '3')
        self.assertEqual(axes['PackageVersion']['values'][0]['version'], '2.3.4')
        self.assertEqual(len(axes['PackageVersion']['values']), 1)
        self.assertEqual(axes['NativeAbiVersion']['status'], 'not-applicable')

    def test_every_axis_has_an_independent_producer(self):
        catalog = copy.deepcopy(self.catalog)
        for name, kind in zip(identity.AXES, identity.KINDS):
            if kind in {'release', 'contracts', 'packages'}:
                continue
            path = name + ('.h' if kind == 'native-abi' else '.json')
            content = '#define ARC_ABI_MAJOR 4\n#define ARC_ABI_MINOR 2\n' if kind == 'native-abi' else json.dumps({
                'migrations' if kind == 'migrations' else 'versions': [{'subject': name, 'version': '7.2'}]})
            (self.root / path).write_text(content)
            catalog['axes'][name] = {'kind': kind, 'sources': [path]}
        axes = self.axes(catalog)
        self.assertTrue(all(axis['status'] == 'present' for axis in axes.values()))
        self.assertEqual(axes['NativeAbiVersion']['values'][0]['version'], '4.2')
        for name, kind in zip(identity.AXES, identity.KINDS):
            version, contract = '0.1.0-ci.5.2', self.contract
            path, original = None, None
            if kind == 'release':
                version = '0.2.0'
            elif kind == 'contracts':
                contract = self.contract.replace('hello.v3', 'hello.v4')
            else:
                path = self.root / catalog['axes'][name]['sources'][0]
                original = path.read_text()
                if kind == 'packages':
                    changed = original.replace('2.3.4', '2.3.5')
                elif kind == 'native-abi':
                    changed = original.replace('ARC_ABI_MINOR 2', 'ARC_ABI_MINOR 3')
                else:
                    changed = original.replace('7.2', '7.3')
                path.write_text(changed)
            try:
                actual = identity.axes(version, contract, self.root, catalog)
                with self.subTest(mutated=name):
                    self.assertEqual([axis for axis in identity.AXES if actual[axis] != axes[axis]], [name])
            finally:
                if path is not None:
                    path.write_text(original)

    def test_missing_alias_wrong_kind_and_duplicate_sources_fail(self):
        for name in identity.AXES:
            for mutation in ('missing', 'alias', 'kind'):
                catalog = copy.deepcopy(self.catalog)
                if mutation == 'missing':
                    del catalog['axes'][name]
                elif mutation == 'alias':
                    catalog['axes'][name]['alias'] = 'AppVersion'
                else:
                    catalog['axes'][name]['kind'] = 'wrong'
                with self.subTest(name=name, mutation=mutation), self.assertRaises(ValueError):
                    self.axes(catalog)
        catalog = copy.deepcopy(self.catalog)
        catalog['axes']['ContractSet']['sources'] *= 2
        with self.assertRaises(ValueError):
            self.axes(catalog)

    def test_absent_producer_and_path_escape_fail(self):
        catalog = copy.deepcopy(self.catalog)
        del catalog['axes']['StorageSchemaVersion']['producer']
        with self.assertRaises(ValueError):
            self.axes(catalog)
        catalog = copy.deepcopy(self.catalog)
        catalog['axes']['ContractSet']['sources'] = ['../escape']
        with self.assertRaises(ValueError):
            self.axes(catalog)

    def test_malformed_contract_receipt_fails(self):
        original = json.loads(self.contract)
        for key, value in [('schema', 'arcforges.hello'), ('dirty', True), ('descriptorSha256', 'version1')]:
            changed = {**original, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                identity.axes('0.1.0', json.dumps(changed), self.root)

    def test_ci_and_local_build_identity(self):
        actual = identity.build(self.root, self.ci)
        self.assertEqual(actual['buildId'], '123.2')
        self.assertFalse(actual['dirty'])
        self.assertEqual(identity.build(self.root, {})['buildId'], 'local.' + self.commit)
        for key, value in [('GITHUB_SHA', 'a' * 40), ('GITHUB_REPOSITORY', 'ArcForges/Other'),
                           ('GITHUB_RUN_ID', '0'), ('GITHUB_RUN_ATTEMPT', '0'), ('GITHUB_SERVER_URL', 'https://invalid')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                identity.build(self.root, {**self.ci, key: value})
        (self.root / 'dirty').write_text('change')
        with self.assertRaises(ValueError):
            identity.build(self.root, self.ci)
        self.assertTrue(identity.build(self.root, {})['dirty'])

    def test_resealed_report_and_every_axis_tamper_fail(self):
        approved = {'contractSourceText': self.contract}
        with patch.object(resources, 'profile', return_value=('fixture', 'digest', approved)), patch.dict(os.environ, self.ci):
            expected = identity.report('0.1.0-ci.5.2', 502, self.root)
            info = {'version_name': '0.1.0-ci.5.2', 'version_code': 502, 'commit': self.commit}
            identity.verify_report(json.dumps(expected).encode(), info, self.root)
            for name in identity.AXES:
                altered = copy.deepcopy(expected)
                altered['axes'][name] = {'status': 'present', 'values': []}
                with self.subTest(axis=name), self.assertRaises(ValueError):
                    identity.verify_report(json.dumps(altered).encode(), info, self.root)
            for key, value in [('sourceCommit', 'c' * 40), ('sourceDateEpoch', 1), ('buildId', '123.1')]:
                altered = copy.deepcopy(expected)
                altered['build'][key] = value
                with self.subTest(build=key), self.assertRaises(ValueError):
                    identity.verify_report(json.dumps(altered).encode(), info, self.root)
            with self.assertRaises(ValueError):
                identity.report('0.1.0-ci.5.2', 503, self.root)


if __name__ == '__main__':
    unittest.main()
