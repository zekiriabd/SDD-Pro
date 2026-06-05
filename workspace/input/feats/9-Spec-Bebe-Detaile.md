# Spec: bebe-detaille

FEAT ID: 9-bebe-detaille
Spec ID: spec-bebe-detaille
Status: Draft

## Context
L'employé connecté (assistante maternelle) accède aujourd'hui à la liste de ses bébés via `/bebes` (cf. spec-bebes AC-2) et peut créer un nouveau contrat via le wizard `/contrats/nouveau` (cf. spec-souscrire-contrat). En revanche, **aucun écran de consultation détaillée** d'un bébé n'existe : impossible aujourd'hui de visualiser dans une seule fiche les informations de l'enfant, les coordonnées des parents, le récap du contrat (dates, période d'essai, Pajemploi, rémunération, horaires hebdomadaires) ni de modifier un contrat existant.

Cette spec décrit la page `/bebes/{ContratId}` (alias `/bebes/detail/{ContratId}`) qui affiche les informations agrégées d'un bébé sélectionné en deux blocs : (1) une **topbar** avec retour vers `/bebes`, le nom du bébé sélectionné et son avatar ; (2) un **conteneur à trois onglets** (`Informations`, `Rapport du jour`, `Rendez-vous`). L'onglet `Informations` (focus principal de cette FEAT) restitue l'identité du bébé, les deux parents et le récap contrat / salaire / horaires via une requête SQL unique joignant `Contrat` × `Employeur`. Les onglets `Rapport du jour` et `Rendez-vous` sont matérialisés en **interfaces statiques uniquement** dans cette FEAT (squelettes UI, aucun appel backend) — leur logique métier est traitée dans des FEATs ultérieures dédiées.

L'écran ouvre également la possibilité de **modifier** le contrat et les informations parents existants : un **FAB unique** (Floating Action Button circulaire coral en bas à droite du panneau `Informations`, icône crayon `Edit`) redirige vers l'écran wizard existant `08-souscrire-contrat.html` sur la route RESTful canonique **`/contrats/{ContratId}`** (route distincte de `/contrats/nouveau` qui reste exclusivement réservée à la création). Le wizard détecte le mode (`create` si `/contrats/nouveau`, `edit` si `/contrats/{numeric-id}`) côté frontend en parsant `window.location.pathname`. En mode edit, l'écran wizard pré-remplit ses 5 étapes depuis le contrat existant, n'exécute **aucune insertion**, et déclenche au save final deux UPDATE séquentiels (`Employeur` puis `Contrat`) dans une transaction unique — par symétrie avec le couple d'INSERT de spec-souscrire-contrat. La spec-souscrire-contrat est complétée pour accepter cette nouvelle route edit sans casser le flux de création.

## Objective
L'employé connecté ouvre la fiche détaillée d'un bébé (depuis le clic sur une card de `/bebes`), visualise dans un onglet `Informations` l'identité enfant + 2 parents + récap contrat + salaire + horaires hebdomadaires (chargés via une requête SQL `Contrat × Employeur` filtrée par `EmployeeId` de session), peut basculer entre 3 onglets (`Informations`, `Rapport du jour`, `Rendez-vous` — ces deux derniers servis comme squelettes UI statiques), et peut déclencher une modification du contrat existant via le wizard `08-souscrire-contrat.html` en mode `edit` (deux UPDATE transactionnels en lieu et place des INSERT) puis revient sur la fiche détaillée avec les valeurs à jour. Le retour `/bebes` est accessible à tout instant via la flèche topbar.

## Quantified Goal (v7.0.0 — anti-GIGO)
- Metric: temps de chargement de la fiche bébé (Time-To-Interactive client après clic sur card `/bebes`)
- Target: p95 < 800 ms sur réseau 4G simulé (1 unique requête SQL joignant `Contrat × Employeur`, payload < 6 KB JSON, rendu client < 200 ms)
- Deadline: livraison stack `kotlin-spring-boot × react × shadcn` au 2026-06-30

## Non-Functional Constraints (v7.0.0)
- Expected volume: ~50 ouvertures de fiche / employé / jour, < 5k requêtes/jour total pour la beta Demo
- Performance SLA: p95 chargement fiche < 800 ms (cf. Quantified Goal) ; p95 UPDATE transactionnel `Employeur + Contrat` < 600 ms
- Data retention: les données `Contrat` et `Employeur` sont conservées tant que l'employé reste actif ; pas d'historique d'audit des modifications dans cette FEAT (out of scope — spec future)
- Compliance: RGPD — les données parents (téléphones, emails, adresse) ne sont visibles que par l'employé propriétaire du contrat (`Contrat.EmployeeId == session.EmployeeId`), jamais cross-employé
- Integration: réutilise l'endpoint backend du wizard existant `POST /api/contrats` (cf. spec-souscrire-contrat FD-7) étendu d'un endpoint symétrique `PUT /api/contrats/{ContratId}` (deux UPDATE transactionnels Employeur+Contrat) déclenché par la route SPA `/contrats/{ContratId}` ; aucun nouveau service externe
- Degraded mode: si le backend est down, la fiche affiche un message d'erreur générique et un bouton `Réessayer` ; aucun cache local ; le retour `/bebes` reste fonctionnel

## Actors
- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session. Aucun accès à la page sans authentification. Seul autorisé à consulter et modifier les contrats dont `Contrat.EmployeeId == session.EmployeeId`.

## Functional Needs

### Navigation et entrée dans la fiche
- SFD-1: L'utilisateur accède à la page `/bebes/{ContratId}` depuis le clic sur une card bébé de `/bebes` (cf. spec-bebes AC-8 — l'icône "Rapport" est étendue / le clic sur la card entière déclenche désormais la navigation vers la fiche détaillée) ; la navigation est SPA (`useNavigate()` / équivalent stack)
- SFD-2: Au chargement, la page envoie une requête backend unique `GET /api/contrats/{ContratId}` qui retourne un payload agrégé `{ contrat: {...}, employeur: {...} }` joignant les deux tables côté serveur via la requête SQL canonique (cf. SFD-12)
- SFD-3: Le `ContratId` provient du segment d'URL ; la requête backend vérifie en plus que `Contrat.EmployeeId == session.EmployeeId` avant de retourner les données (cf. BR-1) — sinon réponse 404 (jamais 403 — anti-énumération)
- SFD-4: Pendant le chargement, un état de squelette / spinner est affiché sur l'ensemble du contenu (topbar et onglets) ; aucune donnée placeholder ne doit être visible
- SFD-5: La flèche `Retour` (topbar gauche) déclenche une navigation SPA vers `/bebes` ; aucun dialogue de confirmation (la fiche est en lecture seule depuis le point de vue de cet écran — les modifications passent par le wizard externe)

