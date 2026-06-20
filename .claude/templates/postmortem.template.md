# Post-Mortem — {IncidentTitle}

> Blameless post-mortem. Focus sur les **gaps systèmes**, pas sur les **personnes**.
> Délai obligatoire : **48h max après résolution** (cf. `source-first.md §5`).
> Source : SDD_Pro `.claude/templates/postmortem.template.md`

**Incident date** : {YYYY-MM-DD}
**Severity** : SEV{1|2|3|4}
**Duration** : {HH:MM} (du {start ISO} au {end ISO} UTC)
**Author** : {Tech Lead}
**Reviewers** : {liste}

---

## 1. Summary (5 lignes max, executive)

{1 paragraphe : ce qui s'est passé, l'impact, comment c'est résolu}

## 2. Impact

| Métrique | Valeur |
|---|---|
| Users affectés | {X} sur {Y total} ({Z%}) |
| Requests failed | {N} |
| Data loss | {none | partial : ...} |
| Revenue impact | {estimé ou N/A} |
| External communication | {oui — status page link | non} |

## 3. Timeline (UTC, chronologique)

| Time | Event |
|---|---|
| {HH:MM} | Déploiement v{X.Y.Z} sur prod |
| {HH:MM} | 1ère alerte PagerDuty (`API p95 > 5s`) |
| {HH:MM} | On-call ack, investigation démarrée |
| {HH:MM} | Cause racine identifiée : {brief} |
| {HH:MM} | Mitigation appliquée : {action} |
| {HH:MM} | Service revenu à la normale (monitor 🟢) |
| {HH:MM} | Communication finale status page |

## 4. Root cause (5 Whys)

**Symptôme observé** : {description observable, ex. "API endpoints /bebes ont retourné 500 pendant 18 min"}

1. **Why ?** {cause directe, ex. "Le pool de connexions DB est devenu saturé"}
2. **Why ?** {cause intermédiaire 1, ex. "Une nouvelle endpoint introduit en v3.4.0 ne libère pas sa connexion en cas d'exception"}
3. **Why ?** {cause intermédiaire 2, ex. "Le `using` C# est absent autour du `DbContext`"}
4. **Why ?** {cause racine 1, ex. "Le code-reviewer SDD_Pro v6.3.1 n'a pas catch ce pattern car la classe `[REVIEW_DB_NO_USING]` n'existe pas dans error-classification.md §1.10"}
5. **Why ?** {cause racine 2, ex. "L'anti-pattern n'a pas été vu en post-mortem précédent → pas patché dans `code-reviewer.md §5.1`"}

## 5. Source-first analysis (discipline SDD_Pro)

Quelle source MD aurait dû prévenir cet incident ?

- [ ] FEAT fonctionnelle : {AC manquante à ajouter ?}
- [ ] User Story : {AC technique manquante ?}
- [ ] Plan technique : {fichier oublié dans `## Files` ?}
- [ ] Stack MD : {pattern à ajouter dans `§X.Y.Z` ?}
- [ ] Agent MD : {checkpoint à ajouter dans `code-reviewer §5.1` ?}
- [ ] Rule MD : {anti-pattern à formaliser ?}

**Patch source obligatoire** (cf. `source-first.md §1`) :
- Fichier : {path}
- Section : {§X.Y.Z}
- Contenu du patch : (citer le diff)

## 6. What went well

- {ex. "L'alerte PagerDuty a déclenché en < 2min après la dégradation"}
- {ex. "On-call était disponible et a ack en < 5min"}

## 7. What went wrong

- {ex. "Aucun staging environment — bug détecté uniquement en prod"}
- {ex. "Le runbook §3.2 n'avait pas de procédure pour pool DB saturé"}

## 8. Where we got lucky

- {ex. "L'incident est arrivé un dimanche matin → faible trafic"}
- {ex. "Le client X n'a pas appelé pendant l'incident"}

## 9. Action items

| # | Action | Owner | Due date | Status | Severity |
|---|---|---|---|---|---|
| 1 | Patcher `code-reviewer.md §5.1` avec `[REVIEW_DB_NO_USING]` | {Tech Lead} | {ISO + 48h} | open | P1 |
| 2 | Ajouter monitor `db.pool.connections.active` Grafana | {DevOps} | {ISO + 1 week} | open | P2 |
| 3 | Mettre à jour runbook §3.3 (DB pool exhausted) | {Tech Lead} | {ISO + 1 week} | open | P2 |
| 4 | Ajouter test d'intégration pool DB sous charge | {QA} | {ISO + 2 weeks} | open | P3 |

**Critique** : les items P1 doivent être **fermés sous 48h**. Sinon le bug
reviendra dans le prochain projet généré (cf. `source-first.md §4`).

## 10. Lessons learned (à propager)

- {ex. "Toute endpoint async qui ouvre une connexion DB doit utiliser `using` (C#) / `with` (Python) / `try-with-resources` (Kotlin)"}
- {ex. "Le code-reviewer SDD_Pro doit catch ce pattern systématiquement"}

---

> **Blameless** : ce post-mortem ne nomme aucune personne en tant que
> cause. Si un humain a fait une erreur, la question est "comment le
> système a-t-il permis cette erreur ?", pas "qui a fait l'erreur ?".
