# Spec: bebe-rdv-edit

FEAT ID: 14-Spec-Bebe-Rdv-Edit
Spec ID: spec-bebe-rdv-edit
Status: Draft

> **Pré-requis schéma** : la table `dbo.BebeRdv` (cf. `spec-bebe-rdv` SFD-3, DDL canonique) **doit exister** en base et figurer dans `workspace/output/db/schema.{json,md,diff.md}` au moment de la matérialisation `dev-backend`. Cette FEAT 14 ne crée **aucune nouvelle table** ni colonne — elle consomme exclusivement les colonnes déjà définies par FEAT 13 (`BebeRdvId`, `Date`, `ContratId`, `HeureRdv`, `Titre`, `Message`) + l'index `IX_BebeRdv_ContratId_Date`.

## Context

La FEAT 13 (`spec-bebe-rdv`) a livré la **lecture + suppression** des rendez-vous bébé : panneau `[data-pane="rdv"]` de la fiche détaillée `/bebes/{ContratId}` alimenté par `GET /api/contrats/{ContratId}/rdv` (filtre serveur `Date = today`), suppression via `DELETE /api/contrats/{ContratId}/rdv/{BebeRdvId}` avec modale de confirmation et update optimiste. Elle a explicitement marqué **out of scope** les deux écrans d'écriture (création / modification) et nommé deux routes SPA réservées :

- `/bebes/{ContratId}/rdv/nouveau` (création — destination du FAB `+` et du redirect `Modifier` global du `section-label`)
- `/bebes/{ContratId}/rdv/{BebeRdvId}` (édition — destination du bouton `Modifier` par card)

Sans cette FEAT 14, ces deux routes tombent sur la 404 du routeur SPA (acceptable temporairement — cf. FEAT 13 AC-20).

Cette FEAT 14 **active fonctionnellement les deux routes** sur un **unique écran** (le formulaire est identique à la création près du chargement initial et du verbe HTTP). Elle livre :

1. **Un seul composant React** monté sur les deux routes (`/rdv/nouveau` et `/rdv/{BebeRdvId}`). Le mode (create vs edit) est détecté par la présence ou non du segment `{BebeRdvId}` dans l'URL — pas de prop, pas de query-string, pas de duplication de composant.
2. **Quatre champs** sur un formulaire mono-step : `Date` (date picker natif HTML5, défaut = `today` côté frontend), `HeureRdv` (time picker natif, format `HH:MM` 24h, step 5 min), `Titre` (input texte ≤ 100 chars, optionnel), `Message` (textarea ≤ 500 chars, optionnel). Règle métier : **au moins l'un des deux entre `Titre` et `Message` est requis** (BR-8 stricte — cf. FEAT 13 BR-8 qui tolère le cas dégradé NULL/NULL avec dash `—`, mais à l'écriture on refuse ce cas).
3. **Deux endpoints backend** :
   - `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` — récupération d'un RDV unique (mode édition, pré-remplissage du formulaire). Out-of-scope de FEAT 13 ; créé ici.
   - `POST /api/contrats/{ContratId}/rdv` (création) et `PUT /api/contrats/{ContratId}/rdv/{BebeRdvId}` (édition). Deux verbes distincts ; pas d'`UPSERT`.
4. **Le top bar du formulaire reproduit fidèlement le composant du `10-1-Spec-Rapport-Du-Jour.html`** : bouton retour rond (chevron-left, chip `--nj-coral-50`) à gauche, titre `{Prénom} {Nom}` (gras 15px) + sous-titre `RDV · Modifier` ou `RDV · Nouveau` (font-mono, uppercase, secondary), avatar bébé rond à droite (38×38, inset shadow). Aucune nouvelle variante de topbar n'est introduite — seul le sous-titre diffère.
5. **Deux issues de navigation** post-action :
   - Clic sur le bouton retour topbar `<` OU sur le bouton footer `Retour` → navigation SPA vers `/bebes/{ContratId}` avec onglet `RDV` actif (panneau `[data-pane="rdv"]`), **sans appel backend**. Les modifications locales du formulaire sont perdues silencieusement (pas de modale « Annuler les modifications ? » dans cette FEAT — cf. Out of Scope).
   - Clic sur le bouton footer `Enregistrer` → validation client → `POST` ou `PUT` → en cas de succès (`201 Created` ou `200 OK`), navigation SPA vers `/bebes/{ContratId}` avec onglet `RDV` actif et **déclenchement immédiat d'un nouveau `GET /api/contrats/{ContratId}/rdv`** côté liste (la FEAT 13 ne pré-fetch pas — il faut donc forcer le re-fetch au retour pour que la nouvelle / modifiée ligne apparaisse).

La maquette de référence est `workspace/input/ui/14-Spec-Bebe-Rdv-Edit.html`. Le top bar est aligné sur `10-1-Spec-Rapport-Du-Jour.html` (mêmes classes CSS `.topbar`, `.topbar__back`, `.topbar__title`, `.topbar__avatar` — réutilisées telles quelles côté JSX, identifiables 1:1 dans le DS isolé du mockup).

La spec **étend partiellement `spec-bebe-rdv`** : SFD-15 (route `Modifier` nommée mais 404), SFD-16 (route `nouveau` nommée mais 404), SFD-17 (composant cible non implémenté), BR-14 (FEAT future qui pré-remplit + POST/PUT + redirect). Ces 4 références deviennent **résolues** après livraison de cette FEAT 14 — les redirections de FEAT 13 cessent de tomber sur la 404 du routeur.

## Objective

L'employé connecté, depuis la liste des RDV `/bebes/{ContratId}` onglet `RDV` (rendue par FEAT 13), clique sur le FAB `+` OU sur le bouton `Modifier` (icône crayon) d'une card RDV existante. Le routeur SPA navigue vers `/bebes/{ContratId}/rdv/nouveau` (mode création) ou `/bebes/{ContratId}/rdv/{BebeRdvId}` (mode édition) — la même page composant est rendue, le mode est détecté par l'URL. En mode édition, un unique `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` est déclenché au montage pour pré-remplir le formulaire (date, heure, titre, message) ; en mode création, aucun appel backend n'est déclenché au montage, le formulaire s'affiche avec `Date = today` et `HeureRdv` vide. Le top bar reproduit le composant de `10-1-Spec-Rapport-Du-Jour.html` (retour chip + prénom/nom + avatar). Quatre champs sont édités : `Date` (picker natif HTML5, `min = today`), `HeureRdv` (picker natif, format `HH:MM`), `Titre` (≤ 100 chars), `Message` (≤ 500 chars). La contrainte temporelle métier est **`(Date + HeureRdv) >= now()`** côté serveur (BR-3 corrigée 2026-05-27) — symétrique du filtre liste FEAT 13 SFD-7 ; le bouton `Enregistrer` est désactivé côté client tant que l'instant exact du RDV n'est pas dans le futur. **Aucun aperçu live n'est rendu sur cet écran** — la liste des RDV (avec rendu visuel fidèle de chaque card) vit exclusivement dans la page parente `9-1-Spec-Bebe-Detaile.html` onglet `RDV` (rendue par FEAT 13). Au clic sur `Enregistrer`, validation client (date/heure obligatoires, au moins un de titre/message non vide) → `POST` (création) ou `PUT` (édition) avec body JSON camelCase → en cas de succès, navigation SPA vers `/bebes/{ContratId}` avec onglet `RDV` actif ET re-fetch du `GET` liste (la nouvelle / modifiée ligne apparaît immédiatement). Le clic sur le bouton retour topbar `<` ou le bouton footer `Retour` navigue vers `/bebes/{ContratId}` avec onglet `RDV` actif sans appel backend ni modale de confirmation (les modifications locales sont perdues silencieusement).

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps de chargement du formulaire en mode édition (Time-To-Interactive après navigation) + temps de soumission (clic `Enregistrer` → redirect + liste re-fetched visible)
- Target: p95 chargement mode édition < 300 ms (1 unique `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` indexé sur PK clustered `BebeRdvId`, payload < 1 KB JSON) ; p95 soumission `POST` ou `PUT` < 250 ms backend ; p95 cycle complet (clic Enregistrer → liste FEAT 13 re-rendue avec la nouvelle ligne visible) < 700 ms ; ouverture mode création (sans round-trip serveur) < 100 ms
- Deadline: livraison stack `fullstack/node-react × ui/shadcn × auth/auth-local` au 2026-07-22 (1 semaine après FEAT 13, dépendance dure sur DDL `dbo.BebeRdv` livré par FEAT 13)

