# Pourquoi SDD_Pro ? — Argumentaire CTO / DSI

> Document commercial v7.0.3-dev (2026-07-26). Présente la valeur de SDD_Pro
> pour les équipes tech (CTO / DSI / Tech Lead).
> Objectif : aider un Tech Lead, CTO ou DSI à arbitrer entre frameworks pour
> son organisation. Base GA : v7.0.0 (2026-06-07).

---

## 1. Le problème que SDD_Pro résout

**Les frameworks LLM-agentiques existants partent du code et essaient de
remonter vers la spec.** Résultat :

- Specs implicites dans le prompt, non versionnées, non auditables.
- Drift silencieux entre l'intention métier et le code produit.
- Aucune garantie de couverture des Acceptance Criteria.
- Aucune traçabilité quand le LLM "improvise" hors scope.

**SDD_Pro impose la trajectoire inverse** : FEAT (spec métier) → US (découpe)
→ Code (matérialisation gated). Chaque étape produit un artefact versionné,
chaque gate est déterministe (Python, 0 token LLM), chaque écart est tracé
par une classe d'erreur dans une taxonomie de **193 classes** `[CLASS]`.

---

## 2. 6 axes où SDD_Pro est objectivement supérieur

### 2.1 Gates déterministes (80 scripts Python, 0 token)

| Gate | SDD_Pro | Cursor | Aider | Devin | BMAD | Superpowers | AgentOS |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Readiness gate FEAT | ✅ `feat-validate` | ❌ | ❌ | ❌ | ⚠️ manuel | ❌ | ⚠️ manuel |
| API Gate back↔front in-memory | ✅ bloquant | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Coverage seuil bloquant | ✅ `CoverageMin` | ❌ | ❌ | ❌ | ❌ | ⚠️ TDD seul | ❌ |
| Acceptance Gate (test/lint/build/E2E) | ✅ post-qa hook | ❌ | ❌ | ❌ | ❌ | ⚠️ TDD | ❌ |
| Cost cap par run + par US | ✅ `MaxCostPerRun` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Force-cumul anti-bypass | ✅ hook bloquant | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Plan-then-review opt-in | ✅ gate manuel | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Conséquence** : SDD_Pro est le **seul framework à pouvoir refuser de
livrer** quand la qualité n'est pas atteinte. Les autres livrent toujours
(quitte à livrer un mauvais code).

### 2.2 Stack-awareness (30 catalogues machine-readable)

Chaque stack a un fichier `{stack-id}.libs.json` qui déclare :
- Versions LTS pinnées (anti-STS, anti-prerelease, anti-CVE)
- Libs core (installées par `arch`) + libs on-demand (triggered par capability)
- Plugins build system + manifest

Aucun concurrent ne fournit ça. BMAD a des "expansion packs" mais ce sont des
agents personas, pas des catalogues machine.

**Conséquence** : un projet généré par SDD_Pro **ne compile pas avec une lib
fantaisie trouvée sur Stack Overflow par le LLM**. Le hook
`preflight_stack_combo` refuse les combos non listés.

### 2.3 Taxonomie d'erreurs structurée (193 classes `[CLASS]`)

Chaque erreur du pipeline porte un préfixe canonique
(`[BUILD_CORRECTIBLE]`, `[QA_COVERAGE_GAP]`, `[SEC_SQL_INJECTION]`,
`[FILE_OWNERSHIP_NESTED]`, etc.) permettant :

- Décision mécanique de `build_loop` (itérer vs fail-fast).
- Dashboard automatique par cause-racine.
- Post-mortem comparable cross-projet.
- Parité tooling sécurité CWE-level (Snyk/Semgrep/CodeQL).

Aucun concurrent n'a ce niveau de granularité. BMAD a des messages d'erreur
en prose libre.

### 2.4 SDLC complet (FEAT → US → arch → back → API gate → front → QA → review)

