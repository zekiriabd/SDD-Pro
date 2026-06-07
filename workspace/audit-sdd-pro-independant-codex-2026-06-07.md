# Audit independant SDD_Pro - 2026-06-07

Auteur: Codex, lecture directe du framework local.

Perimetre: framework de base SDD_Pro dans `G:\Developement\Compart\New`.

Hors perimetre volontaire: rapports d'audit existants. Je n'ai pas ouvert ni
utilise les rapports deja produits comme source de conclusions. Les constats
ci-dessous viennent de la lecture du code, des manifests, des hooks, des
commandes, des agents, des stacks, de la console et des validations locales.

## Verdict executif

SDD_Pro est un framework serieux et beaucoup plus mature qu'un simple ensemble
de prompts. Les points forts sont nets:

- gouvernance par manifests (`loader.yml`, `config.base.yml`, `settings.json`);
- 12 agents specialistes bien separes;
- hooks de protection nombreux et plutot fail-closed;
- validations deterministes en Python avec une vraie suite de tests;
- console locale securisee par origine locale, CSRF, allowlist de fichiers et
  atomic writes;
- catalogues de stacks et templates coherents au niveau syntaxique.

Le principal risque produit n'est pas la securite brute: c'est l'ecart entre la
promesse "/sdd-full automatise bout-en-bout" et l'etat reel de l'orchestrateur.
Le `sdd_full_planner.py` est presente dans `commands/sdd-full.md` comme le coeur
du flux, mais il peut produire un plan qui saute les phases dev sur une FEAT
neuve, car il decide avant que les US soient generees. C'est le point a corriger
en premier.

## Validations executees

| Controle | Resultat | Lecture |
| --- | --- | --- |
| `python -m pytest` dans `.claude/python` | 1294 passed | Socle Python vert |
| `npm test` dans `workspace/console` | passed | Structure console + syntaxe serveur OK |
| `framework_smoke.py --strict` | OK=89 WARN=1 FAIL=0 | Framework global sain, warning telemetry |
| `verify_telemetry_health.py` | Verdict SUSPECT | DB lisible, mais donnees de token usage peu realistes |
| `validate_templates.py --strict` | 15 templates OK | Templates coherents |
| `validate_libs_catalog.py` | 28 catalogues OK, 3 WARN | Trois dependances pre-release |
| `validate_stack_md_headers.py` | 34 stacks OK | Headers stacks coherents |
| `validate_inline_rules.py --strict` | drift=0 missing=0 | Digests inline agents/regles synchronises |
| `validate_project_config.py --json` | PASS | Schema config OK en mode normal |
| `validate_readiness.py --feat-number 1 --json` | NO-GO | Normal: FEAT 1 sans US |
| `sdd_full_planner.py plan --feat-number 1 --json` | dev-backend/dev-frontend = skip | Defaut critique sur FEAT neuve |
| `python -m compileall -q .` | PermissionError Windows sur `__pycache__` | Risque environnement/cache, pas preuve d'erreur syntaxique |

## Findings prioritaires

### P0 - `/sdd-full` peut sauter le developpement sur une FEAT neuve

Fichiers:

- `.claude/commands/sdd-full.md`
- `.claude/python/sdd_scripts/sdd_full_planner.py`
- `.claude/python/sdd_scripts/validate_readiness.py`

Constat:

- `commands/sdd-full.md` recommande le mode wrapper via
  `sdd_full_planner.py plan`.
- `sdd_full_planner.py` lit les US existantes une seule fois au debut.
- Sur une FEAT sans US, il met `us-generate` en `pending`, mais met ensuite
  `dev-backend` et `dev-frontend` en `skip` parce que `us_files` est vide.
- `validate_readiness.py` bloque logiquement sur `US-MISSING` avant generation.

Impact CTO:

- un run client peut sembler "pilote" alors qu'il ne produit pas le code;
- la promesse concurrentielle A-to-Z est fragilisee;
- les tests unitaires ne couvrent pas assez le scenario "fresh FEAT -> US ->
  replan -> dev".

Correction recommandee:

- soit recalculer le plan apres `us-generate`;
- soit donner aux phases dev un statut `pending_after_us_generate` lorsque
  `us-generate` est pending;
- soit rendre `next-action` transactionnel: apres chaque phase terminee, il
  recharge l'etat disque avant de decider;
- ajouter un test de bout-en-bout planner sur FEAT neuve.

