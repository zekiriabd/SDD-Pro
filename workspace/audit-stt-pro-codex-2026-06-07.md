# Audit independant STT Pro / SDD_Pro

Date: 2026-06-07
Auteur: Codex, lecture independante du framework
Scope: framework de base, agents, commandes, hooks, scripts Python, console locale, CI, templates, exemples de specs.

## Regle de non-contamination

Je n'ai pas ouvert les rapports d'audit/roadmap/changelog/migration deja presents. Les scans ont exclu les globs de type `docs/audit*`, `docs/roadmap*`, `CHANGELOG*` et `MIGRATION*`. Les conclusions ci-dessous viennent de l'arbre source, des tests et des checks executes pendant cet audit.

## Verdict executif

STT Pro / SDD_Pro a une base technique serieuse: le coeur Python est tres teste, le modele de workflow est explicite, les hooks de cout/securite/protection existent, la console locale a de vraies protections CSRF/Host/Origin, et la notion de configuration par couches est une bonne decision d'architecture.

Mais le framework n'est pas encore "contractuellement stable" au niveau produit. Le risque principal n'est pas un manque de code, c'est la derive entre prompts, manifests, schemas, docs, tests et scripts. Dans un framework d'agents, cette derive est critique: les agents executent du texte. Une contradiction dans `loader.yml`, un agent `.md`, une regle ou un schema devient un comportement aleatoire ou non reproductible.

Les quatre points a traiter en priorite:

1. `workspace/console` ne passe plus `npm test`: les tests attendent encore `DocMenu` et `/api/help/`, retires le 2026-06-06.
2. `AcceptanceGate.RequireE2E` est lu mais ignore dans le script effectif: la configuration promet une chose que le gate ne respecte pas.
3. `bootstrap.py` documente des exit codes d'infra mais ignore les retours d'installation/smoke; `--auto-init` ne respecte pas son propre commentaire.
4. Le mode `threat-model` est retire dans certains fichiers, mais encore decrit comme actif dans `loader.yml`, `security-reviewer.md`, `error-classification.md` et des schemas DB/historiques.

## Preuves executees

Commandes et resultats observes:

| Zone | Resultat |
| --- | --- |
| `.claude/python` | `python -m pytest` -> 1230 tests passes |
| Framework smoke | `framework_smoke.py --json` -> 87 OK, 2 WARN, 1 FAIL |
| Smoke fail | `smoke-timing`: 1574 ms > seuil 1500 ms |
| Inline rules | 1 drift suspect: `po.md` vs `ownership.md` |
| Telemetry | `console.db` verdict `SUSPECT`, pas `POLLUTED` |
| Console tests | `npm test` -> FAIL |
| Console syntax | `node --check server.js` et `node --check lib/*.js` -> OK |
| Console health | serveur local OK via requete Node HTTPS, `/api/health` -> 200 |
| Curl Windows | `curl -k` Schannel echoue avec `SEC_E_NO_CREDENTIALS` sur le certificat local |

## Findings prioritaires

### P0-1 - La console ne passe plus ses tests

Fichiers:

- `workspace/console/tests/structure.smoke.test.js:25`
- `workspace/console/tests/structure.smoke.test.js:56`
- `workspace/console/app.jsx:214`
- `workspace/console/server.js:705`
- `workspace/console/README.md:40`

Constat:

- Le test attend encore le composant `DocMenu`.
- Le test attend encore une reference a `/api/help/`.
- `app.jsx` indique que `DocMenu` et `DocPage` ont ete retires le 2026-06-06.
- `server.js` indique que `/api/help/:id` a ete retire le 2026-06-06.
- Le README console mentionne encore `help/` rendu par `/api/help/*`.

Impact:

- `npm test` echoue.
- Si la CI execute ce test, la console bloque la livraison.
- Si la CI ne l'execute pas, elle laisse passer une regression contractuelle.

Correction recommandee:

- Choisir explicitement: soit restaurer `DocMenu` et `/api/help/:id`, soit mettre a jour `structure.smoke.test.js` et `README.md`.
- Ajouter un test API negatif/verifie: `/api/help/foo` doit retourner 404 si le retrait est volontaire.

### P0-2 - `AcceptanceGate.RequireE2E` est un faux contrat

