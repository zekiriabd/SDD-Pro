# Spec: statut-bebes

FEAT ID: 15-Spec-Statut-Bebes
Spec ID: spec-statut-bebes
Status: Draft

> **Pré-requis schéma** : (1) ajout d'une colonne `RapportStatut BIT NOT NULL DEFAULT 0` à la table existante `dbo.RapportJournee` (cf. SFD-4 pour le DDL canonique) — la colonne n'est **pas** présente dans le schéma post-DDL alignement POC 2026-05-26 documenté dans `spec-arrivees-departs` (FEAT 11) ; (2) la colonne `JourReposEmploye NVARCHAR(...)` sur `dbo.Contrat` est supposée préexistante en base (contient les abréviations FR 3-lettres des jours de repos contractuels du couple employé/contrat, séparées par virgule ou autre délimiteur — ex. `"LUN,MER"` ou `"LUN.MER."`) ; (3) la table `dbo.BebeRdv` est supposée présente (créée par FEAT 13 `spec-bebe-rdv`). Toute incohérence schéma → STOP DBA avant `dev-backend`. Source de vérité = DB existante (cf. `docs/principles/source-first.md`).

## Context

La page `/bebes` (héritée de `spec-bebes` FEAT 4 et étendue par `spec-arrivees-departs` FEAT 11) affiche aujourd'hui pour l'employé connecté une liste de cards bébés avec deux lignes horaires (`Arrivée HH:MM`, `Départ HH:MM`) et un **bouton d'action unique à trois états** (vert clic → rouge clic → rouge figé) pilotant un automate INSERT arrivée / UPDATE départ sur `dbo.RapportJournee`. L'écran reste cependant **aveugle aux signaux opérationnels du jour** : il ne distingue pas les bébés effectivement en garde aujourd'hui de ceux en jour de repos contractuel, ne signale pas si le rapport journalier a déjà été envoyé aux parents, n'attire pas l'attention sur un rendez-vous médical imminent, et ne neutralise pas visuellement les cards des bébés sans garde du jour (l'employé peut cliquer par erreur sur "Marquer l'arrivée" pour un bébé qui n'est pas attendu).

