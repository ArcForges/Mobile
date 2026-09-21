#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify Android archive resources against an admitted, immutable source profile."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zipfile
import zlib

import check_provenance as provenance

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = ('app-release-unsigned.apk', 'app-release.aab')
ASSETS = ('THIRD_PARTY_NOTICES.txt', 'licence-closure.json', 'source-provenance.json')


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


def profile(root=ROOT):
    inventory = read_json(root / provenance.INVENTORY)
    require(len(inventory['artifacts']) == 1, 'Expected one reviewed Android resource profile')
    record_id = inventory['artifacts'][0]
    record = read_json(root / provenance.STORE / (record_id + '.json'))
    targets = record['artifactTargets']
    admitted = {t['package'] for t in targets}
    require(set(ARCHIVES) <= admitted, 'Incomplete artifact record targets')
    require(len({(t['profile'], t['sha256']) for t in targets}) == 1, 'Ambiguous artifact profile')
    path = targets[0]['profile']
    raw = provenance.read(root, path).replace(b'\r\n', b'\n')
    require(sha(raw) == targets[0]['sha256'], 'Changed Android resource profile')
    data = provenance.document(raw)
    require(data['schemaVersion'] == 1 and data['recordId'] == record_id and
            set(data['archives']) == admitted, 'Invalid Android resource profile')
    return record_id, targets[0]['sha256'], data


def verify_profile_history(root=ROOT):
    """Keep the bytes behind every retained admission immutable after supersession."""
    for path in sorted((root / provenance.STORE).glob('*.json')):
        for target in read_json(path)['artifactTargets']:
            raw = provenance.read(root, target['profile']).replace(b'\r\n', b'\n')
            require(sha(raw) == target['sha256'], 'Changed retained resource profile: ' + target['profile'])


def source_receipt(root=ROOT):
    audit = provenance.run(root, 'Mobile')
    verify_profile_history(root)
    record_id, digest, approved = profile(root)
    for path, expected in {**approved['ownedInputs'], **approved.get('ownedRecipes', {})}.items():
        require(sha(provenance.read(root, path).replace(b'\r\n', b'\n')) == expected,
                'Changed resource generation input: ' + path)
    records = {name: sha(provenance.read(root, provenance.STORE + name + '.json').replace(b'\r\n', b'\n'))
               for name in audit['activeRecords']}
    return {'schemaVersion': 1, 'evidenceClass': 'reviewed-android-resource-inputs',
            'commit': audit['sourceCommit'], 'dirty': audit['dirty'], 'recordId': record_id,
            'profileSha256': digest, 'records': records, 'sourceNoticeSha256': audit['noticeSha256']}


def check_resolved_inputs(resolved, root=ROOT):
    """Use the actual resolved artifacts; never learn resource hashes from an output archive."""
    receipt = source_receipt(root)
    _, _, approved = profile(root)
    observed = {}
    for configuration in resolved:
        for artifact in configuration['artifacts']:
            path = Path(artifact['file'])
            key = artifact['id'] + '/' + path.name
            data = path.read_bytes()
            require(key in approved['inputs'] and sha(data) == approved['inputs'][key]['sha256'],
                    'Unreviewed resource input artifact: ' + key)
            observed[key] = sha(data)
    require(set(observed) == set(approved['inputs']), 'Missing resource input artifact')
    return receipt


def archive_members(path):
    result = {}
    with zipfile.ZipFile(path) as archive:
        folded = set()
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            name = entry.filename
            provenance.path(name)
            require(name.casefold() not in folded, 'Duplicate or case-colliding archive member: ' + name)
            require((entry.external_attr >> 16) & 0o170000 != 0o120000, 'Linked archive member: ' + name)
            require(not entry.flag_bits & 1 and entry.file_size < 100_000_000, 'Encrypted or oversized archive member')
            folded.add(name.casefold())
            result[name] = archive.read(entry)
    return result


def varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        require(offset < len(data), 'Truncated protobuf varint')
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise ValueError('Oversized protobuf varint')


