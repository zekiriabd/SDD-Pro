# MCP Server — Exposing SDD_Pro to MCP clients

> **Framework version** : v7.0.0-alpha (branche `next`).
> **MCP server status** : 🟢 **stable since v6.9.0** (Sprints MCP-1, MCP-2, MCP-3 complets). Aucun BREAKING en v7.0.0 sur l'API MCP — les 14 tools livrés v6.9 sont préservés.
> **Source** : Audit comparatif Taskmaster (mai 2026) — 37 MCP tools observés.
> **Cible** : Cursor, Windsurf, Cline, Claude Desktop, n8n/Make, scripts CI.
> **Zéro modification du cœur** (agents, règles, taxonomie, pipeline).
> **Implémentation** : `.claude/python/sdd_mcp/` (stdlib pure, 0 dépendance
> externe — protocole JSON-RPC implémenté à la main, ~1000 LOC).
> **98 tests pytest dédiés**, 570 tests totaux passent (vs 472 baseline pré-MCP).
>
> ## Récap livré
>
> | Sprint | Livrable | Module | Tests |
> |---|---|---|---|
> | MCP-1 | 7 tools read-only Phase 1 | `tools/status.py` + `tools/us_ops.py` | 45 |
> | MCP-2 | 7 tools LLM-driven (sync + async) | `tools/pipeline.py` + `claude_invoker.py` + `job_store.py` | 38 |
> | MCP-3a | HTTP transport opt-in | `http_server.py` | 13 |
> | MCP-3b | MCPB bundle Claude Desktop | `build_mcpb.py` | 2 |

---

## 1. Vision & contraintes

### 1.1 Ce que ça apporte

Aujourd'hui SDD_Pro est consommable **uniquement depuis Claude Code** (slash
commands `.claude/commands/*.md` interprétés par l'agent système). Cette
limitation ferme l'écosystème :

- ❌ Cursor / Windsurf / Cline / Roo ne peuvent pas appeler `/sdd-full`.
- ❌ Orchestrateurs externes (CI hors-scope mais aussi Make/n8n/Zapier) ne
  peuvent pas piloter `/sdd-status` pour monitoring.
- ❌ Autres clients MCP (Claude Desktop natif, app personnalisée) idem.

Un **serveur MCP** expose les commandes SDD comme **tools standards**, lisibles
par tout client implémentant le protocole MCP (Model Context Protocol). Le
cœur du framework reste **intouché** : les agents Claude (Opus 4.7, Sonnet
4.6, Haiku 4.5) sont toujours invoqués par le serveur MCP via un mécanisme
configurable (Phase 2 ci-dessous).

### 1.2 Contraintes non-négociables

