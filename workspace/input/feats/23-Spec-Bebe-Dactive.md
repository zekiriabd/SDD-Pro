# Spec: bebe-dactive (statut contrat sur liste enfants + nightly job)

FEAT ID: 23-Spec-Bebe-Dactive
Spec ID: spec-bebe-dactive
Status: Draft

> **Pré-requis schéma** : colonne `dbo.Contrat.BebeStatut TINYINT NOT NULL DEFAULT 1` **déjà introduite par FEAT 22** (cf. `spec-cloture-contrat` SFD-3, DDL canonique idempotent `IF NOT EXISTS`). Cette FEAT 23 **ne touche pas le DDL** — elle exploite la colonne existante en (a) étendant les chemins d'écriture INSERT/UPDATE pour calculer la valeur initiale `1` ou `2`, (b) étendant le rendu de la liste enfants pour différencier visuellement les contrats en attente, (c) ajoutant un job SQL serveur (cron / SQL Server Agent) qui bascule chaque nuit les lignes `BebeStatut = 1` vers `2` quand `DateEffetContrat <= GETDATE()`.

## Context

L'écran principal de l'application — `/bebes` (liste des enfants gardés — hérité de FEAT 4 `spec-bebes`, étendu par FEAT 11 `spec-arrivees-departs` puis FEAT 15 `spec-statut-bebes`) — affiche aujourd'hui toutes les cards des bébés actifs de l'employée connectée comme si elles étaient **immédiatement en garde**. Les colonnes lues (`RapportStatut`, `JourReposEmploye`, `BebeRdv`) supposent toutes implicitement que la relation employé/famille est **active dès l'INSERT du contrat** dans `dbo.Contrat`. Ce postulat tombe dans la pratique : un contrat de garde est typiquement **signé plusieurs semaines avant le premier jour d'accueil effectif** (négociation, période d'essai administrative, démarches CAF/Pajemploi). Entre l'INSERT et `DateEffetContrat`, le bébé n'est **pas encore présent** chez l'employée — afficher une card pleinement interactive avec les boutons `Arrivée` / `Départ` / `Appeler les parents` est **trompeur** (l'employée pourrait pointer une arrivée pour un bébé qu'elle n'a pas encore commencé à garder, ce qui pollue les rapports historiques de FEAT 11).

Parallèlement, la FEAT 22 `spec-cloture-contrat` a introduit la colonne `dbo.Contrat.BebeStatut TINYINT NOT NULL DEFAULT 1` avec un domaine de valeurs `{1, 2, 3}` documenté mais dont seule la valeur `3` (clôturé) est aujourd'hui écrite (par le POST `/cloturer`). Les valeurs `1` (en attente) et `2` (en garde) sont à ce jour **conceptuelles** — toutes les lignes préexistantes ont la valeur DEFAULT `1` (issue de la migration DDL) ce qui est sémantiquement incorrect (les contrats déjà actifs en production devraient être à `2`). Cette FEAT 23 **donne une sémantique opérationnelle complète** à `BebeStatut` :

- **`1` = en attente** : contrat signé/inséré côté backend mais `DateEffetContrat > date courante` — le bébé n'est pas encore en garde, la card de `/bebes` est rendue en mode désaturé/blocué avec le libellé `Accueil prévu le {DateEffetContrat}`, aucun bouton d'action n'est interactif.
- **`2` = en garde** : `DateEffetContrat <= date courante` ET `BebeStatut ≠ 3` — le bébé est effectivement gardé, la card est rendue avec tous les boutons interactifs hérités de FEAT 11/15.
- **`3` = clôturé** : (déjà géré par FEAT 22) — la card est exclue de `/bebes` (filtre `WHERE BebeStatut <> 3` posé par FEAT 22 SFD-15).

Le mockup canonique est `workspace/input/ui/23-1-Spec-Bebe-Dactive.html`. Il présente 3 cards exemple : (1) **Lina Bouchet** — `BebeStatut = 2`, en garde, arrivée + départ saisis, RDV + rapport visibles ; (2) **Tom Lefèvre** — `BebeStatut = 2`, en garde, rapport à compléter ; (3) **Noé Marin** — `BebeStatut = 1`, contrat signé mais accueil prévu le 16 juin 2025, card **désaturée avec classe `.baby-card--pending`** (avatar en grayscale, fond gris clair, libellé `Accueil prévu le 16 juin 2025`, aucun bouton `Arrivée/Départ/Appeler` rendu, aucun chevron de navigation vers la fiche détaillée).

La FEAT 23 introduit 3 chantiers indépendants mais cohérents :

1. **Chemins d'écriture INSERT/UPDATE étendus** sur `dbo.Contrat` (FEAT 6 `spec-souscrire-contrat` et FEAT 9 `spec-bebe-detaille` édition) : le frontend calcule `BebeStatut` côté client à partir de `DateEffetContrat` saisie + date système client (`new Date()`) et passe la valeur dans le body POST/PUT vers le backend. Backend valide la valeur (∈ {1, 2}) et l'écrit dans la colonne. Aucun recalcul backend (la date client fait foi à l'INSERT — décision documentée cf. BR-3).
2. **Rendu différencié dans `/bebes`** : le payload existant `GET /api/bebes` (FEAT 11/15) est étendu de 2 colonnes (`bebeStatut`, `dateEffetContrat`) ; le frontend rend la card en mode `baby-card--pending` (cf. mockup card 3) quand `bebeStatut === 1`, en mode normal sinon. Tri par `BebeStatut ASC, Prenom ASC` (les contrats en garde apparaissent **en premier**, les contrats en attente regroupés en fin de liste).
3. **Job SQL nightly de bascule `1 → 2`** : SQL Server Agent job (ou cron + script T-SQL si SQL Agent indisponible) tournant chaque nuit à **00:30** serveur, exécutant un UPDATE bulk paramétré `UPDATE dbo.Contrat SET BebeStatut = 2 WHERE BebeStatut = 1 AND DateEffetContrat <= CAST(GETDATE() AS DATE)`. Le job sert de **filet de sécurité serveur** : si un client a une horloge faussée, ou si un contrat est en attente depuis plusieurs jours sans nouvelle interaction utilisateur, la bascule serveur garantit qu'à 00:30 du jour `DateEffetContrat`, le bébé est correctement marqué en garde et la card devient interactive au prochain refresh de `/bebes`.

## Objective

L'employée connectée signe un nouveau contrat via le wizard `/contrats/nouveau` (FEAT 6) en saisissant `DateEffetContrat = 15 août 2026` alors que le jour courant côté navigateur est le 30 mai 2026 → le frontend détecte `DateEffetContrat > today` et envoie le POST `/api/contrats` avec `bebeStatut: 1` dans le body. Le backend INSERT la ligne `Contrat` avec `BebeStatut = 1`. La card de Noé apparaît dans `/bebes` **immédiatement** en mode désaturé `baby-card--pending` avec le libellé `Accueil prévu le 15 août 2026` ; aucun bouton n'est cliquable, le chevron vers la fiche détaillée est retiré ou inerte. L'employée peut continuer à pointer arrivées/départs pour les autres bébés `BebeStatut = 2` (Lina, Tom) sans confusion. Le 14 août 2026 à 23h59, la card de Noé est encore `pending`. À 00h30 du 15 août, le job SQL bascule la ligne à `BebeStatut = 2`. L'employée ouvre `/bebes` le 15 août matin → la card de Noé est désormais en mode normal, les boutons `Arrivée` / `Départ` / `Appeler les parents` sont interactifs, et le pointage peut commencer. En **scenario d'édition**, l'employée modifie un contrat existant via `/contrats/{ContratId}` (FEAT 9 edit mode) en changeant `DateEffetContrat` de `1 juin 2025` à `1 octobre 2026` → le frontend recalcule `bebeStatut = 1` (date future), le backend UPDATE `BebeStatut = 1` côté `Contrat` (sauf si la valeur courante est `3` — cf. BR-6 anti-réouverture). La card du bébé bascule de mode normal vers `pending` au prochain refresh de `/bebes`. En **scenario de clôture** (FEAT 22), `BebeStatut = 3` est posé par `POST /cloturer` — la card disparaît de `/bebes` (filtre existant SFD-15 FEAT 22).

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps de chargement `/bebes` (1 requête SQL existante, payload étendu de ~30 bytes par card avec `bebeStatut` + `dateEffetContrat`) ; temps d'exécution du job SQL nightly (UPDATE bulk sur lignes filtrées par index) ; temps de calcul client `bebeStatut` au save wizard (1 comparaison Date côté JS).
- Target: p95 chargement `/bebes` < 750 ms (hérité FEAT 15, +50 ms tolérés pour 2 colonnes additionnelles dans payload) ; p95 job SQL nightly < 5 secondes sur 10k contrats actifs (UPDATE filtré sur `BebeStatut = 1`, index `Contrat.ContratId` PK suffisant) ; p95 calcul client `bebeStatut` < 1 ms (1 `Date()` instanciation + 1 comparaison).
- Deadline: livraison stack `fullstack/node-react × ui/shadcn × auth/auth-local` au 2026-10-31.

## Non-Functional Constraints (v7.0.0)

- Expected volume: ~5 contrats actifs / employée (≤ 10 en pic), ~0-2 nouveaux contrats signés / employée / mois (faible turnover), ~0-1 contrat modifié via edit / employée / mois ; le job nightly traite **tous** les contrats en attente du tenant (toutes employées confondues) en 1 UPDATE bulk paramétré, volume estimé < 100 lignes basculées par nuit sur la beta Demo entière.
- Performance SLA: p95 chargement `/bebes` < 750 ms (cf. Quantified Goal) ; aucun risque N+1 (1 SELECT unique étendu de 2 colonnes existantes — `BebeStatut` est déjà sur `dbo.Contrat`, `DateEffetContrat` aussi) ; le job nightly utilise un UPDATE bulk paramétré sans curseur, performance O(N) sur les lignes en attente uniquement (filtre `WHERE BebeStatut = 1` minimise le scan).
- Data retention: aucune nouvelle colonne ajoutée par cette FEAT (`BebeStatut` est créée par FEAT 22) ; le job nightly est **idempotent** par construction (re-exécution sur la même journée ne change rien — la 2ème passe matche 0 ligne) ; aucun log d'audit DB des bascules `1 → 2` n'est conservé (la transition est sémantiquement déterministe à partir de `BebeStatut` courant + `DateEffetContrat` — pas d'information perdue).
- Compliance: RGPD — `BebeStatut` est un TINYINT opérationnel non sensible (statut administratif du contrat) ; `DateEffetContrat` est une donnée contractuelle non sensible (date de début de garde, déjà exposée par FEAT 9 dans la fiche détaillée) ; aucune nouvelle donnée personnelle n'est manipulée par cette FEAT ; le job nightly tourne avec le compte service SQL standard, pas de privilege escalation requis.
- Integration: extension des endpoints existants `POST /api/contrats` (FEAT 6) et `PUT /api/contrats/{ContratId}` (FEAT 9) avec acceptation d'un nouveau champ `bebeStatut: number ∈ {1, 2}` dans le body ; extension de l'endpoint existant `GET /api/bebes` (FEAT 11/15) avec 2 colonnes additionnelles dans le payload (`bebeStatut`, `dateEffetContrat`) ; ajout d'un job SQL Server Agent (ou cron + sqlcmd si SQL Agent indisponible) ; aucun nouveau endpoint applicatif ; aucune passerelle externe.
- Degraded mode: si le client envoie un `bebeStatut` invalide (hors `{1, 2}` ou type incorrect), le backend renvoie 400 ProblemDetails et n'écrit pas la ligne ; si le client n'envoie pas du tout le champ `bebeStatut`, le backend **calcule serveur-side une valeur de fallback** via `CASE WHEN DateEffetContrat > CAST(GETDATE() AS DATE) THEN 1 ELSE 2 END` (filet de sécurité backward-compat pour anciens clients non encore migrés cf. BR-4) ; si le job SQL nightly échoue (panne SQL Agent, erreur transactionnelle), une alerte structurée WARN est loguée mais aucune intervention immédiate n'est requise (les cards en attente restent affichées en mode `pending` jusqu'à la prochaine exécution du job — au pire 24h de décalage) ; si le payload `GET /api/bebes` ne contient pas `bebeStatut` (cas conceptuel — backend non encore déployé avec cette FEAT), le frontend dégrade en rendant **toutes** les cards en mode normal (équivalent au comportement pré-FEAT 23, no regression sur FEAT 11/15).

## Actors

- Employée connectée : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session. Seule autorisée à consulter et créer/modifier des contrats dont `Contrat.EmployeeId == session.EmployeeId`. Ses actions wizard (FEAT 6) et edit (FEAT 9) déclenchent l'écriture de `BebeStatut`. Ses actions de pointage (FEAT 11) sont **bloquées** côté UI pour les cards `BebeStatut = 1` (cf. SFD-9).
- Job SQL serveur (acteur système) : non humain, tourne via SQL Server Agent (ou cron + sqlcmd) en mode service avec credentials read/write sur la table `Contrat`. Exécute 1 UPDATE bulk paramétré chaque nuit à 00:30 serveur. Aucun couplage avec la session employée (le job opère cross-tenant sur toutes les lignes `Contrat` filtrées par `BebeStatut = 1 AND DateEffetContrat <= today`). Aucune notification utilisateur n'est déclenchée par le job (les employées découvrent la bascule au prochain refresh de `/bebes`).

## Functional Needs

### Point d'entrée et navigation

- SFD-1: La spec **étend `spec-bebes` (FEAT 4)** et son lineage `spec-arrivees-departs` (FEAT 11) + `spec-statut-bebes` (FEAT 15) : la page `/bebes` est inchangée en terme de route, layout topbar, FAB `Ajouter un enfant`, tabbar bottom ; seul est modifié (a) le **rendu de chaque baby-card** selon `bebeStatut`, (b) l'**ordre de tri** des cards (en garde d'abord), (c) le **payload** de `GET /api/bebes` (2 colonnes en plus).
- SFD-2: Aucune nouvelle route SPA n'est introduite. Aucune route ajoutée à l'API. Le job SQL nightly est **hors du périmètre HTTP** (composant DBA-side, déclenché par SQL Server Agent ou cron système).

### Schéma de données — exploitation `BebeStatut` (existant FEAT 22)

- SFD-3: La colonne `dbo.Contrat.BebeStatut TINYINT NOT NULL DEFAULT 1` est **réutilisée telle quelle** (créée par FEAT 22 SFD-3). Aucune migration DDL supplémentaire requise. Le domaine de valeurs `{1, 2, 3}` est désormais **complet et opérationnel** : la valeur `2` (en garde) est écrite par cette FEAT, la valeur `3` (clôturé) reste exclusive à FEAT 22 POST `/cloturer`, la valeur `1` (en attente) est écrite par cette FEAT à l'INSERT/UPDATE quand `DateEffetContrat > today`.
- SFD-4: La colonne `dbo.Contrat.DateEffetContrat DATE NULL` est **réutilisée telle quelle** (créée par schéma legacy, déjà lue par FEAT 9 SFD-12). Aucune modification de cette colonne par cette FEAT. **Décision intentionnelle** : la nullabilité existante est conservée. Si `DateEffetContrat IS NULL` à l'INSERT, le frontend ne peut pas calculer `bebeStatut` côté client de manière déterministe — dans ce cas le frontend envoie `bebeStatut: 2` par défaut (assomption "contrat déjà en garde" — backward-compat avec les contrats historiques qui n'avaient pas `DateEffetContrat` rempli) ; le backend valide cette logique (cf. BR-3). Un futur durcissement pourra rendre `DateEffetContrat NOT NULL` quand 100% des lignes auront été backfillées.
- SFD-5: **Backfill optionnel one-shot** (recommandé en pre-deploy, non bloquant pour cette FEAT) : exécuter une seule fois en environnement de production le script SQL :
  ```sql
  UPDATE dbo.Contrat
     SET BebeStatut = CASE
       WHEN DateEffetContrat IS NULL THEN 2
       WHEN DateEffetContrat > CAST(GETDATE() AS DATE) THEN 1
       ELSE 2
     END
   WHERE BebeStatut = 1
     AND NOT EXISTS (SELECT 1 FROM dbo.RapportJournee rj WHERE rj.ContratId = Contrat.ContratId);
  ```
  Cette opération met à jour rétroactivement le statut de tous les contrats préexistants à `1` (DEFAULT issu de la migration FEAT 22) qui ne sont en réalité **pas en attente** (date passée ou nulle). Le filtre `NOT EXISTS (... RapportJournee)` est une heuristique défensive — un contrat ayant déjà des rapports historiques est nécessairement déjà en garde, on évite de toucher les contrats déjà actifs même si leur date est curieusement marquée future. Le script est idempotent (re-exécution = no-op fonctionnel). **Charge DBA / déploiement, hors scope agent dev-backend** — à exécuter manuellement.

### Endpoints backend — écriture (POST/PUT `/api/contrats[/{ContratId}]`)

- SFD-6: L'endpoint `POST /api/contrats` (FEAT 6 `spec-souscrire-contrat` FD-7) est **étendu** pour accepter un champ optionnel `bebeStatut: number` dans le body JSON. Validation Zod backend : si présent, `bebeStatut ∈ {1, 2}` (la valeur `3` est **rejetée 400 ProblemDetails** — la clôture n'est jamais initiée à l'INSERT, elle passe exclusivement par FEAT 22 POST `/cloturer`). Si absent (backward-compat clients legacy), le backend calcule la valeur via le `CASE` de SFD-7. La requête SQL INSERT est étendue pour inclure la colonne :
  ```sql
  INSERT INTO dbo.Contrat (
    EmployeeId, EmployeurId, Nom, Prenom, DateNaissance, AccueilRue, ..., ImageUrl,
    BebeStatut
  ) VALUES (
    @EmployeeId, @EmployeurId, @Nom, @Prenom, @DateNaissance, @AccueilRue, ..., @ImageUrl,
    COALESCE(@BebeStatut, CASE WHEN @DateEffetContrat > CAST(GETDATE() AS DATE) THEN 1 ELSE 2 END)
  );
  ```
- SFD-7: L'endpoint `PUT /api/contrats/{ContratId}` (FEAT 9 `spec-bebe-detaille` SFD-12 wizard edit) est **étendu** symétriquement avec acceptation du même champ `bebeStatut` dans le body. La requête SQL UPDATE est étendue :
  ```sql
  UPDATE dbo.Contrat
     SET Nom = @Nom, Prenom = @Prenom, ..., ImageUrl = @ImageUrl,
         BebeStatut = CASE
           WHEN BebeStatut = 3 THEN 3  -- anti-réouverture (BR-6) : un contrat clôturé reste clôturé
           ELSE COALESCE(@BebeStatut, CASE WHEN @DateEffetContrat > CAST(GETDATE() AS DATE) THEN 1 ELSE 2 END)
         END
   WHERE ContratId = @ContratId
     AND EmployeeId = @SessionEmployeeId;
  ```
  La clause `CASE WHEN BebeStatut = 3 THEN 3` garantit que **modifier un contrat clôturé via PUT ne le réouvre jamais** (cf. BR-6, anti-réouverture). Une employée qui édite un contrat clôturé par mégarde voit sa modification appliquée sur les autres colonnes (nom, salaire, horaires…) mais `BebeStatut` reste à `3` — la card ne réapparaît pas dans `/bebes`.
- SFD-8: La valeur retournée par les endpoints POST et PUT (payload de réponse) **n'inclut pas `BebeStatut`** — le frontend re-fetch `/bebes` après save pour récupérer la liste à jour (comportement actuel inchangé). Pas de propagation explicite via push WebSocket / SSE (out of scope, le rafraîchissement manuel suffit pour les volumes attendus, cf. NFC).

### Endpoint backend — lecture (`GET /api/bebes`)

- SFD-9: L'endpoint `GET /api/bebes` (FEAT 11 SFD-5 / FEAT 15 SFD-6 / FEAT 22 SFD-15) est **étendu** par cette FEAT pour ajouter 2 colonnes au payload JSON aplati :
  - `bebeStatut: number ∈ {1, 2}` (la valeur `3` n'apparaît jamais grâce au filtre `WHERE BebeStatut <> 3` de FEAT 22 SFD-15)
  - `dateEffetContrat: string | null` (format ISO `YYYY-MM-DD`, ou `null` si la colonne `Contrat.DateEffetContrat` est NULL en base)
  Requête SQL canonique mise à jour :
  ```sql
  SELECT
      c.ContratId,
      c.Prenom,
      c.Nom,
      c.DateNaissance,
      c.ImageUrl,
      c.DateEffetContrat,        -- nouveau
      c.BebeStatut,              -- nouveau
      r.HeureArrivee,
      r.HeureDepart,
      r.RapportStatut,
      CHARINDEX(
        REPLACE(UPPER(FORMAT(GETDATE(), 'ddd', 'fr-FR')), '.', ''),
        UPPER(c.JourReposEmploye)
      ) AS isJourRepos,
      FIRST_VALUE(rdv.Titre)
        OVER (PARTITION BY c.ContratId ORDER BY rdv.HeureRdv ASC) AS PremierRdvDuJour
  FROM dbo.Contrat c
  LEFT JOIN dbo.RapportJournee r
    ON r.ContratId = c.ContratId AND r.[Date] = CAST(GETDATE() AS DATE)
  LEFT JOIN dbo.BebeRdv rdv
    ON rdv.ContratId = c.ContratId AND rdv.[Date] = CAST(GETDATE() AS DATE) AND rdv.HeureRdv >= CAST(GETDATE() AS TIME)
  WHERE c.EmployeeId = @SessionEmployeeId
    AND c.BebeStatut <> 3       -- filtre FEAT 22 SFD-15, déjà posé
  ORDER BY c.BebeStatut ASC, c.Prenom ASC, c.Nom ASC;  -- nouvel ordre
  ```
  L'ordre de tri **`BebeStatut ASC`** met les contrats **`BebeStatut = 1` (en attente) en premier visuellement**… **Décision intentionnelle inversée** : le tri est `BebeStatut DESC` pour mettre les **contrats actifs (`2`) en premier** et les contrats en attente (`1`) en fin de liste, conforme à la maquette qui montre Lina/Tom (cards interactives) en haut puis Noé (card désaturée) en bas. **Tri canonique** : `ORDER BY c.BebeStatut DESC, c.Prenom ASC, c.Nom ASC`.
- SFD-10: Le payload JSON enrichi est un tableau de cards :
  ```json
  [
    {
      "contratId": 1,
      "prenom": "Lina",
      "nom": "Bouchet",
      "dateNaissance": "2024-03-12",
      "dateEffetContrat": "2025-06-01",
      "bebeStatut": 2,
      "imageUrl": "lina.png",
      "heureArrivee": "08:42:00",
      "heureDepart": "17:30:00",
      "rapportStatut": true,
      "isJourRepos": 0,
      "premierRdvDuJour": "Vaccination 12 mois"
    },
    { ..., "prenom": "Noé", "bebeStatut": 1, "dateEffetContrat": "2026-06-16", "heureArrivee": null, ... }
  ]
  ```
  Pour les cards `bebeStatut === 1`, les champs `heureArrivee`, `heureDepart`, `rapportStatut`, `premierRdvDuJour` sont **toujours `null`** côté serveur (les LEFT JOIN sur `RapportJournee` et `BebeRdv` du jour matchent 0 ligne logiquement — aucun rapport n'a pu être saisi pour un contrat pas encore démarré). Le frontend tolère ces nulls sans afficher de placeholder erroné.

### Rendu frontend — liste `/bebes`

- SFD-11: Le composant React qui rend chaque card de `/bebes` (déjà livré par FEAT 11/15, probablement `BebeCard` ou équivalent) est **étendu** pour rendre **2 variantes** selon `bebeStatut` :
  - **Variante normale** (`bebeStatut === 2`) : structure existante inchangée — avatar coloré (no grayscale), nom + naissance, attendance box `Arrivée / Départ`, baby-card__bottom avec hints RDV + rapport + boutons `Arrivée` / `Appeler` (icon-btn--checkin + icon-btn--call). Hérité FEAT 11 SFD-12 et FEAT 15 SFD-12.
  - **Variante pending** (`bebeStatut === 1`) : structure dérivée du mockup card 3 Noé Marin — `<article class="baby-card baby-card--pending" aria-disabled="true">`, avatar en grayscale (filter CSS), nom + naissance en couleur désaturée, **pas d'attendance box** (le bloc `Arrivée / Départ` est omis), **pas de chevron** vers `/bebes/{ContratId}` (consultation détails désactivée pendant l'attente — décision SFD-13), **un seul bloc `.baby-card__bottom`** contenant un `.baby-card__row.baby-card__pending-row` avec icône calendrier + libellé `<span>Accueil prévu le <strong>{dateEffetContratFormaté}</strong></span>`, **aucun bouton** `Arrivée` / `Départ` / `Appeler` n'est rendu.
- SFD-12: Le formatage de `dateEffetContrat` côté frontend est strictement français : `{jour} {mois en toutes lettres} {année}` (ex. `16 juin 2025`, `1 août 2026`). Les noms de mois sont la liste fixe `['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']`. Aucune dépendance externe à `Intl.DateTimeFormat`. **Invariant testable** : le libellé date affiché matche la regex `^\d{1,2} (janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre) \d{4}$`. Si `dateEffetContrat === null`, le libellé est `Accueil non daté` (fallback explicite — cas conceptuel pour contrats hérités sans date).
- SFD-13: **Pour les cards `bebeStatut === 1`**, la navigation vers la fiche détaillée `/bebes/{ContratId}` (FEAT 9) est **désactivée** — le chevron de droite n'est pas rendu (ou rendu avec `pointer-events: none` + couleur gris foncé désaturée — cf. mockup classe `.baby-card__chev--off`). Le clic sur le corps de la card n'a aucun effet (`cursor: default`, pas de `useNavigate`). **Décision intentionnelle** : un contrat en attente n'a pas encore de rapports, RDV, ou historique à consulter — la fiche détaillée serait vide donc trompeuse. Une employée qui veut **modifier** un contrat en attente (changer la date d'effet, par exemple) doit passer par le wizard d'édition `/contrats/{ContratId}` accessible via une autre route (non couverte par cette FEAT — out of scope explicite, à arbitrer si demandé).
- SFD-14: **Compteur "présents" dans l'entête** (cf. mockup `.page-head__count` ligne 589 `2 / 3 présents`) — héritage FEAT 15 SFD-1. Cette FEAT **adapte** le compteur : le **dénominateur** est désormais le nombre de contrats `bebeStatut === 2` (pas plus tous les contrats `<> 3`). Les contrats `bebeStatut === 1` sont **exclus** du dénominateur car ils ne sont pas attendus aujourd'hui. Le numérateur reste les bébés `bebeStatut === 2 ET heureArrivee !== null ET isJourRepos === 0` (hérité FEAT 15). Le sous-titre `... · N enfants en garde` (FEAT 15 SFD-1) affiche `N = dénominateur` (nombre de bébés `bebeStatut === 2` hors jours de repos).
- SFD-15: **État vide** — si la liste `/bebes` retourne 0 ligne (cas aucun contrat actif), le rendu hérité FEAT 4 (état vide avec FAB `Ajouter un enfant`) est conservé. Si la liste contient **uniquement des contrats `bebeStatut === 1`** (cas conceptuel : tous les contrats sont signés mais aucun n'a commencé), le compteur `0 / 0 présents` est rendu et toutes les cards sont en mode `pending`. Aucun message d'état vide spécial n'est ajouté pour ce cas (l'employée voit ses cards en attente + un compteur à 0, ce qui est sémantiquement clair).
- SFD-16: **Wizard de création/édition contrat** (FEAT 6 / FEAT 9 edit) — le calcul de `bebeStatut` côté frontend se fait au **moment du save final** (clic sur le bouton `Enregistrer` du wizard étape 5) :
  ```javascript
  const today = new Date();
  today.setHours(0, 0, 0, 0);  // normalise à minuit local
  const dateEffet = new Date(formData.dateEffetContrat);  // parse "YYYY-MM-DD" en Date locale
  dateEffet.setHours(0, 0, 0, 0);
  const bebeStatut = dateEffet > today ? 1 : 2;  // strict > : si date = aujourd'hui → 2 (en garde dès aujourd'hui)
  ```
  La valeur calculée est ajoutée au body POST/PUT vers le backend. Aucun champ saisi par l'employée pour cette valeur — le wizard ne propose pas de choix manuel `BebeStatut` (anti-tampering UX — l'employée n'a pas à décider du statut administratif).
- SFD-17: **Pas de re-fetch optimiste post-save** — après save wizard (FEAT 6 ou FEAT 9 edit), la navigation retour vers `/bebes` (cf. flux hérité) déclenche un GET `/api/bebes` complet qui retourne la liste à jour, incluant le nouveau `bebeStatut`. Pas de mutation locale du store React/Redux pour pré-charger la card (out of scope — le coût d'un GET ~750 ms p95 est acceptable pour une opération rare comme la création de contrat).

### Job SQL nightly — bascule `1 → 2`

- SFD-18: Un **job SQL Server Agent** (ou cron + sqlcmd si SQL Agent indisponible) est configuré côté DBA pour s'exécuter chaque nuit à **00:30 heure serveur** (timezone serveur — Europe/Paris en prod beta Demo). Nom du job : `nj_flip_bebe_statut_pending_to_active`. Périodicité : tous les jours `daily`. Step unique exécutant le script T-SQL :
  ```sql
  -- Job : nj_flip_bebe_statut_pending_to_active
  -- Schedule : daily at 00:30 (server local TZ)
  -- Owner : sa (ou compte service Demo avec droits read/write sur dbo.Contrat)
  SET NOCOUNT ON;
  BEGIN TRY
      BEGIN TRANSACTION;
      UPDATE dbo.Contrat
         SET BebeStatut = 2
       WHERE BebeStatut = 1
         AND DateEffetContrat IS NOT NULL
         AND DateEffetContrat <= CAST(GETDATE() AS DATE);
      DECLARE @rowsAffected INT = @@ROWCOUNT;
      COMMIT TRANSACTION;
      -- Log structuré (table de monitoring optionnelle)
      INSERT INTO dbo.JobAuditLog (JobName, ExecutedAt, RowsAffected, Status, ErrorMessage)
      VALUES (
        'nj_flip_bebe_statut_pending_to_active',
        SYSDATETIMEOFFSET(),
        @rowsAffected,
        'SUCCESS',
        NULL
      );
  END TRY
  BEGIN CATCH
      IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
      INSERT INTO dbo.JobAuditLog (JobName, ExecutedAt, RowsAffected, Status, ErrorMessage)
      VALUES (
        'nj_flip_bebe_statut_pending_to_active',
        SYSDATETIMEOFFSET(),
        0,
        'FAILED',
        ERROR_MESSAGE()
      );
      THROW;  -- propage l'erreur au SQL Server Agent pour alerting
  END CATCH;
  ```
  La table `dbo.JobAuditLog` (création optionnelle DBA — out of scope strict de cette FEAT) loggue chaque exécution avec timestamp UTC, count de lignes touchées, statut, message d'erreur. Si la table n'existe pas, les `INSERT INTO JobAuditLog` peuvent être commentés sans impacter la logique principale.
- SFD-19: Le job est **idempotent par construction** : re-exécution sur la même nuit (test, restart, double scheduling accidentel) matche 0 ligne (les lignes basculées la 1ère passe ne matchent plus le filtre `BebeStatut = 1`). Aucun side-effect, aucune contention de lock attendue (UPDATE sur lignes filtrées avec index PK + filtre `BebeStatut = 1` qui est sélectif).
- SFD-20: **Couverture du démarrage à minuit pile** — le job tourne à 00:30 (pas 00:00 pile) pour donner 30 minutes de marge si la charge serveur est élevée en début de nuit ou si d'autres jobs DBA tournent au même moment. Conséquence : entre 00:00 et 00:30 du jour `DateEffetContrat`, un client qui charge `/bebes` voit encore la card en mode `pending`. Acceptable (fenêtre de 30 min, faible probabilité d'usage à cette heure).
- SFD-21: **Alternative cron** si SQL Server Agent n'est pas disponible (Express Edition sans Agent, ou contraintes hosting) : exécuter `sqlcmd` via une crontab système Linux/Windows Task Scheduler équivalent :
  ```bash
  # crontab : tous les jours à 00:30
  30 0 * * * /usr/bin/sqlcmd -S {DB_HOST} -d {DB_NAME} -U {DB_USER} -P {DB_PASSWORD} -i /opt/nj/jobs/flip_bebe_statut.sql >> /var/log/nj/flip_bebe_statut.log 2>&1
  ```
  Le script `flip_bebe_statut.sql` contient le même T-SQL que SFD-18 (le `JobAuditLog` insert reste optionnel selon disponibilité de la table). Cette alternative est documentée pour les environnements de dev / sandbox / SQL Express et **n'est pas la voie canonique en production beta Demo** (SQL Server Agent recommandé pour observabilité et alerting).

## Business Rules

- BR-1: L'écriture de `BebeStatut` à l'INSERT (`POST /api/contrats`) et à l'UPDATE (`PUT /api/contrats/{ContratId}`) est **toujours bornée à `{1, 2}`** côté backend — la valeur `3` est rejetée 400 ProblemDetails. La clôture passe exclusivement par l'endpoint dédié FEAT 22 `POST /cloturer`. Anti-tampering total.
- BR-2: Le calcul `bebeStatut` côté client utilise la **date courante du navigateur** (`new Date()`) — pas la date serveur. Décision intentionnelle : (a) cohérence UX avec la date affichée à l'employée dans le wizard (calendrier picker calé sur sa timezone locale), (b) évite un round-trip réseau supplémentaire pour fetch la date serveur, (c) le job nightly serveur (SFD-18) corrige toute désynchro horloge client au pire dans les 24h suivantes. Une employée avec une horloge faussée verra son contrat soit en attente trop longtemps soit en garde prématurément — le délai max d'auto-correction est de 24h, jugé acceptable pour la beta.
- BR-3: Côté backend, **si le body ne contient pas `bebeStatut` (clients legacy ou tests E2E)**, le backend calcule la valeur via `CASE WHEN @DateEffetContrat > CAST(GETDATE() AS DATE) THEN 1 ELSE 2 END` (fallback serveur). Filet de sécurité backward-compat ; ne devrait jamais être utilisé en production après déploiement complet des frontends. Une alerte WARN structurée peut être loguée à chaque utilisation du fallback pour détecter les clients non migrés.
- BR-4: Si le body contient `bebeStatut` ET `DateEffetContrat`, le backend **fait confiance à `bebeStatut` envoyé par le client** — pas de validation croisée serveur `bebeStatut === computeFromDate(DateEffetContrat)`. Cette décision est **load-bearing** pour ne pas pénaliser le client en cas de léger décalage timezone (client à minuit -1s, serveur à minuit +1s, etc.). Anti-tampering minimal mais acceptable car la valeur reste bornée à `{1, 2}` (cf. BR-1) — au pire un client malicieux peut marquer un contrat en attente comme déjà en garde, ce qui ne génère aucune fuite de données ni faille de sécurité (l'employée verrait la card interactive prématurément, mais aucun rapport ne peut être saisi pour un contrat où aucune arrivée n'a encore été pointée — le système reste cohérent en aval).
- BR-5: Le **calcul `bebeStatut` côté client utilise la comparaison stricte `>`** : `dateEffet > today` → `1`, sinon → `2`. **Cas limite** : si `DateEffetContrat === today`, la valeur calculée est `2` (en garde **dès aujourd'hui**). Décision intentionnelle — le bébé arrive à l'employée le jour même de la date d'effet, la card doit être immédiatement interactive pour pointer la première arrivée.
- BR-6: **Anti-réouverture en UPDATE** — la requête SQL PUT (cf. SFD-7) utilise `CASE WHEN BebeStatut = 3 THEN 3 ELSE COALESCE(...)` pour garantir qu'un contrat clôturé reste clôturé même si l'employée le modifie via le wizard d'édition par mégarde. Décision symétrique à FEAT 22 BR-2 (anti-réouverture côté endpoint applicatif). Le bypass de cette règle nécessiterait une intervention DBA directe en base.
- BR-7: Le **job nightly** est strictement borné à `1 → 2`. Il **ne touche jamais** les lignes `BebeStatut = 2` ou `BebeStatut = 3`. Aucune transition `2 → 1` n'est jamais effectuée automatiquement (un contrat déjà démarré ne peut pas revenir en attente, même si quelqu'un édite `DateEffetContrat` vers une date future — dans ce cas le wizard PUT côté frontend recalcule `bebeStatut = 1` et écrit via PUT, **mais** ce comportement est intentionnellement laissé à l'edit UI, pas au job). Le job nightly reste minimaliste (1 SQL UPDATE filtré) et auditeable.
- BR-8: Le frontend **n'expose aucun bouton manuel** pour basculer `BebeStatut`. Toutes les transitions sont **dérivées automatiquement** : `1 → 2` (wizard save calculé à partir de `DateEffetContrat` ou nightly job), `2 → 3` (FEAT 22 POST `/cloturer` via FAB clôture), aucune autre. Anti-tampering UX — l'employée n'a pas à comprendre le concept de `BebeStatut` opérationnellement.
- BR-9: La card `baby-card--pending` est **strictement non-interactive** : aucun clic ne déclenche d'action (pas de navigate vers fiche, pas de pointage arrivée, pas d'appel téléphonique). Les boutons `Arrivée` / `Départ` / `Appeler les parents` ne sont **pas rendus du tout** dans le DOM (vs `disabled` — la suppression franche évite tout doute UX et toute fuite tab-key clavier).
- BR-10: L'ordre de tri canonique de `/bebes` est `ORDER BY c.BebeStatut DESC, c.Prenom ASC, c.Nom ASC` — les contrats `2` (en garde) sont rendus **en haut**, les contrats `1` (en attente) **en bas**. Cohérent avec la maquette (Lina + Tom interactives en haut, Noé désaturée en bas). **Décision intentionnelle** : l'employée se concentre d'abord sur les bébés du jour ; les contrats en attente sont des "rappels passifs" en pied de liste.
- BR-11: Aucun audit log applicatif n'est posé sur les transitions `BebeStatut`. Le job nightly peut optionnellement écrire dans `dbo.JobAuditLog` (cf. SFD-18) — c'est un audit **système**, pas applicatif. Cohérent avec FEAT 22 BR-4 (aucun audit DB sur les clôtures).
- BR-12: Le job SQL nightly est **non transactionnel cross-tenant** : un échec d'UPDATE sur une ligne (cas conceptuel — la colonne `BebeStatut` est TINYINT NOT NULL, aucun constraint violation possible sauf désastre majeur) doit rollback la transaction entière (cf. `BEGIN TRY ... BEGIN CATCH ... ROLLBACK`). Tolérance zéro à l'incohérence partielle — soit toutes les lignes éligibles basculent, soit aucune.

## Acceptance Criteria

- AC-1: **payload `GET /api/bebes` enrichi** : la requête retourne pour chaque card 2 nouvelles clés `bebeStatut: number` et `dateEffetContrat: string | null` ; les contrats `bebeStatut = 3` sont absents (filtre FEAT 22 SFD-15 conservé) ; l'ordre est `bebeStatut DESC` puis `prenom ASC` puis `nom ASC` (vérifiable en posant 3 contrats : 1 à statut 2 prénom `Béatrice`, 1 à statut 2 prénom `Anne`, 1 à statut 1 prénom `Charlotte` → ordre retourné `Anne, Béatrice, Charlotte`).
- AC-2: **rendu card normale `bebeStatut === 2`** : la card est rendue avec avatar coloré (sans grayscale), bloc attendance `Arrivée / Départ`, boutons `Arrivée` / `Appeler` interactifs, chevron de navigation vers la fiche détaillée actif (hérité FEAT 11/15, no regression vérifiable visuellement et en grep du DOM).
- AC-3: **rendu card pending `bebeStatut === 1`** : la card a la classe CSS `baby-card baby-card--pending` ; l'avatar affiche `filter: grayscale(1); opacity: 0.78` (vérifiable via DevTools computed styles) ; **aucun** bloc `.attendance` n'est rendu dans le DOM ; **aucun** bouton `.icon-btn--checkin` ni `.icon-btn--call` n'est rendu (vérifiable par `querySelectorAll('.baby-card--pending .icon-btn').length === 0`) ; un seul bloc `.baby-card__row.baby-card__pending-row` est rendu contenant l'icône calendrier SVG + le libellé `Accueil prévu le <strong>{date formatée}</strong>`.
- AC-4: **libellé date formaté français** : le libellé `Accueil prévu le {date}` matche la regex `^Accueil prévu le \d{1,2} (janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre) \d{4}$` (vérifiable par parse du DOM `.baby-card--pending .baby-card__pending-row span`).
- AC-5: **fallback date null** : si `dateEffetContrat === null` dans le payload, le libellé est `Accueil non daté` (sans gras, format simple).
- AC-6: **POST nouveau contrat avec date future** : le wizard `/contrats/nouveau` saisit `DateEffetContrat = today + 30 jours` → le body POST vers `/api/contrats` contient `bebeStatut: 1` ; la ligne `Contrat` insérée en base a `BebeStatut = 1` (vérifiable par SELECT direct) ; le rechargement de `/bebes` affiche immédiatement la card en mode `pending`.
- AC-7: **POST nouveau contrat avec date passée ou today** : le wizard saisit `DateEffetContrat = today` (ou date passée) → le body POST contient `bebeStatut: 2` ; la ligne insérée a `BebeStatut = 2` ; la card apparaît en mode normal sur `/bebes`.
- AC-8: **PUT modification contrat — passage 2 → 1** : un contrat existant `BebeStatut = 2` est édité via FEAT 9 wizard edit, la date d'effet est changée vers une date future → le body PUT contient `bebeStatut: 1` ; la ligne UPDATE en base passe à `BebeStatut = 1` ; la card sur `/bebes` bascule en mode `pending` au prochain refresh.
- AC-9: **PUT modification contrat — passage 1 → 2** : un contrat existant `BebeStatut = 1` est édité, la date d'effet est changée vers une date passée ou today → le body PUT contient `bebeStatut: 2` ; la ligne UPDATE passe à `BebeStatut = 2` ; la card devient interactive.
- AC-10: **anti-réouverture PUT — bebeStatut 3 préservé** : un contrat clôturé (`BebeStatut = 3`) est édité via FEAT 9 wizard edit en changeant n'importe quel champ + envoyant `bebeStatut: 2` dans le body → la ligne UPDATE applique les autres champs mais conserve `BebeStatut = 3` (clause `CASE WHEN BebeStatut = 3 THEN 3` du SQL UPDATE — cf. SFD-7, BR-6). La card ne réapparaît pas dans `/bebes`.
- AC-11: **rejection bebeStatut hors domaine** : un POST/PUT avec `bebeStatut: 3` (ou `0`, `null`, `"abc"`, etc.) retourne 400 ProblemDetails avec message explicite (`bebeStatut must be 1 or 2`) ; aucune écriture en base ; le frontend affiche un toast d'erreur de validation.
- AC-12: **backend fallback bebeStatut absent** : un POST/PUT sans le champ `bebeStatut` dans le body (simulé via Postman, ou client legacy) déclenche le calcul serveur via `CASE WHEN @DateEffetContrat > CAST(GETDATE() AS DATE) THEN 1 ELSE 2 END` (cf. BR-3) ; la ligne est insérée/mise à jour avec la valeur calculée ; aucune erreur 400 n'est retournée (backward-compat préservée).
- AC-13: **compteur `/bebes` exclut bebeStatut 1** : le chip `X / Y présents` (`.page-head__count`) a comme dénominateur `Y` = `count(card where bebeStatut === 2 AND isJourRepos === 0)` ; les cards `bebeStatut === 1` ne comptent **pas** (vérifiable en posant 2 contrats `2` + 1 contrat `1` + 1 contrat `2 jour de repos` → compteur affiche `count(arrivés) / 2 présents`, jamais `... / 3` ou `... / 4`).
- AC-14: **job SQL nightly bascule 1 → 2** : exécuter manuellement le script T-SQL de SFD-18 sur une base contenant 3 lignes `BebeStatut = 1` dont 2 ont `DateEffetContrat <= today` et 1 a `DateEffetContrat > today` → après exécution, 2 lignes ont `BebeStatut = 2`, 1 ligne reste à `BebeStatut = 1` ; aucune ligne `BebeStatut = 2` préexistante n'est touchée ; aucune ligne `BebeStatut = 3` n'est touchée.
- AC-15: **job nightly idempotent** : re-exécuter le script T-SQL immédiatement après la 1ère passe → `@@ROWCOUNT = 0` (aucune ligne touchée) ; le `JobAuditLog` enregistre une 2ème entrée `RowsAffected = 0, Status = SUCCESS` (si la table existe).
- AC-16: **job nightly transactionnel** : si une erreur SQL survient en cours d'UPDATE (cas conceptuel — par exemple un trigger AFTER UPDATE qui échoue), la transaction est rollback (`@@TRANCOUNT > 0` → ROLLBACK) ; aucune ligne n'est partiellement mise à jour ; le `JobAuditLog` enregistre `Status = FAILED, ErrorMessage = <détail>` ; l'exception est rethrow vers SQL Server Agent qui peut alerter (notification email DBA configurée par job step).
- AC-17: **ordre de tri canonique** : un GET `/api/bebes` sur une base contenant des cards mixtes retourne le tableau JSON dans l'ordre `bebeStatut DESC, prenom ASC, nom ASC` (vérifiable par snapshot test sur un fixture connu).
- AC-18: **désactivation navigation card pending** : un clic sur le corps d'une card `baby-card--pending` (zone hors actions et hors chevron) ne déclenche **aucune navigation** vers `/bebes/{ContratId}` (vérifiable en posant un breakpoint sur `useNavigate` ou en inspectant le DOM — `cursor: default`, pas de `onClick` handler attaché au `<article>`). Le chevron de droite n'est pas rendu (`querySelectorAll('.baby-card--pending .baby-card__chev').length === 0`).
- AC-19: **interaction clavier accessibilité** : tab-key sur une card pending **saute** par-dessus la card (les boutons et chevron n'étant pas rendus, aucun focus stop interne) ; `aria-disabled="true"` est posé sur le `<article>` pour signaler aux lecteurs d'écran (cf. mockup ligne 670).
- AC-20: **pas de side-effect au refresh `/bebes`** : un GET `/api/bebes` répété 10 fois retourne exactement le même JSON (en termes de `bebeStatut`) tant qu'aucune action n'est faite (pas de bascule automatique côté backend en cours de session — seul le job nightly à 00:30 fait les bascules).

## Functional Deliverables

- FD-1: **endpoint backend étendu** `POST /api/contrats` (FEAT 6) — accepte `bebeStatut: number ∈ {1, 2}` optionnel dans body ; validation Zod ; INSERT SQL étendu (cf. SFD-6).
- FD-2: **endpoint backend étendu** `PUT /api/contrats/{ContratId}` (FEAT 9 edit) — accepte le même champ optionnel ; UPDATE SQL étendu avec clause anti-réouverture `CASE WHEN BebeStatut = 3` (cf. SFD-7, BR-6).
- FD-3: **endpoint backend étendu** `GET /api/bebes` (FEAT 11/15) — 2 colonnes ajoutées au SELECT (`BebeStatut`, `DateEffetContrat`) ; ORDER BY canonique `BebeStatut DESC, Prenom ASC, Nom ASC` (cf. SFD-9, BR-10).
- FD-4: **composant frontend** `BebeCard` (ou équivalent) — étendu pour rendre 2 variantes (normale + pending) selon `bebeStatut` ; les libellés constants (`Accueil prévu le`, `Accueil non daté`) sont déclarés en tête de fichier (cf. SFD-12).
- FD-5: **composant wizard frontend** `ContratWizard` (ou équivalent FEAT 6 / FEAT 9 edit) — étendu pour calculer `bebeStatut` à l'étape save (cf. SFD-16) ; ajout du champ au body POST/PUT.
- FD-6: **CSS scopé** `.baby-card--pending` (et `.baby-card__pending-row`, `.baby-card__chev--off`) déjà présent dans le mockup — à porter vers `workspace/output/src/Demo/public/styles.css` (mode `augment`, scopé sous le wrapper de la page `/bebes`).
- FD-7: **job SQL Server Agent** `nj_flip_bebe_statut_pending_to_active` configuré par DBA — script T-SQL en SFD-18, schedule quotidien 00:30 serveur (cf. SFD-18, AC-14 à AC-16). **Charge DBA** ; out of scope agent `dev-backend` strict (le script peut être généré dans `workspace/output/src/Demo/scripts/job-flip-bebe-statut.sql` pour traçabilité mais son installation comme job SQL Agent reste manuelle).
- FD-8: **script backfill optionnel one-shot** `workspace/output/src/Demo/scripts/backfill-bebe-statut.sql` (cf. SFD-5) — exécuté manuellement par DBA pre-déploiement pour corriger les lignes `BebeStatut = 1` issues du DEFAULT FEAT 22 qui sont sémantiquement déjà en garde.
- FD-9: **compteur header `/bebes`** — adapté pour exclure les contrats `bebeStatut === 1` du dénominateur (cf. SFD-14, AC-13).

## Dependencies

**FEAT 22 `spec-cloture-contrat`** — pré-requis schéma strict. La colonne `Contrat.BebeStatut` doit exister en base avant le déploiement de cette FEAT 23 (créée par FEAT 22 SFD-3). En POC mode `/sdd-poc`, FEAT 22 doit avoir tourné avant FEAT 23 (l'ordre `/sdd-poc 22 && /sdd-poc 23` est requis).

**FEAT 4 / 11 / 15** (lineage `/bebes`) — extensions cumulatives. Cette FEAT 23 modifie en mode `augment` le code livré par ces 3 FEATs (composant `BebeCard`, requête SQL `GET /api/bebes`, compteur header).

**FEAT 6 `spec-souscrire-contrat`** — extension du wizard POST. Cette FEAT 23 ajoute le calcul + envoi de `bebeStatut` à l'étape save.

**FEAT 9 `spec-bebe-detaille`** — extension du wizard PUT (edit mode). Cette FEAT 23 ajoute le calcul + envoi de `bebeStatut` au save.

## Out of Scope

- **Endpoint applicatif manuel** pour basculer `BebeStatut` (ex. `POST /api/contrats/{n}/marquer-en-garde`) — toutes les transitions sont dérivées automatiquement (cf. BR-8).
- **WebSocket / SSE / push** pour notifier les clients d'une bascule serveur (job nightly) — le rafraîchissement manuel de `/bebes` suffit (cf. SFD-17).
- **Audit log applicatif** des transitions `BebeStatut` — seul le job nightly écrit optionnellement dans `dbo.JobAuditLog` (cf. BR-11).
- **Édition d'un contrat `bebeStatut === 1` directement depuis la card pending** — pas de chevron ni de bouton edit sur la card pending (cf. SFD-13). L'employée doit naviguer manuellement via une autre route si elle veut modifier la date d'effet. (À arbitrer si demandé : ajouter un bouton edit discret sur les cards pending — out of scope strict de cette FEAT.)
- **Backfill automatique** des lignes préexistantes `BebeStatut = 1` issues du DEFAULT FEAT 22 — un script manuel `backfill-bebe-statut.sql` est fourni (FD-8) mais son exécution reste à la charge du DBA.
- **Notification email parent** à la bascule `1 → 2` ("votre bébé peut être accueilli à partir d'aujourd'hui") — out of scope, hors périmètre SDD.
- **Bascule `2 → 1` automatique** via job nightly (si une employée a saisi `DateEffetContrat` futur sur un contrat déjà actif par erreur) — le job ne fait que `1 → 2` (cf. BR-7). La correction passe par le wizard edit qui recalcule + UPDATE explicite.
- **Dashboard administrateur DBA** pour monitorer les exécutions du job nightly — la table `JobAuditLog` (optionnelle) sert de trace ; l'observabilité est laissée aux outils standards SQL Server Agent.
