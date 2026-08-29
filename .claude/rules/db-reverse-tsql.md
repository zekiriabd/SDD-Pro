---
# TOK-C1 : path-scoped rule. Ne s'auto-injecte qu'au contact des artefacts du
# reverse base de données ; hors périmètre, les analystes SQL la lisent en STEP
# contexte. 0 token dans toute session forward ou reverse-de-code.
paths:
  - "workspace/old/**/.sys/proc-snapshot/**"
  - "workspace/old/**/.sys/schema-snapshot/**"
  - "workspace/old/**/.sys/db-context/**"
  - "workspace/old/**/.sys/db-context.json"
---

# Règle — Sémantique SQL pour le reverse base de données

> **Socle d'expertise partagé** par les 5 agents du reverse DB
> (`reverse-db-architect`, `reverse-sql-analyst`, `reverse-sql-function-analyst`,
> `reverse-sql-view-analyst`, `reverse-sql-trigger-analyst`). Ils diffèrent par
> l'**angle** — une opération, un calcul, une projection, un invariant — pas par
> ce qu'ils savent du SQL. Factoriser ce socle évite qu'ils dérivent les uns des
> autres sur la même construction.

Cette règle ne dit pas *quoi produire* (c'est le prompt de chaque agent). Elle
dit **comment lire correctement une construction SQL**, en particulier celles
qui se lisent de travers et produisent une User Story fausse mais crédible.

## TOC

- §1 — Principe : ce que le corps prouve vs ce qu'il suggère
- §2 — Pièges de lecture par construction (T-SQL en tête, équivalents par dialecte)
- §3 — Effets données : lire un CRUD honnête
- §4 — Transaction, atomicité et ce qu'un `ROLLBACK` annule vraiment
- §5 — Erreurs et préconditions → Acceptance Criteria négatifs
- §6 — Ce qui n'est pas statiquement lisible (et comment le déclarer)
- §7 — Équivalences multi-dialecte
- §8 — Règle mentale

---

## §1 Ce que le corps prouve vs ce qu'il suggère

Un corps SQL **prouve** : les tables touchées, les colonnes écrites, les
branches, les erreurs levées, les appels. Il **suggère** : l'intention métier,
le nom du concept, la raison d'une règle.

Ce qui est prouvé peut devenir un **Acceptance Criteria** avec une evidence
`fichier:ligne`. Ce qui est suggéré va en `## Hypothèses métier` avec
`<!-- kind: hypothesis -->`. Aucun agent ne franchit cette frontière — le
validateur la refuse, mais l'intention doit être bonne en amont.

**Corollaire pratique** : un nom d'objet n'est pas une preuve.
`usp_Client_Delete` qui ne fait qu'un `UPDATE Actif = 0` fait une **désactivation
logique**, pas une suppression. Ce que dit le corps l'emporte toujours sur ce que
promet le nom.

---

## §2 Pièges de lecture par construction

### 2.1 `MERGE` — trois effets en une instruction

`MERGE` peut insérer, mettre à jour et supprimer dans le même passage. Le
routage déterministe le compte donc en `CUD` et non en « écriture ». À la
lecture, chaque branche `WHEN MATCHED` / `WHEN NOT MATCHED [BY TARGET|BY SOURCE]`
est une **règle métier distincte** et mérite son propre AC. Un `WHEN NOT MATCHED
BY SOURCE THEN DELETE` est une suppression de masse conditionnelle : ne jamais la
démoter en plomberie.

### 2.2 `OUTPUT` / `RETURNING` — un effet ET un contrat

Une clause `OUTPUT` renvoie les lignes affectées à l'appelant : c'est à la fois
un effet données et une **partie du contrat de sortie**. `OUTPUT … INTO @t`
alimente une table locale (plomberie) ; `OUTPUT` sans `INTO` renvoie un result
set au consommateur (contrat, donc AC).

### 2.3 `inserted` / `deleted` — les pseudo-tables d'un trigger

Dans un trigger, `inserted` et `deleted` sont des **ensembles**, jamais une
ligne. La lecture correcte :

| Événement | `inserted` | `deleted` |
|---|---|---|
| `INSERT` | lignes nouvelles | vide |
| `UPDATE` | valeurs après | valeurs avant |
| `DELETE` | vide | lignes supprimées |

Un `UPDATE` se lit donc comme la **jonction** des deux. Et un corps qui fait
`SELECT @id = Id FROM inserted` ne traite **qu'une ligne arbitraire** d'un lot :
sur un `UPDATE` multi-lignes le trigger est silencieusement faux. C'est un défaut
réel à documenter, pas un détail d'implémentation.

### 2.4 `INSTEAD OF` — l'opération demandée n'a pas lieu

Un trigger `INSTEAD OF` **remplace** l'instruction. Ce que l'appelant croit
faire n'est pas ce qui se produit. C'est l'information la plus importante de la
User Story d'un tel trigger, et elle passe en premier.

### 2.5 `TRY/CATCH` et le piège du `ROLLBACK` implicite

Un `CATCH` qui ne relève pas l'erreur **avale** l'échec : l'appelant croit avoir
réussi. Lire `XACT_STATE()` :
- `-1` : transaction non validable — seul un `ROLLBACK` est possible ;
- `0` : plus de transaction ;
- `1` : transaction active et validable.

Un `CATCH` sans `THROW`/`RAISERROR` de relance est une **dette masquée**, à
signaler explicitement.

### 2.6 `SET NOCOUNT`, `SET XACT_ABORT`

`SET XACT_ABORT ON` change la sémantique d'échec : une erreur runtime annule
toute la transaction, sans passer par le `CATCH` du développeur. Le lire change
la réponse à « que se passe-t-il en cas d'échec ? ».

### 2.7 Table temporaire (`#t`) vs variable table (`@t`)

Une `@t` ne participe pas au `ROLLBACK` (elle survit à l'annulation) et n'a pas
de statistiques ; une `#t` est transactionnelle. Quand un compteur ou un journal
vit dans une `@t`, il **survit à l'échec** — parfois volontairement (audit),
souvent par accident. Le signaler.

### 2.8 `NULL` — trois valeurs, pas deux

`WHERE Colonne <> 'X'` **exclut les `NULL`**. `NOT IN (sous-requête)` renvoie un
ensemble vide dès qu'un `NULL` s'y trouve. Ces deux constructions produisent des
filtres métier que personne n'a écrits volontairement : quand la colonne est
nullable (le pack donne la nullabilité), le dire.

### 2.9 `TOP` / `LIMIT` sans `ORDER BY` déterministe

Résultat non reproductible. Dans une vue de reporting, c'est un défaut
fonctionnel, pas une optimisation.

### 2.10 `INNER JOIN` implicite dans une vue

Un `INNER JOIN` **filtre** : une commande sans client disparaît du reporting.
Une jointure est une règle de visibilité autant qu'un assemblage.

---

## §3 Effets données : lire un CRUD honnête

- `INSERT` → `C` · `UPDATE` → `U` · `DELETE` → `D` · `MERGE` → `CUD` ·
  `SELECT`/`FROM`/`JOIN` → `R`.
- Une écriture dont le verbe n'est pas déterminable se note `W` — **jamais** un
  verbe deviné.
- Une table lue **et** écrite porte les deux lettres.
- Le SQL construit dans une chaîne (`SET @sql = 'INSERT INTO …'`) n'est **pas**
  une écriture statique : l'analyseur masque les littéraux, et l'objet est
  marqué `dynamicSql`. Ne pas ré-inventer l'effet à la main.

Le pack fournit déjà cette matrice, calculée. La relire dans le corps sert à la
**qualifier** (« met à jour le statut », pas « écrit dans Commande »), jamais à
la corriger : si elle est fausse, c'est un bug de l'analyseur, à signaler.

---

## §4 Transaction et atomicité

Une transaction explicite autour d'écritures encode un **invariant tout-ou-rien**
qui est une règle métier : « la réservation de stock et la ligne de commande sont
créées ensemble ou pas du tout ». Cela mérite un AC.

Deux précisions qui changent le sens :
- les transactions imbriquées de T-SQL sont **un leurre** : un `COMMIT` interne
  ne valide rien, seul le `COMMIT` externe compte ; un `ROLLBACK` interne annule
  **tout**, y compris le travail de l'appelant ;
- un trigger s'exécute **dans** la transaction de l'instruction déclenchante :
  son `ROLLBACK` annule l'opération applicative entière.

---

## §5 Erreurs et préconditions

Chaque `RAISERROR` / `THROW` / `RAISE` / `SIGNAL` et chaque `RETURN` de code
d'erreur est une **précondition métier violée** → **un AC négatif**.

Documenter, quand ils sont lisibles : le numéro d'erreur, la sévérité et le
message. Le numéro est souvent la seule clé stable dont dispose l'application
appelante pour distinguer deux refus.

En cas de doute entre « bloque » et « avertit », documenter **bloque** et baisser
la confidence : un faux « bloque » se corrige en revue, un faux « avertit » se
découvre en production.

---

## §6 Ce qui n'est pas statiquement lisible

À déclarer explicitement, avec dégradation de confidence à `medium` :

| Construction | Pourquoi elle échappe à la lecture |
|---|---|
| SQL dynamique (`sp_executesql`, `EXEC(@sql)`, `EXECUTE IMMEDIATE`) | le comportement est assemblé au runtime |
| Curseur | l'effet dépend de l'ordre et du volume parcourus |
| Récursion (auto-appel, cycle mutuel) | terminaison et effet cumulé non lisibles |
| Appelé non résolu (serveur lié, autre base, objet supprimé, nom ambigu) | le corps de l'appelé est hors du périmètre lu |
| Corps chiffré (`WITH ENCRYPTION`) | il n'y a rien à lire — confidence `low`, ne rien inventer |
| `sp_` externe / CLR / `xp_` étendue | comportement hors catalogue |

**Ne jamais compenser une zone aveugle par une supposition confiante.** Le
mécanisme prévu est la question ouverte, qui alimente la boucle de validation
humaine.

---

## §7 Équivalences multi-dialecte

Le socle est T-SQL (moteur prioritaire) ; les équivalents se lisent de la même
façon :

| Notion | T-SQL | PL/pgSQL | PL/SQL | MySQL/PSM |
|---|---|---|---|---|
| Lever une erreur | `RAISERROR` / `THROW` | `RAISE` | `RAISE_APPLICATION_ERROR` | `SIGNAL` |
| SQL dynamique | `sp_executesql` / `EXEC()` | `EXECUTE` | `EXECUTE IMMEDIATE` | `PREPARE`/`EXECUTE` |
| Pseudo-tables trigger | `inserted` / `deleted` | `NEW` / `OLD` | `:NEW` / `:OLD` | `NEW` / `OLD` |
| Portée trigger | par **instruction** (lot) | `FOR EACH ROW` ou statement | `FOR EACH ROW` ou statement | `FOR EACH ROW` |
| Renvoi de lignes affectées | `OUTPUT` | `RETURNING` | `RETURNING INTO` | (absent) |
| Table temporaire | `#t` / `@t` | `TEMP TABLE` | `GLOBAL TEMPORARY` | `TEMPORARY` |

**Piège de portée** : en T-SQL un trigger est déclenché **une fois par
instruction** (d'où §2.3) ; en PL/SQL et MySQL, `FOR EACH ROW` est courant. Ne
jamais transposer l'habitude d'un moteur sur un autre.

---

## §8 Règle mentale

**« Le corps prouve les effets ; le nom ne prouve rien. Ce que je ne peux pas
lire se déclare, ne se devine pas. »**

Pointeurs : `@.sdd/rules/reverse-engineering.md` (§1-§6 anti-derive + taxonomie
`[REVERSE_*]`), `@.sdd/rules/error-classification.md` (format ERROR 3L),
`@.sdd/rules/output-protocol.md` (chat 1L).
