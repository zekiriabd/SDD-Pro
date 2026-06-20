# FEAT: {Name}

FEAT ID: {n}-{Name}
Status: Draft

## Context
<2-4 phrases. Ce qui existe aujourd'hui. Ce qui manque.>

## Objective
<Un seul résultat mesurable. Observable, pas aspirationnel.>

## Quantified Goal (v7.0.0 — anti-GIGO)
<KPI mesurable + valeur cible + délai. Exemples :
"taux conversion +15% sous 6 mois", "p95 latence < 300ms sous charge nominale",
"taux abandon panier -20% sur cible mobile". Écrire `<à préciser>` si non
connu — mais le gap doit être explicite, pas absent.>
- Metric: <à préciser>
- Target: <à préciser>
- Deadline: <à préciser>

## Non-Functional Constraints (v7.0.0)
<Champs structurés non-skippables. Si non applicable, écrire `n/a`
explicitement — l'absence du champ déclenche un WARN feat-validate.>
- Expected volume: <ex. 10k requêtes/jour, 500 utilisateurs concurrents, ou n/a>
- Performance SLA: <ex. p95 < 500ms, ou n/a>
- Data retention: <ex. logs 90 jours, données utilisateur GDPR, ou n/a>
- Compliance: <ex. GDPR/RGPD, HIPAA, SOC2, PCI-DSS, ou n/a>
- Integration: <système d'enregistrement / API externes / SSO, ou n/a>
- Degraded mode: <comportement si dépendance down, ou n/a>

## Actors
- <acteur-1>: <rôle>
- <acteur-2>: <rôle>

## Functional Needs
<Liste de besoins fonctionnels exprimés en verbe d'action. Chaque besoin
porte un identifiant explicite SFD-N stable pour la traçabilité (ne pas
réordonner ni renuméroter après génération des US — ajouter en fin de
liste avec un nouveau N).>
- SFD-1: <besoin fonctionnel exprimé en verbe d'action>
- SFD-2: <besoin fonctionnel>
- SFD-N: <besoin fonctionnel>

## Business Rules
- BR-1: <règle métier sans ambiguïté>
- BR-N: <règle métier sans ambiguïté>

## Acceptance Criteria
- AC-1: <condition observable, testable>
- AC-N: <condition observable, testable>

## Required Stack (v7.0.0-alpha Sprint 1.3 — anti-stack-drift)
<Déclare les stacks attendus par cette FEAT. /feat-validate vérifie que
`workspace/input/stack/stack.md` a activé exactement ces stacks (les commentés
sont rejetés). Évite que l'opérateur lance /sdd-full {n} avec un stack.md
configuré pour une autre FEAT (cas typique : bench multi-stack).

Format : valeurs slash-style `category/id` correspondant aux fichiers
`.claude/stacks/{category}/{id}.md`. Catégories valides : backend, frontend,
fullstack, ui, qa, auth, archi, mobiles. Écrire `none` si la FEAT n'exige
rien de cette catégorie (ex. front-only sans backend dédié).>
- backend: <ex. kotlin-spring-boot, ou none>
- frontend: <ex. vue, ou none>
- ui: <ex. vuetify, ou none>
- qa: <ex. kotlin-junit, node-vitest, ou none>
- auth: <ex. auth-local, azure-ad, ou none>

## Dependencies
- <FEAT-id ou NONE>

## Functional Deliverables
- FD-1: <écran, comportement, livrable observable>
- FD-N: <écran, comportement, livrable observable>

## Out of Scope
- <ce qui est explicitement exclu>
