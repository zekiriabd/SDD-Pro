# Règle — Output Protocol (Executive chat output, v7.0.0)

> **Nouveau v7.0.0** : règle SSoT pour la verbosité de sortie en chat.
> Le Tech Lead voit la progression du pipeline SDD comme un **executive
> dashboard** (1 ligne par étape, label `[AGENT]` + résumé + %), pas
> comme une console terminal verbose. Les détails techniques restent
> persistés sur disque (rapports `workspace/output/qa/...`,
> `workspace/output/.sys/.audit/...`) pour debug/audit.
>
> **Load-bearing** : règle universelle chargée par les 13 agents
> (`po`, `arch`, `dev-backend`, `dev-frontend`, `qa`, `elicitor`,
> `constitutioner`, `code-reviewer`, `security-reviewer`,
> `spec-compliance-reviewer`, `arch-reviewer`, `adversarial-reviewer`)
> et les 13 commandes user-facing.

## TOC

- §1 — Principe et périmètre (qui parle au chat)
- §2 — Format canonique (1 ligne par update)
- §3 — Mapping agent → label `[AGENT]` (16 labels)
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
`{exit: 0, ledger_path: ...}`, "Writing US...", etc.
**Après v7.0.0** (executive, 2 lignes) :
```
[PO] Découpage FEAT en User Stories... (8%)
[PO] FEAT 1-Auth → 2 US identifiées. (12%)
```

**N'impacte PAS** : (a) fichiers disque (rapports QA, audit logs, JSON ledgers,
ADRs — format complet préservé), (b) stdout scripts Python en debug manuel,
(c) format ERROR 3L disque (`error-classification.md §2` — load-bearing pour
build_loop / hooks / dashboards).

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

**Exemples invalides** : `[po] reading FEAT file...` (minuscule, anglais),
`[PO] Read workspace/input/feats/1-Auth.md` (chemin interne),
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

17 labels canoniques (depuis v7.0.0+ — ajout `[ROUTER]` pour le routeur de complexité).
**Aucun autre label admis** dans le chat.

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
| `[ADV-REVIEW]` | agent `adversarial-reviewer` (opt-in `/sdd-review --adversarial`) | 5 |
| `[DONE]` | verdict final pipeline | 100% |

> **Migration** : `[REVIEW]` (générique) supprimé v7.0.0-alpha — utilisé auparavant
> par 4 agents distincts avec collisions de plage. Les logs/scripts qui matchaient
> `^\[REVIEW\]` doivent désormais matcher `^\[(?:CODE|SPEC|ARCH|ADV)-REVIEW\]`.
> `[ARCH]` reste réservé à l'agent `arch` ; la phase de finalisation par
> `constitutioner` émet `[CONSTITUTION]`.

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
| Adversarial review (opt-in) | `[ADV-REVIEW]` | 98-99 (cf. audit P0-doc 2026-06-05 — ne pas chevaucher `[DONE]` 100%) |
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
- **Pointeurs disque** (debug Tech Lead) : 1 fichier max sans contenu, ex. `[QA/FAIL] Tests échec sur US 1-2 → workspace/output/qa/feat-1/report.md. (84%)`

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

Préservation littérale du format `error-classification.md §2` dans le rapport :
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

---

## 8. Itérations `build_loop` (retry visibles, bornes)

### 8.1 Format `[…/FIXING]`

Itère jusqu'à `BuildLoopMaxIter` (default 3). Chaque itération **DOIT** être
visible en chat (signal de coût). `%` ne progresse pas pendant retries
(load-bearing : Tech Lead voit que le coût monte sans avancement).
```
[DEV-BACKEND] Implémentation US 1-2 en cours... (48%)
[DEV-BACKEND/FIXING] Correction erreur compilation (iter 1/3)... (48%)
[DEV-BACKEND] US 1-2 livrée, build vert. (54%)
```

**Échec terminal** :
```
🔴 [DEV-BACKEND/FAIL] US 1-2 — [BUILD_LOOP_EXHAUSTED] 3/3 iters sans convergence → workspace/output/qa/feat-1/build-us1-2.md. (48%)
🔴 [DEV-BACKEND/FAIL] US 1-2 — [BUILD_LOOP_COST_EXCEEDED] $15.30 ≥ $15 cap → STOP. (48%)
```

---

## 9. Verdicts et rendu final

À la toute fin, **une seule ligne** :
```
[DONE] FEAT 1-Auth livrée — 🟢 GREEN (2 US, 47 tests, coverage 82%, 0 issue critique). (100%)
[DONE/WARN] FEAT 1-Auth livrée — 🟡 WARN (3 issues serious, voir workspace/output/qa/feat-1/sdd-review.md). (100%)
[DONE/FAIL] FEAT 1-Auth — 🔴 RED, pipeline interrompu — voir workspace/output/qa/feat-1/sdd-review.md. (66%)
```