| # | Contrainte | Pourquoi |
|---|---|---|
| 1 | **Aucune modification** du cœur (agents `.md`, règles, taxonomie d'erreur, templates) | Le serveur MCP est une **surface d'invocation**, pas un fork du framework |
| 2 | **Agents restent Claude-centric** | Prompts taillés Opus 4.7/Sonnet 4.6/Haiku 4.5 ; multi-provider casserait l'optimisation tokens |
| 3 | **Python stdlib pure** (cohérent v6.x) | Pas de Node.js, pas de fastmcp comme Taskmaster ; ajout léger acceptable (`mcp` SDK officiel Python) |
| 4 | **Pas de réseau sortant** par défaut | Working agreement §11 limite. MCP server **local stdio** uniquement en Phase 1. HTTP/SSE opt-in Phase 3 si demandé. |
| 5 | **Idempotence préservée** | Les tools wrappent les scripts déjà idempotents |

### 1.3 Comparaison avec Taskmaster

| Aspect | Taskmaster (MIT+CC) | SDD_Pro MCP (proposé) |
|---|---|---|
| Framework MCP | `fastmcp@3.23` (Node.js) | `mcp` SDK officiel (Python) |
| Tools exposés | 37 (CRUD tasks complet) | 4 → 9 (lecture + pipeline) |
| Distribution | npm + MCPB Claude Desktop | local stdio (v6.9), MCPB potentiel v7+ |
| Multi-provider | 21 providers | Anthropic only (par design) |
| Surface | task management générique | génération de code spec-driven |

---

## 2. Tools exposés (scope cible)

### 2.1 Phase 1 — Read-only & déterministes (faisable rapidement)

Wrappers directs autour des scripts Python existants. **Zéro LLM call**,
**zéro dépendance Claude Code**, exécution locale Python.

| Tool MCP | Wrapping | Effort | Risque |
|---|---|---|---|
| `sdd_status` | `sdd_state.py` + `phase_planner.py` (read state.json) | 1 j | 🟢 nul |
| `validate_us_deps` | `validate_us_deps.py --feat N --json` | 0.5 j | 🟢 nul |
| `compute_us_complexity` | `compute_us_complexity.py --us X --json` | 0.5 j | 🟢 nul |
| `set_us_status` | `set_us_status.py --us X --status Y` | 0.5 j | 🟢 nul |
| `migrate_us_v1_to_v2` | `migrate_us_v1_to_v2.py --all --json` | 0.5 j | 🟢 nul |
| `validate_readiness` | `validate_readiness.py {n} --json` | 1 j | 🟢 nul (read-only) |
| `feat_validate` | alias de `validate_readiness` (gate `/feat-validate`) | 0 j | 🟢 |

**Total Phase 1** : ~4 jours. Couvre **lecture + pilotage US** sans toucher
aux commandes générant du code.

### 2.2 Phase 2 — Pipeline / LLM-driven (impact + cher)

Ces tools invoquent des agents Claude → nécessitent **un mécanisme
d'invocation** :

**Option A — Claude Code CLI subprocess** (recommandé pour démarrer) :
```python
subprocess.run(["claude", "-p", "/feat-generate Auth", "--print"], ...)
```
- ✅ Réutilise la session Claude Code locale du user (auth, contexte, hooks)
- ✅ Aucun appel API direct → 0 surcoût Anthropic API
- ❌ Requiert `claude` CLI installé localement
- ❌ Long-running (minutes) → pattern async + job ID

**Option B — Anthropic API direct** :
```python
anthropic.messages.create(model="claude-opus-4-7", system=AGENT_PROMPT, ...)
```
- ✅ Standalone, fonctionne sans Claude Code installé
- ❌ Duplique la logique d'invocation des agents (system prompt, tool use, hooks)
- ❌ Coûte le tokens Anthropic indépendamment de la subscription Claude Code

**Option C — Stub informationnel** :
```python
return {"action": "run /sdd-full 1 in Claude Code", "guide": "..."}
```
- ✅ Trivial à implémenter
- ❌ N'exécute rien — le client doit avoir Claude Code de toutes façons

| Tool MCP | Phase 2 option recommandée | Effort | Risque |
|---|---|---|---|
| `feat_generate` | A (claude CLI) ; params upfront pour skip interactive | 2 j | 🟡 dépendance externe |
| `us_generate` | A (claude CLI) | 1 j | 🟡 |
| `sdd_full` | A async + job-id + `get_sdd_full_status` tool | 3 j | 🔴 long-running |

**Total Phase 2** : ~6 jours. Wraps les commandes LLM-driven.

### 2.3 Phase 3 — Distribution & opt-ins (futur)

- HTTP/SSE transport (au lieu de stdio local) — utile pour orchestrateurs distants
- MCPB bundle Claude Desktop (one-click install à la Taskmaster)
- Multi-tenant / auth basique
- Pas planifié v6.9

---

## 3. Architecture proposée

### 3.1 Localisation

```
.claude/python/
  ├── sdd_lib/                  # existant, inchangé
  ├── sdd_scripts/              # existant, inchangé
  ├── sdd_admin/                # existant, inchangé
  ├── sdd_hooks/                # existant, inchangé
  └── sdd_mcp/                  # NOUVEAU (v6.9)
      ├── __init__.py
      ├── server.py             # entry point MCP server (stdio)
      ├── tools/
      │   ├── status.py         # sdd_status, validate_readiness
      │   ├── us_ops.py         # set_us_status, compute_complexity, migrate, validate_deps
      │   └── pipeline.py       # feat_generate, us_generate, sdd_full (Phase 2)
      └── claude_invoker.py     # abstraction over Option A/B/C
```

### 3.2 Invocation

```bash
# Local stdio (par défaut)
python -m sdd_mcp.server

# Avec config explicite
python -m sdd_mcp.server --config ~/.sdd/mcp.yml
```

### 3.3 Manifest MCP

`mcp.json` à publier dans le repo (consommé par Cursor/Windsurf) :
```json
{
  "name": "sdd-pro",
  "version": "6.9.0",
  "command": "python",
  "args": ["-m", "sdd_mcp.server"],
  "cwd": "${workspaceFolder}",
  "transport": "stdio"
}
```

### 3.4 Dépendances Python

- `mcp` (SDK officiel Anthropic, Python) — **nouvelle dep**. Acceptable car
  isolée au module `sdd_mcp/`, le reste du framework reste stdlib pure.
- Si refus de dep externe : implémenter le protocole MCP à la main (JSON-RPC
  sur stdio, ~200 lignes). Faisable car protocole simple.

---

## 4. Compatibilité clients

| Client | Support testé | Note |
|---|---|---|
| Claude Code | ✅ natif (slash commands déjà OK) | MCP utile pour exposer aussi à d'autres |
| Cursor | ✅ MCP supporté (.cursor/mcp.json) | Cible #1 (Taskmaster utilise déjà ça) |
| Windsurf | ✅ MCP supporté | Cible #2 |
| Cline / Roo (VSCode) | ✅ MCP supporté | Cible #3 |
| Claude Desktop | ✅ MCP natif | Distribution MCPB bundle envisageable Phase 3 |
| Orchestrateurs (Make/n8n) | 🟡 via wrapper HTTP | Phase 3 |

---

## 5. Risques & mitigation

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Drift entre script Python et tool MCP | 🟡 moyen | 🟡 moyen | Tests pytest dédiés `tests/test_mcp_*.py` |
| Surcharge maintenance (2 surfaces) | 🟡 moyen | 🟡 moyen | Phase 1 zero LLM ; les tools wrap directement les scripts |
| Phase 2 instable (`claude` CLI subprocess) | 🟡 moyen | 🟡 moyen | Option A en best-effort + Option B en fallback documenté |
| Dépendance `mcp` SDK casse | 🟢 faible | 🟡 moyen | Pin version dans `pyproject.toml` du module `sdd_mcp/`, isolé |
| `sdd-full` async + job-id complexe | 🟡 moyen | 🔴 élevé | Reporter Phase 2.b si timing serré ; livrer Phase 1 + outils non-bloquants Phase 2 d'abord |

---

## 6. Plan d'exécution v6.9

### 6.1 Sprint MCP-1 (sem. 1-2, ~5 j)

- T-MCP1 : scaffold `sdd_mcp/` + `server.py` stdio + `mcp.json` manifest (1 j)
- T-MCP2 : 7 tools read-only Phase 1 (3 j)
- T-MCP3 : tests pytest `test_mcp_tools.py` (1 j)
- Livrable : MCP server avec 7 tools, testable depuis Cursor

### 6.2 Sprint MCP-2 (sem. 3-4, ~6 j)

- T-MCP4 : `claude_invoker.py` (subprocess `claude` CLI, abstraction) (2 j)
- T-MCP5 : tools `feat_generate`, `us_generate` (synchrone) (2 j)
- T-MCP6 : tool `sdd_full` async + job-id + polling tool (2 j)
- Livrable : MCP server avec 10 tools, suite complète

### 6.3 Sprint MCP-3 (sem. 5-6, optionnel)

- T-MCP7 : MCPB bundle Claude Desktop (à la Taskmaster) (3 j)
- T-MCP8 : HTTP/SSE transport opt-in (3 j)
- Livrable : distribution one-click

---

## 7. KPIs de succès v6.9

| Métrique | Cible |
|---|---|
| Tools MCP exposés | ≥ 7 (Phase 1) → ≥ 10 (Phase 2) |
| Clients testés | Claude Code + Cursor + Windsurf |
| Latence tool simple (sdd_status) | < 300ms |
| Tests pytest tools | ≥ 30 |
| Régression sur 472 tests v6.8 | 0 |
| Surcoût tokens runtime existant (`/sdd-full` legacy) | 0 (le serveur MCP est additif) |

---

## 8. Décisions explicites à prendre avant Sprint MCP-1

1. **Dep externe `mcp` SDK ou implémentation maison ?**
   - Dep : +1 install requirement, suit l'évolution officielle Anthropic
   - Maison : zéro dep mais ~200 lignes de protocole JSON-RPC à maintenir
2. **Phase 2 — Option A subprocess `claude` ou B Anthropic API direct ?**
   - A est plus simple, B est plus standalone
3. **MCP server lancé manuellement ou auto-start ?**
   - Manuel : `python -m sdd_mcp.server` (sûr)
   - Auto : daemon `~/.sdd/mcp.pid` (plus pratique mais introduit du state)
4. **Versioning du manifest `mcp.json`** : aligné v6.9.0 ou versionné indépendamment ?

---

## 9. Hors scope explicite v6.9

- ❌ Multi-tenant / auth (server local mono-user)
- ❌ Telemetry MCP (séparé du `record_token_usage.py` existant)
- ❌ HTTP/SSE en Phase 1 (stdio only)
- ❌ Migration des autres slash commands (`/feat-deepen`, `/dev-plan`,
  `/dev-run`, `/qa-generate`, `/arch-init`, `/doc-refresh`,
  `/sdd-discover-stack`, `/sdd-profile`) — pourra arriver v6.10+ une fois
  Phase 1+2 stables
- ❌ Provider Grok/OpenAI/Gemini (par design, agents Claude-only)

---

## Annexe — Mapping commandes Taskmaster ↔ tools MCP envisagés

Pour référence, voici les 37 tools MCP de Taskmaster regroupés par catégorie,
avec l'équivalent SDD_Pro pertinent :

| Taskmaster | SDD_Pro équivalent (v6.9 plan) |
|---|---|
| `initialize-project`, `models`, `rules` | (hors scope — config se fait via `stack.md`) |
| `parse-prd` | `feat_generate` (Phase 2) |
| `add-task`, `update-task`, `expand-task` | (pas dans v6.9 — pas de tasks dans SDD_Pro) |
| `set-task-status`, `next-task` | `set_us_status`, `validate_us_deps --topo` (Phase 1) |
| `analyze`, `complexity-report` | `compute_us_complexity` (Phase 1) |
| `research` | (hors scope — réseau sortant non autorisé) |
| `get-operation-status` | `get_sdd_full_status` (Phase 2 async) |

Le mapping confirme que SDD_Pro **n'imite pas** Taskmaster : il expose son
propre vocabulaire (FEAT → US → code) via MCP, pas un task management
générique.
