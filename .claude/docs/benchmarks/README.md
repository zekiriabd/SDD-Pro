# SDD_Pro — Benchmarks ROI (protocole + index)

> Résout la critique audit v7.0.0-alpha §4.1 :
> *« 100 % des cellules `<TBD>` dans `roi-baseline.md` — la valeur business n'est pas quantifiée. »*
>
> Objectif : remplir `docs/roi-baseline.md` avec des **mesures réelles**
> issues de runs `/sdd-full` reproductibles. **6 runs minimum avant tag GA v7.0.0** :
> FEAT S/M/L × 2 combos validés (C1 .NET, C2 Kotlin).

---

## 1. Matrice de benchmarks

| Run ID | Combo | Taille FEAT | Description | Status |
|---|---|---|---|:---:|
| `bench-s-dotnet` | C1 dotnet/react/shadcn | **S — CRUD simple** | 1 entité (5 colonnes), CRUD complet, pagination | `<TBD>` |
| `bench-m-dotnet` | C1 dotnet/react/shadcn | **M — workflow métier** | 3 entités liées, 2 endpoints "business", validation cross-field | `<TBD>` |
| `bench-l-dotnet` | C1 dotnet/react/shadcn | **L — auth+upload+intégration** | Auth Azure AD, upload fichier (PDF), notif SMTP, 5 entités | `<TBD>` |
| `bench-s-kotlin` | C2 kotlin/react/shadcn | S — CRUD simple | idem `bench-s-dotnet` (FEAT identique, stack différent) | `<TBD>` |
| `bench-m-kotlin` | C2 kotlin/react/shadcn | M — workflow métier | idem `bench-m-dotnet` | `<TBD>` |
| `bench-l-kotlin` | C2 kotlin/react/shadcn | L — auth+upload+intégration | idem `bench-l-dotnet` | `<TBD>` |

**Identité FEAT inter-stacks** : la même FEAT (`workspace/input/feats/{n}-*.md`)
est exécutée sur les 2 stacks. Compare l'effort framework × stack à US/AC
constants.

**3 runs par cellule** pour mesurer la variance (cf. `poc-roi-methodology.md`).
Total : **18 runs `/sdd-full`** pour publier le baseline complet.

---

## 2. Protocole d'exécution

### 2.1 Pré-requis

