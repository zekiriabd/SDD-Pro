# Règle — Output Protocol (Executive chat output, v7.0.0)

> **Nouveau v7.0.0** : règle SSoT pour la verbosité de sortie en chat.
> Le Tech Lead voit la progression comme un **executive dashboard** (1 ligne
> par étape, label `[AGENT]` + résumé + %). Les détails techniques restent
> persistés en base (`console.db` — rendu via `query_console_db.py ...
> --format md`) et sur disque (`workspace/.sys/.audit/...`).
>
> **Load-bearing** : règle universelle chargée par les 13 agents LLM
> (`po`, `arch`, `dev-backend`, `dev-frontend`, `qa`, `elicitor`,
> `constitutioner`, `specbook-writer`, `code-reviewer`, `security-reviewer`,
> `spec-compliance-reviewer`, `arch-reviewer`, `adversarial-reviewer`)
> et les 13 commandes user-facing (`complexity-router`, script déterministe
> 0 token, n'en fait pas partie).
>
> **Seule rule inconditionnelle (audit tokens 2026-08-30)** :
> `error-classification.md` est passée path-scoped (digests par agent =
> canal nominal) — ce fichier porte désormais aussi le **noyau universel**
> error-classification (§7.3/§7.5 : format ERROR 3L disque + règle mentale
> `[CLASS]` + pointeur taxonomie/digests).

## TOC

- §1 — Principe et périmètre (qui parle au chat)
- §2 — Format canonique (1 ligne par update)
- §3 — Mapping agent → label `[AGENT]` (19 labels)
- §4 — Plages de progression par phase (anti-régression)
- §5 — Patterns interdits en chat (liste fermée)
- §6 — Patterns autorisés (résumés exécutifs)
- §7 — Erreurs : chat 1L vs disque 3L (préservation `[CLASS]`)
- §8 — Itérations `build_loop` (retry visibles, max bornes)
- §9 — Verdicts et rendu final
- §10 — Bypass `SDD_CHAT_VERBOSE=1` (debug opt-in)
- §11 — Enforcement et anti-derive
- §12 — Pointeurs vers règles connexes

---

## 1. Principe et périmètre

**Chat** = sortie texte visible par l'utilisateur dans Claude Code (terminal,
VSCode, web). Producteurs concernés : Claude (orchestration), sub-agents SDD,
**executive 1L** depuis v7.0.0. Scripts Python (stdout JSON) et hooks (feedback
bloquant) inchangés.

**Avant v7.0.0** (verbose, 9 lignes) : "Let me read...", "Reads workspace/...",
`{exit: 0, ...}`, etc. **Après** (executive, 2 lignes) :
`[PO] Découpage FEAT en User Stories... (8%)` puis
`[PO] FEAT 1-Auth → 2 US identifiées. (12%)`.

**N'impacte PAS** : (a) fichiers disque (rapports QA, audit logs, JSON ledgers,
ADRs — format complet préservé), (b) stdout scripts Python en debug manuel,
(c) format ERROR 3L disque (§7.3/§7.5 ci-dessous — load-bearing pour
build_loop / hooks / dashboards).

---

## 2. Format canonique

### 2.1 Update standard (1 ligne)

```
[AGENT] Action courte au gérondif... (PROGRESS%)
```

- `[AGENT]` : un des 19 labels §3, entre crochets, majuscules
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

**Exemples invalides** : `[po] reading FEAT file...` (minuscule, anglais),
`[PO] Read workspace/feats/1-Auth.md` (chemin interne),
`[PO] User Stories generated successfully!` (pas de %, pas de gérondif).

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

19 labels canoniques (v7.0.0+ ; ajouts audités : `[ROUTER]` 2026-06-11 (avec
`[REVERSE]`), `[SPECBOOK]` 2026-07-25). **Aucun autre label admis** dans le chat.

