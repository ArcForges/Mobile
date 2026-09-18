#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Mobile-owned project and reviewed Android distributable licence gates."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATIONS = {'releaseRuntimeClasspath', 'debugRuntimeClasspath', 'debugAndroidTestRuntimeClasspath', 'coreLibraryDesugaring'}
ALLOWED = {'Apache-2.0', 'BSD-3-Clause', 'MIT', 'EPL-1.0', 'Apache-2.0 WITH LLVM-exception'}
LOCKS = ['app/gradle.lockfile', 'gradle/verification-metadata.xml', 'gradle/libs.versions.toml']


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def text_bytes(path):
    return path.read_text(encoding='utf-8').encode('utf-8')


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, encoding='utf-8').strip()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def project_audit(root=ROOT):
    files = sorted(set(git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split('\0')) - {''})
    for item in git(root, 'ls-files', '--stage').splitlines():
        require(item.split()[0] not in {'120000', '160000'}, 'Linked source/submodule is not an owned project')
    actual = []
    for name in files:
        path = Path(name)
        if path.name in {'build.gradle.kts', 'build.gradle', 'package.json', 'CMakeLists.txt'} or path.suffix in {'.csproj', '.vcxproj', '.esproj', '.fsproj', '.vbproj'}:
            require(path.name == 'build.gradle.kts', f'Unreviewed build system: {name}')
            require((root / path).resolve().is_relative_to(root.resolve()), 'Project escapes Mobile')
            actual.append({'path': name, 'kind': 'gradle'})
    policy = read_json(root / 'eng/policy/licence-boundary.json')
    require(set(policy) == {'schemaVersion', 'repository', 'spdxLicense', 'licenceBoundary', 'projects'}, 'Invalid project inventory fields')
    require(policy['schemaVersion'] == 1 and policy['repository'] == 'Mobile' and policy['spdxLicense'] == 'Apache-2.0' and policy['licenceBoundary'] == 'Apache', 'Incorrect Mobile assignment')
    require(sorted(policy['projects'], key=lambda x: x['path']) == actual and actual, 'Project inventory drift')
    for project in actual:
        text = (root / project['path']).read_text(encoding='utf-8')
        for key, expected in [('spdxLicense', 'Apache-2.0'), ('licenceBoundary', 'Apache')]:
            values = re.findall(r'extra\["' + key + r'"\]\s*=\s*"([^"\n]*)"', text)
            require(values == [expected], f'Missing or incorrect {key}: {project["path"]}')
    for name in files:
        if name.endswith(('.gradle.kts', '.gradle')):
            text = (root / name).read_text(encoding='utf-8')
            require(not re.search(r'includeBuild\s*\(|mavenLocal\s*\(', text), f'Unpublished build input: {name}')
        if name.endswith('.lockfile'):
            for line in (root / name).read_text().splitlines():
                if line.startswith('io.github.arcforges:'):
                    require(line.split(':')[1] in {'contracts-proto', 'contracts-connect-client'}, f'Unknown/non-public first-party dependency: {line}')
    return {'result': 'passed', 'repository': 'Mobile', 'commit': git(root, 'rev-parse', 'HEAD'),
            'dirty': bool(git(root, 'status', '--porcelain')), 'projects': actual, 'findings': []}


def notice_entries(data):
    """Keep all distributed notices, including notices in nested AAR JARs."""
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            if any(word in Path(item.filename).name.lower() for word in ('license', 'notice', 'copying', 'copyright')):
                text = archive.read(item).decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
                result[item.filename] = digest(text.encode('utf-8'))
            elif item.filename.endswith('.jar'):
                for name, sha in notice_entries(archive.read(item)).items():
                    result[item.filename + '!/' + name] = sha
    return result


