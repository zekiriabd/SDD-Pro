# Règle — Output Protocol (Executive chat output, v7.0.0)

> **Nouveau v7.0.0** : règle SSoT pour la verbosité de sortie en chat.
> Le Tech Lead voit la progression du pipeline SDD comme un **executive
> dashboard** (1 ligne par étape, label `[AGENT]` + résumé + %), pas
> comme une console terminal verbose. Les détails techniques restent
> persistés sur disque (rapports `workspace/output/qa/...`,
> `workspace/output/.sys/.audit/...`) pour debug/audit.
>
> **Load-bearing** : règle universelle chargée par les 11 agents
> (`po`, `arch`, `dev-backend`, `dev-frontend`, `qa`, `elicitor`,
> `constitutioner`, `code-reviewer`, `security-reviewer`,
> `spec-compliance-reviewer`, `arch-reviewer`) et les 10 commandes
> user-facing.

## TOC

- §1 — Principe et périmètre (qui parle au chat)
- §2 — Format canonique (1 ligne par update)
- §3 — Mapping agent → label `[AGENT]` (12 labels)
- §4 — Plages de progression par phase (anti-régression)
- §5 — Patterns interdits en chat (liste fermée)
- §6 — Patterns autorisés (résumés exécutifs)
- §7 — Erreurs : chat 1L vs disque 3L (préservation `[CLASS]`)
- §8 — Itérations `build_loop` (retry visibles, max bornes)
- §9 — Verdicts et rendu final
- §10 — Bypass `SDD_CHAT_VERBOSE=1` (debug opt-in)
- §11 — Enforcement et anti-derive

---

## 1. Principe et périmètre

### 1.1 Qui parle au chat

Le **chat** désigne la sortie texte visible par l'utilisateur dans
Claude Code (terminal, VSCode extension, web app). Tous les
producteurs de texte sont concernés :

| Producteur | Quand il parle | Verbosité avant v7.0.0 | Verbosité v7.0.0 |
|---|---|---|---|
| Claude (boucle principale) | orchestration commandes, narration step-by-step | élevée (Read X, Bash Y, …) | **executive 1L** |
| Sub-agent SDD (po, arch, dev-*, qa, auditors) | exécution STEPs internes | moyenne | **executive 1L** |
| Scripts Python (`preflight.py`, `validate_*.py`, `gate_decide.py`) | stdout/stderr JSON ou texte | bas (JSON) | inchangé (JSON sur disque) |
| Hooks (PostToolUse, SubagentStop, Stop) | feedback bloquant | bas (1L blocage) | inchangé |

### 1.2 Ce que voit l'utilisateur

Avant v7.0.0 (verbose) :
```
Let me read the FEAT file.
[Reads workspace/input/feats/1-Auth.md]
Now I'll Glob for existing US files.
[Globs workspace/output/us/1-*.md → 0 results]
Calling python .claude/python/sdd_scripts/context_budget.py --agent po --feat-number 1
{exit: 0, ledger_path: "console.db", budget_kb: 24.3}
Writing US workspace/output/us/1-1-Auth-Login.md...
[Write file: 8.2 KB]
[PO] User Story 1-1-Auth-Login.md created.
```

Après v7.0.0 (executive) :
```
[PO] Découpage FEAT en User Stories... (8%)
[PO] FEAT 1-Auth → 2 US identifiées. (12%)
```

### 1.3 Ce que ce protocole **n'impacte pas**

- **Fichiers sur disque** : rapports `workspace/output/qa/...`,
  audit logs, JSON ledgers, ADRs → format complet préservé.
- **stdout des scripts Python** quand invoqués hors orchestration
  agent (debug manuel par Tech Lead) → format inchangé.
- **Format ERROR 3 lignes** dans les rapports disque (cf.
  `error-classification.md §2`) → conservé tel quel (load-bearing
  pour `build_loop`, hooks, dashboards).

---

## 2. Format canonique

### 2.1 Update standard (1 ligne)

```
[AGENT] Action courte au gérondif... (PROGRESS%)
```

