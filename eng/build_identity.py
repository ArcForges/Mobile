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
        values = []
        if kind == "packages":
            for path in spec.get("sources", []):
                content, evidence = source(path, root)
                for line in content.decode().splitlines():
                    if not line or line.startswith("#") or line.startswith("empty="):
                        continue
                    coordinate, configurations = line.split("=", 1)
                    if "releaseRuntimeClasspath" not in configurations.split(","):
                        continue
                    group, artifact, version_value = coordinate.split(":")
                    values.append({"subject": group + ":" + artifact, "version": version_value, "source": evidence})
        else:
            for path in spec.get("sources", []):
                if kind == "release" and path == "release/app.json":
                    content = json.dumps({"versions": [{"subject": "io.github.arcforges.mobile", "version": version}]}, sort_keys=True).encode()
                    evidence = {"path": path, "sha256": hashlib.sha256(content).hexdigest()}
                elif kind == "contracts" and path == "packages/contracts/source.json":
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


def report(version: str, code: int, root: Path = ROOT, environment: dict | None = None) -> dict:
    from resources import profile
    if type(code) is not int or not 1 <= code <= 2_100_000_000:
        raise ValueError("Invalid Android versionCode")
    identity = build(root, environment)
    if identity["kind"] == "ci":
        env = os.environ if environment is None else environment
        number, attempt = int(env["GITHUB_RUN_NUMBER"]), identity["runAttempt"]
        if not 1 <= number <= 20_999_999 or not 1 <= attempt <= 99 or code != number * 100 + attempt or version != f"0.1.0-ci.{number}.{attempt}":
            raise ValueError("App version differs from allocated CI version")
    contract_text = profile(root)[2]["contractSourceText"]
    return {"schema": "arcforges.build-identity.v1", "owner": "Mobile",
            "artifact": {"id": "io.github.arcforges.mobile", "version": version},
            "build": identity, "axes": axes(version, contract_text, root),
            "packaging": {"androidVersionCode": code}}


def verify_report(data: bytes, info: dict, root: Path = ROOT) -> None:
    expected = report(info["version_name"], info["version_code"], root)
    # Strict JSON parsing rejects duplicates as well as missing/aliased axes.
    from check_provenance import document
    if document(data) != expected or expected["build"]["sourceCommit"] != info["commit"]:
        raise ValueError("Packaged build identity or independent version axes differ")


def generate(resolved: Path, version: str, code: int) -> None:
    import zipfile
    from resources import profile, sha, save
    approved = profile()[2]
    expected = approved["contractSourceText"].encode()
    observed = set()
    for configuration in json.loads(resolved.read_text(encoding="utf-8")):
        for artifact in configuration["artifacts"]:
            if artifact["id"].startswith("io.github.arcforges:contracts-proto:"):
                path = Path(artifact["file"])
                key = artifact["id"] + "/" + path.name
                if sha(path.read_bytes()) != approved["inputs"][key]["sha256"]:
                    raise ValueError("Changed resolved Contracts producer")
                with zipfile.ZipFile(path) as archive:
                    actual = archive.read("source.json").replace(b"\r\n", b"\n")
                if actual != expected:
                    raise ValueError("Resolved Contracts schema receipt differs from reviewed source")
                observed.add(artifact["id"])
    if len(observed) != 1:
        raise ValueError("Missing or ambiguous resolved Contracts producer")
    save(ROOT / "build/generated/licence-assets/build-identity.json", report(version, code))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--code", type=int, required=True)
    args = parser.parse_args()
    generate(args.resolved, args.version, args.code)
