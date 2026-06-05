# Spec: rapport-du-jour

FEAT ID: 10-rapport-du-jour
Spec ID: spec-rapport-du-jour
Status: Draft

## Context
La fiche détaillée d'un bébé `/bebes/{ContratId}` (cf. `spec-bebe-detaille`) expose aujourd'hui un onglet `Rapport du jour` purement statique : une textarea pré-remplie en dur et un bouton `Envoyer aux parents` non fonctionnel (cf. spec-bebe-detaille SFD-30, FD-10). Aucune logique métier n'existe : ni saisie structurée des observations du jour, ni persistance en base, ni affichage des choix existants.

Cette spec décrit l'écran fonctionnel `/bebes/{ContratId}/rapport` qui matérialise la **saisie du rapport quotidien** sous forme d'un **stepper 4 étapes** (Santé → Nourriture → Activité → Humeur). Chaque étape affiche une grille de cases à cocher (action = libellé + icône Material Symbols) issues de `dbo.Action` filtrées par `IdCategorie`. L'assistante maternelle coche les actions effectivement réalisées dans la journée pour le bébé sélectionné, navigue d'étape en étape via stepper, puis enregistre. Le save **purge** l'intégralité des lignes `dbo.Rapport` du couple `(ContratId, Date=aujourd'hui)` puis **insère** une nouvelle ligne par case cochée (`Valeur = '1'`). Les cases non cochées ne sont **pas** persistées — leur absence (LEFT JOIN sans match) sert de marqueur "non coché" au prochain chargement.

L'écran est accessible exclusivement depuis l'onglet `Rapport du jour` de la fiche détaillée bébé : la spec **étend `spec-bebe-detaille` SFD-30** en rendant fonctionnel le bouton `Modifier` (jusqu'ici cosmétique) du `section-label` Rapport du jour. Le clic navigue en SPA vers `/bebes/{ContratId}/rapport`. Le bouton `Envoyer aux parents` reste cosmétique non fonctionnel dans cette FEAT — l'envoi notifié aux parents (SMS / Email / génération texte agrégé) sera traité dans une FEAT ultérieure dédiée.

Le mockup `workspace/input/ui/10-Spec-rapport-du-jour.html` matérialise la maquette canonique : topbar (retour + nom bébé + avatar), stepper 4 nœuds avec barre de progression coral, body scrollable contenant 4 sections `step` (une seule active à la fois, animation slideIn), grille `cell` 2 colonnes par catégorie avec icône + libellé + pastille de check coral, footer `Précédent` + `Suivant`, dernière étape : bouton `Suivant` muté en `Enregistrer le rapport` (gradient sage).

## Objective
L'employé connecté ouvre la fiche détaillée d'un bébé (`/bebes/{ContratId}`), bascule sur l'onglet `Rapport du jour`, clique sur le bouton `Modifier` qui ouvre `/bebes/{ContratId}/rapport`, navigue dans un stepper 4 étapes (Santé, Nourriture, Activité, Humeur) où chaque étape affiche les actions de la catégorie correspondante (chargées via une requête SQL unique `Action × Rapport LEFT JOIN` filtrée par date du jour et `ContratId`). Les cases déjà cochées en base sont restituées visuellement en `is-on`. L'assistante coche / décoche, clique sur `Enregistrer le rapport` à l'étape 4, ce qui déclenche un endpoint backend exécutant en transaction unique un DELETE de toutes les lignes `(ContratId, Date=today)` suivi de N INSERT (une par case cochée, `Valeur='1'`). Après succès, redirection SPA vers `/bebes/{ContratId}` (onglet Rapport du jour). Le retour topbar via flèche annule la modification (aucun save) et revient sur la fiche détaillée.

## Quantified Goal (v7.0.0 — anti-GIGO)
- Metric: temps de chargement de l'écran (Time-To-Interactive client après clic sur `Modifier`) + temps de save complet (DELETE + N INSERT)
- Target: p95 chargement < 700 ms sur réseau 4G simulé (1 requête SQL `Action × Rapport LEFT JOIN`, payload < 12 KB JSON pour ~40 actions cumulées, rendu client < 200 ms) ; p95 save < 600 ms pour N ≤ 30 cases cochées (DELETE + N INSERT en transaction unique)
- Deadline: livraison stack `kotlin-spring-boot × react × shadcn` au 2026-07-15

## Non-Functional Constraints (v7.0.0)
- Expected volume: ~1 rapport / bébé / jour ouvré, ~5 bébés / employé / jour ⇒ ~5 saves / employé / jour ouvré ; chargements potentiellement multiples (assistante peut rouvrir l'écran pour ajuster) ⇒ ~10 chargements / employé / jour ; < 50k requêtes/jour total beta Demo
- Performance SLA: p95 chargement < 700 ms, p95 save < 600 ms (cf. Quantified Goal) ; le DELETE+INSERT en transaction unique ne doit pas saturer la connexion DB (< 200 ms pour N ≤ 30 lignes sur SQL Server Azure tier S1)
- Data retention: les lignes `dbo.Rapport` sont conservées indéfiniment côté schéma actuel (pas de purge automatique) ; chaque jour est une partition logique par `(ContratId, Date)` — l'historique reste interrogeable mais hors scope de cette FEAT
- Compliance: RGPD — les rapports sont visibles et modifiables uniquement par l'employé propriétaire du contrat (`Contrat.EmployeeId == session.EmployeeId`) ; aucun accès cross-employé ; jamais 403 (anti-énumération) — toujours 404 sur contrat hors périmètre
- Integration: nouvel endpoint backend `GET /api/contrats/{ContratId}/rapport` (charge contrat + actions + valeurs du jour en une seule réponse agrégée pour respecter AC-4) et `PUT /api/contrats/{ContratId}/rapport` (save = DELETE + INSERT en transaction) — aucun query param (date server-side BR-4) ; aucun service externe ; aucun envoi SMS/Email (out of scope)
- Degraded mode: si le backend est down, l'écran affiche un message d'erreur générique avec bouton `Réessayer` ; le retour topbar reste fonctionnel ; aucun cache local ni brouillon ; en cas de session expirée pendant la saisie (401), redirection `/login` avec perte des cases non sauvegardées (comportement assumé)

## Actors
- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session. Seul autorisé à consulter et modifier les rapports des contrats dont `Contrat.EmployeeId == session.EmployeeId`. Aucun accès à l'écran sans authentification.

## Functional Needs

### Point d'entrée et navigation
- SFD-1: La spec **étend `spec-bebe-detaille` SFD-30** : le bouton `Modifier` du `section-label` Rapport du jour (jusqu'ici cosmétique non fonctionnel) devient **fonctionnel** et déclenche une navigation SPA vers `/bebes/{ContratId}/rapport`
- SFD-2: L'utilisateur accède à la page `/bebes/{ContratId}/rapport` exclusivement depuis le clic sur le bouton `Modifier` de l'onglet `Rapport du jour` de la fiche détaillée bébé (`spec-bebe-detaille`) ; aucun autre point d'entrée n'est défini dans cette FEAT
- SFD-3: Le `ContratId` provient du segment d'URL ; toutes les requêtes backend vérifient en plus que `Contrat.EmployeeId == session.EmployeeId` avant de retourner ou modifier les données (cf. BR-1) — sinon 404 (jamais 403 — anti-énumération)
- SFD-4: La flèche `Retour` (topbar gauche) déclenche une navigation SPA vers `/bebes/{ContratId}` (la fiche détaillée d'origine, onglet `Rapport du jour` actif par défaut) ; **aucun save n'est effectué** lors du retour — les cases cochées non enregistrées sont perdues sans dialogue de confirmation (comportement assumé, symétrique de la navigation topbar de spec-bebe-detaille)

### Topbar (bloc supérieur)
- SFD-5: La topbar affiche, de gauche à droite : (1) icône bouton circulaire `Retour` (chevron gauche, fond coral-50, couleur coral-700), (2) nom et prénom du bébé en gras (`Contrat.Prenom + ' ' + Contrat.Nom`), (3) avatar circulaire avec photo du bébé (`Contrat.ImageUrl` concaténé avec la base statique, fallback initiales `{Prenom[0]}{Nom[0]}` si NULL)
- SFD-6: La topbar reste **fixe en haut** de l'écran (flex-shrink:0 du conteneur app) — le scroll s'applique uniquement au body central entre topbar+stepper et footer

### Stepper (sous topbar, fixe)
- SFD-7: Sous la topbar, un stepper 4 nœuds horizontal est affiché : `1 Santé` (icône ronde 30px, fond sage si done / coral si current / gris si pending), `2 Nourriture`, `3 Activité`, `4 Humeur`. Chaque nœud porte une pastille `dot` numérotée, un libellé court 10.5px sous la pastille, et une ligne de liaison vers le nœud suivant (sage si done, gris sinon — masquée sur le dernier nœud)
- SFD-8: Sous les 4 nœuds, une **barre de progression linéaire** 3px de haut affiche le pourcentage d'avancement : largeur = `(current / 4) × 100%`, gradient coral-500 → coral-400, fond gris (`var(--nj-line-soft)`) sur la partie restante
- SFD-9: L'étape `1 Santé` est active par défaut au chargement de l'écran
- SFD-10: Un clic sur un nœud (`.stepper__node`) active immédiatement l'étape correspondante : la section `.step` matchant `data-step` reçoit la classe `is-active` (display:flex + animation `slideIn` 0.35s) et les autres sections sont masquées (display:none) ; aucun save n'est effectué au switch ; les cases cochées dans les autres étapes sont **préservées en mémoire** (état React conservé tant que la page n'est pas quittée)
- SFD-11: Le stepper et la topbar restent fixes — seul le `.body` (zone contenant les `.step`) scrolle verticalement

### Body — Steps (1 active à la fois)
- SFD-12: Au chargement, l'écran envoie une **requête backend unique** `GET /api/contrats/{ContratId}/rapport` (aucun query param — la date est **toujours** `CAST(getdate() AS DATE)` côté serveur, BR-4 anti-tampering) qui exécute la requête SQL canonique :
  ```sql
  SELECT
    c.Prenom      AS ContratPrenom,
    c.Nom         AS ContratNom,
    c.ImageUrl    AS ContratImageUrl,
    a.ActionId,
    a.Nom,
    a.IdCategorie,
    a.Icon,
    r.Valeur
  FROM dbo.Contrat c
  CROSS JOIN dbo.[Action] a
  LEFT JOIN dbo.Rapport r
    ON r.ActionId = a.ActionId
    AND r.ContratId = c.ContratId
    AND r.[Date] = CAST(getdate() AS DATE)
  WHERE c.ContratId = @ContratId
    AND c.EmployeeId = @SessionEmployeeId
  ORDER BY a.IdCategorie ASC, a.ActionId ASC;
  ```
  Le filtre `c.ContratId AND c.EmployeeId` dans la clause WHERE fait office de garde anti-énumération : si le contrat n'appartient pas à l'employé connecté, la requête retourne **0 ligne** (renvoyée en 404 côté API). Le `CROSS JOIN` garantit qu'à chaque ligne, les colonnes contrat (`Prenom`, `Nom`, `ImageUrl`) sont restituées ; toutes les lignes du résultat portent les **mêmes** valeurs contrat (le service ne mappe qu'une fois). Le payload JSON agrégé retourné est `{ contrat: { prenom, nom, imageUrl }, actions: [{ actionId, nom, idCategorie, icon, checked }] }` où `checked` est `true` si une ligne `Rapport` correspondante existe (valeur = `'1'`) ou `false` sinon (LEFT JOIN sans match). **Note schéma** : `Action.Phrase` et `Rapport.RapportId` ont été retirés de la requête (colonnes inexistantes dans la base SQL Server réelle — schéma Prisma corrigé en conséquence).
- SFD-13: Le frontend regroupe les actions par `idCategorie` côté UI pour matérialiser les 4 steps : `idCategorie=1` → step 1 Santé, `idCategorie=2` → step 2 Nourriture, `idCategorie=3` → step 3 Activité, `idCategorie=4` → step 4 Humeur. Si une catégorie n'a aucune action en base, le step affiche une zone vide avec message `Aucune action disponible pour cette catégorie` (cas conceptuel improbable mais traité)
- SFD-14: Chaque step est rendu en grille 2 colonnes (`grid-template-columns:1fr 1fr`, gap:9px) où chaque action est une **cellule** cliquable (`<button class="cell" data-toggle>`) contenant : (1) un bloc icône 40×40px arrondi 12px avec l'icône Material Symbols dont le nom est lu dans `Action.Icon` (rendu `<span class="material-symbols-outlined">{icon}</span>`), (2) un libellé centré 12.5px en gras (`Action.Nom`), (3) une pastille check ronde 18×18px en haut-droite (transparente / coral-500 quand `is-on`)
- SFD-15: Une cellule porte la classe `is-on` si `valeur === "1"` au chargement (ligne `Rapport` existante pour aujourd'hui et ce contrat) ; sinon la cellule est en état "non cochée" (`is-on` absent)
- SFD-16: Un clic sur une cellule **toggle** sa classe `is-on` côté UI (aucun appel backend immédiat) ; l'état local React est mis à jour avec un set `<Set<actionId>>` représentant les cases cochées en cours ; le toggle est instantané sans animation bloquante
- SFD-17: Chaque cellule porte un attribut `data-action-id={actionId}` lisible côté JS/React pour traçabilité du save (permet de retrouver l'`ActionId` à partir du DOM ou du state)
- SFD-18: La step 4 Humeur affiche les cellules avec une classe `cell--mood` qui augmente la taille de l'icône à 32px et permet le rendu d'emojis Unicode si `Action.Icon` est un emoji (ex. `😊`, `😌`, `🤗`) plutôt qu'un nom Material Symbols ; la détection emoji vs nom MS est laissée au CSS Material Symbols (caractère non-mappé → ligature non rendue → fallback emoji natif du navigateur). Le DBA est responsable de remplir `Action.Icon` avec soit un nom Material Symbols (`thermometer`, `restaurant`...) pour les catégories 1-3, soit un emoji direct pour la catégorie 4 Humeur

### Footer (navigation stepper + save final)
- SFD-19: Le footer fixe (flex-shrink:0, fond `var(--nj-surface)`, border-top `var(--nj-line-soft)`) contient deux boutons : (1) `Précédent` (ghost, fond coral-50, masqué si `current === 1`), (2) `Suivant` (primary, fond coral-500, full-width via `flex:1`)
- SFD-20: Le bouton `Suivant` incrémente `current` (1 → 2 → 3 → 4) et met à jour le rendu stepper (cf. SFD-10) sans aucun save intermédiaire ; le scroll vertical du `.body` est remis à 0 à chaque switch
- SFD-21: À l'étape 4, le bouton `Suivant` est **muté** : son label devient `Enregistrer le rapport` (préfixé icône check 16px), sa classe additionnelle `btn-primary--save` applique un gradient sage (`linear-gradient(135deg, var(--nj-sage-500), oklch(0.62 0.085 168))`) au lieu du coral. Un clic sur ce bouton à l'étape 4 déclenche le **save** (cf. SFD-22)
- SFD-22: Le save envoie une requête backend unique `PUT /api/contrats/{ContratId}/rapport` (aucun query param — la date d'INSERT est **toujours** `CAST(getdate() AS DATE)` côté serveur, BR-4 anti-tampering) avec payload JSON `{ actionIds: [12, 17, 23, ...] }` listant les `ActionId` des cellules cochées (toutes étapes confondues). Le backend exécute dans une **transaction SQL unique** :
  ```sql
  BEGIN TRANSACTION;

  -- Étape 1 : purge totale du jour pour ce contrat
  DELETE FROM dbo.Rapport
   WHERE ContratId = @ContratId
     AND Date = CAST(getdate() AS DATE);

  -- Étape 2 : N INSERT (un par actionId du payload)
  -- Exécuté en boucle ou en INSERT ... VALUES batché côté ORM
  INSERT INTO dbo.Rapport (Date, ContratId, ActionId, Valeur)
  VALUES
    (CAST(getdate() AS DATE), @ContratId, @ActionId1, '1'),
    (CAST(getdate() AS DATE), @ContratId, @ActionId2, '1'),
    ...;

  COMMIT TRANSACTION;
  ```
  Les deux opérations sont **atomiques** : échec du DELETE → rollback ; échec d'un INSERT → rollback du DELETE et des INSERT précédents. Aucune ligne `Rapport` n'est insérée pour les cases non cochées (l'absence sert de marqueur "non coché" au prochain chargement via LEFT JOIN sans match).
- SFD-23: Si `actionIds` est un tableau **vide** (aucune case cochée), le save exécute seulement le DELETE (purge) puis COMMIT sans INSERT — un rapport "vide pour aujourd'hui" est une opération légitime (toutes les cases décochées par rapport à un état précédent)
- SFD-24: Le backend vérifie également avant le DELETE que `Contrat.EmployeeId = @SessionEmployeeId` (cf. BR-1) ; sinon 404 et **aucune modification** n'est effectuée
- SFD-25: Après succès complet du couple DELETE+INSERT, le backend retourne `204 No Content` ; le frontend redirige en SPA vers `/bebes/{ContratId}` (la fiche détaillée d'origine, onglet `Rapport du jour` actif par défaut) — **pas** vers `/bebes`
- SFD-26: En cas d'échec backend (500, transaction rollback, timeout), le frontend affiche un toast d'erreur générique `Échec de l'enregistrement. Réessayez.` et reste sur l'étape 4 ; les cases cochées en mémoire React sont **préservées** ; un re-clic sur `Enregistrer le rapport` retente l'opération (idempotente par construction — DELETE+INSERT)
- SFD-27: En cas de session expirée pendant la saisie (401 sur le PUT), le frontend redirige vers `/login` (cf. spec-connexion) ; les valeurs saisies sont **perdues** — comportement degraded mode assumé (symétrique spec-bebe-detaille BR-20)

