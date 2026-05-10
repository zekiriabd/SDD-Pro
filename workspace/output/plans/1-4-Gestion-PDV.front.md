---
us: 1-4-Gestion-PDV
family: frontend
generated-at: 2026-05-07T00:00:00Z
generated-by: agent dev-frontend (mode :plan)
stack-frontend: front-react
stack-ui: shadcn-ui
html-source: workspace/input/ui/1-4-Gestion-PDV.html
---

# Plan technique frontend — 1-4-Gestion-PDV

## Files

- path: workspace/output/src/simfront/apps/web/src/routes/points-de-vente/$pdvId.tsx
  operation: create
  layer: Route
  covers_acs: [AC-1, AC-2, AC-3]
  ds_components: []
  source_html_elements: []
  notes: >
    Route file-based TanStack Router pour le détail d'un PDV.
    Déclare le paramètre $pdvId, lazy-loads PointDeVentePage.
    Route parente monte MainLayout via <Outlet />.

- path: workspace/output/src/simfront/apps/web/src/pages/PointDeVentePage.tsx
  operation: create
  layer: Page
  covers_acs: [AC-1, AC-2, AC-3, AC-5]
  ds_components: [Tabs, TabsList, TabsTrigger, TabsContent, Button, Badge]
  source_html_elements: [<div class="breadcrumb">, <div class="pdv-title">, <div class="tabs">, <div class="main">, <button class="btn-modify">]
  notes: >
    Vue principale montant :
    - Breadcrumb textuel "Points de vente » Points de vente #{id}" (libellés verbatim).
    - Titre "Points de vente #{id} {NOM_PDV}" (libellé verbatim structuré).
    - Tabs shadcn : "INFORMATIONS POINTS DE VENTE" (active), "PÉRIMÈTRES D'EXPLOITATION", "MATÉRIELS".
    - Grille sidebar + content via PdvSidebar + PdvInfoGenerales.
    - Bouton "MODIFIER" (Button variant="outline", icône Pencil lucide-react).
    - Libellé "Dernière modification le {date}" avec date colorée.
    - Orchestration des états isEditOpen / isDeleteOpen pour PdvFormDialog / PdvDeleteDialog.
    - Consomme usePdvQuery(pdvId).

- path: workspace/output/src/simfront/apps/web/src/components/pdv/PdvSidebar.tsx
  operation: create
  layer: Component
  covers_acs: [AC-1, AC-2]
  ds_components: []
  source_html_elements: [<aside class="sidebar">, <h2>, <nav class="side-nav">, <div class="side-item">]
  notes: >
    Sidebar navigation sections du PDV.
    H2 : "Informations points de vente" (libellé verbatim).
    Items nav (libellés verbatim) :
      - "Informations générales" (active)
      - "Informations complémentaires"
      - "Codes externes"
      - "Périmètre actif"
      - "Indicateur de performance"
    Styles via classes Tailwind reflétant les tokens CSS du mockup
    (bg-page, border-r, border-l-primary active state).
    Props : activeSection: string, onSectionChange: (s: string) => void.

- path: workspace/output/src/simfront/apps/web/src/components/pdv/PdvInfoGenerales.tsx
  operation: create
  layer: Component
  covers_acs: [AC-2]
  ds_components: [Card, CardContent, Label, Input, Select, SelectTrigger, SelectValue, SelectContent, SelectItem]
  source_html_elements: [<div class="form-grid">, <div class="panel">, <div class="field">, <label>, <div class="input">, <div class="input select">]
  notes: >
    Section "Informations générales" en mode lecture (view-only).
    Grille 2 colonnes (grid-cols-2 gap Tailwind) — 2 Card shadcn.

    Panel gauche (libellés verbatim) :
      - PV ID → Input disabled
      - Enseigne → Select disabled
      - Format → Select disabled
      - Type de lien → Select disabled
      - Surface (m²) → Input disabled
      - Centrale de rattachement → Input disabled
      - Code TDlinx → Input disabled
      - Actif → Select disabled (Oui/Non)

    Panel droit (libellés verbatim) :
      - Adresse → Input disabled
      - Complément d'adresse → Input disabled
      - Commune → Input disabled
      - Département → Input disabled
      - Code postal → Input disabled
      - Téléphone → Input disabled
      - Fax → Input disabled
      - Pays → Input disabled

    Props : pdv: PointDeVenteDto (typage depuis contrats openapi-codegen).
    Chaque champ : Label + Input/Select disabled, grille label 180px + champ flex-1.

