# /feat-generate — Création guidée d'une FEAT fonctionnelle

Crée un fichier `workspace/input/feats/{n}-{Name}.md` pré-rempli en interrogeant le PO
via 2 séries de questions courtes. Le numéro `{n}` est auto-détecté.

**Usage :** `/feat-generate` ou `/feat-generate {Nom}`

---

## STEP 0 — Preflight projet initialisé (greenfield gate)

Avant toute interaction avec l'utilisateur, vérifier que le projet est
bootstrappé. Évite que `/feat-generate` produise une FEAT orpheline
(sans `stack.md` aval cassé sur `/sdd-full`).

1. **Test existence** : `workspace/input/stack/stack.md` existe et fait
   ≥ 100 octets.
2. **Test template rendu** : Read le fichier, vérifier qu'il ne contient
   pas de placeholder `{{Placeholder}}` (regex `\{\{[A-Za-z][A-Za-z0-9_]*\}\}`).

Si l'un des tests échoue → STOP avec message actionnable (pas d'ERROR
technique, c'est un onboarding utilisateur) :

```
🟡 [FEAT-GENERATE] Projet non initialise — bootstrap requis.

workspace/input/stack/stack.md {absent | contient des placeholders non substitues}.

Avant de creer une FEAT, lance depuis un terminal :
    python bootstrap.py

(interactif, ~5 questions, ~30s — choisit le combo stack, AppName, DB, auth)

Apres bootstrap, relance : /feat-generate {Nom}
Details et options : /sdd-bootstrap
```

Cette commande **ne lance jamais** `bootstrap.py` (interactif, requiert
le terminal utilisateur — pas du sub-agent Claude).

---

## STEP 0.5 — Phase 0 Discovery hint (v7.0.0+, opt-in)

**Conditionnel** : si Glob `workspace/input/feats/*.md` retourne ≥ 2 FEATs
(le 3ᵉ+ FEAT projet, signal de "projet qui grossit"), ET aucun fichier
`product-brief.md` ni `prfaq.md` dans `workspace/input/discovery/`,
émettre **avant** les questions de cadrage :

```
💡 [FEAT-GENERATE] Astuce Phase 0 Discovery (facultative, projets > 3 FEATs)

Vous avez déjà N FEATs. Pour les projets qui grossissent, un brief
Discovery aide à cadrer la vision avant de continuer à empiler les FEATs :
  - `.claude/templates/product-brief.template.md` (10 sections : vision, personas, KPIs, hypothèses, risques)
  - `.claude/templates/prfaq.template.md` (Amazon "Working Backwards" — PR fictive + FAQ interne)

Bénéfice : éviter le scope creep en FEATs parasites. Une FEAT proposée
qui ne sert pas une promesse du brief = probablement à challenger.

Continuer avec /feat-generate quand même ? (oui / non / voir templates)
  - "oui" / Enter        → continuer cadrage FEAT [DEFAULT]
  - "non"                → STOP, copier les templates d'abord dans workspace/input/discovery/
  - "voir templates"     → afficher 5 lignes d'extrait pour chaque template puis re-demander
```

Cette astuce ne s'affiche **jamais** sur les FEATs 1-2 (overhead non
amorti) ni si un brief Discovery est déjà présent (déjà cadré).

**Bypass complet** : `SDD_NO_PHASE0_HINT=1` env var (silence pour
workflows automatisés).

---

## STEP 1 — Nom de la feature

Si l'utilisateur a fourni un nom : l'utiliser.

Sinon, demander :

```
Quel est le nom de la feature ? (ex. : Auth, Crud, Dashboard)
```

**Règles de nommage du fichier** :
- Première lettre en majuscule, pas d'accents, pas d'espaces (utiliser des tirets si plusieurs mots)
- Exemples : `Auth`, `Crud`, `Reset-Password`, `Dashboard`

---

## STEP 2 — Auto-détection du numéro

1. Lister `workspace/input/feats/*.md` (Glob ou ls)
2. Pour chaque fichier, extraire le préfixe numérique avant le premier `-` :
   regex `^(\d+)-.*\.md$`
3. `{n}` = max des numéros trouvés + 1. Si aucun fichier : `{n} = 1`
4. Le fichier final sera : `workspace/input/feats/{n}-{Name}.md` (ex. `1-Auth.md`, `2-Crud.md`)

**Vérifier** : si `{n}-{Name}.md` existe déjà avec ce nom (différent numéro), demander au PO s'il veut écraser ou choisir un autre nom. Pas de doublon de nom.

