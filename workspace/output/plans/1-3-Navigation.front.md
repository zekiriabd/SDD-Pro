---
us: 1-3-Navigation
family: frontend
generated-at: 2026-05-07T00:00:00Z
generated-by: agent dev-frontend (mode :plan)
stack-frontend: front-react
stack-ui: shadcn-ui
html-source: absent
---

# Plan technique frontend — 1-3-Navigation

## Files

- path: workspace/output/src/simfront/apps/web/src/layouts/MainLayout.tsx
  operation: create
  layer: Layout
  covers_acs: [AC-1, AC-2, AC-3]
  ds_components: [Outlet (TanStack Router)]
  notes: >
    Wrapper layout global montant AppSidebar + HeaderBar + <Outlet />.
    Toutes les routes protégées héritent de ce layout.

- path: workspace/output/src/simfront/apps/web/src/routes/__root.tsx
  operation: augment
  layer: Config
  preserves: [MsalAuthenticationTemplate, QueryClientProvider, I18nextProvider]
  adds: [MainLayout comme layout racine pour routes protégées]
  covers_acs: [AC-1, AC-2, AC-3]
  ds_components: []
  notes: >
    Augmentation du root route pour intégrer MainLayout via createRootRoute
    avec le layout wrappant les routes enfants.

- path: workspace/output/src/simfront/apps/web/src/components/AppSidebar.tsx
  operation: create
  layer: Component
  covers_acs: [AC-1]
  ds_components: [Button, Separator]
  notes: >
    Sidebar de navigation latérale. Deux entrées cliquables :
    "Périmètre d'exploitation" (lien vers /perimetre-exploitation)
    et "Configuration de redevances" (lien vers /configuration-redevances).
    Liens via <Link> TanStack Router. Libellés via i18next.

- path: workspace/output/src/simfront/apps/web/src/components/HeaderBar.tsx
  operation: create
  layer: Component
  covers_acs: [AC-2, AC-3]
  ds_components: [DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, Button]
  notes: >
    En-tête présent sur toutes les pages via MainLayout.
    Contient : logo/app name à gauche, dropdown bascule de plateforme au centre
    (liens hors scope dans cette livraison — items non cliquables ou désactivés),
    et UserMenu à droite. Libellés via i18next.

- path: workspace/output/src/simfront/apps/web/src/components/UserMenu.tsx
  operation: create
  layer: Component
  covers_acs: [AC-3, AC-4]
  ds_components: [DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, Avatar, AvatarImage, AvatarFallback]
  notes: >
    Menu utilisateur accessible depuis l'avatar dans HeaderBar.
    Affiche l'avatar (initiales MSAL ou image) + deux entrées :
    "Voir profil" (lien placeholder vers /profil) et "Se déconnecter"
    (appel useMsal().instance.logout()). Libellés via i18next.

- path: workspace/output/src/simfront/apps/web/src/hooks/auth/useUserProfile.ts
  operation: create
  layer: Hook
  covers_acs: [AC-3]
  ds_components: []
  notes: >
    Hook extrayant depuis le compte MSAL actif (useMsal) :
    displayName, initiales (2 premières lettres du displayName),
    et email. Expose { displayName, initials, email }. Utilisé par
    UserMenu pour afficher l'Avatar et le nom.

- path: workspace/output/src/simfront/apps/web/src/routes/perimetre-exploitation/index.tsx
  operation: create
  layer: Route
  covers_acs: [AC-1]
  ds_components: []
  notes: >
    Route file-based TanStack Router vers /perimetre-exploitation.
    Rend PerimetreExploitationPage. Hérite du layout protégé.

- path: workspace/output/src/simfront/apps/web/src/pages/PerimetreExploitationPage.tsx
  operation: create
  layer: Page
  covers_acs: [AC-1]
  ds_components: [Card, CardHeader, CardContent]
  notes: >
    Page placeholder pour "Périmètre d'exploitation". Affiche un
    Card avec titre "Périmètre d'exploitation" et texte "Page en
    cours de développement." Libellés via i18next.