def verify_closure(resolved, root=ROOT):
    source = project_audit(root)
    reviewed = read_json(root / 'eng/policy/android-licences.json')
    require(reviewed['schemaVersion'] == 1, 'Unsupported Android licence inventory')
    require({row['configuration'] for row in resolved} == CONFIGURATIONS and len(resolved) == len(CONFIGURATIONS), 'Incomplete Android configuration closure')
    components = reviewed['components']
    require(len({row['id'] for row in components}) == len(components), 'Duplicate reviewed dependency')
    known = {row['id']: row for row in components}
    checksums = ET.parse(root / 'gradle/verification-metadata.xml')
    verified = {row.attrib['value'] for row in checksums.findall('.//{*}sha256')}
    for entry in components:
        require(set(entry['configurations']).issubset(CONFIGURATIONS) and entry['configurations'], 'Invalid dependency scope')
        require(set(entry['artifacts'].values()).issubset(verified), f'Artifact is outside strict Gradle checksum verification: {entry["id"]}')
    expected_scopes = {name: sorted(row['id'] for row in components if name in row['configurations']) for name in CONFIGURATIONS}
    observed_artifacts = {}
    observed_native = {}
    for row in resolved:
        name = row['configuration']
        ids = [item['id'] for item in row['modules']]
        require(len(ids) == len(set(ids)) and sorted(ids) == expected_scopes[name], f'Unknown or changed Android dependency closure: {name}')
        require(name != 'coreLibraryDesugaring' or not ids, 'Excluded core-library implementation is present')
        for coordinate in ids:
            entry = known[coordinate]
            require(entry['spdxLicense'] in ALLOWED, f'Conflicting or unknown licence: {coordinate}')
            require(entry['spdxLicense'] != 'EPL-1.0' or name == 'debugAndroidTestRuntimeClasspath', 'EPL test library entered an application runtime')
            require(entry['evidence'] and entry['notices'], f'Missing reviewed licence evidence: {coordinate}')
        for module in row['modules']:
            require(set(module['dependencies']).issubset(ids), f'Unresolved dependency edge: {module["id"]}')
        expected = {(coordinate, filename): sha for coordinate in ids for filename, sha in known[coordinate]['artifacts'].items()}
        actual = {}
        for artifact in row['artifacts']:
            coordinate = artifact['id']
            require(coordinate in ids, 'Artifact has no resolved component')
            path = Path(artifact['file'])
            key = (coordinate, path.name)
            data = path.read_bytes()
            checksum = digest(data)
            require(key not in actual or actual[key] == checksum, 'Conflicting duplicate runtime artifact')
            if key in actual:
                continue  # Android variants can legitimately expose the identical AAR twice.
            actual[key] = checksum
            require(expected.get(key) == actual[key], f'Unreviewed artifact bytes: {key}')
            observed_artifacts[coordinate + '/' + path.name] = actual[key]
            embedded = notice_entries(data)
            require(set(embedded.values()).issubset(known[coordinate]['notices']), f'Notice closure drift: {coordinate}')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for item in archive.infolist():
                    if item.filename.endswith('.so'):
                        observed_native[coordinate + '/' + item.filename] = digest(archive.read(item))
        require(actual == expected, f'Incomplete resolved artifact set: {name}')
    require(observed_native == reviewed['nativeFiles'], 'Unreviewed native dependency closure')
    require(not observed_native or reviewed['nativeSourceEvidence'], 'Missing native source provenance')
    notice_hashes = {sha for row in components for sha in row['notices']}
    require({p.stem for p in (root / 'third-party/notices').glob('*.txt')} == notice_hashes, 'Unregistered or missing notice text')
    contents = {}
    for sha in sorted(notice_hashes):
        require(re.fullmatch('[0-9a-f]{64}', sha), 'Invalid notice identity')
        path = root / 'third-party/notices' / (sha + '.txt')
        data = text_bytes(path)
        require(digest(data) == sha, 'Retained notice changed or missing')
        contents[sha] = data.decode('utf-8')
    declarations = read_json(root / 'artifacts/evidence/licence-gradle.json')
    expected_projects = {':' if row['path'] == 'build.gradle.kts' else ':' + str(Path(row['path']).parent).replace('\\', ':').replace('/', ':') for row in source['projects']}
    require({row['path'] for row in declarations} == expected_projects and len(declarations) == len(expected_projects), 'Incomplete effective Gradle declarations')
    require(all(row['spdxLicense'] == 'Apache-2.0' and row['licenceBoundary'] == 'Apache' and set(row['references']).issubset(expected_projects) for row in declarations), 'Incorrect effective Gradle licence boundary')
    locks = {p: digest(text_bytes(root / p)) for p in LOCKS}
    report = {**source, 'evidenceClass': 'resolved-android-distributable-licence-closure',
              'policySha256': digest(text_bytes(root / 'eng/policy/android-licences.json')),
              'locks': locks, 'declarations': declarations, 'configurations': copy.deepcopy(resolved), 'artifacts': observed_artifacts,
              'nativeFiles': observed_native, 'nativeSourceEvidence': reviewed['nativeSourceEvidence'],
              'nativeSystemDependencies': reviewed['nativeSystemDependencies'], 'noticeSha256': sorted(notice_hashes)}
    # Cache paths are diagnostic inputs, never part of a distributed receipt.
    for configuration in report['configurations']:
        for artifact in configuration['artifacts']:
            artifact['file'] = Path(artifact['file']).name
    notice_text = 'ArcForges Mobile third-party notices\n\n'
    for row in components:
        notice_text += row['id'] + ' — ' + row['spdxLicense'] + '\n'
        notice_text += 'Scopes: ' + ', '.join(row['configurations']) + '\n'
        notice_text += 'Evidence: ' + ', '.join(item['url'] for item in row['evidence']) + '\n'
        notice_text += 'Notices: ' + ', '.join(row['notices']) + '\n\n'
    for sha, text in contents.items():
        notice_text += '\n--- ' + sha + ' ---\n\n' + text + '\n'
    assets = root / 'build/generated/licence-assets'
    assets.mkdir(parents=True, exist_ok=True)
    (assets / 'THIRD_PARTY_NOTICES.txt').write_text(notice_text, encoding='utf-8', newline='\n')
    save(assets / 'licence-closure.json', report)
    save(root / 'artifacts/evidence/android-licences.json', report)
    return report


