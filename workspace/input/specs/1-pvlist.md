# Spec: pvlist

Spec ID: 1-pvlist
Status: Draft

## Context

La société SDD-Pro exploite un parc de points de vente issus de contrats signés avec différentes enseignes du retail. Aujourd'hui, ces informations (identifiants, enseignes, formats, surfaces, CATP, adresses, statut d'exploitation) sont dispersées et difficiles à consulter de façon centralisée par l'équipe retail. La plateforme **SIM** (Système d'Information des Magasins) doit offrir une vision globale, structurée et administrable du patrimoine retail, restreinte aux utilisateurs authentifiés via Azure AD.

L'application SIM est structurée en deux composants distincts : un **Frontend** en Blazor qui porte l'expérience utilisateur (authentification, navigation, écrans de consultation et de gestion) et un **Backend** exposé via une **Minimal API** qui porte la logique métier, l'accès aux données et la sécurité. Le Frontend ne parle jamais directement à la base de données : tout transite par le Backend. L'authentification Azure AD est la porte d'entrée unique, et chaque échange entre le Frontend et le Backend est porté par le token Azure AD de l'utilisateur connecté, validé systématiquement côté Backend.

## Objective

Permettre à l'équipe retail d'accéder, via une authentification Azure AD, à une page centralisée listant l'ensemble des points de vente sous contrat avec SDD-Pro, avec recherche, filtrage, pagination et gestion CRUD complète depuis une seule interface, exposée par un Frontend Blazor qui consomme un Backend Minimal API sécurisé par validation JWT à chaque appel.

## Actors

- **Admin retail** (ex. Amélie — équipe retail) : consulte, crée, modifie et supprime les points de vente ; administre le patrimoine PDV.
- **Utilisateur connecté** (via Azure AD) : accède aux fonctionnalités de la plateforme selon ses droits ; dans le périmètre de cette spec, toute connexion Azure AD donne accès admin.

## Functional Needs

- SFD-1: Se connecter à la plateforme via une popup Azure AD avant d'accéder à toute fonctionnalité.
- SFD-2: Arriver sur la page d'accueil "Points de vente" après authentification réussie.
- SFD-3: Consulter la liste des points de vente sous la forme d'un tableau paginé avec les colonnes : ID PDV, Enseigne, Format, Code postal, Commune, Nature Lien, Surface, CATP (K€), Pays, Exploit, Actif, Motif Inactivité, Exploité.
- SFD-4: Voir le nombre total de points de vente directement dans le titre de la page.
- SFD-5: Rechercher un point de vente via une barre de recherche globale qui filtre instantanément le tableau.
- SFD-6: Filtrer le tableau colonne par colonne (code postal, commune, enseigne, format, etc.).
- SFD-7: Paginer le tableau et choisir le nombre de lignes affichées par page parmi plusieurs options.
- SFD-8: Visualiser le statut "Exploité" (OUI / NON) dérivé automatiquement de l'existence d'au moins un périmètre d'exploitation actif pour le PDV.
- SFD-9: Naviguer vers les sections "Périmètre d'exploitation" et "Configuration de redevances" via un menu latéral (les pages cibles sont des placeholders à spécifier ultérieurement).
- SFD-10: Basculer vers une autre plateforme de l'écosystème via un menu dropdown dédié présent dans l'en-tête.
- SFD-11: Accéder au menu utilisateur (avatar) donnant accès à "Voir profil" et "Se déconnecter".
- SFD-12: Créer un nouveau point de vente via un écran dédié.
- SFD-13: Modifier un point de vente existant via un écran dédié.
- SFD-14: Supprimer un point de vente après confirmation explicite.
- SFD-15: Se déconnecter explicitement de la plateforme depuis le menu utilisateur.
- SFD-16: Le Frontend Blazor lit le token Azure AD de la session courante et le transmet sur chaque appel HTTP vers le Backend via l'en-tête `Authorization: Bearer <token>`.
- SFD-17: Le Backend Minimal API valide le JWT Azure AD (signature, émetteur, audience, expiration) à la réception de chaque requête et rejette tout appel dont le token est absent, expiré, mal signé ou dont les claims obligatoires sont manquants.
- SFD-18: Les formulaires de création et de modification d'un point de vente valident les saisies côté Frontend (champs obligatoires, types, longueurs, formats) avant envoi, et affichent des messages d'erreur explicites par champ.
- SFD-19: Le Backend revalide systématiquement les paramètres d'entrée (corps JSON, query string, paramètres de route) dans le pipeline ; toute requête non conforme est rejetée avec un code d'erreur standardisé et un descriptif des champs en erreur, sans atteindre la couche métier.

