# SPDX-License-Identifier: Apache-2.0
"""Offline dependency admission; actual Android artifact checks remain in licences.py."""
import hashlib
import json
import os
import re
import subprocess
import tomllib
from urllib.parse import urlsplit

from licences import ROOT, git, read_json, require, save

POLICY = 'eng/policy/dependency-policy.json'
REVIEWS = 'eng/policy/dependency-reviews'
SHA = re.compile(r'[0-9a-f]{64}')
PUBLIC = {'io.github.arcforges:contracts-proto', 'io.github.arcforges:contracts-connect-client'}
FEEDS = {'https://dl.google.com/dl/android/maven2/', 'https://repo.maven.apache.org/maven2/',
         'https://plugins.gradle.org/m2/'}
REQUIRED = {'compilation', 'licence-provenance', 'security', 'closure-sbom', 'compatibility',
            'local-runtime', 'performance', 'migration'}


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def input_paths(root):
    names = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split('\0')
    return sorted({p for p in names if p and (p.endswith(('.lockfile', '.gradle.kts')) or p in {
        'gradle/libs.versions.toml', 'gradle/verification-metadata.xml', 'gradle.properties',
        'gradle/wrapper/gradle-wrapper.properties', '.java-version', '.python-version',
        '.github/workflows/ci.yml', '.github/workflows/security.yml',
        'eng/policy/android-licences.json', 'eng/policy/reuse-policy.json',
        'eng/policy/licence-boundary.json'})})


def exact_version(version, candidate=False):
    require(isinstance(version, str) and re.fullmatch(r'\d+(?:\.\d+)*(?:-[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*)?', version),
            f'Floating or invalid version: {version}')
    require('-' not in version or candidate, f'Unadmitted prerelease: {version}')


def current_versions(root):
    versions = dict(tomllib.loads((root / 'gradle/libs.versions.toml').read_text())['versions'])
    versions['java'] = (root / '.java-version').read_text().strip()
    wrapper = (root / 'gradle/wrapper/gradle-wrapper.properties').read_text()
    match = re.search(r'/gradle-(\d+(?:\.\d+)+)-bin\.zip', wrapper)
    require(match, 'Invalid Gradle distribution version')
    versions['gradle'] = match.group(1)
    return versions


def validate_publisher(publisher):
    require(publisher == {'repository': 'ArcForges/Mobile', 'workflow': '.github/workflows/ci.yml',
                         'environment': 'android-release', 'ref': 'refs/heads/main', 'event': 'push'},
            'Wrong publisher identity')


def validate_feeds(settings):
    settings = re.sub(r'/\*.*?\*/|//[^\r\n]*', '', settings, flags=re.S)
    blocks = re.findall(r'\brepositories\s*\{([^{}]*)\}', settings)
    declared = [re.sub(r'\s+', '', block) for block in blocks]
    require(len(re.findall(r'\brepositories\s*\{', settings)) == 2 and
            declared == ['google()mavenCentral()gradlePluginPortal()', 'google()mavenCentral()'],
            'Untrusted Gradle feed declaration')
    require('RepositoriesMode.FAIL_ON_PROJECT_REPOS' in settings, 'Project repository override permitted')


def validate_review(review, versions, inputs, previous=None):
    require(review['schemaVersion'] == 1 and re.fullmatch(r'[0-9a-f]{40}', review['sourceCommit']), 'Invalid review source')
    require(review['owner'] == 'Release Engineering Owner' and review['maintenanceAssessment'].strip(), 'Missing maintenance owner/review')
    require(review['inputs'] == inputs and review['versions'] == versions, 'Unreviewed dependency input or mutable version bytes')
    require(set(review['evidence']) == REQUIRED, 'Missing upgrade evidence')
    for item in review['evidence'].values():
        require(item['status'] in {'retained', 'required-ci', 'not-applicable', 'not-run'} and item['reason'].strip(),
                'Invalid evidence disposition')
    if previous:
        changed = {key for key, value in versions.items() if previous['versions'].get(key, '').split('.')[0] != value.split('.')[0]}
        if changed:
            posture = review.get('frameworkMajorReview', {})
            require(set(posture.get('changed', [])) == changed and posture.get('owner') == 'Architecture Owner' and
                    all(posture.get(key, '').strip() for key in ('kotlinArtR8', 'nativeModules', 'transport', 'localCoverage')),
                    'Missing framework major runtime-posture review')


def validate_android(closure, policy):
    require(closure['components'], 'Empty Android closure')
    seen = set()
    for item in closure['components']:
        coordinate = item['id']
        require(coordinate not in seen, 'Duplicate Android component')
        seen.add(coordinate)
        group, name, version = coordinate.split(':')
        first_party = group == 'io.github.arcforges'
        if first_party:
            require(group + ':' + name in PUBLIC, 'Non-public Contracts dependency')
        exact_version(version, coordinate in policy['candidateExceptions'])
        license_id = item['spdxLicense']
        require(license_id in policy['runtimeLicences'] or
                (license_id == 'EPL-1.0' and set(item['configurations']) == {'debugAndroidTestRuntimeClasspath'}),
                'Forbidden Android licence: ' + license_id)
        # Gradle metadata/BOM nodes have no binary; the existing resolved gate
        # compares the exact artifact set, including those empty metadata nodes.
        require(all(SHA.fullmatch(x) for x in item['artifacts'].values()), 'Invalid artifact checksum')
        require(item['evidence'] and item['notices'], 'Missing licence/source evidence')
        for evidence in item['evidence']:
            require(urlsplit(evidence['url']).scheme == 'https', 'Insecure source evidence')
            require((evidence.get('kind') == 'release-source-link' and coordinate == 'androidx.graphics:graphics-path:1.0.1') or
                    SHA.fullmatch(evidence.get('sha256', '')), 'Unbound source evidence')
    require(set(policy['candidateExceptions']) <= seen, 'Stale candidate exception')
    require(closure['nativeSourceEvidence'] and closure['nativeFiles'], 'Missing existing native admission')
    for source in closure['nativeSourceEvidence']:
        require(SHA.fullmatch(source['sha256']) and re.search(r'/\+/[0-9a-f]{40}/', source['url']),
                'Floating native source tag')


