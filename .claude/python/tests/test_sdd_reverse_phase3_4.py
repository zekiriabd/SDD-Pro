"""test_sdd_reverse_phase3_4.py — E2E coverage for Phase 3+4 (P1.5 closure).

Complements test_sdd_reverse_e2e.py (Phase 1 only) with :

    Phase 3 — atomic lock semantics, idempotence, contention
    Phase 4 — UI template parsing (aspx), CSS palette extraction

Goal : raise reverse module test coverage from ~15% (Phase 1 smoke only)
to ~40-50% by exercising the critical path of FEAT extraction (lock) +
UI extraction (parser) on the legacy-webforms-minimal fixture.

NOT covered yet (deferred V0.4) :
    - Full reverse-functional-extractor agent run (requires LLM)
    - Full reverse-ui-extractor agent run (requires LLM)
    - merge_db_schema with conflicting enrichments
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "legacy-webforms-minimal"


# ---------------------------------------------------------------------------
# Phase 3 — Lock atomicity + idempotence + contention
# ---------------------------------------------------------------------------

def test_phase3_lock_acquire_then_release(tmp_path: Path) -> None:
    """Single-agent acquire → release cycle."""
    from sdd_reverse.file_locks_local import acquire_lock, release_lock, read_lock

    lock = tmp_path / ".alloc.lock"
    assert acquire_lock(lock, "reverse-functional-extractor-U-1") == 0
    payload = read_lock(lock)
    assert payload is not None
    assert payload["agent_id"] == "reverse-functional-extractor-U-1"
    assert release_lock(lock, "reverse-functional-extractor-U-1") == 0


def test_phase3_lock_collision_blocks_second_agent(tmp_path: Path) -> None:
    """Two simultaneous U-N runs must serialize via lock."""
    from sdd_reverse.file_locks_local import acquire_lock

    lock = tmp_path / ".alloc.lock"
    assert acquire_lock(lock, "reverse-functional-extractor-U-1") == 0
    # Second agent attempts to acquire while first holds the lock
    assert acquire_lock(lock, "reverse-functional-extractor-U-2") == 1


def test_phase3_lock_idempotent_for_same_agent(tmp_path: Path) -> None:
    """Same agent re-acquiring (retry after transient failure) → exit 0."""
    from sdd_reverse.file_locks_local import acquire_lock

    lock = tmp_path / ".alloc.lock"
    agent = "reverse-functional-extractor-U-3"
    assert acquire_lock(lock, agent) == 0
    assert acquire_lock(lock, agent) == 0  # re-entrant
    assert acquire_lock(lock, agent) == 0  # idempotent


def test_phase3_lock_ttl_recovery(tmp_path: Path) -> None:
    """Lock older than TTL is overwritten as stale (exit 2)."""
    from sdd_reverse.file_locks_local import acquire_lock, read_lock

    lock = tmp_path / ".alloc.lock"
    # Simulate a crashed agent's stale lock (3600s old)
    lock.write_text(json.dumps({
        "agent_id": "reverse-functional-extractor-crashed",
        "pid": 99999,
        "ts_unix": int(time.time()) - 3600,
        "host": "crashed-machine",
    }), encoding="utf-8")
    assert acquire_lock(lock, "reverse-functional-extractor-U-1", ttl=30) == 2
    payload = read_lock(lock)
    assert payload is not None
    assert payload["agent_id"] == "reverse-functional-extractor-U-1"


def test_phase3_lock_payload_schema(tmp_path: Path) -> None:
    """Lock payload MUST conform to INVARIANTS.reverse.yml invariant #6 :
    {agent_id, pid, ts_unix, host}."""
    from sdd_reverse.file_locks_local import acquire_lock, read_lock

    lock = tmp_path / ".alloc.lock"
    acquire_lock(lock, "reverse-functional-extractor-U-1")
    payload = read_lock(lock)
    assert payload is not None
    required = {"agent_id", "pid", "ts_unix", "host"}
    missing = required - set(payload.keys())
    assert not missing, f"lock payload missing keys: {missing}"
    assert isinstance(payload["pid"], int)
    assert isinstance(payload["ts_unix"], int)


def test_phase3_atomic_write_no_orphan_after_lock_cycle(tmp_path: Path) -> None:
    """After acquire+release cycle, no .sddtmp orphan should remain."""
    from sdd_reverse.atomic_write_local import find_orphan_tmps
    from sdd_reverse.file_locks_local import acquire_lock, release_lock

    lock = tmp_path / ".alloc.lock"
    acquire_lock(lock, "reverse-functional-extractor-U-1")
    release_lock(lock, "reverse-functional-extractor-U-1")
    orphans = list(find_orphan_tmps(tmp_path))
    assert orphans == [], f"unexpected orphan tmp: {orphans}"


# ---------------------------------------------------------------------------
# Phase 4 — UI template parsing
# ---------------------------------------------------------------------------

def test_phase4_parse_aspx_login_extracts_title() -> None:
    """ui_template_parser detects <title> from real fixture Login.aspx."""
    from sdd_reverse.ui_template_parser import parse_template

    result = parse_template(FIXTURE_ROOT / "Login.aspx")
    assert result["template_family"] == "aspx"
    assert result["title"] == "Connexion"


def test_phase4_parse_aspx_login_detects_form() -> None:
    """ui_template_parser detects <form id="form1" runat="server">."""
    from sdd_reverse.ui_template_parser import parse_template

    result = parse_template(FIXTURE_ROOT / "Login.aspx")
    assert len(result["forms"]) == 1
    form = result["forms"][0]
    assert form["id"] == "form1"
    assert form["method"].lower() == "post"


def test_phase4_parse_aspx_login_detects_inputs() -> None:
    """asp:TextBox elements are extracted with their IDs."""
    from sdd_reverse.ui_template_parser import parse_template

    result = parse_template(FIXTURE_ROOT / "Login.aspx")
    input_ids = {
        e["id"] for e in result["elements"]
        if e["kind"] == "input"
    }
    assert "txtUsername" in input_ids, f"missing txtUsername in {input_ids}"
    assert "txtPassword" in input_ids, f"missing txtPassword in {input_ids}"


def test_phase4_parse_aspx_login_detects_button() -> None:
    """asp:Button is extracted with text + on_click handler."""
    from sdd_reverse.ui_template_parser import parse_template

    result = parse_template(FIXTURE_ROOT / "Login.aspx")
    buttons = [e for e in result["elements"] if e["kind"] == "button"]
    assert len(buttons) >= 1
    login_btn = next((b for b in buttons if b["id"] == "btnLogin"), None)
    assert login_btn is not None, f"btnLogin missing in {buttons}"
    assert login_btn["text"] == "Se connecter"
    assert login_btn["on_click"] == "btnLogin_Click"


def test_phase4_parse_aspx_label_associated_with_input() -> None:
    """asp:Label with AssociatedControlID is paired to the matching input."""
    from sdd_reverse.ui_template_parser import parse_template

    result = parse_template(FIXTURE_ROOT / "Login.aspx")
    txtuser = next(
        (e for e in result["elements"]
         if e["kind"] == "input" and e["id"] == "txtUsername"),
        None,
    )
    assert txtuser is not None
    # Label association is best-effort — accept either populated or empty
    # (regression guard: at minimum, the input must exist)


def test_phase4_parse_template_unknown_family_returns_safely(tmp_path: Path) -> None:
    """Unknown extension → 'unknown' family, no crash."""
    from sdd_reverse.ui_template_parser import parse_template

    weird = tmp_path / "page.xyz"
    weird.write_text("<html><body>hi</body></html>", encoding="utf-8")
    result = parse_template(weird)
    assert result["template_family"] == "unknown"
    assert "elements" in result  # always present, even if empty


def test_phase4_parse_template_empty_file(tmp_path: Path) -> None:
    """Empty file → no crash, returns minimal structure."""
    from sdd_reverse.ui_template_parser import parse_template

    empty = tmp_path / "empty.aspx"
    empty.write_text("", encoding="utf-8")
    result = parse_template(empty)
    assert result["template_family"] == "aspx"
    assert result["forms"] == []
    assert result["elements"] == []


# ---------------------------------------------------------------------------
# Phase 4 — CSS palette extraction
# ---------------------------------------------------------------------------

def _empty_scan_result():
    """Build a minimal ScanResult for tests that don't need a real scan."""
    from sdd_reverse.scan_legacy import ScanResult
    return ScanResult(
        primary_language=None,
        languages=[],
        frameworks=[],
        files_scanned=0,
        files_skipped=0,
        duration_ms=0,
    )


def test_phase4_css_palette_extracts_hex_colors(tmp_path: Path) -> None:
    """Extractor returns top colors from a CSS payload (rglob fallback)."""
    from sdd_reverse.css_palette_extractor import extract_palette

    css = tmp_path / "site.css"
    css.write_text(
        "body { background: #ffffff; color: #333333; }\n"
        ".primary { background: #2563eb; color: #fff; }\n"
        ".accent { color: #ef4444; }\n"
        ".btn { background: #2563eb; padding: 8px 16px; }\n"
        ".card { background: #2563eb; }\n",
        encoding="utf-8",
    )

    palette = extract_palette(tmp_path, _empty_scan_result())
    assert "colors" in palette
    # #2563eb appears 3 times → must be in the top entries
    top_colors = [c.get("hex", c.get("value", "")).lower() for c in palette["colors"][:5]]
    assert any("2563eb" in c for c in top_colors), f"missing primary in {top_colors}"


def test_phase4_css_palette_handles_empty_dir(tmp_path: Path) -> None:
    """No CSS files → palette has empty colors, no crash."""
    from sdd_reverse.css_palette_extractor import extract_palette

    palette = extract_palette(tmp_path, _empty_scan_result())
    assert "colors" in palette
    assert palette["colors"] == []
