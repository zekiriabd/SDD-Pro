# SDD_Pro — Migration Guide

Guide concis pour migrer un projet existant entre versions majeures.

---

## v6.10 → v7.0.0-alpha (consolidation majeure, post-audit CTO 2026-05-20)

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
MaxCostPerRun: 50.00              # USD hard cap par run (strict CI + interactive)
MaxOpusInflight: 6
BuildLoopMaxCostUsd: 15.00        # cap retries dev-* par US
BuildLoopMaxIter: 5

# Telemetry (P0 #4 — flippé off→record)
TokenUsageMode: record

# Auditors symmetry (P0 #6, #9)
QaFailOnSddFull: true
ReviewFailOnSddFull: true
SpecComplianceRequiredForFeatValidate: true

# Anti-GIGO
FeatAntiGigoMode: warn            # off | warn | strict
UsGranularityHardCap: 10          # was 6
UsGranularityWarnAt: 6
FeatDeepenThreshold: 3
FeatDeepenMode: warn

# Opt-in stacks
MutationTestingMode: "off"        # off | minimal | full
E2EMode: "off"                    # off | smoke | happy-paths | full
IntegrationTestMode: memory       # memory | hybrid | containers

# CI / a11y / perf
CiTemplatesGeneration: true       # arch génère .github/workflows/quality.yml
```

### Templates — nouveaux champs

`feat.template.md` v7.0.0 ajoute `## Quantified Goal` + `## Non-Functional
Constraints`. FEATs legacy → WARN non bloquant.

`us.template.md` v7.0.0 ajoute `Parent FEAT hash: sha256:{8}` au
frontmatter, vérifié par `preflight.py` (détecte FEAT modifiée
post-`/us-generate`).

### Hooks renforcés en CI

- `preflight_cost_cap` : hard block (était WARN-only en interactif)
- `protect_framework` : strict CI auto-detect (override `SDD_PROTECT_FRAMEWORK_MODE`)
- `audit_file_ownership` : WARN visible stderr en CI
- `preflight_agent_budget` : rejette les 5 agents retirés v7 avec `[AGENT_REMOVED_V7]`
- `record_token_usage` : lit layered config + alerte si DB inserts échouent

### DAG strict batching (R3)

`/dev-run` STEP 2.bis utilise `validate_us_deps.py --layered-batches`
(Kahn layered). Garantie hard : aucun US dans un batch ne dépend d'un
autre US du même batch.

### Bypasses cumulables verrouillés (R1)

`--force --no-plan-on-warn --no-validate` (2+ bypass) exige
`SDD_ALLOW_FORCE=1` env var. Sinon `[FORCE_CUMUL_REJECTED]`.

### Console.db migration v2

Table `qa_mutation` ajoutée (opt-in mutation testing). Migration
`0002_add-qa-mutation-table.sql` appliquée automatiquement.

### Atomic write pattern

Nouvelle règle `rules/build-and-loop.md §2.bis` : écritures `{LibName}/`
& projets shared doivent passer par `sdd_lib.atomic_write.atomic_write_text()`
(`.sddtmp + os.replace()`). Anti-corruption crash-mid-write.

### Exit codes convention

Nouveau module `sdd_lib/exit_codes.py` : 0=SUCCESS, 1=FAIL_FAST,
2=CORRECTIBLE, 3=INFRA_BLOCKED. `mark_breaking_resolved.py` migré
(était exit 1 = succès non-standard — **BREAKING** pour callers shell
qui distinguaient via exit code, voir docstring du script).

### Migration projet — checklist

1. Vérifier `stack.md ## Project Config` — ajouter flags v7 nécessaires
2. Lancer `/feat-validate {n}` sur chaque FEAT pour voir les WARN anti-GIGO
3. Optionnel : `/us-generate {n}` pour ajouter `Parent FEAT hash`
4. `console.db` schema_version = 2 (automatique)
5. Re-run `/sdd-full {n}` — bénéficier des nouveaux gates
6. Si CI : `protect_framework` + `audit_file_ownership` deviennent
   strict — vérifier qu'aucun agent custom écrit hors matrice

### Rollback

`git checkout v6.10.4-LTS` sur `main` (freeze jusqu'au 2026-06-18,
rollback safe).

---

## v6.8.0 → v6.9.0 (MCP server — additif opt-in)

**Effort** : 0. Aucun fichier projet à toucher.
**Breaking** : aucun. Le MCP server est purement additif.

### Quoi de neuf

- Serveur MCP exposant 14 tools SDD_Pro à des clients tiers (Cursor,
  Windsurf, Cline, Claude Desktop, n8n, scripts CI).
- 3 transports : stdio (défaut), HTTP opt-in, MCPB bundle Claude Desktop.
- 98 nouveaux tests pytest dédiés (`tests/test_mcp_*.py`).

### Pour utilisateurs Claude Code

**RIEN à faire.** Les slash commands `/sdd-full`, `/feat-generate`, etc.
continuent nativement. Le MCP server est un wrapper externe.

