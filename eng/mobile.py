#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Small, dependency-free checks and Android artifact delivery helpers."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BUILD_TOOLS = "37.0.0"
PACKAGE = "io.github.arcforges.mobile"


def run(*args, capture=False, **kwargs):
    result = subprocess.run(
        [str(arg) for arg in args], check=True, text=True, encoding="utf-8",
        stdout=subprocess.PIPE if capture else None, cwd=ROOT, **kwargs,
    )
    return result.stdout.strip() if capture else ""


def sdk_tool(name):
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not sdk:
        raise ValueError("Set ANDROID_HOME to the installed Android SDK.")
    suffix = ".bat" if name == "apksigner" else ".exe"
    path = Path(sdk) / "build-tools" / BUILD_TOOLS / (name + (suffix if os.name == "nt" else ""))
    if not path.is_file():
        raise ValueError(f"Install Android SDK Build-Tools {BUILD_TOOLS}: missing {path}")
    return path


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def version():
    number = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
    attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", "0"))
    if not (1 <= number <= 20_999_999 and 1 <= attempt <= 99):
        raise ValueError("Release numbering requires run 1..20999999 and attempt 1..99.")
    return {"version_code": number * 100 + attempt, "version_name": f"0.1.0-ci.{number}.{attempt}"}


def repository_check():
    names = run("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", capture=True).split("\0")
    for name in filter(None, names):
        path = ROOT / name
        if not path.is_file() or path.suffix in {".jar", ".png"}:
            continue
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            raise ValueError(f"Missing final newline: {name}")
        if any(line.rstrip() != line for line in text.splitlines()):
            raise ValueError(f"Trailing whitespace: {name}")
        if path.suffix == ".toml":
            tomllib.loads(text)
        if path.suffix == ".xml":
            ET.fromstring(text)
        if path.suffix == ".json":
            json.loads(text)
        if path.suffix in {".jks", ".keystore", ".p12", ".pem", ".key"}:
            raise ValueError(f"Signing material must remain outside the repository: {name}")
    run("git", "diff", "--check")
    run("git", "diff", "--cached", "--check")
    print("Repository text, structured files and whitespace checks passed.")


def bytecode_check():
    counts = {}
    for module in ("app", "shared"):
        paths = [p for p in (ROOT / module / "build").rglob("*.class") if "/io/github/arcforges/mobile/" in p.as_posix()]
        if not paths:
            raise ValueError(f"No compiled application classes found in {module}; build first.")
        for path in paths:
            magic, _, major = struct.unpack(">IHH", path.read_bytes()[:8])
            if magic != 0xCAFEBABE or major != 65:
                raise ValueError(f"Expected JVM 21 (class major 65), got {major}: {path}")
        counts[module] = len(paths)
    print(f"JVM 21 bytecode verified (before Android D8/R8 dex conversion): {counts}")


def inspect_apk(apk, expected, package=PACKAGE):
    details = run(sdk_tool("aapt2"), "dump", "badging", apk, capture=True)
    for token in (f"name='{package}'", f"versionCode='{expected['version_code']}'", f"versionName='{expected['version_name']}'"):
        if token not in details.splitlines()[0]:
            raise ValueError(f"APK metadata mismatch: {token}")
    if "minSdkVersion:'26'" not in details or "targetSdkVersion:'37'" not in details:
        raise ValueError("APK SDK requirements differ from the reviewed release configuration.")


