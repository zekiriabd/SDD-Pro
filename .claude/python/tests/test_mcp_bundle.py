"""Tests for sdd_mcp.build_mcpb — MCPB bundle producer (Phase 3)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_PY_ROOT = REPO_ROOT / ".claude" / "python"
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_mcp import build_mcpb  # noqa: E402


class TestMcpbBundle(unittest.TestCase):
    def test_build_produces_zip_with_required_entries(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            output = Path(tmp) / "sdd-pro.mcpb"
            result = build_mcpb.build(output=output)
            self.assertEqual(result, output)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)

            with zipfile.ZipFile(output) as zf:
                names = set(zf.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("README.md", names)
                # spot-check that key modules made it in
                self.assertTrue(any(n.startswith("server/sdd_mcp/") for n in names))
                self.assertTrue(any(n.startswith("server/sdd_scripts/") for n in names))
                self.assertTrue(any(n.startswith("server/sdd_lib/") for n in names))

                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertEqual(manifest["name"], "sdd-pro")
                self.assertEqual(manifest["server"]["type"], "stdio")
                # All 14 tools advertised
                self.assertEqual(len(manifest["tools"]), 14)

    def test_no_caches_in_bundle(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            output = Path(tmp) / "sdd-pro.mcpb"
            build_mcpb.build(output=output)
            with zipfile.ZipFile(output) as zf:
                for name in zf.namelist():
                    self.assertNotIn("__pycache__", name)
                    self.assertNotIn(".pytest_cache", name)
                    self.assertNotIn(".mypy_cache", name)


if __name__ == "__main__":
    unittest.main()
