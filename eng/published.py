#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify public release bytes and exercise an upgrade with the persistent identity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

import mobile
import resources

CERTIFICATE = '7a8b3b1402e77c3ec78e7a0b9f99d5358adc321d0e8d2a319c838d1cda181e9c'
BASELINE_VERSION = '0.1.0-ci.9.1'
BASELINE_APK = 'ac9af161ad9db56ab7ce578651631be1f779edd64f9488089c8b60f3dc0dcf47'
COMPANIONS = {'mapping.txt', 'THIRD_PARTY_NOTICES.txt', 'licence-closure.json',
              'source-provenance.json', 'resource-provenance.json', 'build-identity.json'}


def release_names(version):
    stem = 'ArcForges-' + version
    return COMPANIONS | {stem + '.apk', stem + '.aab', stem + '.apk.idsig', 'signed-resource-provenance.json'}


def download(version, name, directory):
    resources.require(re.fullmatch(r'0\.1\.0-ci\.[0-9]+\.[0-9]+', version), 'Invalid public release version')
    resources.provenance.path(name)
    resources.require('/' not in name, 'Public release member must be a file')
    url = f'https://github.com/ArcForges/Mobile/releases/download/android-{version}/{name}'
    # No GitHub token: this proves anonymous availability of the published asset.
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(100_000_001)
    resources.require(len(data) <= 100_000_000, 'Oversized public release member')
    (directory / name).write_bytes(data)


def verify(directory, candidate, expected_certificate=CERTIFICATE):
    info = mobile.verify_candidate(candidate)
    release = resources.read_json(directory / 'release.json')
    for key in ('commit', 'version_name', 'version_code', 'package'):
        resources.require(release[key] == info[key], 'Public release identity differs from candidate')
    resources.require(release['candidate_sha256'] == info['sha256'], 'Public release points to another candidate')
    resources.require(release['certificate_sha256'] == expected_certificate, 'Persistent certificate changed')
    stem = 'ArcForges-' + info['version_name']
    names = release_names(info['version_name'])
    resources.require(set(release['sha256']) == names and
                      {p.name for p in directory.iterdir()} == names | {'release.json', 'SHA256SUMS'},
                      'Unexpected public release members')
    checksums = ''.join(f'{mobile.sha256(directory / name)}  {name}\n' for name in sorted(names | {'release.json'}))
    # pathlib orders Windows filenames case-insensitively; require the exact
    # closed checksum entries independently of that harmless host ordering.
    resources.require(sorted((directory / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()) ==
                      sorted(checksums.splitlines()), 'Public SHA256SUMS mismatch')
    for name in names:
        resources.require(mobile.sha256(directory / name) == release['sha256'][name], 'Changed public release member: ' + name)
    for name in COMPANIONS:
        resources.require((directory / name).read_bytes() == (candidate / name).read_bytes(), 'Changed public companion: ' + name)
    apk, bundle = directory / (stem + '.apk'), directory / (stem + '.aab')
    certificate = mobile.run(mobile.sdk_tool('apksigner'), 'verify', '--verbose', '--print-certs', apk, capture=True)
    mobile.verify_certificate(certificate, expected_certificate)
    mobile.inspect_apk(apk, info)
    mobile.run(mobile.sdk_tool('zipalign'), '-c', '-P', '16', '4', apk)
    resources.require('jar verified.' in mobile.run('jarsigner', '-verify', bundle, capture=True), 'Invalid public AAB signature')
    preserved = {'schemaVersion': 1, 'commit': info['commit'], 'result': 'passed',
                 'apk': resources.signed_payload(candidate / 'app-release-unsigned.apk', apk),
                 'aab': resources.signed_payload(candidate / 'app-release.aab', bundle)}
    resources.require(resources.read_json(directory / 'signed-resource-provenance.json') == preserved,
                      'Public signing receipt differs from actual payloads')
    return {**info, 'certificate_sha256': expected_certificate, 'public_sha256': release['sha256']}


def prepare(directory, candidate):
    resources.require(not directory.exists(), 'Use a new public verification directory')
    directory.mkdir(parents=True)
    info = mobile.verify_candidate(candidate)
    version = info['version_name']
    download(version, 'release.json', directory)
    download(version, 'SHA256SUMS', directory)
    release = resources.read_json(directory / 'release.json')
    resources.require(set(release['sha256']) == release_names(version), 'Unexpected public download members')
    for name in sorted(release_names(version)):
        download(version, name, directory)
    verified = verify(directory, candidate)
    baseline = directory.parent / 'public-upgrade-baseline'
    baseline.mkdir()
    name = f'ArcForges-{BASELINE_VERSION}.apk'
    download(BASELINE_VERSION, name, baseline)
    resources.require(mobile.sha256(baseline / name) == BASELINE_APK, 'Changed immutable public upgrade baseline')
    mobile.verify_certificate(mobile.run(mobile.sdk_tool('apksigner'), 'verify', '--verbose', '--print-certs', baseline / name, capture=True), CERTIFICATE)
    resources.save(directory.parent / 'public-verification.json', {'result': 'passed', **verified,
                   'baseline': {'version': BASELINE_VERSION, 'sha256': BASELINE_APK}})
    print('Verified anonymously downloaded release, persistent signature and every candidate payload.')


def parse_identity(dump):
    resources.require(len(re.findall(r'^\s*Package \[' + re.escape(mobile.PACKAGE) + r'\]', dump, re.M)) == 1,
                      'Missing or ambiguous installed package')
    result = {}
    # API 26 calls the application ID userId; API 36 calls it appId. This
    # reader is restricted to user 0, where that value is also the package UID.
    for key, pattern in [('uid', r'^\s*(?:userId|appId)=(\d+)\s*$'),
                         ('firstInstallTime', r'^\s*firstInstallTime=(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*$'),
                         ('versionCode', r'^\s*versionCode=(\d+)\b')]:
        matches = re.findall(pattern, dump, re.M)
        resources.require(len(matches) == 1, 'Missing or ambiguous installed identity: ' + key)
        result[key] = matches[0]
    return result


def installed_identity(serial, output):
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
    adb = sdk / 'platform-tools' / ('adb.exe' if os.name == 'nt' else 'adb')
    def command(*args):
        return subprocess.check_output([str(adb), '-s', serial, *map(str, args)], timeout=90).decode('utf-8')
    resources.require(command('shell', 'am', 'get-current-user').strip() == '0', 'Upgrade requires emulator user 0')
    dump = command('shell', 'dumpsys', 'package', mobile.PACKAGE)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dump, encoding='utf-8')
    return parse_identity(dump)


