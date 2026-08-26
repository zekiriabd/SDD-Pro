# ADR — Multi-harness & multi-provider migration (PLAN ARCHIVED / DONE)

> **Statut** : ✅ **COMPLETED 2026-07-26** (archivé depuis
> `MIGRATION-PLAN-multi-harness-multi-provider.md` racine).
>
> **Ce document est conservé comme trace historique du plan initial** —
> ne pas éditer pour spécifier de nouvelles décisions. Pour toute évolution
> multi-harness/multi-provider, créer un NOUVEL ADR sous
> `.sdd/docs/adrs/ADR-{timestamp}-{decision}.md`.
>
> ## Statut de réalisation par item du plan
> - ✅ Foyer neutre `.sdd/` en place (agents/, commands/, rules/, docs/, python/, providers/, stacks/, templates/).
> - ✅ Façades jetables `.claude/`, `.codex/`, `.gemini/` régénérables via `.sdd/harness_build.py`.
> - ✅ Abstraction `model_tier: deep|balanced|fast` déployée sur les 25 pivots agents.
> - ✅ 4 providers YAML (`anthropic`, `openai`, `google`, `moonshot`).
> - ✅ Bi-root paths (`sdd_lib/paths.py::sdd_home()`).
> - ✅ Suppression du shim `.claude/python/` (commit `44a6509`).
> - ✅ 5 fixes d'audit post-migration (commits `ca4b015..38f5401`) : bug
>   `_MemoryVariantAdapter._command_pivots` `.cmd.yaml→.md`, purge
>   `.claude/python` résiduels dans 21 fichiers, alignement chiffres
>   entrypoint-body.md (188→189 err, 38→40 cmd, 23→25 agents, 35→36 stacks),
>   `_rewrite_at_includes` brace-safe, config-keys test bi-root.
>
> ## Statut backlog (non couvert par la migration initiale)
> - ⏳ Câblage `spawn_agent.py` aux prompts Codex/Gemini (Phase 3+).
> - ⏳ Gate CI byte-strict harness-parity (invariant #14 — voir `.sdd/INVARIANTS.yml`).
> - ⏳ Fixture FEAT `1-CalcABC.md` sous `.sdd/experiments/conformance/feats/`.
> - ⏳ Tests unitaires `conformance_run.py` (0 test à date).
>
> **Périmètre initial** : framework SDD-Pro v7.0.0 GA.
> **Baseline de non-régression** : bench CalcABC — 21 déclinaisons.
> **Plan rédigé** : 2026-07-24. **Migration close** : 2026-07-26.

---

## 1. Résumé exécutif

SDD-Pro est aujourd'hui **soudé à Claude Code** par sa couche de contrôle
(`.claude/` : 25 agents, 40 commandes, 11 rules, 13 skills, 328 références
lazy-load `@.claude/…`) et par des **IDs de modèles Anthropic hardcodés**
(7 agents `claude-opus-4-8`, 18 agents `claude-sonnet-4-6`, + 41 fichiers
`.md/.yml/.py/.json` citant ces IDs). En revanche, **le moteur réel est déjà
portable** : les 331 scripts Python sous `.claude/python/` sont harness-neutres
(0 token, 0 API Claude), les protections vivent dans les scripts + CI (les
hooks runtime ne sont **pas câblés** — `settings.json` ne contient que des
`permissions`, aucune clé `hooks`), et 100 scripts passent déjà par un
résolveur central `sdd_lib/paths.py`.

La cible : **un foyer neutre unique `.sdd/`** (SSoT versionné, édité à la
main) + **des façades générées jetables** (`.claude/`, `.codex/`, `.gemini/`)
produites par un transpileur `harness_build.py`, avec **deux axes orthogonaux**
pilotés depuis `stack.md` : le **harnais** (Claude Code / Codex / Gemini-Antigravity)
et le **provider de modèle** (Anthropic / OpenAI / Google / Moonshot-Kimi),
reliés par une abstraction **`model_tier: deep|balanced|fast`**.

Le plan est en 6 phases (0→5), verrouillé par deux gardes majeures :
le **golden test d'identité** (Phase 2 : `.claude/` régénéré == `.claude/`
committé, à l'octet près) et le **conformance run CalcABC** (par harnais ET
par modèle). Effort global estimé : **66–94 jours-homme** (~3 à 4,5 mois à
1 ETP, parallélisable à 2 ETP à partir de la Phase 3). Le risque n°1 —
l'émulation des sous-agents isolés sous Codex — est dérisqué en Phase 0
par un prototype go/no-go **avant** tout investissement d'extraction.

---

## 2. Décision d'architecture — deux axes orthogonaux

### 2.1 Axe 1 : le HARNAIS (où tourne l'orchestration LLM)

| Harnais | Répertoire façade | Fichier mémoire | Statut cible |
|---|---|---|---|
| Claude Code | `.claude/` (généré) | `CLAUDE.md` (généré) | Référence — parité 100 % |
| Codex (OpenAI CLI) | `.codex/` (généré) | `AGENTS.md` (canonique) | Phase 3 |
| Gemini CLI / Antigravity | `.gemini/` (généré) | `GEMINI.md` (généré) | Phase 4 |

### 2.2 Axe 2 : le PROVIDER de modèle (qui exécute les tokens)

Indépendant du harnais : Claude Code peut pointer Kimi via
`ANTHROPIC_BASE_URL` ; Codex peut pointer Kimi via `base_url` OpenAI-compat.
Le choix se fait dans `stack.md ## Active Model Provider`, résolu par
`providers/*.yaml` via l'abstraction `model_tier`.

### 2.3 Invariant de conception

- `.sdd/` = **moteur** (agents, commandes, rules, templates, docs, python,
  skills, invariants, loader, adapters, providers). Seul répertoire édité.
- `.claude/`, `.codex/`, `.gemini/` = **produits de build**. En-tête
  `# GENERATED FROM .sdd/ — DO NOT EDIT`, garde CI qui rejette tout commit
  les modifiant hors `harness_build.py`.
- **Honnêteté des garanties** : chaque combinaison harnais × provider affiche
  son **niveau de protection réel** (rapport d'impact imprimé par
  `harness_build.py`, cf. §8). Jamais de dégradation silencieuse.

---

## 3. État des lieux chiffré (couplage réel mesuré sur le repo)

> Chiffres mesurés le 2026-07-24 sur `g:/Developement/Transfo/sdd-pro`
> (branche `main`, avec les modifs non commitées du module reverse).

### 3.1 Surface de contrôle Claude Code (à transpiler)

| Artefact | Volume | Couplage Claude Code |
|---|---:|---|
| Agents `.claude/agents/*.md` | 25 | Frontmatter `name/description/model/tools` + corps markdown. Modèles hardcodés : 7 × `claude-opus-4-8` (dev-backend, dev-frontend, reverse-feat-composer, reverse-sql-analyst, reverse-sql-feat-composer, reverse-tech-analyst, reverse-ui-extractor), 18 × `claude-sonnet-4-6`. |
| Commandes `.claude/commands/*.md` | 40 | **26 spawnent des sous-agents** (25 contiennent « spawn » : arch-init, dev-run, feat-validate, sdd-full, sdd-kill-server, sdd-db-reverse[-full], les 15 sdd-reverse-*, sdd-review, spec-book + `qa-generate` via `subagent_type`). Syntaxe slash-command + tool `Task/Agent` = spécifiques Claude Code. |
| Rules `.claude/rules/*.md` | 11 | 9 avec frontmatter `paths:` (path-scoped auto-load = mécanisme natif Claude Code). 2 inconditionnelles (`output-protocol`, `error-classification`). |
| Skills `.claude/skills/` | 13 + VENDORED.md | Auto-trigger = mécanisme Claude Code. **4 skills SDD-owned** (using-sddpro, starting-a-new-feat, starting-a-reverse-eng, debugging-failed-pipeline, test-driven-development, a11y-local) + **~8 skills tiers vendorés** (webapp-testing, semgrep, codeql, sarif-parsing, insecure-defaults, frontend-design, c4-model — licences Apache 2.0 / CC BY-SA 4.0 / MIT, politique de màj manuelle dans `VENDORED.md`). |
| Références lazy-load `@.claude/…` | **328** dans les `.md` de `.claude/` | Mécanisme `@import` propre à Claude Code (le user-brief en comptait 157 hors doublons ; le grep brut retourne 328 occurrences). |
| Templates `.claude/templates/` | 25 fichiers (dont `stack.md.template`, `combos.json`, 3 schémas JSON) | Neutres à ~95 % ; `claude-md-{backend,frontend,shared-lib}.template.md` génèrent des CLAUDE.md **par projet généré** → à dupliquer en AGENTS.md/GEMINI.md projet. |
| Docs `.claude/docs/*.md` | 41 | Neutres (contenu), mais truffés de refs `@.claude/`. |
| Manifests | `loader.yml` (907 l.) + `loader.reverse.yml` (368 l.), `INVARIANTS.yml` (13) + `INVARIANTS.reverse.yml` | Neutres sur le fond ; chemins `.claude/` dans les `reads:/writes:` + annotations `cache_layer` spécifiques Anthropic prompt-caching. |
| Settings | `settings.json` + `settings.local.json` (22 Ko) | **Permissions uniquement, AUCUNE clé `hooks`**. `settings.local.json` = local utilisateur, **non générable** (contient p.ex. `Bash(python:.claude/python/**)` → à migrer manuellement vers `.sdd/python/**`). |

