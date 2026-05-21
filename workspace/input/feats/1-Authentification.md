# Spec: 1-1-Authentification

Spec ID: 1-1-Authentification

## Context

L'application n'a aucun mécanisme d'authentification. Elle doit s'intégrer au tenant Azure Active Directory de l'organisation : toute la sécurité (identité + autorisation) repose sur Azure AD, sans user store local ni login custom.

## Objective

Tout accès fonctionnel de l'application est conditionné à un JWT Azure AD valide, validé côté backend, avec autorisation dérivée des groupes Azure AD.

## Quantified Goal

- **Metric** : 100% des endpoints non publics rejettent les requêtes sans JWT valide ; `/login` flow SSO Microsoft complet
- **Target** : login SSO end-to-end < 3s p95 ; 0 secret hardcodé dans le code (vérifié par security-reviewer)
- **Deadline** : `<à préciser>`

## Non-Functional Constraints

- **Volume** : single tenant, ~`<à préciser>` utilisateurs actifs simultanés
- **Performance** : login redirect end-to-end < 3s p95 ; JWT validation backend < 50ms p99
- **Retention** : aucune session/token stocké côté backend (stateless JWT) ; cache MSAL côté frontend uniquement
- **Compliance** : conformité politique Azure AD du tenant ; pas de PII stockée côté app
- **Integration** : MSAL frontend + spring-security-oauth2-resource-server backend + Azure AD App Registration
- **Degraded mode** : mode "auth seule" si claim `groups` absent (utilisateur authentifié mais 403 sur endpoints scope-gated, cf. SFD-6 AC-8)

## Actors

- Utilisateur Azure AD: se connecte avec son compte d'organisation
- Frontend SPA: porte le flow MSAL (Authorization Code + PKCE)
- Backend API: valide chaque JWT et applique l'autorisation par groupes
- Tenant Azure AD: source unique d'identité et de groupes

## Functional Needs

- SFD-1: Se connecter à l'application via Microsoft Azure AD (flow Authorization Code + PKCE côté frontend MSAL)
- SFD-2: Valider le JWT côté backend sur chaque requête protégée (signature, issuer, audience, expiration)
- SFD-3: Autoriser ou refuser l'accès aux ressources selon les groupes Azure AD présents dans le claim `groups`
- SFD-4: Exposer un endpoint public `GET /auth/config` retournant la configuration Azure AD nécessaire au frontend (authority, clientId, scopes, redirectUri)
- SFD-5: Charger toute la configuration Azure AD depuis des variables d'environnement (aucune valeur hardcodée)
- SFD-6: Supporter un mode dégradé "auth seule" si le mapping groupes → permissions est absent (utilisateur authentifié mais sans droits étendus)
- SFD-7: Afficher une page de démarrage publique `/login` (mockup `1-1-Connexion.html`) quand l'utilisateur n'est pas authentifié ; cette page contient un bouton "Se connecter avec Microsoft" qui déclenche le **redirect MSAL** (`loginRedirect`) du tenant Azure AD
- SFD-8: Après login réussi, rediriger automatiquement l'utilisateur vers la page d'accueil par défaut `/campagnes` (page protégée)
- SFD-9: Le layout principal (menu global) enveloppe **toutes** les routes protégées de l'application ; la page `/login` est la seule exception (page autonome sans menu)

## Business Rules

