# Règle — Chat Output (verbosité minimale)

## Principe

Toute sortie texte affichée dans la fenêtre de chat (commandes,
agents, sub-agents, scripts) suit une **politique de verbosité
minimale**. Objectif : zéro token gaspillé sur du log décoratif,
narratif ou redondant. La fenêtre de chat n'est pas un journal.

Règle mentale : *"Si la ligne ne change pas la décision de
l'utilisateur, elle ne doit pas être affichée."*

Cette règle est **load-bearing** : elle s'applique à toutes les
commandes (`/sdd-full`, `/dev-run`, `/us-generate`, …) et tous les
agents (`po`, `arch`, `dev-backend`, `dev-frontend`, `qa`,
`elicitor`).

**Extension orchestrateur principal (depuis 2026-05-12)** : la règle
s'applique aussi à l'**assistant Claude Code lui-même** quand il
orchestre les commandes inline (par ex. en chaînant `/us-generate`
→ `/spec-validate` → `/dev-plan` → `/dev-run` → `/qa-generate` dans
le cadre d'un `/sdd-full` exécuté en pas-à-pas). Pas de narration
"Je lis le fichier X…", "Maintenant je passe à…", pas de récap
multi-section, pas de duplication du contenu déjà émis par les
commandes/agents sous-jacents. Seules les transitions entre phases
sont éventuellement annoncées (1 ligne).

---

## 1. Quotas stricts par statut

| Statut             | Lignes max | Format                                    |
|--------------------|-----------|-------------------------------------------|
| 🟢 Succès          | **1**     | `{étape} — {résultat condensé}`           |
| ⚙️ En cours        | **1**     | `{étape}…` (uniquement si > 5 s perçu)    |
| 🟡 Warning         | **1**     | `WARNING: {cause condensée}`              |
| 🔴 Erreur / Bug    | **2**     | `ERROR: {quoi}` puis `CAUSE: {pourquoi/fix}` |

> Note : le format ERROR canonique reste 3 lignes (ERROR / CAUSE /
> FIX) **dans les fichiers de log et rapports** (`workspace/output/qa/...`,
> `workspace/output/validation/...`). Dans la **fenêtre de chat**, on
> compresse à 2 lignes (CAUSE et FIX fusionnés ou FIX implicite via
> pointeur de fichier).

---

## 2. Interdictions (anti-bavardage)

L'agent NE DOIT PAS afficher dans le chat :

- **Récap décoratif** (`✅ Pipeline complet — 12 fichiers générés…`
  avec sous-blocs PLANIFICATION / EXÉCUTION / QA en multi-lignes)
  → remplacer par 1 ligne `✅ /sdd-full {n} — {U} US, {F} fichiers`
- **Logs de progression** (`Reading SPEC...`, `Loading stack...`,
  `Parsing constitution...`) → silence
- **Confirmations redondantes** (`OK, je vais maintenant...`) → silence
- **Echo de l'argument utilisateur** (`Vous avez demandé /sdd-full 1
  donc je vais...`) → silence
- **Narration interne** (`Je regarde si la SPEC existe...`,
  `Maintenant je passe au STEP 4...`) → silence
- **Liste exhaustive de fichiers écrits** quand le compteur suffit
  (`12 fichiers écrits` au lieu d'énumérer les 12 chemins)
- **Tableaux ASCII / encadrés Markdown** sauf si explicitement
  demandés par l'utilisateur

---

## 3. Pattern recommandé par phase

### Succès (cas nominal)

```
✅ /sdd-full 1-pvlist — 3 US, GO, 24 fichiers, QA GREEN
```

Une seule ligne, statut + métriques compactes. Pas de bloc
récapitulatif multi-lignes.

### Warning (non bloquant)

```
🟡 /spec-validate 1 — WARN (3 warnings, cf. workspace/output/validation/1-readiness.md)
```

Une seule ligne, pointeur fichier pour le détail.

### Erreur (bloquant)

```
🔴 /dev-backend 1-2 — librairie manquante
CAUSE: [STACK_LIBRARY_MISSING] EPPlus absent §2.4 → cf. .claude/stacks/backend/dotnet-minimalapi.md
```

Deux lignes max. Le **détail complet 3 lignes** vit dans le rapport
(`workspace/output/qa/...`, `workspace/output/validation/...`) ou les logs internes,
pas dans le chat.

### Étape en cours (long-running)

Afficher **uniquement** si la phase prend visiblement > 5 secondes
sans output intermédiaire :

```
⚙️ Phase 4 — dev-backend + dev-frontend (3 US parallèles)…
```

Sinon, silence jusqu'au statut final.

---

## 4. Compression des récaps multi-phases

Les récaps de fin de pipeline (ex. `/sdd-full` STEP 5) sont
**compressés sur 1 à 3 lignes max** :

### Cas succès complet

```
✅ /sdd-full 1-pvlist — 3 US · readiness GO · 24 fichiers · QA 92% (GREEN)
```

### Cas mixte (succès + échecs partiels)

```
🟡 /sdd-full 1-pvlist — 3 US, 2/3 OK, 1 échec
🔴 dev-backend 1-2 : librairie manquante (cf. logs)
```

### Cas erreur bloquante

```
🔴 /sdd-full 1-pvlist — bloqué readiness NO-GO (5 errors)
CAUSE: cf. workspace/output/validation/1-readiness.md §3
```

**Interdit** : le format multi-section `PLANIFICATION / EXÉCUTION /
QA / Échecs / Prochaine étape` documenté dans certaines commandes
**doit être réduit** à ces formats compacts.

---

## 5. Pointeurs vers fichiers (préféré aux dumps)

Plutôt que d'afficher le contenu d'un rapport, **émettre un pointeur
cliquable** :

- ❌ Mauvais : afficher 47 lignes du rapport readiness dans le chat
- ✅ Bon : `cf. workspace/output/validation/1-readiness.md §2 (3 warnings)`

L'utilisateur ouvrira le fichier s'il veut le détail. La fenêtre de
chat reste épurée.

---

## 6. Cas où l'affichage long est autorisé

Cette règle a **3 exceptions** :

1. **L'utilisateur demande explicitement** (`affiche le détail`,
   `montre tout`, `verbose`) → format long autorisé pour cette
   réponse uniquement
2. **Question de clarification** (l'agent doit poser une question
   pour débloquer un argument manquant) → 1-3 lignes nécessaires
3. **Checkpoint humain** (ex. `/sdd-full` STEP 3.6) → format prompt
   choix `ok/stop/retry` autorisé (3-6 lignes)

Hors ces cas, la règle §1-§4 prévaut strictement.

---

## 7. Enforcement

- **Toutes les commandes** (`.claude/commands/*.md`) : section
  STEP 5 / récap doit produire ≤ 3 lignes en cas nominal
- **Tous les agents** (`.claude/agents/*.md`) : sortie finale
  doit produire ≤ 1 ligne (succès) ou ≤ 2 lignes (erreur)
- **Tous les scripts** (`.claude/scripts/*.ps1`) : n'écrire dans
  stdout que les statuts critiques ; détail dans des fichiers
  `workspace/output/...`

---

## 8. Anti-pattern explicite

```
❌ INTERDIT — bloc multi-section verbeux dans le chat :

✅ /sdd-full 1-pvlist — pipeline complet terminé

PLANIFICATION (phases 2-2.7) :
  US               : 3 fichiers
  Mockups HTML     : 2 fichiers
  Readiness gate   : 🟢 GO

EXÉCUTION (phases 3-4) :
  Bootstrap + DB   : init (12 tables)
  Backend          : 3/3
  Frontend         : 3/3

QA (phase 5) :
  Mode             : full
  Tests            : 47/47
  Coverage         : 84%
  Décision         : 🟢 GREEN

Prochaine étape :
  - inspecter le code
  - /sdd-status 1
```

```
✅ AUTORISÉ — 1 ligne :

✅ /sdd-full 1-pvlist — 3 US · GO · 24 fichiers · QA 84% (GREEN)
```

