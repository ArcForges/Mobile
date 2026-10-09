# SPDX-License-Identifier: Apache-2.0
"""Release guards: certificate matching and version ordering."""

import importlib.util
import os
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