### P1 - Documentation et code divergent sur le statut de `sdd_full_planner.py`

Fichiers:

- `.claude/commands/sdd-full.md`
- `.claude/python/sdd_scripts/sdd_full_planner.py`

Constat:

- le script se presente encore comme "prototype runtime" non cable dans
  `/sdd-full`/`/dev-run`;
- la commande `/sdd-full` le presente comme la voie recommandee.

Impact:

- confusion mainteneur;
- risque de vendre un etat plus automatise que le code ne garantit;
- les futurs correctifs peuvent partir dans deux directions.

Correction:

- choisir une source de verite: orchestrateur Python officiel ou Markdown
  legacy;
- si Python devient officiel, mettre a jour docstring, tests et commande;
- sinon retirer la recommandation wrapper.

### P1 - Script reference mais absent: `compact_front_plans.py`

Fichiers:

- `.claude/commands/dev-plan.md`
- `.claude/docs/hooks-and-protections.md`
- `.claude/python/README.md`
- `.claude/python/sdd_lib/markdown_io.py`
- `workspace/console/README.md`

Constat:

- plusieurs fichiers referencent `sdd_scripts/compact_front_plans.py`;
- le fichier n'existe pas dans `.claude/python/sdd_scripts`.

Impact:

- code mort documentaire;
- onboarding mainteneur trompeur;
- un utilisateur qui suit la doc tombe sur une commande absente.

Correction:

- supprimer les references si la compaction a ete retiree;
- ou restaurer un wrapper minimal de compatibilite avec tests.

### P1 - Telemetrie fonctionnelle mais confiance encore suspecte

Fichiers:

- `.claude/python/sdd_admin/verify_telemetry_health.py`
- `.claude/python/sdd_hooks/record_token_usage.py`
- `.claude/python/sdd_lib/console_db/*`
- `workspace/output/db/console.db`

Constat:

- le health check trouve schema OK et DB lisible;
- verdict `SUSPECT`: au moins un run a des volumes tokens trop bas pour un vrai
  run agentique.

Impact:

- ROI, couts et benchmarks peuvent etre contestes;
- les caps de cout se basent sur une telemetrie qui doit etre impeccable.

Correction:

- marquer les donnees de test explicitement;
- separer DB demo/test et DB produit;
- ajouter un gate CI qui echoue si un baseline benchmark contient des volumes
  synthetiques non tagges.

### P1 - Resolution de racine dupliquee et moins stricte dans les hooks inline

Fichiers:

- `.claude/settings.json`
- `.claude/python/_hook.py`
- `.claude/python/sdd_hooks/block_env_bypass.py`
- `.claude/python/sdd_lib/paths.py`

Constat:

- `sdd_lib.paths._looks_like_repo_root()` exige `.claude/agents`,
  `.claude/commands` et `workspace`;
- plusieurs hooks inline dans `settings.json` remontent seulement jusqu'a un
  dossier contenant `.claude`;
- `_hook.py` et `block_env_bypass.py` ont aussi leur logique propre.

Impact:

- edge cases de monorepo ou sous-dossier `.claude` non SDD;
- comportement different entre hooks et scripts;
- surface de maintenance inutile.

Correction:

- centraliser toute resolution de racine dans `sdd_lib.paths`;
- remplacer les one-liners repetes par un launcher stable;
- ajouter tests de hooks depuis sous-dossiers et racines pieges.

### P1 - Message produit incoherent sur les stacks validees

Fichiers:

- `README.md`
- `.claude/CLAUDE.md`
- `.claude/stacks/**/*.md`

Constat:

- les headers reels donnent 34 stacks:
  - 14 `reference`;
  - 11 `bench-validated runtime`;
  - 8 `experimental`;
  - 1 `POC-only`.
- `README.md` annonce 14 reference + 19 experimental + 1 POC-only.
- `.claude/CLAUDE.md` a une lecture plus juste: 25 verts = 14 reference + 11
  bench-runtime, puis 8 experimental, 1 POC-only.

Impact:

- ambiguite marketing/CTO;
- possible survente de stacks non validees end-to-end;
- difficile de comparer proprement avec BMA DeepPlantX / AgentOS Superpower.

Correction:

- aligner README sur le tiering reel;
- afficher clairement: "validated combo end-to-end" vs "bench runtime" vs
  "reference pattern" vs "experimental".

### P2 - Config: cles non implementees ou no-op encore visibles