Fichiers:

- `.claude/python/sdd_scripts/validate_acceptance.py:49`
- `.claude/python/sdd_scripts/validate_acceptance.py:66`
- `.claude/python/sdd_scripts/validate_acceptance.py:161`
- `.claude/python/sdd_scripts/validate_acceptance.py:300-309`
- `.claude/rules/quality.md:417-433`
- `.claude/settings.json:325`

Constat:

- Le script lit `AcceptanceGate.RequireE2E`.
- Le script ajoute quand meme une failure "RequireE2E unmet" pour les projets UI sans script E2E.
- La valeur lue n'est pas appliquee au check.
- Si plus de 8 projets existent sous `workspace/output/src`, le script tronque les projets via `iterdir()` au lieu d'echouer ou de demander `--projects`.
- La regle qualite presente `AcceptanceGate.RequireE2E` comme un vrai levier.

Impact:

- Une config `AcceptanceGate.RequireE2E: false` peut encore echouer.
- En multi-projets, certains projets peuvent ne pas etre verifies selon l'ordre filesystem.
- Le framework perd de la credibilite car une cle de gouvernance ne gouverne pas.

Correction recommandee:

- Utiliser `require_e2e` avant d'ajouter la failure.
- Trier les projets par nom.
- Si `len(projects) > DEFAULT_MAX_PROJECTS` sans `--projects`, retourner un warning bloquant ou demander un scope explicite.
- Ajouter les cles `AcceptanceGate.*` au schema de config.

### P0-3 - `bootstrap.py` ignore des echecs qu'il documente

Fichiers:

- `bootstrap.py:46-51`
- `bootstrap.py:727`
- `bootstrap.py:784-791`

Constat:

- Le fichier documente `3 : INFRA_ERROR` pour echec pip/npm/file write.
- `--auto-init` est commente comme impliquant `--force` et `--skip-install`.
- Le code met `force`, mais ne force pas `skip_install`.
- `install_python_deps()`, `install_console_deps()` et `run_smoke_check()` retournent des booleens qui ne sont pas utilises.

Impact:

- Un bootstrap peut afficher ou subir un echec infra sans exit code fiable.
- En CI, `--auto-init` peut installer des deps alors que le commentaire dit l'inverse.
- La commande donne un faux sentiment de validation.

Correction recommandee:

- Si `args.auto_init`, appliquer aussi `args.skip_install = True` ou corriger le commentaire et les docs.
- Agreger les retours d'installation/smoke et sortir avec `EXIT_INFRA_ERROR` si l'un echoue.
- Ajouter des tests unitaires pour les sorties `2/3`.

### P0-4 - Mode `threat-model`: retire dans le code, encore vivant dans les prompts

Fichiers:

- `.claude/python/sdd_scripts/phase_planner.py:422-428`
- `.claude/agents/security-reviewer.md:3`
- `.claude/agents/security-reviewer.md:555-574`
- `.claude/agents/security-reviewer.md:633-680`
- `.claude/agents/arch-reviewer.md:427`
- `.claude/loader.yml:593-674`
- `.claude/rules/error-classification.md:258-306`
- `.claude/python/sdd_scripts/ingest_agent_report.py:61-75`
- `.claude/python/sdd_lib/console_db_schema.sql:264-275`

Constat:

- `phase_planner.py` desactive le mode `threat_model`.
- `security-reviewer.md` dit au debut que le mode est retire.
- Le meme agent conserve plus loin des interdictions/consignes parlant du mode `threat-model`.
- `loader.yml` decrit encore une phase 3.5 `threat-model` avec fichiers lus/ecrits.
- `error-classification.md`, `ingest_agent_report.py` et le schema DB gardent des references historiques.

Impact:

- Les agents peuvent recevoir des instructions contradictoires.
- Le planificateur et le loader ne racontent pas la meme pipeline.
- Les budgets contextuels et attendus de fichiers peuvent etre faux.

Correction recommandee:

- Separer "legacy ingestion/historique" de "pipeline active".
- Supprimer `threat-model` de `loader.yml` comme phase active.
- Garder le schema DB legacy avec commentaire explicite "historical only".
- Ajouter un test de drift qui verifie qu'aucun manifest actif ne mentionne `security-reviewer --mode threat-model`.

