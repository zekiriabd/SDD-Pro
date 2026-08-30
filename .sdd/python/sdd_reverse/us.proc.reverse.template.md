<!--
us.proc.reverse.template.md — isolated template for db-reverse User Stories.
Read by the 4 specialist analysts (rung 1): reverse-sql-analyst (procédures
stockées + packages Oracle), reverse-sql-function-analyst,
reverse-sql-view-analyst, reverse-sql-trigger-analyst. One SQL object = one US.
Placeholders: {n} feat number, {m} US index, {usName} capability slug,
{module} business module, {fqProc} schema.objet, {dialect} engine,
{confidence}, {objectType} routineType du catalogue (ex. SQL_STORED_PROCEDURE,
VIEW, SQL_TRIGGER — recopié depuis l'inventaire), {objectFamily} libellé de
famille en clair — chaque analyste remplace par SA famille : « procédure
stockée » / « fonction » / « vue » / « trigger » / « package Oracle ».
`Parent FEAT hash:` reste TEL QUEL (sentinel résolu par l'assembleur rung 2,
même mécanique que le chemin déterministe build_proc_us.py — ne jamais le
calculer soi-même). `extraction: analyzed` reste TEL QUEL (il dit comment l'US
a été produite : par un agent, pas par un gabarit — c'est ce que
build_proc_feats.py compte en `us-analyzed`).
Evidence MUST point into .sys/proc-snapshot/{schema}.{objet}.sql:Lstart-Lend
(plain digits, no "L" prefix in the file — e.g. :12-30).
-->
---
ID: {n}-{m}-{usName}
Parent FEAT: {n}-{module}
Parent FEAT hash: sha256:COMPUTE_REQUIRED
generated-by: sdd-reverse
source-proc: {fqProc}
source-object-type: {objectType}
language-detected: {dialect}
Confidence: {confidence}
extraction: analyzed
Status: Draft
---

# US-{m}: {Titre lisible de la capability}

> ⚠️ User Story reverse-engineerée depuis la {objectFamily} `{fqProc}`
> ({dialect}, lecture seule). Décrit le comportement OBSERVÉ, jamais souhaité.

## Story

En tant que **{acteur}**, je veux **{capability}**, afin de **{bénéfice observable}**.

## Acceptance Criteria

<!-- 1 AC par chemin observable dans le corps SQL : nominal + chaque
     précondition/erreur (RAISERROR/THROW/IF EXISTS) = 1 AC négatif.
     Chaque AC porte son evidence + confidence. bias toward present. -->

- AC-1: Given {précondition}, when {sollicitation de l'objet}, then {effet observable
  sur les tables / valeur retournée}. <!-- evidence: .sys/proc-snapshot/{schema}.{objet}.sql:Ls-Le --> <!-- confidence: {confidence} -->

## Data Effects (plomberie démotée)

<!-- tables lues / écrites, paramètres + OUTPUT, transaction, SQL dynamique.
     Démoté ici (pas en règle métier) — sauf logique métier réelle (calcul,
     validation, machine à états) qui remonte en AC/règle ci-dessus. -->

- Lit : {tables_read}
- Écrit : {tables_written}
- Paramètres : {params}
- Transaction : {oui/non} · SQL dynamique : {oui/non}

## Dependencies

<!-- depuis le context pack : ce que l'objet appelle et ce qui l'appelle, avec
     la mention `non résolu` quand c'est le cas. Une dépendance qui ne vit que
     dans le corps SQL disparaît de la chaîne de traçabilité — écrite ici,
     elle survit jusqu'à la FEAT et au cahier des charges. -->

- Appelle : {appelés, ou « aucun »}
- Appelé par : {appelants, ou « aucun »}

## Hypothèses métier

<!-- interprétations que le corps ne prouve pas — JAMAIS en Acceptance
     Criteria. « aucune » est une réponse valide. -->

- {hypothèse, ou « aucune »} <!-- kind: hypothesis -->

## Covers

<!-- back-fill par l'assembleur déterministe (rung 2) : SFD-N / FD-N / AC-N
     de la FEAT module parente. -->