Fichiers:

- `.claude/config.base.yml`
- `.claude/python/sdd_scripts/validate_project_config.py`

Constat:

- plusieurs cles sont documentees comme non implementees ou no-op:
  `MaxOpusInflight`, `IntegrationTestMode`, `PlanCacheStrict`,
  `SecurityThreatModelEnabled`, certains modes perf/a11y historiques;
- `validate_project_config.py` ne signale les cles inconnues qu'avec
  `--strict-unknown`.

Impact:

- les clients peuvent croire activer une capacite qui ne s'execute pas;
- les typos de config passent en mode normal.

Correction:

- deplacer les flags futurs en section `future` ou `experimental`;
- activer `--strict-unknown` en CI;
- transformer les no-op dangereux en warnings explicites au runtime.

### P2 - Console locale solide, mais validations d'entrees perfectibles

Fichiers:

- `workspace/console/server.js`
- `workspace/console/lib/console-db.js`

Constat:

- points forts: host local strict, CSRF, Origin/Referer checks, allowlist de
  fichiers, sandbox CSP pour `/ui/*`, denylist secrets.
- points a renforcer:
  - `/api/validate` et `/api/gate-decide` acceptent des ids/commentaires sans
    regex metier assez stricte;
  - `rawSql()` retourne `[]` en cas d'erreur, ce qui masque les degradations DB;
  - certains chemins Python sont appeles en `spawnSync`, acceptable localement
    mais bloquant si la console grossit.

Impact:

- risque surtout local/operateur, pas exposition internet;
- diagnostics DB parfois trop silencieux.

Correction:

- regex et limites de longueur sur `featId`, `usId`, phase, commentaire;
- exposer un etat `degraded` au lieu de masquer les erreurs SQL;
- isoler les appels Python longs en worker si la console devient multi-user.

### P2 - Dependances prerelease dans les catalogues stacks

Fichiers:

- `.claude/stacks/fullstack/next.libs.json`
- `.claude/stacks/fullstack/nuxt.libs.json`
- `.claude/stacks/mobiles/maui.libs.json`

Constat:

- warnings de `validate_libs_catalog.py`:
  - `next-auth = 5.0.0-beta.25`;
  - `nuxt-ui = 3.0.0-alpha.10`;
  - `livecharts-maui = 2.0.0-rc4.1`.

Impact:

- risque support et reproductibilite;
- acceptable si explicitement assume comme experimental/bench.

Correction:

- documenter le risque dans chaque stack;
- preferer stable par defaut pour les combos vendus.

### P2 - Cache Python Windows: `compileall` touche des `__pycache__` non ecrivables

Fichiers:

- `.claude/python/**/*.py`
- `.claude/python/**/__pycache__`

Constat:

- `pytest` passe;
- `compileall` echoue par `PermissionError [WinError 5]` lors d'ecritures `.pyc`.

Impact:

- CI Windows ou packaging local peuvent etre instables;
- ce n'est pas une preuve d'erreur syntaxique.

Correction:

- nettoyer/regenerer les caches dans un job controle;
- ajouter `PYTHONDONTWRITEBYTECODE=1` pour les checks qui ne doivent pas ecrire;
- verifier permissions et fichiers verrouilles.

## Analyse fichier par fichier / domaine

### Racine

#### `README.md`

Role: vitrine produit et quickstart.

Etat: bon message general, positionnement ambitieux et lisible. La distinction
avec le developpement "vibe coding" est claire.

Risques:

- incoherence de comptage des stacks: 19 experimental annoncees alors que 11
  sont en fait `bench-validated runtime`;
- promesse `/sdd-full` tres forte alors que l'orchestrateur Python a encore un
  gap critique sur FEAT neuve.

Action: aligner le README avec le tiering reel et ajouter une formulation
precise: "C1/C2 end-to-end; autres stacks bench-runtime ou reference pattern".

#### `README.en.md`

Role: version anglaise.

Etat: a synchroniser avec le README francais apres correction des tiers. Je n'ai
pas fonde de finding specifique dessus.

Action: traiter comme doc derivee, jamais comme source de verite.

#### `bootstrap.py`

Role: initialisation stdlib du workspace, choix combo C1-C5, generation de
`stack.md`, options install/smoke.

Etat: robuste et pragmatique. Bons points: secrets locaux generes, pas de
dependance Python externe, mode force/auto-init.

Risques:

- C3-C5 restent soumis a gating `SDD_ALLOW_UNTESTED_COMBO` selon l'etat exact
  du combo;
- la promesse interactive/non-interactive doit rester alignee avec les combos
  reellement validates;
- la generation de secrets est positive, mais il faut verifier qu'aucun exemple
  ne les imprime dans les logs.

Action: afficher explicitement le niveau de validation du combo choisi au
bootstrap.

#### `bootstrap.ps1`

Role: wrapper Windows.

Etat: utilitaire, pas un centre de risque observe.

Action: garder comme wrapper mince; eviter d'y dupliquer de la logique.

#### `mkdocs.yml`

Role: documentation.

Etat: utile pour publier. Le risque principal est la synchronisation entre docs
et code, pas MkDocs lui-meme.

Action: faire passer les validations de docs avant release.

### `.claude/CLAUDE.md`

Role: entree systeme pour l'agent, index des agents, commandes, stacks et modes.

Etat: structure solide. Les comptes de stacks y sont plus corrects que dans le
README: 25 verts dont 14 reference + 11 bench-runtime, 8 experimental, 1 POC.

Risques:

- gros document de pilotage: s'il diverge, tout l'ecosysteme derive;
- il reference beaucoup de docs, donc besoin d'un check de liens/consistance.

Action: faire de `CLAUDE.md` la source de verite produit, puis regenerer les
sections README.

### `.claude/loader.yml`

Role: manifest des lectures/ecritures autorisees, budgets, legacy refs.

Etat: bon manifest de gouvernance. Il encadre les agents et evite les lectures
accidentelles larges.

Risques:

- certaines annotations de cache sont annoncees pour v7.1, donc pas encore
  executoires;
- plusieurs chemins historiques restent references par compatibilite.

Action: separer clairement "runtime actif" et "roadmap/compat".

### `.claude/config.base.yml`

Role: configuration par defaut du framework.

Etat: complet et central.

Risques:

- flags no-op ou non implementes encore visibles;
- un client peut croire que `IntegrationTestMode` ou `MaxOpusInflight` changent
  le runtime alors que les commentaires indiquent une implementation future ou
  partielle.

Action: rendre les futurs flags explicitement experimentaux et visibles dans
`sdd-status`.

### `.claude/settings.json`

Role: permissions Claude Code, deny/allow commands, hooks.

Etat: tres bon durcissement global: protection framework, lint pre-write,
budget agents, couts, combos, telemetry, ownership, acceptance gates, smoke.

Risques:

- duplication massive du one-liner Python;
- resolution de racine plus faible que `sdd_lib.paths`;
- maintenance difficile si un hook change de signature.

Action: remplacer les one-liners par `python .claude/python/_hook.py module`
ou une entree CLI stable, en reutilisant `sdd_lib.paths`.

### Agents `.claude/agents/*.md`

Fichiers:

- `po.md`
- `arch.md`
- `dev-backend.md`
- `dev-frontend.md`
- `qa.md`
- `code-reviewer.md`
- `security-reviewer.md`
- `spec-compliance-reviewer.md`
- `arch-reviewer.md`
- `adversarial-reviewer.md`
- `constitutioner.md`
- `elicitor.md`

Etat: les 12 agents canoniques existent, les references Agent detectees ne
pointent pas vers des agents absents, et `validate_inline_rules.py --strict`
est vert.

Lecture prompt engineering:

- bonne separation des roles: PO/Arch/Dev/QA/Review;
- bons garde-fous contre la lecture excessive;
- agents reviewer volumineux mais utiles pour le controle qualite;
- risque de "prompt entropy" a surveiller: plus les agents grossissent, plus il
  faut de tests de comportement et de digests.

Actions:

- conserver 12 agents canoniques, ne pas recreer de variantes strictes;
- ajouter des tests golden sur sorties attendues pour PO, arch, dev et review;
- mesurer tokens par agent apres le fix telemetry.

### Commandes `.claude/commands/*.md`

#### `sdd-full.md`

Role: orchestrateur principal.

Etat: fonctionnel conceptuellement, mais trop long et en transition vers
Python.

Risque majeur: voir P0. La commande fait confiance a un plan statique qui peut
etre faux apres generation des US.

Action: finir la migration vers un orchestrateur Python vraiment stateful.

#### `dev-run.md`

Role: orchestration arch + dev hors pipeline complet.

Etat: riche, mais encore tres Markdown/procedure.