| Label chat | Agent / Commande source | Phase pipeline |
|---|---|---|
| `[ANALYSIS]` | `/feat-generate` (élicitation initiale) | 1 |
| `[ELICITOR]` | agent `elicitor` (`/feat-deepen`) | 1.5 |
| `[ROUTER]` | `sdd_scripts/complexity_router.py` (rubric `docs/rubrics/complexity-router-scoring.md`, opt-in STEP 0 `/sdd-full`) | 1.8 |
| `[PO]` | agent `po` (`/us-generate`) | 2 |
| `[VALIDATE]` | `/feat-validate` (Readiness Gate) | 2.6 |
| `[PLAN]` | `/dev-plan` + agents `dev-*` en mode `:plan` | 2.7 |
| `[ARCH]` | agent `arch` (`/arch-init`) — bootstrap + scaffolding DB | 3 |
| `[CONSTITUTION]` | agent `constitutioner` (Phase B finalize post-arch) | 3.5 |
| `[DEV-BACKEND]` | agent `dev-backend` (`/dev-backend`) | 4 |
| `[DEV-FRONTEND]` | agent `dev-frontend` (`/dev-frontend`) | 4 |
| `[QA]` | agent `qa` (`/qa-generate`) + API Gate | 4-5 |
| `[CODE-REVIEW]` | agent `code-reviewer` | 5 |
| `[SPEC-REVIEW]` | agent `spec-compliance-reviewer` | 5 |
| `[SECURITY]` | agent `security-reviewer` | 5 |
| `[ARCH-REVIEW]` | agent `arch-reviewer` | 5 |
| `[ADV-REVIEW]` | agent `adversarial-reviewer` (opt-out — actif par défaut, skip avec `--no-adversarial`) | 5 |
| `[REVERSE]` | les 12 agents `reverse-*` + 18 commandes `/sdd-reverse*` + `/sdd-db-reverse*` (module reverse — suffixes d'état et format : `rules/reverse-engineering.md §7`) | reverse 1-4 |
| `[SPECBOOK]` | agent `specbook-writer` (invoqué par `/spec-book` — vulgarise FEAT en langage humain, cache `workspace/docs/.sys/sections/`) | 5 (post-livraison) |
| `[DONE]` | verdict final pipeline | 100% |

> **Migration** : `[REVIEW]` (générique) supprimé v7.0.0-alpha — matcher désormais
> `^\[(?:CODE|SPEC|ARCH|ADV)-REVIEW\]`. `[ARCH]` reste réservé à l'agent `arch` ;
> la finalisation par `constitutioner` émet `[CONSTITUTION]`.

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
| Finalize ADRs + constitution | `[CONSTITUTION]` | 32-36 |
| Backend (ALL US) | `[DEV-BACKEND]` | 36-58 |
| API Gate (in-memory) | `[QA]` (gate API) | 58-66 |
| Frontend (ALL US) | `[DEV-FRONTEND]` | 66-78 |
| QA (tests + coverage) | `[QA]` | 78-88 |
| Code review | `[CODE-REVIEW]` | 88-91 |
| Spec compliance | `[SPEC-REVIEW]` | 91-94 |
| Security review | `[SECURITY]` | 94-96 |
| Arch review | `[ARCH-REVIEW]` | 96-98 |
| Adversarial review (opt-out, défaut) | `[ADV-REVIEW]` | 98-99 (jamais 100% — réservé `[DONE]`) |
| Verdict final | `[DONE]` | 100 |

Invocation isolée (ex. `/dev-backend 1-1` hors `/sdd-full`) : 0%→100% sur scope local.

---

## 5. Patterns interdits en chat (liste fermée)

L'agent / la commande / Claude **NE DOIT JAMAIS** émettre en chat :

| Catégorie | Exemples interdits |
|---|---|
| **Logs/traces** | "Reading file...", chemins internes (`workspace/...`, `.claude/...`), stdout/stderr bruts, stack traces, JSON dumps, commandes bash, liste de Read/Edited |
| **Implémentation** | Noms de classes/méthodes/composants, versions libs, lignes de code, diffs, SQL de migrations, routes HTTP (`POST /api/...`) |
| **Métadonnées** | Context budget (`24.3 KB`), tokens/coûts USD, preflight `A1 OK`, cache hit/miss, audit logs internes |
| **Narration** | "Let me check...", "I'll now...", "Done. Now moving on...", réflexions internes, listes à puces > 3 items |

Exception : `build_loop iter X/Y` autorisé **uniquement** dans `[…/FIXING]`.

---

## 6. Patterns autorisés (résumés exécutifs)

- **Updates de progression** : 1 ligne par STEP majeure, cible **3-6 updates/invocation** (plus = bruit)
- **Compteurs métier** : `2 User Stories créées`, `5 endpoints livrés`, `47/47 tests passés`, `coverage 82%`, verdict `🟢/🟡/🔴`
- **IDs métier** : `FEAT 1-Auth`, `US 1-1-Login`, `AC-3 non couverte`, classe d'erreur `[QA_COVERAGE_GAP]`
- **Pointeurs source** (debug Tech Lead) : 1 pointeur max sans contenu, ex. `[QA/FAIL] Tests échec sur US 1-2 → console.db qa_api_tests (query_console_db.py feat-stats --feat 1 --format md). (84%)`

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
🔴 [DEV-BACKEND/FAIL] Build US 1-2 — [BUILD_BLOCKING] cycle DI détecté → stderr build_loop (voir chat). (48%)
🔴 [QA/FAIL] Coverage US 1-1 — [QA_COVERAGE_GAP] 62% < seuil 80% → console.db qa_coverage (query_console_db.py coverage --feat 1 --format md). (84%)
🔴 [VALIDATE/FAIL] FEAT 1 NO-GO — [READINESS_NO_GO] 2 ACs sans Given/When/Then → workspace/.sys/.validation/1-readiness.md. (15%)
```

### 7.3 Format ERROR sur disque (3 lignes — SSoT universel depuis 2026-08-30)

Format canonique (ex-`error-classification.md §2`, déplacé ici — audit tokens
2026-08-30 ; §2 là-bas en garde le squelette côté taxonomie) :
```
ERROR: {feat/us/task or pipeline-step} failed
CAUSE: [{CLASS}] {détail 1L}
FIX: {action 1L}
```
Exemple (`[BUILD_CORRECTIBLE]` — build_loop itère) :
```
ERROR: dev-backend 1-2 build failed (iter 1/3)
CAUSE: [BUILD_CORRECTIBLE] missing import 'SIM.Backend.Services.IBebeService' in BebesEndpoints.cs:1
FIX: add 'using SIM.Backend.Services;'
```
**DOIT** rester intact (parseable par build_loop + hooks). Chat = vue résumée.

### 7.4 Verdicts intermédiaires (🟡 WARN non bloquant)
```
🟡 [QA/WARN] API Gate US 1-1 — couverture endpoints partielle (12/16) → continue. (66%)
🟡 [CODE-REVIEW/WARN] Code review FEAT 1 — 3 issues serious mais < seuil. (94%)
```

### 7.5 Noyau universel error-classification (déplacé ici, audit tokens 2026-08-30)

`error-classification.md` est **path-scoped** : elle ne s'auto-injecte plus
dans les sessions/agents ordinaires. Son contrat universel vit ici :

- **Format** : chat 1L §7.2, rapport 3L disque §7.3.
- **Règle mentale** : *« Pas de bloc ERROR sans préfixe `[CLASS]`. Si rien ne
  matche → `[UNKNOWN]`. »* — décision mécanique build_loop, classement 0-LLM.
- **Taxonomie complète** (16 familles, comportement build_loop §3) :
  `@.sdd/rules/error-classification.md` (Read on-demand). **Tranche par
  agent** : `.sdd/digests/error-classification.{agent}.md` (Read en STEP
  contexte — canal nominal des 12 agents mappés).

---

## 8. Itérations `build_loop` (retry visibles, bornes)

### 8.1 Format `[…/FIXING]`

Itère jusqu'à `BuildLoopMaxIter` (default 3). Chaque itération **DOIT** être
visible en chat (signal de coût). `%` ne progresse pas pendant retries
(load-bearing : Tech Lead voit que le coût monte sans avancement).
```
[DEV-BACKEND/FIXING] Correction erreur compilation (iter 1/3)... (48%)
```

Échec terminal (`[BUILD_LOOP_EXHAUSTED]` iters, ou `[BUILD_LOOP_COST_EXCEEDED]`
cap $) : format §7.2, ex. :
```
🔴 [DEV-BACKEND/FAIL] US 1-2 — [BUILD_LOOP_EXHAUSTED] 3/3 iters sans convergence → stderr build_loop (voir chat). (48%)
```

---

## 9. Verdicts et rendu final

À la toute fin, **une seule ligne** :
```
[DONE] FEAT 1-Auth livrée — 🟢 GREEN (2 US, 47 tests, coverage 82%, 0 issue critique). (100%)
[DONE/WARN] FEAT 1-Auth livrée — 🟡 WARN (3 issues serious, voir query_console_db.py review --feat 1 --format md). (100%)
[DONE/FAIL] FEAT 1-Auth — 🔴 RED, pipeline interrompu — voir query_console_db.py review --feat 1 --format md. (66%)
```

Après `[DONE]`, **aucune** ligne supplémentaire (pas de "next steps", "consider",
"feel free to ask"). Le Tech Lead sait quoi faire.

---

## 10. Bypass `SDD_CHAT_VERBOSE=1` (debug opt-in)

`SDD_CHAT_VERBOSE=1` (export ou inline) → protocole legacy verbose pré-v7.0.0
(debug profond, pas usage quotidien). Sinon → executive strict.

---

## 10.bis Mode minimal `SDD_CHAT_MINIMAL=1` (CI/CD opt-in, v7.0.1-dev)

Substance déplacée vers `@.sdd/docs/output-protocol-minimal.md` (audit tokens
2026-08-30 — mode opt-in CI/CD, Read on-demand). Résumé : 1 ligne de résultat
par agent, erreurs/warnings conservés, `VERBOSE` gagne sur collision.

---

## 11. Enforcement et anti-derive

**Périmètre** : les 13 agents LLM (liste en tête de fichier) + 1 script
déterministe `complexity_router.py` (label `[ROUTER]`), les 13 commandes
user-facing (cf. `entrypoint-body.md §3`), et Claude orchestrateur.

**Anti-derive — NE JAMAIS** :
- Réécrire ce protocole inline (Read par référence au STEP contexte)
- Inventer un nouveau label `[XYZ]` hors §3
- Sauter à `[DONE]` sans updates intermédiaires
- Verbose-leak (1 tool log en chat = violation)
- Dupliquer la même ligne consécutivement

**Enforcement** : prompt-side (chaque agent Read cette règle) + revue humaine.
Hook `PreOutputHook` runtime = follow-up hors scope (cf. roadmap).

> **Règle mentale** : "Le Tech Lead voit l'avancement métier ; le disque garde
> le détail technique. Pas de `[AGENT]` + résumé + % → pas de sortie en chat."

---

## 12. Pointeurs

- §7.3/§7.5 — format ERROR 3L disque (SSoT universel) ; taxonomie complète :
  `error-classification.md` (path-scoped) + digests `.sdd/digests/`
- `build-and-loop.md §1.3` — statuts QA API Gate (PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED)
- `quality.md §A` — verdict coverage 🟢/🟡/🔴
- `CLAUDE.md §7` — conventions strictes (chat output minimal)
- `docs/conventions.md` — TOC règles cross-cutting