### Pour utilisateurs clients tiers (opt-in)

1. Copier `.claude/mcp.json` vers le manifest du client (`~/.cursor/mcp.json`,
   etc.) en adaptant les paths.
2. Vérifier : `python -m sdd_mcp.server --transport http --port 8765`
3. Auth Bearer optionnelle via `SDD_MCP_AUTH_TOKEN` env var.

Détail design : `@.claude/docs/MCP-SERVER.md`.

### Renommages

- `docs/PROPOSAL-FROMPLAN-STRICT.md` → `docs/DESIGN-FROMPLAN-STRICT.md`
- `docs/MCP-SERVER-PLAN.md` → `docs/MCP-SERVER.md`

Si un projet client a inliné ces paths quelque part : grep + sed pour
synchroniser. Sinon transparent.

### 2 nouvelles rules

- `rules/cors.md` (consolidation pattern CORS multi-stack)
- `rules/ui-tokens.md` (anti hex-hardcode, fidélité design)

Auparavant citées par les stacks mais inexistantes (refs cassées). Maintenant
opérationnelles. Aucun changement de comportement pipeline (les patterns
étaient déjà inlinés dans `auth/azure-ad.md` et `ui/shadcn.md`).

### Rollback

Désactiver le manifest MCP côté client. Le repo reste fonctionnel comme avant.

---

## v6.7.4 → v6.8.0 (US schema v2 + dependency graph)

**Effort** : 0 obligatoire (backward-compat strict). Optionnel : migrer les
US existantes vers le frontmatter v2 via script idempotent.

**Breaking** : aucun. US legacy `Status: Draft|Done` continuent à fonctionner.
US sans `## Dependencies` → graphe vide → topo alphabétique = comportement
v6.7 byte-identique.

### Quoi de neuf

- **7 statuts US granulaires** : `Draft | Ready | InProgress | Review | Done | Deferred | Cancelled`
- **Section `## Metadata` JSON AI-safe** dans US (`complexity` 1-10,
  `effort_estimate` S/M/L/XL, `notes`, `flags`, `custom.*`)
- **Section `## Dependencies` US** validée par `validate_us_deps.py`
  (Tarjan SCC pour cycles, Kahn pour topo order)
- **4 nouveaux scripts** déterministes (zéro coût LLM) :
  - `set_us_status.py` (transitions validées)
  - `compute_us_complexity.py` (scoring 1-10 + S/M/L/XL)
  - `migrate_us_v1_to_v2.py` (migration idempotente)
  - `validate_us_deps.py` (DAG validation + topo)
- **`/dev-run` STEP 2.bis** : validation deps + topo order avant batching
- **7 nouvelles classes d'erreur** taxonomie : `[US_STATUS_*]` (3),
  `[US_NOT_FOUND]`, `[US_DEPS_*]` (3)

### Migration optionnelle vers US v2

```bash
# Dry-run
python .claude/python/sdd_scripts/migrate_us_v1_to_v2.py --all --dry-run

# Appliquer
python .claude/python/sdd_scripts/migrate_us_v1_to_v2.py --all
```

Idempotent : skip US déjà v2.

### Utilisation des nouveaux statuts

```bash
python .claude/python/sdd_scripts/set_us_status.py --us 1-2 --status InProgress
```

Bypass d'une transition rejetée par le graphe : `--force` (tracé en WARN).

### Computing complexity score

```bash
# Read-only (JSON output)
python .claude/python/sdd_scripts/compute_us_complexity.py --us 1-2

# Inject dans ## Metadata
python .claude/python/sdd_scripts/compute_us_complexity.py --us 1-2 --apply
```

### Dependency graph

Ajouter dans les US une section :

```markdown
## Dependencies
- 1-1
- NONE   # ou bullet vide
```

Validation manuelle :

```bash
python .claude/python/sdd_scripts/validate_us_deps.py --feat 1 --topo
```

### Rollback

Tout est idempotent. Pour revenir au format v1, supprimer manuellement les
sections `## Metadata` et `## Dependencies` des US.

---

## v6.7.3 → v6.7.4 (Migrate parse_coverage.py — final policy script)

**Effort** : 0 si pas de team.yml/base.yml.
**Breaking** : aucun. Le comportement legacy est conservé quand `stack_md`
arg n'est pas le path canonique (tests, paths explicites).

### Modifié
- `sdd_scripts/parse_coverage.py::detect_coverage_min()` : logique
  conditionnelle layered-config (path canonique) vs legacy (path custom).

### Rationale
- En usage normal du pipeline, `parse_coverage.py` reçoit le path
  canonique → team policy `CoverageMin: 90` est honorée
- En tests ou usage explicite avec un autre path → comportement
  v6.6.x strict (lecture directe du fichier passé)

### Couverture finale migration
5 scripts migrés vers layered config (~50% des scripts policy-aware).
Les scripts restants lisent des clés d'**identité** (AppName,
BackendName, DatabaseType) qui ne sont pas candidates au layering.

### Rollback
Reverter `parse_coverage.py::detect_coverage_min()` via git. Pas
d'autre fichier touché.

