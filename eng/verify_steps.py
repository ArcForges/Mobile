# SPDX-License-Identifier: Apache-2.0
"""Local verification steps of Mobile, loaded by eng/verify.py (which injects `Step`).

The full profile is every validation job of .github/workflows/ci.yml (and of security.yml where it can run locally),
each on the host the hosted job used, in two legs on two native machines (eng/verify.py; AGENTS.md), with one exception
the user decided on 2026-10-17 ("Option A, my recommendation:
run the full Android build only on Windows locally."; "windows is enough for android"):
- lane `win` (Windows, in <main checkout>/.worktree/_verify): `MAUI (windows-latest)`: the pinned toolchain preflight, the
  locked restores into an emptied NuGet folder, the build identity, the Debug and Release (Mono AOT, R8) builds, the
  identity gate of the Release APK, the offline host and policy tests, the closure, re-proof and notice set, and the
  staging of a local MAUI candidate (`maui-stage --local`, which hosted CI runs on Linux only).
- lane `linux` (Linux, in ~/.cache/arcforges-verify/Mobile): the steps of `MAUI (ubuntu-latest)` that need no Android
  toolchain: the repository check and the tooling tests (`python eng/mobile.py check`,
  `python -m unittest discover -s eng/tests -v`), and the locked restore and run of the offline host and policy tests
  (net10.0). Their restore evaluates the net10.0-android target of the referenced libraries, which needs an android or
  maui-android workload manifest for the SDK band (nothing Android is built or run), so the lane starts with
  `linux-preflight` (LINUX_PREFLIGHT): the SDK that global.json pins and such a manifest, or a failure that names the
  command security.yml's codeql-csharp uses for the same restore, `dotnet workload install android maui-android
  --version 10.0.401`, instead of NETSDK1147 from the restore.
- lane `scan`: the whitespace check of the commits since the merge base (`git diff --check`) and the secret
  scan of security.yml (the pinned gitleaks image digest, .gitleaks.toml) over the same range ({range}), in Docker
  without network and with a read-only mount of the clone; lane `actionlint` (`Workflow lint`) only when
  .github/workflows/** changed.

Not verified locally (LINUX_ANDROID_GAP, printed on every run): the Linux Android build (Debug and Release), its APK
identity gate, the Linux notice set, the Linux licence evidence of the Android workload and the Linux-built candidate.
The Linux leg itself needs no Android SDK or JDK. These run where they run today: in the main-push candidate
job (the Linux `maui` leg, which builds the candidate that `publish` signs) and in the CI of every other PR.

Differences from the hosted jobs:
- No workload is installed. The Windows leg starts with a read-only preflight (PREFLIGHT) of what the hosted job installs
  and then checks: the SDK that global.json pins, workload set 10.0.401 with the android 36.1.69 and maui-android 10.0.20
  manifests (the same `dotnet workload list` guards as ci.yml, read from eng/policy/dotnet-toolchain.json), the Android
  SDK packages of setup-android (platform-tools, the target platform and the pinned build-tools) under ANDROID_HOME, and a
  JDK 21 under JAVA_HOME (hosted: Temurin 21.0.12). A missing prerequisite fails the push and names the exact command
  for the user; nothing is installed by the verification.
- The Windows steps use one SDK root whatever shell pushes: DOTNET_ROOT (a persistent user variable on this
  workstation, also set by the environment loaders; Env.md: the user-local .dotnet of the user profile), first on PATH.
  A plain PowerShell otherwise finds C:\\Program Files\\dotnet first through the machine PATH. Without a valid
  DOTNET_ROOT the Windows tool probe fails and the push is rejected. The Linux leg uses the dotnet of its login shell.
- The version is the local version of eng/mobile.py (`0.1.0-local`, versionCode 1; hosted: `0.1.0-ci.<run>.<attempt>`
  from the run number), and the build identity is `local.<commit>` (kind `local`; hosted: the run id). `maui-stage
  --local` seals the checked-out commit instead of GITHUB_SHA. A local candidate can never be signed: `maui-sign`
  requires the CI version of its own run, and the verification never signs.
- `CI` and `GITHUB_*` are not set (the build identity would claim a CI run). The two MSBuild properties that `CI=true`
  selects in Directory.Build.props are set directly: RestoreLockedMode and ContinuousIntegrationBuild.
- The NuGet folder is emptied before the locked restores of every run, as the hosted job restores into a new
  `$RUNNER_TEMP/nuget-maui-<run>-<attempt>` (AND.40 decision 17): Windows `<git common dir>/arcforges-verify/nuget-maui`,
  Linux `~/.cache/arcforges-verify/nuget-maui-Mobile`. Both lanes start without `artifacts/` and `build/`, as a fresh
  hosted checkout does; ignored bin/obj outputs stay, so the builds are incremental.
- The Linux clone has the identity of a pull-request checkout (`clone-identity`): HEAD is a local branch at the pushed
  commit and `origin/main` is the merge base with main, which the provenance check of `mobile.py check` compares against
  (hosted: the PR base from the event). Nothing is fetched from it.
- Artifacts (the candidate and the reports) are not uploaded; they stay in artifacts/ and build/ until the next run.
- The secret scan covers the pushed range, not the full history: history before it was scanned when it was pushed.
- Not reproduced: GitHub dependency review (a GitHub service; external PRs keep it; the locked restores with NuGet audit
  cover vulnerable packages locally) and CodeQL (external PRs, dispatch and the weekly schedule).
- No step reaches an OS credential store: the tests are offline host tests, the Android Keystore probe is compiled only for
  net10.0-android and runs only on a device, and the Debug-key signature that MSBuild puts on the Release APK uses the
  Android SDK's debug keystore file, not Windows Credential Manager or a Secret Service.
Every change runs the full profile: the policy suite's forbidden-name scan, the provenance inventory and the repository
text checks read every tracked file, Markdown included.
"""

