---
command: sdd-db-reverse
phase: db-reverse
description: Reverse engineering d'UN objet SQL exécutable — procédure stockée, fonction, vue ou trigger (P0.1 2026-07-24) — en lecture seule via la connection string de stack.md. Introspecte l'objet, génère sa User Story (1 objet SQL = 1 US) et met à jour/crée la FEAT du module métier auquel il appartient. Multi-dialecte — SQL Server (live-validé), PostgreSQL + Oracle + MySQL/MariaDB (scaffold-validés, runtime live pending — downgrade PostgreSQL audit 2026-08-29). Ne modifie JAMAIS la base.
loader: .sdd/loader.reverse.yml
---
# /sdd-db-reverse {proc-name} [--project DB] [--no-architect] [--json]

## Rôle

Reverse engineering ciblé d'**un seul** objet SQL exécutable — procédure
stockée, fonction, vue, trigger (ou package Oracle, routé vers le
proc-analyst). Pendant unitaire de `/sdd-db-reverse-full`. L'objet devient
**une User Story** ; il est rattaché à la **FEAT de son module** (créée si
absente, sinon mise à jour).

```
/sdd-db-reverse dbo.usp_Contact_Insert
   └─ introspect READ-ONLY (1 objet) ─► snapshot + inventory (module Contact)
       └─ Phase 0 db-context (0.A faits + pack de l'objet, 0.B interprétation)
          └─ spécialiste de SA famille (proc/fonction/vue/trigger)
             ─► us/{n}-{m}-Creer-Contact.md
              └─ build_proc_feats --unit U-x ─► feats/{n}-Contact.md (assemblé/rafraîchi)
```

> **Phase 0 câblée ici (correctif 2026-08-30).** La commande enchaînait
> l'introspection directement sur le spécialiste, alors que celui-ci exige
> `.sys/db-context/packs/{objet}.md` (pré-condition 2 de sa définition). Sur un
> projet frais — aucun `/sdd-db-context` ni `/sdd-db-reverse-full` préalable —
> le pack n'existait pas et l'analyste sortait en `[REVERSE_DB_PACK_MISSING]`.
> Le mode objet unique construit désormais le Database Context lui-même : il ne
> dépend d'aucun run full antérieur.

## Args

| Arg | Type | Description |
|---|---|---|
| `{proc-name}` | requis | Nom de la procédure (`[schema.]nom`, ex. `dbo.usp_Contact_Insert` ou `usp_Contact_Insert`) |
| `--project DB` | optionnel | Dossier sous `workspace/old/` (défaut = `DB_NAME` de stack.md) |
| `--no-architect` **@llm-only-flag** | flag | Phase 0 limitée à 0.A (faits + pack, 0 token) — aucune interprétation d'architecte. Interprété par la commande (elle ne spawne alors pas l'architecte) ; `db_context_build.py` n'en a pas besoin |
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
4. **Pas de pré-requis de run full.** Le Database Context (Phase 0) n'a pas
   besoin d'exister avant l'appel : l'étape 1.bis le construit ou le rafraîchit.
   Un `/sdd-db-context` préalable reste utile (interprétation sur la base
   entière), jamais obligatoire.

## Actions

1. `python .sdd/python/sdd_reverse_scripts/reverse_proc_introspect.py --proc {proc-name} [--project DB]`
   → snapshot de la procédure + **MERGE** dans `inventory.json` existant (la proc rejoint
   le module de son objet ; si la FEAT du module existe déjà, elle **grandit**, `(n, Name)`
   et `usIndex` des procs déjà reversées sont **préservés** — pas d'écrasement).
1.bis **Phase 0 — Database Context (obligatoire, jamais sautée)** : le
   spécialiste lit **son pack**, pas la base ; sans pack, il STOP en
   `[REVERSE_DB_PACK_MISSING]`. Le mode objet unique construit donc le contexte
   lui-même, exactement comme `/sdd-db-reverse-full` :
   ```bash
   python .sdd/python/sdd_reverse_scripts/db_context_build.py --project workspace/old/{DB}
   ```
   - **0.A déterministe, 0 token** : faits (tables/colonnes/PK/FK/CHECK, corps),
     matrice CRUD, graphe d'appels, plan de vagues, `contextVersion` →
     `db-context.json` + l'arbre `db-context/`, **dont le pack de l'objet visé**.
     Idempotent : sur un contexte déjà à jour, c'est un no-op.
   - **0.B interprétation** : spawn `Agent(reverse-db-architect)` puis
     ```bash
     python .sdd/python/sdd_reverse_scripts/db_context_build.py \
       --project workspace/old/{DB} \
       --merge-hypotheses workspace/old/{DB}/.sys/db-context.hypotheses.json
     ```
     **Sauté** si `--no-architect`, ou si le `contextVersion` est inchangé (les
     hypothèses précédentes sont alors réutilisées telles quelles — cache).
   - **Conséquence à connaître** : introspecter un objet **nouveau** change les
     faits, donc le `contextVersion` — les hypothèses ET les `findings` de vagues
     antérieurs sont abandonnés (une lecture périmée d'une base modifiée est pire
     que pas de lecture). C'est pourquoi 0.B est rejouée ici. Pour reverser
     beaucoup d'objets un à un sans repayer l'architecte à chaque fois, passer
     `--no-architect` puis lancer un `/sdd-db-context` unique à la fin.
   - Détail complet et usage isolé : `/sdd-db-context`.
2. **Routage par complexité (0 token)** :
   `python .sdd/python/sdd_reverse_scripts/build_proc_us.py --project DB --unit {U-N} --json`
   - objet **simple** (CRUD/SELECT, ni branche, ni SQL dynamique, ni erreur) → US générée
     **déterministiquement, 0 token** (champ `written`).
   - objet **complexe** (logique métier) → listé dans `needs_llm` → spawn du
     **spécialiste de sa famille** avec `{U-N} --object {fq}` (1 US, LLM
     seulement là où ça vaut le coût). L'agent à spawner est porté par le champ
     `agent` de l'entrée `needs_llm` — l'utiliser tel quel ; à défaut (inventaire
     antérieur au champ), router par la famille du catalogue :

     | Famille (`routineType`) | Agent |
     |---|---|
     | procédure stockée · package Oracle | `reverse-sql-analyst` |
     | fonction (scalaire / inline / table) | `reverse-sql-function-analyst` |
     | vue | `reverse-sql-view-analyst` |
     | trigger | `reverse-sql-trigger-analyst` |

     Avant le spawn, vérifier que
     `workspace/old/{DB}/.sys/db-context/packs/{schema}.{objet}.md` existe. Absent
     ⇒ la Phase 0 n'a pas produit le pack (objet hors plan, contexte périmé) :
     STOP `[REVERSE_DB_PACK_MISSING]`, FIX = relancer l'étape 1.bis
     (`db_context_build.py --project workspace/old/{DB} --refresh`). Ne jamais
     spawner un analyste sans son pack — il fouillerait la base à sa façon,
     exactement ce que la Phase 0 existe pour empêcher.
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
- **Phase 0 jamais sautée** : aucune US n'est produite avant que le pack de
  l'objet existe (même contrat que `/sdd-db-reverse-full`, même script).
- 1 proc = 1 US ; la FEAT module agrège, jamais relue depuis le T-SQL.
- Lecture seule absolue ; pas d'invention (bias toward present) ; no-spawn d'agent.
- Idempotence : re-run réécrit la même US et rafraîchit la FEAT module.

Voir `.sdd/docs/reverse-proc-engineering.audit.md` + `.sdd/rules/reverse-engineering.md`.
