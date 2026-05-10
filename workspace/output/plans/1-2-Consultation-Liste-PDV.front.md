---
us: 1-2-Consultation-Liste-PDV
family: frontend
generated-at: 2026-05-07T00:00:00Z
generated-by: agent dev-frontend (mode :plan)
stack-frontend: react
stack-ui: shadcn
html-source: workspace/input/ui/1-2-Consultation-Liste-PDV.html
---

# Plan technique frontend — 1-2-Consultation-Liste-PDV

## Files

- path: workspace/output/src/simfront/apps/web/src/api/pdv.api.ts
  operation: create
  layer: Component
  covers_acs: [AC-1, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11]
  ds_components: []
  source_html_elements: []
  notes: >
    Client HTTP typé pour le domaine PDV. Fonctions :
    `getPdvList(params: PdvQueryParams): Promise<PagedResponse<PdvDto>>`,
    `getReferentiels(): Promise<PdvReferentiels>`.
    `PdvQueryParams` contient `page`, `pageSize`, `search`, `filters` (objet par colonne).
    Vérification par grep que les routes backend `/api/v1/pdv` existent avant d'écrire
    les fetch calls. Utilise le token MSAL via hook `useMsalToken` de `src/auth/`.

- path: workspace/output/src/simfront/apps/web/src/hooks/usePdvList.ts
  operation: create
  layer: Component
  covers_acs: [AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10]
  ds_components: []
  source_html_elements: []
  notes: >
    Hook TanStack Query : `usePdvList(params: PdvQueryParams)` wrappant
    `useQuery({ queryKey: ['pdv', params], queryFn: () => pdvApi.getPdvList(params) })`.
    `params` inclut page, pageSize, search, filters. Séparation server state / UI state.
    Hook `useReferentiels()` pour Format / Nature Lien / Motif Inactivité (AC-11).

- path: workspace/output/src/simfront/apps/web/src/schemas/pdv.schema.ts
  operation: create
  layer: Component
  covers_acs: [AC-9]
  ds_components: []
  source_html_elements: []
  notes: >
    Schéma Zod pour la validation du paramètre `pageSize` côté client :
    `z.number().int().min(1).max(1000)`. Si valide : envoyé au backend.
    Si invalide (0, négatif, > 1000) : valeur par défaut appliquée (AC-9),
    champ désactivé dans le Select. Schéma `PdvQueryParamsSchema` complet.

- path: workspace/output/src/simfront/apps/web/src/components/pdv/PdvTable.tsx
  operation: create
  layer: Component
  covers_acs: [AC-2, AC-3, AC-4, AC-5, AC-7, AC-8, AC-9, AC-10, AC-11]
  ds_components: [DataTable, Input, Button, Select, Pagination, DropdownMenu, Badge]
  source_html_elements: [<table>, <thead>, <tbody>, <input type="text" placeholder="Rechercher...">, <button class="btn btn-link">, <button class="btn btn-outline">, <button class="col-picker">, <button class="per-page-select">, <div class="pagination">]
  notes: >
    Composant principal du tableau PDV. Intègre :
    - `DataTable` (TanStack Table v8 + shadcn DataTable pattern) avec 13 colonnes,
      server-side sorting + pagination + column filters (AC-10).
    - Colonnes avec libellés VERBATIM : ID PDV, Enseigne, Format, Code postal,
      Commune, Nature Lien, Surface, CATP (K€), Pays, Exploit, Actif,
      Motif Inactivité, Exploité. Colonne Solution visible dans le mockup
      mais absente de l'AC-2 — incluse comme colonne supplémentaire
      (visible dans le mockup HTML → incluse dans le picker colonne).
    - Colonne "Exploité" : affiche "OUI" si périmètre d'exploitation actif,
      sinon "NON" (AC-7). Calculé depuis le DTO backend.
    - Barre de recherche `<Input placeholder="Rechercher..." />` globale
      avec bouton search (Lucide `Search`), debounce 300ms (AC-3).
    - Filtres individuels par colonne via `DropdownMenu` (funnel icon Lucide
      `Filter`) : texte libre pour colonnes textuelles, `Select` pour
      Format / Nature Lien / Motif Inactivité (référentiels AC-11),
      plage numérique pour Surface / CATP (AC-4).
    - Bouton `Button` variant="ghost" + icône Lucide `Filter` : "RÉINITIALISER
      LES FILTRES" — réinitialise tous les filtres + search (AC-3/4 reset).
    - Bouton `Button` variant="outline" + icône Lucide `Download` : "EXPORTER"
      (déclenche export, handler fourni par la Page).
    - Column picker `DropdownMenu` : "N colonnes visibles" + chevron (Lucide
      `ChevronDown`). Gère visibilité des colonnes.
    - Pagination `Pagination` shadcn : première/précédente/pages/suivante/dernière.
      Info "Page X sur Y (Z éléments)" verbatim à gauche. `Select` "10" +
      libellé "Lignes par page" à droite. Valeurs proposées : 10, 25, 50 (AC-5).
    - Empty state : message "Aucun point de vente ne correspond à votre
      recherche" quand dataset filtré vide (AC-8).
    - Scroll horizontal natif sur `.overflow-x-auto` du conteneur.

