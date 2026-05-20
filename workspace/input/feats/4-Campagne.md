# Spec: 4-Campagne

Spec ID: 4-Campagne

## Context

Aujourd'hui les campagnes sont uniquement consultables (`3-campagnes-vue-liste`). Il manque le flux de création/édition de la **page Campagne** elle-même : un écran unique qui rassemble les informations métier de la campagne, l'import en masse d'EAN via CSV, et la saisie/visualisation unitaire des EAN dans une grille.

Cette FEAT 4 couvre **strictement la page "Campagne"** (= Step 1 du wizard sous-jacent). Les étapes suivantes du wizard (Périmètre / Contenus / Récapitulatif) sont **hors scope FEAT 4** et seront livrées par les FEATs 5, 6, 7. Le sub-menu wizard (visible en top bar avec les 4 onglets et le bouton "Sauvegarder et quitter") est une **infrastructure SPA partagée** : visible dès FEAT 4, alimentée progressivement par les FEATs suivantes au fil de leur livraison.

## Objective

Permettre à un utilisateur authentifié de créer ou modifier une campagne via la page **`CampagneInfosPage.tsx`** (nom canonique, cf. BR-14bis) qui rassemble sur un **seul écran** **trois blocs fonctionnels obligatoires** :

- **Bloc A — Infos générales** : ID campagne (read-only), nom auto-suggéré éditable, description, combo annonceur, combo marque (livré par US 4-1)
- **Bloc C — Import CSV** : zone d'import (dropzone), bouton "Télécharger modèle", FAQ inline "Comment préparer la liste de produits à importer ?" (livré par US 4-3, **monté dans `CampagneInfosPage.tsx`**)
- **Bloc B — Ajout unitaire EAN + Liste produits animés** : formulaire d'ajout manuel (EAN + libellé + bouton "Ajouter l'EAN"), grille paginée des EAN courants de la campagne avec tri par colonne et bouton "Tout supprimer" (livré par US 4-2, **monté dans `CampagneInfosPage.tsx`**)

Les 3 blocs sont rendus **simultanément** sur la même page — l'ordre vertical de mockup : Bloc A → Bloc C (import CSV) → Bloc B (manual + grille). Aucun de ces blocs n'est optionnel ; une page Campagne qui n'affiche pas les 3 blocs au runtime est un bug bloquant (cf. BR-14bis sur le drift de nommage de la page).

Les mutations de la collection EAN (ajout manuel via Bloc B, import CSV via Bloc C, delete unitaire/total) opèrent **en mémoire côté SPA** jusqu'à ce que l'utilisateur clique sur "Sauvegarder et quitter" ou "Suivant" (depuis le sub-menu wizard top bar). Ces 2 actions déclenchent la persistance complète (POST/PUT campagne + DELETE all EAN + bulk insert).

## Actors

- Utilisateur marketing authentifié (Azure AD): saisit la campagne et gère ses EAN sur la page unique
- Frontend SPA: porte la page Campagne (3 blocs intégrés), la collection EAN en mémoire, la grille paginée client-side, le composant SPA partagé "wizard top bar" (sub-menu + bouton "Sauvegarder et quitter")
- Backend API: expose les endpoints annonceur, marque, campagne, EAN (CRUD + bulk insert + suppression totale)
- Base PostgreSQL: stocke les campagnes et les EAN associés
- Frontend SPA assets: héberge le template CSV statique (`assets/ean-template.csv`)

## Functional Needs

- SFD-1: Créer/modifier une campagne avec annonceur, marque, nom (auto-suggéré éditable), description, dates
- SFD-2: Sélectionner un annonceur unique parmi la liste retournée par `GET /api/v1/annonceurs`
- SFD-3: Sélectionner une marque unique parmi la liste retournée par `GET /api/v1/marques`
- SFD-4: Auto-suggérer le nom de la campagne au format `{Marque}_{DateDebut}` (champ éditable, override autorisé). **Résolution ambiguïté §Hypothèses ligne 212** : aucun champ "type d'appareil" n'est livré — il n'existe **aucune table `type_appareil`** dans le schéma SQL (cf. entités scaffoldées CMSPrintBack), aucun champ correspondant dans le mockup HTML, et aucun endpoint backend `/api/v1/types-appareil` n'est exposé. Toute référence à `{TypeAppareil}` dans le format est supprimée.
- SFD-5: Saisir une description libre
- SFD-6: Ajouter manuellement un EAN (code + libellé) à la collection en mémoire de la campagne
- SFD-7: Vider la totalité de la collection EAN en mémoire ("Tout supprimer")
- SFD-8: Importer une liste d'EAN via CSV : lire le fichier, valider chaque ligne (BR-19, BR-20), ajouter les lignes valides à la collection en mémoire, afficher un popup récapitulatif rouge clair listant les lignes rejetées (BR-21)
- SFD-9: Afficher la collection EAN courante dans une grille avec **pagination frontend** (lignes par page configurable : 5/10/25/50) et **tri par colonne** (EAN, Libellé) client-side
- SFD-10: Télécharger le template CSV statique depuis l'asset SPA `/assets/ean-template.csv` (aucun appel backend)
- SFD-11: Supprimer un EAN unitaire de la collection en mémoire via bouton/icône delete par ligne de la grille
- SFD-12: Valider qu'un EAN saisi (manuel OU import CSV) est composé uniquement de chiffres (regex `^[0-9]+$`)
- SFD-13: Valider qu'un libellé EAN saisi (manuel OU import CSV) est non vide (après trim)
- SFD-14: Persister l'état complet de la campagne (Infos + collection EAN) en base via la séquence : POST/PUT campagne, puis DELETE all EAN, puis bulk insert
- SFD-15: Déclencher la persistance via "Sauvegarder et quitter" (sub-menu top bar) → save + redirect vers la liste des campagnes
- SFD-16: Déclencher la persistance via "Suivant" (sub-menu top bar) → save + navigation vers le Step 2 du wizard (`/campagnes/edit/perimetre` — page placeholder en V1, livrée par FEAT 5)
- SFD-17: Restaurer l'état "dernier Save connu" via "Retour/Annuler" sans déclencher de persistance backend
- SFD-18: Prévenir la perte de données : alerter l'utilisateur avant fermeture/refresh/navigation si la collection EAN ou les Infos contiennent des modifications non sauvegardées (drapeau `isDirty` + `beforeunload` + router guard)
- SFD-19: Empêcher l'insertion d'un libellé EAN contenant des caractères dangereux (`<`, `>`, `"`, `'`, `&`, `\0`) — protection XSS au stockage (le rendu utilise l'escaping JSX natif)
- SFD-20: Garantir des performances acceptables sur DELETE/INSERT scope `fk_campagne` via un index DB composé `(fk_campagne, ean)` sur la table `ean`
- SFD-21: Afficher une FAQ inline (accordion repliable) "Comment préparer la liste de produits à importer ?" sous la zone d'import CSV, contenu statique côté SPA (pas d'API)