## Business Rules

- BR-1: Toute fonctionnalité de la plateforme est inaccessible sans authentification Azure AD préalable.
- BR-2: Un utilisateur authentifié dans le périmètre de cette spec a les droits CRUD complets sur les points de vente (pas de rôle intermédiaire).
- BR-3: La colonne "Exploité" est calculée : elle vaut "OUI" si au moins un périmètre d'exploitation actif existe pour le point de vente, "NON" sinon.
- BR-4: Les libellés des colonnes "Format", "Nature Lien" et "Motif Inactivité" proviennent d'une table de référence commune (groupes de référence distincts selon la colonne) ; ils ne sont pas saisis en texte libre.
- BR-5: Un point de vente possède un statut "Actif" indépendant de son statut "Exploité" (un PDV peut être actif mais non exploité).
- BR-6: La suppression d'un point de vente est une action définitive et requiert une confirmation explicite de l'utilisateur.
- BR-7: Le nombre total de PDV affiché dans le titre reflète l'ensemble des points de vente existants (avant application de la recherche et des filtres), pas seulement la page courante.
- BR-8: L'application est structurée en deux composants distincts : un Frontend Blazor et un Backend Minimal API. Le Frontend ne possède aucun accès direct à la base de données ; toutes les opérations de lecture et d'écriture passent par le Backend.
- BR-9: Chaque appel HTTP du Frontend vers le Backend DOIT porter le token Azure AD de l'utilisateur dans l'en-tête `Authorization: Bearer <token>`. Aucune requête anonyme n'est émise par le Frontend vers le Backend.
- BR-10: Le Backend DOIT valider le JWT Azure AD (signature via les clés publiques du tenant, émetteur, audience, durée de validité) à chaque requête entrante. Toute requête sans token valide est rejetée avec un code 401 avant toute exécution de logique métier.
- BR-11: Toute requête dont les claims requis (identité utilisateur, tenant) sont manquants ou incohérents est rejetée avec un code 401 ou 403, sans fuite d'information sur la cause exacte au-delà du strict nécessaire.
- BR-12: Les formulaires de création et de modification d'un point de vente sont validés côté Frontend (champs obligatoires, types, longueurs, formats métier) avant émission de l'appel Backend. Aucun appel Backend n'est émis tant que la validation Frontend n'est pas satisfaite.
- BR-13: Le Backend revalide systématiquement les paramètres d'entrée reçus (corps JSON, query string, paramètres de route) via le pipeline de validation, indépendamment de la validation Frontend. La validation Frontend ne dispense jamais la validation Backend.
- BR-14: Toute requête Backend dont les paramètres d'entrée sont invalides est rejetée avec un code 400 et un descriptif standardisé des champs en erreur, sans atteindre la couche métier ni la base de données.

## Acceptance Criteria

