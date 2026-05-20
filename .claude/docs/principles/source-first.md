# Règle — Source-First Discipline (MD avant code)

## Principe

En méthode SDD strict, **tout bug en code = trou dans une source MD**
(FEAT fonctionnelle, US, plan technique, stack MD, agent MD, rule MD).
À chaque correction, la propagation va du **MD source → code**, jamais
l'inverse.

Cette règle est **load-bearing pour la non-régression cross-projet** :
le framework SDD_Pro génère du code à partir des MD. Si un bug est
corrigé uniquement dans le code généré, le **prochain projet** (autre
FEAT, autre run `/sdd-full`, autre client) reproduira exactement le
même bug — les agents PO / arch / dev-* ne lisent QUE les MD, pas
l'historique de chat ni les commits git du projet précédent.

---

## 1. Workflow obligatoire de correction

Pour chaque bug constaté dans le code généré (`workspace/output/src/...`,
tests, build, runtime) :

### Étape 1 — Identifier la (les) source(s) MD manquante(s)

Mapper le bug → quelle(s) source(s) aurait dû le prévenir :

| Niveau de source | Quand patcher | Exemple |
|---|---|---|
| **FEAT fonctionnelle** (`workspace/input/feats/{n}-*.md`) | Le bug touche une règle métier ou un AC implicite | CORS manquant → ajouter BR-N : "API accessible depuis origin SPA" + AC-M : "preflight OPTIONS répond 200" |
| **User Story** (`workspace/output/us/{n}-{m}-*.md`) | Le bug touche un comportement utilisateur observable | Erreur popup "Failed to fetch" → ajouter AC-X : "message d'erreur lisible si endpoint down" |
| **Plan technique** (`workspace/output/plans/{n}-{m}-*.{back,front}.md`) | Le bug touche un fichier oublié ou mal scopé | `CorsConfig.kt` absent → ajouter en `create:` |
| **Stack MD** (`.claude/stacks/{cat}/{stack}.md`) | Le bug touche un pattern réutilisable cross-projet | Pattern CORS Spring → §5.2.7 avec format ERROR + anti-récap grep |
| **Agent MD** (`.claude/agents/{agent}.md`) | Le bug révèle un piège récurrent pour l'agent | Pattern à grep en STEP build, stratégie de récupération |
| **Rule MD** (`.claude/rules/{rule}.md`) | Le bug viole une règle non encore formalisée | Étendre la matrice ownership, ajouter anti-pattern |

### Étape 2 — Patcher la (les) source(s) MD AVANT le code

L'ordre est strict :

```
1. Read la source MD pertinente
2. Edit/Write la source : ajouter règle, AC, pattern, format ERROR
3. (optionnel) régénérer les artefacts dérivés (US si FEAT patchée,
   plan si stack patché) via /us-generate, /dev-plan
4. ENFIN, appliquer le fix au code (workspace/output/src/...)
```

Patcher le code avant les MD est interdit : ça crée un drift
permanent entre source et code.

### Étape 3 — Vérifier la propagation cross-source

Si plusieurs sources sont concernées, **TOUTES** doivent être à jour :

Exemple (post-mortem CMS-Back 2026-05-11, CORS manquant) :
- FEAT 1 : BR-12 + AC-15 (CORS obligatoire entre origins distincts)
- Stack `auth/azure-ad.md` §5.2.7.9 (pattern Spring / .NET / FastAPI /
  Express + alternative Vite proxy + format ERROR)
- Plan `1-1-Connexion.back.md` : `CorsConfig.kt` listé en `create:`
- Code : `CorsConfig.kt` + `http.cors {}` dans SecurityConfig

Sans ces patches sources, **le prochain projet SPA + Spring
reproduira le bug**.

---

## 2. Format anti-pattern dans les Stack MD

Quand on patche un stack MD pour bloquer un bug récurrent, suivre
le format canonique :

````markdown
### §X.Y.Z — {Nom du piège canonique}

**Symptôme** : {erreur runtime concrète vue côté user}

**Cause racine** : {explication 1-2 lignes}

**Pattern correct** (exemple code stack-aware) :
```kotlin
// CorsConfig.kt
@Configuration
class CorsConfig { ... }
```

**Anti-pattern à grep en STEP build** :
```
grep -r "@CrossOrigin" workspace/output/src/{BackendName}/ && WARN
```

**Format ERROR** :
```
ERROR: dev-backend {n}-{m} — CORS non configuré
CAUSE: [SECURITY_CORS_MISSING] CorsConfig absent OU http.cors{} manquant
FIX: ajouter CorsConfig.kt + http.cors { allowedOrigins=[$env:CORS_ORIGINS] } dans SecurityConfig
```
````

---

## 3. Quand ne pas appliquer cette règle

- Bug **strictement spécifique au projet courant** (pas généralisable) :
  fix code-only acceptable, mais émettre un commentaire explicatif et
  un TODO pour réviser plus tard si le pattern se reproduit.
- Bug dans un **fichier de test généré par QA** (ownership QA) : fix
  test-only, pas de propagation MD nécessaire (les tests ne sont pas
  régénérés depuis les MD).
- Typo / coquille pure dans un libellé : fix code, le mockup HTML reste
  la source de vérité visuelle.

---

## 4. Anti-pattern : "fix code-only récurrent"

Si la même classe de bug apparaît dans ≥ 2 projets / FEATs successifs
sans patch source MD → **STOP** lors de la troisième correction et
exiger :
1. Identification du gap MD
2. Patch source MD (stack ou rule)
3. Fix code uniquement après §1 + §2

Ne pas tomber dans le pattern "je sais comment fixer, je tape le code,
je passe au suivant" — c'est exactement ce qui crée des projets
"snowflake" incompatibles avec le framework SDD.

---

## 5. Enforcement

- **Agents `dev-backend` / `dev-frontend`** : lors d'un fix après
  build_loop échec, vérifier mentalement "ce bug aurait-il pu être
  évité par un patch de stack MD ou rule MD ?". Si oui, émettre un
  WARNING avec pointer vers la source manquante. Le patch lui-même
  est hors scope agent (Tech Lead humain).
- **Tech Lead humain** : pour chaque PR de fix sur un projet généré,
  exiger le patch des sources MD pertinentes (FEAT, stack, rule)
  avant merge.
- **Post-mortem** : tout incident production réglé en hotfix doit
  produire un patch source MD dans les 48h, faute de quoi le bug
  reviendra dans le prochain projet généré.

---

## 6. Règle mentale

**"Avant de toucher le code, je me demande : QUELLE source MD a manqué
pour que cette erreur ne soit pas évitée nativement ? Je patche
d'abord cette source. Le fix code n'est que la concrétisation."**

Le code est une cible, jamais une source.