import base64
import os
import subprocess
import sys
from pathlib import Path

REPOSITORY = "Mobile"

LINUX_ANDROID_GAP = (
    "arcforges-verify: note: the Linux Android build, its APK identity gate and notice set, the Linux workload licence "
    "evidence and the Linux-built candidate are not verified locally (user decision 2026-10-17, Option A: the Android "
    "build runs on Windows only); they run in the main-push candidate job and in the CI of every other PR")
print(LINUX_ANDROID_GAP, flush=True)

# The one .NET SDK root of the Windows steps (see above).
WIN_DOTNET_ROOT = os.environ.get("DOTNET_ROOT", "") if os.name == "nt" else ""
if WIN_DOTNET_ROOT and not Path(WIN_DOTNET_ROOT, "dotnet.exe").is_file():
    WIN_DOTNET_ROOT = ""
WIN_DOTNET = str(Path(WIN_DOTNET_ROOT, "dotnet.exe")) if WIN_DOTNET_ROOT else ""


def _win_dotnet(*args: str) -> list[str]:
    if WIN_DOTNET:
        return [WIN_DOTNET, *args]
    return [sys.executable, "-c", "import sys; sys.exit('DOTNET_ROOT does not name a .NET SDK root with dotnet.exe; set it "
            "to the root the Windows steps use (Env.md: the user-local .dotnet of the user profile)')"]


def _common_dir() -> str:
    if os.name != "nt":
        return ""
    result = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True,
                            text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


# The Windows NuGet folder: under the clone's verification state, outside every checkout.
WIN_NUGET = str(Path(_common_dir(), "arcforges-verify", "nuget-maui")) if _common_dir() else ""
LINUX_NUGET = "$HOME/.cache/arcforges-verify/nuget-maui-Mobile"

# The JDK and Android SDK packages the Windows build uses; it never fails on a missing prerequisite (the preflight step
# names it instead).
_WIN_JDK_ANDROID = (
    "import os, subprocess\n"
    "java = os.path.join(os.environ.get('JAVA_HOME', ''), 'bin', 'java.exe')\n"
    "try:\n"
    "    print(subprocess.run([java, '-version'], capture_output=True, text=True).stderr.splitlines()[0])\n"
    "except (OSError, IndexError):\n"
    "    print('no JDK at JAVA_HOME')\n"
    "sdk = os.environ.get('ANDROID_HOME', '')\n"
    "print('ANDROID_HOME', sdk)\n"
    "for part in ('platforms', 'build-tools'):\n"
    "    path = os.path.join(sdk, part)\n"
    "    print(part, sorted(os.listdir(path)) if os.path.isdir(path) else 'missing')\n"
)

