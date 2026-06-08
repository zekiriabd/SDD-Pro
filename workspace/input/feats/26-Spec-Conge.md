# Spec: conge

FEAT ID: 26-Spec-Conge
Spec ID: spec-conge
Status: Draft

> **Pré-requis schéma** : la table `dbo.Conge` **existe déjà en base** — confirmée par le Tech Lead via le SELECT canonique `SELECT [CongeId], [EmployeeId], [TypeConge], [DateDebut], [DateFin], [Commentaire] FROM [dbo].[Conge] WHERE [EmployeeId] = @EmployeeId`. Aucune nouvelle table n'est créée par cette FEAT. La table n'apparaît pas dans le schéma extrait `workspace/output/db/schema.md` au 2026-05-29 — **re-extraction obligatoire** vers `workspace/output/db/schema.{json,md,diff.md}` avant `dev-backend` (cf. `docs/principles/source-first.md`). Le référentiel des jours fériés français est porté **côté frontend** par une constante TypeScript figée (cf. SFD-10) — aucune table `JourFerie`, aucun endpoint dédié.

## Context

L'assistante maternelle (employée connectée) n'a aujourd'hui **aucun moyen applicatif** de déclarer, consulter ou supprimer ses absences planifiées (congés payés, arrêts maladie, formations, événements familiaux, etc.). La gestion se fait verbalement avec les parents employeurs, sans interface de visualisation calendaire. Le menu principal (`spec-menu-principale` SFD-3, AC-4) ne propose pas d'entrée dédiée à ce domaine fonctionnel — alors que la table `dbo.Conge` **existe déjà en base** mais reste inexploitée par l'application.

Cette FEAT introduit un **module complet de gestion des absences personnelles** de l'assistante maternelle, inspiré du parcours de l'application Lucca (gestion des congés salariés) mais simplifié pour le contexte unipersonnel d'une assistante maternelle indépendante :

1. **Aucune migration DB** dans cette FEAT — la table `dbo.Conge` est utilisée telle qu'existante (colonnes `CongeId`, `EmployeeId`, `TypeConge`, `DateDebut`, `DateFin`, `Commentaire`). Seule la re-extraction du schéma vers `workspace/output/db/schema.{json,md,diff.md}` est requise avant `dev-backend` pour que la table apparaisse comme cible légitime des endpoints scaffoldés.

2. **Nouvelle entrée de menu `Mes congés`** ajoutée à la liste du menu latéral principal (cf. extension de `spec-menu-principale` SFD-3, AC-4) — un clic navigue vers la nouvelle route SPA `/conges`.