- AC-1: Un utilisateur non authentifié est systématiquement redirigé vers la popup Azure AD avant tout accès à une page fonctionnelle.
- AC-2: Après authentification Azure AD réussie, l'utilisateur est redirigé vers la page "Points de vente".
- AC-3: Le tableau de la page "Points de vente" affiche les treize colonnes listées dans les SFD avec les libellés exacts indiqués.
- AC-4: La barre de recherche globale filtre les lignes du tableau sur l'ensemble des colonnes textuelles pendant la frappe.
- AC-5: Chaque colonne du tableau expose un filtre individuel (texte, sélection ou plage selon le type de donnée).
- AC-6: Le sélecteur de taille de page propose au moins trois valeurs (ex. 10, 25, 50) et la valeur choisie est appliquée immédiatement.
- AC-7: Le titre de la page affiche le nombre total de points de vente sous la forme "Points de vente (N)", où N est le nombre total en base, avant filtrage.
- AC-8: La colonne "Exploité" affiche "OUI" dès qu'au moins un périmètre d'exploitation actif existe pour le PDV, sinon "NON".
- AC-9: La création d'un point de vente est accessible depuis la page liste via une action visible ; le formulaire rassemble les champs métier nécessaires.
- AC-10: La modification d'un point de vente est accessible depuis la page liste ligne par ligne ; le formulaire est pré-rempli avec les valeurs existantes.
- AC-11: La suppression d'un point de vente déclenche une boîte de dialogue de confirmation explicite ; l'action n'est exécutée qu'après validation.
- AC-12: Les entrées de menu "Périmètre d'exploitation" et "Configuration de redevances" sont visibles et cliquables mais redirigent vers des pages placeholders.
- AC-13: Le menu dropdown de bascule de plateforme est visible dans l'en-tête sur toutes les pages.
- AC-14: Le menu utilisateur affiche l'avatar et donne accès à "Voir profil" et "Se déconnecter".
- AC-15: Le clic sur "Se déconnecter" termine la session et redirige vers l'écran d'authentification.
- AC-16: Le Frontend Blazor lit le token Azure AD acquis à la connexion et l'ajoute automatiquement sur chaque requête sortante vers le Backend sous la forme d'en-tête `Authorization: Bearer <token>`.
- AC-17: Le Backend Minimal API expose un middleware d'authentification qui valide le JWT Azure AD à chaque requête entrante (signature, émetteur, audience, expiration) et rejette toute requête sans token valide avec un code 401.
- AC-18: Une requête vers le Backend dont le token est expiré ou invalide reçoit un code 401 sans atteindre la logique métier ; le Frontend déclenche alors une relance d'authentification silencieuse ou redirige vers la popup Azure AD.
- AC-19: Les endpoints Backend n'acceptent aucun appel anonyme ; toute tentative sans en-tête `Authorization` retourne 401 avant exécution.
- AC-20: Les formulaires de création et de modification côté Frontend affichent, pour chaque champ invalide, un message d'erreur explicite (ex. champ obligatoire, format incorrect, longueur max dépassée) et bloquent l'envoi tant que la validation n'est pas verte.
- AC-21: Le Backend applique, dans le pipeline de la Minimal API, une validation automatique des paramètres d'entrée (corps JSON, query string, paramètres de route) ; toute requête invalide est rejetée avec un code 400 et une réponse structurée listant les champs en erreur.
- AC-22: La validation Backend s'exécute avant toute exécution de logique métier et avant tout accès à la base de données ; une entrée invalide ne déclenche jamais d'appel persistant.
- AC-23: Les règles de validation métier (champs obligatoires, longueurs, types, valeurs autorisées via référentiels) sont cohérentes entre Frontend et Backend et produisent le même verdict pour une même saisie.

## Dependencies

- Authentification Azure AD opérationnelle (tenant, app registration, groupes) fournie au niveau infrastructure.
- Base de données SQL Server disposant au minimum des tables : `point_vente`, `enseigne`, `reference_lookup` (groupes de référence 9, 15, 16), `perimetre_exploitation`.
- Backend Minimal API hébergeant les endpoints de gestion des points de vente et exposant le middleware de validation JWT Azure AD.
- Frontend Blazor hébergeant l'interface utilisateur et consommant exclusivement le Backend via HTTP sécurisé par Bearer token.

## Functional Deliverables

