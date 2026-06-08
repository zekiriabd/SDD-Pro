#!/usr/bin/env python3
"""SDD_Pro complexity router — deterministic Python scoring (v7.0.0+).

Replaces the previous LLM-based `complexity-router` agent (Haiku 4.5) with a
fully deterministic Python script. Same scoring rubric, 0 token LLM cost,
< 50 ms latency vs ~2-5 s for the agent.

Rationale (audit P1 M2, 2026-06-08) : the scoring is mechanical — grep + parse
+ weighted arithmetic over 10 observable signals in the FEAT markdown. Doing
this with an LLM violated SDD_Pro's "thin orchestrator" philosophy
(cf. /sdd-status which delegates to sdd_state.py).

Usage:
    python -m sdd_scripts.complexity_router --feat-number 1
    python -m sdd_scripts.complexity_router --feat-number 1 --json
    python -m sdd_scripts.complexity_router --feat-number 1 --dry-run

Exit codes (sdd_lib.exit_codes) :
    0 SUCCESS       : routing computed + persisted
    1 FAIL_FAST     : FEAT not found / ambiguous / unreadable
    2 CORRECTIBLE   : invalid arg
    3 INFRA_BLOCKED : disk write failure

Outputs:
    workspace/output/.sys/.routing/{n}-complexity.json   (machine-readable)
    workspace/output/.sys/.routing/{n}-complexity.md     (human report, 1 page)

Bypass (force override) :
    SDD_FORCE_PIPELINE=poc|standard|full|critical  → ignore score, use forced value
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402

INFRA_BLOCKED = 3  # local — not in canonical exit_codes set

# ---------------------------------------------------------------------------
# Scoring weights (mirror docs/rubrics/complexity-router-scoring.md §2 — keep in sync)
# ---------------------------------------------------------------------------

WEIGHT_PER_SFD = 5      # cap +25
CAP_SFD = 25
WEIGHT_PER_BR = 3       # cap +15
CAP_BR = 15
WEIGHT_PER_AC = 2       # cap +20
CAP_AC = 20
WEIGHT_PER_ACTOR = 3    # cap +15
CAP_ACTOR = 15
WEIGHT_COMPLIANCE = 20  # if Compliance ≠ "n/a"
WEIGHT_VOLUME_HIGH = 10  # ≥ 10k req/day or 500 concurrent
WEIGHT_PERF_STRICT = 10  # ≤ 300ms p95
WEIGHT_RETENTION_LONG = 5  # ≥ 1 year
WEIGHT_INTEGRATION = 10    # External APIs / SSO
WEIGHT_DEGRADED = 5
WEIGHT_KPI_MATURE = -5     # Quantified Goal with KPI + target + deadline
WEIGHT_CAPABILITIES_MATURE = -3  # Tech Lead pre-declared Capabilities (v7.0.0+ audit P3 J)

# Bornes
COMPLEXITY_BANDS = (
    (0, 25,  "small"),
    (25, 60, "medium"),
    (60, 85, "large"),
    (85, 101, "critical"),
)

# Override keywords (case-insensitive) — force "critical" regardless of score
CRITICAL_OVERRIDE_KEYWORDS = (
    # Compliance regulations
    "gdpr", "rgpd", "hipaa", "pci-dss", "pci dss", "soc2", "soc 2",
    # Sensitive domains
    "paiement", "payment", "stripe", "credit card",
    "authentification", "authentication", "auth ",
    "medical", "santé", "health", "clinical",
    "mineur", "minor ", "enfant", "child", "underage",
    # Production / public-facing flags
    "production-ready", "public-facing", "audience grand public",
)

# Volume threshold for critical override (req/day)
CRITICAL_VOLUME_THRESHOLD = 100_000


# ---------------------------------------------------------------------------
# FEAT parsing helpers (regex, deterministic)
# ---------------------------------------------------------------------------

def _count_pattern(text: str, pattern: str) -> int:
    """Count occurrences of a pattern in text (multiline)."""
    return len(re.findall(pattern, text, re.MULTILINE))


def _has_pattern(text: str, pattern: str, case_insensitive: bool = True) -> bool:
    """True if pattern appears anywhere in text."""
    flags = re.IGNORECASE | re.MULTILINE if case_insensitive else re.MULTILINE
    return re.search(pattern, text, flags) is not None


def _extract_field_value(text: str, field_name: str) -> str:
    """Extract `- Field name: <value>` from a structured section.

    Returns the value stripped, or empty string if not found.
    """
    pattern = rf"^- {re.escape(field_name)}:\s*(.+?)\s*$"
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip()


def _is_non_empty_value(value: str) -> bool:
    """True if value is set (not n/a, not empty, not placeholder)."""
    if not value:
        return False
    v = value.strip().lower()
    if v in ("n/a", "na", "none", "<à préciser>", "à préciser", "tbd", "todo", ""):
        return False
    if v.startswith("<") and v.endswith(">"):
        return False
    return True


def _count_actors(text: str) -> int:
    """Count unique actors listed under ## Actors section.

    Format expected (template):
        ## Actors
        - <actor-1>: <role>
        - <actor-2>: <role>
    """
    match = re.search(
        r"^## Actors\s*\n(.*?)(?=\n##|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    section = match.group(1) if match else ""
    # Count bullet lines that aren't placeholder
    actor_lines = re.findall(r"^- (\S.*?):\s*\S", section, re.MULTILINE)
    return len([a for a in actor_lines if not a.strip().startswith("<")])


def _check_volume_high(volume_str: str) -> tuple[bool, bool]:
    """Returns (is_high_threshold_10k, is_critical_threshold_100k).

    Parses "10k requêtes/jour", "500 utilisateurs concurrents", "100000 req/day", etc.
    """
    if not _is_non_empty_value(volume_str):
        return False, False
    v = volume_str.lower()

    # Numeric extraction — find first number, then check k/m suffix
    num_match = re.search(r"(\d[\d\s,.]*)\s*([kKmM]?)", v)
    if not num_match:
        return False, False
    raw = num_match.group(1).replace(",", "").replace(".", "").replace(" ", "")
    try:
        n = int(raw)
    except ValueError:
        return False, False
    suffix = num_match.group(2).lower()
    if suffix == "k":
        n *= 1_000
    elif suffix == "m":
        n *= 1_000_000

    # Also check explicit "concurrent" wording with the 500 threshold
    is_concurrent = "concurrent" in v or "simultané" in v or "simultaneous" in v
    is_high = (n >= 10_000) or (is_concurrent and n >= 500)
    is_critical = n >= CRITICAL_VOLUME_THRESHOLD
    return is_high, is_critical


def _check_perf_strict(perf_str: str) -> bool:
    """True if Performance SLA threshold is ≤ 300ms p95 or stricter."""
    if not _is_non_empty_value(perf_str):
        return False
    v = perf_str.lower()
    # Look for milliseconds value
    match = re.search(r"<\s*(\d+)\s*m\s*s|p9[59]\s*<?\s*(\d+)\s*m\s*s", v)
    if match:
        threshold = int(match.group(1) or match.group(2))
        return threshold <= 300
    return False


def _check_retention_long(retention_str: str) -> bool:
    """True if data retention ≥ 1 year."""
    if not _is_non_empty_value(retention_str):
        return False
    v = retention_str.lower()
    if any(k in v for k in ("an", "année", "year", "gdpr", "rgpd")):
        return True
    # Try to parse days/months
    days_match = re.search(r"(\d+)\s*jour|(\d+)\s*day", v)
    if days_match:
        days = int(days_match.group(1) or days_match.group(2))
        return days >= 365
    months_match = re.search(r"(\d+)\s*mois|(\d+)\s*month", v)
    if months_match:
        months = int(months_match.group(1) or months_match.group(2))
        return months >= 12
    return False


def _check_kpi_mature(text: str) -> bool:
    """True if Quantified Goal section has Metric + Target + Deadline filled."""
    match = re.search(
        r"^##\s+Quantified Goal.*?(?=\n##|\Z)",
        text,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return False
    section = match.group(0)
    metric = _extract_field_value(section, "Metric")
    target = _extract_field_value(section, "Target")
    deadline = _extract_field_value(section, "Deadline")
    return all(_is_non_empty_value(v) for v in (metric, target, deadline))


def _check_capabilities_declared(text: str) -> tuple[bool, list[str]]:
    """True if FEAT explicitly declares Capabilities (Project Config override).

    Capabilities (e.g. `excel,pdf,cqrs,redis-cache`) signal that the Tech Lead
    has pre-thought the technical surface of the FEAT — a maturity signal.
    Returns (is_set, list_of_capabilities).

    v7.0.0+ audit P3 J (2026-06-08) — fixes complexity_router blind spot :
    a FEAT with explicit Capabilities was scored without recognition of
    this maturity signal, over-routing to critical when standard would suffice.
    """
    # Look for `Capabilities:` in the FEAT body OR in a Project Config section.
    match = re.search(
        r"^\s*Capabilities\s*:\s*(.+?)\s*$",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    if not match:
        return False, []
    raw = match.group(1).strip()
    if not _is_non_empty_value(raw):
        return False, []
    caps = [c.strip() for c in raw.split(",") if c.strip()]
    return bool(caps), caps


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------

def compute_signals(text: str) -> dict:
    """Extract observable signals from FEAT text."""
    sfd_count = _count_pattern(text, r"^- SFD-\d+")
    br_count = _count_pattern(text, r"^- BR-\d+")
    ac_count = _count_pattern(text, r"^- AC-\d+")
    actors_count = _count_actors(text)

    compliance = _extract_field_value(text, "Compliance")
    expected_volume = _extract_field_value(text, "Expected volume")
    performance_sla = _extract_field_value(text, "Performance SLA")
    data_retention = _extract_field_value(text, "Data retention")
    integration = _extract_field_value(text, "Integration")
    degraded_mode = _extract_field_value(text, "Degraded mode")

    volume_high, volume_critical = _check_volume_high(expected_volume)
    capabilities_set, capabilities_list = _check_capabilities_declared(text)

    # Critical override detection
    text_lower = text.lower()
    critical_overrides: list[str] = []
    for kw in CRITICAL_OVERRIDE_KEYWORDS:
        if kw in text_lower:
            critical_overrides.append(kw)
    if volume_critical:
        critical_overrides.append(f"volume>={CRITICAL_VOLUME_THRESHOLD}")

    return {
        "sfd_count":              sfd_count,
        "br_count":               br_count,
        "ac_count":               ac_count,
        "actors_count":           actors_count,
        "compliance":             compliance or "n/a",
        "compliance_set":         _is_non_empty_value(compliance),
        "expected_volume":        expected_volume or "n/a",
        "volume_high":            volume_high,
        "volume_critical":        volume_critical,
        "performance_sla":        performance_sla or "n/a",
        "perf_strict":            _check_perf_strict(performance_sla),
        "data_retention":         data_retention or "n/a",
        "retention_long":         _check_retention_long(data_retention),
        "integration":            integration or "n/a",
        "integration_set":        _is_non_empty_value(integration),
        "degraded_mode":          degraded_mode or "n/a",
        "degraded_set":           _is_non_empty_value(degraded_mode),
        "kpi_mature":             _check_kpi_mature(text),
        "capabilities_set":       capabilities_set,
        "capabilities_list":      capabilities_list,
        "critical_overrides":     critical_overrides,
    }


def compute_score(signals: dict) -> int:
    """Apply weighted scoring formula. Returns int score 0-100 (clamped)."""
    score = 0
    score += min(signals["sfd_count"] * WEIGHT_PER_SFD, CAP_SFD)
    score += min(signals["br_count"] * WEIGHT_PER_BR, CAP_BR)
    score += min(signals["ac_count"] * WEIGHT_PER_AC, CAP_AC)
    score += min(signals["actors_count"] * WEIGHT_PER_ACTOR, CAP_ACTOR)
    if signals["compliance_set"]:
        score += WEIGHT_COMPLIANCE
    if signals["volume_high"]:
        score += WEIGHT_VOLUME_HIGH
    if signals["perf_strict"]:
        score += WEIGHT_PERF_STRICT
    if signals["retention_long"]:
        score += WEIGHT_RETENTION_LONG
    if signals["integration_set"]:
        score += WEIGHT_INTEGRATION
    if signals["degraded_set"]:
        score += WEIGHT_DEGRADED
    if signals["kpi_mature"]:
        score += WEIGHT_KPI_MATURE
    if signals.get("capabilities_set"):
        score += WEIGHT_CAPABILITIES_MATURE  # negative — Tech Lead maturity signal
    return max(0, min(100, score))


def classify_complexity(score: int, signals: dict) -> str:
    """Map score to band, applying critical override if applicable."""
    if signals["critical_overrides"]:
        return "critical"
    for low, high, name in COMPLEXITY_BANDS:
        if low <= score < high:
            return name
    return "critical"  # score == 100 edge case


def recommend_pipeline(complexity: str, feat_n: int) -> dict:
    """Return recommended pipeline command + Project Config overrides."""
    if complexity == "small":
        return {
            "pipeline_command": f"/sdd-poc {feat_n}",
            "extra_commands": [],
            "project_config_overrides": {
                "QAMode": "off",
                "ReviewMode": "off",
            },
            "rationale": "Petite FEAT (peu d'AC, pas de compliance) — pipeline POC minimal pour itérer vite.",
        }
    if complexity == "medium":
        return {
            "pipeline_command": f"/sdd-full {feat_n}",
            "extra_commands": [],
            "project_config_overrides": {
                "QAMode": "full",
                "ReviewMode": "full",
                "ReviewFailOn": "serious",
            },
            "rationale": "FEAT standard — pipeline complet recommandé avec gates qualité par défaut.",
        }
    if complexity == "large":
        return {
            "pipeline_command": f"/sdd-full {feat_n}",
            "extra_commands": [],
            "project_config_overrides": {
                "QAMode": "full",
                "ReviewMode": "full",
                "ArchReviewMode": "full",
                "ReviewFailOn": "serious",
            },
            "rationale": "FEAT large (multi-acteurs ou volume élevé) — activer arch-reviewer pour cohérence architecturale.",
        }
    # critical
    return {
        "pipeline_command": f"/sdd-full {feat_n}",
        "extra_commands": [f"/sdd-review {feat_n} --adversarial"],
        "project_config_overrides": {
            "QAMode": "full",
            "ReviewMode": "full",
            "ArchReviewMode": "full",
            "AdversarialReviewMode": "full",
            "SecurityFailOn": "moderate",
            "ReviewFailOn": "moderate",
        },
        "rationale": "FEAT critique (compliance, security, ou volume massif) — durcir seuils + activer adversarial-reviewer.",
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def find_feat_file(feat_n: int, root: Path) -> Path:
    """Locate `workspace/input/feats/{n}-*.md`. Raises if absent or ambiguous."""
    feats_dir = root / "workspace" / "input" / "feats"
    if not feats_dir.is_dir():
        raise FileNotFoundError(f"workspace/input/feats/ not found at {feats_dir}")
    matches = sorted(feats_dir.glob(f"{feat_n}-*.md"))
    if not matches:
        raise FileNotFoundError(f"no FEAT file matching {feat_n}-*.md in {feats_dir}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous FEAT — {len(matches)} files match {feat_n}-*.md")
    return matches[0]


def render_markdown(report: dict) -> str:
    """Render the 1-page human report (workspace/output/.sys/.routing/{n}-complexity.md)."""
    n = report["feat_number"]
    name = report["feat_name"]
    score = report["score"]
    complexity = report["complexity"]
    signals = report["signals"]
    rec = report["recommended"]

    lines = [
        f"# Complexity routing — FEAT {n}-{name}",
        "",
        f"**Verdict** : `{complexity}` ({score}/100)",
        "",
        "## Signaux détectés",
        "",
        "| Signal | Valeur |",
        "|---|---|",
        f"| SFD count | {signals['sfd_count']} |",
        f"| BR count | {signals['br_count']} |",
        f"| AC count | {signals['ac_count']} |",
        f"| Acteurs | {signals['actors_count']} |",
        f"| Compliance | {signals['compliance']} |",
        f"| Volume attendu | {signals['expected_volume']} |",
        f"| SLA performance | {signals['performance_sla']} |",
        f"| Data retention | {signals['data_retention']} |",
        f"| Integration externe | {signals['integration']} |",
        f"| Degraded mode | {signals['degraded_mode']} |",
        f"| KPI maturité | {'✓' if signals['kpi_mature'] else '—'} |",
        f"| Overrides critiques | {', '.join(signals['critical_overrides']) or '—'} |",
        "",
        "## Recommandation",
        "",
        f"→ `{rec['pipeline_command']}`",
    ]
    if rec["extra_commands"]:
        for cmd in rec["extra_commands"]:
            lines.append(f"→ `{cmd}`")
    lines.extend([
        "",
        "## Project Config suggérés",
        "",
        "```yaml",
    ])
    for k, v in rec["project_config_overrides"].items():
        lines.append(f"{k}: {v}")
    lines.extend([
        "```",
        "",
        "## Rationale",
        "",
        rec["rationale"],
        "",
        f"_Generated by_ `complexity_router.py` _at_ {report['extracted_at']}_ (deterministic, 0 token LLM)._",
    ])
    return "\n".join(lines) + "\n"


def write_outputs(report: dict, root: Path, dry_run: bool) -> tuple[Path, Path]:
    """Persist JSON + Markdown to workspace/output/.sys/.routing/."""
    out_dir = root / "workspace" / "output" / ".sys" / ".routing"
    out_dir.mkdir(parents=True, exist_ok=True)
    n = report["feat_number"]
    json_path = out_dir / f"{n}-complexity.json"
    md_path = out_dir / f"{n}-complexity.md"
    if dry_run:
        return json_path, md_path
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="complexity_router",
        description="Deterministic FEAT complexity routing (replaces LLM agent v7.0.0+).",
    )
    p.add_argument("--feat-number", "-n", type=int, required=True,
                   help="FEAT number (e.g. 1 for workspace/input/feats/1-*.md)")
    p.add_argument("--json", action="store_true",
                   help="Emit full JSON to stdout (default: 1-line summary)")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute but do not persist to disk")
    return p.parse_args()


def _repo_root() -> Path:
    """Find repo root by walking up from CWD looking for .claude/."""
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root and Path(env_root).is_dir():
        return Path(env_root)
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / ".claude").is_dir():
            return p
    return cwd


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    try:
        args = parse_args()
    except SystemExit:
        return CORRECTIBLE

    root = _repo_root()

    try:
        feat_path = find_feat_file(args.feat_number, root)
    except (FileNotFoundError, ValueError) as exc:
        msg = str(exc)
        cls = "[FEAT_AMBIGUOUS]" if "ambiguous" in msg.lower() else "[FEAT_NOT_FOUND]"
        print(f"ERROR: complexity_router — {msg}", file=sys.stderr)
        print(f"CAUSE: {cls} no unique FEAT for number {args.feat_number}", file=sys.stderr)
        print(f"FIX: vérifier workspace/input/feats/{args.feat_number}-*.md", file=sys.stderr)
        return FAIL_FAST

    try:
        text = feat_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: complexity_router — cannot read {feat_path}: {exc}", file=sys.stderr)
        return FAIL_FAST

    feat_name = feat_path.stem.split("-", 1)[1] if "-" in feat_path.stem else feat_path.stem

    signals = compute_signals(text)
    score = compute_score(signals)
    complexity = classify_complexity(score, signals)

    # Honor force override env var (debug / CI)
    force_pipeline = os.environ.get("SDD_FORCE_PIPELINE", "").strip().lower()
    if force_pipeline in ("poc", "small"):
        complexity = "small"
    elif force_pipeline in ("standard", "medium"):
        complexity = "medium"
    elif force_pipeline in ("full", "large"):
        complexity = "large"
    elif force_pipeline in ("critical",):
        complexity = "critical"

    rec = recommend_pipeline(complexity, args.feat_number)

    report = {
        "feat_number":  args.feat_number,
        "feat_name":    feat_name,
        "feat_path":    str(feat_path.relative_to(root).as_posix()),
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "score":        score,
        "complexity":   complexity,
        "signals":      signals,
        "recommended":  rec,
        "generator":    "complexity_router.py (deterministic, 0 LLM tokens)",
    }

    try:
        json_path, md_path = write_outputs(report, root, args.dry_run)
    except OSError as exc:
        print(f"ERROR: complexity_router — cannot write outputs: {exc}", file=sys.stderr)
        print(f"CAUSE: [INFRA_BLOCKED] disk write error", file=sys.stderr)
        return INFRA_BLOCKED

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
    else:
        suffix = ""
        if args.dry_run:
            suffix = " (dry-run — not persisted)"
        print(
            f"[ROUTER] FEAT {args.feat_number} {complexity} "
            f"(score {score}/100) → {rec['pipeline_command']}{suffix}"
        )

    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