3. **Nouvelle page `/conges`** affichant un **calendrier vertical multi-mois** (16 mois — 2 mois passés + mois courant + 13 mois futurs, conformément au mockup `26-1-Spec-Conge.html` ligne 276) fidèle à la maquette : chaque mois est une carte (`.mcard`) avec en-tête `Mois Année`, badge compteur `{N} j` (nombre de jours d'absence présents dans le mois) si > 0, grille 7 colonnes (Lundi → Dimanche), cellules colorées selon le type d'absence (pool fermé de 9 couleurs distinctes définies en SFD-4), jours fériés cerclés en bleu, jour courant souligné. Au chargement, le scroll vertical se positionne automatiquement sur le mois courant (cf. mockup lignes 366-370).

4. **Création d'une absence** via un Floating Action Button (`+` coral, bas droite) qui ouvre un **bottom sheet** (`.sheet`) avec : dropdown de type (9 valeurs SFD-4), input date début, input date fin, textarea commentaire (optionnel), bouton `Enregistrer`. Validation → INSERT en base + re-render du calendrier (apparition des carrés colorés) + scroll vers le mois de la date de début.

5. **Consultation d'une absence** via tap sur une cellule colorée du calendrier → second bottom sheet (`.sheet-wrap#detail`) affichant : pastille couleur, libellé du type, plage `du JJ mois au JJ mois AAAA`, **nombre de jours décomptés** (= jours ouvrés non fériés entre `DateDebut` et `DateFin` inclus — cf. BR-6), commentaire en italique, bouton `Supprimer`.

6. **Suppression d'une absence** via le bouton `Supprimer` du sheet de détail → appel `DELETE /api/conges/{CongeId}` + retrait de la cellule colorée du calendrier sans rechargement complet.

Cette FEAT **n'inclut pas** la modification d'une absence existante (extension future) ni les contrôles métier sur la durée (nombre maximum de jours par type, minimum, plafond annuel, etc.) — ces règles feront l'objet d'une **FEAT séparée dédiée** (`spec-conge-controle` ou équivalent), hors scope de la 26 — demande explicite de l'utilisateur d'isoler cette logique.

La maquette de référence est `workspace/input/ui/26-1-Spec-Conge.html` (mobile, 446 lignes) — le markup HTML (topbar, body, carousel, mcard, grid, fab, sheets, dropdown, dates) est **réutilisé tel quel** côté JSX, seul le contenu (titres de mois, cellules calendrier, dropdown types, dates) devient dynamique. Le design system actif fournit les primitives Sheet, Button, Input, Select, Textarea — utilisées en priorité quand un équivalent existe (cf. BR-17).

## Objective

L'assistante maternelle connectée ouvre le menu latéral principal, clique sur l'item `Mes congés` → le frontend navigue en SPA vers `/conges` et envoie un unique `GET /api/conges` ; le backend exécute la requête SQL canonique paramétrée `SELECT CongeId, EmployeeId, TypeConge, DateDebut, DateFin, Commentaire FROM dbo.Conge WHERE EmployeeId = @SessionEmployeeId ORDER BY DateDebut ASC, CongeId ASC` (sans `INNER JOIN` car la table porte déjà `EmployeeId`). La page affiche un calendrier vertical multi-mois (16 cartes, 2 mois passés + mois courant + 13 mois futurs) avec les jours d'absence colorés selon le type (9 couleurs distinctes), les jours fériés cerclés en bleu (référentiel **frontend** figé, cf. SFD-10), le jour courant souligné. Le scroll initial se positionne sur le mois courant. Un FAB `+` (coral, bas droite) ouvre un bottom sheet de création (dropdown type, dates début/fin, commentaire) qui sur validation déclenche un `POST /api/conges` puis re-render du calendrier. Un tap sur une cellule colorée ouvre un bottom sheet de détail (libellé type, plage, jours décomptés excluant week-ends et jours fériés, commentaire, bouton Supprimer) ; le bouton Supprimer déclenche `DELETE /api/conges/{CongeId}` puis retire la cellule du DOM. Aucun rechargement complet de la page n'est requis pour les opérations CRUD.

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps d'affichage initial du calendrier (Time-To-Interactive après clic sur `Mes congés` dans le menu) + temps de création d'une absence (clic `Enregistrer` → carré coloré visible) + temps de suppression
- Target: p95 affichage initial < 400 ms sur 4G simulé (1 unique requête SQL `SELECT ... FROM Conge WHERE EmployeeId=@x ORDER BY DateDebut ASC` indexée sur `(EmployeeId, DateDebut)` ; payload < 6 KB JSON pour ≤ 30 absences ; constante jours fériés bundlée avec le JS — pas de round-trip) ; p95 création (POST + re-render) < 600 ms ; p95 suppression (DELETE + retrait DOM) < 300 ms ; scroll initial vers mois courant < 100 ms (calcul `offsetTop - 80` côté frontend, pas de round-trip)
- Deadline: livraison stack `dotnet-minimalapi × react × shadcn × dotnet-xunit × azure-ad` (combo validé v7.0.0) au 2026-08-15

## Non-Functional Constraints (v7.0.0)

- Expected volume: ~5-15 absences déclarées par assistante maternelle et par an (faible volume écriture, ~0-2 créations/mois en moyenne) ; ~10-20 ouvertures de la page `/conges` par employée et par mois ; ≤ 30 absences visibles simultanément dans la fenêtre de 16 mois rendue ; ~30-35 jours fériés référentiels (3 ans × ~11 jours fériés français — constante frontend, pas de table)
- Performance SLA: p95 `GET /api/conges` < 200 ms backend (requête simple sur table indexée si l'index `IX_Conge_EmployeeId_DateDebut` existe — sinon scan acceptable au volume attendu) ; p95 `POST /api/conges` < 250 ms (INSERT simple, aucune validation transactionnelle complexe dans cette FEAT — cf. Out of Scope sur les contrôles métier) ; p95 `DELETE /api/conges/{CongeId}` < 150 ms ; pas de risque N+1 (aucune jointure) ; calcul du décompte de jours ouvrés côté frontend (pas de round-trip serveur supplémentaire)
- Data retention: les lignes `dbo.Conge` sont conservées tant que l'employée existe (la gestion CASCADE éventuelle est hors scope de cette FEAT — la suppression d'un compte employée est hors scope global) ; pas de purge automatique des absences passées (rétention illimitée — un congé pris en 2024 reste en base et consultable en 2027 si on élargit la fenêtre frontend ; dans cette FEAT, seuls les 16 mois autour de la date courante sont visuellement rendus, cf. SFD-12)
- Compliance: RGPD — les motifs d'absence (notamment `maladie`, `maternite`, `enfant`) peuvent contenir des informations médicales potentiellement sensibles (catégorie 9 RGPD si pathologie détaillée dans le commentaire) ; visibles et modifiables uniquement par l'employée propriétaire (`Conge.EmployeeId == session.EmployeeId`) ; jamais 403 (anti-énumération d'ID) — toujours 404 sur `CongeId` hors périmètre ; aucune diffusion automatique vers les parents employeurs dans cette FEAT (notification éventuelle = FEAT future séparée) ; le commentaire est facultatif et l'utilisateur est libre de ne rien y mettre (réduction de surface RGPD)
- Integration: aucune migration DB (table `dbo.Conge` pré-existante — cf. Pré-requis schéma) ; trois nouveaux endpoints backend (`GET /api/conges`, `POST /api/conges`, `DELETE /api/conges/{CongeId}`) ; une nouvelle route SPA `/conges` + une nouvelle entrée de menu `Mes congés` (extension de `spec-menu-principale` SFD-3) ; aucun service externe (pas d'iCal, pas de Google Calendar, pas de service de jours fériés tiers) ; constante TypeScript figée pour les jours fériés (cf. SFD-10) — pas de table, pas d'endpoint ; aucune extension du design system actif
- Degraded mode: si `GET /api/conges` échoue (timeout, 5xx, network error), un état d'erreur générique `Impossible de charger vos congés` + bouton `Réessayer` est affiché en lieu et place du calendrier ; si `POST /api/conges` échoue, la cellule pré-affichée optimistement est retirée et un toast `Création impossible — réessayez` est affiché ; si `DELETE /api/conges/{CongeId}` échoue, la cellule retirée optimistement est ré-affichée et un toast `Suppression impossible — réessayez` est affiché ; aucun appel backend n'est envoyé si l'utilisateur ferme le bottom sheet de création sans valider ; les jours fériés étant en constante frontend, aucun mode dégradé associé (la constante est toujours disponible avec le bundle JS)

## Actors

- Employée connectée : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session (cf. `spec-connexion`). Seule autorisée à consulter, créer ou supprimer les absences pour `Conge.EmployeeId == session.EmployeeId`. Aucun accès à la page `/conges` sans authentification (redirect vers `/login` — cf. spec-connexion).

## Functional Needs

### Point d'entrée et navigation

- SFD-1: Une nouvelle entrée de menu `Mes congés` est ajoutée à la liste des items du menu latéral principal du MainLayout (extension de `spec-menu-principale` SFD-3 et AC-4) — **après** l'item `Mes contrats` et **avant** la zone de déconnexion. L'icône associée est `calendar_month` (Material Symbols Outlined — déjà chargée par le mockup ligne 8). Un clic sur cet item déclenche une navigation SPA vers la route `/conges` et ferme le menu (cohérent avec spec-menu-principale AC-5, AC-6).
- SFD-2: Une nouvelle route SPA `/conges` est introduite — protégée par authentification (cohérent avec spec-connexion ; redirect `/login` si pas de token valide). Le composant cible est la page de gestion des absences décrite par cette FEAT. La route est accessible uniquement via le menu latéral principal (pas de deep link partagé dans cette FEAT, mais l'URL est saisissable manuellement dans la barre).
- SFD-3: Aucune autre route SPA n'est introduite par cette FEAT — la création, le détail et la suppression sont gérés via des bottom sheets in-page (pas de navigation vers une sous-route).

### Structure de la table `dbo.Conge` (existante — aucune migration)

- SFD-4: La table `dbo.Conge` **existe déjà en base** (confirmation Tech Lead 2026-05-31 — cf. Pré-requis schéma). Aucune migration DDL n'est créée par cette FEAT. La structure exploitée par les endpoints backend est :
  - `CongeId` — PK surrogate, type `INT IDENTITY(1,1)` (inféré du contexte du projet et du SELECT canonique fourni)
  - `EmployeeId` — FK logique vers `dbo.Employee.EmployeeId` (`INT NOT NULL`)
  - `TypeConge` — clé technique du type d'absence (chaîne) — pool fermé de 9 valeurs (cf. SFD-5) ; tolérance backend en cas de valeur hors pool (rejet `400`) sans dépendre d'une contrainte CHECK SQL côté DB
  - `DateDebut` — premier jour inclus de l'absence (type `DATE`)
  - `DateFin` — dernier jour inclus de l'absence (type `DATE`) ; règle métier `DateFin >= DateDebut` portée par le backend (cf. BR-11) sans dépendre d'une contrainte CHECK SQL
  - `Commentaire` — texte libre optionnel (`NVARCHAR(500)` ou équivalent — borne soft validée backend à 500 caractères)
  
  Le schéma extrait `workspace/output/db/schema.{json,md,diff.md}` doit être **re-généré** avant `dev-backend` pour refléter la table (l'extract au 2026-05-29 est antérieur à sa création — pré-requis externe DBA, hors scope de cette FEAT au sens du code mais bloquant pour la matérialisation backend). Si après re-extraction, des contraintes additionnelles (CHECK `DateFin >= DateDebut`, CHECK `TypeConge IN (...)`, index `IX_Conge_EmployeeId_DateDebut`) sont absentes, leur ajout éventuel est **hors scope de cette FEAT** — le backend porte seul les validations correspondantes (défense backend uniquement, pas de défense en profondeur DB dans cette FEAT).

- SFD-5: Le pool fermé de 9 types d'absence est figé dans cette FEAT et **partagé entre frontend et backend** via un module TypeScript miroir côté frontend et une enum/sealed class côté backend (cf. BR-12). Chaque type porte une `key` technique (stockée en base dans `TypeConge`), un `label` affichable en français et une `color` au format `oklch(...)` exact issue du mockup (lignes 236-246) :

  | Clé        | Libellé                | Couleur (oklch)              | Texte (ink) |
  |---         |---                     |---                           |---          |
  | `paye`     | Congés payé            | `oklch(0.69 0.16 352)` (rose magenta) | `#fff` |
  | `sans`     | Congés sans solde      | `oklch(0.70 0.05 250)` (gris bleuté) | `#fff` |
  | `maladie`  | Arrêt maladie          | `oklch(0.60 0.20 28)` (rouge orangé) | `#fff` |
  | `formation`| Formation              | `oklch(0.58 0.17 300)` (violet) | `#fff` |
  | `enfant`   | Enfant malade          | `oklch(0.74 0.15 62)` (orange chaud) | `oklch(0.36 0.08 62)` |
  | `maternite`| Congés maternité       | `oklch(0.68 0.12 195)` (turquoise) | `#fff` |
  | `familial` | Évènement familial     | `oklch(0.68 0.15 150)` (vert) | `#fff` |
  | `education`| Éducation parental     | `oklch(0.66 0.14 235)` (bleu) | `#fff` |
  | `autres`   | Autres                 | `oklch(0.66 0.02 280)` (gris neutre) | `#fff` |

  Aucune i18n des libellés dans cette FEAT (français unique). Aucun typage métier additionnel (ex. distinction « rémunéré / non rémunéré ») n'est exposé en BR ni en API — le libellé sert d'unique discriminant utilisateur. Toute évolution du pool (ajout d'un 10ᵉ type, retrait, renommage d'une clé) impose une coordination explicite backend ↔ frontend (cf. BR-12).

### Listage des absences — requête SQL canonique

- SFD-6: Au chargement de la page `/conges` (mount du composant racine), le frontend envoie **un unique** `GET /api/conges` (la liste des jours fériés est une constante frontend bundlée — cf. SFD-10, pas d'appel réseau). Aucun pré-fetch en background depuis le menu ou ailleurs — le `GET` est déclenché uniquement au mount de la page (lazy fetch).
- SFD-7: Le backend exécute la requête SQL canonique paramétrée suivante pour `GET /api/conges` (alignée sur le SELECT fourni par le Tech Lead — pas de `INNER JOIN` car la table porte déjà `EmployeeId`) :
  ```sql
  SELECT
    CongeId,
    EmployeeId,
    TypeConge,
    DateDebut,
    DateFin,
    Commentaire
  FROM dbo.Conge
  WHERE EmployeeId = @SessionEmployeeId
  ORDER BY DateDebut ASC, CongeId ASC;
  ```
  `@SessionEmployeeId` provient exclusivement de la variable singleton de session de l'employée connectée (cf. BR-2) ; aucun paramètre de requête utilisateur ne peut le surcharger. La requête retourne 0 à N lignes triées par `DateDebut ASC` puis `CongeId ASC` (déterminisme — cf. BR-5). Aucun filtre temporel côté serveur — toutes les absences passées et futures de l'employée sont retournées ; le filtrage par fenêtre visible est purement côté frontend (rendu uniquement des cellules incluses dans les 16 mois affichés). Toute query-string transmise (`?from=`, `?to=`, `?type=`) est ignorée silencieusement (cf. BR-10).
- SFD-8: La réponse JSON de `GET /api/conges` est de la forme :
  ```json
  [
    { "congeId": 12, "employeeId": 5, "typeConge": "paye",      "dateDebut": "2026-05-15", "dateFin": "2026-05-18", "commentaire": "Pont de l'Ascension" },
    { "congeId": 13, "employeeId": 5, "typeConge": "formation", "dateDebut": "2026-06-09", "dateFin": "2026-06-10", "commentaire": "Formation premiers secours" }
  ]
  ```
  Les noms de champ sont en `camelCase` (cf. library-and-stack §6.bis.3) en miroir des noms TypeScript frontend. Les valeurs NULL backend (`Commentaire`) sont sérialisées `null` JSON. Les types SQL `date` (`DateDebut`, `DateFin`) sont sérialisés en chaîne `"YYYY-MM-DD"` (ISO 8601 sans heure ni TZ — cohérent avec l'absence de notion d'heure dans le métier).

### Référentiel des jours fériés — constante frontend

- SFD-9: Les jours fériés français métropolitains sont rendus dans le calendrier (cercles bleus — cf. SFD-13) à partir d'une **constante TypeScript figée** côté frontend, jamais depuis la base ni un endpoint backend. La constante est portée dans un module dédié (`src/domain/jours-feries.ts` ou équivalent selon stack) et **strictement alignée** sur la liste hardcodée du mockup `26-1-Spec-Conge.html` lignes 251-254 — couvrant les années 2025, 2026 et 2027 (3 ans × ~11 jours fériés = ~33 entrées). Le mockup utilise un `Set<string>` de dates ISO `YYYY-MM-DD` ; le module TypeScript exporte cette même structure plus un libellé optionnel pour usage futur (`{ date: "YYYY-MM-DD", libelle: "Nom usuel" }[]`). Le mockup référence les dates suivantes (à reproduire telles quelles) :
  - **2025** : `2025-01-01`, `2025-04-21`, `2025-05-01`, `2025-05-08`, `2025-05-29`, `2025-06-09`, `2025-07-14`, `2025-08-15`, `2025-11-01`, `2025-11-11`, `2025-12-25`
  - **2026** : `2026-01-01`, `2026-04-06`, `2026-05-01`, `2026-05-08`, `2026-05-14`, `2026-05-25`, `2026-07-14`, `2026-08-15`, `2026-11-01`, `2026-11-11`, `2026-12-25`
  - **2027** : `2027-01-01`, `2027-03-29`, `2027-05-01`, `2027-05-08`, `2027-05-06`, `2027-07-14`, `2027-08-15`, `2027-11-01`, `2027-11-11`, `2027-12-25`
- SFD-10: Le module `jours-feries.ts` expose au minimum :
  - Une constante `JOURS_FERIES: Set<string>` (dates ISO `YYYY-MM-DD`) pour le test d'appartenance O(1) au rendu calendrier (cohérent avec le `FERIES` du mockup ligne 250)
  - Une fonction `isJourFerie(dateISO: string): boolean` — wrapper triviale du `Set.has`
  
  Aucune logique de calcul (Computus pour Pâques, etc.) n'est implémentée — toutes les dates sont en dur. La mise à jour annuelle du référentiel (ajout de l'année 2028, etc.) est une **opération de maintenance manuelle** du module (out of scope cette FEAT).

### Rendu du calendrier — UI

- SFD-11: La page `/conges` affiche un **calendrier vertical multi-mois** sur 16 mois (cohérent avec `buildMonths` du mockup ligne 273-278 : `for (let i = -2; i <= 13; i++)` → 2 mois passés + mois courant + 13 mois futurs = 16 cartes). Chaque mois est rendu sous forme d'une carte `.mcard` du mockup (lignes 34-38) avec :
  - **En-tête `.mcard__head`** : titre `MoisFR Année` (ex. `Mai 2026` avec `2026` en couleur secondaire — cf. mockup ligne 318) + badge compteur `.mcard__count` `{N} j` affiché si au moins 1 jour d'absence est présent dans le mois (cf. mockup ligne 315, `monthCount`). Le compteur N **n'exclut pas** les week-ends ni les jours fériés dans cette version (compte tous les jours de la plage `[DateDebut, DateFin]` chevauchant le mois) — cohérent avec l'affichage visuel qui colore aussi les week-ends contenus dans une plage d'absence. Le décompte « jours décomptés » du sheet de détail (cf. SFD-17, BR-6) lui exclut bien week-ends et fériés.
  - **Bandeau jours de semaine `.wk`** : `L M M J V S D` en majuscule, font-mono (cf. mockup ligne 257)
  - **Grille `.grid` 7 colonnes** : chaque cellule `.d` est carrée (`aspect-ratio: 1`), comporte le numéro de jour en chiffres
- SFD-12: Chaque cellule `.d` du calendrier est rendue selon les règles suivantes (alignées sur la logique `renderCalendar` du mockup lignes 287-325) :
  - **Cellules muettes** (`.d--muted`) : pour les jours du mois précédent ou suivant qui complètent la première semaine (cf. mockup ligne 295) — texte transparent, non cliquable
  - **Jour courant** (`.d--today`) : box-shadow inset 1.5px sur la couleur `ink-900`, font-weight 800 (cf. mockup ligne 49)
  - **Cellule d'absence** (`.d--abs`) : fond coloré selon `TypeConge` (couleur exacte du pool SFD-5), texte `ink` du pool (blanc sauf `enfant`). Bord arrondi variable selon position dans la plage :
    - `.d--abs.s` (start) : `border-radius: 8px 3px 3px 8px` (arrondi gauche)
    - `.d--abs.e` (end) : `border-radius: 3px 8px 8px 3px` (arrondi droit)
    - `.d--abs.m` (middle) : `border-radius: 3px` (presque carré)
    - `.d--abs.se` (single day) : `border-radius: 8px` (carré arrondi)
    - L'attribut `data-absidx="{index}"` est ajouté pour permettre le tap → ouverture du sheet de détail (cf. mockup ligne 308)
  - **Jour férié** (`.d--ferie`) : cercle bleu (texte `oklch(0.50 0.14 240)`, bordure 1.6px `oklch(0.58 0.14 240)`, fond `oklch(0.95 0.03 240)` — cf. mockup lignes 55-56) ; rendu uniquement si la cellule n'est pas déjà une cellule d'absence (les jours fériés sont masqués visuellement par une absence chevauchante)
  - **Week-end** (`.d--we`, samedi/dimanche) : fond gris pastille `var(--nj-line-soft)` (cf. mockup lignes 46-48) ; rendu uniquement si la cellule n'est pas déjà une cellule d'absence
- SFD-13: Au-dessus du carousel de mois, une zone légende `.pad.legend#legend` (cf. mockup ligne 157, 327-332) affiche dynamiquement **les types d'absence présents** dans la liste retournée par `GET /api/conges` (un carré coloré 11×11px + libellé pour chaque type unique, séparés par 12px) suivi d'un item statique `Jour férié` avec un cercle bleu cerclé (rendu spécial — `box-shadow: inset 0 0 0 2px {ferie-color}`). Si aucune absence n'est encore créée, la légende ne contient que l'item `Jour férié`. La légende est re-rendue à chaque création / suppression d'absence (sync avec le calendrier).
- SFD-14: Au chargement initial de la page (résolution du `GET /api/conges`), le scroll vertical du `.body` se positionne automatiquement sur la carte `.mcard` du mois courant (offset `target.offsetTop - 80` — cf. mockup lignes 366-370). Aucune animation (`scrollTop` direct, pas `scrollTo({behavior: 'smooth'})`).

### Création d'une absence — bottom sheet et endpoint POST

- SFD-15: Un Floating Action Button `.fab` (bouton flottant rond, 58×58px, fond coral, icône `+`, position absolute bottom 22px right 18px — cf. mockup lignes 67-69 et 162-164) est rendu en permanence sur la page `/conges` (sauf pendant le squelette de chargement initial — cf. SFD-19). Un clic ouvre le bottom sheet de création (`.sheet-wrap#sheet`). Le bottom sheet (cf. mockup lignes 167-204) affiche :
  - **En-tête `.sheet__head`** : titre `Ajouter une absence` + bouton croix de fermeture
  - **Corps `.sheet__body`** avec :
    1. **Dropdown type d'absence** (`.dd` cf. mockup lignes 113-125 et 178-183) — bouton qui affiche le type courant avec sa pastille couleur ; un clic ouvre la liste `.dd__list` qui montre les 9 options (chacune avec pastille couleur + libellé + chevron coché si sélectionnée). Valeur par défaut au moment de l'ouverture du sheet : `paye` (Congés payé) — cf. mockup ligne 380 et 395
    2. **Date de début** (`.input[type=date]#d-start`) — pré-remplie au moment de l'ouverture avec la date du jour (cf. mockup ligne 418)
    3. **Date de fin** (`.input[type=date]#d-end`) — pré-remplie avec la date du jour + 1 jour (cf. mockup ligne 419)
    4. **Commentaire** (`.input` textarea, placeholder `Commentaire`, optionnel — cf. mockup ligne 197) ; aucune contrainte de longueur côté UI au-delà du soft limit `NVARCHAR(500)` du backend
  - **Pied `.sheet__foot`** : bouton plein largeur `Enregistrer` (`.btn-primary` cf. mockup lignes 127-128 et 201)
- SFD-16: Au clic sur `Enregistrer` (cf. mockup lignes 426-441), le frontend :
  1. Lit les valeurs `selType` (clé du type), `dStart.value` (DateDebut), `dEnd.value` (DateFin), `cmt.value.trim()` (Commentaire)
  2. Si `DateDebut` est vide → ne fait rien (validation soft, pas de toast — cohérent avec mockup ligne 428)
  3. Si `DateFin` est vide → utilise `DateDebut` (absence d'un seul jour — cohérent avec mockup ligne 429)
  4. **Normalise l'ordre** : si `DateFin < DateDebut`, swap les deux valeurs (cohérent avec mockup ligne 430) — défense côté frontend pour ne jamais POSTer une plage inversée (cf. BR-11)
  5. Envoie un `POST /api/conges` avec payload JSON `{ typeConge, dateDebut, dateFin, commentaire }` (le champ `commentaire` est envoyé même vide — pas omis) ; le backend dérive `EmployeeId` de la session, jamais transmis par le client
  6. Sur succès `201 Created` avec le `Conge` créé en réponse : ferme le sheet, ajoute la nouvelle absence à la liste locale en mémoire, re-render le calendrier et la légende, puis scroll vers le mois de `DateDebut` (cohérent avec mockup lignes 435-440)
  7. Sur échec : retire l'ajout optimiste si déjà fait, affiche un toast `Création impossible — réessayez`
- SFD-17: Le backend exécute la requête SQL paramétrée suivante pour `POST /api/conges` :
  ```sql
  INSERT INTO dbo.Conge (EmployeeId, TypeConge, DateDebut, DateFin, Commentaire)
    OUTPUT INSERTED.CongeId, INSERTED.EmployeeId, INSERTED.TypeConge,
           INSERTED.DateDebut, INSERTED.DateFin, INSERTED.Commentaire
    VALUES (@SessionEmployeeId, @TypeConge, @DateDebut, @DateFin, @Commentaire);
  ```
  Le backend valide en amont (validations applicatives — pas de défense DB requise par cette FEAT, cf. SFD-4) :
  - `TypeConge` doit être l'une des 9 valeurs autorisées (cf. SFD-5) — sinon `400 Bad Request` ProblemDetails
  - `DateDebut` et `DateFin` doivent être des dates ISO valides — sinon `400`
  - `DateFin >= DateDebut` — sinon `400` (la défense backend est l'unique garde-fou)
  - `Commentaire` ≤ 500 caractères après trim — sinon `400`
  - **Aucune validation métier de plafond / durée maximum dans cette FEAT** (out of scope — cf. FEAT future `spec-conge-controle`)

  Retourne `201 Created` avec le Conge inséré (camelCase, mêmes champs que SFD-8). Aucun header `Location` n'est requis dans cette FEAT (la ressource n'est pas individuellement adressable par GET — cf. Out of Scope sur `GET /api/conges/{CongeId}`).

### Détail et suppression d'une absence — bottom sheet et endpoint DELETE

- SFD-18: Un tap sur une cellule `.d--abs` du calendrier (data-absidx présent) ouvre le bottom sheet de détail (`.sheet-wrap#detail` — cf. mockup lignes 207-227, 340-358). Le sheet affiche :
  - Une pastille couleur verticale (`#det-swatch`, 14×36px) prenant la couleur du `TypeConge`
  - Le **libellé** du type (ex. `Congés payé`) en gras 17px
  - La **plage de dates** formatée en français :
    - Si single-day (1 jour) : `JJ mois AAAA` (ex. `15 mai 2026`)
    - Sinon : `du JJ mois au JJ mois AAAA` (ex. `du 15 mai au 18 mai 2026`)
  - Le **nombre de jours décomptés** (cf. BR-6) affiché en gros chiffres + `jour` / `jours` (cf. mockup ligne 355) — **calculé côté frontend** en excluant les samedis, dimanches et jours présents dans la constante `JOURS_FERIES` (cf. SFD-10)
  - Le **commentaire** en italique (ou rien si NULL)
  - Bouton `Fermer` (annulation) et bouton `Supprimer` (couleur danger / coral, icône corbeille — cf. mockup ligne 224)
- SFD-19: Un clic sur `Supprimer` du sheet de détail déclenche :
  1. Mise à jour optimiste — l'absence est retirée de la liste locale, le calendrier et la légende sont re-rendus immédiatement (les cellules colorées disparaissent), le sheet de détail est fermé
  2. Appel `DELETE /api/conges/{CongeId}` (body vide)
  3. En cas de succès `204 No Content` — aucune action UI supplémentaire (l'optimistic update est conservé)
  4. En cas d'échec (`4xx`, `5xx`, network error) — rollback : l'absence est ré-ajoutée à la liste locale à sa position d'origine (tri `DateDebut ASC, CongeId ASC` préservé), le calendrier et la légende re-rendus, un toast `Suppression impossible — réessayez` est affiché
- SFD-20: Le backend exécute la requête SQL paramétrée suivante pour `DELETE /api/conges/{CongeId}` :
  ```sql
  DELETE FROM dbo.Conge
   WHERE CongeId = @CongeId
     AND EmployeeId = @SessionEmployeeId;
  ```
  Le filtre `EmployeeId = @SessionEmployeeId` garantit qu'aucune absence n'est supprimée hors du périmètre de l'employée connectée (anti-cross-tenant — cf. BR-2, BR-3). Si `@@ROWCOUNT = 0` (absence inexistante OU hors périmètre), le backend retourne **404 Not Found** (jamais 403 — anti-énumération d'ID). Si `@@ROWCOUNT = 1`, retour `204 No Content`. Pas de cas `> 1` (PK unique).

### Décompte des jours ouvrés non fériés (logique frontend)

- SFD-21: Le calcul du « nombre de jours décomptés » affiché dans le sheet de détail (SFD-18) est défini comme suit (algorithme déterministe côté frontend) :
  ```
  Soient DateDebut et DateFin la plage d'absence (inclusive)
  Soit FERIES la constante JOURS_FERIES (cf. SFD-10)

  decompte = 0
  Pour chaque date d de DateDebut à DateFin inclus :
    Si d.weekday ∈ {samedi, dimanche} → continue (skip)
    Si d ∈ FERIES → continue (skip)
    decompte += 1
  Retourner decompte
  ```
  Conséquence : une absence du **vendredi 1ᵉʳ mai 2026 (Fête du Travail) au lundi 4 mai 2026** comporte 4 jours calendaires mais **1 jour décompté** (lundi 4 — vendredi 1ᵉʳ étant férié, samedi 2 et dimanche 3 étant week-end). Cette logique reflète la spec verbale utilisateur : « il ne faut pas compter ces jours-là, parce qu'ils sont déjà offerts ... il faut compter que les jours qui ne sont pas des jours fériés et des jours samedi et dimanche. »
- SFD-22: Le calcul SFD-21 est **purement informationnel** dans cette FEAT — il n'agit ni comme borne min / max, ni comme alerte, ni comme contrôle de plafond. La FEAT future `spec-conge-controle` exploitera cette même formule pour valider des règles métier (plafond annuel CP, durée max d'un arrêt maladie, etc.).

### Légende et états UI

- SFD-23: Pendant le `GET /api/conges` initial, le `.body` affiche un état squelette / spinner global ; aucune donnée placeholder ne doit être visible. Le FAB `+` est masqué pendant le chargement initial (création possible uniquement après hydratation du calendrier).
- SFD-24: Si la liste `GET /api/conges` est vide (`[]`), le calendrier affiche tout de même les 16 mois avec uniquement les jours fériés cerclés et le jour courant souligné — aucune carte colorée. La légende contient uniquement l'item `Jour férié`. Le FAB `+` reste affiché et fonctionnel.
- SFD-25: Si `GET /api/conges` échoue (timeout, 5xx, network error), le calendrier est remplacé par un message d'erreur centré `Impossible de charger vos congés` + bouton `Réessayer` (re-déclenche le `GET`). Le FAB `+` est masqué dans cet état (création impossible sans contexte de liste).

## Business Rules

- BR-1: L'endpoint `GET /api/conges` exécute la requête SQL canonique de SFD-7 — paramétrée (`@SessionEmployeeId`), sans `INNER JOIN` (la table porte déjà `EmployeeId`) ; aucune concaténation de chaîne autorisée (anti-injection SQL). L'endpoint `POST /api/conges` exécute SFD-17 (INSERT paramétré). L'endpoint `DELETE /api/conges/{CongeId}` exécute SFD-20 (filtre `EmployeeId` propagé).
- BR-2: `@SessionEmployeeId` provient exclusivement de la variable singleton de session de l'employée connectée (cf. `spec-connexion`, `spec-bebe-rdv` BR-2) ; aucun paramètre de requête utilisateur ne peut le surcharger, aucun champ `employeeId` du payload `POST` n'est lu par le backend (il est inscrit en base depuis la session uniquement).
- BR-3: Le DELETE sur un `CongeId` hors périmètre (appartenant à une autre employée ou inexistant) retourne **404 Not Found** (jamais 403 — anti-énumération d'ID). Le GET ne peut retourner que les absences de l'employée connectée (filtre serveur), donc la fuite cross-tenant est impossible.
- BR-4: Le pool des 9 types d'absence (cf. SFD-5) est **figé** dans cette FEAT. Toute valeur de `TypeConge` hors pool est rejetée en `400 Bad Request` côté backend (validation applicative — pas de contrainte CHECK SQL requise par cette FEAT, cf. SFD-4). Les couleurs `oklch` sont strictement celles du mockup, sans mapping alternatif (HSL, hex). Le rendu HTML utilise directement `style="background:{oklch}"` sur les cellules `.d--abs` (cohérent avec mockup ligne 308). L'inversion de couleur du texte sur cellule (`#fff` par défaut, sauf `enfant` qui utilise `oklch(0.36 0.08 62)`) est portée par le champ `ink` du module miroir frontend.
- BR-5: Les absences sont retournées par `GET /api/conges` triées par `DateDebut ASC` puis `CongeId ASC` côté serveur (ORDER BY SQL — pas de re-tri côté UI). Si deux absences ont la même `DateDebut`, l'ordre tertiaire est `CongeId ASC` (déterministe).
- BR-6: Le décompte de « jours décomptés » (SFD-21) exclut systématiquement samedis, dimanches et jours présents dans la constante `JOURS_FERIES` (SFD-10). Le calcul est effectué **côté frontend** uniquement (économie d'un round-trip — les jours fériés sont bundlés avec le JS). Le backend ne calcule pas le décompte dans cette FEAT (ni dans la persistance, ni dans l'API) — la valeur n'est jamais transmise, jamais persistée.
- BR-7: Les valeurs NULL backend (`Commentaire`) sont sérialisées `null` JSON (cf. library-and-stack §6.bis.3) et affichées comme contenu omis côté UI (jamais `null` ou `undefined` visible utilisateur — cohérent avec spec-bebe-rdv BR-10).
- BR-8: La maquette `26-1-Spec-Conge.html` (446 lignes) est la **maquette de référence canonique** ; le markup HTML (topbar `.topbar`, body `.body`, carousel `.carousel`, mcard `.mcard`, grid `.grid`, fab `.fab`, sheets `.sheet-wrap`, dropdown `.dd`) est **réutilisé tel quel** côté JSX — seul son contenu (titres, cellules, options) devient dynamique. Aucune réorganisation du DOM, aucune dénomination de classe CSS différente n'est autorisée sans amendement explicite de cette FEAT.
- BR-9: La navigation SPA de l'item de menu `Mes congés` utilise le mécanisme du routeur frontend actif (cf. spec-menu-principale BR-2) — l'usage de `<a href>` brut est interdit pour cet item (un `<a>` peut rester dans le markup statique de l'icône mais le clic doit être intercepté par le routeur).
- BR-10: La requête `GET /api/conges` ne filtre **pas** par fenêtre temporelle côté serveur (aucun paramètre `?from=...&to=...` accepté). Le volume d'absences par employée est faible (~5-15/an — cf. Non-Functional Constraints) ; toutes sont retournées et le filtrage par fenêtre visible est purement côté frontend. Toute query-string sur `GET /api/conges` est ignorée silencieusement.
- BR-11: La normalisation de l'ordre `DateFin >= DateDebut` est faite à 2 niveaux dans cette FEAT (le 3ᵉ niveau DB CHECK est hors scope, cf. SFD-4) :
  1. **Frontend** : swap silencieux des deux valeurs si `dEnd.value < dStart.value` (cf. SFD-16 étape 4)
  2. **Backend** : validation explicite avant INSERT — si `DateFin < DateDebut`, retour `400 Bad Request` ProblemDetails
- BR-12: Le module TypeScript miroir des 9 types d'absence (`src/domain/conge-types.ts` ou équivalent côté frontend) doit dupliquer **à l'identique** les `key`, `label`, `color` et `ink` du backend (cf. SFD-5). Tout désynchro est un bug catégorisé `[FRONTEND_BACKEND_CONTRACT_GAP]` (cf. `library-and-stack.md` §6.bis et `error-classification.md §1.6`). Une alternative future serait la génération du module TS depuis l'OpenAPI 3 du backend — non systématisée dans cette FEAT.
- BR-13: Le badge compteur du mois `.mcard__count` (cf. SFD-11) compte **tous** les jours de la plage `[DateDebut, DateFin]` intersectant le mois, **sans** exclure week-ends ni fériés. Cohérence avec le mockup ligne 304 (`monthCount++` pour chaque cellule colorée). Le décompte « ouvré » de SFD-21 est utilisé uniquement dans le sheet de détail — pas dans le badge mensuel.
- BR-14: Aucune information technique (stack trace, identifiant interne, exception SQL) n'est exposée dans les messages d'erreur visibles à l'utilisateur. Les toasts d'erreur sont génériques (`Création impossible — réessayez`, `Suppression impossible — réessayez`, `Impossible de charger vos congés`).
- BR-15: Aucune notification automatique vers les parents employeurs au moment de la création ou de la suppression d'une absence dans cette FEAT. Toute extension de notification relève d'une FEAT future dédiée.
- BR-16: Aucun pré-fetch en background des congés ne se fait depuis le menu principal — le `GET /api/conges` est déclenché **uniquement** au mount du composant `/conges` après navigation (lazy fetch — cohérent avec spec-bebe-rdv SFD-1 et économie de bande passante pour les sessions sans consultation des congés).
- BR-17: Le commentaire est facultatif (NULL admis en base SFD-4) ; l'utilisateur peut créer une absence sans commentaire et le sheet de détail affichera simplement aucun bloc `.det-cmt` (pas de texte placeholder, pas de tirets — l'élément DOM est rendu vide ou avec `display:none`).
- BR-18: Si le design system actif fournit des composants équivalents (`Sheet`/`Drawer` pour le bottom sheet, `Select` pour le dropdown de type, `Input[type=date]` natif ou un `DatePicker`, `Textarea`, `Button` solid/ghost), ils DOIVENT être utilisés en priorité (cf. spec-bebe-rdv BR-17, spec-menu-principale BR-3) ; le CSS isolé du mockup ne complète que pour atteindre la fidélité visuelle (couleurs `oklch`, layout grille calendrier, géométrie pastille/bordure des cellules `.d--abs`).
- BR-19: La FEAT **étend** `spec-menu-principale` : la liste des items du menu latéral (cf. spec-menu-principale SFD-3, AC-4) est complétée d'un 5ᵉ item `Mes congés` (après `Mes contrats`). Aucun autre item existant n'est modifié, retiré, ni réordonné. La spec-menu-principale AC-4 reste applicable pour les 4 items existants — un avenant à cette AC est implicitement porté par AC-1 ci-dessous.
- BR-20: Aucune logique de chevauchement (overlap) de plages d'absence n'est implémentée dans cette FEAT — deux absences peuvent se chevaucher en base et le rendu visuel privilégie la **dernière déclarée** sur les jours en conflit (la cellule colorée prend la couleur du `TypeConge` de l'absence dont le `CongeId` est le plus élevé — ordre `DateDebut ASC, CongeId ASC` puis itération `for-each` sur les absences, la dernière écrasant les précédentes ; cohérent avec le pattern `absForDay` du mockup ligne 281-283 qui retient le premier match en ordre stocké). Une éventuelle UI de conflit (avertissement, refus) sera portée par `spec-conge-controle`.
- BR-21: La constante `JOURS_FERIES` (cf. SFD-9, SFD-10) est figée pour 2025-2027 dans cette FEAT. Toute date hors cette plage triennale est traitée comme un jour ouvré normal (pas de cercle bleu dans le calendrier, comptée dans le décompte SFD-21). La mise à jour annuelle du module (ajout des dates 2028, etc.) est une opération de maintenance hors scope cette FEAT.

## Acceptance Criteria

- AC-1: Le menu latéral principal (cf. spec-menu-principale) affiche un nouvel item `Mes congés` avec icône `calendar_month`, positionné après `Mes contrats` et avant la zone de déconnexion. Un clic déclenche une navigation SPA vers `/conges` et ferme le menu (cohérent avec spec-menu-principale AC-5, AC-6 étendus).
- AC-2: La table `dbo.Conge` est exploitée telle qu'existante (aucune migration créée par cette FEAT). Le fichier `workspace/output/db/schema.{json,md}` est régénéré (re-extraction DBA) **avant** la matérialisation `dev-backend` et liste la table avec ses colonnes `CongeId, EmployeeId, TypeConge, DateDebut, DateFin, Commentaire`. Si la régénération n'a pas eu lieu, `dev-backend` peut émettre un warning `[SCHEMA_MISMATCH]` mais la livraison est tolérée si les endpoints fonctionnent runtime (la table existe bien en base).
- AC-3: Le module frontend `jours-feries.ts` exporte la constante `JOURS_FERIES: Set<string>` contenant exactement les ~33 dates ISO listées en SFD-9 (2025-2027). Une fonction `isJourFerie(dateISO)` retourne `true` ssi la date est dans le Set.
- AC-4: La route SPA `/conges` est accessible et déclenche, au mount du composant racine, **une unique** requête `GET /api/conges` (vérifiable côté Network DevTools). Aucun appel `GET /api/jours-feries` (l'endpoint n'existe pas — référentiel frontend). Aucun autre appel backend n'est envoyé par le rendu initial du calendrier.
- AC-5: `GET /api/conges` exécute exactement la requête SQL de SFD-7 (`SELECT CongeId, EmployeeId, TypeConge, DateDebut, DateFin, Commentaire FROM dbo.Conge WHERE EmployeeId = @SessionEmployeeId ORDER BY DateDebut ASC, CongeId ASC`) — vérifiable côté logs SQL ou test d'intégration. La réponse JSON est un tableau (jamais un objet enveloppant `{ data: [...] }`) trié par `dateDebut ASC` ; chaque élément contient `congeId, employeeId, typeConge, dateDebut, dateFin, commentaire` en `camelCase` (cf. SFD-8).
- AC-6: La page `/conges` affiche un calendrier vertical de 16 mois (2 passés + courant + 13 futurs) ; chaque mois est rendu sous forme de carte `.mcard` avec titre `Mois Année`, badge compteur `{N} j` (si > 0), bandeau jours `L M M J V S D`, grille 7 colonnes (Lundi en première colonne, Dimanche en dernière). La fidélité visuelle est conforme à `26-1-Spec-Conge.html` (markup conservé tel quel — cf. BR-8).
- AC-7: Au chargement initial, le scroll vertical du `.body` se positionne automatiquement sur la carte `.mcard` du mois courant (offset `target.offsetTop - 80` — cf. mockup ligne 369). Aucune animation de scroll initial.
- AC-8: Chaque cellule de jour d'une absence est colorée selon le `TypeConge` (couleur `oklch` exacte de SFD-5), avec bordure variable selon position (`s` start, `e` end, `m` middle, `se` single-day). Le texte est blanc sauf pour `enfant` (brun foncé `oklch(0.36 0.08 62)`).
- AC-9: Chaque jour férié présent dans la constante `JOURS_FERIES` et **non couvert** par une absence est rendu cerclé en bleu (texte `oklch(0.50 0.14 240)`, bordure inset 1.6px, fond `oklch(0.95 0.03 240)`). Un jour férié couvert par une absence prend la couleur de l'absence (priorité absence > férié).
- AC-10: La zone légende `.legend` affiche dynamiquement les types d'absence présents dans la liste retournée (un item par type unique avec carré coloré 11×11px + libellé) suivi d'un item statique `Jour férié` (cercle bleu cerclé inset). Si la liste est vide, seule l'entrée `Jour férié` est rendue.
- AC-11: Un Floating Action Button `.fab` (coral, icône `+`, 58×58px, position absolute bottom 22px right 18px) est visible en permanence sur `/conges` (sauf pendant l'état squelette du chargement initial — cf. SFD-23). Un clic ouvre le bottom sheet de création.
- AC-12: Le bottom sheet de création affiche : dropdown type (9 options avec pastille couleur, valeur par défaut `paye`), input date début (pré-rempli au jour courant), input date fin (pré-rempli au jour courant + 1), textarea commentaire (optionnel), bouton `Enregistrer` plein largeur (`.btn-primary`). Un clic sur la croix ou le scrim ferme le sheet sans envoyer d'appel backend.
- AC-13: Au clic sur `Enregistrer`, le frontend envoie un `POST /api/conges` avec payload JSON `{ typeConge, dateDebut, dateFin, commentaire }`. Si `dateFin < dateDebut`, le swap est fait côté frontend avant l'envoi (cf. BR-11 niveau 1). En cas de succès `201 Created`, le sheet se ferme, le calendrier et la légende sont re-rendus avec la nouvelle absence visible, et le scroll se positionne sur le mois de la date de début.
- AC-14: Le backend exécute la requête SQL paramétrée de SFD-17 (`INSERT ... OUTPUT INSERTED.*`) avec validation `TypeConge IN (...)`, `DateFin >= DateDebut`, `Commentaire <= 500` ; en cas d'échec de validation, retour `400 Bad Request` ProblemDetails. Aucune contrainte DB CHECK n'est attendue (cf. SFD-4) — la validation backend est seule garante.
- AC-15: Un tap sur une cellule `.d--abs` du calendrier (cellule d'absence) ouvre le bottom sheet de détail (`#detail`) avec pastille couleur verticale, libellé du type, plage formatée FR (`JJ mois AAAA` si 1 jour, sinon `du JJ mois au JJ mois AAAA`), nombre de jours décomptés (SFD-21), commentaire en italique (ou rien si NULL), boutons `Fermer` et `Supprimer`.
- AC-16: Le décompte de jours du sheet de détail est calculé côté frontend selon SFD-21 (exclusion samedi/dimanche/fériés de la constante `JOURS_FERIES`). Exemple vérifiable : pour une absence `2026-05-01` (Fête du Travail, vendredi) → `2026-05-04` (lundi), le décompte affiché est `1 jour` (lundi 4 uniquement — vendredi férié, samedi/dimanche WE).
- AC-17: Un clic sur `Supprimer` du sheet de détail déclenche `DELETE /api/conges/{CongeId}` et retire l'absence du calendrier en mise à jour optimiste (le sheet se ferme, les cellules colorées disparaissent). En cas d'échec, rollback : l'absence est ré-injectée et un toast `Suppression impossible — réessayez` est affiché.
- AC-18: Le backend exécute la requête SQL paramétrée de SFD-20 (`DELETE FROM Conge WHERE CongeId = @x AND EmployeeId = @session`). Un appel direct avec un `CongeId` d'une autre employée retourne `404 Not Found` (0 ligne supprimée, jamais 403 — cf. BR-2, BR-3).
- AC-19: Aucun paramètre client n'est accepté par `GET /api/conges` — toute query-string (`?from=...`, `?to=...`, `?type=...`) est ignorée silencieusement, toutes les absences de l'employée sont retournées (cf. BR-10).
- AC-20: Pendant le `GET /api/conges` initial, le `.body` affiche un état squelette / spinner global et le FAB est masqué. Une fois la `Promise` résolue, le calendrier s'hydrate complètement et le FAB devient visible.
- AC-21: Si `GET /api/conges` échoue, le calendrier est remplacé par `Impossible de charger vos congés` + bouton `Réessayer` ; un nouveau clic re-déclenche le `GET`. Le FAB est masqué.
- AC-22: Si `POST /api/conges` échoue après une création optimiste, la cellule pré-affichée est retirée et un toast `Création impossible — réessayez` est affiché.
- AC-23: La cohérence des autres FEATs n'est pas dégradée : `spec-menu-principale` AC-4 reste vérifié pour ses 4 items historiques + le nouvel item `Mes congés` (5 items au total) ; toute autre route SPA (`/bebes`, `/rapports`, etc.) reste fonctionnelle sans régression.

## Dependencies

- **spec-menu-principale** (`5-spec-menu-principale`) : **étendue** par cette FEAT — la liste d'items SFD-3 et AC-4 est complétée d'un 5ᵉ item `Mes congés` positionné après `Mes contrats`. La spec-menu-principale BR-2 (navigation SPA via routeur) reste applicable pour ce nouvel item (cf. BR-9).
- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employée connectée ; redirection vers `/login` en l'absence de session valide ; 401 backend sur les 3 nouveaux endpoints déclenche le redirect côté frontend.
- **Table `dbo.Conge` pré-existante** : pré-requis externe — la table existe déjà en base (confirmation Tech Lead 2026-05-31). Re-extraction du schéma `workspace/output/db/schema.{json,md,diff.md}` requise avant `dev-backend` (pré-requis externe DBA, hors scope code de cette FEAT mais bloquant pour la matérialisation).
- **spec-conge-controle** (FEAT future — non créée) : implémentera les contrôles métier sur la durée des absences (nombre maximum de jours par type, minimum, plafond annuel CP, alerte si dépassement, refus côté backend). Sans cette FEAT future, aucune validation métier de durée n'est faite dans la 26 — le seul refus est `DateFin < DateDebut` (cf. BR-11) et le pool fermé des 9 types (cf. BR-4). Cohérent avec la demande explicite de l'utilisateur d'isoler ces règles dans une spec séparée.

## Functional Deliverables

- FD-1: Aucune migration DB créée par cette FEAT (la table `dbo.Conge` pré-existe). Re-extraction du schéma vers `workspace/output/db/schema.{json,md,diff.md}` requise (opération DBA externe — cf. Pré-requis schéma et Dependencies).
- FD-2: Extension de la liste d'items du menu latéral principal (cf. spec-menu-principale) d'un 5ᵉ item `Mes congés` (icône `calendar_month`, route `/conges`, position après `Mes contrats`) avec navigation SPA et fermeture du menu au clic (cf. BR-9).
- FD-3: Nouvelle route SPA `/conges` protégée par authentification, route racine de la page de gestion des absences.
- FD-4: Endpoint backend `GET /api/conges` exécutant la requête SQL paramétrée de SFD-7 (sans `INNER JOIN` — la table porte `EmployeeId`), retournant un tableau JSON `[{ congeId, employeeId, typeConge, dateDebut, dateFin, commentaire }, ...]` (camelCase, valeurs NULL → `null`, dates → `"YYYY-MM-DD"`).
- FD-5: Endpoint backend `POST /api/conges` exécutant la requête SQL paramétrée de SFD-17 (`INSERT ... OUTPUT INSERTED.*`) avec validation applicative `TypeConge IN (...)`, `DateFin >= DateDebut`, `Commentaire ≤ 500 chars` ; retournant `201 Created` avec le Conge créé en réponse, ou `400 Bad Request` ProblemDetails en cas d'échec validation.
- FD-6: Endpoint backend `DELETE /api/conges/{CongeId}` exécutant la requête SQL paramétrée de SFD-20 (filtre `EmployeeId` propagé pour anti-cross-tenant), retournant `204 No Content` en cas de succès et `404 Not Found` si 0 ligne supprimée.
- FD-7: Composant page `/conges` (React/Blazor/Vue/Angular selon stack actif) qui, au mount, déclenche le `GET /api/conges`, hydrate un état local `{ absences: Conge[], status: 'loading'|'ready'|'error' }`, et rend le calendrier multi-mois en accord avec SFD-11, SFD-12, SFD-13, SFD-14. Le référentiel jours fériés est consommé depuis le module `jours-feries.ts` (FD-9).
- FD-8: Module TypeScript miroir des 9 types d'absence (`src/domain/conge-types.ts` ou équivalent — cf. BR-12) exposant `{ key, label, color, ink }` pour chaque type, dupliqué à l'identique du backend (enum / sealed class selon le stack runtime).
- FD-9: Module TypeScript `src/domain/jours-feries.ts` (ou équivalent selon stack) exportant la constante `JOURS_FERIES: Set<string>` figée pour 2025-2027 (cf. SFD-9) et la fonction `isJourFerie(dateISO: string): boolean` ; aucune dépendance backend.
- FD-10: Composant bottom sheet de création (`SheetCreation`) avec dropdown type, inputs date début/fin pré-remplis, textarea commentaire, bouton Enregistrer ; câblé sur `POST /api/conges` et orchestrant la mise à jour optimiste de l'état local + scroll vers le mois cible (cf. SFD-16, AC-12, AC-13).
- FD-11: Composant bottom sheet de détail (`SheetDetail`) déclenché par tap sur cellule `.d--abs` ; affiche pastille couleur, libellé, plage FR formatée, décompte jours ouvrés non fériés (SFD-21), commentaire, boutons Fermer et Supprimer ; câblé sur `DELETE /api/conges/{CongeId}` avec mise à jour optimiste (cf. AC-15, AC-16, AC-17).
- FD-12: Calcul frontend du décompte de jours ouvrés non fériés (SFD-21, BR-6) — fonction utilitaire pure prenant `(dateDebut, dateFin)` et retournant un entier, en consommant la constante `JOURS_FERIES` du module FD-9 ; utilisée par `SheetDetail` et exposée pour usage futur par `spec-conge-controle`.
- FD-13: Légende dynamique (`.legend`) re-rendue à chaque mutation de la liste d'absences ; un item par type présent + un item statique `Jour férié` (cercle inset bleu — cf. SFD-13, AC-10).
- FD-14: Gestion des états UI : squelette / spinner pendant le `GET` initial, état d'erreur global si `GET /api/conges` échoue (avec bouton `Réessayer`) — cf. SFD-23, SFD-25, AC-20, AC-21.
- FD-15: Gestion des sessions expirées (401 → redirect `/login` cf. spec-connexion) sur les 3 endpoints de cette FEAT.

## Out of Scope

- **Modification d'une absence existante** (édition de `TypeConge`, `DateDebut`, `DateFin`, `Commentaire` après création) — endpoint `PUT /api/conges/{CongeId}` non créé dans cette FEAT, sheet d'édition non implémenté. L'utilisateur doit supprimer puis recréer en cas de besoin (workflow connu, accepté pour la livraison initiale). Extension future possible dans `spec-conge-controle` ou une FEAT dédiée à l'édition.
- **Contrôles métier sur la durée des absences** : nombre maximum de jours par type (ex. plafond annuel CP à 25 jours ouvrés), nombre minimum, plafond glissant, alerte en cas de dépassement, refus côté backend si dépassement — **couvert par une FEAT future séparée** (`spec-conge-controle` ou équivalent) — demande explicite de l'utilisateur d'isoler cette logique dans une spec à part.
- **Détection de chevauchement** entre deux absences de la même employée (overlap des plages) — deux absences peuvent se chevaucher en base dans cette FEAT (cf. BR-20) ; le rendu visuel privilégie la dernière en ordre stocké. Logique de conflit, refus ou avertissement = `spec-conge-controle`.
- **Migration DB / ajout de contraintes** sur `dbo.Conge` (CHECK `DateFin >= DateDebut`, CHECK `TypeConge IN (...)`, index `IX_Conge_EmployeeId_DateDebut`, colonnes d'audit `CreatedAt`/`UpdatedAt`) — la table est utilisée telle qu'existante ; le hardening DB est hors scope de cette FEAT. La défense backend (validation applicative) est seule garante des règles.
- **Référentiel `dbo.JourFerie` en base** — pas de table dédiée aux jours fériés dans cette FEAT ; la liste est portée en constante TypeScript frontend (cf. SFD-9, SFD-10, BR-21). Toute migration vers une table SQL (avec API admin de mise à jour, calcul Computus pour Pâques dynamique, etc.) serait l'objet d'une FEAT future dédiée.
- **Endpoint `GET /api/jours-feries`** — n'existe pas dans cette FEAT (référentiel frontend uniquement). À considérer si une seconde application (employeur, agence) doit partager le référentiel.
- **Notification automatique aux parents employeurs** au moment de la création / suppression d'une absence (SMS, email, push, message in-app) — out of scope strict (anti-confusion avec `spec-rapport-sms` qui couvre le rapport du jour, pas les congés).
- **Endpoint `GET /api/conges/{CongeId}`** (récupération d'un Conge unique pour pré-remplissage d'un formulaire d'édition) — non requis dans cette FEAT (le sheet de détail lit depuis l'état local frontend, pas depuis un nouveau round-trip backend). À créer par la FEAT future d'édition.
- **Filtrage / recherche** sur la liste des absences (par type, par plage, par mois) — out of scope. La liste est exhaustive et le filtrage visuel est limité à la fenêtre de 16 mois rendue.
- **Vue alternative** (vue tableau, vue annuelle compacte, vue par type) — la seule vue est le calendrier vertical multi-mois. Aucune bascule vue / format n'est exposée à l'utilisateur.
- **Élargissement dynamique de la fenêtre de rendu** (charger d'autres mois passés ou futurs par scroll infini) — la fenêtre est figée à 16 mois (cf. SFD-11). Les absences hors fenêtre existent en base mais ne sont pas rendues visuellement (elles sont cependant dans la liste retournée par `GET /api/conges` — non utilisées par le rendu).
- **Export / partage** (PDF, ICS, lien public, copie vers presse-papiers) — out of scope.
- **Multi-device / synchronisation temps réel** entre deux sessions de la même employée — une absence créée sur device A apparaît sur device B uniquement après un rechargement de la page `/conges` (re-déclenchement du `GET`). Aucun mécanisme push (WebSocket, SSE) dans cette FEAT.
- **Synchronisation iCal / Google Calendar / Outlook** (export/import bidirectionnel) — out of scope strict.
- **Pièces jointes** (justificatif médical PDF pour `maladie`, certificat de formation pour `formation`, etc.) — out of scope. Le seul stockage de métadonnée libre est le champ `Commentaire`.
- **Catégorisation rémunéré / non rémunéré** des types d'absence et calcul automatique des indemnités — out of scope (logique paie hors périmètre du POC application).
- **Mise à jour annuelle automatique du référentiel `JOURS_FERIES`** (ajout des dates 2028, 2029, calcul Computus pour Pâques) — out of scope ; mise à jour manuelle du module TS chaque fin d'année (cf. BR-21).
- **Internationalisation (i18n)** des libellés des 9 types d'absence et des libellés de jours fériés — français unique dans cette FEAT.
- **Sélection multi-jours non contigus** (créer 3 absences distinctes en un seul flow sans rouvrir le sheet 3 fois) — out of scope. Un sheet de création = une plage `[DateDebut, DateFin]` contiguë.
- **Drag & drop pour déplacer une absence dans le calendrier** — out of scope.
- **Confirmation post-suppression avec undo** (toast `Absence supprimée · Annuler`) — out of scope. La suppression est définitive après clic sur le bouton `Supprimer` du sheet de détail (pas de modale de confirmation intermédiaire — différence assumée avec spec-bebe-rdv FEAT 13 ; ici le sheet de détail lui-même tient lieu de double opt-in puisque l'utilisateur l'a explicitement ouvert avant de cliquer Supprimer).
- **Permissions parents employeurs** (consultation des absences de l'assistante maternelle côté Employeur, validation d'une demande de congé) — out of scope strict (le Parent ne consulte pas l'app dans le POC).
- **Historique de modifications** (audit log des créations/suppressions d'absences) — out of scope ; aucune colonne `CreatedAt`/`UpdatedAt`/`DeletedAt` sur `dbo.Conge` n'est ajoutée par cette FEAT.
- **Mode hors-ligne** (cache local des absences, sync différée) — out of scope ; l'application requiert une connexion réseau active.
