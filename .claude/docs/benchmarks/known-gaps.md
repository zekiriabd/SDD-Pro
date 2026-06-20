# SDD_Pro — Known gaps from bench 2026-06-05

> **Statut** : tracking ouvert v7.0.0-alpha
> **Source** : section §13 du rapport [`workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md`](../../../workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md)
> **Distinction-clé** : ces gaps **n'invalident pas** la qualité du code généré (23 combinaisons runtime 🟢 prouvent que les stack patterns sont conformes). Ils invalident la **promesse "pipeline automatisé end-to-end"** sur les 10 stacks `bench-validated runtime` — pour les promouvoir en `validated` (au sens C1/C2), il faut combler ces gaps.

---

## Gap 1 — Agents `arch` / `qa` / `arch-reviewer` non câblés au tool `Agent` lors du bench

### Symptôme observé
Lors du bench multi-stack 2026-06-05, le mainteneur a dû **scaffolder manuellement** les projets `CalcABCBackPy`, `CalcABCMaui`, `CalcABCRN`, etc., car ces 3 sub-agents (`arch`, `qa`, `arch-reviewer`) n'étaient pas accessibles via le tool `Agent` dans la session.

### Conséquence
- 23 combinaisons cataloguées comme **runtime 🟢** mais pas **pipeline 🟢 validated** (au sens C1/C2)
- Le claim "FEAT → US → arch → dev → QA → review automatisé" n'est pas démontré pour ces 10 stacks
- US 3-1, 4-1, 5-1 (Blazor/Vue/Angular) **non générées par l'agent `po`** — raccourci économie ~240K tokens × 3 = 720K tokens (~$4-9), AC matérialisés directement dans le code par mainteneur
- Tests `qa` non générés (sauf React + Kotlin) — Vitest/Jasmine/bUnit/xUnit/pytest absents pour les autres
- `/sdd-review` skip — pas de verdict consolidé pour ces FEATs

### Impact commercialisation
**Hard-blocking** pour un pitch "automatisé end-to-end sur 23 combinaisons". Acceptable pour un pitch "code généré conforme + 2 combos C1/C2 entièrement automatisés".

### Reproduction
```bash
# Session bench mainteneur 2026-06-05 — agents listés dans Skill descriptor
# mais pas dans tool Agent runtime → forcé override scaffolding direct
```

### Fix proposé
1. **Diagnostic** : vérifier que les agents `arch`, `qa`, `arch-reviewer` sont bien déclarés dans `.claude/agents/*.md` (✅ fait — les 3 fichiers existent) et exposés au tool `Agent` (à vérifier sur poste neuf après `claude code` restart)
2. **Test smoke** : `framework_smoke.py` — ajouter un check « les 12 agents `.md` sont tous spawnables via tool `Agent` » (actuellement non vérifié)
3. **Re-bench** : rejouer le bench 2026-06-05 avec les agents câblés et mesurer la différence wall-clock vs scaffolding manuel
4. **Critère acceptance** : 6 runs `bench-{s,m,l}-{dotnet,kotlin}` du protocole [`docs/benchmarks/README.md`](README.md) avec agents câblés, verdict 🟢, publier dans `roi-baseline.md`

### Priorité
**P1** — bloquant pour promouvoir C3/C4/C5 en `🟢 validated` et fermer la critique audit v7.0.0 §4.1 (« cellules `<TBD>` dans roi-baseline.md »).

---

## Gap 2 — Token usage mainline non-tracé

### Symptôme observé
Lors du bench 2026-06-05, seuls les 3 sub-agents `po` invoqués (235 644 tokens cumulés, ~$1.50-3.00 Sonnet 4.6) ont été tracés dans `console.db.token_usage`. Le **flow direct mainteneur** (commandes Read/Edit/Bash exécutées par Claude orchestrateur) n'a laissé **aucune trace** dans la table.

### Conséquence
- **Coût total bench inconnu** — impossible de répondre à la question "combien coûte la production de ces 23 combinaisons via SDD_Pro vs développement humain pur ?"
- Métrique ROI baseline (`docs/roi-baseline.md`) reste partiellement spéculative
- Cost caps `[COST_CAP_EXCEEDED]` $50/run et `[BUILD_LOOP_COST_EXCEEDED]` $15/US (cf. `error-classification.md §1.2`) ne peuvent pas se déclencher pour le flow mainline → garde-fou inopérant en pratique

### Cause-racine identifiée
Hook `PostToolUse(Agent)` qui ingest les `<usage>` retournés par le tool `Agent` **n'est pas wired**. Le hook existe partiellement (cf. `sdd_hooks/record_token_usage.py`) mais ne couvre que les sub-agents spawnés, pas les ToolUses Read/Edit/Bash de l'orchestrateur.

### Fix proposé
1. **Audit** : `record_token_usage.py` — vérifier qu'il consomme bien le bloc `<usage>` de **chaque** réponse Anthropic API du runtime, pas seulement des sub-agents
2. **Hook setting** : `.claude/settings.json` — déclarer `PostToolUse` matcher `*` (toute ToolUse) pour ingest token usage, pas seulement `Agent`
3. **Validation** : rejouer 1 run `/sdd-full` minimaliste après fix, vérifier que `token_usage` se peuple avec les 4 colonnes attendues (input/output/cache_read/cache_write tokens × ts)
4. **Critère acceptance** : `query_console_db.py token-usage --run-id {uuid}` retourne un total ≥ 90% du budget effectivement consommé (10% tolérance pour overhead non-mesurable)

### Priorité
**P2** — non-bloquant pour la commercialisation (le framework marche), bloquant pour les claims ROI quantifiés.

---

## Statut consolidé pour décision de mise sur le marché

| Claim | État | Action requise |
|---|:--:|---|
| « SDD_Pro génère du code conforme sur 23 combinaisons stacks » | 🟢 démontré | aucune (bench 2026-06-05) |
| « Pipeline `/sdd-full` automatisé end-to-end » | 🟢 sur C1/C2 uniquement | Gap 1 fix + bench protocole §2 [`docs/benchmarks/README.md`](README.md) |
| « ROI mesuré vs développement humain » | 🔴 non chiffré | Gap 2 fix + 6 runs S/M/L × {C1, C2} |
| « Cost caps bloquants en runtime » | 🟡 partiels (sub-agents only) | Gap 2 fix |
| « Reviewers bloquants (security OWASP, code, spec, arch) » | 🟢 sur C1/C2 | aucune (sdd_review.py + auditor_runs validés) |
| « 5 bugs runtime documentés SSoT » | 🟢 inscrits | aucune (`library-and-stack.md §7`) |

---

## Prochaines actions consolidées

1. **Gap 1** : test smoke agents `Agent`-spawnable + rejouer bench 6 runs protocole `bench-{s,m,l}-{dotnet,kotlin}`
2. **Gap 2** : wire `PostToolUse(*)` hook + validation 1 run consommation tracée
3. **Promotion C3/C4/C5** : exécuter `/sdd-full` complet automatisé sur 1 FEAT M chacun, après Gap 1 fix
4. **Update `roi-baseline.md`** : remplir les cellules `<TBD>` avec mesures réelles, après Gap 2 fix

**Dépendance** : Gap 1 doit être fixé avant Gap 2 (sinon les mesures token incluraient le scaffolding manuel qui n'est pas représentatif du flow nominal).
