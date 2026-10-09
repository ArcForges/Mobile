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
# AND.01 identity-only shape (P2-021 item 3): the project holds these files and nothing else. The Contracts file is
# compile-only evidence; no App, MainPage, MauiProgram, MainActivity, Resources or permission belongs in this stage.
MAUI_CONTRACTS_EVIDENCE = "src/ArcForges.Mobile/Compatibility/ContractsClientCompatibility.cs"
# AndroidX Core merges this signature-level permission, declared by the application package itself, into every app
# (aapt2 xmltree: protectionLevel 0x2). It grants no capability to another app and is the only permission allowed.
MAUI_MERGED_PERMISSION = "com.arcforges.mobile.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"
MAUI_IDENTITY_FILES = {MAUI_PROJECT, MAUI_LOCK, MAUI_MANIFEST, MAUI_CONTRACTS_EVIDENCE}
# The SDK adds INTERNET to the Debug manifest of a debuggable app; the identity manifest removes it with tools:node="remove".
MAUI_INTERNET = "android.permission.INTERNET"
MAUI_NAME_ATTRIBUTE = "{http://schemas.android.com/apk/res/android}name"
MAUI_TOOLS_NODE = "{http://schemas.android.com/tools}node"
MAUI_TOOLCHAIN = "eng/policy/dotnet-toolchain.json"
# The identity project is classified here, apart from the Gradle roster that the Kotlin baseline gates read (AND.01).
MAUI_LICENCE_REGISTRY = "eng/policy/dotnet-licence-boundary.json"
MAUI_GRADLE_ROSTER = "eng/policy/licence-boundary.json"
# AND.40 unit 2: the platform-neutral Hello transport library and its host tests are reviewed .NET projects too. Each is
# Apache-2.0, and none may appear on the Gradle roster. Any other .NET project is refused by the registry check.
MAUI_REVIEWED_DOTNET_PROJECTS = (
    MAUI_PROJECT,
    "src/core/ArcForges.Mobile.Network/ArcForges.Mobile.Network.csproj",
    "tests/ArcForges.Mobile.Tests/ArcForges.Mobile.Tests.csproj",
)
MAUI_ADMISSION = "eng/policy/nuget-admission.json"
# AND.40 unit 1: test-only packages (xUnit family, Microsoft.NET.Test.Sdk). Never referenced by the identity project.
MAUI_TEST_ADMISSION = "eng/policy/nuget-test-admission.json"
MAUI_DEPENDENCY_POLICY = "eng/policy/dependency-policy.json"
MAUI_REVIEWS = "eng/policy/dependency-reviews"
MAUI_WORKLOADS = "eng/policy/workload-admission.json"
MAUI_PUBLISHED = "eng/published.py"
MAUI_CONTROLS = "Microsoft.Maui.Controls"
MAUI_CONTRACTS = "ArcForges.Contracts.PublicApi"
MAUI_EVENTS = "ArcForges.Contracts.Events"
MAUI_GRPC_CLIENT = "Grpc.Net.Client"
MAUI_GRPC_WEB = "Grpc.Net.Client.Web"
MAUI_TRIMMER = "Microsoft.NET.ILLink.Tasks"
# Every direct package of the identity project. Products are pinned in dotnet-toolchain.json; no other package may be referenced.
MAUI_DIRECT = {MAUI_CONTROLS, MAUI_CONTRACTS, MAUI_EVENTS, MAUI_GRPC_CLIENT, MAUI_GRPC_WEB, MAUI_TRIMMER}
MAUI_PRODUCT_DIRECT = {MAUI_EVENTS, MAUI_GRPC_CLIENT, MAUI_GRPC_WEB}
MAUI_FIRST_PARTY = {"ArcForges.Contracts.Foundation", "ArcForges.Contracts.PublicApi", MAUI_EVENTS}
# The reviewer named by every AND.40 receipt and admission record; never PENDING (coordinator adjudication 2026-10-08).
MAUI_REVIEWER = "w-deku-20261008-rev-and-40"
MAUI_ADMITTED_LICENCES = {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MIT"}
MAUI_FORBIDDEN_LICENCE = re.compile(r"AGPL|GPL|SSPL|BUSL|Proprietary|UNLICENSED", re.IGNORECASE)
MAUI_SHA512 = re.compile(r"[A-Za-z0-9+/]{86}==")
MAUI_SHA256 = re.compile(r"[0-9a-f]{64}")
MAUI_RELEASE_CONDITION = "'$(Configuration)' == 'Release'"
MAUI_REQUIRED_DEFERRALS = {
    "linux-android-build-proof",
    "bsd-2-clause-glide-notice",
    "nuget-notice-google-protobuf-3-36-1",
    "nuget-notice-grpc-core-api-2-84-0",
    "workload-pack-notices",
    "workload-licence-evidence",
}


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


def check_licence_registration(root: Path) -> None:
    """The identity project is audited through the .NET inventory (eng/licences.py dotnet_audit) and is absent from the Gradle roster."""
    registry = _load_json(root / MAUI_LICENCE_REGISTRY)
    expected = sorted(({"path": path, "kind": "dotnet"} for path in MAUI_REVIEWED_DOTNET_PROJECTS), key=lambda item: item["path"])
    registered = registry.get("projects")
    _require(isinstance(registered, list) and sorted(registered, key=lambda item: str(item.get("path"))) == expected
             and registry.get("spdxLicense") == "Apache-2.0" and registry.get("licenceBoundary") == "Apache",
             f"{MAUI_LICENCE_REGISTRY} must register exactly the reviewed .NET projects as Apache-2.0 / Apache")
    roster = _load_json(root / MAUI_GRADLE_ROSTER)
    rostered = {item.get("path") for item in roster.get("projects", [])}
    _require(not rostered & set(MAUI_REVIEWED_DOTNET_PROJECTS),
             f"The Gradle licence roster ({MAUI_GRADLE_ROSTER}) must not carry a .NET project")


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
        "AndroidEnableProfiler": "false",
    }
    for name, value in expected.items():
        _require(plain.get(name) == value, f"{name} must be {value!r} in {MAUI_PROJECT}")
    links = [(condition, value) for condition, name, value in scoped if name == "AndroidLinkTool"]
    _require(links == [(MAUI_RELEASE_CONDITION, "r8")], "AndroidLinkTool r8 must apply only to the Release configuration")
    signing = [name for _, name, _ in scoped if name.startswith("AndroidSigning") or name == "AndroidKeyStore"]
    signing += [name for name in plain if name.startswith("AndroidSigning") or name == "AndroidKeyStore"]
    _require(not signing, "Signing belongs to the protected release job, not the identity project build")
    references = [item.get("Include") for item in project.iter("PackageReference")]
    _require(len(references) == len(set(references)) and set(references) == MAUI_DIRECT,
             "The identity project references only Maui, the Contracts client and events, the Hello transport and the pinned trimmer")
    for item in project.iter("PackageReference"):
        _require(item.get("Version") is None and item.get("VersionOverride") is None,
                 "PackageReference versions must come from Directory.Packages.props")
    manifest = (root / MAUI_MANIFEST).read_text(encoding="utf-8")
    _require('android:allowBackup="false"' in manifest and 'android:usesCleartextTraffic="false"' in manifest,
             "The Android manifest must keep the baseline backup and cleartext restrictions")
    _require(' package="' not in manifest, "applicationId must come from the project, not the manifest")
    check_identity_only_shape(root)
    namespace = android["namespace"]
    project_dir = root / "src/ArcForges.Mobile"
    for source in sorted(project_dir.rglob("*.cs")):
        if {"bin", "obj"} & set(source.relative_to(project_dir).parts):
            continue  # build outputs are never committed and never reviewed as source
        for declared in re.findall(r"^namespace\s+([A-Za-z_][\w.]*)", source.read_text(encoding="utf-8"), re.MULTILINE):
            _require(declared == namespace or declared.startswith(namespace + "."),
                     f"Source namespace outside {namespace}: {source.relative_to(root).as_posix()}")