Cette spec **étend `spec-arrivees-departs` (FEAT 11)** en ajoutant à la même page `/bebes` quatre **statuts visuels dérivés** dont l'apparence est entièrement calculée côté serveur via une requête SQL unique enrichie (LEFT JOIN à `dbo.BebeRdv` pour le RDV du jour, calcul `CHARINDEX` sur `Contrat.JourReposEmploye` pour détecter le jour de repos, lecture de `RapportJournee.RapportStatut` pour l'état du rapport) et exposée côté frontend en deux blocs de rendu (chip compteur dans l'entête + 1 à 2 lignes hint sous la card). Aucun nouvel endpoint backend n'est créé : l'endpoint existant `GET /api/bebes` (cf. FEAT 11 SFD-5) est **étendu** par 4 colonnes supplémentaires (`rapportStatut`, `isJourRepos`, `premierRdvDuJour`, et conserve `heureArrivee`, `heureDepart`) — le frontend dérive de ce payload aplati l'apparence des chips et des lignes.

Le mockup `workspace/input/ui/15-1-Spec-Statut-Bebes.html` matérialise les **quatre statuts** sur trois cards canoniques :
1. **Card 1 (Lina Bouchet)** — bébé en garde aujourd'hui non encore arrivé → bouton vert cliquable + ligne `Vaccination 12 mois…` (cloche RDV du jour) + ligne `Rapport du jour à compléter` (cercle warning ambre).
2. **Card 2 (Tom Lefèvre)** — bébé en jour de repos contractuel → cards entière neutralisée : action button gris non cliquable, call button gris non cliquable, ligne `Pas de garde aujourd'hui` (cercle barré gris) — aucune ligne RDV ni rapport rendues. Le clic chevron / corps de card reste actif (consultation détails autorisée).
3. **Card 3 (Noé Marin)** — bébé en garde, journée terminée (arrivée + départ enregistrés) → bouton action rouge figé (cadenas, `disabled`) + call button cliquable + ligne `Consultation suivi…` (cloche RDV du jour) + ligne `Rapport du jour envoyé` (icône check verte).

Le **chip compteur de présents** dans l'entête (`1 / 3 présent`) reflète le ratio **"bébés effectivement présents aujourd'hui / bébés en garde aujourd'hui"** où :
- numérateur = nombre de bébés tels que `heureArrivee != null` ET `isJourRepos == 0` ;
- dénominateur = nombre de bébés tels que `isJourRepos == 0` (les bébés en jour de repos sont **exclus** du dénominateur — leur absence n'est pas un signal de retard mais un état contractuel attendu).

Le sous-titre `Lundi 26 mai · N enfants en garde` affiche `N` = dénominateur ci-dessus (nombre de bébés effectivement attendus aujourd'hui, hors jours de repos).

> **Note maquette** : la maquette historique affichait `1 / 3 présent` (numérateur 1, dénominateur 3) en comptant **par erreur** le bébé en jour de repos dans le dénominateur. Le rendu canonique de cette FEAT est `1 / 2 présent` sur la même scène (Lina + Noé sont en garde, Tom est en jour de repos donc exclu). Cette correction est **intentionnelle** et documentée pour éviter la confusion dev-frontend.

## Objective

L'employé connecté ouvre la page `/bebes` → le frontend envoie un unique `GET /api/bebes` ; le backend exécute la requête SQL canonique paramétrée (cf. SFD-7) qui joint `Contrat`, `RapportJournee` du jour, et `BebeRdv` du jour (futur uniquement) en une seule passe, et calcule la colonne dérivée `isJourRepos` via `CHARINDEX` sur l'abréviation 3-lettres du jour courant dans `Contrat.JourReposEmploye`. Le backend retourne un tableau JSON `[ { contratId, prenom, nom, dateNaissance, imageUrl, heureArrivee, heureDepart, rapportStatut, isJourRepos, premierRdvDuJour }, ... ]` aplati. Le frontend dérive de ce payload : (a) le **chip compteur** `X / Y présent` dans l'entête et le sous-titre `... · Y enfants en garde`, (b) pour chaque card l'**état du bouton d'action** (étendu de 3 à 4 états : vert / rouge cliquable / rouge figé / **gris jour de repos non cliquable**), (c) l'**état du bouton téléphone** (gris non cliquable si jour de repos, sinon coral cliquable cosmétique inchangé), (d) la **ligne hint RDV** (rendue ssi `premierRdvDuJour != null` ET `isJourRepos == 0`) avec le titre du premier RDV à venir aujourd'hui, et (e) la **ligne hint rapport** (rendue ssi `isJourRepos == 0`) `Rapport du jour à compléter` si `rapportStatut == 0` ou `null` / `Rapport du jour envoyé` si `rapportStatut == 1`. Pour les bébés en jour de repos (`isJourRepos > 0`), un **unique** hint `Pas de garde aujourd'hui` remplace les lignes RDV et rapport. L'écran reste interactif pour le bouton d'action arrivée/départ (états A→B→C inchangés depuis FEAT 11) sur les bébés en garde ; les bébés en jour de repos exposent un bouton d'action **inerte** mais permettent la consultation détails via chevron (cf. AC-12).

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps de chargement de la liste enrichie (1 requête SQL multi-JOIN) + temps de rendu des chips et lignes hint côté frontend (calcul pur, pas de fetch additionnel)
- Target: p95 chargement liste `GET /api/bebes` < 700 ms sur 4G simulé (1 requête SQL `Contrat LEFT JOIN RapportJournee LEFT JOIN BebeRdv` + calcul `CHARINDEX` inline ; payload < 12 KB JSON pour 10 bébés cumulés avec colonnes statuts) ; p95 rendu chip + lignes hint < 80 ms côté frontend (transformation pure du payload, aucun fetch supplémentaire) ; p95 rafraîchissement compteur présent après un clic arrivée < 100 ms (mise à jour optimiste locale, le compteur se recalcule depuis l'état React local sans round-trip)
- Deadline: livraison stack `kotlin-spring-boot × react × shadcn` au 2026-08-15

## Non-Functional Constraints (v7.0.0)

- Expected volume: ~5 bébés / employé en garde simultanée (≤ 10 en pic), ~5 chargements `/bebes` / employé / jour ouvré (ouverture matin + relances), ~0 écriture déclenchée par cette FEAT (la colonne `RapportStatut` est lue, jamais mise à jour ici — son écriture relève de `spec-rapport-du-jour` FEAT 10) ; total trafic ajouté par cette FEAT < 5 KB/employé/jour de payload supplémentaire vs FEAT 11
- Performance SLA: p95 chargement < 700 ms (cf. Quantified Goal) ; aucun risque N+1 (1 SELECT unique avec 2 LEFT JOIN + 1 fenêtre `FIRST_VALUE` ; les LEFT JOIN sont indexés sur `(ContratId, Date)` côté `RapportJournee` et `BebeRdv`) ; calcul `CHARINDEX` sur `JourReposEmploye` reste O(1) côté SQL Server (chaîne courte, ≤ 50 caractères en pratique)
- Data retention: aucune nouvelle ligne créée par cette FEAT (lecture seule sur `RapportJournee.RapportStatut`, `Contrat.JourReposEmploye`, `BebeRdv`) ; ajout de la colonne `RapportStatut BIT NOT NULL DEFAULT 0` à `RapportJournee` migration DBA one-shot (cf. SFD-4) — les lignes existantes sont implicitement initialisées à 0 par le `DEFAULT 0`
- Compliance: RGPD — `RapportStatut` est un booléen opérationnel non sensible (envoyé/non envoyé) ; `JourReposEmploye` est une donnée contractuelle non sensible (jours hebdomadaires de repos du couple employé/contrat) ; `BebeRdv.Titre` peut contenir des informations médicales (catégorie 9 RGPD — cf. `spec-bebe-rdv` Non-Functional Constraints) ; tous les statuts sont filtrés par `Contrat.EmployeeId == session.EmployeeId` côté serveur (anti-cross-tenant — symétrique FEAT 11 BR-1)
- Integration: extension de l'endpoint backend existant `GET /api/bebes` (FEAT 11) — aucun nouvel endpoint ; aucune dépendance externe ; aucun service tiers ; aucune notification SMS / email / push (out of scope)
- Degraded mode: si la requête SQL échoue (5xx, timeout), le rendu hérité de FEAT 11 est conservé (état d'erreur générique de la liste) ; si la colonne `RapportStatut` est manquante au schéma (migration DBA non appliquée), le backend logue une alerte structurée et retourne `rapportStatut: null` pour toutes les lignes — le frontend dégrade en `Rapport du jour à compléter` partout (cf. BR-12) ; si la colonne `JourReposEmploye` est manquante ou NULL, `isJourRepos` est forcé à `0` côté backend (tous les bébés considérés en garde — comportement legacy FEAT 11) ; si la table `BebeRdv` est manquante, `premierRdvDuJour` est `null` (ligne RDV jamais rendue) ; aucun fallback offline

## Actors

- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session (cf. `spec-connexion`). Seule autorisée à consulter les statuts agrégés (présents, rapport, RDV, jour de repos) des contrats dont `Contrat.EmployeeId == session.EmployeeId`. Les comportements d'écriture (clic bouton arrivée / départ) restent ceux définis par FEAT 11 (anti-tampering serveur via `getdate()` — BR-4, BR-5).

## Functional Needs

### Point d'entrée et navigation

- SFD-1: La spec **étend `spec-arrivees-departs` (FEAT 11)** et donc indirectement `spec-bebes` (FEAT 4) : la page `/bebes` est inchangée en terme de route, layout, filtres et bouton `Ajouter un enfant` ; seul est modifié (a) l'**entête** (chip compteur + sous-titre dynamiques) et (b) le **bloc bottom de chaque card** (lignes hint contextuelles + état neutralisé du bouton action et du bouton téléphone si jour de repos).
- SFD-2: Aucune nouvelle route SPA n'est introduite ; aucun nouvel endpoint backend n'est créé. Le rendu reste **server-state-driven** (l'apparence est entièrement dérivée du payload `GET /api/bebes` enrichi).

### Schéma de données — extension `dbo.RapportJournee` + colonnes existantes

- SFD-3: La spec **lit** trois colonnes supplémentaires par rapport à FEAT 11 :
  - `dbo.RapportJournee.RapportStatut BIT NOT NULL DEFAULT 0` — **nouvelle colonne** à ajouter (cf. SFD-4) ; `0` = rapport du jour pas encore envoyé aux parents (état initial), `1` = rapport du jour envoyé (set par `spec-rapport-du-jour` FEAT 10, hors scope de cette FEAT).
  - `dbo.Contrat.JourReposEmploye NVARCHAR(...) NULL` — **colonne préexistante** (créée par contrat employé/famille ; format = chaîne contenant les abréviations 3-lettres des jours de repos contractuels, ex. `"LUN,MER"`, `"LUN.MER."`, `"SAM DIM"`). La détection robuste est faite côté serveur via `CHARINDEX(REPLACE(UPPER(FORMAT(GETDATE(), 'ddd', 'fr-FR')), '.', ''), UPPER(c.JourReposEmploye))` — la valeur retournée `> 0` ssi l'abréviation 3-lettres uppercase du jour courant (FR) est présente dans la chaîne uppercase de `JourReposEmploye` (cf. BR-11).
  - `dbo.BebeRdv` (table préexistante, FEAT 13) — colonnes lues : `ContratId`, `Date`, `HeureRdv`, `Titre`. La FEAT extrait via `FIRST_VALUE` le **titre du premier RDV à venir aujourd'hui** par contrat (cf. SFD-7).
- SFD-4: DDL canonique de la migration `RapportStatut` (à appliquer une fois par environnement, idempotent via `IF NOT EXISTS`) :
  ```sql
  IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE Name = N'RapportStatut'
      AND Object_ID = Object_ID(N'dbo.RapportJournee')
  )
  BEGIN
    ALTER TABLE dbo.RapportJournee
      ADD RapportStatut BIT NOT NULL CONSTRAINT DF_RapportJournee_RapportStatut DEFAULT 0;
  END;
  ```
  - La contrainte `DEFAULT 0` initialise toutes les lignes préexistantes à `0` (rapport non envoyé).
  - La colonne est `NOT NULL` côté DDL ; le **frontend** doit néanmoins tolérer un payload `rapportStatut: null` en mode dégradé (cf. BR-12, NFC degraded mode) si la migration n'a pas encore tourné en environnement cible.
- SFD-5: Aucune autre colonne n'est ajoutée à `RapportJournee` dans cette FEAT (les colonnes existantes `Date`, `ContratId`, `HeureArrivee`, `HeureDepart`, `RapportSms` restent inchangées — cf. FEAT 11 SFD-3).

### Endpoint backend — `GET /api/bebes` enrichi (extension FEAT 11 SFD-5)

- SFD-6: La requête SQL canonique de `GET /api/bebes` est désormais (paramétrée, server-side) :
  ```sql
  SELECT
      c.ContratId,
      c.Prenom,
      c.Nom,
      c.DateNaissance,
      c.ImageUrl,
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
    ON r.ContratId = c.ContratId
   AND r.[Date]    = CAST(GETDATE() AS DATE)
  LEFT JOIN dbo.BebeRdv rdv
    ON rdv.ContratId          = c.ContratId
   AND CAST(rdv.[Date] AS DATE) = CAST(GETDATE() AS DATE)
   AND rdv.HeureRdv             > CAST(GETDATE() AS TIME)
  WHERE c.EmployeeId = @SessionEmployeeId
  ORDER BY c.Prenom ASC, c.Nom ASC;
  ```
  - Le filtre `WHERE c.EmployeeId = @SessionEmployeeId` est **obligatoire** et provient exclusivement de la session (cf. BR-4 — hérité FEAT 11 BR-1).
  - Le LEFT JOIN sur `BebeRdv` est filtré par `rdv.Date = today` ET `rdv.HeureRdv > CAST(GETDATE() AS TIME)` — seuls les RDV **à venir aujourd'hui** (heure future stricte) sont retenus ; les RDV déjà passés du jour disparaissent du payload (la card revient à un état "aucun RDV").
  - La fonction `FIRST_VALUE(rdv.Titre) OVER (PARTITION BY c.ContratId ORDER BY rdv.HeureRdv ASC)` retourne le titre du **plus proche RDV à venir** dans l'heure (cf. BR-13). Si plusieurs lignes RDV existent, le résultat est dédupliqué côté frontend (la duplication par fenêtre génère N lignes identiques par contrat avec multiples RDV ; le backend `GROUP BY c.ContratId` OU `DISTINCT` peut être employé pour aplatir — cf. SFD-7 et BR-14).
- SFD-7: Le backend **DOIT** garantir qu'il n'y a **qu'une seule ligne JSON par `contratId`** dans le payload final (cf. SFD-6 — la fenêtre `FIRST_VALUE` peut générer plusieurs lignes identiques par contrat lorsque plusieurs RDV existent). Stratégies d'implémentation autorisées (équivalentes sémantiquement) :
  - **Option A** : utiliser une **CTE** `WITH rdv_today AS (SELECT ContratId, FIRST_VALUE(Titre) OVER (...) AS PremierRdvDuJour FROM BebeRdv WHERE ...)` puis `LEFT JOIN ... rdv_today rt ON rt.ContratId = c.ContratId GROUP BY c.ContratId, ...` (déduplique via agrégation).
  - **Option B** : utiliser un **sous-SELECT** `SELECT TOP 1 Titre FROM BebeRdv WHERE ContratId = c.ContratId AND Date = today AND HeureRdv > now() ORDER BY HeureRdv ASC` (corrélé — 1 ligne max par contrat).
  - **Option C** : utiliser `SELECT DISTINCT c.ContratId, ..., PremierRdvDuJour FROM ...` (déduplique post-JOIN — robuste si toutes les colonnes c.* sont fonctionnellement dépendantes de `c.ContratId`).
  
  L'option retenue est laissée à `dev-backend` selon le dialecte et les contraintes de performance, mais **le contrat de sortie est invariant** : 1 ligne JSON par `contratId`, jamais de doublon.
- SFD-8: La réponse JSON de l'endpoint backend `GET /api/bebes` est de la forme :
  ```json
  [
    {
      "contratId": 1001,
      "prenom": "Lina",
      "nom": "Bouchet",
      "dateNaissance": "2024-03-12",
      "imageUrl": "https://...",
      "heureArrivee": null,
      "heureDepart": null,
      "rapportStatut": 0,
      "isJourRepos": 0,
      "premierRdvDuJour": "Vaccination 12 mois"
    },
    {
      "contratId": 1002,
      "prenom": "Tom",
      "nom": "Lefèvre",
      "dateNaissance": "2024-09-04",
      "imageUrl": null,
      "heureArrivee": null,
      "heureDepart": null,
      "rapportStatut": 0,
      "isJourRepos": 1,
      "premierRdvDuJour": null
    },
    {
      "contratId": 1003,
      "prenom": "Noé",
      "nom": "Marin",
      "dateNaissance": "2023-07-07",
      "imageUrl": "https://...",
      "heureArrivee": "08:42",
      "heureDepart": "17:30",
      "rapportStatut": 1,
      "isJourRepos": 0,
      "premierRdvDuJour": "Consultation suivi"
    }
  ]
  ```
  - `rapportStatut` : entier 0 ou 1 (sérialisé `Int`, jamais bool — facilite l'évolution future ternaire). Mode dégradé : `null` (cf. BR-12).
  - `isJourRepos` : entier ≥ 0 (`CHARINDEX` retourne la **position** de l'occurrence dans la chaîne, ou `0` si absent). Le frontend interprète **uniquement** `== 0` (en garde) vs `> 0` (jour de repos) — cf. BR-11.
  - `premierRdvDuJour` : string (titre du RDV) ou `null` si aucun RDV à venir aujourd'hui (cf. BR-13).

### Entête de la page `/bebes` — chip compteur + sous-titre dynamiques

- SFD-9: L'entête de `/bebes` rend :
  - Un titre `Mes bébés` (inchangé, hérité FEAT 11).
  - Un sous-titre `<JourSemaineFR> <jour> <moisFR> · <N> enfants en garde` où :
    - `<JourSemaineFR>` = nom du jour de la semaine en français capitalisé (`Lundi`, `Mardi`, … — formaté côté frontend depuis `new Date()` ou via librairie locale, jamais depuis le payload).
    - `<jour>` = numéro du jour (1-31), `<moisFR>` = nom du mois en minuscules (`mai`, `juin`, …).
    - `<N>` = nombre de bébés du payload tels que `isJourRepos == 0` (= bébés en garde aujourd'hui — exclut les jours de repos).
  - Un chip `X / Y présent` (background coral-50, foreground coral-700, font-weight 700, padding 6×12, border-radius 999) où :
    - `X` = nombre de bébés du payload tels que `heureArrivee != null` ET `isJourRepos == 0` (numérateur — bébés effectivement présents aujourd'hui).
    - `Y` = nombre de bébés du payload tels que `isJourRepos == 0` (dénominateur — bébés attendus aujourd'hui ; identique à `<N>` du sous-titre).
- SFD-10: Si le dénominateur `Y` vaut 0 (l'employé n'a aucun bébé en garde aujourd'hui — tous en jour de repos ou aucun contrat), le chip affiche `0 / 0 présent` (pas de division by zero, rendu littéral) et le sous-titre dit `... · 0 enfant en garde` (singulier `enfant` quand `Y = 0` ou `Y = 1`, pluriel `enfants` quand `Y >= 2`).

### Card bébé — lignes hint contextuelles

- SFD-11: Chaque `baby-card` rend dans son `baby-card__bottom__hint` (zone à gauche du bouton d'action, sous la séparation pointillée) **0, 1 ou 2 lignes hint** selon la matrice de décision suivante (calculée côté frontend depuis le payload, déterministe) :

  | Condition | Ligne 1 rendue | Ligne 2 rendue |
  |---|---|---|
  | `isJourRepos > 0` | `Pas de garde aujourd'hui` (icône cercle barré gris) | (aucune) |
  | `isJourRepos == 0` ET `premierRdvDuJour != null` ET `(rapportStatut == 0 OU rapportStatut == null)` | `{premierRdvDuJour}` (icône cloche lavande) | `Rapport du jour à compléter` (icône horloge ambre) |
  | `isJourRepos == 0` ET `premierRdvDuJour != null` ET `rapportStatut == 1` | `{premierRdvDuJour}` (icône cloche lavande) | `Rapport du jour envoyé` (icône check verte) |
  | `isJourRepos == 0` ET `premierRdvDuJour == null` ET `(rapportStatut == 0 OU rapportStatut == null)` | `Rapport du jour à compléter` (icône horloge ambre) | (aucune) |
  | `isJourRepos == 0` ET `premierRdvDuJour == null` ET `rapportStatut == 1` | `Rapport du jour envoyé` (icône check verte) | (aucune) |

  L'ordre canonique est : **RDV puis Rapport** (jamais l'inverse) — la cloche RDV est plus saillante visuellement (urgence du jour) et apparaît en premier.
- SFD-12: Les icônes des lignes hint sont **inlinées SVG** (cf. maquette `15-1-Spec-Statut-Bebes.html`) avec les couleurs des tokens UI :
  - Cloche RDV (`baby-card__rdv`) → `color: var(--nj-lavender-500)` (lavande).
  - Horloge "à compléter" (`baby-card__report--pending`) → `color: var(--nj-warning)` (ambre).
  - Check "envoyé" (`baby-card__report`) → `color: var(--nj-sage-500)` ou `var(--nj-success)` (vert sauge).
  - Cercle barré "pas de garde" (`baby-card__report--none`) → `color: var(--nj-ink-400)` (gris).

  Le texte des lignes hint utilise `color: var(--nj-ink-500)` (texte secondaire), le `<strong>` éventuel utilise `var(--nj-ink-700)`. Aucun hex hardcodé (cf. `rules/quality.md §B.5`).

### Bouton d'action et bouton téléphone — état "jour de repos"

- SFD-13: L'automate du **bouton d'action principal** est **étendu** des 3 états FEAT 11 à 4 états :
  - **État A — "à arriver"** : `isJourRepos == 0` ET `heureArrivee == null` ET `heureDepart == null` → bouton **vert plein** + icône `login` blanche + cliquable (inchangé FEAT 11 SFD-11).
  - **État B — "présent"** : `isJourRepos == 0` ET `heureArrivee != null` ET `heureDepart == null` → bouton **rouge plein** + icône `logout` blanche + cliquable (inchangé FEAT 11 SFD-11).
  - **État C — "parti"** : `isJourRepos == 0` ET `heureArrivee != null` ET `heureDepart != null` → bouton **rouge plein opacité 0.55** + icône `lock` blanche + non cliquable (`disabled`) (inchangé FEAT 11 SFD-11).
  - **État D — "jour de repos"** *(nouveau)* : `isJourRepos > 0` (quelles que soient `heureArrivee` / `heureDepart` — par sécurité défensive, en pratique `(null, null)` car aucun INSERT n'a pu se produire sur un jour de repos) → bouton **gris plein** (`background: var(--nj-ink-300)`, classe `.action-btn--off`) + icône `login` blanche + non cliquable (`disabled`, `cursor: not-allowed`, `pointer-events: none`, `box-shadow: none`).
- SFD-14: Le **bouton téléphone** (icône combiné, à droite du bouton d'action — historiquement `icon-btn--call` coral, hérité FEAT 4 / FEAT 11) est aligné sur le même état "jour de repos" : `isJourRepos > 0` → classe `.icon-btn--off` (`background: var(--nj-ink-300)`, blanc, `disabled`, `cursor: not-allowed`, `pointer-events: none`, `box-shadow: none`). Sinon (`isJourRepos == 0`) → rendu coral cosmétique inchangé (toujours non câblé, cf. FEAT 11 SFD-10 — un clic ne déclenche aucune action). Cette neutralisation visuelle est cohérente avec le signal "pas d'activité aujourd'hui".
- SFD-15: Aucune autre partie de la card n'est neutralisée par un jour de repos : l'avatar, le nom, la date de naissance, le chevron de navigation vers `/bebes/{ContratId}` (fiche détaillée — `spec-bebe-detaille`), le bloc horaires (rendu littéralement `--:--` / `--:--` puisque `heureArrivee` et `heureDepart` sont `null`) restent **interactifs** et lisibles. L'employé peut toujours consulter la fiche d'un bébé en jour de repos (planning, contrat, RDV futurs).

### Mise à jour optimiste du chip compteur

- SFD-16: Quand l'employé clique sur le bouton d'action en État A (vert) pour un bébé en garde et que l'INSERT arrivée réussit (201 — cf. FEAT 11 SFD-14, AC-13), le frontend recalcule **immédiatement** le chip compteur de l'entête depuis l'état React local (`X` = nouveau nombre de bébés `heureArrivee != null` ET `isJourRepos == 0`). Le rendu est instantané, sans round-trip serveur. Le sous-titre `Y enfants en garde` reste inchangé (le dénominateur ne dépend que de `isJourRepos` qui est immuable côté payload).
- SFD-17: Quand l'employé clique sur le bouton d'action en État B (rouge) pour un bébé déjà arrivé et que l'UPDATE départ réussit (200 — cf. FEAT 11 SFD-15, AC-18), le chip compteur **n'est pas modifié** (le bébé reste comptabilisé comme "présent aujourd'hui" — ayant `heureArrivee != null` — pour la durée de la journée affichée, même après son départ). C'est intentionnel : le chip mesure le **flux quotidien** (combien sont passés en garde aujourd'hui), pas le flux **instantané** (combien sont physiquement présents dans la maison à l'instant T).

### États de chargement et erreur

- SFD-18: Pendant le chargement initial de `/bebes` (GET en cours), le rendu hérité FEAT 11 / FEAT 4 (squelette / spinner) reste actif ; le chip compteur et les lignes hint ne sont rendus qu'après réception du payload.
- SFD-19: Si la requête SQL échoue (timeout, erreur 5xx), le rendu d'erreur hérité FEAT 11 est conservé ; aucune erreur dédiée à cette FEAT n'est introduite (les 4 statuts dégradent silencieusement vers les valeurs par défaut décrites dans NFC degraded mode).
- SFD-20: Si le payload contient une ligne avec `rapportStatut: null` (migration DBA non appliquée — cf. BR-12) ou `isJourRepos == null` (chaîne `JourReposEmploye` NULL côté `Contrat`), le frontend traite ces cas comme `rapportStatut = 0` (rapport à compléter) et `isJourRepos = 0` (en garde) respectivement, sans afficher d'erreur — comportement dégradé qui privilégie la disponibilité de l'écran sur la fidélité des statuts.

## Business Rules

- BR-1: l'endpoint `GET /api/bebes` retourne **uniquement** les contrats dont `Contrat.EmployeeId == session.EmployeeId` (filtrage server-side, hérité FEAT 11 BR-1 / FEAT 4 BR-1/BR-2) ; aucune donnée d'un autre employé n'est exposée, y compris les colonnes statuts (`rapportStatut`, `isJourRepos`, `premierRdvDuJour`).
- BR-2: la requête SQL est **paramétrée** (`@SessionEmployeeId`) ; aucune concaténation de chaîne, aucune interpolation de variables non échappées (anti-injection SQL — hérité FEAT 11 BR-6).
- BR-3: la **date** utilisée pour les jointures (`r.[Date] = CAST(getdate() AS DATE)`, `CAST(rdv.[Date] AS DATE) = CAST(GETDATE() AS DATE)`) et pour la **détection du jour de repos** (`FORMAT(GETDATE(), 'ddd', 'fr-FR')`) est **toujours** `GETDATE()` côté serveur (date du serveur, locale TZ-naive serveur) ; aucun paramètre `date` côté query / body ne peut la surcharger (anti-tampering — hérité FEAT 11 BR-4).
- BR-4: `@SessionEmployeeId` provient exclusivement de la variable singleton de session ; aucun paramètre de requête (header custom, body, query param) ne peut le surcharger (hérité FEAT 11 BR-3 / FEAT 4 BR-3).
- BR-5: l'endpoint `GET /api/bebes` **ne mute aucun état** en base : la lecture des 3 colonnes statuts (`rapportStatut`, `isJourRepos`, `premierRdvDuJour`) ne déclenche aucun INSERT / UPDATE / DELETE. L'écriture de `rapportStatut = 1` relève de `spec-rapport-du-jour` FEAT 10 (UPDATE serveur déclenché par un autre flow), l'écriture de `JourReposEmploye` relève d'une FEAT contrat (out of scope), l'écriture de `BebeRdv` relève de FEAT 13 / 14.
- BR-6: les champs JSON renvoyés par le backend sont sérialisés en **camelCase** (cf. `rules/library-and-stack.md §6.bis.3` — alignement post-mortem CMS-Back) : `contratId`, `prenom`, `nom`, `dateNaissance`, `imageUrl`, `heureArrivee`, `heureDepart`, `rapportStatut`, `isJourRepos`, `premierRdvDuJour` ; aucune sérialisation en PascalCase ou snake_case.
- BR-7: les valeurs `NULL` SQL sont sérialisées **`null`** JSON (jamais omises, jamais chaîne `"null"`, jamais chaîne vide `""`) — la distinction `null` vs `0` vs `1` (resp. `null` vs `"Vaccination 12 mois"`) est sémantique côté frontend (cf. BR-12, BR-13).
- BR-8: la requête SQL **ne doit pas** retourner plusieurs lignes JSON pour un même `contratId` même quand plusieurs RDV `(ContratId, Date=today, HeureRdv>now())` existent — la stratégie de déduplication (CTE / sous-SELECT corrélé / DISTINCT) est libre (cf. SFD-7) mais le contrat est invariant : 1 ligne par contrat dans le payload final.
- BR-9: le tri du payload est `ORDER BY c.Prenom ASC, c.Nom ASC` (collation par défaut serveur, sensible accent / casse selon la collation `Contrat.Prenom`) — identique FEAT 11 SFD-5 ; aucune autre ordre n'est exposé par cette FEAT.
- BR-10: la requête SQL filtre les RDV à venir aujourd'hui via `CAST(rdv.[Date] AS DATE) = CAST(GETDATE() AS DATE) AND rdv.HeureRdv > CAST(GETDATE() AS TIME)` — un RDV programmé à 10:00:00 disparaît du payload à partir de 10:00:01 (la card revient à un état "aucun RDV"). C'est intentionnel : le statut "RDV imminent" ne sert plus une fois l'heure passée. La gestion de l'historique des RDV passés est hors scope (cf. `spec-bebe-rdv` FEAT 13 Out of Scope).
- BR-11: la détection du **jour de repos** repose sur `CHARINDEX(REPLACE(UPPER(FORMAT(GETDATE(), 'ddd', 'fr-FR')), '.', ''), UPPER(c.JourReposEmploye))` :
  - `FORMAT(GETDATE(), 'ddd', 'fr-FR')` retourne l'abréviation 3-lettres du jour courant en français selon la locale `fr-FR` (peut inclure un point selon les versions SQL Server — ex. `"lun."`, `"lun"`).
  - `REPLACE(..., '.', '')` supprime le point éventuel (normalisation : `"lun."` → `"lun"`).
  - `UPPER(...)` met en majuscules (`"LUN"`).
  - `UPPER(c.JourReposEmploye)` met en majuscules la chaîne complète des jours de repos contractuels (ex. `"LUN,MER"` → `"LUN,MER"`).
  - `CHARINDEX(needle, haystack)` retourne la position (1-indexed) de `needle` dans `haystack`, ou `0` si absent.
  - **Convention** : `isJourRepos > 0` = jour de repos contractuel ; `isJourRepos == 0` = jour de garde. Le frontend interprète **uniquement** ce booléen dérivé.
  - **Limite connue** : si `JourReposEmploye` contient une chaîne ambiguë (ex. `"LUNDI"` contient `"LUN"` mais aussi `"DI"` partiellement — collision faux-positif pour `"DIM"` si la chaîne est `"LUNDIM"`), le `CHARINDEX` peut retourner un faux positif. **Convention contrat** : `JourReposEmploye` est saisi en abréviations **3-lettres séparées par un délimiteur** (virgule, point, espace) — pas de mots complets, pas de concaténation sans séparateur. Cette convention relève de la FEAT de gestion de contrat (out of scope).
- BR-12: le frontend **DOIT** tolérer `rapportStatut: null` dans le payload (mode dégradé — colonne `RapportStatut` absente du schéma OU LEFT JOIN sans ligne `RapportJournee` du jour) et le **traiter comme `0`** (= `Rapport du jour à compléter`). Aucune erreur utilisateur n'est exposée pour ce cas. Le dev-backend logue une alerte structurée (niveau WARN) si la colonne est manquante au schéma (détection au démarrage via introspection ORM — hors scope strict de cette FEAT mais recommandé).
- BR-13: `premierRdvDuJour` est `null` ssi **aucun** RDV n'existe pour `(ContratId, Date=today, HeureRdv>now())` dans `dbo.BebeRdv` (LEFT JOIN sans ligne matchante). Le frontend interprète `null` comme "aucune ligne RDV à rendre" (ligne supprimée du DOM, pas un message vide). Si plusieurs RDV existent, **seul le titre du plus proche dans l'heure** (heure minimale `HeureRdv` ASC parmi les RDV futurs) est retourné — les RDV ultérieurs du jour ne sont pas exposés par cette FEAT (l'utilisateur consulte l'onglet `RDV` de la fiche détaillée pour la liste complète — cf. FEAT 13).
- BR-14: les valeurs textuelles affichées dans les lignes hint sont des **labels statiques** (`Rapport du jour à compléter`, `Rapport du jour envoyé`, `Pas de garde aujourd'hui`) **côté frontend** — ils ne sont **jamais** envoyés par le backend (le backend retourne uniquement les booléens / entiers `rapportStatut`, `isJourRepos` et la chaîne `premierRdvDuJour`). Cette séparation garantit l'i18n future sans nécessiter de migration backend.
- BR-15: aucune information technique (stack trace, exception SQL, nom de colonne brut) n'est exposée dans les réponses d'erreur ; le frontend dégrade silencieusement vers les valeurs par défaut (cf. BR-12, NFC degraded mode) — pas de toast d'erreur dédié pour cette FEAT.
- BR-16: les transitions du bouton d'action (A→B→C, hérité FEAT 11) ne sont **pas** déclenchables depuis l'État D (jour de repos) — l'attribut HTML `disabled` + `pointer-events: none` empêche toute interaction au niveau DOM ; aucun appel backend `POST .../arrivee` n'est jamais émis pour un bébé en jour de repos. Si l'utilisateur force un appel (manipulation manuelle DevTools), le backend retourne `400 Bad Request` avec body `{ code: "JOUR_REPOS" }` (sécurité défense en profondeur — cf. BR-17).
- BR-17: défense en profondeur côté backend : `POST /api/contrats/{ContratId}/arrivee` (cf. FEAT 11 SFD-14) **DOIT** vérifier avant l'INSERT que `CHARINDEX(REPLACE(UPPER(FORMAT(GETDATE(), 'ddd', 'fr-FR')), '.', ''), UPPER(c.JourReposEmploye)) == 0` (= bébé en garde aujourd'hui) ; sinon retour `400 Bad Request { code: "JOUR_REPOS" }` et aucune ligne insérée. Cette règle complète FEAT 11 BR-2 (vérification cross-employee) — elle empêche tout INSERT serveur frauduleux y compris si le frontend laisse fuiter une UI cliquable suite à un bug.
- BR-18: la **règle clé du chip compteur** : `X / Y` où `X` = `count(b ∈ payload | b.heureArrivee != null AND b.isJourRepos == 0)` ET `Y` = `count(b ∈ payload | b.isJourRepos == 0)`. Les bébés en jour de repos sont **systématiquement exclus** du dénominateur — leur absence n'est pas un signal opérationnel mais un état contractuel attendu (cf. Context, paragraphe maquette).
- BR-19: si le design system actif (shadcn / Vuetify / Radzen) fournit un composant `Badge` ou `Chip` natif pour le compteur `X / Y présent`, il **DOIT** être utilisé en priorité avec override de tokens (`bg-coral-50`, `text-coral-700`) — le CSS isolé ne complète que pour la fidélité visuelle (cf. `rules/quality.md §B`).

## Acceptance Criteria

- AC-1: la page `/bebes` reste à la même URL avec le même layout global, les mêmes filtres et le même bouton `Ajouter un enfant` (héritage FEAT 4 / FEAT 11) ; seuls l'entête (chip compteur + sous-titre) et le bloc bottom de chaque card sont modifiés (vérifiable visuellement + DOM diff).
- AC-2: au chargement, la page envoie **une seule** requête `GET /api/bebes` qui retourne le payload enrichi à 10 champs `{contratId, prenom, nom, dateNaissance, imageUrl, heureArrivee, heureDepart, rapportStatut, isJourRepos, premierRdvDuJour}` ; aucune requête additionnelle dédiée aux statuts n'est émise (vérifiable Network DevTools — anti N+1).
- AC-3: la requête SQL exécutée par le backend est **sémantiquement équivalente** à celle de SFD-6 (les 3 LEFT JOIN, le filtre WHERE `EmployeeId`, le `CHARINDEX` du jour de repos, la fenêtre `FIRST_VALUE` ou son équivalent SFD-7) — vérifiable par logs SQL ou test d'intégration. La stratégie de déduplication (CTE / sous-SELECT / DISTINCT) est libre tant que le contrat 1-ligne-par-contrat est respecté (cf. BR-8).
- AC-4: un bébé sans ligne `RapportJournee` pour aujourd'hui apparaît avec `heureArrivee: null`, `heureDepart: null`, `rapportStatut: 0` (valeur de défaut résultant du LEFT JOIN sans match — voir variante BR-12 dégradée) — test d'intégration : insérer un `Contrat` sans `RapportJournee` correspondante → le GET retourne le bébé avec les 3 champs aux valeurs attendues.
- AC-5: un bébé dont `Contrat.JourReposEmploye` contient l'abréviation 3-lettres FR du jour courant (ex. `"LUN,MER"` un lundi) reçoit `isJourRepos > 0` dans le payload (test d'intégration : créer un contrat avec `JourReposEmploye = "LUN"` → exécuter le GET un lundi → `isJourRepos > 0`).
- AC-6: un bébé dont `Contrat.JourReposEmploye` est NULL ou ne contient pas l'abréviation du jour courant reçoit `isJourRepos == 0` dans le payload (test d'intégration : `JourReposEmploye = NULL` ou `"DIM"` un lundi → `isJourRepos == 0`).
- AC-7: l'entête de `/bebes` affiche un sous-titre `<JourSemaineFR> <jour> <moisFR> · <Y> enfant(s) en garde` où `<Y>` = nombre de bébés du payload avec `isJourRepos == 0` (singulier `enfant` si `Y <= 1`, pluriel `enfants` si `Y >= 2`).
- AC-8: l'entête affiche un chip `X / Y présent` (background coral-50, foreground coral-700) où `X` = nombre de bébés avec `heureArrivee != null` ET `isJourRepos == 0`, `Y` = nombre de bébés avec `isJourRepos == 0` ; les bébés en jour de repos sont **exclus** du dénominateur (test : 3 bébés dont 1 en jour de repos et 1 arrivé sur les 2 restants → chip `1 / 2 présent`, jamais `1 / 3 présent`).
- AC-9: pour chaque card avec `isJourRepos > 0`, le bloc hint affiche **uniquement** la ligne `Pas de garde aujourd'hui` (icône cercle barré gris) — aucune ligne RDV, aucune ligne rapport rendues, même si `rapportStatut != null` ou `premierRdvDuJour != null` dans le payload (le frontend les ignore).
- AC-10: pour chaque card avec `isJourRepos == 0` ET `premierRdvDuJour != null`, le bloc hint affiche **en première position** la ligne `{premierRdvDuJour}` (icône cloche lavande) — le titre brut du RDV est rendu tel quel sans transformation, troncature ellipsis CSS autorisée.
- AC-11: pour chaque card avec `isJourRepos == 0`, le bloc hint affiche **en seconde position** (ou première si pas de RDV) la ligne `Rapport du jour à compléter` (icône horloge ambre) si `rapportStatut == 0` ou `null`, OU `Rapport du jour envoyé` (icône check verte) si `rapportStatut == 1`.
- AC-12: pour chaque card avec `isJourRepos > 0`, le bouton d'action principal porte la classe `.action-btn--off` (background `var(--nj-ink-300)`, blanc, `disabled`, `cursor: not-allowed`, `pointer-events: none`) ET le bouton téléphone porte la classe `.icon-btn--off` (mêmes propriétés) ; un clic sur l'un de ces deux boutons ne déclenche aucune action et aucune requête réseau (vérifiable Network DevTools).
- AC-13: pour chaque card avec `isJourRepos > 0`, le chevron de navigation vers `/bebes/{ContratId}` et le clic sur le corps de la card **restent fonctionnels** (l'utilisateur peut consulter la fiche détaillée du bébé même en jour de repos) — vérifiable : cliquer sur le chevron → navigation vers `/bebes/{ContratId}` ; cliquer sur le bouton action gris → reste sur `/bebes`.
- AC-14: pour chaque card avec `isJourRepos == 0`, les états A / B / C du bouton d'action (hérités FEAT 11 SFD-11) restent applicables — le mapping `(heureArrivee, heureDepart)` → couleur / icône / cliquabilité est inchangé.
- AC-15: au succès d'un `POST /api/contrats/{ContratId}/arrivee` (201) déclenché par un clic sur un bouton vert, le chip compteur de l'entête est recalculé localement et `X` est incrémenté de 1 sans rechargement complet de la page (vérifiable : avant clic `0 / 2 présent`, après clic `1 / 2 présent`).
- AC-16: au succès d'un `POST /api/contrats/{ContratId}/depart` (200) déclenché par un clic sur un bouton rouge cliquable, le chip compteur de l'entête **reste inchangé** (`X` ne change pas — le bébé reste comptabilisé comme "passé en garde aujourd'hui").
- AC-17: si la colonne `RapportStatut` est absente du schéma au moment de l'exécution (migration DBA non appliquée), le payload retourne `rapportStatut: null` pour toutes les lignes ET le frontend rend `Rapport du jour à compléter` partout (mode dégradé — pas d'erreur visible) ; le backend logue une alerte WARN structurée (vérifiable côté logs serveur).
- AC-18: une tentative directe de `POST /api/contrats/{ContratId}/arrivee` (manipulation DevTools) pour un bébé en jour de repos (`CHARINDEX(...) > 0` côté serveur) retourne **400 Bad Request** avec body `{ code: "JOUR_REPOS" }` et **aucune** ligne `RapportJournee` insérée (test d'intégration : créer un contrat avec `JourReposEmploye = "LUN"`, appeler le POST un lundi → 400 ; `SELECT COUNT(*) FROM RapportJournee WHERE ContratId = X AND Date = today` = 0 après l'appel).
- AC-19: le payload garantit **une et une seule** ligne JSON par `contratId` même si le contrat a plusieurs RDV pour aujourd'hui dans `BebeRdv` (vérifiable : insérer 3 RDV pour `(ContratId=X, Date=today, HeureRdv > now())` → le GET retourne 1 ligne pour ce contrat avec `premierRdvDuJour` = titre du RDV à l'heure minimale parmi les 3).
- AC-20: si aucun RDV n'existe pour `(ContratId, Date=today, HeureRdv > now())`, `premierRdvDuJour` est `null` dans le payload ET aucune ligne RDV n'est rendue dans la card (vérifiable DOM : `.baby-card__rdv` absent).
- AC-21: si tous les RDV du jour pour un contrat sont déjà passés (`HeureRdv <= now()`), `premierRdvDuJour` est `null` (test d'intégration : insérer un RDV à 09:00:00, exécuter le GET à 10:00:00 → `premierRdvDuJour: null`).
- AC-22: aucune nouvelle dépendance externe (npm package, NuGet, Maven artifact) n'est introduite par cette FEAT — le calcul des chips et lignes hint est pur côté frontend ; le calcul SQL `CHARINDEX` + `FORMAT` + `FIRST_VALUE` est natif SQL Server ≥ 2017 (vérifiable côté CI : aucun diff sur les fichiers de manifest stack).
- AC-23: le rendu des chips et lignes hint utilise **exclusivement** des tokens CSS (`var(--nj-coral-50)`, `var(--nj-coral-700)`, `var(--nj-success)`, `var(--nj-warning)`, `var(--nj-lavender-500)`, `var(--nj-sage-500)`, `var(--nj-ink-300)`, `var(--nj-ink-400)`, `var(--nj-ink-500)`, `var(--nj-ink-700)`) — aucun hex hardcodé dans les composants (cf. `rules/quality.md §B.5`, vérifiable par grep `#[0-9a-fA-F]{3,8}` post-build).
- AC-24: la FEAT **étend** `spec-arrivees-departs` (FEAT 11) sans la casser : tous les AC d'origine de FEAT 11 (AC-1 à AC-27) restent satisfaits sur les bébés en garde (`isJourRepos == 0`) ; les bébés en jour de repos (`isJourRepos > 0`) sont **hors scope** des AC FEAT 11 qui supposent un automate arrivée/départ actif.
- AC-25: aucun nouveau cookie, header de session, ou state local persistant (localStorage, sessionStorage, IndexedDB) n'est introduit par cette FEAT — l'état des statuts est purement dérivé du payload et de l'état React local de la liste courante (cf. FEAT 11 BR-11).
- AC-26: **wiring backend non contournable** — le handler de la route HTTP `GET /api/bebes` (ou le service qu'il invoque **directement** pour produire le tableau renvoyé au frontend, typiquement `babyService.listMyBabies` côté node-express/Fastify, `BabyService.listMyBabies` côté Spring/.NET, `baby_service.list_my_babies` côté FastAPI) **DOIT** retourner un payload où **chacune** des lignes contient les 3 clés `rapportStatut`, `isJourRepos`, `premierRdvDuJour` peuplées par la requête SQL SFD-6. **Interdit** : créer un service ou un module séparé (ex. `rapportJourneeService`, `statutBebeService`, `dailyStatusService`) qui calcule les 3 champs mais n'est **pas** appelé par le pipeline de réponse de `GET /api/bebes`. Vérifiable par : (a) test d'intégration HTTP — `GET /api/bebes` avec session JWT valide → tous les objets JSON contiennent les 10 clés AC-2 ; (b) grep statique sur le handler de la route — montre l'appel au calcul des 3 champs **dans le même chemin d'exécution** que la sérialisation du payload ; (c) tout `services/rapport*.{js,ts,kt,cs,py}` ou `services/statut*.{js,ts,kt,cs,py}` orphelin (jamais importé par `routes/baby.routes.*` ni par `services/babyService.*` ni équivalent stack) est un **gap bloquant** [FRONTEND_BACKEND_CONTRACT_GAP] (cf. `library-and-stack.md §6.bis.4`).
- AC-27: **anti-derive ownership** — la FEAT 15 **DOIT** modifier `services/babyService.*` (ou l'équivalent du stack actif qui implémente `listMyBabies` ou la fonction servant `GET /api/bebes`) en mode **augment** (cf. `ownership.md §1` Edit-augment) ; un commit qui livre uniquement `services/rapportJourneeService.*` **sans** toucher `services/babyService.*` viole cette FEAT. Le repository `repositories/babyRepository.*` (fonction `findByEmployeeId`) **DOIT** également être augmenté pour exécuter la requête SQL SFD-6 enrichie (3 LEFT JOIN, calcul `CHARINDEX`, fenêtre `FIRST_VALUE` ou équivalent SFD-7) — il ne peut plus se contenter d'un `SELECT * FROM Contrat WHERE EmployeeId = @SessionEmployeeId` legacy FEAT 11.

## Dependencies

- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employé connecté.
- **spec-bebes** (`4-spec-bebes`) : route `/bebes`, layout général, filtre par `EmployeeId` (BR-1), bouton `Ajouter un enfant` hérité.
- **spec-arrivees-departs** (`11-Spec-Arrrivees-Departs`) : **étendue directement** par cette FEAT — la requête SQL de `GET /api/bebes` est complétée par 3 colonnes (`rapportStatut`, `isJourRepos`, `premierRdvDuJour`) + 1 LEFT JOIN supplémentaire sur `BebeRdv` ; l'automate du bouton d'action est étendu d'un 4ème état (D — jour de repos) ; les endpoints `POST .../arrivee` et `POST .../depart` reçoivent une garde supplémentaire `JOUR_REPOS` (BR-17, AC-18).
- **spec-rapport-du-jour** (`10-Spec-rapport-du-jour`) : indirecte — `RapportStatut` est **lu** par cette FEAT mais **écrit** par FEAT 10 (UPDATE `RapportStatut = 1` au moment de l'envoi du rapport aux parents) ; les deux FEAT partagent la même colonne sur `dbo.RapportJournee` sans collision (writes sérialisés par contrat/jour).
- **spec-bebe-rdv** (`13-Spec-Bebe-Rdv`) : indirecte — la table `dbo.BebeRdv` (créée par FEAT 13) est **lue** par cette FEAT pour extraire `premierRdvDuJour` ; aucune écriture sur `BebeRdv` n'est déclenchée par cette FEAT (la création / édition / suppression relève de FEAT 13 et FEAT 14).
- **dbo.RapportJournee** (table SQL) : prérequis schéma — colonne `RapportStatut BIT NOT NULL DEFAULT 0` à ajouter via DDL idempotent (cf. SFD-4) ; les colonnes existantes (`Date`, `ContratId`, `HeureArrivee`, `HeureDepart`, `RapportSms`) sont inchangées.
- **dbo.Contrat.JourReposEmploye** (colonne SQL préexistante) : supposée présente en base ; convention de format = abréviations 3-lettres FR séparées par délimiteur (cf. BR-11). La création / migration de cette colonne est out of scope.
- **dbo.BebeRdv** (table SQL préexistante) : créée par FEAT 13 ; colonnes lues = `ContratId`, `Date`, `HeureRdv`, `Titre`.

## Functional Deliverables

- FD-1: migration DBA idempotente ajoutant la colonne `dbo.RapportJournee.RapportStatut BIT NOT NULL CONSTRAINT DF_RapportJournee_RapportStatut DEFAULT 0` (cf. SFD-4) — script à appliquer une fois par environnement avant déploiement backend.
- FD-2: extension de l'endpoint backend `GET /api/bebes` (FEAT 11) — requête SQL enrichie à 10 colonnes (cf. SFD-6) avec 2 LEFT JOIN supplémentaires (un implicite déjà présent FEAT 11 sur `RapportJournee`, un nouveau sur `BebeRdv`) + 1 colonne dérivée `isJourRepos` (`CHARINDEX`) + 1 colonne dérivée `premierRdvDuJour` (`FIRST_VALUE` ou équivalent SFD-7) ; payload JSON aplati garantissant 1 ligne par `contratId` (cf. BR-8).
- FD-3: garde serveur sur `POST /api/contrats/{ContratId}/arrivee` (FEAT 11) — vérification que le bébé n'est pas en jour de repos via le même `CHARINDEX` (cf. BR-17) avant l'INSERT ; retour 400 `{ code: "JOUR_REPOS" }` si la garde échoue, aucune ligne insérée.
- FD-4: entête `/bebes` enrichi — chip compteur `X / Y présent` (background coral-50 / foreground coral-700) + sous-titre `<JourSemaineFR> <jour> <moisFR> · <Y> enfant(s) en garde` (cf. SFD-9, SFD-10, BR-18) ; rendu purement frontend depuis le payload, recalcul optimiste au succès d'un POST arrivée.
- FD-5: lignes hint contextuelles dans le bloc bottom de chaque `baby-card` — 0 à 2 lignes selon la matrice de décision SFD-11 (`Pas de garde aujourd'hui` seul si jour de repos / `{premierRdvDuJour}` + `Rapport du jour à compléter` ou `... envoyé` sinon) ; icônes SVG inlinées (cloche lavande, horloge ambre, check vert, cercle barré gris) consommant les tokens UI (cf. SFD-12, AC-23).
- FD-6: extension du bouton d'action principal — ajout de l'État D `.action-btn--off` (background `var(--nj-ink-300)`, blanc, `disabled`, `pointer-events: none`) rendu ssi `isJourRepos > 0` (cf. SFD-13) ; les états A / B / C inchangés depuis FEAT 11.
- FD-7: neutralisation du bouton téléphone (`.icon-btn--off`) — même mapping conditionnel que le bouton d'action ; rendu coral cliquable cosmétique inchangé sinon (cf. SFD-14).
- FD-8: maquette `workspace/input/ui/15-1-Spec-Statut-Bebes.html` matérialisant les **quatre statuts** sur trois cards canoniques (Lina vert + RDV + rapport à compléter ; Tom jour de repos ; Noé rouge figé + RDV + rapport envoyé) — référence visuelle non-ambiguë pour dev-frontend.
- FD-9: log structuré côté backend (niveau WARN) émis au démarrage du service si la colonne `RapportStatut` est absente du schéma `dbo.RapportJournee` (cf. BR-12, AC-17) — détection via introspection ORM ou via la première requête de chargement avec catch + log puis dégradation `rapportStatut: null` partout.
- FD-10: **wiring backend explicite** (cf. AC-26, AC-27) — augment de `services/babyService.*` (méthode `listMyBabies` ou équivalent stack) **et** de `repositories/babyRepository.*` (méthode `findByEmployeeId` ou équivalent) **dans le même PR** que la FEAT 15. La requête SQL SFD-6 enrichie remplace l'ancienne requête legacy FEAT 11 dans `babyRepository` ; le mapper `toPublic(row)` du `babyService` est augmenté pour exposer les 3 nouvelles clés (`rapportStatut`, `isJourRepos`, `premierRdvDuJour`) en plus des champs FEAT 11 / FEAT 4. **Tout fichier `services/{rapportJournee,statutBebe,dailyStatus,...}Service.*` qui n'est jamais importé par `routes/baby.routes.*` ni par `services/babyService.*` est un livrable orphelin invalide et bloque la livraison FEAT 15.** Cette règle empêche l'anti-pattern « service silo » qui livre du code mort.

## Out of Scope

- **création / migration de la colonne `Contrat.JourReposEmploye`** : supposée préexistante en base (relève d'une FEAT contrat).
- **création / migration de la table `dbo.BebeRdv`** : couverte par FEAT 13 `spec-bebe-rdv`.
- **écriture de `RapportStatut = 1`** (envoi du rapport aux parents) : couverte par FEAT 10 `spec-rapport-du-jour` ; cette FEAT lit uniquement la valeur.
- **interaction sur la ligne hint `{premierRdvDuJour}`** (clic → naviguer vers la liste RDV de la fiche détaillée) : la ligne est purement informative dans cette FEAT — aucun lien actif (FEAT future éventuelle).
- **affichage de tous les RDV du jour** dans la card : seul le titre du **plus proche** est exposé (cf. BR-13) ; la liste complète est consultable via l'onglet `RDV` de `/bebes/{ContratId}` (FEAT 13).
- **état "absent excusé"** distinct (rendu visuel séparé pour un bébé en garde mais signalé absent par le parent — différent de jour de repos contractuel) : aucun attribut `Motif` ou statut explicite n'est introduit ; un bébé en garde non arrivé reste en État A (vert "à arriver") jusqu'à clic ou fin de journée.
- **correction manuelle de la détection "jour de repos"** (override admin / employé pour le jour J — ex. employé exceptionnellement disponible un jour de repos) : hors scope ; la détection est purement dérivée de `JourReposEmploye` contractuel.
- **notification au parent** (SMS / Email / Push) sur le rapport envoyé ou le RDV imminent : FEAT future dédiée.
- **calcul du compteur côté backend** (le backend exposerait un champ `summary.presents` et `summary.enGarde` agrégé) : décision intentionnelle — le calcul reste **frontend** pour permettre la mise à jour optimiste au clic POST arrivée sans round-trip (cf. SFD-16) ; le backend reste sans état d'agrégation.
- **i18n des libellés hint** (`Rapport du jour à compléter`, `Pas de garde aujourd'hui`) : labels en dur en français côté frontend pour cette FEAT (cf. BR-14) ; l'i18n future ne nécessitera aucune migration backend.
- **support multi-locale du calcul `CHARINDEX`** : la détection du jour de repos suppose `FORMAT(..., 'fr-FR')` ; un changement de locale serveur (`en-US`) inverserait les abréviations attendues — la cohérence relève de la configuration `Contrat.JourReposEmploye` (saisi en abréviations 3-lettres FR) et du `FORMAT` SQL Server (locale `fr-FR`). Décision de configuration hors scope.
- **historique des statuts par jour** (consultation d'un calendrier "rapport envoyé / présent / en garde" sur une semaine ou un mois passé) : la page `/bebes` n'expose que la journée du jour ; l'historique relèverait d'un écran dédié type calendrier (FEAT future).
- **synchronisation temps réel** (WebSocket / SSE / polling) du compteur ou des lignes hint si un autre device modifie l'état (autre onglet, autre appareil de l'employé) : un re-chargement manuel reflète l'état persisté ; aucun mécanisme push n'est introduit.
- **filtrage / tri** de la liste par statut (ex. "afficher uniquement les bébés en garde" ou "afficher uniquement les rapports à compléter") : hors scope ; la liste reste triée par `Prenom, Nom`.
- **fallback offline** / cache local des statuts si la connexion est perdue : aucun stockage local (cf. AC-25).
- **rôles Admin / Parent** : un Parent qui consulterait les statuts journaliers de son enfant relève d'une FEAT future dédiée avec règles de filtrage différentes.