- path: workspace/output/src/simfront/apps/web/src/pages/PdvListPage.tsx
  operation: create
  layer: Page
  covers_acs: [AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10]
  ds_components: [Button, Card]
  source_html_elements: [<h1 class="page-title">, <div class="page-header">, <div class="table-card">]
  notes: >
    Page principale rendue par la route `/pdv`. Contient :
    - En-tête page : titre `<h1>Points de vente (N)</h1>` où N est le total
      avant filtrage issu de `data.totalCount` (AC-6). Titre statique
      "Points de vente" avec le compteur injecté dynamiquement.
    - Gère l'état de pagination / filtres / search via `useState` + passe à
      `usePdvList(params)`.
    - Monte `<PdvTable />` avec les props nécessaires (data, params, handlers).
    - Gère l'export : handler `handleExport` fourni à `PdvTable`.
    - Protégée par MSAL (requiresAuth = true via route config).
    - Layout : `<div class="max-w-[1357px] mx-auto px-8 py-8">` fidèle au
      `.page { max-width: 1357px }` du HTML.

- path: workspace/output/src/simfront/apps/web/src/routes/pdv.tsx
  operation: create
  layer: Component
  covers_acs: [AC-1]
  ds_components: []
  source_html_elements: []
  notes: >
    Fichier de route TanStack Router file-based pour `/pdv`. Protège la route
    par authentification Azure AD (via `beforeLoad` MSAL check ou guard hook).
    Rend `<PdvListPage />`. Dépendance: US 1-1-Authentification validée (AC-1).

- path: workspace/output/src/simfront/apps/web/src/index.css
  operation: augment
  layer: Style
  preserves: [tailwind-imports, shadcn-theme-variables, existing-tokens]
  adds: [sim-custom-tokens]
  covers_acs: [AC-2]
  ds_components: []
  source_html_elements: [<style> block du HTML mockup]
  notes: >
    Ajout des tokens couleur SIM extraits du HTML mockup dans le bloc `@theme`
    Tailwind v4. Voir section "Theme overrides" ci-dessous. Les tokens
    s'intègrent aux variables CSS shadcn existantes sans les écraser.

## Theme overrides

- token: --color-accent
  value: "#6f5bff"
  source: extrait de workspace/input/ui/1-2-Consultation-Liste-PDV.html style :root --accent
  binding: surcharge --color-primary (shadcn) pour la teinte accent SIM

- token: --color-accent-hover
  value: "#5a47e0"
  source: extrait de style :root --accent-2
  binding: état hover des boutons primaires

- token: --color-accent-soft
  value: "#efeaff"
  source: extrait de style :root --accent-soft
  binding: fond badges / boutons outline hover

- token: --color-accent-softer
  value: "#f6f3ff"
  source: extrait de style :root --accent-softer
  binding: fond hover boutons ghost / col-picker

