---
description: Reverse engineering d'UN objet SQL exécutable — procédure stockée, fonction, vue ou trigger (P0.1 2026-07-24) — en lecture seule via la connection string de stack.md. Introspecte l'objet, génère sa User Story (1 objet SQL = 1 US) et met à jour/crée la FEAT du module métier auquel il appartient. Multi-dialecte — SQL Server + PostgreSQL (live-validés), Oracle + MySQL/MariaDB (scaffold-validés, runtime live pending). Ne modifie JAMAIS la base.
---
# /sdd-db-reverse {proc-name} [--project DB] [--json]

## Rôle

Reverse engineering ciblé d'**une seule** procédure stockée. Pendant unitaire de
`/sdd-db-reverse-full`. La procédure devient **une User Story** ; elle est
rattachée à la **FEAT de son module** (créée si absente, sinon mise à jour).

```
/sdd-db-reverse dbo.usp_Contact_Insert
   └─ introspect READ-ONLY (1 proc) ─► snapshot + inventory (module Contact)
       └─ reverse-sql-analyst ─► us/{n}-{m}-Creer-Contact.md
           └─ build_proc_feats --unit U-x ─► feats/{n}-Contact.md (assemblé/rafraîchi)
```

## Args

| Arg | Type | Description |
|---|---|---|
| `{proc-name}` | requis | Nom de la procédure (`[schema.]nom`, ex. `dbo.usp_Contact_Insert` ou `usp_Contact_Insert`) |
| `--project DB` | optionnel | Dossier sous `workspace/old/` (défaut = `DB_NAME` de stack.md) |
| `--json` | flag | Sortie machine |

## Garanties lecture seule

Identiques à `/sdd-db-reverse-full` : `SELECT` catalogue + `OBJECT_DEFINITION`
uniquement (validés par `readonly_guard`), jamais de DDL/DML, jamais d'exécution
de la procédure. Le mot de passe (stack.md) reste en RAM, jamais loggé.

## Pré-conditions

1. `stack.md ## Active Database` complet. Sinon → `[REVERSE_DB_CONFIG_MISSING]`.
2. Driver `reverse-db` installé. Sinon → `[REVERSE_DB_UNREACHABLE]`.
3. La procédure existe dans le catalogue. Sinon → `[REVERSE_PROC_NOT_FOUND]`.
   Chiffrée (`WITH ENCRYPTION`) → `[REVERSE_PROC_ENCRYPTED]` (US `low` + bannière, rien inventé).

## Actions

1. `python .sdd/python/sdd_reverse_scripts/reverse_proc_introspect.py --proc {proc-name} [--project DB]`
   → snapshot de la procédure + **MERGE** dans `inventory.json` existant (la proc rejoint
   le module de son objet ; si la FEAT du module existe déjà, elle **grandit**, `(n, Name)`
   et `usIndex` des procs déjà reversées sont **préservés** — pas d'écrasement).
2. **Routage par complexité (0 token)** :
   `python .sdd/python/sdd_reverse_scripts/build_proc_us.py --project DB --unit {U-N} --json`
   - proc **simple** (CRUD/SELECT, ni branche, ni SQL dynamique, ni erreur) → US générée
     **déterministiquement, 0 token** (champ `written`).
   - proc **complexe** (logique métier) → listée dans `needs_llm` → spawn
     `Agent(reverse-sql-analyst)` avec `{U-N} --proc {proc-name}` (1 US, LLM seulement là où ça vaut le coût).
3. `python .sdd/python/sdd_reverse_scripts/build_proc_feats.py --project DB --unit {U-N}`
   → assemble/rafraîchit la FEAT du module (remontée depuis les US **réellement
   lues** + l'inventaire, jamais relecture du corps SQL), puis écrit `Covers:` et
   résout le `Parent FEAT hash` dans chaque US du module. Exit 4 = FEAT préservée
   car éditée par un humain (`--force` pour écraser).
4. `validate_reverse_feat.py` **puis** `check_reverse_feat_for_full.py
   --feat-path workspace/feats/{n}-*.md` (gate de consommation : `confidence != high`
   ⇒ exit 1, revue humaine ; `--allow-reverse-low` pour forcer).
4.bis `check_ladder_traceability.py --project workspace/old/{DB} --unit {U-N}`
   (informational) — chaîne descendante **FEAT item → US AC → ligne de snapshot**,
   avec résolution de chaque `evidence:` **sur disque**. Le chemin base de données
   a un barreau de moins que le chemin code (pas d'analyse 3a) ; le vérificateur
   le reconnaît. Jamais bloquant.
5. Ligne chat `[REVERSE] {objet} → US {n}-{m}, module {Module}. (100%)`.

## Anti-derive

- Une seule procédure par invocation.
- 1 proc = 1 US ; la FEAT module agrège, jamais relue depuis le T-SQL.
- Lecture seule absolue ; pas d'invention (bias toward present) ; no-spawn d'agent.
- Idempotence : re-run réécrit la même US et rafraîchit la FEAT module.

Voir `.sdd/docs/reverse-proc-engineering.audit.md` + `.sdd/rules/reverse-engineering.md`.