def validate_immutable(previous, current):
    before = {item['id']: item['artifacts'] for item in previous['components']}
    after = {item['id']: item['artifacts'] for item in current['components']}
    require(all(after[name] == value for name, value in before.items() if name in after),
            'Immutable coordinate checksum changed across reviews')


def check(root=ROOT):
    policy = read_json(root / POLICY)
    require(policy['schemaVersion'] == 1 and policy['repository'] == 'Mobile' and policy['licenceBoundary'] == 'Apache',
            'Invalid dependency policy owner')
    require(set(policy['feeds']) == FEEDS and set(policy['publicPackages']) == PUBLIC, 'Wrong feed or import authority')
    require(policy['runtimeLicences'] == ['Apache-2.0', 'BSD-3-Clause', 'MIT'], 'Changed runtime licence admission')
    validate_publisher(policy['publisher'])
    validate_feeds((root / 'settings.gradle.kts').read_text())
    versions = current_versions(root)
    for key, value in versions.items():
        exact_version(value, key == 'contracts' and any(x.endswith(':' + value) for x in policy['candidateExceptions']))
    paths = input_paths(root)
    inputs = {p: digest(root / p) for p in paths}
    reviews = []
    historical = set(git(root, 'log', '--diff-filter=A', '--format=', '--name-only', '--', REVIEWS).splitlines()) - {''}
    require(all((root / p).is_file() for p in historical), 'Deleted retained dependency review')
    require(len(policy['reviews']) == len(set(policy['reviews'])), 'Duplicate dependency review')
    require(set(policy['reviews']) == {p.name for p in (root / REVIEWS).glob('*.json')}, 'Dropped retained review')
    for name in policy['reviews']:
        require(re.fullmatch(r'[a-z0-9-]+\.json', name), 'Invalid review path')
        path = f'{REVIEWS}/{name}'
        reviews.append(read_json(root / path))
        # Existing accepted records may only be superseded, never rewritten.
        commits = git(root, 'log', '--diff-filter=A', '--format=%H', '--', path).splitlines()
        if commits:
            original = subprocess.check_output(['git', 'show', f'{commits[-1]}:{path}'], cwd=root)
            require(original.replace(b'\r\n', b'\n') == (root / path).read_bytes().replace(b'\r\n', b'\n'),
                    'Changed retained dependency review')
    require(reviews, 'Missing dependency review')
    for index, review in enumerate(reviews):
        validate_review(review, review['versions'], review['inputs'], reviews[index - 1] if index else None)
    validate_review(reviews[-1], versions, inputs, reviews[-2] if len(reviews) > 1 else None)
    require(policy['stage'] == 'candidate', 'Stable Android production not admitted by this foundation policy')
    closure = read_json(root / 'eng/policy/android-licences.json')
    validate_android(closure, policy)
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    for review in reviews:
        path = 'eng/policy/android-licences.json'
        original = subprocess.check_output(['git', 'show', review['sourceCommit'] + ':' + path], cwd=root, env=environment)
        require(hashlib.sha256(original.replace(b'\r\n', b'\n')).hexdigest() == review['inputs'][path],
                'Review source does not bind admitted Android closure')
        validate_immutable(json.loads(original), closure)
    for name in paths:
        if name.endswith('.lockfile'):
            for line in (root / name).read_text().splitlines():
                if line and not line.startswith(('#', 'empty=')):
                    coordinate = line.split('=', 1)[0]
                    pieces = coordinate.split(':')
                    require(len(pieces) == 3, 'Invalid locked coordinate')
                    exact_version(pieces[2], coordinate in policy['candidateExceptions'] or coordinate in policy['toolPrereleaseExceptions'])
                    if pieces[0] == 'io.github.arcforges':
                        require(':'.join(pieces[:2]) in PUBLIC, 'Non-public first-party import')
    for directory in ('app/src', 'shared/src'):
        for source in (root / directory).rglob('*.kt'):
            require(not re.search(r'^\s*import\s+(?:io\.github\.)?arcforges\.(?:\w+\.)*(?:internal|cloudinternal|localrpc)\b',
                                  source.read_text(), re.M | re.I), 'Internal generated import in public Mobile')
    workflow = (root / policy['publisher']['workflow']).read_text()
    require('environment: android-release' in workflow and "github.ref == 'refs/heads/main'" in workflow and
            "github.event_name == 'push'" in workflow, 'Publisher workflow no longer matches policy')
    return {'schemaVersion': 1, 'repository': 'Mobile', 'result': 'passed', 'review': policy['reviews'][-1],
            'inputCount': len(inputs), 'androidComponents': len(closure['components']),
            'coverage': 'Offline policy; actual artifact/licence/resource checks remain in the existing Gradle candidate gate.'}


if __name__ == '__main__':
    result = check()
    save(ROOT / 'artifacts/evidence/dependency-policy.json', result)
    print(json.dumps(result))