- path: workspace/output/src/simfront/apps/web/src/routes/configuration-redevances/index.tsx
  operation: create
  layer: Route
  covers_acs: [AC-1]
  ds_components: []
  notes: >
    Route file-based TanStack Router vers /configuration-redevances.
    Rend ConfigurationRedevancesPage. Hérite du layout protégé.

- path: workspace/output/src/simfront/apps/web/src/pages/ConfigurationRedevancesPage.tsx
  operation: create
  layer: Page
  covers_acs: [AC-1]
  ds_components: [Card, CardHeader, CardContent]
  notes: >
    Page placeholder pour "Configuration de redevances". Affiche un
    Card avec titre "Configuration de redevances" et texte "Page en
    cours de développement." Libellés via i18next.

- path: workspace/output/src/simfront/apps/web/src/i18n/fr/translation.json
  operation: augment
  layer: Style
  preserves: [clés existantes]
  adds: [nav.perimetreExploitation, nav.configurationRedevances, nav.bascule, nav.voirProfil, nav.seDeconnecter, nav.placeholder]
  covers_acs: [AC-1, AC-2, AC-3, AC-4]
  ds_components: []
  notes: >
    Ajout des clés de traduction FR pour la navigation.

- path: workspace/output/src/simfront/apps/web/src/i18n/en/translation.json
  operation: augment
  layer: Style
  preserves: [clés existantes]
  adds: [nav.perimetreExploitation, nav.configurationRedevances, nav.bascule, nav.voirProfil, nav.seDeconnecter, nav.placeholder]
  covers_acs: [AC-1, AC-2, AC-3, AC-4]
  ds_components: []
  notes: >
    Ajout des clés de traduction EN pour la navigation.

(12 entrées au total)

## Theme overrides

(Aucun mockup HTML source — pas de couleur hex à extraire. Les tokens
utilisés sont les tokens shadcn par défaut : --background, --foreground,
--primary, --muted, --border.)

## UI Assets pending

(Aucun mockup HTML source — aucun <img> non-icône à extraire.
Les icônes sont issues de lucide-react : Menu, ChevronDown, LogOut, User,
Settings, Home.)

## ACs UI Coverage Summary

| AC | Files |
|----|-------|
| AC-1 | AppSidebar.tsx, routes/perimetre-exploitation/index.tsx, pages/PerimetreExploitationPage.tsx, routes/configuration-redevances/index.tsx, pages/ConfigurationRedevancesPage.tsx, i18n/fr/translation.json, i18n/en/translation.json |
| AC-2 | HeaderBar.tsx, MainLayout.tsx, i18n/fr/translation.json, i18n/en/translation.json |
| AC-3 | UserMenu.tsx, hooks/auth/useUserProfile.ts, HeaderBar.tsx, i18n/fr/translation.json, i18n/en/translation.json |
| AC-4 | UserMenu.tsx, i18n/fr/translation.json, i18n/en/translation.json |

## Notes

- **Sidebar** : shadcn/ui ne fournit pas de composant `<Sidebar>` clé-en-main
  dans son catalogue init standard. AppSidebar.tsx est un composant métier
  composé de primitives shadcn (Button variant ghost, Separator) — conforme
  §7 shadcn.md qui indique "Sidebar custom + navigation structurée".

- **Bascule de plateforme (AC-2)** : les liens du dropdown ne redirigent
  vers aucune plateforme tierce dans cette livraison. Les items DropdownMenu
  seront rendus comme disabled ou sans handler onClick — comportement explicite
  de l'AC-2 ("hors scope").

- **MSAL + useUserProfile** : le hook consomme `useMsal()` de `@azure/msal-browser`
  (installé par arch via le stack azure-ad). Aucune valeur Azure AD n'est
  hardcodée ; la déconnexion appelle `instance.logoutRedirect()` conformément
  au Piège 5 du stack auth.

- **Routes file-based** : `routeTree.gen.ts` sera régénéré automatiquement
  par le plugin `@tanstack/router-plugin` au build — ne jamais éditer ce
  fichier manuellement.

- **Dépendance US** : cette US dépend de 1-1-Authentification (MSAL provider
  déjà monté dans App.tsx ou main.tsx). Le hook `useUserProfile` suppose que
  `MsalProvider` est dans l'arbre React — précondition satisfaite par 1-1.