- `[AGENT]` : un des 12 labels §3, entre crochets, majuscules
- `Action courte` : 3-10 mots, verbe + objet métier (pas technique)
- `gérondif` : "Découpage…", "Implémentation…", "Validation…"
- `(PROGRESS%)` : entier 0-100, suffixe `%`, entre parenthèses
- Pas de ponctuation finale (le `%)` clôt)
- 1 ligne stricte (pas de `\n` interne)

**Exemples valides** :
```
[PO] Découpage FEAT en User Stories... (8%)
[ARCH] Bootstrap projets et scaffolding DB... (24%)
[DEV-BACKEND] Implémentation endpoints US 1-1... (48%)
[QA] Validation API Gate (tests in-memory)... (82%)
[DONE] FEAT 1-Auth livrée. (100%)
```

**Exemples invalides** :
```
[po] reading FEAT file...                    ← label minuscule, anglais, action technique
[PO] Read workspace/input/feats/1-Auth.md    ← chemin fichier interne
[PO] User Stories generated successfully!    ← pas de %, pas de gérondif
```

### 2.2 Update résultat (1 ligne, post-step)

```
[AGENT] Résultat factuel sans détail. (PROGRESS%)
```

**Exemples** :
```
[PO] 2 User Stories créées (1-1-Login, 1-2-Reset). (12%)
[DEV-BACKEND] Backend US 1-1 livré, build vert. (54%)
[QA] Coverage 82% ≥ seuil 80%, verdict 🟢. (88%)
```

### 2.3 Verdict final (1 ligne dédiée)

```
[DONE] FEAT {n}-{Name} livrée — {verdict-aggrege}. (100%)
```

Verdict agrégé : `🟢 GREEN` | `🟡 WARN` | `🔴 RED`. Pas d'autre texte
après cette ligne sauf bloc ERROR si verdict 🔴 (cf. §7).

---

## 3. Mapping agent → label `[AGENT]`

12 labels canoniques. **Aucun autre label admis** dans le chat.

| Label chat | Agent / Commande source | Phase pipeline |
|---|---|---|
| `[ANALYSIS]` | `/feat-generate` (élicitation initiale) | 1 |
| `[ELICITOR]` | agent `elicitor` (`/feat-deepen`) | 1.5 |
| `[PO]` | agent `po` (`/us-generate`) | 2 |
| `[VALIDATE]` | `/feat-validate` (Readiness Gate) | 2.6 |
| `[PLAN]` | `/dev-plan` + agents `dev-*` en mode `:plan` | 2.7 |
| `[ARCH]` | agent `arch` (`/arch-init`) | 3 |
| `[DEV-BACKEND]` | agent `dev-backend` (`/dev-backend`) | 4 |
| `[DEV-FRONTEND]` | agent `dev-frontend` (`/dev-frontend`) | 4 |
| `[QA]` | agent `qa` (`/qa-generate`) + API Gate | 4-5 |
| `[REVIEW]` | agents `code-reviewer`, `arch-reviewer`, `spec-compliance-reviewer` | 5 |
| `[SECURITY]` | agent `security-reviewer` | 5 |
| `[DONE]` | verdict final pipeline | 100% |

**Labels d'état orthogonaux** (peuvent suffixer un label agent) :

| Suffixe | Sens |
|---|---|
| `[…/FIXING]` | itération de correction en cours (build_loop, retry QA) |
| `[…/SKIP]` | step skip légitime (US frontend-only côté dev-backend, etc.) |
| `[…/WARN]` | step terminé en 🟡 (continue mais signal) |
| `[…/FAIL]` | step terminé en 🔴 (STOP) |

Exemples : `[DEV-BACKEND/FIXING]`, `[QA/WARN]`, `[ARCH/SKIP]`.

---

## 4. Plages de progression par phase

`PROGRESS%` est **monotone croissant** sur un même run pipeline.
Régression possible uniquement sur `[…/FIXING]` (retry, le % du retry
≤ % de la step initiale). Plages indicatives :

