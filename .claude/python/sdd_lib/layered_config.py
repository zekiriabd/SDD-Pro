"""SDD_Pro layered Project Config — base.yml ← team.yml ← project (stack.md).

Extends `sdd_lib/project_config.py` with a 3-level merge hierarchy
allowing organizations to enforce policies cross-projects.

Layering (lowest → highest precedence) :
    1. `.claude/config.base.yml`    (framework defaults, versionné SDD_Pro)
    2. `~/.sdd/config.team.yml`     (org/team policy, ~/.sdd/ ou %USERPROFILE%/.sdd/)
    3. `## Project Config` block of `workspace/input/stack/stack.md` (per-project)

Deep-merge semantics :
    - dicts: keys merged, child values resolved recursively
    - lists: **replaced** (no concat) — clarté > flexibilité
    - scalars: highest precedence wins
    - missing files: skipped (default-on opt-in)

Backward compatibility :
    - If `config.base.yml` and `~/.sdd/config.team.yml` both absent
      → behavior **byte-identical** to v6.6.x (returns the project config
      as-is, parsed via project_config.read_project_config()).
    - Existing scripts can continue calling read_project_config() unchanged;
      adoption of read_layered_config() is opt-in per script.

Security-down guard :
    - Team config CANNOT relax security thresholds. If
      `team.yml.SecurityFailOn=critical` and project tries to set
      `SpecComplianceFailOn=minor`, the merge raises `[CONFIG_SECURITY_DOWNGRADE]`.
      Project can only DURCIR (raise) not RELAX (lower) policy.
    - Applies to: SecurityFailOn, A11yFailOn, CodeReviewFailOn,
      PerfFailOn, SpecComplianceFailOn, CoverageMin.

Audit trail :
    - `dump_effective_config()` produces `config-effective.yml` showing
      `(value, source: base|team|project)` per key — auditable post-hoc.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from sdd_lib.paths import repo_root
from sdd_lib.project_config import (
    coerce_config_types,
    normalize_project_aliases,
    parse_kv_block,
    section_body,
    stack_md_path,
)


# Keys subject to security-down protection (project cannot relax team's value)
SECURITY_HARDENING_KEYS: set[str] = {
    "SecurityFailOn",
    "A11yFailOn",
    "CodeReviewFailOn",
    "PerfFailOn",
    "SpecComplianceFailOn",
}

# Severity ordering: critical = strictest, minor = most lenient
SEVERITY_ORDER: tuple[str, ...] = ("critical", "serious", "moderate", "minor")

# Numeric keys with "higher is stricter" semantics — project must >= team
COVERAGE_HARDENING_KEYS: set[str] = {"CoverageMin"}


class ConfigError(Exception):
    """Raised when a config layering invariant is violated."""

    def __init__(self, error: str, cause: str, fix: str):
        super().__init__(cause)
        self.error = error
        self.cause = cause
        self.fix = fix


def base_config_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".claude" / "config.base.yml"


def team_config_path() -> Path:
    """User-level team config: ~/.sdd/config.team.yml (cross-platform).

    Honors $SDD_TEAM_CONFIG env var override (useful for tests).
    """
    override = os.environ.get("SDD_TEAM_CONFIG")
    if override:
        return Path(override)
    home = Path(os.path.expanduser("~"))
    return home / ".sdd" / "config.team.yml"


def _parse_yaml_minimal(text: str) -> dict[str, Any]:
    """Minimal YAML subset parser: flat `Key: value` lines.

    No need for full YAML — SDD_Pro Project Config is a flat key-value
    bag. Supports comments (#), empty lines, quoted strings.
    Returns dict with all scalar values as strings (caller normalizes
    type via downstream parsers).
    """
    out: dict[str, str] = {}
    seen: dict[str, int] = {}
    line_re = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.+?)\s*(?:#.*)?$")
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].rstrip() if "#" in raw and not _is_in_quotes(raw, "#") else raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = line_re.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        value = value.strip('"').strip("'")
        if key in seen:
            raise ValueError(
                f"[CONFIG_DUPLICATE_KEY] '{key}' defined twice "
                f"(first at line {seen[key]}, again at line {lineno}). "
                f"Remove one or use layered override (base ← team ← project)."
            )
        seen[key] = lineno
        out[key] = value
    return out


def _is_in_quotes(line: str, marker: str) -> bool:
    """Heuristic: is `marker` inside a quoted string in this line?"""
    idx = line.find(marker)
    if idx < 0:
        return False
    quotes_before = sum(line[:idx].count(q) for q in ('"', "'"))
    return quotes_before % 2 == 1


def _read_yaml_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        return _parse_yaml_minimal(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _read_project_section(root: Path) -> dict[str, str]:
    """Read `## Project Config` block from stack.md (or return empty).

    v6.10.2+: normalizes FrontendName→AppName alias and auto-derives
    AppNamespace/BackendNamespace via `normalize_project_aliases` (SSOT in
    project_config.py).

    v6.10.5+ (audit 2026-05-19): if a `## Auditors` block exists in
    stack.md, it is parsed and expanded to the 12 legacy flat keys
    (A11yMode, A11yFailOn, CodeReviewMode, ...). Legacy flat keys in
    `## Project Config` take precedence over the block (backward compat).
    """
    path = stack_md_path(root)
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    block = section_body(text, "Project Config")
    project_kv: dict[str, str] = {}
    if block is not None:
        project_kv = parse_kv_block(block)
    auditors_block = section_body(text, "Auditors")
    auditors_kv = _parse_auditors_block(auditors_block) if auditors_block else {}
    # Legacy flat keys WIN over Auditors block (backward compat).
    merged = {**auditors_kv, **project_kv}
    return normalize_project_aliases(merged)


# ---------------------------------------------------------------------------
# v6.10.5 (audit 2026-05-19) — `## Auditors` block parser
# ---------------------------------------------------------------------------
# Discovery friction win : replaces 12 scattered flat keys
#   (A11yMode, A11yFailOn, CodeReviewMode, CodeReviewFailOn, ...)
# with a single block:
#
#   ## Auditors
#   a11y: full/serious
#   codeReview: manual/critical
#   security: manual/critical
#   perf: full/serious
#   spec: manual/serious
#   arch: manual/serious
#
# Format per line: `name: mode/failOn` (failOn optional).
# Aliases supported : a11y, codeReview, security, perf, spec, arch.
# ---------------------------------------------------------------------------
AUDITORS_ALIAS_MAP: dict[str, tuple[str, str]] = {
    "a11y":          ("A11yMode",             "A11yFailOn"),
    "accessibility": ("A11yMode",             "A11yFailOn"),
    "codereview":    ("CodeReviewMode",       "CodeReviewFailOn"),
    "code":          ("CodeReviewMode",       "CodeReviewFailOn"),
    "security":      ("SecurityMode",         "SecurityFailOn"),
    "sec":           ("SecurityMode",         "SecurityFailOn"),
    "perf":          ("PerfMode",             "PerfFailOn"),
    "performance":   ("PerfMode",             "PerfFailOn"),
    "spec":          ("SpecComplianceMode",   "SpecComplianceFailOn"),
    "speccompliance":("SpecComplianceMode",   "SpecComplianceFailOn"),
    "arch":          ("ArchReviewMode",       "ArchReviewFailOn"),
    "archreview":    ("ArchReviewMode",       "ArchReviewFailOn"),
}


def _parse_auditors_block(text: str) -> dict[str, str]:
    """Parse `## Auditors` body into the 12 legacy flat keys.

    Each line : `<name>: <mode>` or `<name>: <mode>/<failOn>`.
    Unknown aliases are silently ignored (forward-compat).
    Lines starting with `#` and empty lines are skipped.
    """
    out: dict[str, str] = {}
    line_re = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*([^\s/]+)(?:\s*/\s*([^\s#]+))?\s*(?:#.*)?$")
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = line_re.match(raw)
        if not m:
            continue
        alias = m.group(1).lower().replace("-", "").replace("_", "")
        mapping = AUDITORS_ALIAS_MAP.get(alias)
        if mapping is None:
            continue
        mode_key, failon_key = mapping
        mode_val = m.group(2).strip()
        if mode_val:
            out[mode_key] = mode_val
        failon_val = (m.group(3) or "").strip()
        if failon_val:
            out[failon_key] = failon_val
    return out


def _severity_idx(value: str) -> int | None:
    try:
        return SEVERITY_ORDER.index(value.strip().lower())
    except (ValueError, AttributeError):
        return None


def _check_security_down(key: str, team_val: str, project_val: str) -> None:
    """Raise ConfigError if project's value relaxes team's policy."""
    if key in SECURITY_HARDENING_KEYS:
        ti = _severity_idx(team_val)
        pi = _severity_idx(project_val)
        if ti is not None and pi is not None and pi > ti:
            # Higher index = more lenient. Project more lenient = downgrade.
            raise ConfigError(
                "Layered config rejected — security downgrade attempted",
                f"[CONFIG_SECURITY_DOWNGRADE] project '{key}={project_val}' relaxes "
                f"team policy '{key}={team_val}'",
                f"project must use a value >= team's (critical < serious < moderate < minor)",
            )
    elif key in COVERAGE_HARDENING_KEYS:
        try:
            t_int = int(team_val)
            p_int = int(project_val)
        except (ValueError, TypeError):
            return
        if p_int < t_int:
            raise ConfigError(
                "Layered config rejected — coverage downgrade attempted",
                f"[CONFIG_SECURITY_DOWNGRADE] project '{key}={p_int}' below "
                f"team minimum '{key}={t_int}'",
                f"project must satisfy {key} >= {t_int} (team policy)",
            )


def _merge_with_source_tracking(
    base: dict[str, str],
    team: dict[str, str],
    project: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Merge 3 layers, return (effective_dict, source_dict).

    source_dict maps key → 'base' | 'team' | 'project'.
    """
    effective: dict[str, str] = {}
    source: dict[str, str] = {}

    for k, v in base.items():
        effective[k] = v
        source[k] = "base"

    for k, v in team.items():
        effective[k] = v
        source[k] = "team"

    for k, v in project.items():
        # Security-down check: only when team set the value AND project overrides
        if source.get(k) == "team":
            _check_security_down(k, team.get(k, ""), v)
        effective[k] = v
        source[k] = "project"

    return effective, source


def read_layered_config(
    root: Path | None = None,
    *,
    keys: tuple[str, ...] | None = None,
    include_sources: bool = False,
    coerce: bool = False,
) -> dict[str, Any]:
    """Read 3-level Project Config: base.yml ← team.yml ← project.

    Args:
        root: repo root (default: detect via repo_root())
        keys: restrict to these keys
        include_sources: if True, return {'config': {...}, 'sources': {...}}
                         else return just the merged config dict
        coerce: when True (opt-in, v7.0.0-alpha), apply
            `project_config.coerce_config_types` so int/float/bool keys
            return native Python types instead of strings. Default False
            preserves byte-identical v6.x behaviour for legacy callers
            (phase_planner, parse_coverage, ...) that do their own cast.

    Returns:
        dict[str, Any] merged config (or wrapper dict if include_sources).
        Raises ConfigError on policy violations (security downgrade).

    Backward compatibility:
        If base.yml and team.yml both absent → result identical to
        read_project_config(root, keys=keys).
    """
    if root is None:
        root = repo_root()

    base = _read_yaml_file(base_config_path(root))
    team = _read_yaml_file(team_config_path())
    project = _read_project_section(root)

    effective, sources = _merge_with_source_tracking(base, team, project)

    if keys is not None:
        effective = {k: v for k, v in effective.items() if k in keys}
        sources = {k: v for k, v in sources.items() if k in keys}

    if coerce:
        effective = coerce_config_types(effective)

    if include_sources:
        return {"config": effective, "sources": sources}
    return effective


def dump_effective_config(
    output_path: Path,
    root: Path | None = None,
) -> None:
    """Write `config-effective.yml` for audit/forensics.

    Format:
        # Effective layered config — generated YYYY-MM-DDTHH:MM:SS
        # Sources: base | team | project
        AppName: "MyApp"               # source: project
        CoverageMin: "80"              # source: team
        SpecComplianceMode: "manual"   # source: base
    """
    from sdd_lib.paths import iso_now

    bundle = read_layered_config(root=root, include_sources=True)
    config = bundle["config"]
    sources = bundle["sources"]

    lines = [
        f"# Effective layered config — generated {iso_now()}",
        "# Source per key: base (.claude/config.base.yml) | team (~/.sdd/config.team.yml) | project (## Project Config in stack.md)",
        "",
    ]
    for key in sorted(config.keys()):
        val = config[key]
        src = sources.get(key, "?")
        # Quote value if it contains spaces or special chars
        if any(c in val for c in (" ", "#", ":")):
            val_str = f'"{val}"'
        else:
            val_str = val
        lines.append(f'{key}: {val_str}   # source: {src}')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