- token: --color-sim-ink
  value: "#1f1f1f"
  source: extrait de style :root --ink
  binding: titres / textes forts (h1, th)

- token: --color-sim-text
  value: "#2b2b2b"
  source: extrait de style :root --text
  binding: texte courant des cellules

- token: --color-sim-muted
  value: "#6b6b7a"
  source: extrait de style :root --muted
  binding: textes secondaires (pagination info, libellés)

- token: --color-sim-line
  value: "#e8e8ee"
  source: extrait de style :root --line
  binding: bordures tableau, card

- token: --color-sim-line-2
  value: "#f0f0f4"
  source: extrait de style :root --line-2
  binding: séparateurs internes entre cellules

- token: --color-sim-bg-page
  value: "#fafbfc"
  source: extrait de style :root --bg-page
  binding: fond page (body background)

## UI Assets pending

(Aucun asset image non-icône dans le HTML mockup. Toutes les icônes
sont des SVG inline remplacés par Lucide React.)

- Icônes Lucide utilisées (toutes disponibles dans lucide-react) :
  - `Filter` — bouton RÉINITIALISER LES FILTRES + filter par colonne
  - `Download` — bouton EXPORTER
  - `Search` — bouton de recherche globale
  - `ChevronDown` — col-picker + per-page-select

## ACs UI Coverage Summary

| AC | Files |
|----|-------|
| AC-1 | routes/pdv.tsx, pages/PdvListPage.tsx, api/pdv.api.ts |
| AC-2 | components/pdv/PdvTable.tsx |
| AC-3 | components/pdv/PdvTable.tsx, hooks/usePdvList.ts |
| AC-4 | components/pdv/PdvTable.tsx, hooks/usePdvList.ts |
| AC-5 | components/pdv/PdvTable.tsx |
| AC-6 | pages/PdvListPage.tsx |
| AC-7 | components/pdv/PdvTable.tsx |
| AC-8 | components/pdv/PdvTable.tsx |
| AC-9 | components/pdv/PdvTable.tsx, schemas/pdv.schema.ts |
| AC-10 | hooks/usePdvList.ts, api/pdv.api.ts, components/pdv/PdvTable.tsx |
| AC-11 | hooks/usePdvList.ts, api/pdv.api.ts, components/pdv/PdvTable.tsx |

## Notes

- **Colonne "Solution"** : présente dans le HTML mockup (header + données) mais
  absente de la liste AC-2 (13 colonnes nommées). Elle est intégrée dans le
  column picker comme colonne supplémentaire visible par défaut, en respectant
  la source de vérité HTML. Si le backend ne l'expose pas, la colonne sera
  conditionnelle (masquée si DTO absent).

- **"Exploité" (AC-7)** : colonne calculée côté backend (DTO retourne le booléen
  directement). Le frontend affiche "OUI"/"NON" sans recalcul client — conforme
  AC-7 et AC-10 (pas de traitement client du dataset complet).

- **Pagination server-side** (AC-10) : TanStack Table configuré en mode
  `manualPagination: true`, `manualFiltering: true`, `manualSorting: true`.
  Chaque changement de page / filtre / search déclenche une nouvelle requête
  via `usePdvList`.

- **Route guard** (AC-1) : dépend de l'US 1-1-Authentification. Le guard MSAL
  redirige vers la page de connexion Azure AD si token absent. Le composant
  `PdvListPage` ne gère pas la logique auth elle-même.

- **WARN** : projet `simfront` non initialisé (B4) — ce plan est produit en
  mode `:plan` avant `/arch-init`. L'import `useMsalToken` et la structure
  monorepo (`apps/web/src/`) seront disponibles après initialisation.

- **LibStrategy: openapi-codegen** : les types `PdvDto`, `PagedResponse<T>`,
  `PdvReferentiels` seront générés depuis le contrat OpenAPI backend. Le
  fichier `api/pdv.api.ts` utilisera ces types générés (import depuis le
  package contrats partagé). Le plan anticipe cette dépendance.