| Phase | Label dominant | Plage % |
|---|---|---|
| Analyse FEAT | `[ANALYSIS]` | 0-5 |
| Élicitation | `[ELICITOR]` | 5-8 |
| User Stories | `[PO]` | 8-12 |
| Readiness gate | `[VALIDATE]` | 12-15 |
| Planning technique | `[PLAN]` | 15-22 |
| Architecture + DB | `[ARCH]` | 22-32 |
| Backend (ALL US) | `[DEV-BACKEND]` | 32-58 |
| API Gate (in-memory) | `[QA]` (gate API) | 58-66 |
| Frontend (ALL US) | `[DEV-FRONTEND]` | 66-78 |
| QA (tests + coverage) | `[QA]` | 78-88 |
| Spec compliance + code review | `[REVIEW]` | 88-94 |
| Security review | `[SECURITY]` | 94-97 |
| Arch review + verdict consolidé | `[REVIEW]` | 97-99 |
| Verdict final | `[DONE]` | 100 |

**Pour une invocation isolée** (ex. `/dev-backend 1-1` seul, hors
`/sdd-full`), le label part à 0% et finit à 100% sur le scope local
(la step, pas le pipeline global).

---

## 5. Patterns interdits en chat

L'agent / la commande / Claude **NE DOIT JAMAIS** émettre en chat :

### 5.1 Logs et traces techniques

- Texte "Reading file...", "Opening...", "Executing bash...", "Applying patch..."
- Chemin de fichier interne en clair (`workspace/output/...`, `.claude/...`)
- Sortie `stdout`/`stderr` brute d'un script ou compilateur
- Stack traces, exceptions, JSON dumps de payloads
- Commandes bash invoquées (`python .claude/python/...`)
- Liste de fichiers Read/Edited (1 par 1)

### 5.2 Détails d'implémentation

- Noms de classes/méthodes/composants générés
- Versions de libs installées par arch
- Lignes de code, diffs, snippets
- Détail SQL des migrations
- Routes HTTP ajoutées (`POST /api/auth/login` …)

### 5.3 Métadonnées internes

- Context budget (`24.3 KB / 50 KB`)
- Tokens consommés, coûts USD
- Preflight checks (`A1 OK, A2 OK, …`)
- Cache hit/miss
- Itération de retry numérotée si interne (`build_loop iter 2/3` autorisé en `[…/FIXING]`)
- Audit logs (`legacy-parallel.log`, etc.)

### 5.4 Narration step-by-step

- "Let me check the FEAT file..."
- "I'll now generate the user stories..."
- "Done. Now moving on to..."
- Réflexions internes ("Looking at the structure, I see that...")
- Listes à puces > 3 items

---

## 6. Patterns autorisés (résumés exécutifs)

L'agent / la commande **PEUT** émettre :

### 6.1 Updates de progression (§2.1, §2.2)

1 ligne par STEP majeure (pas par sous-action). Granularité cible :
**3 à 6 updates par invocation agent**. Plus = bruit.

### 6.2 Compteurs métier

- Nombre d'US créées : `2 User Stories créées`
- Nombre d'endpoints implémentés : `5 endpoints livrés`
- Nombre de tests passés : `47/47 tests passés`
- Pourcentage coverage : `coverage 82%`
- Verdict auditeur : `🟢 GREEN`, `🟡 WARN`, `🔴 RED`

### 6.3 Identifiants métier

- Numéro FEAT : `FEAT 1-Auth`
- ID User Story : `US 1-1-Login`
- Numéro AC en cas d'erreur ciblée : `AC-3 non couverte`
- Classe d'erreur (préfixe `[CLASS]`) en cas de FAIL : `[QA_COVERAGE_GAP]`

### 6.4 Pointeurs vers les rapports disque

Quand un détail technique serait pertinent (debug Tech Lead), pointer
**1 fichier** sans le contenu :

```
[QA/FAIL] Tests échec sur US 1-2 → workspace/output/qa/feat-1/report.md. (84%)
```

Pas plus d'1 pointeur par ligne. Le Tech Lead ouvre s'il veut.