### Topbar (bloc supérieur)
- SFD-6: La topbar affiche, de gauche à droite : (1) une icône bouton circulaire `Retour` (chevron gauche), (2) le nom et prénom du bébé (ex. `Lina Bouchet` — `Contrat.Prenom + ' ' + Contrat.Nom`), (3) un avatar circulaire affichant la photo du bébé (`Contrat.ImageUrl` concaténé avec la base statique du serveur, fallback initiales si NULL)
- SFD-7: La topbar reste **fixe en haut** de l'écran (flex-shrink:0 du conteneur app) — le scroll ne s'applique qu'au contenu de l'onglet actif sous la barre des tabs

### Conteneur à 3 onglets
- SFD-8: Sous la topbar, une barre de 3 onglets (TAB) est affichée : `Informations` (icône info), `Rapport du jour` (icône document), `RDV` (icône calendrier — affiche un badge compteur si rendez-vous à venir, ex. `2`)
- SFD-9: Un seul onglet est actif à la fois ; le clic sur un onglet active sa section et remet à zéro le scroll vertical du conteneur de panneaux
- SFD-10: L'onglet `Informations` est actif par défaut au chargement de la page
- SFD-11: La barre des onglets reste **fixe** sous la topbar — seul le contenu de l'onglet actif scrolle verticalement

### Onglet 1 — Informations (focus de cette FEAT)
- SFD-12: L'onglet `Informations` agrège les données via une requête SQL **unique** côté backend joignant `Contrat × Employeur` filtrée par `Contrat.ContratId` ET `Contrat.EmployeeId == session.EmployeeId` :
  ```sql
  SELECT
    -- Contrat (récap enfant + contrat + salaire + horaires)
    c.ContratId, c.Nom, c.Prenom, c.DateNaissance,
    c.AccueilRue, c.AccueilCodePostal, c.AccueilVille,
    c.DateEffetContrat, c.PeriodeEssaiDuree, c.PeriodeEssaiDateDebut,
    c.ModalitesFamiliarisation, c.JourReposEmploye,
    c.NombreHeuresHebdo,
    c.SalaireBaseBrut, c.SalaireBaseNet,
    c.MajorationPourcentage, c.SalaireMajoreBrut, c.SalaireMajoreNet,
    c.LundiDebut, c.LundiFin, c.MardiDebut, c.MardiFin,
    c.MercrediDebut, c.MercrediFin, c.JeudiDebut, c.JeudiFin,
    c.VendrediDebut, c.VendrediFin, c.SamediDebut, c.SamediFin,
    c.ParticularitesPlanning, c.AutresParticularites,
    c.HorairesNonPrecisesComment, c.ImageUrl,
    -- Employeur (récap parent principal)
    e.EmployeurId, e.Nom AS EmployeurNom, e.Prenom AS EmployeurPrenom,
    e.LienParentale,
    e.Rue AS EmployeurRue, e.CodePostal AS EmployeurCodePostal, e.Ville AS EmployeurVille,
    e.TelPersonnel, e.TelPersonnel2, e.TelProfessionnel, e.Email,
    e.NumeroPajemploi
  FROM dbo.Contrat c
  INNER JOIN dbo.Employeur e ON c.EmployeurId = e.EmployeurId
  WHERE c.ContratId = @ContratId
    AND c.EmployeeId = @SessionEmployeeId;
  ```
  La requête est **paramétrée** (jamais de concaténation de chaîne) et retourne 0 ou 1 ligne (PK + filtre session).
- SFD-13: L'onglet `Informations` affiche 5 sections empilées verticalement, sans `section-label` visible (les sections sont délimitées uniquement par l'espacement entre cartes pour un rendu épuré) ; un **FAB unique** (cf. SFD-20) en bas à droite du panneau ouvre le wizard de modification :
  - **Identité enfant**
  - **Parents**
  - **Contrat**
  - **Salaire**
  - **Horaires hebdomadaires**
