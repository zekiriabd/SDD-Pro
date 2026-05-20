# Spec: 3-1-Campagnes-Vue-Liste

Spec ID: 3-1-Campagnes-Vue-Liste

## Context

L'application gère des campagnes marketing stockées en base PostgreSQL dans la table `compagne` (orthographe historique de la base — alias logique `campagne` au niveau DTO/UI). Chaque ligne possède 4 clés étrangères vers les tables référentiels : `marque`, `statut`, `enseigne`, `annonceur`. Toutes ces tables exposent une colonne `libelle` qui sert de valeur d'affichage dans la grille. Les utilisateurs marketing ont besoin d'une page de listing pour consulter, filtrer, exporter ces campagnes et basculer vers une vue temporelle (timeline, traitée dans spec `4-campagnes-vue-timeline`).

## Objective

Permettre à un utilisateur authentifié de consulter l'ensemble des campagnes existantes dans une grille filtrable, paginable et exportable (toutes ces opérations 100% côté frontend via le composant DataGrid du Design System), avec bascule possible vers la vue timeline et accès à la création d'une nouvelle campagne.

## Actors

- Utilisateur marketing authentifié (Azure AD): consulte, filtre, exporte les campagnes
- Frontend SPA: charge la liste complète, affiche la grille, gère filtrage/pagination/tri/export en mémoire via le composant DataGrid du Design System
- Backend API: expose `GET /api/v1/campagnes` qui exécute la requête SQL §SQL Contract (4 INNER JOIN vers `marque/statut/enseigne/annonceur`, retourne la **liste complète** — pas de pagination serveur)
- Base PostgreSQL: stocke les tables `compagne`, `marque`, `statut`, `enseigne`, `annonceur` (toutes avec colonne `libelle` pour l'affichage)

## SQL Contract

La requête canonique exécutée par `GET /api/v1/campagnes` est :

```sql
SELECT
    compagne.id,
    compagne.libelle   AS Nom,
    marque.libelle     AS Marque,
    statut.libelle     AS Statut,
    compagne.date_debut,
    compagne.date_fin,
    enseigne.libelle   AS Enseigne,
    annonceur.libelle  AS Annonceur
FROM compagne
INNER JOIN marque    ON marque.id    = compagne.fk_marque
INNER JOIN statut    ON statut.id    = compagne.fk_statut
INNER JOIN enseigne  ON enseigne.id  = compagne.fk_enseigne
INNER JOIN annonceur ON annonceur.id = compagne.fk_annonceur;
```

**Conséquence des INNER JOIN** : toute campagne qui n'a pas exactement 1 ligne référencée dans chacune des 4 tables FK est **exclue silencieusement** du résultat (cf. RISK-4, EDGE-2).

**Forme du DTO retourné** (un objet plat par ligne, casse `camelCase` côté JSON) :

```json
{
  "id": 12345,
  "nom": "145630 Barilla",
  "marque": "PANZANI",
  "statut": "ACTIVE",
  "dateDebut": "2025-09-02",
  "dateFin": "2025-09-11",
  "enseigne": "Carrefour",
  "annonceur": "Bonduelle Frais France"
}
```

Le backend renvoie un **array JSON** de ces objets.

## Functional Needs

- SFD-1: Afficher un en-tête de bienvenue sur 2 lignes : `Bonjour {Prénom} !` puis `Aujourd'hui, nous sommes le {date}` (Prénom extrait des claims Azure AD)
- SFD-2: Afficher la liste des campagnes existantes dans une grille (composant DataGrid du Design System)
- SFD-3: Proposer une bascule entre "Vue liste campagne" (cette spec) et "Vue timeline campagne" (spec `4-campagnes-vue-timeline`) via un toggle / segmented control
- SFD-4: Permettre la création d'une nouvelle campagne via un bouton "Nouvelle campagne" qui redirige vers la page de création (spec `5-campagne`, nom de route à confirmer)
- SFD-5: Paginer les résultats de la grille (**pagination 100% côté frontend** via le composant DataGrid sur le dataset chargé en mémoire — aucun paramètre de pagination côté backend)
- SFD-6: Filtrer les colonnes de la grille (filtrage **100% côté frontend** sur le dataset chargé via les capacités natives du composant DataGrid — aucun appel backend dédié)
- SFD-7: Afficher / masquer dynamiquement les colonnes de la grille (**côté frontend** uniquement, via le sélecteur de colonnes natif du composant DataGrid)
- SFD-8: Exporter les données filtrées de la grille au format CSV (génération **côté frontend** via `Blob` + `papaparse` ou équivalent fourni par le DataGrid — aucun endpoint backend dédié)
- SFD-9: Afficher le **nombre total de campagnes** chargées sous forme de badge à côté de l'onglet "Vue liste campagne" (compteur **calculé côté frontend** après réception du payload de `GET /api/v1/campagnes` = `campagnes.length`)
- SFD-10: Afficher une bannière promotionnelle "Lancez votre prochaine campagne" en haut de la page contenant le bouton "Nouvelle campagne" (SFD-4)
- SFD-11: La page est accessible via le clic sur l'item "Campagne" du menu principal (cf. spec `2-menu`)

## Business Rules

- BR-1: Les campagnes sont chargées en **un seul appel** via l'endpoint backend `GET /api/v1/campagnes` qui retourne **la liste complète** (sans pagination, filtrage, ni tri côté serveur)
- BR-2: La requête SQL exécutée par `GET /api/v1/campagnes` est strictement celle définie en §SQL Contract — 4 INNER JOIN vers `marque`, `statut`, `enseigne`, `annonceur` ; seule la colonne `libelle` de chaque table FK est exposée côté frontend (aucun `id` de FK n'est sérialisé dans la réponse car non utilisé par la grille)
- BR-3: L'accès à la page est conditionné à un utilisateur authentifié via Azure AD (JWT Bearer token transmis sur HTTPS uniquement, cookies session marqués HttpOnly + Secure ; cf. spec `1-authentification`)
- BR-4: L'export CSV reflète exactement les données filtrées affichées dans la grille (pas l'intégralité du dataset chargé, et a fortiori pas l'intégralité de la base) ; l'export est généré **entièrement côté frontend** depuis le dataset déjà chargé en mémoire (Blob + `papaparse`), **sans appel backend** ; seules les colonnes actuellement **visibles** sont incluses
- BR-5: Les colonnes affichées par défaut sont, dans cet ordre : `nom` (= `compagne.libelle`), `marque` (= `marque.libelle`), `statut` (= `statut.libelle`), `dateDebut`, `dateFin`, `enseigne` (= `enseigne.libelle`), `annonceur` (= `annonceur.libelle`)
- BR-6: Le bouton "Nouvelle campagne" redirige vers `/campagnes/creation` (URL canonique imposée par FEAT 4 BR-14 ; page CampagneInfosPage mode création livrée par US 4-1 de FEAT 4). Aucune autre URL acceptée (`/campagnes/nouvelle`, `/campagnes/nouveau`, etc. interdites).
- BR-7: La page porte un titre de section `Détails des campagnes` au-dessus de la toolbar (tabs + boutons)
- BR-8: L'onglet par défaut sélectionné au chargement de la page est `Vue liste campagne`
- BR-10: **Toolbar unique (composition load-bearing)** — les onglets `Vue liste campagne / Vue timeline campagne` (FD-4), le badge compteur (AC-9), le bouton `Colonnes` (FD-7) et le bouton `Exporter` (FD-8) constituent ensemble **UNE SEULE toolbar** montée **UNE SEULE FOIS** dans la page (au-dessus de la grille, sous le titre `Détails des campagnes`). Si le découpage en User Stories répartit la livraison de ces éléments sur plusieurs US (ex. tabs livrés par une US, boutons par une autre), il est **interdit** de créer un composant "placeholder" avec versions `disabled` qui resterait monté après la livraison de la version fonctionnelle : la toolbar finale ne doit pas comporter de doublons d'onglets, de badges, de bouton `Colonnes` ni de bouton `Exporter`. Toute US qui livre la version fonctionnelle d'un élément doit explicitement, dans son augment contract, retirer/remplacer le placeholder de la version précédente.
- BR-9: La colonne `statut` est rendue par un chip coloré selon la valeur de `statut.libelle`. Le mapping libellé → couleur attendu (couleurs validées par le mockup `3-Campagnes-Vue-Liste.html`) :
  - `ACTIVE` → chip vert
  - `SUSPENDUE` → chip orange
  - `BROUILLON` → chip bleu
  - `PROGRAMMÉE` → chip jaune
  - Toute autre valeur retournée par la base → chip gris neutre par défaut (sans erreur)

## Acceptance Criteria

- AC-1: L'en-tête affiche sur 2 lignes : ligne 1 `Bonjour {Prénom} !` (h1), ligne 2 `Aujourd'hui, nous sommes le {date}` (texte muted) ; `{Prénom}` provient du claim Azure AD (`given_name` ou fallback `name`) ; `{date}` est la date du jour locale au format long FR (ex. `18 juillet 2025`)
- AC-2: La grille affiche toutes les campagnes retournées par `GET /api/v1/campagnes` avec les colonnes définies en BR-5 ; chaque cellule reflète directement la valeur du DTO (pas de transformation côté front au-delà du formatage de date)
- AC-3: Un sélecteur (segmented control / tabs) permet de basculer entre "Vue liste campagne" et "Vue timeline campagne" sans rechargement complet de la page
- AC-4: Le clic sur le bouton "Nouvelle campagne" redirige vers la page de création de campagne (spec `5-campagne`)
- AC-5: La pagination est fonctionnelle (navigation entre pages, taille de page configurable parmi `6 | 10 | 25 | 50`), **opérant côté frontend** sur le dataset chargé via le composant DataGrid (pas d'appel backend par page)
- AC-6: Les filtres par colonne sont fonctionnels (au minimum filtre texte sur les colonnes textuelles `nom/marque/enseigne/annonceur`, filtre date **par égalité exacte** sur `dateDebut/dateFin` — **un seul input `<input type="date">` par colonne**, jamais un range from/to ; la ligne matche si `row[col] === filterValue` au format ISO `YYYY-MM-DD`, filtre vide = pas de contrainte —, filtre liste de valeurs sur `statut`), opérant **côté frontend** sur le dataset chargé (pas d'appel backend par filtre)
- AC-7: L'utilisateur peut afficher/masquer les colonnes via un bouton "Colonnes" dédié dans la toolbar (**état purement frontend**, aucune persistance serveur)
- AC-8: Le clic sur "Exporter" télécharge un fichier CSV contenant uniquement les données correspondant aux filtres actifs et aux colonnes visibles ; le fichier est **généré côté frontend** (Blob + `papaparse`), **aucun endpoint backend** n'est appelé pour l'export
- AC-9: Un badge affichant `{nombre de campagnes chargées}` est visible à côté du libellé de l'onglet "Vue liste campagne" ; ce compteur est **calculé côté frontend** comme `campagnes.length` après réception de la réponse `GET /api/v1/campagnes` (et donc reflète la totalité du dataset chargé, indépendamment des filtres ou de la page courante)
- AC-10: Une bannière "Lancez votre prochaine campagne" est affichée au-dessus du titre `Détails des campagnes`, contenant le bouton "Nouvelle campagne" (le même bouton de SFD-4 — un seul exemplaire dans la page)
- AC-11: La colonne `statut` est rendue conformément à BR-9 (mapping libellé → couleur du chip)
- AC-12: La colonne `enseigne` affiche la valeur unique `enseigne.libelle` (1 enseigne par campagne — relation FK simple, pas de notation `+N`). **Note de divergence** : le mockup HTML montre `Carrefour +5` suggérant un multi-enseignes ; cette représentation est superseded par le contrat SQL (1 enseigne par campagne). Le rendu doit suivre le contrat SQL ; le `+5` du mockup est traité comme une licence graphique non implémentée
- AC-13: **Anti-doublon toolbar (BR-10)** — la page CampagnesPage ne doit afficher au runtime QU'UNE SEULE occurrence visible de chacun des éléments suivants : (a) onglet `Vue liste campagne`, (b) onglet `Vue timeline campagne`, (c) badge compteur de l'onglet liste, (d) bouton `Colonnes`, (e) bouton `Exporter`. Une revue visuelle ou test E2E doit confirmer ce critère avant clôture de la FEAT. Tout placeholder/composant obsolète issu d'une US antérieure doit être démonté.

## Dependencies

- 1-authentification (utilisateur connecté + claims Azure AD `given_name`/`name` pour `{Prénom}`)
- 2-menu (entrée de menu "Campagne" → ouvre cette page)
- 4-campagnes-vue-timeline (bascule depuis la vue liste vers la vue timeline)
- 5-campagne (cible du bouton "Nouvelle campagne", nom de route à confirmer)
- Backend `GET /api/v1/campagnes` exécutant la requête SQL §SQL Contract
- Base PostgreSQL contenant `compagne` + tables référentiels `marque`, `statut`, `enseigne`, `annonceur` (toutes avec colonne `libelle`) et FK valides `compagne.fk_marque / fk_statut / fk_enseigne / fk_annonceur`

## Functional Deliverables

- FD-1: Bloc header affichant le message d'accueil personnalisé sur 2 lignes (Prénom utilisateur + date du jour FR)
- FD-2: Bouton "Nouvelle campagne" (intégré dans la bannière promotionnelle FD-10) redirigeant vers la page de création
- FD-3: Grille de campagnes (composant DataGrid du Design System) avec colonnes `nom`, `marque`, `statut`, `dateDebut`, `dateFin`, `enseigne`, `annonceur` (cf. BR-5)
- FD-4: Segmented control / tabs de bascule entre "Vue liste campagne" et "Vue timeline campagne", avec badge compteur sur l'onglet "Vue liste campagne". **Intégré à la toolbar unique BR-10** (jamais en composant séparé monté en parallèle).
- FD-5: Pagination de la grille (**implémentation frontend** native du DataGrid, sélecteur taille de page `6 | 10 | 25 | 50`)
- FD-6: Filtres par colonne dans la grille (**implémentation frontend** native du DataGrid)
- FD-7: Sélecteur d'affichage / masquage des colonnes (**frontend** uniquement, bouton "Colonnes" dans la toolbar). **Intégré à la toolbar unique BR-10** (jamais en composant séparé monté en parallèle).
- FD-8: Bouton "Exporter" produisant un fichier CSV des données filtrées + colonnes visibles (**génération frontend** via Blob + `papaparse`, **pas d'endpoint backend**). **Intégré à la toolbar unique BR-10** (jamais en composant séparé monté en parallèle).
- FD-9: Endpoint backend `GET /api/v1/campagnes` exécutant la requête §SQL Contract et sérialisant le résultat en tableau JSON conforme au DTO documenté (seul livrable backend de cette spec ; pas de query params de filtrage/tri/pagination)
- FD-10: Bannière promotionnelle "Lancez votre prochaine campagne" en haut de page intégrant FD-2
- FD-11: Titre de section `Détails des campagnes` entre la bannière et la toolbar
- FD-12: Chips de statut (variantes colorées) pour la colonne `statut` selon le mapping BR-9

## Out of Scope

- Création de campagne (détaillée dans spec `5-campagne`)
- Vue timeline (détaillée dans spec `4-campagnes-vue-timeline`)
- Modification / suppression d'une campagne existante
- Filtrage avancé multi-critères croisés / recherche full-text serveur
- Export dans d'autres formats que CSV (Excel, PDF)
- Permissions par rôle sur l'accès aux campagnes
- **Endpoint backend dédié au filtrage / tri / pagination serveur** (toutes ces opérations sont 100% côté frontend dans cette spec)
- **Endpoint backend dédié à l'export CSV** (génération côté navigateur via Blob)
- **Persistance côté serveur de l'état des colonnes affichées / filtres / page courante** (purement client)
- Édition du statut, de l'enseigne, de la marque ou de l'annonceur d'une campagne (hors scope listing)
- **Relation campagne ↔ enseignes multiples** (le mockup `+5` est superseded par le contrat SQL : 1 enseigne par campagne via `fk_enseigne`)
- Récupération des campagnes orphelines (sans `fk_marque/fk_statut/fk_enseigne/fk_annonceur` complet) — exclues par les INNER JOIN (cf. RISK-4)

## Risques Identifiés

| ID | Risque | Sévérité | Mitigation |
|---|---|---|---|
| RISK-1 | Requête `GET /api/v1/campagnes` avec 4 INNER JOIN (`marque`, `statut`, `enseigne`, `annonceur`) non indexées → timeout SQL sur volume > 5 000 lignes | high | Vérifier index FK sur `compagne.fk_marque`, `compagne.fk_statut`, `compagne.fk_enseigne`, `compagne.fk_annonceur` et index PK sur les 4 tables FK ; documenter le plan d'exécution (`EXPLAIN ANALYZE`) avant déploiement |
| RISK-2 | Pagination 100% côté client (chargement de la totalité des lignes en mémoire au premier appel) → freeze UI au-delà de ~5 000 campagnes | high | Documenter la limite : design retenu valable pour volume < 5 000 campagnes ; si dépassement, ouvrir une nouvelle spec pour basculer en pagination serveur (rupture de contrat assumée, hors scope de cette spec) ; activer la virtualisation interne du DataGrid si supportée par le DS |
| RISK-3 | Export CSV généré côté client (Blob JS) sur dataset filtré volumineux → blocage navigateur / onglet mort | medium | Limiter l'export à 5 000 lignes max avec message d'avertissement utilisateur ; en pratique borné par RISK-2 (le dataset entier ne dépasse pas cette limite par design) |
| RISK-4 | **Exclusion silencieuse** par INNER JOIN : toute campagne dont l'une des 4 FK est NULL ou pointe vers un id inexistant est absente du résultat sans aucun log côté backend ni signal côté frontend | **high** | (1) Data/SQL team confirme l'intégrité référentielle (NOT NULL + FK contraintes côté base) sur les 4 colonnes `fk_*` de `compagne` ; (2) ajouter une requête de monitoring backend qui compte `SELECT COUNT(*) FROM compagne` et compare au nombre de lignes retournées par la requête §SQL Contract — alerte si écart ; (3) à arbitrer cross-spec : faut-il passer à LEFT JOIN + valeurs par défaut ? Décision PO requise |
| RISK-5 | Dépendance aux specs `4-campagnes-vue-timeline` et `5-campagne` non livrées → bascule et bouton "Nouvelle campagne" en état cassé | low | Implémenter les boutons/tabs avec route stub retournant page 404 explicite jusqu'à livraison des specs dépendantes |
| RISK-6 | Volume de la réponse `GET /api/v1/campagnes` non borné côté backend → payload XL (plusieurs MB) sur connexion mobile / réseau lent | medium | Documenter la taille moyenne attendue et le SLO p95 latence ; envisager une compression `gzip` HTTP côté backend ; alerte applicative si la réponse dépasse un seuil configurable |
| RISK-7 | Orthographe historique de la table (`compagne` au lieu de `campagne`) → erreur de typage côté code applicatif si quelqu'un présume `campagne` | low | Coder le DAL backend en utilisant strictement le nom DB `compagne` ; aliaser au niveau ORM/DTO vers `Campagne` (entité C#/Java/TS) pour isoler le typo ; documenter le mapping dans le CLAUDE.md projet généré par arch |

---

## Hypothèses

| ID | Hypothèse | Statut | Validation requise |
|---|---|---|---|
| ASS-1 | L'utilisateur arrive sur la page avec un JWT Azure AD valide (flow géré par spec `1-authentification`) | à valider | Confirmer que le guard de route frontend intercepte bien l'accès non authentifié avant le chargement du composant |
| ASS-2 | Les tables `compagne`, `marque`, `statut`, `enseigne`, `annonceur` existent en base PostgreSQL avec les colonnes attendues (`id`, `libelle`, FK `fk_*`) et les FK sont valides (intégrité référentielle stricte) | à valider | Data/SQL team confirme l'état du schéma + des contraintes FK NOT NULL + le volume actuel de données + l'absence d'orphelins (lien direct avec RISK-4) |
| ASS-3 | L'endpoint `GET /api/v1/campagnes` est à créer dans le cadre de cette spec (FD-9) — il n'existe pas encore | à valider | Vérifier qu'aucune autre spec ou code existant n'expose déjà cet endpoint avec un contrat divergent |
| ASS-4 | La pagination, le filtrage et le tri sont implémentés **100% côté frontend** via le composant DataGrid du Design System (PAS de pagination/filtrage/tri serveur) | confirmée par PO | Décision PO documentée le 2026-05-18 — assumée valable pour volume < 5 000 campagnes, sinon nouvelle spec requise |
| ASS-5 | Le volume de campagnes est < 5 000 lignes, ce qui rend la pagination côté client viable sans virtualisation systématique | à valider | Confirmer avec Data/SQL team ; si > 5 000, ouvrir nouvelle spec pour pagination serveur |
| ASS-6 | Le prénom de l'utilisateur connecté (`{Prénom}`) est accessible depuis les claims Azure AD côté frontend (`given_name` en priorité, fallback `name`) | à valider | Vérifier le claim disponible dans le token JWT retourné par l'AD tenant configuré ; définir la stratégie de découpe si seul `name` complet disponible |
| ASS-7 | La locale de date est déterminée côté client (navigateur) ; pas de préférence utilisateur persistée en base | confirmée | Mentionné dans AC-1 : "date du jour locale" + cas limite date indisponible → ISO (cf. EDGE-4) |
| ASS-8 | La table `statut` contient (au minimum) les 4 libellés `ACTIVE`, `SUSPENDUE`, `BROUILLON`, `PROGRAMMÉE` qui sont mappés à des chips colorés ; toute autre valeur tombe sur le chip gris neutre par défaut | à valider | Data/SQL team confirme la liste exhaustive des `libelle` présents dans `statut` ; si d'autres valeurs existent (ex. `TERMINÉE`, `ARCHIVÉE`), le PO doit étendre le mapping BR-9 |
| ASS-9 | Le composant DataGrid du Design System actif supporte nativement : tri par colonne, filtre par colonne (texte/date/enum), pagination, masquage de colonnes, et export CSV (ou expose une API JS suffisante pour le générer) | à valider | Tech Lead confirme les capacités du DataGrid du DS retenu (shadcn DataTable + TanStack Table / Vuetify v-data-table / Radzen DataGrid) ; si une capacité manque, l'implémenter manuellement reste à scope de cette spec |
| ASS-10 | Le mockup `3-Campagnes-Vue-Liste.html` affiche `Carrefour +5` dans la colonne Enseigne, suggérant un multi-enseignes. Le contrat SQL fourni (1 FK `fk_enseigne`) **prévaut** : 1 enseigne unique par campagne | confirmée par PO | Décision PO documentée le 2026-05-18 — le `+5` du mockup est traité comme licence graphique non implémentée ; si un multi-enseigne est réellement requis, ouvrir nouvelle spec avec table de liaison N-N (changement de modèle DB) |

---

## Cas Limites

| ID | Cas limite | Comportement attendu | Couvert par |
|---|---|---|---|
| EDGE-1 | Aucune campagne en base, OU toutes les campagnes ont une FK invalide (donc 0 ligne après INNER JOIN) | Grille affiche un état vide explicite (message "Aucune campagne disponible") plutôt qu'un spinner infini ; badge compteur affiche `0` | à ajouter — AC manquante |
| EDGE-2 | Campagne avec FK invalide (orpheline) → exclue silencieusement par INNER JOIN, donc absente du dataset frontend | **Le cas est volontairement masqué côté UI** (contrat SQL en INNER JOIN). Détection backend uniquement via le monitoring RISK-4 (comparaison COUNT(*) vs lignes retournées) | RISK-4 + ASS-2 |
| EDGE-3 | Export CSV avec 0 lignes après filtrage (filtre trop restrictif) | Fichier CSV produit avec uniquement la ligne d'en-têtes des colonnes visibles | à ajouter — AC manquante |
| EDGE-4 | Locale du navigateur absente ou invalide (rare mais possible en environnement corporate) | Date dans l'en-tête affichée au format ISO 8601 (YYYY-MM-DD) comme fallback | à ajouter — AC manquante |
| EDGE-5 | Token Azure AD expiré pendant la consultation (expiration en session longue) | Interception par guard → redirection vers page login (spec `1-authentification`) sans perte de l'URL courante (deep link restore) | AC-3 de spec `1-authentification` — à vérifier cross-spec |
| EDGE-6 | `GET /api/v1/campagnes` retourne 200 OK mais payload vide `[]` vs erreur réseau 0 / timeout | Les deux cas doivent déclencher des messages distincts : état vide vs erreur technique avec bouton "Réessayer" | à ajouter — AC manquante |
| EDGE-7 | Utilisateur masque toutes les colonnes via le sélecteur (SFD-7) | La grille reste visible avec un message "Aucune colonne sélectionnée" ou au moins 1 colonne forcée (`nom`) impossible à masquer | à ajouter — AC manquante |
| EDGE-8 | Filtrage simultané sur plusieurs colonnes avec caractères spéciaux (apostrophes, guillemets, unicode) | Filtres appliqués côté client en logique purement string (pas d'eval, pas d'injection possible côté serveur puisqu'aucun appel back par filtre) | à ajouter — AC manquante |
| EDGE-9 | Claim Azure AD `given_name` absent, seul `name` complet présent (ex. `SDD-Pro maintainer`) | Extraire le premier token avant espace ; si échec, afficher le `name` complet | à ajouter — AC manquante |
| EDGE-10 | La table `statut` retourne un `libelle` inattendu (ex. `TERMINÉE`) absent du mapping BR-9 | Chip gris neutre par défaut, sans crash UI ni erreur ; logguer côté frontend pour observabilité | BR-9 (fallback gris) |

---

## Parties Prenantes

| Acteur | Rôle vs feature | Niveau d'implication |
|---|---|---|
| Product Owner | Valide les critères d'acceptation, arbitre les priorités, a tranché ASS-4 (pagination 100% front) et ASS-10 (enseigne single) | A (Accountable) |
| Equipe Frontend | Implémente la page liste (grille DS, filtres, pagination, export, bascule, header, bannière) | R (Responsible) |
| Equipe Backend | Implémente `GET /api/v1/campagnes` exécutant exactement la requête §SQL Contract | R (Responsible) |
| Data / SQL Team | Confirme l'état du schéma `compagne` + 4 tables FK, les index, le volume, l'intégrité référentielle, la liste des `statut.libelle` ; valide ASS-2, ASS-5, ASS-8 ; co-arbitre RISK-4 (INNER vs LEFT JOIN) | C (Consulted) |
| Tech Lead | Valide les choix techniques (composant DataGrid du DS, capacités natives vs implémentation manuelle, stratégie export CSV, alias `compagne` → `Campagne` au niveau ORM) ; valide ASS-9 et RISK-7 | C (Consulted) |
| Utilisateurs finaux marketing | Cibles fonctionnelles ; testeurs UAT de la grille, des filtres et de l'export | I (Informed) |
| Equipe spec `1-authentification` | Fournit le mécanisme guard + claims Azure AD (`given_name` / `name`) consommés par cette spec | C (Consulted) |
| Equipe spec `2-menu` | Fournit l'entrée de menu "Campagne" qui ouvre cette page | C (Consulted) |
| Equipe spec `5-campagne` | Fournit la page cible du bouton "Nouvelle campagne" (nom de route à confirmer) | C (Consulted) |
| UX Designer | À reconfirmer : la maquette `3-Campagnes-Vue-Liste.html` montre `Carrefour +5` mais le contrat SQL impose une enseigne unique. Le mockup doit être mis à jour ou la divergence acceptée formellement | C (Consulted) |

---

## Modes de Défaillance

| ID | Mode de défaillance | Indicateur de défaillance | Critère succès en miroir |
|---|---|---|---|
| FAIL-1 | `GET /api/v1/campagnes` indisponible ou timeout → la page liste ne charge aucune donnée | Taux d'erreur 5xx sur `/api/v1/campagnes` > 1% en production ; temps de réponse p95 > 3 s | p95 < 800 ms ; taux erreur < 0,5% ; message d'erreur affiché en < 500 ms après détection + bouton "Réessayer" |
| FAIL-2 | Les utilisateurs n'utilisent pas les filtres (adoption nulle) car UI peu intuitive → exports toujours sur dataset complet → fichiers CSV inutilement volumineux | < 10% des sessions avec au moins 1 filtre actif lors d'un export | > 40% des sessions d'export utilisent au moins 1 filtre actif au bout de 30 jours |
| FAIL-3 | Export CSV inutilisable (encodage, séparateur inadapté, colonnes masquées incluses dans le CSV) | Taux d'abandon de l'action export > 30% (ré-ouverture du fichier sans action suite) | CSV ouvrable directement dans Excel FR (séparateur `;`, encodage UTF-8 BOM) ; colonnes masquées exclues du CSV (BR-4) |
| FAIL-4 | La bascule vers "Vue timeline" (SFD-3) est perçue comme un bug (rechargement complet, perte de filtres) | Feedback négatif utilisateurs ou taux rebond > 50% depuis la bascule | Bascule sans rechargement ; filtres et pagination préservés (ou réinitialisés intentionnellement avec feedback visuel) |
| FAIL-5 | Volume de campagnes dépasse silencieusement la limite ASS-5 (5 000) → freeze UI au chargement, sans signal explicite | Temps de chargement page > 5 s p95 ; rapports utilisateurs "page qui se fige" | Alerte applicative quand `campagnes.length > 4 000` (seuil d'alerte = 80% de la limite ASS-5) déclenchant la planification d'une nouvelle spec pagination serveur |
| FAIL-6 | Badge compteur (SFD-9) désynchronisé du dataset réellement chargé (cache, état stale après bascule onglet) | Différence entre `campagnes.length` et la valeur affichée dans le badge constatée en UAT | Le badge est une projection pure de `campagnes.length` (pas d'état dérivé persisté) ; recalculé à chaque rendu |
| FAIL-7 | Campagnes orphelines en base (FK manquante ou invalide) **invisibles côté front** à cause des INNER JOIN → utilisateurs métier croient à tort que ces campagnes n'existent pas | Différence entre le compte affiché (`campagnes.length`) et `SELECT COUNT(*) FROM compagne` détectée par monitoring backend (RISK-4) | 0 campagne orpheline en base (contraintes FK NOT NULL respectées) OU décision PO de passer à LEFT JOIN documentée + AC ajoutée pour le rendu des cellules vides |
