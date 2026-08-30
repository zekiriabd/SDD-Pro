<!-- GENERATED FROM .sdd/ (commande /sdd-db-context) — DO NOT EDIT -->
<!-- Phase 0 du reverse base de données — construit le Database Context (SSoT versionné) avant toute remontée en User Story. Récolte déterministe des faits (tables, colonnes, PK/FK, index, contraintes CHECK, corps d'objets, matrice CRUD, graphe de dépendances, plan de vagues), puis interprétation par l'agent reverse-db-architect (glossaire, sous-domaines, rôles, risques, questions ouvertes). Produit db-context.json + un arbre Markdown découpé par objet, réutilisé tant que la base n'a pas changé. Ne modifie JAMAIS la base. -->
<!-- ============================================================ -->
<!-- IMPORTANT — SPAWN SEMANTICS UNDER CODEX (audit R10 2026-07-26) -->
<!-- Toute mention `Task tool (subagent_type=X)`, `Agent(X)`, ou    -->
<!-- « spawn agent X » dans le corps ci-dessous est une INSTRUCTION -->
<!-- Claude-Code-native. Sous Codex/Gemini, ces spawns ne sont PAS  -->
<!-- des tools disponibles ; l'émulation passe par la CLI wrapper : -->
<!--                                                                -->
<!--   python .sdd/python/sdd_scripts/spawn_agent_cli.py \         -->
<!--       --agent <name>                                           -->
<!--       --task-file <path>   (ou --task "...")                 -->
<!--       [--harness codex|gemini-cli|claude-code]                 -->
<!--       [--provider openai|google|anthropic|moonshot]            -->
<!--       [--tier deep|balanced|fast]                              -->
<!--       [--schema-file <path.json>]                              -->
<!--                                                                -->
<!-- Le wrapper renvoie du JSON canonique sur stdout : { ok,        -->
<!-- parsed, raw, error_class, schema_errors, attempts, ... }.      -->
<!-- Voir .sdd/python/sdd_lib/spawn_agent.py (isolation cwd,        -->
<!-- parallélisme borné à MaxParallel, retry-on-schema-fail).       -->
<!-- Sub-agents intra-session Claude = 0 tokens ; ici = tokens du   -->
<!-- LLM cible directement + coût réseau.                           -->
<!-- ============================================================ -->
<!-- Arguments SDD passés via $ARGUMENTS (ex. numéro de FEAT). -->

Arguments: $ARGUMENTS

# /sdd-db-context [--project DB] [--refresh] [--no-architect] [--diff-against PATH] [--json]

## Rôle

Construit le **Database Context**, la source de vérité partagée du reverse base
de données. Aucun objet SQL n'est remonté en User Story avant qu'elle existe :
c'est ce qui empêche chaque analyste de redécouvrir la base, chacun à sa façon.

```
db-introspection.json + db-schema.json   (déjà extraits en LECTURE SEULE)
   └─[0.A déterministe, 0 token]─► faits + graphe + plan de vagues
        └─[0.B agent reverse-db-architect]─► hypothèses (glossaire, domaines, risques)
             └─ db-context.json (SSoT versionné) + db-context/ (arbre découpé)
                  └─ packs/{objet}.md ─► consommés par les analystes spécialisés
```

## Le contrat central — faits ≠ hypothèses

| | Produit par | Contenu | Peut devenir un AC ? |
|---|---|---|---|
| `facts` | scripts déterministes (0 token) | tables, colonnes, clés, CHECK, CRUD, graphe | **oui** |
| `hypotheses` | agent `reverse-db-architect` | glossaire, sous-domaines, rôles, risques | **jamais** |

La séparation est **structurelle** : l'agent écrit un fichier distinct
(`db-context.hypotheses.json`) qu'un script fusionne dans la seule branche
`hypotheses`. Il ne peut pas écraser un fait, même en essayant. Même garde que
`db-schema.enrichment.json` (ADV-3).

## Args

| Arg | Type | Description |
|---|---|---|
| `--project DB` | optionnel | Dossier sous `workspace/old/` (défaut = `DB_NAME` de `stack.md`) |
| `--refresh` | flag | Ignore le contexte précédent et relance l'architecte (les hypothèses portées sont abandonnées) |
| `--no-architect` **@llm-only-flag** | flag | S'arrête après 0.A — faits seuls, aucun coût LLM. Interprété par la commande (elle ne spawne pas l'architecte) ; le script 0.A n'en a pas besoin |
| `--depth N` | optionnel | Profondeur d'appelés portée dans un pack (défaut 2) |
| `--budget N` | optionnel | Taille max d'un pack en octets (défaut 14000) |
| `--diff-against PATH` | optionnel | Compare à un `db-context.json` antérieur et rapporte la dérive (exit 4), sans rien écrire |
| `--json` | flag | Sortie machine |

## Pré-conditions

1. `workspace/old/{DB}/.sys/db-introspection.json` existe (produit par
   `reverse_proc_introspect.py --full`). Sinon → `[REVERSE_DB_CONFIG_MISSING]`.
2. `db-schema.json` est optionnel mais fortement recommandé : sans lui, le
   contexte n'a pas la structure relationnelle et les packs sont plus pauvres.

## Actions

