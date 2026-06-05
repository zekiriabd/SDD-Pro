# Spec: rapport-sms

FEAT ID: 12-Spec-rapport-sms
Spec ID: spec-rapport-sms
Status: Draft

> **Pré-requis schéma** : la colonne `dbo.RapportJournee.RapportSms NVARCHAR(500) NULL` est déjà créée (cf. FEAT 11 SFD-3 — « colonne historique non utilisée par cette FEAT, réservée à un envoi SMS futur — out of scope »). Cette FEAT en est l'**activation fonctionnelle**. Aucun DDL supplémentaire n'est demandé. Si la longueur 500 caractères s'avère trop courte en production, un `ALTER COLUMN RapportSms NVARCHAR(MAX)` futur sera tracé via ADR — pour l'instant, la spec définit une stratégie de troncature explicite (BR-15).

## Context
La fiche détaillée d'un bébé `/bebes/{ContratId}` (cf. `spec-bebe-detaille`) expose dans l'onglet 2 `Rapport du jour` une **textarea** + un bouton **`Envoyer aux parents`** aujourd'hui purement statiques : la textarea est pré-remplie en dur dans le mockup et le bouton n'a aucune action câblée (cf. `spec-bebe-detaille` SFD-30, FD-10, `spec-rapport-du-jour` BR-22). La FEAT 10 (`spec-rapport-du-jour`) a câblé la **saisie structurée** des observations du jour via le stepper Santé / Nourriture / Activité / Humeur (lignes `dbo.Rapport` indexées par `(ActionId, Date, ContratId)`), mais **n'a pas câblé la suite logique** : générer un message texte agrégé lisible par un humain (résumé narratif des cases cochées) et le proposer aux parents par SMS.

Cette spec décrit la **génération automatique du résumé narratif** et son **envoi par SMS** aux parents :

