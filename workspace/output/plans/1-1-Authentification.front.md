---
us: 1-1-Authentification
family: frontend
generated-at: 2026-05-07T00:00:00Z
generated-by: agent dev-frontend (mode :plan)
stack-frontend: front-react
stack-ui: shadcn-ui
html-source: workspace/input/ui/1-1-Authentification.html
---

# Plan technique frontend — 1-1-Authentification

## Files

- path: workspace/output/src/simfront/apps/web/src/auth/msalConfig.ts
  operation: create
  layer: Auth
  covers_acs: [AC-1, AC-2, AC-3, AC-5, AC-7]
  ds_components: []
  source_html_elements: []
  notes: >
    Config MSAL dynamique. Fetch `/api/config/auth` (endpoint backend public) AVANT
    `new PublicClientApplication(config)` — obligatoire azure-ad §5.2 Piège 4.
    Exporte `getMsalInstance(): Promise<PublicClientApplication>` consommé par main.tsx.
    Aucune valeur Azure AD hardcodée. Variables lues depuis l'endpoint backend uniquement.

- path: workspace/output/src/simfront/apps/web/src/auth/AuthProvider.tsx
  operation: create
  layer: Auth
  covers_acs: [AC-1, AC-2, AC-5, AC-7]
  ds_components: []
  source_html_elements: []
  notes: >
    Provider racine MSAL React. Enveloppe l'app avec `<MsalProvider instance={msalInstance}>`.
    Intègre `<MsalAuthenticationTemplate interactionType={InteractionType.Redirect}>` (azure-ad §5.2 Piège 5)
    pour forcer la redirection Azure AD sur les routes protégées.
    Gère le cas 403 (utilisateur authentifié mais non autorisé) : affiche un écran neutre sans
    fuite sur la cause (AC-7). Gère le 401 retourné par httpClient : relance acquireTokenSilent
    ou redirect (AC-5).

- path: workspace/output/src/simfront/apps/web/src/auth/useAuth.ts
  operation: create
  layer: Auth
  covers_acs: [AC-3, AC-5, AC-8]
  ds_components: []
  source_html_elements: []
  notes: >
    Custom hook `useAuth()` exposant `{ user, token, logout }`.
    `user` = compte MSAL actif (`AccountInfo`). `token` = Bearer token (via
    `acquireTokenSilent` + fallback `acquireTokenRedirect`). `logout` = `msalInstance.logoutRedirect()`
    + retour vers la popup Azure AD (AC-8). Consommé par httpClient.ts et UserMenu.tsx.

- path: workspace/output/src/simfront/apps/web/src/auth/AuthCallback.tsx
  operation: create
  layer: Auth
  covers_acs: [AC-1, AC-2]
  ds_components: []
  source_html_elements: []
  notes: >
    Composant callback MSAL sur la route `/auth/callback`. Rend `<MsalRedirectComponent />`
    (azure-ad §5.2 Piège 5 — route publique sans guard). Après callback réussi, TanStack Router
    redirige vers "Points de vente" (AC-2).

- path: workspace/output/src/simfront/apps/web/src/routes/auth/callback.tsx
  operation: create
  layer: Route
  covers_acs: [AC-1, AC-2]
  ds_components: []
  source_html_elements: []
  notes: >
    Route TanStack Router file-based. Chemin `/auth/callback`, publique (pas de guard MSAL).
    Rend `<AuthCallback />`. Ne fait pas partie des routes protégées — conforme azure-ad §5.2 Piège 5.

