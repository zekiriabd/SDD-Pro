"""Cross-check security_patterns.yaml against error-classification.md §1.11.

The YAML is the new machine-readable SSoT for OWASP class definitions.
This test ensures no drift between the YAML and the canonical taxonomy.

Note: requires PyYAML. If not available in the test env, the test will
skip cleanly rather than fail (the YAML is informational v7.0.0,
load-bearing from v7.0.1).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

YAML_PATH = Path(__file__).resolve().parents[1] / "security_patterns.yaml"
ERROR_CLASS_PATH = (
    Path(__file__).resolve().parents[2] / "rules" / "error-classification.md"
)


def _load_yaml():
    try:
        import yaml  # type: ignore
    except ImportError:
        pytest.skip("PyYAML not installed (YAML is informational in v7.0.0)")
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


def test_yaml_file_exists():
    assert YAML_PATH.is_file(), f"missing {YAML_PATH}"


def test_yaml_schema_minimum_fields():
    doc = _load_yaml()
    assert doc["schemaVersion"] == 1
    assert isinstance(doc["classes"], list)
    assert len(doc["classes"]) >= 20  # 22 SEC classes expected
    for cls in doc["classes"]:
        assert cls["prefix"].startswith("[SEC_") and cls["prefix"].endswith("]")
        assert cls["severity"] in {"critical", "serious", "moderate", "minor"}
        assert isinstance(cls["hard_blocking"], bool)
        assert cls["owasp"]
        assert cls["mode"] in {"threat-model", "scan"}


def test_yaml_matches_error_classification():
    """Every [SEC_*] prefix in the YAML must also appear in error-classification.md §1.11."""
    doc = _load_yaml()
    md = ERROR_CLASS_PATH.read_text(encoding="utf-8")
    section_111 = md.split("### 1.11")[1].split("### 1.12")[0] if "### 1.11" in md else md
    yaml_prefixes = {cls["prefix"] for cls in doc["classes"]}
    missing = [p for p in yaml_prefixes if p not in section_111]
    assert not missing, f"YAML classes missing from error-classification.md §1.11: {missing}"


def test_yaml_hard_blocking_aligned_with_md():
    """The 8 hard-blocking classes must match error-classification.md §1.11."""
    doc = _load_yaml()
    yaml_hard = {cls["prefix"] for cls in doc["classes"] if cls.get("hard_blocking")}
    expected = {
        "[SEC_SECRET_HARDCODED]",
        "[SEC_SQL_INJECTION]",
        "[SEC_COMMAND_INJECTION]",
        "[SEC_BROKEN_AUTHZ]",
        "[SEC_BROKEN_AUTHN]",
        "[SEC_DESERIALIZATION_UNSAFE]",
        "[SEC_JWT_MISCONFIG]",
        "[SEC_SSRF_RISK]",
    }
    assert yaml_hard == expected, f"drift hard_blocking: YAML={yaml_hard} vs expected={expected}"


def test_yaml_regex_compiles():
    """Every regex pattern compiles without error."""
    doc = _load_yaml()
    for cls in doc["classes"]:
        for pat in cls.get("patterns") or []:
            try:
                re.compile(pat["regex"])
            except re.error as e:  # pragma: no cover
                pytest.fail(f"{cls['prefix']} regex {pat['regex']!r} invalid: {e}")