---

## STEP 3 — Comprendre le besoin (3 questions en bloc)

```
Pour cadrer la FEAT "{Name}" (numérotée {n}), j'ai besoin de comprendre l'essentiel :

1. Quel est l'objectif principal ? Qu'est-ce que l'utilisateur peut faire
   qu'il ne pouvait pas faire avant ?

2. Qui sont les acteurs ? (ex. : utilisateur connecté, admin, visiteur anonyme)

3. Quels sont les 3 à 7 besoins fonctionnels clés ? (verbes d'action)
   Ex. : "se connecter via Azure AD", "réinitialiser son mot de passe", "consulter le dashboard"
```

Attendre la réponse avant de continuer.

---

## STEP 4 — Questions de cadrage (max 3 questions)

Sur la base des réponses du STEP 3, poser **2 à 3 questions ciblées** pour préciser :

```
Quelques précisions :

1. Y a-t-il des règles métier importantes ? (validations, calculs, limites, expirations)
2. Y a-t-il des dépendances avec des FEATs déjà créées ? (lister les FEATs existantes
   trouvées dans `workspace/input/feats/` si pertinent)
3. Qu'est-ce qui est explicitement HORS scope pour cette feature ?
```

Adapter les questions au contexte (ne pas demander la dépendance si aucune FEAT n'existe).

Attendre la réponse avant de continuer.

---

## STEP 5 — Proposer un plan de FEAT

Avant de générer le fichier, présenter un résumé pour validation :

```
Voici le plan de FEAT pour "{n}-{Name}" :

**Objectif :** {résumé en 1 phrase}

**Acteurs :** {liste}

**Besoins fonctionnels (SFD) :**
- SFD-1: {besoin 1 reformulé en verbe d'action}
- SFD-2: {besoin 2}
- ...

**Règles métier :** {liste ou "aucune mentionnée"}

**Dépendances :** {liste ou "aucune"}

**Hors scope :** {liste ou "à préciser"}

OK pour générer le fichier ? (oui / corrections : ...)
```

Attendre validation avant d'écrire le fichier.

---

## STEP 6 — Génération du fichier

Créer `workspace/input/feats/{n}-{Name}.md` à partir du template
`.claude/templates/feat.template.md`. Remplir toutes les sections avec
le contenu validé en STEP 5.

**Règle critique** : la section `## Functional Needs` contient des **SFD bullets identifiés** (préfixés `SFD-1:`, `SFD-2:`, …) — verbes d'action exprimant un besoin fonctionnel, JAMAIS de format `US-N: As a... I want... So that...`. Le découpage en User Stories structurées est la responsabilité de l'agent PO, pas de cette commande.

**IDs stables** : les `SFD-N` (et `FD-N` dans `## Functional Deliverables`) sont explicitement préfixés et stables. Ils ne doivent pas être réordonnés ni renumérotés après la génération des US (les `Covers` des US référencent ces IDs).

**Anti-derive** : ne pas inventer de Business Rules, Acceptance Criteria ou
Functional Deliverables qui n'ont pas été mentionnés par le PO. Si une section
est vide après les questions, écrire `<à préciser par le PO>` plutôt qu'inventer.

---

## STEP 7 — Validation post-écriture (depuis SDD_Pro v2.5)

Re-lire le fichier produit pour valider :

### 7.1 SFD numérotation obligatoire

Toutes les lignes sous `## Functional Needs` qui sont des bullets
DOIVENT respecter le pattern `^- SFD-\d+: .+$`. Si au moins une
ligne bullet ne correspond pas → ERROR :

```
ERROR: /feat-generate — numérotation SFD invalide
CAUSE: ligne(s) sous ## Functional Needs sans préfixe SFD-N (ex. : "{ligne fautive}")
FIX: numéroter tous les bullets de ## Functional Needs au format "SFD-1: …", "SFD-2: …" puis re-sauver
```

Le fichier est conservé tel qu'écrit (l'humain peut corriger
manuellement ou relancer `/feat-generate` après suppression).

### 7.2 FD numérotation obligatoire (si section non vide)

Mêmes règles que §7.1 mais pour `## Functional Deliverables` avec
pattern `^- FD-\d+: .+$`. Si la section est vide ou contient `<à
préciser par le PO>`, validation skip.

### 7.3 BR / AC numérotation (warning, pas erreur)