- path: workspace/output/src/simfront/apps/web/src/api/httpClient.ts
  operation: create
  layer: Auth
  covers_acs: [AC-3, AC-5]
  ds_components: []
  source_html_elements: []
  notes: >
    Fonction `apiFetch<TResponse>(input, init?)` — fetch typé + Bearer token automatique.
    Lit le token via `useAuth().token` (MSAL `acquireTokenSilent`). Ajoute
    `Authorization: Bearer <token>` sur chaque requête sortante (AC-3).
    Sur réponse 401 : relance `acquireTokenSilent` une fois, puis `acquireTokenRedirect`
    si toujours 401 (AC-5). Mappe 4xx/5xx vers exception typée. Base URL depuis
    `import.meta.env.VITE_API_BASE_URL`. Conforme react.md §3.1 (pas d'Axios).

- path: workspace/output/src/simfront/apps/web/src/main.tsx
  operation: augment
  layer: Config
  preserves: [ReactDOM.createRoot, StrictMode]
  adds: [fetchAuthConfig, PublicClientApplication bootstrap, MsalProvider, QueryClientProvider, RouterProvider, I18nextProvider]
  covers_acs: [AC-1, AC-2, AC-3]
  ds_components: []
  source_html_elements: []
  notes: >
    Point d'entrée bootstrap. Ordre obligatoire (azure-ad §5.2 Piège 4) :
    1. `fetchAuthConfig()` → fetch `/api/config/auth` → construit objet config MSAL en RAM
    2. `new PublicClientApplication(config)` avec les valeurs fetchées
    3. Mount `<MsalProvider>` + `<QueryClientProvider>` + `<RouterProvider>` + `<I18nextProvider>`
    Aucune valeur Azure AD dans les fichiers statiques. Env var `VITE_API_BASE_URL` pour la base URL backend.

- path: workspace/output/src/simfront/apps/web/src/layouts/MainLayout.tsx
  operation: create
  layer: Layout
  covers_acs: [AC-2, AC-8]
  ds_components: [TopBar (custom)]
  source_html_elements: [<header class="topbar">]
  notes: >
    Layout principal : `<header><TopBar /></header>` + `<main><Outlet /></main>`.
    Réservé aux routes protégées (enveloppé par `<MsalAuthenticationTemplate>`).
    Post-auth, l'Outlet affiche la page "Points de vente" (AC-2).

- path: workspace/output/src/simfront/apps/web/src/components/TopBar.tsx
  operation: create
  layer: Component
  covers_acs: [AC-8]
  ds_components: [Avatar, AvatarFallback, DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem]
  source_html_elements: [<header class="topbar">, <div class="brand">, <nav class="nav">, <div class="topbar-right">]
  notes: >
    Barre de navigation principale. Verbatim depuis HTML :
    - Brand : div CSS gradient + texte "média" / "performances" (2 lignes)
    - Nav : 3 liens "Points de vente" (active), "Périmètres d'exploitation", "Configuration des redevances"
    - Droite : <LangSwitcher />, <ContextSwitcher />, <UserMenu />
    Classes Tailwind fidèles aux tokens CSS extraits. Hauteur 64px, border-bottom.
    Les `<a>` de nav traduits en `<Link>` TanStack Router avec classes Tailwind
    (pas NavigationMenu shadcn — structure trop simple, 3 liens plats).

- path: workspace/output/src/simfront/apps/web/src/components/UserMenu.tsx
  operation: create
  layer: Component
  covers_acs: [AC-8]
  ds_components: [Avatar, AvatarFallback, DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator]
  source_html_elements: [<button class="avatar">, <div class="dd-menu user-dd">, <div class="item">]
  notes: >
    Dropdown menu utilisateur. Trigger : `<Avatar><AvatarFallback>` avec initiales (ex. "AZ").
    Items verbatim depuis HTML (dans cet ordre exact) :
    1. icône User (Lucide) + nom utilisateur (depuis `useAuth().user.name`)
    2. icône Lock (Lucide) + "Admin"
    3. icône LogOut (Lucide) + "Déconnexion"
    Clic "Déconnexion" → `useAuth().logout()` (AC-8).
    Toutes les chaînes via i18next (`t('nav.user.name')`, `t('nav.user.role')`, `t('nav.logout')`).

- path: workspace/output/src/simfront/apps/web/src/components/LangSwitcher.tsx
  operation: create
  layer: Component
  covers_acs: []
  ds_components: [DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, Button]
  source_html_elements: [<button class="lang-btn">, <div class="dd-menu lang-dd">, <span class="flag-fr">, <span class="flag-en">]
  notes: >
    Dropdown sélecteur de langue FR/EN. Trigger : `<Button variant="outline">` avec flag FR + "FR" + chevron.
    Items : "FR" (actif) et "EN" — verbatim. Flags reproduits via divs CSS (gradient inline — identique au HTML source).
    Clic item → `i18n.changeLanguage(lang)`. État actif via `i18n.language`.

- path: workspace/output/src/simfront/apps/web/src/components/ContextSwitcher.tsx
  operation: create
  layer: Component
  covers_acs: []
  ds_components: [DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem]
  source_html_elements: [<button class="ctx-btn">, <div class="dd-menu ctx-dd">]
  notes: >
    Dropdown sélecteur de contexte applicatif. Trigger : bouton ghost avec "SIM/Patrimoine" + chevron.
    Items verbatim dans l'ordre exact du HTML :
    "SIM/Patrimoine" (actif), "Admnistration Opérations", "Opérations", "ERP",
    "Portail Client", "Power BI", "Administration", "Portail Enseigne".
    Toutes les chaînes via i18next.

- path: workspace/output/src/simfront/apps/web/src/i18n/index.ts
  operation: create
  layer: Config
  covers_acs: []
  ds_components: []
  source_html_elements: []
  notes: >
    Init i18next + `LanguageDetector` + ressources bundlées (fr + en).
    Langue par défaut : "fr". Fallback : "fr". Détection via browser/navigator.

- path: workspace/output/src/simfront/apps/web/src/i18n/fr/translation.json
  operation: create
  layer: Config
  covers_acs: [AC-8]
  ds_components: []
  source_html_elements: [tous les textes visibles du HTML]
  notes: >
    Clés FR. Libellés verbatim depuis HTML :
    nav.pointsDeVente = "Points de vente"
    nav.perimetres = "Périmètres d'exploitation"
    nav.configuration = "Configuration des redevances"
    nav.user.role = "Admin"
    nav.logout = "Déconnexion"
    brand.line1 = "média"
    brand.line2 = "performances"
    lang.fr = "FR"
    lang.en = "EN"
    context.simPatrimoine = "SIM/Patrimoine"
    context.adminOperations = "Admnistration Opérations"
    context.operations = "Opérations"
    context.erp = "ERP"
    context.portailClient = "Portail Client"
    context.powerBi = "Power BI"
    context.administration = "Administration"
    context.portailEnseigne = "Portail Enseigne"

- path: workspace/output/src/simfront/apps/web/src/i18n/en/translation.json
  operation: create
  layer: Config
  covers_acs: []
  ds_components: []
  source_html_elements: []
  notes: >
    Clés EN (traductions anglaises des mêmes clés que fr/translation.json).
    nav.logout = "Sign out"
    nav.pointsDeVente = "Points of sale"
    etc.

- path: workspace/output/src/simfront/apps/web/src/index.css
  operation: augment
  layer: Style
  preserves: [@import "tailwindcss", tokens shadcn existants]
  adds: [tokens couleurs extraits du HTML mockup, surcharges --color-primary, --color-border, etc.]
  covers_acs: []
  ds_components: []
  source_html_elements: [<style> root vars: --accent, --accent-2, --accent-soft, --accent-softer, --avatar, --ink, --text, --muted, --line, --bg-page]
  notes: >
    Overrides des tokens shadcn pour correspondre à la palette du mockup HTML.
    Ajout dans le bloc `@theme { }` de index.css (Tailwind v4).

- path: workspace/output/src/simfront/apps/web/.env
  operation: create
  layer: Config
  covers_acs: [AC-3]
  ds_components: []
  source_html_elements: []
  notes: >
    Variables d'environnement Vite (dev). VITE_API_BASE_URL=http://localhost:5099.
    Jamais de valeurs Azure AD dans ce fichier — toutes proviennent de /api/config/auth.

(17 entrées au total)

## Theme overrides

- token: --color-primary
  value: "#4f3bd9"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--accent: #4f3bd9`
  binding: --color-primary (Tailwind v4 @theme)

- token: --color-primary-hover
  value: "#3a2bb0"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--accent-2: #3a2bb0`
  binding: --color-primary-hover

- token: --color-accent-soft
  value: "#efeaff"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--accent-soft: #efeaff`
  binding: --color-accent-soft

- token: --color-accent-softer
  value: "#f6f3ff"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--accent-softer: #f6f3ff`
  binding: --color-accent-softer

- token: --color-avatar
  value: "#3f37c9"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--avatar: #3f37c9`
  binding: --color-avatar

- token: --color-foreground
  value: "#2b2b2b"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--text: #2b2b2b`
  binding: --color-foreground

- token: --color-foreground-strong
  value: "#1f1f1f"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--ink: #1f1f1f`
  binding: --color-foreground-strong

- token: --color-muted-foreground
  value: "#6b6b7a"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--muted: #6b6b7a`
  binding: --color-muted-foreground

- token: --color-muted-foreground-2
  value: "#9a9aa8"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--muted-2: #9a9aa8`
  binding: --color-muted-foreground-2

- token: --color-border
  value: "#e8e8ee"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--line: #e8e8ee`
  binding: --color-border

- token: --color-background-page
  value: "#fafbfc"
  source: extrait de workspace/input/ui/1-1-Authentification.html style `--bg-page: #fafbfc`
  binding: --color-background-page

## UI Assets pending

(Aucun asset image externe — le logo brand est un div CSS gradient pur. Les flags FR/EN
sont des divs CSS gradient. Aucun `<img>` non-icône dans le HTML source.)

## ACs UI Coverage Summary

| AC      | Files |
|---------|-------|
| AC-1    | auth/msalConfig.ts, auth/AuthProvider.tsx, routes/auth/callback.tsx, main.tsx |
| AC-2    | auth/AuthProvider.tsx, routes/auth/callback.tsx, layouts/MainLayout.tsx, main.tsx |
| AC-3    | api/httpClient.ts, auth/useAuth.ts, main.tsx |
| AC-4    | (backend-only — hors scope frontend) |
| AC-5    | api/httpClient.ts, auth/useAuth.ts, auth/AuthProvider.tsx |
| AC-6    | (backend-only — hors scope frontend) |
| AC-7    | auth/AuthProvider.tsx |
| AC-8    | components/UserMenu.tsx, auth/useAuth.ts |

## Notes

- **MSAL React** : lib requise — `@azure/msal-browser` + `@azure/msal-react`. Ces packages
  ne figurent pas encore dans `react.libs.json` §2.4. Ils devront être ajoutés au catalogue
  avant la génération du code (`[STACK_LIBRARY_MISSING]` bloquant en phase code).
  Libs suggérées : `@azure/msal-browser@4.x`, `@azure/msal-react@3.x`.

- **Nav horizontale** : les 3 liens de nav sont trop simples pour justifier `<NavigationMenu>`
  shadcn complet. Substitution : liens `<Link>` TanStack Router avec classes Tailwind
  reproduisant fidèlement les styles `.nav a` + `.nav a.active` du HTML (underline accent,
  color accent sur active).

- **Logo brand** : reproduit en pur CSS (`background: radial-gradient(...), linear-gradient(...)`)
  sans asset image — identique au mockup HTML.

- **Flags** : reproduits en pur CSS gradient — identiques au mockup HTML (`flag-fr`, `flag-en`).

- **Chaîne "Admnistration Opérations"** : reprise VERBATIM du HTML (faute de frappe conservée —
  source de vérité = mockup).

- **Breakpoints** : le mockup HTML ne définit aucun breakpoint responsive. Aucun breakpoint
  ajouté — fidélité stricte au mockup.

- **topbar height** : 64px (verbatim HTML `.topbar { height: 64px }`).