### États de chargement et erreur
- SFD-28: Pendant le chargement initial (`GET` en cours), un état de squelette/spinner est visible dans la zone `.body` ; aucune cellule placeholder ne doit apparaître figée (anti-confusion utilisateur)
- SFD-29: Si le `ContratId` n'appartient pas à l'employé connecté (404 sur le GET), le frontend affiche une page "Bébé introuvable" avec un bouton `Retour aux bébés` redirigeant vers `/bebes` (cf. spec-bebe-detaille AC-2)
- SFD-30: Le bouton `Enregistrer le rapport` (étape 4) est désactivé pendant l'envoi du PUT (état loading) pour empêcher le double-submit ; un spinner inline 16px remplace l'icône check pendant la requête

## Business Rules
- BR-1: l'endpoint `GET /api/contrats/{ContratId}/rapport` retourne 0 ligne (et 404) si `Contrat.EmployeeId != session.EmployeeId` ; aucun rapport n'est exposé hors du périmètre de l'employé connecté (anti-énumération)
- BR-2: l'endpoint `PUT /api/contrats/{ContratId}/rapport` vérifie également `Contrat.EmployeeId = session.EmployeeId` AVANT le DELETE ; sinon 404 et **aucune modification** n'est effectuée (le DELETE n'est jamais exécuté)
- BR-3: `@SessionEmployeeId` provient exclusivement de la variable singleton de session ; aucun paramètre de requête (header, body, query) ne peut le surcharger (symétrique spec-bebe-detaille BR-2)
- BR-4: la **date** utilisée pour le filtre `Rapport.Date` est **toujours** `CAST(getdate() AS DATE)` côté serveur (date du serveur, locale TZ-naive) ; un paramètre `date` côté query est ignoré silencieusement par le backend (anti-tampering — empêche un client de modifier le rapport d'un jour passé)
- BR-5: les requêtes SQL sont **paramétrées** (`@ContratId`, `@SessionEmployeeId`, `@ActionId`) ; aucune concaténation de chaîne (anti-injection SQL — symétrique spec-bebe-detaille BR-6)
- BR-6: le DELETE et les N INSERT du save s'exécutent dans une **transaction SQL unique** ; échec d'une opération → rollback intégral (atomicité garantie — aucun état partiel persisté en base)
- BR-7: l'INSERT en base n'a lieu que pour les **cases cochées** (`Valeur = '1'`) ; les cases non cochées ne génèrent aucune ligne `Rapport` — leur absence est le marqueur d'état "non coché" au prochain chargement via LEFT JOIN sans match
- BR-8: la valeur stockée dans `Rapport.Valeur` pour une case cochée est la chaîne `'1'` (literal varchar) — convention partagée backend ↔ frontend ; aucune autre valeur n'est insérée par cette FEAT (les autres valeurs éventuelles — `'0'`, `'true'`, JSON — relèveraient d'une extension métier future hors scope)
- BR-9: les actions sont regroupées par `IdCategorie` côté frontend selon le mapping fixe : `1` → Santé, `2` → Nourriture, `3` → Activité, `4` → Humeur ; ce mapping est **codé en dur** dans le frontend (aucune table de catégories en base actuellement — extension future potentielle)
- BR-10: les icônes Material Symbols affichées proviennent **exclusivement** du champ `Action.Icon` (jamais hardcodées côté frontend) ; le DBA est responsable de remplir ce champ avec des noms canoniques Google Material Symbols (ex. `thermometer`, `restaurant`, `directions_walk`) pour catégories 1-3, ou des emojis Unicode (ex. `😊`) pour catégorie 4 Humeur
- BR-11: si `Action.Icon` est NULL, la cellule affiche un placeholder icône générique (carré gris vide 40×40) — la cellule reste cliquable et fonctionnelle (le toggle n'est pas bloqué)
- BR-12: les champs retournés par le backend sont sérialisés en camelCase JSON (cf. library-and-stack §6.bis.3) : `actionId`, `nom`, `idCategorie`, `icon`, `phrase`, `valeur` ; aucune sérialisation en PascalCase ou snake_case
- BR-13: les valeurs NULL backend sont sérialisées `null` JSON ; côté frontend, `valeur === null` (cf. SFD-12) signifie "case non cochée" et `valeur === "1"` signifie "case cochée"
- BR-14: une cellule cochée OU décochée par l'utilisateur en mémoire React **n'est pas** persistée tant que le clic sur `Enregistrer le rapport` (étape 4) n'a pas eu lieu ; tout changement intermédiaire (navigation entre steps, scroll) ne déclenche aucun appel backend (économie de requêtes)
- BR-15: le retour topbar (flèche `←`) navigue vers `/bebes/{ContratId}` **sans** save ; les cases modifiées non enregistrées sont définitivement perdues — aucun dialogue de confirmation n'est affiché (comportement assumé)
- BR-16: aucune information technique (stack trace, exception SQL, identifiant interne, message ORM) n'est exposée dans les messages d'erreur visibles à l'utilisateur (symétrique spec-bebe-detaille BR-24)
- BR-17: les actions affichées dans un step sont **triées** par `ActionId` croissant (ordre stable par défaut SQL `ORDER BY a.IdCategorie, a.ActionId`) — un tri visuel custom (par `Action.Nom` alphabétique, par fréquence d'usage) est hors scope ; le DBA peut influencer l'ordre via les valeurs `ActionId` (qui restent stables)
- BR-18: la requête `GET /api/contrats/{ContratId}/rapport` retourne **toutes** les actions de la base (toutes catégories confondues) en un seul appel — pas de pagination, pas de filtrage côté serveur par catégorie active ; le frontend gère le regroupement par `IdCategorie` (anti N+1, économie de requêtes)
- BR-19: si le design system actif fournit des composants équivalents (Stepper, Button, Card, IconButton), ils DOIVENT être utilisés en priorité (cf. spec-bebe-detaille BR-25) ; le CSS isolé ne complète que pour la fidélité visuelle de la maquette `10-Spec-rapport-du-jour.html`
- BR-20: la navigation `Retour` topbar utilise le mécanisme SPA du framework actif (cf. spec-bebe-detaille BR-26) — l'usage de `<a href>` brut est interdit (le mockup utilise `<a class="topbar__back" href="09-fiche-enfant.html">` pour la maquette HTML statique uniquement, mais la version React/Vue/Angular utilisera `<button>` + `useNavigate()` ou équivalent)
- BR-21: l'écran ne supporte qu'**un seul ContratId à la fois** — aucune édition multi-bébés simultanée ; chaque navigation `/bebes/{ContratId}/rapport` est un cycle indépendant (state React reset à chaque entrée)
- BR-22: le bouton `Modifier` de l'onglet `Rapport du jour` de spec-bebe-detaille (jusqu'ici cosmétique SFD-30) devient fonctionnel **uniquement** dans le contexte de cette FEAT ; le bouton `Envoyer aux parents` reste cosmétique non fonctionnel (couvert par FEAT future dédiée — cf. Out of Scope)

## Acceptance Criteria
- AC-1: la page `/bebes/{ContratId}/rapport` est accessible **exclusivement** depuis le clic sur le bouton `Modifier` du `section-label` Rapport du jour de la fiche détaillée bébé (`/bebes/{ContratId}`, onglet 2) ; aucun autre point d'entrée n'est défini
- AC-2: la page n'est pas accessible sans session valide — redirection `/login` cf. spec-connexion
- AC-3: un accès direct à `/bebes/{ContratId}/rapport` avec un `ContratId` n'appartenant pas à l'employé connecté retourne **404** (jamais 403) ; le frontend affiche "Bébé introuvable" + bouton `Retour aux bébés`
- AC-4: au chargement, la page envoie **une seule** requête backend `GET /api/contrats/{ContratId}/rapport` (aucun query param — réponse agrégée `{ contrat, actions }` couvrant à la fois la topbar et le contenu des steps) ; aucun appel additionnel n'est effectué lors du switch entre steps (vérifiable côté Network DevTools)
- AC-5: la topbar affiche, dans l'ordre : flèche `Retour` (gauche), nom du bébé `{Prenom} {Nom}` (centre/gauche), avatar circulaire (droite) ; un clic sur la flèche `Retour` navigue en SPA vers `/bebes/{ContratId}` (fiche détaillée, onglet `Rapport du jour`) **sans save**
- AC-6: le stepper affiche 4 nœuds avec libellés exacts : `Santé`, `Nourriture`, `Activité`, `Humeur` ; l'étape `Santé` est active par défaut au chargement
- AC-7: la barre de progression linéaire sous les nœuds a une largeur de `25%` à l'étape 1, `50%` à l'étape 2, `75%` à l'étape 3, `100%` à l'étape 4 (gradient coral-500 → coral-400)
- AC-8: un clic sur un nœud `stepper__node` active immédiatement l'étape correspondante (section `.step` matchant `data-step` reçoit `is-active`, les autres sont masquées) ; la transition est animée (slideIn 0.35s)
- AC-9: les cases cochées dans une étape sont préservées en mémoire React lors du switch vers une autre étape (state non remis à 0)
- AC-10: chaque step affiche les actions de sa catégorie (`IdCategorie` mappé : 1=Santé, 2=Nourriture, 3=Activité, 4=Humeur) en grille 2 colonnes avec icône + libellé + pastille check
- AC-11: l'icône de chaque cellule est rendue via `<span class="material-symbols-outlined">{Action.Icon}</span>` ; le nom de l'icône provient **uniquement** de la colonne `Action.Icon` (jamais hardcodé)
- AC-12: pour la step 4 Humeur, les cellules portent la classe `cell--mood` (icône agrandie à 32px) et le champ `Action.Icon` peut contenir un emoji Unicode (ex. `😊`) rendu nativement
- AC-13: une cellule porte la classe `is-on` (fond coral-50, border coral-500, pastille check coral-500) si `valeur === "1"` au chargement (ligne `Rapport` existante pour `ContratId` + date du jour)
- AC-14: un clic sur une cellule toggle sa classe `is-on` immédiatement côté UI (instantané, aucun appel backend) ; le state local React est mis à jour
- AC-15: le footer affiche un bouton `Suivant` (coral-500, full-width) à toutes les étapes sauf 4 ; à l'étape 4, le bouton devient `Enregistrer le rapport` avec gradient sage et icône check préfixée
- AC-16: le bouton `Précédent` est masqué (display:none) à l'étape 1, visible à partir de l'étape 2 (ghost coral-50)
- AC-17: un clic sur `Suivant` (étapes 1-3) incrémente `current`, met à jour le rendu stepper + barre de progression + section active ; le scroll `.body` est remis à 0
- AC-18: un clic sur `Enregistrer le rapport` (étape 4) envoie une requête backend unique `PUT /api/contrats/{ContratId}/rapport` (aucun query param — date server-side `CAST(getdate() AS DATE)` cf. BR-4) avec payload `{ actionIds: [...] }` listant tous les `ActionId` cochés toutes étapes confondues
- AC-19: le backend exécute dans une **transaction SQL unique** : (1) `DELETE FROM dbo.Rapport WHERE ContratId = @ContratId AND Date = CAST(getdate() AS DATE)` ; (2) N `INSERT INTO dbo.Rapport (Date, ContratId, ActionId, Valeur) VALUES (CAST(getdate() AS DATE), @ContratId, @ActionId, '1')` pour chaque `actionId` du payload
- AC-20: en cas d'échec d'une INSERT, le DELETE et les INSERT précédents sont **intégralement rollbackés** (atomicité transaction) ; vérification : aucun état partiel ne persiste en base après une tentative échouée (ex. test d'intégration `SELECT COUNT(*) FROM Rapport WHERE ContratId=X AND Date=today` avant/après save échoué retourne la même valeur)
- AC-21: si `actionIds` est un tableau **vide** (aucune case cochée), le save exécute seulement le DELETE puis COMMIT (rapport vidé pour aujourd'hui) ; le backend retourne 204
- AC-22: après succès complet du couple DELETE+INSERT (204), l'utilisateur est redirigé en SPA vers `/bebes/{ContratId}` (fiche détaillée, onglet `Rapport du jour` actif) et **non** vers `/bebes`
- AC-23: en cas d'échec backend (500, timeout, transaction rollback), un toast d'erreur générique `Échec de l'enregistrement. Réessayez.` est affiché ; les cases cochées en mémoire React sont **préservées** ; un re-clic sur `Enregistrer le rapport` retente l'opération
- AC-24: un appel direct à `PUT /api/contrats/{ContratId}/rapport` avec un `ContratId` n'appartenant pas à la session (manipulation manuelle) est rejeté **avant** le DELETE : retour 404, aucune modification en base
- AC-25: pendant le chargement initial du GET, un état de squelette/spinner est visible dans `.body` ; aucune cellule placeholder figée n'apparaît
- AC-26: pendant l'envoi du PUT (save en cours), le bouton `Enregistrer le rapport` est désactivé et un spinner inline 16px remplace l'icône check (anti double-submit)
- AC-27: la requête SQL exécutée pour le GET est exactement celle de SFD-12 (paramétrée, `CROSS JOIN Contrat × Action LEFT JOIN Rapport`, filtre WHERE `ContratId + EmployeeId`, date `CAST(getdate() AS DATE)` server-side) — vérifiable côté logs SQL ou test d'intégration
- AC-28: la valeur stockée dans `Rapport.Valeur` pour chaque ligne insérée est la chaîne literal `'1'` — pas `'0'`, pas `null`, pas `'true'` (vérifiable côté base ou test d'intégration)
- AC-29: la spec **étend `spec-bebe-detaille` SFD-30** : le bouton `Modifier` du `section-label` Rapport du jour de `/bebes/{ContratId}` (onglet 2) devient fonctionnel et navigue vers `/bebes/{ContratId}/rapport` ; le bouton `Envoyer aux parents` reste cosmétique non fonctionnel (BR-22)
- AC-30: si une catégorie n'a aucune action en base (cas conceptuel improbable), le step affiche un message centré `Aucune action disponible pour cette catégorie` sans casser le rendu du stepper ni des autres steps
- AC-31: la session expirée pendant la saisie ou le save (401) déclenche une redirection frontend vers `/login` ; les valeurs saisies sont perdues (comportement degraded mode assumé)

## Dependencies
- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employé connecté ; redirection vers `/login` en l'absence de session valide
- **spec-bebe-detaille** (`9-bebe-detaille`) : **complétée** par cette FEAT — le bouton `Modifier` du section-label Rapport du jour (SFD-30, jusqu'ici cosmétique) devient fonctionnel et navigue vers `/bebes/{ContratId}/rapport` ; le retour topbar de la nouvelle page revient sur `/bebes/{ContratId}` (onglet `Rapport du jour` actif)
- **spec-bebes** (`4-spec-bebes`) : indirecte — la fiche détaillée bébé est accessible depuis `/bebes`, mais cette FEAT n'en dépend pas directement
- **spec-inscription** (`3-spec-inscription`) : la base statique de stockage d'images est réutilisée pour afficher la photo bébé dans l'avatar topbar via `Contrat.ImageUrl` (cf. spec-bebe-detaille BR-11)

## Functional Deliverables
- FD-1: écran `/bebes/{ContratId}/rapport` à 3 blocs (topbar fixe + stepper fixe + body scrollable + footer fixe) avec stepper 4 étapes Santé/Nourriture/Activité/Humeur, étape 1 active par défaut
- FD-2: endpoint backend `GET /api/contrats/{ContratId}/rapport` (aucun query param — date server-side BR-4) exécutant la requête SQL paramétrée canonique de SFD-12 (`CROSS JOIN Contrat × Action LEFT JOIN Rapport`, filtre WHERE `ContratId + EmployeeId`) ; retourne payload JSON agrégé `{ contrat: { prenom, nom, imageUrl }, actions: [{ actionId, nom, idCategorie, icon, checked }] }` ou 404 si hors périmètre
- FD-3: topbar avec flèche `Retour` (navigation SPA vers `/bebes/{ContratId}`), nom du bébé `{Prenom} {Nom}`, avatar circulaire (photo `Contrat.ImageUrl` ou initiales si NULL)
- FD-4: stepper 4 nœuds horizontal cliquables avec barre de progression linéaire coral ; gestion d'état `current` côté React (1-4) avec animation slideIn entre steps
- FD-5: 4 sections `step` (Santé, Nourriture, Activité, Humeur) en grille 2 colonnes, chaque cellule rendue via `<button class="cell" data-action-id={id} data-toggle>` avec icône Material Symbols depuis `Action.Icon`, libellé `Action.Nom`, pastille check
- FD-6: gestion d'état local React `<Set<actionId>>` représentant les cases cochées en cours ; toggle instantané au clic (pas d'appel backend)
- FD-7: footer avec boutons `Précédent` (ghost, masqué étape 1) et `Suivant`/`Enregistrer le rapport` (primary, muté à l'étape 4 avec gradient sage et icône check)
- FD-8: endpoint backend `PUT /api/contrats/{ContratId}/rapport` (aucun query param — date d'INSERT server-side BR-4) exécutant dans une transaction SQL unique : DELETE des lignes `Rapport (ContratId, Date=today)` puis N INSERT (`Valeur='1'`) pour chaque `actionId` du payload `{ actionIds: [...] }` ; retour 204 ou 404 (hors périmètre) ou 500 (rollback transaction)
- FD-9: redirection SPA vers `/bebes/{ContratId}` (fiche détaillée, onglet `Rapport du jour`) après succès du save ; conservation du state local React et toast d'erreur générique en cas d'échec backend
- FD-10: gestion des états de chargement (squelette/spinner pendant `GET`), d'erreur (404 → page "Bébé introuvable", 500 → toast), de session expirée (401 → redirection `/login`), et d'anti double-submit (bouton désactivé + spinner pendant le `PUT`)
- FD-11: **extension de spec-bebe-detaille** — le bouton `Modifier` du section-label `Rapport du jour` (jusqu'ici cosmétique SFD-30) devient fonctionnel et navigue en SPA vers `/bebes/{ContratId}/rapport` ; le bouton `Envoyer aux parents` reste cosmétique non fonctionnel
- FD-12: rendu emoji natif support sur la step 4 Humeur via classe CSS `cell--mood` (icône 32px) — le champ `Action.Icon` peut contenir un emoji Unicode pour les actions de catégorie 4

## Out of Scope
- envoi de notification SMS / Email aux parents après save (bouton `Envoyer aux parents` reste cosmétique non fonctionnel — FEAT future dédiée)
- génération automatique d'un texte agrégé / résumé narratif depuis les cases cochées pour pré-remplir la textarea de l'onglet `Rapport du jour` de spec-bebe-detaille (FEAT future dédiée)
- ajout d'aliments / actions personnalisés par l'assistante (input `Ajouter un autre aliment…` du mockup ligne 371-375) — l'input n'est **pas rendu** dans le composant React de cette FEAT, seules les actions de `dbo.Action` sont éditables
- modification du rapport d'un jour passé (la date est **toujours** la date du serveur — l'écran ne permet pas d'éditer un rapport historique)
- consultation d'un rapport historique (mode read-only sur un jour passé) — extension future potentielle (`GET /api/contrats/{ContratId}/rapport?date=2026-04-15` avec mode read-only)
- saisie de valeurs autres que coché/non coché (ex. dosage `Valeur='250ml'`, durée `Valeur='30min'`, intensité `Valeur='3/5'`) — le schéma actuel permet `Rapport.Valeur` jusqu'à 100 caractères mais cette FEAT n'insère que `'1'` (extension future potentielle pour saisies quantitatives)
- gestion d'un brouillon / save partiel entre étapes (tout-ou-rien au save final, symétrique spec-souscrire-contrat)
- export PDF du rapport du jour
- partage du rapport (lien public, génération QR code)
- workflow d'approbation / signature électronique du rapport par les parents
- comparaison historique (rapport d'aujourd'hui vs hier vs semaine dernière) ou statistiques agrégées (fréquence des problèmes de santé, types d'activités préférées)
- alertes / seuils (ex. notification au parent si fièvre 3 jours d'affilée) — FEAT future dédiée
- multi-device / synchronisation temps réel entre deux sessions du même employé éditant le même rapport
- gestion d'une table de **catégories** structurée en base (le mapping `IdCategorie` → libellé Santé/Nourriture/Activité/Humeur est codé en dur côté frontend — extension future potentielle avec table `dbo.ActionCategorie`)
- gestion d'**ordres** custom des actions au sein d'une catégorie (tri actuel : `ORDER BY ActionId` — pas de colonne `Ordre` dédiée) — extension future
- gestion de la **visibilité** / **archivage** d'une action (toutes les actions de `dbo.Action` sont affichées — pas de colonne `Active` ou `DateArchivage`) — extension future
- gestion de **plusieurs rapports par jour** pour un même bébé (l'écran traite le rapport comme une **unique** entité jour — DELETE puis INSERT)
- fallback offline / cache local du rapport pour saisie sans réseau
- rôles Admin et Parent (extensions futures — le Parent consulte ses rapports dans une FEAT dédiée hors scope ici)
