<!--
  questions.reverse.template.md — Template ISOLÉ pour la boucle de validation
  humaine du reverse (Phase 3.9, agent reverse-clarifier).

  Conventions :
  - IDs Q-N STABLES : jamais renumérotés ; ajout = max+1 ; un bloc répondu
    n'est JAMAIS réécrit par le mode generate.
  - Chaque question pointe une source citable (artefact + item + evidence) —
    aucun gap inventé (bias toward not-verified §1).
  - Le Tech Lead remplit UNIQUEMENT le champ `Réponse:`. Le champ `Statut:`
    est géré par l'agent (ouverte | ingérée ({date}) | inexploitable).
  - Impact ∈ {critical, moderate, minor} : critical = bloque la fiabilité
    d'une FEAT destinée à /sdd-full ; moderate = item medium/low isolé ;
    minor = cosmétique/documentaire.

  Placeholders : {LegacyProject}, {Date}, {QTotal}, {QCritical}, {QBlocks}.
-->
# Questions reverse — {LegacyProject}

> Boucle de validation humaine (Phase 3.9). Remplir `Réponse:` puis lancer
> `/sdd-reverse-questions {LegacyProject} --ingest`. Une réponse claire permet
> de faire monter l'item concerné en `confidence: high`
> (`<!-- human-validated: Q-N -->`) — unique exception tracée au cap D1.

<!-- QUESTIONS: total={QTotal} ; critical={QCritical} ; generated={Date} -->

{QBlocks}

<!-- ============ FORMAT D'UN BLOC (1 par question) ============

## Q-N — {Titre court}

- **Source** : {artefact}#{item} (ex. FEAT 3-Login#BR-2, completeness-review U-4)
- **Constat** : {gap exact ou evidence file:line}
- **Impact** : {critical|moderate|minor} — {artefact aval affecté}
- **Question** : {1 phrase fermée, actionnable}
- **Réponse** :
- **Statut** : ouverte

============================================================== -->