### 3.2 Couche déterministe Python (déjà portable, à re-raciner)

| Mesure | Valeur |
|---|---:|
| Fichiers `.py` sous `.claude/python/` | **331** (sdd_scripts 56, sdd_reverse 38, sdd_lib 28, sdd_admin 20, sdd_reverse_scripts 20, sdd_hooks 19, tests 148, + pyproject) |
| Fichiers important le résolveur central `sdd_lib/paths.py` | **100** |
| Fichiers contenant un littéral `.claude` | **171** (233 occurrences de chaîne — majorité = messages d'erreur, docstrings, et chemins `templates/`, `stacks/`, `rules/` dérivés de `repo_root()`) |
| Manipulations `sys.path` (bootstrap package local) | 339 occurrences (pattern uniforme `sys.path.insert(0, parent)`) |
| Invocations `python .claude/python/...` dans les `.md` (commands + agents) | **97** |
| Point d'ancrage racine | `sdd_lib/paths.py::_looks_like_repo_root()` exige `.claude/agents/` + `.claude/commands/` + `workspace/` — **c'est LE verrou à généraliser** |
| Variable `SDD_HOME` | **inexistante aujourd'hui** (0 occurrence) |
| Tests | 144 fichiers `test_*.py` (dont `test_invariants_manifest.py`, `test_loader_contract.py`, `test_version_alignment.py`, `test_error_classification_count.py`) |

### 3.3 Références de modèles hors frontmatter agents

**41 fichiers** citent `claude-opus-4-8` / `claude-sonnet-4-6`, dont côté
Python (fonctionnel, pas seulement documentaire) :

- `.claude/python/sdd_lib/pricing.py` — table de prix par ID modèle
  (alimente cost cap `[COST_CAP_EXCEEDED]`, `[BUILD_LOOP_COST_EXCEEDED]`, ROI).
- `.claude/python/sdd_reverse/code_unit_complexity.py` — le **complexity
  router** (ADR `governance-reverse-complexity-ladder`) route Sonnet/Opus
  par unité → doit router par **tier** (`balanced`/`deep`).
- `.claude/python/sdd_hooks/record_token_usage.py` + 8 fichiers de tests
  (pricing, ROI, token usage).
- Docs/rules : mentions descriptives (architecture.md §2-§3, CLAUDE.md §4).

### 3.4 Non-générable / hors périmètre transpileur

1. `settings.local.json` (22 Ko de permissions locales) — machine-local,
   gitignoré, migration **manuelle documentée** (checklist §12).
2. `workspace/stack/stack.md` — instance gitignorée (SSoT projet, pas framework).
3. Skills tiers vendorés — copiés **tels quels** de `.sdd/skills/vendor/`
   vers la façade (pas de transpilation, juste un copy pass-through ;
   attention CC BY-SA 4.0 : conserver `LICENSE-CC-BY-SA-4.0.txt`).
4. `__pycache__/`, `sdd_pro_tools.egg-info/` — artefacts build à exclure.
5. Le plugin marketplace Anthropic (`docx`, `pdf`, `pptx`, `xlsx`) — licence
   propriétaire, installation par poste, **jamais** dans `.sdd/`.

---

## 4. Layout cible `.sdd/` (arbre)

```
.sdd/                                  # LE MOTEUR — SSoT versionné, édité à la main
├── sdd.yml                            # Manifest racine : version framework, schéma, defaults
├── agents/                            # 25 fichiers *.agent.yaml
│   ├── po.agent.yaml                  #   frontmatter neutre + body markdown embarqué
│   ├── dev-backend.agent.yaml         #   model_tier: deep (plus jamais d'ID modèle)
│   └── ...
├── commands/                          # 40 fichiers *.cmd.yaml
│   ├── sdd-full.cmd.yaml              #   déclare: args, flags, steps, spawns: [po, arch...]
│   └── ...
├── rules/                             # 11 rules (frontmatter paths: conservée,
│   └── ...                            #   traduite par adaptateur si le harnais le supporte)
├── skills/
│   ├── sdd/                           # 6 skills SDD-owned (source neutre)
│   └── vendor/                        # ~8 skills tiers (copy pass-through + licences)
├── templates/                         # 25 templates (stack.md.template enrichi §7)
│   └── memory/                        # ex claude-md-*.template.md → memory-*.template.md
├── docs/                              # 41 docs (+ adrs/, rubrics/)
├── stacks/                            # 36 stacks (inchangés, neutres)
├── python/                            # les 331 scripts (déplacés depuis .claude/python/)
│   ├── sdd_lib/ sdd_scripts/ sdd_hooks/ sdd_admin/
│   ├── sdd_reverse/ sdd_reverse_scripts/ tests/
│   └── pyproject.toml
├── providers/                         # NOUVEAU — axe 2
│   ├── anthropic.yaml
│   ├── moonshot.yaml
│   ├── openai.yaml
│   └── google.yaml
├── adapters/                          # NOUVEAU — axe 1 (code du transpileur)
│   ├── base.py                        #   contrat AdapterBase (émission + rapport d'impact)
│   ├── claude.py                      #   Phase 2 (mode identité d'abord)
│   ├── codex.py                       #   Phase 3
│   └── gemini.py                      #   Phase 4
├── harness_build.py                   # CLI du transpileur (lit stack.md → adaptateur)
├── invariants.yml                     # 13 + reverse + NOUVEAU harness-parity (n°14)
├── loader.yml                         # + loader.reverse.yml (chemins re-racinés .sdd/)
└── capabilities.yml                   # NOUVEAU — matrice harnais × mécanismes (SSoT du §7)

# FAÇADES GÉNÉRÉES (jetables, read-only, en-tête DO NOT EDIT)
.claude/   → agents/*.md, commands/*.md, rules/*.md, skills/, settings.json (permissions de base)
.codex/    → prompts/*.md, config.toml, scripts d'émulation sous-agents
.gemini/   → commands/*.toml, config
CLAUDE.md  # généré (superset Claude Code : @imports, skills auto-trigger)
AGENTS.md  # généré (canonique neutre — standard ouvert agents.md)
GEMINI.md  # généré (superset Gemini/Antigravity)
```

### 4.1 Format pivot `*.agent.yaml` (schéma)

```yaml
# .sdd/agents/dev-backend.agent.yaml
schema: sdd.agent/v1
name: dev-backend
description: >
  Agent Dev-Backend — pour UNE US donnée...
model_tier: deep                # deep | balanced | fast (JAMAIS un ID modèle)
tools: [Read, Write, Edit, Glob, Grep, Bash, Skill]
context:
  reads: [...]                  # hoisté depuis loader.yml (ou référence croisée)
  writes: [...]
harness_hints:                  # optionnel, par harnais — dégradations documentées
  codex:
    spawn_mode: exec-isolated   # cf. §7 et prototype Phase 0
body: |
  # Agent Dev-Backend — ... (le markdown actuel, inchangé,
  # avec les refs @.claude/ réécrites en {{SDD_HOME}}/… au moment de l'extraction)
```

### 4.2 Format pivot `*.cmd.yaml`

```yaml
# .sdd/commands/sdd-full.cmd.yaml
schema: sdd.cmd/v1
name: sdd-full
args: "{n}"
flags: [--force, --rebuild-arch, --resume, --manual-gates, ...]
spawns: [po, arch, dev-backend, dev-frontend, qa, code-reviewer, ...]  # extrait des 26 cmd spawnantes
body: |
  # /sdd-full — Pipeline complet de A à Z pour 1 FEAT
  ...
```

> **Choix assumé** : le body markdown reste la substance (pas de réécriture
> des prompts). Le YAML n'ajoute que les métadonnées nécessaires à la
> transpilation (`model_tier`, `spawns`, `harness_hints`). Migration
> mécanique scriptable (extracteur one-shot `.md` → `.agent.yaml`).

---

## 5. Mécanisme de résolution `SDD_HOME`

### 5.1 Contrat

- Variable d'environnement `SDD_HOME` (défaut : `<repo_root>/.sdd`).
- **Windows : AUCUN symlink.** Résolution = chemins relatifs + env var.
- Tous les scripts résolvent via `sdd_lib/paths.py` — jamais `.claude/` en dur.

### 5.2 Modifications précises dans `paths.py` (le seul point chaud)

`_looks_like_repo_root()` (l.33-58) exige aujourd'hui
`.claude/agents/` + `.claude/commands/` + `workspace/`. Cible :

```python
def sdd_home(repo_root=None) -> Path:
    env = os.environ.get("SDD_HOME")
    if env: return Path(env).resolve()
    return _repo_root(repo_root) / ".sdd"

def _looks_like_repo_root(p: Path) -> bool:
    # accepte .sdd/ (nouveau) OU .claude/ (legacy, période de transition)
    has_sdd    = (p / ".sdd" / "agents").is_dir() and (p / ".sdd" / "commands").is_dir()
    has_legacy = (p / ".claude" / "agents").is_dir() and (p / ".claude" / "commands").is_dir()
    ...
```

Impact en cascade mesuré :
- **100 fichiers** importent `paths.py` → gagnent `sdd_home()` gratuitement.
- **171 fichiers** contiennent un littéral `.claude` (233 occurrences) → audit
  ligne-à-ligne : ~60 % sont des chemins fonctionnels (`templates/`, `stacks/`,
  `rules/`, `loader.yml`) à réécrire `paths.sdd_home() / "templates/..."` ;
  ~40 % sont des messages/docstrings (réécriture cosmétique, non bloquante).
- **97 invocations** `python .claude/python/...` dans les `.md` de commandes/
  agents → deviennent `python {{SDD_PYTHON}}/...` dans le pivot, matérialisées
  par l'adaptateur (`.claude/` généré émettra `python .sdd/python/...`).
- `settings.local.json` : la permission `Bash(python:.claude/python/**)` doit
  devenir `Bash(python:.sdd/python/**)` — **manuel**, documenté.
- Garde CI : nouveau test `test_no_hardcoded_claude_paths.py` (grep-gate :
  0 littéral `.claude/` fonctionnel dans `sdd_*` hors couche `adapters/claude.py`).

### 5.3 Période de transition (Phases 1→2)

Pendant la Phase 1, `.claude/` reste le répertoire servi à Claude Code
(comportement inchangé) mais son contenu **provient** de `.sdd/` (d'abord
copie committée à la main, puis générée en Phase 2). Le résolveur accepte
les deux racines ; le test golden verrouille l'équivalence.

---

## 6. Nommage des fichiers mémoire : CLAUDE.md / AGENTS.md / GEMINI.md

| Fichier | Rôle | Généré depuis |
|---|---|---|
| `AGENTS.md` | **Canonique neutre** (standard ouvert agents.md, lu par Codex et de plus en plus d'outils). Contenu : conventions de nommage, IDs stables, pipeline, invariants — SANS mécanismes propres à un harnais. | `.sdd/templates/memory/core.md.tmpl` + injection capacités |
| `CLAUDE.md` | Superset Claude Code = AGENTS.md + refs `@.sdd/docs/...` (lazy-load), déclaration skills auto-trigger, labels output-protocol. **On n'édite plus CLAUDE.md à la main.** | idem + bloc adapter Claude |
| `GEMINI.md` | Superset Gemini/Antigravity (mémoire GEMINI.md native, syntaxe commandes `.toml`). | idem + bloc adapter Gemini |

Idem pour les **projets générés** : les templates
`claude-md-{backend,frontend,shared-lib}.template.md` (3 fichiers) deviennent
`memory-{backend,frontend,shared-lib}.template.md` neutres, et l'agent `arch`
matérialise le(s) fichier(s) mémoire du harnais actif (CLAUDE.md et/ou
AGENTS.md et/ou GEMINI.md) dans `workspace/src/{App}/`.

Règle de drift : les 3 fichiers racine portent l'en-tête généré + le hash du
build (`harness_build.py --stamp`) ; la garde CI échoue si le hash ne
correspond pas à `.sdd/` HEAD.

---

## 7. Matrice d'impact

### 7.1 Harnais × mécanismes SDD-Pro

Légende : 🟢 natif / 🟡 émulé (dégradation contrôlée) / 🔴 absent (report CI-time).
SSoT machine cible : `.sdd/capabilities.yml` (consommé par `harness_build.py`
pour imprimer le rapport d'impact).

| Mécanisme SDD-Pro | Claude Code | Codex | Gemini CLI / Antigravity | Stratégie de repli |
|---|:---:|:---:|:---:|---|
| Sous-agents isolés + parallélisme borné (`MaxParallel: 3`) — 26 commandes spawnantes | 🟢 tool Task/Agent natif | 🟡 émulation `codex exec` (sous-processus CLI, contexte isolé par construction) — **RISQUE #1, prototype Phase 0** | 🟡 émulation équivalente (`gemini -p` non-interactif) ; Antigravity a des agents mais API d'orchestration différente | Wrapper Python `sdd_scripts/spawn_agent.py` : lance le CLI du harnais en sous-processus avec prompt agent + budget ; parallélisme via `concurrent.futures` borné |
| Hooks bloquants runtime (PreToolUse/SubagentStop) | 🟢 (disponible ; **aujourd'hui non câblé** — settings.json = permissions seulement, 19 scripts `sdd_hooks/` invoqués par scripts/CI) | 🔴 pas d'équivalent hook | 🔴 idem | Déjà la réalité de fait : protections = scripts Python + CI. Reporter les gates au wrapper de spawn (pre/post-exec) + CI. **Perte réelle : blocage intra-session interactif** → affichée dans le rapport d'impact |
| Skills auto-trigger (13 skills) | 🟢 natif | 🔴 (AGENTS.md peut lister les workflows, pas d'auto-trigger) | 🟡 (extensions/context, partiel) | Injection statique : l'adaptateur inline le contenu des 4-6 skills SDD-owned critiques (using-sddpro, TDD) dans AGENTS.md/prompts ; les skills outillés (semgrep, codeql) deviennent des commandes explicites |
| Lazy-load `@file` (328 refs) | 🟢 natif | 🔴 | 🟡 (`@` supporté par Gemini CLI dans les prompts, pas en mémoire — à confirmer) | Adaptateur : soit inline (coût contexte ↑), soit consigne « Read X avant STEP n » (les agents le font déjà explicitement — cf. note TOK-C1 : la frontmatter `paths:` ne fait qu'éviter la redondance) |
| Slash-commands (40) | 🟢 `.claude/commands/*.md` | 🟡 `.codex/prompts/*.md` (custom prompts) | 🟢 `.gemini/commands/*.toml` (natif) | Transpilation directe par adaptateur |
| Rules path-scoped (frontmatter `paths:`, 9/11) | 🟢 natif | 🔴 | 🔴 | Repli = chargement inconditionnel dans AGENTS.md (coût contexte) OU consigne Read explicite (déjà en place dans les agents) |
| Python déterministe (331 scripts, gates, validate_*, build_loop) | 🟢 | 🟢 | 🟢 | Aucun repli nécessaire — c'est le cœur portable |
| MCP | 🟢 | 🟢 | 🟢 | — |
| Prompt caching (annotations `cache_layer` loader.yml) | 🟢 Anthropic | 🟡 (caching implicite OpenAI) | 🟡 (context caching Gemini, API différente) | Annotations conservées dans `.sdd/loader.yml`, appliquées seulement si provider=anthropic ; sinon ignorées (info dans rapport d'impact : « estimation coût sans cache ») |
| Permissions allowlist | 🟢 settings.json | 🟡 sandbox/approval Codex (config.toml `approval_policy`) | 🟡 (settings Gemini) | Adaptateur traduit un noyau minimal ; le reste = responsabilité locale |

### 7.2 Harnais × provider Kimi/Moonshot (état 24/07/2026 — IDs à confirmer)

| Harnais | Compat Kimi | Mécanisme | Verdict |
|---|:---:|---|---|
| Claude Code | 🟢 | Endpoint **Anthropic-compat** Moonshot : `ANTHROPIC_BASE_URL=https://api.moonshot.ai/anthropic` (à confirmer) + `ANTHROPIC_API_KEY` Moonshot | Testé en priorité (conformance run §10) |
| Codex | 🟢 | Endpoint **OpenAI-compat** : `base_url` dans `config.toml` | Phase 3+ |
| Gemini CLI / Antigravity | 🟡 | Pas de compat native → proxy de traduction (LiteLLM ou équivalent) | Optionnel, hors SLA initial |

### 7.3 Principe d'honnêteté (rapport d'impact obligatoire)

`harness_build.py` termine TOUJOURS par un rapport imprimé + persisté
(`workspace/.sys/harness-impact.md`) :

```
HARNESS BUILD REPORT — harness=codex, provider=moonshot
  Protections runtime :  6/9 natives, 2 émulées (wrapper), 1 reportée CI-time
  ⚠ Hooks bloquants intra-session : ABSENTS sous codex → gates déplacés au wrapper spawn_agent
  ⚠ Skills auto-trigger : INJECTION STATIQUE (TDD, using-sddpro) — pas de déclenchement contextuel
  ⚠ Provider moonshot : sorties JSON schema-strict = fidélité 94% au dernier conformance run
     (2026-07-xx) — build_loop moyen 1.8 iter vs 1.2 (anthropic)
  Niveau de protection global : B (vs A sous claude-code/anthropic)
```

Ce rapport est un **artefact contractuel** (même logique que les combos SLA
§6 de CLAUDE.md) : un combo harnais × provider non conformance-testé est
marqué `UNTESTED` et exige `SDD_ALLOW_UNTESTED_HARNESS=1` (audit-loggué),
symétrique du hook `preflight_stack_combo` existant.

---

## 8. Abstraction `model_tier` + providers pluggables

### 8.1 Les 3 tiers et le mapping actuel

| Tier | Sémantique | Agents concernés (mesuré) |
|---|---|---|
| `deep` | Raisonnement long, génération de code, synthèse transverse | 7 agents : dev-backend, dev-frontend, reverse-tech-analyst, reverse-feat-composer, reverse-ui-extractor, reverse-sql-analyst, reverse-sql-feat-composer |
| `balanced` | Structuration, review, extraction bornée | 18 agents : po, arch, qa, elicitor, constitutioner, les 5 auditors, specbook-writer, reverse-* restants |
| `fast` | Tâches courtes/routage (réservé — aucun agent aujourd'hui, ouvre le levier coût) | 0 (candidats futurs : reverse-clarifier, statusline) |

### 8.2 Schéma `providers/*.yaml`

```yaml
# .sdd/providers/anthropic.yaml
schema: sdd.provider/v1
name: anthropic
api_format: anthropic                # anthropic | openai | google
base_url: https://api.anthropic.com # défaut SDK
auth_env: ANTHROPIC_API_KEY
tiers:
  deep:     { model: claude-opus-4-8,   context_window: 200000, max_output: 32000 }
  balanced: { model: claude-sonnet-4-6, context_window: 200000, max_output: 16000 }
  fast:     { model: claude-haiku-4-5,  context_window: 200000, max_output: 8000 }
pricing:                             # alimente sdd_lib/pricing.py (source unique)
  claude-opus-4-8:   { in_per_mtok: 15.00, out_per_mtok: 75.00 }   # à confirmer
  claude-sonnet-4-6: { in_per_mtok:  3.00, out_per_mtok: 15.00 }   # à confirmer
capabilities:
  structured_output_fidelity: high   # high | medium | low — nourrit le rapport d'impact
  tool_calling: native
  prompt_caching: anthropic-ephemeral
  thinking: configurable
```

```yaml
# .sdd/providers/moonshot.yaml   (état 24/07/2026 — série K2 classique retirée 25/05/2026)
schema: sdd.provider/v1
name: moonshot
api_format: anthropic               # endpoint Anthropic-compat (aussi openai — cf. endpoints)
endpoints:
  anthropic: https://api.moonshot.ai/anthropic   # à confirmer
  openai:    https://api.moonshot.ai/v1          # à confirmer
auth_env: MOONSHOT_API_KEY
tiers:
  deep:     { model: kimi-k3,        context_window: 1000000, notes: "thinking always-on" }  # à confirmer
  balanced: { model: kimi-k2.7-code, context_window: 256000,  notes: "coding-tuné" }         # à confirmer
  fast:     { model: kimi-k2.5,      context_window: 128000 }                                # à confirmer
pricing: { }                        # à renseigner avant tout run cost-cappé (sinon [TELEMETRY_UNAVAILABLE])
capabilities:
  structured_output_fidelity: to-measure    # verdict du conformance run §10
  tool_calling: anthropic-compat
  prompt_caching: none
```

### 8.3 Sections `stack.md` (les 2 axes — ajout au template, l.~34 avant `## Project Config`)

```markdown
## Active Harness
Harness: claude-code            # claude-code | codex | antigravity | gemini-cli

## Active Model Provider
Provider: anthropic             # anthropic | openai | google | moonshot
Endpoint: default               # default | url custom (proxy interne)
ModelTierMap:                   # override optionnel par tier — MIXAGE cross-provider permis
  deep: anthropic               #   ex. deep sur Claude, balanced/fast sur Kimi = levier coût
  balanced: moonshot
  fast: moonshot
```

Règles de résolution (implémentées dans `sdd_lib/model_resolver.py`, NOUVEAU) :
1. agent → `model_tier` (depuis `.agent.yaml`) ;
2. tier → provider (via `ModelTierMap`, défaut = `Provider:`) ;
3. provider → ID modèle + endpoint + auth (via `providers/{p}.yaml`) ;
4. le résolveur est appelé par : l'adaptateur (matérialise `model:` dans les
   façades), `code_unit_complexity.py` (router Sonnet/Opus → `balanced`/`deep`),
   `pricing.py` (coût par tier), `record_token_usage.py`.

### 8.4 Points de code à modifier (chiffré)

| Fichier | Modification |
|---|---|
| 25 × `.sdd/agents/*.agent.yaml` | `model:` → `model_tier:` (extraction mécanique) |
| `sdd_lib/pricing.py` | table → chargée depuis `providers/*.yaml` (une seule source) |
| `sdd_reverse/code_unit_complexity.py` | sorties `claude-sonnet-4-6`/`claude-opus-4-8` → `balanced`/`deep` |
| `sdd_hooks/record_token_usage.py` | mapping ID→tier inversé (télémétrie par tier ET par ID) |
| ~11 fichiers de tests (pricing, ROI, token usage) | fixtures par provider |
| Docs (~25 mentions descriptives) | réécriture cosmétique « tier deep (ex. Opus 4.8 chez Anthropic) » |

---

## 8.bis Sélection de modèle par agent : statique vs dynamique (routage par complexité)

### 8.bis.1 Constat de l'existant — 2 des 3 briques existent déjà

| Brique | État | Chemin réel |
|---|---|---|
| Modèle **fixe par agent** | ✅ En place — `model:` en frontmatter des 25 agents (7 deep / 18 balanced mesurés, cf. §8.1) | `.claude/agents/*.md` |
| **Scoreur déterministe de complexité** (0 token, < 50 ms, idempotent, 10 signaux : SFD/BR/AC/acteurs/compliance…) | ✅ En place — MAIS il route le **PIPELINE** (`/sdd-poc` / `/dev-run` / `/sdd-full` / full+review), pas le modèle par agent | `.claude/python/sdd_scripts/complexity_router.py` + rubric `.claude/docs/rubrics/complexity-router-scoring.md` (signaux critiques → force `complexity="critical"` ; override `SDD_FORCE_PIPELINE`) |
| **Routage dynamique PAR MODÈLE** | ✅ En place **côté reverse uniquement** — score chaque unité U-N → `claude-sonnet-4-6` si simple / `claude-opus-4-8` si complexe (constantes `OPUS`/`SONNET` l.37-38) | `.claude/python/sdd_reverse/code_unit_complexity.py` + ADR `governance-reverse-complexity-ladder` + rubric `.claude/docs/rubrics/reverse-complexity-routing.md` |

**Conclusion** : la glu manquante est le résolveur `sdd_lib/model_resolver.py`
(déjà prévu §8.3) qui doit combiner **(agent, complexité du work-item,
provider actif) → tier → modèle concret**. Il s'agit de **généraliser au
pipeline forward** le mécanisme déjà audité et en production dans le module
reverse — pas d'inventer un routage nouveau.

### 8.bis.2 Design : un MODE dans stack.md, pas une rupture

Nouvelle section dans `stack.md` (et son template) :

```markdown
## Model Selection
Mode: static                    # static | dynamic
```

- `static` (défaut) = comportement actuel préservé : chaque agent reçoit son
  `tier_default` fixe. **Rétrocompatible : absence de section = static.**
- `dynamic` = à chaque spawn, le scoreur déterministe calcule la complexité
  du work-item et choisit le tier — **borné par agent** (cf. 8.bis.3).

### 8.bis.3 Bornes par agent (garde-fou NON négociable)

Chaque `.agent.yaml` déclare :

```yaml
model:
  tier_default: deep        # utilisé en mode static, et point de départ en dynamic
  tier_floor:   balanced    # le routage ne descend JAMAIS en dessous
  tier_ceiling: deep        # ni au-dessus (maîtrise du coût)
```

**GARDE-FOU critique** : sans `floor`/`ceiling`, le routage dynamique peut
placer une revue sécurité ou une US critique sur `fast` = **régression
qualité silencieuse** — exactement le type de dérive que SDD-Pro proscrit.
Exemples canoniques : `security-reviewer` floor=`balanced` (8 classes
`[SEC_*]` hard-blocking — jamais un modèle fast) ; `specbook-writer` peut
être pinné `fast` (reformulation bornée) ; `dev-backend` peut descendre à
`balanced` sur une US triviale (CRUD 1 entité) mais **jamais** en dessous.
Les bornes sont des invariants de qualité, pas des préférences : elles ne
sont pas surchargeables par le Project Config (seul un changement du
`.agent.yaml`, donc un commit framework, les modifie).

### 8.bis.4 Signaux de scoring — AU GRAIN de l'agent

Le score est calculé sur le work-item que l'agent va traiter, pas sur le
projet global :

| Périmètre | Agents | Signaux (déterministes, parsés depuis les artefacts) |
|---|---|---|
| **FEAT** | po, elicitor, arch, constitutioner, specbook-writer | Réutilise les 10 signaux de `complexity_router.py` : nb SFD/BR/AC/FD, nb acteurs, mots-clés compliance/audit, intégrations externes, signaux critiques (override), Quantified Goal (signal de maturité, poids négatif) |
| **US** | dev-backend, dev-frontend, qa | LOC estimé du plan (`workspace/plans/{n}-{m}-*.md` §Files), nb d'entités touchées (schema.json), nb d'AC de l'US, nb d'opérations DB (reads/writes déclarés), transversalité (touche LibName partagée ? nb de layers), présence auth/rôles |
| **FEAT + code matérialisé** | code-reviewer, security-reviewer, spec-compliance-reviewer, arch-reviewer, adversarial-reviewer | Nb fichiers du diff, nb US de la FEAT, présence surfaces sensibles (auth, crypto, upload, SQL brut) — un diff 3 fichiers CRUD n'exige pas le même effort qu'un diff 40 fichiers multi-layer |
| **Unité U-N legacy** | reverse-* (10 agents) | **Déjà implémenté** : `code_unit_complexity.py` (taille unité, langage, nb dépendances, densité SQL…) — inchangé, seule la sortie passe d'IDs modèles à des tiers (cf. §8.4) |

### 8.bis.5 Flux de résolution (0 token, déterministe, auditable)

```
work-item ──scoreur──▶ score ──seuils──▶ niveau (low|medium|high)
   niveau ──mapping──▶ tier candidat (fast|balanced|deep)
   tier   ──clamp────▶ max(tier_floor, min(tier_candidat, tier_ceiling))
   tier   ──ModelTierMap[provider]──▶ providers/{p}.yaml ──▶ modèle concret + endpoint
```

Propriétés load-bearing :
- **0 token** : tout est Python (`model_resolver.py` + scoreurs existants).
- **Déterministe** : même entrée → même modèle. Reproductible entre runs,
  compatible cache prompt (le modèle ne « flotte » pas d'un retry à l'autre),
  testable unitairement (fixtures par niveau).
- **Auditable** : chaque décision est persistée (même pattern que le
  `{n}-complexity.json` déjà émis par `complexity_router.py`) dans
  `workspace/.sys/.routing/{n}[-{m}]-model-routing.json` :

```json
{
  "agent": "dev-backend", "work_item": "1-2-Piloter-Acces-Actions",
  "mode": "dynamic", "score": 14, "level": "low",
  "tier_candidate": "balanced", "tier_floor": "balanced", "tier_ceiling": "deep",
  "tier_final": "balanced",
  "provider": "moonshot", "model": "kimi-k2.7-code",
  "signals": { "loc_estimate": 180, "entities": 1, "acs": 3, "db_ops": 2, "cross_layer": false }
}
```

Le Tech Lead voit **pourquoi** chaque agent a reçu tel modèle ; la télémétrie
(`record_token_usage.py`) croise routing × coût réel pour objectiver le gain.

### 8.bis.6 Composition avec les 2 axes (§2)

Le scoreur choisit le **TIER** ; le provider actif traduit le tier en modèle
concret. Les deux mécanismes se composent sans interférence : on peut être
« dynamique par complexité » ET « Kimi sur balanced / Opus sur deep »
simultanément :

```markdown
## Model Selection
Mode: dynamic

## Active Model Provider
Provider: anthropic
ModelTierMap:
  deep: anthropic          # US complexes → claude-opus-4-8
  balanced: moonshot       # US simples → kimi-k2.7-code (levier coût)
  fast: moonshot
```

### 8.bis.7 Table des bornes proposées — les 25 agents

> `tier_default` dérivé mécaniquement du `model:` actuel (frontmatter lu le
> 2026-07-24). Bornes = proposition à faire valider ; les lignes marquées
> **⚠ à valider Tech Lead** sont celles où la borne basse change le
> comportement potentiel vs aujourd'hui.

| Agent | tier_default | tier_floor | tier_ceiling | Justification courte |
|---|:---:|:---:|:---:|---|
| po | balanced | balanced | deep | Découpage FEAT→US + traçabilité 100 % SFD/BR/AC = load-bearing ; deep utile sur FEAT à signaux critiques |
| arch | balanced | balanced | deep | Bootstrap + scaffolding DB = décisions structurantes ; jamais fast |
| dev-backend | deep | balanced | deep | Descente à balanced sur US triviale (CRUD 1 entité, score low) ; jamais fast (code de prod) |
| dev-frontend | deep | balanced | deep | Idem + fidélité mockup (`[UI_FIDELITY_GAP]`) ; jamais fast |
| qa | balanced | balanced | deep | Génère du code de test + verdicts bloquants (RED) ; deep sur FEAT large |
| elicitor | balanced | balanced | deep | Élicitation = raisonnement créatif guidé ; ceiling deep **⚠ à valider Tech Lead** (interactif → latence deep perceptible) |
| constitutioner | balanced | fast | balanced | Mise à jour ADRs/constitution = tâche éditoriale bornée, idempotente **⚠ à valider Tech Lead** |
| code-reviewer | balanced | balanced | deep | Raisonnement cross-fichier (N+1, async, contract drift) ; jamais fast |
| security-reviewer | balanced | balanced | deep | 8 classes `[SEC_*]` hard-blocking — le cas d'école du garde-fou floor |
| spec-compliance-reviewer | balanced | balanced | deep | « Do not trust the report », biais not-verified ; jamais fast |
| arch-reviewer | balanced | balanced | deep | Violations de pattern cross-fichier (MVC/DDD) |
| adversarial-reviewer | balanced | balanced | deep | Attaques edge-case/failure-mode = raisonnement, pas du pattern-matching ; opt-in donc coût maîtrisé |
| specbook-writer | balanced | fast | balanced | Reformulation bornée spec→prose non-IT (le frontmatter actuel le qualifie déjà ainsi) — candidat fast canonique |
| reverse-inventory | balanced | fast | balanced | Délègue au script déterministe `reverse_inventory.py`, n'enrichit que la prose **⚠ à valider Tech Lead** |
| reverse-tech-auditor | balanced | balanced | deep | Audit archi/anti-patterns/EOL = analyse |
| reverse-tech-analyst | deep | balanced | deep | 3a — **précédent existant** : déjà routé Sonnet/Opus par `code_unit_complexity.py` (ADR ladder) |
| reverse-us-writer | balanced | fast | balanced | 3b altitude-lift sans lecture code legacy (downgrade Opus→Sonnet déjà audité 2026-06-11 — même logique un cran plus bas) **⚠ à valider Tech Lead** |
| reverse-feat-composer | deep | balanced | deep | 3c synthèse transverse + démotion plomberie ; balanced sur module simple (ladder) |
| reverse-completeness-reviewer | balanced | balanced | balanced | Revue de complétude post-script déterministe — pinné balanced (ni fast : c'est un reviewer, ni deep : checklist bornée) |
| reverse-paradigm-advisor | balanced | balanced | deep | Gap de paradigme = analyse comparative legacy↔cible |
| reverse-parity-inspector | balanced | balanced | deep | Specs Gherkin de parité = contrat comportemental (load-bearing pour la migration) |
| reverse-clarifier | balanced | fast | balanced | Consolidation de gaps en questions + ré-injection mécanique — candidat fast déjà identifié §8.1 |
| reverse-ui-extractor | deep | balanced | deep | Synthèse HTML sémantique multi-templates ; balanced sur écran simple |
| reverse-sql-analyst | deep | balanced | deep | Corps T-SQL/PL-SQL complexes ; balanced sur proc simple (même ladder que le code) |
| reverse-sql-feat-composer | deep | balanced | deep | Parité avec 3c (opt-in `SDD_REVERSE_FEAT_LLM=1`) |

**Bilan** : 25 agents — **20 avec floor=balanced**, **5 avec floor=fast**
(constitutioner, specbook-writer, reverse-inventory, reverse-us-writer,
reverse-clarifier), **0 avec floor=deep** (le tier deep n'est jamais un
plancher : c'est la complexité qui l'active, dans la limite du ceiling).
19 agents ont ceiling=deep, 6 sont plafonnés balanced.

### 8.bis.8 Impact sur le plan phasé

Cette capacité s'ajoute en **Phase 1**, à côté de l'abstraction `model_tier`
(tâche 1.9 du §9) : `model_resolver.py` gagne le mode `dynamic` + la lecture
des bornes `tier_floor`/`tier_ceiling` + la persistance du routing JSON.
Les scoreurs existants (`complexity_router.py`, `code_unit_complexity.py`)
sont réutilisés tels quels (seule la sortie du second passe d'IDs modèles à
des tiers — déjà compté en §8.4). Le mode `dynamic` reste **opt-in et 🟡
UNTESTED** tant qu'un conformance run (§10) n'a pas mesuré son impact
qualité/coût par provider — `static` demeure le défaut GA.

---

## 9. Plan phasé 0 → 5

> Efforts en **jours-homme (j-h)**, fourchette basse = nominal, haute = avec
> imprévus d'audit. Dépendances strictes indiquées. Chaque phase se termine
> par sa garde (aucune phase suivante ne démarre garde rouge).

### Phase 0 — Dérisquage & gouvernance (6–9 j-h) — AUCUNE dépendance

| # | Tâche | Effort | Livrable |
|---|---|---:|---|
| 0.1 | ADR `harness-and-provider-abstraction` (2 axes, format pivot, politique façades générées read-only) | 1 | `.claude/docs/adrs/ADR-...md` (encore dans `.claude/` à ce stade) |
| 0.2 | `capabilities.yml` v0 — matrice §7.1 formalisée machine | 1 | fichier + revue Tech Lead |
| 0.3 | Invariant n°14 `harness-parity` dans INVARIANTS.yml : « toute façade committée == sortie de `harness_build.py` sur `.sdd/` HEAD » + enforcer (test golden, créé Phase 2 ; l'invariant référence l'enforcer en `planned:` jusqu'à P2) | 0,5 | INVARIANTS.yml +1 |
| 0.4 | **PROTOTYPE RISQUE #1** : émulation sous-agents Codex. Script jetable `spawn_agent_codex.py` : lancer `codex exec` en sous-processus avec (a) prompt d'un agent réel (po), (b) isolation contexte, (c) 2 spawns parallèles bornés, (d) récupération du rapport final + exit code, (e) un gate post-exec (validate_readiness.py) appliqué par le wrapper. Mesurer : isolation réelle, coût latence, fiabilité du format de sortie. | 3–5 | Rapport go/no-go + décision `spawn_mode` |
| 0.5 | Critère go/no-go documenté : GO si le wrapper obtient ≥ 95 % de complétion parseable sur 20 runs po/qa synthétiques ; NO-GO → périmètre Codex réduit à « commandes mono-agent » (dégradation affichée) et re-priorisation Gemini | 0,5 | section ADR |

**Garde de sortie** : ADR approuvé + verdict prototype consigné. Si NO-GO,
les Phases 3-4 sont re-scopées AVANT d'engager l'extraction.

### Phase 1 — Extraction du noyau neutre vers `.sdd/` (14–20 j-h) — dép. P0

Objectif : `.sdd/` devient le SSoT ; **ZÉRO changement de comportement Claude
Code** (le contenu de `.claude/` reste fonctionnellement identique).

| # | Tâche | Effort | Détail chiffré |
|---|---|---:|---|
| 1.1 | `git mv .claude/python .sdd/python` + `paths.py` : `sdd_home()`, `_looks_like_repo_root()` bi-racine (§5.2) | 2 | 1 move + 1 fichier chaud (193 l.) |
| 1.2 | Audit + réécriture des 233 littéraux `.claude` dans 171 `.py` (fonctionnels → `sdd_home()` ; cosmétiques → batch sed) + grep-gate `test_no_hardcoded_claude_paths.py` | 3–5 | 171 fichiers, ~60 % triviaux |
| 1.3 | Réécrire les 97 invocations `python .claude/python/...` dans les 65 `.md` (commands+agents) → `.sdd/python/` ; MAJ `settings.local.json` doc (manuel) ; MAJ CI (`framework_smoke.py`, workflows) | 1,5 | 97 occurrences |
| 1.4 | Extracteur one-shot `md2yaml.py` : 25 agents `.md` → `.sdd/agents/*.agent.yaml` + 40 commandes → `*.cmd.yaml` (body embarqué intact, `spawns:` extraits des 26 spawnantes) | 3 | 65 fichiers pivot générés puis committés comme source |
| 1.5 | `model:` → `model_tier:` (25 agents) + `model_resolver.py` + refactor `pricing.py` / `code_unit_complexity.py` / `record_token_usage.py` + ~11 tests | 3–4 | cf. §8.4 |
| 1.6 | `git mv` rules/templates/docs/stacks/skills/loader/invariants vers `.sdd/` ; `.claude/` conserve des **copies committées identiques** (sync manuelle temporaire — courte : Phase 2 la remplace) | 1,5 | ~130 fichiers déplacés |
| 1.7 | Ajouter les 2 sections au `stack.md.template` (§8.3) + defaults rétro-compatibles (absence de section = claude-code/anthropic) + parsing dans `sdd_lib` | 1 | 1 template + 1 parser |
| 1.8 | Providers v1 : `anthropic.yaml` complet + `moonshot.yaml` squelette (IDs « à confirmer ») | 0,5 | 2 fichiers |
| 1.9 | Mode `dynamic` du `model_resolver.py` (§8.bis) : section `## Model Selection` (défaut `static`), bornes `tier_floor`/`tier_ceiling` dans les 25 `.agent.yaml` (table §8.bis.7), clamp + persistance `model-routing.json`, généralisation des signaux US (dev-*/qa) | 2 | réutilise `complexity_router.py` + `code_unit_complexity.py` tels quels |

**Garde de sortie (bloquante)** :
1. Les **144 tests** + `framework_smoke.py` (gate `stacks-count` etc.) verts.
2. **CalcABC re-passe à l'identique** : re-run `/sdd-full` sur 1 FEAT de
   2 déclinaisons représentatives (CalcABCBackNet + CalcABCAngular) — diff
   comportemental nul (mêmes gates, mêmes verdicts, mêmes fichiers générés
   modulo timestamps).
3. `test_version_alignment.py`, `test_loader_contract.py`,
   `test_invariants_manifest.py` adaptés et verts.

### Phase 2 — `harness_build.py` + adaptateur Claude en MODE IDENTITÉ (12–16 j-h) — dép. P1

| # | Tâche | Effort |
|---|---|---:|
| 2.1 | `adapters/base.py` : contrat (emit_agents, emit_commands, emit_rules, emit_skills, emit_memory, impact_report) | 2 |
| 2.2 | `adapters/claude.py` : `.agent.yaml` → `.claude/agents/*.md` (frontmatter reconstruit, `model_tier` résolu en ID via provider actif), `.cmd.yaml` → commands, rules/skills/templates pass-through, `CLAUDE.md` généré (refs `@` réécrites `.sdd/docs/...`), en-tête `# GENERATED FROM .sdd/ — DO NOT EDIT` | 4–6 |
| 2.3 | **GOLDEN TEST** `test_harness_identity.py` : `harness_build.py --harness claude-code --provider anthropic` sur `.sdd/` HEAD → diff octet-à-octet contre `.claude/` committé (normalisation : l'en-tête generated est ajouté au committé lors du switch). **VERROU avant toute suite.** | 2 |
| 2.4 | Garde CI anti-drift : job qui refuse un commit modifiant `.claude/**`, `.codex/**`, `.gemini/**`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` si le diff ≠ sortie du builder (+ hook local optionnel) | 1,5 |
| 2.5 | Rapport d'impact v1 (§7.3) + marquage `UNTESTED` + `SDD_ALLOW_UNTESTED_HARNESS` | 1,5 |
| 2.6 | `AGENTS.md` canonique v1 (généré, même en mode Claude-only — il servira de mémoire aux harnais suivants et aux outils tiers) | 1 |

**Garde de sortie** : golden test vert en CI ; 1 FEAT CalcABC re-passe sur le
`.claude/` **régénéré** (pas le committé historique).

### Phase 3 — Adaptateur Codex (18–25 j-h) — dép. P2 + verdict GO P0.4

| # | Tâche | Effort |
|---|---|---:|
| 3.1 | `adapters/codex.py` : `AGENTS.md` (noyau + inline des skills critiques), `.codex/prompts/*.md` (40 commandes), `config.toml` (provider, base_url, approval_policy, sandbox) | 4–5 |
| 3.2 | Industrialiser le prototype 0.4 : `sdd_scripts/spawn_agent.py` (harness-aware) — spawn `codex exec` isolé, parallélisme `MaxParallel` via pool borné, timeout, capture rapport, retry `[BUILD_CORRECTIBLE]` | 5–7 |
| 3.3 | Fallback gates : les contrôles aujourd'hui « hook-shaped » (protect_framework, preflight_stack_combo, preflight_cost_cap, resolve_us_hash_sentinel…) deviennent pre/post-exec du wrapper + gate CI. Mapping des 19 scripts `sdd_hooks/` → point d'accroche wrapper | 3–4 |
| 3.4 | Émulation output-protocol (labels `[AGENT] … (X%)`) côté wrapper (parsing stdout Codex) — dégradé accepté : best-effort | 1,5 |
| 3.5 | **Validation bout-en-bout : 1 FEAT CalcABC sous Codex** (recommandé : CalcABCBackNet, back-only d'abord, puis full) + provider OpenAI natif ET Kimi OpenAI-compat | 4–6 |
| 3.6 | Doc honnêteté : page `docs/harness-codex.md` (ce qui est perdu/émulé, niveau de protection) | 1 |

**Garde de sortie** : FEAT CalcABC verte sous Codex (build + tests + gates
déterministes), rapport d'impact publié, divergences documentées.

### Phase 4 — Adaptateur Gemini / Antigravity (8–12 j-h) — dép. P2 (parallèle P3 possible)

| # | Tâche | Effort |
|---|---|---:|
| 4.1 | `adapters/gemini.py` : `GEMINI.md`, `.gemini/commands/*.toml` (40), settings | 3–4 |
| 4.2 | Réutiliser `spawn_agent.py` (mode `gemini -p`) — coût marginal si P3 fait | 2–3 |
| 4.3 | Validation 1 FEAT CalcABC sous Gemini CLI (provider Google natif ; Kimi via proxy = hors périmètre, documenté 🟡) | 3–4 |
| 4.4 | Doc honnêteté `docs/harness-gemini.md` | 0,5 |

### Phase 5 — Suite de conformité cross-harnais / cross-provider (10–14 j-h) — dép. P3+P4

| # | Tâche | Effort |
|---|---|---:|
| 5.1 | `conformance_run.py` : rejoue LA MÊME FEAT CalcABC sur N combos (harnais × provider), collecte : verdicts gates, itérations build_loop, coverage, diff structurel des fichiers générés, taux de JSON schema-valide, violations `[DERIVE_*]`/`[CLASS]` | 4–5 |
| 5.2 | Comparateur + rapport de divergences (`workspace/.sys/conformance/{combo}.md`) + agrégat matrice | 2–3 |
| 5.3 | Runs réels : 3 harnais × 2 providers minimum (claude-code×anthropic [référence], claude-code×moonshot, codex×openai, codex×moonshot, gemini×google) | 3–4 (+ coût tokens) |
| 5.4 | Publication de la matrice de confiance dans `docs/validated-combos.md` (extension du modèle combos SLA existant : dimension harnais + provider) | 1 |

---

## 10. Conformance run PAR MODÈLE (protocole + go/no-go)

SDD-Pro dépend massivement de **sorties JSON schema-strictes** (schémas
existants : `status.schema.json`, `project-config.schema.json`,
`libs-catalog.schema.json`, `api-tests.template.json`, frontmatter plans
validée par `validate_plan.py`, rapports auditors ingérés par
`ingest_agent_report`). Un modèle qui « bavarde » autour du JSON casse la
chaîne déterministe. Le harnais ne suffit pas : **chaque provider/modèle doit
être qualifié**.

### 10.1 Protocole (par tier × provider)

1. **Corpus** : 1 FEAT CalcABC canonique (2 US, back+front) + 1 FEAT reverse
   (module db-reverse SQL Server, déjà live-validé) = couvre forward + reverse.
2. **Exécution** : harnais de référence pour le provider (Claude Code pour
   anthropic/moonshot-anthropic-compat ; Codex pour openai/moonshot-openai-compat),
   3 runs par combo (variance).
3. **Métriques** (collectées par `conformance_run.py` depuis console.db +
   artefacts disque) :

| Métrique | Instrument existant | Seuil GO |
|---|---|---|
| Taux de sorties JSON schema-valides au 1er essai | `validate_plan.py`, `ingest_agent_report`, parse `*.json` auditors | ≥ 95 % |
| Discipline anti-derive | comptage `[DERIVE_VIOLATION]`, `[REFACTOR_HORS_SCOPE]`, `[OPTIMIZATION_PROACTIVE]`, `[UNDECLARED_DECISION]` | 0 violation bloquante |
| Fidélité tool-calling | taux d'appels outils malformés / retries harnais | ≥ 98 % |
| Convergence build_loop | itérations moyennes vs référence anthropic | ≤ référence + 1 iter |
| Gates déterministes | readiness GO, API Gate PASS, coverage ≥ seuil, spec-compliance non-RED | tous verts |
| Respect output-protocol (`[AGENT] … (X%)`) | lint des transcripts | ≥ 90 % (informatif) |
| Coût total run | télémétrie `record_token_usage` (exige pricing provider renseigné) | informatif (levier décision) |

4. **Verdict** : `validated` / `bench-validated` / `UNTESTED` — même
   vocabulaire que les combos stacks §6 CLAUDE.md. Persisté dans
   `providers/{p}.yaml → capabilities.structured_output_fidelity` +
   `docs/validated-combos.md`.

### 10.2 Go/no-go

- **GO** : tous les seuils atteints sur les 3 runs → combo vendable (SLA).
- **GO conditionnel** : JSON < 95 % mais ≥ 85 % → activer le mode
  « retry-on-schema-fail » du wrapper (1 re-prompt automatique avec l'erreur
  de validation) et re-mesurer ; combo marqué 🟡.
- **NO-GO** : anti-derive non tenu OU tool-calling < 95 % → provider exclu
  des tiers `deep`/`balanced` (peut rester candidat `fast` sur tâches non
  structurées), décision loggée en ADR.

---

## 11. Registre des risques

| # | Risque | Prob. | Impact | Mitigation | Phase |
|---|---|:---:|:---:|---|:---:|
| R1 | **Parité orchestration sous-agents hors Claude Code** (26 commandes spawnantes ; isolation + parallélisme + rapports parseables) | Haute | Bloquant Codex/Gemini | Prototype go/no-go AVANT extraction (P0.4) ; wrapper `spawn_agent.py` unique réutilisé P3/P4 ; périmètre réduit « mono-agent » si NO-GO, affiché | 0 |
| R2 | **Dégradation des protections** (hooks bloquants, skills auto-trigger, rules path-scoped absents hors Claude) | Certaine | Moyen (acceptable SI visible) | Constat clé : les hooks ne sont déjà PAS câblés dans settings.json — les protections réelles sont Python+CI, portables. Rapport d'impact obligatoire (§7.3), niveau de protection A/B/C, `SDD_ALLOW_UNTESTED_HARNESS` audit-loggué | 2 |
| R3 | **Dérive de synchro 3×** (façades éditées à la main, drift `.sdd/` ↔ générés) | Moyenne | Élevé (corruption SSoT) | Génération exclusive + en-tête DO NOT EDIT + garde CI diff-vs-builder (P2.4) + invariant n°14 `harness-parity` + golden test | 2 |
| R4 | **Fidélité sorties structurées des modèles non-Claude** (chaîne JSON schema-strict) | Moyenne-haute | Élevé | Conformance run par modèle (§10) avec seuils chiffrés ; retry-on-schema-fail ; exclusion par tier possible (mix providers) | 5 |
| R5 | Casse des 97 invocations Python + permission `settings.local.json` lors du move `.sdd/python` | Moyenne | Moyen | Réécriture exhaustive P1.3 + grep-gate CI + checklist manuelle §12 ; garde CalcABC P1 | 1 |
| R6 | `paths.py::_looks_like_repo_root()` — régression de détection racine (post-mortem 2026-05-21 déjà documenté dans le fichier) | Faible | Élevé | Bi-racine transitoire + tests dédiés (les 144 tests couvrent déjà paths) | 1 |
| R7 | IDs modèles / endpoints Moonshot inexacts (kimi-k3, k2.7-code, k2.5, URLs) | Moyenne | Faible | Tous marqués « à confirmer » dans providers/*.yaml ; validation au 1er conformance run ; pricing absent = cost-cap fail-open loggué | 1/5 |
| R8 | Skills tiers vendorés : la transpilation vers d'autres harnais peut violer l'esprit CC BY-SA (redistribution transformée) | Faible | Faible | Pass-through sans transformation + licences conservées ; hors Claude Code, skills tiers = commandes explicites pointant le même contenu | 2 |
| R9 | Coût contexte ↑ hors Claude Code (perte lazy-load `@` : 328 refs, ~150-200 Ko économisés aujourd'hui par TOK-C1) | Certaine | Moyen (coût $) | Stratégie « Read explicite au STEP contexte » (déjà en place dans les agents) plutôt qu'inline massif ; mesurer au conformance run | 3 |
| R10 | Annotations prompt-caching Anthropic inopérantes ailleurs → estimations coût faussées | Certaine | Faible | `cache_layer` appliqué conditionnellement (provider=anthropic) ; rapport d'impact l'affiche | 2 |

---

## 12. Checklist de décisions Tech Lead (à trancher AVANT chaque phase)

**Avant P0 :**
- [ ] Valider le format pivot YAML+body (§4.1-4.2) vs alternative « .md + frontmatter étendue » (moins de migration, moins de structure).
- [ ] Critère go/no-go du prototype Codex (proposé : ≥ 95 % complétion parseable sur 20 runs) — ajuster ?
- [ ] Nom définitif du foyer : `.sdd/` (proposé) — conflit avec un outil existant ?

**Avant P1 :**
- [ ] Fenêtre de gel : la migration P1 touche 171 py + 65 md — geler les développements framework pendant ~2 semaines OU travailler sur branche longue avec rebase quotidien ?
- [ ] `SDD_HOME` : env var seule, ou aussi fichier marqueur `.sdd-home` à la racine (utile pour les layouts workspace-sibling déjà supportés par `paths.py`) ?
- [ ] Tier `fast` : l'activer dès P1 pour des agents candidats (reverse-clarifier ?) ou le réserver ?
- [ ] Politique de sync temporaire `.claude/` ↔ `.sdd/` entre P1 et P2 (copie committée proposée) — acceptable ?

**Avant P2 :**
- [ ] Normalisation du golden test : diff octet-à-octet strict, ou modulo en-tête generated + fins de ligne (repo Windows, CRLF) ?
- [ ] La garde CI anti-drift : hook local bloquant en plus du job CI, ou CI seul ?

**Avant P3 :**
- [ ] Budget tokens/€ alloué à la validation Codex bout-en-bout (1 FEAT × 2 providers × retries).
- [ ] Sous-ensemble de skills SDD-owned à inliner dans AGENTS.md (proposé : using-sddpro + test-driven-development uniquement).
- [ ] Périmètre reverse sous Codex : inclus d'emblée ou Claude-only jusqu'à P5 ?

**Avant P5 :**
- [ ] Combos harnais × provider à qualifier commercialement (proposé : 5 — cf. P5.3) et lesquels portent un SLA.
- [ ] Seuils go/no-go §10.2 — validation ou ajustement.
- [ ] Compte Moonshot + clés API + budget conformance (IDs kimi-k3 / k2.7-code / k2.5 et endpoints **à confirmer** avant tout run).

---

## 13. Synthèse des efforts

| Phase | Contenu | Effort (j-h) | Dépendance |
|---|---|---:|---|
| 0 | ADR + capabilities + invariant 14 + **prototype Codex go/no-go** | 6–9 | — |
| 1 | Extraction `.sdd/` + SDD_HOME + model_tier + stack.md 2 axes + mode dynamic (§8.bis) | 14–20 | P0 |
| 2 | `harness_build.py` + adaptateur Claude identité + **golden test** + garde CI | 12–16 | P1 |
| 3 | Adaptateur Codex + wrapper spawn + fallback gates + validation FEAT | 18–25 | P2, GO P0.4 |
| 4 | Adaptateur Gemini/Antigravity + validation FEAT | 8–12 | P2 (∥ P3) |
| 5 | Suite de conformité + runs + matrice de confiance publiée | 10–14 | P3+P4 |
| **Total** | | **68–96** | ~3–4,5 mois à 1 ETP |

**Chemin critique** : P0.4 (prototype) → P1 (extraction) → P2 (golden test)
→ P3. P4 parallélisable avec P3 à 2 ETP (gain calendaire ~3 semaines).
**Verrous non négociables** : garde CalcABC (P1), golden test identité (P2),
FEAT bout-en-bout par harnais (P3/P4), conformance par modèle (P5).
