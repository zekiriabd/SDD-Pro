"""Faux module central `sdd_lib.delivery_gate` pour les tests de CÂBLAGE.

Les tests de câblage (planner, clôture de run, hook, dev_run_args) prouvent
que les points de sortie consultent `authorize_delivery` et lui obéissent ; la
production réelle des preuves (build/tests exécutés, HMAC) est couverte par
les tests du module central. Ce faux est injecté dans `sys.modules` (le
câblage l'importe paresseusement) — jamais d'écriture dans `workspace/`.

Usage :
    gate = install_fake_gate(monkeypatch)
    gate.prove(1, "build")           # preuve valide pour FEAT 1
    gate.fail(1, "tests")            # preuve en échec
"""
from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field

REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "sdd-full": ("build", "tests", "coverage", "spec_compliance", "readiness"),
    "dev-run": ("build", "readiness"),
    "sdd-poc": ("build",),
    "sdd-deploy": ("build",),
    "qa-generate": ("build", "tests", "coverage"),
    "sdd-review": ("build", "spec_compliance"),
}


@dataclass
class FakeDecision:
    allowed: bool
    workflow: str
    required: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    stale: list = field(default_factory=list)
    reasons: list = field(default_factory=list)


class FakeGate:
    def __init__(self) -> None:
        self.evidence: dict[tuple[int, str], str] = {}
        self.calls: list[dict] = []

    def prove(self, feat_n: int, *checks: str) -> None:
        for c in checks:
            self.evidence[(feat_n, c)] = "pass"

    def fail(self, feat_n: int, *checks: str) -> None:
        for c in checks:
            self.evidence[(feat_n, c)] = "fail"

    def stale(self, feat_n: int, *checks: str) -> None:
        for c in checks:
            self.evidence[(feat_n, c)] = "stale"

    def authorize_delivery(self, *, feat_n, workflow, run_id=None, project_roots=None):
        self.calls.append({"feat_n": feat_n, "workflow": workflow, "run_id": run_id})
        req = list(REQUIREMENTS[workflow])
        missing, failed, stale = [], [], []
        for c in req:
            st = self.evidence.get((feat_n, c))
            if st is None:
                missing.append(c)
            elif st == "fail":
                failed.append(c)
            elif st == "stale":
                stale.append(c)
        allowed = not (missing or failed or stale)
        return FakeDecision(allowed=allowed, workflow=workflow, required=req,
                            missing=missing, failed=failed, stale=stale,
                            reasons=[] if allowed else ["preuve absente/invalide"])


def install_fake_gate(monkeypatch) -> FakeGate:
    gate = FakeGate()
    mod = types.ModuleType("sdd_lib.delivery_gate")
    mod.WORKFLOW_REQUIREMENTS = REQUIREMENTS
    mod.authorize_delivery = gate.authorize_delivery
    monkeypatch.setitem(sys.modules, "sdd_lib.delivery_gate", mod)
    import sdd_lib
    monkeypatch.setattr(sdd_lib, "delivery_gate", mod, raising=False)
    return gate
