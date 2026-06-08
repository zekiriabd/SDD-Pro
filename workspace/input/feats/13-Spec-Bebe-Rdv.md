# Spec: bebe-rdv

FEAT ID: 13-Spec-Bebe-Rdv
Spec ID: spec-bebe-rdv
Status: Draft

> **Pré-requis schéma** : nouvelle table `dbo.BebeRdv` à créer (cf. SFD-3 pour le DDL canonique). La table n'est **pas** présente dans le schéma extrait `workspace/output/db/schema.md` au 2026-05-26 — création obligatoire avant `dev-backend`. DDL exécuté côté DBA OU généré par `arch` Phase B (scaffolding) — arbitrage SDD. Après application, `workspace/output/db/schema.{json,md,diff.md}` doivent refléter la nouvelle table (source de vérité = DB existante, cf. `docs/principles/source-first.md`).

## Context

L'onglet 3 (`RDV`) de la fiche détaillée bébé `/bebes/{ContratId}` (cf. `spec-bebe-detaille` SFD-32, SFD-33, SFD-34, FD-11) est aujourd'hui une **interface statique non interactive** : la liste d'événements est codée en dur dans la maquette (`workspace/input/ui/9-1-Spec-Bebe-Detaile.html` lignes 446-496), le bouton FAB `+` est cosmétique, aucun appel backend n'est déclenché au montage ni au switch d'onglet. La logique métier complète (CRUD rendez-vous, notifications, conflits de planning) était explicitement renvoyée à « une FEAT ultérieure dédiée » dans `spec-bebe-detaille` (cf. Out of Scope).

Cette spec décrit l'**activation fonctionnelle partielle** de cet onglet 3 en trois temps :

1. **Création de la table `dbo.BebeRdv`** (DDL — cf. SFD-3) avec les colonnes `BebeRdvId` (PK IDENTITY), `Date`, `ContratId` (FK → `Contrat`), `HeureRdv`, `Titre`, `Message`. La table porte un rendez-vous par ligne — pas de relation many-to-many, pas de récurrence, pas de notification persistée.

2. **Listage dynamique des RDV à venir** côté frontend — l'onglet `RDV` n'est plus statique mais déclenche, à l'activation (`tab__click` → `pane="rdv"` actif), un appel `GET /api/contrats/{ContratId}/rdv` qui exécute la requête SQL canonique paramétrée sur `dbo.BebeRdv` filtrée par `ContratId` ET `DATEADD(SECOND, DATEDIFF(SECOND, '00:00:00', HeureRdv), CAST(Date AS DATETIME)) >= GETDATE()` (filtre combiné date+heure — cf. SFD-7, **corrigé 2026-05-27**, ancienne version `Date = CAST(getdate() AS DATE)` strict aujourd'hui révoquée car elle masquait toute planification au-delà du jour J). Chaque rendez-vous est rendu sous forme de carte horizontale fidèle au markup de la maquette : pastille `MOIS / JOUR` à gauche (mois sur 3 lettres uppercase, jour sur 2 chiffres), bloc texte central (`Titre` en gras suivi du `Message`, ou `Message` seul si `Titre` est NULL), heure `HH:MM` à droite, deux boutons d'action `Modifier` et `Supprimer`. La couleur de fond de chaque carte est aléatoire parmi 3 variantes du design system (`coral`, `butter`, `sage`) sélectionnée déterministiquement par `BebeRdvId mod 3` (cf. SFD-10, BR-9).

3. **Actions par RDV — partiellement câblées dans cette FEAT** :
   - Le bouton `Supprimer` est **fonctionnel dans cette FEAT** : ouverture d'une modale de confirmation `Supprimer ce rendez-vous ?`, puis sur validation, appel `DELETE /api/contrats/{ContratId}/rdv/{BebeRdvId}` qui exécute le `DELETE FROM dbo.BebeRdv` paramétré. Après succès, la card est retirée du DOM sans rechargement complet de la liste (mise à jour optimiste avec rollback en cas de 4xx/5xx — cf. SFD-13).
   - Le bouton `Modifier` (icône crayon, intégré dans la card) et le FAB `+` (bas droite, ouverture en création) déclenchent **uniquement des navigations SPA** vers `/bebes/{ContratId}/rdv/{BebeRdvId}` et `/bebes/{ContratId}/rdv/nouveau` respectivement. Ces deux routes pointent vers un écran de **création / modification d'un rendez-vous** qui est **out of scope de cette FEAT** — couvert par une FEAT future dédiée (qui implémentera le formulaire, le `POST /api/contrats/{ContratId}/rdv`, le `PUT /api/contrats/{ContratId}/rdv/{BebeRdvId}`, et la redirection retour vers `/bebes/{ContratId}` onglet `RDV`).

La spec **étend `spec-bebe-detaille`** : SFD-32 (interface statique → dynamique), SFD-33 (« aucune persistance » → CRUD partiel), SFD-34 (badge compteur en dur → compteur dynamique du nombre de RDV à venir retourné par l'endpoint), FD-11 (interface statique → liste dynamique câblée + delete fonctionnel + redirects). La maquette de référence reste `9-1-Spec-Bebe-Detaile.html` (panneau `[data-pane="rdv"]`, lignes 435-502) — les marqueurs `section-label`, `event`, `event__date`, `event__body`, `event__time`, `fab` du markup HTML existant sont **conservés tels quels**, seul leur contenu devient dynamique. La section `<div class="section-label">Passé</div>` et les cartes `event--past` du mockup statique sont **supprimées** dans le rendu dynamique de cette FEAT (la requête SQL filtre les RDV passés via `(Date + HeureRdv) >= GETDATE()` — pas d'historique passé visible, mais le futur multi-jour est **inclus** depuis la correction 2026-05-27).

## Objective

