# Output Protocol — Mode minimal `SDD_CHAT_MINIMAL=1` (CI/CD opt-in, v7.0.1-dev)

> **Extraction (audit tokens 2026-08-30)** : substance ex-`rules/output-protocol.md
> §10.bis`, déplacée ici pour alléger la rule inconditionnelle (auto-injectée
> dans chaque session/sous-agent) d'un mode opt-in que seuls les runs CI/CD
> consomment. La rule conserve un pointeur 2L. Aucun changement de contrat.

`SDD_CHAT_MINIMAL=1` (export parent shell AVANT démarrage Claude Code) →
**1 ligne par invocation** au lieu des 3-6 updates standard. Conçu pour
les runs CI/CD où le log doit rester concis (parsing automatique, taille
contrôlée, économie de cache prompt pour orchestration).

## 1. Format minimal

Pour chaque agent / phase, **uniquement la ligne de résultat finale**
au format `[AGENT] verdict (PROGRESS%)`. Les `[AGENT/FIXING]` retries
sont supprimés. Les `[AGENT]` updates intermédiaires sont supprimés.

**Exemple comparatif** (FEAT 1-Auth, 2 US) :

| Mode | Lignes émises |
|---|---:|
| Default (executive) | ~30-50 lignes (3-6 par agent × ~10 agents) |
| `SDD_CHAT_VERBOSE=1` | ~150-300 lignes (legacy v6) |
| `SDD_CHAT_MINIMAL=1` | ~10-12 lignes (1 par agent + verdict final) |

## 2. Sortie type mode minimal

```
[PO] 2 User Stories créées. (12%)
[VALIDATE] FEAT 1-Auth GO. (15%)
[ARCH] Scaffolding terminé (1 backend + 1 frontend). (32%)
[CONSTITUTION] ADRs indexés. (36%)
[DEV-BACKEND] 2 US livrées, build vert. (58%)
[QA] API Gate PASS (24/24 tests). (66%)
[DEV-FRONTEND] 2 US livrées, fidelity 95%. (78%)
[QA] Coverage 82% ≥ 80%, verdict 🟢. (88%)
[CODE-REVIEW] 🟢 0 issue critique. (91%)
[SPEC-REVIEW] 🟢 6/6 AC vérifiés. (94%)
[SECURITY] 🟢 0 hard-blocking. (96%)
[DONE] FEAT 1-Auth livrée — 🟢 GREEN. (100%)
```

## 3. Combinaison des modes

| `SDD_CHAT_VERBOSE` | `SDD_CHAT_MINIMAL` | Effet |
|:---:|:---:|---|
| (vide) | (vide) | Mode executive standard v7.0.0 |
| `1` | (vide) | Mode verbose legacy v6 |
| (vide) | `1` | Mode minimal CI/CD |
| `1` | `1` | **VERBOSE wins** (debug prevails) — un WARN stderr signale la collision |

## 4. Erreurs en mode minimal

Les erreurs `🔴 [AGENT/FAIL]` restent émises (1 ligne — déjà conforme au
format minimal `output-protocol.md §7.2`). Les warnings `🟡 [AGENT/WARN]`
sont émis aussi (coût info précieux même en minimal). Seuls les updates de
progression intermédiaires sont supprimés.

## 5. Detection runtime

Chaque agent vérifie `os.environ.get("SDD_CHAT_MINIMAL", "")` au début
de son exécution. Si truthy (`1`/`true`/`yes`/`on`), bascule en mode
minimal : ne loggue que (a) ligne de résultat finale + (b) erreurs/warnings.

Les commandes orchestratrices (`/sdd-full`, `/dev-run`) propagent
l'env var aux sub-agents (héritée par défaut via subprocess).

## 6. Pointeurs

- `rules/output-protocol.md §10.bis` — pointeur résident dans la rule
- `rules/output-protocol.md §2/§7` — formats canoniques (inchangés en minimal)