# Tool versions recorded in each leg's summary (the python running eng/verify.py is added by the core).
FINGERPRINT = {
    "win": {
        "dotnet-root": [sys.executable, "-c", f"print({WIN_DOTNET_ROOT!r})"] if WIN_DOTNET else _win_dotnet(),
        "dotnet-sdks": _win_dotnet("--list-sdks"),
        "dotnet-workloads": _win_dotnet("workload", "--version"),
        "jdk-android": [sys.executable, "-c", _WIN_JDK_ANDROID],
        # No Windows git entry: the steps use git only for read-only queries (rev-parse, ls-files, status, show), and
        # which git a shell finds differs here (Git Bash: Scoop's build; PowerShell: Git for Windows from the machine
        # PATH), so it would key the pass to the pushing shell instead of the tools that build and test.
    },
    "linux": {
        "dotnet-sdks": "dotnet --list-sdks | tr '\\n' ' '",
        "dotnet-workloads": "dotnet workload --version",
        "python": "python --version",
        "docker": "docker version --format '{{.Server.Version}}'",
        "git": "git --version",
    },
}

APP = "src/ArcForges.Mobile/ArcForges.Mobile.csproj"
APK = "src/ArcForges.Mobile/bin/Release/net10.0-android/com.arcforges.mobile-Signed.apk"
# ci.yml's locked restores, in its order.
RESTORE_PROJECTS = [
    APP,
    "src/core/ArcForges.Mobile.Network/ArcForges.Mobile.Network.csproj",
    "src/core/ArcForges.Mobile.Security/ArcForges.Mobile.Security.csproj",
    "tests/ArcForges.Mobile.Policy/ArcForges.Mobile.Policy.csproj",
    "tests/ArcForges.Mobile.Tests/ArcForges.Mobile.Tests.csproj",
]
TEST_PROJECTS = RESTORE_PROJECTS[3:]
# eng/mobile.py LOCAL_VERSION (maui-stage --local refuses an APK with any other version).
VERSION_NAME, VERSION_CODE = "0.1.0-local", "1"
VERSION_PROPERTIES = f"-p:ArcForgesAndroidVersionName={VERSION_NAME} -p:ArcForgesAndroidVersionCode={VERSION_CODE}"

# Timeouts are about five to ten times the durations measured on this workstation (18 logical processors, both lanes
# concurrently; eng/verify.py's summary.json), with a floor of two to five minutes. Windows, cold (no bin/obj) and warm:
# restore into the emptied folder 51 s / 16 s, Debug build 62 s / 12 s, Release build (Mono AOT, R8) 175 s / 100 s, APK
# identity gate 6 s, tests 12 s / 6 s, notices 3 s. Linux (the workstation's former Linux environment): restore 10 s,
# tests 6 s, tooling tests 1 s.

# The environment of ci.yml without CI=true (see above). MSBuild node reuse is off, so that no build node outlives its step
# (a step's process tree is what a timeout or a failure stops).
ENV = {"DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
       "MSBUILDDISABLENODEREUSE": "1", "RestoreLockedMode": "true", "ContinuousIntegrationBuild": "true"}
WIN_ENV = {**ENV, "DOTNET_ROOT": WIN_DOTNET_ROOT, "NUGET_PACKAGES": WIN_NUGET,
           "PATH": os.pathsep.join(filter(None, [WIN_DOTNET_ROOT, os.environ.get("PATH", "")]))}

