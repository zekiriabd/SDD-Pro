# 📚 Documentation SDD_Pro

> **Spec-Driven Development pour Claude Code** — un framework multi-agent qui transforme des spécifications fonctionnelles en code prêt-à-livrer, via 13 agents IA spécialisés (incl. `complexity-router` opt-in v7.0.0+), une orchestration Python déterministe, et 5 reviewers qualité.

C'est le hub de documentation. Chaque doc a un objectif et une audience cible. Choisis ton parcours ci-dessous.

> 🇫🇷 **Documentation FR canonique**. Versions EN disponibles via le sélecteur de langue (en haut à droite). Si une page EN n'existe pas, fallback automatique sur le FR.

---

## 🚀 Je veux commencer à utiliser SDD_Pro

| Étape | Objectif | Doc |
|---|---|---|
| **1** | Comprendre SDD_Pro en 5 minutes | [getting-started.md](getting-started.md) |
| **2** | Obtenir un projet fonctionnel en 30 minutes | [cookbook.md](cookbook.md) |
| **3** | Apprendre le vocabulaire | [glossary.md](glossary.md) |
| **4** | Configurer un repo brownfield | [quickstart.md](quickstart.md) |
| **5** | Choisir une combo de stacks | [validated-combos.md](validated-combos.md) |

---

## 📖 Je veux comprendre le framework en profondeur

| Sujet | Audience | Doc |
|---|---|---|
| Visualisation du pipeline (mermaid) | Architecte / Tech Lead | [workflow.md](workflow.md) |
| Modèle de composants (agents, rules, hooks) | Architecte / Tech Lead | [architecture.md](architecture.md) |
| Pourquoi ces choix de conception | Tous | [principles/source-first.md](principles/source-first.md) |
| Règles de granularité des User Stories | PO / Tech Lead | [principles/us-granularity.md](principles/us-granularity.md) |
| Anti-derive + idempotence + plans | Tech Lead | [conventions.md](conventions.md) |

---

## 🔧 J'ai besoin d'une référence (fiches)

| Référence | Objet | Doc |
|---|---|---|
| **13 agents** | Rôle / Modèle / Entrées / Sorties / Verdicts | [agents-reference.md](agents-reference.md) |
| **21 commandes** | Args / Flags / Agents / Sorties | [commands-reference.md](commands-reference.md) |
| **Project Config (58 clés)** | Config layered + defaults + plages | [configuration-reference.md](configuration-reference.md) |
| **Classes d'erreur** | Taxonomie (174 préfixes `[CLASS]`) | [../rules/error-classification.md](../rules/error-classification.md) |
| **Hooks + protections** | 13 hooks Claude Code câblés | [hooks-and-protections.md](hooks-and-protections.md) |

---

## 🛟 J'ai une erreur / question

| Situation | Doc |
|---|---|
| Erreurs courantes + récupération | [troubleshooting.md](troubleshooting.md) |
| Précédence de config (base ← team ← project) | [config-precedence.md](config-precedence.md) |
| Nettoyer les fichiers orphelins | [orphan-cleanup-policy.md](orphan-cleanup-policy.md) |
| Décalage de version de stack | [validated-combos.md](validated-combos.md) |

---

## 🤝 Je veux contribuer

| Contribution | Doc |
|---|---|
| Code / docs / corrections | [../../CONTRIBUTING.md](../../CONTRIBUTING.md) |
| Accord de travail (working agreement) | [WORKING-AGREEMENT.md](WORKING-AGREEMENT.md) |
| Politique de versioning | [VERSIONING.md](VERSIONING.md) |
| Ajouter un nouveau stack | [../stacks/README.md](../stacks/README.md) |

---

## 📜 Je consulte l'historique / changelogs

| Doc | Contenu |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Notes de version (par release) |
| [MIGRATION.md](MIGRATION.md) | Guides de mise à niveau v6 → v7 |
| [adrs/](adrs/) | Architecture Decision Records |
| [roadmap-v7-v8.md](roadmap-v7-v8.md) | Ce qui arrive après |

---

## 📊 ROI & benchmarks

| Doc | Objet |
|---|---|
| [poc-roi-methodology.md](poc-roi-methodology.md) | Comment valider un nouveau stack |
| [benchmarks/](benchmarks/) | Rapports de runs + gaps connus |
| [cache-strategy.md](cache-strategy.md) | Plan de cache prompts (cible v7.1) |

---

## 🏛 Sous-systèmes

| Sous-système | Doc |
|---|---|
| **Phases arch** (A/B/C deep dive) | [arch/phase-a-config-propagation.md](arch/phase-a-config-propagation.md), [arch/phase-b-db-scaffolding.md](arch/phase-b-db-scaffolding.md), [arch/phase-c-claude-md-generation.md](arch/phase-c-claude-md-generation.md) |
| **Codebase Python** | [../python/README.md](../python/README.md) |
| **Catalogue stacks** | [../stacks/README.md](../stacks/README.md) |
| **Règles** (5 consolidées + 3 annexes) | [../rules/](../rules/) |

---

## ❓ Toujours perdu ?

- **Nouveau contributeur ?** Lis `getting-started.md` + `cookbook.md` (1h au total).
- **Onboarding repo brownfield ?** Lance `/sdd-discover-stack`, puis lis `quickstart.md`.
- **Pipeline qui plante ?** Ouvre `troubleshooting.md` et grep ta classe d'erreur `[XXX]`.
- **Ajouter un stack ?** Lis d'abord `poc-roi-methodology.md` (le critère de validation est réel).
- **Lire un rapport d'audit ?** Voir `architecture.md §3` (qui écrit quoi).

> 💡 **Astuce** : l'entry-point `.claude/CLAUDE.md` (150 lignes) est un index slim — chaque section y pointe vers les docs détaillées que tu vois ici. Si tu ne lis que 2 fichiers, choisis `CLAUDE.md` + cette page.

---

## 🌐 Statut des traductions

| Page | FR | EN |
|---|:---:|:---:|
| README (cette page) | ✅ canonique | ✅ |
| Getting Started | ✅ canonique | ✅ |
| Agents Reference | ✅ canonique | ✅ (contenu technique anglo-friendly) |
| Commands Reference | ✅ canonique | ✅ (contenu technique anglo-friendly) |
| Configuration Reference | ✅ canonique | 🟡 fallback FR |
| Troubleshooting | ✅ canonique | 🟡 fallback FR |
| Architecture | ✅ canonique | 🟡 fallback FR |
| Autres pages | ✅ canonique | 🟡 fallback FR |

> Quand une page EN manque, le sélecteur de langue retombe gracieusement sur la version FR (via `fallback_to_default: true` dans `mkdocs.yml`). Contributions EN bienvenues — ajouter `page.en.md` à côté de `page.md`.
