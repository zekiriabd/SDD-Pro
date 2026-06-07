# Pourquoi SDD_Pro ? — Argumentaire CTO / DSI

> Document commercial v7.0.0 GA (2026-06-07). Compare SDD_Pro aux 6 frameworks
> agentiques majeurs du marché (Cursor, Aider, Devin, BMAD, Superpowers, AgentOS).
> Objectif : aider un Tech Lead, CTO ou DSI à arbitrer entre frameworks pour
> son organisation.

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
par une classe d'erreur dans une taxonomie de 174 préfixes `[CLASS]`.

---

## 2. 5 axes où SDD_Pro est objectivement supérieur

### 2.1 Gates déterministes (51 scripts Python)

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

### 2.2 Stack-awareness (34 catalogues machine-readable)

Chaque stack a un fichier `{stack-id}.libs.json` qui déclare :
- Versions LTS pinnées (anti-STS, anti-prerelease, anti-CVE)
- Libs core (installées par `arch`) + libs on-demand (triggered par capability)
- Plugins build system + manifest

Aucun concurrent ne fournit ça. BMAD a des "expansion packs" mais ce sont des
agents personas, pas des catalogues machine.

**Conséquence** : un projet généré par SDD_Pro **ne compile pas avec une lib
fantaisie trouvée sur Stack Overflow par le LLM**. Le hook
`preflight_stack_combo` refuse les combos non listés.

### 2.3 Taxonomie d'erreurs structurée (174 classes `[CLASS]`)

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
| Discovery / Élicitation | ✅ `elicitor` (5 techniques) | ❌ | ❌ | ❌ | ✅ Mary BA | ⚠️ brainstorm | ⚠️ spec shape |
| Découpage User Stories | ✅ `po` agent | ❌ | ❌ | ❌ | ✅ Sally PO | ❌ | ❌ |
| Architecture + DB scaffolding | ✅ `arch` agent | ❌ | ❌ | ❌ | ✅ Winston Arch | ❌ | ❌ |
| Code back/front parallèle isolé | ✅ ownership matrix | ❌ | ❌ | ❌ | ✅ Devon Dev | ⚠️ TDD | ❌ |
| Tests + coverage + lint | ✅ `qa` agent | ⚠️ | ⚠️ | ⚠️ | ✅ Quinn QA | ✅ TDD | ❌ |
| Code review cross-fichier | ✅ `code-reviewer` | ❌ | ❌ | ❌ | ⚠️ | ✅ inter-tasks | ❌ |
| Security review OWASP | ✅ `security-reviewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Spec compliance AC-by-AC | ✅ `spec-compliance-reviewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Architecture review | ✅ `arch-reviewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Adversarial review (opt-in) | ✅ `adversarial-reviewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 2.5 Auditabilité industrielle

- **`console.db` SQLite** : chaque run trace tokens, cost, gates, verdicts.
- **9 ADRs versionnés** documentent les décisions structurantes.
- **`run_id` par exécution** : reproductibilité cross-machine.
- **Hooks `SubagentStop`** : audit-loggué chaque sortie d'agent.
- **`workspace/output/.sys/.audit/`** : trail forensique des bypass.

Aucun concurrent ne fournit cette piste d'audit.

---

## 3. Comparaison face-à-face détaillée

| Critère | SDD_Pro v7.0.0 | Superpowers | BMAD-METHOD | AgentOS | Cursor | Aider | Devin |
|---|---|---|---|---|---|---|---|
| ⭐ GitHub | (nouveau) | 93k-150k | 48k | < 5k | (closed) | 25k | (closed) |
| Méthodologie | FEAT-driven SDLC complet | TDD RED-GREEN-REFACTOR | Personas SDLC | Standards injection | Pair programming | Pair programming | Autonomous |
| Agents | 12 spécialisés + 5 reviewers | 13 skills composables | 6 personas nommés | N/A | 1 (LLM) | 1 (LLM) | 1 (LLM) |
| Multi-IDE | ❌ Claude Code only | ✅ 7 harnesses | ✅ any LLM IDE | ✅ 4 IDEs | ✅ Cursor | ✅ CLI | ✅ web |
| Stacks pré-validés | **34 (25 🟢 + 8 🟡)** | N/A | Via expansion packs | N/A | N/A | N/A | N/A |
| Gates déterministes Python | **64 scripts/hooks** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Taxonomie d'erreurs | **174 classes** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
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
- ✅ Vous utilisez **Claude Code** (mono-IDE assumé).
- ✅ Vous valorisez **les gates bloquants** plus que la vitesse brute.
- ✅ Vous générez sur des stacks **pré-validés** (combos C1/C2 + 11 runtime).

### Choisir Superpowers si :
- ⚠️ Vous voulez du **TDD strict** RED-GREEN-REFACTOR.
- ⚠️ Vous voulez du **multi-IDE** (Codex, Gemini, Cursor, Copilot…).
- ⚠️ Vous n'avez **pas besoin de SDLC complet** — juste de l'aide au code.

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

### O3 — "Mono-IDE Claude Code, c'est un risque vendor-lockin."
Vrai. SDD_Pro est conçu pour Claude Code (hooks, agents, sub-agent tool, skills).
Si Anthropic disparaît, le framework est inutilisable. **Mitigation** :
l'essentiel de la valeur (51 scripts Python + 34 catalogues stacks + taxonomie
[CLASS]) est portable. Une porte v8 pourrait viser multi-IDE.

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

- `@.claude/docs/getting-started.md` — démarrage 30 min
- `@.claude/docs/validated-combos.md` — combos supportés SLA
- `@.claude/docs/COMPLIANCE.md` — RGPD, sécurité, audit trail
- `@.claude/docs/SLA.md` — engagement support par combo
- `@.claude/docs/KNOWN-LIMITATIONS.md` — ce que SDD_Pro ne fait PAS
- `@.claude/docs/poc-roi-methodology.md` — méthode de validation combo

---

*Document maintenu à chaque release MAJOR. Source de vérité pour le
positionnement vs concurrents. Référencé depuis README.md.*