def check_identity_only_shape(root: Path) -> None:
    """AND.01 identity-only shape: exact project file set, no permission and no component in the manifest."""
    project_dir = root / "src/ArcForges.Mobile"
    present = {path.relative_to(root).as_posix() for path in project_dir.rglob("*")
               if path.is_file() and not {"bin", "obj"} & set(path.relative_to(project_dir).parts)}
    _require(present == MAUI_IDENTITY_FILES,
             f"The identity project holds only its identity-only files; unexpected: "
             f"{sorted(present - MAUI_IDENTITY_FILES)}, missing: {sorted(MAUI_IDENTITY_FILES - present)}")
    manifest = ET.parse(root / MAUI_MANIFEST).getroot()
    children = list(manifest)
    # The only permission element allowed is the removal marker of the SDK's Debug INTERNET injection (see docs/maui-toolchain.md).
    permissions = [child for child in children if child.tag == "uses-permission"]
    _require(manifest.tag == "manifest" and [child.tag for child in children if child.tag != "uses-permission"] == ["application"],
             "The identity manifest declares no element other than application and the INTERNET removal marker")
    _require(len(permissions) <= 1 and all(
                 item.get(MAUI_NAME_ATTRIBUTE) == MAUI_INTERNET and item.get(MAUI_TOOLS_NODE) == "remove"
                 for item in permissions),
             "The identity manifest may only remove android.permission.INTERNET (tools:node=\"remove\"); it grants no permission")
    application = next(child for child in children if child.tag == "application")
    _require(len(list(application)) == 0, "The identity manifest declares no activity or other component")


