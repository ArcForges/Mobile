#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Mobile-owned .NET project and MAUI NuGet closure licence gates.

The Gradle and Kotlin closure gates are retired with the Kotlin baseline (AND.40 PR B). The identity project and the
other .NET projects are audited against eng/policy/dotnet-licence-boundary.json; the MAUI closure against its
NuGet lock and admission records.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DOTNET_BOUNDARY = 'eng/policy/dotnet-licence-boundary.json'
MAUI_LOCK = 'src/ArcForges.Mobile/packages.lock.json'
MAUI_ADMISSION = 'eng/policy/nuget-admission.json'
MAUI_TARGET = 'net10.0-android36.1'
MAUI_ADMITTED_LICENCES = {'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'MIT', 'Zlib', 'Unicode-3.0'}
MAUI_FORBIDDEN_LICENCE = re.compile(r'AGPL|GPL|SSPL|BUSL|Proprietary|UNLICENSED', re.IGNORECASE)
BUILD_SYSTEM_NAMES = {'build.gradle.kts', 'build.gradle', 'package.json', 'CMakeLists.txt'}
BUILD_SYSTEM_SUFFIXES = {'.csproj', '.vcxproj', '.esproj', '.fsproj', '.vbproj'}


def require(value, message):
    if not value:
        raise ValueError(message)

def digest(value):
    return hashlib.sha256(value).hexdigest()

def git(root, *args):
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    return subprocess.check_output(['git', *args], cwd=root, text=True, encoding='utf-8', env=environment).strip()

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

def dotnet_project_audit(root=ROOT):
    """Every tracked .NET project is a reviewed csproj; no other build system and no link or submodule is owned."""
    files = sorted(set(git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split('\0')) - {''})
    for item in git(root, 'ls-files', '--stage').splitlines():
        require(item.split()[0] not in {'120000', '160000'}, 'Linked source/submodule is not an owned project')
    dotnet = []
    for name in files:
        path = Path(name)
        if path.name in BUILD_SYSTEM_NAMES or path.suffix in BUILD_SYSTEM_SUFFIXES:
            require(path.suffix == '.csproj', f'Unreviewed build system: {name}')
            require((root / path).resolve().is_relative_to(root.resolve()), 'Project escapes Mobile')
            dotnet.append(name)
    return {'result': 'passed', 'repository': 'Mobile', 'commit': git(root, 'rev-parse', 'HEAD'),
            'dirty': bool(git(root, 'status', '--porcelain')), 'dotnetProjects': dotnet_audit(root, dotnet),
            'findings': []}

def dotnet_audit(root, paths):
    """Audit the .NET identity project csproj against its own inventory (AND.01); never the Gradle roster."""
    if not paths and not (root / DOTNET_BOUNDARY).exists():
        return []  # no .NET project exists and none is registered; a csproj without its registry still fails closed
    policy = read_json(root / DOTNET_BOUNDARY)
    require(set(policy) == {'schemaVersion', 'repository', 'spdxLicense', 'licenceBoundary', 'projects'}, 'Invalid .NET project inventory fields')
    require(policy['schemaVersion'] == 1 and policy['repository'] == 'Mobile' and policy['spdxLicense'] == 'Apache-2.0' and policy['licenceBoundary'] == 'Apache', 'Incorrect .NET Mobile assignment')
    actual = [{'path': name, 'kind': 'dotnet'} for name in sorted(paths)]
    require(sorted(policy['projects'], key=lambda x: x['path']) == actual, '.NET project inventory drift')
    for project in actual:
        text = (root / project['path']).read_text(encoding='utf-8')
        for tag, expected in [('PackageLicenseExpression', 'Apache-2.0'), ('LicenceBoundary', 'Apache')]:
            values = re.findall(r'<' + tag + r'>([^<\n]*)</' + tag + '>', text)
            require(values == [expected], f'Missing or incorrect {tag}: {project["path"]}')
    return actual

def maui_closure_audit(root=ROOT):
    """AND.40 MAUI NuGet closure audit only: one Android target, every locked package admitted with its hashes, admitted
    licences only, and no Build.Policy in the closure records."""
    lock_bytes = (root / MAUI_LOCK).read_bytes()
    lock = json.loads(lock_bytes.decode('utf-8'))
    require(lock.get('version') == 2, 'MAUI lock must use lock version 2')
    targets = [key for key in lock['dependencies'] if '/' not in key]
    require(targets == [MAUI_TARGET], 'The MAUI closure must target net10.0-android only')
    admission_bytes = (root / MAUI_ADMISSION).read_bytes()
    require(not re.search(r'build\.policy', (lock_bytes + admission_bytes).decode('utf-8'), re.IGNORECASE),
            'The MAUI closure names ArcForges.Build.Policy')
    packages = {row['id']: row for row in read_json(root / MAUI_ADMISSION)['packages']}
    locked = []
    for name, info in lock['dependencies'][MAUI_TARGET].items():
        if info['type'] == 'Project':
            continue
        require(name in packages, f'Locked MAUI package is not admitted: {name}')
        row = packages[name]
        require(row['version'] == info['resolved'] and row['contentHash'] == info['contentHash'],
                f'Locked MAUI package differs from its admission: {name}')
        require(not MAUI_FORBIDDEN_LICENCE.search(row['licence']), f'Forbidden MAUI licence: {name}')
        tokens = [token for token in re.split(r'\s+(?:AND|OR|WITH)\s+|[()]', row['licence']) if token.strip()]
        require(tokens and all(token.strip() in MAUI_ADMITTED_LICENCES for token in tokens),
                f'Unadmitted MAUI licence for {name}: {row["licence"]}')
        locked.append(name)
    require(sorted(locked) == sorted(packages), 'The admitted MAUI closure differs from the locked closure')
    return {'result': 'passed', 'target': MAUI_TARGET, 'packages': len(locked),
            'lockSha256': digest(lock_bytes), 'admissionSha256': digest(admission_bytes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['projects', 'maui'])
    args = parser.parse_args()
    if args.command == 'projects':
        report = dotnet_project_audit()
        save(ROOT / 'artifacts/evidence/licence-projects.json', report)
    else:
        report = maui_closure_audit()
    print(json.dumps({'result': report['result'], 'dotnetProjects': len(report.get('dotnetProjects', [])),
                      'packages': report.get('packages', 0)}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print(f'Licence verification failed: {error}', file=sys.stderr)
        sys.exit(1)