### P1-1 - Derive de granularite US

Fichiers:

- `.claude/config.base.yml:246-247`
- `.claude/agents/po.md:3`
- `.claude/agents/po.md:13`
- `.claude/agents/po.md:162-187`
- `.claude/commands/us-generate.md:7`
- `.claude/commands/us-generate.md:18`
- `.claude/templates/project-config.schema.json:277-340`

Constat:

- La config base fixe `UsGranularityHardCap: 10`.
- Le corps de `po.md` parle bien de cap 10.
- Le frontmatter/description de `po.md` et une ligne de `/us-generate` parlent encore d'un hard cap 6.
- `us-generate.md:18` parle ensuite du default 10.

Impact:

- L'agent PO peut etre oriente par une description obsolete.
- L'utilisateur peut croire qu'un FEAT a 7-10 US est bloquant alors qu'il est autorise.

Correction recommandee:

- Harmoniser toutes les descriptions sur `warn=6`, `hard cap=10`.
- Ajouter un test de coherence `UsGranularityHardCap` entre config, schema, agent PO et command doc.

### P1-2 - `sdd_full_planner.py` ignore la configuration par couches

Fichiers:

- `.claude/python/sdd_scripts/phase_planner.py:225`
- `.claude/python/sdd_scripts/sdd_full_planner.py:167`
- `.claude/python/sdd_scripts/sdd_full_planner.py:178-181`
- `.claude/config.base.yml:13-16`

Constat:

- `phase_planner.py` utilise `read_layered_config`.
- `sdd_full_planner.py` utilise encore `read_project_config(root, coerce=True)`.
- Il recaste quelques cles manuellement.
- `config.base.yml` documente explicitement que `read_project_config()` ignore les couches base/team.

Impact:

- La vue plan `/sdd-full` peut diverger de l'execution reelle.
- Les politiques team/base ne sont pas garanties dans ce planner.

Correction recommandee:

- Migrer `sdd_full_planner.py` vers `read_layered_config(root=root, coerce=True)`.
- Ajouter un test qui place une cle en base/team et verifie qu'elle influence le planner.

### P1-3 - Permissions Claude mieux durcies, mais encore trop larges

Fichiers:

- `.claude/settings.json:33-52`
- `.claude/settings.json:111-113`
- `.claude/settings.json:130-184`
- `.claude/settings.json:218-237`
- `.claude/python/sdd_hooks/block_env_bypass.py`
- `.claude/python/sdd_hooks/protect_framework.py`
- `.claude/python/sdd_hooks/pre_write_lint.py`

Constat:

- Le catch-all `Bash(*)` semble retire, c'est positif.
- Il reste des allow patterns destructifs larges: `rm workspace/*`, `rm -rf workspace/output/*`, etc.
- `Bash(powershell:*)` et `Bash(cmd:*)` restent tres larges.
- Les denies couvrent beaucoup de vecteurs, mais une allowlist large + denylist pattern-based reste fragile.

Impact:

- Risque de suppression legitime mais excessive dans `workspace`.
- Risque de contournement par shell imbrique ou syntaxe non prevue.

Correction recommandee:

- Remplacer les patterns `rm workspace/*` par scripts controles ou commandes ciblees.
- Restreindre `powershell:*` et `cmd:*` aux commandes effectivement necessaires.
- Ajouter tests de permissions/hook avec payloads representatifs.

### P1-4 - CI et supply-chain: certaines garanties sont molles ou non pinnees

Fichiers:

- `.github/workflows/sdd-ci.yml:154`
- `.github/workflows/sdd-ci.yml:216`
- `.claude/templates/ci-quality.github-actions.yml.template:44`
- `.claude/templates/ci-quality.github-actions.yml.template:90`

Constat:

- Ruff est en `continue-on-error: true`, et donc non bloquant.
- Le template quality installe globalement `@axe-core/cli` et `@lhci/cli` sans version.
- Le workflow utilise `curl -k` pour healthcheck. OK sous Linux CI, mais l'audit local Windows montre une incompatibilite possible avec le certificat local.

Impact:

- CI verte possible malgre lint.
- Builds moins reproductibles.
- Risque supply-chain par CLI globales non pinnees.

Correction recommandee:

- Rendre Ruff bloquant une fois baseline fixee.
- Pinner les versions npm globales, ou mieux utiliser `npm ci` + scripts locaux.
- Pour Windows docs/scripts, preferer un healthcheck Node/PowerShell HTTPS tolerant cert local.

### P1-5 - Root resolver et protection framework: bon principe, implementation a durcir

Fichiers:

- `.claude/python/sdd_lib/paths.py:111-140`
- `.claude/python/sdd_hooks/protect_framework.py:29-80`

Constat:

- La doc de `paths.py` parle d'un root strict, mais le code utilise `resolve(strict=False)`.
- Un `CLAUDE_PROJECT_DIR` invalide/non conforme est honore avec warning.
- `protect_framework.py` identifie des chemins proteges via substring `any(p in norm for p in FRAMEWORK_OWNED)`.

Impact:

- Probabilite faible en usage normal, mais c'est une faiblesse de hardening.
- Un hook de protection devrait preferer des chemins canonises et des checks relatifs exacts.

Correction recommandee:

- Corriger la doc ou le comportement.
- Pour protection, utiliser `Path.resolve()` + `relative_to()` quand possible.
- Garder le fail-open local si necessaire, mais strict par defaut en CI.

### P1-6 - Smoke framework trop sensible au timing

Fichier:

- `.claude/python/sdd_admin/framework_smoke.py`

Constat:

- Le smoke echoue uniquement car il prend 1574 ms pour un seuil de 1500 ms.

Impact:

- Flakiness probable sur machines chargees.
- Un smoke qui echoue pour 74 ms perd sa valeur comme signal produit.

Correction recommandee:

- Augmenter le seuil, ou transformer le timing en warning.
- Garder un seuil bloquant seulement pour regression nette, par exemple base historique + marge.

### P2-1 - Telemetry suspecte

Fichiers/donnees:

- `workspace/output/db/console.db`
- `.claude/python/sdd_admin/verify_telemetry_health.py`

Constat:

- DB presente, 26 tables, pas de pollution test evidente.
- Verdict `SUSPECT` car un run est sous les floors realistes de tokens.

Impact:

- Les dashboards ROI/cout peuvent etre legerement fausses.

Correction recommandee:

- Identifier le run et le taguer comme test/dev, ou nettoyer la DB locale.
- Ajouter un etat "dev_sample" si ces runs sont normaux.

## Analyse par fichier et zone

### Racine du repo

| Fichier | Role | Audit |
| --- | --- | --- |
| `bootstrap.py` | Initialisation greenfield/brownfield, combos, deps, smoke | Bon effort de CLI produit, mais fail propagation defectueuse et contrat `--auto-init` incoherent. Voir P0-3. |
| `bootstrap.ps1` | Wrapper PowerShell | Pas de fail direct detecte dans cet audit; doit rester aligne avec `bootstrap.py`. |
| `README.md`, `README.en.md` | Entree produit | A relire apres correction `threat-model`, US cap et console help pour eviter derive narrative. |
| `CONTRIBUTING.md` | Contribution | Pas de fail direct detecte. |
| `mkdocs.yml`, `requirements-docs.txt` | Documentation site | Pas de fail direct detecte; attention a ne pas publier docs stale. |

### CI et configuration globale

| Fichier | Audit |
| --- | --- |
| `.github/workflows/sdd-ci.yml` | Pipeline utile, mais lint Ruff non bloquant. Les dry-runs bootstrap passent `--skip-install`, ce qui masque le mismatch du commentaire `--auto-init`. |
| `.claude/settings.json` | Gros durcissement visible, mais allowlist encore large pour `rm`, PowerShell et cmd. Les hooks ajoutent de la defense en profondeur. |
| `.claude/config.base.yml` | Base solide pour config par couches. Attention: tout script qui reste sur `read_project_config()` ignore ce contrat. |
| `.claude/loader.yml` | Fichier a corriger rapidement: il decrit encore `threat-model` comme phase active. |
| `.claude/CLAUDE.md` | Entree agent principale; pas de fail direct, mais depend de la coherence des manifests/rules references. |

### Agents