1. **Phase 0.A — faits (déterministe, 0 token)** :
   ```bash
   python .sdd/python/sdd_reverse_scripts/db_context_build.py --project workspace/old/{DB}
   ```
   Produit `db-context.json` (faits + `executionPlan` + `contextVersion`),
   `db-context.digest.json` (digest léger pour l'architecte) et l'arbre
   `db-context/` : `_overview.md`, `glossary.json`, `tables/`, `procedures/`,
   `functions/`, `views/`, `triggers/`, `packages/`, `packs/`.

2. **Cache** : `contextVersion` est un sha256 des faits canoniques. Si la base
   n'a pas bougé, l'interprétation de l'architecte est **réutilisée** — la
   Phase 0.B n'est pas repayée. Si elle a bougé, l'interprétation périmée est
   **abandonnée** (et le rapport le dit) : une lecture obsolète d'une base
   modifiée est pire que pas de lecture.

3. **Phase 0.B — interprétation** (sauf `--no-architect`, et sauf si le cache
   est valide) : spawn `Agent(reverse-db-architect)` avec `{DB}`. Il lit le
   **digest** (aperçu + métriques + fiches des tables pivot), jamais le
   catalogue brut ni un corps d'objet, et écrit
   `.sys/db-context.hypotheses.json`.

4. **Fusion déterministe** :
   ```bash
   python .sdd/python/sdd_reverse_scripts/db_context_build.py \
     --project workspace/old/{DB} \
     --merge-hypotheses workspace/old/{DB}/.sys/db-context.hypotheses.json
   ```
   Refusée si le `contextVersion` déclaré par l'architecte ne correspond plus
   aux faits (`[REVERSE_DB_CONTEXT_STALE]`). Les packs sont régénérés avec le
   bloc d'hypothèses, marqué `kind: hypothesis`, et l'extrait léger
   `db-context/glossary.json` (glossaire + sous-domaines + `contextVersion`)
   est réécrit pour le composer rung 2.

5. Ligne chat `[REVERSE] Contexte DB {DB} → {t} table(s), {o} objet(s),
   {w} vague(s), {u} appel(s) non résolu(s). (100%)`.

## Dérive entre deux reverse

```bash
python .sdd/python/sdd_reverse_scripts/db_context_build.py \
  --project workspace/old/{DB} --diff-against chemin/vers/ancien-db-context.json
```

Rapporte les tables ajoutées/retirées/modifiées (colonnes, types, `CHECK`), les
objets ajoutés/retirés/modifiés (corps, appels, écritures, contrat) et — le seul
chiffre qui compte pour un Tech Lead — **la liste des objets dont la User Story
doit être re-dérivée**. Exit 4 si les deux contextes diffèrent, 0 sinon : le
gate CI qui garantit que le cahier des charges reste synchrone avec la base.

## Sortie

```
workspace/old/{DB}/.sys/db-context.json              SSoT machine (faits + plan + hypothèses)
workspace/old/{DB}/.sys/db-context.digest.json       digest léger lu par l'architecte (0.B) — le SEUL
                                                     porteur du contextVersion qu'il recopie dans
                                                     db-context.hypotheses.json
workspace/old/{DB}/.sys/db-context.hypotheses.json   écrit par l'architecte, fusionné par script
workspace/old/{DB}/.sys/db-context/_overview.md      orientation base entière
workspace/old/{DB}/.sys/db-context/glossary.json     extrait léger (glossary + subdomains +
                                                     contextVersion) pour le composer rung 2 —
                                                     évite la lecture du db-context.json entier
workspace/old/{DB}/.sys/db-context/tables/*.md       1 fiche par table
workspace/old/{DB}/.sys/db-context/{procedures,functions,views,triggers,packages}/*.md
workspace/old/{DB}/.sys/db-context/packs/*.md        1 slice par objet, pour les analystes
```

## Anti-derive

- **Lecture seule absolue** : aucune requête n'est émise ici — la commande
  consomme des artefacts déjà extraits sous `readonly_guard`.
- **Structure uniquement** : aucune donnée métier, aucun identifiant de
  connexion ne rentre dans le contexte.
- **L'architecte n'écrit pas de faits** — garanti par la **whitelist de fusion**
  de `db_context.merge_architect_output`, qui ne recopie que les cinq clés de
  `hypotheses` depuis le fichier séparé `db-context.hypotheses.json` : un `facts`
  ou un `executionPlan` qu'il aurait produit est ignoré. Complété par l'entrée
  `reverse-db-architect` de la matrice `audit_file_ownership.py` (audit
  2026-08-29, M3), qui journalise tout fichier touché hors périmètre. La
  formulation précédente — « garanti par construction » — couvrait plus large que
  le mécanisme : un `Write` direct sur `db-context.json` contourne la fusion, et
  c'est le hook `protect_framework.py` (a priori) plus cette matrice (a
  posteriori) qui traitent ce cas, pas la fusion elle-même.
- **Aucun agent ne lit tout le contexte** : chacun reçoit son pack, borné, qui
  déclare ce qu'il a dû tronquer.
- Idempotence : re-run sur une base inchangée réutilise tout et ne coûte rien.

Voir `.sdd/docs/reverse-db-audit-2026-07.md` + `.sdd/rules/reverse-engineering.md`
+ invariants `reverse-db-context-facts-vs-hypotheses`,
`reverse-db-context-versioned-and-diffable`, `reverse-db-context-slicing`.
