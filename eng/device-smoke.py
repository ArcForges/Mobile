#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install an APK and verify the rendered Hello World screen on an explicit Android device."""

import argparse
import os
from pathlib import Path
import subprocess
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
    command("shell", "am", "start", "-W", "-n", f"{args.package}/io.github.arcforges.mobile.MainActivity")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        command("shell", "uiautomator", "dump", "/sdcard/arcforges-window.xml")
        window = command("shell", "cat", "/sdcard/arcforges-window.xml")
        root = ET.fromstring(window)
        if any(node.get("text") == "Hello, World!" for node in root.iter("node")):
            (args.output / "window.xml").write_bytes(window)
            (args.output / "hello-world.png").write_bytes(command("exec-out", "screencap", "-p"))
            print(f"Installed and rendered Hello World on {args.serial}: {args.package}")
            return
        time.sleep(1)
    raise SystemExit("The release APK did not render Hello, World! within 60 seconds.")


if __name__ == "__main__":
    main()