| Fichier | Audit |
| --- | --- |
| `.claude/agents/po.md` | Agent central; drift visible entre description cap 6 et logique cap 10. |
| `.claude/agents/security-reviewer.md` | Bon retrait annonce du mode `threat-model`, mais sections plus basses gardent des consignes contradictoires. |
| `.claude/agents/arch-reviewer.md` | Mention correcte du retrait `threat-model`. |
| `.claude/agents/qa.md` | Attend l'AcceptanceGate comme contrat; ce contrat est affaibli par `validate_acceptance.py`. |
| `.claude/agents/adversarial-reviewer.md` | Bon usage de `read_layered_config` repere. Pas de fail direct dans ce passage. |
| Autres agents `.claude/agents/*.md` | Pas de fail runtime direct detecte, mais doivent etre couverts par tests de drift sur modes retires, caps, cles de config. |

### Commandes et regles

| Fichier | Audit |
| --- | --- |
| `.claude/commands/us-generate.md` | Contradiction: ligne early hard cap 6, puis default 10. |
| `.claude/commands/dev-run.md` | Mentionne le template threat-model humain; a verifier contre `loader.yml`. |
| `.claude/commands/sdd-full.md` | Commande critique; depend de `sdd_full_planner.py`, qui ignore encore config par couches. |
| `.claude/commands/sdd-review.md` | Bon signal: references a `read_layered_config`. |
| `.claude/commands/feat-validate.md` | Bon signal: references a `read_layered_config`. |
| `.claude/rules/quality.md` | Documente AcceptanceGate en detail, mais implementation effective ne respecte pas toutes les cles. |
| `.claude/rules/error-classification.md` | References `threat-model` encore presentes; clarifier legacy vs actif. |
| `.claude/rules/library-and-stack.md` | Pas de fail direct; role important dans generation stack. |
| `.claude/rules/build-and-loop.md` | Pas de fail direct detecte; couvre tests runtime. |

### Templates

| Fichier | Audit |
| --- | --- |
| `.claude/templates/project-config.schema.json` | Decrit `SecurityThreatModelEnabled` comme deprecie et `UsGranularityHardCap`; ne semble pas exposer clairement `AcceptanceGate.*`. |
| `.claude/templates/ci-quality.github-actions.yml.template` | Installs npm globales non pinnees pour axe/lhci. Risque reproductibilite/supply-chain. |
| `.claude/templates/threat-model.template.md` | Utile comme deliverable humain; ne doit pas etre confondu avec une phase agent active. |
| Autres templates | Pas de fail direct detecte; a inclure dans validation de coherence. |

### Python: librairie coeur

| Fichier | Audit |
| --- | --- |
| `.claude/python/sdd_lib/layered_config.py` | Tres bon pivot d'architecture: base/team/project. Le risque est son adoption partielle. |
| `.claude/python/sdd_lib/project_config.py` | Legacy encore necessaire; dangereux si utilise dans des scripts de gouvernance modernes. |
| `.claude/python/sdd_lib/paths.py` | Doc stricte mais comportement plus permissif avec `CLAUDE_PROJECT_DIR`. A aligner. |
| `.claude/python/sdd_lib/console_db*.py`, `.claude/python/sdd_lib/console_db_schema.sql` | Schema et helpers structurants. Les tables `threat-model` peuvent rester pour historique, mais doivent etre etiquetees legacy. |
| `.claude/python/sdd_lib/run_id.py` | Tests passes; pas de fail direct detecte. |
| `.claude/python/sdd_lib/atomic_write.py`, `file_locks.py` | Patterns sains pour ecriture atomique/verrouillage. |
| `.claude/python/sdd_lib/exit_codes.py` | A aligner avec `bootstrap.py` et les scripts qui documentent des sorties. |
| `.claude/python/sdd_lib/loader_yml.py`, `stack_validator.py`, `markdown_io.py`, `pricing.py`, `checkpoint.py`, `combos.py`, `adr_id.py` | Pas de fail direct detecte dans cet audit; couverts par suite Python globale. |

### Python: hooks

