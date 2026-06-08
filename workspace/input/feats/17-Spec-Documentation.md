# Spec: documentation

FEAT ID: 17-Spec-Documentation
Spec ID: spec-documentation
Status: Draft

> **Pré-requis schéma** : la table `dbo.Documentation` est supposée préexistante en base avec exactement les 5 colonnes décrites ci-dessous (`DocumentationId`, `Titre`, `Icon`, `Tri`, `Url`). Toute incohérence schéma → STOP DBA avant `dev-backend`. Source de vérité = DB existante (cf. `docs/principles/source-first.md`). Aucune migration DDL n'est introduite par cette FEAT — la table est lue uniquement, jamais écrite.

## Context

L'application Demo expose aujourd'hui un menu latéral global (cf. `spec-menu-principale` FEAT 5) qui dirige l'employé connecté vers les modules métiers (`/bebes`, `/rapports`, `/donnees`, `/contrats`). Il n'existe **aucune page de documentation** centralisée : l'employé qui souhaite consulter les ressources de référence du métier (projet d'accueil, formations VAE / CAP petite enfance, site service-public.fr, France Travail, impôts, relais assistantes maternelles, etc.) n'a pas de point d'entrée unique dans l'application — il doit ouvrir un navigateur tiers et taper les URLs de mémoire.

Cette spec introduit une **page statique de consultation** `/documentation` accessible depuis un nouvel item « Documentation » ajouté au menu principal (extension de FEAT 5 — cf. SFD-1). La page liste les ressources documentaires stockées en base dans la table `dbo.Documentation` (5 colonnes : `DocumentationId`, `Titre`, `Icon`, `Tri`, `Url`), triées par `Tri ASC`, chacune rendue comme une **card cliquable** (`<a href>`) qui ouvre l'URL dans un nouvel onglet du navigateur. Aucune écriture en base, aucun état applicatif — pure consultation read-only.