| Phase | SDD_Pro | Cursor | Aider | Devin | BMAD | Superpowers | AgentOS |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Discovery / Élicitation | ✅ `elicitor` (15 techniques) | ❌ | ❌ | ❌ | ✅ Mary BA | ⚠️ brainstorm | ⚠️ spec shape |
| Découpage User Stories | ✅ `po` agent | ❌ | ❌ | ❌ | ✅ Sally PO | ❌ | ❌ |
| Architecture + DB scaffolding | ✅ `arch` agent | ❌ | ❌ | ❌ | ✅ Winston Arch | ❌ | ❌ |
| Code back/front parallèle isolé | ✅ ownership matrix | ❌ | ❌ | ❌ | ✅ Devon Dev | ⚠️ TDD | ❌ |
| Tests + coverage + lint | ✅ `qa` agent | ⚠️ | ⚠️ | ⚠️ | ✅ Quinn QA | ✅ TDD | ❌ |
| Code review cross-fichier | ✅ `code-reviewer` | ❌ | ❌ | ❌ | ⚠️ | ✅ inter-tasks | ❌ |
| Security review OWASP | ✅ `security-reviewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Spec compliance AC-by-AC | ✅ `spec-compliance-reviewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Architecture review | ✅ `arch-reviewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Adversarial review (**opt-out, actif par défaut**) | ✅ `adversarial-reviewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 2.5 Auditabilité industrielle + visibilité IDE

- **`console.db` SQLite** : chaque run trace tokens, cost, gates, verdicts.
- **Statusline IDE** : phase courante + coût cumulé + tokens visibles en temps réel
  dans la barre de statut (VSCode, JetBrains, web). Format : `SDD F2:ARCH 💰$3.2 🔢18K`.
  Fail-open, compatible tout harness.
- **15 ADRs versionnés** documentent les décisions structurantes.
- **31 invariants load-bearing déclarés** (14 forward + 17 reverse), chacun pointant
  vers son *enforcer* sur disque — un test échoue si l'enforcer disparaît.
- **`run_id` par exécution** : reproductibilité cross-machine.
- **Hooks `SubagentStop`** : audit-loggué chaque sortie d'agent.
- **`workspace/.sys/.audit/`** : trail forensique des bypass.

Aucun concurrent ne fournit cette piste d'audit ni cette visibilité IDE en temps réel.

### 2.6 Reverse engineering natif — le seul framework qui remonte l'existant

Tous les concurrents partent d'une page blanche. SDD_Pro sait aussi partir de ce
que vous avez déjà, et c'est souvent là que se trouve le budget réel d'une DSI :

| Capacité | SDD_Pro | Cursor | Aider | Devin | BMAD | Superpowers | AgentOS |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Base de données → spécifications (procédures, fonctions, vues, triggers, jobs) | ✅ **natif** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Code legacy → FEATs (escalier analyse → US → FEAT) | ✅ **natif** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Garantie de lecture seule sur la base (`readonly_guard`) | ✅ | — | — | — | — | — | — |
| Traçabilité `fichier:ligne` résolue sur disque | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Gate de confiance bloquant avant réutilisation | ✅ REVERSE-GATE | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Argument DSI.** Une base de production porte quinze ans de règles métier que
plus personne ne sait énoncer. SDD_Pro les rend sous forme de spécifications
lisibles par un PO, **sans jamais écrire dans la base** : seuls des `SELECT` de
catalogue sont émis, l'interdit est porté par la classe bloquante
`[DB_STRUCTURE_CHANGE_FORBIDDEN]` et l'invariant `reverse-db-readonly`, et le mot
de passe n'est ni loggué ni persisté.

**Argument économique.** Un routeur déterministe classe chaque objet SQL avant
tout appel LLM : les objets réellement simples (CRUD sans branche ni appel)
produisent leur User Story **mécaniquement, à coût nul** — 70 à 80 % d'un
patrimoine typique. Le budget LLM va uniquement là où il y a de la logique.

