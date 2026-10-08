# SPDX-License-Identifier: Apache-2.0
"""AND.01 .NET MAUI identity, SDK pin, NuGet admission and built-APK identity checks (offline).

Kept apart from build_identity.py, whose bytes are reused from Contracts under provenance records.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


MAUI_PROJECT = "src/ArcForges.Mobile/ArcForges.Mobile.csproj"
MAUI_LOCK = "src/ArcForges.Mobile/packages.lock.json"
MAUI_MANIFEST = "src/ArcForges.Mobile/Platforms/Android/AndroidManifest.xml"
MAUI_TOOLCHAIN = "eng/policy/dotnet-toolchain.json"
MAUI_ADMISSION = "eng/policy/nuget-admission.json"
MAUI_PUBLISHED = "eng/published.py"
MAUI_CONTROLS = "Microsoft.Maui.Controls"
MAUI_CONTRACTS = "ArcForges.Contracts.PublicApi"
MAUI_TRIMMER = "Microsoft.NET.ILLink.Tasks"
MAUI_FIRST_PARTY = {"ArcForges.Contracts.Foundation", "ArcForges.Contracts.PublicApi"}
MAUI_ADMITTED_LICENCES = {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MIT"}
MAUI_FORBIDDEN_LICENCE = re.compile(r"AGPL|GPL|SSPL|BUSL|Proprietary|UNLICENSED", re.IGNORECASE)
MAUI_SHA512 = re.compile(r"[A-Za-z0-9+/]{86}==")
MAUI_RELEASE_CONDITION = "'$(Configuration)' == 'Release'"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _project(path: Path) -> tuple[dict, list, ET.Element]:
    """Unconditioned properties, conditioned (condition, name, value) triples and the project root."""
    root = ET.parse(path).getroot()
    plain, scoped = {}, []
    for group in root.findall("PropertyGroup"):
        condition = group.get("Condition", "")
        for child in group:
            if condition:
                scoped.append((condition, child.tag, (child.text or "").strip()))
            else:
                plain[child.tag] = (child.text or "").strip()
    return plain, scoped, root


def check_sdk_pin(root: Path, toolchain: dict) -> None:
    """global.json is the committed SDK pin; local adapters are never committed."""
    pin = _load_json(root / "global.json")
    dotnet = toolchain["dotnet"]
    _require(pin == {"sdk": {"version": dotnet["sdkVersion"], "rollForward": "disable", "allowPrerelease": False}},
             "global.json must pin the reviewed SDK exactly, with rollForward disabled")
    _require(re.fullmatch(r"10\.0\.\d{3}", dotnet["sdkVersion"]) is not None, "The SDK pin must be an exact .NET 10 SDK")


def check_build_policy(root: Path) -> None:
    props = (root / "Directory.Build.props").read_text(encoding="utf-8")
    for required in ("<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>",
                     "<DisableImplicitLibraryPacksFolder>true</DisableImplicitLibraryPacksFolder>",
                     "<NuGetAuditMode>all</NuGetAuditMode>",
                     "<TreatWarningsAsErrors>true</TreatWarningsAsErrors>",
                     "<Deterministic>true</Deterministic>",
                     "<RestoreLockedMode Condition=\"'$(CI)' == 'true'\">true</RestoreLockedMode>"):
        _require(required in props, f"Directory.Build.props lacks {required}")
    packages = (root / "Directory.Packages.props").read_text(encoding="utf-8")
    _require("<ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>" in packages,
             "Central package management must be enabled")
    config = ET.parse(root / "NuGet.config").getroot()
    sources = [(add.get("key"), add.get("value")) for add in config.findall("./packageSources/add")]
    _require(sources == [("nuget.org", "https://api.nuget.org/v3/index.json")],
             "NuGet.config must declare exactly the nuget.org source")
    _require(config.find("./packageSources/clear") is not None, "NuGet.config must clear inherited sources")
    mapping = [(m.get("key"), [p.get("pattern") for p in m.findall("package")])
               for m in config.findall("./packageSourceMapping/packageSource")]
    _require(mapping == [("nuget.org", ["*"])], "Every package must map to nuget.org only")


def check_project(root: Path, toolchain: dict) -> None:
    android = toolchain["android"]
    plain, scoped, project = _project(root / MAUI_PROJECT)
    expected = {
        "TargetFrameworks": toolchain["targetFramework"],
        "OutputType": "Exe",
        "UseMaui": "true",
        "RootNamespace": android["namespace"],
        "ApplicationId": android["applicationId"],
        "SupportedOSPlatformVersion": f"{android['minSdkVersion']}.0",
        "TargetPlatformVersion": android["targetPlatformVersion"],
        "AndroidSdkBuildToolsVersion": android["buildToolsVersion"],
        "UseMonoRuntime": "true",
    }
    for name, value in expected.items():
        _require(plain.get(name) == value, f"{name} must be {value!r} in {MAUI_PROJECT}")
    links = [(condition, value) for condition, name, value in scoped if name == "AndroidLinkTool"]
    _require(links == [(MAUI_RELEASE_CONDITION, "r8")], "AndroidLinkTool r8 must apply only to the Release configuration")
    signing = [name for _, name, _ in scoped if name.startswith("AndroidSigning") or name == "AndroidKeyStore"]
    signing += [name for name in plain if name.startswith("AndroidSigning") or name == "AndroidKeyStore"]
    _require(not signing, "Signing belongs to the protected release job, not the identity project build")
    references = [item.get("Include") for item in project.iter("PackageReference")]
    _require(sorted(references) == sorted([MAUI_CONTROLS, MAUI_CONTRACTS, MAUI_TRIMMER]),
             "The identity project references only Maui, the Contracts client and the pinned trimmer")
    for item in project.iter("PackageReference"):
        _require(item.get("Version") is None and item.get("VersionOverride") is None,
                 "PackageReference versions must come from Directory.Packages.props")
    manifest = (root / MAUI_MANIFEST).read_text(encoding="utf-8")
    _require('android:allowBackup="false"' in manifest and 'android:usesCleartextTraffic="false"' in manifest,
             "The Android manifest must keep the baseline backup and cleartext restrictions")
    _require(' package="' not in manifest, "applicationId must come from the project, not the manifest")
    namespace = android["namespace"]
    project_dir = root / "src/ArcForges.Mobile"
    for source in sorted(project_dir.rglob("*.cs")):
        if {"bin", "obj"} & set(source.relative_to(project_dir).parts):
            continue  # build outputs are never committed and never reviewed as source
        for declared in re.findall(r"^namespace\s+([A-Za-z_][\w.]*)", source.read_text(encoding="utf-8"), re.MULTILINE):
            _require(declared == namespace or declared.startswith(namespace + "."),
                     f"Source namespace outside {namespace}: {source.relative_to(root).as_posix()}")


def check_records(toolchain: dict, admission: dict) -> None:
    """The recorded D-016 target decision, the AND.40 deferrals and the BSD-2-Clause notice obligation."""
    android = toolchain["android"]
    decision = android["targetPlatformDecision"]
    _require(decision.get("value") == android["targetPlatformVersion"],
             "The recorded D-016 target API decision differs from the pinned target")
    _require(str(decision.get("authority", "")).startswith("D-016"), "The target API decision must cite D-016")
    deferrals = {item.get("id"): item for item in toolchain.get("deferrals", [])}
    _require({"linux-android-build-proof", "bsd-2-clause-glide-notice"} <= set(deferrals),
             "The Linux Android build proof and the Glide notice must be recorded as AND.40 deferrals")
    for identifier, item in deferrals.items():
        for key in ("owner", "trigger", "consequence"):
            _require(item.get(key), f"Deferral {identifier} lacks {key}")
        _require(item["owner"] == "AND.40", f"Deferral {identifier} must be owned by AND.40")
    _require("AND.40" in admission.get("licenceExceptions", {}).get("BSD-2-Clause", ""),
             "The BSD-2-Clause exception must name its AND.40 notice obligation")


def check_packages_props(root: Path, toolchain: dict) -> None:
    versions = {item.get("Include"): item.get("Version")
                for item in ET.parse(root / "Directory.Packages.props").getroot().iter("PackageVersion")}
    _require(versions == {MAUI_CONTROLS: toolchain["maui"]["controlsVersion"],
                          MAUI_CONTRACTS: toolchain["contracts"]["version"],
                          MAUI_TRIMMER: toolchain["trimmer"]["version"]},
             "Directory.Packages.props differs from the reviewed MAUI, Contracts and trimmer pins")


def check_lock(root: Path, toolchain: dict, admission: dict) -> None:
    lock_path = root / MAUI_LOCK
    lock = _load_json(lock_path)
    _require(lock.get("version") == 2, "packages.lock.json must use lock version 2")
    _require(hashlib.sha256(lock_path.read_bytes()).hexdigest() == admission["lockSha256"],
             "packages.lock.json changed without a new NuGet admission record")
    target = toolchain["targetFramework"] + toolchain["android"]["targetPlatformVersion"]
    _require(sorted(key for key in lock["dependencies"] if "/" not in key) == [target],
             "packages.lock.json must lock exactly the reviewed Android target")
    locked, direct = set(), set()
    for name, info in lock["dependencies"][target].items():
        _require(info["type"] != "Project", "The identity project must not reference other projects")
        _require(MAUI_SHA512.fullmatch(info.get("contentHash", "")) is not None, f"Invalid content hash: {name}")
        kind = "direct" if info["type"] == "Direct" else "transitive"
        if kind == "direct":
            direct.add(name)
        locked.add((name, info["resolved"], info["contentHash"], kind))
    recorded = {(item["id"], item["version"], item["contentHash"], item["kind"]) for item in admission["packages"]}
    _require(locked == recorded, "The locked closure differs from the NuGet admission record")
    _require(direct == {MAUI_CONTROLS, MAUI_CONTRACTS, MAUI_TRIMMER},
             "Direct packages must be Maui, the Contracts client and the pinned trimmer")
    admitted = set(admission["admittedLicences"])
    _require(admitted <= MAUI_ADMITTED_LICENCES, "Unexpected admitted licence")
    for item in admission["packages"]:
        name, licence = item["id"], item["licence"]
        _require(MAUI_SHA512.fullmatch(item["nupkgSha512"]) is not None, f"Invalid nupkg hash: {name}")
        _require(not MAUI_FORBIDDEN_LICENCE.search(licence), f"Forbidden licence: {name}")
        tokens = [t for t in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", licence) if t.strip()]
        _require(tokens and all(token.strip() in admitted for token in tokens),
                 f"Unadmitted licence for {name}: {licence}")
        if name.startswith("ArcForges."):
            _require(name in MAUI_FIRST_PARTY and licence == "Apache-2.0",
                     f"First-party package outside the Apache Contracts client: {name}")
        if not item["licenceFiles"]:
            _require(item["noticeDisposition"].startswith("nuspec-expression-only"), f"Missing notice disposition: {name}")
    if "BSD-2-Clause" in admitted:
        _require(admission.get("licenceExceptions", {}).get("BSD-2-Clause"), "BSD-2-Clause needs its recorded exception")


def check_maui(root: Path = ROOT) -> dict:
    """Offline AND.01 identity and toolchain gate; raises ValueError on any drift."""
    toolchain = _load_json(root / MAUI_TOOLCHAIN)
    admission = _load_json(root / MAUI_ADMISSION)
    _require(toolchain.get("schemaVersion") == 1 and toolchain.get("owner") == "Mobile"
             and toolchain.get("licenceBoundary") == "Apache", "Invalid toolchain record owner")
    _require(toolchain["targetFramework"] == "net10.0-android", "Only net10.0-android is admitted for Mobile projects")
    certificate = toolchain["signing"]["certificateSha256"]
    _require(re.search(rf"^CERTIFICATE = '{certificate}'$", (root / MAUI_PUBLISHED).read_text(encoding="utf-8"),
                       re.MULTILINE) is not None,
             "The persistent release certificate differs from eng/published.py")
    check_sdk_pin(root, toolchain)
    check_build_policy(root)
    check_project(root, toolchain)
    check_packages_props(root, toolchain)
    check_lock(root, toolchain, admission)
    check_records(toolchain, admission)
    android = toolchain["android"]
    return {"schema": "arcforges.maui-identity.v1", "applicationId": android["applicationId"],
            "namespace": android["namespace"], "targetFramework": toolchain["targetFramework"],
            "targetPlatformVersion": android["targetPlatformVersion"], "sdk": toolchain["dotnet"]["sdkVersion"],
            "lockSha256": admission["lockSha256"], "certificateSha256": certificate}


def parse_badging(text: str) -> dict:
    """Package identity and API levels from `aapt2 dump badging` output."""
    package = re.search(r"^package: name='([^']*)' versionCode='([^']*)' versionName='([^']*)'", text, re.MULTILINE)
    min_sdk = re.search(r"^minSdkVersion:'(\d+)'", text, re.MULTILINE)
    target_sdk = re.search(r"^targetSdkVersion:'(\d+)'", text, re.MULTILINE)
    _require(package is not None and min_sdk is not None and target_sdk is not None,
             "Badging output lacks package or SDK identity")
    return {"package": package[1], "versionCode": package[2], "versionName": package[3],
            "minSdk": int(min_sdk[1]), "targetSdk": int(target_sdk[1])}


def parse_signer_digests(text: str) -> list[str]:
    return re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$", text, re.MULTILINE)


def check_apk(badging: str, certificates: str, root: Path = ROOT, release: bool = False) -> dict:
    """Identity of a built APK; a release proof must carry the persistent release certificate."""
    toolchain = _load_json(root / MAUI_TOOLCHAIN)
    android = toolchain["android"]
    identity = parse_badging(badging)
    _require(identity["package"] == android["applicationId"], "APK applicationId differs from com.arcforges.mobile")
    _require(identity["minSdk"] == android["minSdkVersion"], "APK minSdkVersion differs from the reviewed floor")
    _require(identity["targetSdk"] == int(android["targetPlatformVersion"].split(".")[0]),
             "APK targetSdkVersion differs from the reviewed target")
    digests = parse_signer_digests(certificates)
    _require(len(digests) == 1, "APK must have exactly one signer")
    if release:
        _require(digests == [toolchain["signing"]["certificateSha256"]],
                 "Release APK is not signed by the persistent release certificate")
    return {"identity": identity, "signerSha256": digests[0], "release": release}


def inspect_apk(apk: Path, root: Path = ROOT, release: bool = False) -> dict:
    """Run the Android build tools found through ANDROID_HOME on a built APK."""
    toolchain = _load_json(root / MAUI_TOOLCHAIN)
    sdk = Path(os.environ.get("ANDROID_HOME") or Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk")
    tools = sdk / "build-tools" / toolchain["android"]["buildToolsVersion"]
    aapt2 = tools / ("aapt2.exe" if os.name == "nt" else "aapt2")
    apksigner = tools / ("apksigner.bat" if os.name == "nt" else "apksigner")
    badging = subprocess.run([str(aapt2), "dump", "badging", str(apk)], check=True, capture_output=True,
                             text=True, encoding="utf-8").stdout
    certificates = subprocess.run([str(apksigner), "verify", "--print-certs", str(apk)], check=True,
                                  capture_output=True, text=True, encoding="utf-8").stdout
    return check_apk(badging, certificates, root, release)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, help="also inspect this built APK")
    parser.add_argument("--release", action="store_true", help="with --apk: require the persistent release certificate")
    args = parser.parse_args()
    print(json.dumps(check_maui(ROOT), indent=2, sort_keys=True))
    if args.apk:
        print(json.dumps(inspect_apk(args.apk, ROOT, args.release), indent=2, sort_keys=True))
