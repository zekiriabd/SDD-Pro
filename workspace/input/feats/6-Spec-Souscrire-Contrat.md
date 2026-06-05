# Spec: souscrire-contrat

Status: Draft
Spec ID: spec-souscrire-contrat

## Context
Une assistante maternelle (employé connecté) doit pouvoir souscrire un nouveau contrat de garde — c'est-à-dire enregistrer en base un parent employeur (`Employeur`) **et** l'enfant accueilli sous contrat (`Contrat`) — depuis son espace Demo. Aucun écran de création de contrat n'existe aujourd'hui : le bouton "Ajouter un enfant" exposé en bas de la liste `/bebes` (cf. spec-bebes AC-9) doit aboutir sur cet écran.

Cette spec décrit la page `/contrats/nouveau` (alias `/bebes/nouveau`) sous forme d'**assistant multi-étapes (wizard) à 5 pages** synchronisées par un stepper, avec navigation `Suivant` / `Précédent`. Les 5 étapes correspondent à : (1) Parents, (2) Enfant, (3) Contrat, (4) Rémunération, (5) Horaires. Aucune persistance partielle entre les étapes : la totalité du contrat est enregistrée en **un seul clic final** sur "Enregistrer le contrat", déclenchant deux INSERT successifs (d'abord `Employeur`, puis `Contrat` avec l'`EmployeurId` retourné) dans la même transaction.

La page est personnalisée selon l'`EmployeeId` de l'assistante maternelle connectée : l'employeur créé est attaché à cet `EmployeeId` (colonne `Employeur.EmploierId`), et le contrat le lie également (colonne `Contrat.EmployeeId`). L'adresse d'accueil de l'enfant est pré-remplie en étape 2 depuis l'adresse de l'employé connecté (cf. spec-inscription), avec possibilité de modification (l'enfant peut être gardé ailleurs qu'au domicile principal).

## Objective
L'employé connecté saisit en 5 étapes guidées l'ensemble des informations du parent employeur, du bébé accueilli et du contrat de garde (dates, durée, jour(s) de repos, rémunération, horaires de la semaine), puis enregistre le tout en un seul appel backend. Après succès, l'utilisateur est redirigé vers `/bebes` où le nouvel enfant apparaît dans la liste. Aucun écran intermédiaire n'est nécessaire ; aucun brouillon n'est conservé.

## Actors
- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session. Aucun accès à la page sans authentification.

## Functional Needs

