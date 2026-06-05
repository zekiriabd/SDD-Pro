# Spec: parametres

FEAT ID: 20-Spec-Parametres
Spec ID: spec-parametres
Status: Draft

> **Pré-requis schéma — ACTION DBA REQUISE AVANT `dev-backend`** : la table `dbo.Employee` est supposée préexistante (cf. `spec-inscription` FEAT 3, `spec-reseau-assistantes` FEAT 19) et doit contenir **exactement** les 2 colonnes booléennes suivantes consommées par cette FEAT :
> - `Disponible` (BIT, `NOT NULL`, default `1`) — déjà consommée par FEAT 19 BR-7 pour piloter la visibilité dans le réseau des assistantes maternelles.
> - `Notification` (BIT, `NOT NULL`, default `1`) — drapeau de préférence pour la réception des notifications / emails marketing (newsletters, annonces produit). **Colonne à créer en base si absente** — mise à jour schéma **obligatoire avant** l'invocation de `dev-backend` (`ALTER TABLE [Employee] ADD [Notification] BIT NOT NULL DEFAULT 1;`).
>
> Toute incohérence schéma (colonne absente, type ≠ BIT, NULL toléré) → STOP DBA avant `dev-backend`. Source de vérité = DB existante (cf. `docs/principles/source-first.md`). Aucune migration DDL n'est introduite par le pipeline `dev-backend` lui-même — la création/ALTER de la colonne `Notification` est de la responsabilité du DBA / migration ops en amont du build. La suppression de compte (cf. SFD-12) effectue un `DELETE` physique sur la ligne `Employee` correspondante (et les dépendances cascadées par les FK existantes — cf. BR-13).

## Context

