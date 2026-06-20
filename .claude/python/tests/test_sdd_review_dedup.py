"""v7.0.0 R3 — tests for sdd_review.py path normalization + cross-source dedup."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_scripts.sdd_review import _normalize_path, deduplicate_findings, Finding  # noqa: E402


class TestNormalizePath(unittest.TestCase):
    """All these inputs MUST normalize to 'x/auth.cs'."""

    def test_full_repo_relative(self) -> None:
        self.assertEqual(
            _normalize_path("workspace/output/src/X/Auth.cs"),
            "x/auth.cs",
        )

    def test_project_relative(self) -> None:
        self.assertEqual(_normalize_path("src/X/Auth.cs"), "x/auth.cs")

    def test_leading_dot_slash(self) -> None:
        self.assertEqual(_normalize_path("./X/Auth.cs"), "x/auth.cs")

    def test_windows_backslashes(self) -> None:
        self.assertEqual(
            _normalize_path(r"workspace\output\src\X\Auth.cs"),
            "x/auth.cs",
        )

    def test_module_relative(self) -> None:
        self.assertEqual(_normalize_path("X/Auth.cs"), "x/auth.cs")

    def test_empty_string(self) -> None:
        self.assertEqual(_normalize_path(""), "")

    def test_none(self) -> None:
        self.assertEqual(_normalize_path(None), "")

    def test_duplicate_slashes(self) -> None:
        self.assertEqual(_normalize_path("src//X//Auth.cs"), "x/auth.cs")


class TestDeduplicateFindings(unittest.TestCase):
    """Cross-source dedup with path normalization + canonical class mapping."""

    def _make(self, source: str, cls: str, sev: str, path: str, line: int) -> Finding:
        return Finding(
            source=source, issue_class=cls, severity=sev,
            rule=None, file_path=path, line=line, message=f"{cls} {path}:{line}",
        )

    def test_secrets_duo_dedup_same_path(self) -> None:
        """REVIEW_SECRETS_HARDCODED + SEC_SECRET_HARDCODED on same path:line = 1 finding."""
        findings = [
            self._make("code-review", "REVIEW_SECRETS_HARDCODED", "critical", "src/Auth.cs", 42),
            self._make("security", "SEC_SECRET_HARDCODED", "critical", "src/Auth.cs", 42),
        ]
        deduped, sup = deduplicate_findings(findings)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(sup, 1)

    def test_secrets_duo_dedup_divergent_paths(self) -> None:
        """Same logical file emitted with different prefixes still dedups."""
        findings = [
            self._make("code-review", "REVIEW_SECRETS_HARDCODED", "critical",
                       "workspace/output/src/Auth.cs", 42),
            self._make("security", "SEC_SECRET_HARDCODED", "critical",
                       "src/Auth.cs", 42),  # same logical file, shorter prefix
        ]
        deduped, sup = deduplicate_findings(findings)
        self.assertEqual(len(deduped), 1, "Path normalization should fuse divergent prefixes")
        self.assertEqual(sup, 1)

    def test_layer_violation_trio_dedup(self) -> None:
        """LAYER_VIOLATION + ARCH_LAYER_BYPASS + ARCH_PATTERN_VIOLATION all map to LAYER_VIOLATION_GROUP."""
        findings = [
            self._make("code-review", "LAYER_VIOLATION", "serious", "Pages/Index.razor", 10),
            self._make("arch", "ARCH_LAYER_BYPASS", "serious", "Pages/Index.razor", 10),
            self._make("arch", "ARCH_PATTERN_VIOLATION", "serious", "Pages/Index.razor", 10),
        ]
        deduped, sup = deduplicate_findings(findings)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(sup, 2)

    def test_no_dedup_different_files(self) -> None:
        """Different files = no dedup."""
        findings = [
            self._make("code-review", "REVIEW_SECRETS_HARDCODED", "critical", "Auth.cs", 42),
            self._make("security", "SEC_SECRET_HARDCODED", "critical", "Db.cs", 100),
        ]
        deduped, sup = deduplicate_findings(findings)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(sup, 0)

    def test_keeps_highest_severity(self) -> None:
        """When deduping, keep the finding with the highest severity."""
        findings = [
            self._make("arch", "LAYER_VIOLATION", "serious", "X.cs", 5),
            self._make("code-review", "LAYER_VIOLATION", "critical", "X.cs", 5),
        ]
        deduped, sup = deduplicate_findings(findings)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].severity, "critical")
        self.assertEqual(sup, 1)


if __name__ == "__main__":
    unittest.main()
