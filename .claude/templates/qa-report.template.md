# QA Report — FEAT {n}-{Name}

- **Date** : {YYYY-MM-DD HH:mm}
- **Décision globale** : {🟢 GREEN | 🟡 YELLOW | 🔴 RED}
- **Mode** : {full | tests-only | tests+coverage | quality-only}

---

## Résumé exécutif

| Métrique | Valeur | Seuil | Statut |
|---|---|---|---|
| Tests passants | {passed}/{total} | — | {pass\|fail} |
| Coverage global | {pct}% | {CoverageMin}% | {pass\|warn} |
| Quality errors | {N} | 0 | {pass\|warn} |
| Quality warnings | {N} | — | info |
| Linter warnings | {N} | — | info |

---

## 1. Tests unitaires

### 1.1 Par stack QA actif

| Stack | Tests | Passants | Échecs | Skipped |
|---|---|---|---|---|
| {qa-stack-id} | {total} | {passed} | {failed} | {skipped} |

### 1.2 Par US

| US | Tests générés | Statut |
|---|---|---|
| {n}-1-{Name} | {N} | {GREEN\|RED} |
| {n}-2-{Name} | {N} | {GREEN\|RED} |

### 1.3 Échecs détaillés (si présents)

```
[stack qa-dotnet-xunit] AuthServiceTests.cs:84
  Test: TestRefreshToken_WithExpiredToken_Returns401
  Expected: 401
  Actual:   200
  Stack trace (3 lignes max) :
    at AuthService.RefreshToken() in AuthService.cs:42
    at AuthServiceTests.TestRefreshToken_WithExpiredToken_Returns401 in AuthServiceTests.cs:84
```

---

## 2. Coverage

### 2.1 Global

- **Lignes couvertes** : {covered}/{total} ({pct}%)
- **Seuil** : {CoverageMin}%
- **Verdict** : {🟢 OK | 🟡 GAP}

### 2.2 Par stack

| Stack | Lines % | Branches % | Files mesurés |
|---|---|---|---|
| {stack-id} | {pct}% | {pct}% | {N} |

### 2.3 Top 5 fichiers à plus faible couverture

| Fichier | Lignes % |
|---|---|
| {path} | {pct}% |

---

## 3. Quality scan (sonar-like)

> Détection déterministe via `quality_scan.py`. 0 token consommé.

### 3.1 Résumé par catégorie

| Catégorie | Errors | Warnings | Info |
|---|---|---|---|
| TODO / FIXME / XXX / HACK | {N} | — | — |
| Debug output (console.log, print, etc.) | — | {N} | — |
| Hardcoded hex (hors theme.css) | — | {N} | — |
| Méthodes > 50 lignes | — | {N} | — |
| Code commenté en bloc | — | — | {N} |
| Magic numbers | — | — | {N} |

### 3.2 Top 5 errors (TODO/FIXME)

| Fichier | Ligne | Tag | Message |
|---|---|---|---|
| {path} | {line} | TODO | {message} |

### 3.3 Top 5 warnings

| Fichier | Ligne | Catégorie | Message |
|---|---|---|---|
| {path} | {line} | {category} | {message} |

---

## 4. Linter / Type checker

| Stack | Outil | Warnings | Statut |
|---|---|---|---|
| {stack-id} | {tool} | {N} | {pass\|warn} |

### 4.1 Top 3 warnings linter

```
{file}:{line} : {message}
```

---

## 5. Recommandations (non auto-appliquées)

> L'agent QA NE MODIFIE PAS le code de production. Ces recommandations
> sont à arbitrer par le Tech Lead, qui peut les transformer en :
> - Nouvelle FEAT / US (corrections fonctionnelles)
> - Re-dispatch via `/dev-run {n}` (corrections de bug)
> - Ajout d'AC (couverture insuffisante)

### 5.1 Pour atteindre {CoverageMin}% de coverage

- Ajouter tests dans `workspace/output/src/{Project}/...` ciblant `{symbol}`
- {recommandation 2}

### 5.2 Pour résoudre les errors quality

- {file:line} : {action concrète}

### 5.3 Pour résoudre les test failures

- Vérifier `{file}` ligne {line} : {observation}

---

## 6. Fichiers générés

- `workspace/output/qa/feat-{n}/coverage.json` (schéma normalisé)
- `workspace/output/qa/feat-{n}/quality.json` (sonar-like résultats)
- `workspace/output/qa/feat-{n}/report.md` (ce fichier)