- FD-1: Écran d'authentification (popup Azure AD) servant de porte d'entrée à toute la plateforme.
- FD-2: Page d'accueil "Points de vente" avec tableau paginé, barre de recherche globale, filtres par colonne, sélecteur de taille de page et nombre total affiché dans le titre.
- FD-3: Écran de création d'un point de vente, avec validation des champs côté Frontend avant envoi.
- FD-4: Écran de modification d'un point de vente, avec validation des champs côté Frontend avant envoi.
- FD-5: Action de suppression d'un point de vente depuis la page liste, protégée par une confirmation.
- FD-6: Menu de navigation latéral avec entrées "Points de vente", "Périmètre d'exploitation" (placeholder) et "Configuration de redevances" (placeholder).
- FD-7: Menu dropdown de bascule vers une autre plateforme, visible dans l'en-tête.
- FD-8: Menu utilisateur avec avatar donnant accès à "Voir profil" et "Se déconnecter".
- FD-9: Frontend Blazor qui porte toutes les pages, transmet le token Azure AD sur chaque appel Backend et effectue la validation des formulaires côté client.
- FD-10: Backend Minimal API qui expose les endpoints CRUD des points de vente, valide le JWT Azure AD à chaque requête et applique la validation des paramètres d'entrée dans le pipeline avant toute logique métier.
- FD-11: Réponses d'erreur standardisées du Backend : 401 pour token absent ou invalide, 400 pour entrée mal formée ou champs invalides (avec détail par champ), 403 pour accès refusé.

## Out of Scope

- Contenu fonctionnel des pages "Périmètre d'exploitation" et "Configuration de redevances" (seuls les liens du menu et des pages placeholders sont livrés ; le contenu sera spécifié dans une spec ultérieure).
- Implémentation réelle de la bascule vers une autre plateforme (le dropdown est présent dans l'en-tête mais les liens ne redirigent vers aucune plateforme tierce dans cette livraison).
- Export Excel / CSV / PDF de la liste des points de vente.
- Gestion fine des rôles et permissions au-delà de "utilisateur authentifié = admin".
- Audit / historique des créations, modifications et suppressions sur les points de vente.
- Page "Voir profil" détaillée (le lien est présent dans le menu, la page cible est hors scope).
- Import en masse de points de vente.
- Notifications, alertes, emails liés aux opérations CRUD.

---

> Sections enrichies générées par `/spec-deepen 1` (mode interactif —
> élicitation PO confirmée). Items marqués `à valider` à confirmer
> avant `/dev-run`.

## Risques Identifiés

| ID | Risque | Sévérité | Mitigation |
|---|---|---|---|
| RISK-1 | Volumétrie `point_vente` non bornée — pagination/filtrage serveur sous-optimisés au-delà de ~10K lignes dégradent fortement l'UX | medium | pagination serveur obligatoire (jamais en mémoire) ; indexer `code_postal`, `enseigne_id`, `format_id` ; valider sur dataset réaliste avant mise en prod |
| RISK-2 | Expirations de tokens AAD en cascade — relances simultanées saturent le tenant et dégradent toute la plateforme | high | retry exponentiel + jitter côté Frontend (auth silencieuse MSAL) ; circuit-breaker Backend sur rafale de 401 |
| RISK-3 | Règles de validation Frontend (BR-12) divergent du Backend (BR-13/14) — faux verts UX puis rejets 400 frustrants | medium | DTOs + validators partagés via `SIM.Lib` (FluentValidation Backend, mêmes règles Blazor) ; AC-23 à couvrir par tests automatisés |

---

## Hypothèses

| ID | Hypothèse | Statut | Validation requise |
|---|---|---|---|
| ASS-1 | Tous les comptes AAD sont actifs et les groupes correctement assignés avant mise en prod | confirmée | validé par PO — dépendance mentionnée en Dependencies |
| ASS-2 | Les points de vente existent déjà en base SQL Server au moment du premier déploiement (pas de migration de données incluse dans ce périmètre) | à valider | confirmer avec DBA/Data Engineer — si migration à faire, hors scope 1-pvlist à documenter |
| ASS-3 | Le tenant Azure AD est partagé entre plusieurs applications de l'écosystème SDD-Pro (pas d'isolation tenant dédiée SIM) | à valider | confirmer avec SecOps — impacts sur les claims audience (BR-11) et le périmètre des utilisateurs autorisés |

