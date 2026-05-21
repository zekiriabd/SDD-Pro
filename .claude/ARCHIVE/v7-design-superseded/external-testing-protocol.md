# SDD_Pro — Protocole de test externe (anti mono-utilisateur)

> Résout la critique audit v7.0.0-alpha §4.4 :
> *« Le framework optimise pour son auteur, ce qui produit d'excellentes décisions techniques mais des angles morts UX. »*
>
> Objectif : faire passer le framework du statut « optimisé pour son auteur »
> à « utilisable par un tiers sans aide synchrone ». Mesurer l'écart, prioriser
> les fixes.

---

## 1. Pourquoi ce protocole

Le framework SDD_Pro a été conçu et utilisé par **un seul développeur**
(retour audit : `git log` 1 contributeur principal, 0 issue externe
documentée). Les conséquences mesurables :

- **Vocabulaire dense** : FEAT, US, AC, SFD, FD, BR, ADR, AC-UI, plan v1/v2,
  AppType, capabilities, on-demand, gated workflow, build_loop,
  spec-compliance, etc. — courbe d'apprentissage non chiffrée
- **Configuration distribuée** : 11 calques de précédence (cf.
  `docs/config-precedence.md`) — onboarding ≈ 1 semaine
- **17 commandes** (8 user + 9 internes) — discoverability faible
- **Hypothèses tacites** : conventions stack-specific, post-mortems internalisés,
  workflow Tech Lead non explicité

**Sans validation externe**, ces angles morts restent invisibles à l'auteur.

---

## 2. Profil des testeurs

### 2.1 Critères de sélection (2 testeurs)

| Critère | Testeur A | Testeur B |
|---|---|---|
| Séniorité dev | Senior (5+ ans) | Mid (2-4 ans) |
| Familiarité Claude Code | Connue | Première fois |
| Stack natif | .NET ou Kotlin | React |
| Connaissance SDD_Pro | Aucune | Aucune |
| Domaine métier | Software product | Indifférent |
| Disponibilité | 2-3 jours plein-temps | 2-3 jours plein-temps |

**Pourquoi 2 profils différents** : capturer à la fois les frictions
expert (« je connais le domaine mais pas l'outil ») et débutant
(« je ne connais rien »). Recouvre ~80 % du persona cible.

### 2.2 Indépendance

Critères stricts :
- **Pas de relation hiérarchique** avec l'auteur (collègue OK, manager NON)
- **Pas d'aide synchrone** pendant la session (Slack/téléphone OK uniquement
  pour débloquer un cas de crash, jamais pour interpréter un comportement)
- **Pas d'accès à la conversation Claude Code de l'auteur**
- **Documentation seule** comme support (CLAUDE.md, docs/, README)

---

## 3. Scénarios de test

### 3.1 Scénario S1 — Onboarding froid (½ jour)

**Cible** : tester l'entry point CLAUDE.md + quickstart.

**Tâche** : « Lis CLAUDE.md et installe SDD_Pro pour générer ta première FEAT.
Aucune aide externe. Note tout ce qui te bloque ≥ 3 min. »

**Métriques** :
- Temps total (≤ 4 h cible)
- Nombre de fois où le testeur ouvre une 2ème doc (`@docs/...`)
- Nombre d'incompréhensions terminologiques (FEAT vs US vs AC, etc.)
- Commandes essayées sans succès
- Configuration touchée (combien de fichiers stack.md, config.base.yml, settings.json)

**Livrable testeur** : journal chronologique en Markdown,
`docs/external-testing/{testeur}/s1-onboarding.md`.

### 3.2 Scénario S2 — FEAT triviale (1 jour)

**Cible** : exécuter `/sdd-full` sur une FEAT CRUD simple (référence `bench-s`).

**Tâche** : « Génère une FEAT 'Gérer un catalogue produit' (CRUD `Product`).
Suis le quickstart. Exécute `/sdd-full 1`. Documente chaque étape, chaque
choix, chaque erreur. Cible : code fonctionnel + tests verts. »

**Métriques** :
- Wall-clock (réel, avec interruptions notées)
- Nombre de retries Tech Lead (correction manuelle, re-prompts à Claude)
- Décisions non documentées rencontrées (ex. « `MaxParallel`, je le mets à combien ? »)
- Erreurs `[CLASS]` rencontrées + temps de résolution
- Verdict final : pipeline réussi ? Code utilisable ?

**Livrable testeur** : `docs/external-testing/{testeur}/s2-feat-triviale.md`
avec inputs / outputs / verdict.

