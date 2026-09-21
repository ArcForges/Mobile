#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install the minified APK and require one real, user-triggered Cloud greeting."""

import argparse
import hashlib
import os
import json
from pathlib import Path
import subprocess
import re
import time
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--package", default="io.github.arcforges.mobile")
    parser.add_argument("--output", type=Path, default=Path("artifacts/device"))
    args = parser.parse_args()
    sdk = Path(os.environ.get("ANDROID_HOME") or os.environ["ANDROID_SDK_ROOT"])
    adb = sdk / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")

    def command(*parts):
        return subprocess.run([str(adb), "-s", args.serial, *map(str, parts)], check=True, capture_output=True, timeout=90).stdout

    args.output.mkdir(parents=True, exist_ok=True)
    command("install", "-r", args.apk.resolve())
    command("shell", "am", "force-stop", args.package)
    command("shell", "am", "start", "-W", "-f", "0x10008000", "-n", f"{args.package}/io.github.arcforges.mobile.MainActivity")

    def window():
        command("shell", "uiautomator", "dump", "/sdcard/arcforges-window.xml")
        data = command("shell", "cat", "/sdcard/arcforges-window.xml")
        (args.output / "window.xml").write_bytes(data)
        return ET.fromstring(data)

    def tap(root, label):
        button = next(node for node in root.iter("node") if node.get("text", "").casefold() == label.casefold())
        bounds = list(map(int, re.findall(r"\d+", button.get("bounds", ""))))
        if len(bounds) != 4 or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise ValueError("Diagnostic action has no usable device bounds: " + label)
        command("shell", "input", "tap", (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        root = window()
        texts = {node.get("text") for node in root.iter("node")}
        if "Ready to connect." in texts and "Cloud Hello Â· arcforges.com" in texts:
            candidate = Path(__file__).resolve().parents[1] / "artifacts/candidate/build-identity.json"
            raw = candidate.read_bytes()
            expected = json.loads(raw)
            tap(root, "Build information")
            diagnostic = window()
            content = "\n".join(node.get("text", "") for node in diagnostic.iter("node"))
            required = [expected["artifact"]["version"], expected["build"]["sourceCommit"],
                        expected["build"]["buildId"], str(expected["build"]["sourceDateEpoch"]),
                        hashlib.sha256(raw).hexdigest(), *expected["axes"]]
            if any(value not in content for value in required):
                raise ValueError("Installed APK build information differs from the verified candidate")
            (args.output / "build-identity-window.xml").write_bytes(ET.tostring(diagnostic))
            (args.output / "build-information.png").write_bytes(command("exec-out", "screencap", "-p"))
            (args.output / "runtime-build-identity.json").write_text(json.dumps({
                "evidenceClass": "installed-apk-native-diagnostic-view", "serial": args.serial,
                "reportSha256": hashlib.sha256(raw).hexdigest(), "identity": expected,
                "readBeforeCloudRequest": True,
            }, indent=2) + "\n", encoding="utf-8")
            tap(diagnostic, "Close")
            root = window()
            button = next(node for node in root.iter("node") if node.get("text") == "Say hello")
            bounds = list(map(int, re.findall(r"\d+", button.get("bounds", ""))))
            if len(bounds) != 4:
                raise ValueError("Hello button has no usable device bounds.")
            command("shell", "input", "tap", (bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)
            break
        time.sleep(1)
    else:
        raise SystemExit("The release APK did not present the Cloud action within 60 seconds.")

    # No automatic tap/RPC retry: a stale local greeting cannot satisfy this gate.
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            root = window()
            texts = {node.get("text", "") for node in root.iter("node")}
            if "Hello, World!" in texts:
                (args.output / "release-cloud.json").write_text(json.dumps({
                    "package": args.package, "serial": args.serial,
                    "endpoint": "https://arcforges.com/api", "button_presses": 1,
                    "response": "Hello, World!", "minified_apk": args.apk.name,
                }, indent=2) + "\n", encoding="utf-8")
                print(f"Minified APK called Cloud and rendered Hello, World! on {args.serial}: {args.package}")
                return
            failures = [text for text in texts if text.startswith((
                "Could not ", "Cloud did not ", "Cloud rejected ", "Cloud's request ", "The request was canceled",
            ))]
            if failures:
                raise SystemExit("Release Cloud call failed: " + "; ".join(failures))
            time.sleep(1)
        raise SystemExit("The release APK did not render the Cloud response within 20 seconds.")
    finally:
        (args.output / "hello-world.png").write_bytes(command("exec-out", "screencap", "-p"))


if __name__ == "__main__":
    main()