- SFD-14: Section `Identité enfant` — carte avec icône souriante (coral) affichant : `Prénom` (`Contrat.Prenom`), `Nom` (`Contrat.Nom`), `Naissance` (`Contrat.DateNaissance` formatée `dd mois yyyy`, suffixe âge calculé en mois/années), `Allergies` (placeholder `Aucune connue` — colonne non présente en schéma DB actuel, affichage statique), `Doudou` (placeholder — colonne non présente, affichage statique), `Lieu d'accueil` (`Contrat.AccueilRue` + saut de ligne + `Contrat.AccueilCodePostal + ' ' + Contrat.AccueilVille`)
- SFD-15: Section `Parents` — affiche une carte par parent côté UI. Le schéma actuel ne stocke **qu'un seul `Employeur`** par `Contrat` (FK `Contrat.EmployeurId` unique cf. schema.md ligne 29). Une **seule carte parent** est donc affichée, intitulée selon `Employeur.LienParentale` (ex. `Mère — Sophie Bouchet`, `Père — Marc Bouchet`, `Tuteur légal — X Y`) avec les champs : `Téléphone` (`Employeur.TelPersonnel`), `Tél. pro.` (`Employeur.TelProfessionnel` si renseigné), `Email` (`Employeur.Email`), `Adresse` (`Employeur.Rue` + saut de ligne + `Employeur.CodePostal + ' ' + Employeur.Ville`). Les actions rapides (`Appeler`, `SMS`, `Email`) utilisent des liens natifs `tel:`, `sms:`, `mailto:`
- SFD-16: Section `Contrat` — carte avec icône document (butter) affichant : `Début` (`Contrat.DateEffetContrat` formatée), `Période d'essai` (`Contrat.PeriodeEssaiDuree` + suffixe `jours · jusqu'au {DateEffetContrat + PeriodeEssaiDuree jours}` calculée côté UI), `Familiarisation` (`Contrat.ModalitesFamiliarisation` — texte libre), `Jour(s) de repos` (`Contrat.JourReposEmploye` — CSV `Lun,Mar,...` re-formaté `Dimanche` ou `Samedi, Dimanche`), `Pajemploi` (`Employeur.NumeroPajemploi` en font-mono)
- SFD-17: Section `Salaire` — carte avec icône euro (coral) affichant : `Heures / sem.` (`Contrat.NombreHeuresHebdo` + suffixe `· au-delà : majoré {MajorationPourcentage}%` si `MajorationPourcentage > 0`), `Brut` (`Contrat.SalaireBaseBrut` formaté `X,XX €` en font-mono + ` / h` + suffixe `· majoré : {SalaireMajoreBrut} €` si renseigné), `Net` (idem `SalaireBaseNet` + `SalaireMajoreNet`), `Mensuel net` (calculé côté UI `round(NombreHeuresHebdo × SalaireBaseNet × 52 / 12, 2)`, affiché en gras coral — purement informatif comme SFD-29 de spec-souscrire-contrat)
- SFD-18: Section `Horaires hebdomadaires` — carte avec icône horloge (sky) affichant 6 lignes Lun-Sam avec format `HH:MM — HH:MM` en font-mono, lus depuis `Contrat.{Jour}Debut` / `Contrat.{Jour}Fin` ; pour les jours dont les colonnes sont NULL (jour de repos), afficher `<small>Repos</small>` en place du créneau ; une 7ᵉ ligne `Sam. — Dim.` regroupe les jours de repos en queue si pertinent
- SFD-19: Si l'une des sections n'a pas de donnée (`Contrat.ModalitesFamiliarisation` NULL, `Employeur.TelProfessionnel` NULL, etc.), la ligne correspondante affiche un dash `—` en `info-row__v` ; la ligne reste visible (pas de masquage conditionnel sur les lignes de la fiche détaillée)

