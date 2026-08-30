<!-- GENERATED FROM .sdd/ (commande /sdd-reverse-questions) — DO NOT EDIT -->
<!-- Boucle de validation humaine structurée. Mode generate (défaut) — consolide les gaps reverse (complétude, traçabilité, items medium/low, AC non dérivables, curation HUMAN-DECISION) en questions.md à remplir par le Tech Lead. Mode --ingest — ré-injecte les réponses dans les FEATs (human-validated, confidence, REVERSE-GATE, hash US). Spawn agent reverse-clarifier (Sonnet 4.6). Emprunt Reversa (questions.md + answer_mode) — audit comparatif 2026-06-12. -->
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

<!-- @llm-only-flags-file — les flags de /sdd-reverse-questions sont
     interprétés par le LLM (l'agent reverse-clarifier) ; les scripts
     délégués (check_ladder_traceability, validate_reverse_feat) ont leur
     propre parsing. -->

# /sdd-reverse-questions {LegacyProject} [--ingest] [--interactive] [--json]

## Rôle

Fermer la boucle Tech Lead ↔ reverse : les gaps détectés par les reviewers
(aujourd'hui informationnels et dispersés dans `.sys/modules/*/`) deviennent
des **questions structurées** (`Q-N`, impact, evidence) dans un fichier unique ;
les réponses humaines sont ré-injectées dans les FEATs avec traçabilité
(`<!-- human-validated: Q-N -->`) — c'est la voie officielle pour faire monter
un item `medium`/`low` en `high` (unique exception au cap D1, tracée).

## Args

| Arg | Type | Description |
|---|---|---|
| `{LegacyProject}` | requis | Sous-dossier `workspace/old/` |
| `--ingest` | flag | Ré-injecte les blocs `Réponse:` remplis au lieu de générer |
| `--interactive` | flag | **Clôture la boucle en un run** (C3) : génère `questions.md`, pose les questions ouvertes dans la session, écrit les réponses, puis `--ingest` — sans double invocation manuelle. Dégrade en `generate` si la session n'est pas interactive. |
| `--json` | flag | Émet le résumé en JSON |

## Pré-conditions

- `generate` : `inventory.json` + ≥ 1 FEAT reverse existent. Sinon → ERROR
  `[REVERSE_NO_SOURCE]` / `[REVERSE_UNIT_NOT_FOUND]`.
- `--ingest` : `workspace/old/{P}/.sys/questions.md` existe avec ≥ 1 `Réponse:`
  non vide. Sinon → `[REVERSE_QUESTIONS_PENDING]` (informational, STOP propre).

## Actions

1. **Spawn unique** `Agent(reverse-clarifier)` avec args = `{P}` [+ `--ingest`]. <!-- no-spawn §9 -->
2. `generate` : collecte déterministe (completeness-reviews, ladder-traceability
   re-run, items medium/low, parity-map `## Non dérivables`, curation
   HUMAN-DECISION) → `questions.md` (IDs `Q-N` stables, blocs répondus préservés).
3. `--ingest` : édition chirurgicale des items FEAT concernés, puis
   resynchronisation ordre strict — confidence FEAT + REVERSE-GATE ensemble,
   `validate_reverse_feat.py`, hash US en dernier
   (`resolve_us_hash_sentinel.py --feat-number {n}`, §10).

## Mode `--interactive` (clôture en un run — C3, audit 2026-07-24)

Objectif : supprimer la double invocation manuelle (generate → édition humaine →
ingest). En session interactive, l'orchestrateur :

1. **Génère** `questions.md` (étape `generate` normale).
2. **Liste** les questions ouvertes déterministiquement (jamais de parsing LLM
   du markdown) :
   `python .sdd/python/sdd_reverse_scripts/reverse_questions_io.py workspace/old/{P}/.sys/questions.md --list-open --json`
   → `[{id, title, question, impact}]`, triées `critical → moderate → minor`.
3. **Pose** ces questions au Tech Lead via `AskUserQuestion` (par lots ≤ 4,
   `critical` d'abord). Aucune réponse inventée ; « Autre » toujours possible.
4. **Écrit** chaque réponse **atomiquement** (jamais d'`Edit` LLM à la main) :
   `... reverse_questions_io.py .../questions.md --set-answer Q-N --text "<réponse>"`
5. **Ingère** : `/sdd-reverse-questions {P} --ingest` (agent `reverse-clarifier`,
   resync confidence/REVERSE-GATE/hash US, ordre strict §10).

**Dégradation gracieuse** : si la session n'est pas interactive (run headless /
CI / `AskUserQuestion` indisponible), `--interactive` se comporte comme
`generate` et imprime la marche à suivre manuelle (`[REVERSE_QUESTIONS_PENDING]`
informational). Aucune réponse n'est jamais fabriquée — l'absence de réponse
laisse le bloc ouvert.

## Sortie

```
workspace/old/{P}/.sys/questions.md                      (generate / --interactive)
workspace/feats/{n}-{FeatName}.md  (édités, --ingest / --interactive)  + US resynchronisées
```

## Émission chat

```
[REVERSE] {Q} questions ouvertes ({C} critical) → workspace/old/{P}/.sys/questions.md. (PROGRESS%)
[REVERSE] Ingestion réponses : {I} item(s) clarifié(s), {R} question(s) restante(s). (PROGRESS%)
```

## Anti-derive

- No-spawn d'agent autre que `reverse-clarifier`
- **Jamais d'invention** : ni gap, ni réponse — chaque question pointe une source citable
- IDs `Q-N` stables, jamais renumérotés
- `--ingest` est la SEULE voie d'édition d'une FEAT reverse post-3c (véhicule de la revue humaine Phase 5)
- Jamais bloquant : questions ouvertes = `[REVERSE_QUESTIONS_PENDING]` informational

Voir `.sdd/rules/reverse-engineering.md §6` ([REVERSE_QUESTIONS_PENDING], [REVERSE_ANSWER_INGEST_FAILED]) + §10 + `.sdd/agents/reverse-clarifier.md`.
