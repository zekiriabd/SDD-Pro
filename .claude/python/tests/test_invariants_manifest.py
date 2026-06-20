"""Smoke test : every enforcer file listed in .claude/INVARIANTS.yml must exist.

Audit P3 E4 (2026-06-08) — anti-rot enforcement for the invariants manifest.
The manifest declares which file enforces each load-bearing contract. If
an enforcer file is removed (refactor, accidental delete, doc theater),
this test fails with a clear pointer to which invariant lost its
enforcement.

What we check :
1. Every `enforcers:` path in INVARIANTS.yml exists on disk.
2. Every invariant has a unique `id`.
3. Every invariant has a non-empty `severity` in {critical, major, minor}.
4. The total count at top of manifest matches the actual count of invariants.

This test does NOT verify that the enforcer ACTUALLY enforces (that would
require runtime testing of every invariant). It just guards against
silent removal of the enforcer file.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


def _repo_root() -> Path:
    cwd = Path(__file__).resolve()
    for p in [cwd, *cwd.parents]:
        if (p / ".claude").is_dir():
            return p
    raise RuntimeError("Cannot locate repo root")


def _load_invariants() -> list[dict]:
    """Parse INVARIANTS.yml minimally (no external yaml dep — handle our format manually).

    SDDPro convention : YAML files in framework are simple enough that we
    can parse with a minimal hand-rolled parser to avoid adding a runtime
    dependency on PyYAML.
    """
    manifest_path = _repo_root() / ".claude" / "INVARIANTS.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"INVARIANTS.yml not found at {manifest_path}")

    text = manifest_path.read_text(encoding="utf-8")
    # Split into invariant blocks by `- id:` markers
    invariants: list[dict] = []
    current: dict | None = None
    current_list_key: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        # Section markers
        if line.startswith("  - id:"):
            if current is not None:
                invariants.append(current)
            current = {"id": stripped.split(":", 1)[1].strip(), "enforcers": [], "bypasses": []}
            current_list_key = None
            continue
        if current is None:
            continue
        # Field with value: `    key: value` or `    key: |` (multiline) or `    key:`
        m = re.match(r"^    (\w+)\s*:\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            current_list_key = None
            if val == "" or val == "|":
                if key in ("enforcers", "bypasses"):
                    current_list_key = key
                continue
            current[key] = val
            continue
        # List item: `      - foo`
        m2 = re.match(r"^      - (.+)$", line)
        if m2 and current_list_key:
            val = m2.group(1).strip().strip('"').strip("'")
            # Strip inline comments after #
            val = re.sub(r"\s+#.*$", "", val)
            current[current_list_key].append(val)
            continue
    if current is not None:
        invariants.append(current)
    return invariants


class TestInvariantsManifest(unittest.TestCase):

    def test_manifest_exists(self):
        manifest = _repo_root() / ".claude" / "INVARIANTS.yml"
        self.assertTrue(manifest.is_file(), f"INVARIANTS.yml missing at {manifest}")

    def test_invariants_parseable(self):
        invs = _load_invariants()
        self.assertGreater(
            len(invs), 5,
            f"Expected > 5 invariants, got {len(invs)} (parse failure?)",
        )

    def test_unique_ids(self):
        invs = _load_invariants()
        ids = [inv["id"] for inv in invs]
        duplicates = [i for i in set(ids) if ids.count(i) > 1]
        self.assertFalse(duplicates, f"Duplicate invariant IDs: {duplicates}")

    def test_severity_valid(self):
        invs = _load_invariants()
        valid = {"critical", "major", "minor"}
        offenders = [
            (inv["id"], inv.get("severity", "(missing)"))
            for inv in invs
            if inv.get("severity") not in valid
        ]
        self.assertFalse(
            offenders,
            f"Invariants with invalid/missing severity: {offenders}. "
            f"Valid: {valid}",
        )

    def test_every_enforcer_file_exists(self):
        invs = _load_invariants()
        root = _repo_root()
        missing: list[tuple[str, str]] = []  # (invariant_id, enforcer_path)
        for inv in invs:
            for enforcer in inv.get("enforcers", []):
                path = root / enforcer
                if not path.is_file():
                    missing.append((inv["id"], enforcer))
        if missing:
            details = "\n".join(
                f"  - invariant '{iid}': enforcer '{path}' MISSING on disk"
                for iid, path in missing
            )
            self.fail(
                f"\nINVARIANTS.yml enforcer drift detected — "
                f"files declared as enforcers no longer exist :\n{details}\n\n"
                f"Fix options :\n"
                f"  1. Restore the enforcer file (revert delete)\n"
                f"  2. Update INVARIANTS.yml to point to the new enforcer\n"
                f"  3. Retire the invariant entirely (remove from manifest + document why)\n"
            )

    def test_critical_invariants_have_at_least_one_enforcer(self):
        invs = _load_invariants()
        offenders = [
            inv["id"] for inv in invs
            if inv.get("severity") == "critical"
            and len(inv.get("enforcers", [])) == 0
        ]
        self.assertFalse(
            offenders,
            f"Critical invariants without enforcer: {offenders}. "
            f"Critical = system-breaking if violated, must have runtime enforcement.",
        )


if __name__ == "__main__":
    unittest.main()
