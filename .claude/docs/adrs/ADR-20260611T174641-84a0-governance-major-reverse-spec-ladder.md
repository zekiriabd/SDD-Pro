# ADR-20260611T174641-84a0-governance-major-reverse-spec-ladder

- **Status**: Accepted
- **Date**: 2026-06-11
- **Slug**: `governance-major-reverse-spec-ladder`
- **Phase**: reverse-engineering (Phase 3 — code → FEAT)
- **Materialized**: 2026-06-11 (audit CR-3 — was cited as authoritative in
  `rules/reverse-engineering.md`, `docs/reverse-engineering-workflow.md` and
  `CHANGELOG.md` without an ADR file on disk; the 3a/3b/3c ladder itself was
  already implemented live in agents + commands)

---

## Context

The reverse-engineering module's Phase 3 (`legacy code → FEAT métier`) was
originally implemented as a single agent, `reverse-functional-extractor`
(Opus 4.8), that produced the business FEAT (`feats/{n}-{Name}.md`) in
**one mono-prompt jump** straight from the legacy evidence.

Observed problem: a single prompt asked to do two incompatible altitude
shifts at once — (1) read raw legacy code and extract mechanical behavior,
and (2) phrase clean business intent for a Tech Lead. In practice the
technical altitude **bled into the business FEAT** (SQL fragments, class
names, framework plumbing surfacing as if they were functional needs). The
FEAT was neither a faithful technical photo nor a clean business spec, and
the evidence chain `FEAT item → file:line` was opaque (a single hop hid
where each assertion actually came from).

The reverse workflow already enforces `bias toward not-verified`, evidence
per item, and confidence caps — but those guarantees were diluted when one
prompt collapsed analysis, capability framing, and business composition.

---

## Decision

Decompose Phase 3 into an **ascending three-rung ladder**, one altitude
shift per rung, each a dedicated agent reading only the rung below it:

- **3a `reverse-tech-analyst`** (Opus 4.8) — reads the legacy evidence
  (`units[U-N].evidenceFiles`, transitive deep layer L0) and produces a
  **faithful technical analysis** `workspace/plans/{n}-{Name}.analysis.md`
  (observed behaviors, data access, calculations, side-effects), tasks `T-N`
  with `file:line` evidence. Low altitude (a photo of the code).
- **3b `reverse-us-writer`** (model decided separately — see Consequences)
  — reads **only** the 3a analysis (never the legacy code, `forbidden_reads`)
  and **lifts it one rung** into User Stories grouped by business capability
  `workspace/us/{n}-{m}-{Name}.md`. Each AC points to the 3a tasks
  `T-N` (traceability thread). Medium altitude.
- **3c `reverse-feat-composer`** (Opus 4.8) — reads **only** the 3b user
  stories + the 3a analysis (for evidence resolution and plumbing demotion),
  and composes the clean **business FEAT** `workspace/feats/{n}-{Name}.md`
  with plumbing demoted out of the functional layer. High altitude (the
  Tech-Lead-facing spec). Replaces `reverse-functional-extractor`.

Cross-cutting contracts of the ladder:

- **Traceability thread D3** — `FEAT item → US AC → task T-N → file:line
  evidence` is verifiable end-to-end. Gaps emit
  `[REVERSE_LADDER_TRACEABILITY_GAP]` (informational, never blocking, **never
  filled by invention** — `bias toward not-verified`). Enforced by
  `check_ladder_traceability.py`.
- **Confidence min-monotone ascending** — `confidence(3c) ≤ confidence(3b) ≤
  confidence(3a)`. A higher rung can never claim more confidence than the
  rung it was lifted from.
- **`/sdd-reverse` becomes a sequencer** — it no longer spawns an agent
  directly; it chains `/sdd-reverse-analyze` (3a) + `/sdd-reverse-stories`
  (3b) + `/sdd-reverse-feat` (3c). Each sub-command spawns exactly one agent.
  The no-spawn rule (§9 `rules/reverse-engineering.md`) is preserved.
- **`reverse-functional-extractor` is decommissioned (D2 no-dead-code)** —
  removing it while a command still spawned it (or its prompt lingered)
  would FAIL the deterministic gate `reverse_smoke.check_no_dangling_spawn`
  (invariant `reverse-no-dead-code`).

Intent A (document the legacy faithfully) and Intent B (forward-compatible
rebuild via `/sdd-full`) are both served: 3a/3b carry the legacy photo and
its capability framing, 3c yields a spec consumable by the forward pipeline.

---

## Consequences

**Positifs :**
- Clean altitude separation — technical photo (3a), capability framing (3b),
  business FEAT (3c) no longer leak into one another.
- End-to-end traceability `FEAT → US → T-N → evidence`, each hop auditable.
- Confidence is honestly bounded (min-monotone) instead of optimistically
  asserted at the top.
- No-spawn contract preserved; `/sdd-reverse` is a pure command sequencer,
  isolation D4 intact, deterministic dead-wiring gate covers the migration.
- Each rung reads only the rung below → strict selective reading, smaller
  per-prompt context, easier review.

**Négatifs / dette acceptée :**
- **3× Opus invocations per unit** instead of 1 in the worst case (3a, 3b,
  3c) — higher token cost per unit. Mitigated for 3b: because 3b reads
  **only** the 3a analysis (never the legacy code), it is an altitude-lift
  task within Sonnet's reach and is moved off Opus (audit 2026-06-11,
  ~ -33 % of reverse Opus cost). 3a and 3c stay on Opus (3a reads raw code;
  3c composes the final business spec).
- More artifacts on disk (`.analysis.md`, US set, FEAT) and an extra
  traceability gate to keep green.
- Three rungs must be kept in sync (`[REVERSE_LADDER_STALE]` when a lower
  rung's hash changes without regenerating the upper rungs).

---

## Alternatives considérées

- **Keep the mono-prompt `reverse-functional-extractor`** : écartée car la
  fusion des altitudes faisait baver la plomberie technique dans la FEAT
  métier et rendait la chaîne d'evidence opaque (motivation centrale de
  cet ADR).
- **Two rungs (analysis → FEAT, skip explicit US)** : écartée car le saut
  analyse→FEAT restait trop large (capability framing implicite, non
  traçable) ; la marche US 3b est ce qui rend le fil FEAT→US→T-N vérifiable.
- **Single agent with internal multi-pass prompting** : écartée car non
  isolable, non reprenable rung-par-rung, et incompatible avec le
  séquençage de commandes no-spawn.

---

## Liens

- Règle : `.claude/rules/reverse-engineering.md` (escalier §1, §8, taxonomie
  `[REVERSE_LADDER_*]` §6)
- Design doc : `.claude/docs/reverse-engineering-workflow.md` (v0.7.0)
- Agents : `.claude/agents/{reverse-tech-analyst,reverse-us-writer,reverse-feat-composer}.md`
- Commandes : `/sdd-reverse`, `/sdd-reverse-analyze`, `/sdd-reverse-stories`, `/sdd-reverse-feat`
- Loader : `.claude/loader.reverse.yml`
- Invariants : `.claude/INVARIANTS.reverse.yml` (`reverse-no-dead-code`,
  `reverse-ladder-traceability`)
- Enforcers : `reverse_smoke.check_no_dangling_spawn`,
  `check_ladder_traceability.py`
