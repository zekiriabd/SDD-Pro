# PO Guide — Rédiger une bonne FEAT pour SDD_Pro

> Audience : Product Owners externes (équipes adoptant SDD_Pro sans
> accompagnement Softwe3). Cible : passer de zéro à une FEAT validée par
> `/feat-validate` GO en < 30 minutes.

---

## 1. Pourquoi la FEAT est centrale

`workspace/input/feats/{n}-{Name}.md` est l'**unique** artefact que l'humain
doit rédiger pour piloter le pipeline. Les User Stories, le code, les tests,
les ADRs en découlent automatiquement. Si la FEAT est ambiguë, le code
généré le sera aussi (garbage in → garbage out — pas de magie LLM).

**Règle mentale** : une FEAT bien rédigée doit pouvoir être lue par un
nouvel arrivant et lui permettre de comprendre **quoi livrer**, **pour qui**,
**et comment vérifier que c'est livré** — sans poser de question.

---

## 2. Anatomie d'une FEAT (12 sections)

Voir template canonique : `.claude/templates/feat.template.md`. Sections
obligatoires (extraites du template) :

| Section | Rôle | IDs stables | Min |
|---|---|---|---|
| `## Context` | Pourquoi cette FEAT existe (problème métier) | — | 1 paragraphe |
| `## Actors` | Personae impliqués (utilisateur final, admin, système) | — | 1 |
| `## Functional Needs` | Besoins métier exprimés narrativement | `SFD-N` | 1 |
| `## Functional Deliverables` | Livrables concrets (UI screen, API endpoint, batch) | `FD-N` | 1 |
| `## Business Rules` | Contraintes métier non-négociables | `BR-N` | 0 |
| `## Acceptance Criteria` | Conditions observables Given/When/Then | `AC-N` | 1 |
| `## Data Model` | Entités + champs (input léger pour arch) | — | optional |
| `## Out of Scope` | Ce qui N'est PAS dans la FEAT (anti-derive) | — | optional |

**IDs stables (CRITIQUE)** : `SFD-1`, `BR-1`, `AC-1`, etc. — **jamais
renuméroter** après génération US (les `Covers:` y réfèrent par valeur).
Ajout = `+1` à la fin de la liste. Retrait = supprimer ligne + régénérer
les US (`/us-generate {n}`).

---

## 3. Acceptance Criteria — la partie qui mérite 80% du temps

L'AC est ce qu'un agent QA va matérialiser en test exécutable. Format
strict :

```markdown
- AC-1: Given <état initial>, when <action utilisateur ou système>,
        then <résultat observable mesurable>.
```

**Bonnes ACs (verifiables)** :
- `AC-1: Given un user non connecté, when il POST /api/login avec
   credentials valides, then la réponse est 200 avec un JWT en body et
   un cookie HTTP-only Set-Cookie.`
- `AC-2: Given le formulaire de réservation, when l'utilisateur clique
   "Confirmer" sans avoir rempli email, then un message rouge apparaît
   sous le champ email et le bouton reste désactivé.`

**Mauvaises ACs (à reformuler)** :
- ❌ `AC-1: Le système doit être rapide.` → comment mesurer ?
- ❌ `AC-2: L'interface est intuitive.` → subjectif, non testable.
- ❌ `AC-3: La sécurité est bonne.` → trop large, décomposer.
- ❌ `AC-4: Le user peut se connecter.` → manque Given/When/Then.

**Règle anti-derive** : si une AC ne peut pas être traduite en `assert`
sans imagination du dev, elle est mal formulée. `/feat-validate` flag les
ACs sans Given/When/Then en `[READINESS_AC_INCOMPLETE]`.

---

## 4. Process recommandé (greenfield)

### Étape 1 — Brouillon papier (5 min)
1. Une phrase pour `## Context` (ce que résout cette FEAT)
2. Liste des `## Actors` impliqués
3. 3-7 `AC-N` au format Given/When/Then (le reste découle)

### Étape 2 — `/feat-generate {Nom}` (3-6 questions, 10 min)
La commande pose des questions ciblées (`AskUserQuestion`) pour combler
les sections manquantes (`## Functional Deliverables`, `## Business Rules`).
Réponses courtes — éviter les essais de 3 paragraphes.

### Étape 3 — `/feat-validate {n}` (déterministe, 0-token)
Vérifie :
- IDs stables présents (`SFD-N`, `BR-N`, `AC-N`)
- ACs au format Given/When/Then
- Stacks actifs détectés dans `workspace/input/stack/stack.md`
- Mockups HTML matchant les US (si présents)
- Couverture AC ≥ 80% (chaque AC mappée à ≥ 1 US potentiel)

Exit `GO` → vous pouvez lancer `/sdd-full {n}` les yeux fermés.

Exit `WARN` ou `NO-GO` → corriger les findings listés (file:line précis).

### Étape 4 — `/sdd-full {n}` (pipeline complet)
Pipeline automatique : US → arch → backend → API gate → frontend → QA →
5 reviewers. Durée typique 15-45 min selon taille FEAT (M/L/XL). À la fin,
verdict consolidé 🟢/🟡/🔴.

---

## 5. Granularité — combien d'US par FEAT ?