### Modification du contrat (FAB Edit)
- SFD-20: L'onglet `Informations` affiche **un unique FAB** (Floating Action Button) circulaire en bas à droite du panneau, fond coral-500, icône crayon `Edit` (jamais `+`), 54×54px, ombre douce — il **remplace** les anciens boutons `Modifier` per-section et constitue le seul point d'entrée vers la modification du contrat depuis cet écran
- SFD-21: Un clic sur le FAB de l'onglet `Informations` déclenche une navigation SPA vers `/contrats/{ContratId}` (route RESTful canonique — édition d'une ressource contrat existante ; à distinguer de `/contrats/nouveau` qui reste exclusivement réservé à la création). Le wizard de modification couvre la totalité des 5 étapes (Parents → Enfant → Contrat → Rémunération → Horaires) et s'ouvre par défaut sur la première étape (aucune sélection de section côté fiche)
- SFD-22: Au chargement du wizard en mode edit (route `/contrats/{ContratId}`), l'écran récupère le contrat existant via `GET /api/contrats/{ContratId}` (même endpoint que SFD-2) et **pré-remplit l'intégralité des 5 étapes** : Parents (Employeur), Enfant (Contrat — identité + lieu d'accueil), Contrat (dates + modalités + temps de travail), Rémunération (salaires), Horaires (matrice 6 jours)
- SFD-23: En mode edit (route `/contrats/{ContratId}`), le bouton final de l'étape 5 affiche `Enregistrer les modifications` (au lieu de `Enregistrer le contrat`) et exécute, dans une **transaction SQL unique** côté backend, deux UPDATE séquentiels : (1) `UPDATE Employeur SET ... WHERE EmployeurId = @EmployeurId AND EmploierId = @SessionEmployeeId` ; (2) `UPDATE Contrat SET ... WHERE ContratId = @ContratId AND EmployeeId = @SessionEmployeeId`
- SFD-24: En mode edit (route `/contrats/{ContratId}`), **aucune insertion** n'est exécutée : ni `INSERT INTO Employeur`, ni `INSERT INTO Contrat`. La validation BR-2 de spec-souscrire-contrat (transaction unique back-rollback) reste applicable au couple UPDATE
- SFD-25: En mode edit (route `/contrats/{ContratId}`), le pré-remplissage du Lieu d'accueil n'est **pas** réécrit depuis l'adresse de l'employé connecté (cf. SFD-15 de spec-souscrire-contrat) ; les valeurs `Contrat.AccueilRue / AccueilCodePostal / AccueilVille` du contrat existant sont chargées telles quelles
- SFD-26: En mode edit (route `/contrats/{ContratId}`), la photo bébé pré-chargée à l'étape 2 affiche la `Contrat.ImageUrl` existante (préfixée `/images/{filename}` par le frontend, cf. BR-11) — un remplacement (upload nouveau fichier JPG/PNG ≤ 5 Mo) est autorisé ; règle de remplacement **in-place** : (1) si `Contrat.ImageUrl` est non null, le backend SUPPRIME l'ancien fichier physique sous `public/images/{old_filename}` (best-effort, échec silencieux toléré si déjà absent) puis ÉCRIT le nouveau buffer sous le **même nom** que l'ancien (`Contrat.ImageUrl` reste inchangé en base — préservation des références côté front, pas d'historique image) ; (2) si `Contrat.ImageUrl` est null, le backend génère un nom déterministe `{ContratId}.{ext}` et met à jour `Contrat.ImageUrl` ; sans nouvel upload, `Contrat.ImageUrl` reste strictement inchangé
- SFD-27: Après succès complet du couple UPDATE (et upload image optionnel), l'utilisateur est redirigé en SPA vers `/bebes/{ContratId}` (la fiche détaillée d'origine) et **non** vers `/bebes` — la fiche est rechargée avec les valeurs à jour
- SFD-28: En cas d'échec du second UPDATE (`Contrat`), le premier UPDATE (`Employeur`) est **intégralement rollbacké** — aucune modification partielle ne persiste en base
- SFD-29: La spec `spec-souscrire-contrat` est **complétée** pour accepter le paramètre `mode` avec valeurs `create` (défaut, comportement actuel = couple INSERT) et `edit` (couple UPDATE) ; la cohérence des autres champs et règles métier (BR-4 à BR-25) est préservée

### Onglet 2 — Rapport du jour (interface statique uniquement)
- SFD-30: L'onglet `Rapport du jour` affiche une interface **statique non interactive** sans appel backend : **aucun `section-label`** ni titre `Rapport du jour` visible (rendu épuré), une grande zone `textarea` pré-remplie avec un texte de démonstration en dur (cf. mockup `9-1-Spec-Bebe-Detaile.html`), et un **FAB unique** (Floating Action Button circulaire coral-500, icône crayon `Edit`, en bas à droite) cosmétique pointant vers `07-rapport-du-jour.html` (cible UI uniquement — aucun code/page de destination implémenté dans cette FEAT). Le bouton plein-largeur `Envoyer aux parents` est **retiré** : l'envoi SMS/Email aux parents est traité dans une FEAT ultérieure dédiée à la gestion des rapports
- SFD-31: Aucune persistance, aucun envoi, aucune validation ne sont implémentés pour l'onglet `Rapport du jour` dans cette FEAT — l'interface est purement présentationnelle pour valider le design ; la logique métier complète (génération du texte depuis les choix de la journée, envoi SMS/Email aux parents, archivage en base) est traitée dans une FEAT ultérieure dédiée

### Onglet 3 — Rendez-vous (interface statique uniquement)
- SFD-32: L'onglet `RDV` (Rendez-vous) affiche une interface **statique non interactive** sans appel backend : **aucun `section-label`** `Rendez-vous` visible en tête (rendu épuré), une liste d'événements en dur regroupés en deux sections (la sous-section `Passé` reste introduite par un `section-label` séparateur — cf. mockup), chaque événement présenté en carte horizontale (date pastille, libellé, horaire, chevron), et un bouton FAB `+` flottant en bas droite (cosmétique non fonctionnel, conservé tel quel pour symboliser l'ajout d'un RDV)
- SFD-33: Aucune persistance, aucune création, aucune édition de rendez-vous ne sont implémentées pour l'onglet `RDV` dans cette FEAT — l'interface est purement présentationnelle pour valider le design ; la logique métier complète (CRUD rendez-vous, notifications, conflits de calendrier, synchronisation iCal) est traitée dans une FEAT ultérieure dédiée
- SFD-34: Le badge compteur de l'onglet `RDV` (ex. `2`) est affiché **en dur** (valeur statique `2` ou masqué) dans cette FEAT — aucun calcul dynamique sur le nombre de RDV à venir