L'application Demo expose aujourd'hui un menu principal (cf. `spec-menu-principale` FEAT 5) qui dirige l'employée connectée vers les modules métiers (`/bebes`, `/rapports`, `/donnees`, `/contrats`, `/documentation`, `/contacts`). Il n'existe **aucune page de paramètres** centralisée où l'utilisatrice peut piloter ses préférences cross-FEAT : (a) sa **visibilité dans le réseau des assistantes maternelles** (consommée par `spec-reseau-assistantes` FEAT 19 BR-7 via `Employee.Disponible`) ne peut être modifiée nulle part dans l'UI actuelle ; (b) sa **préférence de réception d'emails marketing** (newsletters, annonces nouvelles fonctionnalités) n'est exposée nulle part ; (c) la **suppression physique de son compte** (RGPD — droit à l'effacement) n'a aucun point d'entrée utilisateur — la seule action possible aujourd'hui est de cesser d'utiliser l'application sans supprimer ses données ; (d) les **documents légaux** (CGU / Mentions légales, Politique de confidentialité, CGV) ne sont liés depuis aucune page.

Cette spec introduit une **page `/parametres`** accessible depuis un **nouvel item « Paramètres » ajouté au menu principal** (extension de FEAT 5 — cf. SFD-1). La page est organisée en **3 onglets** (« Mentions légales », « Onglet 2 », « Onglet 3 »). **Seul l'onglet 1 (« Mentions légales ») est fonctionnellement spécifié dans cette FEAT** — les onglets 2 et 3 sont **réservés pour des FEATs futures** et rendus en placeholder « Contenu à venir » (cf. SFD-3, AC-19).

L'**onglet 1** matérialise quatre sections empilées :
1. **Toggle « Être visible auprès des autres assistantes maternelles »** → drive `Employee.Disponible` via `PATCH /api/employees/me/preferences` déclenché **directement au changement de position** du switch (pas de bouton Enregistrer — cf. SFD-7, BR-3).
2. **Toggle « Recevoir des emails marketing »** → drive `Employee.Notification` via le même endpoint (cf. SFD-7, BR-3).
3. **Bloc « Documents »** : 3 liens cliquables (CGU / Mentions légales, Politique de confidentialité, Conditions générales de vente) qui ouvrent **provisoirement** `https://www.google.com` dans un nouvel onglet du navigateur — le contenu réel des URLs étant out of scope (cf. SFD-10, BR-7, AC-15, FEAT future).
4. **Bouton « Supprimer mon compte »** (texte rouge, plein largeur, sous le bloc documents) qui ouvre un **modal de confirmation** détaillant l'irrévocabilité de l'action (perte de tous les bébés, contrats, rapports, archives, image avatar) puis, après confirmation explicite, déclenche un `DELETE /api/employees/me` qui **supprime physiquement** la ligne `Employee` en base + ses dépendances cascadées (cf. SFD-12, BR-13). Après succès, la session est invalidée (token JWT effacé côté client, cookie de session purgé côté serveur si applicable) et l'utilisatrice est redirigée vers `/login` (cf. AC-13).

Le mockup `workspace/input/ui/20-1-Spec-Parametres.html` matérialise le rendu canonique de l'onglet 1 : topbar avec bouton retour + titre « Paramètres », barre d'onglets en tête (icône + libellé + soulignement coral pour l'onglet actif), corps scrollable avec 2 cards `.pref` (toggle pill 50×30 à droite, libellé en gras + paragraphe descriptif à gauche), section `Documents` avec 3 `.link-row` (chevron droit aligné à droite), pied avec uniquement le bouton « Supprimer mon compte » en rouge. **Note maquette** : le mockup inclut un libellé de version `v7.5.8 (309)` (élément `.meta__v`) qui **N'EST PAS** rendu par le code généré (cf. SFD-11, BR-9, AC-14) — il est conservé dans le mockup pour vestige visuel mais explicitement exclu du DOM canonique.

## Objective

L'employée connectée ouvre le menu principal et clique sur l'item « Paramètres » → la SPA navigue vers `/parametres` ; le frontend envoie un unique `GET /api/employees/me/preferences` qui retourne `{ disponible: bool, notification: bool }` (image brute des 2 colonnes pour l'employée identifiée par le token JWT). Le frontend rend la page complète : topbar (retour + titre), 3 onglets avec onglet 1 actif par défaut, corps scrollable contenant les 2 toggles (positions reflétant le payload), la section Documents avec 3 liens externes, et le bouton « Supprimer mon compte ». L'utilisatrice peut basculer librement entre les 3 onglets (les onglets 2 et 3 affichent un placeholder « Contenu à venir »). Sur **chaque changement de position d'un toggle**, le frontend envoie immédiatement un `PATCH /api/employees/me/preferences` contenant **uniquement** le champ modifié (`{ disponible: true }` ou `{ notification: false }`) — le backend exécute l'UPDATE ciblé en base et retourne `204 No Content` ; en cas d'échec réseau, le frontend remet le switch en position précédente et affiche un message d'erreur transitoire (cf. SFD-9, AC-9). Sur **clic « Supprimer mon compte »**, un modal de confirmation s'ouvre — confirmation explicite déclenche un `DELETE /api/employees/me` qui purge physiquement la ligne en base, invalide la session côté client, et redirige vers `/login` (cf. SFD-12, AC-13). Aucune autre action backend n'est déclenchée par cette page.

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps de chargement de la page paramètres (1 requête SQL `SELECT` sur 2 colonnes scope employée connectée) + latence de persistance d'un toggle (1 requête SQL `UPDATE` sur 1 colonne) + temps de purge physique du compte (1 requête `DELETE` + dépendances cascadées par FK existantes)
- Target: p95 chargement `GET /api/employees/me/preferences` < 200 ms sur 4G simulé (1 SELECT ciblé `WHERE EmployeeId = @session`, payload < 64 octets JSON) ; p95 rendu initial de la page après réception du payload < 50 ms côté frontend ; p95 `PATCH /api/employees/me/preferences` < 200 ms (1 UPDATE ciblé sur 1 ligne, 1 colonne BIT) ; p95 `DELETE /api/employees/me` < 800 ms (purge ligne + dépendances cascadées, dépend du volume de bébés / contrats / rapports de l'employée — borne supérieure tolérée à 2 s en cas de gros volume historique)
- Deadline: livraison stack `kotlin-spring-boot × react × shadcn` au 2026-10-15

## Non-Functional Constraints (v7.0.0)

- Expected volume: ~1-2 visites `/parametres` / employée / mois (page rarement consultée — préférences stables) ; ~1-3 toggles modifiés / employée / an (changement très rare) ; ~0 suppression de compte / employée (action terminale, par définition au plus 1 fois) ; trafic ajouté par cette FEAT < 0,1 KB / employée / mois ; nombre cumulé d'employées susceptibles d'utiliser cette page : ~100-500 sur l'horizon des 12 prochains mois (cohérent avec FEAT 19 / FEAT 17)
- Performance SLA: p95 chargement < 200 ms, p95 UPDATE < 200 ms, p95 DELETE < 800 ms (cf. Quantified Goal) ; aucun risque N+1 (1 SELECT plat sur 2 colonnes ; 1 UPDATE ciblé ; 1 DELETE qui peut cascader mais reste 1 ordre SQL à la racine)
- Data retention: la suppression de compte est **physique** (`DELETE`, pas soft-delete avec `IsDeleted=1`) — la ligne `Employee` et toutes ses dépendances (bébés, contrats, rapports, archives, image avatar sur disque `wwwroot/images/{employeeId}.png` — cf. FEAT 3 BR-15) sont supprimées de manière **irréversible** ; aucun archivage, aucun audit log conservé après purge (la trace de l'action elle-même n'est conservée que dans les logs techniques applicatifs, non scopés par utilisateur — RGPD conformity). Les fichiers statiques (image avatar) sont supprimés en best-effort côté serveur après le `DELETE` SQL (cf. SFD-13, BR-14)
- Compliance: **RGPD article 17 (droit à l'effacement)** — la suppression de compte est conforme à l'exigence d'effacement à la demande ; aucune information personnelle n'est conservée après purge ; le modal de confirmation explicite documente les conséquences (perte de toutes les données associées) ; aucune trace de l'employée supprimée n'est conservée dans les logs applicatifs scopés (les logs techniques anonymes — latence, code HTTP — restent en place). **RGPD article 21 (droit d'opposition au marketing)** — le toggle « Recevoir des emails marketing » expose un opt-out fonctionnel (passe `Notification` à `0` immédiatement, sans confirmation ni délai). Aucune donnée personnelle nouvelle n'est introduite par cette FEAT (seules deux colonnes BIT préexistantes sont exposées en R/W)
- Integration: nouvelle route SPA `/parametres` + 3 nouveaux endpoints backend (`GET /api/employees/me/preferences`, `PATCH /api/employees/me/preferences`, `DELETE /api/employees/me`) ; aucune dépendance externe ; aucun service tiers ; aucune notification ; aucun WebSocket / SSE ; les URLs des documents légaux (cf. SFD-10) sont **hardcodées à `https://www.google.com`** dans cette FEAT (placeholder volontaire — cf. BR-7) et seront remplacées par les URLs réelles dans une FEAT future hors scope
- Degraded mode: si `GET /api/employees/me/preferences` échoue (5xx, timeout), la page affiche un message d'erreur générique `Impossible de charger les paramètres.` avec bouton « Réessayer » (cf. SFD-14, AC-16) ; si `PATCH /api/employees/me/preferences` échoue, le frontend remet le toggle dans sa position précédente et affiche un toast `Modification non enregistrée. Réessayez.` (cf. SFD-9, AC-9, BR-4) ; si `DELETE /api/employees/me` échoue, le modal de confirmation reste affiché avec un message d'erreur générique `La suppression a échoué. Réessayez.` (cf. SFD-13, AC-13) ; aucun fallback offline ; aucun stockage local du payload

## Actors

- Employée connectée : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session (cf. `spec-connexion`). Seule autorisée à consulter et modifier ses propres paramètres (cf. BR-1, BR-2) ; aucun accès aux paramètres d'une autre employée n'est possible (le scoping est strictement basé sur le token JWT — l'endpoint n'accepte aucun `EmployeeId` en path / query / body, l'`EmployeeId` est **toujours résolu côté serveur depuis la session** — cf. BR-2). Seule autorisée à supprimer **son propre** compte (cf. SFD-12, BR-13).

## Functional Needs

### Point d'entrée et navigation

- SFD-1: La spec **étend `spec-menu-principale` (FEAT 5)** en ajoutant un **nouvel item « Paramètres »** dans la liste de navigation du panneau latéral (positionné après les items métiers et avant le bouton « Se déconnecter », ou en position arbitraire mais documentée — cf. AC-1). L'icône de l'item est une icône `settings` (engrenage) cohérente avec le design system du menu (SVG inliné OU `material-symbols-outlined` selon convention du stack actif — la FEAT n'impose pas le format, seule l'iconographie sémantique est requise : engrenage / cog / settings, 23×23 px, couleur `var(--nj-ink-700)` au repos, `var(--nj-coral-600)` actif). Un clic sur l'item déclenche une navigation SPA vers `/parametres` (cf. FEAT 5 BR-2) et ferme le menu (cf. FEAT 5 AC-6).
- SFD-2: La nouvelle route SPA `/parametres` est protégée par le middleware d'authentification global de l'application — une utilisatrice non authentifiée est redirigée vers `/login` (cf. `spec-connexion`, FEAT 5 BR-1).
- SFD-3: La page `/parametres` rend une topbar identique à celle du mockup `20-1-Spec-Parametres.html` : à gauche un bouton retour `.topbar__back` (40×40, background `var(--nj-surface)`, color `var(--nj-ink-700)`, border-radius `var(--nj-radius-md)`, ombre xs, icône SVG flèche gauche `<path d="M15 18 9 12l6-6"/>`) qui ramène à la page précédente via le mécanisme SPA (`history.back()` ou équivalent du router actif) ; immédiatement à droite du bouton retour, un titre `Paramètres` (font-size 18px, font-weight 800, letter-spacing -0.02em). Aucun autre élément dans la topbar.

### Barre d'onglets (3 onglets, onglet 1 actif par défaut)

- SFD-4: Sous la topbar, la page rend une barre d'onglets `.tabs` (background `var(--nj-surface)`, bordures top et bottom `1px solid var(--nj-line-soft)`, padding `0 6px`, layout `display: flex`) contenant **3 boutons d'onglet** dans l'ordre exact :
  1. **Onglet 1 — `Mentions légales`** (icône `gavel` material-symbols, `data-tab="legal"`) — actif par défaut au montage de la page (`is-active`).
  2. **Onglet 2 — `Onglet 2`** (icône `tune` material-symbols, `data-tab="onglet2"`) — libellé volontairement générique, **réservé pour spec future** ; contenu placeholder (cf. SFD-15).
  3. **Onglet 3 — `Onglet 3`** (icône `explore` material-symbols, `data-tab="onglet3"`) — libellé volontairement générique, **réservé pour spec future** ; contenu placeholder (cf. SFD-15).

  Chaque `.tabs__btn` rend un bloc vertical (icône 22px au-dessus, libellé 12,5px en gras dessous, `flex-direction: column`, `align-items: center`, `gap: 5px`). L'onglet actif a `color: var(--nj-coral-700)` et un soulignement bas `::after` (3px de hauteur, `var(--nj-coral-500)`, border-radius top 3px). Un clic sur un bouton d'onglet (a) retire la classe `is-active` du bouton précédent, (b) ajoute `is-active` au bouton cliqué, (c) bascule l'affichage des panneaux `.panel[data-panel="{key}"]` correspondants (le panneau matchant prend `is-active`, les autres la perdent). Aucune navigation SPA, aucun changement d'URL — le switch d'onglet est purement local au composant `ParametresPage` (cf. SFD-5).
- SFD-5: L'état actif de l'onglet courant **n'est pas persisté** dans l'URL (pas de query param `?tab=legal`), ni dans le sessionStorage / localStorage (cf. BR-15). Au prochain montage de `/parametres`, l'onglet 1 (`Mentions légales`) est systématiquement actif par défaut. Cette décision intentionnelle (pas de deep-linking par onglet) est justifiée par le faible nombre d'onglets fonctionnels (1 sur 3 dans cette FEAT) et l'absence de cas d'usage de partage URL ciblé sur un onglet.

### Schéma de données — table `dbo.Employee` (R/W ciblé sur 2 colonnes)

- SFD-6: La spec lit et écrit **exclusivement** les 2 colonnes suivantes de la table préexistante `dbo.Employee` (cf. FEAT 3) — toutes les autres colonnes (`Nom`, `Prenom`, `Email`, `Telephone`, `Image`, etc.) restent intactes :

  | Colonne | Type SQL | Nullable | Default | Description |
  |---|---|---|---|---|
  | `Disponible` | `BIT` | `NOT NULL` | `1` | Drapeau de visibilité dans le réseau des assistantes maternelles. `1` = visible (apparaît dans `GET /api/reseau-assistantes` — cf. FEAT 19 BR-7) ; `0` = caché (exclu du payload de FEAT 19). **Déjà consommé** par FEAT 19, **modifié pour la première fois côté UI** par cette FEAT |
  | `Notification` | `BIT` | `NOT NULL` | `1` | Drapeau de préférence emails marketing (newsletters, annonces produit). `1` = recevoir ; `0` = opt-out. **Non consommé dans le code applicatif actuel** (l'envoi de newsletters relève d'un système externe out of scope) — la valeur est **lue et persistée par cette FEAT** pour respecter la préférence utilisatrice ; la consommation effective par le système d'envoi de mails est out of scope (cf. BR-6) |

  Aucune autre colonne n'est ajoutée par cette FEAT. La création des deux colonnes (si absentes en base au moment du build) relève d'une migration ops dédiée hors scope — la FEAT assume leur présence et émet un STOP DBA dans le cas contraire (cf. Pré-requis schéma). La FEAT **supprime** physiquement la ligne `Employee` complète sur action utilisatrice (cf. SFD-12, BR-13) — cette suppression cascade selon les FK existantes en base sur les tables filles (`Bebe`, `Contrat`, `Rapport`, `Archive`, etc.) ; le détail des cascades est **assumé géré par les contraintes FK ON DELETE CASCADE préexistantes** (cf. Pré-requis schéma — si des FK sans cascade existent, le `DELETE` retournera une erreur SQL `547 REFERENCE constraint conflict` et la suppression sera rollback, ce qui est un état détectable et corrigible par l'ops).

### Endpoint backend — `GET /api/employees/me/preferences` (lecture)

- SFD-7: Nouvel endpoint backend `GET /api/employees/me/preferences` (verbe GET, route en kebab-case singulier `preferences`, segment `me` désignant l'employée connectée, **pas de path param `EmployeeId`** — l'`EmployeeId` est résolu côté serveur depuis le token JWT — cf. BR-2). La requête SQL canonique exécutée par le backend est **strictement** :
  ```sql
  SELECT [Disponible], [Notification]
  FROM [Employee]
  WHERE [EmployeeId] = @SessionEmployeeId;
  ```
  - `@SessionEmployeeId` est **toujours** résolu côté serveur depuis le token JWT (cf. BR-2) — jamais lu depuis un input client.
  - Aucun JOIN (la requête est strictement scopée à 1 ligne sur 2 colonnes).
  - Aucune transformation, aucun filtrage applicatif au-delà du `WHERE` — le payload est l'image brute des 2 colonnes pour la ligne `Employee` correspondante.
  - La requête est **paramétrée** (`@SessionEmployeeId`) — anti-injection SQL trivial (cf. BR-3).

  La réponse JSON est de la forme :
  ```json
  {
    "disponible": true,
    "notification": false
  }
  ```
  - Les clés JSON sont **camelCase** (`disponible`, `notification`) — cf. BR-5.
  - Les valeurs sont des `boolean` JSON natifs (`true` / `false`), **jamais** des entiers `1` / `0` ou des strings `"true"` / `"false"` (le mapping BIT SQL → boolean JSON est de la responsabilité du serializer du stack actif — cf. `library-and-stack.md §6.bis.3`).
  - Le payload **n'inclut aucune métadonnée d'enveloppe** (pas de `{ data: {...} }`, pas de `{ employee: { id: ..., preferences: {...} } }`) — c'est un objet plat à la racine.
  - Si l'employée connectée n'existe plus en base (cas-limite improbable mais théorique : compte supprimé entre l'émission du token et la requête), le backend retourne `404 Not Found` et le frontend redirige vers `/login` (cf. BR-1, AC-16).

### Endpoint backend — `PATCH /api/employees/me/preferences` (mise à jour incrémentale)

- SFD-8: Nouvel endpoint backend `PATCH /api/employees/me/preferences` (verbe PATCH, route identique à SFD-7, **pas de path param `EmployeeId`** — résolu côté serveur — cf. BR-2). Le body de la requête est un objet JSON contenant **un OU plusieurs** des deux champs booléens définis dans le payload de SFD-7 :
  ```json
  { "disponible": false }
  ```
  ou
  ```json
  { "notification": true }
  ```
  ou
  ```json
  { "disponible": true, "notification": false }
  ```
  - Le body est **forcément** un objet JSON valide ; tout autre format (`null`, array, string brute, body vide) retourne `400 Bad Request` (cf. BR-4).
  - Si **aucun** des deux champs reconnus n'est présent dans le body (ex. body `{ "autreChamp": true }`), le backend retourne `400 Bad Request` avec un libellé générique (cf. BR-4, AC-10).
  - Les champs non listés dans le body ne sont **pas modifiés** en base (sémantique PATCH stricte — cf. BR-3) ; le frontend envoie systématiquement **uniquement le champ qui a changé** lors d'un clic sur un toggle (cf. SFD-9).

  La requête SQL canonique exécutée par le backend dépend des champs présents dans le body — elle est **dynamiquement construite** mais **toujours paramétrée** (cf. BR-3) :
  ```sql
  -- Si body = { "disponible": <bool> }
  UPDATE [Employee]
  SET [Disponible] = @Disponible
  WHERE [EmployeeId] = @SessionEmployeeId;

  -- Si body = { "notification": <bool> }
  UPDATE [Employee]
  SET [Notification] = @Notification
  WHERE [EmployeeId] = @SessionEmployeeId;

  -- Si body = { "disponible": <bool>, "notification": <bool> }
  UPDATE [Employee]
  SET [Disponible] = @Disponible, [Notification] = @Notification
  WHERE [EmployeeId] = @SessionEmployeeId;
  ```
  - Le mapping `champ JSON ↔ colonne SQL` est **fixe et statique** (allowlist `{ disponible: "Disponible", notification: "Notification" }`) — aucune génération dynamique du nom de colonne à partir d'un input client (cf. BR-3, anti-injection structurelle).
  - Réponse en cas de succès : `204 No Content` (pas de body) — le frontend ne re-fetch pas après PATCH, il garde son state local synchronisé avec l'action utilisatrice (cf. SFD-9, BR-4).
  - Réponse en cas d'`EmployeeId` introuvable en base : `404 Not Found` (cas-limite identique à SFD-7).

### Comportement frontend des toggles — persistance directe sans bouton Enregistrer

- SFD-9: Chaque toggle (`.switch[data-switch]`) déclenche, **à chaque clic / changement de position**, le flux suivant côté frontend (pas de debounce, pas de batch — action immédiate) :
  1. **Mise à jour optimiste du state local React (ou équivalent stack)** : la position visuelle du switch bascule immédiatement (`is-on` toggle), `aria-checked` est mis à jour.
  2. **Envoi du PATCH** : `fetch('/api/employees/me/preferences', { method: 'PATCH', body: JSON.stringify({ [champ]: nouvelleValeur }) })` avec **uniquement** le champ qui a changé.
  3. **Sur succès (`204 No Content`)** : aucune action visible (le switch reste dans sa nouvelle position, le state local React reflète la valeur persistée) ; optionnellement, un feedback discret (toast court de type « Enregistré », ≤ 2 s) peut être affiché — non requis par cette FEAT (cf. BR-4).
  4. **Sur échec (4xx, 5xx, timeout réseau)** : (a) la position visuelle du switch est **remise dans son état précédent** (rollback optimistique), (b) un toast d'erreur transitoire `Modification non enregistrée. Réessayez.` est affiché ≤ 4 s (cf. AC-9, BR-4).

  Aucun bouton « Enregistrer » n'est rendu sur la page (cf. AC-7) — la décision intentionnelle (persistance directe au clic) est justifiée par la rareté des modifications (cf. NFC volume) et l'absence de risque utilisateur (un toggle erroné est trivialement réversible par un second clic).

### Section « Documents » — 3 liens externes placeholder

- SFD-10: Sous les 2 cards `.pref`, la page rend une étiquette de section `.section-label` au texte `Documents` (font-family `var(--nj-font-mono)`, font-size 11px, letter-spacing 0.12em, text-transform uppercase, color `var(--nj-ink-400)`, font-weight 600, margin top 18px / bottom 10px). Sous cette étiquette, un conteneur `.links` (`display: flex; flex-direction: column; gap: 10px`) contient **exactement 3** éléments `.link-row` dans l'ordre :
  1. **`CGU / Mentions légales`** → ouvre `https://www.google.com` dans un nouvel onglet.
  2. **`Politique de confidentialité`** → ouvre `https://www.google.com` dans un nouvel onglet.
  3. **`Conditions générales de vente`** → ouvre `https://www.google.com` dans un nouvel onglet.

  Chaque `.link-row` est un `<a class="link-row" href="https://www.google.com" target="_blank" rel="noopener noreferrer">` (cf. BR-8) contenant : (a) le libellé textuel à gauche (font-size 14,5px, font-weight 600, color `var(--nj-ink-900)`) ; (b) un chevron droit SVG aligné à droite (`<path d="M9 18l6-6-6-6"/>`, color `var(--nj-ink-400)`, 18×18). Hover : background `var(--nj-coral-50)`. Active : `transform: scale(0.99)`.

  **URL provisoire `https://www.google.com`** (cf. BR-7) : cette FEAT ne définit **pas** le contenu réel des documents légaux (rédaction CGU / Politique / CGV out of scope) — les trois URLs sont **temporaires** et démontrent uniquement le mécanisme d'ouverture en nouvel onglet. Une FEAT future hors scope remplacera les URLs par les valeurs réelles (texte hébergé sur le site Demo, page CMS, PDF statique, etc.).

### Pied de page — Bouton « Supprimer mon compte » (sans libellé de version)

- SFD-11: Sous la section Documents, la page rend une zone `.meta` (`text-align: center; padding: 18px 0 6px`) contenant **uniquement** un bouton plein largeur `.meta__del` au texte `Supprimer mon compte` (font-size 13px, font-weight 700, color `var(--nj-danger)`, background transparent, border 0, cursor pointer, `display: block`, `width: 100%`, margin-top 12px). Un clic ouvre le modal de confirmation (cf. SFD-12).

  **Le libellé de version `v7.5.8 (309)` (élément `.meta__v`) visible dans le mockup `20-1-Spec-Parametres.html` N'EST PAS rendu par le code généré** (cf. AC-14, BR-9). Le mockup conserve l'élément pour vestige visuel (vague historique d'une version antérieure du design) mais la FEAT exclut **explicitement** la version de la spec — la décision est documentée comme intentionnelle (la version du produit n'est pas pertinente pour l'utilisatrice finale dans le contexte de cette page et risquerait de créer de la confusion / friction support).

### Suppression de compte — modal de confirmation + DELETE physique

- SFD-12: Un clic sur le bouton « Supprimer mon compte » (cf. SFD-11) ouvre **immédiatement** un modal de confirmation centré (overlay backdrop semi-opaque `rgba(0,0,0,0.4)` couvrant la page, modal centré, max-width 320px en mobile, background `var(--nj-surface)`, border-radius `var(--nj-radius-lg)`, padding 24px, ombre lg). Le modal contient :
  1. **Titre** : `Supprimer définitivement votre compte ?` (font-size 17px, font-weight 800, color `var(--nj-ink-900)`, margin-bottom 12px).
  2. **Corps explicatif** : paragraphe en français détaillant les conséquences (texte canonique à respecter — peut être légèrement adapté typographiquement mais le contenu sémantique est obligatoire) :
     ```
     Cette action est irréversible.
     En supprimant votre compte, vous perdrez définitivement :
     • tous les bébés enregistrés et leurs informations,
     • tous les contrats en cours et archivés,
     • tous les rapports rédigés et archivés,
     • toutes les archives (arrivées / départs, rendez-vous, statuts),
     • votre photo de profil et vos informations personnelles.

     Aucune restauration n'est possible. Êtes-vous sûre de vouloir supprimer votre compte ?
     ```
  3. **Bouton « Annuler »** (à gauche dans une rangée flex) — background `var(--nj-surface)`, border `1px solid var(--nj-line)`, color `var(--nj-ink-700)`, text `Annuler`, font-weight 600 — clic ferme le modal sans action.
  4. **Bouton « Supprimer mon compte »** (à droite dans une rangée flex) — background `var(--nj-danger)`, color `#fff`, text `Supprimer mon compte`, font-weight 700 — clic déclenche le flux de suppression (cf. SFD-13).

  Le modal est **bloquant** : aucune interaction avec la page sous-jacente n'est possible tant qu'il est ouvert. Un clic sur le backdrop overlay ferme le modal (équivalent du bouton Annuler). La touche `Escape` ferme également le modal (accessibilité — cf. AC-12).
- SFD-13: Un clic sur le bouton **« Supprimer mon compte »** **du modal** (pas celui de la page) déclenche le flux backend :
  1. **Envoi** : `fetch('/api/employees/me', { method: 'DELETE' })` — endpoint dédié `DELETE /api/employees/me` (verbe DELETE, route avec segment `me` — l'`EmployeeId` est résolu côté serveur depuis le token JWT, cf. BR-2). Aucun body, aucun path param, aucun query param.
  2. **Backend** : exécute **une seule** requête SQL canonique paramétrée :
     ```sql
     DELETE FROM [Employee] WHERE [EmployeeId] = @SessionEmployeeId;
     ```
     Les FK `ON DELETE CASCADE` préexistantes sur les tables filles (`Bebe`, `Contrat`, `Rapport`, `Archive`, etc. — cf. Pré-requis schéma) propagent la suppression automatiquement. Le backend exécute également (best-effort) la suppression du fichier statique `wwwroot/images/{@SessionEmployeeId}.png` (cf. FEAT 3 BR-15 — l'image avatar de l'employée) ; un échec de la suppression du fichier ne fait **pas** échouer la transaction SQL (best-effort log WARN, cf. BR-14).
  3. **Sur succès (`204 No Content`)** : le frontend (a) ferme le modal, (b) purge le token JWT côté client (localStorage / cookie selon stack), (c) redirige vers `/login` via navigation SPA (`router.replace('/login')`) — l'utilisatrice voit la page de connexion vide (cf. AC-13).
  4. **Sur échec (4xx, 5xx, timeout réseau)** : le modal **reste ouvert** ; un message d'erreur générique `La suppression a échoué. Réessayez.` est affiché sous le corps explicatif (en rouge, font-size 13px, color `var(--nj-danger)`) ; les deux boutons restent actifs (l'utilisatrice peut annuler ou retenter). Aucune information technique n'est exposée (cf. BR-10).

  L'action n'est **jamais** annulable côté serveur après réception du `DELETE` — il n'y a pas de soft-delete, pas de période de grâce, pas de undo (cf. BR-13, NFC Data retention). Le modal est l'unique safeguard.

### États de chargement, vide, erreur

- SFD-14: Pendant le chargement initial (`GET /api/employees/me/preferences` en cours), la zone scrollable rend une version **désactivée** des 2 cards `.pref` : les deux toggles sont rendus en position « off » désaturée (background `var(--nj-ink-200)`, opacité 0.5) et sont **non cliquables** (`pointer-events: none`) ; les libellés et descriptions sont rendus normalement (le squelette ne masque que les contrôles interactifs). La section Documents et le bouton de suppression de compte sont **également rendus mais désactivés** (les liens ne sont pas cliquables, le bouton n'ouvre pas le modal) pour éviter toute action avant chargement complet. Si le `GET` échoue (5xx, timeout), la zone scrollable affiche un message d'erreur générique pleine largeur `Impossible de charger les paramètres. <button>Réessayer</button>` (style : texte centré `var(--nj-ink-500)`, bouton coral cliquable qui re-déclenche le GET — cf. AC-16, BR-10).
- SFD-15: Les **onglets 2 et 3** (`Onglet 2`, `Onglet 3`) rendent chacun un panneau `.panel[data-panel="onglet2|onglet3"]` contenant :
  1. Un en-tête `.panel__head` : eyebrow `À définir` (font-mono, uppercase, color `var(--nj-coral-600)`), titre H2 `Onglet 2` / `Onglet 3` (font-size 21px, font-weight 800), paragraphe `Le contenu de cet onglet sera précisé dans une prochaine spécification.` (font-size 13px, color `var(--nj-ink-500)`).
  2. Un placeholder visuel `.placeholder` : encart dashed (border 1.5px dashed `var(--nj-line)`, border-radius `var(--nj-radius-lg)`, padding 40×24, text-align center) contenant (a) une icône ronde `.placeholder__ic` (60×60, background `var(--nj-sky-50)`, color `var(--nj-sky-700)`, border-radius 999px) avec un glyphe matérial (`tune` pour onglet 2, `explore` pour onglet 3), (b) un libellé `<b>Contenu à venir</b>` (font-size 16px, color `var(--nj-ink-900)`), (c) un sous-texte `Cet onglet est réservé pour de futurs paramètres.` (font-size 13px, max-width 250px).

  Aucune logique applicative dans ces onglets — pas de fetch, pas de state, pas d'interaction au-delà du switch d'onglet. Ces deux onglets sont **purement décoratifs / réservés** dans cette FEAT et seront spécifiés par des FEATs futures (cf. Out of Scope).

## Business Rules

- BR-1: tous les endpoints `GET /api/employees/me/preferences`, `PATCH /api/employees/me/preferences`, `DELETE /api/employees/me` sont protégés par le middleware d'authentification global de l'application ; une requête sans token JWT valide retourne `401 Unauthorized` et le frontend redirige vers `/login` (comportement standard du client HTTP de l'app — cf. `spec-connexion`).
- BR-2: les trois endpoints **ignorent systématiquement** tout `EmployeeId` reçu en input client (path, query, body) — l'`EmployeeId` est **toujours** résolu côté serveur depuis le token JWT en session (`@SessionEmployeeId`). Aucune employée ne peut consulter, modifier ou supprimer les préférences ou le compte d'une autre. Cette règle est **load-bearing** (cf. FEAT 3 BR-8 sur le même pattern pour `UPDATE Employee` — anti-IDOR).
- BR-3: toutes les requêtes SQL sont **paramétrées** (`@SessionEmployeeId`, `@Disponible`, `@Notification`) — aucune concaténation de chaîne, aucune interpolation de variables non échappées. Le mapping `champ JSON ↔ colonne SQL` (`disponible → Disponible`, `notification → Notification`) est une **allowlist statique fixe** — aucune génération dynamique du nom de colonne à partir d'un input client (anti-injection structurelle).
- BR-4: l'endpoint `PATCH /api/employees/me/preferences` rejette tout body invalide avec `400 Bad Request` : body absent, body non-JSON, body `null`, body array, body objet vide `{}`, body objet sans aucun des deux champs reconnus (`disponible`, `notification`). Les valeurs des champs reconnus doivent être de type `boolean` strict (`true` / `false`) — un type autre (`1`, `"true"`, `null`) retourne également `400`.
- BR-5: les champs JSON renvoyés et reçus par les endpoints sont sérialisés en **camelCase** : `disponible`, `notification` (cf. `rules/library-and-stack.md §6.bis.3`). Le mapping BIT SQL → boolean JSON est de la responsabilité du serializer du stack actif — la valeur retournée est `true` / `false` natifs, jamais `1` / `0` ou strings.
- BR-6: la persistance de `Notification` n'a **aucun impact visible** dans l'application actuelle (aucun système d'envoi de mails n'est branché côté backend dans cette FEAT) — la valeur est lue et écrite pour respecter la préférence utilisatrice et pour préparer une consommation future par un système d'envoi externe (out of scope). Cette absence d'impact immédiat est **intentionnelle** et **doit être documentée** dans la description du toggle (`Newsletters et annonces des nouvelles fonctionnalités de Demo.` — cf. mockup ligne 182).
- BR-7: les 3 URLs de la section Documents (cf. SFD-10) sont **hardcodées à `https://www.google.com`** dans cette FEAT — c'est un placeholder volontaire pour démontrer le mécanisme d'ouverture en nouvel onglet. Une FEAT future hors scope remplacera ces URLs par les valeurs réelles. L'éventuelle externalisation de ces URLs dans une table de configuration (`dbo.Documentation` de FEAT 17 OU table dédiée) relève de cette FEAT future — la décision de stockage est out of scope.
- BR-8: les liens `.link-row` ouvrent l'URL dans un **nouvel onglet** via `<a href="..." target="_blank" rel="noopener noreferrer">`. Les deux attributs `noopener` ET `noreferrer` sont obligatoires (`noopener` pour la sécurité du `window.opener`, `noreferrer` parce que les URLs cibles sont externes à Demo et la coupure du referer est un choix de prudence par défaut sur ces liens documentaires publics).
- BR-9: le libellé de version du produit (`v7.5.8 (309)` dans le mockup) **n'est PAS rendu** dans le DOM canonique généré (cf. SFD-11, AC-14) — aucune classe `.meta__v` ou équivalent n'est présente dans le composant frontend. Cette exclusion est **explicite** et **intentionnelle** (la version du produit n'est pas pertinente pour l'utilisatrice finale sur cette page).
- BR-10: aucune information technique (stack trace, exception SQL, nom de colonne brut, code HTTP) n'est exposée dans les messages d'erreur côté frontend ; les libellés sont des labels statiques en français (`Impossible de charger les paramètres.`, `Modification non enregistrée. Réessayez.`, `La suppression a échoué. Réessayez.`) — cohérent avec la stratégie des autres FEATs (cf. FEAT 17 BR-11, FEAT 15 BR-15).
- BR-11: la persistance des toggles via PATCH est **incrémentale** : le frontend envoie **uniquement** le champ qui vient de changer (`{ disponible: <bool> }` OU `{ notification: <bool> }` — jamais les deux en même temps dans le flux nominal), ce qui minimise la bande passante et la surface d'écrasement concurrent (deux toggles modifiés en parallèle dans deux onglets navigateur ne s'écraseront pas mutuellement).
- BR-12: le rollback optimistique des toggles côté frontend (cf. SFD-9 étape 4) est **purement visuel** — la valeur en base reflète soit l'ancienne valeur (si l'UPDATE n'a pas eu lieu) soit la nouvelle (si l'UPDATE a réussi mais le client n'a pas reçu la réponse). En cas d'incertitude (timeout), le frontend remet le switch en position précédente ET affiche le toast d'erreur — l'utilisatrice peut soit retenter (nouveau clic) soit naviguer ailleurs et revenir (le `GET` au prochain mount affichera la vérité serveur).
- BR-13: la suppression de compte est **physique et irréversible** — `DELETE FROM Employee WHERE EmployeeId = @SessionEmployeeId` cascade selon les FK existantes (cf. Pré-requis schéma) ; aucun soft-delete, aucun champ `IsDeleted`, aucune table d'archive ; le compte et toutes ses dépendances sont purgés. Cette décision est conforme RGPD art. 17 (droit à l'effacement). Le modal de confirmation (cf. SFD-12) est l'**unique** safeguard côté utilisateur — il n'y a ni période de grâce serveur, ni undo.
- BR-14: la suppression du fichier statique avatar (`wwwroot/images/{employeeId}.png` — cf. FEAT 3 BR-15) est exécutée en **best-effort** après le `DELETE` SQL — un échec de la suppression du fichier (permission denied, fichier déjà absent, FS read-only) est loggé en WARN serveur mais ne fait **pas** échouer la requête `DELETE /api/employees/me` qui retourne `204 No Content` quand même. L'orphelin fichier sur disque est tolérable (pas d'information sensible — c'est juste une image PNG sans lien identifiable avec l'employée supprimée puisque sa ligne `Employee` n'existe plus). Un script de nettoyage périodique des images orphelines relève d'un job d'ops out of scope.
- BR-15: aucun cookie, header de session, state local persistant (`localStorage`, `sessionStorage`, IndexedDB) n'est introduit par cette FEAT — la page est entièrement stateless côté client (cf. AC-18). L'onglet actif courant n'est pas persisté (cf. SFD-5). L'état des toggles vit dans le state local React (ou équivalent stack) et est rechargé à chaque visite via le `GET`.
- BR-16: aucune validation cliente sur les valeurs des toggles (`disponible`, `notification`) — les deux booléens acceptent indépendamment `true` ou `false` sans contrainte croisée (l'utilisatrice peut être visible et opt-out marketing, ou cachée et opt-in marketing, ou toute combinaison). La spec ne définit **aucune** règle métier qui forcerait une cohérence entre les deux drapeaux.
- BR-17: si le design system actif (shadcn / Vuetify / Radzen) fournit un composant `Switch` natif ET un composant `Dialog` / `Modal` natif, ils **DOIVENT** être utilisés en priorité avec override de tokens — le CSS isolé ne complète que pour la fidélité visuelle (cf. `rules/quality.md §B`).
- BR-18: le modal de confirmation de suppression de compte (cf. SFD-12) doit être **focus-trapped** (le focus clavier reste piégé dans le modal tant qu'il est ouvert) et **dismissible au clavier** (touche `Escape` = équivalent du bouton Annuler) — accessibilité WCAG 2.1 §2.1.2 « No Keyboard Trap » + §2.4.3 « Focus Order ». Le composant `Dialog` natif du DS actif gère typiquement ces aspects.

## Acceptance Criteria

- AC-1: le menu principal (`spec-menu-principale` FEAT 5) contient un nouvel item « Paramètres » avec une icône engrenage / settings cohérente avec le DS actif, positionné dans la liste de navigation principale après les items métiers et avant le bouton « Se déconnecter » (ou en position arbitraire mais documentée dans le plan dev-frontend) ; un clic sur cet item déclenche une navigation SPA vers `/parametres` et ferme le panneau latéral (héritage FEAT 5 AC-5 + AC-6).
- AC-2: la route `/parametres` est protégée — une utilisatrice non authentifiée est redirigée vers `/login` (héritage FEAT 5 BR-1).
- AC-3: au chargement initial, la page envoie **une seule** requête `GET /api/employees/me/preferences` qui retourne `{ disponible: bool, notification: bool }` ; aucune requête additionnelle (telemetry, prefetch, feature flags) n'est émise (vérifiable Network DevTools — anti N+1).
- AC-4: la requête SQL exécutée par le backend pour le GET est **strictement** `SELECT [Disponible], [Notification] FROM [Employee] WHERE [EmployeeId] = @SessionEmployeeId` ; aucun JOIN, aucun WHERE supplémentaire, aucun GROUP BY (vérifiable par log SQL ou test d'intégration).
- AC-5: le payload du GET est sérialisé en **camelCase** (`disponible`, `notification`) avec valeurs `boolean` natifs ; aucune clé en PascalCase ou snake_case, aucune valeur entière `1` / `0` ou string `"true"` / `"false"` (vérifiable par test d'intégration JSON).
- AC-6: la page rend une topbar avec bouton retour à gauche + titre « Paramètres », puis une barre de 3 onglets (« Mentions légales » actif par défaut, « Onglet 2 », « Onglet 3 ») ; un clic sur un onglet bascule la classe `is-active` localement sans navigation SPA, sans changement d'URL, sans appel réseau (vérifiable manuellement + Network DevTools).
- AC-7: la page **ne contient aucun bouton « Enregistrer »** — les toggles persistent leur valeur via PATCH immédiatement au changement de position (vérifiable par grep DOM : `document.querySelectorAll('button')` n'inclut **aucun** bouton au texte `Enregistrer` / `Save` / équivalent dans l'onglet 1).
- AC-8: un clic sur le toggle « Être visible auprès des autres assistantes maternelles » déclenche immédiatement `PATCH /api/employees/me/preferences` avec body `{ "disponible": <nouvelleValeur> }` ; un clic sur le toggle « Recevoir des emails marketing » déclenche `PATCH ... { "notification": <nouvelleValeur> }` ; chaque PATCH contient **exactement un seul** des deux champs (jamais les deux ensemble dans le flux nominal — vérifiable par fixture E2E Playwright capturant les requêtes Network).
- AC-9: si le PATCH échoue (4xx, 5xx, timeout réseau), le toggle est **remis en position précédente** (rollback optimistique visible à l'œil), et un toast d'erreur transitoire `Modification non enregistrée. Réessayez.` est affiché ≤ 4 s ; aucune trace technique n'est exposée (vérifiable par fixture qui mock le PATCH en `500 Internal Server Error`).
- AC-10: un PATCH avec body invalide (vide, sans champ reconnu, type non-boolean) retourne `400 Bad Request` côté backend ; aucune modification n'est appliquée en base (vérifiable par test d'intégration `PATCH /api/employees/me/preferences` avec body `{ "autreChamp": true }` → `400` ; `SELECT` post-test confirme valeurs inchangées).
- AC-11: la section « Documents » rend exactement 3 `<a class="link-row">` dans l'ordre `CGU / Mentions légales`, `Politique de confidentialité`, `Conditions générales de vente` ; chaque lien a `href="https://www.google.com"`, `target="_blank"`, `rel="noopener noreferrer"` ; un clic ouvre `https://www.google.com` dans un nouvel onglet du navigateur (vérifiable manuellement + DOM query : `Array.from(document.querySelectorAll('a.link-row')).every(a => a.href === 'https://www.google.com/' && a.target === '_blank' && a.rel.includes('noopener') && a.rel.includes('noreferrer'))`).
- AC-12: un clic sur le bouton « Supprimer mon compte » ouvre un modal centré avec backdrop semi-opaque, titre `Supprimer définitivement votre compte ?`, corps explicatif listant les conséquences (bébés, contrats, rapports, archives, image avatar, informations personnelles), boutons « Annuler » + « Supprimer mon compte » ; un clic sur le backdrop OU sur le bouton « Annuler » OU la touche `Escape` ferme le modal sans action ; le focus clavier reste piégé dans le modal tant qu'il est ouvert (vérifiable par fixture E2E Playwright + accessibility audit).
- AC-13: un clic sur le bouton « Supprimer mon compte » **du modal** déclenche `DELETE /api/employees/me` ; sur succès `204 No Content`, le modal se ferme, le token JWT est purgé côté client, et l'utilisatrice est redirigée vers `/login` via navigation SPA (`router.replace`) ; sur échec, le modal reste ouvert avec message d'erreur générique `La suppression a échoué. Réessayez.` (vérifiable par fixture E2E + test d'intégration backend).
- AC-14: le libellé de version du produit `v7.5.8 (309)` (élément `.meta__v` du mockup) **n'est pas rendu** dans le DOM canonique généré ; aucun `<span class="meta__v">` ou équivalent n'est présent dans le composant frontend (vérifiable par grep DOM : `document.querySelector('.meta__v') === null` + grep source code : aucune occurrence du pattern `v\d+\.\d+\.\d+` dans le rendu de la page paramètres).
- AC-15: les 3 URLs des liens documentaires sont **toutes** égales à la valeur littérale `https://www.google.com` (placeholder volontaire de cette FEAT — cf. BR-7) ; aucune URL ne pointe vers une page interne Demo ni vers une URL « réelle » de CGU / Politique / CGV (vérifiable par grep source code : recherche `'CGU'` ou `'Politique'` ou `'Conditions'` dans le composant frontend → toutes les `href` correspondantes valent `'https://www.google.com'`).
- AC-16: si le `GET /api/employees/me/preferences` échoue (5xx, timeout réseau, `404 Not Found`), la page affiche `Impossible de charger les paramètres.` avec un bouton `Réessayer` qui re-déclenche le GET ; les 2 toggles + section Documents + bouton suppression restent dans l'état désactivé tant que le GET n'a pas réussi (vérifiable par fixture E2E + test d'intégration mock 5xx).
- AC-17: la requête SQL exécutée par le backend pour le PATCH est **dynamique mais paramétrée** — le UPDATE inclut uniquement les colonnes présentes dans le body, et utilise des paramètres préparés (`@Disponible`, `@Notification`, `@SessionEmployeeId`) ; aucune concaténation de string SQL avec un input client (vérifiable par revue code-reviewer + test de pénétration tentant `PATCH { "disponible": true; DROP TABLE Employee; --": true }`).
- AC-18: aucun nouveau cookie, header de session, state local persistant (`localStorage`, `sessionStorage`, IndexedDB) n'est introduit par cette FEAT — l'état de la page est purement dérivé du payload courant et de l'état React local (vérifiable DevTools Application).
- AC-19: les onglets 2 et 3 rendent **uniquement** un placeholder (en-tête `À définir` + titre + paragraphe générique + encart dashed avec icône, libellé « Contenu à venir », sous-texte) ; aucune logique applicative, aucun fetch, aucun state interactif au-delà du switch d'onglet (vérifiable par grep source code : les composants `Onglet2Panel` / `Onglet3Panel` n'importent aucun service / hook fetch / store).
- AC-20: le rendu de la page paramètres utilise **exclusivement** des tokens CSS (`var(--nj-coral-500)`, `var(--nj-coral-700)`, `var(--nj-ink-700)`, `var(--nj-ink-900)`, `var(--nj-ink-500)`, `var(--nj-ink-400)`, `var(--nj-ink-300)`, `var(--nj-surface)`, `var(--nj-cream)`, `var(--nj-line)`, `var(--nj-line-soft)`, `var(--nj-success)`, `var(--nj-danger)`, `var(--nj-sky-50)`, `var(--nj-sky-700)`, `var(--nj-radius-lg)`, `var(--nj-radius-md)`, `var(--nj-shadow-xs)`, `var(--nj-font-sans)`, `var(--nj-font-mono)`, `var(--nj-dur-fast)`, `var(--nj-ease)`) — aucun hex hardcodé dans les composants (cf. `rules/quality.md §B.5`, vérifiable par grep `#[0-9a-fA-F]{3,8}` post-build).
- AC-21: aucune nouvelle dépendance **npm / NuGet / Maven** n'est introduite par cette FEAT — les composants Switch et Dialog / Modal du DS actif (shadcn / Vuetify / Radzen) couvrent tous les besoins (cf. BR-17) ; le client HTTP est celui déjà existant (cf. FEAT 11 / FEAT 15 / FEAT 17) ; aucune librairie de gestion de toasts spécifique n'est introduite si le DS en fournit une native (sinon, fallback inline acceptable). Vérifiable côté CI : aucun diff sur `package.json` / `.libs.json` du stack frontend autre que les usages déjà déclarés.
- AC-22: **wiring backend non contournable** — les handlers des routes HTTP `GET`, `PATCH`, `DELETE /api/employees/me[/preferences]` invoquent **directement** un service `employeePreferencesService` / `employeeAccountService` (ou équivalent stack — `EmployeePreferencesService` côté Spring/.NET, `employee_preferences_service` côté FastAPI). Vérifiable par : (a) tests d'intégration HTTP pour les 3 verbes ; (b) grep statique sur les handlers — appel au service dans le même chemin d'exécution que la sérialisation/persistance ; (c) tout fichier `services/employeePreferences*.{js,ts,kt,cs,py}` orphelin (jamais importé par les routes correspondantes) est un **gap bloquant** [FRONTEND_BACKEND_CONTRACT_GAP] (cf. `library-and-stack.md §6.bis.4`).
- AC-23: **anti-derive ownership** — la FEAT 20 crée **un nouveau service** `services/employeePreferencesService.*` (gérant GET + PATCH des préférences) ET **un nouveau service** `services/employeeAccountService.*` (gérant le DELETE de compte) ET **étend** le repository existant `repositories/employeeRepository.*` (cf. FEAT 3) avec 3 nouvelles méthodes : `findPreferencesByEmployeeId(employeeId)`, `updatePreferences(employeeId, partial)`, `deleteById(employeeId)` (cf. `ownership.md §1` Edit-augment exclusif sur fichier existant) ; aucune modification des autres services existants (`babyService` / `rapportService` / `contratService` / `documentationService` / `reseauAssistantesService`). Un commit qui ne livre **que** les route handlers sans les services ou la méthode repository correspondante viole cette FEAT.

## Dependencies

- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employée connectée ; le middleware d'authentification protège `/parametres` et les 3 endpoints `/api/employees/me[/preferences]` (cf. BR-1). La déconnexion automatique post-suppression de compte (cf. SFD-13) réutilise le flux de retour à `/login` couvert par spec-connexion.
- **spec-inscription** (`3-spec-inscription`) : la table `dbo.Employee` est définie par cette FEAT — la spec 20 réutilise la colonne `Disponible` existante et **assume** la pré-existence de `Notification` (migration ops out of scope). La suppression physique du compte (cf. SFD-13) purge la ligne `Employee` créée par FEAT 3, ainsi que le fichier statique avatar `wwwroot/images/{employeeId}.png` (cf. FEAT 3 BR-15).
- **spec-menu-principale** (`5-spec-menu-principale`) : **étendue directement** par cette FEAT — ajout d'un nouvel item « Paramètres » dans la liste de navigation du panneau latéral (cf. SFD-1, AC-1). L'item suit le pattern visuel des items existants (icône SVG ou material-symbols + libellé + navigation SPA).
- **spec-reseau-assistantes** (`19-Spec-Reseau-Assistantes`) : consomme déjà la colonne `Employee.Disponible` pour piloter la visibilité dans le réseau (cf. FEAT 19 BR-7) — cette FEAT introduit l'UI permettant à l'employée de modifier cette valeur ; le comportement de filtrage côté FEAT 19 reste inchangé.

## Functional Deliverables

- FD-1: nouvel item « Paramètres » ajouté à la liste de navigation du panneau latéral de `spec-menu-principale` (extension FEAT 5) — icône engrenage / settings (SVG ou material-symbols selon DS actif), libellé `Paramètres`, navigation SPA vers `/parametres` au clic + fermeture du panneau (héritage FEAT 5 AC-5 + AC-6).
- FD-2: nouvelle route SPA `/parametres` rendant un composant `ParametresPage` (ou équivalent stack) — topbar (bouton retour + titre), barre de 3 onglets, corps scrollable avec onglet 1 fonctionnel (2 toggles + section Documents + bouton suppression) et onglets 2/3 en placeholder (cf. SFD-3, SFD-4, SFD-15).
- FD-3: nouvel endpoint backend `GET /api/employees/me/preferences` — SELECT ciblé sur 2 colonnes scopé à `@SessionEmployeeId` + sérialisation camelCase + middleware d'authentification (cf. SFD-7, BR-1, BR-5).
- FD-4: nouvel endpoint backend `PATCH /api/employees/me/preferences` — body JSON avec ≥ 1 champ booléen reconnu, UPDATE dynamique paramétré scope `@SessionEmployeeId`, réponse `204 No Content` (cf. SFD-8, BR-3, BR-4).
- FD-5: nouvel endpoint backend `DELETE /api/employees/me` — DELETE physique paramétré scope `@SessionEmployeeId` + cascade FK + suppression best-effort du fichier statique avatar, réponse `204 No Content` (cf. SFD-13, BR-13, BR-14).
- FD-6: nouveau service backend `employeePreferencesService` (méthodes `getMyPreferences(sessionEmployeeId)` et `patchMyPreferences(sessionEmployeeId, partial)`) appelé directement par les route handlers GET et PATCH (cf. AC-22) ; pas de logique additionnelle (mapping direct row ↔ DTO).
- FD-7: nouveau service backend `employeeAccountService` (méthode `deleteMyAccount(sessionEmployeeId)`) appelé directement par le route handler DELETE (cf. AC-22) ; orchestre la requête `DELETE` + la suppression best-effort du fichier statique avatar (cf. SFD-13, BR-14).
- FD-8: extension du repository existant `employeeRepository` (cf. FEAT 3) avec **3 nouvelles méthodes** : `findPreferencesByEmployeeId(employeeId): PreferencesDto`, `updatePreferences(employeeId, partial: PartialPreferencesDto): void`, `deleteById(employeeId): void` (cf. AC-23) ; classe DTO `EmployeePreferencesDto` (2 champs `disponible`, `notification`) exposée au service.
- FD-9: composant frontend `ParametresPage` (ou équivalent stack) — gère le state local des préférences, le switch d'onglet, le flux PATCH au changement de toggle (avec rollback optimistique), le flux modal + DELETE pour la suppression de compte (cf. SFD-7, SFD-9, SFD-12, SFD-13).
- FD-10: composant frontend `DeleteAccountModal` (ou équivalent stack) — modal de confirmation centré, focus-trapped, dismissible au clavier (Escape + clic backdrop), avec corps explicatif listant les conséquences (cf. SFD-12, BR-18).
- FD-11: composants frontend `Onglet2Panel` et `Onglet3Panel` (ou équivalents stack) — placeholders réservés rendant l'en-tête « À définir » + encart dashed « Contenu à venir » (cf. SFD-15).
- FD-12: états de chargement / vide / erreur côté frontend — version désactivée des 2 cards + section Documents + bouton suppression pendant le GET (cf. SFD-14), libellé erreur générique `Impossible de charger les paramètres.` + bouton `Réessayer` (cf. SFD-14, AC-16), toasts transitoires sur échec PATCH / DELETE (cf. SFD-9 étape 4, SFD-13 étape 4).
- FD-13: maquette `workspace/input/ui/20-1-Spec-Parametres.html` matérialisant le rendu canonique de l'onglet 1 + placeholders onglets 2/3 — référence visuelle non-ambiguë pour `dev-frontend`. **Note d'écart explicite** : le libellé de version `v7.5.8 (309)` du mockup n'est PAS rendu en code (cf. SFD-11, BR-9, AC-14).

## Out of Scope

- **création / migration** des 2 colonnes `Employee.Disponible` / `Employee.Notification` : la FEAT assume leur pré-existence en base (cf. Pré-requis schéma) ; toute migration DDL relève d'une FEAT ops dédiée hors scope.
- **rédaction et hébergement des documents légaux** réels (CGU / Mentions légales / Politique de confidentialité / Conditions générales de vente) : les 3 URLs sont placeholder `https://www.google.com` (cf. BR-7) ; le contenu réel, le format (HTML / PDF / page CMS), le stockage (table `Documentation` de FEAT 17 OU table dédiée OU URL externe) et la mécanique de mise à jour relèvent d'une FEAT future hors scope.
- **système d'envoi d'emails marketing** : la valeur de `Notification` est lue et persistée par cette FEAT, mais aucun système d'envoi de mails n'est branché côté backend (cf. BR-6) ; l'intégration d'un service d'emailing (SendGrid, Mailgun, SMTP custom) et la logique de filtrage par opt-out relèvent d'une FEAT future hors scope.
- **contenu fonctionnel des onglets 2 et 3** : les deux onglets sont **réservés** et rendent un placeholder « Contenu à venir » (cf. SFD-15, AC-19) ; leur spécification fonctionnelle relève de FEATs futures dédiées (les libellés génériques `Onglet 2` / `Onglet 3` seront remplacés à ce moment-là).
- **deep-linking par onglet** : l'onglet actif n'est pas persisté dans l'URL (cf. SFD-5, BR-15) ; un futur deep-linking `/parametres?tab=onglet2` relève d'une FEAT future si justifié par un cas d'usage de partage URL.
- **période de grâce post-suppression** / soft-delete / undo : la suppression de compte est physique et immédiate (cf. SFD-13, BR-13) ; toute introduction d'un délai de réversibilité (« 30 jours pour annuler ») nécessiterait un soft-delete + job d'ops + UI dédiée — out of scope, décision RGPD priorisée pour la simplicité et la conformité art. 17.
- **export RGPD avant suppression** (téléchargement de toutes ses données au format JSON / PDF) : aucun export n'est exposé par cette FEAT — l'utilisatrice peut consulter ses données dans les pages existantes (`/donnees`, `/bebes`, `/contrats`, `/rapports`) mais aucun bouton « Télécharger mes données » n'est introduit. Une FEAT future pourrait répondre à l'article 20 RGPD (droit à la portabilité).
- **suppression sélective** (supprimer uniquement les bébés / contrats / rapports sans supprimer le compte) : aucune granularité n'est exposée — la suppression de compte est une action all-or-nothing.
- **historique de modifications** des préférences (audit log des changements de toggle) : aucun log applicatif scopé par utilisateur n'est introduit (cf. NFC compliance) ; les logs techniques (latence, code HTTP) restent en place.
- **2FA / mot de passe pour confirmer la suppression** : le modal de confirmation est l'unique safeguard (cf. SFD-12, BR-13) ; aucune saisie de mot de passe ou code 2FA n'est exigée. Une FEAT future de hardening sécurité pourrait introduire un second facteur.
- **notification email post-suppression** (envoi d'un email de confirmation « Votre compte a été supprimé ») : aucun email n'est envoyé (cf. BR-6 absence de système d'envoi) — la confirmation visuelle est la redirection vers `/login`.
- **i18n des libellés statiques** (`Paramètres`, `Mentions légales`, `Être visible auprès des autres assistantes maternelles`, `Recevoir des emails marketing`, `Documents`, `CGU / Mentions légales`, `Politique de confidentialité`, `Conditions générales de vente`, `Supprimer mon compte`, `Supprimer définitivement votre compte ?`, corps explicatif du modal, `Annuler`, `Impossible de charger les paramètres.`, `Modification non enregistrée. Réessayez.`, `La suppression a échoué. Réessayez.`, `Réessayer`, `Contenu à venir`, `Cet onglet est réservé pour de futurs paramètres.`, `À définir`) : libellés en dur en français (cf. FEAT 15 BR-14, FEAT 17 Out of Scope) ; l'i18n future n'impactera pas le backend.
- **affichage de la version du produit** : le libellé `v7.5.8 (309)` du mockup est explicitement exclu (cf. SFD-11, BR-9, AC-14) ; aucune information de version, build number, hash commit n'est exposée sur cette page.
- **rôles Admin / Parent** : la spec couvre uniquement le rôle Employée (assistante maternelle) ; les paramètres d'un Admin (modération, configuration globale) ou d'un Parent (préférences spécifiques à un suivi enfant) relèvent de FEATs futures dédiées avec règles différentes.
- **support multi-comptes** (basculer entre plusieurs comptes Employée depuis la page paramètres) : un seul compte par session, pas de switch utilisateur intra-app.
- **personnalisation du thème** (mode sombre, taille de police, contraste élevé) : aucun toggle d'apparence dans cette FEAT ; pourrait relever d'une FEAT future « Préférences d'affichage ».
- **suppression batch / restauration** : aucune opération bulk côté admin (supprimer N comptes en une fois) ni restauration de compte supprimé par erreur — l'irrévocabilité est totale (cf. BR-13).
- **téléchargement de l'image avatar** avant suppression : non exposé — l'image PNG est purgée du disque server-side en best-effort (cf. BR-14) sans copie préalable côté client.
