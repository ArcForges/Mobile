# SPDX-License-Identifier: Apache-2.0
"""AND.40 unit 4: the resolved MAUI NuGet closure listing, the F-023-class re-proof and the MAUI notice gate (offline).

closure   writes artifacts/evidence/maui-closure.json: every locked package with licence, source, distribution class and notices.
reproof   proves the shipped closure holds no build-only, test-only, AGPL or DesktopPlatform package, and prints the result.
check     validates the notice data against the retained texts, the lock, the admission records and the AND.40 deferrals.
render    writes the MAUI section of THIRD_PARTY_NOTICES.md from the notice data (check fails when it is stale).
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCK = "src/ArcForges.Mobile/packages.lock.json"
ADMISSION = "eng/policy/nuget-admission.json"
TEST_ADMISSION = "eng/policy/nuget-test-admission.json"
DISTRIBUTION = "eng/policy/maui-distribution.json"
NOTICE_DATA = "eng/policy/maui-notices.json"
TOOLCHAIN = "eng/policy/dotnet-toolchain.json"
WORKLOADS = "eng/policy/workload-admission.json"
MARKDOWN = "THIRD_PARTY_NOTICES.md"
EVIDENCE = "artifacts/evidence/maui-closure.json"
TARGET = "net10.0-android36.1"
NUGET_SOURCE = "https://api.nuget.org/v3/index.json"
REVIEWER = "w-deku-20261008-rev-and-40"
ADMITTED = {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MIT", "Zlib", "Unicode-3.0"}
# AND.40 unit 5b: the workload bundles of the APK (Mono runtime, AOT Cross) and the SDK bundle (build tooling).
WORKLOAD_ADMITTED = ADMITTED | {"CC0-1.0", "LLVM-exception", "NCSA", "W3C-20150513",
                               "LicenseRef-IETF-RFC-Notice", "LicenseRef-ISO-8879-Notice", "LicenseRef-OSF-UUID-Notice",
                               "LicenseRef-Practice-of-Programming-Notice", "LicenseRef-Public-Domain-Dedication",
                               "LicenseRef-Slicing-by-8-BSD-Notice"}
FORBIDDEN = re.compile(r"AGPL|GPL|SSPL|BUSL|Proprietary|UNLICENSED", re.IGNORECASE)
BUILD_ONLY = ["Microsoft.Maui.Controls.Build.Tasks", "Microsoft.Maui.Resizetizer", "Microsoft.NET.ILLink.Tasks"]
BEGIN = "<!-- maui-notices:begin -->"
END = "<!-- maui-notices:end -->"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(root: Path, relative: str):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON key in {relative}: {key}")
            result[key] = value
        return result
    return json.loads((root / relative).read_text(encoding="utf-8"), object_pairs_hook=unique)


def licence_tokens(expression: str):
    return [token for token in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", expression) if token.strip()]


def closure(root: Path = ROOT) -> dict:
    lock_bytes = (root / LOCK).read_bytes()
    lock = json.loads(lock_bytes.decode("utf-8"))
    locked = lock["dependencies"][TARGET]
    admission = read_json(root, ADMISSION)
    packages = {item["id"]: item for item in admission["packages"]}
    distribution = {item["id"]: item["class"] for item in read_json(root, DISTRIBUTION)["packages"]}
    notices = read_json(root, NOTICE_DATA)["packages"]
    rows = []
    for name in sorted(locked, key=str.lower):
        info = locked[name]
        if info["type"] == "Project":
            rows.append({"id": name, "kind": "project", "distribution": "shipped", "licence": "Apache-2.0",
                         "source": "repository: src/core/ArcForges.Mobile.Network", "notices": []})
            continue
        item = packages[name]
        rows.append({"id": name, "version": item["version"], "kind": item["kind"], "licence": item["licence"],
                     "source": NUGET_SOURCE, "nupkgSha512": item["nupkgSha512"], "contentHash": item["contentHash"],
                     "distribution": distribution[name], "notices": sorted(notices.get(name, [])),
                     "noticeDisposition": item["noticeDisposition"]})
    locked_names = {row["id"] for row in rows if row["kind"] != "project"}
    require(set(distribution) == locked_names,
            "The distribution record must classify exactly the locked packages: classified only "
            + str(sorted(set(distribution) - locked_names)) + "; unclassified " + str(sorted(locked_names - set(distribution))))
    test_classes = {item["id"]: item["class"] for item in read_json(root, DISTRIBUTION).get("testOnly", [])}
    test_rows = [{"id": item["id"], "version": item["version"], "kind": item["kind"], "licence": item.get("licence"),
                  "source": NUGET_SOURCE, "nupkgSha512": item.get("nupkgSha512"), "contentHash": item.get("contentHash"),
                  "distribution": test_classes.get(item["id"], "unclassified")}
                 for item in sorted(read_json(root, TEST_ADMISSION)["packages"], key=lambda entry: entry["id"].lower())]
    return {
        "schemaVersion": 1,
        "target": TARGET,
        "lockSha256": digest(lock_bytes),
        "admissionSha256": digest((root / ADMISSION).read_bytes()),
        "distributionSha256": digest((root / DISTRIBUTION).read_bytes()),
        "lockedPackages": sum(1 for row in rows if row["kind"] != "project"),
        "shipped": sum(1 for row in rows if row["kind"] != "project" and row.get("distribution") == "shipped"),
        "buildOnly": sorted(row["id"] for row in rows if row.get("distribution") == "build-only"),
        "rows": rows,
        "testOnly": test_rows,
    }


def reproof(root: Path = ROOT) -> dict:
    report = closure(root)
    test_admission = {item["id"]: item for item in read_json(root, TEST_ADMISSION)["packages"]}
    test_scope = set(test_admission)
    test_classes = {item["id"]: item for item in read_json(root, DISTRIBUTION).get("testOnly", [])}
    rows = [row for row in report["rows"] if row["kind"] != "project"]
    shipped = [row for row in rows if row["distribution"] == "shipped"]
    shipped_ids = {row["id"] for row in shipped}
    findings = []
    for row in shipped:
        if row["id"] in BUILD_ONLY:
            findings.append("build-only package in the shipped closure: " + row["id"])
        if row["id"] in test_scope:
            findings.append("test-only package in the shipped closure: " + row["id"])
        if "DesktopPlatform" in row["id"] or "Build.Policy" in row["id"]:
            findings.append("forbidden first-party package in the shipped closure: " + row["id"])
        if FORBIDDEN.search(row["licence"]):
            findings.append("shipped package with a forbidden licence: " + row["id"] + " " + row["licence"])
    require(sorted(row["id"] for row in rows if row["distribution"] == "build-only") == sorted(BUILD_ONLY),
            "The build-only class is not exactly the reviewed build tasks")
    for identifier in sorted(test_scope - set(test_classes)):
        findings.append("unclassified test-only package: " + identifier)
    for identifier in sorted(set(test_classes) - test_scope):
        findings.append("test-only classification without a test-scope admission: " + identifier)
    for identifier in sorted(test_scope & set(test_classes)):
        entry = test_classes[identifier]
        if entry.get("class") != "test-only" or entry.get("version") != test_admission[identifier]["version"]:
            findings.append("test-only classification differs from its admission: " + identifier)
    require(not findings, "; ".join(findings))
    return {"result": "passed", "target": TARGET, "lockSha256": report["lockSha256"], "lockedPackages": len(rows),
            "shipped": len(shipped), "buildOnlyExcluded": report["buildOnly"],
            "testOnlyInShipped": sorted(test_scope & shipped_ids), "testOnlyClassified": len(test_classes),
            "desktopPlatformInShipped": [], "agplInShipped": []}


def check(root: Path = ROOT) -> dict:
    data = read_json(root, NOTICE_DATA)
    require(data.get("schemaVersion") == 1 and data.get("owner") == "Mobile" and data.get("licenceBoundary") == "Apache",
            "Invalid MAUI notice data owner")
    require(data.get("reviewer") == REVIEWER and "PENDING" not in (root / NOTICE_DATA).read_text(encoding="utf-8"),
            "The MAUI notice data must name the AND.40 reviewer and must not say PENDING")
    require(data["lockSha256"] == digest((root / LOCK).read_bytes()), "The MAUI notice data is bound to another lock")
    notice_shas = set()
    for row in data["notices"]:
        path = root / row["path"]
        require(row["path"] == "third-party/notices/" + row["sha256"] + ".txt", f"Notice path does not match its digest: {row['path']}")
        require(path.is_file(), f"Missing retained notice: {row['path']}")
        content = path.read_bytes()
        require(b"\r" not in content, f"Retained notice is not LF-normalized: {row['path']}")
        require(digest(content) == row["sha256"], f"Retained notice changed: {row['path']}")
        require(licence_tokens(row["licence"]) and set(licence_tokens(row["licence"])) <= ADMITTED,
                f"Notice licence outside the admitted set: {row['licence']}")
        notice_shas.add(row["sha256"])
    existing = {path.stem for path in (root / "third-party/notices").glob("*.txt")}
    for name, shas in data["packages"].items():
        require(shas, f"Package without a notice: {name}")
        for sha in shas:
            require(sha in notice_shas or sha in existing, f"Notice for {name} is not retained: {sha}")
    admission = read_json(root, ADMISSION)
    unnoticed = {item["id"] for item in admission["packages"] if not item["licenceFiles"]}
    require(unnoticed <= set(data["packages"]), "A package without licence files has no retained notice: " +
            ", ".join(sorted(unnoticed - set(data["packages"]))))
    for pack in data["workloadPacks"]:
        require(pack.get("contributes") in {"apk", "build-tooling"}, f"Workload pack without a contribution class: {pack['pack']}")
        if pack["contributes"] == "apk":
            require(pack.get("licence") and set(licence_tokens(pack["licence"])) <= WORKLOAD_ADMITTED,
                    f"APK workload pack licence outside the admitted set: {pack['pack']}")
        for sha in pack["notices"]:
            retained = root / "third-party/notices" / (sha + ".txt")
            require(retained.is_file() and digest(retained.read_bytes()) == sha, f"Workload pack notice is not retained: {sha}")
    for item in data.get("admissions", []):
        require(item.get("reviewer") == REVIEWER and item.get("decision") == "admitted"
                and set(licence_tokens(item["licence"])) <= WORKLOAD_ADMITTED,
                f"Admission is not reviewed or names an unadmitted licence: {item.get('licence')}")
    host = data.get("hostOnly", [])
    require(len(host) == 1 and host[0].get("component") == "gnu/binutils" and host[0].get("classification") == "host-only"
            and host[0].get("distributionNoticeSet") == "excluded" and host[0].get("binutilsMemberCount") == 0,
            "The gnu/binutils host-only evidence is missing or does not exclude the component")
    toolchain = read_json(root, TOOLCHAIN)
    for item in toolchain["deferrals"]:
        if "package" in item:
            require(item["package"] in data["packages"], f"Notice deferral {item['id']} is not carried by the notice data")
    pending = {item["id"]: item for item in data.get("pending", [])}
    require("linux-licence-evidence" in pending and pending["linux-licence-evidence"]["owner"] == "AND.40 unit 5"
            and pending["linux-licence-evidence"]["status"] == "pending",
            "The Linux licence evidence must stay pending, owned by AND.40 unit 5")
    text = (root / MARKDOWN).read_text(encoding="utf-8")
    require(text.count(BEGIN) == 1 and text.count(END) == 1, "THIRD_PARTY_NOTICES.md lacks the MAUI notice block")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    require(block == "\n" + render(root) + "\n", "THIRD_PARTY_NOTICES.md MAUI block is stale; run eng/maui_notices.py render")
    return {"result": "passed", "notices": len(data["notices"]), "packages": len(data["packages"]),
            "pending": sorted(pending), "escalated": [item["id"] for item in data.get("escalated", [])]}


def render(root: Path = ROOT) -> str:
    data = read_json(root, NOTICE_DATA)
    lines = [
        "The MAUI Android app (AND.40) is redistributed under the NuGet closure in",
        "[eng/policy/nuget-admission.json](eng/policy/nuget-admission.json). Its licence texts are retained in",
        "[third-party/notices](third-party/notices) and listed here by digest. The machine-checked data is",
        "[eng/policy/maui-notices.json](eng/policy/maui-notices.json). The resolved closure with sources is in",
        "`artifacts/evidence/maui-closure.json`, written by `python -I eng/maui_notices.py closure`.",
        "",
        "### Packages whose nupkg carries no licence file",
        "",
        "| Package | Licence | Retained notice (SHA-256) |",
        "| --- | --- | --- |",
    ]
    admission = {item["id"]: item for item in read_json(root, ADMISSION)["packages"]}
    for name in sorted(data["packages"], key=str.lower):
        item = admission[name]
        shas = ", ".join("`" + sha[:16] + "`" for sha in data["packages"][name])
        lines.append(f"| {name} {item['version']} | {item['licence']} | {shas} |")
    lines += ["", "### Workload packs admitted for the Android build", "", "| Pack | Version | Retained notices |", "| --- | --- | --- |"]
    for pack in data["workloadPacks"]:
        shas = ", ".join("`" + sha[:16] + "`" for sha in pack["notices"])
        lines.append(f"| {pack['pack']} | {pack['version']} | {shas} |")
    lines += ["", "### Open notice obligations", ""]
    for item in data.get("escalated", []):
        if item.get("status") != "resolved":
            lines.append(f"- {item['item']}")
    for item in data.get("pending", []):
        lines.append(f"- Pending ({item['owner']}): " + " ".join(item["items"]))
    return "\n".join(lines)


def write_markdown(root: Path = ROOT) -> None:
    path = root / MARKDOWN
    text = path.read_text(encoding="utf-8")
    block = BEGIN + "\n" + render(root) + "\n" + END
    if BEGIN in text:
        head, rest = text.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        text = head + block + tail
    else:
        text = text.rstrip("\n") + "\n\n## MAUI Android app (AND.40)\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


# AND.40 unit 5: the release notice set. Every shipped package contributes the licence files its restored nupkg
# carries (from the NuGet global packages folder, verified against the admitted nupkg SHA-512) and the retained
# texts recorded for it. Build-only and test-only packages never contribute.
DISTRIBUTION_OUTPUT = "build/generated/maui-licence-assets/THIRD_PARTY_NOTICES.txt"
DISTRIBUTION_EVIDENCE = "artifacts/evidence/maui-notices-distribution.json"
LINUX_EVIDENCE = "artifacts/evidence/linux-licence-evidence.json"
LICENCE_MEMBER = re.compile(r"^(LICEN[CS]E|NOTICE|THIRD[-_ ]PARTY)", re.IGNORECASE)
LINUX_PACKS = {
    "Microsoft.Android.Sdk.Linux": ("LICENSE.TXT", "THIRD-PARTY-NOTICES.TXT"),
    "Microsoft.NET.Runtime.MonoAOTCompiler.Task": ("THIRD-PARTY-NOTICES.TXT",),
    "Microsoft.NET.Runtime.MonoTargets.Sdk": ("THIRD-PARTY-NOTICES.TXT",),
}


def distribution(root: Path = ROOT, nuget_root: Path | None = None) -> dict:
    import base64
    import os
    import zipfile
    nuget_root = Path(nuget_root or os.environ.get("NUGET_PACKAGES", "")).resolve()
    require(nuget_root.is_dir(), "A restored NuGet packages folder is required (NUGET_PACKAGES)")
    data = read_json(root, NOTICE_DATA)
    report = closure(root)
    entries = {}
    for row in report["rows"]:
        if row["kind"] == "project" or row.get("distribution") != "shipped":
            continue
        identifier = row["id"].lower()
        nupkg = nuget_root / identifier / row["version"] / f"{identifier}.{row['version']}.nupkg"
        require(nupkg.is_file(), f"Restored nupkg missing for shipped package {row['id']} {row['version']}")
        payload = nupkg.read_bytes()
        require(base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii") == row["nupkgSha512"],
                f"Restored nupkg differs from the admitted SHA-512: {row['id']}")
        with zipfile.ZipFile(nupkg) as archive:
            for member in sorted(archive.namelist()):
                if member.endswith("/") or not LICENCE_MEMBER.match(member.rsplit("/", 1)[-1]):
                    continue
                text = archive.read(member).replace(b"\r\n", b"\n")
                entries[(row["id"], row["version"], member, digest(text))] = text
        for shadow in sorted(data["packages"].get(row["id"], [])):
            text = (root / "third-party/notices" / (shadow + ".txt")).read_bytes()
            require(digest(text) == shadow, f"Retained notice changed: {shadow}")
            entries[(row["id"], row["version"], "retained", shadow)] = text
    apk_notices = {}
    for pack in data["workloadPacks"]:
        if pack.get("contributes") == "apk":
            for sha in pack["notices"]:
                apk_notices.setdefault(sha, []).append(pack["pack"] + " " + pack["version"])
    for sha in sorted(apk_notices):
        text = (root / "third-party/notices" / (sha + ".txt")).read_bytes()
        require(digest(text) == sha, f"Retained notice changed: {sha}")
        entries[("APK workload packs: " + "; ".join(sorted(apk_notices[sha])), "workload", "retained", sha)] = text
    require(entries, "No shipped package carries licence text")
    lines = []
    for key in sorted(entries):
        identifier, version_value, member, checksum = key
        text = entries[key].decode("utf-8")
        lines.append(f"==== {identifier} {version_value} :: {member} (sha256 {checksum}) ====\n{text.rstrip(chr(10))}\n")
    output = root / DISTRIBUTION_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(lines).encode("utf-8")
    output.write_bytes(body)
    summary = {"schemaVersion": 1, "result": "written", "file": DISTRIBUTION_OUTPUT,
               "sha256": hashlib.sha256(body).hexdigest(), "texts": len(entries),
               "packages": sorted({key[0] for key in entries}), "lockSha256": report["lockSha256"]}
    evidence = root / DISTRIBUTION_EVIDENCE
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary


# AND.40 hosted run 37928097917: the android workload on a hosted runner installs only the Cross pack of the HOST
# architecture. ArcForges builds Android only on hosted x64 runners, so the other alias is not applicable there.
LINUX_HOST_ALIASES = {"x86_64": "linux-x64", "amd64": "linux-x64", "aarch64": "linux-arm64", "arm64": "linux-arm64"}
LINUX_CROSS_ALIASES = ("linux-x64", "linux-arm64")


def linux_host_alias(machine: str) -> str:
    alias = LINUX_HOST_ALIASES.get(str(machine).lower())
    require(alias, f"Linux licence evidence: unknown host architecture {machine!r}; no Cross alias is defined for it")
    return alias


def linux_evidence(dotnet_root: Path, root: Path = ROOT, machine: str | None = None) -> dict:
    """Licence files of the Linux host packs the Android build needs (run on the hosted Linux runner).

    The Cross alias of the current host architecture is required and fails closed when absent. The other alias is
    recorded as not applicable, because it is not a build host and its Cross pack exists only on its own architecture.
    """
    host_architecture = machine or platform.machine()
    host_alias = linux_host_alias(host_architecture)
    packs = Path(dotnet_root) / "packs"
    require(packs.is_dir(), f"No packs folder under {dotnet_root}")
    found = {}
    for name, files in LINUX_PACKS.items():
        versions = sorted(p for p in (packs / name).glob("*") if p.is_dir()) if (packs / name).is_dir() else []
        require(versions, f"Linux licence evidence: pack {name} is not installed")
        folder = versions[-1]
        present = {}
        for file in files:
            path = folder / file
            require(path.is_file(), f"Linux licence evidence: {name} {folder.name} lacks {file}")
            present[file] = digest(path.read_bytes().replace(b"\r\n", b"\n"))
        found[name] = {"version": folder.name, "files": present}
    crosses = {}
    for host in LINUX_CROSS_ALIASES:
        if host != host_alias:
            crosses[host] = {"status": "not-applicable",
                             "reason": f"not the build host architecture ({host_architecture} builds use {host_alias}); "
                                       f"the {host} Cross pack exists only on {host} build hosts"}
            continue
        matches = sorted(p for p in packs.glob(f"Microsoft.NETCore.App.Runtime.AOT.{host}.Cross.android-arm64") if p.is_dir())
        require(matches, f"Linux licence evidence: no Cross alias for {host} (host architecture {host_architecture})")
        versions = sorted(p for p in matches[-1].glob("*") if p.is_dir())
        require(versions, f"Linux licence evidence: Cross alias {host} has no installed version")
        folder = versions[-1]
        path = folder / "THIRD-PARTY-NOTICES.TXT"
        require(path.is_file(), f"Linux licence evidence: Cross alias {host} lacks THIRD-PARTY-NOTICES.TXT")
        crosses[host] = {"status": "required", "pack": matches[-1].name, "version": folder.name,
                         "thirdPartyNotices": digest(path.read_bytes().replace(b"\r\n", b"\n"))}
    report = {"schemaVersion": 1, "result": "produced", "host": "linux", "hostArchitecture": host_architecture,
              "hostAlias": host_alias, "packs": found, "crossAliases": crosses}
    output = root / LINUX_EVIDENCE
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def release_ready(root: Path = ROOT) -> dict:
    """A MAUI release is published only when no notice escalation is open (fail closed)."""
    data = read_json(root, NOTICE_DATA)
    open_items = [item["id"] for item in data.get("escalated", []) if item.get("status") != "resolved"]
    require(not open_items, "Open notice escalations block the MAUI release: " + ", ".join(sorted(open_items)))
    return {"result": "ready", "openEscalations": 0}


HOST_ONLY_APKS = (
    "src/ArcForges.Mobile/bin/Debug/net10.0-android/com.arcforges.mobile-Signed.apk",
    "src/ArcForges.Mobile/bin/Release/net10.0-android/com.arcforges.mobile-Signed.apk",
)
BINUTILS_MEMBER = re.compile(r"(^|/)(as|ld|ld\.bfd|ld\.gold|gold|objcopy|objdump|ar|nm|ranlib|strip|readelf|addr2line|size|strings|gprof|c\+\+filt|elfedit)(\.exe)?$|libbfd|libopcodes|libctf|libiberty|binutils", re.IGNORECASE)
BINUTILS_CONTENT = (b"GNU ld", b"GNU assembler", b"GNU objcopy", b"GNU Binutils", b"binutils-gdb", b"libbfd", b"GNU gold")


def apk_host_only(apk: Path) -> dict:
    """AND.40 decision 20: refuse an APK that carries a gnu/binutils member or its content signature.

    The MAUI candidate stage, the signing job, the published-prerelease verification and the local gate call this on
    the APK they handle, so a binutils copy cannot reach a sealed candidate or a public release unnoticed.
    """
    import zipfile
    require(apk.is_file(), f"APK missing for the host-only proof: {apk.name}")
    with zipfile.ZipFile(apk) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        findings = [name for name in names if BINUTILS_MEMBER.search(name)]
        for name in names:
            data = archive.read(name)
            findings.extend(f"{name} contains {pattern.decode()}" for pattern in BINUTILS_CONTENT if pattern in data)
    require(not findings, "binutils is inside the APK (stop): " + "; ".join(findings[:10]))
    return {"entries": len(names), "binutilsMembers": 0}


def host_only(root: Path = ROOT, relatives: tuple[str, ...] = HOST_ONLY_APKS) -> dict:
    """AND.40 unit 5b: prove from the APK contents that the GPL-3.0 gnu/binutils tools are host-only."""
    builds = [{"apk": relative, **apk_host_only(root / relative)} for relative in relatives]
    return {"result": "absent", "component": "gnu/binutils", "builds": builds}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["closure", "reproof", "check", "render", "distribution",
                                            "linux-evidence", "release-ready", "host-only"])
    parser.add_argument("--nuget-root", type=Path, default=None, help="distribution: the restored NuGet packages folder")
    parser.add_argument("--dotnet-root", type=Path, default=None, help="linux-evidence: the dotnet root holding packs")
    args = parser.parse_args()
    try:
        if args.command == "closure":
            report = closure(ROOT)
            (ROOT / EVIDENCE).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / EVIDENCE).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
            print(json.dumps({"result": "written", "file": EVIDENCE, "lockedPackages": report["lockedPackages"],
                              "shipped": report["shipped"], "buildOnly": report["buildOnly"]}))
        elif args.command == "reproof":
            print(json.dumps(reproof(ROOT), indent=2))
        elif args.command == "check":
            print(json.dumps(check(ROOT), indent=2))
        elif args.command == "distribution":
            print(json.dumps(distribution(ROOT, args.nuget_root), indent=2))
        elif args.command == "linux-evidence":
            if args.dotnet_root is None:
                raise ValueError("linux-evidence requires --dotnet-root")
            print(json.dumps(linux_evidence(args.dotnet_root, ROOT), indent=2))
        elif args.command == "host-only":
            print(json.dumps(host_only(ROOT), indent=2))
        elif args.command == "release-ready":
            print(json.dumps(release_ready(ROOT), indent=2))
        else:
            write_markdown(ROOT)
            print(json.dumps({"result": "rendered", "file": MARKDOWN}))
    except (ValueError, OSError, KeyError) as error:
        print(f"MAUI notice gate failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