- BR-1: Tous les endpoints backend sont protégés par JWT, sauf `GET /auth/config` qui est public
- BR-2: L'autorisation s'appuie exclusivement sur les groupes Azure AD du claim `groups` (pas de rôles locaux, pas de table d'utilisateurs)
- BR-3: Le frontend ne fait que masquer l'UI selon les groupes ; la décision d'autorisation réelle est prise côté backend (401 / 403)
- BR-4: Un refus d'accès (403) ne déclenche pas de re-login (le token reste valide, c'est le scope qui est insuffisant)
- BR-5: Le JWT est transporté en `Authorization: Bearer <token>` ; aucun parsing manuel du JWT côté application (uniquement le middleware standard)
- BR-6: Aucun secret Azure AD ne réside côté client (clientSecret backend uniquement si confidential client — sinon flow PKCE pur SPA)
- BR-7: La configuration Azure AD (tenantId, clientId, audiences, domain, callback paths) vient des variables d'environnement `AZ_TENANTID`, `AZ_CLIENTID`, `AZ_DOMAIN`, `AZ_AUDIENCES`, `AZ_BE_CALLBACKPATH`, `AZ_FE_CALLBACKPATH`
- BR-8: La route `/login` est **publique** (aucun guard, aucune redirection si l'utilisateur arrive dessus) et constitue le seul point d'entrée public de l'application. Toute autre URL accédée par un utilisateur non authentifié déclenche une redirection client-side vers `/login` (pas de redirection automatique vers Azure AD — c'est le clic utilisateur sur `/login` qui déclenche `loginRedirect`).
- BR-9: **Le mode d'authentification MSAL est `loginRedirect` (PAS `loginPopup`)** — choix arbitré par post-mortem session 2026-05-19 (AADSTS50011 + bloqueurs popup enterprise). Le SPA navigue plein écran vers Azure AD ; au retour sur `/authentication/login-callback`, `handleRedirectPromise()` au bootstrap MSAL extrait l'`AuthenticationResult` et l'enregistre. **Anti-pattern interdit** : `loginPopup({ scopes })` — fragile sur Firefox/Safari, bloqué par certaines policies d'entreprise, et certaines App Registrations Azure AD (mode SPA + cross-origin token redemption strict) ne tolèrent que le redirect flow.
- BR-10: Après le retour `loginRedirect` (callback `/authentication/login-callback` traité par `handleRedirectPromise()` au bootstrap), `LoginCallbackPage` redirige vers `/campagnes` (page d'accueil par défaut). Si l'utilisateur venait d'une route protégée X, on peut optionnellement mémoriser X et y rediriger après login (hors scope v1).
- BR-11: Le **layout principal** (menu global cf. SPEC 2) enveloppe toutes les routes protégées. La route `/login` est la seule exception : page autonome sans menu, conformément au mockup `1-1-Connexion.html`.
- BR-12: **CORS obligatoire** côté backend. Le SPA et le backend tournent par défaut sur deux origins distincts (`http://localhost:5173` dev / `http://localhost:4173` preview / origin de prod). Le backend expose une `CorsConfigurationSource` (origins via env `APP_CORS_ALLOWED_ORIGINS`, methods `GET POST PUT PATCH DELETE OPTIONS`, headers `*`, exposed `Location, Content-Disposition`, credentials `true`) et branche `.cors {}` dans `SecurityFilterChain`. Sans ça, `fetch('/auth/config')` côté front lève `TypeError: Failed to fetch`.
- BR-13: **Hygiène format env vars** (post-mortem 2026-05-11) — l'agent (backend ou frontend) qui consomme `AZ_AUDIENCES` DOIT strip les guillemets parasites `"..."` autour de chaque token avant usage (cas Windows où le shell capture les quotes dans la valeur). De même, `AZ_FE_CALLBACKPATH` lu côté Git Bash subit la conversion MSYS (`/login-callback` → `C:/Program Files/Git/login-callback`) — l'agent backend DOIT strip ce préfixe par regex avant d'émettre la valeur dans `/auth/config` (cf. §2.102 stack azure-ad).
- BR-14: **Redirect URI MSAL = `window.location.origin + AZ_FE_CALLBACKPATH`** (post-mortem 2026-05-11) — l'App Registration Azure AD enregistre une **URI complète** (ex. `https://localhost:5185/login-callback` en dev HTTPS, `https://app.exemple.com/login-callback` en prod). Le frontend DOIT composer `redirectUri: window.location.origin + cfg.redirectUri` lors de la construction de `PublicClientApplication` ET ne JAMAIS utiliser `window.location.origin` seul (path manquant). Sinon Azure répond `AADSTS900971: No reply address provided` (ou `AADSTS50011: The redirect URI does not match`). Le path retourné par `/auth/config` doit donc être un path absolu commençant par `/` (jamais une URL complète, jamais vide). En prod, l'origin diffère mais le path reste identique — toujours composé runtime côté SPA.
- BR-15: **HTTPS obligatoire pour MSAL + Azure AD** (post-mortem 2026-05-11) — Azure AD exige HTTPS pour toute Redirect URI **hors** `http://localhost` strict. Si l'App Registration liste `https://localhost:5185/authentication/login-callback`, le SPA DOIT tourner sur HTTPS port 5185 (pas HTTP port 5173). En dev :
  - Frontend Vite : plugin `@vitejs/plugin-basic-ssl` (cert auto-signé) + `server.https: {}` + `server.port: 5185` dans `vite.config.ts`
  - Backend Spring : `server.port: 44328` + `server.ssl.enabled: true` + keystore PKCS12 généré via `keytool`
  - L'utilisateur accepte le cert auto-signé une fois par origin
  - Les ports + URLs sont configurés dans `## Project Config` de `workspace/input/stack/stack.md` (clés `FrontendDevUrl`, `BackendDevUrl`)
  - CORS backend `APP_CORS_ALLOWED_ORIGINS` doit lister les origins HTTPS exacts
- BR-16: **Variables d'environnement frontend Vite** — la base URL backend est exposée au SPA via `VITE_API_BASE_URL` (préfixe `VITE_` obligatoire — cf. azure-ad.md §5.2.7.2 / BR-9). Pour le dev HTTPS : `VITE_API_BASE_URL=https://localhost:44328` dans un `.env.local` à la racine de `apps/web/`. **Anti-pattern** : lire `BACKEND_URL` sans préfixe `VITE_` — invisible côté navigateur.
- BR-17: **Bootstrap MSAL — `handleRedirectPromise()` + `acquireTokenSilent` fallback (load-bearing)** — post-mortem session 2026-05-19 (401 systématique sur `/api/v1/*` après reload de page). Le singleton MSAL `msalInstance.ts` au bootstrap DOIT exécuter cette séquence :
  1. `await instance.initialize()`
  2. `const result = await instance.handleRedirectPromise()` — récupère le résultat OAuth si on revient de `/authentication/login-callback` ; `result.accessToken` est poussé en `sessionStorage[TOKEN_STORAGE_KEY]`.
  3. `instance.setActiveAccount(result?.account ?? instance.getAllAccounts()[0])`
  4. **Si `result === null` ET un compte est en cache** (cas reload SPA sans redirect en cours) → `await instance.acquireTokenSilent({ scopes: cfg.scopes, account })` puis push du token frais dans `sessionStorage`.
  Sans l'étape 4, `httpClient` n'a aucun Bearer à envoyer après chaque reload → 401 systématique sur tous les `/api/*`. Le try/catch sur étape 4 est silencieux (si refresh token expiré → laisser passer, le prochain `apiFetch` lèvera 401 → AuthGuard renverra sur `/login`).

## Acceptance Criteria

- AC-1: Un utilisateur non authentifié accédant à une ressource protégée est redirigé vers le flow de login Azure AD
- AC-2: Un utilisateur authentifié avec un JWT valide accède aux ressources autorisées par ses groupes
- AC-3: Une requête backend sans header `Authorization` retourne `401 Unauthorized`
- AC-4: Une requête backend avec JWT expiré retourne `401 Unauthorized`
- AC-5: Une requête backend avec JWT valide mais groupe insuffisant retourne `403 Forbidden` (sans re-login)
- AC-6: `GET /auth/config` retourne un JSON `{ authority, clientId, scopes, redirectUri }` sans authentification
- AC-7: Aucune valeur Azure AD (tenantId, clientId, etc.) n'apparaît dans le code source — uniquement via env vars
- AC-8: Si le mapping groupes → permissions n'est pas disponible, l'utilisateur reste authentifié mais en mode dégradé (auth seule, fonctionnalités limitées)
- AC-9: Un utilisateur non authentifié accédant à `/` ou à toute route protégée est redirigé client-side vers `/login` (page mockup `1-1-Connexion.html` rendue avec composants shadcn)
- AC-10: La page `/login` affiche un bouton "Se connecter avec Microsoft" qui, au clic, appelle `instance.loginRedirect({ scopes, redirectUri })` — **redirection plein écran vers Azure AD** (PAS de popup). Au retour sur `/authentication/login-callback`, `handleRedirectPromise()` au bootstrap MSAL extrait l'`AuthenticationResult`.
- AC-11: Après le retour `loginRedirect` traité par `handleRedirectPromise()` puis `LoginCallbackPage`, le frontend redirige vers `/campagnes` (page d'accueil par défaut)
- AC-12: La page `/login` est rendue **sans le menu global** (page autonome) ; toutes les autres routes protégées sont rendues **avec le menu** (MainLayout)
- AC-13: Si l'utilisateur abandonne le flow Azure AD côté Microsoft (back navigator, ferme l'onglet), l'app revient sur `/login` sans erreur bloquante au prochain accès. Pas de popup à fermer (cf. BR-9 : redirect, pas popup).
- AC-19: **Token rafraîchi au bootstrap (BR-17)** — après chaque reload de page sur une route protégée, le bootstrap MSAL `msalInstance.ts` invoque `acquireTokenSilent` si aucun redirect n'est en cours mais qu'un compte est en cache, puis stocke l'access token frais dans `sessionStorage`. Test d'acceptation : naviguer sur `/campagnes`, F5, observer que `/api/v1/annonceurs` est appelé avec un Bearer valide (pas de 401).
- AC-14: Le SPA peut tourner sur `http://localhost:5173` et appeler `http://localhost:8080/auth/config` sans erreur CORS — le backend retourne `Access-Control-Allow-Origin: <origin du SPA>` + `Allow-Credentials: true` sur toutes les requêtes pré-flight et GET
- AC-15: L'endpoint `/auth/config` retourne `scopes` au format strict **singleton** `["api://${AZ_CLIENTID}/access_as_user"]` (UN seul élément, dérivé de `AZ_CLIENTID` — **PAS** de `AZ_AUDIENCES`), et un `redirectUri` au format strict `/path` sans préfixe de path Windows MSYS. **Anti-pattern interdit** : construire les scopes par split de `AZ_AUDIENCES` (multi-valeurs) — provoque `AADSTS900971` côté MSAL.js v3 car un `loginRedirect` n'autorise qu'un resource unique. `AZ_AUDIENCES` est utilisé exclusivement côté backend pour valider les JWT (cf. BR-7, stack `azure-ad.md §3` + §5.2.7.1).
- AC-16: Le frontend MSAL initialise `PublicClientApplication` **après** la résolution du `fetch /auth/config` (pas avant) — `loadMsalConfig()` est awaitée par `main.tsx` avant le `createRoot().render(<MsalProvider/>)`. Tant que le backend est down, le SPA affiche une page d'erreur "Backend indisponible" plutôt que crash
- AC-17: Le `redirectUri` MSAL transmis à Azure est composé runtime `window.location.origin + cfg.redirectUri` (ex. `https://localhost:5185/authentication/login-callback` en dev, `https://app.exemple.com/authentication/login-callback` en prod). Le path canonique est `/authentication/login-callback` (convention Blazor WASM, partagée avec React/MSAL.js — aligne le SPA sur les URIs déjà déclarées de l'App Reg sans dupliquer côté Azure). Cette URI complète DOIT être enregistrée dans l'App Registration Azure AD onglet Authentication → Single-page application → Redirect URIs. Erreur Azure `AADSTS900971` ou `AADSTS50011` au login = mismatch d'URI à corriger côté portail ou côté `redirectUri` SPA.
- AC-18: En dev local, le SPA tourne sur `https://localhost:5185/` (Vite + `@vitejs/plugin-basic-ssl`) et le backend sur `https://localhost:44328/` (Spring + keystore PKCS12). `VITE_API_BASE_URL=https://localhost:44328`. `APP_CORS_ALLOWED_ORIGINS=https://localhost:5185`. Les certificats auto-signés sont acceptés manuellement par le navigateur la première fois.

## Dependencies

- NONE (spec fondatrice — toutes les autres specs dépendent de celle-ci)

## Functional Deliverables

- FD-1: Endpoint public `GET /auth/config` (backend) retournant la configuration Azure AD pour le frontend
- FD-2: Middleware backend de validation JWT (signature, issuer, audience, expiration) appliqué à tous les endpoints non publics
- FD-3: Pipeline d'autorisation backend basé sur le claim `groups` du JWT (401 / 403 selon le cas)
- FD-4: Intégration MSAL côté frontend (Authorization Code + PKCE) avec interception automatique des appels HTTP pour ajouter le header `Authorization: Bearer`
- FD-5: ~~Mécanisme de logout~~ **(retiré — pas de spécification, voir Out of Scope)**. La déconnexion est entièrement déléguée à Azure AD via l'URL de logout standard (`/oauth2/v2.0/logout`). Côté frontend, MSAL fournit `logoutRedirect({ postLogoutRedirectUri })` (1 ligne) ; côté backend, aucun code.
- FD-6: Lecture de la configuration Azure AD depuis les variables d'environnement (backend et frontend via `/auth/config`)
- FD-7: Page publique `/login` côté frontend (composant `LoginPage` mappant le mockup `1-1-Connexion.html` vers shadcn) avec bouton "Se connecter avec Microsoft" déclenchant `loginRedirect`
- FD-9: Page `/authentication/login-callback` côté frontend (composant `LoginCallbackPage`) — route publique, attend que `handleRedirectPromise()` ait été résolu au bootstrap MSAL puis redirige vers `/campagnes`. URI enregistrée côté Azure AD App Registration section "Single-page application".
- FD-8: Layout principal `MainLayout` (menu global cf. SPEC 2) enveloppant toutes les routes protégées ; `/login` exclue
- FD-13: Guard de route global (dans `__root.tsx` ou layout parent `_protected`) qui : (1) si user non authentifié et route ≠ `/login` → `Navigate to="/login"`, (2) si user authentifié → rendre `<MainLayout><Outlet/></MainLayout>`
- FD-10: Route `/` index qui redirige : authentifié → `/campagnes`, sinon → `/login`
- FD-11: Bean Spring `CorsConfigurationSource` (`CorsConfig.kt`) listant les origins autorisés via `APP_CORS_ALLOWED_ORIGINS` (CSV, default `http://localhost:5173,http://localhost:4173`) ; branché via `http.cors {}` dans `SecurityFilterChain`
- FD-12: `AuthConfigController.kt` (GET `/auth/config`, public via `permitAll(HttpMethod.GET)` dans `SecurityConfig`), lecture des env vars `AZ_TENANTID / AZ_CLIENTID / AZ_AUDIENCES / AZ_FE_CALLBACKPATH` avec strip quotes + strip préfixe MSYS Git Bash dans `AZ_FE_CALLBACKPATH`

## Out of Scope

- MFA (géré par Azure AD lui-même, hors application)
- Audit logs de connexion
- Fédération multi-tenant
- Gestion / création / désactivation d'utilisateurs (responsabilité Azure AD)
- Login interne, mot de passe local, password reset applicatif
- Roles / permissions stockés en base applicative
- **Déconnexion applicative** : entièrement déléguée à Azure AD. Aucun endpoint backend de logout, aucun code métier. Côté frontend, MSAL gère via `logoutRedirect({ postLogoutRedirectUri })` (configuration uniquement, pas de spec). Le `postLogoutRedirectUri` est déclaré dans l'App Registration Azure AD (portail) — pas de fichier projet à générer pour cette logique.

---

## Risques Identifiés

| ID | Risque | Sévérité | Mitigation |
|---|---|---|---|
| RISK-1 | Les variables d'environnement Azure AD (`AZ_TENANTID`, `AZ_CLIENTID`, etc.) ne sont pas configurées ou contiennent des valeurs parasites (guillemets Windows, préfixe MSYS) au moment du premier déploiement, rendant l'app totalement inaccessible | high | Documenter et valider les env vars dans un checklist de déploiement ; implémenter un health-check au démarrage backend qui valide la présence et le format des 6 variables ; BR-13 strip déjà tracé |
| RISK-2 | La Redirect URI enregistrée dans l'App Registration Azure AD ne correspond pas à celle composée runtime par le SPA (`window.location.origin + cfg.redirectUri`), provoquant `AADSTS50011` en prod avec une URL différente du dev | high | Lister explicitement toutes les Redirect URIs prod+dev dans l'App Reg dès l'init ; AC-17 couvre le format ; valider par smoke test login en pré-prod |
| RISK-3 | ~~Le flow popup MSAL bloqué par les navigateurs~~ **résolu (négatif)** : le flow choisi est `loginRedirect` (BR-9), pas popup. Aucun risque de blocage popup. Trade-off : l'app perd brièvement son état SPA pendant la redirection plein écran (acceptable v1) ; au retour, `handleRedirectPromise()` au bootstrap restaure l'`AuthenticationResult`. | low | — |
| RISK-4 | Les certificats auto-signés HTTPS dev (Vite `@vitejs/plugin-basic-ssl` + Spring keystore PKCS12) génèrent des erreurs `net::ERR_CERT_AUTHORITY_INVALID` non acceptées par le navigateur, bloquant les appels CORS et le flow MSAL | medium | Documenter la procédure d'acceptation manuelle du cert dans le README projet ; valider en CI avec un cert de dev reconnu ou en HTTP strict `localhost` uniquement |
| RISK-5 | La décision d'autorisation backend basée uniquement sur le claim `groups` Azure AD échoue si les groupes ne sont pas inclus dans le JWT (token trop grand, option Azure AD "Group Claims" non activée dans le manifest de l'App Reg) | medium | Vérifier l'activation de "Group Claims" dans l'App Registration lors de la configuration initiale ; logguer un WARNING si le claim `groups` est absent dans le JWT validé |
| RISK-6 | MSAL stocke les tokens dans `localStorage` par défaut — en cas de XSS sur la SPA React/shadcn, un attaquant peut exfiltrer le Bearer token et l'utiliser depuis n'importe quelle machine jusqu'à expiration du JWT (TTL Azure AD défaut = 1h) | high | Configurer `cacheLocation: "sessionStorage"` dans l'instance `PublicClientApplication` (tokens détruits à la fermeture du tab) ; ajouter une Content-Security-Policy stricte côté backend (`script-src 'self'`) pour réduire la surface XSS ; AC-7 couvre l'absence de secret client mais ne couvre pas le storage |
| RISK-7 | La base PostgreSQL n'est pas accessible depuis le backend au démarrage (mauvais DSN, réseau, credentials) — Spring Boot fail-fast au boot, le backend ne démarre pas et la FEAT entière est inaccessible même pour l'endpoint public `/auth/config` | medium | Séparer la configuration DB du reste : si la FEAT 1 n'a pas d'entités DB propres, désactiver l'auto-création schema Spring au boot pour cette FEAT ; documenter le DSN postgres dans la checklist de déploiement aux côtés des env vars Azure AD |

---

## Hypothèses

| ID | Hypothèse | Statut | Validation requise |
|---|---|---|---|
| ASS-1 | L'organisation dispose d'un tenant Azure AD actif et l'équipe projet a les droits pour créer/modifier une App Registration (ajouter Redirect URIs, activer Group Claims) | à valider | Confirmer avec l'administrateur Azure AD de l'organisation avant le sprint 1 |
| ASS-2 | Les utilisateurs cibles ont tous un compte dans ce tenant Azure AD (pas d'utilisateurs externes ou invités B2B) | à valider | Confirmer la population cible avec le PO métier ; si invités B2B → impact sur BR-2 (claim `groups` non garanti) |
| ASS-3 | Le claim `groups` du JWT Azure AD contient les GUIDs des groupes AD auxquels l'utilisateur appartient (option activée dans l'App Reg, manifest `"groupMembershipClaims": "SecurityGroup"`) | à valider | Vérifier dans le portail Azure → App Registration → Token configuration |
| ASS-4 | Le backend et le frontend tournent sur des origins distincts en dev (`:44328` backend, `:5185` frontend) et les deux ports sont libres sur les machines des développeurs | à valider | Vérifier l'absence de conflit de port en kickoff dev ; documenter dans le README |
| ASS-5 | ~~Hypothèse popup autorisée~~ **obsolète** : flow `loginRedirect` plein écran (BR-9), pas popup. Plus de dépendance à la policy popup du navigateur. | résolu | — |
| ASS-6 | Aucune règle de sécurité réseau (WAF, proxy d'entreprise) n'intercepte ou ne modifie les headers `Authorization: Bearer` entre le SPA et le backend | à valider | Tester en environnement réseau entreprise représentatif ; valider avec l'équipe infra/sécurité |
| ASS-7 | Le mode dégradé "auth seule" (SFD-6, AC-8) est acceptable pour les utilisateurs sans mapping groupes → permissions — ils voient l'app mais ne peuvent rien faire ; ce comportement est communiqué aux utilisateurs | confirmée | PO a validé ce comportement dans la SPEC (SFD-6 + AC-8 explicites) |
| ASS-8 | La version de `spring-security-oauth2-resource-server` fournie par Spring Boot 4.x (kotlin-spring-boot stack) est compatible avec les JWTs Azure AD v2 (`https://login.microsoftonline.com/{tenantId}/v2.0` comme issuer) sans configuration personnalisée du `JwtDecoder` | à valider | Vérifier la version de `spring-boot` dans `kotlin-spring-boot.libs.json` ; tester la validation JWT Azure AD dès le bootstrap arch avec un token réel ; si incompatible → ADR customJwtDecoder |
| ASS-9 | La base PostgreSQL cible est accessible depuis l'environnement d'exécution backend et les credentials (DSN, user, password) sont disponibles comme variables d'environnement standard — la FEAT 1 elle-même n'a pas d'entités DB propres mais le backend Spring Boot requiert un DataSource valide au démarrage | à valider | Confirmer avec l'équipe infra que le DSN postgres est provisionné en dev et en prod avant le sprint 1 ; sinon activer `spring.datasource.url=jdbc:postgresql://...` avec valeur de fallback ou lazy init |

---

## Cas Limites

| ID | Cas limite | Comportement attendu | Couvert par |
|---|---|---|---|
| EDGE-1 | L'utilisateur abandonne le flow Azure AD côté Microsoft (back nav, ferme l'onglet, blocage SSO) | Le SPA revient sur `/login` au prochain accès, sans erreur bloquante. Plus de "popup à fermer" — flow `loginRedirect` plein écran (BR-9). | AC-13 |
| EDGE-2 | Le backend `/auth/config` est indisponible au chargement du SPA (down, timeout réseau) | Le SPA affiche une page d'erreur "Backend indisponible" sans crash JS ; pas de `PublicClientApplication` instancié | AC-16 |
| EDGE-3 | Le JWT arrive à expiration pendant une session active (requête envoyée avec token expiré) | Le backend retourne `401 Unauthorized` ; MSAL intercepte et tente un `acquireTokenSilent` (refresh via iframe) ; si échec → redirection vers `/login` | AC-4 ; à valider que le comportement MSAL silent renewal est câblé |
| EDGE-4 | Un utilisateur authentifié accède directement à une URL protégée `/campagnes/123` sans passer par `/login` (lien direct, favori) | Le guard de route laisse passer si le token est valide ; si token absent ou expiré → redirect vers `/login` (sans mémoriser l'URL cible en v1, BR-10) | AC-1, FD-13 |
| EDGE-5 | Le claim `groups` est absent du JWT (option non activée dans l'App Reg ou groupe > 200 membres déclenchant le Graph overflow) | Le backend place l'utilisateur en mode dégradé (auth seule, pas d'autorisation par groupe) ; `403` sur les endpoints nécessitant un groupe | AC-8, BR-2 ; à ajouter : logguer un WARNING côté backend si claim absent |
| EDGE-6 | Deux onglets de navigateur ouverts simultanément, le token est révoqué sur Azure AD (ex. admin force sign-out) | Les deux onglets reçoivent `401` à la prochaine requête ; MSAL `acquireTokenSilent` échoue ; l'utilisateur est redirigé vers `/login` | AC-3, AC-4 ; comportement dépendant du TTL du JWT — à valider |
| EDGE-7 | La valeur de `AZ_FE_CALLBACKPATH` contient un préfixe MSYS Git Bash (`C:/Program Files/Git/login-callback`) au lieu de `/login-callback` | `AuthConfigController.kt` strip le préfixe par regex avant d'émettre la valeur ; la Redirect URI composée côté SPA reste correcte | AC-15, BR-13, FD-12 |
| EDGE-8 | L'utilisateur accède à `/login` alors qu'il est déjà authentifié (compte MSAL en cache + access token frais via `acquireTokenSilent` cf. BR-17) | Le guard de route ou `LoginPage` détecte les `accounts.length > 0` (useMsal hook) et redirige immédiatement vers `/campagnes` sans relancer `loginRedirect` | AC-6 (US 1-2) |
| EDGE-9 | Un JWT valide signé par un autre tenant Azure AD (ou un faux JWT signé avec `alg: none` ou un algorithme symétrique HS256) est envoyé au backend Spring | Le middleware `spring-security-oauth2-resource-server` rejette le token : `401 Unauthorized` avec message `invalid_token` ; aucun accès ne passe — comportement garanti par la validation `issuer` + `audience` + signature RSA via JWKS URI | AC-2, AC-3 ; à valider explicitement dans les tests QA avec un token forgé |
| EDGE-10 | Le SPA React est chargé depuis un navigateur sans accès réseau sortant vers `login.microsoftonline.com` (réseau d'entreprise très restrictif) — `fetch /auth/config` réussit (backend local) mais `loginRedirect` échoue (l'utilisateur arrive sur une page d'erreur Microsoft ou ne charge jamais Azure AD) | Au retour sur l'app (back navigator), `handleRedirectPromise()` lève une erreur MSAL — afficher un message "Votre réseau bloque Microsoft Login" et rester sur `/login` | à ajouter comme AC dans US Login |

---

## Parties Prenantes

| Acteur | Rôle vs feature | Niveau d'implication |
|---|---|---|
| Utilisateur Azure AD | Utilisateur final — se connecte, utilise l'app | I (informé du comportement login redirect plein écran, mode dégradé) |
| PO Humain | Valide les critères d'acceptation (AC-1 à AC-18), décide du scope v1 vs v2 (ex. mémorisation URL) | A (accountable validation fonctionnelle) |
| Tech Lead | Configure `stack.md`, valide les env vars, édite l'App Registration Azure AD, review code auth | R (responsible implémentation) + A (accountable config Azure) |
| Agent dev-backend | Implémente `SecurityConfig`, `CorsConfig`, `AuthConfigController`, validation JWT | R (responsible code backend) |
| Agent dev-frontend | Implémente `LoginPage`, guard de route, MSAL init, interception HTTP | R (responsible code frontend) |
| Administrateur Azure AD | Crée/modifie l'App Registration, active Group Claims, enregistre les Redirect URIs | C (consulté lors de la config initiale) |
| Équipe infra/sécurité | Valide que le proxy réseau n'intercepte pas les Bearer tokens ; valide l'accès sortant vers `login.microsoftonline.com` | C (consulté avant mise en prod) |
| Agent arch | Bootstrap les projets, installe MSAL + `microsoft-identity-web`, configure le `.sln` | R (responsible bootstrap) |

---

## Modes de Défaillance

| ID | Mode de défaillance | Indicateur de défaillance | Critère succès en miroir |
|---|---|---|---|
| FAIL-1 | L'authentification Azure AD est fonctionnellement cassée en prod (mismatch Redirect URI, env vars manquantes, cert HTTPS invalide) rendant l'application 100% inaccessible | Taux d'erreur login = 100% (aucun utilisateur ne passe) ; erreurs `AADSTS50011` ou `AADSTS900971` dans les logs navigateur | Taux de succès du flow login > 99% en prod sur une semaine de référence |
| FAIL-2 | Le claim `groups` n'est pas activé sur l'App Registration Azure AD — tous les utilisateurs se retrouvent en mode dégradé sans autorisation (AC-8) et ne peuvent rien faire dans l'app | 100% des utilisateurs authentifiés en mode dégradé ; aucune route métier accessible | 0% d'utilisateurs en mode dégradé involontaire (seuls ceux sans groupe AD affecté doivent l'être) |
| FAIL-3 | Les performances de validation JWT côté backend dégradent sous charge (appels Azure AD JWKS répétés à chaque requête sans cache) rendant l'API lente ou indisponible | Latence médiane `/api/*` > 500 ms ; timeouts observables sous 50 utilisateurs concurrents | Latence médiane < 100 ms sur les endpoints protégés ; JWKS mis en cache (durée configurable) |
| FAIL-4 | ~~Popup MSAL inutilisable sur enterprise~~ **mitigé** : flow `loginRedirect` plein écran (BR-9) — pas de dépendance à la policy popup. Le risque résiduel = blocage réseau sortant vers `login.microsoftonline.com` (EDGE-10). | > 5% des utilisateurs signalent un blocage réseau vers Azure AD | message explicite "Votre réseau bloque Microsoft Login" + IT incident |
| FAIL-5 | Les tokens MSAL stockés en `localStorage` sont exfiltrés via une vulnérabilité XSS sur la SPA React (dépendance tierce compromise, injection via rendu markdown) — l'attaquant usurpe l'identité d'un utilisateur authentifié pendant toute la durée de vie du JWT (jusqu'à 1h) | Incident sécurité signalé avec token valide utilisé depuis une IP anormale ; aucun mécanisme de révocation JWT côté application (Azure AD n'invalide pas les JWT en cours de validité sauf Continuous Access Evaluation) | Zéro incident de vol de token signalé ; configuration `sessionStorage` + CSP `script-src 'self'` vérifiées en audit sécurité avant mise en prod |