## Business Rules
- BR-1: la requête `GET /api/contrats/{ContratId}` exécute la jointure `Contrat × Employeur` filtrée à la fois par `ContratId = @ContratId` ET `Contrat.EmployeeId = @SessionEmployeeId` ; aucun contrat n'est exposé hors du périmètre de l'employé connecté
- BR-2: `@SessionEmployeeId` provient exclusivement de la variable singleton de session de l'employé connecté ; aucun paramètre de requête utilisateur ne peut le surcharger
- BR-3: si le contrat n'est pas trouvé OU appartient à un autre employé, la réponse backend est **404 Not Found** (jamais 403 — anti-énumération d'ID)
- BR-4: la requête SQL `GET /api/contrats/{ContratId}` retourne 0 ou 1 ligne (`ContratId` est PK + filtre session) ; si 0 ligne → 404
- BR-5: la jointure utilise `INNER JOIN` sur `Contrat.EmployeurId = Employeur.EmployeurId` ; un contrat sans `EmployeurId` (FK NULL admis par le schéma cf. schema.md ligne 29) retourne 0 ligne — donc 404 — car l'écran n'a aucune valeur sans parent
- BR-6: la requête SQL est **paramétrée** (`@ContratId`, `@SessionEmployeeId`) — aucune concaténation de chaîne autorisée (anti-injection SQL)
- BR-7: les champs retournés par le backend sont sérialisés en camelCase JSON (cf. library-and-stack §6.bis.3) en miroir des noms TS frontend
- BR-8: les types SQL `time` (LundiDebut, LundiFin, etc.) sont sérialisés en JSON sous format `"HH:MM"` (24h, sans secondes ni TZ — les colonnes SQL sont locales TZ-naive)
- BR-9: les champs `decimal` SQL (`SalaireBaseBrut`, `NombreHeuresHebdo`, etc.) sont sérialisés en `number` JSON ; le formatage UI (séparateur décimal virgule, suffixe `€`, suffixe `h`) est de la responsabilité du frontend
- BR-10: les valeurs NULL backend sont sérialisées `null` JSON et affichées comme dash `—` côté UI (jamais `null` ou `undefined` visible utilisateur)
- BR-11: la photo bébé (`Contrat.ImageUrl`, nvarchar 20 cf. schema.md ligne 62) est un filename brut (ex. `"2.png"`, `"3.jpg"`) ; le frontend préfixe `/images/{filename}` pour reconstruire l'URL servie statiquement par `@fastify/static` (cf. spec-inscription BR-15 / spec-souscrire-contrat BR-18) — résolution canonique : `null|''` → asset défaut `/assets/default-baby-avatar.png` ; `"http(s)://..."` → URL absolue préservée ; `"/..."` → chemin déjà rooté préservé ; sinon `/images/{value}`. Si NULL (et fallback échoué), `BabyCard` utilise l'asset défaut ; pour la topbar `BebeDetailPage`/`RapportDuJourPage`, les initiales `{Prenom[0]}{Nom[0]}` en upper restent le fallback ultime
- BR-12: l'âge affiché en SFD-14 est calculé côté UI à partir de `Contrat.DateNaissance` et de la date du jour (mois si < 24 mois, années si ≥ 24 mois — ex. `14 mois`, `3 ans`)
- BR-13: la date de fin de période d'essai (SFD-16) est calculée côté UI : `Contrat.DateEffetContrat + Contrat.PeriodeEssaiDuree jours` (`PeriodeEssaiDuree` parsé comme entier ; si non parsable, afficher uniquement la durée sans la date)
- BR-14: le décodage de `Contrat.JourReposEmploye` (CSV `Lun,Mar,...` cf. spec-souscrire-contrat BR-14) en libellé long (`Dimanche`, `Samedi, Dimanche`) est de la responsabilité du frontend
- BR-15: l'estimation mensuelle nette affichée en SFD-17 est calculée côté UI selon la même formule que spec-souscrire-contrat SFD-29 (`round(NombreHeuresHebdo × SalaireBaseNet × 52 / 12, 2)`) ; cette valeur n'est **pas persistée** en base
- BR-16: le FAB unique de l'onglet `Informations` redirige vers la route RESTful `/contrats/{ContratId}` et ouvre le wizard par défaut sur la première étape (aucune sélection de section côté fiche — le wizard couvre les 5 étapes séquentiellement). La route `/contrats/nouveau` est strictement réservée à la création (aucun `?mode=edit`)
- BR-17: en mode edit (route `/contrats/{ContratId}`), le wizard `08-souscrire-contrat.html` exécute exclusivement des UPDATE — aucun INSERT, aucune duplication, aucune création de nouveau `ContratId` ou `EmployeurId`
- BR-18: le couple UPDATE `Employeur` + `Contrat` en mode edit (route `/contrats/{ContratId}`) s'exécute dans une **transaction SQL unique** ; échec du second → rollback intégral du premier (symétrique de la transaction INSERT de spec-souscrire-contrat BR-2)
- BR-19: les clauses WHERE des deux UPDATE incluent **systématiquement** un filtre de propriété : `Employeur.EmploierId = @SessionEmployeeId` ET `Contrat.EmployeeId = @SessionEmployeeId` — un appel direct manipulant `contratId` ne peut pas modifier un contrat d'un autre employé
- BR-20: si la session expire entre l'ouverture du wizard sur la route `/contrats/{ContratId}` et le clic sur `Enregistrer les modifications`, le backend retourne 401 et le frontend redirige vers `/login` (cf. spec-connexion) ; les valeurs saisies sont perdues — comportement assumé (cf. degraded mode)
- BR-21: les contraintes de longueur nvarchar (cf. spec-souscrire-contrat BR-4) restent applicables en mode edit (route `/contrats/{ContratId}`) ; un UPDATE qui dépasserait une longueur DB est rejeté par le backend (400 Bad Request)
- BR-22: les onglets `Rapport du jour` et `Rendez-vous` ne déclenchent **aucun appel backend** dans cette FEAT (ni au mount, ni sur clic) — toute interaction est purement visuelle / cosmétique
- BR-23: l'onglet `Informations` est **read-only** depuis cet écran ; toute modification passe obligatoirement par le wizard externe sur la route `/contrats/{ContratId}` (`08-souscrire-contrat.html` en mode edit) — aucune édition inline dans la fiche détaillée
- BR-24: aucune information technique (stack trace, identifiant interne, exception SQL) n'est exposée dans les messages d'erreur visibles à l'utilisateur (symétrique spec-souscrire-contrat BR-21)
- BR-25: si le design system actif fournit des composants équivalents (Tabs / TabPanel, Card, Avatar, IconButton, List/ListItem), ils DOIVENT être utilisés en priorité ; le CSS isolé ne complète que pour atteindre la fidélité visuelle de la maquette (`9-1-bebe-detaile.html`)
- BR-26: la navigation `Retour` topbar utilise le mécanisme SPA du framework actif (cf. spec-bebes BR-4) — l'usage de `<a href>` brut est interdit
- BR-27: la requête `GET /api/contrats/{ContratId}` retourne uniquement les champs listés dans la requête SQL canonique (SFD-12) — pas de `SELECT *` exposant des colonnes futures ajoutées au schéma (anti-leak)