def verify_distribution(directory, commit, root=ROOT):
    """Bind the reviewed closure and retained notices to every delivered Android archive."""
    report = read_json(directory / 'licence-closure.json')
    policy = read_json(root / 'eng/policy/android-licences.json')
    require(report['commit'] == commit and report['dirty'] is False and report['result'] == 'passed', 'Licence receipt is not from this clean commit')
    require(report['policySha256'] == digest(text_bytes(root / 'eng/policy/android-licences.json')), 'Licence policy changed after the candidate build')
    require(report['locks'] == {p: digest(text_bytes(root / p)) for p in LOCKS}, 'Android locks changed after the candidate build')
    require(report['artifacts'] == {row['id'] + '/' + name: sha for row in policy['components'] for name, sha in row['artifacts'].items()}, 'Incomplete candidate dependency evidence')
    notices = text_bytes(directory / 'THIRD_PARTY_NOTICES.txt')
    for row in policy['components']:
        require((row['id'] + ' — ' + row['spdxLicense']).encode('utf-8') in notices, 'Missing dependency attribution')
        for sha in row['notices']:
            retained = text_bytes(root / 'third-party/notices' / (sha + '.txt'))
            require(digest(retained) == sha and retained in notices, 'Missing or changed retained notice')
    expected_native = {name.split('/jni/', 1)[1] for name in policy['nativeFiles']}
    for name in ['app-release-unsigned.apk', 'app-release.aab', 'app-debug.apk', 'app-debug-androidTest.apk']:
        prefix = 'base/' if name.endswith('.aab') else ''
        with zipfile.ZipFile(directory / name) as archive:
            for asset in ['THIRD_PARTY_NOTICES.txt', 'licence-closure.json']:
                member = prefix + 'assets/' + asset
                require(archive.namelist().count(member) == 1, f'Missing or duplicate packaged licence asset: {name}')
                require(archive.read(member) == (directory / asset).read_bytes(), f'Missing or changed packaged licence asset: {name}')
            native = {path.split('/lib/', 1)[1] if '/lib/' in path else path.removeprefix('lib/') for path in archive.namelist() if path.endswith('.so')}
            require(native.issubset(expected_native) if 'androidTest' in name else native == expected_native, f'Unreviewed or missing native payload in {name}')
            require(not any(b'Lj$/' in archive.read(path) for path in archive.namelist() if path.endswith('.dex')), f'Excluded core-library implementation in {name}')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['projects', 'closure'])
    parser.add_argument('--resolved', type=Path)
    args = parser.parse_args()
    if args.command == 'projects':
        report = project_audit()
        save(ROOT / 'artifacts/evidence/licence-projects.json', report)
    else:
        require(args.resolved, 'Pass the actual Gradle resolution report')
        report = verify_closure(read_json(args.resolved))
    print(json.dumps({'result': report['result'], 'projects': len(report['projects']),
                      'artifacts': len(report.get('artifacts', {}))}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        print(f'Licence verification failed: {error}', file=sys.stderr)
        sys.exit(1)