- **Console.db propre** : `python .claude/python/sdd_scripts/init_console_db.py --reset`
  (sauvegarde l'existant en `console.db.bak-{ts}`)
- **TokenUsageMode=record** : déjà par défaut v7.0.0 (`config.base.yml`)
- **Run ID stable** : `/sdd-full` génère un `run_id` UUID propre,
  tracé dans `sdd_state.run-*.json` et console.db.
- **Environnement isolé** : run sur machine de bench dédiée, pas de
  charge concurrente, modèles Claude figés (Sonnet 4.6 + Opus 4.7).
- **DB de test isolée** : PostgreSQL local séparé de prod, schéma vierge
  avant chaque run.

### 2.2 Séquence par run

```powershell
# 1. Préparer la FEAT (idempotent — réutiliser l'identique cross-stack)
cp templates/bench-feats/feat-{size}.md workspace/input/feats/1-Bench{Size}.md

# 2. Configurer le stack cible
# Éditer workspace/input/stack/stack.md pour activer le combo C1 ou C2

# 3. Snapshot avant run
python .claude/python/sdd_scripts/bench_run.py --snapshot-before --bench-id bench-{size}-{combo}-run-{n}

# 4. Exécution chronométrée
$start = Get-Date
/sdd-full 1
$end = Get-Date
$wallclock_min = ($end - $start).TotalMinutes

# 5. Snapshot après run + agrégation
python .claude/python/sdd_scripts/bench_run.py \
  --snapshot-after \
  --bench-id bench-{size}-{combo}-run-{n} \
  --wallclock-min $wallclock_min \
  --output docs/benchmarks/runs/bench-{size}-{combo}-run-{n}.json

# 6. Auditer le résultat (manuel, ~15 min)
# Remplir docs/benchmarks/feat-{size}-{combo}.md sur la base du JSON
```

### 2.3 Métriques capturées (par `bench_run.py`)

**Temps** (depuis `sdd_state.run-*.json` + console.db) :
- Wall-clock total (Get-Date diff)
- Durée par phase (us-gen, dev-plan, arch, dev-back, api-gate, dev-front, qa, reviewers)
- Temps Tech Lead actif (humain) vs IA (estimé par durée Agent invocation)

**Coût** (depuis `console.db` table `token_usage`) :
- Tokens input/output/cache par modèle (Sonnet/Opus/Haiku)
- Coût $ par phase, par US, total FEAT
- Coût `build_loop` (retries [BUILD_CORRECTIBLE])
- Coût `BuildLoopMaxCostUsd` consommé

**Qualité** (depuis rapports auditors `.sys/.validation/`, `qa/feat-{n}/`) :
- AC validés % (spec-compliance `[SPEC_AC_VERIFIED]` / total ACs)
- Retries build (compteur build_loop)
- Retries QA (re-runs `/qa-generate --filter`)
- Auditors FAIL/WARN count (code-review, security-scan, spec-compliance, arch-review)
- Coverage lines % vs `CoverageMin`
- Bugs post-run (review humaine 1h indep, count [critical, serious, moderate])

**Fiabilité** (depuis logs + observation) :
- Crash mid-run ? (Y/N + cause [CLASS])
- Relance idempotente ? (`/sdd-full --resume` → succès Y/N)
- Drift API back↔front ? (`[FRONTEND_BACKEND_CONTRACT_GAP]` détecté ?)
- Build convergent ? (build_loop atteint exit 0 < `BuildLoopMaxIter` ?)
- `[FEAT_HASH_MISMATCH]` détecté ? (FEAT modifiée mid-run)
- `[CHECKPOINT_HASH_MISMATCH]` détecté ?

---

## 3. Templates FEAT (pour bench identique cross-stack)

Les 3 FEATs de bench sont **figées** dans `.claude/templates/bench-feats/` :

| Template | Cible | Caractéristiques |
|---|---|---|
| `feat-s.template.md` | CRUD simple | 1 entité `Product` (id, name, price, sku, stock), 5 AC, mockup HTML 1 page liste + 1 page form |
| `feat-m.template.md` | Workflow métier | 3 entités (`Order`, `OrderLine`, `Product`), validation cross-field (total = sum lines), endpoint `POST /orders/{id}/confirm` business, 8 AC |
| `feat-l.template.md` | Intégration | Auth Azure AD scoped, upload PDF (`POST /documents`), notification email SMTP via SendGrid, 5 entités, 12 AC, 3 US |

> Les templates ne sont **pas** dans ce repo encore — à créer en partie
> du protocole. Voir §6 plan d'exécution.

---

## 4. Format rapport par bench

Chaque cellule de la matrice §1 produit un fichier `feat-{size}-{combo}.md`
agrégeant les 3 runs (médiane + variance). Structure type :

```markdown
# Bench {size} — {combo}

## Méta
- Date première run : YYYY-MM-DD
- Stack : {combo description}
- FEAT : `bench-feats/feat-{size}.template.md` v{hash}
- Modèles : Sonnet 4.6 + Opus 4.7
- Machine : {CPU, RAM, OS}

## Runs

| Métrique | Run 1 | Run 2 | Run 3 | Médiane | σ (variance %) |
|---|---:|---:|---:|---:|---:|
| Wall-clock (min) | ... | ... | ... | ... | ... |
| Coût $ | ... | ... | ... | ... | ... |
| Tokens input | ... | ... | ... | ... | ... |
| Tokens output | ... | ... | ... | ... | ... |
| Tokens cache hit | ... | ... | ... | ... | ... |
| AC verified % | ... | ... | ... | ... | ... |
| Build loops | ... | ... | ... | ... | ... |
| Coverage lines % | ... | ... | ... | ... | ... |
| Auditors RED | ... | ... | ... | ... | ... |
| Auditors WARN | ... | ... | ... | ... | ... |
| Bugs post-run (crit+ser) | ... | ... | ... | ... | ... |

## Cycles correctifs (FEAT L uniquement)
(éventuels retries Tech Lead post-`/sdd-full`)

## Verdict
🟢 / 🟡 / 🔴 vs critères release v7.0.0 (`roi-baseline.md §5.2`)
```

---

## 5. Critères de release v7.0.0 (sync `roi-baseline.md §5.2`)

| Critère | Cible | Mesuré sur |
|---|---|---|
| FEAT M wall-clock | framework ≤ humain / 5 | bench-m-dotnet + bench-m-kotlin (médiane) |
| FEAT M coût $ | framework ≤ humain / 50 | idem |
| FEAT M coverage | framework ≥ humain - 5 pts | idem |
| FEAT M AC verified | framework ≥ 90 % | idem |
| FEAT M quality serious+ | framework ≤ humain + 50 % | idem |
| Variance 3 runs | σ ≤ 15 % wall-clock & coût | par cellule |
| FEAT L fiabilité | 0 crash, idempotence OK | bench-l-* |
| Cross-stack consistency | écart C1/C2 ≤ 30 % par métrique | dotnet vs kotlin |

**Release GA autorisée** ssi toutes les colonnes Status sont 🟢 ou 🟡
(jamais 🔴) sur les 6 cellules.

---

## 6. Plan d'exécution (post-création de ce protocole)

| # | Étape | Effort | Bloquant pour GA ? |
|:---:|---|---|:---:|
| 1 | Créer 3 templates FEAT (`bench-feats/`) | 2-3 h | OUI |
| 2 | Setup machine de bench dédiée (Docker postgres, env figé) | 1-2 h | OUI |
| 3 | Établir baseline humaine FEAT S/M/L (chrono développeur senior) | 3 j (1 j/FEAT) | OUI |
| 4 | Run `bench-s-dotnet` × 3 | 30 min | OUI |
| 5 | Run `bench-m-dotnet` × 3 | 1 h | OUI |
| 6 | Run `bench-l-dotnet` × 3 | 1 h 30 | OUI |
| 7 | Run `bench-s-kotlin` × 3 | 30 min | OUI |
| 8 | Run `bench-m-kotlin` × 3 | 1 h | OUI |
| 9 | Run `bench-l-kotlin` × 3 | 1 h 30 | OUI |
| 10 | Review humaine indépendante bugs post-run (1 h/cellule × 6) | 6 h | OUI |
| 11 | Remplir `roi-baseline.md` avec données consolidées | 2 h | OUI |
| 12 | Publier README projet "ROI mesuré" | 1 h | NON (post-tag) |

**Total estimé** : **5-6 jours-homme** (3 j baseline humaine + 1.5 j runs + 1.5 j review/synthèse).

---

## 7. Anti-cherry-pick (méthodologie §7.1 source)

À documenter explicitement dans `roi-baseline.md §6` post-bench :

- **Cas où le framework N'EST PAS le bon outil** (mesuré, pas supposé) :
  - Si bench-s wall-clock ≥ humain (× 0.5) → framework non économique sur trivial
  - Si bench-l échoue (build_loop non convergent) → framework non robuste sur complexe
  - Refactoring code legacy : hors scope SDD_Pro (jamais bench)
  - Debug runtime post-prod : hors scope

Sans cette section, le baseline est un cherry-pick non auditable.

---

## 8. Tooling — `bench_run.py`

Script d'agrégation snapshot-before / snapshot-after → JSON consolidé :

```bash
# Pré-run snapshot (capture état console.db, sdd_state, fs)
python .claude/python/sdd_scripts/bench_run.py --snapshot-before --bench-id {id}

# Post-run agrégation
python .claude/python/sdd_scripts/bench_run.py \
  --snapshot-after \
  --bench-id {id} \
  --wallclock-min {N} \
  --output docs/benchmarks/runs/{id}.json
```

Cf. `.claude/python/sdd_scripts/bench_run.py` (cf. §10 ci-dessous pour spec).

---

## 9. Pointers

- `@.claude/docs/poc-roi-methodology.md` — méthodologie source
- `@.claude/docs/roi-baseline.md` — destination des résultats consolidés
- `@.claude/docs/validated-combos.md` — détail combos C1/C2
- `@.claude/python/sdd_scripts/bench_run.py` — script d'agrégation
- `@.claude/python/sdd_scripts/report_token_usage.py` — agrégation tokens existante (réutilisée par bench_run)
- `@.claude/python/sdd_scripts/query_console_db.py` — read queries SQL
- `@workspace/output/.sys/.context/adrs/ADR-20260519T193000-governance-roi-poc.md` — ADR décision + critères release
