# SPDX-License-Identifier: Apache-2.0
"""Mobile-owned support metadata; compatibility versions never follow releases."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
AXES = ("AppVersion", "ContractSet", "CapabilityVersion", "NativeFormatVersion",
        "StorageSchemaVersion", "NativeAbiVersion", "PolicySchemaVersion",
        "ExtensionProtocolVersion", "PackageVersion")
KINDS = ("release", "contracts", "declarations", "declarations", "migrations",
         "native-abi", "declarations", "declarations", "packages")


def git(*arguments: str, root: Path = ROOT) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, text=True, encoding="utf-8",
                                   env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}).strip()


def build(root: Path = ROOT, environment: dict | None = None) -> dict:
    env = os.environ if environment is None else environment
    commit = git("rev-parse", "HEAD", root=root)
    dirty = bool(git("status", "--porcelain", root=root))
    epoch = int(git("show", "-s", "--format=%ct", commit, root=root))
    ci = env.get("GITHUB_ACTIONS") == "true" or env.get("CI", "").lower() == "true"
    result = {"sourceCommit": commit, "dirty": dirty, "kind": "ci" if ci else "local",
              "buildId": "local." + commit, "runId": None, "runAttempt": None,
              "pipelineRun": None, "sourceDateEpoch": epoch}
    if ci:
        run, attempt = env.get("GITHUB_RUN_ID", ""), env.get("GITHUB_RUN_ATTEMPT", "")
        if (dirty or env.get("GITHUB_SHA") != commit
                or env.get("GITHUB_REPOSITORY") != "ArcForges/Mobile"
                or not re.fullmatch(r"[1-9][0-9]*", run)
                or not re.fullmatch(r"[1-9][0-9]*", attempt)
                or env.get("GITHUB_SERVER_URL") != "https://github.com"):
            raise ValueError("Incomplete, dirty or mismatched CI build identity")
        result.update(buildId=f"{run}.{attempt}", runId=run, runAttempt=int(attempt),
                      pipelineRun=f"https://github.com/ArcForges/Mobile/actions/runs/{run}")
    validate_build(result)
    return result


def validate_build(value: dict) -> None:
    if (set(value) != {"sourceCommit", "dirty", "kind", "buildId", "runId", "runAttempt", "pipelineRun", "sourceDateEpoch"}
            or not re.fullmatch(r"[0-9a-f]{40}", value["sourceCommit"])
            or type(value["dirty"]) is not bool or type(value["sourceDateEpoch"]) is not int
            or value["sourceDateEpoch"] <= 0):
        raise ValueError("Malformed build identity")
    if value["kind"] == "ci":
        run, attempt = value["runId"], value["runAttempt"]
        if (not isinstance(run, str) or not re.fullmatch(r"[1-9][0-9]*", run)
                or type(attempt) is not int or attempt < 1 or value["dirty"]
                or value["buildId"] != f"{run}.{attempt}"
                or value["pipelineRun"] != f"https://github.com/ArcForges/Mobile/actions/runs/{run}"):
            raise ValueError("Malformed CI build identity")
    elif value["kind"] != "local" or value["buildId"] != "local." + value["sourceCommit"] or any(value[key] is not None for key in ("runId", "runAttempt", "pipelineRun")):
        raise ValueError("Malformed local build identity")


def validate_source(value: dict, root: Path = ROOT) -> None:
    validate_build(value)
    if value["sourceCommit"] != git("rev-parse", "HEAD", root=root):
        raise ValueError("Build identity source commit differs from checkout")
    if value["sourceDateEpoch"] != int(git("show", "-s", "--format=%ct", value["sourceCommit"], root=root)):
        raise ValueError("Build identity source timestamp differs")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if (value["kind"] != "ci" or value["runId"] != os.environ.get("GITHUB_RUN_ID")
                or value["runAttempt"] > int(os.environ["GITHUB_RUN_ATTEMPT"])):
            raise ValueError("Build identity belongs to another pipeline run")


def source(path: str, root: Path) -> tuple[bytes, dict]:
    if Path(path).is_absolute() or "\\" in path or ":" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("Version source must be an owner-relative path")
    candidate = root / path
    if not candidate.resolve().is_relative_to(root.resolve()) or candidate.is_symlink():
        raise ValueError("Version source escapes owner")
    content = candidate.read_bytes().replace(b"\r\n", b"\n")
    return content, {"path": path, "sha256": hashlib.sha256(content).hexdigest()}


def axes(version: str, contract_text: str, root: Path = ROOT, catalog: dict | None = None) -> dict:
    if catalog is None:
        catalog = json.loads((root / "eng/version-sources.json").read_text(encoding="utf-8"))
    if set(catalog.get("axes", {})) != set(AXES) or catalog.get("owner") != "Mobile" or catalog.get("schemaVersion") != 1:
        raise ValueError("Version source catalog must define exactly nine axes")
    output = {}
    for name, kind in zip(AXES, KINDS, strict=True):
        spec = catalog["axes"][name]
        if spec.get("kind") != kind:
            raise ValueError(f"Wrong independent source kind for {name}")
        if kind == "release":
            # AppVersion is the allocated release name under the MAUI artifact id. No source file backs it, so no
            # synthetic source path is recorded (AND.40 PR B: the retired io.github applicationId leaves no trace).
            if set(spec) != {"kind", "allocation"} or spec["allocation"] != "release-name":
                raise ValueError("The release axis is the allocated release name, not a source file")
            if not re.fullmatch(r"[0-9]+(?:[.][0-9]+)*(?:[-+][A-Za-z0-9.-]+)?", version):
                raise ValueError("Malformed independent version")
            output[name] = {"status": "present", "values": [{
                "subject": MAUI_ARTIFACT, "version": version,
                "source": {"allocation": "release-name", "sha256": hashlib.sha256(version.encode()).hexdigest()}}]}
            continue
        if "absence" in spec:
            allowed = {"kind", "absence", "reason", "producer"}
            if set(spec) - allowed or spec["absence"] not in {"not-applicable", "not-produced"} or not spec.get("reason"):
                raise ValueError("Invalid absent axis")
            if spec["absence"] == "not-produced" and not spec.get("producer"):
                raise ValueError("Absent producer must identify its future owner")
            output[name] = {"status": spec["absence"], "reason": spec["reason"]}
            if "producer" in spec:
                output[name]["producer"] = spec["producer"]
            continue
        if set(spec) - {"kind", "sources"}:
            raise ValueError("Aliases and unknown version source properties are forbidden")
        if kind == "packages":
            raise ValueError("The package axis comes from the MAUI NuGet lock (maui_report), not from a source list")
        values = []
        for path in spec.get("sources", []):
            if kind == "contracts" and path == "packages/contracts/source.json":
                content = contract_text.encode()
                evidence = {"path": path, "sha256": hashlib.sha256(content).hexdigest()}
            else:
                content, evidence = source(path, root)
            if kind == "contracts":
                producer = json.loads(content)
                match = re.fullmatch(r"([a-zA-Z0-9_.]+)\.v([1-9][0-9]*)", producer.get("schema", ""))
                if (not match or producer.get("dirty") is not False
                        or not re.fullmatch(r"[0-9a-f]{40}", producer.get("commit", ""))
                        or not re.fullmatch(r"[0-9a-f]{64}", producer.get("descriptorSha256", ""))):
                    raise ValueError("Contract source requires published namespace and descriptor")
                values.append({"subject": match[1], "version": match[2], "source": evidence,
                               "descriptorSha256": producer["descriptorSha256"]})
            elif kind == "native-abi":
                major = re.search(rb"#define\s+ARC_ABI_MAJOR\s+(\d+)", content)
                minor = re.search(rb"#define\s+ARC_ABI_MINOR\s+(\d+)", content)
                if not major or not minor:
                    raise ValueError("Native ABI constants missing")
                values.append({"subject": path, "version": major[1].decode() + "." + minor[1].decode(), "source": evidence})
            else:
                declared = json.loads(content)
                entries = declared["migrations"][-1:] if kind == "migrations" else declared["versions"]
                values.extend({"subject": item["subject"], "version": item["version"], "source": evidence} for item in entries)
        if not values:
            raise ValueError(f"No implemented source for {name}")
        seen = set()
        for value in values:
            if (not isinstance(value["subject"], str) or not value["subject"] or value["subject"] in seen
                    or not isinstance(value["version"], str) or not re.fullmatch(r"[0-9]+(?:[.][0-9]+)*(?:[-+][A-Za-z0-9.-]+)?", value["version"])):
                raise ValueError("Duplicate subject or malformed independent version")
            seen.add(value["subject"])
        output[name] = {"status": "present", "values": sorted(values, key=lambda item: item["subject"])}
    return copy.deepcopy(output)


# AND.40 decision 14: the MAUI path. The identity is generated from the NuGet lock of the shipped
# net10.0-android closure, the pinned toolchain, the SDK that built the candidate and the source inputs.
MAUI_ARTIFACT = "com.arcforges.mobile"
MAUI_FRAMEWORK = "net10.0-android"
MAUI_LOCK_TARGET = "net10.0-android36.1"  # the NuGet lock keys the closure by the moniker with the platform version
MAUI_PROJECT = "src/ArcForges.Mobile/ArcForges.Mobile.csproj"
MAUI_LOCK = "src/ArcForges.Mobile/packages.lock.json"
MAUI_TOOLCHAIN = "eng/policy/dotnet-toolchain.json"
MAUI_WORKLOAD_ADMISSION = "eng/policy/workload-admission.json"
MAUI_SOURCE_INPUTS = ("global.json", "Directory.Build.props", "Directory.Packages.props", "NuGet.config",
                      MAUI_PROJECT, MAUI_LOCK, MAUI_TOOLCHAIN, MAUI_WORKLOAD_ADMISSION)
MAUI_OUTPUT = "build/generated/licence-assets/build-identity.json"
# The reviewed Contracts producer source (the ContractSet axis). Its bytes are the ones the retired Kotlin resource
# profile carried (AND.40 PR B); the pinned digest makes a change a reviewed code change.
CONTRACT_SOURCE = "eng/policy/contracts-source.json"
CONTRACT_SOURCE_SHA256 = "7536a3dc371d282d5ed7528f6217c69512b068a9fd2f5a196c665f4a66a2bbed"


def contract_source_text(root: Path = ROOT) -> str:
    content = (root / CONTRACT_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(content).hexdigest() != CONTRACT_SOURCE_SHA256:
        raise ValueError("The reviewed Contracts source text differs from its pinned digest")
    return content.decode("utf-8")


def lf_source(path: str, root: Path = ROOT) -> dict:
    """Evidence for one repository input, hashed over its LF-normalised bytes (the rule of `source`)."""
    content = (root / path).read_bytes().replace(b"\r\n", b"\n")
    return {"path": path, "sha256": hashlib.sha256(content).hexdigest()}


def maui_packages(root: Path = ROOT) -> list[dict]:
    """Every package of the net10.0-android closure in the NuGet lock, with its resolved version.

    Project references carry no resolved version and are skipped; the lock itself is bound by its digest.
    """
    evidence = lf_source(MAUI_LOCK, root)
    content = (root / MAUI_LOCK).read_bytes().replace(b"\r\n", b"\n")
    closure = json.loads(content)["dependencies"].get(MAUI_LOCK_TARGET)
    if not isinstance(closure, dict) or not closure:
        raise ValueError(f"{MAUI_LOCK} has no {MAUI_LOCK_TARGET} closure")
    values = []
    for name, entry in closure.items():
        if "resolved" not in entry:
            continue
        if not re.fullmatch(r"[0-9]+(?:[.][0-9]+)*(?:[-+][A-Za-z0-9.-]+)?", entry["resolved"]):
            raise ValueError(f"Malformed locked version for {name}")
        values.append({"subject": name, "version": entry["resolved"], "source": evidence})
    if not values:
        raise ValueError(f"{MAUI_LOCK} lists no resolved package for {MAUI_LOCK_TARGET}")
    return sorted(values, key=lambda item: item["subject"].lower())


def committed_source(path: str, root: Path = ROOT) -> dict:
    """Evidence for an input read from HEAD rather than the working tree.

    global.json is read from its committed bytes: a local MAUI build swaps in the uncommitted SDK adapter, and the
    identity must not depend on that swap. The repository gates still require the committed pin.
    """
    content = subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=root,
                                      env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")})
    content = content.replace(b"\r\n", b"\n")
    return {"path": path, "sha256": hashlib.sha256(content).hexdigest(), "source": "HEAD"}


def maui_toolchain(root: Path = ROOT, observed_sdk: str = "") -> dict:
    """The pinned SDK, workload, MAUI and Android values, with the SDK that built this candidate."""
    toolchain = json.loads((root / MAUI_TOOLCHAIN).read_bytes().replace(b"\r\n", b"\n"))
    workloads = {alias: {"id": item["id"], "manifestVersion": item["manifestVersion"], "packVersion": item["packVersion"]}
                 for alias, item in toolchain["workloads"].items()}
    return {
        "framework": MAUI_FRAMEWORK,
        "sdk": {"pinned": toolchain["dotnet"]["sdkVersion"], "rollForward": toolchain["dotnet"]["rollForward"],
                "observed": observed_sdk},
        "workloads": workloads,
        "maui": {"controlsVersion": toolchain["maui"]["controlsVersion"], "runtime": toolchain["maui"]["runtime"],
                 "useMonoRuntime": toolchain["maui"]["useMonoRuntime"], "linkTool": toolchain["maui"]["linkTool"],
                 "linkToolCondition": toolchain["maui"]["linkToolCondition"]},
        "android": {"applicationId": toolchain["android"]["applicationId"],
                    "minSdkVersion": toolchain["android"]["minSdkVersion"],
                    "targetPlatformVersion": toolchain["android"]["targetPlatformVersion"],
                    "buildToolsVersion": toolchain["android"]["buildToolsVersion"]},
        "sourceInputs": [committed_source(path, root) if path == "global.json" else lf_source(path, root)
                         for path in MAUI_SOURCE_INPUTS],
    }


def maui_report(version: str, code: int, root: Path = ROOT, environment: dict | None = None,
                identity: dict | None = None, observed_sdk: str = "") -> dict:
    """The build identity of the MAUI candidate. `identity` may be supplied by tests; a build reads it from git."""
    if type(code) is not int or not 1 <= code <= 2_100_000_000:
        raise ValueError("Invalid Android versionCode")
    build_identity = build(root, environment) if identity is None else identity
    validate_build(build_identity)
    env = os.environ if environment is None else environment
    if build_identity["kind"] == "ci":
        number, attempt = int(env["GITHUB_RUN_NUMBER"]), build_identity["runAttempt"]
        if not 1 <= number <= 20_999_999 or not 1 <= attempt <= 99 or code != number * 100 + attempt or version != f"0.1.0-ci.{number}.{attempt}":
            raise ValueError("App version differs from allocated CI version")
    toolchain = maui_toolchain(root, observed_sdk)
    if build_identity["kind"] == "ci" and observed_sdk != toolchain["sdk"]["pinned"]:
        raise ValueError("The CI build did not run the pinned SDK")
    catalog = json.loads((root / "eng/version-sources.json").read_text(encoding="utf-8"))
    # PackageVersion is not-applicable in the catalog (the NuGet lock is its source, read below).
    axes_output = axes(version, contract_source_text(root), root, catalog)
    axes_output["PackageVersion"] = {"status": "present", "values": maui_packages(root)}
    return {"schema": "arcforges.build-identity.v1", "owner": "Mobile",
            "artifact": {"id": MAUI_ARTIFACT, "version": version}, "build": build_identity,
            "axes": dict(sorted(axes_output.items())), "packaging": {"androidVersionCode": code},
            "toolchain": toolchain}


def verify_maui_report(data: bytes, info: dict, root: Path = ROOT, observed_sdk: str = "") -> None:
    """Refuse an embedded or packaged MAUI identity that differs from the one this checkout derives."""
    from check_provenance import document
    expected = maui_report(info["version_name"], info["version_code"], root, observed_sdk=observed_sdk)
    if document(data) != expected or expected["build"]["sourceCommit"] != info["commit"]:
        raise ValueError("Packaged MAUI build identity differs from the checkout")


def generate_maui(version: str, code: int, observed_sdk: str, root: Path = ROOT) -> dict:
    """Write build/generated/licence-assets/build-identity.json, which the csproj embeds in every build that has it."""
    from resources import save
    report_value = maui_report(version, code, root, observed_sdk=observed_sdk)
    save(root / MAUI_OUTPUT, report_value)
    return report_value


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maui", action="store_true", required=True,
                        help="the MAUI identity: derived from the NuGet lock of the shipped closure")
    parser.add_argument("--observed-sdk", default="", help="the output of `dotnet --version` for this build")
    parser.add_argument("--version", required=True)
    parser.add_argument("--code", type=int, required=True)
    args = parser.parse_args()
    generate_maui(args.version, args.code, args.observed_sdk)