def stage(destination):
    if destination.exists():
        raise ValueError(f"Use an empty candidate directory: {destination}")
    destination.mkdir(parents=True)
    files = {
        "app-release-unsigned.apk": "app/build/outputs/apk/release/app-release-unsigned.apk",
        "app-release.aab": "app/build/outputs/bundle/release/app-release.aab",
        "app-debug.apk": "app/build/outputs/apk/debug/app-debug.apk",
        "app-debug-androidTest.apk": "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
        "mapping.txt": "app/build/outputs/mapping/release/mapping.txt",
    }
    for name, source in files.items():
        shutil.copyfile(ROOT / source, destination / name)
    info = version()
    info.update(commit=os.environ["GITHUB_SHA"], package=PACKAGE)
    inspect_apk(destination / "app-release-unsigned.apk", info)
    inspect_apk(destination / "app-debug.apk", info, f"{PACKAGE}.debug")
    info["sha256"] = {name: sha256(destination / name) for name in files}
    (destination / "candidate.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(f"Staged immutable candidate {info['version_name']} from {info['commit']}.")


def verify_candidate(directory):
    info = json.loads((directory / "candidate.json").read_text(encoding="utf-8"))
    expected = {"app-release-unsigned.apk", "app-release.aab", "app-debug.apk", "app-debug-androidTest.apk", "mapping.txt"}
    if set(info["sha256"]) != expected or {p.name for p in directory.iterdir()} != expected | {"candidate.json"}:
        raise ValueError("The candidate file set is incomplete or contains unexpected files.")
    if info["commit"] != os.environ["GITHUB_SHA"] or info["package"] != PACKAGE:
        raise ValueError("The candidate was built for another commit or application.")
    if any(info[key] != value for key, value in version().items()):
        raise ValueError("Candidate version differs from this workflow run and attempt.")
    for name, checksum in info["sha256"].items():
        if sha256(directory / name) != checksum:
            raise ValueError(f"Candidate checksum mismatch: {name}")
    inspect_apk(directory / "app-release-unsigned.apk", info)
    return info


def sign_candidate(directory, destination):
    info = verify_candidate(directory)
    required = ("ANDROID_KEYSTORE_BASE64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD", "ANDROID_SIGNING_CERT_SHA256")
    if any(not os.environ.get(name) for name in required):
        raise ValueError("Configure the five Android signing settings documented in docs/releasing.md.")
    if destination.exists():
        raise ValueError(f"Use an empty release output directory: {destination}")
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="arcforges-sign-") as scratch:
        key = Path(scratch) / "release.jks"
        key.write_bytes(base64.b64decode(os.environ["ANDROID_KEYSTORE_BASE64"], validate=True))
        key.chmod(0o600)
        aligned = Path(scratch) / "aligned.apk"
        run(sdk_tool("zipalign"), "-P", "16", "-f", "4", directory / "app-release-unsigned.apk", aligned)
        apk = destination / f"ArcForges-{info['version_name']}.apk"
        run(sdk_tool("apksigner"), "sign", "--ks", key, "--ks-key-alias", os.environ["ANDROID_KEY_ALIAS"],
            "--ks-pass", "env:ANDROID_KEYSTORE_PASSWORD", "--key-pass", "env:ANDROID_KEY_PASSWORD", "--out", apk, aligned)
        certificate = run(sdk_tool("apksigner"), "verify", "--verbose", "--print-certs", apk, capture=True)
        fingerprint = re.search(r"Signer #1 certificate SHA-256 digest: ([a-fA-F0-9]+)", certificate)
        if not fingerprint or fingerprint.group(1).lower() != os.environ["ANDROID_SIGNING_CERT_SHA256"].replace(":", "").lower():
            raise ValueError("APK signing certificate does not match the configured persistent identity.")
        run(sdk_tool("zipalign"), "-c", "-P", "16", "4", apk)
        inspect_apk(apk, info)
        bundle = destination / f"ArcForges-{info['version_name']}.aab"
        shutil.copyfile(directory / "app-release.aab", bundle)
        run("jarsigner", "-keystore", key, "-storepass:env", "ANDROID_KEYSTORE_PASSWORD", "-keypass:env", "ANDROID_KEY_PASSWORD",
            "-digestalg", "SHA-256", "-sigalg", "SHA256withRSA", bundle, os.environ["ANDROID_KEY_ALIAS"])
        result = run("jarsigner", "-verify", bundle, capture=True)
        if "jar verified." not in result:
            raise ValueError("AAB signature verification failed.")
        info["certificate_sha256"] = fingerprint.group(1).lower()
    shutil.copyfile(directory / "mapping.txt", destination / "mapping.txt")
    info["candidate_sha256"] = info.pop("sha256")
    info["sha256"] = {p.name: sha256(p) for p in sorted(destination.iterdir())}
    (destination / "release.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    checksums = "".join(f"{sha256(p)}  {p.name}\n" for p in sorted(destination.iterdir()))
    (destination / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    print(f"Verified signed APK and AAB: {info['version_name']} (certificate {info['certificate_sha256']}).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "bytecode", "version", "stage", "verify", "sign", "hooks"])
    parser.add_argument("--candidate", type=Path, default=ROOT / "artifacts/candidate")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/release")
    args = parser.parse_args()
    if args.command == "check":
        repository_check()
    elif args.command == "bytecode":
        bytecode_check()
    elif args.command == "version":
        data = version()
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                stream.writelines(f"{key}={value}\n" for key, value in data.items())
        print(json.dumps(data))
    elif args.command == "stage":
        stage(args.candidate)
    elif args.command == "verify":
        print(json.dumps(verify_candidate(args.candidate), indent=2))
    elif args.command == "sign":
        sign_candidate(args.candidate, args.output)
    else:
        run("git", "config", "extensions.worktreeConfig", "true")
        run("git", "config", "--worktree", "core.hooksPath", ".githooks")
        print("Enabled hooks for this checkout/worktree.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
