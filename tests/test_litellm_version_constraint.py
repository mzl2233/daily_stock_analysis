# -*- coding: utf-8 -*-
"""Verify that requirements.txt excludes the compromised litellm 1.82.7 and 1.82.8 versions.

These versions contained a supply-chain attack that stole SSH keys, cloud credentials,
and Kubernetes secrets. See https://github.com/BerriAI/litellm/issues/24521
"""

import os
import re
import unittest


class LiteLLMVersionConstraintTest(unittest.TestCase):
    """Ensure requirements.txt pins away from the malicious litellm releases."""

    def _get_litellm_constraint(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        req_path = os.path.join(repo_root, "requirements.txt")
        with open(req_path, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.split("#")[0].strip()
                if stripped.startswith("litellm"):
                    return stripped
        return None

    def test_litellm_line_present(self):
        constraint = self._get_litellm_constraint()
        self.assertIsNotNone(constraint, "litellm must be listed in requirements.txt")

    def test_excludes_1_82_7(self):
        """requirements.txt must exclude the malicious 1.82.7 build."""
        constraint = self._get_litellm_constraint()
        self.assertIsNotNone(constraint)
        self.assertIn("!=1.82.7", constraint,
                      "litellm 1.82.7 (supply-chain attack) must be excluded via !=1.82.7")

    def test_excludes_1_82_8(self):
        """requirements.txt must exclude the malicious 1.82.8 build."""
        constraint = self._get_litellm_constraint()
        self.assertIsNotNone(constraint)
        self.assertIn("!=1.82.8", constraint,
                      "litellm 1.82.8 (supply-chain attack) must be excluded via !=1.82.8")

    def test_no_upper_bound_blocking_safe_versions(self):
        """Constraint must not use <1.82.7 which would block all subsequent safe versions."""
        constraint = self._get_litellm_constraint()
        self.assertIsNotNone(constraint)
        self.assertNotIn("<1.82.7", constraint,
                         "Upper bound <1.82.7 blocks safe versions 1.82.9+; use !=1.82.7,!=1.82.8 instead")

    def test_minimum_version_preserved(self):
        """Minimum version >=1.80.10 must still be present."""
        constraint = self._get_litellm_constraint()
        self.assertIsNotNone(constraint)
        self.assertIn(">=1.80.10", constraint,
                      "Minimum version >=1.80.10 must be kept in the litellm constraint")


if __name__ == "__main__":
    unittest.main()
