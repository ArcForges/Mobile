#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise public-release validation with real candidate archives and disposable signatures."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from unittest.mock import patch

import mobile
import published
import resources


def main():
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        raise ValueError("Runtime/public-release checks are local opt-in only; forbidden in CI.")
    candidate = mobile.ROOT / 'artifacts/candidate'
    info = mobile.verify_candidate(candidate)
    with tempfile.TemporaryDirectory(prefix='mobile-public-fixture-') as temporary:
        root = Path(temporary)
        key, certificate, release = root / 'test.jks', root / 'certificate.der', root / 'release'
        password = secrets.token_hex(20)
        environment = dict(os.environ, ANDROID_KEYSTORE_PASSWORD=password, ANDROID_KEY_PASSWORD=password)
        subprocess.run(['keytool', '-genkeypair', '-keystore', str(key), '-storepass:env', 'ANDROID_KEYSTORE_PASSWORD',
                        '-keypass:env', 'ANDROID_KEY_PASSWORD', '-alias', 'test', '-keyalg', 'RSA', '-keysize', '3072',
                        '-validity', '2', '-dname', 'CN=Disposable public-release fixture'],
                       check=True, env=environment, capture_output=True)
        subprocess.run(['keytool', '-exportcert', '-keystore', str(key), '-storepass:env', 'ANDROID_KEYSTORE_PASSWORD',
                        '-alias', 'test', '-file', str(certificate)], check=True, env=environment, capture_output=True)
        fingerprint = hashlib.sha256(certificate.read_bytes()).hexdigest()
        environment.update(ANDROID_KEYSTORE_BASE64=base64.b64encode(key.read_bytes()).decode(),
                           ANDROID_KEY_ALIAS='test', ANDROID_SIGNING_CERT_SHA256=fingerprint)
        with patch.dict(os.environ, environment):
            mobile.sign_candidate(candidate, release)
        published.verify(release, candidate, fingerprint)
        # A disposable signature must never satisfy the persistent public identity.
        try:
            published.verify(release, candidate)
        except ValueError as error:
            resources.require('Persistent certificate changed' in str(error), 'Unexpected identity failure')
        else:
            raise AssertionError('Disposable identity accepted as persistent')
        # A rewritten outer release manifest cannot admit different source notices.
        name = 'THIRD_PARTY_NOTICES.txt'
        (release / name).write_bytes(b'changed public notice\n')
        manifest = resources.read_json(release / 'release.json')
        manifest['sha256'][name] = mobile.sha256(release / name)
        resources.save(release / 'release.json', manifest)
        checksums = ''.join(f'{mobile.sha256(release / name)}  {name}\n'
                            for name in sorted(set(manifest['sha256']) | {'release.json'}))
        (release / 'SHA256SUMS').write_text(checksums, encoding='utf-8', newline='\n')
        try:
            published.verify(release, candidate, fingerprint)
        except ValueError as error:
            resources.require('Changed public companion' in str(error), 'Unexpected public notice failure')
        else:
            raise AssertionError('Rehashed changed public notice accepted')
    resources.save(mobile.ROOT / 'artifacts/evidence/published-fixture.json', {
        'result': 'passed', 'commit': info['commit'], 'realApkAndAabSignatures': True,
        'disposableIdentityRejected': True, 'rehashedChangedPublicNoticeRejected': True})
    print('Real signed candidate fixture and independent public identity/notice failures passed.')


if __name__ == '__main__':
    main()