## Acceptance Criteria
- AC-1: la page `/bebes/{ContratId}` est accessible depuis le clic sur une card bébé de `/bebes` (cf. spec-bebes AC-8 étendue) et n'est pas accessible sans session valide (redirection `/login` cf. spec-connexion)
- AC-2: un accès direct à `/bebes/{ContratId}` avec un `ContratId` n'appartenant pas à l'employé connecté retourne **404** (jamais 403) ; le frontend affiche une page "Bébé introuvable" avec un bouton `Retour aux bébés`
- AC-3: au chargement, la page envoie **une seule** requête backend `GET /api/contrats/{ContratId}` ; les onglets `Rapport du jour` et `Rendez-vous` ne déclenchent aucun appel additionnel (AC vérifiable côté Network DevTools)
- AC-4: la topbar affiche, dans l'ordre : flèche `Retour` (gauche), nom du bébé `{Prenom} {Nom}` (centre/gauche), avatar circulaire (droite) ; un clic sur la flèche `Retour` navigue en SPA vers `/bebes`
- AC-5: la barre des 3 onglets (`Informations`, `Rapport du jour`, `RDV`) est visible sous la topbar ; l'onglet `Informations` est actif par défaut au chargement
- AC-6: un clic sur un onglet change le contenu affiché sous la barre des tabs sans recharger la page ; le scroll vertical du conteneur de panneaux est remis à 0 à chaque switch
- AC-7: l'onglet `Informations` affiche 5 sections (cartes) empilées dans l'ordre : `Identité enfant`, `Parents`, `Contrat`, `Salaire`, `Horaires hebdomadaires` — **aucun `section-label`** n'est affiché entre les cartes (rendu épuré, séparation uniquement par l'espacement)
- AC-8: un **FAB unique** (circulaire coral-500, icône crayon `Edit`, ~54×54px, bas-droite du panneau) est affiché dans l'onglet `Informations` — aucun bouton `Modifier` per-section, aucun bouton `Modifier` dans la topbar
- AC-9: la section `Identité enfant` affiche les 6 lignes : Prénom, Nom, Naissance (avec âge calculé), Allergies (placeholder statique `Aucune connue`), Doudou (placeholder statique), Lieu d'accueil (Rue + CP/Ville sur deux lignes)
- AC-10: la section `Parents` affiche **une carte** par parent ; le schéma actuel ne supportant qu'un seul `EmployeurId` par `Contrat`, une seule carte est affichée intitulée selon `Employeur.LienParentale` (ex. `Mère — {Prénom} {Nom}`) avec les lignes Téléphone, Tél. pro. (si renseigné, sinon dash), Email, Adresse (Rue + CP/Ville)
- AC-11: les actions rapides de la carte Parent (`Appeler`, `SMS`, `Email`) utilisent des liens natifs `tel:`, `sms:`, `mailto:` (cliquables sur mobile)
- AC-12: la section `Contrat` affiche les lignes Début (date formatée), Période d'essai (durée + date de fin calculée), Familiarisation (texte libre), Jour(s) de repos (CSV décodé en libellé long), Pajemploi (en font-mono)
- AC-13: la section `Salaire` affiche les lignes Heures/sem., Brut (€/h en mono + suffixe majoré), Net (idem), Mensuel net (calculé UI, en gras coral)
- AC-14: la section `Horaires hebdomadaires` affiche 6 lignes Lun-Sam au format `HH:MM — HH:MM` ; les jours avec `{Jour}Debut`/`{Jour}Fin` NULL affichent `<small>Repos</small>` à la place du créneau
- AC-15: un clic sur le FAB unique de l'onglet `Informations` navigue en SPA vers `/contrats/{ContratId}` (route RESTful canonique edit, cf. SFD-21 — distincte de `/contrats/nouveau` réservée à la création) ; le wizard s'ouvre par défaut sur la première étape
- AC-16: au chargement du wizard sur la route `/contrats/{ContratId}` (mode edit), les 5 étapes sont pré-remplies avec les valeurs du contrat existant (Parents = `Employeur.*`, Enfant = `Contrat.{identité + lieu d'accueil + ImageUrl}`, Contrat = `Contrat.{dates + modalités + heures hebdo}`, Rémunération = `Contrat.{salaires}`, Horaires = `Contrat.{Lundi..Samedi}Debut/Fin`) ; **l'étape 2 affiche la photo bébé existante** (résolue via `/images/{ImageUrl}`) dans la zone d'aperçu, et le bouton bascule sur le libellé `+ Remplacer la photo` (au lieu de `+ Ajouter une photo`)
- AC-17: en mode edit (route `/contrats/{ContratId}`), le bouton final de l'étape 5 affiche `Enregistrer les modifications` (au lieu de `Enregistrer le contrat`)
- AC-18: un clic sur `Enregistrer les modifications` déclenche une requête backend unique (PUT/PATCH `/api/contrats/{ContratId}`) qui exécute deux UPDATE séquentiels dans une transaction unique : (1) `UPDATE Employeur SET ... WHERE EmployeurId = @EmployeurId AND EmploierId = @SessionEmployeeId` ; (2) `UPDATE Contrat SET ... WHERE ContratId = @ContratId AND EmployeeId = @SessionEmployeeId`
- AC-19: en cas d'échec du second UPDATE (`Contrat`), le premier UPDATE (`Employeur`) est intégralement rollbacké ; vérification : aucune modification partielle ne persiste en base après une tentative échouée
- AC-20: après succès complet du couple UPDATE, l'utilisateur est redirigé en SPA vers `/bebes/{ContratId}` (la fiche détaillée) et **non** vers `/bebes` ; la fiche est rechargée avec les valeurs à jour (cf. SFD-27)
- AC-21: un appel direct à l'endpoint UPDATE avec un `EmployeurId` ou `ContratId` n'appartenant pas à la session (manipulation manuelle) est ignoré : les filtres WHERE `EmploierId = @SessionEmployeeId` ET `EmployeeId = @SessionEmployeeId` rejettent silencieusement (0 ligne modifiée, retour 404)
- AC-22: en mode edit (route `/contrats/{ContratId}`), **aucun INSERT** n'est exécuté sur les tables `Contrat` ou `Employeur` (vérifiable par audit log SQL ou test d'intégration `SELECT COUNT(*)` avant/après save)
- AC-23: l'onglet `Rapport du jour` affiche une textarea pré-remplie avec un texte de démonstration en dur (cf. mockup), **sans** `section-label` ni titre `Rapport du jour`, **sans** bouton `Envoyer aux parents` (retiré — traité par une FEAT future) ; un **FAB unique** (icône crayon `Edit`, coral-500, bas-droite) pointant vers `07-rapport-du-jour.html` est affiché, cosmétique non fonctionnel — aucun appel backend
- AC-24: l'onglet `RDV` affiche une liste statique d'événements (sous-section `Passé` introduite par un séparateur `section-label`, **sans** `section-label` `Rendez-vous` en tête) avec un FAB `+` cosmétique non fonctionnel — aucun appel backend
- AC-25: pendant le chargement de la fiche (`GET /api/contrats/{ContratId}` en cours), un état de squelette/spinner est visible ; aucune donnée placeholder ne doit apparaître figée
- AC-26: si la photo bébé (`Contrat.ImageUrl`) est NULL, l'avatar topbar affiche les initiales `{Prenom[0]}{Nom[0]}` en upper (cf. BR-11) ; si non NULL, l'image est servie depuis la base statique du serveur
- AC-27: la requête SQL exécutée par le backend pour `GET /api/contrats/{ContratId}` est exactement celle de SFD-12 (paramétrée, `INNER JOIN`, double filtre PK + session) — vérifiable côté logs SQL ou test d'intégration
- AC-28: les contraintes de longueur nvarchar (cf. spec-souscrire-contrat BR-4) sont respectées en mode edit (route `/contrats/{ContratId}`) côté UI (maxlength sur les inputs préservés) ET côté backend (rejet 400 en cas de dépassement par manipulation directe)
- AC-29: la session expirée pendant l'édition (entre ouverture du wizard sur `/contrats/{ContratId}` et clic `Enregistrer`) déclenche un 401 backend et une redirection frontend vers `/login` ; les valeurs saisies sont perdues (comportement degraded mode assumé)