def protobuf_fields(data):
    offset = 0
    result = []
    while offset < len(data):
        start = offset
        tag, offset = varint(data, offset)
        number, wire = tag >> 3, tag & 7
        require(number > 0, 'Invalid protobuf field')
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire in {1, 2, 5}:
            if wire == 2:
                size, offset = varint(data, offset)
            else:
                size = 8 if wire == 1 else 4
            require(offset + size <= len(data), 'Truncated protobuf field')
            value = data[offset:offset + size]
            offset += size
        else:
            raise ValueError('Unsupported protobuf wire type')
        result.append((number, wire, value, data[start:offset]))
    return result


def source_pool(data):
    """Decode AAPT's UTF-8 source-path string pool, including every path and padding byte."""
    require(len(data) >= 28, 'Truncated source string pool')
    kind, header, size, count, styles, flags, start, style_start = struct.unpack_from('<HHIIIIII', data)
    require((kind, header, size, styles, flags, style_start) == (1, 28, len(data), 0, 256, 0)
            and start == 28 + count * 4, 'Unexpected source string-pool structure')
    paths = []
    cursor = start
    for index in range(count):
        offset = struct.unpack_from('<I', data, 28 + index * 4)[0] + start
        require(offset == cursor, 'Noncanonical source pool offset')
        def length(position):
            require(position < len(data), 'Truncated string length')
            value = data[position]
            if value & 128:
                require(position + 1 < len(data), 'Truncated string length')
                return ((value & 127) << 8) | data[position + 1], position + 2
            return value, position + 1
        chars, offset = length(offset)
        size, offset = length(offset)
        require(offset + size < len(data) and data[offset + size] == 0, 'Invalid source path string')
        text = data[offset:offset + size].decode('utf-8')
        require(len(text.encode('utf-16-le')) // 2 == chars, 'Incorrect source path length')
        text = text.replace('\\', '/')
        text = re.sub(r'gradleHome-[0-9]+:/caches/9\.7\.1/transforms/[0-9a-f]{32}/transformed/',
                      'gradle/transformed/', text)
        text = re.sub(r'(io\.github\.arcforges\.mobile\.app-[A-Za-z]+)-[0-9]+:/', r'\1:/', text)
        paths.append(text)
        cursor = offset + size + 1
    require(len(data) - cursor < 4 and not any(data[cursor:]), 'Unexpected source pool trailer')
    return paths


def resource_table_identity(data):
    fields = protobuf_fields(data)
    require([n for n, _, _, _ in fields].count(1) == 1, 'Missing/duplicate resource source pool')
    pool = next(value for n, _, value, _ in fields if n == 1)
    inner = protobuf_fields(pool)
    require(len(inner) == 1 and inner[0][:2] == (1, 2), 'Unknown source-pool field')
    return {'tableSha256': sha(b''.join(raw for n, _, _, raw in fields if n != 1)),
            'sourcePaths': source_pool(inner[0][2])}


def class_mapping(data):
    values = {}
    for line in data.decode('utf-8').splitlines():
        if line and not line.startswith((' ', '#')):
            match = re.fullmatch(r'(\S+) -> (\S+):', line)
            require(match is not None and match[1] not in values, 'Invalid/duplicate R8 class mapping')
            values[match[1]] = match[2]
    require(values, 'Missing R8 class mapping')
    return values


def service_mapping(service, providers, mapping):
    # The independently retained ci.9.1 R8 output merges this one interface into
    # its sole Android implementation. Every other missing type remains an error.
    merged = 'kotlinx.coroutines.internal.MainDispatcherFactory'
    implementation = 'kotlinx.coroutines.android.AndroidDispatcherFactory'
    if service not in mapping and service == merged and providers == [implementation]:
        service = implementation
    require(service in mapping and all(value in mapping for value in providers), 'Unmapped service resource')
    return mapping[service], ('\n'.join(mapping[p] for p in providers) + '\n').encode()


def aapt2():
    sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    require(sdk, 'Set ANDROID_HOME for actual Android resource verification')
    tool = Path(sdk) / 'build-tools/37.0.0' / ('aapt2.exe' if os.name == 'nt' else 'aapt2')
    require(tool.is_file(), 'Install reviewed Android Build-Tools 37.0.0')
    return tool


def manifest_identity(file, info, test=False):
    with tempfile.TemporaryDirectory(prefix='mobile-manifest-') as scratch:
        source = file
        if file.suffix == '.aab':
            # Convert the actual bundle's proto manifest/resource table, without rebuilding it.
            source = Path(scratch) / 'binary.apk'
            proto = Path(scratch) / 'proto.ap_'
            with zipfile.ZipFile(file) as archive, zipfile.ZipFile(proto, 'w') as output:
                output.writestr('AndroidManifest.xml', archive.read('base/manifest/AndroidManifest.xml'))
                output.writestr('resources.pb', archive.read('base/resources.pb'))
                for member in archive.namelist():
                    if member.startswith('base/res/') and not member.endswith('/'):
                        output.writestr(member.removeprefix('base/'), archive.read(member))
            subprocess.run([str(aapt2()), 'convert', '--output-format', 'binary', '-o', str(source), str(proto)], check=True, capture_output=True)
        output = subprocess.check_output([str(aapt2()), 'dump', 'xmltree', str(source), '--file', 'AndroidManifest.xml'], text=True, encoding='utf-8')
    if not test:
        code = str(info['version_code'])
        name = info['version_name']
        namespace = r'A: http://schemas\.android\.com/apk/res/android:'
        pattern = '(' + namespace + r'versionCode\(0x0101021b\)=)' + re.escape(code) + r'(?=\s|$)'
        output, count = re.subn(pattern, r'\1{VERSION_CODE}', output)
        require(count == 1, 'Manifest versionCode differs from candidate')
        line = f'"{name}" (Raw: "{name}")'
        output, count = re.subn('(' + namespace + r'versionName\(0x0101021c\)=)' + re.escape(line), r'\1{VERSION_NAME}', output)
        require(count == 1, 'Manifest versionName differs from candidate')
    return sha(output.replace('\r\n', '\n').encode())


def verify_dex(data):
    require(len(data) >= 112 and re.fullmatch(b'dex\n0[0-9]{2}\x00', data[:8]), 'Invalid DEX header')
    require(struct.unpack_from('<I', data, 32)[0] == len(data), 'Incorrect DEX length')
    require(struct.unpack_from('<I', data, 8)[0] == zlib.adler32(data[12:]) & 0xffffffff and
            data[12:32] == hashlib.sha1(data[32:]).digest(), 'Changed DEX payload/checksum')


def asset_paths(data):
    paths = []
    for number, wire, value, _ in protobuf_fields(data):
        require((number, wire) == (1, 2), 'Unexpected assets table field')
        fields = protobuf_fields(value)
        require(len(fields) == 2 and fields[0][:2] == (1, 2) and fields[1][:3] == (2, 2, b''), 'Unexpected asset targeting')
        paths.append(fields[0][2].decode('utf-8'))
    return paths


def verify_archives(directory, info, root=ROOT):
    record_id, profile_hash, approved = profile(root)
    expected_source = source_receipt(root)
    actual_source = read_json(directory / 'source-provenance.json')
    require(actual_source == expected_source and actual_source['commit'] == info['commit'] and
            actual_source['dirty'] is False, 'Resource receipt is not from this clean source')
    provenance.verify_package_notice((directory / 'THIRD_PARTY_NOTICES.txt').read_bytes(), root)
    mapping_bytes = (directory / 'mapping.txt').read_bytes()
    mapping = class_mapping(mapping_bytes)
    results = {}
    payloads = {}
    for name in ARCHIVES:
        file = directory / name
        members = archive_members(file)
        payloads[name] = members
        rules = approved['archives'][name]
        expected = dict(rules['members'])
        prefix = 'base/root/' if name.endswith('.aab') else ''
        for service, providers in rules['services'].items():
            renamed, contents = service_mapping(service, providers, mapping)
            path = prefix + 'META-INF/services/' + renamed
            require(path not in expected, 'Colliding transformed service resource')
            expected[path] = {'kind': 'r8-service', 'sha256': sha(contents)}
        require(set(members) == set(expected), 'Unclassified or missing archive resources: ' + name + ': ' +
                repr(sorted(set(members) ^ set(expected))))
        for path, data in members.items():
            digest = sha(data)
            require(digest not in approved['excludedSha256'] and not any(s in path for s in approved['excludedNames']),
                    'Excluded resource or renamed excluded bytes: ' + path)
            rule = expected[path]
            kind = rule['kind']
            if kind in {'fixed', 'compiled-resource', 'r8-service'}:
                require(digest == rule['sha256'], 'Changed reviewed resource: ' + name + '/' + path)
            elif kind == 'receipt-asset':
                require(data == (directory / Path(path).name).read_bytes(), 'Changed source/notice asset: ' + path)
            elif kind == 'build-identity':
                import build_identity
                require(data == (directory / 'build-identity.json').read_bytes(), 'Changed packaged build identity')
                build_identity.verify_report(data, info, root)
            elif kind == 'dex':
                verify_dex(data)
            elif kind == 'manifest':
                require(manifest_identity(file, info, 'androidTest' in name) == rule['sha256'], 'Manifest differs from reviewed recipe: ' + name)
            elif kind == 'resource-table':
                require(resource_table_identity(data) == rule['identity'], 'Compiled resource table/source inputs changed')
            elif kind == 'vcs':
                expected_vcs = ('repositories {\n  system: GIT\n  local_root_path: "$PROJECT_DIR"\n  revision: "' + info['commit'] + '"\n}\n').encode()
                # AGP's worktree limitation is explicit; the independent source receipt still binds HEAD.
                worktree_error = b'generate_error_reason: NO_VALID_GIT_FOUND\n'
                require(data == expected_vcs or ((root / '.git').is_file() and data == worktree_error), 'Incorrect packaged source revision')
            elif kind == 'r8-map':
                require(data == mapping_bytes, 'AAB mapping differs from candidate mapping')
            elif kind == 'assets-table':
                require(asset_paths(data) == ['assets'], 'Bundle asset directory/targeting changed')
            elif kind == 'art-profile':
                require(data.startswith(b'pro\x00010\x00') if path.endswith('.prof') else data.startswith(b'prm\x00002\x00'), 'Unexpected compiled ART profile')
            elif kind == 'r8-info':
                metadata = provenance.document(data)
                require(metadata['options'] == approved['r8Options'] and metadata['version'] == approved['r8Version'],
                        'Changed R8 generator profile')
                require(metadata['dexFiles'] == [{'checksum': sha(members['base/dex/classes.dex']),
                        'sizeInBytes': len(members['base/dex/classes.dex']), 'startup': False}], 'R8 metadata differs from actual DEX')
            else:
                raise ValueError('Unknown resource classification: ' + kind)
        results[name] = {'sha256': sha(file.read_bytes()), 'members': {path: {'sha256': sha(data), 'kind': expected[path]['kind'], 'recordId': record_id}
                                                                    for path, data in sorted(members.items())}}
    apk = payloads['app-release-unsigned.apk']
    bundle = payloads['app-release.aab']
    for apk_name, bundle_name in [('classes.dex', 'base/dex/classes.dex'),
                                  ('assets/dexopt/baseline.prof', 'BUNDLE-METADATA/com.android.tools.build.profiles/baseline.prof'),
                                  ('assets/dexopt/baseline.profm', 'BUNDLE-METADATA/com.android.tools.build.profiles/baseline.profm')]:
        require(apk[apk_name] == bundle[bundle_name], 'APK/AAB compiled payloads disagree')
    return {'schemaVersion': 1, 'result': 'passed', 'evidenceClass': 'actual-android-archive-resource-provenance',
            'commit': info['commit'], 'recordId': record_id, 'profileSha256': profile_hash, 'archives': results}


def signed_payload(candidate, signed):
    before, after = archive_members(candidate), archive_members(signed)
    signature = re.compile(r'META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))')
    extras = set(after) - set(before)
    require(all(signature.fullmatch(path) for path in extras), 'Unexpected signed archive member')
    require(all(after.get(path) == data for path, data in before.items()), 'Signing changed or removed candidate payload')
    return {'candidateSha256': sha(candidate.read_bytes()), 'signedSha256': sha(signed.read_bytes()),
            'unchangedMembers': len(before), 'signatureMembers': sorted(extras)}
