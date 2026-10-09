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
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
import zipfile

from licences import maui_closure_audit
import check_provenance
import maui_notices
import resources
import maui_identity

ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False, **kwargs):
    if args and str(args[0]) == "git":
        kwargs["env"] = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    result = subprocess.run(
        [str(arg) for arg in args], check=True, text=True, encoding="utf-8",
        stdout=subprocess.PIPE if capture else None, cwd=ROOT, **kwargs,
    )
    return result.stdout.strip() if capture else ""


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
    maui_identity.check_maui(ROOT)  # AND.01: MAUI identity, SDK pin and NuGet admission
    maui_closure_audit(ROOT)  # AND.40 unit 4: MAUI NuGet closure audit (licences, admission equality, one Android target)
    maui_notices.reproof(ROOT)  # AND.40 unit 4: F-023-class re-proof of the shipped closure
    maui_notices.check(ROOT)  # AND.40 unit 4: notice data, retained texts, deferrals and the THIRD_PARTY_NOTICES.md block
    provenance_report = check_provenance.run(ROOT, 'Mobile')
    resources.save(ROOT / 'artifacts/evidence/provenance.json', provenance_report)
    names = run("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", capture=True).split("\0")
    for name in filter(None, names):
        path = ROOT / name
        if not path.is_file() or path.suffix in {".jar", ".png"}:
            continue
        text = path.read_text(encoding="utf-8")
        if name.startswith("third-party/notices/"):
            continue  # Preserve upstream notice text; the licence gate verifies its reviewed hash.
        if not text.endswith("\n") and name != maui_identity.MAUI_LOCK:
            # NuGet writes the MAUI packages.lock.json without a final newline; its bytes are bound by eng/policy/nuget-admission.json.
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


def verify_certificate(output, expected):
    # Build-Tools 37 labels these "V3.0 Signer", rather than "Signer #1".
    fingerprints = {value.lower() for value in re.findall(r"certificate SHA-256 digest: ([a-fA-F0-9]{64})$", output, re.MULTILINE)}
    normalized = expected.replace(":", "").lower()
    if not re.search(r"^Number of signers: 1$", output, re.MULTILINE) or fingerprints != {normalized}:
        raise ValueError("APK signing certificate does not match the configured persistent identity.")
    return normalized


def maui_sdk_tool(name):
    """Build-Tools named by the MAUI toolchain pin (36.1.0), not the Kotlin path's 37.0.0."""
    pin = json.loads((ROOT / "eng/policy/dotnet-toolchain.json").read_text(encoding="utf-8"))["android"]["buildToolsVersion"]
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not sdk:
        raise ValueError("Set ANDROID_HOME to the installed Android SDK.")
    suffix = (".bat" if name == "apksigner" else ".exe") if os.name == "nt" else ""
    path = Path(sdk) / "build-tools" / pin / (name + suffix)
    if not path.is_file():
        raise ValueError(f"Install Android SDK Build-Tools {pin}: missing {path}")
    return path


def strip_signature(source, destination):
    """Rewrite an APK without its META-INF signature entries, keeping every payload entry and its compression.

    The Release APK that MSBuild writes is signed with the debug key. The persistent key signs the unsigned payload.
    """
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as unsigned:
        for entry in original.infolist():
            if entry.filename.startswith("META-INF/"):
                continue
            unsigned.writestr(entry, original.read(entry.filename), compress_type=entry.compress_type)


# AND.40: the MAUI candidate and release path. The release tag is android-VERSION (AND.40 PR B, decision 5); the
# android-maui-VERSION prerelease namespace from PR A stays as published history.
MAUI_TRACK = "maui"
MAUI_PACKAGE = "com.arcforges.mobile"  # the release applicationId, permanent since AND.01
MAUI_OUTPUT_DIR = ROOT / "src/ArcForges.Mobile/bin/Release/net10.0-android"
MAUI_UNSIGNED = "maui-release-unsigned.apk"
MAUI_COMPANIONS = ("mapping.txt", "THIRD_PARTY_NOTICES.txt", "licence-closure.json", "build-identity.json", "maui-archive.json")
MAUI_CANDIDATE_FILES = {MAUI_UNSIGNED, *MAUI_COMPANIONS}
MAUI_SIGNING_ENVIRONMENT = ("ANDROID_KEYSTORE_BASE64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS",
                            "ANDROID_KEY_PASSWORD", "ANDROID_SIGNING_CERT_SHA256")