## Dependencies
- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employé connecté ; redirection vers `/login` en l'absence de session valide
- **spec-bebes** (`4-spec-bebes`) : le clic sur une card bébé de `/bebes` (AC-8 étendue dans cette FEAT) est la porte d'entrée vers `/bebes/{ContratId}` ; le retour topbar revient sur `/bebes`
- **spec-souscrire-contrat** (`6-spec-souscrire-contrat`) : **complétée** par cette FEAT pour ajouter la route RESTful edit `/contrats/{ContratId}` (couple UPDATE transactionnel via `PUT /api/contrats/{ContratId}`) en plus de la route création `/contrats/nouveau` actuelle (couple INSERT via `POST /api/contrats`) ; tous les écrans wizard + endpoints + règles métier BR-4 à BR-25 de spec-souscrire-contrat restent applicables
- **spec-inscription** (`3-spec-inscription`) : la base statique de stockage d'images (cf. spec-inscription FD-10) est réutilisée pour afficher la photo bébé via `Contrat.ImageUrl`
- **spec-menu-principale** (`5-spec-menu-principale`) : indirecte — l'accès à `/bebes` passe par le menu principal mais cette FEAT n'en dépend pas directement

## Functional Deliverables
- FD-1: écran `/bebes/{ContratId}` à 2 blocs (topbar fixe + conteneur 3 onglets) avec onglet `Informations` actif par défaut
- FD-2: endpoint backend `GET /api/contrats/{ContratId}` exécutant la requête SQL paramétrée canonique de SFD-12 (`INNER JOIN Contrat × Employeur`, filtres `ContratId` + `EmployeeId`), retournant un payload JSON agrégé `{ contrat: {...}, employeur: {...} }` ou 404 si non trouvé ou hors périmètre
- FD-3: topbar avec flèche `Retour` (navigation SPA vers `/bebes`), nom du bébé `{Prenom} {Nom}`, avatar circulaire avec photo `Contrat.ImageUrl` ou initiales si NULL
- FD-4: barre de 3 onglets (`Informations`, `Rapport du jour`, `RDV`) avec gestion d'état d'onglet actif côté UI (aucune persistance, aucun appel backend au switch)
- FD-5: onglet `Informations` — 5 sections (Identité enfant, Parents, Contrat, Salaire, Horaires hebdomadaires) restituant les données du payload backend, présentées sans `section-label` (rendu épuré) ; un FAB unique (icône crayon `Edit`, bas-droite) est rendu au-dessus du contenu
- FD-6: navigation SPA `/contrats/{ContratId}` déclenchée par le FAB unique de l'onglet `Informations` (wizard ouvre étape 1 par défaut)
- FD-7: **extension de spec-souscrire-contrat** — wizard `08-souscrire-contrat.html` accepte `mode=edit` : pré-remplissage complet des 5 étapes depuis `GET /api/contrats/{ContratId}`, bouton final renommé `Enregistrer les modifications`, save final remplaçant le couple INSERT par un **couple UPDATE transactionnel** (`Employeur` puis `Contrat`) avec rollback intégral en cas d'échec
- FD-8: endpoint backend `PUT /api/contrats/{ContratId}` (ou `PATCH`) exécutant les deux UPDATE séquentiels dans une transaction unique, scoped à `EmployeeId = session.EmployeeId` pour les deux clauses WHERE
- FD-9: redirection SPA vers `/bebes/{ContratId}` après succès du couple UPDATE (rechargement de la fiche détaillée avec valeurs à jour), conservation des valeurs saisies en cas d'échec backend (mêmes garanties que spec-souscrire-contrat AC-23)
- FD-10: onglet `Rapport du jour` — interface statique non interactive avec textarea pré-remplie en dur, sans `section-label` ni titre, sans bouton `Envoyer aux parents` (retiré), et FAB unique (icône crayon `Edit`, cible UI `07-rapport-du-jour.html`) cosmétique ; **aucun appel backend, aucune logique métier** (couvert par une FEAT future dédiée à la gestion des rapports incluant l'envoi SMS/Email aux parents)
- FD-11: onglet `RDV` — interface statique non interactive avec liste d'événements en dur (sans titre `Rendez-vous` en tête, sous-section `Passé` conservée) et FAB `+` cosmétique ; **aucun appel backend, aucune logique métier** (couvert par une FEAT future dédiée)
- FD-12: gestion des états de chargement (squelette/spinner pendant `GET`), des erreurs (404 → page "Bébé introuvable", autres → toast erreur générique), et des sessions expirées (401 → redirection `/login`)

## Out of Scope
- gestion d'un second parent / co-employeur (le schéma actuel ne supporte qu'un seul `EmployeurId` par `Contrat`) — extension future (potentielle table `ContratEmployeur` many-to-many)
- édition inline dans la fiche détaillée (toutes les modifications passent obligatoirement par le wizard `08-souscrire-contrat.html?mode=edit`)
- suppression / archivage / résiliation d'un contrat (spec future dédiée)
- duplication d'un contrat existant
- historique d'audit / journal des modifications du contrat ou de l'employeur (out of scope — spec future)
- onglet `Rapport du jour` — **logique métier complète** (génération du texte depuis les choix du jour, validation, persistance en base `dbo.Rapport`, **envoi SMS / Email aux parents** — explicitement retiré de l'UI de cette FEAT, gestion historique des rapports) — couvert par une FEAT future dédiée à la gestion des rapports
- onglet `RDV` — **logique métier complète** (CRUD événements, notifications, conflits de planning, synchronisation iCal/Google Calendar, gestion des autorisations parentales) — couvert par une FEAT future dédiée
- enregistrement partiel / brouillon d'édition de contrat entre les étapes du wizard `mode=edit` (pas de persistance intermédiaire — tout-ou-rien au save final, symétrique de spec-souscrire-contrat)
- gestion des allergies, doudou, particularités sanitaires du bébé (colonnes non présentes en schéma DB actuel — placeholder statique dans cette FEAT, extension future)
- récupération de l'adresse via API tierce (BAN, Google Places)
- notification email / SMS au parent après modification du contrat
- génération PDF d'avenant au contrat à l'issue de la modification
- workflow d'approbation / signature électronique de l'avenant
- gestion des avenants contractuels structurés (au-delà d'une simple modification des champs existants)
- multi-device / synchronisation temps réel des modifications entre deux sessions du même employé
- export / partage de la fiche bébé (PDF, lien public)
- rôles Admin et Parent (extensions futures — le Parent ne consulte pas sa propre fiche dans cette FEAT)
- fallback offline / cache local de la fiche détaillée pour consultation sans réseau