Risque:

- logique operationnelle difficile a tester integralement;
- divergence possible avec `run_dev_phase.py` et `phase_planner.py`.

Action: extraire les decisions runtime dans Python et garder Markdown comme
wrapper lisible.

#### `dev-plan.md`

Role: plan de dev.

Etat: utile, mais references mortes a `compact_front_plans.py`.

Action: nettoyer ou restaurer le script.

#### `us-generate.md`

Role: generation US par PO.

Etat: coherent comme commande interne. Le blocage vient surtout de
l'orchestrateur qui doit replanifier apres son execution.

Action: s'assurer que la completion de cette commande invalide/recharge le plan.

#### `arch-init.md`, `dev-backend.md`, `dev-frontend.md`, `qa-generate.md`

Role: wrappers vers agents et scripts de validation.

Etat: scope clair.

Risque: depends du respect strict des outputs contractuels par les agents.

Action: maintenir des fixtures minimales par stack pour detecter les drifts.

#### `sdd-review.md`

Role: aggregation reviewers.

Etat: bonne logique de review post-code.

Risque: volumetrie token et dedup findings a surveiller.

Action: continuer a tester `sdd_review.py`, garder les reviewers actifs par
config.

#### `sdd-poc.md`

Role: pipeline rapide POC.

Etat: bien marque comme non-prod.

Risque: le stack `fullstack/node-react` est correctement POC-only, mais une
documentation ancienne peut encore le faire paraitre plus general.

Action: garder les bannieres POC obligatoires.

#### `feat-*`, `sdd-bootstrap.md`, `sdd-status.md`, `sdd-serve.md`,
`sdd-kill-server.md`, `doc-refresh.md`, `sdd-profile.md`,
`sdd-discover-stack.md`

Etat: utilitaires utiles, pas de defaut critique observe.

Action: garder ces commandes minces et testees par scripts deterministes.

### Regles `.claude/rules/*.md`

Fichiers:

- `build-and-loop.md`
- `dev-shared-preflight.md`
- `error-classification.md`
- `error-classification-legacy.md`
- `library-and-stack.md`
- `output-protocol.md`
- `ownership.md`
- `quality.md`

Etat: gros point fort du framework: elles transforment les agents en workflow
industrialisable.

Risques:

- `error-classification.md` est volumineux; il doit rester synchronise avec les
  scripts qui emettent les codes;
- presence de legacy utile mais potentiellement confuse;
- si les regles deviennent plus longues que les agents, le cout token augmente.

Action: maintenir les digests inline et ajouter une table machine-readable des
codes erreur.

### Stacks `.claude/stacks`

Etat global:

- 34 stacks detectees;
- headers valides;
- catalogues libs valides avec 3 warnings prerelease.

Lecture CTO:

- la granularite des stacks est un avantage competitif;
- il faut eviter de melanger "bench-runtime" et "end-to-end /sdd-full".

Par domaine:

- `backend/*`: patterns riches; Node/FastAPI/.NET/Kotlin bien documentes.
- `frontend/*`: React/Vue/Angular/Blazor riches; attention aux details
  runtime deja notes dans headers.
- `fullstack/*`: Next/Nuxt/Blazor/Kotlin Mustache/Angular Universal en
  bench-runtime; `node-react` POC-only correctement marque.
- `mobiles/*`: React Native, MAUI, Kotlin Android utiles; certains targets non
  testes sans device/toolchain.
- `qa/*`: bonne couverture de frameworks de test.
- `ui/*`: shadcn, vuetify, radzen clairs.
- `auth/*`: auth-local et Azure AD riches; verifier que les secrets restent
  hors logs.
- `archi/*`: DDD/MVC/microservice utiles; bien garder "un service" comme scope
  pour microservice.

Action: publier une matrice de maturite distincte des headers Markdown:
`end_to_end`, `bench_runtime`, `reference_pattern`, `experimental`, `poc_only`.

### Python admin `.claude/python/sdd_admin`

Etat:

- `framework_smoke.py` apporte un vrai controle transversal;
- validateurs templates/stacks/catalogues utiles;
- outils d'audit/cleanup coherents.

Risques:

- `verify_telemetry_health.py` signale encore `SUSPECT`;
- `sync_stack_md.py` et assimilables doivent etre utilises avec prudence pour
  eviter du churn doc.

Action: rendre le warning telemetry bloquant pour une release GA.