def check_records(toolchain: dict, admission: dict) -> None:
    """The recorded D-016 target decision, the AND.40 deferrals and the BSD-2-Clause notice obligation."""
    android = toolchain["android"]
    decision = android["targetPlatformDecision"]
    _require(decision.get("value") == android["targetPlatformVersion"],
             "The recorded D-016 target API decision differs from the pinned target")
    _require(str(decision.get("authority", "")).startswith("D-016"), "The target API decision must cite D-016")
    deferrals = {item.get("id"): item for item in toolchain.get("deferrals", [])}
    _require(MAUI_REQUIRED_DEFERRALS <= set(deferrals),
             "The Linux Android build proof, the Glide notice, the NuGet notices and the workload licence "
             "evidence must be recorded as AND.40 deferrals")
    for identifier, item in deferrals.items():
        for key in ("owner", "trigger", "consequence"):
            _require(item.get(key), f"Deferral {identifier} lacks {key}")
        _require(item["owner"] == "AND.40", f"Deferral {identifier} must be owned by AND.40")
    _require("AND.40" in admission.get("licenceExceptions", {}).get("BSD-2-Clause", ""),
             "The BSD-2-Clause exception must name its AND.40 notice obligation")


def check_packages_props(root: Path, toolchain: dict, test_record: dict) -> None:
    """Central versions: the product pins of dotnet-toolchain.json plus the test-only pins of the test-scope record, nothing else."""
    versions = {item.get("Include"): item.get("Version")
                for item in ET.parse(root / "Directory.Packages.props").getroot().iter("PackageVersion")}
    product = toolchain["packages"]["direct"]
    _require(set(product) == MAUI_PRODUCT_DIRECT,
             "dotnet-toolchain.json must pin exactly the Contracts events and the Grpc transport packages as product directs")
    test_direct = {item["id"]: item["version"] for item in test_record["packages"] if item["kind"] == "direct"}
    expected = {MAUI_CONTROLS: toolchain["maui"]["controlsVersion"],
                MAUI_CONTRACTS: toolchain["contracts"]["version"],
                MAUI_TRIMMER: toolchain["trimmer"]["version"]}
    expected.update(product)
    _require(not set(test_direct) & set(expected), "A test-only package must not be a product pin")
    expected.update(test_direct)
    _require(versions == expected,
             "Directory.Packages.props differs from the reviewed MAUI, Contracts, trimmer, transport and test-only pins")


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
    _require(direct == MAUI_DIRECT,
             "Direct packages must be Maui, the Contracts client and events, the Hello transport and the pinned trimmer")
    check_prerelease(lock["dependencies"][target], admission)
    # A package whose nupkg carries no licence file needs one AND.40 notice deferral naming it, and no deferral may be stale.
    unnoticed = {(item["id"], item["version"], item["licence"]) for item in admission["packages"] if not item["licenceFiles"]}
    notice_deferrals = [item for item in toolchain.get("deferrals", []) if "package" in item]
    recorded = {(item["package"], item["version"], item["licence"]) for item in notice_deferrals}
    _require(len(recorded) == len(notice_deferrals) and recorded == unnoticed,
             "Each package without a licence file needs exactly one AND.40 notice deferral, and no notice deferral may be stale")
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


def check_prerelease(locked_target: dict, admission: dict) -> None:
    """Every prerelease third-party package needs one explicit exception naming a parent that really depends on it.

    First-party candidates are admitted by their own rule (exact Contracts versions). AND.40 decision 10: the
    Xamarin.AndroidX.Security.SecurityCrypto 1.1.0.4-alpha07 pulled in by Microsoft.Maui.Essentials is required by MAUI.
    """
    exceptions = {(item.get("id"), item.get("version")): item for item in admission.get("prereleaseExceptions", [])}
    used = set()
    for item in admission["packages"]:
        name, version = item["id"], item["version"]
        if "-" not in version or name in MAUI_FIRST_PARTY:
            continue
        exception = exceptions.get((name, version))
        _require(exception is not None, f"Prerelease package needs an explicit admission exception: {name} {version}")
        parent = exception.get("requiredBy", "")
        parent_info = locked_target.get(parent)
        _require(parent_info is not None and parent_info.get("dependencies", {}).get(name) == version,
                 f"Prerelease exception for {name} {version} names a parent that does not require it: {parent}")
        _require(str(exception.get("reason", "")).strip(), f"Prerelease exception for {name} {version} lacks a reason")
        used.add((name, version))
    _require(set(exceptions) == used, "A prerelease exception is stale or names a package outside the locked closure")


