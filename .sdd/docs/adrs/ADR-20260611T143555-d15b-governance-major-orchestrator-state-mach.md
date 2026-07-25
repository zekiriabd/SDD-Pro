# ADR — Orchestrateur déterministe : machine à états complète dans `sdd_full_planner.py` (RFC)

- **Statut** : Proposed (RFC — implémentation sur branche `next`, MAJOR/MINOR governance)
- **Date** : 2026-06-11
- **Auteur** : Tech Lead (audit consolidé 2026-06-11, finding C4)
- **Phase** : transverse (orchestration `/sdd-full`, `/dev-run`)

---

## Context

L'audit consolidé 2026-06-11 a identifié comme risque architectural n°1
que l'orchestration vit dans des **programmes markdown interprétés par le
LLM** : `dev-run.md` (~36 KB, 837 lignes) et `sdd-full.md` (~32 KB)
contiennent du pseudo-code bash/Python inline ré-interprété à chaque run
(~33K tokens de logique de contrôle non déterministe par invocation).
Chaque ré-interprétation est une opportunité de dérive : ordre des STEPs,
conditions de gates, sémantique `--resume`.

Le contrepoids existe déjà partiellement : `sdd_full_planner.py`
(subcommands `plan` / `next-action` / `recap`, 33 tests verts) porte une
partie de la boucle de décision, et `sdd-full.md §⚡` le recommande comme
"pattern thin-wrapper". Mais le planner ne couvre pas : les 4 gates
manuels LOT 3, la procédure GATE générique, les STEPs 4.45-4.9
(index ADRs, QA gate, spec-compliance post-dev, sdd-review, drift), ni
l'orchestration interne de `/dev-run` (batches parallèles, API gate,
two-stage auditors).

La roadmap v7.2 (`docs/roadmap-v7-v8.md`) prévoyait déjà "STEPs Markdown
re-générés depuis le planner Python" — ce RFC formalise la cible.

---

## Decision

Étendre `sdd_full_planner.py` (et un futur `dev_run_planner.py` symétrique)
en **machine à états complète et SSoT exécutable** de l'orchestration :

1. **Toute décision de contrôle** (skip/run/stop/gate/resume/verdict
   consolidé) est calculée par le planner Python (0 token, testable),
   y compris : gates manuels LOT 3, anti-cumul bypass, QA gate
   (`QaFailOnSddFull`), spec-compliance post-dev, review gate, batches
   parallèles bornés et two-stage auditors de `/dev-run`.
2. **Les `.md` de commandes deviennent des fiches minces** (~3-8 KB) :
   préconditions, appel du planner, exécution de l'action retournée
   (`skill` / `script` / `stop` / `done`), application de
   `output-protocol.md`. Le pseudo-code inline est supprimé.
3. **Le LLM décide DANS les agents, jamais ENTRE eux** : le routage
   inter-agents est 100 % déterministe.
4. Les STEPs actuels des `.md` sont conservés transitoirement comme spec
   de référence, puis **générés** depuis le planner (anti-drift par
   construction, gate smoke de comparaison).

## Périmètre exclu

- Aucun changement des prompts agents (po, arch, dev-*, qa, reviewers).
- Aucun changement des contrats de gates (mêmes seuils, mêmes classes
  `[CLASS]`, mêmes bypass env vars audit-loggués).
- Le module reverse garde son séquenceur dédié (`/sdd-reverse-full`).

---

## Consequences

**Positifs :**
- Économie estimée ~25-35K tokens de logique de contrôle par run
  (la fiche mince remplace les 17K+15K tokens des deux orchestrateurs).
- Dérive d'orchestration ≈ 0 (machine à états testée, pas ré-interprétée).
- `--resume` et idempotence prouvables par tests unitaires.
- Source unique : fin de la double-maintenance sdd-full.md ↔ dev-run.md.

**Négatifs / risques :**
- Chantier cœur (~2-3 semaines), risque de régression élevé → exige la
  branche `next`, un bench C1/C2 complet avant merge, et le gel des
  `.md` orchestrateurs pendant la migration.
- La lisibilité "tout dans le .md" diminue — compensée par la génération
  des STEPs de référence depuis le planner.

**Gating** : ne PAS implémenter sur `main`. Critères d'acceptation :
33+ tests planner étendus à ≥ 80 décisions couvertes, bench C1/C2 vert,
`framework_smoke` vert, diff de comportement nul sur les fixtures
d'orchestration (golden runs).
