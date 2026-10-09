#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Shared JSON helpers and the MAUI archive gate. The Kotlin archive resource gates retire with the Kotlin baseline (AND.40 PR B)."""
import hashlib
import json
from pathlib import Path
import zipfile

import check_provenance as provenance

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def read_json(path):
    return provenance.document(path.read_bytes())


# AND.40 unit 5: the MAUI archive gate. A built MAUI APK must carry the reviewed identity, must embed the
# build-identity.json of its own build, and its native libraries must be 16 KB aligned (zipalign -c -P 16 4 is run
# by the caller). The release flag adds the persistent certificate check of maui_identity.check_apk.
#
# Embedding is proven in two places. On the build side, every linked ArcForges.Mobile.dll (one per Android runtime
# identifier, the assemblies the APK packs) holds the identity bytes verbatim. In the APK, the assembly store holds
# the report's schema line verbatim. The store is compressed, so the identity bytes are not decoded from it here; the
# decoded comparison is recorded as not run. Without an assemblies root (the publish job, which has no build
# outputs) only the APK check runs, and the caller relies on the candidate-stage record.
MAUI_STORE_MARKER = b'"schema": "arcforges.build-identity.v1"'


def maui_archive(apk, identity_path, root=ROOT, release=False, assemblies_root=None):
    import maui_identity
    apk = Path(apk)
    expected = Path(identity_path).read_bytes()
    report = maui_identity.inspect_apk(apk, root, release=release, configuration='Release')
    il_assemblies = []
    if assemblies_root is not None:
        linked = sorted(Path(assemblies_root).glob('*/linked/ArcForges.Mobile.dll'))
        require(linked, 'No linked ArcForges.Mobile assembly was found for the identity proof')
        for path in linked:
            require(expected in path.read_bytes(),
                    'A linked ArcForges.Mobile assembly does not embed build-identity.json: ' + path.parent.parent.name)
        il_assemblies = [path.parent.parent.name for path in linked]
    with zipfile.ZipFile(apk) as archive:
        members = [name for name in archive.namelist() if not name.endswith('/')]
        stores = [name for name in members if name.endswith('libassembly-store.so')]
        require(stores, 'The APK has no assembly store')
        marked = sorted(name for name in stores if MAUI_STORE_MARKER in archive.read(name))
    require(marked, 'The APK assembly store does not carry the release build identity (decision 14)')
    return {'schemaVersion': 1, 'result': 'passed', 'release': release,
            'apkSha256': sha(apk.read_bytes()), 'members': len(members),
            'ilAssemblies': il_assemblies, 'apkStoreMarkerIn': marked,
            'decodedIdentityCompared': False,
            'identity': report['identity'], 'signerSha256': report['signerSha256']}
