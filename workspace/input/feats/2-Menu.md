# Spec: 2-1-Menu

Spec ID: 2-1-Menu

## Context

L'application possède plusieurs pages fonctionnelles (campagnes, etc.) mais aucun composant de navigation transverse. Il manque un menu principal global pour passer d'une section à l'autre et exposer les accès rapides (langue, profil, aide, notifications).

## Objective

Disposer d'un composant menu global persistant sur le layout principal, accessible uniquement aux utilisateurs authentifiés Azure AD, qui centralise la navigation et les actions transverses.

## Actors

- Utilisateur authentifié Azure AD: utilise le menu pour naviguer et accéder à son profil
- Frontend SPA: héberge le composant menu dans le layout principal
- Backend (à terme): exposera les notifications via une API dédiée (hors scope cette spec)

## Functional Needs

- SFD-1: Afficher le branding (icône + nom de l'application) en tête du menu
- SFD-2: Permettre la sélection de la langue d'interface entre Français (FR, défaut) et English (EN), avec persistance côté client
- SFD-3: Fournir un bouton de navigation principal "Home" redirigeant vers la page `campagnes`
- SFD-4: Afficher une icône de notifications (sans logique fonctionnelle dans cette spec — placeholder)
- SFD-5: Exposer un bouton "Besoin d'aide" qui ouvre/télécharge un document PDF d'aide depuis une URL configurable
- SFD-6: Afficher l'initiale de l'utilisateur connecté (récupérée depuis Azure AD : nom + prénom)
- SFD-7: Au clic sur l'icône utilisateur, afficher un pop-up avec nom complet, groupe Azure AD et bouton "Déconnexion"
- SFD-8: Le bouton "Déconnexion" appelle `msalInstance.logoutRedirect({ postLogoutRedirectUri })` (1 ligne, **frontend uniquement**). MSAL gère le clear du cache local et la redirection vers `/oauth2/v2.0/logout` d'Azure AD ; **aucun endpoint backend**, **aucune logique métier serveur**, **aucun nettoyage manuel du contexte applicatif**. Cf. `.claude/stacks/auth/azure-ad.md §5.2.6`.

## Business Rules

- BR-1: Le menu est affiché de manière persistante sur le layout principal (visible sur toutes les pages applicatives)
- BR-2: L'accès au menu est conditionné à un utilisateur authentifié (cf. spec `1-authentification`)
- BR-3: Tous les items de navigation passent par ce composant — aucune navigation directe ailleurs dans l'app
- BR-4: Les URLs de redirection des items sont centralisées dans une configuration unique (modifiables sans toucher la structure)
- BR-5: Le menu est responsive (desktop / mobile) et accessible (navigation clavier + attributs ARIA de base)
- BR-6: La langue choisie est persistée côté client (local/session storage), défaut FR au premier chargement
- BR-7: Les informations utilisateur (initiales, nom, prénom, groupe) proviennent exclusivement d'Azure AD (jamais saisies / stockées localement)
- BR-8: Aucun rôle / permission spécifique n'est requis dans cette version — tous les items sont visibles pour tout utilisateur connecté
- BR-9: **Anti-doublon visuel (composition load-bearing)** — chaque élément visuel du menu (drapeau du sélecteur de langue, icône notifications, icône utilisateur, bouton "Besoin d'aide", bouton "Home") est rendu **UNE SEULE FOIS** dans la barre de menu repliée. Pour le sélecteur de langue spécifiquement : si le composant DS (ex. shadcn `<Select>`) utilise un primitif type `<SelectValue />` qui re-rend le contenu de l'élément sélectionné (déjà composé de drapeau + libellé dans les options), alors **ne pas ajouter** de drapeau séparé dans le trigger ; symétriquement, si le drapeau est posé explicitement dans le trigger, alors les options du dropdown ne doivent contenir que le libellé textuel. Interdiction de cumuler drapeau-dans-trigger + drapeau-dans-options-rendu-par-SelectValue.

## Acceptance Criteria

- AC-1: Au chargement de l'application authentifiée, le menu est visible et persistant sur le layout principal
- AC-2: Le sélecteur de langue propose FR et EN ; la sélection est persistée et restaurée au rechargement
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