---

## 7. Erreurs : chat 1L vs disque 3L

### 7.1 Principe de séparation

| Surface | Format | Audience |
|---|---|---|
| **Chat** | 1 ligne compressée avec classe `[CLASS]` | Tech Lead (vue live) |
| **Disque** | 3 lignes `ERROR / CAUSE / FIX` complet | `build_loop`, hooks, dashboards, audit post-hoc |

### 7.2 Format ERROR en chat (1 ligne)

```
🔴 [AGENT/FAIL] {résumé} — [CLASS_PREFIX] {détail 1L} → {pointer fichier rapport}. ({PROGRESS%})
```

**Exemples** :
```
🔴 [DEV-BACKEND/FAIL] Build US 1-2 — [BUILD_BLOCKING] cycle DI détecté → workspace/output/qa/feat-1/build.md. (48%)
🔴 [QA/FAIL] Coverage US 1-1 — [QA_COVERAGE_GAP] 62% < seuil 80% → workspace/output/qa/feat-1/coverage.md. (84%)
🔴 [VALIDATE/FAIL] FEAT 1 NO-GO — [READINESS_NO_GO] 2 ACs sans Given/When/Then → workspace/output/.sys/.validation/1-readiness.md. (15%)
```

### 7.3 Format ERROR sur disque (3 lignes, inchangé)

Préservation littérale du format `error-classification.md §2` dans le
fichier rapport :

```
ERROR: dev-backend 1-2 build failed (iter 1/3)
CAUSE: [BUILD_CORRECTIBLE] missing import 'SIM.Backend.Services.IBebeService' in BebesEndpoints.cs:1
FIX: add 'using SIM.Backend.Services;'
```

Ce format **DOIT** rester intact pour que `build_loop` et les hooks
puissent parser la classe `[CLASS]`. Le chat est une **vue résumée**,
pas une substitution.

### 7.4 Verdicts intermédiaires (🟡 WARN non bloquant)

```
🟡 [QA/WARN] API Gate US 1-1 — couverture endpoints partielle (12/16) → continue. (66%)
🟡 [REVIEW/WARN] Code review FEAT 1 — 3 issues serious mais < seuil. (94%)
```

---

## 8. Itérations `build_loop` (retry visibles, bornes)

### 8.1 Format `[…/FIXING]`

Le `build_loop` peut itérer jusqu'à `BuildLoopMaxIter` (default 3).
Chaque itération **DOIT** être visible en chat (signal de coût) :

```
[DEV-BACKEND] Implémentation US 1-2 en cours... (48%)
[DEV-BACKEND/FIXING] Correction erreur compilation (iter 1/3)... (48%)
[DEV-BACKEND/FIXING] Correction erreur compilation (iter 2/3)... (48%)
[DEV-BACKEND] US 1-2 livrée, build vert. (54%)
```

Le `%` ne progresse pas pendant les retries (load-bearing : le Tech
Lead voit que le coût monte sans avancement).

### 8.2 Format échec terminal (`[BUILD_LOOP_EXHAUSTED]`)

```
🔴 [DEV-BACKEND/FAIL] US 1-2 — [BUILD_LOOP_EXHAUSTED] 3/3 iters sans convergence → workspace/output/qa/feat-1/build-us1-2.md. (48%)
```

### 8.3 Coût exceedé (`[BUILD_LOOP_COST_EXCEEDED]`)

```
🔴 [DEV-BACKEND/FAIL] US 1-2 — [BUILD_LOOP_COST_EXCEEDED] $15.30 ≥ $15 cap → STOP. (48%)
```

---

## 9. Verdicts et rendu final

### 9.1 Verdict pipeline `/sdd-full`

À la toute fin, **une seule ligne** :

```
[DONE] FEAT 1-Auth livrée — 🟢 GREEN (2 US, 47 tests, coverage 82%, 0 issue critique). (100%)
```

Si 🟡 WARN :
```
[DONE/WARN] FEAT 1-Auth livrée — 🟡 WARN (3 issues serious, voir workspace/output/qa/feat-1/sdd-review.md). (100%)
```

