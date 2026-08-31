# 🚀 Premiers pas avec SDD_Pro

**5 minutes pour comprendre. 30 minutes pour ton premier projet fonctionnel.**

Ce guide t'emmène de zéro à une application full-stack générée par SDD_Pro, avec tests et reviews qualité intégrés.

---

## Qu'est-ce que SDD_Pro ?

**Spec-Driven Development pour Claude Code** : un framework qui transforme des **spécifications fonctionnelles** en **code prêt-à-livrer** via des agents IA coordonnés.

Tu écris **ce que** le logiciel doit faire (FEAT spec + mockup HTML optionnel). SDD_Pro orchestre **29 agents spécialisés** (13 sur le pipeline forward, 16 sur le module reverse) et des routeurs Python déterministes (0 token) pour déterminer **comment** :

```
Tu écris :              SDD_Pro produit :
─────────────────       ─────────────────────────────────
FEAT spec               • User Stories (atomiques, traçables)
+ HTML mockup    ──→    • Code backend (services, endpoints, DTOs)
+ choix de stack        • Code frontend (pages, components, theme)
                        • Tests unitaires (back + front)
                        • 5 rapports review qualité
                        • Coverage / lint / security / spec compliance
                        • Architectural Decision Records (ADRs)
```

L'innovation clé : **orchestration Python déterministe** (80 scripts, 0 token) + **agents LLM** (29 spécialisés) + **5 reviewers cross-file** = un pipeline auditable, idempotent et reprenable.

---

## En quoi c'est différent de BMAD / Spec-Kit / etc. ?

| Aspect | SDD_Pro | BMAD | Spec-Kit |
|---|---|---|---|
| Multi-agents | **29 spécialisés** | ~6 | 1 |
| Reviewers post-code | **5 angles distincts** | 1 | 0 |
| Anti-derive strict | strict (matrice ownership + STOP) | partiel | ❌ |
| Catalogue stacks | `.libs.json` machine + CVE + LTS check | ❌ | ❌ |
| Taxonomie d'erreurs | **193 classes `[CLASS]`** cross-agent | ❌ | ❌ |
| Télémétrie | SQLite (cost cap, audit, gates) | ❌ | ❌ |
| Déterminisme | 80 scripts Python (0 token) | ❌ | ❌ |
| Idempotence / resume | mode checkpoint | ❌ | ❌ |

**Différenciateur** : SDD_Pro **industrialise la qualité** — c'est l'équivalent de **Sonar + Snyk + gouvernance ADR** appliqué aux pipelines LLM.

---

## 🏗 Vue d'ensemble (tour de 5 min)

### Modèle des phases

```
┌─ Phase 1 ─ Cadrage FEAT  ─────┐
│   /feat-generate Auth         │
│   ↓                            │
├─ Phase 1.5 (optionnelle)      │
│   /feat-deepen Auth           │  ← élicitation (Pre-mortem, Red Team...)
│   ↓                            │
├─ Phase 2 ─ User Stories ──────┤
│   /us-generate 1              │
│   ↓                            │
├─ Phase 2.6 ─ Readiness gate   │
│   /feat-validate 1            │  ← gate déterministe, 0 token
│   ↓                            │
├─ Phase 2.7 (optionnelle) ─────┤
│   /dev-plan 1                 │  ← review humain des plans techniques
│   ↓                            │
├─ Phase 3 ─ Architecture ──────┤
│   /arch-init                  │  ← scaffolding + DB
│   ↓                            │
├─ Phase 4 ─ Code (parallèle) ──┤
│   dev-backend × N  ──→ API Gate ──→ dev-frontend × N
│   (build_loop ≤3 iter)         │
│   ↓                            │
├─ Phase 5 ─ QA ────────────────┤
│   /qa-generate 1              │  ← tests + coverage + quality
│   ↓                            │
├─ Phase 6 ─ Auditors (batch) ──┤
│   code-reviewer + security-reviewer + spec-compliance + arch-reviewer
│   ↓                            │
└─ Phase 7 ─ Verdict ───────────┘
    /sdd-review 1               ← consolidé 🟢/🟡/🔴
```

**Une seule commande lance les 7 phases :** `/sdd-full 1`

