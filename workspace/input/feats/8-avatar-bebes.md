# Spec: 8-avatar-bebes

Status: Draft
Spec ID: 8-avatar-bebes

## Context
La FEAT 4 (`spec-bebes`) a livré la page `/bebes` listant les bébés rattachés à l'assistante maternelle connectée, avec un composant `BabyCard` par enfant. Aujourd'hui, le rendu visuel ne correspond pas à la nouvelle maquette `workspace/input/ui/8-avatar-bebes.html` : (a) l'avatar du bébé tombe en fallback initiales-texte au lieu d'utiliser un PNG par défaut quand `Contrat.ImageUrl` est vide, (b) la card embarque encore une icône "✏️ Rapport" qui n'a plus lieu d'être, (c) la composition d'icônes par card est désynchronisée de la maquette (la maquette demande **deux icônes** : appel parents + chevron de redirection). Le bouton de recherche en topbar n'a jamais été implémenté et n'a pas besoin de l'être. **Cette FEAT ne touche que le rendu visuel — toute la logique de statut (présent/absent/excusé, rapport envoyé/à compléter, heure d'arrivée, "pas de garde aujourd'hui") reste hors scope et sera traitée par une FEAT ultérieure.** Surface critique : la liste des bébés expose des données nominatives d'enfants — la confidentialité multi-tenant doit être enforced **côté serveur depuis le JWT exclusivement**, jamais reposer sur un paramètre client manipulable.

## Objective
La page `/bebes` rend pour chaque bébé une `BabyCard` strictement alignée sur la maquette `8-avatar-bebes.html` : avatar circulaire (image `Contrat.ImageUrl` si présente, sinon PNG statique constant `/assets/default-baby-avatar.png`), nom + prénom, date de naissance, et exactement **deux icônes interactives** (appel parents + chevron de navigation vers la page de détail). Le filtrage des bébés par employée connectée reste enforced **exclusivement côté serveur** à partir du claim `sub` du JWT validé, sans aucune dépendance à un identifiant transitant par URL, localStorage, sessionStorage, cookie non-httpOnly, body ou query.

## Actors
- Employé connecté : assistante maternelle authentifiée (cf. spec-connexion FEAT 1). Aucun nouvel acteur introduit.
- Attaquant authentifié (modèle de menace) : utilisateur connecté légitime tentant d'accéder via manipulation client (DevTools, URL, localStorage) aux bébés rattachés à une AUTRE assistante maternelle. La FEAT doit rendre ce scénario impossible sans changement côté backend (le backend FEAT 4 enforce déjà la règle).

## User Stories
- À l'ouverture de `/bebes`, l'utilisatrice voit la liste de SES bébés (filtre serveur depuis JWT) — la liste est vide si elle n'a aucun contrat actif
- Chaque card affiche un avatar rond contenant l'image uploadée à la souscription du contrat (`Contrat.ImageUrl` exposé sous la clé `imageUrl` par l'API)
- Si l'`ImageUrl` est vide / null OU si l'image utilisateur échoue à charger (404, CORS, réseau), la card affiche à la place le PNG statique servi sur `/assets/default-baby-avatar.png` (silhouette neutre de bébé) — JAMAIS d'initiale texte, JAMAIS de container vide
- Chaque card rend exactement deux icônes interactives : (1) un bouton "Appeler les parents" (icône téléphone) et (2) un chevron de navigation (visuel) signalant la redirection vers la page de détail du bébé
- L'icône "Rapport" (crayon ✏️) précédemment présente sur la card est **supprimée du markup**
- Le topbar de la page contient uniquement le bouton menu (hamburger) et le titre "Demo" — aucun bouton de recherche, aucune cloche de notifications
- Toute tentative d'accéder à des bébés d'une autre assistante maternelle via manipulation client (changer un id dans l'URL, éditer localStorage, forger une query) est bloquée côté serveur sans fuite d'information

## Business Rules
- BR-1: la source de filtrage de la liste `/api/babies` est **exclusivement** la valeur du claim `sub` du JWT validé par le middleware d'authentification serveur — aucun paramètre query, body, header (hors `Authorization: Bearer <jwt>`), cookie, ou hint client n'est consulté pour déterminer "quels bébés appartiennent à quelle employée"
- BR-2: l'identifiant de l'employée connectée NE DOIT JAMAIS apparaître dans une URL (path, query, fragment), ni dans une variable côté client manipulable (localStorage, sessionStorage, cookie non-httpOnly, variable globale JS, attribut DOM) — le client n'a pas besoin de cette information pour fonctionner, elle reste interne au JWT côté backend
- BR-3: toute requête `/api/babies` (ou tout endpoint dérivé futur) sans Bearer token valide retourne 401 sans révéler si une ressource existe ; toute tentative d'accès à un bébé non rattaché au JWT (ex. via path `/api/babies/{id}` futur) retourne 404 (pas 403, pour ne pas confirmer l'existence) — aucun cross-tenant leak observable
- BR-4: l'avatar du bébé est rendu dans un container circulaire (`border-radius: 50%` ou `999px`) avec `object-fit: cover` ; aucune déformation, aucun ratio non préservé toléré
- BR-5: si `Contrat.ImageUrl` est vide, null, ou si la requête de l'image échoue (404, CORS, erreur réseau), l'`<img>` du composant bascule sur le chemin URL constant `/assets/default-baby-avatar.png` — JAMAIS d'initiale texte, JAMAIS d'avatar généré dynamiquement (gravatar, couleur déterministe, etc.)
- BR-6: le fichier `public/assets/default-baby-avatar.png` (URL publique `/assets/default-baby-avatar.png`) est traité comme un asset versionné du projet ; sa source canonique est `workspace/input/assets/avatar-bebe.png` et il est copié vers `public/assets/default-baby-avatar.png` au scaffolding/déploiement ; le chemin URL est exposé via une constante unique (ex. `DEFAULT_BABY_AVATAR_URL`) déclarée en haut du module `BabyCard`
- BR-7: chaque `BabyCard` rend **exactement deux** icônes interactives : (a) un `<button>` "Appeler les parents" (icône téléphone, `aria-label` explicite) et (b) un chevron visuel de navigation indiquant la redirection vers la page de détail du bébé — toute autre icône (rapport, statut, badge présence, indicateur de garde) est **interdite** par cette FEAT
- BR-8: le topbar de la page `/bebes` contient uniquement deux éléments visuels : le bouton menu (hamburger) à gauche et le titre "Demo" — aucun bouton de recherche, aucune cloche de notifications, aucun bouton de filtre ne doit être présent dans le markup
- BR-9: aucune logique de statut (présent/absent/excusé, rapport envoyé/à compléter/à venir, heure d'arrivée, "pas de garde aujourd'hui", filtres chips) n'est implémentée dans cette FEAT — ni dans le markup, ni dans le state React, ni dans l'API (les hooks de récupération existants côté backend ne sont pas étendus) ; tous ces éléments sont déférés à une FEAT ultérieure
- BR-10: aucun élément de la maquette n'introduit un appel HTTP supplémentaire au montage de la page (la liste se fait toujours via un seul `GET /api/babies` qui retourne `{ babies: [...], count }`) ; le chargement de l'image utilisateur ou du PNG par défaut passe uniquement par la balise `<img>` du navigateur

## Acceptance Criteria
- AC-1: `GET /api/babies` requiert un Bearer JWT valide ; sans header `Authorization` ou avec un JWT invalide / expiré, l'endpoint retourne 401 sans payload révélant l'existence d'une ressource
- AC-2: la liste retournée par `GET /api/babies` ne contient **que** les bébés liés à l'employée identifiée par `JWT.sub` ; aucun bébé d'une autre employée ne fuit dans la réponse, vérifiable par test d'intégration avec 2 employées et 2 jeux de bébés disjoints
- AC-3: aucun paramètre query, body, header (hors `Authorization`), ou cookie ne peut modifier le filtre côté serveur — la requête `GET /api/babies?employeeId=999` retourne la même liste que `GET /api/babies` pour le JWT donné
- AC-4: aucun identifiant d'employée n'est présent dans le code frontend matérialisé sous une forme manipulable : pas de `localStorage.setItem('employeeId', ...)`, pas de `sessionStorage.setItem('employeeId', ...)`, pas de paramètre `?employeeId=` construit côté client, pas d'attribut `data-employee-id` dans le DOM
- AC-5: chaque `BabyCard` affiche un avatar dans un container circulaire (`border-radius: 50%` ou `999px`) avec `object-fit: cover`
- AC-6: si le champ `imageUrl` (exposé par `/api/babies` depuis `Contrat.ImageUrl`) est non-vide ET que l'image charge correctement, l'avatar affiche cette image ; sinon, l'avatar pointe sur `/assets/default-baby-avatar.png`
- AC-7: le fichier `workspace/output/src/Demo/public/assets/default-baby-avatar.png` existe dans le projet (copié depuis `workspace/input/assets/avatar-bebe.png`) et est servi avec un Content-Type `image/png` sur le chemin URL `/assets/default-baby-avatar.png` (réponse 200, pas 404)
- AC-8: le chemin URL `/assets/default-baby-avatar.png` est défini comme une constante unique (`DEFAULT_BABY_AVATAR_URL`) en haut du module `BabyCard` ; c'est la seule occurrence textuelle de ce chemin dans le code du composant
- AC-9: chaque `BabyCard` rend **exactement deux** éléments interactifs : un `<button aria-label="Appeler les parents">` (icône téléphone) et un chevron visuel (`<svg>` dans un container `.baby-card__chev`) ; aucun bouton "Rapport" / "✏️" n'est présent dans le markup généré
- AC-10: le topbar de `/bebes` contient exactement deux éléments visuels : le `<button class="topbar__menu">` (hamburger) et `<div class="topbar__title">` (Demo) ; aucun `<button class="topbar__search">` ni `<button class="topbar__bell">` n'est présent
- AC-11: aucun chip de statut (`.baby-card__chip`, `chip--present`, `chip--absent`), aucun indicateur de rapport (`.baby-card__report`), aucune heure d'arrivée, aucun texte "Pas de garde aujourd'hui" / "Rapport envoyé" / "Rapport à compléter" n'est rendu dans la card pour cette FEAT
- AC-12: la composition rendue d'une `BabyCard` est strictement : avatar (cercle) + nom complet + date de naissance (formattée FR) + bouton appel parents + chevron — rien d'autre
- AC-13: au montage de `BabiesPage`, exactement un appel HTTP est émis (`GET /api/babies`) ; le chargement de l'avatar (vrai ou défaut) passe uniquement par la balise `<img>` du navigateur, pas par un fetch JS
- AC-14: les ACs de FEAT 4 hors statut/rapport (AC-1 auth required, AC-2 filter EmployeeId, AC-3 loader, AC-7 empty list, AC-9 bouton "Ajouter un enfant", AC-10 no cross-employee leak) restent opérationnels sans régression

## Dependencies
- spec-connexion (FEAT 1) : fournit le JWT signé HS256 contenant `sub` = `Employee.id` ; sans login préalable, `/bebes` redirige sur `/login` (cf. AC-1 / AC-3 de cette FEAT et de FEAT 4)
- spec-bebes (FEAT 4) : base du composant `BabyCard`, de la page `BabiesPage`, de l'endpoint `GET /api/babies`, du service `listMyBabies(sessionUserId)` et du repository `babyRepository` ; cette FEAT modifie le rendu sans toucher la logique de récupération ni la sécurité backend déjà enforced
- spec-souscrire-contrat (FEAT 6) : alimente le champ `Contrat.ImageUrl` lors de la souscription d'un nouveau contrat / ajout d'un bébé (upload par l'assistante maternelle) — cette FEAT consomme la donnée déjà persistée

## Functional Deliverables
- mise à jour du composant `public/components/BabyCard.jsx` : suppression du bouton "Rapport" (✏️), ajout d'un bouton "Appeler les parents" (icône téléphone, `aria-label` explicite), ajout d'un chevron visuel de navigation, bascule du fallback avatar des initiales-texte vers `<img src={DEFAULT_BABY_AVATAR_URL}>`
- nouvel asset statique `workspace/output/src/Demo/public/assets/default-baby-avatar.png` (silhouette neutre de bébé, PNG ratio carré) servi sur le chemin URL `/assets/default-baby-avatar.png` ; source canonique = `workspace/input/assets/avatar-bebe.png`
- constante `DEFAULT_BABY_AVATAR_URL = "/assets/default-baby-avatar.png"` déclarée dans le module `BabyCard`
- mise à jour des styles CSS (`public/styles.css`) si nécessaire pour le rendu circulaire de l'avatar et la composition à deux icônes du `.baby-card__bottom` (ou suppression du `.baby-card__bottom` si non requis par la nouvelle composition)
- vérification (test ou revue manuelle) que `BabiesPage.jsx` topbar n'introduit ni bouton de recherche ni cloche de notifications
- vérification (audit sécurité) que `routes/baby.routes.js` continue à dériver `sub` exclusivement de `request.user` (claim JWT) et que `services/babyService.js` n'expose aucun overload accepting un employeeId externe (la signature `listMyBabies(sessionUserId)` reste l'unique point d'entrée)

## Out of Scope
- gestion du statut présent/absent/excusé et des chips correspondants (`.baby-card__chip`, `chip--present`, `chip--absent`)
- gestion du statut de rapport (envoyé / à compléter / pas de garde aujourd'hui) et de l'icône associée
- affichage de l'heure d'arrivée et de l'âge en mois sur la card
- filtres chips au-dessus de la liste (Aujourd'hui / Cette semaine / Tous, etc.)
- recherche textuelle dans la liste des bébés
- compteur "X enfants en garde" enrichi (le compteur basique `count` de FEAT 4 reste affiché tel quel)
- édition / upload / suppression de l'image de profil d'un bébé depuis la card (l'upload se fait à la souscription du contrat — couvert par FEAT 6)
- migration du schéma de la table `Contrat` (champ `ImageUrl` déjà existant)
- endpoint backend de récupération individuelle d'un bébé (`GET /api/babies/{id}`) — l'AC-3 de cette FEAT documente le comportement attendu (404 sur cross-tenant) si un tel endpoint était ajouté par une FEAT ultérieure
- avatar de fallback généré dynamiquement (initiales, couleur déterministe à partir du nom, gravatar par hash) — explicitement rejeté au profit du PNG statique constant
- personnalisation par bébé du fichier `default-baby-avatar.png` (le même asset est servi pour tous les bébés sans `ImageUrl`)
- changement du destinataire / numéro de téléphone de l'action "Appeler les parents" (cette FEAT pose le bouton et l'`aria-label` ; le câblage du `tel:` ou de l'action réelle peut être déféré à une FEAT ultérieure si non trivial — minimum acceptable : un placeholder `tel:` no-op ou un handler `onClick` vide documenté)
- thème dark/light, accessibilité avancée (focus management des chips, annonces ARIA dynamiques)
