# SPDX-License-Identifier: Apache-2.0
"""Release guards: version ordering and rejecting changed or unrelated candidates."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location("mobile", Path(__file__).resolve().parents[1] / "mobile.py")
mobile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile)


class ReleaseGuardsTest(unittest.TestCase):
    def test_certificate_guard_accepts_current_tool_labels_and_rejects_other_signers(self):
        fingerprint = "a" * 64
        for label in ["V3.0 Signer:", "Signer #1"]:
            output = f"Number of signers: 1\n{label} certificate SHA-256 digest: {fingerprint}"
            self.assertEqual(fingerprint, mobile.verify_certificate(output, fingerprint))
            with self.assertRaises(ValueError):
                mobile.verify_certificate(output, "b" * 64)
            with self.assertRaises(ValueError):
                mobile.verify_certificate(output.replace("signers: 1", "signers: 2"), fingerprint)

    def test_attempt_does_not_overlap_next_run(self):
        with patch.dict(os.environ, {"GITHUB_RUN_NUMBER": "42", "GITHUB_RUN_ATTEMPT": "99"}):
            previous = mobile.version()["version_code"]
        with patch.dict(os.environ, {"GITHUB_RUN_NUMBER": "43", "GITHUB_RUN_ATTEMPT": "1"}):
            self.assertGreater(mobile.version()["version_code"], previous)
        for number, attempt in [("1", "100"), ("0", "1"), ("21000000", "1")]:
            with patch.dict(os.environ, {"GITHUB_RUN_NUMBER": number, "GITHUB_RUN_ATTEMPT": attempt}):
                with self.assertRaises(ValueError):
                    mobile.version()

    def test_candidate_rejects_tampering_and_wrong_commit(self):
        env = {"GITHUB_RUN_NUMBER": "1", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env):
            root = Path(directory)
            names = ["app-release-unsigned.apk", "app-release.aab", "app-debug.apk", "app-debug-androidTest.apk", "mapping.txt", "THIRD_PARTY_NOTICES.txt", "licence-closure.json", "source-provenance.json", "resource-provenance.json"]
            for name in names:
                (root / name).write_bytes(b"candidate artifact")
            info = {**mobile.version(), "commit": env["GITHUB_SHA"], "package": mobile.PACKAGE,
                    "sha256": {name: mobile.sha256(root / name) for name in names}}
            (root / "candidate.json").write_text(json.dumps(info), encoding="utf-8")
            (root / 'resource-provenance.json').write_text('{}\n', encoding='utf-8')
            info['sha256']['resource-provenance.json'] = mobile.sha256(root / 'resource-provenance.json')
            (root / 'candidate.json').write_text(json.dumps(info), encoding='utf-8')
            with patch.object(mobile, "inspect_apk") as inspect, patch.object(mobile, "verify_distribution") as licence, \
                    patch.object(mobile.resources, 'verify_archives', return_value={}):
                mobile.verify_candidate(root)
                inspect.assert_called_once()
                licence.assert_called_once_with(root, env["GITHUB_SHA"])
                (root / "app-release.aab").write_bytes(b"replaced after validation")
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    mobile.verify_candidate(root)
                info["commit"] = "b" * 40
                (root / "candidate.json").write_text(json.dumps(info), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "another commit"):
                    mobile.verify_candidate(root)


if __name__ == "__main__":
    unittest.main()