## Non-Functional Constraints (v7.0.0)

- Expected volume: ~1-3 créations RDV / bébé / jour ouvré ; ~0-1 modification RDV / bébé / jour (faible volume d'écriture, dominé par la création) ; ~5-10 ouvertures de la route `/rdv/nouveau` par employé / jour, ~1-3 ouvertures de la route `/rdv/{BebeRdvId}`
- Performance SLA: p95 `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` < 150 ms backend (1 SELECT sur PK clustered, payload < 1 KB) ; p95 `POST` < 200 ms (1 INSERT, retour de l'`Id` généré IDENTITY) ; p95 `PUT` < 200 ms (1 UPDATE sur PK clustered) ; aucun N+1 ; le serveur n'autorise **pas** la mise à jour de `ContratId` (la FK est dérivée de l'URL — anti-tampering, le client ne peut pas réaffecter un RDV d'un bébé à un autre)
- Data retention: les lignes créées suivent la rétention définie par FEAT 13 (CASCADE non requis, pas de purge automatique). Aucune table d'audit ajoutée dans cette FEAT (out of scope cf. FEAT 13 SFD-4).
- Compliance: RGPD — le `Titre` et le `Message` peuvent contenir des informations médicales potentiellement sensibles (catégorie 9 RGPD) ; visibles, créables, modifiables uniquement par l'employé propriétaire du contrat (`Contrat.EmployeeId == session.EmployeeId`) ; le backend retourne toujours **404 Not Found** (jamais 403) sur un `{ContratId}` ou un `{BebeRdvId}` hors périmètre (anti-énumération d'ID — cohérent avec FEAT 13 BR-3) ; le `Date` envoyé par le client est **accepté** (contrairement au `GET` liste qui force `today` côté serveur) mais doit respecter `Date ≥ CAST(getdate() AS DATE)` côté validation backend (anti-création rétroactive — cohérent avec une logique de RDV programmé, pas d'historisation passée)
- Integration: aucune nouvelle table (réutilise `dbo.BebeRdv` créée par FEAT 13). Trois nouveaux endpoints backend (`GET /:id`, `POST`, `PUT /:id`). Aucun service externe (pas de notification email, SMS, ni iCal export). Le composant React du formulaire est nouveau ; le top bar réutilise les classes CSS `.topbar*` du mockup `10-1-Spec-Rapport-Du-Jour.html` ; les composants formulaire (`Input`, `Textarea`, `Button`) utilisent le design system actif `ui/shadcn`.
- Degraded mode: si `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` échoue en mode édition (timeout, 5xx, 404), un état d'erreur `Impossible de charger ce rendez-vous` + bouton `Retour` est affiché à la place du formulaire (aucun champ pré-rempli — l'utilisateur ne doit pas pouvoir éditer un RDV partiellement chargé) ; si `POST` ou `PUT` échoue, le formulaire reste rempli avec les valeurs saisies, un toast `Enregistrement impossible — réessayez` est affiché et le bouton `Enregistrer` redevient cliquable ; si la session est expirée (`401`), redirect vers `/login` (cohérent avec spec-connexion) ; si la validation client échoue (date/heure manquantes ou titre+message tous deux vides), le bouton `Enregistrer` est désactivé visuellement et aucun appel backend n'est envoyé (validation purement frontend en première barrière, doublée backend)

## Actors

- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session (cf. `spec-connexion`). Seul autorisé à créer, modifier ou consulter (en édition) les RDV des contrats dont `Contrat.EmployeeId == session.EmployeeId`. Aucun accès à l'écran d'édition sans authentification.

## Functional Needs

### Routes SPA et détection de mode

- SFD-1: La spec **active deux routes SPA réservées par FEAT 13** :
  - `/bebes/{ContratId}/rdv/nouveau` → mode création (aucun `BebeRdvId` dans l'URL)
  - `/bebes/{ContratId}/rdv/{BebeRdvId}` → mode édition (`BebeRdvId` numérique présent dans l'URL)
  
  Les deux routes montent **le même composant React** ; le mode est détecté côté composant par la présence de `params.BebeRdvId` dans `useParams()` (ou équivalent du routeur frontend actif — cf. `spec-bebes` BR-4). Aucun composant dupliqué, aucun arbre de routes parallèle.
- SFD-2: Le segment `{ContratId}` est obligatoire dans les deux routes — il est extrait du même endroit que pour FEAT 13 SFD-6. Si `{ContratId}` est manquant ou non numérique, le routeur frontend renvoie la page 404 globale (comportement hors scope de cette FEAT — délégué au routeur). De même, `{BebeRdvId}` quand présent doit être numérique (`^\d+$`) ; non-numérique → 404 frontend.
- SFD-3: Le mode est résolu **avant toute requête backend** au montage du composant (cf. SFD-7). Aucun fallback create → edit ou inverse en cas d'erreur (404 backend en mode édition reste un état d'erreur — pas de bascule silencieuse en mode création).

### Top bar (réutilisation `10-1-Spec-Rapport-Du-Jour.html`)

- SFD-4: Le top bar du formulaire reproduit fidèlement le composant `.topbar` de `workspace/input/ui/10-1-Spec-Rapport-Du-Jour.html` (lignes 138-144 du mockup) :
  - À gauche : un bouton retour rond (`.topbar__back`, 38×38, `background: var(--nj-coral-50)`, `color: var(--nj-coral-700)`, icône chevron-left SVG inline `stroke-width="2.2"`)
  - Au centre : un titre `.topbar__title` sur deux lignes — gras 15px `{Prénom} {Nom}` du bébé, font-mono 11px uppercase `RDV · Modifier` (mode édition) OU `RDV · Nouveau` (mode création)
  - À droite : un avatar `.topbar__avatar` rond 38×38 avec image du bébé, `box-shadow: inset 0 0 0 2px #fff, 0 2px 6px rgba(40,20,10,0.10)`
  
  Le markup HTML et les classes CSS sont **réutilisés tels quels** côté JSX — aucune nouvelle variante de topbar n'est créée. Le sous-titre `RDV · Modifier` / `RDV · Nouveau` est le **seul élément variable** entre les deux modes.
- SFD-5: Le clic sur `.topbar__back` déclenche une **navigation SPA** vers `/bebes/{ContratId}` avec l'onglet `RDV` actif (panneau `[data-pane="rdv"]` du composant fiche-détaillée). Aucun appel backend n'est envoyé au clic. Les modifications locales du formulaire (champs modifiés non sauvegardés) sont **perdues silencieusement** — pas de modale de confirmation `Annuler les modifications ?` (cf. Out of Scope — décision UX assumée pour POC).
- SFD-6: Le `{Prénom} {Nom}` du bébé est dérivé de la réponse `GET /api/contrats/{ContratId}` (déjà appelé par la fiche détaillée parente — la donnée doit transiter par le state global de l'app, le store SPA, OU être re-fetched dans cette FEAT). Dans le cadre de cette FEAT, la solution canonique est **un appel local supplémentaire `GET /api/contrats/{ContratId}` au montage du composant** (en parallèle du `GET /:id` en mode édition) pour récupérer `Prénom`, `Nom`, `Photo`. Si ce `GET` échoue, le top bar affiche un état dégradé (`Bébé` à la place du nom, avatar placeholder) — mais le formulaire reste fonctionnel.

### Mode édition — pré-remplissage du formulaire

- SFD-7: En mode édition (`{BebeRdvId}` présent dans l'URL), au montage du composant, **un unique appel** `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` est déclenché (en parallèle du `GET /api/contrats/{ContratId}` de SFD-6). Le backend exécute la requête SQL paramétrée suivante :
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
  WHERE r.BebeRdvId  = @BebeRdvId
    AND r.ContratId  = @ContratId
    AND c.EmployeeId = @SessionEmployeeId;
  ```
  - `INNER JOIN dbo.Contrat` propage le filtre de propriété (anti-cross-tenant)
  - Le `WHERE r.ContratId = @ContratId` garantit qu'un `BebeRdvId` ne peut pas être édité depuis l'URL d'un **autre** bébé (anti-tampering ID — un attaquant ne peut pas substituer `{ContratId}` dans l'URL pour pivoter sur un RDV d'un autre contrat de l'employé)
  - 0 ligne → `404 Not Found` (jamais 403 — anti-énumération)
  - 1 ligne → `200 OK` + payload JSON unique (objet, pas tableau) `{ bebeRdvId, date, heureRdv, titre, message }` (camelCase, BR-9)
- SFD-8: Le payload du `GET /:id` pré-remplit les 4 champs du formulaire :
  - `Date` (input type `date`) ← `date` (format `YYYY-MM-DD`, conversion frontend si besoin pour le widget natif)
  - `HeureRdv` (input type `time`) ← `heureRdv` (format `HH:MM`)
  - `Titre` (input type `text`) ← `titre` (string ou `null` → champ vide)
  - `Message` (textarea) ← `message` (string ou `null` → champ vide)
- SFD-9: Si le `GET /:id` échoue (`404`, `5xx`, network, timeout), un état d'erreur remplace le formulaire entier : message centré `Impossible de charger ce rendez-vous` + bouton `Retour` qui ramène à `/bebes/{ContratId}` onglet `RDV`. **Aucun champ pré-rempli partiellement** — l'utilisateur ne doit pas pouvoir éditer un RDV dont le payload n'a pas été reçu intégralement (anti-écrasement accidentel).

### Mode création — état initial du formulaire

- SFD-10: En mode création (URL `/rdv/nouveau`, pas de `{BebeRdvId}`), aucun `GET /:id` n'est déclenché (économie d'un round-trip). Le formulaire s'affiche avec :
  - `Date` ← valeur par défaut `today` calculée côté frontend (`new Date().toISOString().slice(0,10)` ou équivalent) — l'utilisateur peut la modifier
  - `HeureRdv` ← vide (placeholder du picker natif)
  - `Titre` ← vide
  - `Message` ← vide
  
  Le `GET /api/contrats/{ContratId}` de SFD-6 reste déclenché en parallèle pour alimenter le top bar — c'est le **seul appel backend** du mode création au montage.

### Champs et validation client

- SFD-11: Le formulaire mono-step expose 4 champs dans l'ordre vertical suivant :
  1. **Date** (`<input type="date">`, attribut HTML5 natif) — picker natif, requis, format `YYYY-MM-DD`, `min` = `today` (anti-création rétroactive cf. BR-3)
  2. **HeureRdv** (`<input type="time">`, attribut HTML5 natif) — picker natif, requis, format `HH:MM` 24h, `step="300"` (incréments de 5 min)
  3. **Titre** (`<input type="text">`, optionnel) — `maxlength="100"`, placeholder `ex. Rdv de vaccination`, compteur live `N / 100`
  4. **Message** (`<textarea>`, optionnel) — `maxlength="500"`, `rows="4"`, placeholder `ex. Je dois préparer Amatallah pour le rdv de vaccination`, compteur live `N / 500`, redimensionnement vertical désactivé
- SFD-12: Règle d'**au moins un parmi `Titre` ou `Message`** : la validation client refuse la soumission si `Titre.trim() === '' && Message.trim() === ''`. Cette règle est plus stricte que FEAT 13 BR-8 (qui tolère le cas dégradé NULL/NULL en affichant `—`) — à l'écriture, on refuse ce cas pour ne pas produire des cards « fantômes ». Côté backend, la même règle est appliquée à la validation `POST` / `PUT` (cf. BR-7) — la frontline frontend est doublée d'une garde serveur.
- SFD-13: Le bouton `Enregistrer` est **désactivé visuellement** (opacité réduite, `cursor: not-allowed`, aucun handler de submit) tant que **une** des conditions suivantes est vraie :
  - `Date` est vide OU
  - `HeureRdv` est vide OU
  - `Titre.trim() === '' && Message.trim() === ''` OU
  - **`(Date + HeureRdv) <= now()` côté navigateur** (cf. BR-3 corrigée 2026-05-27) — l'instant précis du RDV est déjà passé ou est exactement maintenant
  
  Dès que **toutes** ces conditions sont satisfaites (4 conditions remplies = toutes fausses), le bouton devient actif (couleur primaire pleine). Le champ `Date` accepte uniquement des dates `≥ today` (HTML5 `min`). La validation combinée date+heure se fait via un effet React qui recompute `canSubmit` à chaque modification de l'un des 4 champs **et** sur un timer (≥ 30s) pour absorber l'écoulement du temps si l'utilisateur reste sur la page (anti-stale state). Le backend re-vérifie au submit (double-check — l'horloge backend fait foi).

### Aperçu live — **explicitement hors scope** (décision UX 2026-05-27)

- SFD-14: Aucun aperçu live (`.preview`, mini-card de récap, miniature card finale) n'est rendu sur l'écran d'édition / création. La visualisation fidèle des cards `.event` vit **exclusivement** dans la page parente `9-1-Spec-Bebe-Detaile.html` onglet `RDV` (rendue par FEAT 13 — pastille `MOIS / JOUR`, bloc texte avec règles d'omission, heure `HH:MM`, variantes de couleur par `BebeRdvId mod 3`). Après `Enregistrer`, la redirection vers `/bebes/{ContratId}` + re-fetch automatique (cf. SFD-18, BR-13) déclenche le rendu de la nouvelle / modifiée ligne dans la liste de FEAT 13 — c'est la seule surface d'aperçu post-écriture. Décision motivée par : (a) éviter la duplication de logique de rendu entre l'écran d'édition et la liste, (b) garder l'écran d'édition focalisé sur la saisie pure (date / heure / titre / message + compteurs), (c) la pastille `MOIS / JOUR` et la variante de couleur dépendent de `BebeRdvId` (inconnu en mode création — BR-9 de FEAT 13) ce qui rendrait l'aperçu partiellement représentatif.

### Soumission — endpoints `POST` et `PUT`

- SFD-15: Au clic sur `Enregistrer` (formulaire valide), le frontend envoie :
  - **Mode création** : `POST /api/contrats/{ContratId}/rdv` avec body JSON `{ date, heureRdv, titre, message }` (camelCase, `titre` et `message` sont `null` si vides — l'un des deux est garanti non-null par SFD-12). Réponse attendue : `201 Created` + body `{ bebeRdvId, date, heureRdv, titre, message }` (l'`Id` IDENTITY généré est retourné pour permettre une éventuelle update optimiste — non utilisée dans cette FEAT mais utile pour future extension).
  - **Mode édition** : `PUT /api/contrats/{ContratId}/rdv/{BebeRdvId}` avec body JSON `{ date, heureRdv, titre, message }` (mêmes règles). Réponse attendue : `200 OK` + body `{ bebeRdvId, date, heureRdv, titre, message }` (le payload complet à jour est renvoyé — pas de `204` car le client peut vouloir afficher un toast récap, et la cohérence client/serveur est garantie par la re-lecture).
- SFD-16: Le backend exécute, en mode création, la requête SQL paramétrée :
  ```sql
  INSERT INTO dbo.BebeRdv ([Date], ContratId, HeureRdv, Titre, Message)
  SELECT @Date, @ContratId, @HeureRdv, @Titre, @Message
   WHERE EXISTS (
     SELECT 1 FROM dbo.Contrat
      WHERE ContratId = @ContratId
        AND EmployeeId = @SessionEmployeeId
   );

  SELECT
    BebeRdvId, [Date], ContratId, HeureRdv, Titre, Message
  FROM dbo.BebeRdv
  WHERE BebeRdvId = SCOPE_IDENTITY();
  ```
  Le `WHERE EXISTS` garantit qu'aucune ligne n'est insérée si le contrat n'appartient pas à l'employé connecté (anti-cross-tenant). Si `@@ROWCOUNT = 0` après l'`INSERT` (contrat inexistant OU hors périmètre), le backend retourne **404 Not Found** (jamais 403, jamais d'erreur cryptique). Si `@@ROWCOUNT = 1`, retour `201 Created` avec le payload re-lu (qui contient le `BebeRdvId` IDENTITY généré).
- SFD-17: Le backend exécute, en mode édition, la requête SQL paramétrée :
  ```sql
  UPDATE r
     SET r.[Date]    = @Date,
         r.HeureRdv  = @HeureRdv,
         r.Titre     = @Titre,
         r.Message   = @Message
    FROM dbo.BebeRdv r
   INNER JOIN dbo.Contrat c ON c.ContratId = r.ContratId
   WHERE r.BebeRdvId   = @BebeRdvId
     AND r.ContratId   = @ContratId
     AND c.EmployeeId  = @SessionEmployeeId;

  SELECT
    BebeRdvId, [Date], ContratId, HeureRdv, Titre, Message
  FROM dbo.BebeRdv
  WHERE BebeRdvId = @BebeRdvId
    AND ContratId = @ContratId;
  ```
  Le triple filtre (`BebeRdvId`, `ContratId`, `EmployeeId`) garantit qu'un RDV ne peut pas être édité depuis l'URL d'un autre bébé ni d'un autre employé. **Le champ `ContratId` du body est ignoré côté serveur** (anti-tampering — la FK est dérivée exclusivement de l'URL). Si `@@ROWCOUNT = 0` après l'`UPDATE`, retour **404 Not Found**. Si `@@ROWCOUNT = 1`, retour `200 OK` avec le payload re-lu.
- SFD-18: En cas de succès (`201` ou `200`), le frontend déclenche immédiatement une navigation SPA vers `/bebes/{ContratId}` **avec onglet `RDV` actif** (via l'API du store SPA OU une convention URL telle qu'un hash `#rdv`, OU le state du routeur — implémentation au choix du dev-frontend, conforme à `spec-bebes` BR-4). La fiche détaillée parente détecte que l'onglet `RDV` doit s'activer et déclenche un `GET /api/contrats/{ContratId}/rdv` (cf. FEAT 13 SFD-1 : le `GET` est déclenché au clic sur l'onglet — l'activation programmatique de l'onglet doit produire le même effet). La nouvelle / modifiée ligne apparaît ainsi sans intervention utilisateur supplémentaire.
- SFD-19: En cas d'échec (`4xx`, `5xx`, timeout, network), le formulaire **conserve les valeurs saisies** (pas de reset), un toast d'erreur `Enregistrement impossible — réessayez` est affiché en bas de l'écran (composant Toast du DS actif si disponible), et le bouton `Enregistrer` redevient cliquable. Aucun appel backend n'est ré-émis automatiquement — l'utilisateur déclenche manuellement la nouvelle tentative.

### Sessions et erreurs

- SFD-20: Toute réponse `401 Unauthorized` (session expirée) du backend déclenche un redirect SPA vers `/login` (cohérent avec spec-connexion et FEAT 13 FD-11). Les modifications locales du formulaire sont perdues — pas de sauvegarde temporaire dans le `localStorage` (out of scope cette FEAT).
- SFD-21: Toute réponse `404 Not Found` sur un `GET /:id`, `PUT /:id`, ou `POST` (le contrat n'existe pas OU n'appartient pas à l'employé) déclenche, côté UI :
  - En mode édition (`GET /:id` 404) → état d'erreur `Impossible de charger ce rendez-vous` (cf. SFD-9)
  - En mode soumission (`POST` ou `PUT` 404) → toast `Enregistrement impossible — réessayez` (cf. SFD-19), aucun comportement spécifique 404 (l'utilisateur ne doit pas savoir si c'est un problème de permissions ou de RDV inexistant — anti-énumération)

### Liens et extensions

- SFD-22: La spec **résout 4 références out-of-scope de FEAT 13** : SFD-15 (route `Modifier` cible 404 → fonctionnelle), SFD-16 (route `nouveau` cible 404 → fonctionnelle), SFD-17 (composant cible non implémenté → implémenté ici), BR-14 (FEAT future qui pré-remplit + POST/PUT + redirect → implémenté ici).
- SFD-23: Aucun composant CSS ni token nouveau n'est introduit. Le mockup `14-Spec-Bebe-Rdv-Edit.html` réutilise exclusivement les tokens du `design-system.css` (`--nj-coral-*`, `--nj-cream`, `--nj-surface`, `--nj-ink-*`, `--nj-line-soft`, `--nj-font-mono`, `--nj-radius-*`, `--nj-shadow-xs`, `--nj-shadow-brand`) et les classes CSS isolées spécifiques au mockup (`.topbar*`, `.field`, `.row-2`, `.btn*`). Les composants formulaire (`Input`, `Textarea`, `Button`, `Toast`) du design system actif `ui/shadcn` doivent être utilisés en priorité côté implémentation React (cf. spec-bebe-detaille BR-25).

## Business Rules

- BR-1: L'écran d'édition / création est accessible exclusivement aux employés authentifiés ; toute requête backend `GET /:id`, `POST`, `PUT` sans session valide retourne `401 Unauthorized` et déclenche redirect frontend vers `/login` (cohérent avec spec-connexion).
- BR-2: `@SessionEmployeeId` provient exclusivement de la variable singleton de session ; aucun paramètre client (`X-Employee-Id` header, query-string) ne peut le surcharger (cf. FEAT 13 BR-2).
- BR-3 (**corrigée 2026-05-27**) : la **combinaison `(Date + HeureRdv)`** acceptée côté backend doit respecter `(Date + HeureRdv) >= GETDATE()` — c'est-à-dire que le **moment exact** du RDV doit être dans le futur ou en cours. Cette règle est **symétrique** du filtre liste de FEAT 13 SFD-7 (`DATEADD(SECOND, DATEDIFF(SECOND, '00:00:00', HeureRdv), CAST(Date AS DATETIME)) >= GETDATE()`) — un RDV créé / modifié est garanti d'apparaître ensuite dans la liste. Cas couverts :
  - `Date < today` → **rejeté** (passé évident)
  - `Date == today` ET `HeureRdv ≤ now()` → **rejeté** (créneau déjà écoulé aujourd'hui)
  - `Date == today` ET `HeureRdv > now()` → **accepté**
  - `Date > today` (n'importe quelle heure) → **accepté**
  
  Côté frontend, l'input `type="date"` porte l'attribut `min` = `today` (HTML5 — granularité jour minimum), et la validation client `canSubmit` désactive le bouton `Enregistrer` quand `Date == today` ET `HeureRdv ≤ heure actuelle navigateur` (anti soumission inutile, le backend rejetterait de toute façon). Le backend re-vérifie au `POST` et au `PUT` (double-check) — l'horloge backend fait foi (cohérence inter-utilisateur). Si la combinaison est passée, le backend retourne `400 Bad Request` avec ProblemDetails `{ "detail": "Le rendez-vous doit être à un moment futur (date + heure)" }` ; le frontend affiche le toast d'erreur générique `Enregistrement impossible — réessayez` (pas de message d'erreur métier détaillé exposé côté UI — cohérent avec FEAT 13 BR-16). **Ancienne formulation `Date ≥ CAST(getdate() AS DATE)`** (jour seul) est **révoquée** : elle autorisait à recréer un RDV pour 10h00 alors qu'il est 14h00, créant un RDV qui n'apparaîtrait jamais dans la liste FEAT 13 (filtré au moment exact).
- BR-4: Le champ `HeureRdv` est obligatoire et doit respecter le format `HH:MM` (24h). Le backend valide via regex serveur `^([01]\d|2[0-3]):[0-5]\d$`. Aucune contrainte sur la plage horaire (un RDV à 03:00 du matin reste accepté — pas de logique métier sur les heures « raisonnables »).
- BR-5: Le champ `Titre` est optionnel (`null` autorisé), max 100 caractères. Le backend valide `LEN(@Titre) ≤ 100` avant l'`INSERT` / `UPDATE` (cohérent avec la contrainte SQL `NVARCHAR(100)` de FEAT 13 SFD-3 — la validation explicite côté code évite une erreur SQL cryptique en cas de débordement).
- BR-6: Le champ `Message` est optionnel (`null` autorisé), max 500 caractères. Le backend valide `LEN(@Message) ≤ 500` avant l'`INSERT` / `UPDATE` (cohérent avec `NVARCHAR(500)`).
- BR-7: **Au moins l'un des deux entre `Titre` et `Message` doit être non-vide** (après `trim()` côté frontend, après suppression des `whitespace` côté backend). Si les deux sont `null` ou vides, le backend retourne `400 Bad Request` avec ProblemDetails `{ "detail": "Titre ou Message requis" }` ; le frontend affiche le toast générique. Cette règle est plus stricte que FEAT 13 BR-8 (lecture tolérante avec dash `—`) — à l'écriture on refuse le cas dégradé.
- BR-8: Le `ContratId` du body JSON envoyé par le client est **ignoré** côté serveur. La FK est exclusivement dérivée du segment `{ContratId}` de l'URL. Un client malveillant qui enverrait `POST /api/contrats/42/rdv` avec body `{ contratId: 99, date: ..., ... }` créera bien un RDV sur le contrat `42` (URL prime), pas sur `99` (body ignoré).
- BR-9: Les payloads JSON `GET /:id`, `POST` (request + response), `PUT` (request + response) sont en `camelCase` (cf. library-and-stack §6.bis.3) en miroir des noms TS frontend : `bebeRdvId`, `date`, `heureRdv`, `titre`, `message`. Les valeurs `null` sont sérialisées `null` JSON (jamais `""` ni omises). Le type SQL `time` est sérialisé `"HH:MM"` (24h, sans secondes ni TZ — cohérent avec FEAT 13 BR-12).
- BR-10: La colonne SQL `HeureRdv` (`time`) est stockée et sérialisée TZ-naive en fuseau serveur local (cohérent avec FEAT 13 BR-12).
- BR-11: Aucune information technique (stack trace, identifiant interne, exception SQL) n'est exposée dans les messages d'erreur visibles à l'utilisateur (cohérent avec FEAT 13 BR-16). Tous les `4xx` et `5xx` côté soumission produisent le même toast générique `Enregistrement impossible — réessayez`.
- BR-12: La navigation SPA des boutons retour (topbar `<` et footer `Retour`), ainsi que la redirection post-succès, utilisent le mécanisme du routeur frontend actif (cf. spec-bebes BR-4 et FEAT 13 BR-18) ; l'usage de `<a href>` brut est interdit pour ces actions (un `<a>` peut rester dans le markup statique de l'icône mais le clic doit être intercepté par le routeur).
- BR-13: La redirection post-succès vers `/bebes/{ContratId}` avec onglet `RDV` actif doit **déclencher un nouveau `GET /api/contrats/{ContratId}/rdv`** sur la fiche détaillée parente (la liste FEAT 13 n'a pas de cache local — le re-fetch est obligatoire pour faire apparaître la nouvelle / modifiée ligne). L'implémentation peut passer par : (a) un évènement custom écouté par la fiche détaillée, (b) un flag dans le state du routeur lu au mount de l'onglet, (c) une simple re-activation programmatique de l'onglet qui déclenche le handler de clic existant (méthode privilégiée car réutilise le code existant FEAT 13). Tout choix est acceptable tant que la nouvelle ligne est visible sans intervention utilisateur post-redirect.
- BR-14: Aucune modale `Annuler les modifications ?` n'est affichée au clic sur le retour quand le formulaire contient des modifications non sauvegardées. Les modifications sont perdues silencieusement (décision UX assumée pour POC — extension future cf. Out of Scope).
- BR-15: Si le `GET /api/contrats/{ContratId}` (top bar SFD-6) échoue mais que les autres appels réussissent, le top bar affiche un état dégradé (`Bébé` à la place du nom, avatar placeholder neutre) mais le formulaire reste fonctionnel. C'est un échec **silencieux** — pas de toast ni d'erreur bloquante (la donnée bébé est cosmétique pour l'édition).
- BR-16: Si le `GET /api/contrats/{ContratId}` (top bar SFD-6) ET le `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` (pré-remplissage SFD-7) échouent tous les deux en mode édition, l'état d'erreur du formulaire (cf. SFD-9) prime sur l'état dégradé du top bar (cf. BR-15) — l'utilisateur voit `Impossible de charger ce rendez-vous`.
- BR-17: ~~Aperçu live~~ — règle retirée 2026-05-27 (cf. SFD-14 mise à jour). Aucune carte d'aperçu n'est rendue sur cet écran ; la visualisation finale vit exclusivement dans la liste FEAT 13 post-redirect.
- BR-18: Le payload `POST` ou `PUT` envoyé au backend trim les valeurs `Titre` et `Message` côté frontend avant envoi (anti-whitespace pollution). Le backend re-trim côté serveur (double-check). Une chaîne après trim devenue vide est sérialisée `null` JSON (jamais `""`).

## Acceptance Criteria

- AC-1: Le routage SPA monte le **même composant React** sur `/bebes/{ContratId}/rdv/nouveau` et `/bebes/{ContratId}/rdv/{BebeRdvId}` ; le mode (create / edit) est détecté par la présence de `BebeRdvId` dans les params (vérifiable côté code review — un seul composant, pas de duplication).
- AC-2: En mode édition, au montage du composant, **deux appels** backend sont déclenchés en parallèle : `GET /api/contrats/{ContratId}` (top bar) + `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` (pré-remplissage). Aucun autre appel.
- AC-3: En mode création, au montage du composant, **un seul appel** backend est déclenché : `GET /api/contrats/{ContratId}` (top bar). Aucun `GET /:id` n'est émis.
- AC-4: Le top bar du formulaire est visuellement identique au top bar de `10-1-Spec-Rapport-Du-Jour.html` (mêmes classes CSS `.topbar`, `.topbar__back`, `.topbar__title`, `.topbar__avatar` — même styles compilés ; vérifiable côté DOM).
- AC-5: Le sous-titre du top bar affiche `RDV · Modifier` en mode édition et `RDV · Nouveau` en mode création (vérifiable par changement de l'URL).
- AC-6: En mode édition, le formulaire est pré-rempli avec les valeurs du `GET /:id` : `Date` ← `date`, `HeureRdv` ← `heureRdv`, `Titre` ← `titre` (ou vide si null), `Message` ← `message` (ou vide si null).
- AC-7: En mode création, le formulaire s'affiche avec `Date = today` (calculé côté frontend) ; `HeureRdv`, `Titre`, `Message` sont vides.
- AC-8: Le bouton `Enregistrer` est **désactivé** (visuellement et fonctionnellement) tant que `Date` est vide OU `HeureRdv` est vide OU (`Titre.trim() === '' && Message.trim() === ''`).
- AC-9: Le bouton `Enregistrer` devient **actif** dès que les 3 conditions de AC-8 sont remplies (vérifiable par modification des champs un à un).
- AC-10: La combinaison `(Date + HeureRdv)` doit être strictement future (cf. BR-3 corrigée 2026-05-27). L'input `Date` HTML5 porte l'attribut `min = today` (granularité jour). La validation client `canSubmit` désactive en plus le bouton `Enregistrer` quand `Date == today` ET `HeureRdv ≤ heure courante navigateur`. Côté backend, un `POST`/`PUT` avec `(Date + HeureRdv) < now()` retourne `400 Bad Request`. Vérifiable par : (a) saisir `Date = today-1` → bouton désactivé par HTML5 ; (b) saisir `Date = today` + `HeureRdv = current-1h` → bouton désactivé par JS ; (c) saisir `Date = today` + `HeureRdv = current+1h` → bouton actif, save OK ; (d) saisir `Date = today+7` + `HeureRdv = 02:00` → bouton actif, save OK.
- AC-11: L'input `HeureRdv` accepte uniquement le format `HH:MM` 24h avec step de 5 min (incréments de 0, 5, 10, ..., 55 min) ; saisir `25:99` n'est pas possible via le picker natif.
- AC-12: Le champ `Titre` accepte jusqu'à 100 caractères ; le compteur live affiche `N / 100` et s'incrémente en temps réel.
- AC-13: Le champ `Message` accepte jusqu'à 500 caractères ; le compteur live affiche `N / 500` et s'incrémente en temps réel.
- AC-14: ~~Carte d'aperçu live~~ — retiré 2026-05-27. Aucune carte d'aperçu n'est rendue sur l'écran d'édition (cf. SFD-14, BR-17). L'écran reste focalisé sur la saisie pure (4 champs + compteurs).
- AC-15: ~~Aperçu cas dégradé~~ — retiré 2026-05-27 (idem AC-14). Le cas dégradé NULL/NULL est strictement empêché par BR-7 côté écriture (et reste toléré côté lecture FEAT 13 BR-8 avec dash `—`).
- AC-16: Au clic sur `Enregistrer` en mode création, **un seul** appel `POST /api/contrats/{ContratId}/rdv` est envoyé avec body JSON camelCase `{ date, heureRdv, titre, message }` (les valeurs trim, `null` si vides). Aucun autre appel n'est émis en parallèle de la soumission.
- AC-17: Au clic sur `Enregistrer` en mode édition, **un seul** appel `PUT /api/contrats/{ContratId}/rdv/{BebeRdvId}` est envoyé avec body JSON camelCase ; le `ContratId` éventuel du body est ignoré côté serveur (vérifiable par tampering manuel — envoyer un `contratId` du body différent de l'URL n'a pas d'effet).
- AC-18: Le backend exécute exactement la requête SQL paramétrée de SFD-7 (`GET /:id`) avec triple filtre `BebeRdvId / ContratId / EmployeeId` — vérifiable côté logs SQL ou test d'intégration. Un `GET /:id` sur un `BebeRdvId` d'un autre employé retourne 404 (jamais 403).
- AC-19: Le backend exécute exactement la requête SQL paramétrée de SFD-16 (`POST` avec `WHERE EXISTS Contrat.EmployeeId`) — un `POST` sur un `ContratId` hors périmètre retourne 404 (aucune ligne insérée).
- AC-20: Le backend exécute exactement la requête SQL paramétrée de SFD-17 (`PUT` avec triple filtre) — un `PUT` sur un `BebeRdvId` hors périmètre retourne 404 (aucune ligne mise à jour).
- AC-21: En cas de succès `POST` (`201 Created`) ou `PUT` (`200 OK`), le frontend navigue vers `/bebes/{ContratId}` avec onglet `RDV` actif (vérifiable côté router). Un nouveau `GET /api/contrats/{ContratId}/rdv` est déclenché par la fiche détaillée parente (cf. FEAT 13 SFD-1) ; la nouvelle / modifiée ligne apparaît dans la liste **sans intervention utilisateur supplémentaire**.
- AC-22: En cas d'échec (`4xx`, `5xx`, timeout, network), le formulaire conserve les valeurs saisies, un toast `Enregistrement impossible — réessayez` est affiché, le bouton `Enregistrer` redevient cliquable. Aucun message d'erreur métier détaillé n'est exposé (cohérent avec FEAT 13 BR-16).
- AC-23: En cas de `401 Unauthorized` sur n'importe quel appel (`GET /api/contrats/{ContratId}`, `GET /:id`, `POST`, `PUT`), un redirect SPA vers `/login` est déclenché (cohérent avec spec-connexion).
- AC-24: Au clic sur le bouton retour topbar `<` OU sur le bouton footer `Retour`, le frontend navigue vers `/bebes/{ContratId}` avec onglet `RDV` actif **sans appel backend** et **sans modale de confirmation**, même si des modifications locales non sauvegardées sont présentes (cf. BR-14).
- AC-25: Si le `GET /:id` échoue en mode édition (`404` ou `5xx` ou timeout), un état d'erreur `Impossible de charger ce rendez-vous` + bouton `Retour` remplace le formulaire entier — aucun champ pré-rempli partiellement visible.
- AC-26: Si le `GET /api/contrats/{ContratId}` (top bar) échoue mais que le `GET /:id` réussit, le top bar affiche un état dégradé (`Bébé` à la place du nom, avatar placeholder) et le formulaire reste fonctionnel (vérifiable par network throttling sélectif).
- AC-27: La règle BR-7 (Titre ou Message requis) est appliquée côté backend même si le frontend a été bypassé : un `POST` ou `PUT` direct avec `{ titre: null, message: null }` retourne `400 Bad Request` (vérifiable par test API direct hors UI).
- AC-28: La règle BR-3 corrigée (`(Date + HeureRdv) >= GETDATE()`) est appliquée côté backend, **indépendamment du frontend** : (a) un `POST` avec `{ date: "2026-01-01", heureRdv: "10:00" }` (passé évident) sur une session active 2026-05-27 retourne `400 Bad Request` ; (b) un `POST` avec `{ date: today, heureRdv: current-1h }` (créneau écoulé aujourd'hui) retourne aussi `400 Bad Request` ; (c) un `POST` avec `{ date: today, heureRdv: current+5min }` réussit (`201 Created`) ; (d) un `POST` avec `{ date: today+30, heureRdv: "23:59" }` réussit. Le message d'erreur backend `"Le rendez-vous doit être à un moment futur (date + heure)"` reste interne — le frontend n'expose que le toast générique (BR-16).
- AC-29: Aucun nouveau token CSS ni nouvelle classe CSS globale n'est introduit ; le mockup utilise exclusivement les variables `--nj-*` du `design-system.css` (vérifiable par grep absence de hex hardcodé `#[0-9a-fA-F]` hors design-system).
- AC-30: La spec résout les 4 références out-of-scope de FEAT 13 (SFD-15, SFD-16, SFD-17, BR-14) — après livraison, les redirections `Modifier` et FAB `+` de FEAT 13 tombent sur un écran fonctionnel et non plus sur la 404 du routeur.

## Dependencies

- **spec-bebe-rdv** (`13-Spec-Bebe-Rdv`) : **étend partiellement** cette FEAT — résout SFD-15, SFD-16, SFD-17, BR-14 (cf. SFD-22). La table `dbo.BebeRdv` (DDL SFD-3 de FEAT 13) est un **pré-requis dur** : si la table n'existe pas en base au moment de la matérialisation `dev-backend` de cette FEAT 14, la matérialisation échoue avec `[SCHEMA_MISMATCH]`. Le filtrage `Date = today` côté liste FEAT 13 reste actif — les RDV créés sur une date future n'apparaissent dans la liste qu'au jour J.
- **spec-bebe-detaille** (`9-spec-bebe-detaille`) : la fiche détaillée parente accueille la redirection post-succès et post-retour ; l'activation programmatique de l'onglet `RDV` au retour doit déclencher le handler de clic existant (cf. FEAT 13 SFD-1 et BR-13 de cette FEAT).
- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session ; redirect `/login` sur `401` ; cohérent avec FEAT 13 et FEAT 9.
- **spec-bebes** (`4-spec-bebes`) : BR-4 (navigation SPA via routeur) reste applicable pour les routes `/bebes/{ContratId}/rdv/nouveau` et `/bebes/{ContratId}/rdv/{BebeRdvId}` ainsi que pour les boutons retour.
- **design-system.css** + maquette `10-1-Spec-Rapport-Du-Jour.html` : le top bar du formulaire **réutilise** les classes `.topbar*` (lignes 12-16 du `<style>` de `10-1-Spec-Rapport-Du-Jour.html`) — aucune nouvelle variante n'est créée. Le sous-titre `RDV · Modifier` / `RDV · Nouveau` est le seul élément variable.
- **Stack `ui/shadcn`** (design system actif) : les composants `Input`, `Textarea`, `Button`, `Toast` (et `Dialog` si la FEAT future ajoute la modale `Annuler les modifications ?`) sont utilisés en priorité côté implémentation (cf. spec-bebe-detaille BR-25). Le CSS isolé du mockup `14-Spec-Bebe-Rdv-Edit.html` ne complète que pour atteindre la fidélité visuelle (cards `.field`, `.preview`).

## Functional Deliverables

- FD-1: Endpoint backend `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` exécutant la requête SQL paramétrée de SFD-7 (triple filtre `BebeRdvId / ContratId / EmployeeId`), retournant un objet JSON unique `{ bebeRdvId, date, heureRdv, titre, message }` (camelCase, NULL → `null`, `time` → `"HH:MM"`) en `200 OK` ou `404 Not Found` si hors périmètre.
- FD-2: Endpoint backend `POST /api/contrats/{ContratId}/rdv` exécutant la requête SQL paramétrée de SFD-16 (`INSERT ... WHERE EXISTS Contrat.EmployeeId`) avec validation serveur des règles métier (BR-3 `(Date + HeureRdv) >= GETDATE()` — combinée, BR-4 HeureRdv format `HH:MM`, BR-5 + BR-6 longueurs max, BR-7 Titre ou Message requis), retournant `201 Created` + payload re-lu ou `400 Bad Request` (validation) ou `404 Not Found` (contrat hors périmètre).
- FD-3: Endpoint backend `PUT /api/contrats/{ContratId}/rdv/{BebeRdvId}` exécutant la requête SQL paramétrée de SFD-17 (`UPDATE` avec triple filtre + re-lecture), retournant `200 OK` + payload re-lu ou `400 Bad Request` (validation) ou `404 Not Found` (hors périmètre). Le champ `ContratId` du body est ignoré (anti-tampering BR-8).
- FD-4: Composant React **unique** monté sur les deux routes `/bebes/{ContratId}/rdv/nouveau` et `/bebes/{ContratId}/rdv/{BebeRdvId}` ; détection de mode via présence de `BebeRdvId` dans `useParams()`. Aucune duplication.
- FD-5: Top bar du formulaire réutilisant les classes `.topbar`, `.topbar__back`, `.topbar__title`, `.topbar__avatar` du mockup `10-1-Spec-Rapport-Du-Jour.html` ; sous-titre variable `RDV · Modifier` / `RDV · Nouveau` selon le mode.
- FD-6: Formulaire mono-step avec 4 champs (Date date-picker natif, HeureRdv time-picker natif `step=300`, Titre input texte max 100, Message textarea max 500 avec compteurs live), validation client (BR-3, BR-4, BR-7) et désactivation visuelle du bouton `Enregistrer` si invalide (AC-8, AC-9).
- FD-7: ~~Carte d'aperçu live~~ — retirée 2026-05-27 (cf. SFD-14). L'écran d'édition n'expose plus de mini-aperçu — la liste FEAT 13 reste la seule surface de rendu visuel des cards `.event`.
- FD-8: Mode édition — pré-remplissage des 4 champs depuis le payload `GET /:id` ; état d'erreur `Impossible de charger ce rendez-vous` + bouton `Retour` si le `GET /:id` échoue (cf. SFD-9, AC-25).
- FD-9: Mode création — état initial du formulaire avec `Date = today` (frontend), autres champs vides ; aucun `GET /:id` au montage (cf. SFD-10, AC-3, AC-7).
- FD-10: Soumission `POST` (création) ou `PUT` (édition) avec body JSON camelCase trim'é ; navigation SPA post-succès vers `/bebes/{ContratId}` avec onglet `RDV` actif **et déclenchement automatique du `GET` liste** pour faire apparaître la nouvelle / modifiée ligne (cf. BR-13, AC-21).
- FD-11: Gestion des erreurs (`4xx`/`5xx`/network) côté soumission — toast `Enregistrement impossible — réessayez`, formulaire conservé, bouton `Enregistrer` re-actif (cf. SFD-19, AC-22).
- FD-12: Gestion `401 Unauthorized` côté tous les appels — redirect SPA `/login` (cf. SFD-20, AC-23).
- FD-13: Boutons retour (topbar `<` et footer `Retour`) déclenchant une navigation SPA `/bebes/{ContratId}` avec onglet `RDV` actif sans appel backend ni modale de confirmation (cf. SFD-5, BR-14, AC-24).
- FD-14: État dégradé du top bar (`Bébé` + avatar placeholder) si `GET /api/contrats/{ContratId}` échoue mais que le reste fonctionne (cf. BR-15, AC-26).

## Out of Scope

- **Modale `Annuler les modifications ?`** au clic sur le retour quand des modifications locales sont présentes — les modifications sont perdues silencieusement dans cette FEAT (cf. BR-14). Extension future pour améliorer l'UX.
- **Sauvegarde temporaire dans le `localStorage`** (récupération du formulaire après refresh accidentel ou session expirée) — non implémenté.
- **Validation avancée** : pas de détection de conflit de planning (deux RDV même heure même bébé restent autorisés en base — cf. FEAT 13 SFD-4) ; pas d'alerte si un RDV chevauche un créneau de repos `JourReposEmploye` ; pas de validation que l'heure est « raisonnable » (RDV à 03:00 accepté).
- **Récurrence** (« créer un RDV hebdomadaire ») — hors scope strict (cf. FEAT 13 Out of Scope). Une ligne `dbo.BebeRdv` = un RDV unique.
- **Notification post-création** (email aux parents, SMS, push) — hors scope (cohérent avec FEAT 13).
- **Catégorisation du RDV** (médical, sortie, administratif) — pas de champ `Catégorie` ajouté. La couleur de la card reste déterministe par `BebeRdvId mod 3` (FEAT 13 BR-9) — sans relation métier.
- **Pièces jointes** (PDF d'ordonnance, photo) — hors scope.
- **Suppression depuis l'écran d'édition** (bouton `Supprimer` en bas du formulaire) — la suppression reste accessible exclusivement depuis la liste FEAT 13 (cf. FEAT 13 SFD-13).
- **Duplication d'un RDV** (« créer un nouveau RDV à partir d'un existant ») — hors scope.
- **Historique des modifications** (audit log des changements `Date / HeureRdv / Titre / Message` d'un RDV) — pas de colonnes d'audit ajoutées (cohérent avec FEAT 13 SFD-4).
- **Édition d'un RDV passé** (`(Date + HeureRdv) < now()`) — bloquée par BR-3 corrigée 2026-05-27. Pour modifier un RDV passé (cas exceptionnel), passer par la base directement (admin DBA). Pas d'override UI. À noter : un RDV passé n'apparaît plus dans la liste FEAT 13 (filtré côté serveur), donc l'utilisateur ne pourrait de toute façon pas y accéder via le bouton `Modifier` — la garde backend est belt-and-suspenders contre les URL forgées.
- **Multi-bébé** (créer un RDV commun à plusieurs bébés en une seule action) — un RDV = un `ContratId` = un bébé. Pas de relation many-to-many ajoutée.
- **Intégration calendrier externe** (iCal export, Google Calendar sync, Outlook) — hors scope strict (cohérent avec FEAT 13).
- **Permissions parents** (validation d'un RDV proposé par l'employé côté Employeur) — hors scope (le Parent ne consulte pas l'app dans le POC).
- **Création / modification en masse** (formulaire pour saisir 5 RDV d'un coup) — hors scope.
- **Mode brouillon** (sauvegarder un RDV partiellement saisi sans le publier) — hors scope. La règle BR-7 (Titre ou Message requis) interdit le brouillon vide.
- **Internationalisation** (mois affiché en EN, formats de date locale) — la pastille `MOIS / JOUR` reste FR uppercase (cohérent avec FEAT 13 BR-4).
- **Accessibilité avancée** (lecture vocale du formulaire pour malvoyants, navigation clavier renforcée au-delà des défauts HTML5) — couverture WCAG basique uniquement (labels `<label for>`, attributs `aria-label` sur les boutons icon-only) ; pas d'audit axe-core dédié dans cette FEAT.
- **Bouton `Modifier` global du `section-label` Rendez-vous** (cf. FEAT 13 SFD-19) — sa redirection cible (`/rdv/nouveau` par défaut FEAT 13) devient fonctionnelle ici, mais aucun changement de comportement du bouton lui-même n'est introduit (il reste un raccourci création).
- **Carte d'aperçu live / mini-card de récap / miniature `.preview` / pastille `MOIS/JOUR` cosmétique** — **STRICTEMENT INTERDIT** sur l'écran d'édition / création (décision UX figée 2026-05-27, cf. SFD-14, BR-17, AC-14, AC-15, FD-7 marqués `~~retirés~~`). **Anti-derive bloquant pour tout futur run** `dev-frontend` / `dev-plan` / `/sdd-poc` / `/sdd-full` sur cette FEAT 14 : aucun composant `<Preview>`, `<RdvPreview>`, `<RdvMiniCard>`, `<RecapCard>`, classe CSS `.preview*`, `.recap*`, `.event-preview*`, ni équivalent ne DOIT être généré sous le formulaire ou ailleurs sur cet écran. La visualisation fidèle des cards `.event` vit **exclusivement** dans la liste FEAT 13 (page 9 onglet RDV) — toute duplication de logique de rendu serait un drift de scope (cf. `error-classification.md [DERIVE_VIOLATION]`). L'écran d'édition reste focalisé sur la saisie pure (4 champs Date/HeureRdv/Titre/Message + compteurs live + boutons Retour/Enregistrer). Si une future itération veut introduire un aperçu, créer une FEAT séparée — ne pas l'inliner ici.

## Anti-derive (load-bearing pour dev-frontend / dev-plan)

Cette section est **bloquante** pour tout agent ou commande matérialisant la FEAT 14. Elle synthétise les interdictions strictes du scope frontend :

- **PAS d'aperçu live, mini-card, miniature, récap visuel** sous le formulaire (cf. ligne « Carte d'aperçu live » de la section Out of Scope ci-dessus) — duplication de FEAT 13 = drift.
- **PAS de logique de rendu `.event` / `.event--*` / pastille `MOIS-JOUR`** dans le composant `BebeRdvEditPage` ou équivalent. Ces patterns appartiennent à FEAT 13.
- **PAS de calcul `BebeRdvId mod 3`** côté écriture (FEAT 13 BR-9 est exclusivement consommée en lecture par la liste — pas par le formulaire).
- **PAS de helper `MOIS_FR`, `formatDateBadge`, `monthShort3`** ni équivalent dans ce composant. Ces helpers, s'ils existent côté frontend, doivent vivre dans le composant qui rend la liste (FEAT 13).
- **PAS de duplication du markup `.event__date / .event__body / .event__time`** ni de leurs variantes. Le formulaire utilise uniquement `.field*`, `.row-2`, `.form-mode`, `.char-count`, `.btn*`, `.topbar*` (cf. SFD-23).
- **PAS de fetch `GET /api/contrats/{ContratId}/rdv` (liste)** depuis ce composant — c'est FEAT 13 qui fetch. Ce composant fetch uniquement `GET /api/contrats/{ContratId}` (top bar, SFD-6) et, en mode édition, `GET /api/contrats/{ContratId}/rdv/{BebeRdvId}` (pré-remplissage, SFD-7).

Le respect de ces interdictions est vérifiable par grep post-génération sur `workspace/output/src/**/BebeRdvEdit*` :
```
grep -E '\.preview|MOIS_FR|monthShort|\.event__date|\.event__body|\.event__time|BebeRdvId.*mod' → doit retourner 0 match.
```

### Anti-derive bonus — bump `CACHE_VERSION` du service worker (post-mortem 2026-05-27)

**Bloquant** : tout ajout de **nouvelles routes SPA** ou de **nouveau composant `.jsx` ajouté à `index.html`** doit s'accompagner d'un bump de `CACHE_VERSION` dans `workspace/output/src/{AppName}/public/service-worker.js`. Sans bump :

1. Le browser charge l'**ancien `app.jsx` cacheé** par le SW (le SW pré-cache `/app.jsx` dans `APP_SHELL`).
2. L'utilisateur clique sur un bouton qui pousse une URL valide (ex. `/bebes/3/rdv/nouveau`) — l'historique navigateur est mis à jour.
3. Le SPA re-rend, mais avec l'**ancien routeur** qui ne connaît pas la nouvelle route → fallback silencieux sur la route catch-all (typiquement la fiche détaillée ou la page d'accueil) → **bug fantôme** : URL correcte, mauvais composant rendu.

**Procédure obligatoire pour `dev-frontend` quand il ajoute une route SPA** :
- Lire le `CACHE_VERSION` courant dans `service-worker.js`
- Bumper le suffixe avec le numéro de FEAT (`vN-featM`) — ex. `v3-feat13` → `v4-feat14`
- Ajouter un commentaire à côté de la constante expliquant le pourquoi (ex. « bump 2026-05-27 pour invalider l'ancien app.jsx sans routes /bebes/:id/rdv/* »)
- Aucun bump n'est requis si la FEAT n'ajoute **que** des modifications de composants existants déjà dans `APP_SHELL` (les SW serve les `.jsx` non-listés via `network-first`, donc le cache se met à jour spontanément). En revanche, dès que `app.jsx` est modifié, bump obligatoire (car il est dans `APP_SHELL`).

**Vérification post-génération** :
```bash
git diff workspace/output/src/{AppName}/public/service-worker.js | grep -E '^\+.*CACHE_VERSION' → doit retourner 1 match si app.jsx a été modifié.
```

**Post-mortem 2026-05-27** : la 1re matérialisation FEAT 14 a omis ce bump. Conséquence : URL `/bebes/3/rdv/nouveau` correcte mais formulaire BebeRdvEditPage jamais rendu (l'ancien `app.jsx` cacheé ne contenait pas le route matcher). Corrigé par bump manuel `v3-feat13` → `v4-feat14`.

### Anti-derive bonus — scoping CSS des classes `.topbar*` réutilisées (post-mortem 2026-05-27 #2)

**Bloquant** : le mockup FEAT 14 (`14-Spec-Bebe-Rdv-Edit.html`) réutilise **les noms de classes** `.topbar`, `.topbar__back`, `.topbar__title`, `.topbar__avatar` (et leurs descendants `.topbar__title b`, `.topbar__title span`, `.topbar__avatar img`) en référence au mockup `10-1-Spec-Rapport-Du-Jour.html` (cf. SFD-4). **Mais** chaque page React du projet `Demo/` scope ses propres styles sous un nom de container racine (`.bebe-detail .topbar*`, `.rapport-page .topbar*`, etc.) pour éviter toute fuite cross-page — il n'existe **pas** de styles `.topbar*` globaux.

Conséquence : si `dev-frontend` se contente d'appliquer les classes `.topbar*` dans le JSX sans générer les **règles CSS scopées** correspondantes sous `.bebe-rdv-edit`, le composant `<img>` de l'avatar est rendu à sa **taille native** (typiquement 160×160px ou plus selon le fichier source), la chip retour perd son fond rond, et la mise en page topbar se désaligne. Bug visible à l'œil nu mais silencieux côté build (CSS valide).

**Procédure obligatoire pour `dev-frontend` quand il copie des classes CSS depuis un autre mockup** :
- Identifier le **container racine** de la page courante (typiquement `.{nom-de-feat}` ou `.{nom-mockup}` au niveau du wrapper `<div className="app ...">`)
- Pour chaque classe copiée (`.topbar`, `.topbar__back`, `.topbar__title`, `.topbar__avatar`, etc.), **régénérer la règle CSS scopée** sous `.<container> .<classe>` dans `styles.css` du projet généré
- Copier les déclarations (`width`, `height`, `border-radius`, `background`, etc.) depuis la source — ne jamais hériter implicitement
- Vérifier post-génération que la page concernée a au moins un bloc CSS topbar scopé (grep `.{container} \.topbar` doit retourner ≥ 4 matches : `.topbar`, `.topbar__back`, `.topbar__title`, `.topbar__avatar`)

**Vérification post-génération** :
```bash
grep -E '\.bebe-rdv-edit \.topbar' workspace/output/src/{AppName}/public/styles.css | wc -l
# doit retourner ≥ 4 (sinon : topbar styles manquants)
```

**Post-mortem 2026-05-27 #2** : la 1re matérialisation FEAT 14 a oublié de scoper les styles topbar — seules les classes JSX étaient appliquées, sans règles CSS sous `.bebe-rdv-edit`. Conséquence visuelle : avatar bébé en taille native (énorme), chip retour sans cercle, titre mal aligné. Corrigé par ajout manuel d'un bloc de 6 règles scopées (`.bebe-rdv-edit .topbar`, `.topbar__back`, `.topbar__title`, `.topbar__title b`, `.topbar__title span`, `.topbar__avatar`, `.topbar__avatar img`) dans `styles.css` + 2e bump `CACHE_VERSION` (v4 → v5).
