# /sdd-review — Audit qualité consolidé par FEAT (style Sonar)

<!-- @llm-only-flags-file : la plupart des flags CLI de cette commande slash sont interprétés par Claude. Exception : `--no-spec-gate` ET `--feat-number/--skip-scans/--ensure-scans/--fail-on/--json/--adversarial` (selon contexte) sont parsés par sdd_review.py argparse. Le test smoke vérifie l'union (Python OR @llm-only). -->


**Phase A — rapport seul, 0 auto-fix.** Re-run du scan déterministe
[`quality_scan.py`](.claude/python/sdd_scripts/quality_scan.py), agrégation
des findings de tous les auditeurs déjà persistés dans
[`console.db`](workspace/output/db/console.db) (qa_quality, qa_code_review,
qa_security, qa_a11y, qa_performance, qa_spec_compliance), **triage
déterministe par owner** (backend / frontend / shared / unknown) basé sur
le path, calcul du verdict 🟢/🟡/🔴 contre `ReviewFailOn`, persistance dans
`validation_reports(report_type='review')` + rendu Markdown
[`workspace/output/qa/feat-{n}/review.md`](workspace/output/qa/feat-).

**Phase B (à venir v7.2)** : auto-fix loop (dispatcher `dispatch_fixes.py`
écrit, non encore wired à une commande user-facing).

**Phase C (✅ déjà câblée v7.0.0)** : agent `arch-reviewer` (Pattern + Layers
+ ADRs) auto-invoqué par `/dev-run` STEP 6.4 (auditor batch) et `/sdd-review`
STEP 3.0. Cf. `agents/arch-reviewer.md`.

---

## Usage

```bash
/sdd-review {n}                       # audit FEAT {n}, verdict + report
/sdd-review {n} --skip-scans          # lecture DB seule (sans re-scan)
/sdd-review {n} --ensure-scans        # v7.0.0 : exit 3 si une source QA obligatoire manque
/sdd-review {n} --fail-on critical    # override seuil (info|minor|moderate|serious|critical)
/sdd-review {n} --json                # sortie JSON pour CI/tooling
/sdd-review {n} --adversarial         # v7.2.0 R1 : avocat du diable post-agrégation (informational, jamais bloquant)
/sdd-review {n} --no-spec-gate        # v7.0.0+ : skip Stage A spec-compliance gate (legacy comportement parallèle)
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

Si `AdversarialReviewMode: full` OU flag CLI `--adversarial` → spawn agent
`adversarial-reviewer` au STEP 6 (post-agrégation, opt-in, jamais bloquant).

---

## STEP 3.0.bis — `spec-compliance-reviewer` (gate two-stage)

**Pattern v7.0.0+ (two-stage, emprunt superpowers)** : avant d'agréger les
findings code/security/arch, vérifier que la spec est respectée. Si le code
n'implémente pas les ACs, agréger des findings code/security/arch est
prématuré (le code sera réécrit, les findings deviennent obsolètes).

Vérification rapide avant spawn (lecture déterministe DB) :

```bash
python .claude/python/sdd_scripts/query_console_db.py spec-compliance-present \
  --feat {n} [--max-age-hours 24]
# exit 0 = entrée FRAÎCHE présente (< 24h, défaut) → SKIP fallback
# exit 1 = aucune entrée fraîche → spawn fallback ci-dessous
```

Si exit 1 (aucune entrée spec-compliance fraîche dans `qa_spec_compliance`),
spawner l'agent en fallback :

```
Agent: spec-compliance-reviewer
  prompt: "Audit FEAT {n} — verification AC-by-AC (cf. agents/spec-compliance-reviewer.md). Mode gate two-stage. FailOn={SpecComplianceFailOn}"
```

Lecture du verdict produit (`{n}-spec-compliance.json` → `summary.verdict`) :

| Verdict spec | Action |
|---|---|
| 🟢 GREEN | → STEP 3.0 (arch-reviewer) + STEP 3 (aggregator) |
| 🟡 WARN | → STEP 3.0 + STEP 3 + propager warning verdict consolidé |
| 🔴 RED | STOP early — bloc 3.0.bis.STOP (économie : pas d'agrégation inutile) |

### STEP 3.0.bis.STOP — Format STOP sur spec RED

```
🔴 /sdd-review {n} — spec-compliance gate RED ({NV} ACs non vérifiées)

Verdict spec-compliance : 🔴 RED ({V}/{T} ACs verified)
Rapport : workspace/output/.sys/.validation/{n}-spec-compliance.md

⊘ arch-reviewer + agrégation code/security/quality : skipped (gate failed)
   Rationale : agréger des findings sur du code qui ne respecte pas la spec
   produit un rapport trompeur. Corriger d'abord la spec.

Débloquer :
  1. Lire {n}-spec-compliance.md §Findings (ACs not_verified + suggestions)
  2. Corriger (/dev-{backend|frontend} {n}-{m} ou édit manuel)
  3. Relancer /sdd-review {n} (idempotent : re-run gate puis agrégation)

