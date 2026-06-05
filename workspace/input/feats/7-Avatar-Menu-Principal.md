# Spec: 7-avatar-menu-principal

Status: Draft
Spec ID: 7-avatar-menu-principal

## Context
La FEAT 5 (`spec-menu-principale`) a livré un menu latéral (drawer) dont le header affiche un bloc utilisateur. Aujourd'hui, ce bloc rend un avatar par défaut (disque générique) ET un libellé "Assistante maternelle" sous le nom — alors que la photo de profil réelle de l'employée connectée est déjà disponible dans la session applicative (champ `ImageUrl` de la table `Employee`, alimenté au login par spec-connexion). La nouvelle maquette `workspace/input/ui/7-avatar-menu-principal.html` retire le libellé de rôle et impose un rendu circulaire de la vraie photo. Cette FEAT corrige uniquement le header du drawer : aucun autre élément du menu n'est modifié.

## Objective
Le header du drawer du menu principal affiche la photo de profil réelle de l'employée connectée (champ `Employee.ImageUrl` récupéré en session au moment du login), rendue dans un cercle, et le libellé "Assistante maternelle" est retiré — il ne reste que la photo, le nom + prénom et le numéro de téléphone.

## Actors
- Employé connecté : assistante maternelle authentifiée (cf. spec-connexion). Identique à l'acteur de FEAT 5, aucun nouvel acteur introduit.

## User Stories
- À l'ouverture du drawer, l'utilisateur voit sa propre photo de profil (l'image uploadée lors de son inscription) à la place du disque par défaut
- La photo est rendue dans un cercle (avatar rond) avec `object-fit: cover` pour préserver le ratio
- Le libellé "Assistante maternelle" (ou tout badge/rôle équivalent) n'apparaît plus dans le header du drawer
- Le header du drawer ne contient plus que trois éléments : la photo de profil (en cercle), le nom + prénom, le numéro de téléphone
- L'URL de l'image provient exclusivement de la session/contexte applicatif côté client (alimenté au login depuis `Employee.ImageUrl`) — aucun appel API supplémentaire n'est déclenché à l'ouverture du drawer
- Si `ImageUrl` est vide, null, ou si l'image n'est pas accessible (404, erreur réseau, CORS), une image PNG par défaut, identique pour toutes les utilisatrices (silhouette neutre), est affichée à la place — servie depuis un chemin statique constant `public/assets/default-avatar.png` (URL `/assets/default-avatar.png`)

## Business Rules
- BR-1: la source de l'image affichée est exclusivement `Employee.ImageUrl` de l'employée connectée, récupérée au login et stockée dans la session/contexte applicatif client (singleton, store ou équivalent) — aucun nouvel appel HTTP n'est émis pour rafraîchir l'image à l'ouverture du drawer
- BR-2: l'image est rendue dans un container circulaire (border-radius 50% ou 999px) avec `object-fit: cover` ; aucune déformation, aucun ratio non préservé toléré
- BR-3: le header du drawer NE DOIT PAS afficher le libellé "Assistante maternelle" ni aucun badge/pill rôle équivalent — la composition autorisée est strictement : photo + nom + prénom + téléphone
- BR-4: si `ImageUrl` est vide, null, ou si la requête de l'image échoue (404, CORS, erreur réseau), l'app affiche l'image PNG statique servie sur `/assets/default-avatar.png` — JAMAIS d'initiales texte, JAMAIS de container vide, JAMAIS d'avatar généré dynamiquement (gravatar, couleur déterministe, etc.)
- BR-5: le fichier `public/assets/default-avatar.png` (URL publique `/assets/default-avatar.png`) est traité comme un asset versionné du projet ; sa source canonique est `workspace/input/assets/avatar.png` et il est copié vers `public/assets/default-avatar.png` au scaffolding/déploiement ; le chemin URL est une constante référencée par le code (pas hardcodée à plusieurs endroits)
- BR-6: aucun autre élément du menu (items de navigation, bouton déconnexion, comportement SPA, fermeture du panneau) n'est modifié par cette FEAT — toutes les ACs de FEAT 5 hors header restent valides en l'état

## Acceptance Criteria
- AC-1: le header du drawer affiche la photo de profil de l'employée connectée en lisant `ImageUrl` depuis la session/contexte applicatif client
- AC-2: la photo de profil est rendue dans un cercle (border-radius 50% ou 999px) avec `object-fit: cover`
- AC-3: si `ImageUrl` est vide, null ou si l'image n'est pas accessible, l'`<img>` du header pointe sur `/assets/default-avatar.png` (le navigateur récupère ce PNG statique servi par l'app)
- AC-4: le libellé "Assistante maternelle" (et tout badge/pill rôle équivalent) n'apparaît plus dans le header du drawer
- AC-5: le header du drawer contient exactement trois éléments rendus : la photo (cercle, vraie OU défaut), le nom + prénom, le numéro de téléphone
- AC-6: aucun appel HTTP additionnel n'est émis à l'ouverture du drawer pour récupérer l'image (vérifiable via DevTools Network — seule la requête `<img src="…">` vers l'URL stockée en session OU vers `/assets/default-avatar.png` est attendue)
- AC-7: l'ensemble des ACs de FEAT 5 hors header (navigation SPA, déconnexion, fermeture overlay, accès non connecté) reste opérationnel sans régression
- AC-8: le fichier `workspace/output/src/Demo/public/assets/default-avatar.png` existe dans le projet (copié depuis `workspace/input/assets/avatar.png`) et est servi avec un Content-Type `image/png` sur le chemin URL `/assets/default-avatar.png` (réponse 200, pas 404)
- AC-9: le chemin URL `/assets/default-avatar.png` est défini comme une constante unique (ex. `DEFAULT_AVATAR_URL`) en haut du module `MainLayout` et est la seule occurrence textuelle de ce chemin dans le code du composant