## Business Rules

- BR-1: Le nom de la campagne est **auto-suggéré** par concaténation `{Marque}_{DateDebut}` dès que les 2 champs sont renseignés, mais reste **éditable manuellement**. La valeur soumise au backend est celle du champ au submit, qu'elle vienne de l'auto-suggestion ou d'une saisie utilisateur. **Note** : `{TypeAppareil}` retiré du format (cf. SFD-4 résolution ambiguïté — pas de table backing).
- BR-2: L'annonceur est un **choix unique** (pas de multi-sélection).
- BR-3: La marque est un **choix unique** (pas de multi-sélection). Le placeholder du champ doit être `"Sélectionner une marque"` (singulier).
- BR-4: La liste des annonceurs est chargée via `GET /api/v1/annonceurs` (pluriel, body `List<AnnonceurOutputDto>`).
- BR-5: La liste des marques est chargée via `GET /api/v1/marques` (pluriel, body `List<MarqueOutputDto>`).
- BR-6: Un EAN est composé obligatoirement d'un code EAN (BR-19) et d'un libellé non vide (BR-20). Les deux contrôles sont **bloquants** au clic "Ajouter l'EAN" (validation du formulaire avant insertion mémoire). Tant que l'un des champs est invalide ou vide, le bouton "Ajouter l'EAN" reste à l'état `disabled`.
- BR-7: **Persistance différée (in-memory jusqu'au Save)** — toute mutation de la collection EAN (ajout manuel, import CSV, suppression unitaire, suppression totale) opère **uniquement en mémoire côté SPA**. La persistance en base ne se déclenche que lors du Save explicite via les boutons "Suivant" ou "Sauvegarder et quitter". Tant que ces boutons ne sont pas cliqués, fermer/refresh la page perd les modifications EAN (mitigé par BR-26 dialog confirm).
- BR-8: L'import CSV respecte strictement le template fourni : colonnes `ean;libelle` (séparateur `;`), encodage UTF-8, première ligne = header, ordre des colonnes strict.
- BR-9: L'accès à la page est conditionné à un utilisateur authentifié via Azure AD (JWT Bearer + HTTPS + cookies HttpOnly+Secure ; cf. spec `1-authentification`).
- BR-10: La création de campagne échoue si l'un des champs obligatoires (annonceur, marque, dates, nom) est manquant.
- BR-11bis: **Contrat field naming (DTO payload)** — le champ libellé de campagne expose **`nom`** côté API publique (input ET output DTO), conformément au libellé UI `Nom de la campagne` (cf. FEAT 3 BR-5 + mockup `4-1-Informations-Generales.html` ligne 419). Mapping interne backend : DTO.`nom` ↔ Entity `Compagne.libelle` (DB column). Aucune autre divergence de naming admise entre l'API et le formulaire (les keys DTO front et back DOIVENT être identiques : `nom`, `description`, `fkAnnonceur`, `fkMarque`, `dateDebut`, `dateFin`).
- BR-11: **Contrat REST URL canonique** — tous les endpoints sous `/api/v1/` au pluriel :
  - `POST /api/v1/campagnes` → 201 + `Location: /api/v1/campagnes/{id}`
  - `PUT /api/v1/campagnes/{id}` → 200 + body mis à jour
  - `GET /api/v1/campagnes/{id}` → 200
  - `GET /api/v1/annonceurs` / `GET /api/v1/marques` → 200 listes
  - `GET /api/v1/campagnes/{campagneId}/eans` → 200 collection EAN
  - `DELETE /api/v1/campagnes/{campagneId}/eans` → 204 (suppression totale scope campagne — appelée en interne par l'opération Save uniquement, pas exposée à un bouton UI direct)
  - `POST /api/v1/campagnes/{campagneId}/eans/bulk` → 201 (insertion batch transactionnelle de la collection finale)
  Aucun endpoint singulier (`/ean`, `/annonceur`, `/marque`) ni verbe RPC. Le template CSV n'est PAS exposé par le backend (cf. BR-12).
- BR-12: **Template CSV statique** — `ean-template.csv` est livré dans les assets publiés du frontend (`public/assets/` pour Vite, `wwwroot/assets/` pour Blazor). URL relative `/assets/ean-template.csv`. Le bouton "Télécharger modèle" est un lien HTML statique (`<a href="/assets/ean-template.csv" download>`), aucun appel backend.
- BR-13: **Récupération de `campagneId` côté front** — la page reçoit l'identifiant via la query string (`/campagnes/edit?campagneId={guid}`). En édition, lu au mount, propagé aux composants enfants via state SPA. En création, `campagneId` est `null` (collection EAN avec parent ID `null`/`-1`) jusqu'au 1er Save ; le POST campagne retourne l'`id` (header `Location`) et la page met à jour son state + URL (`?campagneId={id}`).
- BR-14: **Structure de routes frontend** — `/campagnes` (liste), `/campagnes/creation` (page Campagne en mode création), `/campagnes/edit?campagneId={id}` (page Campagne en mode édition) sont des **routes sœurs**, pas des modales ni des sections intégrées. Chaque URL rend exactement une page (pas de mélange parent/enfant). Si le routing utilise une convention parent-enfants, le composant parent doit être un layout pass-through.
- BR-14bis: **Nom canonique de la page Campagne — `CampagneInfosPage.tsx`** (load-bearing). Le fichier React qui orchestre les **3 blocs A/B/C** vit dans `src/pages/CampagneInfosPage.tsx` (PAS `CampagneFormPage.tsx`, PAS `CampagnePage.tsx`, PAS autre). Toutes les US dépendantes (4-2 Gestion-EAN, 4-3 Import-CSV, futures FEAT 5/6/7) référencent ce nom littéral dans leur augment contract. Drift de nommage (US 4-1 livre `CampagneInfosPage` mais US 4-2/4-3 augmentent `CampagneFormPage`) = bug **bloquant** : les composants Bloc B/C sont créés mais ne sont jamais montés → la page n'affiche que le Bloc A.
- BR-15: **Affichage ID Campagne** — la zone "Infos générales" affiche un champ "ID Campagne" en **lecture seule** (placeholder `"Ajouter un ID de campagne"` selon mockup actuel, à remplacer par `"Sera généré après création"` en création OU la valeur réelle en édition). Le champ ID n'est jamais inclus dans le payload POST/PUT (généré côté backend).
- BR-16: **Pré-remplissage mode édition** — au mount, la page charge :
  - `GET /api/v1/campagnes/{campagneId}` → pré-remplit Infos générales (combos pré-sélectionnés sur `Fk_annonceur`/`Fk_marque` matchés par `id`, nom, description, dates)
  - `GET /api/v1/campagnes/{campagneId}/eans` → initialise la collection EAN en mémoire avec le résultat
  Si un FK référence un id absent des listes (annonceur/marque supprimé), afficher "Valeur indisponible" et bloquer le Save jusqu'à correction.
- BR-17: **Sub-menu wizard partagé — composition stricte mockup `_shared-4-Menu-Campagne.html`** — la page Campagne s'affiche **dans le shell d'un wizard 4-steps** dont le top bar contient (de gauche à droite) :
  1. **Bouton "Sauvegarder et quitter"** (colonne gauche, icône disquette + libellé verbatim mockup ligne 169).
  2. **Stepper 4 steps** (colonne centre, libellés verbatim mockup lignes 173-191) :
     - **Step 1 — Informations générales** : page de FEAT 4 (cette spec), step actif par défaut au mount, 3 blocs Infos+CSV+EAN. **Libellé exact = `Informations générales` (PAS `Campagne`)** — verbatim mockup ligne 175.
     - **Step 2 — Périmètre** : page à livrer par FEAT 5 (visible dans le menu, navigable via "Suivant" qui pointe vers `/campagnes/edit/perimetre` — placeholder "Page à venir" tant que FEAT 5 n'est pas implémentée)
     - **Step 3 — Contenus** : page à livrer par FEAT 6 (visible dans le menu)
     - **Step 4 — Récapitulatif** : page à livrer par FEAT 7 (visible dans le menu)
  3. **Groupe "Retour" + "Suivant"** (colonne droite, icône flèche-gauche + libellés verbatim mockup lignes 199 + 201). **Ces 2 boutons vivent uniquement dans le top bar du wizard — interdit de les dupliquer en bas du formulaire**.
  Le step actif est mis en évidence visuellement. Tous les libellés viennent du mockup HTML, source de vérité visuelle.
- BR-18: **Suppression unitaire EAN (en mémoire)** — chaque ligne de la grille EAN affiche un bouton delete (icône poubelle) qui retire la ligne de la **collection en mémoire** uniquement (aucune persistance immédiate). La grille se rafraîchit automatiquement. La ligne n'est définitivement perdue qu'au prochain Save (qui exécute DELETE all + bulk insert de la collection restante).
- BR-19: **Validation EAN — chiffres uniquement** — la valeur d'un EAN doit matcher `^[0-9]+$`. Espaces, lettres, accents, symboles, séparateurs sont **rejetés**. S'applique au formulaire d'ajout manuel (bloquant) et à chaque ligne du CSV importé (skip ligne, traitement continue).
- BR-20: **Validation libellé EAN — non vide** — chaîne non vide après trim. Whitespace seul rejeté. S'applique manuel (bloquant) et CSV (skip).
- BR-21: **Popup d'erreur d'import CSV** — à la fin d'un import ayant rejeté ≥ 1 ligne (BR-19/20), un popup **rouge clair** (dismissable, non bloquant) s'affiche dans la zone d'import listant :
  - Nombre total de lignes lues, validées, rejetées
  - Pour chaque rejet : numéro de ligne CSV + raison (`EAN manquant`, `EAN non numérique : "{valeur}"`, `Libellé manquant`)
  Les lignes valides sont quand même ajoutées (import **partiel**, pas tout-ou-rien).
- BR-22: **Bouton "Suivant" (top bar wizard)** — déclenche la séquence Save complète : (1) POST campagne (création) ou PUT campagne (édition) avec Infos générales, (2) DELETE all EAN de la campagne, (3) POST bulk EAN avec la collection finale en mémoire. Puis navigation vers `/campagnes/edit/perimetre?campagneId={id}` (Step 2 = FEAT 5, page placeholder "À venir" tant que FEAT 5 non livrée). Sur erreur HTTP backend : reste sur la page courante + message d'erreur, ne perd pas la collection en mémoire.
- BR-23: **Bouton "Sauvegarder et quitter" (top bar wizard)** — déclenche la même séquence de persistance que BR-22, puis redirige vers `/campagnes` (liste). Visible dès le Step 1 (= dès FEAT 4).
- BR-24: **Bouton "Retour" / "Annuler"** — restaure l'état "dernier Save connu" : en mode édition, recharge `GET /api/v1/campagnes/{id}` + `GET /api/v1/campagnes/{campagneId}/eans` ; en mode création antérieur au 1er Save, vide la collection EAN et reset le form. **Aucune persistance backend**.
- BR-25: **Sanitization libellé EAN (anti-XSS)** — validation JSR-303 backend sur DTO EanInputDto : `@Pattern(regexp = "^[^<>\"'&\\x00]+$", message = "Libellé contient des caractères interdits")` ; rejet 400 ProblemDetails sur violation. Frontend : escaping JSX natif sur tout rendu de libellé (`{ean.libelle}`), **interdire** `dangerouslySetInnerHTML`.
- BR-30: **Queries au mount — endpoints backed-by-DB uniquement** — la page Campagne (mode `create` ou `edit`) n'invoque au mount QUE des endpoints **explicitement déclarés en BR-11** ET backed par une entité scaffoldée en DB (cf. CMSPrintBack entities : `Annonceur`, `Marque`, `Compagne`, `Ean`, `Enseigne`, `Statut`, …). Endpoints autorisés :
  - Mode `create` : `GET /api/v1/annonceurs` + `GET /api/v1/marques` (combos). **Aucun autre appel** — formulaire vierge sinon.
  - Mode `edit` (campagneId présent) : idem + `GET /api/v1/campagnes/{id}` + `GET /api/v1/campagnes/{id}/eans`.
  Tout appel à un endpoint phantom (sans entité DB, sans déclaration BR-11) — exemple historique : `/api/v1/types-appareil` — est **interdit** : il produit un 404 systématique et un état "Valeur indisponible" parasite.
- BR-26: **Prévention perte de données (beforeunload + router guard)** — composant page maintient un drapeau `isDirty` (true dès la 1ère mutation locale depuis le dernier Save). Tant que `isDirty == true` :
  - `window.beforeunload` retournant `event.preventDefault()` + `event.returnValue = ""` → dialog natif navigateur
  - Guard router frontend (`useBlocker` TanStack/RR v6.4+) → dialog modal applicatif "Modifications non sauvegardées — êtes-vous sûr de quitter ?" (actions : Quitter sans sauver / Annuler / Sauvegarder et quitter)
  Reset `isDirty` à false après chaque Save (BR-22/23) ou Retour/Annuler (BR-24).
- BR-27: **Index DB composé `(fk_campagne, ean)` sur table `ean`** — `CREATE INDEX idx_ean_campagne_ean ON ean(fk_campagne, ean);` à matérialiser dans la migration DB scaffoldée par arch (à vérifier dans `workspace/output/db/schema.{json,md}` et compléter via migration explicite si manquant).
- BR-28: **Pagination + tri frontend de la grille EAN** — la grille EAN est paginée **client-side** (le backend retourne la collection complète via `GET /api/v1/campagnes/{campagneId}/eans` sans pagination ; le composant grid SPA paginate localement). Lignes par page configurables : 5 (défaut) / 10 / 25 / 50. Tri par colonne EAN et Libellé (asc/desc). Affichage du compteur "X-Y de Z" et navigation paginée (prev/next + numéros). **Pas de pagination backend** (out of scope).
- BR-29: **FAQ inline "Comment préparer la liste de produits à importer ?"** — composant accordion repliable sous la dropzone d'import. Contenu statique côté SPA (texte ou markdown bundle, pas d'appel API). Au clic, déplie/replie. Contient des règles de format CSV (séparateur, encodage, header, exemples).

## Acceptance Criteria

- AC-1: La page affiche un combo annonceur peuplé depuis `GET /api/v1/annonceurs` (sélection unique)
- AC-2: La page affiche un combo marque peuplé depuis `GET /api/v1/marques` (sélection unique, placeholder singulier `"Sélectionner une marque"`)
- AC-3: Le nom de la campagne est **auto-suggéré** au format `{Marque}_{DateDebut}` dès que les 2 champs sont renseignés ET le champ reste **éditable** (input texte normal). L'utilisateur peut accepter la suggestion ou la remplacer. La valeur soumise est celle du champ au submit.
- AC-4: La description est saisissable librement
- AC-5: La création/édition de campagne est possible dès que tous les champs obligatoires sont valides (annonceur, marque, dates, nom)
- AC-6: L'ajout manuel d'un EAN (Bloc B : champs code + libellé + bouton "Ajouter l'EAN") — déclenche une validation locale bloquante (BR-6, BR-19, BR-20), insère la ligne dans la **collection en mémoire**, rafraîchit la grille (Liste produits animés). Aucun appel backend.
- AC-7: Le bouton "Tout supprimer" (au-dessus de la grille) **vide la collection EAN en mémoire** après confirmation, rafraîchit la grille (devient vide). Aucun appel backend immédiat — la perte effective ne se produit qu'au prochain Save.
- AC-8: L'import CSV (Bloc C dropzone) : (1) lit le fichier sélectionné côté front, parse `ean;libelle`, (2) applique BR-19 + BR-20 ligne par ligne, (3) ajoute les lignes valides à la collection EAN en mémoire (invalides skipped), (4) si ≥ 1 rejet → affiche popup BR-21 récap, (5) la grille se rafraîchit. **Aucun appel backend** déclenché par l'import.
- AC-9: Le bouton "Télécharger modèle" (Bloc C en-tête) est un lien HTML statique vers `/assets/ean-template.csv` (servi par le SPA), aucun appel API.
- AC-10: Un CSV au template invalide (colonnes absentes, encodage corrompu, fichier non-CSV) est refusé **avant la validation ligne-par-ligne** avec message explicite ; la collection EAN reste inchangée.
- AC-11: En mode création (`/campagnes/creation`, sans `campagneId` en query string), tous les blocs (A/B/C) sont accessibles avant tout Save backend : la collection EAN utilise `campagneId = null`. Le 1er Save (Suivant ou Sauvegarder et quitter) crée la campagne via `POST /api/v1/campagnes`, récupère l'`id`, déclenche immédiatement le bulk insert EAN si la collection n'est pas vide, met à jour l'URL avec `?campagneId={id}`.
- AC-12: La zone "Infos générales" affiche un champ "ID Campagne" en lecture seule (BR-15). En création : placeholder approprié. En édition : valeur lue depuis `?campagneId={guid}` affichée dès le mount.
- AC-13: En mode édition, la page exécute `GET /api/v1/campagnes/{campagneId}` ET `GET /api/v1/campagnes/{campagneId}/eans` au mount, pré-remplit Infos (combos pré-sélectionnés sur `Fk_annonceur`/`Fk_marque`, nom, desc, dates) et initialise la collection EAN avec le résultat du GET EAN. Si FK référence id absent des listes, afficher "Valeur indisponible" et bloquer le Save.
- AC-14: Le sub-menu wizard (top bar partagé `_shared-4-Menu-Campagne.html`) affiche les 4 steps (Campagne / Périmètre / Contenus / Récapitulatif) avec Step 1 actif. Les Steps 2-3-4 sont visibles dans le menu mais leur clic direct dans le menu (sans passer par "Suivant") peut être désactivé ou afficher "Page à venir" tant que FEAT 5/6/7 ne sont pas livrées.
- AC-15: La grille EAN affiche un bouton delete par ligne (icône poubelle). Le clic retire la ligne de la **collection en mémoire** uniquement (BR-18), rafraîchit la grille, sans appel backend.
- AC-16: Une saisie manuelle d'EAN avec valeur non numérique (lettres, espaces, symboles, accents) est rejetée au clic "Ajouter l'EAN" avec message d'erreur sous le champ ; le bouton reste disabled tant que la valeur est invalide. Aucune insertion dans la collection.
- AC-17: Une saisie manuelle d'EAN avec libellé vide (ou whitespace seul) est rejetée au clic "Ajouter l'EAN" avec message d'erreur sous le champ. Aucune insertion.
- AC-18: L'import CSV produit un popup rouge clair (BR-21) listant les lignes rejetées avec leur numéro CSV + raison précise (`EAN manquant`, `EAN non numérique : "ABC123"`, `Libellé manquant`). Popup dismissable, n'empêche pas l'utilisation de la page.
- AC-19: Le bouton "Suivant" (top bar) déclenche la séquence Save (BR-22) puis navigation vers `/campagnes/edit/perimetre?campagneId={id}`. En V1 (FEAT 5 non livrée), la page cible est un placeholder "Périmètre — à venir". Sur erreur backend, reste sur la page courante + message, collection en mémoire préservée.
- AC-20: Le bouton "Sauvegarder et quitter" (top bar, visible dès FEAT 4) déclenche la persistance complète (BR-23) puis redirige vers `/campagnes`. Sur erreur backend, reste sur la page courante + message.
- AC-21: Le bouton "Retour" / "Annuler" restaure l'état dernier-Save-connu sans persister (BR-24). En édition : reload depuis backend. En création antérieure au 1er Save : reset state mémoire.
- AC-22: Une tentative de fermeture/refresh/navigation alors que `isDirty == true` déclenche un dialog confirm (natif `beforeunload` ou modal applicatif selon nav). Si l'utilisateur annule, il reste sur la page avec la collection EAN intacte. Si l'utilisateur confirme, modifs non sauvegardées perdues (sauf option "Sauvegarder et quitter" intégrée au modal in-SPA). Après tout Save (BR-22/23) ou Retour (BR-24), `isDirty == false` et le warning ne se déclenche plus.
- AC-23: Une tentative d'ajout EAN (manuel OU CSV) avec libellé contenant `<`, `>`, `"`, `'`, `&`, `\0` est rejetée au Save par le backend (400 ProblemDetails avec détail du champ). Côté frontend, tout libellé EAN est rendu via escaping JSX (`{ean.libelle}`), jamais `dangerouslySetInnerHTML`. Vérifiable par test : libellé `<script>alert(1)</script>` ne provoque aucune exécution JS au rendu.
- AC-24: La table `ean` du schéma DB porte un index composé `idx_ean_campagne_ean` sur `(fk_campagne, ean)`. Vérifiable via `EXPLAIN ANALYZE DELETE FROM ean WHERE fk_campagne = ?` qui utilise l'index (pas de Seq Scan).
- AC-25: La grille EAN paginée côté frontend affiche 5 lignes par défaut, avec selector "Lignes par page" (5/10/25/50) et navigation paginée (prev/next + numéros de page). Tri cliquable sur colonnes EAN et Libellé (asc/desc). La pagination/tri opère sur la collection en mémoire complète, **aucun appel backend** déclenché par changement de page ou tri.
- AC-26: Une FAQ accordion "Comment préparer la liste de produits à importer ?" (BR-29) est présente sous la dropzone d'import CSV, repliable au clic, contenu statique inline (pas d'API).
- AC-27: **3 blocs montés simultanément (cf. BR-14bis)** — au runtime de `/campagnes/creation` ET `/campagnes/edit`, la page `CampagneInfosPage.tsx` doit afficher dans l'ordre vertical du mockup : (1) Bloc A `<CampagneInfosForm>` (US 4-1), (2) Bloc C `<EanImportBlock>` (US 4-3), (3) Bloc B `<EanManager>` (US 4-2 — ajout manuel + grille paginée). Une page qui n'affiche que le Bloc A est un bug **bloquant** : vérifier que les augment-contracts des plans US 4-2 et 4-3 ciblent bien `CampagneInfosPage.tsx` (PAS `CampagneFormPage.tsx`).
- AC-28: **Bouton "Suivant" déclenche la persistance EAN AVANT navigation (cf. BR-22)** — la séquence Save complète (POST/PUT campagne → DELETE all EAN → POST bulk EAN) doit être appelée depuis `CampagneInfosPage` via la handle impérative `eanManagerRef.current.persist(items)` exposée par `<EanManager>`. Sans cet appel, la collection EAN est perdue au moment du Save.

## Dependencies

- 1-authentification (utilisateur connecté + claims Azure AD)
- 2-menu (navigation, depuis "Créer campagne" sur la vue liste)
- 3-campagnes-vue-liste (bouton "Créer campagne" → `/campagnes/creation` ; clic ligne → `/campagnes/edit?campagneId={guid}`)
- Backend `GET /api/v1/annonceurs`, `GET /api/v1/marques`
- Backend `POST /api/v1/campagnes` (201 + Location), `PUT /api/v1/campagnes/{id}` (200), `GET /api/v1/campagnes/{id}` (200)
- Backend EAN (`GET /api/v1/campagnes/{campagneId}/eans` collection complète sans pagination ; `DELETE /api/v1/campagnes/{campagneId}/eans` 204 ; `POST .../eans/bulk` 201)
- Fichier statique `assets/ean-template.csv` livré dans les assets publiés du frontend
- Base PostgreSQL contenant `campagne`, `annonceur`, `marque`, `ean` (index composé `(fk_campagne, ean)` requis cf. BR-27)
- Composant SPA partagé `_shared-4-Menu-Campagne.html` (wizard top bar avec 4 onglets + bouton "Sauvegarder et quitter")
- Composant SPA grille paginée avec tri client-side (TanStack Table ou équivalent stack frontend)
- Composant SPA popup d'alerte rouge clair, dismissable
- FEATs futures déclarées dans le sub-menu mais non implémentées en V1 : FEAT 5 (Périmètre), FEAT 6 (Contenus), FEAT 7 (Récapitulatif)

## Functional Deliverables

- FD-1: Page Campagne (création/édition) — écran unique intégrant 3 blocs verticalement (mockup `4-1-Informations-Generales.html`)
- FD-2: Bloc A — Infos générales : ID Campagne (read-only), Nom (auto-suggéré éditable), Description, Combo Annonceur, Combo Marque (placeholder singulier)
- FD-3: Combo annonceur (sélection unique) alimenté via `GET /api/v1/annonceurs`
- FD-4: Combo marque (sélection unique) alimentée via `GET /api/v1/marques`
- FD-5: Génération automatique du nom au format `{Marque}_{DateDebut}`
- FD-6: Bloc C — Import CSV : dropzone (max 50 MB .CSV) + bouton "Télécharger modèle" (lien statique vers `/assets/ean-template.csv`) + FAQ accordion inline "Comment préparer la liste de produits à importer ?"
- FD-7: Bloc B — Ajout unitaire EAN : `ean-row` avec input EAN, input Libellé, bouton "Ajouter l'EAN" (disabled tant que invalide)
- FD-8: Grille "Liste des produits animés" — table EAN/Libellé sourcée depuis la collection en mémoire, avec bouton delete par ligne, bouton "Tout supprimer" en en-tête, pagination + tri frontend (5/10/25/50 lignes/page, navigation prev/next/numéros, tri asc/desc sur chaque colonne)
- FD-9: Fichier `ean-template.csv` livré sous `public/assets/` (Vite) ou `wwwroot/assets/` (Blazor) avec header `ean;libelle` + 2-3 lignes exemple
- FD-10: Endpoints campagne — `POST /api/v1/campagnes` (201 + Location), `PUT /api/v1/campagnes/{id}` (200), `GET /api/v1/campagnes/{id}` (200)
- FD-11: Endpoints EAN sous `/api/v1/campagnes/{campagneId}/eans` : `GET` collection complète, `DELETE` total (interne au Save), `POST /bulk` insertion batch transactionnelle
- FD-12: Endpoints `GET /api/v1/annonceurs` et `GET /api/v1/marques` (listes pluriel)
- FD-13: Composant SPA partagé `_shared-4-Menu-Campagne` (wizard top bar 4 steps + boutons "Sauvegarder et quitter" + "Suivant" + "Retour/Annuler")
- FD-14: État partagé SPA (context React, store Pinia/Vuex ou équivalent) qui héberge : `campagneId` (null/guid), Infos générales (form state), collection EAN en mémoire, drapeau `isDirty`
- FD-15: Composant SPA popup d'alerte rouge clair, dismissable
- FD-16: Service SPA `campagneSaveService` orchestrant la séquence Save : POST/PUT campagne, DELETE all EAN, POST bulk EAN, mise à jour URL `?campagneId={id}` en création
- FD-17: Service SPA `csvImportService` parsant + validant ligne-par-ligne le CSV, retournant `{validRows, rejectedRows: [{lineNumber, reason}]}`
- FD-18: Guards SPA `isDirty` + `window.beforeunload` + `useBlocker` router + dialog modal applicatif "Modifications non sauvegardées"
- FD-19: Validation JSR-303 backend sur DTO `EanInputDto` (`@Pattern` reject `<>"'&\0`) renvoyant 400 ProblemDetails
- FD-20: Migration DB scaffoldée pour index composé `idx_ean_campagne_ean ON ean(fk_campagne, ean)` (Flyway/Liquibase ou SQL natif, idempotent)
- FD-21: Composant FAQ accordion statique sous la dropzone CSV (contenu inline, repliable)

## Out of Scope

**Hors scope FEAT 4 (V1)** — couvert par les FEATs suivantes du wizard :

- Step 2 "Périmètre" — page à livrer par **FEAT 5**
- Step 3 "Contenus" — page à livrer par **FEAT 6**
- Step 4 "Récapitulatif" — page à livrer par **FEAT 7**

**Hors scope FEAT 4 (et toutes FEATs wizard V1)** :

- Validation métier avancée des EAN (checksum GTIN-13, format ISO, format pays, longueur min/max) — FEAT séparée future
- Sauvegarde automatique (auto-save) périodique
- Pagination **backend** de la collection EAN (`GET /eans` retourne tout sans pagination) — la pagination est purement frontend (BR-28)
- Versioning / historisation des fichiers CSV importés
- Recherche / filtrage texte dans la grille EAN
- Création multi-annonceur ou multi-marque par campagne
- Édition unitaire d'un EAN existant dans la grille (seuls add/delete sont supportés)
- Sauvegarde partielle granulaire EAN (DELETE/POST par ligne) — la stratégie est toujours DELETE all + bulk insert au Save
- Annulation granulaire (undo/redo) sur les mutations de la collection EAN
- Anti-formule Excel à l'export (pas d'export CSV/Excel dans FEAT 4, à anticiper si une FEAT future ajoute un export)
- **Champ "Type d'appareil" et endpoint `/api/v1/types-appareil`** — aucune table `type_appareil` n'existe en DB, aucun champ correspondant n'est présent dans le mockup HTML, aucun endpoint backend n'est exposé. Toute génération de hook `useTypesAppareil` / d'appel `GET /api/v1/types-appareil` / de champ `fkTypeAppareil` dans le schéma de form est **interdite** (cf. SFD-4 résolution + BR-30).
- Mode multi-onglets navigateur sur la même campagne (last-write-wins acceptable V1)

## Risques Identifiés

- Erreurs de format CSV (encodage, séparateur, BOM) → mitigé par validation stricte et popup récap
- Doublons d'EAN dans la même collection en mémoire (ajout manuel ou import) → comportement par défaut : skip silencieux + ligne ajoutée au popup récap, raison `Doublon` ; alternative à valider
- Timeout sur import massif (>10k EAN) au moment du Save (DELETE all + bulk insert) → considérer pagination du bulk côté backend si nécessaire ; index composé BR-27 mitige
- Incohérence marque/annonceur sélectionnés (hors check métier)
- Génération auto du nom impossible si marque ou date de début non renseignées → champ nom reste éditable manuellement
- Perte de la collection EAN en mémoire si fermeture/refresh sans Save → mitigé par BR-26 dialog confirm + `beforeunload`
- Stratégie DELETE all + bulk insert au Save → risque de last-write-wins si édition concurrente multi-user → acceptable V1
- Performance pagination/tri frontend dégradée si collection > 10k EAN → considérer virtualisation (TanStack virtual) si nécessaire

## Hypothèses

- Les endpoints `/annonceurs` et `/marques` sont stables et retournent des listes en ordre alphabétique
- Le backend gère le bulk insert transactionnel des EAN (rollback automatique sur échec partiel)
- ~~Le type d'appareil est une donnée saisissable dans le step 1~~ → **résolu (négatif)** : aucun champ "type d'appareil" n'est livré. Pas de table `type_appareil` en DB, pas de représentation dans le mockup HTML, pas d'endpoint `/api/v1/types-appareil` exposé. Le format d'auto-suggestion devient `{Marque}_{DateDebut}` (cf. SFD-4 / BR-1 / AC-3).
- Les performances DELETE all + bulk insert restent acceptables pour campagnes < 10 000 EAN (à mesurer)
- Le SPA dispose d'un mécanisme d'état partagé pour propager la collection EAN entre Infos/CSV/Grille
- Le composant grille (TanStack Table ou équivalent) supporte pagination + tri client-side nativement
- Le sub-menu wizard est cohérent avec le design system shadcn déjà actif

## Cas Limites

- CSV vide ou invalide → import refusé avec message explicite, collection EAN inchangée
- CSV avec **toutes** les lignes invalides → popup rouge clair affiche le récap, collection inchangée
- EAN déjà existant dans la collection en mémoire (doublon ajout manuel ou CSV) → skip silencieux + ligne au popup, raison `Doublon`
- Annulation upload en cours → état stable (pas d'ajout partiel)
- Aucune marque ou aucun annonceur disponible en base → message bloquant la création + désactivation du combo
- Date début non saisie → nom auto-généré incomplet, l'utilisateur peut saisir le nom manuellement
- Click "Suivant" alors que collection EAN est vide → autorisé, Save propage collection vide
- Click "Retour" / "Annuler" en mode création antérieur au 1er Save → reset state mémoire, retour à `/campagnes`
- Connexion perdue au moment du Save → erreur backend bubble up, collection en mémoire préservée, retry possible
- Grille EAN avec ≥ 10 000 lignes → pagination frontend peut être lente sans virtualisation (à mesurer)

## Parties Prenantes

- Product Owner (décide format CSV, règles validation EAN, arbitrage strictness vs adoption)
- Équipe Frontend (page Campagne 3 blocs, grille paginée, popup, drapeau isDirty, FAQ accordion, composant wizard partagé)
- Équipe Backend (endpoints campagne + EAN bulk, validation JSR-303 anti-XSS)
- Data team (perf DELETE+bulk insert, index composé `(fk_campagne, ean)`, monitoring queries)
- Sécurité (sanitization libellé XSS, politique escape rendu)
- Utilisateurs marketing (UX page, taux de rejet CSV réel)

## Modes de Défaillance

- API `/annonceurs` ou `/marques` indisponible → combos vides + message d'erreur
- Erreur de parsing CSV (format invalide) → import refusé, collection inchangée
- Échec bulk insert EAN au Save → transaction annulée backend, collection en mémoire préservée, message d'erreur
- DELETE all préalable au bulk échoue → opération avortée avant bulk, collection préservée
- Perte de la collection EAN suite à refresh inopiné (avant Save) → BR-26 mitige via `beforeunload` + router guard ; en mode édition, recharge depuis backend
- Nom de campagne mal généré (données incomplètes) → bouton "Suivant"/"Sauvegarder et quitter" disabled jusqu'à saisie manuelle
- Session Azure AD expirée → 401 → redirection login (préserve l'URL pour reprise après auth)
- Erreur réseau ponctuelle au Save → reste sur la page, message d'erreur, retry possible
- Grille EAN avec collection vide → affiche état "empty" (icône + message "Aucun produit animé pour cette campagne")
- Navigation vers Step 2 (FEAT 5 non livrée) → affichage placeholder "Périmètre — à venir" sans crash

---

# Élicitation structurée (feat-deepen 2026-05-18)

Sections enrichies via 5 techniques d'élicitation, retenues après le **recentrage scope FEAT 4 = Step 1 uniquement** (les contre-mesures liées aux Steps 2/3/4 sont déplacées vers les FEATs 5/6/7 futures).

## Pre-mortem — projection 6 mois post-livraison

Trois causes d'échec probables identifiées par le PO :

1. **Validation CSV trop stricte** — le pattern BR-19 (`^[0-9]+$`) rejette les fichiers réels des annonceurs contenant des EAN avec tirets, espaces, séparateurs. Risque : 80% des imports échoués → utilisateurs reviennent à la saisie manuelle / Excel partagé → adoption nulle.
   - **Contre-mesure à arbitrer PO** (non intégrée par défaut) : pré-traitement automatique du CSV (strip whitespace + `-` + `.`) avant validation `^[0-9]+$`.
2. **Bulk insert lent / timeout sur > 10k EAN** — la séquence `DELETE all + bulk insert` est mono-transactionnelle. Au-delà d'un certain volume, le timeout HTTP (défaut 30s) ou la transaction PostgreSQL deviennent bloquants.
   - **Contre-mesures** : index composé BR-27 (intégré), pagination du bulk backend (out of scope V1), augmenter timeout HTTP.
3. **Perte données in-memory (refresh accidentel)** — sans `beforeunload` warning, l'utilisateur perd 30 min de saisie EAN au moindre F5 / crash navigateur.
   - **Contre-mesure intégrée BR-26** : `beforeunload` + `useBlocker` router guard avec dialog confirm.

## First Principles — hypothèses non questionnées

(Technique passée par le PO. Hypothèses à reconsidérer si la FEAT évolue : `1 campagne = 1 annonceur + 1 marque unique` ; `DELETE all + bulk insert acceptable` ; `EAN strictement numérique`.)

## Red Team — scénarios adverses

1. **Injection CSV (formules Excel, XSS dans libellé)** — Backend valide via BR-25 (JSR-303 `@Pattern`), Frontend escape JSX natif. Anti-formule Excel = hors scope V1 (pas d'export).
2. **Browser back / refresh / close avec données non sauvegardées** — BR-26 mitige via `beforeunload` + router guard.
3. **Multi-onglets navigateur sur même campagne** — hors scope V1 (last-write-wins acceptable).

## Stakeholder Mapping (RACI)

| Stakeholder | R / A / C / I | Responsabilité |
|---|---|---|
| PO Marketing | **A** | Décide format CSV + règles métier validation EAN + arbitrage adoption vs strictness |
| Data team | **R** sur perf bulk + schema | Valide perf DELETE+bulk ; ajoute index BR-27 ; surveille EXPLAIN ANALYZE en pré-prod |
| Sécurité | **R** sur sanitization | Définit politique escape XSS sur libellé EAN ; revue code points d'entrée upload CSV |
| Équipe Frontend | R | Page Campagne 3 blocs, état partagé, popup, `beforeunload`/`useBlocker`, grille paginée, FAQ accordion, composant wizard partagé |
| Équipe Backend | R | Endpoints campagne + EAN, validation JSR-303 |
| Utilisateurs marketing | C / I | Testent UX, signalent rejets CSV faux-positifs |

**Note forward-looking** : contrôles EAN avancés (longueur min/max, checksum GTIN, format pays) reportés à une FEAT séparée post-MVP.

## Inversion — comment garantir l'échec et défenses associées

| Façon de saboter | Défense |
|---|---|
| Aucun warning sur close/refresh avec données non sauvegardées | **BR-26** intégré : `beforeunload` + `useBlocker` + dialog confirm si `isDirty == true` |
| Pas d'index DB sur `(fk_campagne, ean)` → bulk insert full scan | **BR-27** intégré : `CREATE INDEX idx_ean_campagne_ean ON ean(fk_campagne, ean);` (user a confirmé "c'est fait", à vérifier dans schema scaffold) |
| Page ne sauvegarde rien jusqu'à fermeture utilisateur | **BR-22/23** intégrés : Suivant + Sauvegarder-et-quitter déclenchent persistance complète. In-memory uniquement INTRA-page (pas de Save automatique). |

## Items intégrés post-élicitation

Suite à l'élicitation, items **promus en règles load-bearing** dans la spec :

- **BR-25** (Sanitization libellé EAN) — intégré ; AC-23 ; SFD-19 ; FD-19
- **BR-26** (beforeunload + router guard) — intégré ; AC-22 ; SFD-18 ; FD-18
- **BR-27** (Index DB composé) — intégré ; AC-24 ; SFD-20 ; FD-20

**Items NON intégrés (à arbitrer ultérieurement)** :

- **Normalisation pré-validation EAN** (strip whitespace + `-` + `.`) — décision PO différée, à reconsidérer après mesure du taux de rejet réel.
- **Contrôles EAN avancés** (longueur min/max, checksum GTIN-13) — FEAT séparée post-MVP.
- **Anti-formule Excel à l'export** — pas applicable V1 (pas d'export prévu).
