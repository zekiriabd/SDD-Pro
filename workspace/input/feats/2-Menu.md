# Spec: 2-1-Menu

Spec ID: 2-1-Menu

## Context

L'application possède plusieurs pages fonctionnelles (campagnes, etc.) mais aucun composant de navigation transverse. Il manque un menu principal global pour passer d'une section à l'autre et exposer les accès rapides (langue, profil, aide, notifications).

## Objective

Disposer d'un composant menu global persistant sur le layout principal, accessible uniquement aux utilisateurs authentifiés Azure AD, qui centralise la navigation et les actions transverses.

## Quantified Goal

- **Metric** : présence visuelle du menu sur 100% des routes protégées ; navigation cross-route sans flicker
- **Target** : rendu menu < 100ms après mount du layout ; persistance d'état (collapsed/expanded) entre routes
- **Deadline** : `<à préciser>`

## Non-Functional Constraints

- **Volume** : ~`<à préciser>` items menu (ordre de grandeur ≤ 20)
- **Performance** : rendu sans appel réseau (purement client) ; pas de re-render au changement de route
- **Retention** : état UI menu en localStorage uniquement, pas de persistance serveur
- **Compliance** : n/a (UI uniquement)
- **Integration** : composant du Design System actif ; consommé par MainLayout (cf. FEAT 1 FD-8)
- **Degraded mode** : menu rendu même si endpoint notifications futur est indisponible (notifications hors scope cette spec)

## Actors

- Utilisateur authentifié Azure AD: utilise le menu pour naviguer et accéder à son profil
- Frontend SPA: héberge le composant menu dans le layout principal
- Backend (à terme): exposera les notifications via une API dédiée (hors scope cette spec)

## Functional Needs

