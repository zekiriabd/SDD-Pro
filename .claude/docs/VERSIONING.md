# SDD_Pro — Versioning Policy (SemVer strict + Freeze window)

> **SSoT** (audit mineur #6 v7.0.0-alpha 2026-06-05) : ce fichier est la
> **source unique** pour la politique de versioning et les fenêtres freeze.
> `CHANGELOG.md` (entrées par release) et `MIGRATION.md` (procédures upgrade)
> **consomment** les décisions tracées ici. En cas de divergence : VERSIONING.md
> fait foi. Bump de version → mettre à jour VERSIONING.md puis CHANGELOG +
> MIGRATION.

> **Statut au 2026-06-07** : v7.0.0 **GA tagué** post-audit CTO. v6.10.4
> conservée comme **LTS** pour projets legacy (support sécurité jusqu'au
> 2026-12-31). La branche `main` accepte désormais les bumps MINOR et PATCH
> v7.x. Toute proposition MAJOR (v8.x) reste sur la branche `next`.

---

## 0. Registre des versions (audit 2026-06-11 — SSoT anti-labels fantômes)

| Version | Date | Statut |
|---|---|---|
| v6.10.4 | 2026-05-17 | **LTS** (sécurité jusqu'au 2026-12-31) |
| v7.0.0 | GA taguée **2026-06-07** (publication industrielle 2026-05-23) | **GA** — inclut R1 adversarial-reviewer + R7 ingest CI (livrés 2026-05-24 pré-GA, anciennement mal étiquetés « v7.2.0 ») |
| v7.0.1-dev | 2026-06-05 → courant | ligne de dev active (audits post-GA) — sera taguée v7.0.1 PATCH ou v7.1.0 MINOR |
| reverse-v0.x-dev | 2026-06-09 → courant | module reverse (versionné séparément, pré-intégration) |

**Règle (audit 2026-06-11 M9)** : aucun label `vX.Y` ne doit apparaître dans
une rule/doc/agent **sans entrée correspondante dans ce registre + CHANGELOG**.
Les drafts de features futures référencent la roadmap (`roadmap-v7-v8.md`),
jamais un numéro de version inventé. Le drift « v7.2.0 livrée 2026-05-24 »
(antérieure à la GA !) est exactement ce que cette règle empêche.

---

## 1. Constat motivant cette politique

Entre **2026-05-06 (v6.0.0)** et **2026-05-17 (v6.9.0)**, 17 bumps de
version ont été tagués en 11 jours — dont au moins 2 BREAKING majeurs
(v6.8 US schema v2, v6.10 console DB centralisée). Le drift CHANGELOG.md
(s'arrête à v6.9.0) ↔ CLAUDE.md (référence v6.10.0 → v6.10.4) confirme
que la cadence dépasse la capacité documentaire et la confiance utilisateur.

**Aucune équipe consommatrice ne peut adopter un framework qui change
de structure tous les 2 jours.** Cette politique gèle cette dérive.

---

## 2. Version LTS désignée (HISTORIQUE — fenêtre de freeze pré-GA close)

> **Statut au 2026-06-07** : la fenêtre de freeze décrite ci-dessous était
> une mesure pré-GA. **Elle est close** : v7.0.0 GA a été tagué le 2026-06-07,
> la branche `main` accepte désormais les bumps **MINOR + PATCH v7.x**
> (cf. bannière haute + §3.2). Les sections §2 et §4 sont conservées comme
> trace historique de la discipline qui a mené à la GA — elles ne décrivent
> plus la politique active.

| Champ | Valeur |
|---|---|
| Version LTS | **v6.10.4** |
| Date de désignation | 2026-05-19 |
| Tag git réel | `SDD_Prov6_10_5` (tag existant sur la baseline LTS — le tag `v6.10.4-LTS` initialement *attendu* n'a jamais été créé ; correction audit 2026-06-12) |
| Branche stable | `main` (v7.0.0 GA — freeze clos depuis le 2026-06-07) |
| Branche expérimentale | `next` (dev post-GA, audits) |
| Fin de freeze | **close (2026-06-07)** — v7.0.0 GA tagué `v7.0.0` |

**Note tag (audit 2026-06-12)** : la baseline LTS v6.10.x est tagguée
`SDD_Prov6_10_5` dans git (convention de nommage historique). Le tag
`v6.10.4-LTS` n'a jamais été matérialisé — toute référence contractuelle
(SLA.md) pointe désormais vers le tag réel `SDD_Prov6_10_5`. La GA v7.0.0
porte le tag `v7.0.0`.

---

## 3. Règles SemVer strictes (MAJOR.MINOR.PATCH)

### 3.1 MAJOR — changement incompatible

Bump MAJOR **obligatoire** si l'une de ces conditions est vraie :

- Suppression ou renommage d'un slash command listé dans CLAUDE.md §3
- Suppression ou renommage d'un agent (`.claude/agents/*.md`)
- Modification du schéma `stack.md` rendant invalides les `stack.md`
  pré-existants (clé obligatoire ajoutée sans défaut, valeur enum retirée)
- Modification du schéma `coverage.json`, `console.db` ou des artefacts
  consommés par des scripts externes (CI, BI, MCP)
- Changement du flux pipeline `/sdd-full` invalidant les `--resume` checkpoint
- Suppression ou renommage d'une règle `.claude/rules/*.md` référencée par
  un agent ou par `error-classification.md`
- Suppression d'une classe d'erreur `[*]` listée dans `error-classification.md`

**Procédure** : RFC ADR `governance-major-{slug}` validée par 2 mainteneurs
+ section dédiée dans CHANGELOG sous header `### Breaking` + entrée
`@.claude/docs/MIGRATION.md` avec script ou recette de migration.

### 3.2 MINOR — ajout rétrocompatible

Bump MINOR **autorisé** si :

- Nouvelle slash command, nouvel agent, nouvelle règle, nouveau script
  Python sous `sdd_scripts/`
- Nouvelle clé optionnelle dans `## Project Config` (avec défaut documenté)
- Nouvelle classe d'erreur dans `error-classification.md`
- Nouveau stack dans `.claude/stacks/{cat}/`
- Nouvelle capability on-demand dans un `.libs.json` existant
- Nouvelle table dans `console.db` sans modifier les existantes

**Procédure** : ADR `governance-minor-{slug}` + entrée CHANGELOG dédiée.
**Interdit pendant la fenêtre de freeze** (cf. §4).

### 3.3 PATCH — correctif sans effet de bord

Bump PATCH **autorisé même pendant le freeze** si :

- Typo, reformulation, lien cassé dans un `.md`
- Fix bug d'un script Python sans changer sa signature CLI ni son schéma
  de sortie
- Mise à jour de version d'une lib dans un `.libs.json` sans changer
  `installCommand` ni introduire de breaking change amont (CVE patch,
  point release)
- Régénération d'un dashboard, INDEX.md ADRs, ou autre sortie déterministe
- Correction d'un message d'erreur sans changer son préfixe `[CLASS]`
- Hotfix de sécurité validé par un mainteneur

**Interdit même en PATCH** : ajout/suppression de fichier MD agent/règle/
command/stack, modification d'une signature CLI, changement de défaut
documenté.

---

## 4. Fenêtre de freeze 2026-05-19 → 2026-06-18 (HISTORIQUE — close, GA atteinte)

> **Close 2026-06-07** : la fenêtre de freeze pré-GA a rempli son objectif —
> v7.0.0 GA tagué post-audit CTO. Les règles ci-dessous ne s'appliquent plus
> sur `main` (qui accepte MINOR + PATCH v7.x, cf. §3.2 + bannière haute).
> Conservées comme trace historique de la discipline appliquée jusqu'à la GA.

### 4.1 Règles pendant la fenêtre (historique)

| Type de change | Branche `main` | Branche `next` |
|---|:---:|:---:|
| PATCH (§3.3) | ✅ autorisé | ✅ autorisé |
| MINOR (§3.2) | ❌ **interdit** | ✅ autorisé (merge différé) |
| MAJOR (§3.1) | ❌ **interdit** | ⚠️ autorisé (RFC ADR obligatoire) |
| Hotfix sécurité CVE ≥ high | ✅ autorisé (PATCH) | n/a |

### 4.2 Procédure de merge `next` → `main` post-freeze

À partir du **2026-06-19** :

1. Lister les commits accumulés sur `next` (`git log main..next --oneline`).
2. Regrouper en releases cohérentes (max 1 MINOR/semaine, max 1 MAJOR/mois).
3. Pour chaque release : ADR validé + CHANGELOG dédié + entry `MIGRATION.md`
   si MAJOR.
4. Annoncer 7 jours avant le merge dans un canal dédié (issue GitHub,
   discussion équipe).
5. Tag git annoté de la nouvelle version.

### 4.3 Tests d'acceptation du freeze

Le freeze tient si, au 2026-06-18, **tous** ces invariants sont vrais :
- Aucun bump MAJOR ni MINOR n'a été tagué sur `main` entre le 2026-05-19
  et le 2026-06-18.
- Aucun fichier supprimé sous `.claude/agents/`, `.claude/rules/`,
  `.claude/commands/`, `.claude/stacks/` sur `main` pendant la fenêtre.
- Aucune classe d'erreur retirée de `error-classification.md`.
- Aucune clé obligatoire ajoutée à `## Project Config`.
- CHANGELOG `main` ne contient que des entrées PATCH (X.Y.Z avec Z > 0).

Échec d'un invariant = freeze rompu → post-mortem 48 h obligatoire +
extension automatique de 30 jours supplémentaires.

---

## 5. Cadence cible post-freeze

À partir du **2026-06-19** :

| Type | Cadence max | Procédure |
|---|---|---|
| PATCH | illimité (qualité = humain) | commit direct sur `main` |
| MINOR | **1 par semaine** | ADR + 24h review window |
| MAJOR | **1 par mois** | RFC ADR + 7 jours d'annonce + entrée MIGRATION.md |

**Interdit définitivement** : > 2 bumps MINOR le même jour. > 1 bump
MAJOR la même semaine. Bump MINOR ou MAJOR sans ADR.

---

## 6. RFC ADR — gabarit minimal pour MINOR/MAJOR

Tout MINOR ou MAJOR exige un ADR sous
`workspace/.sys/.context/adrs/ADR-{YYYYMMDDTHHmmss}-governance-{minor|major}-{slug}.md`
contenant **au minimum** :

```markdown
# ADR — Governance {MINOR|MAJOR} — {Titre}

## Context
{1 paragraphe : pourquoi ce change, signal d'usage qui le motive}

## Decision
{1 paragraphe : ce qui change concrètement}

## Consequences
- **Breaking impact** : {oui/non, description, qui est concerné}
- **Migration path** : {pour MAJOR uniquement, recette ou lien MIGRATION.md}
- **Backward-compat window** : {durée pendant laquelle l'ancien comportement
  reste supporté, ou "aucune" si MAJOR avec break immédiat}

## Status
Proposed | Accepted | Superseded by ADR-XXX

## Reviewers
- @mainteneur1 (lead)
- @mainteneur2 (second)
```

Status `Accepted` exige 2 approbations distinctes. Pas de self-merge.

---

## 7. Audit post-mortem v6.0 → v6.10.4 (résumé)

Pour mémoire historique — **ne pas réécrire le CHANGELOG**, juste
documenter ce qui a déclenché cette politique.

| Cause racine | Effet observable |
|---|---|
| Pas de politique SemVer explicite | Bumps MINOR pour des features qui auraient dû être MAJOR (v6.8 schema US, v6.10 console.db) |
| Pas de cadence cible | 17 versions / 13 jours |
| Pas de freeze ni LTS | Aucune référence stable pour les consommateurs |
| Pas d'ADR `governance-*` obligatoire | Décisions structurelles non débattues, intégrées en commit unique |
| Drift CHANGELOG ↔ CLAUDE.md (v6.10 manquante du CHANGELOG) | Symptôme : la cadence dépasse la documentation |

---

## 8. Enforcement

- **Tech Lead humain** : applique manuellement les règles §3 et §4 lors
  des merges. Refuse tout PR MINOR/MAJOR sur `main` jusqu'au 2026-06-19.
- **CI (futur)** : un workflow GitHub doit valider que le tag git créé
  respecte le diff (PATCH = aucun fichier MD agent/règle/command/stack
  modifié ; MINOR = pas de suppression ; MAJOR = ADR `governance-major-*`
  présent dans le commit range).
- **Memory utilisateur** : entrée `feedback_versioning_freeze.md` créée
  pour rappeler la fenêtre active.

---

## 9. Communication aux consommateurs

À publier dans un canal dédié (issue épinglée GitHub, README, mail
équipe) avec le contenu suivant :

> **SDD_Pro v6.10.4-LTS — fenêtre de stabilité jusqu'au 2026-06-18**
>
> Suite à 17 versions en 13 jours dont 2 BREAKING majeurs, nous gelons
> SDD_Pro sur v6.10.4 jusqu'au 2026-06-18 inclus. Seuls les correctifs
> PATCH (typo, fix bug, CVE) seront publiés sur `main` pendant cette
> fenêtre. Toute nouvelle feature ou breaking change attendra le
> 2026-06-19 sur la branche `next`.
>
> Politique complète : `@.claude/docs/VERSIONING.md`.
> Prochaine release MINOR au plus tôt : 2026-06-19.
> Prochaine release MAJOR au plus tôt : 2026-07-19.

---

## 10. Pointeurs

- `@.claude/docs/CHANGELOG.md` — historique versions (à compléter rétroactivement pour combler le gap v6.9 → v6.10.4)
- `@.claude/docs/MIGRATION.md` — guide migration entre versions majeures
- `@.claude/rules/ownership.md` Partie B §4 — format ADR (la gouvernance MAJOR/MINOR adopte le même format ; fusionné depuis `constitution.md` au merge v7.0.0)