## Dependencies
- spec-connexion (FEAT 1) : fournit la session/contexte applicatif client alimenté au login avec `Employee.ImageUrl`
- spec-menu-principale (FEAT 5) : base du menu latéral dont seul le header du drawer est modifié par cette FEAT

## Functional Deliverables
- mise à jour du markup du header du drawer : binding de la source d'image sur `ImageUrl` de l'employée connectée (lecture depuis la session/contexte applicatif client)
- suppression du nœud DOM rendant le libellé "Assistante maternelle" dans le header du drawer
- nouvel asset statique `workspace/output/src/Demo/public/assets/default-avatar.png` (silhouette neutre, PNG ratio carré) servi sur le chemin URL `/assets/default-avatar.png` ; source canonique = `workspace/input/assets/avatar.png`
- constante `DEFAULT_AVATAR_URL = "/assets/default-avatar.png"` déclarée dans le module `MainLayout` et utilisée comme `src` de l'`<img>` lorsque `ImageUrl` est vide ou que l'image utilisateur échoue à charger
- mise à jour des styles du container avatar pour garantir le rendu circulaire conforme à la maquette `7-avatar-menu-principal.html` (border-radius, object-fit, dimensions)

## Out of Scope
- modification du flux de login ou du mécanisme de stockage en session de `ImageUrl` (couvert par spec-connexion)
- édition / upload / suppression de la photo de profil depuis le menu (consultation seule)
- modification du reste du menu : items de navigation, footer, bouton déconnexion, comportement SPA, fermeture du panneau (couvert et inchangé par FEAT 5)
- endpoint backend de récupération ou de mise à jour de `Employee.ImageUrl`
- migration du schéma de la table `Employee` (schéma supposé inchangé, champ `ImageUrl` déjà existant)
- gestion de cache navigateur ou de CDN pour les images de profil
- avatar de fallback généré dynamiquement (initiales, couleur déterministe à partir du nom, gravatar par hash d'email, etc.) — explicitement rejeté au profit du PNG statique constant
- personnalisation par utilisatrice du fichier `default-avatar.png` (le même asset est servi pour toutes les utilisatrices sans `ImageUrl`)
- thème dark/light, accessibilité avancée (alt text dynamique reste hors scope spécifique à cette FEAT)
