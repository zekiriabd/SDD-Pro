---
command: sdd-reverse-paradigm
phase: '"2.7"'
description: Analyse de gap de paradigme legacy↔stack cible + curation des unités (MIGRATE / DISCARD / HUMAN-DECISION). Spawn agent reverse-paradigm-advisor (Sonnet 4.6). Verdict informational/WARN, jamais bloquant, jamais destructif. Emprunt Reversa (agents Paradigm Advisor + Curator) — audit comparatif 2026-06-12.
loader: .sdd/loader.reverse.yml
---
<!-- @llm-only-flags-file — les flags de /sdd-reverse-paradigm sont
     interprétés par le LLM (l'agent reverse-paradigm-advisor) ; aucune
     gate Python dédiée (verdicts informational). -->

# /sdd-reverse-paradigm {LegacyProject} [--json]

## Rôle

Avant l'extraction Phase 3 : (1) documenter l'écart de **paradigme** entre le
legacy (ex. WebForms postback/ViewState) et la stack cible déclarée dans
`stack.md` (ex. React SPA + API stateless), avec une décision consciente à
arbitrer (`adopt-target` / `preserve-legacy` / `hybrid`) ; (2) **curer** les
unités de l'inventory pour ne pas migrer du code mort (suggestion `--units`
consommable par `/sdd-reverse-full`).

## Args

| Arg | Type | Description |
|---|---|---|
| `{LegacyProject}` | requis | Sous-dossier `workspace/old/` |
| `--json` | flag | Émet le résumé en JSON |

## Pré-conditions

1. `workspace/old/{P}/.sys/inventory.json` existe (Phase 1 a tourné). Sinon → ERROR `[REVERSE_NO_SOURCE]`.
2. Recommandé (non bloquant) : Phase 2 (`tech-audit.md`, `deps-graph.json`) —
   sans elle les verdicts `DISCARD` perdent leur signal principal (orphelins).
3. `workspace/stack/stack.md` avec lignes actives — sinon la partie
   paradigme est émise en mode « cible non déclarée » (informational).

## Actions

1. **Spawn unique** `Agent(reverse-paradigm-advisor)` avec arg = `{P}`. <!-- no-spawn §9 -->
2. L'agent produit la table de gap (mécanisme legacy file:line → idiome cible →
   risque), la recommandation 3-options avec `Décision: PENDING`, et la table
   de curation par unité.

## Sortie

```
workspace/old/{P}/.sys/paradigm-decision.md
workspace/old/{P}/.sys/curation.md          (header machine-parseable <!-- CURATION: ... -->)
```

## Émission chat

```
[REVERSE] Paradigme {legacy}→{cible} : {G} gaps ; curation {N} MIGRATE / {K} DISCARD / {H} à arbitrer. (PROGRESS%)
```

`H > 0` ou `Décision: PENDING` → `[REVERSE/WARN]` + `[REVERSE_CURATION_PENDING]`.

## Anti-derive

- No-spawn d'agent autre que `reverse-paradigm-advisor`
- **Jamais destructif** : aucune unité retirée d'inventory.json, aucun fichier legacy touché
- **Jamais bloquant** : le Tech Lead arbitre (Phase 5) ; `/sdd-reverse-full` reste
  intégral par défaut — la curation n'est qu'une suggestion `--units`
- Idempotent : relancer régénère l'analyse en **préservant** les arbitrages humains posés

Voir `.sdd/rules/reverse-engineering.md §6` ([REVERSE_PARADIGM_GAP], [REVERSE_CURATION_PENDING]) + `.sdd/agents/reverse-paradigm-advisor.md`.
