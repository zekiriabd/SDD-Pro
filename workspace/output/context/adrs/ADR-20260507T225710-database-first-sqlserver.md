# ADR-20260507T225710 -- Database-First approach -- SQL Server

- **Statut** : Accepted
- **Date** : 2026-05-07
- **Auteur** : arch
- **Phase** : 4-ARCH

---

## Context

DatabaseType=SqlServer est configure dans Project Config. L'approche Database-First (introspection du schema existant -> generation des entities JPA) est requise. Le driver mssql-jdbc 12.8.1.jre11 est installe dans simback.

---

## Decision

Le scaffolding utilise l'approche Database-First: introspection READ-ONLY de INFORMATION_SCHEMA + sys.indexes, puis generation des entities Kotlin JPA via templates. Le schema est capture dans workspace/output/db/schema.json (source de verite machine) et workspace/output/db/schema.md (humain).

Note: la Phase B (introspection + scaffolding) a ete differee au run suivant car le serveur SQL Server (10.9.0.238:1433) est inaccessible depuis l'environnement de build actuel (reseau prive non route). Relancer /arch-init depuis un poste avec acces reseau a la base.

---

## Consequences

**Positifs :**
- Schema DB fait autorite -- les entities Kotlin reflètent fidelement la base existante.
- Introspection READ-ONLY (aucune modification de la base).
- schema.json versione avec diff (schema.prev.json + schema.diff.md) pour detecter les evolutions.

**Negatifs / dette acceptee :**
- Phase B incomplete ce run (reseau indisponible). Les entities /entity/ sont a generer manuellement ou via prochain /arch-init avec acces reseau.
- hibernate-tools a besoin d'une configuration Gradle supplementaire si utilise en mode automatique.

---

## Alternatives considerees

- Code-First (Flyway + entity manuelles) : ecarte car la base SQL Server existante fait foi.
- jOOQ codegen : ecarte (hibernate-tools est la recommandation du stack §4.5 pour SDD_Pro v6).

---

## Liens

- Stack : `.claude/stacks/backend/kotlin-spring-boot.md §4.5`
- Schema : `workspace/output/db/schema.json` (a generer au prochain run avec acces reseau)