### Navigation et entrée dans le wizard
- SFD-1: L'utilisateur accède à la page `/contrats/nouveau` depuis le bouton "Ajouter un enfant" situé en fin de liste `/bebes` (cf. spec-bebes AC-9) — la navigation est SPA (`NavigationManager.NavigateTo()` ou équivalent stack)
- SFD-2: Au chargement de la page, l'étape 1 (Parents) est affichée et le stepper indique `ÉTAPE 1/5` ; le bouton `Précédent` est masqué tant que l'utilisateur est sur l'étape 1
- SFD-3: Le bouton `Suivant` fait avancer d'une étape (1 → 2 → 3 → 4 → 5) ; sur l'étape 5, le libellé devient `Enregistrer le contrat` et l'icône change
- SFD-4: Le bouton `Précédent` (visible à partir de l'étape 2) recule d'une étape sans perdre les valeurs saisies dans les étapes ultérieures déjà visitées
- SFD-5: Un clic sur un nœud du stepper navigue directement vers l'étape correspondante sans perte de saisie ; cette navigation est autorisée même vers une étape non encore validée
- SFD-6: Le bouton `Retour` (flèche en haut à gauche de la topbar) quitte le wizard et navigue vers `/bebes` — un dialogue de confirmation prévient l'utilisateur que la saisie en cours sera perdue dès lors qu'au moins un champ a été renseigné
- SFD-7: Aucune persistance partielle (brouillon) entre les étapes : tant que l'utilisateur ne clique pas sur `Enregistrer le contrat`, aucun appel backend de création n'est émis

### Étape 1 — Parents (Employeur)
- SFD-8: L'étape 1 affiche les champs d'identité du parent : `Prénom` (`Prenom`, nvarchar 25), `Nom` (`Nom`, nvarchar 25), `Lien parental` (`LienParentale`, nvarchar 15) — sélecteur avec valeurs `Mère`, `Père`, `Tuteur légal`, `Autre`
- SFD-9: L'étape 1 affiche les champs d'adresse du parent : `Rue` (`Rue`, nvarchar 200), `Code postal` (`CodePostal`, nvarchar 10), `Ville` (`Ville`, nvarchar 50)
- SFD-10: L'étape 1 affiche les champs de contact : `Téléphone personnel` (`TelPersonnel`, nvarchar 20, obligatoire), `Téléphone personnel 2` (`TelPersonnel2`, nvarchar 20, optionnel), `Téléphone professionnel` (`TelProfessionnel`, nvarchar 20, optionnel), `Email` (`Email`, nvarchar 50, obligatoire)
- SFD-11: L'étape 1 affiche le champ `Numéro Pajemploi` (`NumeroPajemploi`, nvarchar 25, optionnel) précédé d'un message informatif rappelant que ce numéro est attribué par l'URSSAF lors de la première déclaration d'employeur

### Étape 2 — Enfant (Contrat — identité + lieu d'accueil)
- SFD-12: L'étape 2 affiche un composant d'**upload de photo de l'enfant** acceptant les fichiers JPG ou PNG, taille maximale 5 Mo ; le fichier est conservé côté client (état formulaire) jusqu'au clic final sur `Enregistrer le contrat` — aucun upload immédiat n'est effectué
- SFD-13: L'étape 2 affiche les champs d'identité du bébé : `Prénom` (`Prenom`, nvarchar 100), `Nom` (`Nom`, nvarchar 100), `Date de naissance` (`DateNaissance`, date)
- SFD-14: L'étape 2 affiche la section `Lieu d'accueil` (adresse où l'enfant sera gardé) avec les champs : `Rue` (`AccueilRue`, nvarchar 255), `Code postal` (`AccueilCodePostal`, nvarchar 10), `Ville` (`AccueilVille`, nvarchar 100)
- SFD-15: À l'ouverture de l'étape 2 pour la **première fois** dans une session de wizard, les trois champs `Lieu d'accueil` (`AccueilRue`, `AccueilCodePostal`, `AccueilVille`) sont **pré-remplis automatiquement** depuis l'adresse de l'employé connecté (`Employee.Rue`, `Employee.CodePostal`, `Employee.Ville` du profil session, cf. spec-inscription)
- SFD-16: Le pré-remplissage SFD-15 est **modifiable** : l'utilisateur peut écraser n'importe lequel des trois champs (cas usage : garde au domicile des parents ou dans un autre lieu) ; les valeurs modifiées sont conservées en l'état lors d'un retour ultérieur sur l'étape 2 dans la même session de wizard
- SFD-17: Si l'employé connecté n'a aucune adresse renseignée dans son profil (`Employee.Rue` ou `Employee.CodePostal` ou `Employee.Ville` NULL ou vide), les champs `Lieu d'accueil` restent vides et l'utilisateur doit les renseigner manuellement

### Étape 3 — Contrat (dates, modalités, temps de travail, particularités)
- SFD-18: L'étape 3 affiche la section `Dates clés` avec les champs : `Date d'effet du contrat` (`DateEffetContrat`, date), `Période d'essai — durée` (`PeriodeEssaiDuree`, nvarchar 50 — saisie numérique en jours dans l'UI, suffixe `jours`), `Début période` (`PeriodeEssaiDateDebut`, date)
- SFD-19: L'étape 3 affiche la section `Familiarisation` avec un champ textarea `Modalités de familiarisation` (`ModalitesFamiliarisation`, nvarchar 800)
- SFD-20: L'étape 3 affiche la section `Temps de travail` avec : `Nombre d'heures hebdomadaires` (`NombreHeuresHebdo`, decimal(18,2) — saisie numérique en heures, suffixe `h / semaine`) ; ce champ est saisi **manuellement** par l'utilisateur (n'est pas calculé automatiquement à partir des horaires de l'étape 5)
- SFD-21: L'étape 3 affiche un sélecteur **multi-sélection** `Jour de repos hebdomadaire` (`JourReposEmploye`, nvarchar 50) sous forme de chips cliquables pour les 7 jours de la semaine (`Lun`, `Mar`, `Mer`, `Jeu`, `Ven`, `Sam`, `Dim`)
- SFD-22: La multi-sélection des jours de repos permet de sélectionner **zéro, un ou plusieurs** jours (cas extrême : aucun jour de repos coché si l'assistante maternelle travaille toute la semaine ; cas usuel : un ou deux jours, ex. `Sam` + `Dim`)
- SFD-23: Les jours de repos sélectionnés sont sérialisés en CSV ordonné selon l'ordre canonique de la semaine (`Lun,Mar,Mer,Jeu,Ven,Sam,Dim`) pour stockage dans la colonne `JourReposEmploye` ; exemple : sélection Samedi + Dimanche → stocké `Sam,Dim`
- SFD-24: L'étape 3 affiche la section `Particularités` avec trois textareas optionnels : `Particularités du planning` (`ParticularitesPlanning`, nvarchar max), `Autres particularités` (`AutresParticularites`, nvarchar max), `Si horaires non précisés, comment ?` (`HorairesNonPrecisesComment`, nvarchar max)

### Étape 4 — Rémunération (salaire de base + heures majorées)
- SFD-25: L'étape 4 affiche la carte `Salaire de base` (badge `HORAIRE`) avec deux champs en ligne : `Brut` (`SalaireBaseBrut`, decimal(18,2), suffixe `€ / h`), `Net` (`SalaireBaseNet`, decimal(18,2), suffixe `€ / h`)
- SFD-26: L'étape 4 affiche la carte `Heures majorées` (badge `AU-DELÀ DE 45H` informationnel) avec : `Taux de majoration` (`MajorationPourcentage`, decimal(5,2), suffixe `%`), `Brut majoré` (`SalaireMajoreBrut`, decimal(18,2), suffixe `€ / h`), `Net majoré` (`SalaireMajoreNet`, decimal(18,2), suffixe `€ / h`)
- SFD-27: Le `Brut majoré` et le `Net majoré` sont **pré-calculés automatiquement** côté UI dès qu'un `Brut` / `Net` de base et un `Taux de majoration` sont renseignés : `SalaireMajoreBrut = round(SalaireBaseBrut × (1 + MajorationPourcentage/100), 2)` et `SalaireMajoreNet = round(SalaireBaseNet × (1 + MajorationPourcentage/100), 2)`
- SFD-28: Les champs `Brut majoré` et `Net majoré` restent **éditables manuellement** : un utilisateur peut écraser la valeur calculée par une valeur saisie (cas usage : taux non linéaire, arrondi conventionnel) ; la valeur saisie remplace définitivement le calcul automatique tant que l'utilisateur ne modifie pas `MajorationPourcentage` ou les valeurs de base
- SFD-29: Une `Estimation mensuelle nette` informative est affichée au bas de la carte `Heures majorées` selon la formule indicative `round((NombreHeuresHebdo × SalaireBaseNet) × 52 / 12, 2)` (basée sur 52 semaines) ; cette valeur n'est **pas persistée** en base — purement indicative pour aider la saisie

### Étape 5 — Horaires hebdomadaires
- SFD-30: L'étape 5 affiche une matrice horaire pour les 6 jours de la semaine ouvrés/semi-ouvrés (`Lundi`, `Mardi`, `Mercredi`, `Jeudi`, `Vendredi`, `Samedi`) avec deux champs `time` par jour : heure de début et heure de fin
- SFD-31: Les 12 champs horaires correspondent strictement aux colonnes : `LundiDebut` / `LundiFin`, `MardiDebut` / `MardiFin`, `MercrediDebut` / `MercrediFin`, `JeudiDebut` / `JeudiFin`, `VendrediDebut` / `VendrediFin`, `SamediDebut` / `SamediFin` (type SQL `time(7)`)
- SFD-32: Le dimanche **n'apparaît pas** dans la matrice horaire (par convention le dimanche n'est jamais travaillé dans le schéma — pas de colonne `DimancheDebut` / `DimancheFin` en base)
- SFD-33: Les jours sélectionnés comme `Jour de repos hebdomadaire` à l'étape 3 (SFD-21) sont affichés en **état désactivé / dashed** dans la matrice de l'étape 5 (style `is-rest` du mockup), et leurs champs horaires sont vides et non saisissables ; les valeurs NULL correspondantes sont enregistrées en base
- SFD-34: Un récapitulatif `Total hebdomadaire` est calculé côté UI au bas de la matrice : somme des amplitudes (`Fin - Début`) sur les jours non-repos ; ce total est **informatif** et n'est **pas persisté** (le champ persisté est `NombreHeuresHebdo` saisi manuellement à l'étape 3)
- SFD-35: Aucune cohérence n'est imposée entre le `NombreHeuresHebdo` (étape 3, manuel) et le total calculé à l'étape 5 — un éventuel écart informatif peut être signalé visuellement (badge "écart Xh") mais ne bloque pas l'enregistrement

### Enregistrement final
- SFD-36: Sur l'étape 5, le bouton `Suivant` devient `Enregistrer le contrat` (style bouton de sauvegarde, ex. dégradé sage)
- SFD-37: Un clic sur `Enregistrer le contrat` déclenche un appel unique au backend qui exécute, dans une **transaction SQL unique**, deux INSERT séquentiels : (1) `INSERT INTO Employeur` avec `EmploierId = session.EmployeeId`, retournant l'`EmployeurId` auto-incrémenté ; (2) `INSERT INTO Contrat` avec `EmployeeId = session.EmployeeId` et `EmployeurId = <id retourné en (1)>`
- SFD-38: En cas d'échec de l'un des deux INSERT, la transaction est **intégralement rollbackée** — aucun `Employeur` orphelin ne reste en base sans son `Contrat` associé
- SFD-39: Si une photo de bébé a été sélectionnée à l'étape 2 (SFD-12), elle est uploadée au backend dans le même appel (ou dans un appel immédiatement consécutif après succès du INSERT Contrat), stockée dans le répertoire statique du serveur (cf. spec-inscription FD-10), et seul le nom de fichier est inscrit dans `Contrat.ImageUrl` (nvarchar 20 — pattern court, ex. `{ContratId}.jpg` ou `{guid8}.png`)
- SFD-40: Le bouton `Enregistrer le contrat` est désactivé pendant le traitement pour empêcher toute double-soumission
- SFD-41: Après succès complet (INSERT Employeur + INSERT Contrat + upload image éventuel), l'utilisateur est redirigé en SPA vers `/bebes` et le nouvel enfant apparaît dans la liste filtrée par son `EmployeeId` (cf. spec-bebes AC-2)
- SFD-42: En cas d'échec backend (erreur réseau, contrainte violée, transaction rollback), l'utilisateur reste sur l'étape 5 avec un message d'erreur générique et l'intégralité des données saisies est conservée — aucune perte silencieuse de saisie

## Business Rules
- BR-1: l'`EmployeeId` utilisé pour `Employeur.EmploierId` ET pour `Contrat.EmployeeId` provient exclusivement de la variable singleton de session de l'employé connecté ; aucun paramètre de requête utilisateur ne peut le surcharger
- BR-2: les deux INSERT (`Employeur` puis `Contrat`) sont exécutés dans une **transaction unique** côté backend ; un échec sur le second INSERT rollback le premier — pas de `Employeur` orphelin sans `Contrat`
- BR-3: l'`EmployeurId` utilisé pour `Contrat.EmployeurId` est le `SCOPE_IDENTITY()` (ou équivalent ORM tel que `INSERT ... OUTPUT INSERTED.Id`) retourné par le INSERT `Employeur` ; aucun ID utilisateur fourni
- BR-4: les longueurs des champs respectent les contraintes nvarchar du schéma DB : `Employeur.Nom`, `Employeur.Prenom` ≤ 25 ; `Employeur.Rue` ≤ 200 ; `Employeur.CodePostal` ≤ 10 ; `Employeur.Ville` ≤ 50 ; `Employeur.LienParentale` ≤ 15 ; `Employeur.TelPersonnel`, `TelPersonnel2`, `TelProfessionnel` ≤ 20 ; `Employeur.Email` ≤ 50 ; `Employeur.NumeroPajemploi` ≤ 25 ; `Contrat.Nom`, `Contrat.Prenom` ≤ 100 ; `Contrat.AccueilRue` ≤ 255 ; `Contrat.AccueilCodePostal` ≤ 10 ; `Contrat.AccueilVille` ≤ 100 ; `Contrat.PeriodeEssaiDuree` ≤ 50 ; `Contrat.ModalitesFamiliarisation` ≤ 800 ; `Contrat.JourReposEmploye` ≤ 50 ; `Contrat.ImageUrl` ≤ 20
- BR-5: les champs obligatoires pour enregistrement sont : `Employeur` → `Nom`, `Prenom`, `LienParentale`, `Rue`, `CodePostal`, `Ville`, `TelPersonnel`, `Email` ; `Contrat` → `Nom`, `Prenom`, `DateNaissance`, `AccueilRue`, `AccueilCodePostal`, `AccueilVille`, `DateEffetContrat`, `NombreHeuresHebdo`, `SalaireBaseBrut`, `SalaireBaseNet`
- BR-6: les champs optionnels (`TelPersonnel2`, `TelProfessionnel`, `NumeroPajemploi`, `PeriodeEssaiDuree`, `PeriodeEssaiDateDebut`, `ModalitesFamiliarisation`, `JourReposEmploye`, `ParticularitesPlanning`, `AutresParticularites`, `HorairesNonPrecisesComment`, `MajorationPourcentage`, `SalaireMajoreBrut`, `SalaireMajoreNet`, `ImageUrl`, et les colonnes horaires des jours marqués comme repos) sont stockés NULL si non renseignés
- BR-7: l'`Email` du parent (`Employeur.Email`) doit respecter une forme RFC-5322 minimale (validation UI + backend) ; aucun contrôle de duplication n'est imposé (un même email parent peut être employeur de plusieurs assistantes maternelles)
- BR-8: les téléphones (`Employeur.TelPersonnel`, `TelPersonnel2`, `TelProfessionnel`) sont stockés tels quels sans normalisation de format ; le caractère obligatoire de `TelPersonnel` est imposé côté UI ET backend
- BR-9: la `DateNaissance` du bébé doit être antérieure ou égale à la date du jour (validation UI + backend)
- BR-10: la `DateEffetContrat` doit être supérieure ou égale à la `DateNaissance` du bébé (validation backend)
- BR-11: `NombreHeuresHebdo`, `SalaireBaseBrut`, `SalaireBaseNet` sont strictement positifs (`> 0`) ; `MajorationPourcentage` est ≥ 0 (peut être nul si pas d'heures majorées)
- BR-12: pour chaque jour de la semaine (Lun-Sam), si `{Jour}Debut` est renseigné alors `{Jour}Fin` doit l'être également ET `{Jour}Fin > {Jour}Debut` (validation backend) ; le couple (Debut, Fin) est soit entièrement NULL (jour non travaillé / repos), soit entièrement renseigné et cohérent
- BR-13: les jours marqués comme repos dans `JourReposEmploye` doivent avoir leurs colonnes `{Jour}Debut` / `{Jour}Fin` à NULL (le backend rejette toute incohérence : repos déclaré ET horaires renseignés pour le même jour)
- BR-14: la sérialisation de `JourReposEmploye` suit l'ordre canonique `Lun,Mar,Mer,Jeu,Ven,Sam,Dim` séparé par virgules sans espaces (ex. `Sam,Dim`, `Dim`, chaîne vide ou NULL si aucun jour de repos)
- BR-15: l'upload de photo bébé (SFD-12) accepte uniquement les types MIME `image/jpeg` et `image/png` et les extensions `.jpg`, `.jpeg`, `.png` ; tout autre format est rejeté côté UI ET côté backend
- BR-16: la taille maximale d'une photo bébé est de **5 Mo** ; au-delà, l'upload est rejeté côté UI avant envoi et défensivement côté backend
- BR-17: le nom du fichier image stocké dans le répertoire statique est **renommé de manière déterministe** par le backend pour respecter la contrainte `ImageUrl ≤ 20 caractères` et éviter collisions / injection de path ; pattern recommandé : `{ContratId}.{ext}` (ex. `42.png`) — généré après obtention de l'`Id` du `Contrat` inséré
- BR-18: la colonne `Contrat.ImageUrl` stocke uniquement le **nom du fichier** (ex. `42.png`), pas le chemin complet ; le frontend reconstruit l'URL d'affichage en préfixant `/images/{filename}` (servi statiquement par `@fastify/static` ou équivalent stack, cf. spec-inscription BR-15) — résolution canonique appliquée par tous les composants consommateurs (`BabyCard`, `BebeDetailPage` topbar, `RapportDuJourPage` topbar, `StepEnfant` aperçu edit) : `null|''` → asset défaut `/assets/default-baby-avatar.png` ; `"http(s)://..."` → URL absolue préservée ; `"/..."` → chemin déjà rooté préservé ; sinon `/images/{value}`
- BR-19: en cas d'échec de l'upload image (après succès des deux INSERT), l'opération globale est considérée comme un **succès partiel** : `Contrat.ImageUrl` reste NULL, un message d'avertissement non bloquant est affiché à l'utilisateur, et la redirection vers `/bebes` a lieu normalement — l'utilisateur pourra téléverser l'image plus tard (spec future, hors scope)
- BR-20: l'`EmployeurId` retourné par le INSERT `Employeur` est utilisé **strictement** pour le INSERT `Contrat` immédiatement consécutif dans la même transaction ; il n'est jamais exposé au client ni retourné dans la réponse HTTP
- BR-21: aucune information technique (stack trace, identifiant interne, exception SQL) n'est exposée dans les messages d'erreur visibles à l'utilisateur
- BR-22: la navigation entre les étapes du wizard (Suivant, Précédent, clic sur stepper) ne déclenche **aucun appel backend** ; seul le bouton final `Enregistrer le contrat` produit le couple INSERT
- BR-23: la validation client par étape (champs obligatoires) bloque le clic `Suivant` si un champ obligatoire de l'étape courante est vide ; un message d'erreur inline par champ manquant est affiché
- BR-24: aucun rendu / saisie possible pour un utilisateur non connecté ; la redirection vers `/login` en l'absence de session valide est gérée par spec-connexion
- BR-25: si le design system actif fournit des composants équivalents (Stepper / Wizard, TextField, NumberField, DatePicker, TimePicker, MultiSelectChip, FileUpload, Card), ils DOIVENT être utilisés en priorité ; le CSS isolé ne complète que pour atteindre la fidélité visuelle de la maquette (`4-2-Spec-Souscrire-Contrat.html`)

## Acceptance Criteria
- AC-1: la page `/contrats/nouveau` (ou `/bebes/nouveau`) est accessible depuis le bouton "Ajouter un enfant" de `/bebes` (cf. spec-bebes AC-9) et n'est pas accessible sans session valide
- AC-2: au chargement, l'étape 1 (Parents) est affichée, le stepper indique `ÉTAPE 1/5`, et le bouton `Précédent` n'est pas visible
- AC-3: l'étape 1 affiche les 11 champs Parent : Prénom, Nom, Lien parental (select), Rue, Code postal, Ville, Tél personnel, Tél personnel 2, Tél professionnel, Email, Numéro Pajemploi
- AC-4: un clic sur `Suivant` en étape 1 avec un champ obligatoire vide (Nom, Prénom, Lien parental, Rue, Code postal, Ville, Tél personnel, Email) affiche un message d'erreur inline et **ne change pas d'étape**
- AC-5: l'étape 2 (Enfant) affiche le composant d'upload photo (JPG/PNG ≤ 5 Mo), les champs Prénom/Nom/Date de naissance du bébé, et la section Lieu d'accueil (Rue/CP/Ville)
- AC-6: à la première ouverture de l'étape 2 dans la session du wizard, les champs `AccueilRue`, `AccueilCodePostal`, `AccueilVille` sont **pré-remplis** depuis l'adresse de l'employé connecté (cf. SFD-15) ; l'utilisateur peut modifier librement ces valeurs et celles-ci sont conservées en cas de retour ultérieur sur l'étape
- AC-7: l'étape 2 conserve les valeurs saisies à l'étape 1 (un retour `Précédent` puis `Suivant` ne réinitialise pas l'étape 1)
- AC-8: l'étape 3 (Contrat) affiche les sections Dates clés, Familiarisation, Temps de travail (avec le multi-sélecteur de jours de repos sous forme de chips), Particularités
- AC-9: le sélecteur `Jour de repos hebdomadaire` permet de cocher **plusieurs** chips simultanément (cas attendu : zéro, un ou plusieurs jours) ; les jours sélectionnés sont stockés en CSV ordonné `Lun,Mar,Mer,Jeu,Ven,Sam,Dim` (cf. BR-14)
- AC-10: l'étape 4 (Rémunération) affiche les deux cartes Salaire de base et Heures majorées avec les champs Brut/Net (base) et Taux/Brut majoré/Net majoré
- AC-11: en étape 4, dès que `SalaireBaseBrut`, `SalaireBaseNet` et `MajorationPourcentage` sont renseignés, les champs `SalaireMajoreBrut` et `SalaireMajoreNet` sont pré-calculés automatiquement (cf. SFD-27) ; l'utilisateur peut écraser ces valeurs calculées
- AC-12: l'étape 5 (Horaires) affiche une matrice de 6 lignes (Lundi à Samedi) avec heure début + heure fin par jour ; le dimanche n'apparaît pas
- AC-13: les jours sélectionnés à l'étape 3 comme jours de repos apparaissent en étape 5 en état désactivé/dashed avec champs horaires vides et non saisissables (cf. SFD-33)
- AC-14: un récapitulatif `Total hebdomadaire` est affiché au bas de la matrice étape 5, calculé en temps réel à partir des amplitudes (Fin - Début) des jours travaillés ; ce total n'est pas persisté
- AC-15: sur l'étape 5, le bouton `Suivant` est remplacé par `Enregistrer le contrat` avec un style de bouton de sauvegarde distinctif
- AC-16: un clic sur `Enregistrer le contrat` avec tous les champs obligatoires renseignés (cf. BR-5) déclenche un appel backend unique exécutant deux INSERT séquentiels dans une transaction unique : (1) `INSERT INTO Employeur ... VALUES (..., session.EmployeeId)` puis (2) `INSERT INTO Contrat ... VALUES (session.EmployeeId, <EmployeurId retourné>, ...)`
- AC-17: en cas d'échec du second INSERT (`Contrat`), le premier INSERT (`Employeur`) est **intégralement rollbacké** ; vérification : la table `Employeur` ne contient pas d'enregistrement orphelin sans `Contrat` lié après une tentative échouée
- AC-18: après succès complet, l'utilisateur est redirigé en SPA vers `/bebes` et le nouvel enfant créé apparaît dans la liste filtrée par son `EmployeeId` (cf. spec-bebes AC-2)
- AC-19: une photo bébé uploadée et acceptée (JPG/PNG ≤ 5 Mo) est stockée dans le répertoire statique du serveur (cf. spec-inscription FD-10) avec un nom déterministe ≤ 20 caractères (pattern `{ContratId}.{ext}`), et ce nom est inscrit dans `Contrat.ImageUrl`
- AC-20: un upload de fichier non JPG/PNG (ex. `.gif`, `.svg`, `.webp`) est rejeté côté UI avec un message explicite et n'est pas envoyé au backend
- AC-21: un upload de fichier > 5 Mo est rejeté côté UI avec un message explicite et n'est pas envoyé au backend
- AC-22: un échec d'upload image après succès des deux INSERT laisse `Contrat.ImageUrl` à NULL, affiche un avertissement non bloquant, et redirige vers `/bebes` normalement (cf. BR-19)
- AC-23: un échec backend lors du couple INSERT (réseau, contrainte violée, rollback) maintient l'utilisateur sur l'étape 5 avec un message d'erreur générique et **l'intégralité des données saisies dans les 5 étapes est conservée** (aucune perte)
- AC-24: le bouton `Enregistrer le contrat` est désactivé pendant le traitement pour empêcher toute double-soumission
- AC-25: un appel direct au endpoint backend avec un `EmployeeId` différent de celui de la session (manipulation manuelle de la requête) est ignoré : le backend force `EmployeeId = session.EmployeeId` pour les colonnes `Employeur.EmploierId` ET `Contrat.EmployeeId`
- AC-26: un clic sur la flèche `Retour` de la topbar avec au moins un champ saisi affiche un dialogue de confirmation avant la navigation vers `/bebes` ; sans champ saisi, la navigation est immédiate
- AC-27: un clic sur un nœud du stepper navigue directement vers l'étape correspondante sans perte de saisie dans les autres étapes
- AC-28: les contraintes de longueur nvarchar (cf. BR-4) sont respectées côté UI (maxlength sur les inputs) ET côté backend (rejet 400 Bad Request en cas de dépassement par manipulation directe)

## Dependencies
- **spec-connexion** : `EmployeeId` provient de la variable singleton de session de l'employé connecté ; redirection vers `/login` en l'absence de session valide
- **spec-inscription** : l'adresse de l'employé connecté (`Employee.Rue`, `Employee.CodePostal`, `Employee.Ville`) est lue depuis le profil créé/complété par spec-inscription pour le pré-remplissage du Lieu d'accueil (SFD-15) ; le répertoire statique de stockage d'images (cf. spec-inscription FD-10) est réutilisé pour les photos bébé
- **spec-bebes** : le bouton "Ajouter un enfant" de `/bebes` (AC-9) est la porte d'entrée de cette spec ; après succès, la redirection vers `/bebes` permet de visualiser le nouveau contrat dans la liste filtrée par `EmployeeId`
- **spec-menu-principale** : indirecte — l'accès à `/bebes` passe par le menu principal mais cette spec n'en dépend pas directement

## Functional Deliverables
- FD-1: écran wizard `/contrats/nouveau` à 5 étapes synchronisées par un stepper (Parents → Enfant → Contrat → Rémunération → Horaires) avec navigation Suivant/Précédent et clic direct sur les nœuds du stepper
- FD-2: étape 1 (Parents) — formulaire de saisie des 11 champs `Employeur` (identité, lien parental, adresse, contacts, Pajemploi) avec validation des champs obligatoires
- FD-3: étape 2 (Enfant) — formulaire de saisie identité bébé + composant d'upload photo (JPG/PNG ≤ 5 Mo, conservation client jusqu'au save) + section Lieu d'accueil **pré-remplie automatiquement** depuis l'adresse de l'employé connecté et **modifiable**
- FD-4: étape 3 (Contrat) — formulaire de saisie dates contrat / période d'essai / modalités familiarisation / nombre d'heures hebdo / **multi-sélecteur de jours de repos** (chips, 0-7 jours) / particularités
- FD-5: étape 4 (Rémunération) — deux cartes Salaire de base + Heures majorées avec **pré-calcul automatique** des salaires majorés (Brut majoré, Net majoré) et estimation mensuelle nette informative
- FD-6: étape 5 (Horaires) — matrice horaire 6 jours (Lun-Sam) avec champs heure début/fin par jour, **désactivation visuelle des jours de repos** sélectionnés à l'étape 3, et total hebdomadaire calculé en temps réel (non persisté)
- FD-7: endpoint backend `POST /api/contrats` (ou équivalent) recevant un payload unique `{ employeur: {...}, contrat: {...}, image?: <multipart> }`, exécutant deux INSERT SQL séquentiels (`Employeur` puis `Contrat`) dans une **transaction unique**, scoped à `EmployeeId = session.EmployeeId` (cf. BR-1, BR-2)
- FD-8: rollback intégral de la transaction en cas d'échec de l'un des deux INSERT (cf. BR-2, AC-17)
- FD-9: gestion du fichier image bébé : upload, validation type MIME + taille, stockage dans `wwwroot/images/` (ou équivalent stack) sous nom déterministe ≤ 20 caractères (cf. BR-17), inscription du nom dans `Contrat.ImageUrl`, succès partiel toléré si upload échoue (cf. BR-19)
- FD-10: redirection SPA vers `/bebes` après succès (cf. AC-18) et conservation intégrale des données saisies en cas d'échec (cf. AC-23)
- FD-11: dialogue de confirmation au clic sur la flèche `Retour` de la topbar lorsque des champs ont été saisis (cf. AC-26)
- FD-12: validation UI par étape bloquant l'avancement (`Suivant`) si un champ obligatoire est vide, avec message d'erreur inline (cf. BR-23, AC-4)
- FD-13: validation backend exhaustive du payload (longueurs nvarchar, formats date/email, contraintes métier BR-9 à BR-14, cohérence horaires/repos) avec retour 400 Bad Request en cas d'erreur

## Out of Scope
- édition d'un contrat existant (cette spec couvre la création uniquement)
- suppression / archivage / fin de contrat
- duplication d'un contrat existant
- gestion multi-parents (un second `Employeur` lié au même `Contrat`) — le schéma actuel ne supporte qu'un seul `EmployeurId` par `Contrat`
- enregistrement partiel / brouillon d'un contrat entre les étapes du wizard (pas de persistance intermédiaire — tout-ou-rien au save final)
- import en masse de contrats
- remplacement / suppression de la photo bébé après création — couvert par une spec future
- redimensionnement / compression / génération de thumbnails automatique de la photo bébé après upload
- formats d'image autres que JPG et PNG (GIF, WebP, SVG, HEIC…) pour la photo bébé
- récupération de l'adresse de l'enfant via API tierce (BAN, Google Places)
- validation métier avancée des téléphones (format E.164, vérification HLR), du Numéro Pajemploi (validation URSSAF), du code postal vs ville
- calcul automatique réglementaire des salaires majorés (taux conventionnel par convention collective des assistants maternels) — l'utilisateur saisit les valeurs ou s'appuie sur le pré-calcul UI simple (cf. SFD-27) qui reste éditable
- gestion du dimanche travaillé (le schéma DB ne dispose pas de colonnes `DimancheDebut` / `DimancheFin`)
- gestion d'horaires multiples sur une même journée (matin + après-midi distincts) — le schéma ne supporte qu'un seul couple Début/Fin par jour
- notification email / SMS au parent après création du contrat
- génération PDF du contrat à l'issue de la création
- workflow d'approbation / signature électronique du contrat
- gestion des avenants au contrat
- rôles Admin et Parent (extensions futures)