def _check_workload_pack(pack: dict, pin: dict, nuget_versions: dict, deferral_ids: set, alias: str) -> None:
    pid = pack.get("id")
    if pack.get("source") == "nuget-admission":
        # MAUI library packs are restored from the NuGet closure, so they must match its locked version.
        _require(pack.get("kind") == "library" and nuget_versions.get(pid) == pack.get("version") == pin["packVersion"],
                 f"Library pack {pid} differs from the NuGet admission and the pinned {alias} version")
        return
    _require(pack.get("version") == pin["packVersion"], f"Pack {pid} differs from the pinned {alias} pack version")
    licence = pack.get("licence")
    if licence is None:
        evidence = pack.get("licenceEvidence") or {}
        _require(evidence.get("status") == "deferred" and evidence.get("deferral") == "workload-licence-evidence"
                 and "workload-licence-evidence" in deferral_ids,
                 f"Pack {pid} has neither a licence nor its AND.40 licence-evidence deferral")
    else:
        tokens = [t for t in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", licence) if t.strip()]
        _require(tokens and all(token.strip() in MAUI_ADMITTED_LICENCES for token in tokens)
                 and not MAUI_FORBIDDEN_LICENCE.search(licence), f"Unadmitted workload licence for {pid}: {licence}")
        licence_file = pack.get("licenceFile") or {}
        _require(str(licence_file.get("path", "")).startswith("packs/")
                 and MAUI_SHA256.fullmatch(str(licence_file.get("sha256", ""))) is not None,
                 f"Pack {pid} lacks its licence file path and SHA-256")
    if pack.get("unverifiedHostAliases"):
        _require("workload-licence-evidence" in deferral_ids,
                 f"Pack {pid} has unverified host aliases without its AND.40 deferral")


def check_workloads(root: Path, toolchain: dict, admission: dict) -> None:
    """AND.01 workload admission: manifest pins, declared-pack partition, licence evidence and NuGet cross-check."""
    record = _load_json(root / MAUI_WORKLOADS)
    _require(record.get("schemaVersion") == 1 and record.get("owner") == "Mobile"
             and record.get("licenceBoundary") == "Apache", "Invalid workload admission record owner")
    _require(record["reviewedHost"]["sdkPinned"] == toolchain["dotnet"]["sdkVersion"],
             "The workload admission record must cite the pinned SDK version")
    deferral_ids = {item.get("id") for item in toolchain.get("deferrals", [])}
    nuget_versions = {item["id"]: item["version"] for item in admission["packages"]}
    pins = toolchain["workloads"]
    entries = {item.get("alias"): item for item in record.get("workloads", [])}
    _require(len(entries) == len(record.get("workloads", [])) and set(entries) == set(pins),
             "The workload admission record must cover exactly the pinned workloads")
    for alias, pin in pins.items():
        entry = entries[alias]
        _require(entry.get("id") == pin["id"] and entry.get("manifestVersion") == pin["manifestVersion"]
                 and entry.get("packVersion") == pin["packVersion"],
                 f"Workload {alias} differs from its reviewed manifest and pack pins")
        files = entry.get("manifestFiles", {})
        _require("WorkloadManifest.json" in files and all(MAUI_SHA256.fullmatch(value or "") for value in files.values()),
                 f"Workload {alias} lacks SHA-256 hashes of its manifest files")
        declared = entry.get("declaredPacks", [])
        admitted = entry.get("admittedPacks", [])
        excluded = entry.get("excludedPacks", [])
        _require(len(set(declared)) == len(declared)
                 and sorted(item.get("id") for item in admitted + excluded) == sorted(declared),
                 f"Workload {alias} must partition its declared packs into admitted and excluded")
        for item in excluded:
            _require(str(item.get("reason", "")).strip(), f"Excluded pack lacks a reason: {item.get('id')}")
        for pack in admitted:
            _check_workload_pack(pack, pin, nuget_versions, deferral_ids, alias)
    for item in record.get("excludedManifests", []):
        _require(str(item.get("reason", "")).strip() and item.get("manifestVersion"),
                 f"Excluded manifest lacks a version or reason: {item.get('id')}")


def check_test_admission(test_record: dict) -> None:
    """Test-only closure (xUnit family, Microsoft.NET.Test.Sdk): Apache or MIT, never distributed, reviewed by AND.40."""
    _require(test_record.get("schemaVersion") == 1 and test_record.get("owner") == "Mobile"
             and test_record.get("licenceBoundary") == "Apache", "Invalid test-scope admission owner")
    _require(test_record.get("reviewer") == MAUI_REVIEWER, "The test-scope admission must name the AND.40 reviewer")
    _require(test_record.get("targetFramework") == "net10.0", "Test projects target net10.0 (AND.40 decision 1)")
    _require("test-only" in str(test_record.get("scope", "")), "The test-scope record must state its test-only scope")
    ids = [item.get("id") for item in test_record.get("packages", [])]
    _require(ids and len(ids) == len(set(ids)), "The test-scope record needs unique packages")
    _require(MAUI_TRIMMER not in ids and not set(ids) & MAUI_DIRECT, "A product package appears in the test-only record")
    for item in test_record["packages"]:
        name, licence = item["id"], item["licence"]
        _require(item.get("kind") in {"direct", "transitive"}, f"Invalid test-scope kind: {name}")
        _require(MAUI_SHA512.fullmatch(item.get("contentHash", "")) is not None, f"Invalid test-scope content hash: {name}")
        _require(MAUI_SHA512.fullmatch(item.get("nupkgSha512", "")) is not None, f"Invalid test-scope nupkg hash: {name}")
        _require(not MAUI_FORBIDDEN_LICENCE.search(licence), f"Forbidden test-scope licence: {name}")
        tokens = [t for t in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", licence) if t.strip()]
        _require(tokens and all(token.strip() in {"Apache-2.0", "MIT"} for token in tokens),
                 f"Test-scope licence outside Apache-2.0 and MIT: {name}: {licence}")
        if not item.get("licenceFiles"):
            _require(str(item.get("noticeDisposition", "")).startswith("test-only:"),
                     f"A test-scope package without licence files needs a test-only disposition: {name}")
    _require(any(item["kind"] == "direct" for item in test_record["packages"]),
             "The test-scope record must name its direct packages")


def check_receipts(root: Path, admission: dict, test_record: dict, toolchain: dict) -> None:
    """Every AND.40 admission record and the active inventory receipt name the AND.40 reviewer; none says PENDING."""
    records = {MAUI_ADMISSION: admission, MAUI_TEST_ADMISSION: test_record, MAUI_TOOLCHAIN: toolchain}
    for name, record in records.items():
        _require(record.get("reviewer") == MAUI_REVIEWER, f"{name} must name the AND.40 reviewer")
        _require("PENDING" not in (root / name).read_text(encoding="utf-8"), f"{name} must not say PENDING")
    policy = _load_json(root / MAUI_DEPENDENCY_POLICY)
    inventory = [name for name in policy["reviews"] if name.startswith("maui-identity-inventory-")]
    _require(inventory, "The MAUI identity inventory receipt chain is empty")
    active = _load_json(root / MAUI_REVIEWS / inventory[-1])
    _require(active.get("reviewer") == MAUI_REVIEWER, f"The active MAUI inventory receipt {inventory[-1]} must name the AND.40 reviewer")
    _require("PENDING" not in (root / MAUI_REVIEWS / inventory[-1]).read_text(encoding="utf-8"),
             f"The active MAUI inventory receipt {inventory[-1]} must not say PENDING")


def check_maui(root: Path = ROOT) -> dict:
    """Offline AND.01 identity and toolchain gate; raises ValueError on any drift."""
    toolchain = _load_json(root / MAUI_TOOLCHAIN)
    admission = _load_json(root / MAUI_ADMISSION)
    test_record = _load_json(root / MAUI_TEST_ADMISSION)
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
    check_licence_registration(root)
    check_packages_props(root, toolchain, test_record)
    check_lock(root, toolchain, admission)
    check_test_admission(test_record)
    check_receipts(root, admission, test_record, toolchain)
    check_workloads(root, toolchain, admission)
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
    permissions = re.findall(r"^uses-permission(?:-sdk-\d+)?: name='([^']*)'", badging, re.MULTILINE)
    _require(set(permissions) <= {MAUI_MERGED_PERMISSION} and "android.permission.INTERNET" not in permissions,
             "The identity APK requests no permission except the AndroidX merged signature permission")
    _require(not re.search(r"^(uses-implied-permission|(leanback-)?launchable-activity)", badging, re.MULTILINE),
             "The identity APK declares no launchable activity and no implied permission")
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
