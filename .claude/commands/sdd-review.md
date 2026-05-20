# /sdd-review — Audit qualité consolidé par FEAT (style Sonar)

**Phase A — rapport seul, 0 auto-fix.** Re-run du scan déterministe
[`quality_scan.py`](.claude/python/sdd_scripts/quality_scan.py), agrégation
des findings de tous les auditeurs déjà persistés dans
[`console.db`](workspace/output/db/console.db) (qa_quality, qa_code_review,
qa_security, qa_a11y, qa_performance, qa_spec_compliance), **triage
déterministe par owner** (backend / frontend / shared / unknown) basé sur
le path, calcul du verdict 🟢/🟡/🔴 contre `ReviewFailOn`, persistance dans
`validation_reports(report_type='review')` + rendu Markdown
[`workspace/output/qa/feat-{n}/review.md`](workspace/output/qa/feat-).

**Phase B (à venir)** : auto-fix loop (dispatch `dev-backend:fix` et
`dev-frontend:fix` sur les findings corrigeables).

**Phase C (à venir)** : agent `arch --mode review` (Pattern + Layers + ADRs)
+ auto-invoke en fin de `/sdd-full`.

---

## Usage

```bash
/sdd-review {n}                       # audit FEAT {n}, verdict + report
/sdd-review {n} --skip-scans          # lecture DB seule (sans re-scan)
/sdd-review {n} --ensure-scans        # v7.0.0 : exit 3 si une source QA obligatoire manque
/sdd-review {n} --fail-on critical    # override seuil (info|minor|moderate|serious|critical)
/sdd-review {n} --json                # sortie JSON pour CI/tooling
```

`--ensure-scans` (v7.0.0, codex audit follow-up) : exige que toutes les
sources auditeur obligatoires soient présentes dans `console.db` avant
de produire le verdict consolidé. Évite le faux 🟢 GREEN quand un agent
auditor a simplement été oublié pour cette FEAT.

| Source | Requise par défaut | Conditionnelle |
|---|:---:|---|
| `quality` (quality_scan.py) | ✅ | — |
| `code-review` (code-reviewer agent) | ✅ | — |
| `security` (security-reviewer agent, mode scan) | ✅ | — |
| `spec` (spec-compliance-reviewer agent) | ✅ | — |
| `arch` (arch-reviewer agent) | optionnel | requise SI `ArchReviewMode: full` |
| `a11y` (deprecated v7.0.0) | optionnel | jamais requise — agent supprimé |
| `perf` (deprecated v7.0.0) | optionnel | jamais requise — agent supprimé |

Exit code `3` avec `[REVIEW_SOURCES_MISSING]` + liste exacte des
invocations à lancer pour combler les manques.

Argument **obligatoire** : `{n}` (entier ≥ 1, numéro de FEAT).

---

## STEP 1 — Valider l'argument

Si argument absent →
```
ERROR: /sdd-review — argument manquant
CAUSE: [INVALID_ARG] aucun numéro de FEAT fourni
FIX: relancer /sdd-review {n} (ex. /sdd-review 1)
```

Si non numérique →
```
ERROR: /sdd-review — argument invalide
CAUSE: [INVALID_ARG] "{argument}" n'est pas un entier
FIX: relancer /sdd-review {n}
```

Si FEAT inconnue (aucun fichier `workspace/input/feats/{n}-*.md`) →
```
ERROR: /sdd-review {n} — FEAT inconnue
CAUSE: [FEAT_NOT_FOUND] aucun fichier workspace/input/feats/{n}-*.md
FIX: relancer /feat-generate ou utiliser un numéro existant
```

---

## STEP 2 — Lire la configuration (layered)

Read `## Project Config` de [`workspace/input/stack/stack.md`](workspace/input/stack/stack.md)
via `read_layered_config()`. Clés relevantes (toutes optionnelles) :

```yaml
ReviewFailOn:      serious   # défaut: serious (info|minor|moderate|serious|critical)
ReviewMode:        full      # défaut: full (full|scans-only|read-only)
ArchReviewMode:    manual    # défaut: manual (full|manual|off)
ArchReviewFailOn:  serious   # défaut: serious
```

Si `ReviewMode: read-only` → forcer `--skip-scans` (pas de re-run quality_scan).

Si `ArchReviewMode: full` → spawn agent `arch-reviewer` au STEP 3.5 ci-dessous.

---

## STEP 3.0 — Spawn `arch-reviewer` (conditionnel, si `ArchReviewMode: full`)

Si `ArchReviewMode: full` → spawner l'agent `arch-reviewer` via tool Agent
**AVANT** l'orchestrateur Python (l'agent écrit dans `qa_code_review` table,
puis `sdd_review.py` STEP 3.2 lit cette table et inclut les `[ARCH_*]`).

```
Agent: arch-reviewer
  prompt: "Audit FEAT {n} — Pattern + Layers + ADRs (cf. agents/arch-reviewer.md). FailOn={ArchReviewFailOn}"
```

Sur skip (`ArchReviewMode in (manual, off)`) → continuer STEP 3 directement,
les findings `[ARCH_*]` ne seront simplement pas présents dans l'agrégation.

Échec arch-reviewer (timeout, erreur infra) → WARN dans le récap final,
continuer STEP 3 (rapport partiel mais non bloquant — la review consolidée
reste utile).

---

## STEP 3 — Exécuter l'orchestrateur Python (déterministe)