# What the hosted maui job installs (setup-dotnet, setup-java, setup-android, the pinned workload set) and then checks,
# checked read-only on Windows from the pushed commit's global.json and eng/policy/dotnet-toolchain.json. On a gap it
# names the exact prerequisite command for the user.
PREFLIGHT = (
    "import json, os, re, subprocess, sys\n"
    "toolchain = json.load(open('eng/policy/dotnet-toolchain.json', encoding='utf-8'))\n"
    "sdk = json.load(open('global.json', encoding='utf-8'))['sdk']['version']\n"
    "workload_set = toolchain['workloadSet']['version']\n"
    "pins = {alias: toolchain['workloads'][alias]['manifestVersion'] for alias in ('android', 'maui-android')}\n"
    "platform = 'android-' + toolchain['android']['targetPlatformVersion']\n"
    "build_tools = toolchain['android']['buildToolsVersion']\n"
    "root = os.environ.get('DOTNET_ROOT', '')\n"
    "dotnet = os.path.join(root, 'dotnet.exe')\n"
    "call = f'In PowerShell: & \"{dotnet}\"'\n"
    "problems, commands = [], []\n"
    "def run(*args):\n"
    "    result = subprocess.run([dotnet, *args], capture_output=True, text=True)\n"
    "    return (result.stdout + result.stderr).strip()\n"
    "if not os.path.isfile(dotnet):\n"
    "    problems.append(f'no dotnet.exe in the SDK root ({root or \"none\"})')\n"
    "else:\n"
    "    selected = run('--version')\n"
    "    if selected != sdk:\n"
    "        problems.append(f'{dotnet} selects SDK {selected!r} here, not {sdk} as global.json pins')\n"
    "        commands.append(f'install the .NET SDK {sdk} into {root}')\n"
    "    listing = run('workload', 'list')\n"
    "    found = re.search(r'^Workload version: (\\S+)\\s*$', listing, re.MULTILINE)\n"
    "    installed = {m.group(1): m.group(2) for m in re.finditer(r'^([a-z][\\w-]*)\\s+([0-9][^/\\s]*)/', listing,\n"
    "                                                                re.MULTILINE)}\n"
    "    version = found.group(1) if found else 'none'\n"
    "    missing = [alias for alias in pins if alias not in installed]\n"
    "    if missing:\n"
    "        problems.append(f'the {\" and \".join(missing)} workload is not installed (workload version {version})')\n"
    "        commands.append(f'{call} workload install android maui-android --version {workload_set}')\n"
    "    elif version != workload_set:\n"
    "        problems.append(f'workload version {version} is installed, not the pinned set {workload_set} (AND.40 '\n"
    "                        'decision 22; set 10.0.400 has the Mono toolchain 10.0.111, not the admitted 10.0.112)')\n"
    "        commands.append(f'{call} workload update --version {workload_set}')\n"
    "    else:\n"
    "        for alias, pin in pins.items():\n"
    "            if installed[alias] != pin:\n"
    "                problems.append(f'workload set {workload_set} gives {alias} {installed[alias]}, not {pin} (AND.40 '\n"
    "                                'decision 3: move to SDK 10.0.401 with a reviewed admission; not applied silently)')\n"
    "android = os.environ.get('ANDROID_HOME', '')\n"
    "wanted = {'platform-tools': 'platform-tools', f'platforms;{platform}': f'platforms/{platform}/android.jar',\n"
    "          f'build-tools;{build_tools}': f'build-tools/{build_tools}/zipalign.exe'}\n"
    "absent = [package for package, path in wanted.items() if not (android and os.path.exists(os.path.join(android, path)))]\n"
    "if absent:\n"
    "    problems.append(f'ANDROID_HOME ({android or \"unset\"}) lacks the Android SDK packages {\", \".join(absent)}')\n"
    "    packages = ' '.join(f'\"{package}\"' for package in absent)\n"
    "    commands.append(f'In PowerShell: & \"{android}\\\\cmdline-tools\\\\latest\\\\bin\\\\sdkmanager.bat\" {packages}')\n"
    "java = os.path.join(os.environ.get('JAVA_HOME', ''), 'bin', 'java.exe')\n"
    "try:\n"
    "    jdk = subprocess.run([java, '-version'], capture_output=True, text=True).stderr\n"
    "except OSError:\n"
    "    jdk = ''\n"
    "if not re.search(r'version \"21[.\"]', jdk):\n"
    "    problems.append(f'JAVA_HOME ({os.environ.get(\"JAVA_HOME\") or \"unset\"}) is not a JDK 21 (the hosted job uses '\n"
    "                    'Temurin 21.0.12 for the Android build tooling)')\n"
    "    commands.append('a JDK 21 with JAVA_HOME set as a persistent user variable')\n"
    "if problems:\n"
    "    sys.exit('The Windows MAUI toolchain is not the one the hosted maui job builds with: ' + '; '.join(problems)\n"
    "             + '. Prerequisites (installs by the user): ' + ' ; '.join(commands) + '. Then verify again.')\n"
    "print(f'SDK {sdk} at {root}, workload set {workload_set} (android {pins[\"android\"]}, maui-android '\n"
    "      f'{pins[\"maui-android\"]}), Android SDK {android} ({\", \".join(wanted)}), {jdk.splitlines()[0]}')\n"
)