Le mockup `workspace/input/ui/17-1-documentation.html` matérialise le rendu canonique : barre supérieure avec hamburger + logo `Nounou<em>Job</em>`, **barre de recherche pleine largeur** (champ pill avec icône loupe à gauche et bouton croix à droite quand non vide), **liste verticale de cards documentaires** (gap 10px, padding 14px par card, border-radius 22px, ombre xs, hover lift -1px + shadow md), chaque card composée de :
1. **Tuile icône 46×46** à gauche (border-radius 16px, background coloré dérivé de `DocumentationId`, contenant une **icône Google Material Icons** rendue en tant que glyphe de police (font-icon, pas SVG) — le nom de l'icône est la valeur littérale de la colonne `Icon` (ex. `"description"`, `"language"`, `"link"`, `"school"`, `"account_balance"`) ;
2. **Libellé `Titre` en gras** (font-size 15px, font-weight 700, color `var(--nj-ink-900)`) ;
3. **Aucune métadonnée supplémentaire** (pas de badge, pas de chevron action, pas d'URL exposée à l'utilisateur — le mockup montre un layout simplifié sans `.doc-item__action` ni `.doc-badge` dans le rendu canonique de cette FEAT).

> **Note maquette** : le mockup `17-1-documentation.html` inline les icônes en SVG brut pour rester autonome (pas de dépendance fonts au moment de l'aperçu statique). Le **rendu canonique de cette FEAT** remplace ce SVG inliné par un `<span class="material-icons">{ligne.icon}</span>` (ou `<span class="material-symbols-outlined">{ligne.icon}</span>` selon la variante chargée — cf. SFD-13) — le nom de l'icône lu depuis la colonne `dbo.Documentation.Icon` est passé tel quel comme `textContent` du `<span>`, la police Material Icons (ou Material Symbols) le résout en glyphe. La maquette reste la référence pour le **layout**, pas pour la technologie d'icône.

La **barre de recherche** filtre la liste **au fur et à mesure** de la frappe (event `input`, debounce non requis vu le volume attendu — cf. NFC) : la normalisation est `lowercase + suppression diacritiques (NFD + strip combining marks)` côté frontend, le match est `substring` sur le `Titre` normalisé. Quand l'utilisateur tape `projet`, la card `Projet d'accueil` reste visible et toutes les autres sont masquées. Un message `Aucun document ne correspond.` est affiché si le filtre vide la liste. Le bouton croix à droite vide le champ et restaure la liste complète.

Le **clic** sur une card déclenche une navigation native `<a href="{Url}" target="_blank" rel="noopener">` qui ouvre l'URL stockée en base dans un nouvel onglet du navigateur (par exemple `https://monenfant.fr/...`, `https://www.francevae.fr`, `https://www.service-public.fr/...`). Aucun appel API supplémentaire, aucune redirection serveur, aucune URL générée dynamiquement — c'est la valeur littérale du champ `Url` de la table qui est consommée.

## Objective

L'employé connecté ouvre le menu principal et clique sur l'item « Documentation » → la SPA navigue vers `/documentation` ; le frontend envoie un unique `GET /api/documentation` qui retourne le tableau JSON de toutes les lignes de `dbo.Documentation` triées par `Tri ASC`, payload aplati `[ { documentationId, titre, icon, tri, url }, ... ]`. Le frontend rend la page complète : barre supérieure (hamburger + logo), champ de recherche pill, liste verticale de cards documentaires (icône 46×46 à background coloré dérivé, libellé en gras), filtre live à la frappe (normalisation accents + lowercase, match substring sur `titre`), navigation externe au clic via `<a href target="_blank">`. La page reste interactive : l'employé peut filtrer plusieurs fois, ouvrir plusieurs documents dans plusieurs onglets, et revenir au menu via le bouton hamburger (header). Aucune action backend autre que la lecture initiale n'est déclenchée.

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps de chargement de la liste documentaire (1 requête SQL `SELECT` sans JOIN) + temps de rendu de la page côté frontend (calcul pur, pas de fetch additionnel) + latence de filtrage in-memory à la frappe
- Target: p95 chargement `GET /api/documentation` < 300 ms sur 4G simulé (1 SELECT sur table ≤ 50 lignes typiques en pratique, payload < 8 KB JSON pour 30 documents) ; p95 rendu initial de la liste après réception du payload < 60 ms côté frontend ; p95 latence de filtrage à chaque frappe < 16 ms (1 frame à 60 FPS — calcul pur côté navigateur, pas de fetch) ; p95 ouverture du nouvel onglet au clic sur une card < 100 ms (navigation native navigateur, hors latence réseau du site cible)
- Deadline: livraison stack `kotlin-spring-boot × react × shadcn` au 2026-09-15

## Non-Functional Constraints (v7.0.0)

- Expected volume: ~10-30 lignes typiques en base `dbo.Documentation` (la table est curée manuellement par un admin via une FEAT future hors scope) ; ~1-3 chargements `/documentation` / employé / semaine (consultation occasionnelle, pas usage quotidien) ; ~0 écriture déclenchée par cette FEAT (la table est lue uniquement, jamais mutée) ; total trafic ajouté par cette FEAT < 1 KB/employé/jour
- Performance SLA: p95 chargement < 300 ms (cf. Quantified Goal) ; aucun risque N+1 (1 SELECT plat sans JOIN) ; latence de filtrage frontend < 16 ms par frappe (boucle JS `Array.filter` + `String.includes` sur ≤ 50 entrées normalisées une seule fois au chargement et mémorisées)
- Data retention: aucune nouvelle ligne créée par cette FEAT (lecture seule sur `dbo.Documentation`) ; aucune migration DDL ; pas de cache backend (la requête est suffisamment rapide pour un appel direct DB à chaque GET)
- Compliance: RGPD — la table `Documentation` ne contient aucune donnée personnelle (uniquement des libellés génériques `Titre`, des identifiants d'icône `Icon`, un entier `Tri`, et des URLs publiques `Url`) ; aucune information sur l'employé n'est jointe au payload ; aucun log d'accès par employé n'est introduit (consultation anonyme)
- Integration: nouvelle route SPA `/documentation` + nouvel endpoint backend `GET /api/documentation` ; aucune dépendance externe ; aucun service tiers ; aucune notification ; aucun WebSocket / SSE
- Degraded mode: si la requête SQL échoue (5xx, timeout), la page affiche un message d'erreur générique avec bouton « Réessayer » qui re-déclenche le GET (cf. SFD-15) ; si la table `dbo.Documentation` est vide (aucune ligne), la page affiche l'état vide `Aucun document disponible.` (cf. SFD-14) ; si une ligne a un champ `Icon` inconnu du mapping frontend, un fallback icône générique (rectangle gris avec point d'interrogation) est rendu (cf. BR-7) ; si une ligne a une `Url` malformée (ne commence pas par `http://` ou `https://`), elle est exclue du payload côté backend avec log WARN (cf. BR-9) ; aucun fallback offline / cache local

## Actors

- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session (cf. `spec-connexion`). Seule autorisée à consulter la page `/documentation` (la route est protégée par le même middleware d'authentification que les autres pages applicatives — cf. BR-1). **Note importante** : le contenu de la table `dbo.Documentation` est **global et non scopé par employé** — tous les employés voient le même tableau. Aucun filtrage par `EmployeeId` n'est appliqué côté backend (cf. BR-2).

## Functional Needs

### Point d'entrée et navigation

- SFD-1: La spec **étend `spec-menu-principale` (FEAT 5)** en ajoutant un **nouvel item « Documentation »** dans la liste de navigation du panneau latéral (entre `Mes contrats` et le bouton `Se déconnecter`, ou en position arbitraire mais documentée — cf. AC-1). L'icône de l'item est une icône `book` ou `file-text` cohérente avec le design system du menu (SVG inliné, 23×23 px, couleur `var(--nj-ink-700)` au repos, `var(--nj-coral-600)` actif). Un clic sur l'item déclenche une navigation SPA vers `/documentation` (cf. FEAT 5 BR-2) et ferme le menu (cf. FEAT 5 AC-6).
- SFD-2: La nouvelle route SPA `/documentation` est protégée par le middleware d'authentification global de l'application — un utilisateur non authentifié est redirigé vers `/login` (cf. `spec-connexion`, FEAT 5 BR-1).
- SFD-3: La page `/documentation` rend une barre supérieure identique à celle du mockup `17-1-documentation.html` : à gauche un bouton hamburger (40×40, background `var(--nj-surface)`, color `var(--nj-ink-700)`, border-radius `var(--nj-radius-md)`, ombre xs) qui réouvre le menu principal au clic ; au centre-gauche un titre `Nounou<em>Job</em>` (font-size 19px, font-weight 800, letter-spacing -0.02em, le `Job` en `var(--nj-coral-600)`) ; le reste de la barre est un spacer flex (pas de bouton à droite dans cette FEAT).

### Schéma de données — table `dbo.Documentation` (lecture seule)

- SFD-4: La spec lit la table préexistante `dbo.Documentation` qui possède exactement les 5 colonnes suivantes :

  | Colonne | Type SQL | Nullable | Description |
  |---|---|---|---|
  | `DocumentationId` | `INT` (clé primaire, identité) | `NOT NULL` | Identifiant unique de la ligne, utilisé pour calculer le background coloré dérivé (cf. BR-6) |
  | `Titre` | `NVARCHAR(...)` (longueur libre, en pratique ≤ 100) | `NOT NULL` | Libellé affiché en gras dans la card (ex. `Projet d'accueil`, `Formation CAP petite enfance`) |
  | `Icon` | `NVARCHAR(...)` (longueur libre, en pratique ≤ 60 caractères snake_case) | `NOT NULL` | **Nom d'icône Google Material Icons / Material Symbols** (ex. `description`, `language`, `link`, `school`, `account_balance`, `picture_as_pdf`, `work`, `gavel`) — passé tel quel comme `textContent` d'un `<span class="material-icons">` côté frontend ; la police Material Icons (cf. SFD-13) le résout en glyphe (cf. BR-7) |
  | `Tri` | `INT` | `NOT NULL` | Entier de tri croissant — la liste est rendue `ORDER BY Tri ASC` (cf. BR-8) |
  | `Url` | `NVARCHAR(...)` (longueur libre, en pratique URL HTTP/HTTPS) | `NOT NULL` | URL absolue ouverte dans un nouvel onglet au clic ; doit commencer par `http://` ou `https://` (cf. BR-9) |

  Aucune autre colonne n'est introduite ou modifiée par cette FEAT. La table est supposée préexistante en base — sa création / migration relève d'une FEAT admin hors scope. La spec n'introduit aucun DDL (cf. Pré-requis schéma).

### Endpoint backend — `GET /api/documentation`

- SFD-5: Nouvel endpoint backend `GET /api/documentation` (verbe GET, route en kebab-case singulier `documentation`, pas de query param ni de path param). La requête SQL canonique exécutée par le backend est **strictement** :
  ```sql
  SELECT [DocumentationId], [Titre], [Icon], [Tri], [Url]
  FROM [Documentation]
  ORDER BY Tri;
  ```
  - Aucun filtre `WHERE` (la table est globale — cf. BR-2).
  - Aucun JOIN (la table est isolée).
  - Aucun tri secondaire — `ORDER BY Tri` tel quel, l'ordre des lignes en cas d'égalité de `Tri` est celui retourné par le moteur SQL (non-déterministe mais acceptable — l'admin est responsable de l'unicité des valeurs `Tri` à l'insertion).
  - Aucune transformation, aucun filtrage applicatif, aucune validation des champs lus — le payload est l'image brute des 5 colonnes de la table (pas de CRUD, cf. BR-12).
  - La requête est sans paramètre (pas d'interpolation, pas de concaténation — anti-injection SQL trivial puisqu'aucun input utilisateur n'atteint la requête).
- SFD-6: La réponse JSON de l'endpoint backend `GET /api/documentation` est de la forme :
  ```json
  [
    {
      "documentationId": 1,
      "titre": "Projet d'accueil",
      "icon": "pdf",
      "tri": 1,
      "url": "https://exemple.com/projet-accueil.pdf"
    },
    {
      "documentationId": 2,
      "titre": "Assistantes maternelles par commune",
      "icon": "site",
      "tri": 2,
      "url": "https://monenfant.fr/que-recherchez-vous/un-mode-d-accueil/assistant-maternel"
    },
    {
      "documentationId": 3,
      "titre": "Relais Assistantes Maternelles",
      "icon": "link",
      "tri": 3,
      "url": "https://www.relais-assistantes-maternelles.fr"
    }
  ]
  ```
  - Les clés JSON sont **camelCase** (`documentationId`, `titre`, `icon`, `tri`, `url`) — cf. BR-4.
  - Toutes les valeurs sont non-nullables (la table est `NOT NULL` sur les 5 colonnes — cf. SFD-4).
  - `tri` est un entier (sérialisé `Int`, jamais string).
  - Le payload **n'inclut aucune métadonnée d'enveloppe** (pas de `{ data: [...] }`, pas de `{ items: [...], total: N }`) — c'est un tableau JSON à la racine pour rester aligné avec les autres endpoints `GET /api/*` de l'application (cf. FEAT 11 SFD-5, FEAT 15 SFD-8).

### Route SPA `/documentation` — page statique

- SFD-7: La page SPA `/documentation` est un composant frontend dédié (nom de composant `DocumentationPage` ou équivalent stack — cf. plan dev-frontend). Au montage, elle envoie **une seule** requête `GET /api/documentation` (cf. SFD-5) et stocke le résultat dans un state local React (ou équivalent stack). Aucune autre requête réseau n'est émise par la page (pas de prefetch, pas de telemetry, pas de feature flag query).
- SFD-8: La page rend les éléments DOM dans cet ordre (de haut en bas) :
  1. **Status bar iOS** (cosmétique, hérité du gabarit phone-mockup — cf. FEAT 4 / FEAT 5).
  2. **Topbar** : bouton hamburger (40×40, classe `.topbar__menu`) + titre `Nounou<em>Job</em>` (classe `.topbar__title`) + spacer flex (cf. SFD-3).
  3. **Zone scrollable** (classe `.doc-scroll`) contenant :
     - **Barre de recherche** (cf. SFD-10) — champ `input[type="search"]` pleine largeur en pill (cf. SFD-11).
     - **Message état vide filtré** (cf. SFD-14) — `<div class="doc-empty" hidden>Aucun document ne correspond.</div>` affiché ssi le filtre courant ne match aucune ligne.
     - **Liste de cards documentaires** (classe `.doc-list`) — `<a class="doc-item">` par ligne du payload, dans l'ordre du tableau JSON reçu (donc déjà trié par `Tri ASC`).
  4. **Tab bar** (vide / masquée — `<nav class="tabbar" hidden></nav>`) — réservée pour FEAT future éventuelle.
  5. **Home indicator iOS** (cosmétique).
- SFD-9: Chaque `<a class="doc-item">` rend :
  - **Attributs HTML** : `href="{ligne.url}"`, `target="_blank"`, `rel="noopener"` (cf. BR-10 — `noopener` obligatoire pour la sécurité du `window.opener`). Pas de `noreferrer` par défaut (le site cible peut légitimement collecter le referer Demo ; si la politique projet change, le frontend peut systématiser `rel="noopener noreferrer"` — décision out of scope ici).
  - **Tuile icône** : `<span class="doc-item__icon" style="background: {color-bg-derived};">{SVG inliné de l'icône}</span>` — voir SFD-12 (calcul du background) et SFD-13 (mapping icône).
  - **Corps** : `<div class="doc-item__body"><p class="doc-item__name">{ligne.titre}</p></div>` — `<p>` font-size 15px, font-weight 700 (gras — cf. BR-5).
  - **Pas de chevron action**, **pas de badge**, **pas de URL exposée** dans le rendu canonique (le mockup `17-1-documentation.html` montre une version simplifiée — les classes `.doc-item__action`, `.doc-badge`, `.doc-item__src` du mockup d'origine ne sont pas réutilisées par cette FEAT pour rester minimal).

### Barre de recherche — filtre live

- SFD-10: La barre de recherche est un `<input type="search">` avec placeholder `Rechercher un document`, autocomplete désactivé, à l'intérieur d'un conteneur `.doc-search` contenant aussi (a) une icône loupe SVG positionnée absolue à gauche (classe `.doc-search__icon`, 18×18, `var(--nj-ink-400)`, `pointer-events: none`) et (b) un bouton croix `.doc-search__clear` positionné absolu à droite (30×30, background `var(--nj-cream)`, `var(--nj-ink-500)`, hidden quand le champ est vide).
- SFD-11: Le filtre live applique l'algorithme suivant **à chaque event `input`** sur le champ recherche (pas de debounce — le volume ≤ 50 lignes garantit < 16 ms / frame, cf. NFC) :
  1. Récupérer `q = input.value.trim()`.
  2. Normaliser `q` via : `lowercase` puis `String.prototype.normalize("NFD")` puis `replace(/[̀-ͯ]/g, "")` (suppression des diacritiques combinants).
  3. Si `q.length === 0` → afficher toutes les cards (style `display: ""`) + masquer `.doc-empty` + masquer le bouton croix (`hidden = true`).
  4. Sinon, pour chaque card :
     - Récupérer le `Titre` de la card depuis l'état local React (mémorisé, pas un `textContent` du DOM).
     - Normaliser le `Titre` avec le même algorithme (lowercase + NFD + strip).
     - `match = titre_normalisé.includes(q_normalisé)`.
     - Si `match === true` → `display: ""` ; sinon → `display: "none"`.
  5. Compter `shown` = nombre de cards avec `display: ""`. Si `shown === 0` → afficher `.doc-empty` (`Aucun document ne correspond.`) ; sinon → masquer `.doc-empty`.
  6. Afficher le bouton croix (`hidden = false`).
- SFD-12: Le **background coloré aléatoire** de la tuile icône est calculé côté frontend de manière **déterministe** à partir du `documentationId` (entier reçu dans le payload). Algorithme canonique (à implémenter dans un helper `getDocBackground(id)` côté frontend, déterministe et idempotent) :
  ```
  palette = [
    { bg: "var(--nj-coral-100)",    fg: "var(--nj-coral-700)"    },
    { bg: "var(--nj-sage-100)",     fg: "var(--nj-sage-700)"     },
    { bg: "var(--nj-lavender-100)", fg: "var(--nj-lavender-700)" },
    { bg: "var(--nj-sky-100)",      fg: "var(--nj-sky-700)"      },
    { bg: "var(--nj-butter-100)",   fg: "oklch(0.42 0.10 165)"   },
    { bg: "var(--nj-mint-100)",     fg: "oklch(0.42 0.10 165)"   },
  ]
  index = documentationId % palette.length
  return palette[index]
  ```
  - L'algorithme est **purement déterministe** par `documentationId` — la card de la ligne `DocumentationId = 7` aura toujours la même couleur dans tous les écrans et tous les onglets (cf. BR-6). « Aléatoire » dans la description utilisateur signifie ici « varié sur l'ensemble de la liste », pas « différent à chaque rendu ».
  - La palette utilise les **tokens UI du design system** (cf. `rules/quality.md §B`) — aucun hex hardcodé (cf. AC-19).
  - L'inline style sur la tuile icône est `style="background: {palette[i].bg}; color: {palette[i].fg};"` — le `color` propage la couleur du SVG inliné via `currentColor` (le SVG utilise `stroke="currentColor"` ou `fill="currentColor"`).
- SFD-13: Le **rendu de l'icône** côté frontend utilise la police **Google Material Icons** (ou la variante moderne **Material Symbols Outlined**, au choix du `dev-frontend` selon les conventions du stack UI actif — la police choisie est documentée dans le plan technique mais la valeur du champ `Icon` reste compatible avec les deux car les deux fonts partagent la même nomenclature snake_case). Aucun mapping intermédiaire côté frontend — le `textContent` du `<span>` est **la valeur littérale** du champ `Icon` reçue dans le payload :
  ```jsx
  <span class="material-icons" aria-hidden="true">{row.icon}</span>
  ```
  ou, pour la variante moderne :
  ```jsx
  <span class="material-symbols-outlined" aria-hidden="true">{row.icon}</span>
  ```
  Chargement de la police (au choix du stack, ordre de préférence) :
  1. **Web font Google CDN** (recommandé par défaut, pas de dépendance npm) : `<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">` (ou `family=Material+Symbols+Outlined`) ajouté au `<head>` du `index.html` (ou layout racine équivalent). C'est la voie standard, conforme à la doc Material Icons et utilisée par Vuetify / Radzen out-of-the-box.
  2. **Package npm `material-icons`** (alternative self-hosted) : `npm i material-icons` + import CSS `@import 'material-icons/iconfont/material-icons.css';` dans le bundle. À privilégier si le projet exige du self-hosting (RGPD strict, isolation réseau).
  
  La taille / couleur de l'icône est contrôlée par CSS : `.doc-item__icon .material-icons { font-size: 26px; color: inherit; }` — la couleur hérite du `color` posé inline sur la tuile parente (cf. SFD-12).
  
  Si la valeur du champ `Icon` est un nom inconnu de la police Material Icons (typo en base, nouvelle icône non publiée, valeur vide après trim), la police rend un glyphe « tofu » (carré vide / point d'interrogation natif). Aucun fallback applicatif n'est introduit côté frontend — le glyphe « tofu » est le fallback **inhérent à la police** (cf. BR-7). La card reste cliquable et l'URL fonctionne normalement.

### États de chargement, vide et erreur

- SFD-14: Pendant le chargement initial (`GET /api/documentation` en cours), la zone `.doc-scroll` rend un **squelette** minimal — par exemple 3 placeholders `.doc-item` au layout identique avec background `var(--nj-line-soft)` et hauteur figée 75 px (gap 10 px, padding 14 px). Le champ recherche est rendu désactivé (`disabled`) pendant le chargement initial. Si la liste reçue est **vide** (payload `[]`), la page affiche un état vide pleine largeur `<div class="doc-empty">Aucun document disponible.</div>` (texte distinct du filtre vide — cf. AC-12).
- SFD-15: Si la requête SQL échoue (timeout, 5xx, erreur réseau), la zone scrollable affiche un message d'erreur générique `Impossible de charger la documentation. <button>Réessayer</button>` (style : texte centré `var(--nj-ink-500)`, bouton coral cliquable qui re-déclenche le GET). Aucune information technique (stack trace, code HTTP, message d'erreur SQL) n'est exposée (cf. BR-11, AC-13).

## Business Rules

- BR-1: l'endpoint `GET /api/documentation` est protégé par le même middleware d'authentification que les autres endpoints `/api/*` de l'application (cf. `spec-connexion`) ; une requête sans token JWT valide retourne `401 Unauthorized` ; le frontend redirige alors vers `/login` (comportement standard du client HTTP de l'app).
- BR-2: l'endpoint `GET /api/documentation` **ne filtre PAS** par `EmployeeId` — la table `dbo.Documentation` est globale, partagée par tous les employés authentifiés ; aucune notion de scoping par tenant / employé / contrat n'est introduite. Le payload est identique pour tous les employés au même instant.
- BR-3: la requête SQL est **paramétrée sans paramètres** (aucun input utilisateur n'atteint la requête) — risque d'injection SQL trivial absent ; aucune concaténation de chaîne, aucune interpolation de variables non échappées (cf. `rules/library-and-stack.md §B`, conventions cross-FEAT héritées).
- BR-4: les champs JSON renvoyés par le backend sont sérialisés en **camelCase** : `documentationId`, `titre`, `icon`, `tri`, `url` (cf. `rules/library-and-stack.md §6.bis.3`). Aucune sérialisation en PascalCase ou snake_case.
- BR-5: le libellé `titre` est rendu **en gras** dans la card (`font-weight: 700`) avec la typographie principale du design system (`var(--nj-font-sans)`, 15 px) et la couleur `var(--nj-ink-900)`. La troncature ellipsis CSS est autorisée si la card est trop étroite (`overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`) mais le rendu canonique du mockup laisse le texte se replier sur 2 lignes maximum (line-height 1.25).
- BR-6: le background coloré de la tuile icône est **calculé déterministement** côté frontend à partir du `documentationId` modulo la longueur de la palette UI (cf. SFD-12) ; la même ligne en base retourne toujours la même couleur, dans tous les rendus, dans tous les onglets, dans tous les écrans (deux employés voient les cards dans la même couleur). Aucun champ `BackgroundColor` n'est stocké en base.
- BR-7: la valeur du champ `Icon` du payload est passée **telle quelle** comme `textContent` d'un `<span class="material-icons">` (ou `material-symbols-outlined` selon la variante chargée — cf. SFD-13) ; aucun mapping intermédiaire côté frontend, aucune transformation (pas de lowercase forcé — l'admin saisit déjà en snake_case lowercase conforme à la nomenclature Material Icons). Si la valeur est inconnue de la police (typo en base, glyphe non publié), la police elle-même rend un « tofu » (carré vide) — c'est le fallback **inhérent à la police**, aucun code applicatif ne le compense. La card reste cliquable et l'URL est rendue correctement. **Convention admin** (out of scope de cette FEAT mais documentée ici) : les valeurs insérées en base doivent suivre la nomenclature officielle Google Material Icons (snake_case, en minuscules — cf. https://fonts.google.com/icons) — ex. `description`, `picture_as_pdf`, `language`, `link`, `school`, `account_balance`, `work`, `gavel`, `menu_book`.
- BR-8: le tri du payload est `ORDER BY Tri` côté backend (cf. SFD-5) ; le frontend rend les cards dans l'ordre du tableau JSON reçu sans re-trier côté client (le tri est server-state-driven — single source of truth). Aucun tri secondaire applicatif n'est imposé en cas d'égalité de `Tri` (responsabilité admin à l'insertion).
- BR-9: aucune validation, aucun filtrage, aucune transformation des champs lus côté backend — le payload est l'image brute des 5 colonnes de la table `dbo.Documentation`. Les URLs sont retournées **telles quelles** (la spec assume que l'admin saisit des URLs HTTP/HTTPS valides — pas de CRUD donc pas de validation à l'insertion non plus dans cette FEAT). Le frontend les utilise telles quelles dans le `href` du `<a>` (cf. BR-10).
- BR-10: le clic sur une card ouvre l'URL dans un **nouvel onglet** via `<a href="{url}" target="_blank" rel="noopener">` — l'attribut `rel="noopener"` est **obligatoire** (protection contre `window.opener` exposé à l'origin cible — sécurité XSS / phishing standard). L'attribut `rel="noreferrer"` est **optionnel** dans cette FEAT (la politique projet n'impose pas la coupure du referer ; un avenant peut systématiser si requis ultérieurement).
- BR-11: aucune information technique (stack trace, exception SQL, nom de colonne brut, code HTTP) n'est exposée dans les messages d'erreur côté frontend ; les libellés sont des labels statiques en français (`Impossible de charger la documentation.`, `Aucun document disponible.`, `Aucun document ne correspond.`) — cohérent avec la stratégie des autres FEATs (cf. FEAT 15 BR-15).
- BR-12: aucune écriture en base n'est déclenchée par cette FEAT — la table `dbo.Documentation` est lue uniquement par `GET /api/documentation` ; aucun endpoint `POST` / `PUT` / `DELETE` n'est introduit. La création / édition / suppression des lignes relève d'une FEAT admin future (out of scope).
- BR-13: la barre de recherche **n'expose aucune requête réseau** par frappe — le filtre est purement in-memory côté frontend (le payload complet a déjà été chargé au mount de la page, cf. SFD-7). Cette décision intentionnelle (pas de search-as-you-type côté serveur) est justifiée par le volume attendu (≤ 50 lignes — cf. NFC) ; au-delà de 500 lignes, une FEAT future pourrait introduire une recherche serveur (out of scope).
- BR-14: la normalisation du filtre (`lowercase + NFD + strip diacritiques`) est appliquée **identiquement** au texte tapé par l'utilisateur ET au `Titre` de chaque ligne — la mémoisation côté frontend pré-calcule `titre_normalisé` une seule fois au chargement du payload pour économiser les opérations à chaque frappe. Match `String.includes` (substring, sans regex, sans wildcard, sans tokenisation).
- BR-15: aucune information sensible (token JWT, identifiants applicatifs, cookies de session) n'est passée dans l'URL cible quand l'utilisateur clique sur une card — le `href` contient **exclusivement** la valeur littérale du champ `Url` du payload, sans interpolation ni paramètre additionnel.
- BR-16: aucun cookie, header de session, state local persistant (localStorage, sessionStorage, IndexedDB) n'est introduit par cette FEAT — la page est entièrement stateless côté client (cf. AC-18).
- BR-17: si le design system actif (shadcn / Vuetify / Radzen) fournit un composant `Input` natif pour le champ de recherche ET un composant `Card` natif pour les items, ils **DOIVENT** être utilisés en priorité avec override de tokens — le CSS isolé ne complète que pour la fidélité visuelle (cf. `rules/quality.md §B`).

## Acceptance Criteria

- AC-1: le menu principal (`spec-menu-principale` FEAT 5) contient un nouvel item « Documentation » avec une icône SVG cohérente (book / file-text), positionné dans la liste de navigation principale ; un clic sur cet item déclenche une navigation SPA vers `/documentation` et ferme le panneau latéral (héritage FEAT 5 AC-5 + AC-6).
- AC-2: la route `/documentation` est protégée — un utilisateur non authentifié est redirigé vers `/login` (héritage FEAT 5 BR-1).
- AC-3: au chargement initial, la page envoie **une seule** requête `GET /api/documentation` qui retourne un tableau JSON `[ { documentationId, titre, icon, tri, url }, ... ]` ; aucune requête additionnelle (telemetry, prefetch, feature flags) n'est émise (vérifiable Network DevTools — anti N+1).
- AC-4: la requête SQL exécutée par le backend est **strictement** `SELECT [DocumentationId], [Titre], [Icon], [Tri], [Url] FROM [Documentation] ORDER BY Tri` ; aucun JOIN, aucun WHERE, aucun GROUP BY, aucun TOP, aucun tri secondaire (vérifiable par log SQL ou test d'intégration).
- AC-5: le payload est sérialisé en **camelCase** (`documentationId`, `titre`, `icon`, `tri`, `url`) ; aucune clé en PascalCase ou snake_case ne doit apparaître (vérifiable par contrat OpenAPI ou test d'intégration JSON).
- AC-6: les cards sont rendues dans l'ordre du tableau JSON (donc trié par `Tri` côté backend) ; le frontend **ne re-trie pas** côté client (vérifiable : 5 lignes avec `Tri = [3, 1, 2, 1, 5]` apparaissent dans un ordre où les deux `Tri=1` sont contigus en tête, puis `Tri=2`, puis `Tri=3`, puis `Tri=5`).
- AC-7: chaque card rend (a) une tuile icône 46×46 à gauche avec un background coloré dérivé de `documentationId % palette.length` (cf. SFD-12) ET un `<span class="material-icons">{icon}</span>` (ou variante `material-symbols-outlined`) dont le `textContent` est **strictement égal** à la valeur du champ `icon` du payload (cf. SFD-13), (b) un libellé `titre` en gras (font-weight 700, color `var(--nj-ink-900)`) ; aucun chevron / badge / URL exposée dans le rendu canonique. Vérifiable par DOM query : `document.querySelectorAll('.doc-item__icon .material-icons').forEach(el => expect(payload.map(r => r.icon)).toContain(el.textContent.trim()))`.
- AC-8: chaque card est un `<a>` avec `href="{url}"`, `target="_blank"`, `rel="noopener"` ; un clic ouvre l'URL dans un nouvel onglet du navigateur (vérifiable manuellement OU par test E2E Playwright).
- AC-9: la barre de recherche filtre la liste **à chaque frappe** sans appel réseau (vérifiable Network DevTools : aucune requête HTTP émise pendant la saisie) ; la normalisation supprime accents et casse — par exemple taper `projet` matche `Projet d'accueil`, taper `formation` matche `Formation CAP petite enfance`, taper `pétiTe` matche `Formation CAP petite enfance`.
- AC-10: quand le filtre courant ne match aucune card, le message `Aucun document ne correspond.` est affiché et toutes les cards sont masquées (`display: none`) ; quand le champ est vidé (par frappe ou par clic sur le bouton croix), la liste complète est restaurée.
- AC-11: le bouton croix `.doc-search__clear` est masqué (`hidden = true`) quand le champ est vide, et visible dès que le champ contient au moins 1 caractère ; un clic vide le champ, redonne le focus à l'input, et restaure la liste complète.
- AC-12: si l'API retourne un tableau vide (`[]` — table `dbo.Documentation` sans ligne), la page affiche **un seul** état vide pleine largeur `Aucun document disponible.` ; ce libellé est distinct du libellé filtre vide (`Aucun document ne correspond.`) — vérifiable par fixture d'intégration retournant `[]`.
- AC-13: si l'API retourne une erreur (5xx, timeout réseau), la page affiche `Impossible de charger la documentation.` avec un bouton `Réessayer` qui re-déclenche le GET ; aucune trace technique n'est exposée à l'utilisateur (pas de code HTTP, pas de message d'erreur SQL).
- AC-14: pendant le chargement initial (avant réception du payload), la zone scrollable affiche un squelette minimal (3 placeholders rectangulaires) et le champ recherche est désactivé ; au succès, le squelette est remplacé par les cards et le champ devient actif.
- AC-15: le background coloré de chaque tuile icône est **stable cross-rendu** — deux chargements successifs de la même page produisent les mêmes couleurs sur les mêmes lignes (vérifiable par snapshot DOM ou test E2E qui charge `/documentation` deux fois et compare les `style="background:..."` des tuiles).
- AC-16: si une ligne du payload contient un `icon` non reconnu par la police Material Icons (typo en base, glyphe non publié, valeur vide), la card rend le glyphe « tofu » natif de la police (carré vide) — aucun fallback applicatif n'est exécuté, aucun `console.warn` n'est émis (la police gère seule l'inconnu — cf. BR-7) ; l'item reste cliquable et l'URL fonctionne (vérifiable par fixture avec `icon: "totally_unknown_glyph_xyz"`).
- AC-17: le backend **ne valide pas, ne filtre pas, ne transforme pas** les valeurs lues — le payload reflète exactement l'image brute de la table (vérifiable par fixture qui insère 3 lignes et vérifie que `GET /api/documentation` retourne exactement les 3 lignes avec les mêmes valeurs).
- AC-18: aucun nouveau cookie, header de session, state local persistant (localStorage, sessionStorage, IndexedDB) n'est introduit par cette FEAT — l'état de la page est purement dérivé du payload courant et de l'état React local (vérifiable DevTools Application).
- AC-19: le rendu des cards et de la barre de recherche utilise **exclusivement** des tokens CSS (`var(--nj-coral-100)`, `var(--nj-sage-100)`, `var(--nj-lavender-100)`, `var(--nj-sky-100)`, `var(--nj-butter-100)`, `var(--nj-mint-100)`, `var(--nj-coral-700)`, `var(--nj-ink-900)`, `var(--nj-ink-500)`, `var(--nj-ink-400)`, `var(--nj-surface)`, `var(--nj-line)`, `var(--nj-line-soft)`, `var(--nj-radius-lg)`, `var(--nj-radius-md)`, `var(--nj-radius-pill)`, `var(--nj-shadow-xs)`, `var(--nj-shadow-md)`, `var(--nj-font-sans)`, `var(--nj-font-mono)`, `var(--nj-dur-fast)`) — aucun hex hardcodé dans les composants (cf. `rules/quality.md §B.5`, vérifiable par grep `#[0-9a-fA-F]{3,8}` post-build).
- AC-20: aucune nouvelle dépendance **npm / NuGet / Maven** n'est introduite par cette FEAT — le filtre live et le calcul de background sont du code TypeScript / Kotlin pur ; le tri est natif SQL ; la requête HTTP utilise le client HTTP déjà existant (cf. FEAT 11 / FEAT 15). **Exception documentée** : la police Material Icons est chargée via la voie 1 de SFD-13 (web font Google CDN — `<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">` ajouté au `<head>` du layout racine) qui **n'est pas un package npm** mais une ressource web externe ; si le stack ou la politique projet exige du self-hosting (RGPD, isolation réseau), la voie 2 (`npm i material-icons`) est autorisée et **ajoute une seule dépendance** dûment tracée dans le `.libs.json` du stack frontend (cf. `library-and-stack.md §1.0`). Vérifiable côté CI : si voie 1, aucun diff sur les manifests ; si voie 2, exactement un ajout `material-icons` dans `package.json` et dans `.libs.json` du stack.
- AC-21: **wiring backend non contournable** — le handler de la route HTTP `GET /api/documentation` invoque **directement** un service `documentationService.listAll` (ou équivalent stack — `DocumentationService.listAll` côté Spring/.NET, `documentation_service.list_all` côté FastAPI) qui retourne le tableau JSON peuplé par la requête SQL SFD-5. Vérifiable par : (a) test d'intégration HTTP — `GET /api/documentation` avec session JWT valide → tableau JSON avec les 5 clés AC-5 ; (b) grep statique sur le handler de la route — montre l'appel au service **dans le même chemin d'exécution** que la sérialisation du payload ; (c) tout fichier `services/documentation*.{js,ts,kt,cs,py}` orphelin (jamais importé par `routes/documentation.routes.*` ou équivalent stack) est un **gap bloquant** [FRONTEND_BACKEND_CONTRACT_GAP] (cf. `library-and-stack.md §6.bis.4`).
- AC-22: **anti-derive ownership** — la FEAT 17 crée **un nouveau service** `services/documentationService.*` et **un nouveau repository** `repositories/documentationRepository.*` (cf. `ownership.md §1` Create exclusif côté nouveaux fichiers) ; aucune modification des services existants `babyService` / `rapportService` / `contratService` (cf. FEAT 4 / 11 / 15). Un commit qui ne livre **que** le route handler sans le service ou le repository correspondant viole cette FEAT.

## Dependencies

- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employé connecté ; le middleware d'authentification protège `/documentation` et `GET /api/documentation` (cf. BR-1).
- **spec-menu-principale** (`5-spec-menu-principale`) : **étendue directement** par cette FEAT — ajout d'un nouvel item « Documentation » dans la liste de navigation du panneau latéral (cf. SFD-1, AC-1). L'item suit le pattern visuel des 4 items existants (`Mes bébés`, `Rapports`, `Mes données`, `Mes contrats`) avec une icône book / file-text et une navigation SPA vers `/documentation`.
- **dbo.Documentation** (table SQL préexistante) : table globale lue par cette FEAT (5 colonnes `DocumentationId`, `Titre`, `Icon`, `Tri`, `Url` — cf. SFD-4) ; aucune migration DDL introduite ; aucune écriture déclenchée (cf. BR-12).

## Functional Deliverables

- FD-1: nouvel item « Documentation » ajouté à la liste de navigation du panneau latéral de `spec-menu-principale` (extension FEAT 5) — icône book / file-text SVG inlinée, libellé `Documentation`, navigation SPA vers `/documentation` au clic + fermeture du panneau (héritage FEAT 5 AC-5 + AC-6).
- FD-2: nouvelle route SPA `/documentation` rendant un composant `DocumentationPage` (ou équivalent stack) — barre supérieure (hamburger + logo), barre de recherche pill, liste de cards documentaires triées par `Tri ASC` (cf. SFD-7, SFD-8).
- FD-3: nouvel endpoint backend `GET /api/documentation` — requête SQL plate sur `dbo.Documentation` (cf. SFD-5) + sérialisation camelCase + middleware d'authentification (cf. BR-1). **Aucune** logique applicative au-delà de la lecture (pas de validation, pas de filtrage, pas de transformation — cf. BR-9, AC-17).
- FD-4: nouveau service backend `documentationService.listAll` (ou équivalent stack — `DocumentationService.listAll` Spring/.NET, `documentation_service.list_all` FastAPI) appelé directement par le route handler de `GET /api/documentation` (cf. AC-21) ; pas de logique additionnelle (mapping direct row → DTO).
- FD-5: nouveau repository backend `documentationRepository.findAllOrderedByTri` (ou équivalent stack) exécutant la requête SQL SFD-5 ; classe DTO `DocumentationDto` (5 champs `documentationId`, `titre`, `icon`, `tri`, `url`) exposée au service (cf. AC-22).
- FD-6: barre de recherche pill (cf. SFD-10) avec filtre live in-memory côté frontend (cf. SFD-11) — normalisation `lowercase + NFD + strip diacritiques` (cf. BR-14), match `String.includes`, message état vide filtré `Aucun document ne correspond.`, bouton croix `.doc-search__clear` (cf. AC-11).
- FD-7: helper frontend `getDocBackground(documentationId)` retournant `{ bg, fg }` par `documentationId % palette.length` (cf. SFD-12) — palette de 6 couleurs (coral, sage, lavender, sky, butter, mint en tones 100/700) consommant les tokens UI (cf. AC-19).
- FD-8: chargement de la police **Google Material Icons** (voie 1 web font CDN — `<link>` dans `<head>` du layout racine ; OU voie 2 self-hosted `npm i material-icons` selon politique projet — cf. SFD-13, AC-20) + rendu inline `<span class="material-icons" aria-hidden="true">{row.icon}</span>` dans chaque card (pas de mapping intermédiaire, pas de helper — la valeur du champ `Icon` est `textContent` direct, cf. BR-7).
- FD-9: états de chargement / vide / erreur côté frontend — squelette 3 placeholders pendant le GET (cf. SFD-14), libellé vide global `Aucun document disponible.` (cf. AC-12), libellé erreur générique `Impossible de charger la documentation.` + bouton `Réessayer` (cf. SFD-15, AC-13).
- FD-10: maquette `workspace/input/ui/17-1-documentation.html` matérialisant le rendu canonique (barre supérieure + recherche + liste de 9 cards exemples) — référence visuelle non-ambiguë pour `dev-frontend`.

## Out of Scope

- **création / migration / édition / suppression** des lignes de `dbo.Documentation` : la table est lue uniquement ; toute mutation relève d'une FEAT admin future (CRUD documentation côté admin).
- **upload de fichiers PDF** ou ressources binaires : le champ `Url` est une URL externe ; la spec ne couvre pas le stockage de PDFs / images côté Demo (out of scope — la table pointe vers des ressources hébergées ailleurs).
- **recherche serveur** (search-as-you-type avec endpoint dédié, pagination, full-text-search) : non requise vu le volume attendu (≤ 50 lignes — cf. BR-13) ; FEAT future éventuelle si le volume dépasse 500.
- **catégorisation / regroupement** par section (ex. « Formation », « Réglementaire », « Outils ») : le mockup montre une liste plate sans section ; un regroupement par `Categorie` nécessiterait une 6ème colonne en base (out of scope).
- **favoris / pinned** : l'employé ne peut pas marquer une ressource comme favorite (aucun stockage par employé — cf. BR-2) ; FEAT future éventuelle avec une table `EmployeeDocumentationFavorite`.
- **historique de consultation** (tracking des clics, analytics par ressource) : aucun log par employé n'est introduit (cf. NFC compliance) — la consultation est anonyme.
- **téléchargement direct** (forcer un `Content-Disposition: attachment`) : la spec ouvre l'URL en navigation native — le comportement (téléchargement vs ouverture inline) est dicté par les headers du serveur cible, pas par Demo.
- **prévisualisation inline** (iframe / lecteur PDF embarqué) : aucune prévisualisation dans la SPA — le clic ouvre toujours un nouvel onglet (cf. BR-10, AC-8).
- **i18n des libellés statiques** (`Rechercher un document`, `Aucun document ne correspond.`, `Aucun document disponible.`, `Impossible de charger la documentation.`, `Réessayer`) : libellés en dur en français pour cette FEAT (cf. FEAT 15 BR-14) ; l'i18n future n'impactera pas le backend (le backend retourne `titre` brut, pas de label).
- **validation à l'insertion** que le nom d'icône Material Icons stocké dans `Documentation.Icon` est un glyphe publié dans la version courante de la police (la police a ~2000+ glyphes publiés et évolue) : aucune validation côté backend ou frontend dans cette FEAT — la convention admin (cf. BR-7) suffit ; un avenant pourrait introduire un linter à l'insertion (out of scope) ou un fallback applicatif visible (out of scope, cf. AC-16).
- **icônes alternatives** (Font Awesome, Lucide, Tabler, Phosphor, Hero Icons) : la spec impose Material Icons / Material Symbols (cf. SFD-13) pour rester compatible avec le contenu existant de la table `dbo.Documentation`. Tout changement de provider d'icône nécessiterait une migration des valeurs `Icon` en base (out of scope).
- **gestion offline** / cache local du payload : aucun stockage local (cf. AC-18 + BR-16) ; le payload est rechargé à chaque visite de la page.
- **partage social** (boutons « Partager sur Facebook / Twitter / WhatsApp ») : aucun bouton de partage exposé ; un avenant peut introduire le pattern `navigator.share` ultérieurement.
- **mode hors-ligne** des URLs (snapshot HTML offline) : aucun export / archive ; les URLs externes sont consommées en live.
- **notification au parent** (SMS / Email / Push) lors de la consultation d'un document : aucune notification (cf. NFC integration) ; consultation purement passive.
- **rôles Admin / Parent** : un Admin qui éditerait la table `dbo.Documentation` ou un Parent qui consulterait une documentation parent-spécifique relève d'une FEAT future dédiée avec règles différentes (filtrage par rôle, scoping par compte parent).
- **support multi-locale du `Titre`** (versions française / anglaise / espagnole de la même ressource) : un seul `Titre` en base (FR implicite) ; une i18n complète nécessiterait une table `DocumentationTranslation` (out of scope).
- **validation au moment de l'insertion** des URLs malformées (`javascript:`, `data:`, chemins relatifs) côté admin / migration : la spec filtre côté backend au moment du GET (cf. BR-9) — la validation à l'insertion relèverait de la FEAT admin CRUD.