| Fichier | Audit |
| --- | --- |
| `.claude/python/sdd_hooks/protect_framework.py` | Bonne intention de protection; matching chemin a durcir. |
| `.claude/python/sdd_hooks/block_env_bypass.py` | Defense utile contre bypass `SDD_ALLOW_*`/`SDD_DISABLE_*`. |
| `.claude/python/sdd_hooks/pre_write_lint.py` | Fichier non tracke actuellement; warn-only par defaut. Bon mode adoption, mais pas un gate dur sans env strict. |
| `.claude/python/sdd_hooks/preflight_cost_cap.py` | Bon signal: utilise config par couches. |
| `.claude/python/sdd_hooks/record_token_usage.py` | Bon signal: essaie config par couches; depend de telemetry propre. |
| `.claude/python/sdd_hooks/validate_acceptance_gate.py` | Wrapper/gate depend du script acceptance; message promet correction ou `AcceptanceGate=warn`. |
| Autres hooks | Pas de fail direct observe; la suite Python passe. |

### Python: scripts

| Fichier | Audit |
| --- | --- |
| `.claude/python/sdd_scripts/validate_acceptance.py` | Defaut majeur: `RequireE2E` lu mais non respecte; scan multi-projets tronque. |
| `.claude/python/sdd_scripts/sdd_full_planner.py` | Defaut de gouvernance: ignore config par couches. |
| `.claude/python/sdd_scripts/phase_planner.py` | Bon: desactive `threat_model` et utilise config par couches. |
| `.claude/python/sdd_scripts/validate_project_config.py` | Bon signal: lit layered config. Doit couvrir `AcceptanceGate.*`. |
| `.claude/python/sdd_scripts/validate_readiness.py` | Tests passent; utilise layered config dans certaines sections. |
| `.claude/python/sdd_scripts/sdd_review.py` | Bon signal: lit `ArchReviewMode` et `ReviewFailOn` via layered config. |
| `.claude/python/sdd_scripts/ingest_agent_report.py` | Supporte encore `threat-model`; OK si legacy, a clarifier. |
| `.claude/python/sdd_scripts/query_console_db.py` | Query encore `mode='threat-model'`; OK si historique, a clarifier dans UI/docs. |
| `.claude/python/sdd_scripts/context_budget.py` | Commentaire inclut encore threat-model dans budget security-reviewer. A nettoyer. |
| `.claude/python/sdd_scripts/parse_coverage.py`, `validate_spec_compliance.py`, `detect_arch_shortcircuit.py` | Bon signal: fallback legacy mais preference layered config. |
| `.claude/python/sdd_scripts/triage_issues.py` | Utilise encore `read_project_config`; verifier si acceptable ou migrer. |
| Autres scripts | Pas de fail direct observe; suite Python globale verte. |

### Python: admin

| Fichier | Audit |
| --- | --- |
| `.claude/python/sdd_admin/framework_smoke.py` | Smoke utile mais seuil timing trop strict ou machine-dependent. |
| `.claude/python/sdd_admin/verify_telemetry_health.py` | Bon check; verdict local suspect a traiter comme hygiene donnees. |
| `.claude/python/sdd_admin/validate_templates.py` | Important pour eviter drift; devrait inclure checks threat-model/US cap/AcceptanceGate. |
| `.claude/python/sdd_admin/audit_orphans.py`, `cleanup_orphans.py`, `cache_manifest.py`, `sync_stack_md.py`, `validate_libs_catalog.py`, `validate_stack_md_headers.py` | Pas de fail direct observe; suite Python verte. |

### Console locale

| Fichier | Audit |
| --- | --- |
| `workspace/console/server.js` | Securite locale solide: Host allowlist exacte, Origin/Referer/Sec-Fetch, CSRF nonce, routes fichiers whitelist, CSP/sandbox UI. Mais tests stale, help retire, health Windows curl fragile. |
| `workspace/console/app.jsx` | UI stats/projets; `DocMenu` retire. Le test doit suivre. |
| `workspace/console/tests/structure.smoke.test.js` | Test structurel utile mais stale et faible couverture comportementale. |
| `workspace/console/README.md` | Stale sur `/api/help/*`. |
| `workspace/console/lib/atomic-write.js` | Pas de fail syntaxique; role sain. |
| `workspace/console/lib/console-db.js` | Pas de fail syntaxique; depend de DB locale saine. |
| `workspace/console/lib/explain.js` | Health signale `ANTHROPIC_API_KEY not set`, comportement attendu en local sans cle. |
| `workspace/console/lib/markdown-filter.js` | Pas de fail syntaxique; a tester avec cas path traversal et markdown hostile. |
| `workspace/console/package.json`, `package-lock.json` | `npm test` est le probleme effectif; lock present. |
| `workspace/console/index.html`, `styles.css`, logos | Pas de fail direct observe. |