def upgrade(directory, candidate, serial):
    info = verify(directory, candidate)
    resources.require(info['version_code'] > 901, 'Public upgrade must increase the version code')
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
    adb = sdk / 'platform-tools' / ('adb.exe' if os.name == 'nt' else 'adb')
    output = directory.parent / 'public-device'
    baseline = directory.parent / 'public-upgrade-baseline' / f'ArcForges-{BASELINE_VERSION}.apk'
    resources.require(mobile.sha256(baseline) == BASELINE_APK, 'Changed public upgrade baseline')
    subprocess.run([str(adb), '-s', serial, 'install', str(baseline)], check=True, timeout=90)
    before = installed_identity(serial, output / 'before-package.txt')
    resources.require(before['versionCode'] == '901', 'Unexpected installed baseline')
    apk = directory / f'ArcForges-{info["version_name"]}.apk'
    subprocess.run([sys.executable, str(mobile.ROOT / 'eng/device-smoke.py'), str(apk), '--serial', serial,
                    '--output', str(output)], check=True)
    after = installed_identity(serial, output / 'after-package.txt')
    resources.require(before['uid'] == after['uid'] and before['firstInstallTime'] == after['firstInstallTime'] and
                      after['versionCode'] == str(info['version_code']), 'Public upgrade lost installed identity')
    resources.save(output / 'upgrade.json', {'result': 'passed', 'commit': info['commit'], 'serial': serial,
                   'before': before, 'after': after, 'certificate_sha256': CERTIFICATE,
                   'publishedApkSha256': mobile.sha256(apk)})
    print('Public persistent-signature upgrade preserved installation and called real Cloud.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'identity', 'upgrade'])
    parser.add_argument('--directory', type=Path, default=mobile.ROOT / 'artifacts/public-release')
    parser.add_argument('--candidate', type=Path, default=mobile.ROOT / 'artifacts/candidate')
    parser.add_argument('--serial', default='emulator-5554')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.directory, args.candidate)
    elif args.command == 'identity':
        identity = installed_identity(args.serial, mobile.ROOT / 'artifacts/device/package.txt')
        info = mobile.verify_candidate(args.candidate)
        resources.require(identity['versionCode'] == str(info['version_code']), 'Installed candidate version differs')
        resources.save(mobile.ROOT / 'artifacts/device/installed-identity.json', identity)
    else:
        upgrade(args.directory, args.candidate, args.serial)
