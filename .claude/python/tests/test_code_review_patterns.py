"""Cross-check code_review_patterns.yaml against error-classification.md §1.10."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

YAML_PATH = Path(__file__).resolve().parents[1] / "code_review_patterns.yaml"
ERROR_CLASS_PATH = (
    Path(__file__).resolve().parents[2] / "rules" / "error-classification.md"
)


def _load_yaml():
    try:
        import yaml  # type: ignore
    except ImportError:
        pytest.skip("PyYAML not installed")
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


def test_yaml_file_exists():
    assert YAML_PATH.is_file()


def test_yaml_schema_minimum_fields():
    doc = _load_yaml()
    assert doc["schemaVersion"] == 1
    assert isinstance(doc["classes"], list)
    assert len(doc["classes"]) >= 10
    for cls in doc["classes"]:
        assert cls["prefix"].startswith("[REVIEW_") and cls["prefix"].endswith("]")
        assert cls["severity"] in {"critical", "serious", "moderate", "minor"}
        assert isinstance(cls["hard_blocking"], bool)


def test_yaml_matches_error_classification():
    """Each [REVIEW_*] in YAML must exist in error-classification.md §1.10."""
    doc = _load_yaml()
    md = ERROR_CLASS_PATH.read_text(encoding="utf-8")
    section_110 = md.split("### 1.10")[1].split("### 1.11")[0] if "### 1.10" in md else md
    yaml_prefixes = {cls["prefix"] for cls in doc["classes"]}
    missing = [p for p in yaml_prefixes if p not in section_110]
    assert not missing, f"YAML classes missing from §1.10: {missing}"


def test_yaml_regex_compiles():
    doc = _load_yaml()
    for cls in doc["classes"]:
        for pat in cls.get("patterns") or []:
            try:
                re.compile(pat["regex"])
            except re.error as e:  # pragma: no cover
                pytest.fail(f"{cls['prefix']} regex {pat['regex']!r} invalid: {e}")


def test_yaml_dedup_section():
    """Coordination section must mention security_patterns + quality_scan."""
    doc = _load_yaml()
    dedup = doc["coordination"]["dedup_against"]
    assert any("security_patterns" in s for s in dedup)
    assert any("quality_scan" in s for s in dedup)