```bash
python .claude/python/sdd_scripts/sdd_review.py \
  --feat-number {n} \
  [--skip-scans] \
  [--ensure-scans] \
  [--fail-on {info|minor|moderate|serious|critical}] \
  [--json]
```

Exit codes :
- `0` → 🟢 GREEN ou 🟡 YELLOW (verdict sous le seuil)
- `1` → 🔴 RED (verdict ≥ ReviewFailOn)
- `2` → erreur infra (FEAT absente, DB inaccessible, args malformés)
- `3` → `--ensure-scans` actif et au moins une source obligatoire manquante (v7.0.0)

Le script effectue automatiquement :
1. **STEP 3.1** — Re-run `quality_scan.py --feat-number {n}` (sauf `--skip-scans`)
   → refresh table `qa_quality`
2. **STEP 3.2** — Read DB : qa_quality + qa_code_review + qa_security
   (mode=`scan`) + qa_a11y + qa_performance + qa_spec_compliance (verdict
   ≠ `verified`) où `feat_n = {n}`
3. **STEP 3.3** — Pour chaque finding, classifier l'owner via
   `triage_issues.classify_path()` :
   - `workspace/output/src/{BackendName}/**`  → backend
   - `workspace/output/src/{AppName}/**`      → frontend
   - `workspace/output/src/{LibName}/**`      → shared
   - autre                                     → unknown
4. **STEP 3.4** — Verdict :
   - 🔴 RED si ≥ 1 finding `critical`/`blocker` OU ≥ 1 ≥ `ReviewFailOn`
   - 🟡 YELLOW si findings sous le seuil mais non vides
   - 🟢 GREEN sinon
5. **STEP 3.5** — Persister `validation_reports` (report_type=`review`) +
   émettre [`workspace/output/qa/feat-{n}/review.md`](workspace/output/qa/feat-)

---

## STEP 4 — Restituer le résultat dans le chat

**Format compressé** (cf. mémoire utilisateur — 1L succès, 2L max erreur) :

🟢 GREEN :
```
🟢 /sdd-review FEAT {n}: 0 findings → GREEN (markdown: workspace/output/qa/feat-{n}/review.md)
```

🟡 YELLOW :
```
🟡 /sdd-review FEAT {n}: {N} findings (0 ≥ {fail_on}) → YELLOW
   owner: {back:N, front:M} | source: {quality:X, code-review:Y, ...}
   → workspace/output/qa/feat-{n}/review.md
```

🔴 RED :
```
🔴 /sdd-review FEAT {n}: {N} findings ({T} ≥ {fail_on}) → RED
CAUSE: [REVIEW_VERDICT_RED] {T} findings critical/serious à corriger
FIX: lire workspace/output/qa/feat-{n}/review.md §"Findings déclenchants" puis dispatcher
```

---

## STEP 5 — Suite manuelle (Phase B/C à venir)

Tant que Phase B (auto-fix dispatcher) et Phase C (arch review +
auto-invoke `/sdd-full`) ne sont pas livrées, le Tech Lead arbitre :

1. Consulter `workspace/output/qa/feat-{n}/review.md` — colonne **Owner**
   = quel agent dispatcher
2. Pour **backend** issues : `/dev-backend {n}-{m}` (re-spawn idempotent)
   ou édit manuel
3. Pour **frontend** issues : `/dev-frontend {n}-{m}` ou édit manuel
4. Re-run `/sdd-review {n}` jusqu'à convergence

---

## Configuration `## Project Config`

```yaml
# Defaults conservateurs
ReviewMode:     full        # full | scans-only | read-only
ReviewFailOn:   serious     # info | minor | moderate | serious | critical
```

| Clé | Défaut | Effet |
|---|---|---|
| `ReviewMode` | `full` | `full` = re-scan + read DB ; `scans-only` = re-scan + skip DB read ; `read-only` = pas de re-scan |
| `ReviewFailOn` | `serious` | Seuil de bascule 🟡 → 🔴. `critical` = très permissif, `info` = très strict |

---

## Lectures utiles

- `query_console_db.py review --feat {n}` — JSON résumé du dernier run
- `workspace/output/qa/feat-{n}/review.md` — rapport humain
- `validation_reports` table avec `report_type='review'`

---

## Anti-derive

- ❌ JAMAIS d'auto-fix en Phase A (rapport seul)
- ❌ JAMAIS de modification du code applicatif (`workspace/output/src/`)
- ❌ JAMAIS de ré-écriture des findings dans qa_quality / qa_code_review /
  qa_security / etc. — l'orchestrateur LIT, AGRÈGE, mais ne TOUCHE PAS aux
  tables des auditeurs sources
- ❌ JAMAIS de `--force` pour bypasser un verdict RED (corriger les
  findings puis re-lancer)

---

## Coordination avec autres commandes

| Avant | `/sdd-review` | Après |
|---|---|---|
| `/qa-generate` | ⚠️ pas obligatoire mais recommandé (quality + coverage déjà à jour) | — |
| `/dev-run` STEP 6.4 | déjà fait : code-reviewer + a11y + security-scan | — |
| `/sdd-full` | tout fait : qa + auditors | **Phase C** : auto-invoke `/sdd-review --fix` |

`/sdd-review` est **idempotent** : re-runs lisent l'état actuel de la DB,
overwrites la ligne `validation_reports` précédente (via
`replace_validation_reports`).