---

## ⚡ Le tutoriel de 30 minutes

### Prérequis

- **Python ≥ 3.10** (`python --version`)
- **Node.js ≥ 20** (pour la console web optionnelle)
- **Git**
- **Une clé API Anthropic** (pour Claude Code) — `export ANTHROPIC_API_KEY=<votre-cle>`
  (variable d'environnement uniquement — ne jamais écrire une clé dans un fichier versionné)
- **Claude Code** installé (`https://claude.com/claude-code`)
- Un runtime stack-spécifique selon le combo (ex. .NET 10, Node 22, etc.)

---

### Étape 1 — Récupérer le framework (2 min)

Utilise ce repo comme **template** (recommandé) :

1. Copie le repo vers un nouveau emplacement privé (clone Azure DevOps, fork, etc.)
2. Clone-le localement :

```bash
git clone <ton-url-repo> mon-premier-projet-sdd
cd mon-premier-projet-sdd
```

---

### Étape 2 — Bootstrap (5 min)

Lance le bootstrap interactif. On va te demander le nom du projet + 3-4 choix de stack.

```bash
# macOS / Linux
python3 bootstrap.py

# Windows, macOS et Linux
python bootstrap.py
```

**Recommandé pour le 1er essai** : combo **C1** = .NET Minimal API + React + shadcn + Azure AD + xUnit.

```bash
python bootstrap.py --combo c1
```

Ce qui se passe :
- ✅ `workspace/stack/stack.md` généré (43 clés Project Config)
- ✅ Structure `workspace/.sys/` créée
- ✅ Deps Python installées (`pip install -e .sdd/python[dev]`)
- ✅ Deps console installées optionnellement (`workspace/console/`)
- ✅ Smoke check passe

Après ça, ton repo est **initialisé** mais ne contient pas encore de FEAT.

---

### Étape 3 — Éditer les secrets (1 min)

Ouvre `workspace/stack/stack.md` (déjà ouvert par bootstrap dans la plupart des éditeurs) et remplace les placeholders :

```yaml
## Active Database
Type: PostgreSql
Server: <hote-de-votre-base>
Database: <nom-de-votre-base>
User: <utilisateur>
Password: <mot-de-passe>          # ← à renseigner
Port: 5432

## Active Auth Specs
AzureAD.TenantId: <votre-tenant-id>   # ← à renseigner (ou utiliser auth-local)
AzureAD.ClientId: <votre-client-id>   # ← à renseigner
```

> 🔒 **Sécurité.** ⚠️ Depuis le 2026-08-30, `stack.md` est **versionné** : il voyage
> avec le repo comme SSoT de configuration projet. Tout secret réel écrit ici **part
> sur `origin` au premier push** et doit être considéré comme compromis. N'y mettre
> que des placeholders `${VAR}` ou des valeurs non sensibles ; pour garder des vraies
> valeurs en local sans les pousser : `git update-index --skip-worktree
> workspace/stack/stack.md`. Le reste de `workspace/` reste ignoré. Ne jamais recopier
> un secret dans une doc, une issue, un ticket ou un message.
> `application.yml` au moment du scaffold. Pour le reverse SGBD, utilise un login dédié
> en **lecture seule** (`GRANT VIEW DEFINITION` + `db_datareader`) — jamais un compte
> d'administration.

---

### Étape 4 — Ta première FEAT (5 min)

Dans Claude Code, lance :

```
/feat-generate Auth
```

On va te poser 3-6 questions :
- Que fait Auth ?
- Quels sont les acteurs (PO, utilisateurs finaux, admins, etc.) ?
- Flux principaux ?
- Règles métier ?
- Critères d'acceptation ?

L'agent produit `workspace/feats/1-Auth.md` avec des sections structurées : `## Functional Needs`, `## Functional Deliverables`, `## Business Rules`, `## Acceptance Criteria`, chacune avec des IDs stables `SFD-N`, `FD-N`, `BR-N`, `AC-N`.

**Optionnel** : dépose un mockup HTML à `workspace/ui/1-2-Login.html` pour la fidélité visuelle.

---

### Étape 5 — Lancer le pipeline complet (15 min, varie selon taille FEAT)

```
/sdd-full 1
```

Regarde le chat — tu verras des updates exécutifs 1-ligne :

```
[PO] Découpage FEAT en User Stories... (8%)
[PO] 2 User Stories créées (1-1-Login, 1-2-Reset). (12%)
[VALIDATE] FEAT 1-Auth → GO (readiness 87%). (15%)
[ARCH] Bootstrap projets et scaffolding DB... (24%)
[ARCH] schema.json généré (3 entités). (32%)
[DEV-BACKEND] Implémentation US 1-1... (40%)
[DEV-BACKEND] US 1-1 livré, build vert. (48%)
[DEV-BACKEND] Implémentation US 1-2... (50%)
[DEV-BACKEND] US 1-2 livré, build vert. (54%)
[QA] API Gate (tests in-memory)... (60%)
[QA] API Gate 🟢 12/12 endpoints. (66%)
[DEV-FRONTEND] Implémentation US 1-1... (70%)
[DEV-FRONTEND] US 1-1 livré, fidelity 92%. (76%)
[DEV-FRONTEND] US 1-2 livré, fidelity 88%. (78%)
[QA] Tests + Coverage... (82%)
[QA] Coverage 84%, verdict 🟢. (88%)
[CODE-REVIEW] 0 critical, 2 minor. (91%)
[SPEC-REVIEW] 12/12 ACs verified. (94%)
[SECURITY] 0 vulnérabilité. (96%)
[ARCH-REVIEW] Layer mapping OK. (98%)
[DONE] FEAT 1-Auth livrée — 🟢 GREEN (2 US, 47 tests, coverage 84%, 0 critique). (100%)
```

Coût attendu : **$15-30 USD** pour une FEAT typique de 2-3 US sur le combo C1.

---

### Étape 6 — Inspecter le résultat (2 min)

```bash
# Vérifier l'état
/sdd-status 1

# Voir le code généré
ls workspace/src/MonAppBack/
ls workspace/src/MonAppFront/

# Voir la review consolidée (rendue à la demande depuis console.db)
python .sdd/python/sdd_scripts/query_console_db.py review --feat 1 --format md
```

---

### Étape 7 — Le faire tourner (optionnel, 2 min)

```bash
/sdd-serve            # lance backend + frontend + console en background
```

Ouvre dans le navigateur :
- **App web** : http://localhost:5173 (ou le port utilisé par ton stack)
- **API** : http://localhost:8080 (Swagger UI exposé)
- **Console SDD** : http://localhost:4000 (dashboard télémétrie)

Quand tu as fini :
```bash
/sdd-kill-server
```

---

## 🎯 Ce que tu viens de faire

En 30 minutes :
1. ✅ Bootstrapé un combo stack validé
2. ✅ Écrit une FEAT spec de 2-3 pages
3. ✅ Généré 2 user stories avec traçabilité complète
4. ✅ Scaffoldé une solution multi-projet (back + front + lib)
5. ✅ Matérialisé le code backend (services, endpoints, DTOs, entities)
6. ✅ Vérifié le contrat API via tests in-memory (API Gate)
7. ✅ Matérialisé le code frontend (pages, components, theme) depuis le mockup HTML
8. ✅ Généré les tests unitaires (back + front)
9. ✅ Obtenu 5 verdicts qualité (code, security, spec, arch, adversarial optionnel)
10. ✅ Un verdict consolidé 🟢 GREEN prêt pour code review / déploiement

Coût : **$15-30 USD** d'API Claude.
Lignes de code générées : **~1000-3000 LOC** (varie selon FEAT).

---

## 📚 Prochaines étapes

| Objectif | Lire |
|---|---|
| Accélérer la prochaine session | [cookbook.md](cookbook.md) (recette 10 min) |
| Comprendre l'architecture | [architecture.md](architecture.md) |
| Rechercher le rôle d'un agent | [agents-reference.md](agents-reference.md) |
| Rechercher les flags d'une commande | [commands-reference.md](commands-reference.md) |
| Ajuster cost cap, coverage threshold etc. | [configuration-reference.md](configuration-reference.md) |
| Ajouter une nouvelle FEAT | répéter depuis **Étape 4** ci-dessus |
| Rencontré une erreur ? | [troubleshooting.md](troubleshooting.md) |
| Onboarding repo brownfield | [quickstart.md](quickstart.md) |
| Ajouter un nouveau stack | [poc-roi-methodology.md](poc-roi-methodology.md) |
| **Récupérer une base de données legacy** | [reverse-engineering-workflow.md](reverse-engineering-workflow.md) — `/sdd-db-context` puis `/sdd-db-reverse-full` |
| **Récupérer du code source legacy** | [reverse-engineering-workflow.md](reverse-engineering-workflow.md) — `/sdd-reverse-full` |
| Travailler sous Codex / Gemini CLI | [multi-llm-getting-started.md](multi-llm-getting-started.md) |
| Contribuer au framework | [WORKING-AGREEMENT.md](WORKING-AGREEMENT.md) |

---

## ❓ Questions fréquentes en première utilisation

### "SDD_Pro va-t-il modifier mon code existant ?"

Non. SDD_Pro écrit **uniquement sous `workspace/src/`** (son propre sandbox). Le code source existant de ton repo n'est jamais touché.

### "Et si ma FEAT est trop vague ?"

Utilise `/feat-deepen 1` (l'agent `elicitor`) pour l'enrichir via 5 angles (Pre-mortem, Red Team, RACI, Failure Modes, Inversion). Lance ça AVANT `/sdd-full` pour les features critiques.

### "Et si une phase échoue à mi-chemin ?"

```bash
/sdd-full 1 --resume
```

La logique de resume utilise `sdd_state.py resume-target` pour sauter les phases déjà complétées. Chaque phase est idempotente.

### "Comment je review le travail des agents étape par étape ?"

```bash
/sdd-full 1 --plan --manual-gates=us,plan,code
```

Ça pause après chaque phase majeure, te permettant d'inspecter + approuver dans la console web (ou en éditant `workspace/console/status.json`).

### "Mes données sont-elles sécurisées ?"

- ⚠️ `workspace/stack/stack.md` est **versionné** (SSoT config projet) — placeholders
  `${VAR}` uniquement ; tout le reste de `workspace/` est gitignored.
- `workspace/console/.certs/` (clés HTTPS) est gitignored.
- Aucune télémétrie ne quitte ta machine (SQLite est local).
- Les appels API Anthropic suivent la politique Claude Code.

### "Puis-je utiliser SDD_Pro en production ?"

Oui pour les **combos C1 et C2** (🟢 validés bout-en-bout). Les autres combos (C3-C5) sont bench-validated runtime mais le pipeline `/sdd-full` complet a quelques gaps de scaffolding manuel. Voir [validated-combos.md](validated-combos.md).

---

## 🎓 Modèle mental en 3 idées

1. **Tu écris les specs, les agents écrivent le code.** Le contrat est la FEAT spec (avec IDs de traçabilité). La sortie est du code qui compile, les tests passent, et 5 reviewers approuvent.

2. **La qualité est industrialisée, pas aspirationnelle.** Chaque sortie est vérifiée par des scripts Python déterministes (coverage parsing, quality scan, OWASP regex) ET par des agents LLM (review cross-file). Les erreurs hard-blocking ne peuvent pas être bypassées sans décision tracée.

3. **Le framework refuse de dériver.** Les règles anti-derive (`build-and-loop §3`, matrice ownership, checks de staleness des plans) STOP le pipeline plutôt que de deviner. Le message d'erreur te dit exactement quoi corriger.

C'est le **Sonar + Snyk + gouvernance ADR** du développement assisté par LLM. Bienvenue à bord.

---

## 🔗 Où aller ensuite

- 📖 **Cookbook (recettes 10 min)** : [cookbook.md](cookbook.md)
- 🏗 **Architecture deep-dive** : [architecture.md](architecture.md)
- 🤖 **Agent reference** : [agents-reference.md](agents-reference.md)
- 💻 **Command reference** : [commands-reference.md](commands-reference.md)
- 🛟 **Troubleshooting** : [troubleshooting.md](troubleshooting.md)
- 🤝 **Contribuer** : [WORKING-AGREEMENT.md](WORKING-AGREEMENT.md) · [VERSIONING.md](VERSIONING.md)