### Python hooks `.claude/python/sdd_hooks`

Etat:

- `protect_framework.py`: protection framework presente; la suite actuelle
  passe;
- `block_env_bypass.py`: bon verrou contre bypass runtime;
- `pre_write_lint.py`: garde-fou utile;
- `preflight_agent_budget.py`: controle agent budget/agents retires;
- `preflight_cost_cap.py`: controle cout run/per-US;
- `preflight_stack_combo.py`: empeche combos invalides/untested;
- `record_token_usage.py`: essentiel pour ROI;
- `validate_*` hooks: bons gates contracts/acceptance/stack.

Risques:

- racine projet dupliquee;
- `preflight_cost_cap.py` depend de la fiabilite telemetry;
- certains comportements fail-open/fail-warn doivent etre documentes par mode
  CI vs interactif.

Action: centraliser root resolution et ajouter tests integration hooks depuis
la CLI reelle.

### Python libs `.claude/python/sdd_lib`

Etat:

- `paths.py`: bonne source de verite stricte;
- `layered_config.py`: fusion base/team/project claire;
- `project_config.py`: parsing stack central;
- `atomic_write.py` / `file_locks.py`: bonne base concurrency;
- `console_db/*`: schema et acces DB bien separes;
- `stack_validator.py`: controle combos utile;
- `markdown_io.py`: parseur utile mais contient references a l'ancien compact
  front plans;
- `run_id.py`, `checkpoint.py`: indispensables pour resume/idempotence.

Risques:

- la securite-down de `layered_config.py` protege surtout project vs team; un
  projet peut toujours relacher des defaults base si aucune policy team ne les
  verrouille;
- `console_db` doit eviter les erreurs silencieuses cote Node.

Action: formaliser une policy team obligatoire pour usages pro.

### Python scripts `.claude/python/sdd_scripts`

Etat global: c'est le vrai moteur deterministe du produit.

Fichiers critiques:

- `sdd_full_planner.py`: priorite P0, rendre stateful.
- `phase_planner.py`: bon planner reviewers; heuristiques a tester par stack.
- `run_dev_phase.py`: utile pour batch/API gate; lit certains parametres du
  `stack.md` brut, a aligner avec layered config.
- `validate_readiness.py`: gate fort, correctement bloquant.
- `validate_project_config.py`: bon, mais `--strict-unknown` devrait etre CI.
- `validate_stack_combo.py`: essentiel pour maturite stacks.
- `gate_decide.py` / `record_gate_decision.py`: bonne symetrie console/pipeline.
- `sdd_state.py`: base d'etat importante; a garder comme SSoT runtime.
- `validate_*`, `ingest_*`, `report_*`: utiles pour QA/ROI/audit.

Code mort/incoherence:

- absence de `compact_front_plans.py` malgre references.

Action: concentrer la roadmap technique sur l'orchestrateur Python et la
telemetrie, pas sur de nouveaux agents.

### Tests `.claude/python/tests`

Etat:

- 1294 tests passent;
- bonne couverture de scripts, hooks, config, DB, planner, gates.

Manques:

- test frais "FEAT sans US -> plan -> us-generate -> replan -> dev pending";
- tests de hooks avec root resolution piegee;
- test de non-regression sur references de scripts absents;
- test de maturite README vs headers stacks.

Action: ajouter ces quatre familles avant prochaine release taggee.

### Console `workspace/console`

#### `server.js`

Role: API locale Fastify et securite console.

Etat: bon niveau local: host local strict, Origin/Referer, CSRF nonce,
allowlists, deny secrets, CSP sandbox.

Risques: validations d'ids et erreurs DB silencieuses a renforcer.

#### `app.jsx`

Role: UI React de la console.

Etat: volumineux mais structure smoke OK.

Risque: fichier de 80KB, evolution difficile sans modularisation.

Action: extraire composants par vues quand le produit se stabilise.

#### `styles.css`

Role: style console.

Etat: coherent pour un cockpit interne.

Action: garder sobre; priorite a lisibilite et densite.

#### `lib/atomic-write.js`

Role: write atomique status/gates.

Etat: bon miroir Node du locking Python.

Action: conserver avec tests concurrence.

#### `lib/console-db.js`

Role: acces DB lecture/ecriture gate decision.

Etat: pragmatique; fallback Python utile.

Risque: `rawSql()` masque les erreurs en retournant `[]`.