**Argument de rigueur.** Depuis 2026-08-26, une Phase 0 obligatoire
(`/sdd-db-context`) construit une compréhension globale versionnée de la base
avant tout découpage, sépare **structurellement** les faits (qui peuvent devenir
des critères d'acceptation) des hypothèses de l'architecte (qui ne le peuvent
jamais), et ordonne l'analyse **par vagues** — tout objet appelé est analysé
avant son appelant. Détail : `@.sdd/docs/reverse-engineering-workflow.md`.

> ⚠️ **Réserve annoncée** : Phase 0 et ordonnancement par vagues sont validés hors
> ligne (corpus synthétiques). Les seuils seront recalibrés après le premier run
> contre une base de production réelle. SQL Server et PostgreSQL sont live-validés ;
> Oracle et MySQL/MariaDB restent scaffold-validés.

---

## 3. Comparaison face-à-face détaillée

| Critère | SDD_Pro v7.0.0 | Superpowers | BMAD-METHOD | AgentOS | Cursor | Aider | Devin |
|---|---|---|---|---|---|---|---|
| ⭐ GitHub | (nouveau) | 93k-150k | 48k | < 5k | (closed) | 25k | (closed) |
| Méthodologie | FEAT-driven SDLC complet | TDD RED-GREEN-REFACTOR | Personas SDLC | Standards injection | Pair programming | Pair programming | Autonomous |
| Agents | **29** (13 forward dont 5 reviewers + 16 reverse) | 13 skills composables | 6 personas nommés | N/A | 1 (LLM) | 1 (LLM) | 1 (LLM) |
| Multi-harness | ✅ **Claude Code + Codex + Gemini CLI + Antigravity** | ✅ 7 harnesses | ✅ any LLM IDE | ✅ 4 IDEs | ✅ Cursor | ✅ CLI | ✅ web |
| Stacks pré-validés | **36 (28 🟢 + 8 🟡)** | N/A | Via expansion packs | N/A | N/A | N/A | N/A |
| Gates déterministes Python | **80 scripts + 20 hooks** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Taxonomie d'erreurs | **193 classes** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Statusline IDE (phase + coût + tokens) | ✅ hook natif | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Plugin marketplace (discovery IDE natif) | ✅ `plugin.json` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Idempotence + resume | ✅ `--resume` | ❌ | ⚠️ partiel | ❌ | ❌ | ❌ | ❌ |
| Cost cap | ✅ par run + par US | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ partiel |
| Audit trail SQLite | ✅ `console.db` | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ logs |
| Compliance ready | ✅ `COMPLIANCE.md` | ❌ | ❌ | ❌ | ⚠️ entreprise SaaS | ❌ | ⚠️ SaaS |
| Self-hosted | ✅ (workspace local) | ✅ | ✅ | ✅ | ❌ SaaS | ✅ | ❌ SaaS |
| Licence | Apache 2.0 (LICENSE publié 2026-06-07) | MIT | MIT | MIT | Commercial | Apache 2.0 | Commercial |
| Coût par FEAT | $15-30 (mesuré) | $5-15 (TDD only) | $20-40 (full SDLC) | $5-10 (planning seul) | $20/mois | $0.50-5/session | $500/run |

---

## 4. Quand choisir SDD_Pro vs concurrents

### Choisir SDD_Pro si :
- ✅ Vous générez des projets **complets** (back + front + DB + tests), pas du
  code spot.
- ✅ Vous voulez une **traçabilité auditable** (compliance, post-mortem,
  reproductibilité).
- ✅ Vous travaillez sur **.NET / Node / Python / Kotlin** (les 4 backends
  supportés).
- ✅ Vous utilisez **Claude Code, Codex, Gemini CLI ou Antigravity** — le pipeline
  est identique sur chaque harness (multi-harness natif depuis v7.0.2).
- ✅ Vous valorisez **les gates bloquants** plus que la vitesse brute.
- ✅ Vous générez sur des stacks **pré-validés** (combos C1/C2 + 11 runtime).
- ✅ Vous voulez **voir la phase et le coût en temps réel** dans la barre de statut
  IDE sans quitter votre éditeur.

### Choisir Superpowers si :
- ⚠️ Vous voulez du **TDD strict** RED-GREEN-REFACTOR sans pipeline FEAT/US.
- ⚠️ Vous n'avez **pas besoin de SDLC complet** — juste de l'aide au code.
- ⚠️ Votre équipe préfère les **skills composables** plutôt que les commandes orchestratrices.

### Choisir BMAD si :
- ⚠️ Vous voulez des **personas humanisées** pour la démo CEO (Mary la BA,
  Winston l'architecte).
- ⚠️ Vous travaillez sur un **domaine non-tech** (BMAD a des expansion packs
  creative-writing, healthcare).
- ⚠️ Vous **n'avez pas besoin de gates déterministes** (BMAD est 100% LLM-driven).

### Choisir Cursor / Aider si :
- ⚠️ Vous voulez du **pair-programming**, pas du pipeline.
- ⚠️ Votre **équipe est petite** et l'audit n'est pas un sujet.

### Choisir Devin si :
- ⚠️ Vous avez un **budget illimité** ($500/run accepté).
- ⚠️ Vous voulez un **agent autonome** sans superviser le détail.

---

## 5. Réponse aux objections courantes

### O1 — "Pourquoi pas juste Cursor + un bon CLAUDE.md ?"
CLAUDE.md ne **bloque rien**. Le LLM peut l'ignorer silencieusement. SDD_Pro
ajoute des hooks Python qui interrompent l'exécution si le LLM dérive
(ownership, libs non listées, cost cap, etc.). Différence essentielle :
**discipline conseillée vs discipline forcée**.

### O2 — "BMAD a 48k stars, c'est plus sûr."
Adoption ≠ qualité technique. BMAD est un **excellent framework persona-driven**,
mais aucune gate déterministe. Pour un POC créatif ou une démo, BMAD est plus
séduisant. Pour un projet industriel auditable, SDD_Pro est plus rigoureux.

### O3 — "Un seul IDE, c'est un risque de vendor lock-in."
**Plus d'actualité depuis v7.0.2.** La couche source `.sdd/` est compilée en
façades par harness : le même pipeline tourne sous **Claude Code, OpenAI Codex,
Gemini CLI et Antigravity**, et 4 providers LLM sont déclarés
(`.sdd/providers/`). Reste vrai : le socle de valeur (80 scripts Python,
30 catalogues de stacks, taxonomie `[CLASS]`, 31 invariants) est du Python et du
Markdown — **portable, lisible, sans runtime propriétaire**. Ce qui dépend du
harness, ce sont les façades de commandes, pas la logique.

### O4 — "On peut tout faire avec un bon prompt."
Empiriquement faux. Le post-mortem CMS-Back 2026-05-11 (cf.
`library-and-stack.md §B.7`) documente 5 bugs runtime que **seul un framework
avec règles disque** peut prévenir (CORS, null-strict templates,
coerce DOM number, etc.). Un prompt ne survit pas au prochain run.

### O5 — "Quel est le ROI mesuré ?"
PoC interne CMS-Back (FEAT 1 sur combo C2 kotlin+react) : **~3h de prompt
→ 2 US livrées vs ~2 jours en manuel**, soit **~5×-8× plus rapide**.
Coût observé : **$22 USD** par FEAT 2 US (combo C2, 2026-05-13).
Variance ROI à mesurer sur 3 runs supplémentaires (roadmap v7.1).

---

## 6. Cible commerciale

**SDD_Pro v7.0.0 GA** est destiné en priorité à :

1. **Tech Leads .NET / Java / Node / Python** qui veulent générer des
   features complètes auditables (pas du code spot).
2. **Directeurs de projets / DSI** qui ont besoin d'une traçabilité
   compliance-ready (cf. `COMPLIANCE.md`).
3. **Équipes orientées qualité** (TDD, security review, OWASP) plutôt
   que vitesse brute.

**Non destiné à** :
- Hackers solo qui veulent du pair-programming spot → Cursor / Aider.
- Démos commerciales avec personas humanisées → BMAD.
- Code dans des langages non supportés (Go, Rust, PHP, Ruby → roadmap v8).

---

## 7. Liens

- `@.sdd/docs/getting-started.md` — démarrage 30 min
- `@.sdd/docs/validated-combos.md` — combos supportés SLA
- `@.sdd/docs/COMPLIANCE.md` — RGPD, sécurité, audit trail
- `@.sdd/docs/SLA.md` — engagement support par combo
- `@.sdd/docs/KNOWN-LIMITATIONS.md` — ce que SDD_Pro ne fait PAS
- `@.sdd/docs/poc-roi-methodology.md` — méthode de validation combo

---

*Document maintenu à chaque release MAJOR. Source de vérité pour le
positionnement vs concurrents. Référencé depuis README.md.*