Pour `## Business Rules` et `## Acceptance Criteria`, idem mais en
mode WARNING uniquement (ces IDs sont moins critiques que SFD/FD pour
la traçabilité downstream).

---

## STEP 7.5 — Bootstrap / extension de la constitution (depuis SDD_Pro v3)

Vérifier l'existence de `workspace/output/.sys/.context/constitution.md`.

### 7.5.1 Si la constitution n'existe PAS (premier `/feat-generate` du projet)

> **v7.0.0-alpha audit P0-doc 2026-06-05** — STEP 7.5.1 doit créer le
> répertoire parent `workspace/output/.sys/.context/` AVANT d'écrire,
> sinon le `Write` natif Claude Code échoue sur env greenfield où
> `/sdd-bootstrap` aurait créé `workspace/` mais pas `.sys/.context/`.

0. **mkdir parent** (idempotent, cross-platform) :
   ```bash
   python -c "from pathlib import Path; Path('workspace/output/.sys/.context').mkdir(parents=True, exist_ok=True)"
   ```
1. Read `.claude/templates/constitution.template.md`.
2. Lire `workspace/input/stack/stack.md` (si présent) pour récupérer
   `AppName` du `## Project Config`. Si absent → utiliser le nom du
   dossier projet (résolu via `pwd` ou racine relative).
3. Remplir le template :
   - §1 `{ProjectName}` = `AppName` ou nom dossier
   - §1 `{YYYY-MM-DD}` = aujourd'hui (deux fois : créé / mis à jour)
   - §2 Glossaire : tableau vide (pas d'invention)
   - §3 Acteurs : extraire de la section `## Actors` de la FEAT
     créée à l'étape STEP 6. Une ligne par acteur, colonne FEATs =
     `{n}-{Name}`
   - §4 Stack : laisser les `<stack>` placeholders (`/arch-init` les
     remplira)
   - §5 Conventions : tableau §5.3 vide (par défaut)
   - §6 ADRs : tableau vide (en-têtes seuls)
   - §7 Risques/Hypothèses : sections vides
   - §8 Index des écrivains : laisser tel quel
4. Write `workspace/output/.sys/.context/constitution.md` (mode `create`).

### 7.5.2 Si la constitution existe DÉJÀ (FEAT additionnelle)

Append-only sur §3 Acteurs (mêmes règles que l'agent PO §8.5.1) :
- Pour chaque acteur de la FEAT créée, append en §3 ou MAJ la colonne
  "FEATs concernées".
- Edit la ligne `**Dernière mise à jour**` avec la date du jour.

Aucune autre section n'est touchée.

---

## STEP 8 — Confirmation

```
FEAT créée : workspace/input/feats/{n}-{Name}.md
Constitution : workspace/output/.sys/.context/constitution.md ({"créée" si bootstrap, "étendue" sinon})

Prochaines étapes :
1. Relire le fichier et l'ajuster si besoin
2. Déposer les mockups HTML statiques dans workspace/input/ui/ si la feature a une UI (optionnel — convention {n}-{m}-{Name}.html)
3. Lancer plus tard : /us-generate {n}
```

Aucune autre ligne. STOP.

---

## Règles de cette commande

- **Max 6 questions au total** sur les STEPS 3 et 4 combinés. Trop de questions = friction.
- **Ne jamais générer** de User Stories structurées (US-N, "As a..."). Seulement des SFD bullets identifiés (`SFD-N:`).
- **Ne jamais imposer** de décisions techniques. Cette commande est fonctionnelle, pas technique.
- **Ne jamais inventer** de contenu non mentionné par le PO (anti-derive).
- **Hors scope** : générer du code, créer des tâches techniques, lire le stack, lire les maquettes UI.
  Cette commande produit uniquement `workspace/input/feats/{n}-{Name}.md`.

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[ANALYSIS]` (cf. output-protocol.md §3)
**Plage de progression couverte** : `0-12%` (cf. output-protocol.md §4)

**Granularité cible** : 3-5 updates (cadrage initial, questions Q/R,
écriture FEAT, bootstrap constitution). Format
`[ANALYSIS] Action au gérondif... (X%)` ou résultat factuel 1L.

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- tool call narration, stdout/stderr bash
- détail des sections FEAT générées (compteurs SFD/BR/AC suffisent)
- context budget, tokens

**Verdict final** : 1 ligne `[ANALYSIS] FEAT {n}-{Name} créée
(N SFD, M BR, P AC). (12%)`. Pas de "next steps" après (cf. §9.3).

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
