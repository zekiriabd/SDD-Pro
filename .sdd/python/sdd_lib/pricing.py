"""SDD_Pro — Single source of truth for Anthropic model pricing.

Centralizes per-million-token pricing for all models used by Claude Code
agents, consumed by `report_roi.py` (post-hoc ROI aggregation),
`preflight_cost_cap.py` (real-time cost cap enforcement),
`sdd_hooks/statusline.py` (coût du run courant) and
`sdd_scripts/context_budget.py` (coût estimé du contexte d'un agent).

Before v7.0.1 the pricing was duplicated in both files with an explicit
comment "avoid import cycle". The cycle no longer exists since this
module has zero hard dependencies; consumers should import from here.

Rates (USD per million tokens) sourced from Anthropic API pricing page
(https://www.anthropic.com/pricing), reviewed 2026-11-07.

Freshness contract (audit m4, 2026-06-06)
-----------------------------------------
The `PRICING_LAST_REVIEWED` constant below MUST be updated each time
the pricing table is reviewed/edited. `framework_smoke.py` invokes
`check_pricing_freshness()` which compares this date against
`PricingFreshnessMaxAgeDays` (config.base.yml, default 90 days) and
emits a WARN or STOP per `PricingFreshnessMode` (off/warn/strict).

Unknown-model contract (audit tokens 2026-11-07)
------------------------------------------------
Before this audit an unknown id silently priced at Sonnet 4.6 rates — the
cheapest plausible reading of an unknown spend, i.e. the one direction a
cost cap must never err in. Now :

  * ``get_pricing(unknown)`` logs ONE ``WARN [pricing]`` line on stderr per
    distinct id per process, and returns ``CONSERVATIVE_PRICING`` — the most
    expensive tariff the table knows. A cap computed on it trips early,
    never late.
  * ``has_known_pricing()`` still answers the factual question, so reports
    can label such rows (`pricing_source=fallback` in `agent_journal`).
"""

from __future__ import annotations

import datetime as _dt
import sys as _sys

