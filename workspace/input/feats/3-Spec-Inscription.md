# Spec: inscription

Status: Draft
Spec ID: spec-inscription

## Context
Demo doit permettre à de nouveaux employés (assistantes maternelles) de créer leur compte de façon autonome avant de pouvoir se connecter. Sans ce flux, seuls des comptes pré-injectés en base seraient utilisables. L'inscription est constituée de **deux écrans successifs** :

1. **Page 1 — Création de compte** (obligatoire) : email + mot de passe + numéro de téléphone. Génère un `Employee` en base via INSERT et récupère l'`ID` auto-incrémenté.
2. **Page 2 — Complétion du profil** (optionnelle à l'inscription) : nom, prénom, état civil, adresse, agrément, assurance, image. Renseigne le reste des colonnes via UPDATE sur l'`ID` récupéré.

La Page 2 est aussi accessible plus tard depuis le menu **"Mes données"** (employé connecté), pour permettre à l'assistante maternelle de compléter ou modifier ses informations après inscription. La complétion du profil deviendra **prérequise** pour la création d'un contrat (spec future), mais ne bloque pas la création de compte.

Le bascule final vers `/login` (couvert par spec-connexion) intervient après "Enregistrer" Page 2 OU après clic sur "Continuer plus tard".

## Objective
Un visiteur anonyme crée son compte employé via email + mot de passe + téléphone sur la **Page 1** de `/register`, puis voit s'afficher la **Page 2** où il peut soit compléter son profil détaillé soit le différer via "Continuer plus tard". Dans les deux cas, il est ensuite redirigé vers `/login`. L'employé connecté peut revenir compléter/modifier ses informations via le menu **"Mes données"**.

## Actors
- Visiteur anonyme : utilisateur non connecté qui souhaite créer un compte employé (Page 1 + Page 2)
- Employé connecté : assistante maternelle authentifiée qui revient compléter ou modifier ses informations via "Mes données"

## Functional Needs

### Page 1 — Création de compte (obligatoire)
- SFD-1: L'utilisateur accède à la page `/register` depuis le lien "Créer un compte" de l'écran `/login`
- SFD-2: L'utilisateur saisit son email, un mot de passe, la confirmation du mot de passe et son numéro de téléphone
- SFD-3: Le système valide la complexité du mot de passe côté UI avant la soumission
- SFD-4: Le système vérifie côté backend que l'email n'existe pas déjà en table `Employee`
- SFD-5: Un compte est créé en base via `INSERT INTO Employee (Telephone, Email, MotdePass)` avec le mot de passe hashé si la validation réussit
- SFD-6: Après création réussie Page 1, l'utilisateur est redirigé vers la **Page 2** (complétion du profil) — pas directement vers `/login`
- SFD-7: Un message d'erreur générique est affiché si l'email est déjà utilisé sans révéler explicitement l'existence du compte
- SFD-8: Un message d'erreur de validation est affiché si la confirmation ne correspond pas au mot de passe
- SFD-9: Un message d'erreur de validation est affiché si le mot de passe ne respecte pas les règles de complexité
- SFD-10: Le bouton "Créer un compte" est désactivé pendant le traitement pour empêcher toute double-soumission

### Page 2 — Complétion du profil (optionnelle à l'inscription)
- SFD-11: Après la création réussie en Page 1, le système récupère l'`ID` auto-incrémenté de l'`Employee` créé et le conserve côté client (state ou URL) pour piloter l'UPDATE de la Page 2
- SFD-12: La Page 2 affiche les champs d'état civil : `Nom`, `Prenom`, `NomJeuneFille`, `DateNaissance`
- SFD-13: La Page 2 affiche les champs de lieu de naissance : `LieuNaissancePays`, `LieuNaissanceDepartement`, `LieuNaissanceVille`
- SFD-14: La Page 2 affiche les champs d'adresse : `Rue`, `CodePostal`, `Ville`
- SFD-15: La Page 2 affiche les champs réglementaires : `NumeroSecuriteSociale`, `DateDebutAgrement`, `DateDernierRenouvellement`, `AssuranceProNumero`, `AssuranceProCompagnie`
- SFD-16: La Page 2 affiche un composant **d'upload d'image** (avatar de l'assistante maternelle) accepting **uniquement des fichiers PNG**. Le fichier est envoyé au backend, stocké dans le répertoire statique `wwwroot/images/` (ou équivalent selon stack) du serveur, et **seul le nom du fichier** est persisté dans la colonne `Image` de la table `Employee` (la URL/chemin complet est reconstruit côté client à l'affichage)
- SFD-16.bis: Une preview d'avatar est **TOUJOURS affichée** en haut au centre du formulaire (Page 2 post-register OU "Mes données"), au-dessus du composant d'upload. Si la colonne `Image` est renseignée, c'est l'image actuelle de l'assistante maternelle qui est affichée ; sinon, c'est un **avatar par défaut** servi statiquement par l'application (`/assets/default-avatar.png`) qui est affiché. Dans les deux cas le composant d'upload est disponible pour remplacer/définir l'image.
- SFD-16.ter: Lors d'un remplacement d'image, le fichier statique est **écrasé en place** (nom de fichier stable `{employeeId}.png`, un seul fichier image par employé, pas d'accumulation d'historique). La colonne `Image` reste cohérente avec le nom de fichier stable. Aucun fichier orphelin n'est généré tant que le schéma de nommage reste `{employeeId}.png`.
- SFD-17: La Page 2 propose deux boutons explicites : **"Enregistrer"** et **"Continuer plus tard"** (libellé alternatif accepté : "Renseigner plus tard")
- SFD-18: Un clic sur **"Enregistrer"** déclenche un `UPDATE Employee SET ... WHERE id = {ID}` côté backend avec les valeurs saisies, puis redirige vers `/login`
- SFD-19: Un clic sur **"Continuer plus tard"** redirige immédiatement vers `/login` **sans** appel UPDATE — les colonnes Page 2 restent à leur valeur par défaut en base
- SFD-20: Aucun champ de la Page 2 n'est obligatoire pour finaliser l'inscription : un employé peut créer son compte avec uniquement les champs Page 1
- SFD-21: Le bouton "Enregistrer" Page 2 est désactivé pendant le traitement pour empêcher toute double-soumission

### Menu "Mes données" — Modification du profil (employé connecté)
- SFD-22: L'employé connecté accède à la **page "Mes données"** depuis l'item correspondant du menu principal
- SFD-23: "Mes données" affiche les mêmes champs que la Page 2 (SFD-12 à SFD-16.ter) pré-remplis depuis l'état actuel de l'employé en base, y compris la **preview de l'image avatar** courante au-dessus du composant d'upload (cf. SFD-16.bis)
- SFD-24: "Mes données" permet à l'employé connecté de modifier ses informations et de cliquer sur "Enregistrer" pour déclencher le même `UPDATE Employee WHERE id = {ID}` que la Page 2
- SFD-25: L'accès à "Mes données" sans session valide redirige vers `/login` (comportement standard, couvert par spec-connexion)
- SFD-26: Tant que les champs réglementaires (`NumeroSecuriteSociale`, agrément, assurance) ne sont pas renseignés, un message d'avertissement informatif est affiché à l'employé pour signaler que la création d'un contrat (spec future) en sera bloquée

## Business Rules
- BR-1: l'email d'un employé doit être unique en table `Employee`
- BR-2: le mot de passe doit respecter une politique de complexité minimale (longueur minimale et présence d'au moins un caractère varié)
- BR-3: le mot de passe est stocké uniquement sous forme de hash sécurisé, jamais en clair
- BR-4: le message d'erreur en cas de duplication d'email reste générique pour ne pas révéler l'existence d'un compte
- BR-5: aucune information technique (stack trace, identifiant interne, exception) n'est exposée dans les messages d'erreur visibles à l'utilisateur
- BR-6: le numéro de téléphone est obligatoire à la création de compte (Page 1) et stocké tel quel ; aucune normalisation de format n'est imposée à ce stade
- BR-7: l'`ID` auto-incrémenté de l'`Employee` créé en Page 1 est retourné par l'endpoint `POST /api/auth/register` et conservé côté client (state) jusqu'au choix utilisateur Page 2 ("Enregistrer" ou "Continuer plus tard")
- BR-8: l'endpoint `UPDATE Employee` utilisé par la Page 2 ET par "Mes données" n'accepte que l'`ID` de l'employé propriétaire (Page 2 → ID récupéré juste après INSERT ; "Mes données" → ID issu du token JWT de session) ; aucun employé ne peut modifier les données d'un autre
- BR-9: les champs Page 2 sont nullable au niveau métier — l'absence d'un champ ne bloque ni la création de compte ni la connexion ; elle ne bloque que les fonctionnalités aval (création de contrat, spec future) qui les exigent
- BR-10: la validation des longueurs des champs Page 2 respecte les contraintes nvarchar de la table `Employee` (cf. schéma DB) : `Nom`, `Prenom`, `NomJeuneFille` ≤ 25 ; `LieuNaissancePays` ≤ 25 ; `LieuNaissanceDepartement` ≤ 50 ; `LieuNaissanceVille`, `Ville` ≤ 50 ; `Rue` ≤ 200 ; `CodePostal` ≤ 10 ; `NumeroSecuriteSociale`, `AssuranceProNumero`, `Image` ≤ 100 ; `AssuranceProCompagnie` ≤ 150
- BR-11: en cas d'erreur réseau ou serveur lors de l'UPDATE Page 2 ou "Mes données", l'utilisateur reste sur la page courante avec un message générique ; aucune perte silencieuse des données saisies (le formulaire conserve les valeurs)
- BR-12: l'upload d'image avatar **n'accepte que le type MIME `image/png`** et l'extension `.png` ; tout autre format (JPEG, GIF, WebP, SVG…) est rejeté côté UI ET côté backend avec un message d'erreur explicite
- BR-13: la taille maximale d'un fichier image uploadé est de **2 Mo** ; au-delà, l'upload est rejeté côté UI avant envoi (et défensivement côté backend)
- BR-14: le nom du fichier image stocké en `wwwroot/images/` (ou équivalent) est **stable et déterministe** : pattern strict `{employeeId}.png`. Un seul fichier image par employé est conservé sur disque ; pas d'accumulation d'historique. Le remplacement écrase le fichier précédent. Le nom d'origine fourni par l'utilisateur n'est **jamais** réutilisé tel quel.
- BR-15: la colonne `Image` de la table `Employee` stocke uniquement le **nom du fichier** (ex. `42.png`), pas le chemin complet ni l'URL. L'API serveur (`GET /api/employees/me`) renvoie ce champ sous forme d'URL servable directement (`/images/{nom}`) pour éviter toute concaténation côté client.
- BR-16: lors du remplacement d'une image existante, le fichier est **écrasé en place** (writeFile sur le même chemin `wwwroot/images/{employeeId}.png`) ; aucun delete séparé n'est requis. Cas particulier — migration depuis l'ancien schéma de nommage timestampé (`{employeeId}-{ms}.png`, legacy) : si la colonne `Image` actuelle diffère du nouveau nom stable, l'ancien fichier est supprimé après UPDATE en best-effort (échec de suppression → fichier orphelin toléré, log warning serveur, pas de rollback).
- BR-17: la réponse de l'endpoint d'upload `POST /api/employees/me/image` inclut une URL **avec cache-buster** (`/images/{nom}?v={timestamp}`) pour forcer le navigateur à recharger l'image après remplacement, le nom de fichier étant désormais stable.

## Acceptance Criteria
- AC-1: la page `/register` (Page 1) affiche un champ email, un champ mot de passe, un champ confirmation du mot de passe, un champ numéro de téléphone, et un bouton "Créer un compte"
- AC-2: une création Page 1 avec email inédit, mot de passe conforme à la politique de complexité, et téléphone renseigné affiche **la Page 2** (complétion du profil) après succès
- AC-3: une tentative Page 1 avec email déjà existant affiche un message d'erreur générique et l'utilisateur reste sur `/register` Page 1
- AC-4: une confirmation de mot de passe différente du mot de passe affiche un message d'erreur de validation (Page 1, jamais soumis au backend)
- AC-5: un mot de passe ne respectant pas la complexité affiche un message d'erreur de validation (Page 1, jamais soumis au backend)
- AC-6: le bouton "Créer un compte" est désactivé pendant le traitement de la Page 1
- AC-7: après une inscription complète (Page 1 + Page 2 "Enregistrer" OU Page 1 + Page 2 "Continuer plus tard"), l'utilisateur peut se connecter à `/login` avec son email et son mot de passe
- AC-8: la Page 2 affiche tous les champs listés en SFD-12 à SFD-16.ter (état civil, lieu de naissance, adresse, réglementaires, composant d'upload image PNG) et deux boutons "Enregistrer" / "Continuer plus tard"
- AC-9: un clic sur "Enregistrer" en Page 2 avec au moins un champ renseigné déclenche un `UPDATE Employee WHERE id = {ID}` puis redirige vers `/login`
- AC-10: un clic sur "Continuer plus tard" en Page 2 redirige immédiatement vers `/login` **sans** appel UPDATE — le compte employé existe en base avec uniquement les colonnes Page 1 renseignées
- AC-11: une Page 2 entièrement vide soumise via "Enregistrer" est traitée comme un UPDATE avec tous les champs à NULL (équivalent fonctionnel à "Continuer plus tard", mais l'appel backend est effectif) — comportement toléré, le frontend peut court-circuiter en mode "Continuer plus tard" si l'utilisateur n'a rien modifié
- AC-12: après connexion ultérieure, un clic sur le menu "Mes données" affiche les champs renseignés (ou vides) depuis la base
- AC-13: la modification d'un champ dans "Mes données" suivie d'un clic sur "Enregistrer" persiste les changements en base via `UPDATE Employee WHERE id = {ID_session}` et affiche un feedback de succès
- AC-14: un appel `UPDATE Employee` avec un `id` différent de celui de l'employé connecté (manipulation manuelle de la requête) est rejeté côté backend avec un statut 403 Forbidden
- AC-15: tant que les champs réglementaires (`NumeroSecuriteSociale`, `DateDebutAgrement`, `AssuranceProNumero`, `AssuranceProCompagnie`) sont vides en base, un bandeau d'avertissement informatif est affiché en haut de la page "Mes données"
- AC-16: un upload de fichier non PNG (ex. `.jpg`, `.gif`, `.svg`) sur le composant d'upload de la Page 2 ou "Mes données" est rejeté côté UI avec un message d'erreur explicite ("Seuls les fichiers PNG sont acceptés") et n'est pas envoyé au backend
- AC-17: un upload de fichier PNG > 2 Mo est rejeté côté UI avec un message d'erreur explicite ("Fichier trop volumineux, taille maximale 2 Mo") et n'est pas envoyé au backend
- AC-18: un upload de fichier PNG ≤ 2 Mo sur la Page 2 puis clic sur "Enregistrer" stocke le fichier dans `wwwroot/images/` (ou équivalent serveur) avec le nom stable `{employeeId}.png`, enregistre ce nom dans la colonne `Image` de `Employee`, et redirige vers `/login`
- AC-19: à l'ouverture de la Page 2 OU de "Mes données", une preview avatar est **TOUJOURS affichée** en haut au centre du formulaire au-dessus du composant d'upload. Pour un `Employee` ayant `Image` non NULL, la preview affiche l'image courante de l'employée (URL `/images/{nom}` retournée par l'API). Pour un `Employee` ayant `Image` NULL, la preview affiche l'avatar par défaut (`/assets/default-avatar.png`). Dans les deux cas le composant d'upload reste disponible pour définir/remplacer l'image.
- AC-20: l'upload d'une nouvelle image PNG sur un `Employee` ayant déjà une `Image` non NULL suivi d'un clic sur "Enregistrer" écrase le fichier `{employeeId}.png` sur disque en place (nom stable, pas d'accumulation), conserve la même valeur dans la colonne `Image` et permet au navigateur de réafficher la nouvelle image via la réponse URL avec cache-buster (cf. BR-17). Si la colonne `Image` contenait un nom legacy timestampé différent, l'ancien fichier est supprimé en best-effort.
- AC-21: un appel direct au endpoint d'upload avec un fichier dont le type MIME n'est pas `image/png` (manipulation manuelle de la requête) est rejeté côté backend avec un statut 400 Bad Request

## Dependencies
- NONE pour la livraison de Page 1 + Page 2 (spec-connexion est liée navigationnellement via le lien "Créer un compte" mais n'est pas bloquante)
- L'accès au menu "Mes données" requiert que **spec-connexion** soit livrée (session JWT valide pour identifier l'employé via son ID — cf. BR-8) et que **spec-menu-principale** expose l'item de menu "Mes données"

## Functional Deliverables
- FD-1: écran de création de compte `/register` Page 1 avec formulaire email + mot de passe + confirmation + numéro de téléphone
- FD-2: création persistante du compte employé en table `Employee` via INSERT (Telephone, Email, MotdePass) avec mot de passe hashé, retour de l'`ID` auto-incrémenté
- FD-3: validation côté UI et côté backend de l'email, du mot de passe et de la non-duplication
- FD-4: redirection automatique vers la Page 2 après création Page 1 réussie (et vers `/login` après finalisation Page 2)
- FD-5: écran de complétion du profil (Page 2) affiché après inscription Page 1, avec les champs d'état civil, lieu de naissance, adresse, agrément, assurance et **composant d'upload image PNG** — deux boutons "Enregistrer" et "Continuer plus tard"
- FD-6: page "Mes données" accessible depuis le menu principal à l'employé connecté, affichant les mêmes champs que la Page 2 pré-remplis depuis la base, **incluant la preview de l'image avatar courante** au-dessus du composant d'upload si `Image` est non NULL
- FD-7: endpoint backend `PUT /api/employees/{id}` (ou équivalent) effectuant l'UPDATE Employee scoped à l'`id` propriétaire (cf. BR-8), consommé par la Page 2 ET par "Mes données"
- FD-8: bandeau d'avertissement informatif affiché dans "Mes données" tant que les champs réglementaires sont vides (cf. AC-15)
- FD-9: endpoint backend `POST /api/employees/{id}/image` (ou équivalent) effectuant la réception du fichier PNG (multipart/form-data), validant type MIME + taille (cf. BR-12, BR-13), stockant le fichier sous nom déterministe dans `wwwroot/images/` (cf. BR-14), mettant à jour la colonne `Image` du `Employee` propriétaire (cf. BR-8), et supprimant l'ancien fichier statique en cas de remplacement (cf. BR-16)
- FD-10: répertoire statique serveur dédié au stockage des images uploadées (`wwwroot/images/` pour .NET / Blazor, `public/images/` pour Node, `static/images/` pour FastAPI/Spring), servi par le backend en routes statiques (`GET /images/{filename}`), utilisé pour les images d'assistantes maternelles ET (à venir, hors scope) des bébés et autres entités du domaine

## Out of Scope
- validation de l'email par lien de confirmation envoyé par email
- import en masse de comptes employés
- création de compte par un administrateur
- rôles Admin et Parent (extensions futures)
- intégration SSO / OAuth
- formats d'image autres que PNG (JPEG, WebP, SVG, GIF…) — uniquement PNG accepté par cette spec
- redimensionnement / compression / génération de thumbnails automatique côté serveur après upload (le fichier est stocké tel que uploadé après validation type + taille)
- upload d'images pour des entités autres que `Employee` (bébés, contrats, etc.) — le répertoire statique est mutualisé (cf. FD-10) mais ces specs sont à venir
- validation de format métier des champs réglementaires (`NumeroSecuriteSociale` français, codes postaux étrangers, validation croisée des dates d'agrément) — Out of Scope, les champs sont stockés tels quels en Page 2 / Mes données
- création / modification du contrat employé (couvert par spec future, qui exigera les champs réglementaires renseignés)
- récupération du mot de passe oublié (couverte par spec-reinitialisation)
- gestion multi-tenant / multi-organisation