---

## Cas Limites

| ID | Cas limite | Comportement attendu | Couvert par |
|---|---|---|---|
| EDGE-1 | Utilisateur Azure AD authentifié mais hors tenant SDD-Pro (ou hors groupe autorisé) tente d'accéder à une ressource | rejet 403 sans fuite d'information sur la cause exacte (BR-11) ; pas d'exposition du périmètre d'un autre tenant | à ajouter (AC manquante — ambiguïté BR-2 "tout authentifié = admin" vs BR-11 vérification claims tenant) |
| EDGE-2 | Pagination demande un `pageSize` hors limites (0, négatif, > 1000) | Backend retourne 400 avec message structuré ; Frontend applique la valeur par défaut (ex. 25) et désactive l'envoi tant que la valeur est invalide | à ajouter (AC manquante) |
| EDGE-3 | Tableau filtré ne retourne aucun résultat | message UI explicite "Aucun point de vente ne correspond à votre recherche" ; le compteur titre reste affichage du total avant filtrage (BR-7) | AC-7 + à ajouter (comportement 0 résultat non couvert explicitement) |

---

## Parties Prenantes

| Acteur | Rôle vs feature | Niveau d'implication (RACI) |
|---|---|---|
| Amélie (Admin retail) | Utilisatrice quotidienne, représentante retail — seule personne nommée côté équipe retail ; valide l'expérience utilisateur | R (utilise), A (valide UX) |
| PO Métier (équipe retail SDD-Pro) | Sponsor fonctionnel ; valide les SFD/BR et les évolutions de périmètre | A (valide la SPEC) |
| Tech Lead SDD-Pro | Valide l'architecture (Front/Back séparés, JWT, DB-First) ; arbitre les choix structurants | A (arbitre technique) |
| Service SecOps / IT | Configure Azure AD (tenant, app registration, redirect URIs, claims) ; fournit les variables `AZ_*` | C (consulté avant `arch-init`) |
| DBA / Data Engineer | Maintient le schéma SQL Server et les tables référentielles ; consulté pour indexation et `reference_lookup` | C (consulté) |
| Équipe recette / QA | Conditions et périmètre de recette à définir | à définir (hypothèse ouverte) |
| DevOps / Hébergement | Déploie les 2 composants (Frontend WASM + Backend Minimal API) ; contraintes d'hébergement à clarifier | I (informé) — contraintes à définir |
| Équipe BI | Pourrait consommer les données PDV ultérieurement | I (informée du modèle de données) |

---

## Modes de Défaillance

| ID | Mode de défaillance | Indicateur de défaillance | Critère succès en miroir |
|---|---|---|---|
| FAIL-1 | Page liste "Points de vente" met > 3s à charger (dataset réaliste, pagination serveur) | Time-to-Interactive p95 mesuré côté Frontend (RUM ou Lighthouse) | < 1.5s p95 sur dataset de ~10K lignes avec pagination serveur active |
| FAIL-2 | Taux d'erreur 401/403 > 5% des appels Backend sur 30 jours (auth instable ou cascade expirations) | logs Backend, métrique Application Insights ou équivalent | < 1% sur 30 jours roulants |
| FAIL-3 | Calcul colonne "Exploité" (BR-3) produit des valeurs incorrectes pour > 1% des PDV (anomalie JOIN) | rapport de contrôle spot : comparer valeur calculée vs périmètres réels sur échantillon | 0 anomalie sur les tests automatisés ; tolérance < 1% acceptable si signalement et correction sous 48h |
| FAIL-4 | Processus de récupération post-suppression PDV (BR-6 définitive) non défini — ticket support non résolu | tickets "PDV supprimé par erreur" / mois | processus de récupération documenté avant mise en prod ; envisager soft-delete dans une SPEC future si tickets > 0 |
