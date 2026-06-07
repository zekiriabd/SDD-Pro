# Audit CTO consolidé — SDD_Pro v7.0.0 GA

> **Auditeur** : Claude Opus 4.7 (1M ctx) — 6 agents IA indépendants en lecture directe des sources (aucun rapport pré-existant consulté).
> **Date** : 2026-06-07 (jour du tag GA).
> **Périmètre couvert** : 12 agents, 20 commandes, 8 règles, 47 docs, 34 stacks + 26 `.libs.json`, 16 templates, 9 ADRs, ~80 scripts Python (sdd_scripts + sdd_hooks + sdd_admin), 88 tests, `loader.yml`, `settings.json`, `CLAUDE.md`.
> **Méthode** : audit indépendant + cross-checks par grep exhaustif + comparaison concurrentielle web (SuperPowers / BMAD / Agent OS).
> **Volume** : ~420 findings cités (file:line quand possible).

---

## 0. Executive Summary (lecture DSI — 90 secondes)

| Question | Verdict |
|---|---|
| **SDD_Pro est-il prod-ready au sens DSI strict (banque, secteur régulé) ?** | ❌ **Non en l'état**, ✅ **Oui sur 2 combos restreints** (C1/C2) après correction des 15 Critical. |
| **Le tag « v7.0.0 GA 2026-06-07 » reflète-t-il la maturité réelle ?** | ⚠️ **Non** — c'est un **alpha déguisé en GA** sur 11 des 13 combos annoncés. Les 2 combos vraiment validés tournent en réalité depuis 1 mois. |
| **Est-il supérieur à SuperPowers / BMAD / Agent OS ?** | **Techniquement oui** sur 5 dimensions critiques (gates, audit, sécurité, stack catalog, taxonomie d'erreurs). **Commercialement non** (0 ⭐ vs 48 k–220 k, mono-IDE, verbosité 3-10× supérieure). |
| **Est-il vendable à un Tech Architect / DSI senior aujourd'hui ?** | ⚠️ **Pas en l'état — risque de rejet en 5 minutes** sur audit acheteur (chiffres marketing non auditables, LICENSE absente, BENCH-REPORT inexistant). |
| **Combien de sprints pour atteindre 8/10 (vendable propre) ?** | **3-5 sprints** (6-10 semaines) — Critical + 30 Major + nettoyage 1 100 lignes mortes. |
| **Note globale produit** | **6.5/10** (cf. décomposition §11) |

### Verdict 1-ligne pour le commercial

> SDD_Pro est le framework spec-driven techniquement le plus rigoureux du marché en 2026, mais il sort en GA avec un emballage qui ne tient pas un audit DSI sérieux : chiffres marketing inexacts, fichier de preuve bench inexistant, LICENSE manquante. Corrigez les 15 Critical en un sprint et il devient défendable face à BMAD pour la cible compliance/audit.

---

## 1. Méthodologie d'audit (transparence)

6 audits indépendants ont été lancés en parallèle, **sans accès aux rapports d'audit pré-existants** (`workspace/audit-*.md` interdits) :

| ID | Agent | Périmètre | Findings |
|---|---|---|---|
| R1 | Expert prompts agentiques | 12 agents + 20 commands + loader.yml | 57 (7 C / 20 M / 25 m + 5 forces + 5 red flags) |
| R2 | Staff engineer Python | ~80 scripts + 88 tests + sdd_lib | 85 (3 C / 41 M / 20 m + 4 candidats suppr.) |
| R3 | Architecte doc/règles | 8 rules + 47 docs + 9 ADRs | 140 (5 C / 20 M / 20 m + 8 promesses non-tenues + 3 ADRs orphelins) |
| R4 | Expert stacks full-stack | 34 stacks + .libs.json + templates + combos | 74 (11 C / 24 M / 15 m) |
| R5 | Expert refactoring/cleanup | dead code chase exhaustif | 3 suppressions sûres + 3 bugs réels + 4 archives |
| R6 | Product manager + analyse concurrentielle web | Comparaison SuperPowers / BMAD / Agent OS | tableau /110 + verdict niche |

Chaque audit a cité des `file:line` précis. Les findings ci-dessous sont consolidés (dédupliqués + classés par impact business pour un DSI).

---

## 2. Top 15 Critical (bloquants pour vente DSI)

Classés par **risque de rejet acheteur** en cas d'audit en 5 minutes.

### CRIT-1 — Fichier de preuve bench `BENCH-GLOBAL-REPORT.md` **n'existe pas sur disque**
*R4:CRIT-1. Référencé 4× comme SSoT (validated-combos.md:36, combos.json:2, benchmarks/known-gaps.md:4, CLAUDE.md §6).*

`workspace/output/qa/bench/` n'existe **pas**. Aucun rapport, aucun hash, aucune métrique reproductible pour les 11 combos `bench-validated runtime`. La promesse "13 combos SLA" est **non auditable**. Un acheteur DSI demande "montrez-moi le run C7 (kotlin+vue)" → impossible.

**Risque** : pertes immédiate de crédibilité commerciale + risque juridique sur SLA.md.

### CRIT-2 — Spring Boot **4.0.x** doc vs **3.3.5** catalogue (stack qui n'existe pas en GA)
*R4:CRIT-2. kotlin-spring-boot.md:20,76,225,965 ≠ kotlin-spring-boot.libs.json:17.*

Le `.md` documente **Spring Boot 4 + Kotlin 2.3 + Spring Security 7** — qui n'existent **pas** en GA au 2026-06-07 (Spring Boot 3.5 LTS courant). Le `.libs.json` pin 3.3.5 (correct). Tout dev-backend qui suit le `.md` génère du code Spring 4 → STOP runtime.

### CRIT-3 — `radzen-blazor` versionné **5.5.7** ET **10.2.3** dans deux catalogues (10.x **n'existe pas**)
*R4:CRIT-3. ui/radzen-blazor.libs.json:11 vs frontend/blazor-webassembly.libs.json:12.*

Le combo C1 (validated reference) repose sur une version **hallucinée** (Radzen 10.x latest réel ≈ 6.x). Arch installe l'une OU l'autre selon ordre de chargement. **La preuve d'or v7.0.0 est cassée**.

### CRIT-4 — "13 combos SLA" est un comptage **trompeur** (réel : 2 + 23 ou 2 + 11)
*R3:C1, R4:MAJ-2.*

- CLAUDE.md §6 : "13 combos SLA = 2 validated + 11 bench-validated"
- `validated-combos.md §1.3` : "**23 combinaisons** bench"
- `combos.json:10` : `totalSlaCombos: 13`

Trois SSoT, trois chiffres. La promesse contractuelle SLA est **non auditable arithmétiquement**. Un DSI compte en 5 minutes : impossible à expliquer.

### CRIT-5 — "**174 classes d'erreur**" non vérifiable (4 chiffres distincts trouvés)
*R3:C4. error-classification.md:14, intro vs quick-ref vs détail.*

L'intro dit 174, quick-ref somme à 174, détail des tables somme à 175, total avec legacy = 179, grep unique sur le fichier principal = 152. Quatre chiffres pour la **même promesse**, répétée dans 5 docs commerciaux (CLAUDE.md, WHY-SDD-PRO ×2, getting-started FR+EN, README FR+EN). Le test CI annoncé "enforced gate" soit n'existe pas, soit ne valide qu'un seul axe.

### CRIT-6 — LICENSE Apache 2.0 **promise mais absente**
*R3:P1. WHY-SDD-PRO.md:116.*

> "Licence | Apache 2.0 (à publier sur tag v7.0.1)"

Aucun fichier `LICENSE` à la racine du repo. Un DSI bancaire ne peut pas évaluer un outil OSS sans LICENSE — c'est **bloquant pour onboarding juridique**.

### CRIT-7 — `next-auth 5.0.0-beta.25` en CORE — viole `library-and-stack.md §0` (LTS-only)
*R4:CRIT-4. next.libs.json:33,65.*

Pre-release en CORE sans ADR `runtime-prerelease-exception`. `validate_libs_catalog.py` aurait dû bloquer → soit le script ne couvre pas ce champ, soit la règle est silencieusement enfreinte par le mainteneur lui-même. Symétrique : `livecharts-maui 2.0.0-rc4.1` (CRIT-5 R4) + `react-pdf` major incohérent.

### CRIT-8 — `bcryptjs` **deprecated upstream 2025** en path auth-local Node prod
*R4:CRIT-7. node-express.libs.json:29, node-react.libs.json:51.*

Le mainteneur dcodeIO a flagué `bcryptjs` deprecated en 2025 (favoriser `bcrypt` natif). C'est 10× plus lent → poussera les Tech Lead à baisser `cost factor` → **fenêtre brute-force**. Dette sécurité directe sur le path par défaut Node.

### CRIT-9 — Drift `msal-browser` cross-frontend (React 5.10.1 vs Vue/Angular 3.27.0)
*R4:CRIT-8. react.libs.json:40 vs vue.libs.json:22, angular.libs.json:20.*

Même combo Azure AD → 2 versions OIDC différentes selon le frontend. msal-browser v4 GA depuis Fév 2025, aucun stack aligné.

### CRIT-10 — Classes `[SEC_ENV_VAR_FORBIDDEN]` et `[SEC_CORS_MISSING]` **documentées mais agent ne les émet jamais**
*R1:C2. error-classification.md §1.11 vs security-reviewer.md §5.1-§5.10.*

Le quick-ref taxonomie annonce 23 classes `[SEC_*]` + 8 hard-blocking. L'agent LLM en couvre **21**. Les 2 autres ne sont scannées par aucun code → faux positif marketing sur la couverture sécurité OWASP.

### CRIT-11 — Combos `bench-validated` contiennent **composants `experimental`** (logique max-severity cassée)
*R4:MAJ-3,4,5. combos.json:229 (auth-local exp), C3-C13 tier bench-validated.*

`combos.json` déclare `levelPriority` "max-severity wins" mais **8 des 11 combos bench-validated** contiennent au moins 1 composant `experimental` (auth-local, vuetify, python-pytest, angular-jasmine). Le combo *devrait* être downgradé à `experimental`. Le validateur ne le fait pas → contradiction logique interne.

### CRIT-12 — `dev-backend` agent : `archiPattern` fallback non implémenté en cas d'absence stack.md
*R1:C4. dev-backend.md:120-148 STEP 3.bis.*

L'agent SKIP silencieusement le chargement archi si `archiPattern == null`. Pour back-front avec backend, la doc dit "MVC défaut" mais le défaut n'est implémenté nulle part. → drift vs DDD/microservice clients.

### CRIT-13 — `/sdd-full` référence un `STEP 5.5` qui **n'existe pas**
*R1:C5. sdd-full.md:269,281-289 → grep "## STEP 5.5" = 0 hit.*

`should-skip-step --target STEP_5_5` route fallback vers RUN → en mode `--resume`, le skip post-QA ne fonctionne jamais. Bug silencieux, le pipeline reprend toujours du début.

### CRIT-14 — `/sdd-full --no-validate` **bloqué** par anti-cumul depuis v7.0.0
*R1:C7. sdd-full.md:455-456 vs STEP 1.bis:195-231.*

Le flag legacy `--no-validate` est compté dans `BYPASS_COUNT` cumulé avec `--force` → `[FORCE_CUMUL_REJECTED]`. Pour bypass légitime il faut `SDD_ALLOW_FORCE=1` env var **non documenté** dans `--no-validate`. Usage CLI standard impossible sans connaissance occulte.

### CRIT-15 — Agent `po` : contradiction tools frontmatter ↔ corps (post-mortem v7.0.0 partiel)
*R1:C1. po.md:5 (tools include Bash) vs po.md:237-238 (corps affirme "pas Bash").*

Le pattern hook+sentinel `resolve_us_hash_sentinel.py` est construit pour contourner une contrainte **fausse** (l'agent *peut* appeler Bash via frontmatter). Si on corrige le frontmatter pour retirer Bash, le STEP 8.5 read-back casse. Décision architecturale à trancher.

---

## 3. Top 30 Major (problématiques mais contournables)

### Famille A — Cohérence cross-fichiers (R1+R3+R4)

| # | Finding | Source |
|---|---|---|
| M-A1 | Loader.yml `cache_layer` annotations en **3 formats différents** (dict, comment, path composite non parsable) | R1:M2, loader.yml:144,624 |
| M-A2 | C1 contradictoire : SLA.md dit Blazor+Radzen, validated-combos.md dit React+Shadcn | R3:C2 |
| M-A3 | kotlin-android **downgradé aujourd'hui** à `🟡 scaffold-validated` (5e tier non documenté CLAUDE.md §6) | R3:C3, R4:MAJ-1 |
| M-A4 | CLAUDE.md §6 annonce 14 reference, réel 13 (kotlin-android downgrade non propagé) | R4:MAJ-1 |
| M-A5 | WORKING-AGREEMENT.md référence un `CLAUDE.md §11` qui n'existe pas | R3:C5 |
| M-A6 | output-protocol : range `[CONSTITUTION]` 32-36% chevauche `[DEV-BACKEND]` 32-58% (monotonicité cassée) | R1:C3 |
| M-A7 | Quick-ref §0 vs détail §1.2/§1.3/§1.5 désynchronisés (25 vs 24, 13 vs 14, 7 vs 8) | R3:M6 |
| M-A8 | `[DONE/POC]` émis par sdd-poc mais non listé dans output-protocol §3 | R1:m8 |
| M-A9 | Mapping `--manual-gates=us\|plan\|...` côté CLI vs `afterUS\|afterPlan\|...` côté `gate_decide.py` non aligné | R1:M6 |
| M-A10 | `feat-validate --post-dev` flag invoqué par /sdd-full mais non défini dans feat-validate.md STEP 1 | R1:M10 |

### Famille B — Stacks / libs drifts (R4)

| # | Finding | Source |
|---|---|---|
| M-B1 | Angular doc 19 vs bench 18 vs marché 20 (1 LTS de retard) | R4:MAJ-6 |
| M-B2 | react-native triple-drift Expo 52/56 + RN 0.76/0.81 | R4:MAJ-7 |
| M-B3 | EF Core 9.0.4 sur stack ciblant .NET 10 (justification Npgsql 9 preview à re-vérifier après 7 mois) | R4:CRIT-6 |
| M-B4 | MAUI net9.0 vs combo .NET 10 (doc contradictoire) | R4:MAJ-8 |
| M-B5 | `node-express` ne contient pas package `config` cité par auth-local.md → `[STACK_LIBRARY_MISSING]` runtime | R4:MAJ-9 |
| M-B6 | Express 4.21.2 (EOL branche, Express 5 GA Oct 2024) sans ADR `stay-on-4` | R4:MAJ-10 |
| M-B7 | `jspdf 2.5.2` (vue) — patché 3.0.1 pour CVE-2025-30097 ReDoS | R4:CRIT-9 |
| M-B8 | `archi/microservice.md` 445 lignes "hors SLA jusqu'à ADR" mais consommé par 3 backends | R4:MAJ-17 |
| M-B9 | `archi/ddd.md` 250 lignes pseudo-YAML sans code concret (combo C2 validated en hérite) | R4:MAJ-14 |
| M-B10 | `auth/azure-ad.md` 984 lignes mais peu d'exemples Vue/Angular (combos C7/C8 incomplets) | R4:MAJ-16 |

### Famille C — Python engine (R2)

| # | Finding | Source |
|---|---|---|
| M-C1 | **Triple-implémentation `find_repo_root`** dont 2 utilisent la version "bug post-mortem 2026-05-21" | R2:M6 |
| M-C2 | **Quintuple-implémentation `iso_now`** au lieu d'importer `sdd_lib.paths` | R2:M7 |
| M-C3 | **22 scripts sans aucun test** dont `framework_smoke.py` (763 LOC, le smoke runner lui-même) | R2:M9 |
| M-C4 | **8 transgressions exit codes** non documentées (`return 4/5` en dur) | R2:M10-M17 |
| M-C5 | **11 fonctions >100 LOC** dont 4 >200 LOC (`framework_smoke.main()` 535L, `validate_readiness.main()` 514L) | R2:M18-M28 |
| M-C6 | **README.md python obsolète x2.6** (annonce 29 fichiers, réel 76 ; 4 hooks vs 13 réels ; exit codes pré-v7.0.0) | R2:M29-M32 |
| M-C7 | **7 broad except** qui avalent silencieusement (faux PASS, traces perdues) | R2:M33-M39 |
| M-C8 | Coverage `fail_under=60` framework vs `CoverageMin=80` imposé aux user projects (auto-application laxiste) | R2:m18 |
| M-C9 | 215 `noqa E402` = 69 `sys.path.insert` hacks → absence d'install packagé `pip install -e .` | R2:M40 |
| M-C10 | Dead code prouvé : `sdd_admin/rotate_audit_logs.py` (173 LOC, **mensonge actif** dans `record_token_usage.py:338`) | R2:M1 |

---

## 4. Minor (résumé — ~80 findings)

- **STEP numbering chaotique** : `/sdd-full` contient STEP 1.bis, 1.ter, 1.gates, 1.gate-proc, 3.bis, 3.5, 3.6, 3.6.quart, 3.7, 4.bis, 4.45, 4.5, 4.7, 4.8, 4.9. Illisible pour un nouvel arrivant.
- **Mix verdict canonique (PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED) vs legacy (GREEN/YELLOW/RED)** — migration non terminée, double champ persisté.
- **30+ commentaires inline "v7.0.0-alpha audit MAJ-X"** qui polluent les prompts LLM (archéologie internalisée).
- **CHANGELOG.md = 2 479 lignes**, surcharge cognitive, à segmenter.
- **4 entry-points doc qui s'entrecroisent** : README.md, README.en.md, getting-started.md, getting-started.en.md, CLAUDE.md, cookbook.md, quickstart.md — un nouveau Tech Lead ne sait pas où entrer.
- **Cookbook "10 minutes" prend 30 min documentées** (M2 R3).
- **WHY-SDD-PRO claim "12 agents + 5 reviewers" lu = 17, réel = 12** (les 5 sont inclus dans 12).
- **3 chiffres distincts pour "51 scripts" / "64 scripts+hooks" / "196 python"** — choisir UN canonique.
- **Templates orphelins** : `explain-po.prompt.md` (annotation CHANGELOG fausse — il EST utilisé par `workspace/console/lib/explain.js`), `bench-feats/` (scope interne mal isolé).
- **3 ADRs orphelins** (0 référence externe) : `runtime-sts-prerelease-exceptions`, `secrets-config-ssot-stack-md`, `sprint-2026-06-07`.
- **Slug ADR `…sprint-2026-06-07-execu`** = 7 mots / 40 chars (viole "max 5 mots" ownership.md §3.2).
- **`[QA]` label couvre 2 plages disjointes** (58-66 API Gate + 78-88 tests unit) — illisible en log.
- **Vocabulaire `Tech Lead` (×35) vs `DSI` (×3) vs `Architecte` (×2)** — clarification cible commerciale.

---

## 5. Code mort / orphans (R5 — synthèse)

### À supprimer immédiatement (P0, risque nul)
| Fichier | Volume | Raison |
|---|---:|---|
| `.claude/scheduled_tasks.lock` | 1 L | sessionId mort, runtime stale |
| `.claude/docs/audit-2026-06-06-roadmap.md` | 316 L | superseded par ADR-20260606T222017 |
| Section §6 `error-classification-legacy.md` | ~15 L | méta-audit auto-référentiel "consultable via git log" |

### À corriger (P0, bugs réels)
| Bug | File:Line | Fix |
|---|---|---|
| Path-drift dans hint d'erreur | `audit_orphans.py:184` | `sdd_scripts/cleanup_orphans.py` → `sdd_admin/cleanup_orphans.py` |
| Annotation CHANGELOG fausse | `CHANGELOG.md:2127` | `explain-po.prompt.md` est utilisé, pas orphelin |
| Drift doc vs code | `poc-roi-methodology.md:144` | "À créer bench_run.py" alors qu'il existe |

### À archiver (P2, scripts dormants)
- `sdd_scripts/dispatch_fixes.py` (360 L, "phase B v7.2") + `tests/test_dispatch_fixes_unit.py`
- `sdd_admin/migrate_exit_codes.py` (refactor one-shot achevé)
- `sdd_scripts/migrate_us_v1_to_v2.py` (migration v6→v7 achevée)

### Volumétrie totale nettoyable
- **Immédiat (P0/P1)** : ~330 lignes / 2-3 fichiers
- **Avec archive dormants** : ~1 100 lignes / 5-7 fichiers
- **Gain maintenance estimé** : 2-4 h/mois

---

## 6. Sécurité (synthèse cross-audits)

### ✅ Forces sécurité

- **Aucun** `shell=True`, `eval`, `exec`, `pickle.load`, `os.system` dans le moteur Python (R2)
- **Path traversal** verrouillé par regex `_SAFE_PROJECT_NAME` (validate_acceptance.py:89)
- **Atomic writes** pour artefacts critiques (`sdd_lib/atomic_write.py`)
- **Untrusted content discipline** documentée dans `build-and-loop.md §3.bis bullet 4`
- **Taxonomie OWASP** complète (23 classes `[SEC_*]` + STRIDE threat-model mode)

### ⚠️ Risques sécurité résiduels

| Risque | Source |
|---|---|
| **`bcryptjs` deprecated** dans path Node prod | R4:CRIT-7 |
| **`jspdf 2.5.2` CVE-2025-30097** | R4:CRIT-9 |
| **`next-auth 5.0.0-beta.25`** prerelease en CORE | R4:CRIT-4 |
| **`livecharts-maui 2.0.0-rc4.1`** prerelease | R4:CRIT-5 |
| **2 classes `[SEC_*]` non scannées** par security-reviewer | R1:C2 |
| **Mockup HTML untrusted** lu sans sanitization deterministe (prompt injection théorique) | R1:M20 |
| **Hook `block_env_bypass.py` non documenté** (audit-friendly = "deviner") | R1:m15 |
| `_hook.py:39` re-implémentation **moins stricte** de `find_repo_root` (bug post-mortem 2026-05-21 récurrent) | R2:C1 |

**Verdict sécurité** : 7/10. Forte intention + bonnes fondations, mais 4 libs avec dette sécurité dans les catalogues officiels = signal négatif sur la discipline de maintenance des `.libs.json`.

---

## 7. Architecture (synthèse pondérée)

### Forces architecturales (rares dans l'industrie LLM-coding)

1. **Source-first discipline systématique** — la substance vit dans des MD lisibles, pas dans du Python opaque. ADR `principles/source-first.md` appliqué (anti-derive, plan v2, rule consolidation).
2. **File ownership matrix + LibName lock O_EXCL** — `ownership.md §1` rend le parallélisme N agents *safe by construction*.
3. **Plan v2 strict-ready avec `us-hash` SHA-256** — idempotence cross-run + détection staleness. Pattern « spec → executable artifact ».
4. **Externalisation déterministe vers Python** — `validate_readiness.py`, `parse_coverage.py`, `sdd_review.py`, etc. = 0 token LLM sur la logique critique. 88 tests pytest sur la couche déterministe.
5. **Taxonomie d'erreurs `[CLASS]`** load-bearing pour 4 systèmes (YAML patterns, tests enforcement, fix dispatcher, sécurité tooling CWE-level). Inhabituel à ce niveau de granularité.

### Faiblesses architecturales

| # | Faiblesse | Impact |
|---|---|---|
| F1 | **Sur-ingénierie défensive** : sentinels disque + double-gates + STEP 3.6.quart "defense-in-depth no-op" + cache_control v7.1 prévus non câblés | Bus factor élevé, onboarding > 1 semaine |
| F2 | **Numérotation chaotique** (`3.6.quart`, `1.gate-proc`, `4.45`) | Lecture impossible pour nouvel arrivant |
| F3 | **Mono-IDE Claude Code** = vendor lock-in Anthropic | Si Anthropic change pricing/policy, framework inutilisable |
| F4 | **Engagement commercial vs périmètre testé** : 34 stacks affichés, 2 vraiment validés | Risque dérive marketing à la prochaine release |
| F5 | **Couplage faible loader.yml ↔ agents** : `cache_layer` annotations en 3 formats, `{Project}` placeholder non résolu, sub-docs lazy non tracés | `context_budget.py` ne peut pas être déterministe |

---

## 8. Comparaison concurrentielle (R6)

### Tableau /110 (notes /10)

| Critère | **SDD_Pro** | SuperPowers | BMAD | Agent OS |
|---|:---:|:---:|:---:|:---:|
| Maturité release | **4** (J0 GA) | 9 | 9 | 7 |
| Communauté (⭐) | **1** (0 ⭐) | 10 (~200 k) | 9 (48,7 k) | 5 (4,8 k) |
| Cible utilisateur claire | **6** (DSI niche) | 9 | 9 | 7 |
| Verbosité (moins = mieux) | **3** (le plus lourd) | 8 | 5 | 9 |
| Support stacks (catalogues) | **9** | 3 | 6 | 4 |
| Support sécurité (OWASP) | **9** | 2 | 3 | 1 |
| Support tests (coverage+API gate) | **9** | 7 | 6 | 2 |
| Support audit (trail+ADRs+DB) | **9** | 2 | 3 | 2 |
| Multi-IDE | **2** (Claude only) | 10 (7 IDE) | 8 (4 IDE) | 7 (3 IDE) |
| Prix / modèle économique | **5** (ambigu) | 10 | 10 | 8 |
| Honnêteté positionnement | **9** (KNOWN-LIMITATIONS solide) | 6 | 7 | 8 |
| **TOTAL /110** | **66** | **76** | **75** | **60** |

### Réponse à la question utilisateur : SDD_Pro est-il supérieur ?

**Réponse honnête : DÉPEND DE LA CIBLE.**

#### ✅ SDD_Pro est SUPÉRIEUR à SuperPowers / BMAD / Agent OS si on évalue :
1. **Rigueur des gates** (seul framework qui peut *refuser* une livraison)
2. **Audit trail** (console.db SQLite + ADRs versionnés + 174 classes)
3. **Stack catalog machine-readable** (`.libs.json` versionnés vs `expansion packs persona` de BMAD)
4. **Sécurité OWASP** intégrée (23 classes `[SEC_*]` + hard-blocking)
5. **Spec-compliance AC-by-AC** indépendante du rapport `dev-*`

#### ❌ SDD_Pro est INFÉRIEUR si on évalue :
1. **Adoption** (0 ⭐ vs 48 k–220 k chez concurrents)
2. **Verbosité / onboarding** (10× SuperPowers, 3× BMAD)
3. **Multi-IDE** (mono-IDE Claude Code)
4. **Maturité communautaire** (pas de tutoriels tiers, Stack Overflow vide)
5. **Maturité produit** (J0 de GA vs ≥ 8 mois pour les autres)
6. **Démo CEO-friendly** (personas Mary/Winston/Sally chez BMAD vs `po/arch/dev-backend` austère)

#### Verdict opérationnel pour Tech Architect français
> Pour un Tech Architect dans une **banque française avec contrainte DORA/NIS2/RGPD article 22** : **mettre SDD_Pro en short-list** + POC parallèle BMAD sur 1 FEAT en combo C2 (Kotlin+React+shadcn).
>
> Pour une **startup / ESN générique** : prendre **BMAD ou SuperPowers**, pas SDD_Pro.
>
> Pour une **équipe Go / Rust / PHP / Ruby** : attendre v8 (pas supporté).

---

## 9. Promesses commerciales vs réalité (R3)

8 promesses critiques pour la vente DSI dont la vérification factuelle échoue :

| # | Promesse | Vérification | Statut |
|---|---|---|---|
| P1 | Apache 2.0 publié sur tag v7.0.1 | LICENSE absent | ❌ Non tenue |
| P2 | 174 classes `[CLASS]` cross-agent | 4 chiffres distincts (152/174/175/179) | ❌ Non auditable |
| P3 | 13 combos SLA — 2 validated + 11 bench-validated | 11 = stacks comptés comme combos, réel 2 + 23 combinaisons | ❌ Non auditable |
| P4 | Cost cap $50/run, $15/US | Existe en config, prouvé sur 1 run seulement (n=1) | ⚠️ Partielle |
| P5 | Idempotence + resume `--resume` | Vrai sur C1/C2, faux sur 11 bench-validated (scaffolding manuel mainteneur) | ⚠️ Partielle |
| P6 | Coverage seuil bloquant | Vrai mais pas d'historique (overwritten chaque run) | ⚠️ Partielle |
| P7 | ROI ~5×-8× plus rapide | 1 PoC unique (n=1), extrapolation | ❌ Non prouvé |
| P8 | Multi-IDE roadmap v8 | "Roadmap envisageable mais non engagée" | ⚠️ Promesse molle |

### Verdict marketing/DSI

> En lecture acheteur DSI (5 minutes), **5 des 8 promesses commerciales centrales s'effondrent**. C'est le **point unique le plus dangereux** du dossier de vente actuel. À corriger AVANT toute démo client sérieuse.

---

## 10. Note globale + décomposition

### Synthèse des notes par périmètre

| Périmètre auditeur | Note /10 | Justification courte |
|---|:---:|---|
| R1 — Agents + commands | **6.5** | Rigueur exceptionnelle + sur-ingénierie défensive |
| R2 — Python engine | **7.0** | Solide mais README obsolète + 22 scripts sans test |
| R3 — Règles + docs | **6.5** | Couverture exhaustive + arithmétique cassée sur promesses |
| R4 — Stacks + templates | **5.5** | Système intelligent + drifts version + BENCH-REPORT inexistant |
| R5 — Code mort / hygiène | **8.0** | Très peu de dead code réel, hygiène acceptable |
| R6 — Position concurrentielle | **6.5** | Niche défendable mais adoption 0 |

### **Note finale produit : 6.5/10**

#### Pourquoi pas 8/10 ?
- **−0.5** : 15 Critical findings — toute promesse commerciale auditable casse en 5 min (CRIT-1 BENCH inexistant, CRIT-4 13 combos faux, CRIT-5 174 classes faux, CRIT-6 LICENSE absente).
- **−0.5** : Verbosité ~10× SuperPowers, ~3× BMAD — onboarding > 2 jours minimum.
- **−0.3** : Mono-IDE Claude Code (vendor lock-in fort).
- **−0.2** : 0 ⭐ vs 48 k–220 k concurrents (signal d'adoption nulle).

#### Pourquoi pas 4/10 ?
- **+0.5** : 5 différenciateurs techniques **réels** (gates, audit, security, stack catalog, taxonomie) qu'aucun concurrent ne combine.
- **+0.3** : Doc `KNOWN-LIMITATIONS.md` + `validated-combos.md` **brutalement honnêtes** (rare).
- **+0.2** : Architecture mature (source-first, ownership matrix, plan v2 idempotent).

---

## 11. Roadmap de remédiation priorisée

### Sprint 1 (1-2 semaines) — Critical commerciaux (rendre vendable)

| P | Action | Effort | Impact |
|:---:|---|---:|---|
| P0 | Ajouter `LICENSE` Apache 2.0 à la racine | 5 min | Débloque eval juridique DSI |
| P0 | Générer **réellement** `BENCH-GLOBAL-REPORT.md` avec preuves hash pour les 13 combos, OU retirer le claim "13 combos SLA" | 2-3 j | Débloque audit acheteur |
| P0 | Réconcilier "13 combos" / "23 combinaisons" / "11 bench" partout (CLAUDE.md, SLA.md, validated-combos.md, WHY-SDD-PRO.md) | 1 j | Débloque comptage DSI |
| P0 | Trancher chiffre "174 classes" : refaire arithmétique pour intro+quickref+détail+test CI matchent | 1 j | Promesse devient auditable |
| P0 | Fixer CRIT-2 (Spring Boot 4 doc vs 3.3.5 libs) + CRIT-3 (radzen 5.5.7 vs 10.2.3) | 2 j | Combos C1 vraiment vérifiables |
| P0 | Bumper `bcryptjs` deprecated → `bcrypt` natif ou `@node-rs/argon2` (2 stacks Node) | 1 j | Élimine dette sécurité bloquante |
| P0 | Bumper `jspdf 2.5.2 → 3.0.1` (CVE-2025-30097) | 30 min | Élimine CVE active |
| P0 | Ajouter `[SEC_ENV_VAR_FORBIDDEN]` + `[SEC_CORS_MISSING]` au scan security-reviewer §5 | 1 j | Honore promesse 23 classes |
| P0 | Fixer 3 bugs path-drift (audit_orphans.py:184, CHANGELOG.md:2127, poc-roi-methodology.md:144) | 30 min | Élimine faux signaux |
| P0 | Supprimer `.claude/scheduled_tasks.lock` + `audit-2026-06-06-roadmap.md` | 5 min | Nettoyage trivial |

**Sortie sprint 1** : note passe **6.5 → 7.5**. Vendable propre face à BMAD pour cible compliance.

### Sprint 2 (1-2 semaines) — Major engineering

| P | Action | Effort | Impact |
|:---:|---|---:|---|
| P1 | Implémenter `validate_libs_versions_in_md.py` (cross-check `.md` ↔ `.libs.json`) | 2-3 j | Élimine futurs drifts |
| P1 | Refactor `validate_stack_combo.py` : règle "max-severity wins" effective (combo avec composant exp ≠ bench-validated) | 1 j | Élimine contradiction interne CRIT-11 |
| P1 | Refresh `python/README.md` complet (compteurs, hooks, exit codes) | 1 j | Première porte d'entrée dev correcte |
| P1 | Refactor `find_repo_root` (3 impls → 1) + `iso_now` (5 impls → 1) | 1 j | Élimine bug récurrent post-mortem 2026-05-21 |
| P1 | Tests minimaux pour 5 scripts critiques sans test (framework_smoke, statusline, validate_templates, validate_libs_catalog, query_console_db) | 3-4 j | Bloque régressions silencieuses |
| P1 | Documenter ou régulariser les 5 `return 4/5` non documentés exit_codes | 1 j | Convention respectée partout |
| P1 | Fixer CRIT-13 (STEP_5_5 inexistant) + CRIT-14 (`--no-validate` cassé) | 1 j | CLI utilisable sans connaissance occulte |
| P1 | Aligner output-protocol ranges (CONSTITUTION 32-36 vs DEV-BACKEND 36-58) | 30 min | Monotonicité chat-output restaurée |

**Sortie sprint 2** : note passe **7.5 → 8.0**.

### Sprint 3-5 (4-8 semaines) — Maturité long-terme

| Action | Effort |
|---|---:|
| Refactor STEP numbering (3.6.quart, 4.45, 1.gate-proc → numérotation propre) | 1 sem |
| Extraire fonctions monstres >200 LOC en helpers testables (`framework_smoke.main` 535L, `validate_readiness.main` 514L) | 1 sem |
| Migration `pip install -e .` (élimine 215 noqa E402 + 69 sys.path hacks) | 3-4 j |
| Segmentation `CHANGELOG.md` (2479 L) → CHANGELOG-v7.md + archive v6.x | 2 j |
| Fusion ou hiérarchisation des 4 entry-points (README/getting-started/quickstart/cookbook) | 2 j |
| Mode "minimal verbosity" pour CI/CD (1 update/agent au lieu de 3-6) | 3 j |
| ADR cross-refs depuis error-classification (runtime-sts), library-and-stack (secrets-stack-md) | 1 j |
| Publication OSS + dépôt marketplace Anthropic | 1 sem |
| 3 tutoriels Medium / dev.to / DSI white-paper | 2 sem |
| POC réel client externe (combo C1 ou C2) avec mesure ROI sur 3 runs | 4-6 sem |

**Sortie sprint 5** : note passe **8.0 → 8.5+**. Devient un produit de référence pour la cible DSI/compliance.

---

## 12. Verdict final pour l'utilisateur

### Réponse directe à la question « SDD_Pro est-il efficace et vendable ? »

**Oui, mais pas en l'état au 2026-06-07.**

#### Ce qui est **vrai et vendable** aujourd'hui
- 2 combos C1 (.NET+React+shadcn) et C2 (Kotlin+React+shadcn) **réellement validés** depuis 1 mois
- Architecture interne **techniquement supérieure** à BMAD/SuperPowers sur 5 dimensions critiques (gates, audit, sécurité, stack catalog, taxonomie)
- Discipline source-first + ownership matrix + plan v2 idempotent = **inhabituel** dans l'industrie LLM-coding
- Documentation `KNOWN-LIMITATIONS.md` + `validated-combos.md` d'une honnêteté rare (point positif fort)

#### Ce qui **bloque la vente** aujourd'hui
1. **LICENSE Apache 2.0 absente** (bloquant DSI bancaire)
2. **BENCH-GLOBAL-REPORT.md inexistant** (la "preuve" des 11 combos bench-validated n'est pas sur disque)
3. **5 chiffres marketing centraux non auditables** en 5 min (174 classes / 13 combos / 25 stacks 🟢 / 64 scripts/hooks / coût ROI 5×-8×)
4. **Stack Spring Boot 4 documenté** alors qu'il **n'existe pas en GA**
5. **Stack Radzen 10.2.3 inventé** alors que latest réel ≈ 6.x
6. **bcryptjs deprecated** dans path Node prod par défaut
7. **0 ⭐ vs 48 k–220 k concurrents** — signal d'adoption nulle qu'aucun DSI ne peut ignorer

#### Plan d'action commercial recommandé (mes 5 actions prioritaires)
1. **NE PAS faire de démo client DSI cette semaine** — risque trop élevé d'audit-killer en 5 min
2. **Exécuter le Sprint 1 (≤ 2 semaines)** — 10 actions P0 → note passe 6.5 → 7.5
3. **Publier OSS + soumettre Marketplace Anthropic** dès tag v7.0.1 avec LICENSE
4. **Identifier 1 client pilote bienveillant** (réseau Tech Lead francophone, banque ou assurance) pour POC C1 ou C2 mesuré
5. **Rédiger 1 white-paper DSI** ciblé compliance (DORA/NIS2/RGPD art. 22) — c'est LE positionnement défendable, pas "concurrent généraliste de BMAD"

### Comparaison nette aux concurrents

| Question | Réponse 1-mot |
|---|---|
| Supérieur à **SuperPowers** ? | Sur la cible DSI/audit/compliance : **OUI**. Sur l'adoption / multi-IDE / simplicité : **NON**. |
| Supérieur à **BMAD-Method** ? | Sur les gates déterministes / sécurité OWASP / audit trail : **OUI**. Sur l'adoption / personas / maturité communautaire : **NON**. |
| Supérieur à **Agent OS** ? | Sur le pipeline complet end-to-end / stacks pré-validés : **OUI** largement. Sur la simplicité / brownfield-first : **NON**. |

### Cible vraie de SDD_Pro

✅ **Tech Architect / DSI dans secteur régulé** (banque, assurance, santé, secteur public) avec contrainte audit DORA/NIS2/RGPD article 22, équipe 5-20 devs, projets internes from-scratch, stacks .NET / Kotlin / Node / Python.

❌ **PAS pour** : devs solos, startups vélocité, équipes Go/Rust/PHP/Ruby, projets brownfield majoritaires, multi-IDE imposé.

---

## 13. Annexes — fichiers rapports détaillés

Les 6 rapports d'audit indépendants sont conservés dans `G:\tmp\` (~85 KB total) :

- `/tmp/audit-r1-agents-commands.md` — 57 findings agents+commands
- `/tmp/audit-r2-python.md` — 85 findings Python engine
- `/tmp/audit-r3-rules-docs.md` — 140 findings rules+docs
- `/tmp/audit-r4-stacks-templates.md` — 74 findings stacks+templates
- `/tmp/audit-r5-deadcode.md` — chasse code mort + bugs
- `/tmp/audit-r6-competitors.md` — comparaison concurrentielle détaillée

Pour le commit dans le repo, recommandation : déplacer sous `workspace/audits/2026-06-07-audit-CTO-consolide/` (cf. R5:E "naming non-canonique").

---

*Rapport consolidé livré 2026-06-07. Audit indépendant, sans complaisance. La sévérité des findings vise à servir le produit — pas à l'enterrer. Les 15 Critical sont tous corrigibles en 1-2 sprints, et le delta technique vs concurrents reste l'atout principal défendable de SDD_Pro pour la cible niche DSI/compliance.*