- path: workspace/output/src/simfront/apps/web/src/components/pdv/PdvFormDialog.tsx
  operation: create
  layer: Component
  covers_acs: [AC-1, AC-2, AC-5]
  ds_components: [Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, Form, FormField, FormItem, FormLabel, FormControl, FormMessage, Input, Select, SelectTrigger, SelectValue, SelectContent, SelectItem, Button]
  source_html_elements: [<div class="field">, <label>, <div class="input">, <div class="input select">, <button class="btn-modify">]
  notes: >
    Dialog formulaire création (AC-1) et modification (AC-2).
    Mode déterminé par prop : mode: "create" | "edit", initialData?: PointDeVenteDto.
    Titre dialog : "Créer un point de vente" (create) / "Modifier le point de vente" (edit).

    Champs du formulaire (libellés verbatim, disposition identique à PdvInfoGenerales) :
      Panel gauche :
        - Enseigne (Select, obligatoire)
        - Format (Select, obligatoire)
        - Type de lien (Select, obligatoire)
        - Surface (m²) (Input number, optionnel)
        - Centrale de rattachement (Input text, optionnel)
        - Code TDlinx (Input text, optionnel)
        - Actif (Select Oui/Non, obligatoire)
      Panel droit :
        - Adresse (Input text, obligatoire)
        - Complément d'adresse (Input text, optionnel)
        - Commune (Input text, obligatoire)
        - Département (Input text, optionnel)
        - Code postal (Input text, obligatoire)
        - Téléphone (Input text, optionnel)
        - Fax (Input text, optionnel)
        - Pays (Input text, obligatoire, défaut "France")

    Validation : react-hook-form + zodResolver(pdvSchema) (AC-5).
    FormMessage affiché sous chaque champ invalide (message d'erreur explicite).
    Bouton submit bloqué tant que validation non verte (AC-5).
    Consomme usePdvCreateMutation / usePdvUpdateMutation selon mode.
    Props : open: boolean, onClose: () => void, mode, initialData, pdvId?.

- path: workspace/output/src/simfront/apps/web/src/components/pdv/PdvDeleteDialog.tsx
  operation: create
  layer: Component
  covers_acs: [AC-3, AC-4]
  ds_components: [Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, Button]
  source_html_elements: []
  notes: >
    Dialog confirmation suppression (AC-3).
    Titre : "Supprimer le point de vente"
    Description : "Cette action est définitive et irréversible. Aucune récupération automatique n'est prévue." (AC-4 verbalisé).
    Boutons : "Annuler" (Button variant="outline") + "Supprimer" (Button variant="destructive").
    Consomme usePdvDeleteMutation.
    Props : open: boolean, onClose: () => void, pdvId: number, pdvName: string.

- path: workspace/output/src/simfront/apps/web/src/schemas/pdv.ts
  operation: create
  layer: Config
  covers_acs: [AC-5, AC-8]
  ds_components: []
  source_html_elements: []
  notes: >
    Schema Zod pdvSchema aligné sur les règles métier (AC-8).
    Champs obligatoires : enseigne, format, typeDeLien, actif, adresse, commune, codePostal, pays.
    Champs optionnels : complementAdresse, departement, surface, centraleDerattachement, codeTDlinx, telephone, fax.
    Messages d'erreur explicites en français (AC-5) :
      ex. "Enseigne obligatoire", "Code postal invalide (5 chiffres)", "Adresse trop longue (max 255 caractères)".
    Exports : pdvSchema (FormValues), type PdvFormValues.

- path: workspace/output/src/simfront/apps/web/src/hooks/pdv/usePdvQuery.ts
  operation: create
  layer: Hook
  covers_acs: [AC-2]
  ds_components: []
  source_html_elements: []
  notes: >
    Hook useQuery TanStack Query : GET /api/v1/points-de-vente/{id}.
    queryKey: ['pointDeVente', pdvId].
    Retourne { data: PointDeVenteDto | undefined, isLoading, isError }.
    Vérifie avant implémentation que la route GET /api/v1/points-de-vente/{id} existe
    dans workspace/output/src/simback/Endpoints/ (contrat backend-first).

- path: workspace/output/src/simfront/apps/web/src/hooks/pdv/usePdvMutations.ts
  operation: create
  layer: Hook
  covers_acs: [AC-1, AC-2, AC-3]
  ds_components: []
  source_html_elements: []
  notes: >
    Trois mutations TanStack Query :
      - usePdvCreateMutation : POST /api/v1/points-de-vente → 201 (AC-1)
      - usePdvUpdateMutation : PUT /api/v1/points-de-vente/{id} → 200 (AC-2)
      - usePdvDeleteMutation : DELETE /api/v1/points-de-vente/{id} → 204 (AC-3)
    Chaque mutation invalide queryKey ['pointDeVente', ...] et ['pointsDeVente'] on success.
    Erreurs 400 (détail par champ) remontées vers FormMessage via setError react-hook-form.
    Erreurs 401/403 loggées via utils/logger.ts.
    Vérifie avant implémentation les routes POST/PUT/DELETE dans workspace/output/src/simback/Endpoints/.

- path: workspace/output/src/simfront/apps/web/src/api/pdvApi.ts
  operation: augment
  layer: Config
  preserves: [pointsDeVenteApi existant si présent]
  adds: [getPdvById, createPdv, updatePdv, deletePdv]
  covers_acs: [AC-1, AC-2, AC-3]
  ds_components: []
  source_html_elements: []
  notes: >
    Fonctions typed utilisant apiFetch<T> (httpClient.ts).
    Toutes les URLs préfixées avec import.meta.env.VITE_API_BASE_URL.
    getPdvById(id): Promise<PointDeVenteDto>
    createPdv(payload: PdvFormValues): Promise<PointDeVenteDto>
    updatePdv(id: number, payload: PdvFormValues): Promise<PointDeVenteDto>
    deletePdv(id: number): Promise<void>

- path: workspace/output/src/simfront/apps/web/src/index.css
  operation: augment
  layer: Style
  preserves: [tokens shadcn existants, @import tailwindcss, @theme existant]
  adds: [overrides tokens accent + bg-page + muted extraits du HTML mockup]
  covers_acs: []
  ds_components: []
  source_html_elements: [<style> :root { --accent: #6f5bff; --bg-page: #f7f6fb; ... }]
  notes: >
    Overrides CSS variables dans @theme pour correspondre aux couleurs du mockup.
    Voir section "Theme overrides" ci-dessous pour la liste complète.

- path: workspace/output/src/simfront/apps/web/src/i18n/fr/translation.json
  operation: augment
  layer: Config
  preserves: [clés existantes]
  adds: [namespace pdv.* avec toutes les clés UI de cette US]
  covers_acs: [AC-1, AC-2, AC-3, AC-5]
  ds_components: []
  source_html_elements: []
  notes: >
    Clés ajoutées sous namespace "pdv" :
      pdv.breadcrumb.list, pdv.breadcrumb.detail,
      pdv.title, pdv.tabs.informations, pdv.tabs.perimetres, pdv.tabs.materiels,
      pdv.sidebar.title, pdv.sidebar.infoGenerales, pdv.sidebar.infoComplementaires,
      pdv.sidebar.codesExternes, pdv.sidebar.perimetreActif, pdv.sidebar.indicateurPerf,
      pdv.section.infoGenerales, pdv.btn.modifier, pdv.lastMod,
      pdv.fields.pvId, pdv.fields.enseigne, pdv.fields.format, pdv.fields.typeDeLien,
      pdv.fields.surface, pdv.fields.centrale, pdv.fields.codeTDlinx, pdv.fields.actif,
      pdv.fields.adresse, pdv.fields.complementAdresse, pdv.fields.commune,
      pdv.fields.departement, pdv.fields.codePostal, pdv.fields.telephone,
      pdv.fields.fax, pdv.fields.pays,
      pdv.form.createTitle, pdv.form.editTitle, pdv.form.submit, pdv.form.cancel,
      pdv.delete.title, pdv.delete.description, pdv.delete.confirm, pdv.delete.cancel,
      pdv.validation.required, pdv.validation.codePostalFormat, pdv.validation.maxLength

(12 fichiers au total)

## Theme overrides

Liste des couleurs extraites du HTML mockup à matérialiser dans index.css @theme :

- token: --color-accent
  value: #6f5bff
  source: extrait de workspace/input/ui/1-4-Gestion-PDV.html style="--accent: #6f5bff"
  binding: --color-primary (shadcn primary → accent violet)

- token: --color-accent-2
  value: #5a47e0
  source: extrait --accent-2: #5a47e0
  binding: --color-primary/90 (hover state)

- token: --color-accent-soft
  value: #efeaff
  source: extrait --accent-soft: #efeaff
  binding: custom var --color-accent-soft (utilisé pour bg active states)

- token: --color-accent-softer
  value: #f6f3ff
  source: extrait --accent-softer: #f6f3ff
  binding: custom var --color-accent-softer (hover sur items nav)

- token: --color-bg-page
  value: #f7f6fb
  source: extrait --bg-page: #f7f6fb
  binding: --color-background (shadcn background → bg page légèrement violacé)

- token: --color-bg-field
  value: #faf9fd
  source: extrait --bg-field: #faf9fd
  binding: custom var --color-bg-field (input backgrounds)

- token: --color-muted
  value: #6b6b7a
  source: extrait --muted: #6b6b7a
  binding: --color-muted-foreground

- token: --color-link
  value: #7a3fb5
  source: extrait --link: #7a3fb5
  binding: custom var --color-link (breadcrumb links)

- token: --color-link-2
  value: #4a8fd9
  source: extrait --link-2: #4a8fd9
  binding: custom var --color-link-2 (date modification)

- token: --color-ink
  value: #1f1f1f
  source: extrait --ink: #1f1f1f
  binding: --color-foreground (texte principal)

- token: --color-line
  value: #e8e8ee
  source: extrait --line: #e8e8ee
  binding: --color-border

## UI Assets pending

Aucun asset image non-icône identifié dans le HTML mockup.
Les icônes utilisées sont inline SVG (crayon/pencil) → mappé vers `<Pencil />` lucide-react.

## ACs UI Coverage Summary

| AC | Fichiers |
|----|---------|
| AC-1 (création accessible depuis liste via action visible) | PointDeVentePage.tsx, PdvFormDialog.tsx, usePdvMutations.ts, pdvApi.ts |
| AC-2 (modification accessible ligne par ligne, formulaire pré-rempli) | PointDeVentePage.tsx, PdvInfoGenerales.tsx, PdvFormDialog.tsx, usePdvQuery.ts, usePdvMutations.ts |
| AC-3 (suppression via dialog de confirmation explicite) | PdvDeleteDialog.tsx, usePdvMutations.ts |
| AC-4 (suppression définitive — verbalisé dans UI) | PdvDeleteDialog.tsx |
| AC-5 (messages d'erreur explicites + blocage envoi) | PdvFormDialog.tsx, pdv.ts (schema Zod), i18n fr/translation.json |
| AC-6 (validation backend 400) | Backend — hors scope frontend ; gestion erreurs 400 dans usePdvMutations.ts |
| AC-7 (validation avant logique métier) | Backend uniquement |
| AC-8 (cohérence règles frontend/backend) | pdv.ts (schema Zod aligné sur backend FluentValidation) |
| AC-9 (droits CRUD pour utilisateur authentifié) | Routes protégées via <ProtectedRoute> dans $pdvId.tsx |
| AC-10 (401/400/403 backend retournés) | usePdvMutations.ts (interception erreurs apiFetch) |

## Notes

- La page PDV est une vue détail (fiche complète) — le formulaire création/modification
  est rendu en Dialog (pas en page séparée) car le HTML mockup montre une navigation
  dans la fiche existante sans indication de route séparée pour le formulaire.

- La sidebar "Informations points de vente" avec 5 sections est rendue en composant
  PdvSidebar dédié (pas via shadcn Sidebar block) car la structure est custom
  (border-left active state, pas de collapsible). Justifié par l'absence du composant
  Sidebar shadcn dans le mapping strict HTML→DS pour ce pattern.

- Les tabs "PÉRIMÈTRES D'EXPLOITATION" et "MATÉRIELS" sont rendus avec leur libellé
  verbatim mais sans contenu (TabsContent vide avec placeholder) — leur implémentation
  complète relève d'US séparées non présentes dans 1-4.

- Icône crayon (MODIFIER button) : SVG inline du mockup traduit en `<Pencil size={12} />`
  de lucide-react (pack officiel shadcn).

- La route $pdvId.tsx impose la vérification FRONTEND_BACKEND_CONTRACT_GAP avant
  implémentation des hooks : grep sur workspace/output/src/simback/Endpoints/ pour
  GET/POST/PUT/DELETE /api/v1/points-de-vente.

- LibStrategy openapi-codegen : les types PointDeVenteDto et PdvFormValues sont
  importés depuis le package contracts généré (`@simfront/contracts`). Si les types
  ne sont pas encore générés, utiliser des types locaux temporaires typés.