def maui_verify_candidate(directory):
    info = json.loads((directory / "candidate.json").read_text(encoding="utf-8"))
    if set(info["sha256"]) != MAUI_CANDIDATE_FILES or {p.name for p in directory.iterdir()} != MAUI_CANDIDATE_FILES | {"candidate.json"}:
        raise ValueError("The MAUI candidate file set is incomplete or contains unexpected files.")
    if info["commit"] != os.environ["GITHUB_SHA"] or info["package"] != MAUI_PACKAGE or info.get("track") != MAUI_TRACK:
        raise ValueError("The MAUI candidate was built for another commit, application or track.")
    if any(info[key] != value for key, value in version().items()):
        raise ValueError("MAUI candidate version differs from this workflow run and attempt.")
    for name, checksum in info["sha256"].items():
        if sha256(directory / name) != checksum:
            raise ValueError(f"MAUI candidate checksum mismatch: {name}")
    return info


def maui_stage(destination):
    """Seal the Release MAUI APK, its companions and the build identity as one immutable candidate."""
    import build_identity
    if destination.exists():
        raise ValueError(f"Use an empty MAUI candidate directory: {destination}")
    apk = MAUI_OUTPUT_DIR / f"{MAUI_PACKAGE}-Signed.apk"
    if not apk.is_file():
        raise ValueError(f"Build the Release MAUI APK first: missing {apk}")
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="arcforges-maui-stage-") as scratch:
        stripped = Path(scratch) / "stripped.apk"
        strip_signature(apk, stripped)
        run(maui_sdk_tool("zipalign"), "-P", "16", "-f", "4", stripped, destination / MAUI_UNSIGNED)
    run(maui_sdk_tool("zipalign"), "-c", "-P", "16", "4", destination / MAUI_UNSIGNED)
    maui_notices.apk_host_only(destination / MAUI_UNSIGNED)  # decision 20: a sealed candidate never carries binutils
    shutil.copyfile(MAUI_OUTPUT_DIR / "mapping.txt", destination / "mapping.txt")
    shutil.copyfile(ROOT / maui_notices.DISTRIBUTION_OUTPUT, destination / "THIRD_PARTY_NOTICES.txt")
    shutil.copyfile(ROOT / maui_notices.EVIDENCE, destination / "licence-closure.json")
    shutil.copyfile(ROOT / build_identity.MAUI_OUTPUT, destination / "build-identity.json")
    info = version()
    info.update(commit=os.environ["GITHUB_SHA"], package=MAUI_PACKAGE, track=MAUI_TRACK)
    identity = maui_identity.inspect_apk(apk, ROOT, release=False, configuration="Release")
    if identity["identity"]["versionCode"] != str(info["version_code"]) or identity["identity"]["versionName"] != info["version_name"]:
        raise ValueError("MAUI APK version differs from the allocated CI version")
    resources.save(destination / "maui-archive.json",
                   resources.maui_archive(apk, destination / "build-identity.json", ROOT, release=False,
                                          assemblies_root=ROOT / "src/ArcForges.Mobile/obj/Release/net10.0-android"))
    raw = (destination / "build-identity.json").read_bytes()
    build_identity.verify_maui_report(raw, info, ROOT, observed_sdk=json.loads(raw)["toolchain"]["sdk"]["observed"])
    info["sha256"] = {name: sha256(destination / name) for name in sorted(MAUI_CANDIDATE_FILES)}
    (destination / "candidate.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(f"Staged immutable MAUI candidate {info['version_name']} from {info['commit']}.")


def maui_sign(candidate, destination):
    """Sign the verified MAUI candidate with the persistent identity and seal release.json and SHA256SUMS."""
    import build_identity
    info = maui_verify_candidate(candidate)
    raw = (candidate / "build-identity.json").read_bytes()
    build_identity.verify_maui_report(raw, info, ROOT, observed_sdk=json.loads(raw)["toolchain"]["sdk"]["observed"])
    if any(not os.environ.get(name) for name in MAUI_SIGNING_ENVIRONMENT):
        raise ValueError("Configure the five Android signing settings documented in docs/releasing.md.")
    maui_notices.release_ready(ROOT)  # fail closed while any notice escalation is open
    if destination.exists():
        raise ValueError(f"Use an empty MAUI release output directory: {destination}")
    destination.mkdir(parents=True)
    expected = json.loads((ROOT / "eng/policy/dotnet-toolchain.json").read_text(encoding="utf-8"))["signing"]["certificateSha256"]
    with tempfile.TemporaryDirectory(prefix="arcforges-maui-sign-") as scratch:
        key = Path(scratch) / "release.jks"
        key.write_bytes(base64.b64decode(os.environ["ANDROID_KEYSTORE_BASE64"], validate=True))
        key.chmod(0o600)
        aligned = Path(scratch) / "aligned.apk"
        run(maui_sdk_tool("zipalign"), "-P", "16", "-f", "4", candidate / MAUI_UNSIGNED, aligned)
        apk = destination / f"ArcForges-{info['version_name']}.apk"
        run(maui_sdk_tool("apksigner"), "sign", "--ks", key, "--ks-key-alias", os.environ["ANDROID_KEY_ALIAS"],
            "--ks-pass", "env:ANDROID_KEYSTORE_PASSWORD", "--key-pass", "env:ANDROID_KEY_PASSWORD", "--out", apk, aligned)
        certificate = run(maui_sdk_tool("apksigner"), "verify", "--verbose", "--print-certs", apk, capture=True)
        fingerprint = verify_certificate(certificate, os.environ["ANDROID_SIGNING_CERT_SHA256"])
        run(maui_sdk_tool("zipalign"), "-c", "-P", "16", "4", apk)
        if fingerprint != expected:
            raise ValueError("The configured signing certificate differs from eng/policy/dotnet-toolchain.json")
    maui_notices.apk_host_only(apk)  # decision 20: the signed release APK carries no binutils member either
    release_identity = maui_identity.inspect_apk(apk, ROOT, release=True, configuration="Release")
    if release_identity["identity"]["versionCode"] != str(info["version_code"]):
        raise ValueError("Signed MAUI APK version differs from the candidate")
    info["certificate_sha256"] = fingerprint
    for name in MAUI_COMPANIONS:
        if name != "maui-archive.json":  # derived from the signed APK below (its digest and signer), not copied
            shutil.copyfile(candidate / name, destination / name)
    resources.save(destination / "maui-archive.json",
                   resources.maui_archive(apk, destination / "build-identity.json", ROOT, release=True))
    info["candidate_sha256"] = info.pop("sha256")
    info["track"] = MAUI_TRACK
    info["tag"] = f"android-{info['version_name']}"
    release_names = sorted(p.name for p in destination.iterdir())
    # The seal lists each published member by digest, as published.maui_verify reads it (the Kotlin path does too).
    info["sha256"] = {name: sha256(destination / name) for name in release_names}
    (destination / "release.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    checksums = "".join(f"{sha256(destination / name)}  {name}\n" for name in sorted(release_names + ["release.json"]))
    (destination / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    print(f"Verified signed MAUI APK: {info['version_name']} (certificate {fingerprint}).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "version", "hooks", "maui-stage", "maui-sign"])
    parser.add_argument("--candidate", type=Path, default=ROOT / "artifacts/maui-candidate")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/maui-release")
    args = parser.parse_args()
    if args.command == "check":
        repository_check()
    elif args.command == "version":
        data = version()
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                stream.writelines(f"{key}={value}\n" for key, value in data.items())
        print(json.dumps(data))
    elif args.command == "maui-stage":
        maui_stage(args.candidate)
    elif args.command == "maui-sign":
        maui_sign(args.candidate, args.output)
    else:
        run("git", "config", "extensions.worktreeConfig", "true")
        run("git", "config", "--worktree", "core.hooksPath", ".githooks")
        print("Enabled hooks for this checkout/worktree.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
