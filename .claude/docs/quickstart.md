# SDD_Pro — Démarrage rapide

> Document chargé **à la demande** (`Read @.claude/docs/quickstart.md`).
> Référencé depuis `@.claude/CLAUDE.md §10` (slim entry point).

## 1. Sélectionner le stack

Éditer `workspace/input/stack/stack.md` : activer 1 backend, 1 frontend,
1 UI DS, et éventuellement 1 auth.

Renseigner `## Project Config` :
- `AppName`, `BackendName`, `LibName`
- `LibStrategy: shared | openapi-codegen | none` — défaut auto selon
  match des langages back/front

## 2. Renseigner les blocs de configuration de stack.md

Depuis 2026-05-14, plus d'env vars : le Tech Lead écrit les valeurs
dans `stack.md`. L'agent `arch` les propage vers les fichiers de config
applicatifs (`appsettings.json` / `application.yml` /
`config/default.json` / `app/config.py`) lors de Phase A — STEP 4.5.

### `## Active Database` (si backend SQL)

```
DatabaseType: <none|postgres|sqlserver|mysql|sqlite>
DB_HOST: ...
DB_PORT: ...
DB_NAME: ...
DB_USER: ...
DB_PASSWORD: ...
```

### `## Active Auth Specs` (si auth Azure AD)

Ligne chemin `.claude/stacks/auth/azure-ad.md` + clés :

```
AZ_TENANTID: ...
AZ_CLIENTID: ...
AZ_DOMAIN: ...
AZ_AUDIENCES: ...
AZ_BE_CALLBACKPATH: ...
AZ_FE_CALLBACKPATH: ...
```

## 3. Créer une FEAT

```
/feat-generate Auth
```

Répondre aux 3-6 questions interactives. Le fichier
`workspace/input/feats/1-Auth.md` est créé + bootstrap
`workspace/output/.sys/.context/constitution.md`.

## 4. (Optionnel) Déposer les mockups HTML

Sous `workspace/input/ui/` avec la convention `{n}-{m}-{Name}.html`
(basenames identiques aux US à générer).

### 4.bis Assets design-system partagés (convention UX humaine)

`workspace/input/ui/` peut aussi accueillir **deux fichiers spéciaux**
hors convention `{n}-{m}-*.html` :

- `design-system.html` — palette de référence, primitives, états des composants
- `design-system.css` — variables CSS / tokens / utilitaires partagés

Ces fichiers sont **chargés par les autres mockups via `<link rel="stylesheet">`**
mais **ne sont PAS lus par `dev-frontend`** (qui ne grep que les
basenames `{n}-{m}-*.html`). Ils servent au **UX designer humain** pour
maintenir la cohérence visuelle entre mockups successifs.

Lors du scaffolding, `arch` peut copier `design-system.css` dans
`workspace/output/src/{AppName}/src/index.css` comme socle de tokens
shadcn/vuetify/radzen (cf. `.claude/rules/quality.md` Partie B §B.2, ex-ui-tokens.md).

**Non requis** : si vous n'avez pas de palette projet définie, omettre
les 2 fichiers et utiliser les tokens par défaut du Design System.

## 5. Lancer le pipeline

```
/sdd-full 1
```

Pipeline complet de A à Z (phases 2 → 5).

### Variantes plus granulaires

- `/us-generate 1` — US uniquement (phase 2)
- `/feat-validate 1` — readiness gate (phase 2.6)
- `/dev-plan 1` — plans techniques sans coder (phase 2.7)
- `/dev-run 1` — exécution seule (phases 3-4)
- `/qa-generate 1` — tests + coverage + quality (phase 5)

## 6. Vérifier l'état

```
/sdd-status        # vue globale projet
/sdd-status 1      # détail FEAT 1
```

## Référence complète

- Commandes : `@.claude/CLAUDE.md §3`
- Working Agreement : `@.claude/WORKING-AGREEMENT.md`
- Conventions strictes : `@.claude/docs/conventions.md`
- Architecture détaillée : `@.claude/docs/architecture.md`