Action: retourner `{ degraded: true, errorCode }` cote API.

#### `lib/explain.js`

Role: explication LLM des fichiers allowlistes.

Etat: securise par allowlist amont.

Risque: verifier periodiquement disponibilite du modele Anthropic configure.

Action: exposer le modele et l'etat API dans `/api/health`.

#### `lib/markdown-filter.js`

Role: extraction Markdown FEAT/US.

Etat: simple et utile.

Risque: parsing fragile si les titres changent.

Action: lier aux templates ou utiliser un parseur Markdown structure.

#### `package.json`, `tests/structure.smoke.test.js`

Etat: smoke test utile et rapide.

Action: ajouter tests API sur `/api/file`, `/api/validate`, `/api/gate-decide`.

#### Artefacts console

- `workspace/console/node_modules`: dependances, hors source.
- `workspace/console/.certs`: certificats dev; verifier qu'ils restent dev-only.
- `workspace/console/console.db`: fichier 0 octet local, artefact.
- `workspace/console/status.json`: etat runtime, pas code source.

### Templates `.claude/templates`

Etat: `validate_templates.py --strict` vert.

Action: les garder comme schema contractuel des agents; ajouter un check de
round-trip avec les parseurs Markdown.

### CI `.github/workflows/sdd-ci.yml`

Etat: le depot dispose d'une logique CI, et les validateurs locaux sont
executables.

Risque: si CI ne force pas `--strict-unknown`, des typos config passent.

Action: ajouter explicitement:

- `validate_project_config.py --strict-unknown`;
- test absence de references a scripts inexistants;
- test coherence README tiers vs headers stacks;
- scenario planner FEAT neuve.

### Workspace exemples

Fichiers:

- `workspace/input/feats/*`
- `workspace/output/*`

Etat: donnees d'exemple et artefacts de runs.

Constat: FEAT 1 est NO-GO en readiness car pas d'US generees, ce qui est
normal pour un input brut mais revele le bug du plan statique.

Action: separer exemples demo, fixtures tests, et sorties runtime.

## Code mort ou references mortes

1. `compact_front_plans.py` reference mais absent.
2. Cles config no-op/deprecated visibles: `PlanCacheStrict`,
   `SecurityThreatModelEnabled`, modes perf/a11y historiques.
3. Mentions legacy d'anciens agents/flags: utiles pour migration, mais a
   borner dans une section compatibilite.
4. Artefacts runtime (`node_modules`, DB, caches, cert dev) melanges au
   workspace: normal localement, mais a exclure clairement des audits release.

## Failles / risques securite

Niveau global: plutot bon pour un outil local de dev.

Points forts:

- denylist commandes dangereuses;
- hooks de protection framework;
- blocage des bypass env;
- CSRF et origin checks console;
- allowlist stricte de fichiers lisibles;
- refus des secrets evidents;
- atomic writes cross-language.

Risques residuels:

- root resolution non centralisee;
- endpoints console mutateurs a typer plus strictement;
- erreurs DB silencieuses cote Node;
- telemetry suspecte qui peut affecter les caps cout/ROI;
- pre-release deps sur stacks commercialisables si non signalees.

## Recommandation roadmap CTO

### Sprint 1 - Stabiliser la promesse A-to-Z

1. Fix P0 du planner `/sdd-full`.
2. Ajouter test fresh FEAT end-to-end planner.
3. Aligner docstring `sdd_full_planner.py` et `commands/sdd-full.md`.
4. Supprimer/restaurer `compact_front_plans.py`.

### Sprint 2 - Fiabiliser gouvernance et release

1. Centraliser root resolution.
2. Activer `validate_project_config.py --strict-unknown` en CI.
3. Rendre telemetry health bloquant pour release.
4. Nettoyer README tiers stacks.

### Sprint 3 - Durcir produit commercial

1. Maturite stacks publiee en matrice machine-readable.
2. Console: validation ids + degraded DB.
3. Tests API console.
4. Benchmarks separes demo/test/prod.

## Conclusion

SDD_Pro a une architecture de framework agentique credible: ce n'est pas un
simple prompt pack. Le niveau de tests et de hooks est deja au-dessus de la
moyenne. La faiblesse principale est la transition incomplete entre
orchestration Markdown et orchestrateur Python. Une fois le P0 `/sdd-full`
corrige et la telemetry rendue incontestable, le produit pourra soutenir une
promesse commerciale beaucoup plus solide.
