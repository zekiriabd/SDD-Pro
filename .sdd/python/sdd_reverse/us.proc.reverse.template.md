<!--
us.proc.reverse.template.md — isolated template for db-reverse User Stories.
Read by the reverse-sql-analyst agent (rung 1). One stored procedure = one US.
Placeholders: {n} feat number, {m} US index, {usName} capability slug,
{module} business module, {fqProc} schema.proc, {dialect} engine, {confidence}.
Evidence MUST point into .sys/proc-snapshot/{schema}.{proc}.sql:Lstart-Lend
(plain digits, no "L" prefix in the file — e.g. :12-30).
-->
---
ID: {n}-{m}-{usName}
Parent FEAT: {n}-{module}
generated-by: sdd-reverse
source-proc: {fqProc}
language-detected: {dialect}
Confidence: {confidence}
Status: Draft
---

# US-{m}: {Titre lisible de la capability}

> ⚠️ User Story reverse-engineerée depuis la procédure stockée `{fqProc}`
> ({dialect}, lecture seule). Décrit le comportement OBSERVÉ, jamais souhaité.

## Story

En tant que **{acteur}**, je veux **{capability}**, afin de **{bénéfice observable}**.

## Acceptance Criteria

<!-- 1 AC par chemin observable dans le corps T-SQL : nominal + chaque
     précondition/erreur (RAISERROR/THROW/IF EXISTS) = 1 AC négatif.
     Chaque AC porte son evidence + confidence. bias toward present. -->

- AC-1: Given {précondition}, when {appel de la procédure}, then {effet observable
  sur les tables / valeur retournée}. <!-- evidence: .sys/proc-snapshot/{schema}.{proc}.sql:Ls-Le --> <!-- confidence: {confidence} -->

## Data Effects (plomberie démotée)

<!-- tables lues / écrites, paramètres + OUTPUT, transaction, SQL dynamique.
     Démoté ici (pas en règle métier) — sauf logique métier réelle (calcul,
     validation, machine à états) qui remonte en AC/règle ci-dessus. -->

- Lit : {tables_read}
- Écrit : {tables_written}
- Paramètres : {params}
- Transaction : {oui/non} · SQL dynamique : {oui/non}

## Covers

<!-- back-fill par l'assembleur déterministe (rung 2) : SFD-N / FD-N / AC-N
     de la FEAT module parente. -->