Si 🔴 RED :
```
[DONE/FAIL] FEAT 1-Auth — 🔴 RED, pipeline interrompu — voir workspace/output/qa/feat-1/sdd-review.md. (66%)
```

### 9.2 Rendu progression optionnel (UI extension)

Si le harness affiche une barre de progression dédiée (VSCode
extension, MCP server), l'agent **peut** émettre en supplément :

```
✔ Analyse · ✔ PO · ✔ Plan · ✔ Arch · ⏳ Backend · ⬜ Frontend · ⬜ QA
```

Optionnel, jamais en remplacement du `[AGENT] ... (%)` standard.

### 9.3 Pas de "next steps" ni "what's next"

Après `[DONE]`, **aucune** ligne supplémentaire. Pas de :
- "You can now run `/sdd-status 1`..."
- "Next, consider..."
- "Feel free to ask if you have questions..."

Le Tech Lead sait quoi faire.

---

## 10. Bypass `SDD_CHAT_VERBOSE=1` (debug opt-in)

Variable d'environnement `SDD_CHAT_VERBOSE=1` (export shell parent ou
inline `SDD_CHAT_VERBOSE=1 claude ...`) :

- **Non set / 0** : protocole executive (défaut, §2-§9 strict)
- **1** : protocole legacy verbose (avant v7.0.0) — utile pour
  debug profond du framework, pas pour usage quotidien

Chaque agent / commande **DOIT** lire `$SDD_CHAT_VERBOSE` au démarrage
et adapter sa verbosité. Si la lecture env n'est pas disponible (mode
prompt-only), default = executive.

Aucune autre variable n'altère ce protocole.

---

## 11. Enforcement et anti-derive

### 11.1 Qui doit appliquer ce protocole

- **11 agents** : `po`, `arch`, `dev-backend`, `dev-frontend`, `qa`,
  `elicitor`, `constitutioner`, `code-reviewer`, `security-reviewer`,
  `spec-compliance-reviewer`, `arch-reviewer`
- **10 commandes user-facing** : `/feat-generate`, `/feat-validate`,
  `/sdd-full`, `/dev-run`, `/qa-generate`, `/sdd-review`,
  `/sdd-status`, `/sdd-discover-stack`, `/sdd-serve`,
  `/sdd-kill-server`
- **Claude (boucle principale)** quand elle orchestre une commande SDD

### 11.2 Anti-derive

L'agent / la commande NE DOIT JAMAIS :

- Réécrire ce protocole inline dans son prompt (Read par référence
  `@.claude/rules/output-protocol.md` au STEP contexte)
- Inventer un nouveau label `[XYZ]` hors §3
- Sauter directement à `[DONE]` sans updates intermédiaires
- Verbose-leak (un seul tool log en chat = violation)
- Doubler la même ligne deux fois consécutivement

### 11.3 Hook futur (v7.1)

Hook `PreOutputHook` planifié : intercepte chaque ligne émise par
Claude/sub-agent, vérifie le format §2 (regex
`^\[[A-Z/-]+\] .+\.\.\. \(\d{1,3}%\)$` ou variante résultat/erreur),
réécrit ou strip les violations §5.

En attendant v7.1, l'enforcement est **prompt-side** (chaque agent
lit cette règle au STEP contexte) + revue humaine (Tech Lead signale
si protocole violé).

### 11.4 Règle mentale

> **"Le Tech Lead voit l'avancement métier. Le disque garde le détail
> technique. Si une ligne ne porte pas un `[AGENT]` + résumé + %,
> elle ne sort pas en chat."**

---

## 12. Pointeurs

- `error-classification.md §2` — format ERROR 3L disque (préservé)
- `build-and-loop.md §1.3` — statuts QA API Gate (PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED)
- `quality.md §A` — verdict coverage 🟢/🟡/🔴
- `CLAUDE.md §7` — conventions strictes (chat output minimal)
- `docs/conventions.md` — TOC règles cross-cutting
