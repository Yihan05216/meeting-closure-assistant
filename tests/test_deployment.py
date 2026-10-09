import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment_support import read_secret, reserve_analysis


class DeploymentTests(unittest.TestCase):
    def test_shared_budget_and_no_duplicate_attempts(self):
        state = {}
        for i in range(8):
            self.assertIsNone(reserve_analysis(state, {"request": i}))
        self.assertIn("limit", reserve_analysis(state, {"request": 9}))
        self.assertIn("already", reserve_analysis(state, {"request": 0}))
        self.assertEqual(len(state["public_analysis_attempts"]), 8)

    def test_secrets_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch('streamlit.secrets', {"DEEPSEEK_API_KEY": "test-placeholder"}):
            self.assertEqual(read_secret("DEEPSEEK_API_KEY"), "test-placeholder")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-placeholder"}):
            self.assertEqual(read_secret("DEEPSEEK_API_KEY"), "env-placeholder")


if __name__ == '__main__':
    unittest.main()
