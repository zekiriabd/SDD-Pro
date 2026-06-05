# Spec: infos-enfant (refonte bloc rémunération + champ NBHoraireMajore)

FEAT ID: 27-Spec-Infos-Enfant
Spec ID: spec-infos-enfant
Status: Draft

> **Périmètre** — Cette FEAT raffine deux écrans déjà existants :
> (1) la fiche détaillée `/bebes/{ContratId}` onglet `Informations` (cf.
> FEAT 9 `spec-bebe-detaille` SFD-17) où la carte `Salaire` (ou
> historiquement `Rémunération`) est **remplacée** par un nouveau bloc
> détaillé `Heures déclarées au Salaire mensualisé total` qui expose la
> formule complète (heures normales / heures majorées × taux horaire ⇒
> salaire mensualisé brut + net) ;
> (2) le wizard `08-souscrire-contrat.html` (cf. FEAT 6
> `spec-souscrire-contrat` étape 4 Rémunération) qui ajoute l'édition
> du nouveau champ `NBHoraireMajore` (heures hebdomadaires majorées
> au-delà de 45 h, saisie manuelle par l'assistante) en complément des
> deux champs `SalaireHoraireNet` et `SalaireHoraireMajoreNet`
> actuellement seuls éditables côté tarification (valeurs NET stockées,
> Brut dérivé affichage).
>
> **Aucune autre FEAT n'est impactée**. Le mockup canonique est
> `workspace/input/ui/27-1-Spec-Infos-Enfant.html`. L'image de
> référence des règles de calcul (formulaire papier Pajemploi
> « Calcul du nombre d'heures majorées » + « Calcul du salaire ») est
> jointe à la demande utilisateur — toutes les formules SFD-CALC-* en
> dérivent.
>
> **MAJ 2026-06-01** — Refactor naming : les champs `SalaireHoraire` /
> `SalaireHoraireMajore` ont été renommés `SalaireHoraireNet` /
> `SalaireHoraireMajoreNet` pour expliciter qu'ils stockent des valeurs
> NET ; les valeurs Brut sont désormais des dérivations affichage via
> `Brut = Net / 0.78`. La spec FEAT 6 SFD-25 à SFD-28 (étape 4
> Rémunération) reste à aligner ultérieurement.

## Context

Le bloc `Rémunération` (ex-SFD-17 de FEAT 9) affiche aujourd'hui des
agrégats partiels (`Heures / sem.`, `Brut / h`, `Net / h`, `Mensuel
net`) sans détailler la décomposition normale / majorée. L'assistante
maternelle (et l'inspectrice URSSAF en cas de contrôle) doivent
pouvoir lire en un coup d'œil **comment** le salaire mensualisé total
est constitué, conformément au formulaire papier Pajemploi de
référence : amplitudes hebdomadaires → mensualisation × 52 / 12 →
salaire brut par catégorie → total brut → total net (après abattement
~22 % cf. FEAT 25). Le bloc n'est **pas éditable** depuis la fiche
(read-only, conformément à FEAT 9 BR-23) ; toute modification des
intrants passe par le wizard externe.

Côté schéma DB, deux champs `SalaireHoraireNet` et
`SalaireHoraireMajoreNet` (Decimal(18,2) nullable) sont déjà présents
en table `Contrat` (cf.
`workspace/output/src/Demo/prisma/schema.prisma` lignes 61-62) et
sont saisis manuellement à l'étape 4 du wizard (cf. FEAT 6 SFD-25 à
SFD-28). Ces champs stockent la valeur **NETTE** ; la valeur Brute
correspondante est dérivée à l'affichage uniquement (cf. SFD-CALC-5). En revanche, le nombre d'heures **majorées** hebdomadaires
(`NBHoraireMajore`, > 45 h) **n'existe pas** en base — il était jusqu'à
présent dérivé indirectement de `NombreHeuresHebdo` (manuel) sans
distinction explicite. Cette FEAT introduit une colonne
`NBHoraireMajore` Decimal(18,2) nullable en table `Contrat` + son
entrée Prisma + son champ d'édition dans le wizard étape 4.

Les heures **normales** hebdomadaires restent **calculées** côté UI
(non stockées en base) à partir des amplitudes des 7 colonnes
`{Jour}Debut`/`{Jour}Fin` déjà existantes (cf. FEAT 6 SFD-30 à
SFD-32), plafonnées à 45 h par semaine.

## Objective

L'assistante consulte `/bebes/{ContratId}` → onglet `Informations` →
fait défiler jusqu'au bloc `Heures déclarées au Salaire mensualisé
total` (4ᵉ carte, remplace l'ancienne carte `Salaire`/`Rémunération`).
Elle voit : (1) un tableau `Heures par type / Par sem. / Mensualisé`
avec deux lignes (Normal, Majoré >45h) ; (2) un tableau `Taux horaire
Brut/Net` avec deux lignes (Normal, Majoré) ; (3) un tableau `Salaire
mensuel base / majoré` Brut / Net ; (4) un encart `Salaire mensualisé
total` Brut / Net en pied. Toutes les valeurs sont calculées côté
frontend à partir du payload existant `GET /api/contrats/{ContratId}`
(cf. FEAT 9 SFD-12) **enrichi du champ `NBHoraireMajore`**. Aucun
nouvel endpoint backend n'est requis.

Pour pouvoir alimenter correctement ces calculs, l'assistante édite
le contrat via le FAB de la fiche (cf. FEAT 9 SFD-20) → wizard étape 4
Rémunération → la carte `Heures majorées` expose désormais un champ
supplémentaire `Heures majorées / sem. (> 45 h)` (`NBHoraireMajore`,
suffixe `h / semaine`) en plus des champs `SalaireHoraireNet` et
`SalaireHoraireMajoreNet` déjà présents. Le couple INSERT (création) ou
UPDATE (édition) persiste la nouvelle colonne dans la même transaction
unique que les autres champs `Contrat`.

## Quantified Goal (v7.0.0 — anti-GIGO)

- Metric: temps de rendu de la carte `Heures déclarées au Salaire
  mensualisé total` (4 sous-tables + total) après mount de l'onglet
  `Informations` ; latence du couple UPDATE `Employeur` + `Contrat`
  côté backend lorsque `NBHoraireMajore` figure dans le payload.
- Target: rendu carte p95 < 50 ms côté frontend (calculs purs JS sur
  ≤ 20 champs, aucune requête réseau) ; p95 UPDATE transactionnel
  inchangé vs FEAT 9 (< 600 ms cf. NFC FEAT 9).
- Deadline: livraison fin **2026-07-15**.

## Non-Functional Constraints (v7.0.0)

- Expected volume: inchangé vs FEAT 9 (~50 ouvertures fiche /
  employée / jour) ; le payload `GET /api/contrats/{ContratId}` gagne
  1 champ Decimal nullable (impact < 30 octets).
- Performance SLA: p95 rendu carte < 50 ms ; aucun impact sur le SLA
  global de la fiche (cf. FEAT 9 Quantified Goal p95 < 800 ms TTI).
- Data retention: `NBHoraireMajore` suit la rétention `Contrat`
  (conservé tant que l'employée reste active, cf. FEAT 9 NFC).
- Compliance: RGPD inchangé — la donnée est lue uniquement par
  l'employée propriétaire du contrat (filtre `EmployeeId` cf. FEAT 9
  BR-1).
- Integration: réutilise les endpoints existants `GET
  /api/contrats/{ContratId}` (lecture), `POST /api/contrats`
  (création, FEAT 6 FD-7), `PUT /api/contrats/{ContratId}` (édition,
  FEAT 9 FD-8) — étendus pour sérialiser / accepter `NBHoraireMajore`.
- Degraded mode: si `NBHoraireMajore` est NULL (contrats créés avant
  cette FEAT), la ligne `Majoré` du tableau affiche `0 h` partout et
  les colonnes salaire majoré affichent `0,00 €` (cf. BR-9) — le bloc
  reste cohérent.

## Actors

- Employée connectée : assistante maternelle authentifiée, identifiée
  par son `EmployeeId` de session. Seule autorisée à consulter et
  modifier les contrats dont `Contrat.EmployeeId == session.EmployeeId`
  (cf. FEAT 9 BR-1 à BR-3). Saisit `NBHoraireMajore` au même titre
  que `SalaireHoraireNet` / `SalaireHoraireMajoreNet` dans le wizard étape 4.

## Functional Needs

### Bloc `Heures déclarées au Salaire mensualisé total` (onglet Informations)

- SFD-UI-1: La 4ᵉ carte de l'onglet `Informations` (entre `Contrat` et
  `Horaires hebdomadaires`) s'intitule `Heures déclarées` (titre de
  carte, conservé du mockup `27-1`), avec icône euro coral inchangée
  vs FEAT 9 SFD-17 ; le `section-label` parent en tête peut rester
  vide (rendu épuré conforme à FEAT 9 AC-7) ou afficher `Rémunération`
  selon stack UI active — non bloquant.
- SFD-UI-2: La carte expose **3 tableaux empilés** suivis d'un
  encart total, dans cet ordre exact (cf. mockup `27-1` lignes
  461-500) :
  1. Tableau `Heures` — colonnes `Type / Par sem. / Mensualisé`,
     lignes `Normal` et `Majoré (>45h)`.
  2. Tableau `Taux horaire` — colonnes `Type / Brut / h / Net / h`,
     lignes `Normal` et `Majoré (>45h)`.
  3. Tableau `Salaire mensuel` — colonnes `Salaire / Brut / Net`,
     lignes `Base · {N}h` et `Majoré · {M}h`.
  4. Encart `Salaire mensualisé total` (`pay-total` du mockup) avec
     2 tuiles `Brut` et `Net`.
- SFD-UI-3: Toutes les valeurs numériques (heures, taux, salaires)
  sont rendues en font-mono ; les heures sont suffixées `h`, les
  montants suffixés `€` ; le séparateur décimal est la virgule, le
  séparateur de milliers est l'espace insécable (`1 194,85 €`).
- SFD-UI-4: Les valeurs nettes sont affichées en couleur atténuée
  (`var(--nj-ink-500)`) pour signaler visuellement leur caractère
  dérivé (cf. mockup lignes 477-489), tout en restant lisibles
  (contraste WCAG AA min).
- SFD-UI-5: Si `Contrat.SalaireHoraireNet` OU
  `Contrat.SalaireHoraireMajoreNet` est NULL, la cellule correspondante
  affiche `—` (dash) et **tous les agrégats dérivés** (salaire mensuel
  base/majoré, total brut/net) affichent également `—` — aucun calcul
  sur valeur NULL.
- SFD-UI-6: Aucun `FAB` ni bouton `Modifier` n'est affiché dans la
  carte (le FAB unique de l'onglet `Informations` cf. FEAT 9 SFD-20
  reste le seul point d'entrée d'édition).

### Calculs frontend (formules canoniques)

- SFD-CALC-1: `NBHoraireNormalWeekly` (heures normales hebdomadaires,
  plafonnées à 45 h) est calculé côté UI : pour chaque jour
  `j ∈ {Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi, Dimanche}`,
  si `{j}Debut` ET `{j}Fin` sont non-NULL, l'amplitude
  `min({j}Fin − {j}Debut, en heures décimales)` est sommée ; le total
  est plafonné par `min(Σ, 45)`. Si aucun jour n'a d'amplitude valide,
  `NBHoraireNormalWeekly = 0`.
- SFD-CALC-2: `NBHoraireMajoreWeekly` est lu **directement** depuis
  `Contrat.NBHoraireMajore` (Decimal(18,2)) ; si NULL → traité comme
  `0`. Cette valeur n'est **jamais** déduite de `NombreHeuresHebdo` ou
  des amplitudes (séparation stricte normale / majorée).
- SFD-CALC-3: `NBHoraireNormalMonthly = round(NBHoraireNormalWeekly ×
  52 / 12, 0)` (entier d'heures mensualisées, ex. `45 × 52 / 12 =
  195`).
- SFD-CALC-4: `NBHoraireMajoreMonthly = round(NBHoraireMajoreWeekly ×
  52 / 12, 0)` (entier d'heures mensualisées, ex. `2,5 × 52 / 12 ≈
  11`).
- SFD-CALC-5: Brut/h est **dérivé** depuis le Net/h stocké via
  `SalaireHoraireBrut = round(SalaireHoraireNet / (1 − AbattementRate), 2)`
  avec `AbattementRate = 0.22` (divisor `0.78`). Idem
  `SalaireHoraireMajoreBrut = round(SalaireHoraireMajoreNet / 0.78, 2)`.
  Les valeurs Net sont stockées manuellement par l'assistante (single
  source of truth, colonnes `Contrat.SalaireHoraireNet` /
  `Contrat.SalaireHoraireMajoreNet`) ; le Brut est purement une
  dérivation informationnelle d'affichage. `AbattementRate = 0.22` reste
  une constante frontend dérivée du taux Pajemploi 2025-2026
  (paramétrage dynamique hors scope cette FEAT).
- SFD-CALC-6: Net mensuel = `SalaireBaseNetMois = round(SalaireHoraireNet
  × NBHoraireNormalMonthly, 2)` (direct depuis le stocké).
  Brut mensuel = `SalaireBaseBrutMois = round(SalaireHoraireBrut ×
  NBHoraireNormalMonthly, 2)` (dérivé via SFD-CALC-5).
- SFD-CALC-7: Net mensuel majoré = `SalaireMajoreNetMois = round(
  SalaireHoraireMajoreNet × NBHoraireMajoreMonthly, 2)` (direct).
  Brut mensuel majoré = `SalaireMajoreBrutMois = round(
  SalaireHoraireMajoreBrut × NBHoraireMajoreMonthly, 2)` (dérivé).
- SFD-CALC-8: `SalaireMensTotalBrut = SalaireBaseBrutMois +
  SalaireMajoreBrutMois`. `SalaireMensTotalNet = SalaireBaseNetMois +
  SalaireMajoreNetMois`.
- SFD-CALC-9: Toutes les divisions et multiplications sont effectuées
  en **nombre flottant double-précision** (JS `Number`) puis arrondies
  à 2 décimales par `Math.round(v × 100) / 100` ; aucune
  approximation cumulative.

### Schéma DB & ORM

- SFD-DATA-1: Ajouter en table `dbo.Contrat` la colonne
  `NBHoraireMajore` de type `decimal(18,2)` NULL, sans valeur par
  défaut, positionnée logiquement après `NombreHeuresHebdo` (avant
  `JourReposEmploye`) — l'ordre physique sur disque n'est pas
  load-bearing.
- SFD-DATA-2: Mettre à jour `workspace/output/db/schema.json` pour
  refléter SFD-DATA-1 (ajout d'une entrée dans le tableau `columns`
  de la table `Contrat`).
- SFD-DATA-3: Mettre à jour le modèle Prisma
  `workspace/output/src/Demo/prisma/schema.prisma` modèle
  `Contrat` pour ajouter le champ correspondant :
  `NBHoraireMajore Decimal? @db.Decimal(18, 2)` (placé après
  `NombreHeuresHebdo` pour la lisibilité du diff).
- SFD-DATA-4: La migration SQL associée (script `ALTER TABLE` ou
  équivalent Prisma migrate) est **hors scope** de la matérialisation
  agent — elle sera générée manuellement par l'opérateur DBA. La FEAT
  livre uniquement `schema.json` + `schema.prisma` + le code
  applicatif consommateur. Aucun `prisma migrate dev` ne doit être
  invoqué par l'agent (cf. FEAT 25 SFD-DATA-MIGRATION pour pattern
  identique).

### Wizard étape 4 — saisie de `NBHoraireMajore`

- SFD-EDIT-1: Le wizard `08-souscrire-contrat.html` étape 4
  Rémunération (cf. FEAT 6 SFD-25 à SFD-29) ajoute, dans la carte
  `Heures majorées`, un nouveau champ numérique en haut de la carte :
  `Heures majorées / sem. (> 45 h)` (label visible), placeholder
  `0`, suffixe `h / semaine`, lié à `Contrat.NBHoraireMajore`.
- SFD-EDIT-2: Le champ est **optionnel** : absence de saisie ⇒ valeur
  persistée `NULL` (équivalent fonctionnel à `0`). Une saisie
  explicite de `0` est également acceptée et persistée telle quelle
  (`0.00`).
- SFD-EDIT-3: Pas de validation cross-field bloquante côté UI entre
  `NBHoraireMajore` et `NombreHeuresHebdo` (cf. SFD-EDIT-7) — un écart
  informatif peut être affiché (`Σ amplitudes hebdo − 45h ≠
  NBHoraireMajore`) mais ne bloque jamais l'enregistrement.
- SFD-EDIT-4: En mode `edit` (route `/contrats/{ContratId}`, cf.
  FEAT 9 SFD-21), le champ est pré-rempli depuis le payload `GET
  /api/contrats/{ContratId}` (qui inclut désormais `NBHoraireMajore`
  cf. SFD-API-1).
- SFD-EDIT-5: Au save final (`Enregistrer le contrat` création OU
  `Enregistrer les modifications` édition), la valeur `NBHoraireMajore`
  est sérialisée dans le payload du POST/PUT `Contrat` et persistée
  dans la même transaction unique (cf. FEAT 6 SFD-37 / FEAT 9 SFD-23).
- SFD-EDIT-6: La carte `Heures majorées` du wizard conserve les
  champs existants `SalaireHoraireMajoreNet` (Net majoré stocké, cf.
  FEAT 6 SFD-26 — le Brut équivalent est dérivé affichage via
  SFD-CALC-5) et son `Net majoré` éventuellement pré-calculé (cf.
  FEAT 6 SFD-27) — le nouveau champ s'ajoute, ne remplace rien.
- SFD-EDIT-7: Le champ existant `NombreHeuresHebdo` (saisi étape 3,
  cf. FEAT 6 SFD-20) **reste éditable** pour compatibilité avec les
  contrats existants, mais sa valeur n'est plus utilisée par le
  nouveau bloc d'affichage (SFD-UI-2) — toutes les heures sont
  recalculées via SFD-CALC-1 à SFD-CALC-4. La dépréciation effective
  de `NombreHeuresHebdo` est hors scope de cette FEAT (spec future
  dédiée à la simplification du wizard).

### Endpoint backend `GET /api/contrats/{ContratId}`

- SFD-API-1: La requête SQL canonique de FEAT 9 SFD-12 est étendue
  pour sélectionner également `c.NBHoraireMajore` dans la liste des
  colonnes projetées ; aucune autre modification (jointure, filtres,
  paramètres) n'est requise.
- SFD-API-2: Le payload JSON de réponse inclut désormais les champs
  `salaireHoraireNet`, `salaireHoraireMajoreNet` (renommés camelCase
  depuis les anciens `salaireHoraire` / `salaireHoraireMajore`) et
  `nbHoraireMajore` (camelCase, `number` ou `null`) dans l'objet
  `contrat` (cf. FEAT 9 BR-7 sur le mapping camelCase).

### Endpoints `POST /api/contrats` et `PUT /api/contrats/{ContratId}`

- SFD-API-3: Les payloads d'entrée des deux endpoints utilisent les
  clés `salaireHoraireNet` et `salaireHoraireMajoreNet` (renommées
  camelCase depuis les anciens `salaireHoraire` / `salaireHoraireMajore`)
  et acceptent le champ optionnel `nbHoraireMajore` (number ≥ 0 OU null)
  dans le sous-objet `contrat` ; la validation Zod (cf. stack
  fullstack/node-react §1.4) est étendue avec la règle
  `nbHoraireMajore: z.number().nonnegative().nullable().optional()`.
- SFD-API-4: La colonne SQL `NBHoraireMajore` est intégrée à la
  requête `INSERT INTO Contrat` (FEAT 6 SFD-37) et au statement
  `UPDATE Contrat SET ...` (FEAT 9 SFD-23) dans la même transaction
  unique — pas de batch séparé.

## Business Rules

- BR-1: la colonne `Contrat.NBHoraireMajore` est de type
  `decimal(18,2)` NULL (cf. SFD-DATA-1) ; les valeurs négatives sont
  rejetées côté UI ET backend (validation Zod `nonnegative()`). Les
  colonnes `Contrat.SalaireHoraireNet` / `Contrat.SalaireHoraireMajoreNet`
  (renommées depuis `SalaireHoraire` / `SalaireHoraireMajore`) restent
  `decimal(18,2)` NULL — **Net est la valeur stockée canonique**.
- BR-2: la précision de stockage est `(18, 2)` — soit max 16 chiffres
  avant la virgule + 2 après ; au-delà, le backend retourne 400 (cas
  irréaliste, garde-fou anti-saisie aberrante).
- BR-3: `NULL` et `0` sont sémantiquement équivalents pour le calcul
  affichage (cf. SFD-CALC-2), mais sont persistés distinctement (`NULL`
  = champ jamais renseigné, `0` = explicitement renseigné à zéro) —
  pas de coercition automatique en base.
- BR-4: `NBHoraireNormalWeekly` (cf. SFD-CALC-1) est strictement
  plafonné à 45 h — toute somme d'amplitudes > 45 h est tronquée à
  45 h pour ce calcul ; le surplus est considéré comme implicitement
  reporté sur `NBHoraireMajore` (mais n'y est pas automatiquement
  injecté — l'assistante saisit la valeur).
- BR-5: la conversion hebdo → mensualisé utilise strictement
  `× 52 / 12` (52 semaines par an étalées sur 12 mois) — toute autre
  base (52,143 ; 4,33 ; etc.) est rejetée par convention Pajemploi.
- BR-6: le taux d'abattement `AbattementRate = 0.22` (SFD-CALC-5) est
  une **constante frontend** valable au 2026-06-01 ; en cas d'écart
  futur avec le taux légal, modification ponctuelle dans le code
  frontend (out of scope de cette FEAT — spec future éventuelle de
  paramétrage `Contrat.AbattementRate` colonne ou `app_config`).
  Le divisor utilisé pour dériver Brut depuis Net est `(1 − 0.22) = 0.78`
  (cf. SFD-CALC-5 — Net est la valeur stockée canonique).
- BR-7: les calculs SFD-CALC-1 à SFD-CALC-8 sont effectués
  **exclusivement côté frontend** ; aucun nouveau calcul n'est
  effectué côté backend (le payload `GET` retourne uniquement les
  données brutes — heures, taux — et le frontend dérive l'affichage).
- BR-8: si `Contrat.SalaireHoraireNet` ET
  `Contrat.SalaireHoraireMajoreNet` sont **tous deux** NULL, la carte
  affiche `—` partout (cf. SFD-UI-5) — pas de bloc partiellement rempli
  incohérent. **Net est la valeur canonique stockée**, Brut est dérivé
  uniquement à l'affichage.
- BR-9: si `Contrat.NBHoraireMajore` est NULL mais
  `SalaireHoraireMajoreNet` est renseigné, la ligne `Majoré` affiche
  `0 h × {salaire net} € = 0,00 €` (cf. SFD-UI degraded mode) — cas
  légitime : contrat sans heures majorées prévues mais taux renseigné
  par anticipation.
- BR-10: l'éventuel écart entre `Σ(amplitudes hebdo) − 45h` et
  `NBHoraireMajore` saisi (SFD-EDIT-3) est **non bloquant** —
  l'assistante reste seule juge de la déclaration Pajemploi.
- BR-11: aucune information technique (stack trace, exception SQL)
  n'est exposée à l'utilisateur en cas d'erreur (symétrique FEAT 9
  BR-24).
- BR-12: la requête SQL étendue (SFD-API-1) ne fait que `SELECT` une
  colonne supplémentaire — aucune nouvelle jointure, aucun nouvel
  index requis (lecture sur la PK `Contrat.ContratId` couvre déjà la
  colonne).

## Acceptance Criteria

- AC-1: l'onglet `Informations` de `/bebes/{ContratId}` affiche une
  carte intitulée `Heures déclarées` (ou équivalent stack UI actif)
  en 4ᵉ position (entre `Contrat` et `Horaires hebdomadaires`), avec
  l'icône euro coral et la structure 3 tableaux + 1 encart total
  conformément au mockup `27-1` (cf. SFD-UI-2).
- AC-2: l'ancienne carte `Salaire`/`Rémunération` (FEAT 9 SFD-17) est
  **supprimée** de l'onglet — aucune duplication, aucune coexistence
  avec le nouveau bloc.
- AC-3: le tableau `Heures` affiche 2 lignes : `Normal` (Par sem.
  calculée par SFD-CALC-1, Mensualisé calculé par SFD-CALC-3) et
  `Majoré (>45h)` (Par sem. = `NBHoraireMajore` brut DB, Mensualisé
  calculé par SFD-CALC-4).
- AC-4: le tableau `Taux horaire` affiche 2 lignes : `Normal` (Net =
  `SalaireHoraireNet` stocké, Brut dérivé via SFD-CALC-5
  `= Net / 0.78`) et `Majoré (>45h)` (Net = `SalaireHoraireMajoreNet`
  stocké, Brut dérivé via SFD-CALC-5).
- AC-5: le tableau `Salaire mensuel` affiche 2 lignes : `Base ·
  {NBHoraireNormalMonthly}h` (Net = SFD-CALC-6 direct, Brut = SFD-CALC-6
  dérivé) et `Majoré · {NBHoraireMajoreMonthly}h` (Net = SFD-CALC-7
  direct, Brut = SFD-CALC-7 dérivé).
- AC-6: l'encart `Salaire mensualisé total` en pied de carte affiche
  deux tuiles `Brut` (somme des bruts dérivés) et `Net` (somme des nets
  stockés, SFD-CALC-8), en font-mono, format `{X XXX,XX €}`.
- AC-7: la colonne `Contrat.NBHoraireMajore` existe en base SQL
  Server (type `decimal(18,2)` NULL) et l'entrée correspondante
  figure dans `workspace/output/db/schema.json` (table `Contrat`,
  attribut `columns[]`) et dans
  `workspace/output/src/Demo/prisma/schema.prisma` modèle
  `Contrat` (champ `NBHoraireMajore Decimal? @db.Decimal(18, 2)`).
- AC-8: le wizard `08-souscrire-contrat.html` étape 4 affiche un
  nouveau champ `Heures majorées / sem. (> 45 h)` en haut de la carte
  `Heures majorées`, lié bidirectionnellement à
  `Contrat.NBHoraireMajore` (lecture en mode edit, écriture au save).
- AC-9: en mode création (`/contrats/nouveau`), la valeur saisie pour
  `NBHoraireMajore` est persistée par l'INSERT `Contrat` dans la même
  transaction unique que les autres champs (cf. SFD-API-4).
- AC-10: en mode édition (`/contrats/{ContratId}`), la valeur saisie
  pour `NBHoraireMajore` est persistée par l'UPDATE `Contrat` dans la
  même transaction unique que les autres champs (cf. SFD-API-4) ; le
  rollback intégral en cas d'échec second statement reste garanti
  (cf. FEAT 9 AC-19).
- AC-11: l'endpoint `GET /api/contrats/{ContratId}` retourne désormais
  les champs `salaireHoraireNet`, `salaireHoraireMajoreNet` (renommés
  camelCase depuis les anciens `salaireHoraire` / `salaireHoraireMajore`)
  et `nbHoraireMajore` (number OU null) dans le sous-objet `contrat` du
  payload JSON — vérifiable côté Network DevTools.
- AC-12: un payload POST/PUT contenant `nbHoraireMajore: -5` (négatif)
  est rejeté par le backend avec un 400 Bad Request (validation Zod
  `nonnegative()`) ; le frontend bloque également la soumission avec
  un message inline.
- AC-13: un payload POST/PUT **sans** clé `nbHoraireMajore`
  (omission, backward-compat pour anciens clients) est accepté et
  persisté avec `NBHoraireMajore = NULL` — aucune régression sur les
  flux existants FEAT 6 / FEAT 9.
- AC-14: pour un contrat dont `NBHoraireMajore = NULL` ET
  `SalaireHoraireMajoreNet = NULL` (contrats créés avant cette FEAT),
  la ligne `Majoré (>45h)` du tableau `Heures` affiche `0 h` (Par sem.
  et Mensualisé) et les cellules `Net` et `Brut` (dérivé) du tableau
  `Taux horaire` affichent `—` — l'affichage reste cohérent, non cassé.
- AC-15: pour un contrat dont **toutes** les heures hebdomadaires
  (Lundi à Dimanche) sont NULL (cas extrême non réaliste),
  `NBHoraireNormalWeekly = 0` (cf. SFD-CALC-1) et toutes les cellules
  dérivées affichent `0` ou `—` — aucun NaN ou Infinity dans le
  rendu.
- AC-16: la carte `Heures déclarées` est **read-only** : aucun bouton,
  aucun champ éditable, aucun FAB local — l'unique entrée d'édition
  reste le FAB global de l'onglet `Informations` (cf. FEAT 9 AC-8).
- AC-17: les valeurs nettes (`Net / h`, `Net` mensuel, `Net` total)
  sont affichées en couleur atténuée (`var(--nj-ink-500)`) tout en
  conservant un contraste WCAG AA (cf. SFD-UI-4).
- AC-18: le format d'affichage respecte SFD-UI-3 : font-mono pour les
  chiffres, virgule décimale, espace insécable comme séparateur de
  milliers, suffixes `h` et `€` collés à la valeur ou séparés par
  espace insécable selon le mockup.
- AC-19: la requête SQL exécutée pour `GET /api/contrats/{ContratId}`
  est exactement celle de FEAT 9 SFD-12 **étendue** de la colonne
  `c.NBHoraireMajore` — aucune autre modification de la clause SELECT,
  FROM, WHERE, JOIN (vérifiable côté logs SQL).
- AC-20: aucun nouvel endpoint n'est créé par cette FEAT (uniquement
  extension des trois endpoints existants `GET`, `POST`, `PUT`) —
  vérifiable par diff des routes Fastify enregistrées.

## Dependencies

- **FEAT 6 spec-souscrire-contrat** : extension de l'étape 4
  Rémunération avec le nouveau champ `NBHoraireMajore`, sérialisation
  dans le payload POST/PUT, INSERT/UPDATE SQL inclus dans la
  transaction unique existante. Les règles BR-4 à BR-25 et SFD-25 à
  SFD-29 de FEAT 6 restent applicables sans modification.
- **FEAT 9 spec-bebe-detaille** : remplacement de la 4ᵉ carte de
  l'onglet `Informations` (ex-SFD-17 `Salaire`) par la nouvelle carte
  `Heures déclarées`. Extension de la requête SQL canonique SFD-12
  pour projeter `c.NBHoraireMajore`. Aucune autre modification de la
  structure de l'écran, des autres onglets ou du FAB global.
- **FEAT 25 spec-abattement-fiscal** : le taux d'abattement utilisé
  pour dériver les valeurs `Net / h` et `Net` mensuel reste cohérent
  avec la convention Pajemploi documentée (22 % par défaut). La
  source de vérité dynamique reste la table `dbo.Abattement` pour
  l'historique fiscal mensuel (hors scope de cette FEAT).
- **stack fullstack/node-react** : ajout d'une validation Zod
  `nbHoraireMajore` dans les schémas `ContratCreateSchema` et
  `ContratUpdateSchema` ; aucune nouvelle dépendance npm.

## Functional Deliverables

- FD-1: nouvelle colonne `NBHoraireMajore decimal(18,2) NULL` en
  table `dbo.Contrat`, reflétée dans `workspace/output/db/schema.json`
  (entrée dans `tables[Contrat].columns[]`) et dans
  `workspace/output/src/Demo/prisma/schema.prisma` modèle
  `Contrat` (champ `NBHoraireMajore Decimal? @db.Decimal(18, 2)`).
- FD-2: composant React `RemunerationDetailCard` (ou nom équivalent
  stack actif) rendu dans la `BebeDetailPage` onglet `Informations`,
  remplaçant le composant existant `SalaireCard` (issu de FEAT 9
  FD-5). Implémente SFD-UI-1 à SFD-UI-6 et SFD-CALC-1 à SFD-CALC-9.
- FD-3: extension du composant React `StepRemuneration` (ou
  équivalent) du wizard `08-souscrire-contrat.html` étape 4 avec un
  nouveau champ contrôlé `NBHoraireMajore`. Implémente SFD-EDIT-1 à
  SFD-EDIT-6.
- FD-4: extension de la requête SQL `GET /api/contrats/{ContratId}`
  pour projeter `c.NBHoraireMajore` (cf. FEAT 9 SFD-12 + SFD-API-1) ;
  extension du serializer JSON pour exposer `nbHoraireMajore` en
  camelCase.
- FD-5: extension des endpoints `POST /api/contrats` et `PUT
  /api/contrats/{ContratId}` pour : (1) accepter le champ optionnel
  `nbHoraireMajore` dans le payload (validation Zod
  `nonnegative().nullable().optional()`) ; (2) inclure la colonne dans
  l'INSERT / UPDATE de la transaction unique existante.
- FD-6: tests unitaires frontend des formules SFD-CALC-1 à SFD-CALC-9
  (couverture des cas limites : NULL, 0, > 45h, valeurs aberrantes
  négatives bloquées en amont par Zod).
- FD-7: tests d'intégration backend du POST/PUT avec
  `nbHoraireMajore` renseigné, NULL, omis, et négatif (rejet 400) ;
  vérification que la transaction unique reste atomique (rollback si
  un autre champ échoue).
- FD-8: aucune nouvelle migration SQL automatisée (cf. SFD-DATA-4) —
  le DBA exécute manuellement `ALTER TABLE dbo.Contrat ADD
  NBHoraireMajore decimal(18,2) NULL;` lors du déploiement.

## Out of Scope

- dépréciation effective du champ `NombreHeuresHebdo` (saisie manuelle
  étape 3 de FEAT 6) — préservé pour compat, sa simplification ou son
  retrait est une spec future
- paramétrage dynamique du taux d'abattement `AbattementRate` (BR-6,
  défaut 0,22 frontend) — colonne `Contrat.AbattementRate` ou
  configuration globale `app_config` hors scope
- évolution du libellé `Majoré (>45h)` en fonction d'une convention
  collective tierce (ex. 35h hebdo standard, seuil différent) —
  conservation du seuil légal Pajemploi 45 h par cette FEAT
- intégration avec la table `dbo.Abattement` (FEAT 25) pour dériver
  le `Net` mensuel à partir de l'abattement réel par couple
  (ContratId, Annee, Mois) — l'affichage de la carte `Heures
  déclarées` reste **prévisionnel** (forecast contractuel) et utilise
  la constante 0,22 ; la donnée fiscale réelle reste consultée via
  la page `/abattement-fiscal` (FEAT 25)
- édition inline depuis la fiche `/bebes/{ContratId}` (l'unique
  entrée d'édition reste le FAB global de l'onglet `Informations` cf.
  FEAT 9 SFD-20)
- ajout de nouveaux champs salaire (prime panier, indemnité
  déplacement, indemnité kilométrique, congés payés provisionnés…) —
  spec future de calculs Pajemploi étendus
- génération automatique d'un PDF récapitulatif du calcul (export
  bulletin de paie simplifié) — spec future
- gestion multi-contrats / cumul des heures majorées sur plusieurs
  employeurs — chaque `Contrat` reste isolé
- alertes / notifications en cas d'écart `Σ amplitudes hebdo − 45h ≠
  NBHoraireMajore` (BR-10 prévoit affichage non bloquant uniquement,
  pas d'alerte push)
- migration de données rétroactive des contrats existants pour
  inférer `NBHoraireMajore` à partir des amplitudes (NULL par défaut
  sur l'existant, l'assistante édite manuellement si besoin)
- internationalisation des libellés (français exclusif dans cette
  FEAT)
- support écran desktop / large viewport (la carte reste optimisée
  mobile/tablette comme le reste de la fiche, cf. FEAT 9)
