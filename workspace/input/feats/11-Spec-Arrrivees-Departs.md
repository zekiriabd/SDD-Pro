# Spec: arrivees-departs

FEAT ID: 11-Spec-Arrrivees-Departs
Spec ID: spec-arrivees-departs
Status: Draft

> **Amendment post-mortem POC 2026-05-26** : la table `dbo.RapportJournee` préexistait en base avec un schéma différent de la version initiale de cette spec. Source de vérité = DB existante (cf. `docs/principles/source-first.md`). 2 DDL minimaux appliqués (`sp_rename HeureaArrivee → HeureArrivee` + `ALTER COLUMN HeureDepart time NULL`). Conséquences propagées : PK composite `(Date, ContratId)` au lieu de surrogate `RapportJourneeId`, types `time` au lieu de `datetime2`, payload `POST /arrivee` simplifié à `{ heureArrivee }` (drop `rapportJourneeId`), colonne `RapportSms nvarchar(500) NULL` documentée mais inutilisée par cette FEAT. Détails : `workspace/output/db/schema.diff.md`.

## Context
La page `/bebes` (cf. `spec-bebes`) affiche aujourd'hui la liste des bébés en garde pour l'employé connecté (filtre `Contrat.EmployeeId == session.EmployeeId`) avec image, nom + prénom et date de naissance. Aucune information opérationnelle sur la journée en cours n'est exposée : l'assistante maternelle ne peut ni savoir d'un coup d'œil qui est arrivé, qui est parti, qui n'est pas encore arrivé, ni enregistrer ces horaires depuis l'écran.

Cette spec **étend `spec-bebes`** en ajoutant à chaque card un **suivi minimal arrivée / départ** alimenté par la table `dbo.RapportJournee` (une ligne par couple `(ContratId, Date)`) jointe en LEFT JOIN à la requête de liste. La carte expose désormais deux horaires (`HeureArrivee`, `HeureDepart`, vides si absents) et **un bouton d'action unique** à deux états (`vert` → `rouge cliquable` → `rouge figé`) qui pilote un automate côté serveur : clic sur vert = INSERT d'une ligne `RapportJournee` avec heure d'arrivée serveur ; clic sur rouge = UPDATE de la ligne avec heure de départ serveur ; un troisième clic sur le bouton rouge figé est impossible (button disabled — la journée est verrouillée pour ce bébé).

Le mockup `workspace/input/ui/11-Spec-Arrrivees-Departs.html` matérialise la maquette canonique : topbar (menu + titre `Nounou Job` + loupe), entête `Mes bébés` + sous-titre date du jour + chip compteur présents, liste verticale de cards par bébé identique à `spec-bebes` enrichie de deux lignes horaires (`Arrivée HH:MM` / `Départ HH:MM`) et d'un **bouton d'action unique** (38×38 px) à trois rendus visuels : (1) vert plein avec icône `login` (flèche entrant) si pas encore arrivé, (2) rouge plein avec icône `logout` (flèche sortant) si arrivé mais non parti, (3) rouge plein opacité réduite + icône cadenas si arrivé et parti (non cliquable). Le bouton téléphone `Appel parents` est conservé visuellement (hors scope, cf. `spec-bebes` BR-7). Le chip statut (`Présent` / `Absent`) est supprimé : redondant avec l'état du bouton d'action.

## Objective
L'employé connecté visualise en un coup d'œil l'état d'arrivée et de départ de chaque bébé du jour depuis `/bebes`, et enregistre l'heure d'arrivée puis l'heure de départ d'un bébé en **deux clics maximum** sur un **bouton d'action unique** dont l'apparence (vert / rouge cliquable / rouge figé) reflète directement l'état persisté en base.

