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
ADMITTED = {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MIT"}
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["closure", "reproof", "check", "render"])
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
        else:
            write_markdown(ROOT)
            print(json.dumps({"result": "rendered", "file": MARKDOWN}))
    except (ValueError, OSError, KeyError) as error:
        print(f"MAUI notice gate failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
