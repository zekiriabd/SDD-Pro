# SDD_Pro — Migration Guide

Guide concis pour migrer un projet existant entre versions majeures.

---

## v6.10 → v7.0.0 GA (consolidation majeure)

**Effort** : 1-2h pour mettre à jour `stack.md ## Project Config` + relancer
`/feat-validate {n}` sur chaque FEAT pour bénéficier des nouveaux gates.
**Breaking** : 5 (agents retirés + statuts API gate + comportements).

### Agents retirés (5)

| Agent | Remplacement |
|---|---|
| `accessibility-auditor` | axe-core CI step (`.github/workflows/quality.yml` auto-généré si `CiTemplatesGeneration: true`) |
| `performance-auditor` | Lighthouse CI + wrk/k6 CI step |
| `dashboard` | `sdd_scripts/index_adrs.py` (0 token) |
| `dev-backend-strict` | `dev-backend` Opus 4.7 (plan v2 préservé) |
| `dev-frontend-strict` | `dev-frontend` Opus 4.7 |

### API Gate — statuts normalisés (BREAKING)

`GREEN/YELLOW/RED` → `PASS / WARN / FAIL / SKIPPED / INFRA_BLOCKED`.
Champ `verdict` legacy conservé en parallèle de `status` canonique
(cf. `rules/build-and-loop.md §1.3`). Callers v7+ doivent lire `status`.

### Rules consolidées (11 → 5) — stubs supprimés

Migration `Read @.claude/rules/X.md` → nouveau path :

| Ancien stub (supprimé) | Nouveau path |
|---|---|
| `backend-first.md` | `build-and-loop.md` Partie A |
| `dev-shared.md` | `build-and-loop.md` Partie B |
| `qa-coverage.md` | `quality.md` Partie A |
| `ui-tokens.md` | `quality.md` Partie B |
| `file-ownership.md` | `ownership.md` Partie A |
| `constitution.md` | `ownership.md` Partie B |
| `stack-completeness.md` | `library-and-stack.md` Partie A |
| `cors.md` | `library-and-stack.md` Partie B |
| `source-first.md` | `docs/principles/source-first.md` |
| `us-granularity.md` | `docs/principles/us-granularity.md` |

### Project Config — nouveaux flags v7.0.0

Ajouter dans `## Project Config` selon besoin (tous ont des défauts sains) :

```yaml
# Cost caps (P0)
MaxCostPerRun: 50.00              # USD hard cap par run
MaxOpusInflight: 6
BuildLoopMaxCostUsd: 15.00        # cap retries dev-* par US
BuildLoopMaxIter: 5

# Telemetry
TokenUsageMode: record

# Auditors symmetry
QaFailOnSddFull: true
ReviewFailOnSddFull: true
SpecComplianceRequiredForFeatValidate: true

# Anti-GIGO
FeatAntiGigoMode: warn            # off | warn | strict
UsGranularityHardCap: 10
UsGranularityWarnAt: 6

# Opt-in stacks
MutationTestingMode: "off"        # off | minimal | full
E2EMode: "off"                    # off | smoke | happy-paths | full
IntegrationTestMode: memory       # memory | hybrid | containers

# CI / a11y / perf
CiTemplatesGeneration: true
```

### Templates v7

- `feat.template.md` : `## Quantified Goal` + `## Non-Functional Constraints`
  (FEATs legacy → WARN non bloquant)
- `us.template.md` : `Parent FEAT hash: sha256:{8}` frontmatter
  (détection FEAT modifiée post-`/us-generate` via `preflight.py`)

### Hooks renforcés CI

- `preflight_cost_cap` : hard block (était WARN-only interactif)
- `protect_framework` : strict CI auto-detect
- `audit_file_ownership` : WARN stderr CI
- `preflight_agent_budget` : rejette agents retirés v7 avec `[AGENT_REMOVED_V7]`
- `record_token_usage` : layered config + alerte DB

### Autres BREAKING

- **DAG strict batching (R3)** : `validate_us_deps.py --layered-batches`
  (Kahn). Garantie : aucun US dans batch ne dépend d'un autre US du même batch.
- **Bypass cumulables (R1)** : `--force --no-plan-on-warn --no-validate`
  (2+ flags) exige `SDD_ALLOW_FORCE=1` env var.
- **Console.db v2** : table `qa_mutation` (migration `0002` auto).
- **Atomic write** (`rules/build-and-loop.md §2.bis`) : écritures
  `{LibName}/` & shared via `sdd_lib.atomic_write.atomic_write_text()`.
- **Exit codes** (`sdd_lib/exit_codes.py`) : 0=SUCCESS, 1=FAIL_FAST,
  2=CORRECTIBLE, 3=INFRA_BLOCKED. `mark_breaking_resolved.py` migré
  (était exit 1 = succès, **BREAKING** callers shell).

### Checklist migration projet

1. Vérifier `stack.md ## Project Config` — ajouter flags v7 nécessaires
2. Lancer `/feat-validate {n}` sur chaque FEAT (WARN anti-GIGO)
3. Optionnel : `/us-generate {n}` pour ajouter `Parent FEAT hash`
4. `console.db` schema_version = 2 (automatique)
5. Re-run `/sdd-full {n}` — bénéficier des nouveaux gates
6. CI : vérifier qu'aucun agent custom n'écrit hors matrice ownership

### Rollback

`git checkout v6.10.4-LTS` sur `main` (freeze 2026-06-18, safe).

---

## Migrations v6.x → v6.y (historique)

Pour migrer un projet plus ancien (v5.x, v6.0-v6.10), suivre la chaîne
des migrations successives via :

- `docs/CHANGELOG-v6.md` (archive 2026-02 → 2026-05, 1504 L) — chaque
  entrée release indique les fichiers à toucher + actions Tech Lead
- `git log --oneline -- .claude/docs/MIGRATION.md` pour récupérer les
  procédures détaillées historiques (v6.5→v6.6, v6.6→v6.7, etc.)
- v3→v4 (HTML direct) et v4→v5 (Inline Rules) : `archive/MIGRATION-legacy.md`
  (archivé 2026-05-13)

Le saut le plus large supporté est **v6.10 → v7.0.0 GA**. Pour les sauts
plus larges (v6.5 → v7.0), passer par v6.10 intermédiaire en suivant
`CHANGELOG-v6.md` release par release.