1. **Persistance du résumé narratif** dans `dbo.RapportJournee.RapportSms` (UPDATE par clé naturelle `(Date, ContratId)` — la ligne `RapportJournee` est supposée déjà créée par FEAT 11 lors de l'enregistrement de l'heure d'arrivée). La génération du texte se déclenche **côté serveur** au moment du save du rapport du jour (FEAT 10 PUT endpoint), dans la **même transaction SQL** que les `DELETE + INSERT` des cases à cocher. Le texte est composé à partir d'un **template constant** embarqué dans le code backend (jamais en DB), avec **2 lignes systématiques** sur les horaires du jour (heure d'arrivée réelle vs. déclarée au contrat, heure de départ réelle vs. déclarée au contrat — cf. SFD-29, SFD-30, SFD-31 ci-dessous) puis **4 phrases conditionnelles** (Santé / Nourriture / Activités / Humeur) chacune incluse uniquement si la catégorie correspondante a au moins une case cochée. Le template ajoute une **salutation d'ouverture** avec le prénom du bébé et une **formule de clôture** signée par l'employé. Les deux lignes horaires permettent au parent de constater visuellement un éventuel écart (retard d'arrivée, départ anticipé) sans calcul manuel.

2. **Affichage du résumé** dans la textarea de l'onglet 2 de la fiche détaillée bébé : la textarea n'est plus pré-remplie en dur — son contenu est désormais lu depuis `RapportJournee.RapportSms` via un nouvel endpoint `GET /api/contrats/{ContratId}/rapport-sms`. Si aucun rapport n'a encore été enregistré aujourd'hui (`RapportSms IS NULL` ou ligne `RapportJournee` absente), la textarea reste **vide** avec un placeholder explicatif. La textarea est **lecture-seule** (le contenu est régénéré côté serveur à chaque save de FEAT 10 — toute édition manuelle serait écrasée au prochain save, anti-confusion utilisateur).

3. **Envoi du SMS** via le bouton `Envoyer aux parents` qui devient **fonctionnel** : un clic récupère le **numéro de téléphone principal** des parents (`Employeur.TelPersonnel` en priorité, fallback `TelPersonnel2` puis `TelProfessionnel`) et ouvre l'**application SMS native** du téléphone via un lien `sms:{numero}?body={texte_encodé}` (mécanisme HTML standard cross-platform iOS / Android). Aucune passerelle SMS serveur-side n'est utilisée — l'envoi reste manuel via l'app SMS de l'utilisateur (l'employé reste maître de l'envoi et le SMS est facturé sur son forfait, pas via un service tiers).

La spec **étend `spec-bebe-detaille` SFD-30** (bouton `Envoyer aux parents` jusqu'ici cosmétique → fonctionnel) et **étend `spec-rapport-du-jour` SFD-22** (le save du rapport persiste désormais aussi `RapportSms` dans la même transaction). La spec **dépend** de `spec-arrivees-departs` (FEAT 11) qui garantit qu'une ligne `RapportJournee` du jour existe pour permettre l'UPDATE — si aucune arrivée n'a été enregistrée, le save FEAT 10 reste fonctionnel mais le SMS n'est pas persisté (cf. BR-9, comportement degraded mode).

Aucun mockup HTML dédié n'est produit pour cette FEAT — la maquette canonique est l'onglet 2 (tab `report`) de `workspace/input/ui/9-1-Spec-Bebe-Detaile.html` (lignes 398-433 : `section-label` + `report-card` + `textarea` + `report-actions/btn-send`). La textarea hérite du markup existant ; seul son contenu devient dynamique et le bouton devient fonctionnel.

## Objective
L'employé connecté complète son rapport du jour pour un bébé (FEAT 10 — coche les cases Santé / Nourriture / Activités / Humeur dans le stepper), clique sur `Enregistrer le rapport` à l'étape 4 → le backend exécute en **transaction SQL unique** (1) le DELETE+INSERT des lignes `dbo.Rapport` (déjà câblé par FEAT 10) puis (2) la génération côté serveur d'un texte narratif structuré à partir du template constant + les libellés `Action.Nom` cochés, puis (3) l'UPDATE de `dbo.RapportJournee.RapportSms` par clé `(Date=today, ContratId)`. Au retour sur la fiche détaillée bébé `/bebes/{ContratId}` (onglet `Rapport du jour`), la textarea est désormais peuplée du texte persisté (chargé via `GET /api/contrats/{ContratId}/rapport-sms`). Un clic sur `Envoyer aux parents` ouvre l'application SMS native du téléphone avec le numéro principal du parent pré-rempli et le texte du rapport pré-saisi prêt à être envoyé — l'employé valide l'envoi depuis son app SMS.

## Quantified Goal (v7.0.0 — anti-GIGO)
- Metric: temps de génération du texte côté serveur (template render + UPDATE), temps de chargement du contenu de la textarea côté frontend (`GET /api/contrats/{ContratId}/rapport-sms`), temps de réponse du clic sur `Envoyer aux parents` (préparation du lien `sms:` côté client)
- Target: p95 génération + UPDATE serveur < 80 ms (la transaction FEAT 10 reste sous 600 ms p95 incluant cet ajout, soit < 13% du budget) ; p95 chargement textarea < 250 ms (1 requête SQL `SELECT RapportSms FROM RapportJournee WHERE Date=today AND ContratId=X`, payload < 1 KB) ; clic `Envoyer aux parents` → ouverture app SMS < 100 ms (préparation côté JS, pas de round-trip serveur)
- Deadline: livraison stack `kotlin-spring-boot × react × shadcn` au 2026-08-15

## Non-Functional Constraints (v7.0.0)
- Expected volume: ~5 rapports / employé / jour ouvré (un par bébé en garde) ⇒ ~5 générations de texte + UPDATE / employé / jour ; chargements textarea ~10 / employé / jour (assistante peut consulter plusieurs fois) ; clics `Envoyer aux parents` ~3-5 / employé / jour (certains rapports envoyés, d'autres consultés sans envoi) ; < 30k UPDATE/jour total beta Demo
- Performance SLA: p95 UPDATE `RapportSms` < 80 ms (cf. Quantified Goal) ; aucun impact perceptible sur la transaction FEAT 10 (qui reste < 600 ms p95) ; p95 `GET /api/contrats/{ContratId}/rapport-sms` < 250 ms ; pas de risque N+1 (1 SELECT JOIN unique pour récupérer cases cochées + libellés)
- Data retention: la colonne `RapportSms` est conservée indéfiniment (pas de purge automatique) ; chaque jour est une partition logique par `(ContratId, Date)` — la régénération à chaque save écrase la valeur précédente du jour (pas d'historique des versions intermédiaires) ; l'historique journalier reste interrogeable comme pour les autres colonnes de `RapportJournee` (hors scope de cette FEAT)
- Compliance: RGPD — le texte généré peut contenir le prénom du bébé et des observations de santé (informations potentiellement sensibles, notamment cat. 9 RGPD si pathologie identifiée) ; visible et envoyable uniquement par l'employé propriétaire du contrat (`Contrat.EmployeeId == session.EmployeeId`) ; jamais 403 (anti-énumération) — toujours 404 sur contrat hors périmètre ; le numéro de téléphone parent n'est jamais exposé directement à l'utilisateur (il est utilisé en construction du lien `sms:` côté JS mais pas affiché ni copié dans le clipboard)
- Integration: extension de l'endpoint backend `PUT /api/contrats/{ContratId}/rapport` (hérité de FEAT 10) — ajout d'un step de génération + UPDATE dans la même transaction ; nouvel endpoint `GET /api/contrats/{ContratId}/rapport-sms` retournant `{ rapportSms, parentTelephone, parentNom }` ; aucun service SMS externe (Twilio / OVHcloud SMS / Vonage) — l'envoi passe **exclusivement** par le lien `sms:` natif du téléphone qui ouvre l'app SMS de l'utilisateur ; aucun coût d'envoi côté SDD (le SMS est facturé sur le forfait de l'employé)
- Degraded mode: si la génération du texte ou l'UPDATE `RapportSms` échoue (rollback transaction FEAT 10 par contrainte SQL, timeout, exception template render), le save complet de FEAT 10 est rollbacké (atomicité — cf. AC-9) → un toast d'erreur générique s'affiche à l'utilisateur ; aucun état partiel n'est persisté (ni cases cochées, ni texte SMS) ; si la ligne `RapportJournee` du jour est absente (FEAT 11 non câblée pour ce bébé, arrivée non marquée), le save FEAT 10 réussit mais le SMS n'est **pas** persisté (UPDATE matche 0 ligne) — cf. BR-9 ; si le numéro de téléphone parent est NULL, le bouton `Envoyer aux parents` est désactivé avec tooltip explicatif (cf. AC-19)

## Actors
- Employé connecté : assistante maternelle authentifiée, identifiée par son `EmployeeId` issu de la variable singleton de session. Seul autorisé à consulter le rapport SMS et à déclencher l'envoi depuis l'app SMS native des contrats dont `Contrat.EmployeeId == session.EmployeeId`. Aucun accès à l'écran sans authentification.
- Parent (Employeur) : destinataire passif du SMS — n'a aucune interaction directe avec l'application SDD. Son numéro de téléphone (`Employeur.TelPersonnel` en priorité) est consommé en lecture par l'application pour construire le lien `sms:` (jamais affiché ni édité dans l'UI).

## Functional Needs

### Point d'entrée et navigation
- SFD-1: La spec **étend `spec-bebe-detaille` SFD-30** : le bouton `Envoyer aux parents` du `report-actions` de l'onglet `Rapport du jour` de `/bebes/{ContratId}` (jusqu'ici cosmétique non fonctionnel — cf. `spec-rapport-du-jour` BR-22) devient **fonctionnel** et déclenche l'ouverture de l'application SMS native du téléphone avec numéro et corps de message pré-remplis
- SFD-2: La spec **étend `spec-rapport-du-jour` SFD-22** : l'endpoint backend `PUT /api/contrats/{ContratId}/rapport` (save du stepper FEAT 10) intègre désormais dans sa transaction SQL un step supplémentaire de génération + UPDATE de `dbo.RapportJournee.RapportSms` — la chaîne `DELETE Rapport → INSERT Rapport → UPDATE RapportJournee.RapportSms` est **atomique** (cf. AC-9, BR-7)
- SFD-3: Aucune nouvelle route frontend n'est introduite — l'affichage et l'envoi s'effectuent **exclusivement** depuis l'onglet 2 (`Rapport du jour`) de la fiche détaillée bébé existante (`/bebes/{ContratId}`)

### Stockage du texte SMS — colonne `dbo.RapportJournee.RapportSms`
- SFD-4: La colonne `RapportSms` (`NVARCHAR(500) NULL`) de `dbo.RapportJournee` (déjà créée en base, cf. FEAT 11 SFD-3) stocke le texte du résumé narratif du jour pour le couple `(Date, ContratId)`. `NULL` signifie « pas encore généré » (aucun save FEAT 10 effectué aujourd'hui) ; une chaîne non vide signifie « rapport SMS prêt à envoyer ». Aucune sentinelle métier (ex. chaîne vide `""` ou `"PENDING"`) n'est utilisée — la distinction `NULL` vs chaîne non-NULL est strictement binaire
- SFD-5: La régénération à chaque save FEAT 10 **écrase** la valeur précédente de `RapportSms` pour le jour courant (pas de versionning, pas de merge) ; l'employé qui re-coche/décoche des cases puis réenregistre obtient un texte régénéré à partir de l'état final des cases — symétrique à la stratégie `DELETE + INSERT` de FEAT 10

### Génération du texte — template constant côté backend
- SFD-6: Le **template du message SMS** est stocké en **constante de code** dans le backend (objet Kotlin `companion object` ou équivalent — jamais en base de données, jamais en fichier de config externalisé pour cette FEAT). Le template est **versionné avec le code source** (visible en `git blame`), modifiable uniquement par une mise à jour de code suivie d'un déploiement. Aucune interface d'édition du template n'est exposée
- SFD-7: Le template canonique est le suivant (chaîne unique, sauts de ligne `\n` matérialisés) :
  ```
  Bonjour,

  Voici le rapport de la journée de {Prenom}.

  {ligne_arrivee}{ligne_depart}{phrase_sante}{phrase_nourriture}{phrase_activites}{phrase_humeur}

  Bien cordialement,
  {EmployeePrenom} {EmployeeNom}
  ```
  Les 2 placeholders `{ligne_arrivee}` et `{ligne_depart}` portent les phrases d'horaires systématiques définies en SFD-29 ; les 4 placeholders `{phrase_*}` portent les phrases conditionnelles définies en SFD-8. Les placeholders `{Prenom}` (du bébé), `{EmployeePrenom}` et `{EmployeeNom}` proviennent respectivement de `dbo.Contrat.Prenom`, `dbo.Employee.Prenom`, `dbo.Employee.Nom` (jointures côté serveur lors du save). L'ordre est strict : les 2 lignes horaires précèdent les 4 phrases catégories (la lecture par le parent commence par "à quelle heure" avant "qu'est-ce qui s'est passé").
- SFD-8: Les **4 phrases conditionnelles** sont définies comme **constantes templates secondaires** dans le code backend. Chaque phrase n'est ajoutée au texte final que si la catégorie correspondante (`IdCategorie` de `dbo.Action`) compte **au moins 1 case cochée** dans `dbo.Rapport (Date=today, ContratId=X, Valeur='1')`. Si le compte = 0, la phrase est **omise intégralement** (pas de placeholder vide, pas de phrase tronquée). Templates :
  - **Catégorie 1 — Santé** : `Santé : L'enfant présente aujourd'hui les signes suivants : {liste_sante}.\n` (omise si aucune case Santé cochée)
  - **Catégorie 2 — Nourriture** : `Repas : L'enfant a bien mangé aujourd'hui, notamment : {liste_nourriture}.\n` (omise si aucune case Nourriture cochée)
  - **Catégorie 3 — Activités** : `Activités : Une activité principale a été réalisée aujourd'hui : {liste_activites}.\n` (omise si aucune case Activité cochée)
  - **Catégorie 4 — Humeur** : `Humeur : Aujourd'hui, l'enfant a présenté les états suivants : {liste_humeur}.\n` (omise si aucune case Humeur cochée)
- SFD-9: Les **listes `{liste_*}`** sont construites en joignant les valeurs `dbo.Action.Nom` des cases cochées de la catégorie correspondante avec le séparateur **`, `** (virgule + espace) ; aucun enrichissement (article défini, mise en forme, capitalisation, accord, ponctuation autre que la virgule séparatrice) n'est appliqué côté serveur ; les libellés `Action.Nom` sont consommés **tels que stockés en base** (charge au DBA de les remplir avec des libellés cohérents — ex. `biberon`, `légumes`, `yaourt`)
- SFD-10: Les actions sont **triées par `ActionId` croissant** au sein de chaque catégorie (ordre stable SQL `ORDER BY a.IdCategorie ASC, a.ActionId ASC` — symétrique à `spec-rapport-du-jour` BR-17) ; aucun tri par fréquence d'usage, par ordre alphabétique du libellé, ou par horaire n'est appliqué
- SFD-11: Si **les 4 catégories ont 0 case cochée** (rapport entièrement vidé — symétrique à FEAT 10 SFD-23 où `actionIds: []` est légitime), le texte généré est **la coquille seule** (salutation + signature, sans les 4 phrases conditionnelles ; les 2 lignes horaires SFD-29 restent présentes si les données existent — elles sont indépendantes du contenu observationnel). La valeur `RapportSms` est alors une chaîne non-NULL mais ne contenant aucune information observationnelle — l'employé constate visuellement et choisit de ne pas envoyer le SMS (le bouton `Envoyer aux parents` reste actif mais l'envoi serait un message vide d'information — comportement assumé non bloquant)

### Heures d'arrivée et de départ — lignes systématiques (extension v7)
- SFD-29: Le rapport SMS comporte, **immédiatement après la salutation `Voici le rapport de la journée de {Prenom}.`** et **avant** les 4 phrases conditionnelles SFD-8, **deux lignes systématiques** sur les horaires du jour :
  - **Ligne arrivée** : `Heure d'arrivée : {HeureArriveeReelle} (heure prévue au contrat : {HeureArriveeDeclaree}).\n`
  - **Ligne départ** : `Heure de départ : {HeureDepartReel} (heure prévue au contrat : {HeureDepartDeclaree}).\n`

  Les heures sont formatées **`HH:MM`** (24h, zéros gauches, séparateur `:`). Si la valeur **réelle** correspondante (`dbo.RapportJournee.HeureArrivee` ou `dbo.RapportJournee.HeureDepart`) est NULL, **la ligne entière est omise** (BR-21). Si la valeur **déclarée** au contrat est NULL (jour non planifié au contrat — Dimanche en particulier, le schéma `dbo.Contrat` ne portant pas de colonnes `DimancheDebut`/`DimancheFin`), la sous-mention `(heure prévue au contrat : ...)` est remplacée par `(heure non prévue au contrat)` (BR-22). L'objectif est de permettre au parent de constater visuellement un retard / écart sans calcul, par simple comparaison des deux valeurs sur une même ligne.
- SFD-30: La récupération des 4 valeurs (`HeureArriveeReelle`, `HeureDepartReel`, `HeureArriveeDeclaree`, `HeureDepartDeclaree`) s'effectue **dans la même transaction SQL** que le step génération SMS (SFD-12, AC-3), via une requête additionnelle exécutée **juste avant** l'UPDATE de `RapportSms` :
  ```sql
  SELECT
    rj.HeureArrivee AS HeureArriveeReelle,
    rj.HeureDepart  AS HeureDepartReel,
    CASE ((DATEDIFF(DAY, '2024-01-01', CAST(getdate() AS DATE)) % 7) + 7) % 7
      WHEN 0 THEN c.LundiDebut
      WHEN 1 THEN c.MardiDebut
      WHEN 2 THEN c.MercrediDebut
      WHEN 3 THEN c.JeudiDebut
      WHEN 4 THEN c.VendrediDebut
      WHEN 5 THEN c.SamediDebut
      WHEN 6 THEN NULL                       -- Dimanche (colonne absente du schéma)
    END AS HeureArriveeDeclaree,
    CASE ((DATEDIFF(DAY, '2024-01-01', CAST(getdate() AS DATE)) % 7) + 7) % 7
      WHEN 0 THEN c.LundiFin
      WHEN 1 THEN c.MardiFin
      WHEN 2 THEN c.MercrediFin
      WHEN 3 THEN c.JeudiFin
      WHEN 4 THEN c.VendrediFin
      WHEN 5 THEN c.SamediFin
      WHEN 6 THEN NULL                       -- Dimanche (colonne absente du schéma)
    END AS HeureDepartDeclaree
  FROM dbo.Contrat c
  LEFT JOIN dbo.RapportJournee rj
    ON rj.ContratId = c.ContratId
   AND rj.[Date]    = CAST(getdate() AS DATE)
  WHERE c.ContratId = @ContratId
    AND c.EmployeeId = @SessionEmployeeId;
  ```
  Le calcul du jour de la semaine est **`DATEFIRST`-indépendant** : la formule `((DATEDIFF(DAY, '2024-01-01', CAST(getdate() AS DATE)) % 7) + 7) % 7` retourne 0=Lundi … 5=Samedi, 6=Dimanche, quelle que soit la valeur de `@@DATEFIRST` du serveur SQL (`2024-01-01` est canoniquement un lundi). La requête utilisateur initiale (`DATEPART(WEEKDAY, GETDATE())` avec mapping 1=Dimanche..7=Samedi) suppose `SET DATEFIRST 7` (US-default) et est **rejetée** en faveur de la formule canonique pour robustesse cross-environnement. Le `LEFT JOIN RapportJournee` garantit qu'un bébé sans ligne du jour retourne `HeureArriveeReelle: NULL` et `HeureDepartReel: NULL` (le rapport SMS est généré quand-même, mais les deux lignes seront omises par BR-21 — comportement degraded mode symétrique BR-9)
- SFD-31: Le formatage `HH:MM` est appliqué **côté serveur (application layer)** après extraction du `TIME` SQL :
  - Prisma retourne le `@db.Time` comme `Date` JavaScript ancré à `1970-01-01` UTC ; le formatage extrait `getUTCHours()` et `getUTCMinutes()` puis applique `String(n).padStart(2, '0')` sur chaque
  - Aucune dépendance lib `date-fns` / `dayjs` / `luxon` n'est introduite pour cette FEAT (formatage trivial 2 lignes JS)
  - Si la lecture Prisma retourne `null`, le formateur retourne `null` (la ligne sera omise par BR-21 OU la mention `(non prévue)` sera utilisée par BR-22)

### Génération côté serveur — SQL et flux transactionnel
- SFD-12: Au moment du save FEAT 10 (`PUT /api/contrats/{ContratId}/rapport`), **après les `DELETE` + `INSERT` de `dbo.Rapport`** (cf. `spec-rapport-du-jour` SFD-22) et **dans la même transaction**, le backend exécute la requête SQL canonique de récupération des cases cochées **enrichies du libellé et de la catégorie** :
  ```sql
  SELECT
    a.IdCategorie,
    a.ActionId,
    a.Nom
  FROM dbo.Rapport r
  INNER JOIN dbo.[Action] a ON a.ActionId = r.ActionId
  WHERE r.ContratId = @ContratId
    AND r.[Date]    = CAST(getdate() AS DATE)
    AND r.Valeur    = '1'
  ORDER BY a.IdCategorie ASC, a.ActionId ASC;
  ```
  Le résultat est groupé en mémoire par `IdCategorie` (Map<Int, List<String>> côté Kotlin) puis passé au moteur de template (cf. SFD-7, SFD-8) pour produire la chaîne finale. **Note schéma** : `a.Phrase` n'est **pas** consommé par cette FEAT (les phrases sont dans le template constant côté code, pas dans la colonne `Action.Phrase` qui reste pour un usage hypothétique futur — out of scope)
- SFD-13: Le backend récupère également **dans la même transaction** les informations nécessaires aux placeholders `{Prenom}`, `{EmployeePrenom}`, `{EmployeeNom}` via une requête (ou un cache déjà chargé en début de transaction) :
  ```sql
  SELECT
    c.Prenom        AS ContratPrenom,
    e.Prenom        AS EmployeePrenom,
    e.Nom           AS EmployeeNom
  FROM dbo.Contrat c
  INNER JOIN dbo.Employee e ON e.EmployeeId = c.EmployeeId
  WHERE c.ContratId = @ContratId
    AND c.EmployeeId = @SessionEmployeeId;
  ```
  Le filtre `EmployeeId = @SessionEmployeeId` est redondant avec la vérification déjà effectuée par FEAT 10 au début de sa transaction (`spec-rapport-du-jour` BR-2) — il est conservé en défense en profondeur ; un résultat à 0 ligne ici déclenche un rollback (état conceptuellement impossible dans le flux normal mais traité par sécurité)
- SFD-14: Une fois le texte généré (chaîne complète assemblée selon SFD-7, SFD-8, SFD-9), le backend exécute l'UPDATE SQL canonique :
  ```sql
  UPDATE dbo.RapportJournee
     SET RapportSms = @GeneratedText
   WHERE ContratId = @ContratId
     AND [Date]    = CAST(getdate() AS DATE);
  ```
  L'UPDATE est **paramétré** (`@GeneratedText`, `@ContratId`) — aucune concaténation de la chaîne dans la requête (anti-injection, symétrique `spec-rapport-du-jour` BR-5). Le nombre de lignes affectées est inspecté :
  - **1 ligne** mise à jour → succès, la transaction continue puis COMMIT
  - **0 ligne** mise à jour (ligne `RapportJournee` du jour absente — bébé non « marqué arrivé » via FEAT 11) → le backend **logue un WARN** côté serveur (`RapportSms not persisted: no RapportJournee row for ContratId=X, Date=today`) mais **ne déclenche PAS** de rollback de FEAT 10 ; la transaction COMMIT normalement (les cases cochées sont persistées dans `Rapport`). Le frontend reçoit `204 No Content` comme prévu par FEAT 10. La textarea de l'onglet 2 affichera ultérieurement « Marquez d'abord l'arrivée du bébé pour générer le rapport SMS » (cf. SFD-20) au prochain chargement — cf. BR-9 (comportement degraded mode)

### Lecture du texte SMS — endpoint dédié
- SFD-15: Un nouvel endpoint backend `GET /api/contrats/{ContratId}/rapport-sms` retourne pour le jour courant le contenu nécessaire à l'onglet 2 de la fiche détaillée bébé :
  ```sql
  SELECT
    r.RapportSms,
    emp.Prenom        AS ParentPrenom,
    emp.Nom           AS ParentNom,
    emp.TelPersonnel,
    emp.TelPersonnel2,
    emp.TelProfessionnel
  FROM dbo.Contrat c
  LEFT JOIN dbo.RapportJournee r
    ON r.ContratId = c.ContratId
   AND r.[Date]    = CAST(getdate() AS DATE)
  LEFT JOIN dbo.Employeur emp
    ON emp.EmployeurId = c.EmployeurId
  WHERE c.ContratId = @ContratId
    AND c.EmployeeId = @SessionEmployeeId;
  ```
  Le `LEFT JOIN RapportJournee` garantit qu'un bébé sans ligne du jour retourne `rapportSms: null` (au lieu de 404). Le `LEFT JOIN Employeur` couvre le cas hypothétique d'un `Contrat.EmployeurId IS NULL` (parent non rattaché — `parentTelephone: null` côté JSON). Le filtre WHERE garantit l'anti-énumération : un `ContratId` hors périmètre retourne 0 ligne → **404** côté API (cf. BR-3)
- SFD-16: La réponse JSON de `GET /api/contrats/{ContratId}/rapport-sms` est un objet aplati :
  ```json
  {
    "rapportSms": "Bonjour,\n\nVoici le rapport de la journée de Lina.\n..." | null,
    "parentNom": "Bouchet" | null,
    "parentPrenom": "Sophie" | null,
    "parentTelephone": "0612345678" | null
  }
  ```
  Le champ `parentTelephone` est calculé côté serveur par **résolution en cascade** : `TelPersonnel ?? TelPersonnel2 ?? TelProfessionnel ?? null` (le premier non-NULL gagne — cf. BR-12). Les trois colonnes brutes ne sont **pas** exposées séparément côté frontend (anti-fuite). La chaîne retournée est nettoyée des caractères non-numériques côté serveur (espaces, points, parenthèses, tirets), conservant uniquement les chiffres et un éventuel `+` initial — facilite l'injection dans le lien `sms:` (cf. BR-13)
- SFD-17: Le payload est **strictement** limité aux 4 champs ci-dessus — aucun autre champ (autre numéro de téléphone, email, prénom du second parent, ID interne `EmployeurId`) n'est exposé par cet endpoint (principle of least exposure)

### Affichage côté frontend — onglet 2 fiche détaillée bébé
- SFD-18: Au chargement de l'onglet 2 (`Rapport du jour`) de la fiche détaillée bébé, le frontend exécute **une seule** requête `GET /api/contrats/{ContratId}/rapport-sms` (orthogonale à la requête principale de l'onglet 1 — chaque onglet a sa propre stratégie de chargement, cf. `spec-bebe-detaille`). Le payload retourné peuple la textarea et les attributs du bouton `Envoyer aux parents` (cf. SFD-21)
- SFD-19: La textarea (`.report-card__textarea` du mockup `9-1-Spec-Bebe-Detaile.html`) est passée en **lecture seule** (`readonly` HTML / `readOnly` React) : son contenu est alimenté **exclusivement** par la valeur `rapportSms` reçue ; aucune saisie manuelle n'est conservée (toute édition côté UI serait écrasée au prochain save FEAT 10). Le style visuel `readonly` doit rester lisible (fond, couleur, hauteur identiques au mockup — `disabled` ne convient pas car il assombrit la zone et bloque la sélection / copie du texte)
- SFD-20: Si `rapportSms === null` (aucun rapport généré aujourd'hui), la textarea affiche un **placeholder** explicatif (attribut `placeholder` HTML) :
  - **Cas A — bébé non encore « marqué arrivé »** (détection : la requête FEAT 11 `GET /api/bebes` retournerait `heureArrivee: null` pour ce bébé, ou plus simplement : si `parentTelephone !== null` mais `rapportSms === null`, on n'a pas assez d'info pour distinguer — on choisit donc le placeholder générique ci-dessous, lisible dans les deux cas)
  - **Placeholder générique** : `Le rapport SMS sera généré automatiquement après l'enregistrement des cases cochées dans « Rapport du jour ». Si le bouton reste vide, vérifiez d'abord que l'arrivée du bébé est marquée.`
  
  Aucun appel backend supplémentaire ne tente de discriminer les deux cas — le placeholder unique couvre les deux scénarios sans surcoût
- SFD-21: Le bouton `Envoyer aux parents` (`.btn-send` du mockup) devient **fonctionnel** :
  - Si `rapportSms === null` OU `parentTelephone === null` → bouton **désactivé** (attribut `disabled`, opacité 0.55, `cursor: not-allowed`) avec **tooltip** (`title=`) approprié :
    - `rapportSms === null` → `Aucun rapport disponible — enregistrez d'abord les cases cochées dans « Rapport du jour ».`
    - `parentTelephone === null` → `Aucun numéro de téléphone parent disponible dans le contrat.`
    - Les deux NULL → priorité au message `rapportSms === null` (cause-racine la plus probable)
  - Si `rapportSms !== null` ET `parentTelephone !== null` → bouton **actif** ; un clic exécute l'algorithme SFD-22

### Envoi du SMS — pattern HTML natif `sms:`
- SFD-22: Au clic sur `Envoyer aux parents` (bouton actif), le frontend construit l'URI `sms:` puis déclenche la navigation vers ce lien :
  ```
  sms:{parentTelephone}?body={encoded_rapportSms}
  ```
  où `{encoded_rapportSms}` est la valeur `rapportSms` passée par `encodeURIComponent(...)` côté JS (encodage des sauts de ligne, espaces, caractères spéciaux conformément à RFC 3986). La navigation est déclenchée via `window.location.href = "sms:..."` ou en construisant un `<a href="sms:..."></a>` cliqué programmatiquement. Le **device** (smartphone / tablette) intercepte le lien et **ouvre son application SMS native** (Messages iOS, Messages Android, SMS Samsung, etc.) avec le numéro et le corps pré-remplis ; l'employé voit le brouillon, vérifie, ajuste éventuellement, puis envoie depuis l'app SMS
- SFD-23: Aucun callback backend n'est déclenché par l'envoi du SMS — l'application SDD ne sait **jamais** si le SMS a été effectivement envoyé, ni quand. Le suivi des envois (timestamp, statut delivery, opt-out parent) est **out of scope** (cf. Out of Scope — FEAT future avec passerelle SMS serveur-side type Twilio)
- SFD-24: Si le device de l'employé n'est pas un smartphone (ex. usage desktop / navigateur de bureau sans handler `sms:` enregistré), le clic peut produire un comportement variable selon le navigateur (erreur silencieuse, popup `Aucune application n'est associée à ce protocole`, etc.). Aucune détection préventive n'est implémentée côté frontend (le case d'usage cible est mobile — cf. mockup `nj-phone` du design system) ; un fallback type « copier dans le presse-papier » est laissé en **Out of Scope** (FEAT future)

### États de chargement et erreur
- SFD-25: Pendant le chargement initial de `GET /api/contrats/{ContratId}/rapport-sms`, la textarea affiche un **squelette/spinner** (équivalent visuel à `spec-rapport-du-jour` SFD-28) ; le bouton `Envoyer aux parents` est désactivé pendant ce chargement (état loading)
- SFD-26: Si le `ContratId` n'appartient pas à l'employé connecté (404 sur le GET), le frontend affiche une page « Bébé introuvable » avec bouton `Retour aux bébés` (symétrique à `spec-rapport-du-jour` SFD-29 et `spec-bebe-detaille` AC-2)
- SFD-27: En cas d'échec backend du GET (500, timeout), la textarea affiche un message d'erreur générique `Échec du chargement du rapport. Réessayez.` et un bouton `Réessayer` rechargeant l'endpoint ; le bouton `Envoyer aux parents` reste désactivé
- SFD-28: La session expirée pendant la consultation (401 sur le GET) déclenche une redirection frontend vers `/login` (cf. `spec-connexion`)

## Business Rules
- BR-1: l'endpoint `GET /api/contrats/{ContratId}/rapport-sms` retourne 0 ligne (et 404) si `Contrat.EmployeeId != session.EmployeeId` ; aucun rapport SMS n'est exposé hors du périmètre de l'employé connecté (anti-énumération — symétrique `spec-rapport-du-jour` BR-1)
- BR-2: l'extension de l'endpoint `PUT /api/contrats/{ContratId}/rapport` (FEAT 10) vérifie également `Contrat.EmployeeId == session.EmployeeId` AVANT la génération du texte SMS et l'UPDATE de `RapportJournee.RapportSms` ; sinon 404 et **aucune modification** n'est effectuée (ni `Rapport`, ni `RapportJournee.RapportSms`) — hérité de `spec-rapport-du-jour` BR-2
- BR-3: `@SessionEmployeeId` provient exclusivement de la variable singleton de session ; aucun paramètre de requête (header, body, query) ne peut le surcharger (symétrique `spec-rapport-du-jour` BR-3)
- BR-4: la **date** utilisée pour le filtre `Rapport.Date` et `RapportJournee.Date` est **toujours** `CAST(getdate() AS DATE)` côté serveur (date du serveur, locale TZ-naive — symétrique `spec-rapport-du-jour` BR-4 et `spec-arrivees-departs` BR-4) ; aucun paramètre `date` côté query / body ne peut la surcharger (anti-tampering — empêche un client de générer un rapport SMS pour un jour passé)
- BR-5: les requêtes SQL sont **paramétrées** (`@ContratId`, `@SessionEmployeeId`, `@GeneratedText`) ; aucune concaténation de chaîne — y compris pour le texte SMS qui est passé en paramètre `@GeneratedText` à l'UPDATE (anti-injection, symétrique `spec-rapport-du-jour` BR-5)
- BR-6: le **template du SMS** (chaîne canonique de SFD-7 + 4 phrases conditionnelles de SFD-8) est stocké **en constante de code** dans le backend (objet Kotlin `companion object` ou équivalent — fichier `RapportSmsTemplate.kt` ou nom équivalent du stack actif) ; aucune persistance en base de données, aucun fichier de config externe, aucun mécanisme de hot-reload — toute évolution passe par modification du code source + déploiement (visible en `git blame`)
- BR-7: la chaîne complète `DELETE Rapport → INSERT Rapport → SELECT Rapport JOIN Action → UPDATE RapportJournee.RapportSms` s'exécute dans une **transaction SQL unique** ; échec d'une étape → rollback intégral (atomicité garantie — aucun état partiel persisté en base) — étend `spec-rapport-du-jour` BR-6
- BR-8: la régénération à chaque save FEAT 10 **écrase** la valeur précédente de `RapportSms` du jour (pas d'historique des versions intermédiaires, pas de merge) ; symétrique à la stratégie DELETE + INSERT de FEAT 10
- BR-9: si la ligne `RapportJournee` du jour est absente au moment du save FEAT 10 (bébé non « marqué arrivé » via FEAT 11), l'UPDATE de `RapportSms` matche **0 ligne** ; le backend **logue un WARN** côté serveur mais **ne déclenche PAS** de rollback de FEAT 10 (les cases cochées restent persistées) ; la transaction COMMIT normalement et `204 No Content` est retourné — comportement degraded mode assumé (cf. SFD-14 + AC-12)
- BR-10: si **les 4 catégories ont 0 case cochée** (`actionIds: []`), le texte généré reste **non-NULL** mais consiste uniquement en la coquille du template (salutation + signature, sans les 4 phrases conditionnelles — cf. SFD-11) ; aucune sentinelle NULL n'est insérée pour ce cas
- BR-11: les libellés `Action.Nom` consommés par le générateur de texte sont utilisés **tels que stockés en base** (sans transformation, sans capitalisation, sans accord — le DBA est responsable de la qualité éditoriale des libellés ; cf. `spec-rapport-du-jour` BR-10 pour l'analogue côté `Action.Icon`)
- BR-12: le **numéro de téléphone parent** est résolu **côté serveur** par la cascade `TelPersonnel ?? TelPersonnel2 ?? TelProfessionnel ?? null` sur `dbo.Employeur` (joint à `Contrat.EmployeurId`). Si `Contrat.EmployeurId IS NULL` (parent non rattaché — cas conceptuel rare hérité du schéma) → `parentTelephone: null` côté JSON. Si l'`Employeur` existe mais ses 3 colonnes téléphone sont NULL → idem `parentTelephone: null`. Le frontend interprète `null` comme « bouton désactivé » (cf. SFD-21)
- BR-13: le numéro de téléphone retourné par le backend est **nettoyé** : suppression des caractères non-numériques (espaces, points, parenthèses, tirets, antislash, mais conservation d'un éventuel `+` initial pour les numéros internationaux). Exemples : `"06 12 34 56 78"` → `"0612345678"` ; `"+33 6 12 34 56 78"` → `"+33612345678"` ; `"01.44.55.66.77"` → `"0144556677"`. Ce nettoyage facilite la construction du lien `sms:` côté frontend (qui n'a pas besoin d'effectuer le nettoyage lui-même)
- BR-14: la **textarea** de l'onglet 2 est **lecture seule** (`readonly`) : son contenu reflète **exclusivement** la valeur `rapportSms` retournée par le backend ; aucune édition manuelle n'est conservée (toute saisie serait écrasée au prochain save FEAT 10 — anti-confusion utilisateur)
- BR-15: si la chaîne générée dépasse **500 caractères** (limite stockage `RapportSms NVARCHAR(500)`), le backend **tronque** à 497 caractères et ajoute `...` (3 caractères, donc 500 final). Un WARN est logué côté serveur (`RapportSms truncated for ContratId=X, original_length=N, truncated_to=500`). Le frontend ne fait **aucune** détection de troncature — il affiche tel quel ; l'employé peut ajuster le SMS dans l'app SMS native si besoin (les SMS modernes supportent jusqu'à ~1530 caractères concaténés mais le coût ne dépend pas du volume affiché en app native — il dépend du forfait de l'employé et du nombre de segments envoyés)
- BR-16: aucune information technique (stack trace, exception SQL, nom de table interne, identifiant `EmployeurId`) n'est exposée dans les réponses d'erreur côté API ; le frontend affiche uniquement des toasts génériques (symétrique `spec-rapport-du-jour` BR-16)
- BR-17: aucun envoi SMS effectif n'est déclenché par le backend SDD — l'envoi passe **exclusivement** par le lien `sms:` natif du téléphone client. Le backend n'a **aucune** dépendance à un service tiers (Twilio, OVHcloud SMS, Vonage, etc.) ni à une passerelle SMS interne ; aucun coût d'envoi côté SDD ; le SMS est facturé sur le forfait téléphonique de l'employé (cf. SFD-23)
- BR-18: aucune trace d'envoi (timestamp, statut delivery, lecture) n'est persistée par cette FEAT — l'application n'a **jamais** de feedback sur l'effectivité de l'envoi (cf. SFD-23, Out of Scope FEAT future avec passerelle SMS)
- BR-19: le champ `Contrat.Prenom` (prénom du bébé) est inséré tel que stocké dans le template (`{Prenom}` — cf. SFD-7) sans transformation ; si `Contrat.Prenom` est NULL ou chaîne vide (cas conceptuel improbable côté contrat actif), le template insère une chaîne vide (le rendu sera `Voici le rapport de la journée de .` — anomalie visuelle assumée, signal que le contrat est mal renseigné côté DBA)
- BR-20: le champ `Employee.Prenom`+`Employee.Nom` (signataire du SMS) est récupéré via la jointure `Contrat → Employee` (cf. SFD-13) ; si l'un est NULL, le rendu insère une chaîne vide à sa place (espacement préservé) — cas conceptuel improbable car `Employee` actif a normalement ces champs renseignés à l'inscription (cf. `spec-inscription`)
- BR-21: si `dbo.RapportJournee.HeureArrivee` est NULL pour `(ContratId, Date=today)` (bébé non marqué arrivé via FEAT 11), la ligne `Heure d'arrivée : ...` du SMS est **omise intégralement** (pas de mention "non marquée", pas de placeholder vide, pas de tiret). Symétrique pour `HeureDepart` / ligne `Heure de départ : ...`. Les deux omissions sont **indépendantes** : un bébé arrivé mais pas encore parti voit la ligne arrivée présente et la ligne départ omise (cas le plus fréquent quand le save est déclenché en fin de matinée)
- BR-22: si **l'heure déclarée** au contrat est NULL pour le jour courant (jour non planifié — typiquement Dimanche, le schéma `dbo.Contrat` ne portant pas de colonnes `DimancheDebut`/`DimancheFin` — OU planning incomplet renseigné par le DBA), la sous-mention `(heure prévue au contrat : {HH:MM})` est remplacée par `(heure non prévue au contrat)` dans la ligne correspondante. La ligne reste présente tant que la valeur **réelle** existe (BR-21 prime sur BR-22 pour l'omission de ligne entière)
- BR-23: les heures **déclarées** (`{Jour}Debut`/`{Jour}Fin` du contrat) sont sélectionnées sur la base du **jour courant côté serveur** uniquement, jamais d'un paramètre client (query, body, header) — anti-tampering, symétrique BR-4. Le calcul du jour de la semaine utilise la formule canonique `DATEFIRST`-indépendante SFD-30 (jamais `DATEPART(WEEKDAY, ...)` brut)

## Acceptance Criteria
- AC-1: la spec **étend `spec-bebe-detaille` SFD-30** : le bouton `Envoyer aux parents` du `report-actions` de l'onglet 2 de `/bebes/{ContratId}` (jusqu'ici cosmétique non fonctionnel) devient fonctionnel — clic ouvre l'application SMS native du téléphone (cf. AC-15) si bouton actif (cf. AC-14)
- AC-2: la spec **étend `spec-rapport-du-jour` SFD-22** : l'endpoint backend `PUT /api/contrats/{ContratId}/rapport` (save du stepper FEAT 10) intègre désormais, dans sa transaction SQL existante, un step supplémentaire de génération du texte SMS + UPDATE de `dbo.RapportJournee.RapportSms` — vérifiable par test d'intégration (avant : `SELECT RapportSms FROM RapportJournee WHERE Date=today AND ContratId=X` → NULL ; après save : valeur non-NULL contenant les libellés cochés)
- AC-3: au save FEAT 10 (PUT), le backend exécute en plus du `DELETE` + `INSERT` de `dbo.Rapport` (déjà câblé), dans la **même transaction** : (1) `SELECT a.IdCategorie, a.ActionId, a.Nom FROM Rapport r INNER JOIN Action a WHERE r.ContratId=@ContratId AND r.Date=CAST(getdate() AS DATE) AND r.Valeur='1' ORDER BY a.IdCategorie, a.ActionId` ; (2) génération du texte côté serveur via template constant ; (3) `UPDATE RapportJournee SET RapportSms = @GeneratedText WHERE ContratId=@ContratId AND Date=CAST(getdate() AS DATE)` — vérifiable côté logs SQL
- AC-4: le template du SMS est stocké **en constante de code** dans le backend (visible en `git blame` du fichier source — ex. `RapportSmsTemplate.kt`) ; aucune chaîne template n'est lue depuis la base de données ni depuis un fichier de config externe (vérifiable par grep du codebase + test d'intégration : modifier la valeur en base ne change pas la sortie générée)
- AC-5: si une case Santé est cochée (catégorie 1), le texte contient exactement la phrase `Santé : L'enfant présente aujourd'hui les signes suivants : {liste_sante}.` (avec les libellés `Action.Nom` joints par `, ` dans l'ordre `ActionId ASC`)
- AC-6: si une case Nourriture est cochée (catégorie 2), le texte contient exactement la phrase `Repas : L'enfant a bien mangé aujourd'hui, notamment : {liste_nourriture}.`
- AC-7: si une case Activités est cochée (catégorie 3), le texte contient exactement la phrase `Activités : Une activité principale a été réalisée aujourd'hui : {liste_activites}.`
- AC-8: si une case Humeur est cochée (catégorie 4), le texte contient exactement la phrase `Humeur : Aujourd'hui, l'enfant a présenté les états suivants : {liste_humeur}.`
- AC-9: si une catégorie a 0 case cochée (count=0), la phrase correspondante est **intégralement omise** du texte généré (pas de placeholder vide, pas de phrase tronquée, pas de mention « aucun élément ») — vérifiable par test : enregistrer un rapport avec seulement des cases Santé cochées → le texte ne contient ni la phrase Repas ni la phrase Activités ni la phrase Humeur
- AC-10: si les 4 catégories ont 0 case cochée (`actionIds: []`), le texte généré contient **uniquement** la coquille (salutation + signature), valeur non-NULL côté DB — vérifiable par test : save avec payload `{ actionIds: [] }` → `RapportSms` non-NULL, longueur ~80-120 chars
- AC-11: en cas d'échec de la génération ou de l'UPDATE `RapportSms` (exception SQL, contrainte violée, timeout), la **transaction entière FEAT 10 est rollbackée** : ni les lignes `Rapport` ni la colonne `RapportSms` ne sont modifiées (vérifiable par test : injecter une exception template render → `SELECT COUNT(*) FROM Rapport WHERE ContratId=X AND Date=today` retourne la valeur d'avant le save, et `RapportSms` reste à sa valeur précédente)
- AC-12: si la ligne `RapportJournee` du jour est **absente** (bébé non marqué arrivé), l'UPDATE `RapportSms` matche 0 ligne, **aucun rollback** n'est déclenché (FEAT 10 reste idempotente — les cases cochées sont persistées) ; le backend logue un WARN serveur-side ; le frontend reçoit `204 No Content` et redirige vers `/bebes/{ContratId}` comme d'habitude (cf. `spec-rapport-du-jour` AC-22)
- AC-13: un nouvel endpoint `GET /api/contrats/{ContratId}/rapport-sms` retourne le payload aplati `{ rapportSms, parentNom, parentPrenom, parentTelephone }` (cf. SFD-16) — vérifiable par test : appeler le GET avec un `ContratId` valide → réponse 200 avec les 4 champs (chacun pouvant être null selon le contexte de SFD-15)
- AC-14: la textarea de l'onglet 2 est passée en **lecture seule** (`readonly`) ; aucune saisie manuelle n'est conservée (vérifiable : taper dans la textarea, recharger la page → le contenu original revient) ; le style visuel reste lisible (pas de fond grisé `disabled`)
- AC-15: si `rapportSms === null` OU `parentTelephone === null`, le bouton `Envoyer aux parents` est **désactivé** (HTML `disabled`, opacité 0.55) avec tooltip approprié (cf. SFD-21) ; un clic ne déclenche **aucune** action (vérifiable côté DevTools Network)
- AC-16: si `rapportSms !== null` ET `parentTelephone !== null`, le bouton `Envoyer aux parents` est **actif** ; un clic déclenche la navigation vers le lien `sms:{parentTelephone}?body={encoded_rapportSms}` — vérifiable sur device mobile : l'app SMS native s'ouvre avec numéro et corps pré-remplis
- AC-17: le numéro de téléphone parent est résolu **côté serveur** par la cascade `TelPersonnel ?? TelPersonnel2 ?? TelProfessionnel ?? null` ; le frontend ne reçoit qu'un seul champ `parentTelephone` (jamais les trois colonnes séparément) — vérifiable par test : 3 contrats avec respectivement seulement `TelPersonnel`, seulement `TelPersonnel2`, seulement `TelProfessionnel` renseignés → le GET retourne le bon numéro à chaque fois ; un 4ème contrat avec les 3 colonnes NULL retourne `parentTelephone: null`
- AC-18: le numéro de téléphone retourné par le backend est **nettoyé** des caractères non-numériques sauf le `+` initial éventuel (cf. BR-13) — vérifiable par test : un téléphone stocké `"06 12 34 56 78"` retourne `"0612345678"`, un téléphone stocké `"+33 6 12 34 56 78"` retourne `"+33612345678"`
- AC-19: si `Contrat.EmployeurId IS NULL` (parent non rattaché — cas conceptuel rare) OU si l'`Employeur` rattaché a ses 3 colonnes téléphone NULL → `parentTelephone: null` côté JSON ; le bouton `Envoyer aux parents` est désactivé avec tooltip `Aucun numéro de téléphone parent disponible dans le contrat.`
- AC-20: la chaîne générée si > 500 caractères est **tronquée** par le backend à 497 caractères + `...` (total 500) avant l'UPDATE ; un WARN serveur-side est logué (cf. BR-15) — vérifiable par test : cocher beaucoup d'actions de libellés longs jusqu'à dépasser 500 chars → `RapportSms` en DB termine par `...` et fait exactement 500 chars
- AC-21: la session expirée pendant le chargement (401 sur le GET) déclenche une redirection frontend vers `/login` (cf. `spec-connexion`)
- AC-22: un accès direct à `GET /api/contrats/{ContratId}/rapport-sms` avec un `ContratId` n'appartenant pas à l'employé connecté retourne **404** (jamais 403) ; le frontend affiche la page "Bébé introuvable" (cf. `spec-rapport-du-jour` AC-3)
- AC-23: l'endpoint `GET /api/contrats/{ContratId}/rapport-sms` n'expose **aucun autre champ** que les 4 documentés en SFD-16 — vérifiable par inspection du payload : pas de `tel_personnel`, pas de `tel_personnel2`, pas de `tel_professionnel`, pas de `employeurId`, pas de `email`
- AC-24: pendant le chargement initial du GET, la textarea affiche un squelette/spinner ; le bouton `Envoyer aux parents` est désactivé pendant cet état (cf. SFD-25)
- AC-25: en cas d'échec backend du GET (500, timeout), la textarea affiche `Échec du chargement du rapport. Réessayez.` + bouton `Réessayer` rechargeant l'endpoint ; le bouton `Envoyer aux parents` reste désactivé (cf. SFD-27)
- AC-26: aucun envoi SMS effectif n'est déclenché par le backend SDD — aucune dépendance NuGet/npm/maven à Twilio, OVHcloud SMS, Vonage, ou équivalent dans le code de la FEAT (vérifiable par grep du `pom.xml`/`build.gradle.kts`/`package.json` post-livraison)
- AC-27: les requêtes SQL du save FEAT 10 enrichi sont **paramétrées** (`@ContratId`, `@SessionEmployeeId`, `@GeneratedText`) — vérifiable côté logs SQL : la chaîne `@GeneratedText` n'est jamais concaténée littéralement dans l'UPDATE (anti-injection, même quand `RapportSms` contient des caractères spéciaux SQL comme `'` ou `;`)
- AC-28: les libellés `Action.Nom` consommés par le générateur de texte sont restitués **tels que stockés en base** (sans transformation) — vérifiable par test : modifier un libellé `Action.Nom = "biberon de lait"` en base, relancer un save → le texte généré contient exactement `biberon de lait` (pas `Biberon de lait`, pas `Biberons de lait`)
- AC-29: si `dbo.RapportJournee.HeureArrivee` ET `HeureDepart` sont non-NULL pour `(ContratId, Date=today)`, le texte SMS contient, **immédiatement après** `Voici le rapport de la journée de {Prenom}.` et **avant** toute phrase catégorie, exactement deux lignes consécutives :
  - `Heure d'arrivée : HH:MM (heure prévue au contrat : HH:MM).` (ou `(heure non prévue au contrat).` si la déclarée est NULL — BR-22)
  - `Heure de départ : HH:MM (heure prévue au contrat : HH:MM).` (ou `(heure non prévue au contrat).` si la déclarée est NULL — BR-22)

  Vérifiable par test : insérer en base `RapportJournee.HeureArrivee = '08:35'`, `HeureDepart = '17:45'`, `Contrat.LundiDebut = '08:30'`, `Contrat.LundiFin = '18:00'`, déclencher save un lundi → `RapportSms` contient exactement les chaînes `Heure d'arrivée : 08:35 (heure prévue au contrat : 08:30).` et `Heure de départ : 17:45 (heure prévue au contrat : 18:00).`
- AC-30: si `HeureArrivee` est NULL (bébé non marqué arrivé), la ligne `Heure d'arrivée : ...` est **entièrement absente** du texte SMS — vérifiable par test : save sans ligne `RapportJournee` du jour → `RapportSms` ne contient pas la sous-chaîne `Heure d'arrivée`. Symétrique pour `HeureDepart` / ligne `Heure de départ : ...`. Les deux omissions sont indépendantes (cas mixte arrivée présente / départ absent doit fonctionner)
- AC-31: le jour de la semaine utilisé pour sélectionner les colonnes `{Jour}Debut`/`{Jour}Fin` du contrat est calculé via la formule SQL canonique `((DATEDIFF(DAY, '2024-01-01', CAST(getdate() AS DATE)) % 7) + 7) % 7` (0=Lundi … 5=Samedi, 6=Dimanche) — vérifiable côté logs SQL : la requête SFD-30 ne contient **pas** de `DATEPART(WEEKDAY, ...)` brut (dépendant de `@@DATEFIRST`) et n'expose **aucun** paramètre client influant sur le jour (BR-23). Pour 6=Dimanche, les valeurs `HeureArriveeDeclaree` et `HeureDepartDeclaree` sont NULL (colonnes `DimancheDebut`/`DimancheFin` absentes du schéma `dbo.Contrat` — comportement attendu, BR-22 prend le relais)

## Dependencies
- **spec-connexion** (`1-spec-connexion`) : `EmployeeId` provient de la variable singleton de session de l'employé connecté ; redirection vers `/login` en l'absence de session valide ou en cas de 401 sur le GET
- **spec-rapport-du-jour** (`10-Spec-rapport-du-jour`) : **étendue** par cette FEAT — l'endpoint `PUT /api/contrats/{ContratId}/rapport` intègre désormais le step génération + UPDATE de `RapportJournee.RapportSms` dans sa transaction SQL existante (cf. SFD-2, AC-2)
- **spec-arrivees-departs** (`11-Spec-Arrrivees-Departs`) : **prérequis fonctionnel** — la ligne `dbo.RapportJournee` du jour pour le bébé doit exister (créée au moment de l'enregistrement de l'arrivée par FEAT 11) pour que l'UPDATE de `RapportSms` matche une ligne ; si absente, `RapportSms` n'est pas persisté (degraded mode, cf. BR-9, AC-12) ; la colonne `RapportSms NVARCHAR(500) NULL` documentée par FEAT 11 SFD-3 est **activée** par cette FEAT
- **spec-bebe-detaille** (`9-spec-bebe-detaille`) : **étendue** par cette FEAT — le bouton `Envoyer aux parents` du `report-actions` de l'onglet 2 (SFD-30, jusqu'ici cosmétique) devient fonctionnel (cf. SFD-1, AC-1) ; la textarea du même onglet est désormais alimentée dynamiquement par `GET /api/contrats/{ContratId}/rapport-sms` (cf. SFD-18, AC-13)
- **spec-inscription** (`3-spec-inscription`) : indirecte — la table `dbo.Employee` est alimentée par l'inscription ; les champs `Employee.Prenom` et `Employee.Nom` sont consommés en lecture pour la signature du SMS (cf. SFD-7, SFD-13, BR-20)
- **dbo.Employeur** (table SQL) : prérequis schéma supposé créé en base (lien parent — héritage spec-souscrire-contrat) avec les colonnes `TelPersonnel`, `TelPersonnel2`, `TelProfessionnel` consommées en cascade par BR-12

## Functional Deliverables
- FD-1: **extension de l'endpoint backend `PUT /api/contrats/{ContratId}/rapport`** (hérité de FEAT 10) — ajout dans la transaction existante des étapes : (1) `SELECT Rapport JOIN Action ORDER BY IdCategorie, ActionId` pour récupérer les libellés cochés du jour, (1bis — extension v7) `SELECT RapportJournee.HeureArrivee/HeureDepart + Contrat.{Jour}Debut/{Jour}Fin` via la formule canonique de jour SFD-30 pour récupérer les 4 valeurs horaires nécessaires aux 2 lignes systématiques, (2) génération du texte côté serveur via template constant (incluant les 2 lignes horaires conditionnelles + 4 phrases catégories conditionnelles), (3) `UPDATE RapportJournee SET RapportSms WHERE Date=today AND ContratId=X` ; la transaction reste atomique (rollback intégral en cas d'échec d'un step — cf. AC-11)
- FD-2: **nouvel endpoint backend `GET /api/contrats/{ContratId}/rapport-sms`** retournant le payload aplati `{ rapportSms, parentNom, parentPrenom, parentTelephone }` (cf. SFD-15, SFD-16, AC-13) avec résolution serveur du numéro de téléphone parent par cascade `TelPersonnel ?? TelPersonnel2 ?? TelProfessionnel ?? null` (cf. BR-12) et nettoyage des caractères non-numériques sauf `+` initial (cf. BR-13)
- FD-3: **constante de code backend** matérialisant le template du SMS (chaîne canonique de SFD-7 + 4 sous-templates conditionnels de SFD-8 + 2 sous-templates systématiques arrivée/départ de SFD-29) — fichier source dédié (ex. `rapport-sms-template.js` / `RapportSmsTemplate.kt`), versionné avec le code, jamais lu depuis la DB ou un fichier de config externe (cf. BR-6, AC-4)
- FD-4: **moteur de rendu du template** côté backend — fonction prenant en entrée `(contratPrenom, employeePrenom, employeeNom, actionsByCategory: Map<Int, List<String>>, hours: { arrivalActual, arrivalDeclared, departureActual, departureDeclared })` et produisant la chaîne finale avec :
  - Insertion des 2 lignes horaires (arrivée + départ) entre la salutation et les phrases catégories, conditionnelle selon BR-21 / BR-22 (cf. SFD-29, AC-29, AC-30)
  - Formatage `HH:MM` des `@db.Time` Prisma via `getUTCHours()` / `getUTCMinutes()` + `padStart(2, '0')` (cf. SFD-31)
  - Omission intégrale d'une phrase si la catégorie correspondante est vide (cf. SFD-8, AC-9)
  - Jointure des libellés par `, ` au sein d'une catégorie (cf. SFD-9, AC-28)
  - Tronqure à 500 chars si dépassement (497 chars + `...`, cf. BR-15, AC-20)
- FD-5: **modification de la textarea de l'onglet 2** de la fiche détaillée bébé — passage en lecture seule (`readonly`), contenu alimenté par `rapportSms` du GET, placeholder explicatif si NULL (cf. SFD-19, SFD-20, AC-14)
- FD-6: **bouton `Envoyer aux parents` fonctionnel** — état dérivé du couple `(rapportSms, parentTelephone)` : actif si les deux non-NULL, désactivé avec tooltip explicatif sinon (cf. SFD-21, AC-15, AC-19) ; clic actif construit le lien `sms:{telephone}?body={encoded_rapportSms}` et déclenche la navigation native (cf. SFD-22, AC-16)
- FD-7: **gestion des états de chargement et erreur** côté frontend onglet 2 — squelette pendant le GET (cf. SFD-25), 404 → page "Bébé introuvable" (cf. SFD-26, AC-22), 500/timeout → message erreur + bouton Réessayer (cf. SFD-27, AC-25), 401 → redirection `/login` (cf. SFD-28, AC-21)
- FD-8: **logging côté serveur** des cas degraded mode : WARN sur 0 ligne UPDATE (bébé non marqué arrivé — cf. BR-9, AC-12), WARN sur troncature (cf. BR-15, AC-20) ; aucune trace d'envoi SMS effective (cf. BR-18)

## Out of Scope
- **passerelle SMS serveur-side** (Twilio, OVHcloud SMS, Vonage, AWS SNS, MessageBird, etc.) — l'envoi reste exclusivement via le lien `sms:` natif du téléphone client ; aucun coût d'envoi côté SDD (cf. BR-17, AC-26) ; une FEAT future pourrait introduire un envoi automatisé déclenché côté serveur (planification, retry, statut delivery) — hors scope ici
- **suivi des envois** (timestamp envoi, statut delivery, lecture par le parent, opt-out parent) — l'application n'a aucun feedback sur l'effectivité de l'envoi (cf. SFD-23, BR-18) ; une FEAT future avec passerelle SMS serveur-side pourrait persister ces données — hors scope ici
- **envoi par Email** ou **notification Push** en complément/remplacement du SMS — l'objectif principal est le SMS (cf. user prompt) ; le canal email pourrait être ajouté dans une FEAT future avec template adapté — hors scope ici
- **édition manuelle du texte SMS** par l'employé dans la textarea — la textarea est strictement lecture seule (cf. BR-14) ; l'ajustement éventuel s'effectue dans l'app SMS native après ouverture du lien `sms:` ; l'ajout d'un mode "édition + sauvegarde manuelle" serait une FEAT future avec une stratégie de versionning et de précédence (manuel vs auto-régénéré) — hors scope ici
- **édition du template du SMS** depuis l'interface utilisateur (super-admin, paramètres employé, configuration projet) — le template reste en constante de code (cf. BR-6) ; une FEAT future pourrait introduire une table `dbo.RapportSmsTemplate` éditable avec versioning, par employé ou par projet — hors scope ici
- **template multi-langue** (français / anglais / arabe / espagnol selon langue parent) — le template français unique est codé en dur (cf. SFD-7) ; une FEAT future pourrait introduire la sélection de langue selon `Employeur.Langue` ou paramétrage employé — hors scope ici
- **personnalisation du template par catégorie** (ex. SMS Santé séparé en cas de fièvre uniquement) — les 4 phrases sont conditionnelles uniquement sur `count > 0`, pas sur le contenu ; une FEAT future pourrait introduire des règles métier (ex. tag `urgent` sur certaines `Action` qui produisent une phrase d'alerte distincte) — hors scope ici
- **alertes / seuils** (notification automatique SMS au parent si fièvre N jours d'affilée, si refus alimentaire répété) — extension future avec règles métier déclenchant des SMS séparés de celui du rapport quotidien — hors scope ici
- **historique des SMS envoyés** (consultation par l'employé des rapports SMS des jours passés) — la colonne `RapportSms` stocke un rapport par jour mais aucun écran ne le consulte rétrospectivement dans cette FEAT (seul le jour courant est affiché) ; une FEAT future de calendrier / historique pourrait l'exposer — hors scope ici
- **export PDF** du rapport SMS (impression, archivage local par le parent) — hors scope ; le texte reste un message éphémère côté parent
- **partage du rapport** (lien public consultable par le parent sans installer l'app, génération QR code) — hors scope ; le SMS suffit
- **deux parents destinataires simultanément** (envoi du SMS à TelPersonnel ET TelPersonnel2) — actuellement seul le premier non-NULL est consommé (cf. BR-12) ; une FEAT future pourrait introduire un envoi multi-destinataire (l'app SMS native gère déjà `sms:0612345678,0698765432?body=...` sur certains devices, mais le comportement est variable) — hors scope ici (one-shot single destinataire)
- **envoi groupé** d'un même message à plusieurs bébés / parents en une opération — hors scope ; chaque bébé a son propre rapport et son propre envoi
- **fallback desktop** quand le navigateur n'a pas de handler `sms:` (ex. copier-coller automatique vers le presse-papier + tooltip "Texte copié, collez-le dans votre app SMS") — comportement variable selon device, non implémenté (cf. SFD-24) ; une FEAT future pourrait l'adresser pour les employés utilisant l'app depuis un desktop — hors scope ici
- **ALTER COLUMN `RapportSms` vers `NVARCHAR(MAX)`** pour supporter des messages plus longs (cas avec de très nombreuses cases cochées) — la limite 500 est conservée dans cette FEAT avec stratégie de troncature (cf. BR-15) ; un ALTER futur serait tracé via ADR — hors scope ici (DDL out of scope SDD côté table existante)
- **changement de canal de transport** (WhatsApp Business API, Telegram Bot, Signal) — hors scope ; SMS uniquement
- **template stocké en base** avec interface d'administration multi-tenant (un template par projet/employé) — hors scope ; constante de code suffit pour le scope actuel
- **statistiques d'envoi** (nombre de rapports SMS envoyés par employé / par mois) — hors scope ; aucune trace n'est persistée (cf. BR-18)
- **modification du template par feature-flag / A/B test** (tester plusieurs formulations auprès des parents) — hors scope ; déploiement de code uniquement
- **rendu emoji / icônes** dans le SMS (ex. 🩺 Santé / 🍽 Repas / 🎨 Activités / 🙂 Humeur comme dans la textarea exemple du mockup) — le template SFD-7/SFD-8 ne contient pas d'emojis pour rester compatible avec les SMS basiques (GSM-7 / UCS-2) et économiser des segments ; une FEAT future pourrait introduire un mode "SMS riche" avec emojis si l'analytics révèle que la majorité des parents lisent en RCS / iMessage — hors scope ici
- **validation de la conformité du contenu** (anti-PII excessive, anti-spam, anti-injection HTML/JS dans le texte) — `Action.Nom` étant maîtrisé par le DBA et le template étant en constante de code, le risque est nul dans le scope actuel ; aucune validation runtime n'est implémentée — hors scope ici
- **gestion d'un mode "envoyer plus tard"** ou "planifier" — hors scope ; l'envoi est immédiat ou pas d'envoi
- **fallback en cas d'absence de réseau au moment du clic** — le lien `sms:` ouvre l'app SMS qui gère elle-même le mode "à envoyer dès retour réseau" ; aucune logique additionnelle SDD — hors scope ici
- **consultation du SMS par le parent dans une interface dédiée** (espace parent web sans installer l'app) — out of scope ; le SMS reste le canal unique de notification (cf. `spec-rapport-du-jour` Out of Scope analogue)