Configuration `## Project Config` (stack.md) :
```yaml
UsGranularityCible:  3         # cible : 1-3 US par FEAT
UsGranularityWarnAt: 6         # > 6 → WARNING (non bloquant)
UsGranularityHardCap: 10       # > 10 → STOP sauf --allow-large-feat
```

**Indicateurs FEAT trop grosse** :
- > 7 ACs distinctes
- 2+ acteurs avec workflows complètement disjoints
- Mention de "et puis" / "et aussi" / "ensuite" qui chaîne 3+ besoins
- Modélisation de 5+ entités

→ Découper en 2-3 FEATs distinctes avec dépendances déclarées (référence
inter-FEAT dans `## Context`).

**Indicateurs FEAT trop petite** :
- 1 seul AC, < 100 mots
- Pas de business rule, pas de delivrable concret

→ Souvent une refacto ou un bug fix — utilisez plutôt un commit direct,
SDD_Pro est conçu pour les **features**.

---

## 6. Données et mockups (optionnel mais recommandé)

### `## Data Model` (input léger arch)
```markdown
## Data Model
- User { id (UUID), email (unique, lowercase), passwordHash, createdAt }
- Session { id, userId (FK), expiresAt, refreshToken }
```

L'agent `arch` lit cette section pour scaffolder le schéma DB. Pas besoin
de SQL — l'arch convertit selon le DatabaseType (`postgres` / `sqlite` /
`sqlserver`) déclaré dans `stack.md`.

### Mockups HTML (`workspace/input/ui/{n}-{m}-{Name}.html`)
Pour les FEATs avec UI, un mockup HTML statique (Tailwind autorisé)
**accélère la convergence** du frontend généré. Convention :
- Basename strict : `{n}-{m}-{Name}.html` (matchant la future US)
- Pas de JS — uniquement structure + styles
- Couleurs hex acceptées (l'agent dev-frontend les convertit en tokens CSS)

Exemples : voir [docs/ux-designer-guide.md](ux-designer-guide.md) §3.

---

## 7. Élicitation avancée — `/feat-deepen {n}`

Pour les FEATs critiques (auth, paiement, données sensibles), invoquer :
```
/feat-deepen {n}
```

L'agent `elicitor` applique 5 techniques :
- **Pre-mortem** : "imagine que la livraison a échoué — pourquoi ?"
- **First Principles** : "quel est le besoin métier *vraiment* sous-jacent ?"
- **Red Team** : "comment un attaquant abuserait de cette feature ?"
- **Stakeholder Mapping** : "qui est impacté hors des Actors listés ?"
- **Inversion** : "quel anti-objectif évite-t-on ?"

Sortie : 5 sections enrichies ajoutées en fin de FEAT (`## Risks`,
`## Edge Cases`, `## Red Team`, `## Hidden Stakeholders`, `## Anti-Goals`).
Cycle moyen : 15-20 min.

---

## 8. Anti-patterns rejetés

| Anti-pattern | Pourquoi rejeté | Remplacer par |
|---|---|---|
| FEAT qui décrit l'implémentation ("utiliser Redis pour le cache") | C'est de l'archi, pas du fonctionnel | Décrire le besoin de perf en AC mesurable |
| AC qui référence un screenshot externe ("voir Figma") | Non traçable post-livraison | Inliner le mockup HTML |
| Réorganisation `## Functional Needs` après génération US | Casse les `Covers:` | Append-only sur ces sections |
| FEAT qui réfère "voir ticket Jira INGEST-1234" | Pas d'accès agent | Inliner le contenu nécessaire |
| Acceptance Criteria avec "etc.", "..." | Non exhaustif | Lister explicitement |

---

## 9. Checklist avant `/sdd-full`

- [ ] Tous les IDs stables présents (`SFD-N`, `BR-N`, `AC-N`)
- [ ] Chaque AC au format Given/When/Then complet
- [ ] `## Actors` ≥ 1 acteur nommé
- [ ] `## Functional Deliverables` liste les artefacts concrets (UI/API)
- [ ] `## Out of Scope` exclut explicitement les sujets connexes hors périmètre
- [ ] `/feat-validate {n}` retourne GO (ou WARN consciemment accepté)
- [ ] Si UI complexe : mockup HTML `workspace/input/ui/{n}-{m}-*.html` présent
- [ ] Si FEAT sensible : `/feat-deepen {n}` exécuté + sections enrichies revues

---

## 10. Exemples de FEATs validées

Voir le repo bench : `workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md`
référence 14 FEATs réelles passées en pipeline `/sdd-full` complet
(stacks variés : React+.NET, Vue+Spring, Angular+FastAPI, etc.).

Pour chaque combo bench, le diff `workspace/input/feats/{n}-{Name}.md`
montre une FEAT canonique de 80-200 lignes, lisible en < 5 minutes.

---

## 11. Support

- **Onboarding** : `@docs/getting-started.md` + ce guide
- **Glossaire** : `@docs/glossary.md` (acronymes SDD_Pro)
- **Troubleshooting** : `@docs/troubleshooting.md` (40+ erreurs classées)
- **UX/Designer companion** : `@docs/ux-designer-guide.md`
- **Issues** : https://github.com/anthropics/claude-code/issues (framework
  Claude Code) — SDD_Pro est un projet privé Softwe3