### Workspace input/output

| Zone | Audit |
| --- | --- |
| `workspace/input/feats/*.md` | Specs exemples calc multi-stacks. Bon banc de regression. Un fichier Vue est modifie dans le working tree; ne pas ecraser. |
| `workspace/input/stack/stack.md` | Ignore par git, lu comme Project Config runtime. C'est normal mais sensible. |
| `workspace/output/db/console.db` | Donnee locale ignoree par git; verdict telemetry `SUSPECT`. |
| `workspace/output/src/*` | Source generee non auditee comme framework de base, sauf effet indirect AcceptanceGate. |

## Codes morts ou quasi morts

| Element | Type | Action |
| --- | --- | --- |
| `/api/help/:id` | Route retiree mais encore attendue par test/README | Supprimer attentes ou restaurer route |
| `DocMenu` | Composant retire mais encore attendu | Supprimer du test ou restaurer |
| `AcceptanceGate.RequireE2E` | Cle lue mais comportement non applique | Brancher la cle dans le script |
| `bootstrap.py` return booleans install/smoke | Chemins d'erreur ignores | Agreger et retourner exit 3 |
| `threat-model` phase agent | Retire du code mais present prompts/manifests | Nettoyer actif vs legacy |
| `read_project_config()` dans scripts modernes | Legacy necessaire mais source de divergence | Migrer les scripts de gouvernance |

## Failles et risques securite

1. Allowlist Bash encore large (`rm`, PowerShell, cmd). Pas une faille exploitable seule, mais surface inutile.
2. Resolver root permissif via `CLAUDE_PROJECT_DIR` non conforme honore avec warning.
3. Hooks de protection chemin par substring, pas par canonicalisation stricte.
4. CI quality template installe des CLIs globales non pinnees.
5. Console locale est bien protegee contre web externe, mais certains endpoints de mutation (`/api/validate`, `/api/gate-decide`) doivent etre couverts par tests anti-pollution et validation stricte d'IDs.

## Recommandations CTO

### Sprint P0: stabiliser le contrat

1. Faire repasser `workspace/console npm test`.
2. Corriger `validate_acceptance.py` pour respecter `RequireE2E`.
3. Corriger `bootstrap.py` pour propager les echecs et clarifier `--auto-init`.
4. Nettoyer `threat-model` des manifests actifs.
5. Ajuster ou degrader en warning le seuil `framework_smoke` timing.

### Sprint P1: eliminer la derive agents/config

1. Migrer `sdd_full_planner.py` vers `read_layered_config`.
2. Harmoniser `UsGranularityHardCap` partout.
3. Ajouter `AcceptanceGate.*` au schema.
4. Ajouter tests de drift: mode retire, cap, cles config, endpoints console.
5. Rendre Ruff bloquant apres baseline.

### Sprint P2: industrialisation

1. Renforcer tests console: API security, path traversal, CSRF, mutation status, markdown hostile.
2. Pinner CLIs quality ou les passer en deps locales.
3. Durcir `settings.json` en scripts controles plutot que wildcards destructifs.
4. Nettoyer/etiqueter telemetry dev.
5. Ajouter golden tests de prompts agents: chaque agent doit etre coherent avec `loader.yml`, schemas et scripts.

## Conclusion

Le framework a un vrai potentiel produit: la structure d'agents, les gates, la console, les stacks et la telemetry forment deja un systeme coherent. Le niveau de tests Python est excellent. Le probleme a corriger maintenant est la coherence operationnelle: ce que les prompts promettent, ce que les schemas autorisent, ce que les scripts executent, ce que les tests attendent et ce que la CI bloque doivent redevenir une seule source de verite.

En tant que CTO, je ne classerais pas STT Pro comme "fragile"; je le classerais comme "bon moteur, gouvernance de contrat a resserrer". Une fois les P0 traites, le produit sera beaucoup plus credible face a des frameworks concurrents d'agents de generation applicative.