# ---------------------------------------------------------------------------
# Canonical pricing table (USD per million tokens)
# ---------------------------------------------------------------------------
# Schema : { model_id : { "input", "output", "cache_read", "cache_creation" } }
#
# Audit C2 (2026-08-29) — current-generation ids added. Before this fix the
# table stopped at the 4.x family, so a runtime model id such as
# ``claude-opus-5`` (or ``claude-opus-5[1m]``) missed every lookup and
# ``get_pricing()`` silently returned Sonnet rates, under-counting the run.
#
# KNOWN DIVERGENCE — CLOSED 2026-08-30 (follow-up to audit 2026-08-29 C2).
# The ``claude-opus-4-*`` rows carried a historical $15/$75 rate; the
# published rate for that family is $5/$25. Corrected here AND in every
# coordinated location (`providers/anthropic.yaml`, bench_run docstring,
# tests). Deliberately NOT touched: any cost already recorded in a project's
# live `console.db` — a historical record, not a live value.
#
# Audit tokens 2026-11-07 — 5.5 / 5.1 generation added with the exact
# published rates. Cache read / creation are NOT a fixed ratio of input on
# this generation (opus-5-5 reads at 0.20 for a 4.00 input ; fable-5-1 at
# 0.25 for 10.00) : values are explicit, never derived from `input`.
PRICING: dict[str, dict[str, float]] = {
    # --- current generation (5.5 / 5.1 / 5) ------------------------------
    "claude-opus-5-5":    {"input":  4.00, "output": 20.00, "cache_read": 0.20, "cache_creation":  5.00},
    "claude-sonnet-5-5":  {"input":  2.00, "output": 10.00, "cache_read": 0.20, "cache_creation":  2.50},
    "claude-haiku-5-5":   {"input":  0.10, "output":  0.50, "cache_read": 0.01, "cache_creation":  0.125},
    "claude-fable-5-1":   {"input": 10.00, "output": 50.00, "cache_read": 0.25, "cache_creation": 12.50},
    "claude-fable-5":     {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_creation": 12.50},
    "claude-mythos-5":    {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_creation": 12.50},
    "claude-opus-5":      {"input":  5.00, "output": 25.00, "cache_read": 0.50, "cache_creation":  6.25},
    "claude-sonnet-5":    {"input":  2.00, "output": 10.00, "cache_read": 0.20, "cache_creation":  2.50},
    # --- 4.x family (kept : agents pinned by `model:` + historical rows) ---
    "claude-opus-4-8":    {"input":  5.00, "output": 25.00, "cache_read": 0.50, "cache_creation":  6.25},
    "claude-opus-4-7":    {"input":  5.00, "output": 25.00, "cache_read": 0.50, "cache_creation":  6.25},
    "claude-opus-4-6":    {"input":  5.00, "output": 25.00, "cache_read": 0.50, "cache_creation":  6.25},
    "claude-sonnet-4-6":  {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-sonnet-4-5":  {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-haiku-4-5":   {"input":  1.00, "output":  5.00, "cache_read": 0.10, "cache_creation":  1.25},
}

#: Fields of a pricing row, in the order `as_tuple()` emits them.
PRICE_FIELDS: tuple[str, ...] = ("input", "output", "cache_creation", "cache_read")


def _most_expensive(table: dict[str, dict[str, float]]) -> str:
    """Id of the costliest tariff (output, then input, then cache rates)."""
    return max(
        table,
        key=lambda m: (table[m]["output"], table[m]["input"],
                       table[m]["cache_creation"], table[m]["cache_read"]),
    )


#: The tariff applied to a model the table does not know. Deliberately the
#: MOST expensive known one : a cost cap must over-estimate an unknown, never
#: under-estimate it (audit tokens 2026-11-07 — replaces the Sonnet midpoint).
CONSERVATIVE_MODEL_ID: str = _most_expensive(PRICING)
# Copie : une identité distincte permet aux tests de distinguer « tarif
# trouvé » de « repli » (`is not CONSERVATIVE_PRICING`).
CONSERVATIVE_PRICING: dict[str, float] = dict(PRICING[CONSERVATIVE_MODEL_ID])

#: Legacy alias kept for `report_roi.py` (`DEFAULT_PRICING` tuple) and any
#: external reader — same object as CONSERVATIVE_PRICING, no longer Sonnet.
FALLBACK_PRICING: dict[str, float] = CONSERVATIVE_PRICING


# ---------------------------------------------------------------------------
# Multi-provider pricing (audit 2026-07-26 R2 — fail-closed under non-Anthropic)
# ---------------------------------------------------------------------------
# Provider YAMLs under `.sdd/providers/*.yaml` declare their own `pricing:`
# blocks (OpenAI, Google, Moonshot). Before v7.0.1 the cost-cap only knew
# Anthropic models and silently under-counted OpenAI o1 / Gemini Pro / Kimi
# K3 at Sonnet rates → up to 5× underestimation. Now pricing.py lazy-loads
# every provider YAML and exposes `has_known_pricing()` so callers can label
# (or reject) truly-unknown models.
#
# Lazy import : hooks are short-lived subprocesses; the yaml cost (~50 ms) is
# paid once and only when the run has non-Anthropic activity.
_PROVIDER_PRICING_CACHE: dict[str, dict[str, float]] | None = None


def _load_provider_pricing() -> dict[str, dict[str, float]]:
    """Load pricing tables from every `.sdd/providers/*.yaml`, cached.

    Never raises : provider YAMLs are treated as best-effort augmentation
    of the canonical Anthropic table. Any parse error or missing key is
    silently skipped (caller falls back to `CONSERVATIVE_PRICING`).
    """
    global _PROVIDER_PRICING_CACHE
    if _PROVIDER_PRICING_CACHE is not None:
        return _PROVIDER_PRICING_CACHE
    result: dict[str, dict[str, float]] = {}
    try:
        from .paths import providers_dir  # local import — avoid circular
        pdir = providers_dir()
    except Exception:
        _PROVIDER_PRICING_CACHE = result
        return result
    if not pdir.is_dir():
        _PROVIDER_PRICING_CACHE = result
        return result
    try:
        import yaml  # local import — hooks pay only when needed
    except Exception:
        _PROVIDER_PRICING_CACHE = result
        return result
    for ypath in sorted(pdir.glob("*.yaml")):
        try:
            data = yaml.safe_load(ypath.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        pricing = data.get("pricing")
        if not isinstance(pricing, dict):
            continue
        for model_id, tariffs in pricing.items():
            if not isinstance(tariffs, dict):
                continue
            inp = tariffs.get("input")
            outp = tariffs.get("output")
            if inp is None or outp is None:
                continue
            try:
                inp_f = float(inp)
                outp_f = float(outp)
                cr = float(tariffs.get("cache_read", inp))
                cc = float(tariffs.get("cache_creation", inp))
            except (TypeError, ValueError):
                continue
            # Canonical PRICING wins on collision (Anthropic SSoT).
            if str(model_id) in PRICING:
                continue
            result[str(model_id)] = {
                "input": inp_f,
                "output": outp_f,
                "cache_read": cr,
                "cache_creation": cc,
            }
    _PROVIDER_PRICING_CACHE = result
    return result


def has_known_pricing(model_id: str | None) -> bool:
    """Return True iff pricing for `model_id` is known (canonical OR provider YAML).

    Used by `preflight_cost_cap` and `journal.compute_cost` to label rows
    whose cost was estimated at the conservative tariff.
    """
    base = base_model_id(model_id)
    if not base:
        return False
    if base in PRICING:
        return True
    return base in _load_provider_pricing()


def base_model_id(model_id: str | None) -> str:
    """Strip a runtime context-window suffix like ``[1m]`` from a model id.

    Claude Code may report ``claude-opus-4-8[1m]`` at runtime while the
    pricing table is keyed on the canonical ``claude-opus-4-8``. Without
    this normalization the cost-cap would miss the table and fall back,
    mis-counting Opus spend (audit CR-1, 2026-06-11).
    """
    return (model_id or "").split("[", 1)[0].strip()


#: Unknown ids already reported on stderr in this process (one WARN each).
_WARNED_UNKNOWN: set[str] = set()


def _warn_unknown(label: str) -> None:
    if label in _WARNED_UNKNOWN:
        return
    _WARNED_UNKNOWN.add(label)
    try:
        print(
            f"WARN [pricing] modèle {label} sans tarif connu — tarif "
            f"conservateur appliqué ({CONSERVATIVE_MODEL_ID} : "
            f"${CONSERVATIVE_PRICING['input']:.2f} in / "
            f"${CONSERVATIVE_PRICING['output']:.2f} out par Mtok). "
            f"FIX : ajouter l'id dans sdd_lib/pricing.py PRICING ou dans "
            f".sdd/providers/{{provider}}.yaml `pricing:` puis bumper "
            f"PRICING_LAST_REVIEWED.",
            file=_sys.stderr, flush=True,
        )
    except Exception:  # noqa: BLE001 — a log line must never break a caller
        pass


def get_pricing(model_id: str | None, *, warn_unknown: bool = True) -> dict[str, float]:
    """Return per-million-token pricing dict for a given model_id.

    Lookup order (audit 2026-07-26 R2) :
      1. Canonical Anthropic ``PRICING`` (SSoT).
      2. ``.sdd/providers/*.yaml`` ``pricing:`` blocks (OpenAI, Google, Moonshot).
      3. ``CONSERVATIVE_PRICING`` — most expensive known tariff — with ONE
         ``WARN [pricing]`` on stderr per distinct id per process (audit
         tokens 2026-11-07 ; before : silent Sonnet 4.6 under-count).

    The id is normalized (``base_model_id``) before lookup so a runtime
    ``[1m]`` suffix still resolves. Never raises. ``warn_unknown=False``
    silences the stderr line (pure reporting callers that already label the
    row via :func:`has_known_pricing`).
    """
    base = base_model_id(model_id)
    if base in PRICING:
        return PRICING[base]
    provider_pricing = _load_provider_pricing()
    if base in provider_pricing:
        return provider_pricing[base]
    if warn_unknown:
        _warn_unknown(repr(base) if base else "<non enregistré (NULL)>")
    return CONSERVATIVE_PRICING


def estimate_cost(
    model_id: str | None,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    warn_unknown: bool = True,
) -> float:
    """USD cost of a token bundle at ``model_id`` rates (conservative if unknown).

    One arithmetic in one place : `preflight_cost_cap`, `statusline` and
    `context_budget` all used to re-implement the four multiplications.
    """
    p = get_pricing(model_id, warn_unknown=warn_unknown)
    return (
        (input_tokens or 0) * p["input"]
        + (output_tokens or 0) * p["output"]
        + (cache_creation_tokens or 0) * p["cache_creation"]
        + (cache_read_tokens or 0) * p["cache_read"]
    ) / 1_000_000.0


def as_tuple(model_id: str) -> tuple[float, float, float, float]:
    """Return pricing as (input, output, cache_creation, cache_read) tuple.

    Compat shim for `report_roi.py` legacy PRICING_TABLE shape.
    """
    p = get_pricing(model_id)
    return (p["input"], p["output"], p["cache_creation"], p["cache_read"])


# ---------------------------------------------------------------------------
# Freshness check (audit m4, 2026-06-06)
# ---------------------------------------------------------------------------
#: ISO date of the last manual review against https://www.anthropic.com/pricing
#: BUMP THIS each time you edit the PRICING table — `framework_smoke.py`
#: checks staleness against `PricingFreshnessMaxAgeDays` (config.base.yml).
PRICING_LAST_REVIEWED = "2026-11-07"


def check_pricing_freshness(max_age_days: int = 90, today: _dt.date | None = None
                            ) -> tuple[bool, int, str]:
    """Return (is_fresh, age_days, last_reviewed_iso).

    is_fresh : True ssi (today - PRICING_LAST_REVIEWED) <= max_age_days.
    Caller (framework_smoke.py) decides off/warn/strict per
    `PricingFreshnessMode` in layered config.
    """
    reviewed = _dt.date.fromisoformat(PRICING_LAST_REVIEWED)
    ref = today or _dt.date.today()
    age = (ref - reviewed).days
    return (age <= max_age_days, age, PRICING_LAST_REVIEWED)