# The Linux lane's prerequisite for the host-test restore (see above), checked read-only from the pushed commit's
# global.json and eng/policy/dotnet-toolchain.json; passed as base64, so that no quoting layer between eng/verify.py and
# bash changes the program.
LINUX_PREFLIGHT = (
    "import json, re, shutil, subprocess, sys\n"
    "sdk = json.load(open('global.json', encoding='utf-8'))['sdk']['version']\n"
    "workload_set = json.load(open('eng/policy/dotnet-toolchain.json', encoding='utf-8'))['workloadSet']['version']\n"
    "command = f'dotnet workload install android maui-android --version {workload_set}'\n"
    "dotnet = shutil.which('dotnet')\n"
    "if not dotnet:\n"
    "    sys.exit(f'The Linux host has no dotnet on PATH; install the .NET SDK {sdk}, then run, on the Linux host '\n"
    "             f'in a Mobile checkout: {command}')\n"
    "def run(*args):\n"
    "    result = subprocess.run([dotnet, *args], capture_output=True, text=True)\n"
    "    return (result.stdout + result.stderr).strip()\n"
    "problems = []\n"
    "selected = run('--version')\n"
    "if selected != sdk:\n"
    "    problems.append(f'{dotnet} selects SDK {selected!r} here, not {sdk} as global.json pins (install that SDK into '\n"
    "                    'the .NET root of the Linux host)')\n"
    "listing = run('workload', 'list')\n"
    "manifests = re.findall(r'^(android|maui-android)\\s+(\\S+)', listing, re.MULTILINE)\n"
    "if not manifests:\n"
    "    problems.append('no android or maui-android workload manifest is installed for this SDK band, so the locked '\n"
    "                    'restore of the host test projects cannot evaluate the net10.0-android target of the libraries '\n"
    "                    f'they reference (NETSDK1147). Prerequisite (an install by the user), on the Linux host in a Mobile '\n"
    "                    f'checkout: {command}')\n"
    "if problems:\n"
    "    sys.exit('The Linux host-test toolchain is incomplete: ' + '; '.join(problems) + '. Then verify again.')\n"
    "print(f'SDK {sdk} at {dotnet}; workload manifests ' + ', '.join(f'{n} {v}' for n, v in manifests)\n"
    "      + ' (only evaluated by the host-test restore; nothing Android is built here)')\n"
)
LINUX_PREFLIGHT_BASE64 = base64.b64encode(LINUX_PREFLIGHT.encode("utf-8")).decode("ascii")

# security.yml's secret scan (same pinned image digest and redaction, with .gitleaks.toml named explicitly), over the
# pushed range, without network and with a read-only mount of the verification clone.
SECRET_SCAN = (
    "docker run --rm --network none -v \"$PWD:/repo:ro\" "
    "-e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo "
    "ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f "
    "git /repo --redact=100 --no-banner --verbose --config /repo/.gitleaks.toml "
    "--log-opts=\"--full-history {range}\""
)

# actionlint as pinned in ci.yml, cached once on the Linux host; the archive is checked on every run.
ACTIONLINT = (
    "set -euo pipefail; v=1.7.12; "
    "sum=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8; "
    "d=\"$HOME/.cache/arcforges-verify/tools\"; t=\"$d/actionlint_${v}_linux_amd64.tar.gz\"; mkdir -p \"$d\"; "
    "if [ ! -f \"$t\" ]; then "
    "curl --fail --silent --show-error --location --output \"$t.part\" "
    "\"https://github.com/rhysd/actionlint/releases/download/v${v}/actionlint_${v}_linux_amd64.tar.gz\"; "
    "echo \"$sum  $t.part\" | sha256sum --check --quiet; mv \"$t.part\" \"$t\"; fi; "
    "echo \"$sum  $t\" | sha256sum --check --quiet; "
    "mkdir -p \"$d/actionlint-$v\"; tar -xzf \"$t\" -C \"$d/actionlint-$v\" actionlint; "
    "\"$d/actionlint-$v/actionlint\" -color"
)


def select_profile(changed: list[str]) -> str:
    return "full"


def workflows_changed(changed: list[str]) -> bool:
    return any(path.startswith(".github/workflows/") for path in changed)


