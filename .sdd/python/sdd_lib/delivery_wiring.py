"""SDD_Pro — câblage des points de sortie sur le gate de livraison (2026-11-07).

Le gate lui-même (`sdd_lib.delivery_gate.authorize_delivery`) ne lit QUE la
table `delivery_evidence` (preuves authentifiées, écrites exclusivement par
`verify_build.py` / `verify_tests.py` / `delivery_gate.py record-*`). Ce module
est la colle entre ce gate et les points où une livraison est déclarée :

  - `sdd_full_planner` (étapes verify_* planifiées + sortie `done`) ;
  - clôture de run (`run_close.py`, `sdd_state.py end-run`, `set-phase
    sdd_review`) : tout `completed` / `success` / `partial` d'un run dont la
    commande porte un workflow de livraison est soumis au gate ; refus →
    `failed` + verdict RED + `[DELIVERY_GATE_BLOCKED]` ;
  - `dev_run_args.py --end pass|warn` ;
  - verdict final de `sdd_review.py` (GREEN/YELLOW → workflow `sdd-review`) ;
  - run `/sdd-poc` ouvert par `feat_to_pseudo_us.py --open-run` (clôture ci-dessus) ;
  - hook `enforce_phase_order` (preuve build pour qa / reviewers).

Invariants (SSoT `.sdd/docs/delivery-gates.md`) :
  - la décision de livraison = UNIQUEMENT `authorize_delivery` (preuves). Les
    statuts / payloads de `run_phases` (`pass`, `warn`, `buildVerified`,
    `executed`, `coverage`…) ne peuvent jamais AUTORISER, au plus refuser ;
  - aucun bypass (`--force`, WARN, `--resume`, variable d'environnement) n'est
    lu ici : il n'existe aucun paramètre pour lever le gate ;
  - ce module n'écrit JAMAIS dans `delivery_evidence` ;
  - import paresseux du module central ; module absent ou en erreur → refus
    (fail-closed), jamais une autorisation par défaut.
"""
from __future__ import annotations

import importlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

BLOCKED_CLASS = "[DELIVERY_GATE_BLOCKED]"

#: Statuts de clôture de run qui valent « livraison déclarée ».
SUCCESS_CLOSE_STATUSES = frozenset({"completed", "success", "partial"})

#: `runs.command` → clé `WORKFLOW_REQUIREMENTS` du module central.
COMMAND_TO_WORKFLOW: dict[str, str] = {
    f"{prefix}{wf}": wf
    for wf in ("sdd-full", "sdd-poc", "dev-run", "sdd-deploy", "qa-generate", "sdd-review")
    for prefix in ("/", "")
}

#: Familles de preuves reconnues (noms de checks du module central normalisés).
CHECK_FAMILIES: tuple[str, ...] = ("build", "tests", "coverage", "spec", "readiness")


@dataclass
class WiredDecision:
    """Vue normalisée d'un `GateDecision` (tolère dict / objet / module absent)."""

    allowed: bool
    workflow: str
    required: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    available: bool = True

    def summary(self) -> str:
        parts = []
        for label, items in (("manquant", self.missing), ("échec", self.failed),
                             ("périmé", self.stale)):
            if items:
                parts.append(f"{label}: {', '.join(items)}")
        if not parts and self.reasons:
            parts.append("; ".join(self.reasons[:2]))
        return " | ".join(parts) or "preuve de livraison absente"

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "workflow": self.workflow,
                "required": self.required, "missing": self.missing,
                "failed": self.failed, "stale": self.stale,
                "reasons": self.reasons, "available": self.available}


def family_of(check: str) -> str | None:
    """Nom de check du module central → famille (`build`, `tests`, …)."""
    c = (check or "").lower()
    if "build" in c:
        return "build"
    if "cover" in c:
        return "coverage"
    if "test" in c:
        return "tests"
    if "spec" in c:
        return "spec"
    if "readiness" in c or "ready" in c:
        return "readiness"
    return None


def normalize_command(command: str | None) -> str:
    """Nom canonique d'une commande slash (`sdd-full`, `dev-run`…).

    Audit gates (2026-11-07) : sous Git Bash (MSYS), un argument `/sdd-full`
    est réécrit en chemin Windows (`C:/Program Files/Git/sdd-full`) avant
    d'atteindre Python. Stocké tel quel, il ne matchait plus
    `COMMAND_TO_WORKFLOW` → le gate de livraison était silencieusement SAUTÉ
    pour ce run. On garde le dernier segment de chemin, sans slash initial.
    """
    raw = (command or "").strip().replace("\\", "/").lower()
    return raw.rstrip("/").rsplit("/", 1)[-1]


