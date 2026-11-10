"""Regression tests for the Claude Code plugin manifest."""

import json
import unittest
from pathlib import Path


class PluginManifestTests(unittest.TestCase):
    def test_manifest_declares_empty_mcp_server_map_for_marketplace_contract(self):
        """A hook-only plugin still declares the marketplace MCP field."""
        manifest_path = Path(__file__).parents[1] / ".claude-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIn("mcpServers", manifest)
        self.assertEqual(manifest["mcpServers"], {})


if __name__ == "__main__":
    unittest.main()