### 3.3 Scénario S3 — Bug intentionnel (½ jour)

**Cible** : capacité de diagnostic autonome.

**Tâche** : l'auteur injecte un bug subtil dans `stack.md` (ex.
`CoverageMin: 95` avec test setup faible). Le testeur exécute
`/sdd-full 2` (FEAT préparée à l'avance), observe le 🔴 RED
`[QA_COVERAGE_GAP]`, et doit :
1. Identifier la cause-racine sans aide
2. Choisir entre fix code ou fix config (décision tracée)
3. Relancer le pipeline jusqu'à 🟢

**Métriques** :
- Temps de diagnostic (≤ 30 min cible)
- Documents consultés (`error-classification.md`, `quality.md`, autres)
- Recours à `/sdd-status`, `dump_effective_config`, etc.
- Bypass `--force` utilisé ? (mauvais signal — la doc devrait suffire)

**Livrable testeur** : `docs/external-testing/{testeur}/s3-diagnostic.md`.

### 3.4 Scénario S4 — Modification de stack (½ jour, testeur A senior uniquement)

**Cible** : extensibilité.

**Tâche** : « Ajoute une nouvelle lib `RestSharp` au stack
`dotnet-minimalapi` pour le scenario 'appel API tierce' d'une US.
Suis la procédure `library-and-stack.md`. Mesure le temps total. »

**Métriques** :
- Procédure trouvée du premier coup ? (sinon nb de docs consultés)
- `.libs.json` édité correctement ? (validate_libs_catalog.py exit 0)
- `sync_stack_md.py` invoqué ?
- Compréhension du couplage `.md` ↔ `.libs.json` ?

**Livrable** : `docs/external-testing/{testeur}/s4-stack-extension.md`.

---

## 4. Métriques agrégées à mesurer

| Catégorie | Métrique | Méthode |
|---|---|---|
| **Temps onboarding** | Heures jusqu'au premier `/sdd-full` réussi | Journal chronologique |
| **Incompréhensions** | Nombre de termes/concepts non clairs sans recherche | Comptage explicite par le testeur |
| **Docs lues** | Nombre de fichiers `@.claude/docs/*.md` ouverts | Journal |
| **Commandes bloquantes** | Commandes essayées sans succès / abandonnées | Journal |
| **Friction config** | Nombre de fichiers de config touchés pour 1 décision | Comptage |
| **Erreurs récurrentes** | Classes `[CLASS]` rencontrées ≥ 2× | Logs framework |
| **Bypass forcés** | Recours à `--force`, `SDD_*` env vars | Audit log |
| **Verdict subjectif** | « Recommanderiez-vous SDD_Pro à un collègue ? » 0-10 | Sondage post-test |
| **Top 3 pain points** | Open question : 3 frictions majeures | Sondage post-test |

---

## 5. Format du livrable testeur

Chaque session produit un fichier dans
`docs/external-testing/{testeur-alias}/s{N}-{nom}.md` :

```markdown
# {Scénario} — {Testeur-alias}

## Méta
- Date : YYYY-MM-DD
- Durée totale : Xh
- Profil testeur : senior .NET / mid React / ...
- Pré-requis : SDD_Pro installé depuis tag v7.0.0-alphaX

## Journal chronologique
- HH:MM — action — observation
- HH:MM — bloqué — cause / résolution / temps perdu
- ...

## Métriques
- Wall-clock : Xh
- Docs consultées : N (liste)
- Commandes essayées : N (liste avec succès Y/N)
- `[CLASS]` rencontrées : ...
- Bypass utilisés : oui/non (préciser)

## Pain points (top 3)
1. ...
2. ...
3. ...

## Verdict
- Tâche complétée ? Y/N
- Recommandation 0-10 : N
- Suggestion #1 d'amélioration : ...
```

---

## 6. Synthèse post-test (auteur)

Après les 2 testeurs (~6 jours-homme cumulés), l'auteur consolide :

### 6.1 Document de synthèse

`docs/external-testing/synthesis-v7-{date}.md` :

```markdown
# Synthèse external testing v7.0.0 — {date}

## Testeurs
- Testeur A (senior .NET) — {N} jours
- Testeur B (mid React) — {N} jours

## Onboarding cold-time médian : Xh (cible ≤ 4h)

## Top 10 pain points consolidés
| # | Pain point | Fréquence | Sévérité | Fix proposé |
|---|---|:---:|:---:|---|
| 1 | ... | 2/2 | critical | ... |
| 2 | ... | 2/2 | serious | ... |
| ... | ... | ... | ... | ... |

## Décisions
- [ ] Fix P0 avant GA : ...
- [ ] Fix P1 post-GA : ...
- [ ] Roadmap v7.1+ : ...
```

### 6.2 Critères d'acceptation v7.0.0 GA (testing external)

| Critère | Cible | Mesure |
|---|---|---|
| Cold onboarding | ≤ 4 h pour S1 sur médiane 2 testeurs | journaux |
| FEAT triviale réussie | 2/2 testeurs achèvent S2 sans `--force` | livrables |
| Diagnostic autonome | 2/2 testeurs résolvent S3 sans aide externe | livrables |
| Pain points critical | ≤ 3 critical mentionnés par 2/2 testeurs | synthèse |
| Recommandation moyenne | ≥ 6/10 | sondage |

**Si ≥ 1 critère 🔴** : fixes P0 obligatoires avant tag GA.

---

## 7. Coût estimé

| Poste | Effort |
|---|---|
| Préparation matériel (3 FEATs templates + bug S3 + injection) | 2-3 j auteur |
| Recrutement 2 testeurs (réseau pro) | 1-2 j |
| Sessions testeurs (S1+S2+S3 = 2-3 j × 2 testeurs) | 4-6 j testeur |
| Synthèse + priorisation | 1-2 j auteur |
| Fixes P0 post-synthèse | 2-5 j auteur (variable) |
| **Total séquentiel** | **10-18 jours-homme** |
| **Total auteur uniquement** | **5-12 jours** |

**Modèle rémunération testeurs** : à la prestation (300-600 €/jour selon
séniorité), 2-3 j × 2 = 1200-3600 €. Acceptable pour un produit qui vise
GA crédible.

---

## 8. Anti-patterns à éviter

| ❌ Ne PAS faire | ✅ Faire |
|---|---|
| Briefer les testeurs sur le vocabulaire | Laisser les frictions remonter naturellement |
| Tester sur des collègues directs (biais) | Recruter via réseau pro élargi |
| Tester par texte/chat asynchrone uniquement | Demander journal chronologique synchrone |
| Réécrire les pain points pour les rendre plus « techniquement précis » | Préserver le wording brut du testeur (signal UX) |
| Sauter à l'implémentation des fixes sans prioriser | Synthétiser d'abord, prioriser ensuite |
| Considérer un échec testeur comme un « testeur incompétent » | C'est toujours un signal framework |
| Annoncer GA avant validation 2/2 critères §6.2 | Tag uniquement après preuve |

---

## 9. Articulation avec les autres protocoles

| Protocole | Quand l'exécuter | Output |
|---|---|---|
| **Bench ROI** (`docs/benchmarks/README.md`) | En parallèle de external-testing | `roi-baseline.md` rempli |
| **External testing** (ce doc) | Après bench (sinon testeurs sans baseline) | `docs/external-testing/synthesis-v7-{date}.md` |
| **Scope reduction** (`scope-reduction-v7-ga.md`) | Avant external-testing (testeurs sur scope C1/C2 uniquement) | ADR `governance-scope-reduction-v7-ga` |

**Séquence recommandée pré-GA** :

```
1. ADR scope-reduction (1 j)
   ↓
2. Exécution bench ROI (5-6 j) — bench-s/m/l × dotnet+kotlin
   ↓
3. Recrutement testeurs (1-2 j)
   ↓
4. Sessions external testing (parallèle 2-3 j calendrier)
   ↓
5. Synthèse + fixes P0 (3-5 j)
   ↓
6. Tag v7.0.0 GA
```

**Total chemin critique** : 12-17 jours calendrier.

---

## 10. Pointers

- `@.claude/docs/AUDIT-FRAMEWORK-v7.md §4.4` — diagnostic mono-utilisateur
- `@.claude/docs/benchmarks/README.md` — protocole ROI parallèle
- `@.claude/docs/scope-reduction-v7-ga.md` — réduction périmètre prérequise
- `@.claude/docs/config-precedence.md` — référence onboarding diagnostic
- `@.claude/docs/quickstart.md` — point d'entrée testeur S1
- `@.claude/CLAUDE.md` — entry point testeur S1
- Templates testeurs (à créer post-validation protocole) :
  `templates/external-test-journal.template.md`

---

*Document protocole. Exécution conditionnée à validation budget testeurs externes (~1500-3600 €) + freeze partiel (3 semaines calendrier).*
