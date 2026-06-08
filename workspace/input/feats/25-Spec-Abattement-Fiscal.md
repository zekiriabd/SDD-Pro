# Spec: abattement-fiscal (page dynamique SQL — backend + frontend)

FEAT ID: 25-Spec-Abattement-Fiscal
Spec ID: spec-abattement-fiscal
Status: Draft

> **MAJ 2026-05-31** — passage du mode preview/constantes hardcodées à une
> intégration **dynamique pleine** (backend + base SQL Server). Les
> constantes TypeScript inlinées sont **supprimées** et remplacées par un
> endpoint `GET /api/abattement-fiscal` lisant la table `dbo.Abattement`
> jointe à `dbo.Contrat` × `dbo.Employeur` × `dbo.Employee`, scopé par la
> session JWT (EmployeeId du Bearer). Les écrans, l'ergonomie de l'accordion
> et la palette restent strictement identiques à la maquette
> `workspace/input/ui/25-1-Spec-Abattement-Fiscal.html`. **Cette FEAT introduit
> donc** : (1) une nouvelle table SQL `dbo.Abattement`, (2) une nouvelle
> entrée Prisma `Abattement`, (3) un nouvel endpoint backend `GET
> /api/abattement-fiscal`, (4) un repository + un service Node métier, (5) une
> Page React `AbattementFiscalPage` mise à jour pour consommer cet endpoint
> au lieu d'une constante figée. **Aucune autre FEAT n'est impactée.**

## Context

L'application Demo expose un menu principal latéral (cf. `spec-menu-principale` FEAT 5, étendu par `spec-documentation` FEAT 17 ajoutant `Documentation` et `spec-reseau-assistantes` FEAT 19) listant les modules métiers. La fiscalité — et plus précisément le **calcul de l'abattement fiscal** sur les revenus déclarés par l'assistante maternelle — est aujourd'hui **absente** de l'application en mode dynamique. L'employée doit ouvrir manuellement le simulateur impots.gouv.fr, ressaisir ses salaires mensuels par employeur, et appliquer elle-même la formule de l'abattement spécifique au métier.

Cette FEAT 25 industrialise la lecture de ces données. La source de vérité est désormais la **table `dbo.Abattement`** (cf. SFD-DATA-1) qui stocke un enregistrement par couple `(ContratId, Annee, Mois)` avec trois colonnes monétaires (`Brut`, `Net`, `Abattement`). Une requête SQL canonique (cf. SFD-API-1) joint cette table à `dbo.Contrat`, `dbo.Employeur` puis `dbo.Employee` pour filtrer par session (le `EmploierId` de `Employeur` réfère `Employee.EmployeeId` — naming historique conservé). La requête retourne les enregistrements de l'**année courante** et de l'**année précédente** (`Annee >= Year(Getdate()) - 1`), couvrant ainsi 2 années glissantes.

Le mockup canonique reste `workspace/input/ui/25-1-Spec-Abattement-Fiscal.html` — il sert de référence visuelle. Les valeurs hardcodées dans le `<script>` du mockup (Marc Bouchet, Karim Lefèvre, Hugo Marin) sont **purement illustratives** et **NE SONT PLUS** la source de vérité (anciennement SFD-4 / AC-15). Le rendu réel utilisera les données SQL filtrées par session.