## Quantified Goal (v7.0.0 — anti-GIGO)
- Metric: temps de chargement de la liste enrichie (requête `Contrat LEFT JOIN RapportJournee` filtrée par `EmployeeId` et date du jour) + temps de réponse de chaque clic (INSERT arrivée ou UPDATE départ)
- Target: p95 chargement liste < 600 ms sur 4G simulé (1 requête SQL, payload < 8 KB JSON pour 10 bébés cumulés) ; p95 INSERT arrivée < 300 ms ; p95 UPDATE départ < 300 ms ; rafraîchissement visuel du bouton optimiste < 50 ms (état affiché immédiatement, rollback uniquement si l'API renvoie une erreur)
- Deadline: livraison stack `kotlin-spring-boot × react × shadcn` au 2026-07-30

## Non-Functional Constraints (v7.0.0)
- Expected volume: ~5 bébés / employé en garde simultanée, ~2 clics / bébé / jour ouvré (1 arrivée + 1 départ) ⇒ ~10 writes / employé / jour ; chargements potentiellement multiples (ouverture matin, milieu de journée, fin de journée) ⇒ ~5 chargements / employé / jour ouvré ; < 30k writes/jour total beta Demo
- Performance SLA: p95 chargement < 600 ms, p95 INSERT < 300 ms, p95 UPDATE < 300 ms (cf. Quantified Goal) ; pas de risque N+1 (LEFT JOIN unique, pas de boucle backend)
- Data retention: les lignes `dbo.RapportJournee` sont conservées indéfiniment côté schéma actuel (pas de purge automatique) ; l'historique reste interrogeable par `(ContratId, Date)` mais hors scope de cette FEAT
- Compliance: RGPD — `HeureArrivee` et `HeureDepart` sont des données opérationnelles non sensibles (pas de PII supplémentaire) ; visibles et modifiables uniquement par l'employé propriétaire du contrat (`Contrat.EmployeeId == session.EmployeeId`) ; jamais 403 (anti-énumération) — toujours 404 sur contrat hors périmètre
- Integration: extension de l'endpoint backend `GET /api/bebes` de `spec-bebes` (ajout des colonnes `heureArrivee`, `heureDepart` via LEFT JOIN `RapportJournee`) ; deux nouveaux endpoints `POST /api/contrats/{ContratId}/arrivee` (INSERT arrivée) et `POST /api/contrats/{ContratId}/depart` (UPDATE départ) ; aucun service externe ; aucun envoi SMS/Email/Push aux parents (out of scope)
- Degraded mode: si l'INSERT ou l'UPDATE échoue (500, timeout), le bouton revient à son état précédent (rollback optimiste) et un toast d'erreur générique s'affiche ; le rechargement de `/bebes` reste fonctionnel ; aucun cache local des horaires ; en cas de session expirée pendant un clic (401), redirection `/login`

## Actors
- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session. Seul autorisé à consulter la liste filtrée et à enregistrer arrivée/départ des contrats dont `Contrat.EmployeeId == session.EmployeeId`. Aucun accès à l'écran sans authentification.

## Functional Needs

### Point d'entrée et navigation
- SFD-1: La spec **étend `spec-bebes` (FEAT 4)** : l'écran `/bebes` est inchangé en terme de route, layout général, filtres et bouton `Ajouter un enfant` ; seul le rendu de chaque `baby-card` est enrichi (deux lignes horaires + bouton d'action unique) et la requête backend qui l'alimente est complétée par une LEFT JOIN à `dbo.RapportJournee`
- SFD-2: Aucun nouvel écran n'est introduit ; aucune route nouvelle n'est ajoutée ; le navigateur n'est jamais redirigé suite à un clic sur le bouton d'action (les transitions d'état sont locales et serveur-side, le rendu se met à jour sur place)

### Schéma de données — table `dbo.RapportJournee`
- SFD-3: La table `dbo.RapportJournee` porte le suivi journalier minimal arrivée / départ par contrat avec les colonnes (schéma DB post-DDL alignement POC 2026-05-26) :
  - `Date` (`DATE NOT NULL`) — partie 1 de la PK composite ; journée concernée, `CAST(getdate() AS DATE)` à l'INSERT
  - `ContratId` (`INT NOT NULL`, FK vers `dbo.Contrat.ContratId`) — partie 2 de la PK composite
  - `HeureArrivee` (`TIME NOT NULL`) — heure d'arrivée serveur via `CAST(getdate() AS TIME)`
  - `HeureDepart` (`TIME NULL`) — heure de départ serveur (NULL tant que pas parti)
  - `RapportSms` (`NVARCHAR(500) NULL`) — colonne historique, **non utilisée par cette FEAT** (réservée à un envoi SMS futur — out of scope)
  
  La **PK composite `(Date, ContratId)`** (contrainte `PK_RapportJournee` PRIMARY KEY CLUSTERED) garantit nativement qu'il n'existe **au plus** une ligne par bébé par jour (remplace l'UNIQUE séparé envisagé initialement — sémantique identique). La création / migration de la table elle-même est out of scope SDD (cf. `## Out of Scope`).
- SFD-4: Aucune autre colonne (note, statut, motif d'absence) n'est ajoutée à `RapportJournee` dans cette FEAT ; les extensions éventuelles (`Motif`, `NoteJour`, statut explicite `Absent`) sont laissées à des FEATs ultérieures

### Liste des bébés (`/bebes`) — requête enrichie
- SFD-5: La requête backend qui alimente la page `/bebes` est désormais (paramétrée, server-side) :
  ```sql
  SELECT
    c.ContratId,
    c.Prenom,
    c.Nom,
    c.DateNaissance,
    c.ImageUrl,
    r.RapportJourneeId,
    r.HeureArrivee,
    r.HeureDepart
  FROM dbo.Contrat c
  LEFT JOIN dbo.RapportJournee r
    ON r.ContratId = c.ContratId
   AND r.[Date]    = CAST(getdate() AS DATE)
  WHERE c.EmployeeId = @SessionEmployeeId
  ORDER BY c.Prenom ASC, c.Nom ASC;
  ```
  Le `LEFT JOIN` garantit qu'un bébé **sans** ligne `RapportJournee` pour aujourd'hui est **quand même** retourné, avec `HeureArrivee = NULL` et `HeureDepart = NULL` côté résultat (et `heureArrivee: null`, `heureDepart: null` côté JSON)
- SFD-6: La réponse JSON de l'endpoint backend `GET /api/bebes` est de la forme `[ { contratId, prenom, nom, dateNaissance, imageUrl, heureArrivee, heureDepart }, ... ]` ; les champs `heureArrivee` et `heureDepart` sont sérialisés `null` quand la valeur SQL est `NULL` (cf. BR-7) ou sous forme `"HH:MM"` (chaîne formatée 24h, fuseau serveur, sans secondes ni date) quand la valeur est non-nulle
- SFD-7: L'endpoint backend ne renvoie **jamais** d'objet `rapportJournee` imbriqué : les champs sont **aplatis** sur chaque bébé pour simplifier la consommation frontend et économiser le payload (le `RapportJourneeId` interne n'est pas exposé côté frontend — il est purement serveur)

### Card bébé — rendu enrichi
- SFD-8: Chaque `baby-card` continue d'afficher (cf. `spec-bebes`) l'avatar + nom + âge + date de naissance ; en complément, **deux nouvelles lignes** sont rendues sous le bloc identité :
  - Ligne `Arrivée` : pastille de couleur (verte si `heureArrivee` non-null, grise sinon) + libellé `Arrivée` + valeur `HH:MM` ou `--:--`
  - Ligne `Départ` : pastille de couleur (verte si `heureDepart` non-null, grise sinon) + libellé `Départ` + valeur `HH:MM` ou `--:--`
- SFD-9: Le **chip statut** (`Présente` / `Absent` / `En retard`) historiquement positionné en haut-droite de la card dans la maquette `spec-bebes` est **supprimé** dans cette spec : redondant avec l'état du bouton d'action (vert/rouge/rouge-figé) et avec les horaires affichés
- SFD-10: Le bouton `📞 Appeler les parents` est **conservé** visuellement sur la card par fidélité à `spec-bebes` BR-7 et reste **non câblé** dans cette FEAT (hors scope, comportement défini par une spec téléphonie ultérieure)

### Bouton d'action unique — état dérivé
- SFD-11: Chaque card affiche **un seul** bouton d'action principal (38×38 px, à gauche du bouton téléphone) dont l'apparence et le comportement sont **entièrement dérivés** des valeurs `heureArrivee` et `heureDepart` du payload backend :
  - **État A — "à arriver"** : `heureArrivee = null` ET `heureDepart = null` → bouton **vert plein** (`background: var(--nj-success)`), icône `login` blanche (flèche entrant dans une boîte), cliquable, `aria-label="Marquer l'arrivée"`
  - **État B — "présent"** : `heureArrivee != null` ET `heureDepart = null` → bouton **rouge plein** (`background: var(--nj-danger)`), icône `logout` blanche (flèche sortant d'une boîte), cliquable, `aria-label="Marquer le départ"`
  - **État C — "parti"** : `heureArrivee != null` ET `heureDepart != null` → bouton **rouge plein** opacité réduite (`opacity: 0.55`, `cursor: not-allowed`), icône `lock` blanche (cadenas), **non cliquable** (`disabled`), `aria-label="Journée terminée"`
- SFD-12: L'état théorique `heureArrivee = null` ET `heureDepart != null` est **impossible** côté backend par construction (le départ est un UPDATE de la ligne créée par l'arrivée — cf. SFD-15) ; si le frontend reçoit ce couple anomalique (corruption manuelle de la base, bug serveur), il l'affiche comme **État C** (rouge figé) par sécurité et logue une alerte console (la cohérence est restaurée au prochain chargement après correction DBA)
- SFD-13: Aucun bouton "grisé / pas encore arrivé" séparé n'est rendu (décision design — le user a explicitement écarté un troisième état visuel gris pour ne garder que **vert clic → rouge clic → rouge figé** et éviter la confusion entre "non arrivé" et "absent excusé")

### Clic sur le bouton — automate serveur-side
- SFD-14: Un clic sur le bouton en **État A — vert** déclenche un appel `POST /api/contrats/{ContratId}/arrivee` (body vide — la date et l'heure sont **toujours** générées côté serveur, BR-5 anti-tampering) qui exécute :
  ```sql
  INSERT INTO dbo.RapportJournee ([Date], ContratId, HeureArrivee, HeureDepart)
  VALUES (CAST(getdate() AS DATE), @ContratId, CAST(getdate() AS TIME), NULL);
  ```
  Réponse `201 Created` avec body JSON `{ heureArrivee: "HH:MM" }` ; le frontend met à jour la card immédiatement (le bouton passe en État B rouge, la ligne `Arrivée` affiche la valeur reçue) sans rechargement complet de la liste. La clé naturelle de la ligne créée est `(Date=today, ContratId)` — déjà connue du frontend, donc aucun identifiant supplémentaire n'est renvoyé dans le payload.
- SFD-15: Un clic sur le bouton en **État B — rouge cliquable** déclenche un appel `POST /api/contrats/{ContratId}/depart` (body vide) qui exécute :
  ```sql
  UPDATE dbo.RapportJournee
     SET HeureDepart = CAST(getdate() AS TIME)
   WHERE ContratId = @ContratId
     AND [Date]    = CAST(getdate() AS DATE)
     AND HeureDepart IS NULL;
  ```
  La clause `AND HeureDepart IS NULL` rend l'UPDATE **idempotent vers le bas** : si le départ a déjà été enregistré (suite à un double-clic ou un appel concurrent), l'UPDATE matche 0 ligne et le backend retourne 409 (cf. SFD-17). Réponse `200 OK` avec body JSON `{ heureDepart: "HH:MM" }` quand 1 ligne mise à jour ; le frontend met à jour la card immédiatement (le bouton passe en État C rouge figé, la ligne `Départ` affiche la valeur reçue)
- SFD-16: Un clic sur le bouton en **État C — rouge figé** est impossible (attribut HTML `disabled`) ; aucun appel backend n'est envoyé ; le bouton reste inerte pour garantir qu'on ne peut pas dépasser un cycle arrivée + départ par bébé par jour
- SFD-17: Si l'utilisateur tente malgré tout d'envoyer un `POST .../arrivee` alors qu'une ligne existe déjà (manipulation manuelle, double-clic optimiste sur état stale, race condition multi-onglets), le backend renvoie `409 Conflict` avec body JSON `{ code: "ALREADY_ARRIVED", heureArrivee: "HH:MM" }` ; idem `POST .../depart` retourne `409 Conflict` `{ code: "ALREADY_DEPARTED" | "NOT_ARRIVED" }` quand l'UPDATE matche 0 ligne. Le frontend réconcilie l'état affiché avec la réponse (force re-fetch ciblé de la card concernée) et affiche un toast `Action déjà enregistrée — vue rafraîchie.`

### Mise à jour optimiste côté frontend
- SFD-18: Au clic sur le bouton vert (État A), le frontend **anticipe** la transition vers État B : le bouton est désactivé pendant la requête (spinner inline 14px à la place de l'icône `login`) ; en cas de succès (201), la transition est confirmée et l'heure reçue est affichée ; en cas d'erreur (500, timeout), le bouton revient en État A, un toast `Échec de l'enregistrement de l'arrivée. Réessayez.` s'affiche, aucune ligne `Arrivée` n'est mise à jour
- SFD-19: Au clic sur le bouton rouge cliquable (État B), même logique : spinner pendant l'UPDATE, transition vers État C en cas de succès (200), rollback vers État B en cas d'erreur avec toast `Échec de l'enregistrement du départ. Réessayez.`
- SFD-20: Aucun double-clic ne déclenche deux requêtes : le bouton est `disabled` dès le premier clic et reste `disabled` jusqu'à la résolution (succès ou erreur) de la requête en cours

### États de chargement et erreur
- SFD-21: Pendant le chargement initial de `/bebes` (GET en cours), un état de squelette/spinner est visible à l'emplacement de la liste (comportement hérité de `spec-bebes` AC-3, non modifié par cette FEAT)
- SFD-22: Si l'employé n'a aucun bébé assigné (réponse vide du GET), le message hérité `Aucun enfant assigné` reste affiché (cf. `spec-bebes` AC-7) ; la table `RapportJournee` n'est jamais interrogée pour rien
- SFD-23: En cas d'échec du GET (500, timeout), le rendu hérité de `spec-bebes` est conservé (pas de comportement nouveau introduit par cette FEAT pour le chargement initial)
- SFD-24: En cas de session expirée pendant un clic (401 sur POST arrivée ou POST départ), le frontend redirige vers `/login` (cf. `spec-connexion`) ; aucune ligne n'est insérée / mise à jour

## Business Rules
- BR-1: l'endpoint `GET /api/bebes` retourne **uniquement** les contrats dont `Contrat.EmployeeId == session.EmployeeId` (filtrage côté serveur, hérité de `spec-bebes` BR-1 et BR-2) ; aucune donnée d'un autre employé n'est exposée
- BR-2: les endpoints `POST /api/contrats/{ContratId}/arrivee` et `POST /api/contrats/{ContratId}/depart` vérifient **avant** toute modification que `Contrat.EmployeeId == session.EmployeeId` ; sinon **404 Not Found** (anti-énumération — jamais 403) et **aucune** modification base
- BR-3: `@SessionEmployeeId` provient exclusivement de la variable singleton de session ; aucun paramètre de requête (header custom, body, query param) ne peut le surcharger (symétrique `spec-bebes` BR-3)
- BR-4: la **date** utilisée pour la jointure `RapportJournee` et pour l'INSERT/UPDATE est **toujours** `CAST(getdate() AS DATE)` côté serveur (date du serveur, locale TZ-naive serveur) ; aucun paramètre `date` côté query / body ne peut la surcharger (anti-tampering — empêche un client d'enregistrer une arrivée pour un jour passé)
- BR-5: les **horaires** `HeureArrivee` et `HeureDepart` sont **toujours** `getdate()` côté serveur (timestamp serveur au moment de l'INSERT / UPDATE) ; aucun paramètre `heureArrivee` / `heureDepart` côté body ne peut les surcharger (anti-tampering — l'employé ne peut pas falsifier les horaires)
- BR-6: les requêtes SQL sont **paramétrées** (`@ContratId`, `@SessionEmployeeId`) ; aucune concaténation de chaîne (anti-injection SQL — symétrique `spec-bebe-detaille` BR-6)
- BR-7: le LEFT JOIN sur `RapportJournee` garantit qu'un bébé **sans** ligne du jour est retourné quand même avec `HeureArrivee = NULL`, `HeureDepart = NULL` ; le frontend interprète `null` comme "pas encore enregistré" et rend l'état correspondant du bouton (cf. SFD-11)
- BR-8: la **PK composite `(Date, ContratId)`** sur `RapportJournee` garantit nativement l'unicité d'une ligne par bébé par jour ; un INSERT en doublon déclenche une violation de contrainte PK (SQL Server error 2627) mappée par le backend en `409 Conflict { code: "ALREADY_ARRIVED" }` (cf. SFD-17) — jamais une exception 500 brute exposée à l'utilisateur
- BR-9: l'UPDATE départ utilise une clause `AND HeureDepart IS NULL` qui rend l'opération idempotente vers le bas : un double-clic ou un appel concurrent matche 0 ligne au second appel, mappé en `409 Conflict { code: "ALREADY_DEPARTED" }` (cf. SFD-17) — jamais d'écrasement silencieux d'une heure de départ déjà enregistrée
- BR-10: les transitions d'état du bouton sont **strictement linéaires** : État A (vert) → État B (rouge cliquable) → État C (rouge figé) ; aucune transition arrière (rouge figé → rouge cliquable, ou rouge cliquable → vert) n'est exposée côté UI dans cette FEAT ; une correction d'erreur (mauvais clic, départ enregistré par erreur) relève d'une **FEAT ultérieure dédiée** (modification manuelle horaires par admin / employé — out of scope)
- BR-11: le frontend ne stocke **aucune** valeur `heureArrivee` / `heureDepart` côté client en dehors de l'état React local de la liste courante ; chaque rechargement de la page `/bebes` re-déclenche le GET et reflète l'état persisté en base (pas de cache local stale)
- BR-12: les champs JSON renvoyés par le backend sont sérialisés en **camelCase** (cf. `library-and-stack §6.bis.3`) : `contratId`, `prenom`, `nom`, `dateNaissance`, `imageUrl`, `heureArrivee`, `heureDepart`, `rapportJourneeId` ; aucune sérialisation en PascalCase ou snake_case
- BR-13: les valeurs `NULL` backend sont sérialisées **`null`** JSON (jamais omises, jamais chaîne `"null"`, jamais chaîne vide `""`) — la distinction `null` vs `"08:42"` est sémantique côté frontend
- BR-14: le format des heures retournées est **`HH:MM`** (chaîne 24h, ex. `"08:42"`, `"18:05"`) ; aucune seconde, aucun fuseau, aucune date dans la chaîne — la séparation date/heure est gérée côté serveur via le type SQL `DATETIME2` qui sépare logiquement les deux composants côté API
- BR-15: aucune information technique (stack trace, exception SQL, identifiant `RapportJourneeId` interne, message ORM) n'est exposée dans les réponses d'erreur côté API ; le frontend affiche uniquement des toasts génériques (`Échec de l'enregistrement de l'arrivée. Réessayez.`, etc.)
- BR-16: la navigation déclenchée par le bouton `Ajouter un enfant` (hérité de `spec-bebes`) ou le clic chevron sur une card (vers fiche détaillée bébé `spec-bebe-detaille`) est inchangée par cette FEAT (le clic sur le bouton d'action arrivée/départ est **scoped** au bouton lui-même via `stopPropagation` côté frontend — il ne déclenche **jamais** la navigation vers la fiche bébé)
- BR-17: si le design system actif (shadcn / Vuetify / Radzen) fournit un composant `Button` avec gestion d'état `loading` et `disabled`, il DOIT être utilisé en priorité pour le bouton d'action (cf. `spec-bebes` BR-5) ; le CSS isolé ne complète que pour la fidélité visuelle des couleurs `--nj-success` / `--nj-danger`

## Acceptance Criteria
- AC-1: la page `/bebes` (héritée de `spec-bebes`) est inchangée en terme de route, layout, filtres et bouton `Ajouter un enfant` ; seul le rendu de chaque card est enrichi conformément à SFD-8 / SFD-11
- AC-2: au chargement, la page envoie **une seule** requête `GET /api/bebes` qui retourne la liste enrichie `[ { contratId, prenom, nom, dateNaissance, imageUrl, heureArrivee, heureDepart }, ... ]` ; aucune requête additionnelle n'est émise pour récupérer les horaires (vérifiable côté Network DevTools — anti N+1)
- AC-3: la requête SQL exécutée est exactement celle de SFD-5 (paramétrée, `Contrat LEFT JOIN RapportJournee ON ContratId AND Date = CAST(getdate() AS DATE)`, filtre WHERE `EmployeeId = @SessionEmployeeId`, `ORDER BY Prenom, Nom`) — vérifiable côté logs SQL ou test d'intégration
- AC-4: un bébé sans ligne `RapportJournee` pour aujourd'hui apparaît **quand même** dans la réponse avec `heureArrivee: null` et `heureDepart: null` (test d'intégration : insérer un `Contrat` sans `RapportJournee` correspondante → le GET retourne le bébé avec horaires null)
- AC-5: chaque card affiche, en plus du contenu hérité de `spec-bebes`, **deux lignes** `Arrivée HH:MM | --:--` et `Départ HH:MM | --:--` (la valeur est `--:--` quand le champ est null, sinon la valeur formatée `HH:MM`)
- AC-6: chaque card affiche **un seul** bouton d'action principal (38×38 px) dont l'apparence reflète l'état dérivé du couple `(heureArrivee, heureDepart)` selon le mapping SFD-11 :
  - `(null, null)` → bouton vert + icône `login` + cliquable
  - `(non-null, null)` → bouton rouge + icône `logout` + cliquable
  - `(non-null, non-null)` → bouton rouge opacité 0.55 + icône `lock` + non cliquable (HTML `disabled`)
- AC-7: le chip statut `Présente` / `Absent` / `En retard` (présent dans la maquette historique `spec-bebes` `4-Spec-Bebes.html`) est **supprimé** dans le rendu des cards de cette FEAT (vérifiable visuellement et côté DOM — aucun élément `.baby-card__chip` rendu)
- AC-8: le bouton téléphone (📞) est conservé visuellement à droite du bouton d'action principal mais **non câblé** (cf. SFD-10, hérité de `spec-bebes` BR-7) ; un clic ne déclenche **aucune** action
- AC-9: un clic sur le bouton vert (État A) envoie un `POST /api/contrats/{ContratId}/arrivee` avec body vide ; aucun query param `date` ou `heure` n'est jamais émis par le frontend (la valeur serveur fait foi, cf. BR-4, BR-5)
- AC-10: le backend, sur réception du `POST .../arrivee`, vérifie `Contrat.EmployeeId == session.EmployeeId` ; sinon **404 Not Found** et aucune ligne insérée (vérifiable par test d'intégration : appeler le POST avec un `ContratId` d'un autre employé → 404 ; `SELECT COUNT(*) FROM RapportJournee WHERE ContratId = X AND Date = today` = 0 après l'appel)
- AC-11: le backend, sur succès du `POST .../arrivee`, exécute un `INSERT INTO RapportJournee ([Date], ContratId, HeureArrivee, HeureDepart) VALUES (CAST(getdate() AS DATE), @ContratId, CAST(getdate() AS TIME), NULL)` et retourne **201 Created** avec body `{ heureArrivee: "HH:MM" }`
- AC-12: en cas d'INSERT en doublon (ligne déjà existante pour `(Date, ContratId)` du jour), la violation de la **PK composite `PK_RapportJournee`** est mappée par le backend en **409 Conflict** avec body `{ code: "ALREADY_ARRIVED", heureArrivee: "HH:MM" }` (vérifiable par test d'intégration : appeler le POST deux fois de suite → premier appel 201, second appel 409). Le catch côté repository couvre Prisma `P2002` ET `P2010` avec `meta.code ∈ {'2627', '2601'}` (SQL Server PK / UNIQUE violation respectivement)
- AC-13: le frontend, sur 201, met à jour immédiatement la card concernée : le bouton passe en État B (rouge cliquable + icône `logout`), la ligne `Arrivée` affiche la valeur `HH:MM` reçue ; aucun rechargement complet de la liste n'est effectué
- AC-14: le frontend, sur 409 (`ALREADY_ARRIVED`), affiche un toast `Action déjà enregistrée — vue rafraîchie.` et met à jour la card en utilisant la `heureArrivee` reçue (réconciliation optimiste)
- AC-15: un clic sur le bouton rouge cliquable (État B) envoie un `POST /api/contrats/{ContratId}/depart` avec body vide
- AC-16: le backend, sur succès du `POST .../depart`, exécute un `UPDATE RapportJournee SET HeureDepart = getdate() WHERE ContratId = @ContratId AND Date = CAST(getdate() AS DATE) AND HeureDepart IS NULL` et retourne **200 OK** avec body `{ heureDepart: "HH:MM" }`
- AC-17: si l'UPDATE matche 0 ligne (départ déjà enregistré OU pas encore arrivé), le backend retourne **409 Conflict** avec body `{ code: "ALREADY_DEPARTED" }` (si une ligne existe mais `HeureDepart != NULL`) ou `{ code: "NOT_ARRIVED" }` (si aucune ligne `(ContratId, Date)` du jour n'existe) ; aucune modification base
- AC-18: le frontend, sur 200, met à jour immédiatement la card : le bouton passe en État C (rouge figé, opacité 0.55, icône `lock`, HTML `disabled`), la ligne `Départ` affiche la valeur `HH:MM` reçue
- AC-19: le bouton en État C (rouge figé) porte l'attribut HTML `disabled` et l'attribut CSS `pointer-events: none` ; un clic ne déclenche aucune requête réseau (vérifiable côté Network DevTools)
- AC-20: pendant l'envoi d'un `POST .../arrivee` ou `POST .../depart`, le bouton concerné est désactivé et un spinner inline 14px remplace l'icône `login` ou `logout` (anti double-submit) ; un re-clic n'envoie aucune nouvelle requête
- AC-21: en cas d'échec serveur (500, timeout) sur `POST .../arrivee`, le bouton revient en État A (vert), un toast `Échec de l'enregistrement de l'arrivée. Réessayez.` est affiché, aucune ligne `Arrivée` n'est mise à jour côté UI
- AC-22: en cas d'échec serveur (500, timeout) sur `POST .../depart`, le bouton revient en État B (rouge cliquable), un toast `Échec de l'enregistrement du départ. Réessayez.` est affiché, aucune ligne `Départ` n'est mise à jour côté UI
- AC-23: le clic sur le bouton d'action principal **n'entraîne pas** la navigation vers la fiche détaillée du bébé (`spec-bebe-detaille`) ; `stopPropagation` est appliqué côté frontend pour scoper l'évènement au bouton uniquement (vérifiable : cliquer sur le bouton → reste sur `/bebes`, cliquer sur le chevron / corps de la card → navigation vers `/bebes/{ContratId}`)
- AC-24: un appel direct à `POST /api/contrats/{ContratId}/arrivee` ou `.../depart` avec un `ContratId` d'un autre employé (manipulation manuelle) retourne **404 Not Found** ; aucune modification en base (vérifiable par test d'intégration)
- AC-25: les horaires retournés par tous les endpoints (`GET /api/bebes`, `POST .../arrivee`, `POST .../depart`) sont formatés exactement **`HH:MM`** (24h, sans secondes, sans date, sans fuseau) — vérifiable par test d'intégration (`assertMatches "^\\d{2}:\\d{2}$" body.heureArrivee`)
- AC-26: la session expirée pendant un clic (401 sur l'un des POST) déclenche une redirection frontend vers `/login` (cf. `spec-connexion`) ; aucune ligne n'est insérée / mise à jour en base
- AC-27: la spec **étend `spec-bebes` (FEAT 4)** sans la casser : tous les AC d'origine de `spec-bebes` restent satisfaits (route, layout, filtres, ajout enfant, navigation chevron) — la seule régression visuelle est la suppression du chip statut (cf. AC-7) qui est intentionnelle et documentée

## Dependencies
- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employé connecté ; redirection vers `/login` en l'absence de session valide ou en cas de 401 sur un POST
- **spec-bebes** (`4-spec-bebes`) : **étendue** par cette FEAT — la requête backend de la liste des bébés est complétée par un LEFT JOIN sur `RapportJournee` (cf. SFD-5) ; le rendu de chaque card est enrichi (deux lignes horaires + bouton d'action unique) tout en conservant le layout général, les filtres et le bouton `Ajouter un enfant` ; le chip statut est supprimé (cf. AC-7)
- **spec-bebe-detaille** (`9-spec-bebe-detaille`) : indirecte — un clic sur le corps de la card / chevron continue de naviguer vers la fiche détaillée bébé ; le bouton d'action arrivée/départ ne déclenche **jamais** cette navigation (cf. AC-23)
- **dbo.RapportJournee** (table SQL) : prérequis schéma supposé créé en base par un script DBA séparé (création/migration de la table elle-même hors scope de cette FEAT côté SDD)

## Functional Deliverables
- FD-1: extension de l'endpoint backend `GET /api/bebes` (hérité de `spec-bebes`) — la requête SQL canonique est complétée par un `LEFT JOIN dbo.RapportJournee r ON r.ContratId = c.ContratId AND r.Date = CAST(getdate() AS DATE)` (cf. SFD-5) ; la réponse JSON aplatit `heureArrivee` et `heureDepart` sur chaque bébé (cf. SFD-6)
- FD-2: nouvel endpoint backend `POST /api/contrats/{ContratId}/arrivee` exécutant un INSERT dans `dbo.RapportJournee` avec `Date = CAST(getdate() AS DATE)`, `HeureArrivee = CAST(getdate() AS TIME)`, `HeureDepart = NULL` (cf. SFD-14, BR-4, BR-5) ; retour **201** + `{ heureArrivee }` ou **404** (hors périmètre) ou **409** (`ALREADY_ARRIVED`)
- FD-3: nouvel endpoint backend `POST /api/contrats/{ContratId}/depart` exécutant un UPDATE conditionnel (`HeureDepart IS NULL`) sur `dbo.RapportJournee` avec `HeureDepart = CAST(getdate() AS TIME)` (cf. SFD-15, BR-9) ; retour **200** + `{ heureDepart }` ou **404** (hors périmètre) ou **409** (`ALREADY_DEPARTED` ou `NOT_ARRIVED`)
- FD-4: rendu de chaque `baby-card` enrichi de deux lignes horaires `Arrivée HH:MM | --:--` et `Départ HH:MM | --:--` (cf. SFD-8) ; suppression du chip statut historique (cf. SFD-9, AC-7)
- FD-5: bouton d'action unique 38×38 px à trois états visuels (vert clic / rouge clic / rouge figé) dont l'apparence est dérivée du couple `(heureArrivee, heureDepart)` (cf. SFD-11) ; transitions optimistes au clic avec rollback si l'API échoue (cf. SFD-18, SFD-19, AC-21, AC-22)
- FD-6: gestion d'état React local de la liste enrichie avec mise à jour ciblée d'une seule card au succès POST (sans rechargement complet de la liste) ; spinner inline pendant la requête + anti double-submit via attribut `disabled` (cf. SFD-20, AC-20)
- FD-7: réconciliation optimiste sur conflit 409 (`ALREADY_ARRIVED` / `ALREADY_DEPARTED` / `NOT_ARRIVED`) — la card est rafraîchie avec les valeurs serveur et un toast informatif est affiché (cf. SFD-17, AC-14)
- FD-8: maquette `workspace/input/ui/11-Spec-Arrrivees-Departs.html` matérialisant les **trois états visuels** du bouton (vert / rouge cliquable / rouge figé) sur trois cards d'exemple distinctes (une par état) afin de fournir une référence visuelle non-ambiguë à dev-frontend
- FD-9: `stopPropagation` côté frontend sur le bouton d'action pour empêcher la navigation vers la fiche détaillée bébé (cf. AC-23) lorsque l'utilisateur clique sur le bouton ; le reste de la card reste cliquable pour la navigation chevron (héritée de `spec-bebes`)

## Out of Scope
- **création / migration de la table `dbo.RapportJournee`** elle-même : la table est supposée préexistante en base ou créée par un script DBA séparé (DDL non géré par cette FEAT côté SDD)
- **correction manuelle d'un horaire enregistré par erreur** (mauvais clic, départ avant l'arrivée réelle) — relève d'une FEAT ultérieure dédiée (modification admin / employé avec audit log)
- **bouton "Annuler l'arrivée" / "Annuler le départ"** côté UI — aucune transition arrière n'est exposée dans cette FEAT (cf. BR-10)
- **état "absent excusé"** distinct (rendu visuel séparé pour un bébé prévu absent du jour) — pas d'attribut `Motif` ou statut explicite dans `RapportJournee` ; la card affiche simplement l'état "à arriver" (bouton vert) tant qu'aucune ligne du jour n'existe
- **multi-arrivées par jour** (départ matin → arrivée midi → départ soir) : la contrainte `UNIQUE (ContratId, Date)` et l'automate État A → B → C **interdit explicitement** cette flexibilité dans cette FEAT
- **notification au parent** (SMS / Email / Push) sur arrivée ou départ — FEAT future dédiée
- **historique des horaires** (consultation des journées passées par bébé) — la page `/bebes` n'expose que la journée du jour ; l'historique relèverait d'un écran dédié type calendrier ou liste paginée (FEAT future)
- **modification du **lien parent ↔ enfant** ou des informations bébé** — hors scope (cf. `spec-bebes` Out of Scope)
- **comportement du bouton téléphone 📞** (lien `tel:` ou page contact) — reste cosmétique non câblé (cf. `spec-bebes` BR-7)
- **filtrage / tri / recherche** dans la liste enrichie (par exemple "afficher uniquement les bébés non encore arrivés") — hors scope ; la liste reste triée par `Prenom, Nom`
- **pagination** de la liste — hors scope (cf. `spec-bebes` Out of Scope)
- **synchronisation temps réel** multi-onglets / multi-appareils (WebSocket, SSE, polling) — un re-chargement manuel de la page reflète l'état persisté
- **export PDF / CSV** des journées
- **statistiques agrégées** (taux de retard, durée moyenne de garde par bébé) — FEAT future dédiée
- **fallback offline** / cache local des clics si la connexion est perdue
- **rôles Admin / Parent** (extensions futures — un Parent qui consulterait l'historique des horaires de son enfant relève d'une FEAT dédiée)
- **séparation des heures et minutes en deux champs distincts** côté UI ou côté schéma — le format `HH:MM` est suffisant et stable pour cette FEAT