def workflow_for_command(command: str | None) -> str | None:
    raw = (command or "").strip().lower()
    return COMMAND_TO_WORKFLOW.get(raw) or COMMAND_TO_WORKFLOW.get(normalize_command(raw))


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [str(k) for k in value]
    try:
        return [str(v) for v in value]
    except TypeError:
        return [str(value)]


def _normalize(raw: Any, workflow: str) -> WiredDecision:
    def get(key: str, default: Any = None) -> Any:
        if isinstance(raw, dict):
            return raw.get(key, default)
        return getattr(raw, key, default)

    return WiredDecision(
        allowed=get("allowed", False) is True,  # seul un True explicite autorise
        workflow=str(get("workflow", workflow) or workflow),
        required=_as_list(get("required")), missing=_as_list(get("missing")),
        failed=_as_list(get("failed")), stale=_as_list(get("stale")),
        reasons=_as_list(get("reasons")),
    )


def _project_roots(module: Any, root: Path | None) -> list[Path]:
    """Racines de code de l'arbre courant — défaut du module central (`workspace/src`)."""
    default = getattr(module, "default_project_roots", None)
    if callable(default):
        return list(default(root))
    from sdd_lib.paths import repo_root, workspace_root
    return [workspace_root(root or repo_root()) / "src"]


def authorize(*, feat_n: int, workflow: str, run_id: str | None,
              root: Path | None = None,
              project_roots: Iterable[Path] | None = None) -> WiredDecision:
    """Appelle `authorize_delivery` (import paresseux) — fail-closed."""
    try:
        central = importlib.import_module("sdd_lib.delivery_gate")
        authorize_delivery = central.authorize_delivery
    except (ImportError, AttributeError) as exc:
        return WiredDecision(
            allowed=False, workflow=workflow, available=False,
            reasons=[f"module sdd_lib.delivery_gate indisponible ({exc}) — refus par défaut"])
    try:
        roots = (list(project_roots) if project_roots is not None
                 else _project_roots(central, root))
        raw = authorize_delivery(feat_n=feat_n, workflow=workflow, run_id=run_id,
                                 project_roots=roots)
    except Exception as exc:  # noqa: BLE001 — gate en erreur = refus, jamais autorisation
        return WiredDecision(allowed=False, workflow=workflow, available=False,
                             reasons=[f"authorize_delivery en erreur : "
                                      f"{type(exc).__name__}: {exc}"])
    return _normalize(raw, workflow)


def family_state(decision: WiredDecision, family: str) -> str:
    """État d'une famille de preuve : failed | missing | stale | ok | not_required."""
    for state, items in (("failed", decision.failed), ("missing", decision.missing),
                         ("stale", decision.stale)):
        if any(family_of(i) == family for i in items):
            return state
    if any(family_of(i) == family for i in decision.required):
        return "ok"
    if not decision.available:
        return "missing"  # gate injoignable : rien n'est prouvé
    return "not_required"


def blocked_message(feat_n: int | None, workflow: str, decision: WiredDecision) -> str:
    return (f"{BLOCKED_CLASS} livraison {workflow} FEAT {feat_n} refusée — "
            f"{decision.summary()}")


def _run_row(db: Path, run_id: str) -> tuple[str | None, int | None] | None:
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=5.0)
        try:
            row = conn.execute("SELECT command, feat_n FROM runs WHERE run_id = ?",
                               (run_id,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return (row[0], row[1]) if row else None


def gate_run_close(run_id: str, status: str, verdict: str | None = None,
                   error: str | None = None, *, root: Path | None = None,
                   db_path: Path | None = None
                   ) -> tuple[str, str | None, str | None, dict[str, Any] | None]:
    """Soumet une clôture de run au gate de livraison.

    Retourne `(status, verdict, error, decision_dict|None)`. Un statut de
    succès (`completed`/`success`/`partial`) sur un run porteur d'un workflow
    de livraison est rétrogradé en `failed` / `RED` / `[DELIVERY_GATE_BLOCKED]`
    si le gate refuse. Statuts d'échec/annulation : inchangés (pas de gate).
    Run hors livraison (`hook`, reverse, inconnu) : inchangé.
    """
    if status not in SUCCESS_CLOSE_STATUSES:
        return status, verdict, error, None
    from sdd_lib.paths import console_db_path
    row = _run_row(db_path or console_db_path(root), run_id)
    if row is None:
        return status, verdict, error, None
    command, feat_n = row
    workflow = workflow_for_command(command)
    if workflow is None or feat_n is None:
        return status, verdict, error, None
    decision = authorize(feat_n=int(feat_n), workflow=workflow, run_id=run_id, root=root)
    if decision.allowed:
        return status, verdict, error, decision.to_dict()
    return "failed", "RED", blocked_message(feat_n, workflow, decision), decision.to_dict()
