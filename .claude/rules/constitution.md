# Règle — Constitution projet + ADRs

## Principe

Le fichier `workspace/output/.sys/.context/constitution.md` est la **source de vérité
partagée** entre tous les agents SDD_Pro. Il garantit la cohérence
sémantique cross-FEAT (glossaire, acteurs, conventions) et trace les
décisions architecturales (ADRs).

Chaque ADR (`workspace/output/.sys/.context/adrs/ADR-{nnn}-{slug}.md`) trace **une
décision structurante** au format Context / Decision / Consequences.

---

## 1. Création initiale

`/feat-generate` (premier appel sur un projet) bootstrap la constitution
avec :
- §1 Identité (`ProjectName` = `AppName` du `workspace/input/stack/stack.md` si
  défini, sinon nom du dossier projet)
- §2 Glossaire (vide initialement, étendu par les agents)
- §3 Acteurs (extraits de la FEAT créée)
- §4 Stack technique (`<à compléter par /arch-init>`)
- §5 Conventions (références CLAUDE.md §3-§4, vide pour 5.3)
- §6 ADRs (vide initialement)
- §7 Risques (vide tant que `/feat-deepen` n'a pas tourné)
- §8 Index des écrivains (statique)

**Idempotent** : si `workspace/output/.sys/.context/constitution.md` existe déjà, ne
JAMAIS l'écraser. Étendre seulement les acteurs (§3) et termes (§2)
de la nouvelle FEAT.

---

## 2. Read-only par défaut

Tous les agents **lisent** la constitution en début d'exécution
(intégrée dans leur STEP de chargement). Elle compte ~2 KB → coût
négligeable.

**Personne ne réécrit** le fichier intégralement. Les modifications
sont :
- **Append-only** sur les listes (ajout d'une ligne acteur, terme,
  ADR)
- **Update-in-place** sur 1 ligne de tableau (ex. : MAJ statut ADR de
  Proposed → Accepted)

---

## 3. Qui peut écrire dans la constitution

| Agent / Commande | Sections autorisées | Mode | Phase |
|---|---|---|---|
| `/feat-generate` | §1 (bootstrap), §2-3 (init) | Création ou extend | 1 |
| Agent `elicitor` (`/feat-deepen`) | §7 (risques, hypothèses) | Append-only | 1.5 |
| Agent `po` | §2 (nouveaux termes), §3 (nouveaux acteurs) | Append-only | 2 |
| Agent `arch` | §4 (stack final + DatabaseType), §6 (ADRs index) | Update §4 / Append §6 | 4 |

**Modifié en v3.0.1** : les **agents `dev-*` sont désormais STRICTEMENT
read-only** sur `constitution.md`. Ils créent leurs ADRs en fichiers
indépendants (`workspace/output/.sys/.context/adrs/ADR-{timestamp}-{slug}.md` —
numérotation atomique, voir §4) **sans toucher §6**. L'index §6 est
rebuild par le prochain `arch` ou ignoré (la source de vérité = les
fichiers ADR eux-mêmes).

**Pourquoi ?** `/dev-run` lance dev-backend + dev-frontend en
parallèle sur N US (jusqu'à 2×N invocations). Si chacun éditait §6,
on aurait des race conditions garanties sur le même fichier. La
règle `.claude/rules/file-ownership.md` formalise cette sérialisation.

**Tout autre agent ou phase** = read-only strict (lecture passive
pour glossaire, acteurs, ADRs existants).

### 3.bis Procédure append-only durcie pour §3 Acteurs (depuis v3.1.3)

L'agent PO suit cette procédure **obligatoire** au STEP 8.5
(cf. `agents/po.md`) — toute version antérieure (skip silencieux,
append simple) est dépréciée :

1. **Détection placeholder bootstrap** : la ligne
   `| `<a completer par agent PO>` | <role> | - |` (issue de
   `templates/constitution.template.md`) est détectée et **remplacée**
   par le 1er acteur (Edit, pas append).
2. **Append normal** pour les acteurs suivants ou si pas de placeholder.
3. **Edit in-place** sur la 3ᵉ colonne (`FEATs concernées`) si l'acteur
   est déjà listé pour une autre FEAT.
4. **Validation read-back obligatoire** : à la fin du STEP, l'agent
   re-Read constitution.md et vérifie que **tous** les acteurs de la
   section `## Actors` de la FEAT parente apparaissent en colonne 1
   du tableau §3, ET qu'il n'y a plus de ligne placeholder.
5. **STOP + ERROR si validation échoue** : un STEP 8.5 ne peut plus
   se terminer silencieusement vide.

**Cas réel ayant motivé ce durcissement** (run 1-pvlist, audit A1) :
le STEP 8.5 v3 d'origine acceptait un skip silencieux quand le pattern
Edit append ne matchait pas le placeholder. Résultat : §3 est resté
avec `<a completer par agent PO>` pendant toute la durée du projet.
La v3.1.3 supprime cette possibilité de défaillance silencieuse.

---

## 4. Création d'un ADR

Un ADR est créé quand :

- **Arch Phase C** : pour chaque décision majeure (choix backend,
  frontend, UI DS, auth, DatabaseType, stratégie scaffolding). Au
  moins 1 ADR par dimension active du stack.
- **Dev-* en cours d'exécution** : si un choix d'implémentation
  important n'est pas couvert par un ADR existant ET ne découle pas
  directement du stack actif (ex. : choix d'une stratégie de
  pagination, d'une convention de naming spécifique au projet).
  Sinon, suivre le stack sans tracer.

### 4.1 Identifiant — timestamp atomique (v3.0.1)

**Ne PAS utiliser** `ADR-{nnn}-{slug}.md` avec numérotation
incrémentale (`Glob + max + 1`) — racy quand plusieurs agents
créent un ADR en parallèle (`/dev-run` lance dev-backend +
dev-frontend simultanément).

**Utiliser** : `ADR-{YYYYMMDDTHHmmss}-{slug}.md`

- `{YYYYMMDDTHHmmss}` : timestamp UTC à la seconde
  - Format compact ISO 8601 sans séparateurs de date/heure
  - Exemples : `20260505T143022`, `20260605T091533`
- En cas de collision théorique (deux agents au même T à la seconde),
  ajouter un suffixe `-{rand4}` : `20260505T143022-1234`
- `{slug}` = kebab-case, lowercase, max 5 mots significatifs

### 4.2 Tri et lecture

Les ADRs se trient **chronologiquement** par tri alphabétique du
filename (le timestamp ISO le garantit). Aucune ambiguïté entre
agents parallèles.

Exemples :
- `ADR-20260505T143022-stack-backend-dotnet.md`
- `ADR-20260505T143025-database-first-approach.md`
- `ADR-20260605T091533-pagination-cursor-based.md`

Optionnellement, le H1 du fichier peut conserver un alias court
(`# ADR-001 — Backend stack`) pour la lisibilité humaine, mais cet
alias **n'est PAS l'identifiant** — il peut être renuméroté
post-hoc sans casser de lien (les liens utilisent le filename).

### 4.3 Format

Read `.claude/templates/adr.template.md`. Remplir tous les champs.
Status initial = `Accepted` (les ADRs SDD_Pro tracent des décisions
déjà prises, pas des propositions à débattre).

### 4.4 Index dans constitution.md §6

⚠️ **Modifié v3.0.1** : seul l'agent `arch` (phase 4, séquentielle)
peut écrire dans §6. Les agents `dev-*` (phase 5, parallèles) **ne
touchent PAS** constitution.md — ils créent uniquement le fichier
ADR.

**Comportement par phase** :
- **Arch (phase 4)** : après création de chaque ADR, append une ligne
  dans le tableau §6 de `workspace/output/.sys/.context/constitution.md` :
  ```markdown
  | ADR-{YYYYMMDDTHHmmss}-{slug} | <titre> | Accepted | 4-ARCH |
  ```
- **Dev-* (phase 5)** : crée uniquement le fichier ADR. L'index §6
  reste à jour seulement pour les ADRs phase 4. Pour les ADRs phase
  5, la source de vérité = `Glob workspace/output/.sys/.context/adrs/*.md`.

Pour reconstruire l'index §6 manuellement après une session
`/dev-run` qui aurait produit des ADRs : prochaine invocation `arch`
(idempotente) re-scanne et reconstruit, OU commande dédiée
`/sdd-rebuild-index` (futur v3.1).

---

## 5. Quand créer un ADR vs ne pas en créer

**Créer un ADR** :
- Choix entre 2+ options techniques avec trade-off (ex. Database-First
  vs Code-First)
- Convention projet inhabituelle ou non triviale (ex. naming
  endpoints, stratégie pagination, format DTOs)
- Décision qui affecte plusieurs US ou plusieurs agents
- Décision qui invalide ou supersede une décision antérieure

**Ne PAS créer d'ADR** :
- Choix entièrement imposé par le stack actif (ex. utiliser Razor
  pour Blazor — c'est inhérent au stack)
- Détail d'implémentation interne à 1 service (ex. nom d'une variable
  privée)
- Décision triviale (ex. ordre des `using`)

---

## 6. Anti-derive

- Aucun ADR ne contient de code applicatif (uniquement décision +
  rationale)
- Aucun ADR ne supersede sans le mentionner explicitement (`Superseded
  by ADR-XXX` dans l'ADR antérieur)
- Aucun ADR ne dépend d'une FEAT ou US qui n'existe pas
- La constitution n'est jamais réécrite intégralement par un agent —
  uniquement étendue
- En cas de conflit entre constitution.md et un ADR plus récent, l'ADR
  fait foi

---

## 7. Localisation des fichiers

```
workspace/output/.sys/.context/
├── constitution.md                    # 1 fichier projet, partagé
└── adrs/
    ├── ADR-001-{slug}.md
    ├── ADR-002-{slug}.md
    └── ...
```

Aucun autre emplacement n'est valide.
