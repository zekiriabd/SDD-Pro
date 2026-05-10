# QA Stack — Code Quality (Sonar-like cross-stack)

## 1. Scope

Stack **non-LLM** : règles d'analyse statique appliquées par le script
`.claude/scripts/quality-scan.ps1` sur le code de production de la
SPEC ciblée.

**0 token** consommé. Très rapide (< 1s pour ~5000 LOC).

S'applique cross-stack (.NET, Node, Python, Kotlin, Angular). Active dès
qu'au moins un autre QA stack est listé.

---

## 2. Activation

Dans `workspace/input/stack/stack.md` :

```markdown
## Active QA Specs
- .claude/stacks/qa/dotnet-xunit.md
- .claude/stacks/qa/code-quality.md      # active le scan sonar-like
```

Cette stack est **non-prescriptive sur le test runner** — elle complète
les autres QA stacks par un audit de qualité du code de production.

---

## 3. Catégories analysées

### 3.1 TODO / FIXME / XXX / HACK (errors)

Détecte les commentaires de dette technique :
- `// TODO: ...`, `// FIXME: ...`, `// XXX: ...`, `// HACK: ...`
- `# TODO: ...` (Python)
- `<!-- TODO: ... -->` (HTML/Razor)

**Sévérité** : `error` (à résoudre avant prod).

### 3.2 Debug output (warnings)

Détecte les sorties de debug oubliées :

| Pattern | Contexte |
|---|---|
| `console.log(`, `console.error(`, `console.warn(` | JS/TS |
| `Console.WriteLine(`, `Debug.Print(` | C# |
| `print(` (en début de ligne) | Python |
| `System.out.println(` | Java/Kotlin |
| `println!(` | Rust |

**Sévérité** : `warning`.

### 3.3 Hardcoded hex (warnings)

Détecte les valeurs hex hardcodées (#RRGGBB ou #RGB) **hors** de
`theme.css` / `theme.scss`.

Concerne : `.css`, `.scss`, `.razor`, `.tsx`, `.jsx`, `.vue`.

Le seul endroit autorisé pour les hex est le fichier theme global
référencé par `rules/ui-tokens.md` (héritage SDD_Lite philosophie).

**Sévérité** : `warning`.

### 3.4 Méthodes longues (warnings)

Détecte les méthodes / fonctions / classes > 50 lignes (heuristique
basée sur les accolades pour C#/Kotlin/TS, indentation pour Python).

**Sévérité** : `warning`.

### 3.5 Code commenté en bloc (info)

Détecte les blocs de ≥ 5 lignes consécutives de commentaires qui
ressemblent à du code (présence de parenthèses, points-virgules, points,
affectations).

**Sévérité** : `info`.

### 3.6 Magic numbers (info)

Détecte les littéraux numériques ≥ 100 chiffres en contexte
exécutable (hors annotations, hors strings). Exclut les codes communs
(200, 401, 1024, 8080, …).

**Sévérité** : `info`.

---

## 4. Exclusions

Le script exclut automatiquement :

| Type | Patterns |
|---|---|
| Dossiers de build | `bin/`, `obj/`, `dist/`, `build/` |
| Dépendances | `node_modules/`, `.angular/`, `wwwroot/_framework/` |
| Tests | `*.Tests/`, `__tests__/`, `*.spec.*`, `*.test.*`, `test_*`, `_test.*` |
| Coverage | `coverage/`, `TestResults/` |
| IDE | `.vs/`, `.idea/` |

Le quality scan s'applique **uniquement au code de production**.

---

## 5. Output

Le script produit `workspace/output/qa/feat-{n}/quality.json` :

```json
{
  "spec": 1,
  "extractedAt": "2026-05-05T14:32:18Z",
  "summary": {
    "total_files": 42,
    "errors": 3,
    "warnings": 12,
    "info": 7
  },
  "errors": [
    {
      "category": "todo",
      "severity": "error",
      "file": "workspace/output/src/SIMBackend/Services/AuthService.cs",
      "line": 42,
      "tag": "TODO",
      "message": "TODO: implement token refresh"
    }
  ],
  "warnings": [...],
  "info": [...]
}
```

---

## 6. Règle d'évaluation (non bloquante)

Le quality scan **ne bloque jamais** le pipeline. Il est purement
informatif :

| Niveau | Présence | Effet sur la décision globale `/qa-generate` |
|---|---|---|
| `errors` | 0 | GREEN (si tests + coverage OK) |
| `errors` | ≥ 1 | YELLOW |
| `warnings` | toujours informatif | n'affecte pas la décision |
| `info` | toujours informatif | n'affecte pas la décision |

**Pas de seuil bloquant** : un projet avec 50 warnings reste GREEN si
les tests passent. C'est de l'**audit**, pas une **gate**.

---

## 7. Personnalisation (futur)

Cette stack est volontairement **non-personnalisable** dans v3.1.0
(pas de fichier de config par projet). Si un projet souhaite désactiver
une catégorie :

- **Workaround actuel** : retirer la ligne
  `- .claude/stacks/qa/code-quality.md` de `## Active QA Specs`
  → désactive le scan complet
- **Cible v3.2** : fichier de config par projet pour désactiver
  catégorie par catégorie (`disable: [magic-number, commented-code]`)

---

## 8. Pourquoi pas un LLM-based code review ?

Choix architectural fort de SDD_Pro v3.1.0 :

| Approche | Coût tokens | Faux positifs | Détecte vrais bugs |
|---|---|---|---|
| **Quality scan PowerShell** (cette stack) | **0** | bas | non (mais smells) |
| LLM code review "trouve les bugs" | ~30-50k / feature | ~30% | partiellement |
| Tests unitaires (autre stack QA) | ~5-8k / US | bas | **oui** |
| Linter / Type checker (stack-native) | 0 | bas | **oui** (compile-time) |

Les **vrais bugs** sont mieux détectés par :
1. **Tests unitaires** (exécution)
2. **Type checker** (compile-time, déterministe)
3. **Linter stack-native** (eslint, dotnet format, ruff, ktlint)

Les **code smells** sont mieux détectés par :
1. **Quality scan PowerShell** (déterministe, 0 token)
2. **SonarQube / Sonar Cloud** (intégration externe, hors scope)

Pas d'overlap inutile, pas de duplication de coût.

---

## 9. Performance

Sur un projet ~5000 LOC réparti en ~50 fichiers, le scan complet :
- **Durée** : < 1 seconde (PowerShell + regex)
- **Tokens** : 0
- **CPU** : faible (~1 cœur, pas de concurrence)
- **I/O** : 1 lecture par fichier source, 1 écriture quality.json

Coût négligeable comparé à un test runner (`dotnet test` ~10-30s).
