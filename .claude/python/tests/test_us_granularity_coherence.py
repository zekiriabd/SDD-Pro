"""P1-1 fix 2026-06-07 — coherence test for US granularity caps.

Ensures `UsGranularityHardCap` and `UsGranularityWarnAt` are consistently
described across config.base.yml, project-config.schema.json, the `po`
agent prompt, and the `/us-generate` command doc. Drift = test fail.

Audit found 2026-06-07 :
  - po.md description claimed `hard cap 6` (legacy v6.x value)
  - us-generate.md introduction claimed `hard cap 6`
  - config.base.yml actually sets `UsGranularityHardCap: 10`
  - project-config.schema.json describes `UsGranularityHardCap` with
    range allowing values up to 99 and default 10

This drift means an LLM reading po.md's frontmatter could refuse FEATs
of 7-10 US when config legitimately allows them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

# Repo root = the directory containing both .claude/ and workspace/
_REPO_ROOT = _PYTHON_ROOT.parent.parent

CONFIG_BASE = _REPO_ROOT / ".claude" / "config.base.yml"
PO_MD = _REPO_ROOT / ".claude" / "agents" / "po.md"
US_GENERATE_MD = _REPO_ROOT / ".claude" / "commands" / "us-generate.md"


def test_config_base_declares_hardcap_10() -> None:
    """Baseline contract — config.base.yml is the source of truth."""
    content = CONFIG_BASE.read_text(encoding="utf-8")
    match = re.search(r"^UsGranularityHardCap:\s*(\d+)", content, re.MULTILINE)
    assert match is not None, "UsGranularityHardCap missing from config.base.yml"
    assert int(match.group(1)) == 10, "config.base.yml should declare hard cap = 10"


def test_config_base_declares_warnat_6() -> None:
    content = CONFIG_BASE.read_text(encoding="utf-8")
    match = re.search(r"^UsGranularityWarnAt:\s*(\d+)", content, re.MULTILINE)
    assert match is not None, "UsGranularityWarnAt missing from config.base.yml"
    assert int(match.group(1)) == 6, "config.base.yml should declare warn = 6"


def test_po_md_description_does_not_claim_hardcap_6() -> None:
    """P1-1 drift detection — po.md must not advertise the legacy cap 6."""
    content = PO_MD.read_text(encoding="utf-8")
    # The phrase "hard cap 6" appears in the legacy description ("warning 4-6, hard cap 6")
    # Look for it in the frontmatter description (first 30 lines)
    head = "\n".join(content.splitlines()[:40])
    # Match `hard cap` followed by ` 6` (but allow `hard cap 10` and references like
    # `UsGranularityHardCap (default 10)`)
    bad = re.search(r"hard cap\s+6(?!\d)", head, re.IGNORECASE)
    assert bad is None, (
        "po.md still advertises legacy 'hard cap 6' in description — "
        "should reference UsGranularityHardCap (default 10)"
    )


def test_us_generate_md_does_not_claim_hardcap_6() -> None:
    """P1-1 drift detection — us-generate.md must not advertise the legacy cap 6."""
    content = US_GENERATE_MD.read_text(encoding="utf-8")
    # Look only in the introduction (before STEP 1), where the user-facing
    # cap is mentioned.
    intro = content.split("## STEP")[0]
    bad = re.search(r"hard cap\s+6(?!\d)", intro, re.IGNORECASE)
    assert bad is None, (
        "us-generate.md still advertises legacy 'hard cap 6' in introduction — "
        "should reference UsGranularityHardCap (default 10)"
    )


def test_po_md_references_config_keys() -> None:
    """po.md must reference the configurable keys, not hardcode the values."""
    content = PO_MD.read_text(encoding="utf-8")
    assert "UsGranularityHardCap" in content, (
        "po.md should mention `UsGranularityHardCap` configurable key"
    )
    assert "UsGranularityWarnAt" in content, (
        "po.md should mention `UsGranularityWarnAt` configurable key"
    )