L'employé connecté ouvre la fiche détaillée d'un bébé `/bebes/{ContratId}` puis clique sur l'onglet `RDV` → le frontend envoie un unique `GET /api/contrats/{ContratId}/rdv` ; le backend exécute la requête SQL canonique paramétrée sur `dbo.BebeRdv` filtrée `ContratId = @ContratId AND DATEADD(SECOND, DATEDIFF(SECOND, '00:00:00', HeureRdv), CAST(Date AS DATETIME)) >= GETDATE()` (filtre combiné date+heure pour ne retenir que les RDV à venir, avec vérification serveur que `Contrat.EmployeeId = @SessionEmployeeId` — anti-cross-tenant) et retourne un tableau JSON `[ { bebeRdvId, date, heureRdv, titre, message }, ... ]` trié par `Date ASC, HeureRdv ASC, BebeRdvId ASC`. La liste est rendue dans le panneau `[data-pane="rdv"]` existant : chaque ligne affiche pastille `MOIS / JOUR` (extraite côté UI de `Date`, mois 3-lettres FR uppercase, jour 2 chiffres), titre + message (ou message seul si pas de titre), heure `HH:MM`, bouton `Modifier` (icône crayon, redirige `/bebes/{ContratId}/rdv/{BebeRdvId}`), bouton `Supprimer` (icône corbeille, ouvre modale de confirmation puis appel `DELETE /api/contrats/{ContratId}/rdv/{BebeRdvId}`). Un FAB `+` en bas droite redirige `/bebes/{ContratId}/rdv/nouveau`. Si la liste est vide, un état empty-state (« Aucun rendez-vous à venir ») remplace la liste. Le badge compteur de l'onglet (cf. spec-bebe-detaille SFD-8) reflète dynamiquement la longueur de la liste retournée. Les écrans de création et de modification eux-mêmes (`/bebes/{ContratId}/rdv/nouveau` et `/bebes/{ContratId}/rdv/{BebeRdvId}`) sont **out of scope** de cette FEAT 13 — couverts par FEAT 14.

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps de chargement de la liste RDV (Time-To-Interactive du panneau `RDV` après clic sur l'onglet) + temps de suppression (clic confirmer → card retirée du DOM)
- Target: p95 chargement liste < 350 ms sur 4G simulé (1 unique requête SQL `SELECT ... FROM BebeRdv WHERE ContratId=X AND (Date+HeureRdv) >= now()` indexée sur `(ContratId, Date)`, payload < 4 KB JSON pour ≤ 10 RDV ; les RDV à venir restent normalement ≤ quelques dizaines par bébé) ; p95 suppression < 250 ms (modale → DELETE backend → DOM update) ; redirection vers route de création / édition < 100 ms (pas de round-trip serveur, navigation SPA)
- Deadline: livraison stack `fullstack/node-react × ui/shadcn × auth/auth-local` au 2026-07-15

## Non-Functional Constraints (v7.0.0)

- Expected volume: ~3-5 RDV / bébé / jour ouvré en moyenne ; ~50 ouvertures de l'onglet `RDV` par employé / jour ; ~1-2 suppressions par employé / jour (faible volume écriture, lecture dominante)
- Performance SLA: p95 `GET /api/contrats/{ContratId}/rdv` < 200 ms backend (cf. Quantified Goal) ; p95 `DELETE /api/contrats/{ContratId}/rdv/{BebeRdvId}` < 150 ms ; aucun risque N+1 (1 SELECT unique sur table indexée) ; le filtre temporel `(Date + HeureRdv) >= GETDATE()` est calculé serveur — jamais transmis par le client (anti-tampering, cohérence inter-utilisateur sur la définition de « maintenant »)
- Data retention: les lignes `dbo.BebeRdv` sont conservées tant que le contrat parent existe (CASCADE non requis dans cette FEAT — la suppression d'un contrat reste out of scope) ; pas de purge automatique des RDV passés (les RDV dont la combinaison `Date + HeureRdv < now()` restent en base mais ne sont jamais affichés tant que le filtre serveur `(Date + HeureRdv) >= GETDATE()` reste actif — visibilité = RDV futurs ou en cours uniquement)
- Compliance: RGPD — les rendez-vous (titre, message, heure) peuvent contenir des informations médicales potentiellement sensibles (catégorie 9 RGPD si pathologie / vaccin évoqué) ; visibles et modifiables uniquement par l'employé propriétaire du contrat (`Contrat.EmployeeId == session.EmployeeId`) ; jamais 403 (anti-énumération d'ID) — toujours 404 sur contrat hors périmètre ; aucune diffusion automatique (pas de notification aux parents dans cette FEAT)
- Integration: nouvelle table `dbo.BebeRdv` (FK simple vers `dbo.Contrat`) ; deux nouveaux endpoints backend (`GET` liste + `DELETE` unique) ; aucun service externe (pas de iCal, Google Calendar, ni notification SMS / email) ; le rendu UI réutilise le markup et CSS isolé existants du panneau `[data-pane="rdv"]` de `9-1-Spec-Bebe-Detaile.html` ; aucune extension du design system actif `ui/shadcn`
- Degraded mode: si le `GET` liste échoue (timeout, 5xx), un message d'erreur générique `Impossible de charger les rendez-vous` + bouton `Réessayer` est affiché en lieu et place de la liste ; si le `DELETE` échoue, la card retirée optimistement est ré-insérée et un toast `Suppression impossible — réessayez` est affiché ; si la modale de confirmation est annulée, aucun appel backend n'est envoyé ; si la table `dbo.BebeRdv` est inaccessible en lecture, le backend retourne 503 et le frontend bascule sur l'état d'erreur ; les boutons `Modifier` et FAB `+` redirigent même si le `GET` initial a échoué (cohérent — la page cible est out of scope et gérera son propre chargement)

## Actors

- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session (cf. `spec-connexion`). Seul autorisé à lister, supprimer ou éditer (via redirect future FEAT) les RDV des contrats dont `Contrat.EmployeeId == session.EmployeeId`. Aucun accès à l'onglet `RDV` sans authentification.

## Functional Needs

### Point d'entrée et navigation

- SFD-1: La spec **étend `spec-bebe-detaille` SFD-32 / SFD-33 / FD-11** : le panneau `[data-pane="rdv"]` de la fiche détaillée bébé `/bebes/{ContratId}` (jusqu'ici statique non interactif) est désormais alimenté dynamiquement par un appel `GET /api/contrats/{ContratId}/rdv` déclenché **au clic sur l'onglet `RDV`** (lazy fetch). Le fetch n'est **pas** déclenché au chargement initial de la fiche (l'onglet `Informations` étant actif par défaut — cf. spec-bebe-detaille SFD-10) — économie d'un round-trip si l'utilisateur ne consulte pas les RDV.
- SFD-2: Aucune nouvelle route SPA n'est introduite par cette FEAT pour le **listage** — l'affichage se fait dans le panneau existant `[data-pane="rdv"]` de `/bebes/{ContratId}`. Deux routes SPA sont **nommées mais non implémentées** par cette FEAT (cf. SFD-15, SFD-16, Out of Scope) :
  - `/bebes/{ContratId}/rdv/nouveau` (création — destination du FAB `+` et du redirect bouton `Modifier` quand `BebeRdvId` est absent)
  - `/bebes/{ContratId}/rdv/{BebeRdvId}` (édition — destination du bouton `Modifier` sur une card existante)

### Schéma de données — table `dbo.BebeRdv` (nouvelle)

- SFD-3: La table `dbo.BebeRdv` porte les rendez-vous programmés par l'employé pour chaque bébé. DDL canonique :
  ```sql
  CREATE TABLE dbo.BebeRdv (
    BebeRdvId INT IDENTITY(1,1) NOT NULL,
    [Date] DATE NOT NULL,
    ContratId INT NOT NULL,
    HeureRdv TIME NOT NULL,
    Titre NVARCHAR(100) NULL,
    Message NVARCHAR(500) NULL,
    CONSTRAINT PK_BebeRdv PRIMARY KEY CLUSTERED (BebeRdvId),
    CONSTRAINT FK_BebeRdv_Contrat FOREIGN KEY (ContratId)
      REFERENCES dbo.Contrat (ContratId)
  );

  CREATE NONCLUSTERED INDEX IX_BebeRdv_ContratId_Date
    ON dbo.BebeRdv (ContratId, [Date]) INCLUDE (HeureRdv);
  ```
  - `BebeRdvId` (`INT IDENTITY(1,1) NOT NULL`) — PK surrogate, auto-incrémentée par SQL Server
  - `Date` (`DATE NOT NULL`) — journée du rendez-vous (sans heure)
  - `ContratId` (`INT NOT NULL`, FK vers `dbo.Contrat.ContratId`) — bébé concerné
  - `HeureRdv` (`TIME NOT NULL`) — heure du rendez-vous, fuseau serveur local TZ-naive (cf. BR-12)
  - `Titre` (`NVARCHAR(100) NULL`) — libellé court du rendez-vous (ex. « Rendez-vous pédiatre », « Vaccin 12 mois ») ; **NULL admis** (cf. SFD-9 — certains RDV n'ont qu'un message)
  - `Message` (`NVARCHAR(500) NULL`) — texte libre descriptif (ex. « Maman vient chercher Lina · départ anticipé ») ; **NULL admis** pour préserver la souplesse côté FEAT future de création
  - Index `IX_BebeRdv_ContratId_Date` (non-clustered) — optimise la requête SQL canonique `WHERE ContratId = @x AND Date = @today`
- SFD-4: Aucune colonne d'audit (`CreatedAt`, `CreatedBy`, `UpdatedAt`) n'est ajoutée dans cette FEAT (out of scope — cf. `## Out of Scope`). Aucune contrainte d'unicité métier (`UNIQUE (ContratId, Date, HeureRdv)`) n'est définie — deux RDV simultanés sur le même bébé sont autorisés au niveau base (l'arbitrage de conflit éventuel relève de la FEAT future de création / édition).
- SFD-5: La création / migration de la table elle-même est portée par le DDL ci-dessus (SFD-3). Elle est exécutée **avant** toute matérialisation `dev-backend` de cette FEAT — soit manuellement par le DBA, soit via `arch` Phase B si le projet `fullstack/node-react` actif délègue le scaffolding DB à arch (cf. ADR projet en place). Le fichier `workspace/output/db/schema.{json,md,diff.md}` doit être régénéré post-DDL pour refléter la nouvelle table avant `dev-backend`.

### Listage des RDV — requête SQL canonique

- SFD-6: Au clic sur l'onglet `RDV` (et uniquement à ce moment-là — pas de pré-fetch), le frontend envoie un unique `GET /api/contrats/{ContratId}/rdv` ; le `ContratId` est extrait du segment d'URL `/bebes/{ContratId}` de la fiche détaillée parente (cf. spec-bebe-detaille SFD-1, SFD-3).
- SFD-7: Le backend exécute la requête SQL canonique paramétrée suivante (**corrigée 2026-05-27** — ancienne version `r.[Date] = CAST(getdate() AS DATE)` trop stricte, masquait les RDV du lendemain et au-delà) :
  ```sql
  SELECT
    r.BebeRdvId,
    r.[Date],
    r.ContratId,
    r.HeureRdv,
    r.Titre,
    r.Message
  FROM dbo.BebeRdv r
  INNER JOIN dbo.Contrat c ON c.ContratId = r.ContratId
  WHERE r.ContratId  = @ContratId
    AND c.EmployeeId = @SessionEmployeeId
    AND DATEADD(
          SECOND,
          DATEDIFF(SECOND, '00:00:00', r.HeureRdv),
          CAST(r.[Date] AS DATETIME)
        ) >= GETDATE()
  ORDER BY r.[Date] ASC, r.HeureRdv ASC, r.BebeRdvId ASC;
  ```
  Le `INNER JOIN dbo.Contrat` n'est pas utilisé pour rapatrier des colonnes mais **uniquement** pour propager le filtre de propriété `c.EmployeeId = @SessionEmployeeId` (anti-cross-tenant — un accès direct manipulant `contratId` ne peut pas lister les RDV d'un bébé d'un autre employé). Le filtre temporel `DATEADD(SECOND, DATEDIFF(SECOND, '00:00:00', r.HeureRdv), CAST(r.[Date] AS DATETIME)) >= GETDATE()` combine `Date` + `HeureRdv` en un seul instant et le compare au timestamp serveur courant — il retient tout RDV dont le moment exact est futur ou en cours :
   - aujourd'hui à 14h, un RDV de 13h00 (même jour) est **exclu** (déjà passé) ;
   - aujourd'hui à 14h, un RDV de 15h00 (même jour) est **inclus** ;
   - tout RDV de demain ou au-delà est **inclus**, quelle que soit son heure.
  
  La requête retourne 0 à N lignes triées par `Date ASC` puis `HeureRdv ASC` puis `BebeRdvId ASC` (déterminisme — cf. BR-6).
- SFD-8: La réponse JSON de l'endpoint est de la forme :
  ```json
  [
    { "bebeRdvId": 42, "date": "2026-05-27", "heureRdv": "15:30", "titre": "Rendez-vous pédiatre", "message": "Maman vient chercher Lina · départ anticipé" },
    { "bebeRdvId": 43, "date": "2026-05-27", "heureRdv": "16:00", "titre": null, "message": "Sortie au parc · autorisation signée" }
  ]
  ```
  Les noms de champ sont en `camelCase` (cf. library-and-stack §6.bis.3) en miroir des noms TS frontend. Les valeurs NULL backend sont sérialisées `null` JSON (cf. BR-10 — affichage UI sans `null` ni `undefined` visible). Les types `time` SQL (`HeureRdv`) sont sérialisés `"HH:MM"` (24h, sans secondes ni TZ — cf. BR-12).
- SFD-9: Côté UI, chaque RDV est rendu sous forme d'une carte horizontale fidèle au markup existant `<a class="event">` de `9-1-Spec-Bebe-Detaile.html` (lignes 446-454). Layout en 4 zones (de gauche à droite) :
  1. **Pastille date** (`.event__date`) — bloc compact carré affichant `mois` (3-lettres FR uppercase — ex. `MAI`, `JUI`, `OCT`) au-dessus de `jour` (2 chiffres — ex. `13`, `06`) ; valeurs extraites côté frontend depuis le champ `date` du payload (cf. BR-4)
  2. **Bloc texte central** (`.event__body`) — sur deux lignes : `<b>{titre}</b>` en gras suivi de `<span>{message}</span>` en texte secondaire ; **si `titre` est NULL**, seul le `<span>{message}</span>` est affiché (la balise `<b>` est omise — pas de chaîne `null` ni de placeholder) ; **si les deux sont NULL** (cas dégradé, FEAT future de création garantira la présence d'au moins un des deux), un dash `—` est affiché
  3. **Heure** (`.event__time`) — `HH:MM` en font-mono à droite du bloc texte
  4. **Actions** — deux boutons icône à droite : `Modifier` (icône crayon, SVG inline cf. mockup) et `Supprimer` (icône corbeille, SVG inline) ; le chevron droit `.event__chev` du mockup statique est **supprimé** au profit de ces deux actions explicites
- SFD-10: La couleur de fond de chaque carte est **déterministe** mais visuellement variée — calculée côté frontend par `BebeRdvId mod 3` :
  - `0` → variante par défaut (`.event` du CSS isolé — fond crème pastel)
  - `1` → variante `.event--butter` (fond beurre / jaune pastel)
  - `2` → variante `.event--sage` (fond sauge / vert pastel)
  
  Aucune autre variante (`coral`, `sky`, etc.) n'est utilisée dans cette FEAT — le pool est limité à 3 par décision design (cf. BR-9). La couleur est **purement cosmétique** : elle n'a aucune signification métier (priorité, urgence, catégorie) — l'utilisateur a explicitement écarté toute corrélation sémantique avec la couleur (« couleurs aléatoires »).

### Onglet `RDV` — états d'affichage

- SFD-11: Pendant le chargement (`GET` en cours), le panneau `[data-pane="rdv"]` affiche un état de squelette / spinner ; aucune donnée placeholder ne doit être visible (symétrique de spec-bebe-detaille SFD-4).
- SFD-12: Si la liste retournée est vide (`[]`), un état empty-state remplace la liste : un texte centré `Aucun rendez-vous à venir` (italique, couleur secondaire) ; le FAB `+` reste affiché (l'utilisateur peut créer un RDV malgré la liste vide). Aucune carte vide / fantôme n'est rendue. **Mise à jour 2026-05-27** — wording corrigé : « pour aujourd'hui » → « à venir » (cohérent avec le filtre étendu `(Date + HeureRdv) >= GETDATE()`).
- SFD-12bis: Si le `GET` échoue (timeout, 5xx, network error), un message d'erreur générique remplace la liste : `Impossible de charger les rendez-vous` (texte centré) + bouton `Réessayer` (re-déclenche le `GET`). Le FAB `+` reste affiché et fonctionnel (la redirection ne dépend pas du `GET` initial).
- SFD-12ter: Le badge compteur de l'onglet (cf. spec-bebe-detaille SFD-8 — initialement valeur statique en dur `2`) reflète désormais **dynamiquement** la longueur de la liste retournée par le `GET` : `0` → badge masqué ; `≥ 1` → badge affiché avec le nombre. La mise à jour du badge est synchrone avec l'arrivée du payload (post-`GET`) ou avec la suppression locale (cf. SFD-13).

### Suppression d'un RDV (action `Supprimer`)

- SFD-13: Le bouton `Supprimer` (icône corbeille) de chaque card déclenche, au clic, l'ouverture d'une **modale de confirmation** (dialogue modal centré) :
  - Titre : `Supprimer ce rendez-vous ?`
  - Corps : `{Titre ou Message} · {HH:MM}` (libellé identifiant — récap du RDV concerné)
  - Actions : bouton `Annuler` (secondaire) + bouton `Supprimer` (danger / coral)
  
  L'annulation ferme la modale sans envoyer d'appel backend. La confirmation déclenche :
  1. Mise à jour optimiste — la card est retirée du DOM immédiatement et le badge compteur est décrémenté
  2. Appel `DELETE /api/contrats/{ContratId}/rdv/{BebeRdvId}` (body vide)
  3. En cas de succès (`204 No Content`) — aucune action UI supplémentaire (l'optimistic update est conservé)
  4. En cas d'échec (`4xx` ou `5xx` ou network error) — rollback : la card est ré-insérée à sa position d'origine (ordre `HeureRdv ASC` préservé), le badge est ré-incrémenté, un toast `Suppression impossible — réessayez` est affiché
- SFD-14: Le backend exécute la requête SQL paramétrée :
  ```sql
  DELETE FROM dbo.BebeRdv
   WHERE BebeRdvId = @BebeRdvId
     AND ContratId IN (
       SELECT ContratId FROM dbo.Contrat
        WHERE ContratId = @ContratId
          AND EmployeeId = @SessionEmployeeId
     );
  ```
  La sous-requête garantit qu'aucun RDV n'est supprimé hors du périmètre de l'employé connecté (anti-cross-tenant — cf. BR-2, BR-3). Si `@@ROWCOUNT = 0` après l'exécution (RDV inexistant OU hors périmètre), le backend retourne **404 Not Found** (jamais 403 — anti-énumération). Si `@@ROWCOUNT = 1`, retour `204 No Content`. Pas de cas `> 1` possible (PK unique sur `BebeRdvId`).

### Modification d'un RDV (action `Modifier`) — redirect vers FEAT future

- SFD-15: Le bouton `Modifier` (icône crayon) de chaque card déclenche, au clic, une **navigation SPA** vers `/bebes/{ContratId}/rdv/{BebeRdvId}` (route nommée par cette FEAT — implémentation out of scope, cf. SFD-16). Aucun appel backend n'est envoyé au clic — la cible de redirection charge ses propres données.

### Création d'un RDV (FAB `+`) — redirect vers FEAT future

- SFD-16: Un FAB `+` (Floating Action Button — bouton flottant rond, bas droite de l'écran, icône `+`) est rendu en permanence sur le panneau `[data-pane="rdv"]` (à l'identique du mockup statique lignes 498-500 — réutilisation du markup `<button class="fab">`). Un clic sur le FAB déclenche une navigation SPA vers `/bebes/{ContratId}/rdv/nouveau` (route nommée par cette FEAT — implémentation out of scope). Aucun appel backend n'est envoyé.
- SFD-17: Les routes `/bebes/{ContratId}/rdv/nouveau` (création) et `/bebes/{ContratId}/rdv/{BebeRdvId}` (édition) ne sont **pas implémentées par cette FEAT** : tout clic sur un bouton `Modifier` ou sur le FAB `+` déclenche bien la navigation SPA, mais l'écran cible est traité par une **FEAT future dédiée** (`spec-bebe-rdv-edit` ou équivalent — non créée dans ce périmètre). Pendant la phase d'absence de cette FEAT future, la cible affichera par défaut la page 404 / not-found du routeur SPA — comportement acceptable pour la livraison de cette FEAT (cf. `## Out of Scope`).

### Liens et extensions

- SFD-18: La maquette `9-1-Spec-Bebe-Detaile.html` (panneau `[data-pane="rdv"]`, lignes 435-502) reste la **maquette de référence** ; le markup HTML existant (`<section class="pane" data-pane="rdv">`, `<div class="section-label">`, `<a class="event">`, `<div class="event__date">`, `<div class="event__body">`, `<div class="event__time">`, `<button class="fab">`) est **réutilisé tel quel** côté JSX — seul son contenu devient dynamique et les boutons `Modifier`/`Supprimer` remplacent le chevron `.event__chev`. La section `<div class="section-label">Passé</div>` et toutes les cartes `event--past` du mockup statique sont **supprimées** (le filtre serveur `(Date + HeureRdv) >= GETDATE()` ne retourne pas d'historique passé). Le mockup statique avait une sous-section « Aujourd'hui » et une sous-section « Demain » — la FEAT 13 rend désormais **une seule liste plate** triée chronologiquement (Date ASC, HeureRdv ASC) qui peut contenir des RDV d'aujourd'hui ET des jours futurs. Aucun regroupement par jour n'est introduit dans cette FEAT (extension cosmétique future).
- SFD-19: Le `section-label` `Rendez-vous` est **conservé** au-dessus de la liste, avec le bouton `Modifier` qui pointait dans le mockup statique vers `10-planning-enfant.html` (cf. ligne 440). Dans cette FEAT, ce bouton `Modifier` (cosmétique global au panneau, distinct des boutons `Modifier` par card de SFD-15) reste affiché et redirige vers la **route SPA de gestion globale des RDV** — qui est, pour cette FEAT, simplement `/bebes/{ContratId}/rdv/nouveau` (création d'un nouveau RDV — équivalent fonctionnel du FAB `+`). Toute amélioration de cette navigation (page de gestion multi-RDV, historique, calendrier complet) est out of scope.

## Business Rules

- BR-1: L'endpoint `GET /api/contrats/{ContratId}/rdv` exécute la requête SQL canonique de SFD-7 — paramétrée (`@ContratId`, `@SessionEmployeeId`), avec `INNER JOIN dbo.Contrat` pour propager le filtre de propriété ; aucune concaténation de chaîne autorisée (anti-injection SQL).
- BR-2: `@SessionEmployeeId` provient exclusivement de la variable singleton de session de l'employé connecté (cf. spec-bebe-detaille BR-2) ; aucun paramètre de requête utilisateur ne peut le surcharger.
- BR-3: Si le contrat n'existe pas OU appartient à un autre employé, l'endpoint `GET` retourne une **liste vide `[]`** (cohérent avec « 0 RDV à afficher » — symétrique du comportement 404 sur `GET /api/contrats/{ContratId}` de spec-bebe-detaille BR-3 dans la mesure où l'absence du contrat est déjà signalée par le 404 de la fiche détaillée parente — donc on ne réatteint pas l'endpoint RDV depuis un état illégal). L'endpoint `DELETE` retourne **404 Not Found** quand `@@ROWCOUNT = 0` (jamais 403 — anti-énumération d'ID).
- BR-4: La pastille `MOIS / JOUR` est calculée côté frontend depuis le champ `date` du payload :
  - `MOIS` : 3 premières lettres du nom du mois en français, uppercase. Pool fermé : `JAN, FEV, MAR, AVR, MAI, JUI, JUL, AOU, SEP, OCT, NOV, DEC`. Aucune i18n dans cette FEAT.
  - `JOUR` : `getDate()` formaté sur 2 chiffres (zero-pad — ex. `06`, `13`, `28`).
- BR-5: La requête `GET` filtre **systématiquement** côté serveur sur `(Date + HeureRdv) >= GETDATE()` (cf. SFD-7 — clause `DATEADD(SECOND, DATEDIFF(SECOND, '00:00:00', r.HeureRdv), CAST(r.[Date] AS DATETIME)) >= GETDATE()`) — jamais de filtre transmis par le client (anti-tampering, cohérence inter-utilisateur sur la définition de « maintenant »). Aucun paramètre `?date=...`, `?from=...`, `?to=...` ni équivalent n'est accepté (extension future). **Mise à jour 2026-05-27** — l'ancienne règle `Date = CAST(getdate() AS DATE)` (filtre strict sur le jour courant) est **révoquée** : elle masquait les RDV programmés au-delà du jour J, ce qui rendait inutile toute planification future. Le nouveau filtre retient tous les RDV dont le moment exact n'est pas encore passé.
- BR-6: Les RDV sont retournés triés par `Date ASC` puis `HeureRdv ASC` côté serveur (ORDER BY SQL — pas de re-tri côté UI). Si deux RDV ont la même `Date` et la même `HeureRdv` (cas autorisé par l'absence de contrainte d'unicité métier — cf. SFD-4), l'ordre tertiaire est `BebeRdvId ASC` (déterministe).
- BR-7: Le payload JSON est sérialisé en `camelCase` (cf. library-and-stack §6.bis.3) en miroir des noms TS frontend : `bebeRdvId`, `date`, `heureRdv`, `titre`, `message`. Les types SQL `time` sont sérialisés `"HH:MM"` (24h, sans secondes ni TZ — cf. BR-12). Les valeurs NULL backend sont sérialisées `null` JSON.
- BR-8: Côté UI, si `titre` est `null`, la balise `<b>` du bloc `.event__body` est **omise** (pas de chaîne `null` ni d'espace réservé `—` à la place du titre) ; seul `<span>{message}</span>` est rendu. Si `message` est `null` ET `titre` est non-null, seul `<b>{titre}</b>` est rendu. Si les deux sont `null` (cas dégradé — la FEAT future de création garantira la présence d'au moins un des deux), un dash `—` est affiché en `.event__body` (jamais `null` visible utilisateur).
- BR-9: La couleur de fond de chaque card est strictement déterminée par `BebeRdvId mod 3` (pool de 3 variantes — défaut, butter, sage — cf. SFD-10) ; aucune corrélation métier (priorité, urgence, catégorie). Le choix de la couleur n'est **pas** persisté en base — il est purement calculé côté UI à partir du `bebeRdvId` reçu. Conséquence : la même carte garde sa couleur entre deux rechargements (déterministe), mais si le `BebeRdvId` change (suppression + recréation), la couleur peut différer — comportement assumé.
- BR-10: Les valeurs NULL backend sont affichées comme contenu omis ou dash `—` côté UI (jamais `null` ou `undefined` visible utilisateur — cohérent avec spec-bebe-detaille BR-10).
- BR-11: Le bouton `Supprimer` ne lance **jamais** d'appel `DELETE` sans confirmation préalable via modale (cf. SFD-13). Aucune action destructive sans double opt-in.
- BR-12: La colonne SQL `HeureRdv` (`time`) est stockée et sérialisée TZ-naive en fuseau serveur local (cohérent avec `Contrat.{Jour}Debut/Fin` et `RapportJournee.HeureArrivee/HeureDepart` — cf. spec-bebe-detaille BR-8, spec-arrivees-departs SFD-3). Aucune conversion TZ client n'est faite (le navigateur peut être dans n'importe quel fuseau — l'heure affichée reste l'heure du serveur).
- BR-13: Le badge compteur de l'onglet `RDV` reflète la longueur du dernier payload `GET` reçu, mise à jour optimistement à chaque suppression locale (cf. SFD-12ter, SFD-13). Si le `GET` n'a jamais été déclenché (utilisateur n'a pas cliqué sur l'onglet `RDV`), le badge est **masqué** (pas de valeur `0` figée — économie cognitive). Aucun pré-fetch en background pour pré-remplir le badge.
- BR-14: Les routes SPA `/bebes/{ContratId}/rdv/nouveau` et `/bebes/{ContratId}/rdv/{BebeRdvId}` sont **réservées** par cette FEAT mais leur implémentation est out of scope. La FEAT future qui les câblera devra : (1) pré-remplir le formulaire en mode édition depuis `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` (endpoint à créer) ; (2) exécuter `POST` (création) ou `PUT` (édition) avec validation `Titre ≤ 100 chars`, `Message ≤ 500 chars`, `HeureRdv` au format `HH:MM` ; (3) rediriger après succès vers `/bebes/{ContratId}` onglet `RDV` actif. Cette FEAT ne couvre **aucun** de ces 3 points.
- BR-15: La table `dbo.BebeRdv` est créée avec un index non-clustered `IX_BebeRdv_ContratId_Date` sur `(ContratId, Date)` pour optimiser la requête liste. Aucun index supplémentaire n'est ajouté (extension future si volume justifie).
- BR-16: Aucune information technique (stack trace, identifiant interne, exception SQL) n'est exposée dans les messages d'erreur visibles à l'utilisateur (cohérent avec spec-bebe-detaille BR-24).
- BR-17: Si le design system actif (`ui/shadcn`) fournit des composants équivalents (Dialog / AlertDialog pour la modale de confirmation, Button, IconButton), ils DOIVENT être utilisés en priorité (cf. spec-bebe-detaille BR-25) ; le CSS isolé du mockup `9-1-Spec-Bebe-Detaile.html` ne complète que pour atteindre la fidélité visuelle des cards `.event` (pastille, layout, couleurs).
- BR-18: La navigation SPA des boutons `Modifier` et du FAB `+` utilise le mécanisme du routeur frontend actif (cf. spec-bebes BR-4) — l'usage de `<a href>` brut est interdit pour ces actions (un `<a>` peut rester dans le markup statique de l'icône mais le clic doit être intercepté par le routeur — symétrique du chevron du mockup remplacé par les nouveaux boutons).
- BR-19: La spec **complète `spec-bebe-detaille`** : la valeur statique du badge `RDV` (`2` en dur — cf. spec-bebe-detaille SFD-34) est **remplacée** par la valeur dynamique calculée selon BR-13. La cohérence des autres SFD / BR / AC de spec-bebe-detaille (BR-22 — onglets `Rapport du jour` et `Rendez-vous` sans appel backend) est **rompue** pour l'onglet `Rendez-vous` uniquement ; spec-bebe-detaille BR-22 reste applicable pour l'onglet `Rapport du jour` (jusqu'à ce que `spec-rapport-sms` FEAT 12 la complète à son tour).

## Acceptance Criteria

- AC-1: La table `dbo.BebeRdv` existe en base avec le DDL exact de SFD-3 (PK `BebeRdvId IDENTITY`, FK `ContratId` → `Contrat.ContratId`, index `IX_BebeRdv_ContratId_Date`) ; le fichier `workspace/output/db/schema.{json,md}` est régénéré et liste la nouvelle table.
- AC-2: L'onglet `RDV` de `/bebes/{ContratId}` (cf. spec-bebe-detaille AC-5) ne déclenche **aucun** appel backend tant qu'il n'est pas cliqué (économie d'un round-trip pour les utilisateurs qui consultent uniquement `Informations` ou `Rapport du jour`).
- AC-3: Au clic sur l'onglet `RDV`, le frontend envoie **une seule** requête `GET /api/contrats/{ContratId}/rdv` (vérifiable côté Network DevTools) ; aucun autre appel backend n'est déclenché par le rendu de la liste.
- AC-4: Le backend exécute exactement la requête SQL paramétrée de SFD-7 (`SELECT ... FROM BebeRdv INNER JOIN Contrat WHERE ContratId = @x AND Date = CAST(getdate() AS DATE) AND EmployeeId = @session ORDER BY HeureRdv ASC`) — vérifiable côté logs SQL ou test d'intégration.
- AC-5: La réponse JSON est un tableau (jamais un objet enveloppant `{ data: [...] }`) trié par `heureRdv ASC` ; chaque élément contient `bebeRdvId, date, heureRdv, titre, message` (cf. SFD-8, BR-7).
- AC-6: Si le contrat n'appartient pas à l'employé connecté, le `GET` retourne `[]` (liste vide — pas d'exposition de l'existence du contrat). Le `DELETE` sur un RDV hors périmètre retourne **404 Not Found** (jamais 403).
- AC-7: Chaque card RDV affiche, de gauche à droite : pastille `MOIS / JOUR` (mois 3-lettres FR uppercase, jour 2 chiffres) → bloc texte `<b>{titre}</b><span>{message}</span>` (avec règle d'omission BR-8) → heure `HH:MM` en font-mono → bouton `Modifier` (icône crayon) + bouton `Supprimer` (icône corbeille).
- AC-8: Si `titre` est NULL, la balise `<b>` est omise (vérifiable côté DOM — la card ne contient qu'un `<span>{message}</span>` dans `.event__body`).
- AC-9: La couleur de fond de chaque card est l'une des 3 variantes (`event`, `event--butter`, `event--sage`) sélectionnée par `BebeRdvId mod 3` (déterministe — vérifiable en rechargeant deux fois la page : même couleur pour le même RDV).
- AC-10: Pendant le `GET` en cours, un état squelette / spinner est visible dans le panneau ; aucune donnée placeholder n'apparaît figée.
- AC-11: Si la liste retournée est vide, un état empty-state `Aucun rendez-vous à venir` remplace la liste ; le FAB `+` reste visible et fonctionnel.
- AC-12: Si le `GET` échoue, un message `Impossible de charger les rendez-vous` + bouton `Réessayer` remplace la liste ; un nouveau clic sur `Réessayer` re-déclenche le `GET`.
- AC-13: Le badge compteur de l'onglet `RDV` (cf. spec-bebe-detaille SFD-8) reflète la longueur du dernier payload : masqué si `0`, affiché avec le nombre sinon. Décrémenté optimistement à chaque suppression locale réussie.
- AC-14: Un clic sur le bouton `Supprimer` d'une card ouvre une modale de confirmation `Supprimer ce rendez-vous ?` avec récap `{Titre ou Message} · {HH:MM}` et deux boutons `Annuler` / `Supprimer`.
- AC-15: Annuler la modale ferme le dialogue sans envoyer d'appel backend ; la card reste en place.
- AC-16: Confirmer la modale retire la card du DOM immédiatement (mise à jour optimiste) et envoie `DELETE /api/contrats/{ContratId}/rdv/{BebeRdvId}` ; en cas de succès `204`, aucune action UI supplémentaire ; en cas d'échec, la card est ré-insérée à sa position d'origine (ordre `HeureRdv ASC` préservé) et un toast `Suppression impossible — réessayez` est affiché.
- AC-17: Le backend exécute la requête `DELETE` paramétrée de SFD-14 avec sous-requête de propriété sur `Contrat.EmployeeId = @SessionEmployeeId` — vérifiable côté logs SQL ; un appel direct avec un `BebeRdvId` d'un autre employé retourne 404 (0 ligne supprimée).
- AC-18: Un clic sur le bouton `Modifier` d'une card déclenche une navigation SPA vers `/bebes/{ContratId}/rdv/{BebeRdvId}` (vérifiable côté router / history) ; aucun appel backend n'est envoyé au clic.
- AC-19: Un clic sur le FAB `+` déclenche une navigation SPA vers `/bebes/{ContratId}/rdv/nouveau` ; aucun appel backend n'est envoyé.
- AC-20: La page cible des redirections `Modifier` et FAB `+` (`/bebes/{ContratId}/rdv/...`) n'est **pas implémentée** par cette FEAT — l'utilisateur arrive sur la page 404 du routeur (acceptable pour cette FEAT, cf. Out of Scope).
- AC-21: Les RDV **déjà passés** (combinaison `Date + HeureRdv < now()` serveur) ne sont jamais retournés par le `GET`. Vérifiable en : (a) insérant manuellement un RDV à `Date = today, HeureRdv = current_hour - 1` puis en vérifiant son absence dans la réponse ; (b) insérant un RDV à `Date = today - 1` (n'importe quelle heure) et vérifiant son absence ; (c) insérant un RDV à `Date = today, HeureRdv = current_hour + 1` et vérifiant sa présence ; (d) insérant un RDV à `Date = today + 7, HeureRdv = 03:00` et vérifiant sa présence.
- AC-22: Aucun paramètre client (`?date=...`, `?from=...`, `?to=...`, `?include_past=true`, etc.) n'est accepté par l'endpoint `GET` — toute query-string est ignorée, le filtre `(Date + HeureRdv) >= GETDATE()` est purement serveur (anti-tampering BR-5).
- AC-23: La spec ne dégrade aucun comportement existant de spec-bebe-detaille : l'onglet `Informations` reste fonctionnel et atomique (1 seul appel `GET /api/contrats/{ContratId}` au chargement de la fiche), l'onglet `Rapport du jour` reste statique (ou alimenté par spec-rapport-sms FEAT 12 si déjà déployée), le retour topbar `/bebes` reste fonctionnel, la session expirée déclenche toujours un 401 + redirect `/login`.

## Dependencies

- **spec-bebe-detaille** (`9-spec-bebe-detaille`) : **étendue** par cette FEAT — SFD-32 (interface statique → dynamique), SFD-33 (« aucune persistance » → CRUD partiel), SFD-34 (badge statique → badge dynamique), FD-11 (interface statique → liste dynamique + delete fonctionnel + redirects). Le markup du panneau `[data-pane="rdv"]` de `9-1-Spec-Bebe-Detaile.html` (lignes 435-502) reste la maquette de référence. La spec-bebe-detaille BR-22 (« onglets Rapport du jour et Rendez-vous sans appel backend ») est partiellement rompue — uniquement pour l'onglet `Rendez-vous`.
- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employé connecté ; redirection vers `/login` en l'absence de session valide ; 401 backend déclenche le redirect côté frontend.
- **spec-bebes** (`4-spec-bebes`) : l'accès à `/bebes/{ContratId}` (porte d'entrée vers l'onglet `RDV`) passe par le clic sur une card bébé de `/bebes` ; BR-4 (navigation SPA via routeur) reste applicable pour les redirections `Modifier` et FAB `+`.
- **DDL nouvelle table `dbo.BebeRdv`** : pré-requis externe (DBA OU arch Phase B) — la matérialisation `dev-backend` exige la table en base et le `workspace/output/db/schema.{json,md,diff.md}` régénéré.
- **spec-bebe-rdv-edit** (FEAT future — non créée) : implémentera les routes `/bebes/{ContratId}/rdv/nouveau` et `/bebes/{ContratId}/rdv/{BebeRdvId}` (formulaire création / édition, `POST` / `PUT`, validation). Sans cette FEAT future, les redirections de cette FEAT 13 tombent sur la 404 du routeur — acceptable (cf. Out of Scope).

## Functional Deliverables

- FD-1: DDL `CREATE TABLE dbo.BebeRdv` (cf. SFD-3) appliqué en base + index `IX_BebeRdv_ContratId_Date` + régénération de `workspace/output/db/schema.{json,md,diff.md}` reflétant la nouvelle table.
- FD-2: Endpoint backend `GET /api/contrats/{ContratId}/rdv` exécutant la requête SQL paramétrée de SFD-7 (`INNER JOIN Contrat` pour propriété, filtre temporel combiné `DATEADD(SECOND, DATEDIFF(SECOND, '00:00:00', HeureRdv), CAST(Date AS DATETIME)) >= GETDATE()`, `ORDER BY Date ASC, HeureRdv ASC, BebeRdvId ASC`), retournant un tableau JSON `[{ bebeRdvId, date, heureRdv, titre, message }, ...]` (camelCase, valeurs NULL → `null`, `time` → `"HH:MM"`).
- FD-3: Endpoint backend `DELETE /api/contrats/{ContratId}/rdv/{BebeRdvId}` exécutant la requête SQL paramétrée de SFD-14 (sous-requête de propriété sur `Contrat.EmployeeId`), retournant `204 No Content` en cas de succès et `404 Not Found` si 0 ligne supprimée.
- FD-4: Lazy-fetch côté frontend : le `GET /api/contrats/{ContratId}/rdv` est déclenché au **clic** sur l'onglet `RDV` (pas au chargement initial de la fiche détaillée) ; aucune pré-récupération en background.
- FD-5: Rendu dynamique du panneau `[data-pane="rdv"]` : pour chaque RDV du payload, une card `.event` avec pastille `MOIS / JOUR` (BR-4), bloc texte `<b>{titre}</b><span>{message}</span>` (avec règles d'omission BR-8), heure `HH:MM` en font-mono, deux boutons `Modifier` + `Supprimer` ; couleur de fond déterministe par `BebeRdvId mod 3` (BR-9). Markup conservé tel quel depuis `9-1-Spec-Bebe-Detaile.html` lignes 446-484 (modulo remplacement du chevron par les deux boutons d'action).
- FD-6: État empty-state (`Aucun rendez-vous à venir`) si liste vide ; état d'erreur (`Impossible de charger les rendez-vous` + bouton `Réessayer`) si `GET` échoue ; état squelette / spinner pendant le `GET` en cours.
- FD-7: Modale de confirmation au clic sur `Supprimer` (titre `Supprimer ce rendez-vous ?`, corps récap, boutons `Annuler` / `Supprimer`) — utilisation du composant `Dialog` / `AlertDialog` du design system actif si disponible.
- FD-8: Suppression optimiste côté frontend (card retirée du DOM immédiatement, badge décrémenté) avec rollback en cas d'échec backend (card ré-insérée à sa position, toast d'erreur).
- FD-9: FAB `+` (bouton flottant rond, bas droite) + bouton `Modifier` par card déclenchent une navigation SPA vers `/bebes/{ContratId}/rdv/nouveau` et `/bebes/{ContratId}/rdv/{BebeRdvId}` respectivement (aucun appel backend, aucun composant cible implémenté dans cette FEAT).
- FD-10: Badge compteur dynamique de l'onglet `RDV` : masqué si liste vide, affiché avec le nombre sinon ; mise à jour optimiste à chaque suppression locale réussie (cf. SFD-12ter, BR-13). Remplace la valeur statique `2` du mockup et de spec-bebe-detaille SFD-34.
- FD-11: Gestion des erreurs (4xx / 5xx / network), des sessions expirées (401 → redirect `/login` cf. spec-connexion), et du filtre temporel `(Date + HeureRdv) >= GETDATE()` strict côté serveur (anti-tampering BR-5).

## Out of Scope

- **Écran de création / modification d'un rendez-vous** (`/bebes/{ContratId}/rdv/nouveau` et `/bebes/{ContratId}/rdv/{BebeRdvId}`) — formulaire, validation, endpoints `POST /api/contrats/{ContratId}/rdv` et `PUT /api/contrats/{ContratId}/rdv/{BebeRdvId}`, redirection retour — **couvert par une FEAT future dédiée** (cf. SFD-15, SFD-16, SFD-17, BR-14). Les routes sont nommées par cette FEAT mais leur composant cible tombe sur la 404 du routeur tant que la FEAT future n'est pas livrée.
- **Endpoint `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}`** (récupération d'un RDV unique pour pré-remplissage du formulaire d'édition) — à créer par la FEAT future de création / édition.
- **Filtrage borné (`?from=...&to=...`, vue mensuelle, vue semaine)** — cette FEAT filtre côté serveur sur `(Date + HeureRdv) >= GETDATE()` (RDV futurs uniquement, illimité dans le futur — cf. BR-5, AC-21, AC-22). L'ancien comportement « jour J seul » est révoqué (correction 2026-05-27). Extension future possible avec bornes paramétrables (`?from=...&to=...`) ou vue calendrier mois/semaine — toujours hors scope de cette FEAT.
- **Récurrence des RDV** (RDV hebdomadaires, mensuels) — pas de colonne `Recurrence` ni de logique de duplication dans cette FEAT ; chaque RDV est une ligne unique en base.
- **Notification aux parents** (SMS, email, push) au moment de la création ou en rappel pré-RDV — out of scope strict (anti-confusion avec `spec-rapport-sms` FEAT 12 qui couvre le rapport du jour, pas les RDV).
- **Conflits de planning** (alerte si deux RDV se chevauchent, ou si un RDV tombe pendant un créneau de repos `JourReposEmploye`) — pas de validation côté FEAT 13.
- **Synchronisation iCal / Google Calendar / Outlook** — out of scope strict.
- **Historique des RDV passés** (`Date < today`) consultable depuis l'UI — les lignes restent en base mais ne sont jamais affichées par cette FEAT.
- **Suppression en cascade** (DELETE CASCADE sur `Contrat.ContratId`) — non requis dans cette FEAT (la suppression d'un contrat est elle-même out of scope global du POC).
- **Colonnes d'audit** (`CreatedAt`, `CreatedBy`, `UpdatedAt`, `UpdatedBy`) sur `dbo.BebeRdv` — extension future.
- **Catégorisation des RDV** (médical, sortie, administratif) avec icône / couleur correspondante — la couleur reste arbitraire (BR-9, SFD-10).
- **Pièces jointes** (PDF d'ordonnance, photo d'autorisation parentale) — out of scope.
- **Export / partage** (PDF de la liste, lien public, calendrier ICS téléchargeable) — out of scope.
- **Multi-device / synchronisation temps réel** entre deux sessions du même employé — un RDV créé sur device A apparaît sur device B uniquement après un nouveau `GET` (re-clic sur l'onglet ou re-chargement de la page).
- **Permissions parents** (consultation côté Employeur, validation d'un RDV proposé) — out of scope strict (le Parent ne consulte pas l'app dans le POC).
- **Drag & drop pour réordonner / déplacer un RDV dans le temps** — out of scope.
- **Recherche / filtre textuel** sur `Titre` ou `Message` — out of scope (volume attendu < 10 RDV / jour ne justifie pas).
- **Suppression en masse** (cocher plusieurs RDV, supprimer la sélection) — out of scope.
- **Confirmation post-suppression** (toast `RDV supprimé · Annuler ?` avec undo) — out of scope ; la suppression est définitive après confirmation modale (BR-11).
- **Bouton `Modifier` global du `section-label` Rendez-vous** (cf. SFD-19, mockup ligne 440) — redirige vers `/bebes/{ContratId}/rdv/nouveau` par défaut dans cette FEAT, équivalent fonctionnel du FAB `+`. Toute amélioration (page de gestion multi-RDV avec historique, calendrier complet, vue mensuelle) est out of scope.
