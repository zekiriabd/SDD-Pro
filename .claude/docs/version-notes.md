# SDD_Pro — Notes de version (archive)

> Archive des **sous-sections §10.bis → §10.novies** de l'ancien `CLAUDE.md`
> (slim 2026-05-19, cf. ADR-20260519T153000-governance-major-prompts-trim).
> Les entrées détaillées par version vivent dans `@.claude/docs/CHANGELOG.md` ;
> ce fichier conserve les notes opérationnelles courtes-format de chaque
> sprint pour l'onboarding et le diagnostic.

---

## v6.5.1 — Telemetry tokens (opt-in)

Capture post-call des tokens réels consommés par chaque sub-agent
(input/output/cache). Désactivée par défaut. Pour activer une session :

```powershell
$env:SDD_TOKEN_USAGE_MODE = "record"
/sdd-full 1
python .claude/python/sdd_scripts/report_token_usage.py --feat 1
```

Modes : `off` (défaut) | `record` (append ledger) | `debug` (record + dump).
Depuis v6.10, l'ledger vit dans `console.db` table `token_usage`.

---

## v6.5.2 — Spec-compliance reviewer (opt-in)

Agent `spec-compliance-reviewer` (Sonnet 4.6) qui re-lit indépendamment le
code matérialisé et vérifie AC-par-AC qu'il existe une preuve concrète
d'implémentation (`file:line`). Pattern « Do not trust the report ».

Activer dans `## Project Config` :
```yaml
SpecComplianceMode: full              # défaut: manual (skip)
SpecComplianceFailOn: serious
```

> v7.0.0 (proposé) : les 5 clés Mode + 8 clés FailOn fusionnent en
> `Auditors: core | off` + `AuditorsFailOn: critical|serious|moderate`
> (cf. `ADR-20260519T143000-governance-major-flags-trim.md`).

---

## v6.6.1 — Discover stack auto-detection (brownfield)

Pour adopter SDD_Pro sur un repo existant en ~2 min :

```powershell
/sdd-discover-stack
```

Scan + détection automatique parmi les 11 stacks 🟢 reference (4 backend,
4 frontend, 3 UI). Écrit `workspace/input/stack/stack.md.candidate` (rename
manuel → `stack.md`). Hors moteur — ne touche pas `/dev-run` ni `/sdd-full`.

---

## v6.6.2 — Checkpoint lib (input-hash resume)

Reprise post-crash via hashing des inputs. Opt-in `CheckpointMode: off | record | resume`.

> v7.0.0 (proposé) : la clé `CheckpointMode` disparaît, seul `--resume`
> flag CLI subsiste (record automatique).

---

## v6.7.1 — Layered config (opt-in)

Project Config lue en **3 couches mergées** :
- `.claude/config.base.yml` (framework defaults)
- `~/.sdd/config.team.yml` (org/team policy)
- `## Project Config` de stack.md (per-project, final override)

Précédence : project > team > base. Sécurité : project ne peut JAMAIS
relâcher la policy team → `[CONFIG_SECURITY_DOWNGRADE]`.

API : `sdd_lib.layered_config.read_layered_config()`.

> v7.0.0 (proposé) : `read_project_config()` legacy retiré, tous les
> scripts passent à `read_layered_config()` (cf.
> `ADR-20260519T133000-governance-major-config-ssot.md`).

---

## v6.7.2 — Profile manager

Snapshots de `~/.sdd/config.team.yml` :

```powershell
/sdd-profile export strict-prod
/sdd-profile import dev-only           # backup auto en .bak
/sdd-profile list
```

Storage : `~/.sdd/profiles/{name}.yml`. Hors repo, hors workspace.

---

## v6.8.0 — US schema v2 + dependency graph

**Frontmatter US enrichi** :
- 7 statuts granulaires : `Draft | Ready | InProgress | Review | Done | Deferred | Cancelled`
- Section `## Metadata` JSON AI-safe (`complexity` 1-10, `effort_estimate` S/M/L/XL)

**4 scripts déterministes** :
```bash
python .claude/python/sdd_scripts/set_us_status.py --us 1-2 --status InProgress
python .claude/python/sdd_scripts/compute_us_complexity.py --us 1-2 --apply
python .claude/python/sdd_scripts/migrate_us_v1_to_v2.py --all      # idempotent
python .claude/python/sdd_scripts/validate_us_deps.py --feat 1 --topo
```

**`/dev-run` STEP 2.bis** valide le graphe `## Dependencies` (cycles via
Tarjan SCC, refs manquantes) AVANT batching, puis ordonne `US_LIST` en
topo order (Kahn). Backward-compat : US sans `## Dependencies` → topo
alphabétique = comportement v6.7 byte-identique.

---

## v6.10.0 — Console DB SQLite (BREAKING)

**Refactor majeur** : tous les `.json` / `.jsonl` / `.log` de télémétrie
retirés du FS, centralisés dans `workspace/output/db/console.db` (SQLite
WAL). Les rapports `.md` lecture humaine sont conservés.

**24 tables** en 4 familles :
- Artefacts SDD : `feats`, `us`, `plans`, `adrs`
- Runs/Telemetry : `runs`, `run_phases`, `gates`, `events`, `token_usage`,
  `context_budget`, `validation_reports`, `breaking_changes`
- QA : `qa_coverage` (+ files), `qa_quality`, `qa_api_tests` (+ endpoints),
  `qa_a11y`, `qa_code_review`, `qa_security`, `qa_performance`,
  `qa_spec_compliance`
- Méta : `schema_version`

**Scripts clés** :
- `init_console_db.py` — bootstrap idempotent
- `query_console_db.py` — read-only queries (api-gate / coverage / quality / …)
- `ingest_agent_report.py` — bridge auditor LLM → DB (parse JSON → insert → delete)

**API helper canonique (Python)** :
```python
from sdd_lib.console_db import connect, ensure_initialized, insert_event, upsert_run

ensure_initialized()
with connect() as conn:
    upsert_run(conn, run_id="abc", command="/dev-run", feat_n=1, status="running")
    insert_event(conn, event_type="phase.start", run_id="abc", feat_n=1, phase="backend")
```

**Retiré v6.10** : HTML dashboards (README.html, qa-dashboard.html), tous
les fichiers `*.json` / `*.jsonl` de stats, agent `dashboard` réduit à
`INDEX.md` des ADRs.

**Roadmap** : UI `workspace/console/` non touché, sera refactoré
ultérieurement pour lire `console.db` dynamiquement.

---

## v6.10.4 — CORS auto-injection + alias FrontendName

- `AppName` peut être déclaré comme `FrontendName` dans `stack.md` (alias
  normalisé par `sdd_lib.project_config.normalize_project_aliases()`).
- `AppNamespace`/`BackendNamespace` auto-dérivés (plus requis dans
  `## Project Config`).
- Agent `arch` STEP 4.5.6 propage automatiquement l'origin du frontend
  dev dans la config CORS backend (allowlist explicite, jamais wildcard).

---

## Pointers

- `@.claude/docs/CHANGELOG.md` — historique versions complet
- `@.claude/docs/VERSIONING.md` — politique SemVer + freeze window active
- `@.claude/docs/MIGRATION.md` — guide migration entre versions majeures
- `workspace/output/.sys/.context/adrs/ADR-2026*` — 4 ADRs governance v7.0.0 proposées (auditors-trim, config-ssot, flags-trim, prompts-trim)