---

## v6.7.2 → v6.7.3 (Migrate 4 scripts to layered config, transparent)

**Effort** : 0 si pas de team.yml/base.yml. Migration interne transparente.
**Breaking** : aucun (try/except fallback).

### Modifié
- 4 scripts : `phase_planner.py`, `validate_spec_compliance.py`,
  `context_budget.py`, `detect_arch_shortcircuit.py`
- Pattern : `read_layered_config()` puis fallback `read_project_config()` legacy
- `ConfigError [CONFIG_SECURITY_DOWNGRADE]` propagé explicitement par phase_planner

### Rollback
Reverter les 4 fichiers via git ou retirer les imports `layered_config`. Aucun
fichier nouveau créé.

### Garanties non-régression
- 358/358 tests passent (aucun nouveau test, migration interne)
- Fallback try/except absorbe toute exception du nouveau lib
- Si team.yml et base.yml absents : comportement byte-identique v6.7.2

---

## v6.6.5 → v6.6.5 (Checkpoint integration in dev-run)

**Effort** : 0 si `CheckpointMode: off` (défaut).
**Breaking** : aucun.

### Modifié
- `commands/dev-run.md` : STEP 1.75 (skip) + STEP 6.6 (record)
- Granularité : dev-run complet (arch + back + front + API Gate + auditors)
- Inputs hashés : FEAT + US + mockups HTML + stack.md

### Activation
```yaml
## Project Config
CheckpointMode: resume    # Skip dev-run entier si inputs unchanged
```

### Rollback
`CheckpointMode: off` (défaut) = STEPs skippés = byte-identical v6.6.4.

---

## v6.6.3 → v6.6.4 (Checkpoint integration in us-generate)

**Effort** : 0 si `CheckpointMode: off` (défaut).
**Breaking** : aucun.

### Modifié
- `commands/us-generate.md` : STEP 2.5 (skip) + STEP 3.bis (record)
- Inputs hashés : FEAT + stack.md

### Coverage finale (v6.6.5)
- ✅ `/qa-generate` (v6.6.3)
- ✅ `/us-generate` (v6.6.4)
- ✅ `/dev-run` (v6.6.5)

Tout opt-in via `CheckpointMode: off|record|resume` (défaut `off`).

### Rollback
`CheckpointMode: off` (défaut) = STEPs skippés = byte-identical v6.6.3.

---

## v6.7.1 → v6.7.2 (Profile manager — team config snapshots)

**Effort** : 0 (rien à faire si on ne crée pas de profile).
**Breaking** : aucun.

### Fichiers ajoutés
- `python/sdd_scripts/manage_profile.py` (~180 LOC, 5 subcommands)
- `python/tests/test_manage_profile.py` (15 tests)
- `commands/sdd-profile.md` (slash wrapper)

### Activation
```powershell
# Setup initial team.yml
mkdir ~/.sdd
notepad ~/.sdd/config.team.yml      # éditer manuellement

# Sauver comme profile
/sdd-profile export strict-prod
# Plus tard, basculer
/sdd-profile import dev-only         # backup auto en team.yml.bak
```

Storage : `~/.sdd/profiles/{name}.yml`. Override via `$SDD_PROFILES_DIR` et `$SDD_TEAM_CONFIG` (utile CI).

### Rollback
Ne rien faire = comportement v6.7.1. Pour supprimer : retirer les 3 fichiers + section CHANGELOG.

---

## v6.7.0 → v6.7.1 (Layered config 3-niveaux)

**Effort** : 0 si on ne crée pas `~/.sdd/config.team.yml` (base.yml seul est inactif).
**Breaking** : aucun. Lib opt-in, scripts existants inchangés.