def pwsh(script: str) -> list[str]:
    return ["pwsh", "-NoProfile", "-NonInteractive", "-Command",
            "$ErrorActionPreference = 'Stop'; " + script + "; exit $LASTEXITCODE"]


def checked(*commands: str) -> str:
    """PowerShell commands run in order, stopping at the first non-zero exit code."""
    return "; ".join(f"{command}; if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}" for command in commands)


def win(step_id: str, cmd: list[str], timeout: int, **options) -> Step:
    return Step(step_id, "win", cmd, timeout=timeout, env=WIN_ENV, **options)


def linux(step_id: str, cmd: str, timeout: int, **options) -> Step:
    # The NuGet folder is under $HOME, which the step's own shell expands (Step.env values are quoted literally).
    return Step(step_id, "linux", f"set -euo pipefail; export NUGET_PACKAGES=\"{LINUX_NUGET}\"; {cmd}", timeout=timeout,
                env=ENV, **options)


NOTICES = ["closure", "reproof", "check", "distribution"]
BUILD = f"build {APP} -f net10.0-android --no-restore -nologo {VERSION_PROPERTIES}"
TEST = "--no-restore --logger \"console;verbosity=normal\""

STEPS = [
    # ci.yml maui (windows-latest), plus the candidate staging that hosted CI runs on Linux
    win("win-fresh-outputs", pwsh("foreach ($d in 'artifacts', 'build') { if (Test-Path $d) { Remove-Item -Recurse "
                                  "-Force $d } }"), 120),
    win("win-preflight", ["python", "-I", "-c", PREFLIGHT], 120),
    win("win-restore", pwsh(
        "if (Test-Path $env:NUGET_PACKAGES) { Remove-Item -Recurse -Force $env:NUGET_PACKAGES }; "
        "New-Item -ItemType Directory -Force $env:NUGET_PACKAGES | Out-Null; "
        + checked(*(f"dotnet restore {p} --locked-mode" for p in RESTORE_PROJECTS))), 600),
    win("win-build-identity", pwsh(checked(
        f"python eng/build_identity.py --maui --observed-sdk (dotnet --version) --version {VERSION_NAME} "
        f"--code {VERSION_CODE}")), 120),
    win("win-build-debug", pwsh(checked(f"dotnet {BUILD} -c Debug")), 900),
    win("win-build-release", pwsh(checked(f"dotnet {BUILD} -c Release")), 1800),
    win("win-apk-identity", ["python", "eng/maui_identity.py", "--apk", APK, "--configuration", "Release"], 120),
    win("win-test", pwsh(checked(*(f"dotnet test {p} -c Release {TEST}" for p in TEST_PROJECTS))), 300),
    win("win-notices", pwsh(checked(*(f"python eng/maui_notices.py {c}" for c in NOTICES))), 120),
    win("win-stage", ["python", "eng/mobile.py", "maui-stage", "--local", "--candidate", "artifacts/maui-candidate"], 300),
    # ci.yml maui (ubuntu-latest): the steps that need no Android toolchain (LINUX_ANDROID_GAP)
    linux("linux-preflight", f"python -I -c \"$(printf %s {LINUX_PREFLIGHT_BASE64} | base64 -d)\"", 120),
    linux("clone-identity", "git checkout -q -B arcforges-verify {sha}; git update-ref refs/remotes/origin/main {base}", 60),
    linux("fresh-outputs", "rm -rf artifacts build", 120),
    linux("repository-check", "python eng/mobile.py check", 300),
    linux("tooling-tests", "python -m unittest discover -s eng/tests -v", 300),
    linux("restore", f"rm -rf \"$NUGET_PACKAGES\"; mkdir -p \"$NUGET_PACKAGES\"; "
          f"for p in {' '.join(TEST_PROJECTS)}; do dotnet restore \"$p\" --locked-mode; done", 600),
    linux("test", f"for p in {' '.join(TEST_PROJECTS)}; do dotnet test \"$p\" -c Release {TEST}; done", 300),
    # the whitespace check and security.yml's secret scan over the commits since the merge base; actionlint when a workflow changed
    Step("whitespace", "linux", "git diff --check {base} {sha}", timeout=120, lane="scan"),
    Step("secret-scan", "linux", SECRET_SCAN, timeout=600, lane="scan"),
    Step("actionlint", "linux", ACTIONLINT, timeout=300, lane="actionlint", when=workflows_changed),
]
