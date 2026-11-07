#!/usr/bin/env python3
"""SDD_Pro hook PreToolUse(Agent) — séquencement des phases par FEAT.

Lot « orchestration mécanique » (2026-11-07). L'ordre des phases de
`/sdd-full` et `/dev-run` n'était garanti que par la lecture d'un Markdown
par le LLM. Ce hook refuse (exit 2, `[PHASE_ORDER_VIOLATION]` + action
attendue) de spawner un agent SDD hors séquence pour la FEAT N extraite du
prompt, d'après `run_phases` (console.db) du run courant de la FEAT :

    agent                              prérequis (run_phases du run courant)
    ---------------------------------  -----------------------------------------
    dev-backend, dev-frontend          readiness ∈ {pass, warn, skip}
                                       (skip = --no-validate, décision tracée)
    qa                                 dev_run ∈ {running, pass, warn}
                                       (running : l'API gate tourne DANS /dev-run)
                                       ou, marqueur TEST-FIRST, readiness ∈ {pass, warn}
    spec-compliance-reviewer           dev_run ∈ {pass, warn}
    code-reviewer, security-reviewer,  qa ∈ {pass, warn, skip}
    arch-reviewer, adversarial-reviewer (skip = QAMode off/manual, tracé)

Run courant = le plus récent `runs.status='running'` de la FEAT, sinon le plus
récent tout court (`$SDD_RUN_ID` gagne s'il est visible du hook).

Preuves d'exécution (gate de livraison, 2026-11-07 — `docs/delivery-gates.md`).
Le statut déclaré de la phase amont est une condition NÉCESSAIRE, jamais
suffisante :
  - payload amont `buildVerified: false` / `executed: false` (déclaration
    d'échec de l'orchestrateur) → DENY `[DELIVERY_EVIDENCE_MISSING]` même si
    le statut est `warn` ;
  - `qa` post-dev (dev_run pass/warn), `spec-compliance-reviewer` et les
    reviewers Stage B exigent une preuve BUILD valide pour l'arbre courant
    (`authorize_delivery(workflow=dev-run)`, table `delivery_evidence` écrite
    par `verify_build.py` seulement) ;
  - les reviewers Stage B exigent en plus la preuve TESTS quand `qa` est
    déclarée pass/warn (une QA honnêtement `skip` n'est pas « prouvée » ici :
    le gate de sortie /sdd-full la refusera) ;
  - `qa` de l'API gate (dev_run `running`, DANS /dev-run) : inchangé ;
  - /sdd-poc (pas de QA ni de reviewers) : inchangé.
Ces refus de preuve n'ont AUCUN bypass (`SDD_ALLOW_PHASE_SKIP` ne s'y applique pas).

QA test-first (TDD RED, 2026-11-07). `enforce_tdd` (strict pour les sous-agents)
exige un test compagnon AVANT le code de production de dev-* ; seul `qa` écrit
des tests ; or `qa` exigeait dev_run → interblocage. Règle exacte :
    qa est ALLOW en mode TEST-FIRST  ⇔  prompt/description contient le marqueur
    explicite `test-first` | `test first` | `--test-first` | `TDD RED`
    ET dev_run ∉ {running, pass, warn} (absente, fail…)
    ET readiness ∈ {pass, warn}   (skip/--no-validate NE suffit PAS).
Sinon (readiness absente/fail) → DENY `[PHASE_ORDER_VIOLATION]`. Dès que dev_run
est running/pass/warn, le marqueur est IGNORÉ : `qa` suit la règle nominale
(API gate pendant running ; preuve BUILD exigée après pass/warn) — un prompt
« test-first » ne contourne donc jamais le gate de livraison. Le spawn test-first
n'enregistre aucune phase et ne constitue aucune preuve (`[PHASE_ORDER_TEST_FIRST]`
en WARN).

Extraction FEAT/US (2026-11-07) : motif US et validation disque partagés avec
`record_token_usage` (`sdd_lib/feat_us_ids.py`) — dates (`2026-10-10`) et plages
de lignes (`84-92`) ne sont plus prises pour des US ; un candidat absent de
`workspace/us` / `workspace/feats` est ignoré.

Autres règles :
  - agent hors registre SDD (`general-purpose`, `Explore`…) ou agent SDD sans
    prérequis (`po`, `arch`, `elicitor`, reverse-*) : ALLOW ;
  - agent soumis à prérequis dont la FEAT n'est pas extractible du prompt :
    DENY explicite (plus de « FEAT inconnue → allow ») ;
  - console.db illisible : DENY `[INFRA_BLOCKED]` (une base absente = aucun
    run enregistré → `[PHASE_ORDER_VIOLATION]`) ;
  - FEAT en mode POC (toutes ses US portent `generated-by: feat_to_pseudo_us.py`,
    `/sdd-poc` assume l'absence de readiness) : ALLOW dev-* avec WARN ;
  - mode plan (`:plan` / « mode plan » dans le prompt de dev-*, `/dev-plan`
    standalone) : un rapport `{n}-readiness.md` GO/WARN sur disque suffit.

Bypass : `SDD_ALLOW_PHASE_SKIP=1` — une ligne dans
`workspace/.sys/.audit/bypass.log`.

Sur refus, le créneau éventuellement réservé par `enforce_max_parallel` pour
ce `tool_use_id` est libéré (`note_denied`).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.feat_us_ids import iter_us_candidates, known_ids  # noqa: E402
from sdd_lib.hook_input import get_nested, read_hook_input  # noqa: E402
from sdd_lib.paths import console_db_path, repo_root, workspace_root  # noqa: E402
from sdd_hooks.enforce_max_parallel import (  # noqa: E402
    agent_type_of,
    audit_bypass,
    note_denied,
    sdd_agent_registry,
)

BYPASS_ENV = "SDD_ALLOW_PHASE_SKIP"

#: agent → (phase requise, statuts acceptés, action attendue si absente)
REQUIREMENTS: dict[str, tuple[str, frozenset[str], str]] = {
    "dev-backend": ("readiness", frozenset({"pass", "warn", "skip"}),
                    "/feat-validate {n} (ou /sdd-full {n}) — readiness GO/WARN enregistrée"),
    "dev-frontend": ("readiness", frozenset({"pass", "warn", "skip"}),
                     "/feat-validate {n} (ou /sdd-full {n}) — readiness GO/WARN enregistrée"),
    "qa": ("dev_run", frozenset({"running", "pass", "warn"}),
           "/dev-run {n} d'abord (phase dev_run)"),
    "spec-compliance-reviewer": ("dev_run", frozenset({"pass", "warn"}),
                                 "terminer /dev-run {n} (phase dev_run pass/warn)"),
    "code-reviewer": ("qa", frozenset({"pass", "warn", "skip"}),
                      "/qa-generate {n} d'abord (phase qa)"),
    "security-reviewer": ("qa", frozenset({"pass", "warn", "skip"}),
                          "/qa-generate {n} d'abord (phase qa)"),
    "arch-reviewer": ("qa", frozenset({"pass", "warn", "skip"}),
                      "/qa-generate {n} d'abord (phase qa)"),
    "adversarial-reviewer": ("qa", frozenset({"pass", "warn", "skip"}),
                             "/qa-generate {n} d'abord (phase qa)"),
}

#: FEAT explicite. `(?![\-./:]\d)` : `FEAT 2026-10-10` / `feat-11.6` ne sont pas
#: des FEAT (dates, versions) — même défense que `sdd_lib/feat_us_ids.US_RE`.
_FEAT_PATTERNS = (
    r"\bFEAT[\s:#-]*(\d{1,4})\b(?![\-./:]\d)",
    r"\bfeat[-_](\d{1,4})\b(?![\-./:]\d)",
    r"--feat(?:-number)?[\s=]+(\d{1,4})\b",
    r"args\s*=\s*[\"'](\d{1,4})",
    r"/(?:sdd-full|dev-run|dev-plan|qa-generate|sdd-review|feat-validate|us-generate)\s+(\d{1,4})\b",
)
_PLAN_MODE_RE = re.compile(r"(:plan\b|mode\s+plan\b|plan[- ]only|--plan-only)", re.IGNORECASE)
#: Marqueur explicite du mode TEST-FIRST de `qa` (cf. docstring « QA test-first »).
_TEST_FIRST_RE = re.compile(
    r"(--test-first\b|\btest[- ]first\b|\bTDD[\s:/-]*RED\b)", re.IGNORECASE)
_TEST_FIRST_READINESS = frozenset({"pass", "warn"})
_POC_MARKER = "generated-by: feat_to_pseudo_us.py"


class DbUnreadable(RuntimeError):
    pass


#: Agents dont le spawn exige une preuve build (et éventuellement tests).
_BUILD_EVIDENCE_AGENTS = frozenset({
    "qa", "spec-compliance-reviewer", "code-reviewer", "security-reviewer",
    "arch-reviewer", "adversarial-reviewer",
})
_TESTS_EVIDENCE_AGENTS = frozenset({
    "code-reviewer", "security-reviewer", "arch-reviewer", "adversarial-reviewer",
})
#: Clés de payload par lesquelles l'orchestrateur DÉCLARE un échec d'exécution.
_NEGATIVE_CLAIMS = ("buildVerified", "build_verified", "executed", "testsExecuted")


def _declared_failure(payload: dict[str, Any]) -> str | None:
    """Clé de payload déclarant une non-exécution (`False`), y compris imbriquée 1 niveau."""
    for scope in (payload, *(v for v in payload.values() if isinstance(v, dict))):
        for key in _NEGATIVE_CLAIMS:
            if key in scope and scope[key] is False:
                return key
    return None


def evidence_denial(agent: str, feat_n: int, run_id: str | None,
                    phases: dict[str, tuple[str, dict[str, Any]]],
                    root: Path) -> str | None:
    """Message de refus si la preuve d'exécution manque, sinon None.

    Le statut déclaré n'est jamais suffisant : seule `authorize_delivery`
    (preuves `delivery_evidence`) peut lever ce contrôle.
    """
    if agent not in _BUILD_EVIDENCE_AGENTS:
        return None
    dev_status, dev_payload = phases.get("dev_run", ("", {}))
    qa_status, qa_payload = phases.get("qa", ("", {}))
    if agent == "qa" and dev_status == "running":
        return None  # API gate DANS /dev-run : le build complet n'existe pas encore
    claim = _declared_failure(dev_payload) or (
        _declared_failure(qa_payload) if agent in _TESTS_EVIDENCE_AGENTS else None)
    if claim:
        return (f"ERROR: [DELIVERY_EVIDENCE_MISSING] spawn de '{agent}' refusé pour FEAT {feat_n} — "
                f"phase amont déclarée avec {claim}=false (statut {dev_status or qa_status})\n"
                f"CAUSE: un WARN avec build/tests non exécutés ne satisfait aucun prérequis.\n"
                f"FIX: python .sdd/python/sdd_scripts/verify_build.py --feat-number {feat_n}"
                f"{' --run-id ' + run_id if run_id else ''} (puis verify_tests.py si requis) ; "
                f"aucun bypass.\n")
    from sdd_lib.delivery_wiring import authorize, family_state
    decision = authorize(feat_n=feat_n, workflow="dev-run", run_id=run_id, root=root)
    families = ["build"]
    if agent in _TESTS_EVIDENCE_AGENTS and qa_status in ("pass", "warn"):
        families.append("tests")
    if "tests" in families:
        tests_decision = authorize(feat_n=feat_n, workflow="sdd-full", run_id=run_id, root=root)
    for family in families:
        d = tests_decision if family == "tests" else decision
        state = family_state(d, family)
        if state in ("ok", "not_required"):
            continue
        script = "verify_build.py" if family == "build" else "verify_tests.py"
        return (f"ERROR: [DELIVERY_EVIDENCE_MISSING] spawn de '{agent}' refusé pour FEAT {feat_n} — "
                f"preuve {family} {state} pour l'arbre courant (statut déclaré non probant)\n"
                f"CAUSE: {d.summary()}\n"
                f"FIX: python .sdd/python/sdd_scripts/{script} --feat-number {feat_n}"
                f"{' --run-id ' + run_id if run_id else ''} ; aucun bypass.\n")
    return None


def _prompt_text(payload: dict[str, Any]) -> str:
    return " ".join(str(get_nested(payload, "tool_input", k) or "")
                    for k in ("prompt", "description"))


def extract_feat(payload: dict[str, Any], root: Path | None = None) -> int | None:
    """FEAT N depuis prompt + description (FEAT explicite > US `{n}-{m}`).

    `root` fourni : chaque candidat est confronté aux FEAT/US présentes sur
    disque (`sdd_lib.feat_us_ids.known_ids`) — une date (`2026-10-10`) ou une
    plage de lignes (`84-92`) n'est jamais prise pour une US, et un candidat
    inconnu est ignoré au profit du suivant. Workspace sans FEAT ni US →
    contrat syntaxique seul.
    """
    text = _prompt_text(payload)
    if not text.strip():
        return None
    known = known_ids(root) if root is not None else None
    known_feats = known[1] if known else set()
    for pat in _FEAT_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            n = int(m.group(1))
            if not known_feats or n in known_feats:
                return n
    for n, _us_id in iter_us_candidates(text, known):
        return n
    return None


def is_test_first_qa(payload: dict[str, Any]) -> bool:
    """Prompt de `qa` portant le marqueur explicite TEST-FIRST / TDD RED."""
    return agent_type_of(payload) == "qa" and bool(_TEST_FIRST_RE.search(_prompt_text(payload)))


def _current_run_phases(db: Path, feat_n: int) -> tuple[str | None, dict[str, str]]:
    """(run_id, {phase: status}) du run courant de la FEAT."""
    run_id, detailed = _current_run_phases_detailed(db, feat_n)
    return run_id, {k: v[0] for k, v in detailed.items()}


def _current_run_phases_detailed(
        db: Path, feat_n: int) -> tuple[str | None, dict[str, tuple[str, dict[str, Any]]]]:
    """(run_id, {phase: (status, payload)}) du run courant de la FEAT."""
    if not db.is_file():
        return None, {}
    try:
        conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        raise DbUnreadable(str(exc)) from exc
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        run_id = (os.environ.get("SDD_RUN_ID") or "").strip() or None
        if run_id:
            row = conn.execute("SELECT run_id FROM runs WHERE run_id = ? AND feat_n = ?",
                               (run_id, feat_n)).fetchone()
            run_id = row[0] if row else None
        if not run_id:
            row = conn.execute(
                "SELECT run_id FROM runs WHERE feat_n = ? "
                "ORDER BY (status = 'running') DESC, started_at DESC LIMIT 1",
                (feat_n,),
            ).fetchone()
            run_id = row[0] if row else None
        if not run_id:
            return None, {}
        phases: dict[str, tuple[str, dict[str, Any]]] = {}
        for r in conn.execute(
                "SELECT phase, status, payload_json FROM run_phases WHERE run_id = ?",
                (run_id,)):
            try:
                payload = json.loads(r[2]) if r[2] else {}
            except ValueError:
                payload = {}
            phases[r[0]] = ((r[1] or "").lower(), payload if isinstance(payload, dict) else {})
        return run_id, phases
    except sqlite3.Error as exc:
        raise DbUnreadable(str(exc)) from exc
    finally:
        conn.close()


def _is_poc_feat(root: Path, feat_n: int) -> bool:
    us_dir = workspace_root(root) / "us"
    files = sorted(us_dir.glob(f"{feat_n}-*.md")) if us_dir.is_dir() else []
    if not files:
        return False
    try:
        return all(_POC_MARKER in f.read_text(encoding="utf-8", errors="replace")[:2048]
                   for f in files)
    except OSError:
        return False


def _disk_readiness_ok(root: Path, feat_n: int) -> bool:
    report = workspace_root(root) / ".sys" / ".validation" / f"{feat_n}-readiness.md"
    try:
        text = report.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    m = re.search(r"[Dd][ée]cision[^:\n]*:\s*\**\s*(?:🟢|🟡|🔴)?\s*(GO|WARN|NO-GO)\b", text)
    return bool(m) and m.group(1).upper() in ("GO", "WARN")


def evaluate(payload: dict[str, Any], root: Path) -> tuple[int, str]:
    """Décision pure (exit code, message stderr)."""
    if payload.get("tool_name") not in ("Agent", "Task"):
        return HOOK_ALLOW, ""
    agent = agent_type_of(payload)
    if not agent or agent not in sdd_agent_registry(root):
        return HOOK_ALLOW, ""
    req = REQUIREMENTS.get(agent)
    if req is None:
        return HOOK_ALLOW, ""
    phase, accepted, expected = req

    def deny(msg: str) -> tuple[int, str]:
        if os.environ.get(BYPASS_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
            audit_bypass(root, f"{BYPASS_ENV}=1 agent={agent} rule={phase} "
                               f"session={payload.get('session_id')} :: {msg.splitlines()[0]}")
            return HOOK_ALLOW, f"WARN [PHASE_ORDER_BYPASSED] {msg.splitlines()[0]} (audit-loggué)\n"
        note_denied(root, payload.get("tool_use_id"))
        return HOOK_DENY, msg

    feat_n = extract_feat(payload, root)
    if feat_n is None:
        return deny(
            f"ERROR: [PHASE_ORDER_VIOLATION] '{agent}' spawné sans FEAT identifiable dans le prompt\n"
            f"CAUSE: le séquencement des phases est vérifié par FEAT ; un agent soumis à "
            f"prérequis ({phase}) ne peut pas être autorisé à l'aveugle.\n"
            f"FIX: inclure « FEAT {{n}} » ou l'US « {{n}}-{{m}} » dans le prompt de l'agent "
            f"(convention des commandes SDD) ; bypass audit-loggué {BYPASS_ENV}=1.\n"
        )

    if agent in ("dev-backend", "dev-frontend") and _is_poc_feat(root, feat_n):
        return HOOK_ALLOW, (f"WARN [PHASE_ORDER_POC] FEAT {feat_n} en mode POC (pseudo-US) — "
                            f"readiness non exigée pour '{agent}'.\n")

    try:
        run_id, detailed = _current_run_phases_detailed(console_db_path(root), feat_n)
        phases = {k: v[0] for k, v in detailed.items()}
    except DbUnreadable as exc:
        return deny(
            f"ERROR: [INFRA_BLOCKED] console.db illisible — séquencement de '{agent}' "
            f"(FEAT {feat_n}) invérifiable : {exc}\n"
            f"FIX: vérifier workspace/db/console.db (verrou, droits, corruption) puis relancer.\n"
        )

    status = phases.get(phase)
    # QA TEST-FIRST (TDD RED) : fenêtre ouverte uniquement AVANT toute livraison
    # dev_run (statut absent / fail…, hors running qui reste l'API gate). Une
    # fois dev_run pass/warn, le marqueur est ignoré → QA de livraison + preuves.
    if (agent == "qa" and status not in accepted and is_test_first_qa(payload)):
        readiness = phases.get("readiness")
        if readiness in _TEST_FIRST_READINESS:
            return HOOK_ALLOW, (
                f"WARN [PHASE_ORDER_TEST_FIRST] FEAT {feat_n} — 'qa' autorisé en mode "
                f"TEST-FIRST (readiness {readiness}, dev_run {status or 'absente'}) : tests RED "
                f"uniquement, ne vaut ni phase qa ni preuve de livraison.\n")
        seen_r = readiness if readiness else ("absente" if run_id else "aucun run enregistré")
        return deny(
            f"ERROR: [PHASE_ORDER_VIOLATION] spawn de 'qa' (TEST-FIRST) refusé pour FEAT {feat_n} — "
            f"readiness : {seen_r} (attendu : {', '.join(sorted(_TEST_FIRST_READINESS))})\n"
            f"CAUSE: le mode test-first écrit les tests RED depuis les US ; il exige une "
            f"readiness GO/WARN enregistrée (console.db run_phases, run {run_id or '—'}).\n"
            f"FIX: /feat-validate {feat_n} (ou /sdd-full {feat_n}) ; bypass audit-loggué "
            f"{BYPASS_ENV}=1.\n"
        )

    if status in accepted:
        # Statut déclaré = condition nécessaire ; la preuve d'exécution est
        # exigée en plus (aucun bypass — SDD_ALLOW_PHASE_SKIP ne s'applique pas).
        denial = evidence_denial(agent, feat_n, run_id, detailed, root)
        if denial:
            note_denied(root, payload.get("tool_use_id"))
            return HOOK_DENY, denial
        return HOOK_ALLOW, ""

    if (agent in ("dev-backend", "dev-frontend")
            and _PLAN_MODE_RE.search(str(get_nested(payload, "tool_input", "prompt") or ""))
            and _disk_readiness_ok(root, feat_n)):
        return HOOK_ALLOW, ""

    seen = status if status else ("absente" if run_id else "aucun run enregistré")
    return deny(
        f"ERROR: [PHASE_ORDER_VIOLATION] spawn de '{agent}' refusé pour FEAT {feat_n} — "
        f"phase prérequise '{phase}' : {seen} (attendu : {', '.join(sorted(accepted))})\n"
        f"CAUSE: ordre des phases SDD (readiness → dev_run → qa → reviewers), lu dans "
        f"console.db run_phases (run {run_id or '—'}).\n"
        f"FIX: {expected.format(n=feat_n)} ; l'action exacte est donnée par "
        f"`python .sdd/python/sdd_scripts/sdd_full_planner.py next-action --feat {feat_n}`. "
        f"Bypass audit-loggué : {BYPASS_ENV}=1.\n"
    )


def main() -> int:
    try:
        payload = read_hook_input()
    except (OSError, ValueError, UnicodeError) as exc:
        sys.stderr.write(f"ERROR: [PHASE_ORDER_PAYLOAD_INVALID] {type(exc).__name__}: {exc}\n")
        return HOOK_DENY
    code, msg = evaluate(payload, repo_root())
    if msg:
        sys.stderr.write(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