### Fichiers ajoutés
- `.claude/config.base.yml` (~30 clés, framework defaults — reproduit v6.6.x à l'identique)
- `python/sdd_lib/layered_config.py` (~270 LOC)
- `python/tests/test_layered_config.py` (19 tests)

### Comportement par défaut
- Si `~/.sdd/config.team.yml` absent → `read_layered_config()` retourne EXACTEMENT le `## Project Config` de stack.md (= v6.6.x strict)
- Scripts existants (`phase_planner.py`, `validate_*.py`, etc.) appellent toujours `read_project_config()` legacy → 0 changement de comportement
- L'adoption de `read_layered_config()` est opt-in par script (prévue v6.7.3+)

### Activation org-wide
```yaml
# ~/.sdd/config.team.yml
CoverageMin: 90              # team enforce minimum coverage
SecurityFailOn: critical     # team enforce strictest security
SpecComplianceMode: full     # team activate spec-compliance by default
```

Tous les futurs projets héritent. Project peut DURCIR (e.g. `CoverageMin: 95`)
mais pas RELÂCHER (e.g. `CoverageMin: 50` → `[CONFIG_SECURITY_DOWNGRADE]`).

### Audit forensic
```python
from sdd_lib.layered_config import dump_effective_config
dump_effective_config(Path("workspace/output/.sys/.audit/config-effective.yml"))
# Génère un YAML annoté avec la source de chaque clé (base|team|project)
```

### Rollback
Supprimer `.claude/config.base.yml` + `~/.sdd/config.team.yml` → `read_layered_config()` retombe sur project-only. Scripts legacy `read_project_config()` non impactés.

---

## v6.6.2 → v6.6.3 (Checkpoint integration in qa-generate, opt-in)

**Effort** : 0 si `CheckpointMode: off` (défaut).
**Breaking** : aucun.

### Fichiers modifiés
- `commands/qa-generate.md` : +STEP 1.5 (checkpoint skip) + STEP 6.bis (record hash)

### Activation
```yaml
## Project Config
CheckpointMode: record       # ou "resume" pour skip-on-resume
```

Effet :
- `record` : capture input_hash à chaque fin de phase qa-generate (lightweight, gathers data)
- `resume` : capture + skip qa-generate au démarrage si inputs inchangés
- `off` (défaut) : aucun effet, comportement v6.6.2 strict

### Inputs hashés pour qa-generate
- `workspace/input/feats/{n}-*.md`
- `workspace/output/us/{n}-*.md`
- `workspace/input/stack/stack.md`

### Pattern adoption pour autres commands
Documenté dans CHANGELOG §6.6.3. À reporter dans `us-generate`, `dev-run` etc. progressivement (prévu v6.6.4-5).

### Rollback
Garder `CheckpointMode: off` (défaut). Les STEPs 1.5 + 6.bis se skippent eux-mêmes.

---

## v6.6.1 → v6.6.2 (Checkpoint lib foundation, no-op until adopted)

**Effort** : 0. Pure foundation, aucune command intégrée en v6.6.2.
**Breaking** : aucun. La lib est disponible mais inactive jusqu'à adoption.

### Étapes pour récupérer v6.6.2

1. **Fichiers ajoutés** (3) :
   ```
   .claude/python/sdd_lib/checkpoint.py            (NOUVEAU, ~200 LOC)
   .claude/python/tests/test_checkpoint.py         (NOUVEAU, 22 tests)
   .claude/rules/error-classification.md           (+§1.16 CHECKPOINT_*)
   .claude/CHANGELOG.md                            (entry v6.6.2)
   .claude/MIGRATION.md                            (ce fichier)
   ```

2. **Aucun changement de comportement** — la lib n'est invoquée nulle part.
   Le `--resume` actuel continue à fonctionner exactement comme v6.6.1.

3. **Pour utiliser la lib dans un script ad-hoc** :
   ```python
   from sdd_lib.checkpoint import is_phase_resumable, record_input_hash, get_phase_payload

   resumable, reason = is_phase_resumable(
       feat=1,
       phase="us-generate",
       input_paths=["workspace/input/feats/1-Auth.md"],
   )
   if resumable:
       print("Can skip this phase on resume")
   else:
       print(f"Must re-run: {reason}")
   ```

### Rollback

Pour revenir à v6.6.1 strict : supprimer les 3 fichiers nouveaux + la
section §1.16 de error-classification.md. Aucun autre nettoyage.

### Garanties non-régression

- 324/324 tests passent (302 baseline v6.6.1 + 22 v6.6.2)
- Aucune modification de `sdd_state.py` (source de vérité state.json)
- Aucune modification des commands (`--resume` actuel intact)
- Lib opère via atomic write (tempfile + rename)
- Hashs déterministes (mêmes inputs → même digest)

### Plan d'adoption progressif (v6.6.3+)

Ne pas activer en masse. Stratégie suggérée :
1. **v6.6.3** : intégrer dans `/qa-generate` uniquement (phase isolée, peu de dépendances inputs)
2. **v6.6.4** : intégrer dans `/us-generate`
3. **v6.6.5** : intégrer dans `/dev-run` (phase par phase, pas tout d'un coup)

Entre chaque étape, mesurer via telemetry v6.5.1 :
- Combien de runs profitent du skip ?
- Combien de fois `[CHECKPOINT_HASH_MISMATCH]` se déclenche (faux skips évités) ?
- Coût marginal du record_input_hash (négligeable, mais vérifier)

Si après une étape le ROI est nul ou négatif → retour arrière sans bloquer le pipeline.

---

## v6.5.2 → v6.6.1 (Stack auto-discovery, additive)

**Effort** : 0 (rien à faire — nouvelle commande complètement isolée).
**Breaking** : aucun. La commande n'est jamais invoquée par le pipeline
standard, doit être appelée manuellement par le Tech Lead.

### Étapes pour récupérer v6.6.1

1. **Fichiers ajoutés** (zéro fichier existant modifié sauf docs) :
   ```
   .claude/python/sdd_scripts/scan_repo.py              (NOUVEAU, ~400 LOC)
   .claude/python/sdd_scripts/match_stack_catalog.py    (NOUVEAU, ~270 LOC)
   .claude/python/tests/test_scan_repo.py               (NOUVEAU, 28 tests)
   .claude/python/tests/test_match_stack_catalog.py     (NOUVEAU, 16 tests)
   .claude/commands/sdd-discover-stack.md               (NOUVEAU, ~200 lignes)
   .claude/rules/error-classification.md                (+§1.15 DISCOVER_*)
   .claude/CHANGELOG.md                                 (entry v6.6.1)
   .claude/CLAUDE.md                                    (§10.quater)
   .claude/MIGRATION.md                                 (ce fichier)
   ```

2. **Pas de comportement par défaut nouveau** — la commande n'existe pas
   dans le chemin critique. Comportement strictement identique v6.5.2.

3. **Adopter SDD_Pro sur un repo existant** (cas d'usage principal) :
   ```powershell
   # Cloner le repo cible dans une SDD_Pro instance
   git clone <repo> .
   # Détecter le stack
   /sdd-discover-stack
   # → workspace/input/stack/stack.md.candidate généré

   # Revoir les `# TODO` (AppName, BackendName, secrets DB/JWT)
   # Renommer
   mv workspace/input/stack/stack.md.candidate workspace/input/stack/stack.md

   # Suite normale du workflow SDD_Pro
   /feat-generate <FeatName>
   ```

4. **Outputs forensic** (pour debug) :
   ```
   workspace/output/.sys/.audit/scan-report.json     # détection brute
   workspace/output/.sys/.audit/match-report.json    # mapping → stacks SDD
   ```

### Rollback

Pour revenir à v6.5.2 : ne rien faire. La commande est isolée, ne pas
l'invoquer = comportement v6.5.2 strict.

Pour la supprimer : retirer les 5 fichiers nouveaux (cf. liste ci-dessus)
et la section §1.15 de `error-classification.md`. Les tests peuvent
rester sans impact.

### Garanties non-régression

- 302/302 tests passent (258 anciens + 44 v6.6.1)
- Aucune modification du moteur (build_loop, API Gate, phases auditor,
  scripts validate_*, file ownership matrix, hooks)
- Commande jamais invoquée par `/sdd-full`, `/dev-run`, `/qa-generate`,
  `/feat-generate`, etc.
- Écrit toujours dans `.candidate` quand `stack.md` existe (jamais
  d'overwrite sauf `--force` explicite)
- Hors network, hors LLM jusqu'à STEP 5 (scripts Python déterministes)

### Stacks supportés (11 🟢 reference)

| Backend | Frontend | UI |
|---|---|---|
| dotnet-minimalapi | react | shadcn |
| kotlin-spring-boot | vue | vuetify |
| python-fastapi | angular | radzen-blazor |
| node-express | blazor-webassembly | |

Stacks 🟡 expérimentaux non détectés en v6.6.1 (à ajouter dans
`STACK_RULES` de `match_stack_catalog.py` si besoin).

---

## v6.5.1 → v6.5.2 (Spec-compliance reviewer, opt-in)

**Effort** : 0 (rien à faire pour rester en v6.5.1 strict). ~30 secondes
(2 lignes dans Project Config) pour activer.
**Breaking** : aucun. Mode défaut `manual` = skip = comportement v6.5.1.

### Étapes pour récupérer v6.5.2

1. **Fichiers ajoutés / modifiés** :
   ```
   .claude/agents/spec-compliance-reviewer.md            (NOUVEAU, ~300 lignes)
   .claude/python/sdd_scripts/validate_spec_compliance.py (NOUVEAU, ~300 LOC)
   .claude/python/tests/test_validate_spec_compliance.py  (NOUVEAU, 19 tests)
   .claude/python/tests/test_phase_planner.py             (+6 tests TestDecideSpecCompliance, 2 tests updated pour phases=6)
   .claude/python/sdd_scripts/phase_planner.py            (+_decide_spec_compliance + config keys)
   .claude/rules/error-classification.md                  (+§1.14 SPEC_* + ligne table §3)
   .claude/commands/dev-run.md                            (STEP 6.4 batch: 4 agents au lieu de 3)
   .claude/CHANGELOG.md                                   (entry v6.5.2)
   .claude/CLAUDE.md                                      (§10.ter)
   .claude/MIGRATION.md                                   (ce fichier)
   ```

2. **Comportement par défaut** : `SpecComplianceMode: manual` (default)
   → spec-compliance-reviewer est **skipped** dans STEP 6.4. Comportement
   strictement identique v6.5.1 / v6.4.2.

3. **Activer la spec-compliance** (optionnel) — éditer
   `workspace/input/stack/stack.md` :
   ```yaml
   ## Project Config
   SpecComplianceMode: full          # active le 4e auditeur dans STEP 6.4
   SpecComplianceFailOn: serious     # seuil verdict 🔴 RED (défaut: serious)
   ```

4. **Lancer normalement** :
   ```powershell
   /sdd-full 1
   # Output normal + nouvelle ligne dans la table verdict :
   #   ✓ spec-compliance     : 🟢 GREEN — 12/12 ACs verified
   ```

5. **Valider manuellement le rapport** :
   ```powershell
   python .claude/python/sdd_scripts/validate_spec_compliance.py --feat 1
   # Exit 0 = GREEN | 1 = WARN | 2 = RED ou invalide
   ```

### Rollback

Pour revenir au comportement v6.5.1 :

```yaml
## Project Config
SpecComplianceMode: manual    # ou off — désactive la phase
```

Ou retirer les 2 lignes du Project Config (default = manual = skip).
L'agent + scripts + tests peuvent rester en place sans impact.

### Garanties non-régression

- 258/258 tests passent (193 anciens + 40 v6.5.1 + 25 v6.5.2)
- Mode `manual` (défaut) = skip dans STEP 6.4 = comportement byte-identique v6.5.1
- Aucune modification des chemins critiques (build_loop, API Gate, file
  ownership, scripts validate_plan/readiness/coverage)
- 4e agent dans STEP 6.4 = pattern identique aux 3 existants (paths
  d'écriture disjoints, idempotent, pas de build_loop)
- File-ownership matrix `audit_file_ownership.py` ignore les paths sous
  `.sys/.validation/` (déjà couvert par IGNORE_PATTERNS v6.4.2)

### Recommandation d'activation

Activer **uniquement après** avoir validé v6.5.1 sur ≥ 2-3 FEATs réelles
(la telemetry permettra de mesurer le coût réel de v6.5.2). Pour la
première activation, démarrer avec `SpecComplianceFailOn: critical`
(plus permissif) puis descendre à `serious` une fois la qualité des
ACs validée.

---

## v6.4.2 → v6.5.1 (Real token telemetry, opt-in)

**Effort** : 0 (rien à faire pour rester en v6.4.2 strict). ~10 secondes
(1 env var) pour activer la telemetry.
**Breaking** : aucun. Hook désactivé par défaut.

### Étapes pour récupérer v6.5.1

1. **Fichiers ajoutés** (aucun fichier existant modifié sauf `settings.json` et `CHANGELOG.md` / `CLAUDE.md` / `MIGRATION.md`) :
   ```
   .claude/python/sdd_hooks/record_token_usage.py        (NOUVEAU, ~210 LOC)
   .claude/python/sdd_scripts/report_token_usage.py      (NOUVEAU, ~230 LOC)
   .claude/python/tests/test_record_token_usage.py       (NOUVEAU, 24 tests)
   .claude/python/tests/test_report_token_usage.py       (NOUVEAU, 16 tests)
   .claude/settings.json                                 (+2 entrées hooks)
   .claude/CHANGELOG.md                                  (entry v6.5.1)
   .claude/CLAUDE.md                                     (§10.bis)
   .claude/MIGRATION.md                                  (ce fichier)
   ```

2. **Comportement par défaut** : `SDD_TOKEN_USAGE_MODE` non défini ou `off` → hook fire mais exit immédiat = strictement équivalent v6.4.2. Aucun fichier `.jsonl` créé.

3. **Activer la telemetry** (optionnel) :
   ```powershell
   # PowerShell — pour la session courante
   $env:SDD_TOKEN_USAGE_MODE = "record"

   # PowerShell — persistent (machine user)
   [Environment]::SetEnvironmentVariable("SDD_TOKEN_USAGE_MODE", "record", "User")
   ```

4. **Mode debug** (forensic, première activation pour vérifier que Claude Code expose bien `usage`) :
   ```powershell
   $env:SDD_TOKEN_USAGE_MODE = "debug"
   # Lancer un /sdd-full puis inspecter
   ls workspace/output/.sys/.audit/token-debug/
   # Si les fichiers payload-*.json contiennent un champ `usage` -> mode "record" suffit
   # Sinon -> rapport `report_token_usage.py` montrera raw_usage_found: false
   ```

5. **Produire un rapport** :
   ```powershell
   python .claude/python/sdd_scripts/report_token_usage.py
   python .claude/python/sdd_scripts/report_token_usage.py --feat 1 --output workspace/output/.sys/.audit/report-feat-1.md
   python .claude/python/sdd_scripts/report_token_usage.py --json --since 2026-05-15T00:00:00Z
   ```

### Rollback

Pour revenir au comportement v6.4.2 :

```powershell
# Désactiver l'env var
Remove-Item Env:SDD_TOKEN_USAGE_MODE
# OU forcer off
$env:SDD_TOKEN_USAGE_MODE = "off"
```

Ou supprimer les 2 entrées hooks ajoutées dans `settings.json` (matchers
`Agent` dans `PostToolUse` et la 2ᵉ commande dans le bloc
`SubagentStop`). Les scripts et tests Python peuvent rester en place
sans impact (jamais invoqués).

### Garanties non-régression

- 233/233 tests passent (193 anciens + 40 nouveaux)
- Hook wrappé en try/except à tous niveaux — ne peut pas casser le
  pipeline même en cas de payload corrompu
- Mode `off` = early return avant tout I/O — comportement byte-identique v6.4.2
- Aucune modification des chemins critiques (build_loop, API Gate, file
  ownership, scripts validate_*)

---

## v6.1.x → v6.2.0 (From-Plan Strict + Cache Discipline, opt-in)

**Effort** : ~30 secondes (1 ligne dans `## Project Config`) si tu veux
activer ; **0 effort** si tu restes en v6.1 behaviour.
**Breaking** : aucun. Tout est opt-in.

### Étapes pour adopter le chemin strict

1. **Récupérer les fichiers v6.2** :
   ```
   .claude/agents/dev-backend.md             (§5.2 patché : v2 emission)
   .claude/agents/dev-frontend.md            (§6.4 patché : v2 emission)
   .claude/agents/dev-backend-strict.md      (NOUVEAU, Sonnet 4.6)
   .claude/agents/dev-frontend-strict.md     (NOUVEAU, Sonnet 4.6)
   .claude/agents/dashboard.md               (§5 widget Plan Cache)
   .claude/commands/dev-run.md               (STEP 6.0.bis + routing strict)
   .claude/commands/dev-plan.md              (STEP 4.7 auto-validation)
   .claude/rules/dev-shared.md               (§7.4.bis + §7.6 + §7.7 + §7.8)
   .claude/rules/error-classification.md     (12 nouveaux codes PLAN_*)
   .claude/python/sdd_scripts/validate_plan.py        (NOUVEAU)
   .claude/python/sdd_scripts/compute_plan_metadata.py (NOUVEAU)
   .claude/python/sdd_scripts/sdd_state.py   (docstring events v6.2)
   .claude/python/tests/test_validate_plan.py          (NOUVEAU, 21 tests)
   .claude/python/tests/test_compute_plan_metadata.py  (NOUVEAU, 7 tests)
   .claude/loader.yml                        (entries dev-*-strict)
   .claude/CLAUDE.md                         (v6.2.0)
   .claude/CHANGELOG.md                      (entry v6.2.0)
   .claude/MIGRATION.md                      (ce fichier)
   .claude/docs/DESIGN-FROMPLAN-STRICT.md    (design de référence)
   ```

2. **Activer le chemin strict** dans `workspace/input/stack/stack.md` :
   ```yaml
   ## Project Config
   # ... lignes existantes ...
   PlanCacheStrict: true       # opt-in v6.2 (défaut: false = v6.1 behavior)
   ```

3. **Vérifier la cohérence du framework** :
   ```bash
   python .claude/python/sdd_admin/framework_smoke.py
   python .claude/python/tests/test_validate_plan.py
   python .claude/python/tests/test_compute_plan_metadata.py
   ```
   Doivent retourner 21/21 + 7/7 verts.

4. **Régénérer les plans v2 sur tes FEATs existantes** (les v1 restent
   utilisables en fallback classic) :
   ```bash
   /dev-plan {n}             # produit des plans v2 strict-ready
   ```

5. **Lancer un /dev-run avec routing strict** :
   ```bash
   /dev-run {n}              # back→API gate→front, Sonnet 4.6 sur From-Plan strict
   ```

### Mesurer le gain (benchmark avant/après)

Pour quantifier le gain sur ton projet :

1. **Run baseline** (PlanCacheStrict: false ou v6.1) :
   ```bash
   /sdd-full {n}             # noter run-id, durée, tokens (state.jsonl)
   ```

2. **Run strict** (PlanCacheStrict: true) :
   ```bash
   /sdd-full {n} --plan      # garantit un /dev-plan avant /dev-run
   ```

3. **Comparer** :
   ```bash
   python .claude/python/sdd_scripts/sdd_state.py list-runs --feat-number {n} --limit 5
   # depuis v6.10 : voir tables `runs` + `run_phases` + `events` dans console.db
   # (`query_console_db.py` ou /api/state) — plus de state.jsonl ni events.jsonl FS
   ```

   Cibles attendues (cf. `docs/DESIGN-FROMPLAN-STRICT.md §1.2`) :
   - Latence dev-* From-Plan : ÷3 (45s → 15s médiane)
   - Coût tokens dev-* : ÷5 (Sonnet vs Opus tarif)
   - Cache hit rate : ≥ 70 % (mesuré via dashboard widget §5)

### Compatibilité ascendante

- ✅ Projets v6.1 sans `PlanCacheStrict: true` : aucun changement de
  comportement, aucune régression.
- ✅ Plans v1 existants : restent utilisables (lecture backward-compat).
  Sur prochain `/dev-plan`, ils seront régénérés en v2.
- ✅ `--force`, `--max-parallel`, `--rebuild-arch`, `--manual-gates`,
  `--resume` : inchangés.
- ✅ Workflow gated v6.1 (back → API gate → front) : préservé en v6.2.
- ✅ Fidelity check `validate_fidelity.py` : actif en strict mode aussi.
- ✅ File ownership, source-first, idempotence : invariants maintenus.

### Quand le chemin strict bascule en classic (fallback automatique)

Le routing est défensif : si un plan ne peut pas être consommé par un
agent strict, l'orchestrateur bascule automatiquement sur l'agent
classique (Opus 4.7) sans interruption du pipeline.

| Cas | Détection | Action |
|---|---|---|
| Plan v1 (legacy) | `validate_plan.py --strict` exit 1 | Classic Opus |
| Plan v2 sans `## Inline Digest` | exit 1 | Classic Opus |
| Plan v2 stale (us-hash mismatch) | exit 2 | STOP + ERROR, re-`/dev-plan` |
| Digest incomplet runtime (agent ne trouve pas l'info) | `[PLAN_DIGEST_INSUFFICIENT]` du strict agent | Re-spawn classic dans même batch |

Ces fallbacks sont loggés dans la table `events` de `console.db`
(`event_type = 'plan_cache_fallback'`) et consultables via
`/api/state` ou `query_console_db.py`. (v6.10 BREAKING : plus
de fichier `events.jsonl` sur FS.)

### Désactiver le chemin strict (revert)

Suffit de retirer ou mettre `PlanCacheStrict: false` dans Project
Config. Tous les fichiers v6.2 restent compatibles v6.1 — aucun
nettoyage requis.

### Risques connus

- **Qualité Sonnet vs Opus sur templating complexe** : sur des US avec
  beaucoup d'augment + preserves/adds entrelacés, Sonnet 4.6 peut
  produire un code légèrement moins idiomatique. Surveiller la
  régression sur le combo référence avant promotion défaut.
- **Plan digest insuffisant** : si le digest généré par `/dev-plan` ne
  capture pas une convention projet spécifique, l'agent strict
  s'arrêtera (fallback automatique). Cas rare, observable via event
  `plan_cache_fallback` dashboard.

---

## v5.0.0 → v6.0.0 (ultra-lean — suppression validator)

**Effort** : ~2 minutes. **Breaking** : agent `validator` retiré.

### Étapes

1. **Récupérer les fichiers modifiés** depuis le template :
   ```
   .claude/CLAUDE.md              (version v6.0.0, 4 cœur + 2 support)
   .claude/CHANGELOG.md           (entry v6.0)
   .claude/MIGRATION.md           (ce fichier)
   .claude/commands/feat-validate.md (réécrit, 100% déterministe)
   .claude/loader.yml             (validator retiré, version 6.0.0)
   .claude/python/sdd_admin/framework_smoke.py (validator retiré du check 1)
   .claude/docs/architecture.md   (validator retiré du tableau modèles)
   .claude/docs/workflow.md       (mention agent validator → déterministe)
   workspace/output/docs/presentation.html  (v6.0.0, 6 agents, section Validator retirée)
   workspace/output/docs/readme.html        (v6.0.0)
   ```

2. **Supprimer** `.claude/agents/validator.md` (plus utilisé).

3. **Si tu as un rapport readiness existant** : la section §2
   (validations sémantiques) ne sera plus régénérée. Aucune action
   requise — un nouveau `/feat-validate` produit un rapport sans §2.

4. **Vérifier la cohérence** :
   ```bash
   python .claude/python/sdd_admin/framework_smoke.py
   ```
   Doit retourner OK=70+ (au lieu de 50 en v5, car validator retiré
   et nouveaux checks anti-régression ajoutés en v6.1.2).

5. **(Optionnel) Mesurer le delta tokens** :
   ```bash
   python .claude/python/sdd_admin/measure_batch.py --since 2026-05-XX
   ```
   Cible : –1.4M tokens raw par `/sdd-full` vs v5.

### Compatibilité ascendante

- ✅ Tous les autres commands fonctionnent identiquement.
- ✅ Les artefacts `workspace/output/{us,src,context,db,qa}/` v5 sont consommés
  tels quels par v6.
- ✅ Les FEATs `workspace/input/feats/*.md` v5 sont valides v6.
- ✅ Les rapports readiness v5 (avec §2 sémantique) restent lisibles ;
  les nouveaux rapports v6 n'auront simplement pas de §2.

### Comportements changés

- `/feat-validate` est désormais **100% script PS, 0 token LLM**.
- Plus de détection automatique d'AC vagues, ambiguïtés cross-artefact,
  hypothèses implicites. **Review humaine PO obligatoire** pour ces
  aspects sémantiques.
- Décision finale = décision déterministe seule (plus de combinaison
  det/sem).

### Pour réintroduire le validator localement

Si tu trouves la review sémantique LLM nécessaire :
1. Restaurer `.claude/agents/validator.md` depuis git history < v6.0
2. Restaurer la STEP 4 dans `.claude/commands/feat-validate.md`
3. Restaurer la section `validator:` dans `loader.yml`
4. Ajouter `validator` à `expectedAgents` dans `framework_smoke.py`

---

## Versions antérieures (v3.x → v4.x, v4.x → v5.x)

Voir [`.claude/ARCHIVE/MIGRATION-legacy.md`](ARCHIVE/MIGRATION-legacy.md) pour
les procédures de migration v3→v4 (HTML direct) et v4→v5 (Inline Rules
+ tokens-lean). Archivé le 2026-05-13.

Pour les versions v1.x → v2.x → v3.x, voir l'historique git.
