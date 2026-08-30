"""reverse_smoke.py — Enforcer for INVARIANTS.reverse.yml (ADV-7).

Per design doc §15.1. Runs deterministic checks against the reverse workflow
invariants. NOT plugged into framework_smoke.py (D4 isolation strict) —
the Tech Lead runs this manually OR via CI when the reverse workflow is in
use.

Invocation:
    python -m sdd_reverse_scripts.reverse_smoke [--json]

Exit codes:
    0  all invariants OK (warnings tolerated)
    1  ≥ 1 invariant violated (hard fail)

Output format mirrors framework_smoke.py for visual consistency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.paths import workspace_root

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class CheckResult:
    name: str
    status: str   # OK | WARN | FAIL
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def check_isolation_no_cross_imports() -> CheckResult:
    """sdd_reverse/* MUST NOT import from sdd_lib, sdd_scripts, sdd_admin, sdd_hooks."""
    sdd_reverse = REPO_ROOT / ".sdd" / "python" / "sdd_reverse"
    bad_patterns = [
        re.compile(r"^\s*from\s+sdd_lib\b"),
        re.compile(r"^\s*import\s+sdd_lib\b"),
        re.compile(r"^\s*from\s+sdd_scripts\b"),
        re.compile(r"^\s*import\s+sdd_scripts\b"),
        re.compile(r"^\s*from\s+sdd_admin\b"),
        re.compile(r"^\s*import\s+sdd_admin\b"),
        re.compile(r"^\s*from\s+sdd_hooks\b"),
        re.compile(r"^\s*import\s+sdd_hooks\b"),
    ]
    violations: list[str] = []
    for p in sdd_reverse.rglob("*.py"):
        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            for pat in bad_patterns:
                if pat.match(line):
                    violations.append(f"{p.relative_to(REPO_ROOT)}:{line_no}: {line.strip()}")
    if violations:
        return CheckResult(
            "reverse-isolation-no-cross-imports", "FAIL",
            f"{len(violations)} cross-import(s) detected (D4 violation)",
            {"violations": violations[:10]},
        )
    return CheckResult("reverse-isolation-no-cross-imports", "OK")


def check_loader_autonomous() -> CheckResult:
    """loader.reverse.yml referenced ONLY by reverse commands/skill, NEVER by loader.yml."""
    loader_yml = REPO_ROOT / ".claude" / "loader.yml"
    if loader_yml.is_file():
        try:
            content = loader_yml.read_text(encoding="utf-8")
            if "loader.reverse.yml" in content or "loader.reverse" in content:
                return CheckResult(
                    "reverse-loader-autonomous", "FAIL",
                    "loader.yml references loader.reverse.yml (D4 violation)",
                )
        except OSError:
            pass
    return CheckResult("reverse-loader-autonomous", "OK")


def check_inventory_schema_v1() -> CheckResult:
    """All inventory.json under workspace/old/*/.sys/ SHOULD be schemaVersion==1 with required keys.

    Severity: WARN, NOT FAIL (audit 2026-06-11 MA-8). The class
    [REVERSE_INVENTORY_SCHEMA_STALE] is INFO/WARN in rules/reverse-engineering.md §6
    (a pre-v0.4.0 cache triggers a forced refresh, it is not a hard contract
    breach). The code is the authority — INVARIANTS.reverse.yml is aligned to
    WARN, not the other way around (do not harden an untested runtime path).
    """
    workspace_old = workspace_root(REPO_ROOT) / "old"
    if not workspace_old.is_dir():
        return CheckResult("reverse-inventory-schema-v1", "OK", "(no workspace/old/ found)")
    violations: list[str] = []
    for inv in workspace_old.rglob(".sys/inventory.json"):
        try:
            data = json.loads(inv.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            violations.append(f"{inv.relative_to(REPO_ROOT)}: unparseable")
            continue
        rel = str(inv.relative_to(REPO_ROOT))
        if data.get("schemaVersion") != 1:
            violations.append(f"{rel}: schemaVersion != 1")
        if "_allocatedNames" not in data:
            violations.append(f"{rel}: _allocatedNames missing (ADV-23)")
        if "_featAllocations" not in data:
            violations.append(f"{rel}: _featAllocations missing (ADV-23)")
    if violations:
        return CheckResult(
            "reverse-inventory-schema-v1", "WARN",
            f"{len(violations)} inventory issue(s) — refresh recommended",
            {"violations": violations[:10]},
        )
    return CheckResult("reverse-inventory-schema-v1", "OK")


def check_db_schema_enrichment_separate() -> CheckResult:
    """Verify db-schema.enrichment.json exists separately when audit ran (no merge directly into base)."""
    workspace_old = workspace_root(REPO_ROOT) / "old"
    if not workspace_old.is_dir():
        return CheckResult("reverse-db-schema-enrichment-separate", "OK", "(no workspace/old/ found)")
    issues: list[str] = []
    for tech_audit in workspace_old.rglob(".sys/tech-audit.md"):
        sys_dir = tech_audit.parent
        enrich = sys_dir / "db-schema.enrichment.json"
        base = sys_dir / "db-schema.json"
        if tech_audit.is_file() and not enrich.is_file() and base.is_file():
            # Audit ran but no enrichment.json → could mean nothing to enrich (acceptable)
            # OR auditor wrote to base directly (violation).
            # Best-effort: WARN to flag for review.
            issues.append(f"{tech_audit.parent.relative_to(REPO_ROOT)}: audit ran but no enrichment.json — review")
    if issues:
        return CheckResult(
            "reverse-db-schema-enrichment-separate", "WARN",
            f"{len(issues)} project(s) need review",
            {"projects": issues[:5]},
        )
    return CheckResult("reverse-db-schema-enrichment-separate", "OK")


def check_template_isolated() -> CheckResult:
    """The 3 reverse templates must exist in sdd_reverse/ and not be symlinks.

    Audit 2026-06-11 (B7) : INVARIANTS.reverse.yml étend explicitement ADV-9
    aux templates 3a/3b (`analysis.reverse.template.md`, `us.reverse.template.md`)
    mais ce check ne couvrait que `feat.reverse.template.md` — supprimer un des
    deux autres ne faisait pas FAIL le smoke.
    """
    import sdd_reverse
    base = pathlib.Path(sdd_reverse.__file__).resolve().parent
    names = (
        "feat.reverse.template.md",
        "analysis.reverse.template.md",
        "us.reverse.template.md",
    )
    problems: list[str] = []
    for name in names:
        t = base / name
        if not t.is_file():
            problems.append(f"{name} missing — ADV-9 violation (no fallback inline allowed)")
        elif t.is_symlink():
            problems.append(f"{name} is a symlink — ADV-9 requires a deliberate local copy")
    if problems:
        return CheckResult(
            "reverse-template-isolated", "FAIL",
            "; ".join(problems),
        )
    return CheckResult("reverse-template-isolated", "OK")


def check_no_spawn_of_agents() -> CheckResult:
    """INVARIANT reverse-no-spawn-of-agents (§9 rules/reverse-engineering.md).

    Audit 2026-06-10 : declared in INVARIANTS.reverse.yml with this script as
    enforcer, but the check was absent from `_ALL_CHECKS` (manifest rot).

    Deterministic heuristics :
        - no reverse AGENT prompt may instruct spawning another agent
          (`Agent(reverse-` pattern outside no-spawn statements) ;
        - the orchestrator command must keep its no-spawn statement.
    """
    agents_dir = REPO_ROOT / ".claude" / "agents"
    spawn_re = re.compile(r"Agent\(\s*reverse-", re.IGNORECASE)
    violations: list[str] = []
    for p in sorted(agents_dir.glob("reverse-*.md")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if spawn_re.search(line) and "no-spawn" not in line.lower():
                violations.append(f"{p.name}:{line_no}: {line.strip()[:80]}")
    # Audit 2026-06-11 (B8) : le motif littéral `Agent(reverse-` n'apparaît
    # dans aucune formulation réelle de spawn — check renforcé DÉTERMINISTE :
    # aucun agent reverse ne doit déclarer le tool `Agent`/`Task` dans son
    # frontmatter `tools:` (c'est le seul canal de spawn réel du harness).
    for p in sorted(agents_dir.glob("reverse-*.md")):
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        for line in head.splitlines():
            if line.lower().startswith("tools:"):
                declared = {t.strip().lower() for t in line.split(":", 1)[1].split(",")}
                forbidden = declared & {"agent", "task"}
                if forbidden:
                    violations.append(
                        f"{p.name}: frontmatter tools declares {sorted(forbidden)} (spawn channel)"
                    )
                break
    full_cmd = REPO_ROOT / ".claude" / "commands" / "sdd-reverse-full.md"
    if full_cmd.is_file():
        text = full_cmd.read_text(encoding="utf-8", errors="replace")
        if "no-spawn" not in text.lower() and "ne spawn" not in text.lower():
            violations.append("sdd-reverse-full.md: no-spawn statement missing")
    if violations:
        return CheckResult(
            "reverse-no-spawn-of-agents", "FAIL",
            f"{len(violations)} no-spawn violation(s)",
            {"violations": violations[:10]},
        )
    return CheckResult("reverse-no-spawn-of-agents", "OK")


def check_no_dangling_spawn() -> CheckResult:
    """INVARIANT reverse-no-dead-code (ADR governance-major-reverse-spec-ladder D2).

    Verifies the LIVE wiring of loader.reverse.yml has no dead reference :
      1. every agent named in a command `spawns: [...]` array has a prompt
         `.claude/agents/{name}.md` on disk (no dangling spawn after an agent
         is decommissioned) ;
      2. every reverse-* agent block declared under `agents:` has a `.md` on
         disk ;
      3. every `reverse-*.md` prompt on disk is declared as an `agents:` block
         (no orphan prompt) ;
      4. (audit 2026-08-29, m1) every `sdd_reverse_scripts/*.py` has at least one
         referrer somewhere in `.sdd/` — WARN, not FAIL.

    This is the gate that makes the 3a/3b/3c ladder migration safe : removing
    `reverse-functional-extractor` while a command still spawned it (or its
    prompt lingered) would FAIL here. Prose mentions in docs/rules/CHANGELOG
    are intentionally NOT checked (historical references are legitimate).

    Scope note (audit 2026-08-29, m1) : despite its name this check only ever
    looked at loader<->prompt WIRING — never at Python. Three orphan scripts sat
    in `sdd_reverse_scripts/` with zero referrers anywhere in the repo and it
    stayed green. Part (4) closes that blind spot so the name is honest. It is
    deliberately WARN and not FAIL: a script landed one commit ahead of the
    prompt that will call it is normal in-flight work, not a defect — the signal
    is for the human, the gate stays on the wiring that can actually break a run.

    Part (4) is a reachability scan since the M-1 follow-up (2026-08-30) : the
    referrer set is computed per script, then réduit à point fixe — un orphelin
    référencé uniquement par un autre orphelin est désormais rapporté (cluster
    mort entier), plus seulement sa racine.
    """
    # Audit 2026-08-26 : le manifeste a demenage en `.sdd/` a la migration
    # Phase 2 (foyer neutre). Le chemin `.claude/` etant reste code en dur, ce
    # check rendait WARN "loader absent" depuis — c'est-a-dire qu'il ne
    # verifiait plus rien. On resout `.sdd/` d'abord, `.claude/` en repli.
    loader = REPO_ROOT / ".sdd" / "loader.reverse.yml"
    if not loader.is_file():
        loader = REPO_ROOT / ".claude" / "loader.reverse.yml"
    agents_dir = REPO_ROOT / ".claude" / "agents"
    if not loader.is_file():
        return CheckResult("reverse-no-dead-code", "WARN", "loader.reverse.yml absent")
    text = loader.read_text(encoding="utf-8", errors="replace")

    # Slice the `agents:` section (from `agents:` to the next top-level key like `commands:`)
    agent_block_names: set[str] = set()
    in_agents = False
    for line in text.splitlines():
        if re.match(r"^agents:\s*$", line):
            in_agents = True
            continue
        if in_agents and re.match(r"^\S", line):  # next top-level key ends the section
            in_agents = False
        if in_agents:
            m = re.match(r"^  ([A-Za-z][\w-]*):\s*$", line)
            if m:
                agent_block_names.add(m.group(1))

    # Agents named in any `spawns: [...]` array
    spawned: set[str] = set()
    for arr in re.findall(r"spawns:\s*\[([^\]]*)\]", text):
        for tok in arr.split(","):
            name = tok.strip().strip("'\"")
            if name:
                spawned.add(name)

    on_disk = {p.stem for p in agents_dir.glob("reverse-*.md")}

    violations: list[str] = []
    # (1) dangling spawn → spawned agent missing prompt on disk
    for name in sorted(spawned):
        if not (agents_dir / f"{name}.md").is_file():
            violations.append(f"command spawns '{name}' but .claude/agents/{name}.md is missing (dangling spawn / dead wiring)")
    # (2) loader agent block without prompt on disk
    for name in sorted(agent_block_names):
        if name.startswith("reverse-") and not (agents_dir / f"{name}.md").is_file():
            violations.append(f"loader agents: declares '{name}' but .claude/agents/{name}.md is missing")
    # (3) orphan reverse prompt without loader agent block
    for name in sorted(on_disk):
        if name not in agent_block_names:
            violations.append(f".claude/agents/{name}.md exists but has no agents: block in loader.reverse.yml (orphan prompt)")

    if violations:
        return CheckResult(
            "reverse-no-dead-code", "FAIL",
            f"{len(violations)} dead-wiring / orphan issue(s) (ADR reverse-spec-ladder D2)",
            {"violations": violations[:10]},
        )

    # (4) Python scripts with zero referrers — WARN (see the scope note above).
    orphan_scripts = _unreferenced_reverse_scripts()
    if orphan_scripts:
        return CheckResult(
            "reverse-no-dead-code", "WARN",
            f"wiring OK, but {len(orphan_scripts)} script(s) under "
            f"sdd_reverse_scripts/ have no referrer in .sdd/ "
            f"(dead code, or wiring still to come)",
            {"unreferenced_scripts": orphan_scripts},
        )
    return CheckResult("reverse-no-dead-code", "OK")


#: Referrers are looked for in the manifests, prompts, docs and Python that make
#: up the module — never in `.git`, caches or generated facades.
_REF_SEARCH_GLOBS = ("*.py", "*.md", "*.yml", "*.yaml", "*.json")
_REF_SKIP_PARTS = frozenset({"__pycache__", ".build", ".git", "node_modules"})


def _unreferenced_reverse_scripts() -> list[str]:
    """Names of `sdd_reverse_scripts/*.py` unreachable from any live referrer.

    Fixed-point extension (M-1 follow-up, audit 2026-08-30) : the original scan
    was direct-reference only, so an orphan referenced solely by ANOTHER orphan
    script stayed invisible (e.g. `promote_confidence` cited only by an orphan
    `reverse_report`). We now record, per script, WHICH files mention it, then
    iterate: a script whose remaining referrers are all orphan scripts becomes
    orphan itself, until nothing changes (point fixe).
    """
    scripts_dir = REPO_ROOT / ".sdd" / "python" / "sdd_reverse_scripts"
    if not scripts_dir.is_dir():
        return []
    stems = {
        p.stem for p in scripts_dir.glob("*.py")
        if p.stem != "__init__" and not p.stem.startswith("_")
    }
    if not stems:
        return []
    # Pass 1 — record referrer paths per stem (one filesystem walk).
    referrers: dict[str, set[Path]] = {stem: set() for stem in stems}
    for pattern in _REF_SEARCH_GLOBS:
        for path in (REPO_ROOT / ".sdd").rglob(pattern):
            if any(part in _REF_SKIP_PARTS for part in path.parts):
                continue
            # This very file names scripts in prose; a checker must not be the
            # reason its own subject looks alive.
            if path.resolve() == Path(__file__).resolve():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for stem in stems:
                # A file never counts as its own referrer.
                if path.parent == scripts_dir and path.stem == stem:
                    continue
                if stem in text:
                    referrers[stem].add(path)
    # Pass 2 — fixed point : discard referrers that are themselves orphans.
    orphans: set[str] = set()
    changed = True
    while changed:
        changed = False
        for stem in sorted(stems - orphans):
            live = [
                p for p in referrers[stem]
                if not (p.parent == scripts_dir and p.stem in orphans)
            ]
            if not live:
                orphans.add(stem)
                changed = True
    return sorted(orphans)


def check_helper_parity_drift() -> CheckResult:
    """Compare sdd_lib/atomic_write.py + file_locks.py hashes to snapshots (informational WARN)."""
    snap_path = REPO_ROOT / ".sdd" / "python" / "sdd_reverse" / "_parity_snapshots.json"
    if not snap_path.is_file():
        return CheckResult("helper-parity-drift", "WARN", "_parity_snapshots.json absent")
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return CheckResult("helper-parity-drift", "WARN", f"snapshots unreadable: {e}")
    drifts: list[str] = []
    for rel_path, snap_hash in (snap.get("snapshots") or {}).items():
        target = REPO_ROOT / ".sdd" / "python" / rel_path
        if not target.is_file():
            drifts.append(f"{rel_path}: file missing (was present at snapshot time)")
            continue
        current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if snap_hash and current_hash != snap_hash:
            drifts.append(f"{rel_path}: hash changed (snap={snap_hash[:12]}... current={current_hash[:12]}...)")
    if drifts:
        return CheckResult(
            "helper-parity-drift", "WARN",
            f"{len(drifts)} helper(s) drifted upstream — review local copies",
            {"drifts": drifts},
        )
    return CheckResult("helper-parity-drift", "OK")


# ---------------------------------------------------------------------------
# P1.6 closure — direct checks for invariants previously delegated to
# validate_reverse_feat.py. Smoke now enforces them STANDALONE so a missing
# /sdd-reverse run doesn't silently mask malformed FEATs already committed.
# ---------------------------------------------------------------------------

_REVERSE_FEAT_FRONTMATTER_CONFIDENCE = re.compile(
    r"^---\s*$.*?^confidence:\s*(\S+)\s*$.*?^---\s*$",
    re.MULTILINE | re.DOTALL,
)
_REVERSE_GATE_COMMENT = re.compile(
    r"<!--\s*REVERSE-GATE:\s*confidence=(\w+)\s*(?:;\s*allow-sdd-full=(\w+))?\s*-->",
)
_REVERSE_FEAT_GENERATED_BY = re.compile(
    r"^generated-by:\s*sdd-reverse\b", re.MULTILINE,
)
_VALID_CONFIDENCE = {"high", "medium", "low"}
# Section headings in a FEAT that introduce items requiring an evidence comment
_EVIDENCE_REQUIRED_HEADINGS = (
    "## Functional Needs",
    "## Functional Deliverables",
    "## Business Rules",
    "## Acceptance Criteria",
)
_EVIDENCE_COMMENT_RE = re.compile(r"<!--\s*evidence:\s*[^>]+-->")
_ITEM_ID_RE = re.compile(r"^\s*-?\s*\*?\*?(SFD|FD|BR|AC)-\d+", re.MULTILINE)


def _iter_reverse_feats() -> list[Path]:
    """Return FEAT files under workspace/feats/ that look reverse-generated."""
    feats_dir = workspace_root(REPO_ROOT) / "feats"
    if not feats_dir.is_dir():
        return []
    out: list[Path] = []
    for f in feats_dir.glob("*.md"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _REVERSE_FEAT_GENERATED_BY.search(text):
            out.append(f)
    return out


def check_reverse_evidence_required() -> CheckResult:
    """INVARIANT #3 reverse-evidence-required — every SFD/FD/BR/AC item in a
    reverse FEAT must carry an `<!-- evidence: ... -->` comment nearby.

    Heuristic: for each section heading in `_EVIDENCE_REQUIRED_HEADINGS`,
    count the number of item IDs vs the number of evidence comments in
    the same section. Mismatch → WARN with file pointer.
    """
    feats = _iter_reverse_feats()
    if not feats:
        return CheckResult(
            "reverse-evidence-required", "OK",
            "(no reverse-generated FEATs found)",
        )
    issues: list[str] = []
    for f in feats:
        text = f.read_text(encoding="utf-8", errors="replace")
        # Slice the text by section
        sections: list[tuple[str, str]] = []
        current_heading: str | None = None
        current_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("## "):
                if current_heading is not None:
                    sections.append((current_heading, "\n".join(current_lines)))
                current_heading = line.strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_heading is not None:
            sections.append((current_heading, "\n".join(current_lines)))

        for heading, body in sections:
            if heading not in _EVIDENCE_REQUIRED_HEADINGS:
                continue
            items = _ITEM_ID_RE.findall(body)
            evidence_count = len(_EVIDENCE_COMMENT_RE.findall(body))
            if items and evidence_count < len(items):
                issues.append(
                    f"{f.relative_to(REPO_ROOT)} [{heading}]: "
                    f"{len(items)} items, {evidence_count} evidence comments"
                )
    if issues:
        return CheckResult(
            "reverse-evidence-required", "WARN",
            f"{len(issues)} section(s) missing evidence",
            {"issues": issues[:10]},
        )
    return CheckResult("reverse-evidence-required", "OK")


def check_reverse_confidence_enum_strict() -> CheckResult:
    """INVARIANT #4 reverse-confidence-enum-strict — confidence values in
    frontmatter AND in inline `<!-- confidence: X -->` comments must be one
    of {high, medium, low} (lowercase, no quotes). Any other value = FAIL.
    """
    feats = _iter_reverse_feats()
    if not feats:
        return CheckResult(
            "reverse-confidence-enum-strict", "OK",
            "(no reverse-generated FEATs found)",
        )
    violations: list[str] = []
    inline_re = re.compile(r"<!--\s*confidence:\s*(\S+?)\s*-->")
    for f in feats:
        text = f.read_text(encoding="utf-8", errors="replace")
        # Frontmatter
        m = _REVERSE_FEAT_FRONTMATTER_CONFIDENCE.search(text)
        if m:
            val = m.group(1).strip().strip('"').strip("'").lower()
            if val not in _VALID_CONFIDENCE:
                violations.append(
                    f"{f.relative_to(REPO_ROOT)} frontmatter: confidence={val!r}"
                )
        else:
            violations.append(
                f"{f.relative_to(REPO_ROOT)}: frontmatter.confidence missing"
            )
        # Inline comments
        for inline_m in inline_re.finditer(text):
            val = inline_m.group(1).strip('"').strip("'").lower()
            if val not in _VALID_CONFIDENCE:
                violations.append(
                    f"{f.relative_to(REPO_ROOT)} inline comment: confidence={val!r}"
                )
    if violations:
        return CheckResult(
            "reverse-confidence-enum-strict", "FAIL",
            f"{len(violations)} invalid confidence value(s)",
            {"violations": violations[:10]},
        )
    return CheckResult("reverse-confidence-enum-strict", "OK")


def check_reverse_gate_comment_sync() -> CheckResult:
    """INVARIANT #5 reverse-gate-comment-sync — the
    `<!-- REVERSE-GATE: confidence=X ... -->` comment must match
    `frontmatter.confidence`. Desync = REVERSE_GATE_DRIFT (ADV-22).
    """
    feats = _iter_reverse_feats()
    if not feats:
        return CheckResult(
            "reverse-gate-comment-sync", "OK",
            "(no reverse-generated FEATs found)",
        )
    drifts: list[str] = []
    for f in feats:
        text = f.read_text(encoding="utf-8", errors="replace")
        fm_m = _REVERSE_FEAT_FRONTMATTER_CONFIDENCE.search(text)
        gate_m = _REVERSE_GATE_COMMENT.search(text)
        if fm_m is None or gate_m is None:
            # Missing either → reported by other checks (evidence/enum)
            continue
        fm_val = fm_m.group(1).strip().strip('"').strip("'").lower()
        gate_val = gate_m.group(1).strip().lower()
        if fm_val != gate_val:
            drifts.append(
                f"{f.relative_to(REPO_ROOT)}: frontmatter={fm_val!r} ≠ gate={gate_val!r}"
            )
    if drifts:
        return CheckResult(
            "reverse-gate-comment-sync", "FAIL",
            f"{len(drifts)} FEAT(s) with frontmatter/gate drift (ADV-22)",
            {"drifts": drifts[:10]},
        )
    return CheckResult("reverse-gate-comment-sync", "OK")


def check_validator_parity_drift() -> CheckResult:
    """DRIFT CHECK #1 validator-parity-drift — verify that
    `validate_reverse_feat.py` declares the required `REQUIRED_SECTIONS`
    constants and a `validate_reverse_feat` entry point (sanity guard
    against accidental deletion / refactor that would silently disable
    enforcement of invariants #3-#5).
    """
    validator = REPO_ROOT / ".sdd" / "python" / "sdd_reverse_scripts" / "validate_reverse_feat.py"
    if not validator.is_file():
        return CheckResult(
            "validator-parity-drift", "FAIL",
            "validate_reverse_feat.py missing — invariants #3-#5 lose their direct enforcer",
        )
    src = validator.read_text(encoding="utf-8", errors="replace")
    missing: list[str] = []
    # Sanity markers (presence-only, not semantic equivalence)
    for marker in (
        "REQUIRED_SECTIONS",
        "REQUIRED_FRONTMATTER_KEYS_REVERSE",
        "REVERSE-GATE",
        "evidence",
    ):
        if marker not in src:
            missing.append(marker)
    if missing:
        return CheckResult(
            "validator-parity-drift", "WARN",
            f"validate_reverse_feat.py lacks expected markers: {missing}",
        )
    return CheckResult("validator-parity-drift", "OK")


def check_dialect_queries_readonly() -> CheckResult:
    """Every registered dialect's catalog query constants must be pure reads.

    m4, audit 2026-08-29. `readonly_guard`'s own docstring claimed this check
    lived here; it did not — the only verification was inside the pytest suite,
    so a Tech Lead running the smoke script got an "all invariants OK" that said
    nothing about the module's headline safety property.

    Constructing each `Dialect` re-runs `Dialect.__post_init__`, which validates
    the routine queries, the optional dependency query, the structure queries and
    the catalog-object queries. Every constant is then re-checked here explicitly
    so the count in the message is the real number of guarded statements, not a
    claim about them.
    """
    try:
        from sdd_reverse.dialects import get_dialect, supported_db_types
        from sdd_reverse.readonly_guard import is_readonly
    except Exception as exc:  # pragma: no cover - layout guard
        return CheckResult(
            "reverse-db-readonly-dialect-queries", "FAIL",
            f"dialect registry not importable: {exc}",
        )

    offenders: list[str] = []
    checked = 0
    engines = supported_db_types()
    for eng in engines:
        try:
            d = get_dialect(eng)          # re-runs __post_init__ validation
        except Exception as exc:
            offenders.append(f"{eng}: construction refused ({exc})")
            continue
        named: list[tuple[str, str]] = [
            ("list_routines_sql", d.list_routines_sql),
            ("single_routine_sql", d.single_routine_sql),
        ]
        if d.dependency_query:
            named.append(("dependency_query", d.dependency_query))
        named += [(f"schema_queries[{n}]", q) for n, q in d.schema_queries]
        named += [(f"catalog_object_queries[{n}]", q)
                  for n, q in d.catalog_object_queries]
        for label, sql in named:
            checked += 1
            if not is_readonly(sql):
                offenders.append(f"{eng}.{label}")

    if offenders:
        return CheckResult(
            "reverse-db-readonly-dialect-queries", "FAIL",
            f"non-read-only catalog query constants: {offenders}",
            {"engines": engines, "checked": checked},
        )
    return CheckResult(
        "reverse-db-readonly-dialect-queries", "OK",
        f"{checked} catalog query constant(s) across {len(engines)} engine(s) "
        f"pass readonly_guard.is_readonly",
        {"engines": engines, "checked": checked},
    )


def check_lock_format() -> CheckResult:
    """If .alloc.lock exists, validate its JSON shape (informational)."""
    lock = workspace_root(REPO_ROOT) / "feats" / ".alloc.lock"
    if not lock.is_file():
        return CheckResult("reverse-lock-format-valid", "OK", "(no active lock)")
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CheckResult(
            "reverse-lock-format-valid", "WARN",
            ".alloc.lock present but unparseable (will be overwritten as stale on next acquire)",
        )
    required = {"agent_id", "pid", "ts_unix", "host"}
    missing = required - set(data.keys())
    if missing:
        return CheckResult(
            "reverse-lock-format-valid", "FAIL",
            f".alloc.lock missing required keys: {sorted(missing)}",
        )
    return CheckResult("reverse-lock-format-valid", "OK")


# Smoke check registry — 14 deterministic checks (audit 2026-06-11 MA-8 :
# the doc/manifest historically said "11" but the registry has grown after the
# P1.6 closure added 4 direct-enforcement checks while one was folded in
# elsewhere ; audit 2026-08-29 m4 added the dialect read-only check, which
# `readonly_guard`'s docstring had claimed lived here for months without it
# existing). The authoritative count is `len(_ALL_CHECKS)` ; the anti-rot test
# `tests/test_reverse_smoke_selfcheck.py` pins it and cross-maps every
# INVARIANTS.reverse.yml id to a check here.
_EXPECTED_CHECK_COUNT = 14
_ALL_CHECKS = [
    check_isolation_no_cross_imports,       # reverse-isolation-no-cross-imports
    check_loader_autonomous,                # reverse-loader-autonomous
    check_inventory_schema_v1,              # reverse-inventory-schema-v1 (WARN — see check)
    check_db_schema_enrichment_separate,    # reverse-db-schema-enrichment-separate
    check_template_isolated,                # reverse-template-isolated
    check_no_spawn_of_agents,               # reverse-no-spawn-of-agents
    check_no_dangling_spawn,                # reverse-no-dead-code
    check_helper_parity_drift,              # helper-parity-drift (drift_check)
    check_lock_format,                      # reverse-lock-format-valid
    # P1.6 closure (2026-06-10) — direct enforcement of invariants
    # previously delegated to validate_reverse_feat.py
    check_reverse_evidence_required,        # reverse-evidence-required
    check_reverse_confidence_enum_strict,   # reverse-confidence-enum-strict
    check_reverse_gate_comment_sync,        # reverse-gate-comment-sync
    check_validator_parity_drift,           # validator-parity-drift (drift_check)
    # m4 closure (2026-08-29) — the read-only barrier, verifiable without pytest
    check_dialect_queries_readonly,         # reverse-db-readonly-dialect-queries
]
assert len(_ALL_CHECKS) == _EXPECTED_CHECK_COUNT, (
    f"reverse_smoke registry drift: {len(_ALL_CHECKS)} checks "
    f"!= expected {_EXPECTED_CHECK_COUNT} (update _EXPECTED_CHECK_COUNT "
    "and tests/test_reverse_smoke_selfcheck.py together)"
)


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    parser = argparse.ArgumentParser(
        prog="reverse_smoke",
        description="Enforcer for INVARIANTS.reverse.yml (ADV-7 closure).",
    )
    parser.add_argument("--json", action="store_true", help="Emit report as JSON")
    args = parser.parse_args(argv)

    results = [check() for check in _ALL_CHECKS]
    ok_count = sum(1 for r in results if r.status == "OK")
    warn_count = sum(1 for r in results if r.status == "WARN")
    fail_count = sum(1 for r in results if r.status == "FAIL")

    if args.json:
        print(json.dumps({
            "ok": fail_count == 0,
            "summary": {"OK": ok_count, "WARN": warn_count, "FAIL": fail_count, "total": len(results)},
            "checks": [
                {"name": r.name, "status": r.status, "message": r.message, "details": r.details}
                for r in results
            ],
        }, ensure_ascii=False))
    else:
        print("=== Reverse Engineering Invariants Smoke ===")
        for r in results:
            # ASCII icons (Windows cp1252 console compatibility)
            icon = {"OK": "[OK]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(r.status, "[??]")
            line = f"  {icon} {r.name}"
            if r.message:
                line += f" — {r.message}"
            print(line)
            for k, v in r.details.items():
                if isinstance(v, list):
                    for item in v[:5]:
                        print(f"        • {item}")
        print()
        print(f"Summary: OK={ok_count}  WARN={warn_count}  FAIL={fail_count}  total={len(results)}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