Après `[DONE]`, **aucune** ligne supplémentaire (pas de "next steps", "consider",
"feel free to ask"). Le Tech Lead sait quoi faire.

---

## 10. Bypass `SDD_CHAT_VERBOSE=1` (debug opt-in)

`SDD_CHAT_VERBOSE=1` (export ou inline) → protocole legacy verbose pré-v7.0.0
(debug profond, pas usage quotidien). Sinon → executive strict.

---

## 10.bis Mode minimal `SDD_CHAT_MINIMAL=1` (CI/CD opt-in, v7.0.2)

`SDD_CHAT_MINIMAL=1` (export parent shell AVANT démarrage Claude Code) →
**1 ligne par invocation** au lieu des 3-6 updates standard. Conçu pour
les runs CI/CD où le log doit rester concis (parsing automatique, taille
contrôlée, économie de cache prompt pour orchestration).

### 10.bis.1 Format minimal

Pour chaque agent / phase, **uniquement la ligne de résultat finale**
au format `[AGENT] verdict (PROGRESS%)`. Les `[AGENT/FIXING]` retries
sont supprimés. Les `[AGENT]` updates intermédiaires sont supprimés.

**Exemple comparatif** (FEAT 1-Auth, 2 US) :

| Mode | Lignes émises |
|---|---:|
| Default (executive) | ~30-50 lignes (3-6 par agent × ~10 agents) |
| `SDD_CHAT_VERBOSE=1` | ~150-300 lignes (legacy v6) |
| `SDD_CHAT_MINIMAL=1` | ~10-12 lignes (1 par agent + verdict final) |

### 10.bis.2 Sortie type mode minimal

```
[PO] 2 User Stories créées. (12%)
[VALIDATE] FEAT 1-Auth GO. (15%)
[ARCH] Scaffolding terminé (1 backend + 1 frontend). (32%)
[CONSTITUTION] ADRs indexés. (36%)
[DEV-BACKEND] 2 US livrées, build vert. (58%)
[QA] API Gate PASS (24/24 tests). (66%)
[DEV-FRONTEND] 2 US livrées, fidelity 95%. (78%)
[QA] Coverage 82% ≥ 80%, verdict 🟢. (88%)
[CODE-REVIEW] 🟢 0 issue critique. (91%)
[SPEC-REVIEW] 🟢 6/6 AC vérifiés. (94%)
[SECURITY] 🟢 0 hard-blocking. (96%)
[DONE] FEAT 1-Auth livrée — 🟢 GREEN. (100%)
```

### 10.bis.3 Combinaison des modes

| `SDD_CHAT_VERBOSE` | `SDD_CHAT_MINIMAL` | Effet |
|:---:|:---:|---|
| (vide) | (vide) | Mode executive standard v7.0.0 |
| `1` | (vide) | Mode verbose legacy v6 |
| (vide) | `1` | Mode minimal CI/CD |
| `1` | `1` | **VERBOSE wins** (debug prevails) — un WARN stderr signale la collision |

### 10.bis.4 Erreurs en mode minimal

Les erreurs `🔴 [AGENT/FAIL]` restent émises (1 ligne — déjà conforme au
format minimal §7.2). Les warnings `🟡 [AGENT/WARN]` sont émis aussi
(coût info précieux même en minimal). Seuls les updates de progression
intermédiaires sont supprimés.

### 10.bis.5 Detection runtime

Chaque agent vérifie `os.environ.get("SDD_CHAT_MINIMAL", "")` au début
de son exécution. Si truthy (`1`/`true`/`yes`/`on`), bascule en mode
minimal : ne loggue que (a) ligne de résultat finale + (b) erreurs/warnings.

Les commandes orchestratrices (`/sdd-full`, `/dev-run`) propagent
l'env var aux sub-agents (héritée par défaut via subprocess).

---

## 11. Enforcement et anti-derive

**Périmètre** : les 12 agents LLM (po, arch, dev-backend, dev-frontend, qa, elicitor,
constitutioner, code-reviewer, security-reviewer, spec-compliance-reviewer,
arch-reviewer, adversarial-reviewer) + 1 script déterministe `complexity_router.py`
(label `[ROUTER]`), les 13 commandes user-facing (cf.
`CLAUDE.md §3`), et Claude orchestrateur.

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

- `error-classification.md §2` — format ERROR 3L disque (préservé)
- `build-and-loop.md §1.3` — statuts QA API Gate (PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED)
- `quality.md §A` — verdict coverage 🟢/🟡/🔴
- `CLAUDE.md §7` — conventions strictes (chat output minimal)
- `docs/conventions.md` — TOC règles cross-cutting
