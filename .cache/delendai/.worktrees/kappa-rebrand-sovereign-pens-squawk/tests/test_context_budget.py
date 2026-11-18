"""Regression checks for the compact skill entry points."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContextBudgetTests(unittest.TestCase):
    def test_skill_entries_fit_context_budget_and_reference_resolves(self):
        entries = [ROOT / "SKILL.md", ROOT / "skills" / "agent-chat" / "SKILL.md"]
        self.assertLessEqual(max(path.stat().st_size for path in entries), 8192)
        reference = ROOT / "skills" / "agent-chat" / "reference.md"
        self.assertTrue(reference.is_file())
        self.assertIn("reference.md", entries[1].read_text(encoding="utf-8"))
        self.assertNotIn("reference.md", entries[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