Bypass : `--no-spec-gate` (rapport agrégat même si spec RED — déconseillé)
ou baisser SpecComplianceFailOn en Project Config.
```

**Skip légitime** :
- `SpecComplianceMode: off` Project Config → skip gate, continuer
- Flag CLI `--no-spec-gate` → skip gate (audit-loggué)
- `phases.spec_compliance.enabled == false` (FEAT sans AC testable strict)

---

## STEP 3.0 — `arch-reviewer` (fallback standalone uniquement)

**Fallback standalone** (`/sdd-review {n}` invoqué directement, hors
`/sdd-full`) : si `ArchReviewMode: full` ET aucune entrée `[ARCH_*]`
trouvée pour la FEAT `{n}` dans `qa_code_review` (signal que dev-run
n'a pas tourné dans la session courante), spawner l'agent en
fallback :

```
Agent: arch-reviewer
  prompt: "Audit FEAT {n} — Pattern + Layers + ADRs (cf. agents/arch-reviewer.md). FailOn={ArchReviewFailOn}"
```

Vérification rapide avant spawn (lecture déterministe DB) :
```bash
python .claude/python/sdd_scripts/query_console_db.py arch-review-present --feat {n} [--max-age-hours 24]
# exit 0 = entrées FRAÎCHES présentes (< 24h, défaut) → SKIP fallback (déjà fait par dev-run)
# exit 1 = aucune entrée fraîche → spawn fallback ci-dessus
```

> **TTL 24h par défaut (audit C4 closure 2026-06-07)** : si le dernier
> `[ARCH_*]` finding est plus vieux que 24h, le code a probablement
> changé entre-temps. Le fallback re-spawne l'agent pour obtenir une
> review à jour. Override : `--max-age-hours 0` (no TTL, legacy v7.0.0)
> ou valeur custom selon contexte CI/CD.

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

## STEP 4.5 — Spawn `adversarial-reviewer` (opt-in, post-agrégation)

Si `--adversarial` (CLI) OU `AdversarialReviewMode: full` (config),
**et uniquement après** que le rapport consolidé
[`workspace/output/qa/feat-{n}/review.md`](workspace/output/qa/feat-)
est écrit (l'agent en a besoin comme précondition) :

```
Agent: adversarial-reviewer
  prompt: "Audit FEAT {n} — avocat du diable post-/sdd-review (cf. agents/adversarial-reviewer.md)."
```

- L'agent produit `workspace/output/qa/feat-{n}/adversarial.{md,json}`
  puis appelle `ingest_agent_report --type adversarial` qui insère dans
  `validation_reports(report_type='adversarial', verdict='informational')`.
- **Verdict consolidé inchangé** : les `[ADV_*]` ne sont PAS agrégés
  dans `validation_reports(report_type='review')` ni dans l'exit code.
  C'est un canal séparé consultable via :
  ```bash
  # Audit final 2026-06-07 (BROKEN-4 closure) : query_console_db.py n'expose
  # pas `--raw-sql` (subcommands explicites uniquement). Pour consulter le
  # canal adversarial, utiliser sqlite3 CLI directement :
  sqlite3 workspace/output/db/console.db \
    "SELECT feat_number, verdict, payload_json FROM validation_reports
     WHERE report_type='adversarial' AND feat_number={n}
     ORDER BY id DESC LIMIT 1"
  ```
- Échec adversarial-reviewer (timeout, erreur infra) → WARN dans le
  récap final, ne bloque jamais (par design).
- Skip légitime si `AdversarialReviewMode: off` OU absence du flag —
  message court `adversarial-reviewer feat-{n}: skipped`.

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
ReviewMode:                 full        # full | scans-only | read-only
ReviewFailOn:               serious     # info | minor | moderate | serious | critical
AdversarialReviewMode:      manual      # off | manual | full (v7.2.0 R1)
AdversarialMinAttacks:      5
AdversarialMaxAttacks:      10
```

| Clé | Défaut | Effet |
|---|---|---|
| `ReviewMode` | `full` | `full` = re-scan + read DB ; `scans-only` = re-scan + skip DB read ; `read-only` = pas de re-scan |
| `ReviewFailOn` | `serious` | Seuil de bascule 🟡 → 🔴. `critical` = très permissif, `info` = très strict |
| `AdversarialReviewMode` | `manual` | `off` = jamais ; `manual` = uniquement si `--adversarial` ; `full` = auto-invoke à chaque `/sdd-review` |
| `AdversarialMinAttacks` | `5` | Plancher cible (warn `coverage_warning: true` si moins) |
| `AdversarialMaxAttacks` | `10` | Plafond strict (verdict toujours informational) |

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

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[CODE-REVIEW]`, `[SPEC-REVIEW]`,
`[ARCH-REVIEW]`, `[ADV-REVIEW]` (opt-in), `[SECURITY]`, `[DONE]`
(cf. output-protocol.md §3)
**Plage de progression couverte** : `88-100%` (cf. output-protocol.md §4)

**Granularité cible** : 5-7 updates (agrégation 5 sources : arch +
code + security-scan + spec + quality, puis verdict consolidé style
Sonar).

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- détail des findings par source (compteurs par sévérité suffisent)
- stdout/stderr de bash, JSON dumps sdd_review.py
- snippets de code citées

**Verdict consolidé** : 1 ligne avec emoji style Sonar. Exemple :
`[CODE-REVIEW] Verdict consolidé: 0 critical, 5 serious, 12 moderate — 🟡 WARN. (99%)`.
En cas de RED bloquant : `🔴 [DONE/FAIL] FEAT {n} — [REVIEW_VERDICT_RED] → workspace/output/qa/feat-{n}/review.md. (99%)`.

**Verdict final** : 1 ligne `[DONE]` (🟢) / `[DONE/WARN]` (🟡) /
`[DONE/FAIL]` (🔴) (cf. §9.1). Pas de "next steps" après (cf. §9.3).

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
