#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the anonymously downloaded MAUI prerelease bytes against the sealed candidate (local opt-in only)."""
import argparse
import os
from pathlib import Path
import re
import urllib.request

import maui_notices
import mobile
import resources

CERTIFICATE = '7a8b3b1402e77c3ec78e7a0b9f99d5358adc321d0e8d2a319c838d1cda181e9c'
# AND.40: the MAUI prerelease track (tag android-VERSION, from PR B; the PR A releases under android-maui-VERSION stay
# verifiable through their own record). Its public members are the signed APK, its companions and the release seal;
# no AAB, idsig or Kotlin resource receipt is published on this track.
MAUI_TAG = 'android-'
MAUI_COMPANIONS = {'mapping.txt', 'THIRD_PARTY_NOTICES.txt', 'licence-closure.json', 'build-identity.json', 'maui-archive.json'}


def maui_release_names(version):
    return MAUI_COMPANIONS | {'ArcForges-' + version + '.apk'}


def maui_download(version, name, directory):
    resources.require(re.fullmatch(r'0\.1\.0-ci\.[0-9]+\.[0-9]+', version), 'Invalid public release version')
    resources.provenance.path(name)
    resources.require('/' not in name, 'Public release member must be a file')
    url = f'https://github.com/ArcForges/Mobile/releases/download/{MAUI_TAG}{version}/{name}'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(100_000_001)
    resources.require(len(data) <= 100_000_000, 'Oversized public release member')
    (directory / name).write_bytes(data)


def maui_verify(directory, candidate, expected_certificate=CERTIFICATE):
    """Verify the anonymously downloaded MAUI prerelease against the sealed MAUI candidate it was published from."""
    info = mobile.maui_verify_candidate(candidate)
    release = resources.read_json(directory / 'release.json')
    for key in ('commit', 'version_name', 'version_code', 'package'):
        resources.require(release[key] == info[key], 'MAUI release identity differs from the candidate')
    resources.require(release.get('track') == mobile.MAUI_TRACK and release.get('tag') == MAUI_TAG + info['version_name'],
                      'MAUI release is not on the android track')
    resources.require(release['candidate_sha256'] == info['sha256'], 'MAUI release points to another candidate')
    resources.require(release['certificate_sha256'] == expected_certificate, 'Persistent certificate changed')
    stem = 'ArcForges-' + info['version_name']
    names = maui_release_names(info['version_name'])
    resources.require(set(release['sha256']) == names and
                      {p.name for p in directory.iterdir()} == names | {'release.json', 'SHA256SUMS'},
                      'Unexpected MAUI release members')
    checksums = ''.join(f'{mobile.sha256(directory / name)}  {name}\n' for name in sorted(names | {'release.json'}))
    resources.require(sorted((directory / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()) ==
                      sorted(checksums.splitlines()), 'MAUI SHA256SUMS mismatch')
    for name in names:
        resources.require(mobile.sha256(directory / name) == release['sha256'][name], 'Changed MAUI release member: ' + name)
    for name in MAUI_COMPANIONS - {'maui-archive.json'}:
        resources.require((directory / name).read_bytes() == (candidate / name).read_bytes(), 'Changed MAUI companion: ' + name)
    apk = directory / (stem + '.apk')
    certificate = mobile.run(mobile.maui_sdk_tool('apksigner'), 'verify', '--verbose', '--print-certs', apk, capture=True)
    mobile.verify_certificate(certificate, expected_certificate)
    import maui_identity
    maui_identity.inspect_apk(apk, mobile.ROOT, release=True, configuration='Release')
    mobile.run(mobile.maui_sdk_tool('zipalign'), '-c', '-P', '16', '4', apk)
    maui_notices.apk_host_only(apk)  # decision 20: the public APK carries no gnu/binutils member
    # The release archive names the signed APK's digest and signer, so it is derived again from the public APK.
    resources.require(resources.read_json(directory / 'maui-archive.json') ==
                      resources.maui_archive(apk, directory / 'build-identity.json', mobile.ROOT, release=True),
                      'Public MAUI archive differs from the signed APK')
    return {**info, 'certificate_sha256': expected_certificate, 'public_sha256': release['sha256']}


def maui_prepare(directory, candidate):
    resources.require(not directory.exists(), 'Use a new public verification directory')
    directory.mkdir(parents=True)
    info = mobile.maui_verify_candidate(candidate)
    version = info['version_name']
    maui_download(version, 'release.json', directory)
    maui_download(version, 'SHA256SUMS', directory)
    for name in sorted(maui_release_names(version)):
        maui_download(version, name, directory)
    verified = maui_verify(directory, candidate)
    resources.save(directory.parent / 'public-maui-verification.json', {'result': 'passed', **verified})
    print('Verified the anonymously downloaded MAUI prerelease, persistent signature and every candidate payload.')


if __name__ == '__main__':
    if os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'):
        raise ValueError('Public download verification is local opt-in only; forbidden in CI.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['maui-prepare'])
    parser.add_argument('--directory', type=Path, default=mobile.ROOT / 'artifacts/public-release')
    parser.add_argument('--candidate', type=Path, default=mobile.ROOT / 'artifacts/maui-candidate')
    args = parser.parse_args()
    maui_prepare(args.directory, args.candidate)
