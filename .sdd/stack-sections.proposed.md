# Sections proposées pour `stack.md.template` — 2 axes + sélection de modèle

> **PROPOSITION versionnée à part (Phase 1.7 / 1.9)** — le vrai
> `.sdd/templates/stack.md.template` n'est PAS modifié par cet incrément.
> Insertion prévue : ~l.34, avant `## Project Config`. Défauts
> rétro-compatibles : **absence de section = claude-code / anthropic / static**.

---

## Active Harness

```markdown
## Active Harness
Harness: claude-code            # claude-code | codex | antigravity | gemini-cli
```

## Active Model Provider

```markdown
## Active Model Provider
Provider: anthropic             # anthropic | openai | google | moonshot
Endpoint: default               # default | url custom (proxy interne)
ModelTierMap:                   # override optionnel par tier — MIXAGE cross-provider permis
  deep: anthropic               #   ex. deep sur Claude, balanced/fast sur Kimi = levier coût
  balanced: anthropic
  fast: anthropic
```

## Model Selection

```markdown
## Model Selection
Mode: static                    # static | dynamic
```

- `static` (défaut) : chaque agent reçoit son `tier_default` fixe
  (`.sdd/agent-bounds.yaml`) — comportement actuel préservé.
- `dynamic` (opt-in, 🟡 UNTESTED tant qu'aucun conformance run §10) :
  à chaque spawn, le scoreur déterministe (0 token) calcule la complexité
  du work-item → tier candidat, **clampé** par `tier_floor`/`tier_ceiling`
  de l'agent (invariants non surchargeables par le Project Config).
  Décision persistée dans
  `workspace/.sys/.routing/{n}[-{m}]-model-routing.json`.

---

**Parsing** de ces 3 sections : `.sdd/python/sdd_lib/stack_config.py`
(`parse_stack_config` / `load_stack_config`, défauts rétro-compat, tests
`test_stack_config.py`). **Résolution** du modèle : `.sdd/python/sdd_lib/model_resolver.py` :
`agent → model_tier → (ModelTierMap → provider) → providers/{p}.yaml → modèle concret`.
Le parseur fournit à `model_resolver` le `mode` (static|dynamic) et le provider
par tier (`provider_for_tier`) ; il alimente aussi `impact_report` (harnais + provider actifs).