Composition écran (inchangée vs maquette) :
- **Topbar** : bouton retour 38×38 coral + titre `Abattement Fiscal` + bouton partage (icône `ios_share` Material Symbols).
- **Sélecteur d'année segmenté** centré : 2 boutons pill, l'année précédente (label `à déclarer`) et l'année courante (label `en cours`). Les libellés des deux années sont **dérivés dynamiquement** de la date serveur (cf. SFD-DATA-3).
- **Hint visuel** : `Touchez un employeur pour voir le détail mois par mois` avec icône `touch_app`.
- **Liste de contrats** (anciennement « liste d'employeurs ») rendue en cards accordéon :
  - Avatar 42×42 carré arrondi avec dégradé `oklch(...)` dérivé d'un `hue` numérique stable par contrat (cf. SFD-UI-4) + initiales.
  - **Nom + Prénom de l'employeur** (associé au contrat) — affichés sur 2 lignes ou 1 ligne avec espace selon la fidélité maquette (15px, font-weight 700).
  - Chevron à droite qui pivote 90° quand la card est ouverte.
  - **3 stats calculées côté frontend par sommation des 12 mois** (cf. SFD-UI-3) en grille 3 colonnes : `Total brut`, `Net imposable` (mis en avant en fond `coral-50`), `Abattement`.
  - **Drawer ouvert** : table `Mois | Brut | Net imp. | Abat.` (12 lignes janvier à décembre, valeurs dynamiques ou `—` si mois vide) + ligne total annuel en fond `coral-50`.
- **Comportement** : la card du **premier contrat** est ouverte par défaut ; clic sur la tête d'une card toggle l'ouverture ; changement d'année réinitialise `openIndex = 0` et re-rend la liste à partir du payload déjà chargé (un seul fetch initial, pas de fetch supplémentaire au switch année — cf. SFD-API-3).

## Objective

L'employée connectée ouvre le menu principal → voit un nouvel item `Abattement Fiscal` entre `Mes contrats` et `Documentation` → clique → la SPA navigue vers `/abattement-fiscal` et ferme le menu (héritage FEAT 5 AC-5 + AC-6). La page **émet un unique appel API** `GET /api/abattement-fiscal` avec le `Bearer` JWT en header → reçoit en réponse les enregistrements de l'année courante et de l'année précédente pour TOUS les contrats de l'employée connectée → rend immédiatement la liste des contrats de l'année par défaut (année précédente, label `à déclarer`) avec la première card ouverte. L'employée clique sur un autre contrat → sa card s'ouvre, les autres restent dans leur état (multi-ouverture autorisée). Elle clique sur l'année courante → la liste se recharge **depuis le même payload local** (zéro requête réseau supplémentaire), la première card est ouverte par défaut. Le bouton retour topbar renvoie vers le menu principal.

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps de rendu initial de la page après navigation depuis le menu, mesuré entre `mount` et `firstPaint` (1 fetch HTTP + parsing JSON + render React) ; temps de toggle d'une card accordéon (toggle classe CSS, re-render local) ; latence p95 de `GET /api/abattement-fiscal` côté serveur.
- Target: p95 rendu initial < 350 ms côté frontend (fetch + parse + render sur ≤ 12 contrats × 12 mois × 2 ans ≈ 288 cellules) ; p95 toggle accordéon < 16 ms (1 frame à 60 FPS) ; p95 changement d'année < 40 ms (re-render local sur ≤ 12 cards) ; p95 endpoint `GET /api/abattement-fiscal` < 200 ms côté backend (1 requête SQL avec INNER JOIN sur indexes `IX_Abattement_Contrat_Annee` + `PK_Contrat` + `PK_Employeur`).
- Deadline: livraison fin **2026-06-30**.

## Non-Functional Constraints (v7.0.0)

- Expected volume: 1 chargement `/abattement-fiscal` par employée environ 2-3 fois par mois (consultation modérée) ; 2 années retournées par requête (courante + précédente, fenêtre glissante côté SQL `[Annee] >= Year(Getdate()) - 1`) ; ≤ 12 contrats actifs ou clôturés par employée (cf. FEAT 22 statut `BebeStatut`) ; 12 mois par contrat ; total ≤ 288 enregistrements en payload ; payload JSON ≤ 60 KB sans compression, ≤ 6 KB avec gzip.
- Performance SLA: p95 `GET /api/abattement-fiscal` < 200 ms côté backend (cf. Quantified Goal) ; p99 < 500 ms ; aucun appel cascade (1 seule requête SQL paramétrée par `@EmploierId`).
- Data retention: les enregistrements `dbo.Abattement` sont conservés indéfiniment (historique fiscal — cf. obligations légales 6 ans minimum côté URSSAF/Pajemploi). Aucune purge automatique par cette FEAT.
- Compliance: RGPD — données fiscales personnelles d'une employée traitées par cette FEAT. Scoping par session **obligatoire** côté SQL (filtre `EmploierId = @EmploierId` paramétré, où `@EmploierId` provient du JWT `sub`). Aucune fuite cross-employée possible (anti-énumération AC-DATA-3).
- Integration: extension de `spec-menu-principale` (FEAT 5) avec 1 nouvel item ; nouvelle route SPA `/abattement-fiscal` ; **nouvel** endpoint backend `GET /api/abattement-fiscal` ; **nouvelle** table `dbo.Abattement` + entrée Prisma `Abattement` ; aucune notification ; aucun WebSocket / SSE.
- Degraded mode: si le backend est indisponible (5xx) ou la table `dbo.Abattement` vide pour l'employée connectée → la page affiche un **état vide** explicite (cf. SFD-UI-8) sans crash JS. Aucune retry automatique (le user re-click le menu pour relancer).

## Actors

- Employée connectée : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu du JWT (`request.user.sub` côté Fastify). Seule autorisée à consulter `/abattement-fiscal`. Aucune action mutative n'est exposée par cette FEAT (`GET` uniquement). Les données affichées sont **scopées par session** : l'employée X ne voit JAMAIS les revenus de l'employée Y (cf. BR-AUTH-2).

## Functional Needs

### Source de données SQL — table dbo.Abattement

- SFD-DATA-1: La FEAT introduit la **table SQL Server `dbo.Abattement`** (DDL fournie en `prisma/scripts/create-abattement.sql`, idempotente) :
  - `AbattementId INT IDENTITY PRIMARY KEY`
  - `ContratId INT NOT NULL FK → dbo.Contrat(ContratId)`
  - `Annee INT NOT NULL`
  - `Mois TINYINT NOT NULL` avec contrainte `CHECK (Mois BETWEEN 1 AND 12)`
  - `Brut DECIMAL(18, 2) NOT NULL` — salaire brut mensuel
  - `Net DECIMAL(18, 2) NOT NULL` — net imposable mensuel
  - `Abattement DECIMAL(18, 2) NOT NULL` — abattement mensuel **stocké** (peut différer de `Brut - Net` selon règle métier future ; le backend consomme la valeur stockée telle quelle, sans recalcul).
  - Index unique `UQ_Abattement_Contrat_Annee_Mois (ContratId, Annee, Mois)` — empêche les doublons mensuels.
  - Index secondaire `IX_Abattement_Contrat_Annee (ContratId, Annee)` — accélère la requête SFD-API-1.
- SFD-DATA-2: Une entrée correspondante est ajoutée au **`schema.prisma`** :
  ```prisma
  model Abattement {
    AbattementId Int      @id(map: "PK_Abattement") @default(autoincrement())
    ContratId    Int
    Annee        Int
    Mois         Int      @db.TinyInt
    Brut         Decimal  @db.Decimal(18, 2)
    Net          Decimal  @db.Decimal(18, 2)
    Abattement   Decimal  @db.Decimal(18, 2)
    Contrat      Contrat  @relation(fields: [ContratId], references: [ContratId], onUpdate: NoAction, map: "FK_Abattement_Contrat")

    @@unique([ContratId, Annee, Mois], map: "UQ_Abattement_Contrat_Annee_Mois")
    @@index([ContratId, Annee], map: "IX_Abattement_Contrat_Annee")
  }
  ```
  La relation inverse `Contrat.Abattement Abattement[]` est ajoutée au modèle `Contrat`. **Aucune autre table** existante n'est modifiée par cette FEAT.
- SFD-DATA-3: Les **deux années retournées** par la requête canonique sont calculées côté SQL via `Year(Getdate()) - 1` (année précédente) et `Year(Getdate())` (année courante). Le backend expose dans le payload les deux clés `previousYear` et `currentYear` (entiers) pour que le frontend connaisse les labels année **sans calcul JS local** (anti-drift horloge serveur ↔ client). Le mapping des libellés (`à déclarer` / `en cours`) reste côté frontend (constante UI — cf. SFD-UI-6).

### Endpoint backend — GET /api/abattement-fiscal

- SFD-API-1: La FEAT introduit l'endpoint **`GET /api/abattement-fiscal`** (Fastify, `routes/abattementFiscal.routes.js`). Authentification obligatoire (`preHandler: fastify.authenticate`). Pas de query param ni de body. La requête SQL canonique exécutée côté repository (via Prisma raw query ou Prisma `findMany` avec relations — implémentation laissée au `dev-backend` selon perf observée) est sémantiquement équivalente à :
  ```sql
  SELECT
         e.Nom
        ,e.Prenom
        ,c.ContratId
        ,c.Nom    AS EnfantNom
        ,c.Prenom AS EnfantPrenom
        ,a.Annee
        ,a.Mois
        ,a.Net
        ,a.Brut
        ,a.Abattement
    FROM [dbo].[Abattement] a
    INNER JOIN [dbo].[Contrat]   c  ON c.ContratId   = a.ContratId
    INNER JOIN [dbo].[Employeur] e  ON e.EmployeurId = c.EmployeurId
    INNER JOIN [dbo].[Employee]  ee ON ee.EmployeeId = e.EmploierId
   WHERE e.EmploierId = @EmploierId
     AND a.Annee >= Year(Getdate()) - 1
   ORDER BY a.Annee DESC, a.Mois DESC;
  ```
  - `c.Nom` et `c.Prenom` correspondent à l'**identité de l'enfant** confié (clé contrat), à distinguer de `e.Nom`/`e.Prenom` qui désignent le parent employeur. Le payload les expose sous `childNom` / `childPrenom` (cf. SFD-API-2).
  - Le paramètre `@EmploierId` est **lié exclusivement** à `request.user.sub` (JWT `sub` claim). Toute valeur fournie par le client (query, header, body) est ignorée (anti-énumération).
  - L'INNER JOIN sur `Employee` n'est pas strictement nécessaire pour le scoping (déjà couvert par `e.EmploierId = @EmploierId`) mais est conservé pour rester strictement aligné sur la requête canonique fournie par le Tech Lead (et fournit une garantie d'intégrité référentielle implicite — un Employeur orphelin sans Employee n'apparaît pas).
  - `ORDER BY` permet un ordre déterministe en sortie (utile pour le rendu et les tests).
- SFD-API-2: La **réponse** est un objet JSON unique (pas d'enveloppe `{ data: ... }`) avec la forme suivante :
  ```json
  {
    "currentYear": 2026,
    "previousYear": 2025,
    "years": {
      "2025": [
        {
          "contratId": 12,
          "nom": "Bouchet",
          "prenom": "Marc",
          "childNom": "Bouchet",
          "childPrenom": "Lina",
          "hue": 8,
          "totals": { "brut": 9660, "net": 5670, "abattement": 3990 },
          "months": [
            { "mois": 1,  "brut": 920, "net": 540, "abattement": 380 },
            { "mois": 2,  "brut": 920, "net": 540, "abattement": 380 },
            { "mois": 3,  "brut": 0,   "net": 0,   "abattement": 0 },
            ... (12 entrées au total — mois sans Abattement = 0)
          ]
        }
      ],
      "2026": [...]
    }
  }
  ```
  - **Clé `years`** : record dont les clés sont les années (chaînes), valeurs = tableau de contrats agrégés. Toujours **exactement 2 clés** (`previousYear.toString()` et `currentYear.toString()`) — si une année est absente côté SQL pour l'employée, la valeur correspondante est un tableau vide `[]` (jamais omise).
  - **`contratId`** : identifiant numérique du Contrat. Sert de clé React stable et permet au frontend de référencer le contrat dans des FEATs futures.
  - **`nom` / `prenom`** : champs `Employeur.Nom` et `Employeur.Prenom` (PascalCase SQL converti en camelCase). Affichés côté frontend comme `{prenom} {nom}` (parent employeur).
  - **`childNom` / `childPrenom`** : champs `Contrat.Nom` et `Contrat.Prenom` (identité de l'enfant confié, clé contrat). Affichés en sous-ligne sous le nom du parent dans la card `.emp__head` (classe CSS `.emp__child`).
  - **`hue`** : entier 0-359 calculé **côté backend** par un hash stable du couple `(contratId, "nom prenom")` (FNV-1a 32 bits modulo 360 — cf. helper `computeHueFromContrat` dans `services/abattementFiscalService.js`). Permet au frontend de générer le dégradé OKLCH d'avatar sans logique métier locale.
  - **`totals`** : objet contenant les 3 sommes annuelles (`brut`, `net`, `abattement`) calculées **côté backend** par sommation des 12 mois. Ces valeurs sont les **3 champs calculés affichés dans l'UI** (cf. SFD-UI-3 : `Total brut`, `Net imposable`, `Abattement`). Évite la duplication de logique de sommation entre backend et frontend.
  - **`months`** : tableau de **toujours exactement 12 entrées** (janvier=1 à décembre=12, dans l'ordre croissant — différent de l'ORDER BY SQL qui est DESC pour la latence d'extraction). Chaque entrée a 4 clés : `mois`, `brut`, `net`, `abattement`. Les mois sans données SQL sont **explicitement** remplis par le backend avec `{ brut: 0, net: 0, abattement: 0 }` (cf. SFD-API-4) — le frontend ne fait jamais d'imputation locale.
  - L'ordre des contrats dans chaque année est `ORDER BY contratId ASC` (déterministe, simple, stable cross-machine).
- SFD-API-3: **Un unique fetch** est émis par le frontend au montage de la page. Le payload couvre les 2 années glissantes — le toggle d'année dans la year-segment **NE déclenche AUCUN appel HTTP supplémentaire** (cf. AC-API-4). C'est un re-render purement local du composant React avec la nouvelle clé.
- SFD-API-4: Le **comblement des mois manquants** (mois où la table `dbo.Abattement` n'a pas de ligne pour le contrat × année donné) est effectué **dans le service Node** (`services/abattementFiscalService.js`), pas en SQL (qui retournerait juste les lignes existantes). Algorithme déterministe : pour chaque couple (year, contratId) du résultat SQL, on construit un Map `Map<mois, {brut, net, abattement}>` puis on itère `mois = 1..12` en récupérant la valeur du Map ou un objet zéro `{brut: 0, net: 0, abattement: 0}`.
- SFD-API-5: **Codes de retour** :
  - `200 OK` : payload SFD-API-2, même si l'employée n'a aucun contrat ni aucune ligne `dbo.Abattement` (le payload aura `years: { "{prev}": [], "{cur}": [] }`).
  - `401 Unauthorized` : JWT absent / invalide / expiré (héritage `fastify.authenticate`).
  - `500 Internal Server Error` : erreur DB / parsing Prisma / autre — propagée par `errorMiddleware`.
  - **Aucun 404** : la FEAT n'expose pas de paramètre URL → pas d'anti-énumération à gérer ici.

### Point d'entrée et navigation

- SFD-NAV-1: La spec **étend `spec-menu-principale` (FEAT 5)** en ajoutant un **nouvel item `Abattement Fiscal`** dans la liste de navigation du panneau latéral, **positionné entre `Mes contrats` et `Documentation`** (l'item Documentation a été ajouté par FEAT 17). L'ordre canonique des items de menu devient donc : `Mes bébés` → `Rapports` → `Mes données` → `Mes contrats` → **`Abattement Fiscal`** → `Documentation` → (éventuels items ajoutés par FEATs 19, 20) → `Se déconnecter`. L'icône de l'item est `account_balance` ou `payments` (Material Symbols, au choix `dev-frontend` documenté en PR).
- SFD-NAV-2: Un clic sur l'item `Abattement Fiscal` déclenche une navigation SPA vers `/abattement-fiscal` (cf. FEAT 5 BR-2) et **ferme le panneau latéral** (héritage FEAT 5 AC-6).
- SFD-NAV-3: La nouvelle route SPA `/abattement-fiscal` est protégée par le middleware d'authentification global — un utilisateur non authentifié est redirigé vers `/login` (héritage FEAT 5 BR-1).

### Composant frontend — AbattementFiscalPage

- SFD-UI-1: La page rend les éléments DOM dans l'ordre suivant (de haut en bas), strictement fidèle au mockup :
  1. **Status bar iOS** (hérité du gabarit phone-mockup).
  2. **Topbar** (`.af-topbar`) :
     - Bouton retour 38×38 rond (`.af-topbar__back`, classe coral) — chevron `<` SVG inliné, `aria-label="Retour"`, déclenche `history.back()` au clic.
     - Titre `.af-topbar__title` font-size 18, font-weight 800, contenu littéral `Abattement Fiscal`.
     - Bouton action 38×38 rond (`.af-topbar__action`, classe coral) — icône Material Symbols `ios_share`. **Aucun handler attaché** (cf. SFD-UI-7) ; rendu visuel uniquement.
  3. **Body scrollable** (`.af-body`, padding 16 16 28) contenant :
     - **Year segment** (`.year-seg`) — pill horizontal centré, 2 boutons enfants (boucle sur `[previousYear, currentYear]` du payload). Le bouton actif a la classe `.is-active`.
     - **Section hint** (`.section-hint`) — icône Material Symbols `touch_app` font-size 15 + texte `Touchez un employeur pour voir le détail mois par mois`.
     - **Liste de contrats** (`<div class="af-emp-list">`) — rendue par boucle sur `data.years[activeYear]`, voir SFD-UI-2.
  4. **Home indicator iOS** (cosmétique, `.home-indicator`).
- SFD-UI-2: Chaque card contrat (`.emp`) rend, dans l'ordre :
  - Tête cliquable `.emp__head` contenant : avatar dégradé `.emp__avatar` (background = `linear-gradient(140deg, oklch(0.80 0.10 H), oklch(0.64 0.14 (H+25)%360))`, où `H = item.hue`) avec initiales 2 caractères (`initials(prenom + ' ' + nom)`), bloc `.emp__id` avec `.emp__name = "{prenom} {nom}"` (note : v7.0.0 — **affichage `prenom nom` complet**, plus seulement un champ `name`), chevron SVG `.emp__chev` qui pivote 90° quand `.is-open`.
  - 3 stats `.emp__stats` toujours visibles : `Total brut` = `eur(item.totals.brut)`, `Net imposable` (classe `.emp__stat--net`) = `eur(item.totals.net)`, `Abattement` = `eur(item.totals.abattement)`. **Ces 3 valeurs proviennent du backend** (cf. SFD-API-2 / SFD-UI-3).
  - Drawer `.emp__drawer` (`grid-template-rows: 0fr` fermé / `1fr` ouvert) avec en-tête `Mois | Brut | Net imp. | Abat.`, 12 lignes mensuelles (cf. SFD-UI-5), et une ligne `.month-total` avec libellé `Total {activeYear}` et les 3 totaux annuels (mêmes valeurs que les 3 stats du head, cohérence garantie côté backend).
- SFD-UI-3: Les **3 champs calculés** affichés dans l'UI (`Total brut`, `Net imposable`, `Abattement`) correspondent **strictement** aux 3 champs `item.totals.brut`, `item.totals.net`, `item.totals.abattement` du payload backend (cf. SFD-API-2). Le frontend **ne recalcule pas** les sommes — il consomme les valeurs servies. Cette discipline garantit que la valeur affichée dans les 3 stats du `.emp__stats` (head, toujours visibles) est **identique** à celle affichée dans la ligne `.month-total` (drawer ouvert), sans risque de drift d'arrondi.
- SFD-UI-4: Le **hue d'avatar** est **fourni par le backend** (champ `item.hue`, entier 0-359 calculé par hash FNV-1a — cf. SFD-API-2). Le frontend ne dérive plus le hue à partir d'un mapping local par nom — la stabilité visuelle est garantie côté serveur (un même contrat aura toujours le même hue à chaque visite).
- SFD-UI-5: La **table mensuelle** dans le drawer rend **12 lignes** (`.month-row`), une par mois `Jan` à `Déc`, dans l'ordre. Chaque ligne :
  ```html
  <div class="month-row{ ' is-empty' si brut === 0 && net === 0 && abattement === 0 }">
    <span class="month-row__m">{MOIS_LABELS[mois - 1]}</span>
    <span class="month-row__brut">{ '—' si empty sinon eur(brut) }</span>
    <span class="month-row__net">{ '—' si empty sinon eur(net) }</span>
    <span class="month-row__abat">{ '—' si empty sinon eur(abattement) }</span>
  </div>
  ```
  - `MOIS_LABELS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']` (constante UI, 12 entrées).
  - Un mois rempli intégralement à 0 (`brut = 0 && net = 0 && abattement = 0`) est rendu **désaturé** via la classe CSS `.is-empty` (`opacity: 0.4`), avec `—` en colonnes valeurs. **Important** : la valeur d'abattement affichée est **`item.months[i].abattement`** (champ backend) — PAS un recalcul `brut - net` côté frontend. Ce changement est intentionnel : permettre à une FEAT future d'introduire des règles métier où `Abattement` n'est pas strictement `Brut - Net` (forfait, plafond CGI 80 sexies, etc.) sans casser le rendu.
- SFD-UI-6: Le **mapping des libellés année** est une constante UI dans le frontend :
  ```javascript
  function getYearTag(year, previousYear, currentYear) {
    if (year === previousYear) return 'à déclarer';
    if (year === currentYear)  return 'en cours';
    return ''; // jamais atteint en pratique
  }
  ```
  Pas de mapping figé `{'2025': 'à déclarer', ...}` — les libellés sont **dérivés** des champs `previousYear` / `currentYear` du payload backend, ce qui rend la page robuste au passage d'année (au 1er janvier, sans déploiement, la fenêtre glissante 2026+2027 affichera automatiquement les bons libellés).
- SFD-UI-7: Le **bouton partage** `ios_share` du topbar est **rendu sans handler** en preview (placeholder visuel pour une FEAT future d'export PDF / partage natif). Aucun clic ne déclenche d'action. Préserver l'`aria-label="Exporter"` pour l'accessibilité.
- SFD-UI-8: **Trois états d'affichage de la page** :
  1. **Loading** : pendant le `fetch('/api/abattement-fiscal')`, afficher un état de chargement (spinner ou skeleton — au choix `dev-frontend`, cohérent avec les autres pages). Pas de constante figée affichée.
  2. **Erreur** : si le fetch échoue (`response.ok === false`, network error, JSON parse error), afficher un message d'erreur générique (ex. `Impossible de charger les abattements. Vérifiez votre connexion.`) sans details techniques (pas de stack trace ni de statut HTTP exposé). Pas de retry automatique.
  3. **Vide** : si `data.years[previousYear].length === 0 && data.years[currentYear].length === 0`, afficher un message explicite (`Aucun abattement disponible pour les années {previousYear} et {currentYear}.`).
- SFD-UI-9: La **logique d'accordéon** est : `openIndex` est un `Set<number>` initialisé à `Set([0])` au montage (première card ouverte par défaut). Un clic sur `.emp__head[data-emp="{i}"]` toggle `i` dans le Set. **Multi-ouverture autorisée**. Au changement d'année, le Set est réinitialisé à `Set([0])`.

### Pas d'écriture, pas de mutation

- SFD-WRITE-1: **Aucun endpoint d'écriture** n'est introduit par cette FEAT — la table `dbo.Abattement` est **populée hors-bande** (manuellement par DBA ou par un job futur d'agrégation depuis `dbo.RapportJournee` × `dbo.Contrat` — out of scope). L'application Demo est **strictement consommatrice** de ces données en lecture.
- SFD-WRITE-2: **Aucune mutation runtime** sur la table — pas d'`INSERT`, `UPDATE`, `DELETE` côté code applicatif Node. Le repository utilise uniquement `prisma.abattement.findMany(...)` (ou Prisma raw query lecture seule).

## Business Rules

- BR-AUTH-1: l'accès à `/abattement-fiscal` (frontend SPA) ET à `GET /api/abattement-fiscal` (backend API) est **strictement protégé** par le middleware d'authentification global — un utilisateur non authentifié est redirigé vers `/login` (SPA) ou reçoit 401 Unauthorized (API). Héritage FEAT 5 BR-1 + FEAT 17 SFD-2.
- BR-AUTH-2: la requête SQL filtre **obligatoirement** par `EmploierId = @EmploierId` où `@EmploierId` provient **exclusivement** du JWT (`request.user.sub`). Une employée X ne voit JAMAIS les revenus d'une employée Y. Aucun paramètre URL/body/header client ne peut altérer le filtre (anti-énumération). Vérification automatisable par tests d'intégration (cf. AC-DATA-3).
- BR-DATA-1: la table `dbo.Abattement` impose **unicité** par `(ContratId, Annee, Mois)` via l'index `UQ_Abattement_Contrat_Annee_Mois`. Toute tentative d'INSERT en doublon échouera côté SQL (DBA arbitre l'erreur — hors scope de cette FEAT puisque l'app est read-only).
- BR-DATA-2: La colonne `Mois` est contrainte `BETWEEN 1 AND 12` par `CK_Abattement_Mois_Range`. Le service Node **ne re-vérifie pas** côté Node (la contrainte SQL est la source de vérité).
- BR-DATA-3: La colonne `Abattement` est **stockée** (DECIMAL(18,2) NOT NULL), pas dérivée. Le backend retourne la valeur stockée telle quelle. Cette décision est intentionnelle pour préparer une FEAT future qui appliquera des règles fiscales réelles (forfait, plafonds, exclusions article 80 sexies CGI) où `Abattement ≠ Brut − Net`.
- BR-API-1: La requête SQL canonique (SFD-API-1) filtre `Annee >= Year(Getdate()) - 1` — fenêtre glissante de 2 années. L'horloge serveur SQL est **autoritaire** sur le périmètre temporel (pas de paramètre `clientNow` ici — la fiscalité française dépend de l'année calendaire serveur, pas du fuseau horaire utilisateur). Cohérent avec la pratique URSSAF.
- BR-API-2: La réponse expose `previousYear` et `currentYear` calculés côté backend à partir de `Year(Getdate())`. **Le frontend NE recalcule PAS** ces valeurs avec `new Date().getFullYear()` — risque de désynchronisation client/serveur au passage d'année (minuit UTC vs minuit local) évité.
- BR-API-3: Le payload **ne contient JAMAIS** d'informations sensibles supplémentaires (NumeroSecuriteSociale, NumeroPajemploi, MotdePass, Token JWT…). Seuls les 8 champs définis SFD-API-2 sont exposés (`contratId`, `nom`, `prenom`, `hue`, `totals.{brut,net,abattement}`, `months[].{mois,brut,net,abattement}`).
- BR-UI-1: Le frontend **affiche exactement** les valeurs reçues du backend (cf. SFD-UI-3) — pas de transformation, pas d'arrondi, pas de conversion de devise. Les montants sont des entiers euros (DECIMAL(18,2) tronqué à 0 décimale côté `eur()` ; si une décimale apparaît, le format pourra être étendu — out of scope).
- BR-UI-2: l'**ordre des contrats** au sein d'une année est l'ordre du tableau dans le payload backend (ORDER BY ContratId ASC — cf. SFD-API-2 dernier paragraphe). Pas de re-tri côté frontend.
- BR-UI-3: les **mois sans données** (entrée `{ brut: 0, net: 0, abattement: 0 }` complétée par le backend en SFD-API-4) sont rendus avec la classe CSS `.month-row.is-empty` (opacité 0.4) et les colonnes de valeurs affichent `—` (em-dash U+2014). Décision identique à v6.x — on ne masque pas le mois pour préserver l'alignement vertical.
- BR-UI-4: le bouton partage du topbar est **rendu sans handler** (cf. SFD-UI-7). Aucun message d'erreur ni toast n'est affiché en cas de clic (silencieux total).
- BR-UI-5: l'**accordion permet l'ouverture multiple** — cliquer sur un contrat ne ferme pas les autres.
- BR-UI-6: le **changement d'année** réinitialise `openIndex = Set([0])` (premier contrat de la nouvelle année ouvert par défaut).
- BR-UI-7: la page **ne persiste aucun état** entre les sessions — pas de localStorage, pas de sessionStorage, pas de cookie. L'année active et `openIndex` sont réinitialisés à chaque visite. Le payload n'est pas mis en cache navigateur au-delà du cache HTTP standard.
- BR-UI-8: **aucune télémétrie / analytics** n'est introduit par cette FEAT — aucune mesure du temps passé, aucun event tracker sur les clics. Cohérent avec FEAT 17 BR-16.
- BR-UI-9: les **icônes Material Symbols** (`touch_app`, `ios_share`, `account_balance` ou `payments`) sont chargées via la même voie que FEAT 17 SFD-13 (web font Google CDN) — **aucune nouvelle dépendance externe n'est introduite par cette FEAT 25**.
- BR-UI-10: le rendu utilise **exclusivement** des tokens CSS du design system (`var(--nj-*)`) — **aucun hex hardcodé** dans les composants. Seule exception : les couleurs OKLCH du dégradé d'avatar (`oklch(0.80 0.10 {hue})`) qui sont calculées dynamiquement à partir de `hue` — fonction OKLCH avec variable interpolée, pas hex statique.

## Acceptance Criteria

- AC-NAV-1: le menu principal contient un nouvel item `Abattement Fiscal` avec icône Material Symbols `account_balance` ou `payments`, **positionné entre `Mes contrats` et `Documentation`**. Un clic déclenche une navigation SPA vers `/abattement-fiscal` et ferme le panneau latéral (héritage FEAT 5 AC-5 + AC-6).
- AC-NAV-2: la route `/abattement-fiscal` est protégée — un utilisateur non authentifié est redirigé vers `/login`.
- AC-NAV-3: le bouton retour topbar navigue vers la page précédente via le mécanisme SPA actif (`history.back()` ou équivalent). Pas de rechargement complet de page.
- AC-API-1: l'endpoint `GET /api/abattement-fiscal` est exposé par Fastify avec `preHandler: fastify.authenticate`. Une requête sans `Authorization: Bearer <jwt>` ou avec un JWT invalide retourne `401 Unauthorized`. Vérifiable par test d'intégration.
- AC-API-2: une requête authentifiée valide retourne `200 OK` avec un payload JSON conforme à SFD-API-2 (clés `currentYear`, `previousYear`, `years.{prev}`, `years.{cur}`). Vérifiable par snapshot test.
- AC-API-3: chaque entrée `years[year][i]` du payload contient **exactement** les champs `contratId`, `nom`, `prenom`, `hue`, `totals.{brut,net,abattement}`, `months` (12 entrées). Aucun champ supplémentaire (anti-leak — cf. BR-API-3).
- AC-API-4: la page frontend **émet exactement un seul fetch** `GET /api/abattement-fiscal` lors du montage initial. Le toggle d'année dans le year-segment n'émet **aucun fetch supplémentaire** (vérifiable Network DevTools — exactement 1 entrée pour `/api/abattement-fiscal` après navigation + 1 click sur l'autre année).
- AC-API-5: chaque tableau `months` dans le payload contient **exactement 12 entrées** dans l'ordre `mois = 1..12`. Les mois sans données SQL sont remplis par le backend avec `{ brut: 0, net: 0, abattement: 0 }` (cf. SFD-API-4). Vérifiable par test unitaire sur le service.
- AC-API-6: les `totals.brut`, `totals.net`, `totals.abattement` retournés par le backend pour un contrat sont **strictement égaux** à la sommation `months[].brut`, `months[].net`, `months[].abattement` (sur les 12 mois). Vérifiable par test unitaire (`expect(item.totals.brut).toBe(item.months.reduce((s, m) => s + m.brut, 0))`).
- AC-API-7: les `currentYear` et `previousYear` retournés par le backend sont des entiers tels que `currentYear === Year(Getdate())` et `previousYear === currentYear - 1`. Vérifiable par test d'intégration (mock de l'horloge ou vérification dynamique).
- AC-DATA-1: la table SQL `dbo.Abattement` existe avec les 7 colonnes (`AbattementId`, `ContratId`, `Annee`, `Mois`, `Brut`, `Net`, `Abattement`) + PK + FK vers `dbo.Contrat` + index `UQ_Abattement_Contrat_Annee_Mois` + index `IX_Abattement_Contrat_Annee` + contrainte `CK_Abattement_Mois_Range`. Vérifiable post-déploiement par requête `sys.tables`, `sys.indexes`, `sys.check_constraints`.
- AC-DATA-2: le `schema.prisma` contient le modèle `Abattement` avec la relation FK vers `Contrat` et la relation inverse `Contrat.Abattement Abattement[]`. Vérifiable par `prisma format` + `prisma validate`.
- AC-DATA-3: une employée X authentifiée appelant `GET /api/abattement-fiscal` ne reçoit **JAMAIS** les enregistrements d'une employée Y (scope strict par `Employee.EmployeeId = Employeur.EmploierId = request.user.sub`). Vérifiable par test d'intégration avec 2 employees disposant chacune de leur jeu de données.
- AC-UI-1: au chargement initial, la page **affiche un état de chargement** pendant le fetch ; au retour du fetch, elle rend la topbar, le year-segment (2 boutons dérivés du payload), le hint, et la liste de contrats de l'année par défaut (`previousYear`, label `à déclarer`).
- AC-UI-2: la card du **premier contrat** de l'année active est **ouverte par défaut** (classe `.is-open` posée, drawer visible avec 12 lignes mensuelles + ligne total). Les autres cards sont fermées.
- AC-UI-3: un clic sur la tête d'une card fermée l'**ouvre** ; un clic sur la tête d'une card ouverte la **ferme**. Plusieurs cards peuvent être ouvertes simultanément (cf. BR-UI-5).
- AC-UI-4: chaque card affiche **3 stats** toujours visibles : `Total brut`, `Net imposable` (mis en avant avec fond `var(--nj-coral-50)` et bordure `var(--nj-coral-100)`), `Abattement`. Les valeurs sont **les 3 champs `item.totals.{brut,net,abattement}` du payload backend** (cf. SFD-UI-3), formatés en euros français.
- AC-UI-5: le drawer ouvert contient :
  1. En-tête `Mois | Brut | Net imp. | Abat.`.
  2. **12 lignes mensuelles** (`.month-row`), une par mois `Jan` à `Déc` dans l'ordre, chacune avec 4 colonnes.
  3. Une ligne totale `.month-total` avec libellé `Total {activeYear}` et les 3 totaux annuels (mêmes valeurs que les 3 stats du head — cohérence backend SFD-UI-3).
- AC-UI-6: les mois avec `brut === 0 && net === 0 && abattement === 0` sont rendus avec la classe `.month-row.is-empty` (opacité 0.4) et les 3 colonnes valeurs affichent `—` (em-dash U+2014).
- AC-UI-7: un clic sur le bouton de l'autre année du year-segment :
  1. Bascule la classe `.is-active` entre les 2 boutons.
  2. Re-rend la liste avec les contrats de la nouvelle année **depuis le payload local** (zéro fetch supplémentaire, cf. AC-API-4).
  3. Réinitialise l'accordion : la première card de la nouvelle année est ouverte par défaut.
  4. Le libellé `Total {year}` dans `.month-total__m` de chaque drawer reflète l'année active.
- AC-UI-8: le **nom et prénom de l'employeur** sont affichés dans `.emp__name` sous la forme `{prenom} {nom}` (espace entre les deux). Vérifiable par DOM query (`textContent === 'Marc Bouchet'` par exemple pour `{prenom: 'Marc', nom: 'Bouchet'}`).
- AC-UI-9: le bouton partage topbar (`.af-topbar__action`) est rendu visuellement avec l'icône `ios_share` mais **aucun clic ne déclenche d'action**. Pas de toast, pas de navigation, pas d'appel API.
- AC-UI-10: les valeurs monétaires affichées sont formatées en euros français — vérifiable par regex `^\d{1,3}(?:[\s  ]\d{3})* €$` sur le `textContent` des éléments concernés (hors cellules vides affichant `—`).
- AC-UI-11: **trois états** sont gérés : loading, erreur, vide — chacun rend un fragment DOM dédié sans crash JS (cf. SFD-UI-8).
- AC-UI-12: aucun nouveau cookie, localStorage, sessionStorage, IndexedDB n'est introduit (cf. BR-UI-7).
- AC-UI-13: aucun hex hardcodé dans les composants (cf. BR-UI-10) — vérifiable par grep `#[0-9a-fA-F]{3,8}` post-build sur `public/pages/AbattementFiscalPage.jsx` et `public/constants/abattementFiscalData.js`.
- AC-UI-14: aucune nouvelle dépendance npm n'est introduite par cette FEAT — la police Material Symbols est déjà chargée par FEAT 17 (cf. BR-UI-9). Vérifiable côté CI : aucun diff sur `package.json` autre que les ajouts liés à cette FEAT (si nécessité d'un nouveau lib backend pour Prisma raw query, justifier en PR — par défaut, aucun ajout attendu).
- AC-INTEG-1: l'app **démarre proprement** (`node server.js`) après les modifications — `Abattement` étant un modèle Prisma valide et la route enregistrée dans `server.js`. Vérifiable par `npm run start` + smoke check.
- AC-INTEG-2: le rendu visuel respecte la maquette `25-1-Spec-Abattement-Fiscal.html` à la grille près — vérifiable par revue visuelle côté Tech Lead.

## Functional Deliverables

- FD-DATA-1: **table SQL `dbo.Abattement`** créée par `prisma/scripts/create-abattement.sql` (idempotent) avec colonnes, PK, FK, 2 indexes, et contrainte CHECK.
- FD-DATA-2: **entrée Prisma `Abattement`** dans `prisma/schema.prisma` + relation inverse `Contrat.Abattement Abattement[]`.
- FD-API-1: **endpoint `GET /api/abattement-fiscal`** exposé par `routes/abattementFiscal.routes.js`, enregistré dans `server.js` via `registerAbattementFiscalRoutes(fastify)`.
- FD-API-2: **repository `abattementFiscalRepository.js`** — read-only `findByEmployeeId(employeeId, { fromYear })` retournant les lignes brutes SQL (avec `Employeur.Nom`, `Employeur.Prenom`, `Contrat.ContratId`, `Abattement.{Annee,Mois,Brut,Net,Abattement}`).
- FD-API-3: **service `abattementFiscalService.js`** — agrège les lignes brutes en payload SFD-API-2, calcule `totals` par contrat, comble les mois manquants, calcule `hue` via hash stable, et résout `previousYear` / `currentYear`.
- FD-API-4: **schéma `AbattementFiscalSchema.js`** — Zod + JSON schema pour validation `response` Fastify + référence Swagger UI.
- FD-NAV-1: nouvel item `Abattement Fiscal` ajouté à la liste de navigation du panneau latéral (extension `MainLayout.jsx` ou équivalent) — icône Material Symbols, libellé, **positionné entre `Mes contrats` et `Documentation`**.
- FD-UI-1: nouvelle route SPA `/abattement-fiscal` enregistrée dans `app.jsx` rendant `AbattementFiscalPage`.
- FD-UI-2: **composant `AbattementFiscalPage.jsx`** mis à jour — fetch initial via `dataLoader.getJson('/api/abattement-fiscal', { headers: { Authorization: 'Bearer ' + token } })`, états loading/erreur/vide, year-segment dérivé du payload, accordion avec multi-ouverture, format `{prenom} {nom}`.
- FD-UI-3: **fichier `constants/abattementFiscalData.js`** réduit à **helpers purs uniquement** (`eur`, `initials`, `avatarGradient`) + constante `ABATTEMENT_FISCAL_MONTHS`. **Supprimer** la constante `ABATTEMENT_FISCAL_DATA` (anciennement hardcodée).
- FD-UI-4: CSS scopé (ou classes Tailwind/shadcn équivalentes) reproduisant les styles du mockup — **inchangé** vs v6.x (déjà livré).
- FD-UI-5: maquette `workspace/input/ui/25-1-Spec-Abattement-Fiscal.html` matérialisant le rendu canonique — référence visuelle non-ambiguë.

## Dependencies

- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient du JWT `sub` claim ; le middleware d'authentification protège `/abattement-fiscal` + `GET /api/abattement-fiscal`.
- **spec-menu-principale** (`5-spec-menu-principale`) : **étendue directement** — ajout d'un nouvel item `Abattement Fiscal` entre `Mes contrats` et `Documentation`.
- **spec-documentation** (`17-spec-documentation`) : **référencée** pour la voie de chargement de la police Material Symbols Outlined. Aucun couplage de code.
- **spec-contrats** (`6-spec-contrats` et autres FEATs contrat) : la table `dbo.Abattement` référence `dbo.Contrat(ContratId)` via FK. Aucune contrainte de schéma sur l'app Demo côté contrat (lecture seule).

## Out of Scope

- **alimentation de la table `dbo.Abattement`** (jobs d'agrégation depuis `dbo.RapportJournee` × `dbo.Contrat`, imports CSV/XLSX, saisie manuelle DBA) — strictement hors scope de cette FEAT. La table est **lue** par Demo mais **populée hors-bande**.
- **calcul fiscal réel** (formule article 80 sexies CGI, SMIC horaire, jours d'accueil, plafonds, exclusions, revalorisation annuelle) — la colonne `Abattement` est **stockée** ; le calcul lui-même appartient au job d'alimentation, pas à cette FEAT.
- **export PDF récapitulatif** déclenché par le bouton partage `ios_share` du topbar — placeholder visuel uniquement (cf. SFD-UI-7).
- **partage natif** `navigator.share` (mobile iOS/Android) — non implémenté.
- **comparatif inter-années** (graphique 2025 vs 2026, variation %, projection annuelle) — non couvert.
- **détail des heures complémentaires, indemnités d'entretien, repas fournis, congés payés** — non décomposé dans la maquette (`brut` et `net` sont les seules colonnes affichées).
- **édition manuelle** des montants par l'employée — strictement read-only (cf. SFD-WRITE-1).
- **filtrage / recherche** par mois ou contrat dans la table mensuelle — pas de barre de recherche.
- **gestion des contrats clôturés** (FEAT 22) — la requête SQL ne filtre pas sur `BebeStatut` (tous les contrats actifs ou clôturés de l'employée apparaissent si la table `dbo.Abattement` contient des lignes les concernant). Décision intentionnelle preview — la FEAT future pourra ajouter un filtre opt-in.
- **persistance UX** (mémoriser la dernière année consultée dans localStorage) — pas en preview (cf. BR-UI-7).
- **i18n des libellés** — libellés en dur en français.
- **mode dark / high-contrast** — non couvert.
- **animation de transition d'année** (cross-fade entre années) — pas d'animation, re-render direct.
- **alertes / notifications fiscales** (rappel échéance déclaration, seuil d'imposition atteint) — out of scope.
- **export CSV / XLSX** de la table mensuelle — out of scope.
- **lien externe** vers impots.gouv.fr ou pajemploi.fr — pas de redirection sortante.
- **historique d'années** au-delà des 2 années glissantes (rétroactif 2023/2024, ou prospectif 2027) — la requête SQL filtre `Annee >= Year(Getdate()) - 1` ; étendre la fenêtre nécessitera une FEAT future avec un paramètre de filtre.
- **graphique / chart** (courbe mensuelle, barre par contrat) — la maquette est purement tabulaire.
- **rôles Admin / Parent / Comptable** — preview uniquement pour l'employée connectée.
- **A/B test ou feature flag** de cette FEAT — la page est livrée en condition normale.
- **versioning des données** (changelog des valeurs `dbo.Abattement`) — pas requis ; trace par audit log SQL si DBA le configure.
- **télémétrie d'usage** — pas de tracking (cf. BR-UI-8).
- **tests E2E Playwright** spécifiques à cette FEAT — les ACs sont vérifiables par tests unitaires sur composant/service et tests d'intégration backend ; un E2E complet sera ajouté avec la FEAT successive.
- **migration Prisma `migrate`** : le projet utilise un workflow DBA → SQL script idempotent (cf. `prisma/scripts/create-abattement.sql`). Le `schema.prisma` est synchronisé manuellement avec l'état réel de la base. Aucun `prisma migrate dev` n'est invoqué.