- SFD-1: Afficher le branding (icône + nom de l'application) en tête du menu
- SFD-2: Permettre la sélection de la langue d'interface entre Français (FR, défaut) et English (EN), avec persistance côté client. **Libellés des options = codes ISO 639-1 stricts (`FR`, `EN`)** — aucun préfixe marque/produit. Le mockup HTML `2-Menu.html` affiche `MPF FR` dans le trigger (où `MPF` = brand), mais c'est une licence graphique du mockup : le sélecteur livré est générique (réutilisable hors brand CMS Print), donc le label dropdown reste `FR` / `EN`. Si une exigence brand est confirmée par PO, ajouter un préfixe via prop `BrandPrefix` du composant, pas en dur dans les options.
- SFD-3: Fournir un bouton de navigation principal "Home" redirigeant vers la page `campagnes`
- SFD-4: Afficher une icône de notifications (sans logique fonctionnelle dans cette spec — placeholder)
- SFD-5: Exposer un bouton "Besoin d'aide" qui ouvre/télécharge un document PDF d'aide depuis une URL configurable
- SFD-6: Afficher l'initiale de l'utilisateur connecté (récupérée depuis Azure AD : nom + prénom)
- SFD-7: Au clic sur l'icône utilisateur, afficher un pop-up avec nom complet, groupe Azure AD et bouton "Déconnexion"
- SFD-8: Le bouton "Déconnexion" appelle `msalInstance.logoutRedirect({ postLogoutRedirectUri })` (1 ligne, **frontend uniquement**). MSAL gère le clear du cache local et la redirection vers `/oauth2/v2.0/logout` d'Azure AD ; **aucun endpoint backend**, **aucune logique métier serveur**, **aucun nettoyage manuel du contexte applicatif**. Cf. `.claude/stacks/auth/azure-ad.md §5.2.6`.

## Business Rules

- BR-1: Le menu est affiché de manière persistante sur le layout principal (visible sur toutes les pages applicatives). **Orientation = TOP BAR HORIZONTAL** (LOAD-BEARING, clarifié 2026-05-22) — height ~64px, items en flex row, fond blanc, séparateur bottom. **Anti-pattern interdit** : sidebar verticale gauche (RadzenSidebar / RadzenPanelMenu / VerticalNav / shadcn Sheet drawer). Le mockup `2-Menu.html` (source de vérité visuelle) montre `<nav class="nav">` avec `display: flex; align-items: center; height: 64px` — tous les items (brand, lang, menu Home/Campagnes/Inventaire/Mediaplanning/Médiathèque, notifications, help, avatar) alignés horizontalement. Toute interprétation comme menu vertical (post-mortem dev-frontend 2026-05-22) est un bug bloquant.
- BR-2: L'accès au menu est conditionné à un utilisateur authentifié (cf. spec `1-authentification`)
- BR-3: Tous les items de navigation passent par ce composant — aucune navigation directe ailleurs dans l'app
- BR-4: Les URLs de redirection des items sont centralisées dans une configuration unique (modifiables sans toucher la structure)
- BR-5: Le menu est responsive (desktop / mobile) et accessible (navigation clavier + attributs ARIA de base)
- BR-6: La langue choisie est persistée côté client (local/session storage), défaut FR au premier chargement
- BR-7: Les informations utilisateur (initiales, nom, prénom, groupe) proviennent exclusivement d'Azure AD (jamais saisies / stockées localement)
- BR-8: Aucun rôle / permission spécifique n'est requis dans cette version — tous les items sont visibles pour tout utilisateur connecté
- BR-9: **Anti-doublon visuel (composition load-bearing)** — chaque élément visuel du menu (drapeau du sélecteur de langue, icône notifications, icône utilisateur, bouton "Besoin d'aide", bouton "Home") est rendu **UNE SEULE FOIS** dans la barre de menu repliée. Pour le sélecteur de langue spécifiquement : si le composant DS (ex. shadcn `<Select>`) utilise un primitif type `<SelectValue />` qui re-rend le contenu de l'élément sélectionné (déjà composé de drapeau + libellé dans les options), alors **ne pas ajouter** de drapeau séparé dans le trigger ; symétriquement, si le drapeau est posé explicitement dans le trigger, alors les options du dropdown ne doivent contenir que le libellé textuel. Interdiction de cumuler drapeau-dans-trigger + drapeau-dans-options-rendu-par-SelectValue.
- BR-10: **Templates trigger vs items distincts (post-mortem 2026-05-22)** — quand le DS expose 2 slots de template (Radzen : `<ValueTemplate>` pour le trigger + `<Template>` pour les items ; shadcn : `<SelectValue>` + `<SelectItem>` children ; vuetify : `v-slot:selection` + `v-slot:item`), le slot des items DOIT consommer la donnée de l'item courant (`ctx`/`item`/`option`), JAMAIS la donnée de la valeur sélectionnée du composant parent. Anti-pattern qui a cassé l'US 2-1 en runtime : le slot items consommait `_selectedCode` au lieu de `ctx.Code` → tous les items du dropdown affichaient la langue active (2× drapeau FR + 2× label "FR" au lieu de FR/EN distincts). La séparation trigger-vs-items doit être strictement contextuelle.

## Acceptance Criteria

- AC-1: Au chargement de l'application authentifiée, le menu est visible et persistant sur le layout principal
- AC-2: Le sélecteur de langue propose **exactement 2 options aux labels `FR` et `EN`** (ISO 639-1), chacune affichée avec son drapeau correspondant **distinct** (drapeau tricolore français pour FR, drapeau Union Jack pour EN — PAS deux fois le même drapeau). La sélection est persistée en localStorage clé `cms.lang` et restaurée au rechargement. Le trigger (langue active) affiche `{flag} {code}` ; chaque item du dropdown affiche `{flag} {code}` correspondant à SA propre langue (anti-pattern bug 2026-05-22 : `<Template>` qui re-rend la langue active pour tous les items au lieu d'utiliser le contexte de l'item).
- AC-3: Le clic sur le bouton "Home" redirige vers la page `campagnes`
- AC-4: L'icône de notifications est affichée (sans action fonctionnelle dans cette version)
- AC-5: Le clic sur "Besoin d'aide" ouvre/télécharge le PDF d'aide depuis l'URL configurée
- AC-6: L'icône utilisateur affiche l'initiale de l'utilisateur connecté (calculée depuis nom + prénom Azure AD)
- AC-7: Le clic sur l'icône utilisateur ouvre un pop-up affichant nom complet, groupe Azure AD et bouton "Déconnexion"
- AC-8: Le clic sur "Déconnexion" appelle `msalInstance.logoutRedirect()` côté frontend. MSAL redirige vers le endpoint Azure AD `/oauth2/v2.0/logout` qui invalide la session et renvoie l'utilisateur sur `postLogoutRedirectUri`. **Aucun appel backend, aucune logique métier.**
- AC-9: Un utilisateur non authentifié ne peut pas accéder au menu (redirigé vers le flow d'auth)
- AC-10: Le menu reste utilisable au clavier (focus visible, tab order cohérent) et expose les attributs ARIA de base
- AC-11: **Anti-doublon visuel (cf. BR-9)** — revue visuelle au runtime du menu replié : (a) 1 seul drapeau visible dans le trigger du sélecteur de langue, (b) 1 seule icône notifications, (c) 1 seule icône utilisateur, (d) 1 seul bouton "Besoin d'aide", (e) 1 seul bouton "Home". Tout cumul (ex. drapeau dans trigger + drapeau re-rendu par primitif `SelectValue` depuis l'item sélectionné) = bug bloquant.

## Dependencies

- 1-authentification (le menu requiert un utilisateur authentifié et lit les claims Azure AD)

## Functional Deliverables

- FD-1: Composant Menu global intégré dans le layout principal du frontend
- FD-2: Sous-composant Branding (icône + nom application)
- FD-3: Sélecteur de langue (FR / EN) avec persistance client (local/session storage)
- FD-4: Bouton de navigation "Home" → route `campagnes`
- FD-5: Icône de notifications (placeholder visuel uniquement)
- FD-6: Bouton "Besoin d'aide" pointant vers une URL PDF configurable
- FD-7: Sous-composant Profil utilisateur (initiale + pop-up nom/groupe/bouton déconnexion) alimenté par Azure AD. **Le bouton déconnexion est un onClick → `msalInstance.logoutRedirect()` (1 ligne, frontend uniquement, pas de fichier backend, pas de service applicatif dédié)**.
- FD-8: Configuration centralisée des routes des items de menu (un fichier de config / module unique)

## Out of Scope

- Implémentation complète d'un système d'i18n riche (clé/valeur sur tout le contenu de l'app) — seule la bascule FR/EN du menu est livrée
- Gestion fine des rôles et permissions par item de menu
- Backend des notifications (API, persistance, push) — uniquement l'icône placeholder
- Définition finale des routes applicatives — tous les items pointent temporairement vers `campagnes`, à raffiner dans une spec dédiée
- Design détaillé de l'UI du menu (cf. mockup [workspace/input/ui/2-1-Menu-Navigation.html](workspace/input/ui/2-1-Menu-Navigation.html) pour la référence visuelle)
- **Endpoint backend de déconnexion** : entièrement délégué à Azure AD (cf. `.claude/stacks/auth/azure-ad.md §5.2.6`). Le bouton "Déconnexion" du menu se réduit à un `onClick={() => msalInstance.logoutRedirect()}` ; aucun fichier backend (controller, service, endpoint) ne doit être généré pour cette logique.

---

## Risques Identifiés

| ID | Risque | Sévérité | Mitigation |
|---|---|---|---|
| RISK-1 | L'orientation top bar horizontale (BR-1) est interprétée à nouveau comme sidebar par dev-frontend — post-mortem déjà documenté 2026-05-22, risque de récidive si BR-1 n'est pas relu en STEP 0 preflight | high | Ajouter une vérification explicite dans le plan front : grep `RadzenSidebar\|RadzenPanelMenu\|VerticalNav` post-build + asserter `display:flex` sur `<nav>` |
| RISK-2 | Le bug doublon visuel BR-9/BR-10 (drapeau×2 ou items du dropdown consommant la valeur sélectionnée plutôt que leur propre contexte) récidive sur une autre version du composant DS ou lors d'un upgrade shadcn | high | AC-11 (anti-doublon visuel) doit être couverte par un test de rendu (vitest/bunit) ; le plan front doit documenter explicitement le slot `<SelectItem>` vs `<SelectValue>` |
| RISK-3 | `msalInstance` n'est pas disponible au scope du composant Menu si l'initialisation MSAL (FEAT 1) n'est pas achevée ou si le provider n'est pas correctement chaîné dans le layout | high | Vérifier la dépendance FEAT 1-Auth en preflight ; le composant doit utiliser le hook `useMsal()` plutôt qu'une instance globale importée directement |
| RISK-4 | La persistance localStorage (`cms.lang`) écrase silencieusement les préférences lors d'un changement de clé entre versions (ex. migration future de `cms.lang` vers `cms.preferences.lang`) | medium | Documenter la clé dans FD-8 (configuration centralisée) ; ajouter une migration de lecture avec fallback dans le service de langue |
| RISK-5 | L'URL PDF "Besoin d'aide" (SFD-5) n'est pas encore définie — si elle pointe vers un asset non déployé, le bouton échoue silencieusement sans feedback utilisateur | medium | Valider l'URL avec le PO avant livraison ; ajouter un état d'erreur visible (toast ou message) si le PDF ne se charge pas |

---

## Hypothèses

| ID | Hypothèse | Statut | Validation requise |
|---|---|---|---|
| ASS-1 | FEAT 1 (authentification Azure AD) est livrée et opérationnelle avant que FEAT 2 ne soit intégrée dans le layout principal | à valider | Confirmer l'ordre de déploiement et la disponibilité de `msalInstance` / `useMsal()` dans le contexte React |
| ASS-2 | Le Design System shadcn est déjà scaffoldé par arch (composants `Select`, `DropdownMenu`, `Popover` disponibles dans le projet React) | à valider | Vérifier l'output de `/arch-init` — les composants doivent figurer dans `onDemand` triggés ou `core` |
| ASS-3 | Les claims Azure AD (`given_name`, `family_name`, `groups`) sont accessibles via `useMsal()` sans appel réseau supplémentaire (claims présents dans le token ID) | à valider | Confirmer la configuration Azure AD (manifest + scopes) avec l'équipe infra/IAM |
| ASS-4 | Le nombre d'items menu est stable et ne dépassera pas ~20 pour cette version (Non-Functional Constraints) | à valider | Confirmer avec le PO la liste définitive des items avant la génération des US |
| ASS-5 | La langue par défaut FR est acceptée pour tous les utilisateurs sans mécanisme de détection du navigateur (`navigator.language`) | confirmée | Spécifié explicitement dans BR-6 ("défaut FR au premier chargement") |
| ASS-6 | Aucun rôle Azure AD spécifique ne conditionne la visibilité des items — BR-8 confirme que tous les items sont visibles pour tout utilisateur connecté | confirmée | BR-8 explicite dans la FEAT |
| ASS-7 | L'URL PDF d'aide (SFD-5) sera fournie via une variable de configuration (env var ou fichier de config) accessible au build time du frontend | à valider | Définir le mécanisme de config avec le Tech Lead avant la génération du plan front |

---

## Cas Limites

| ID | Cas limite | Comportement attendu | Couvert par |
|---|---|---|---|
| EDGE-1 | Claims Azure AD incomplets ou absents (`given_name`/`family_name` null) — utilisateur authentifié mais profil incomplet | Afficher un fallback neutre (ex. icône avatar générique, initiale `?`) sans crash ; log une warning côté client | à ajouter (AC-6 ne couvre que le cas nominal) |
| EDGE-2 | Token MSAL expiré exactement au moment du clic sur "Déconnexion" — `logoutRedirect()` appelé avec session déjà expirée | MSAL gère silencieusement la redirection vers `postLogoutRedirectUri` ; aucun écran d'erreur | AC-8 (à compléter : préciser le comportement sur session expirée) |
| EDGE-3 | `localStorage` indisponible ou quota dépassé (mode navigation privée, Safari ITP, quota plein) | La langue bascule dans la session mais ne persiste pas ; pas de crash ; message informatif optionnel | à ajouter |
| EDGE-4 | Deux onglets du même navigateur changent la langue simultanément (StorageEvent cross-tab) | Le deuxième onglet reflète le changement via `window.addEventListener('storage', ...)` OU ignore le changement selon l'implémentation | à ajouter (BR-6 ne précise pas le comportement cross-tab) |
| EDGE-5 | L'URL PDF "Besoin d'aide" retourne une erreur HTTP (404, 503) ou timeout réseau | Afficher un message d'erreur utilisateur (toast ou alerte inline) ; ne pas laisser l'onglet vide | à ajouter (SFD-5 ne couvre que le cas nominal) |
| EDGE-6 | Menu rendu sur mobile (≤ 375px) avec 5+ items en flex row — débordement horizontal | Items masqués dans un menu hamburger ou scroll horizontal avec indicateur ; jamais de coupure texte illisible | AC-10 / BR-5 (à compléter avec les breakpoints concrets) |
| EDGE-7 | Navigation clavier : focus piégé dans le pop-up profil (SFD-7) sans moyen d'en sortir via Échap ou Tab | Pop-up expose `role="dialog"` + `aria-modal="true"` + fermeture sur Échap ; focus retourne à l'icône avatar | AC-10 (à affiner avec les attributs ARIA précis) |
| EDGE-8 | Groupe Azure AD contenant des caractères spéciaux ou très long (> 80 chars) affiché dans le pop-up profil | Tronquer avec ellipsis CSS + tooltip au survol ; ne jamais déborder le layout du pop-up | à ajouter |

---

## Parties Prenantes

| Acteur | Rôle vs feature | Niveau d'implication |
|---|---|---|
| Utilisateur authentifié Azure AD | Utilise le menu pour naviguer, changer de langue, accéder au profil et se déconnecter | RACI : I (consommateur final) |
| PO / Product Owner | Valide les items de menu, les libellés, l'URL PDF aide et les critères d'acceptation | RACI : A (accountable) |
| Dev Frontend | Implémente le composant Menu, le sélecteur de langue, l'intégration MSAL | RACI : R (responsible) |
| Tech Lead | Valide le plan technique, les choix de composition shadcn, la config centralisée FD-8 | RACI : A (co-accountable architecture) |
| Equipe IAM / Azure AD | Doit confirmer la disponibilité des claims (`given_name`, `family_name`, `groups`) dans le token ID | RACI : C (consulted) |
| UX Designer | A fourni le mockup `2-1-Menu-Navigation.html` — référence visuelle source de vérité | RACI : C (consulted pour clarifications visuelles) |
| Backend (futur) | Exposera l'API notifications (hors scope FEAT 2) — à informer du placeholder SFD-4 pour éviter un design conflictuel | RACI : I (informé) |

---

## Modes de Défaillance

| ID | Mode de défaillance | Indicateur de défaillance | Critère succès en miroir |
|---|---|---|---|
| FAIL-1 | Le menu est rendu en sidebar verticale au lieu de top bar horizontale (anti-pattern BR-1 récidivant) | Build livré avec `RadzenSidebar` ou `display:block` sur `<nav>` au lieu de `display:flex` + height 64px | Build rejeté par gate post-build (grep + assertion CSS) ; 0 livraison avec sidebar |
| FAIL-2 | Le sélecteur de langue affiche deux fois le même drapeau dans le dropdown (bug AC-2 / BR-9 / BR-10 récidivant) | Runtime : dropdown langue affiche FR×2 ou EN×2 au lieu de FR et EN distincts | AC-2 couverte par test de rendu vérifiant 2 items distincts avec drapeaux différents |
| FAIL-3 | Le menu ne s'affiche pas pour les utilisateurs authentifiés (régression FEAT 1 ou provider MSAL manquant dans le layout) | Taux de rendu menu sur routes protégées < 100% (Metric §Quantified Goal) | Menu visible sur 100% des routes protégées après authentification réussie |
| FAIL-4 | La persistance de langue échoue silencieusement et revient toujours à FR même après changement explicite | Après rechargement de page, la langue sélectionnée n'est pas restaurée ; `cms.lang` absent du localStorage | Clé `cms.lang` présente en localStorage après sélection ; valeur restaurée au rechargement (AC-2) |
