# Règle — Politique librairies (extracted from arch.md v5.0)

> Règle propriétaire **arch** uniquement. Read on-demand seulement si
> arch détecte une CVE ou une lib non-canonique pendant Phase A
> (bootstrap). Pas en system prompt.

## Principe

Toute librairie installée par les Init Commands (§2.2.1 du stack actif)
ou par le STEP 5.bis (capabilities on-demand) DOIT respecter les
critères suivants. La politique est inlinée dans `agents/arch.md`
(section dédiée v2.2) ; ce fichier en est la source canonique pour les
edge-cases.

## 1. Critères d'acceptation

### 1.1 Origine officielle
Registry canonique uniquement :
- **NuGet** (`api.nuget.org`)
- **npm** (`registry.npmjs.org`)
- **PyPI** (`pypi.org`)
- **Maven Central** (`repo1.maven.org/maven2`)
- **Gradle plugins portal** (`plugins.gradle.org`)

Pas de fork, pas de mirror tiers, pas de feed privé non documenté.

### 1.2 Version stable et pinnée
- Version pinnée dans `## 2.4 Librairies` du stack OU dernière stable
  au moment de l'install (avec stockage de la version résolue)
- Interdit : pre-release (`-alpha`, `-beta`, `-rc`, `-preview`,
  `-snapshot`) sauf justification explicite dans le stack
- Interdit : version `latest` non pinnée

### 1.3 Sans CVE ≥ moderate
Vérifié post-install :
- **NuGet** : `dotnet list package --vulnerable --include-transitive`
- **npm** : `npm audit --omit=dev --audit-level=moderate`
- **pip** : `pip-audit`
- **Maven/Gradle** : `mvn dependency:check` (OWASP Dependency-Check)
  ou plugin Gradle `dependency-check`

## 2. Format ERROR sur CVE détectée

```
ERROR: arch — librairie vulnérable
CAUSE: <pkg> <version> présente CVE <ID> (gravité ≥ moderate) — <URL advisory>
FIX: mettre à jour <pkg> dans .claude/stacks/<chemin>.md §2.4 et §2.2.1,
     puis relancer /arch-init
```

## 3. Anti-patterns interdits

- **Install ad-hoc** : `npm install <pkg>` ou `dotnet add package <pkg>`
  hors §2.2.1 du stack ou hors §2.2.2 (capabilities on-demand)
- **Modification manuelle** par dev-* de `.csproj` / `package.json` /
  `pyproject.toml` / `build.gradle.kts` (réservé arch)
- **Réflexion / chargement dynamique** pour contourner la politique
- **Confiance dans "le compilateur trouve la dépendance"** comme
  justification d'autorisation

## 4. Workflow d'ajout d'une lib (par Tech Lead)

1. Vérifier CVE et licence de la lib candidate
2. Ajouter une ligne dans `## 2.4 Librairies` du stack approprié
   (`.claude/stacks/{cat}/{stack-id}.md`)
3. Ajouter la commande d'install dans `## 2.2.1 Init Commands`
4. (Optionnel) Documenter le pattern d'usage en `## 3 Conventions`
5. Relancer `/arch-init` (idempotent — pas de duplication)

## 5. Lien avec autres règles

- `stack-completeness.md` — interdit l'install ad-hoc côté dev-*
- `file-ownership.md §1` — arch est seul owner des fichiers projet
  (`.csproj`, `package.json`, etc.)
- `responsibilities.md §7-§8` — arch installe, dev-* utilise
