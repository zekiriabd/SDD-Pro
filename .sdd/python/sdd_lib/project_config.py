"""Parse `workspace/stack/stack.md` to extract Project Config + active stacks.

SSOT for all Project Config readers (cf. audit 2026-05-14 — 10 ad-hoc
re-implementations consolidated).

v7.0.0-alpha (2026-05-21) — opt-in type coercion : `coerce_config_types`
converts string-shaped int / float / bool values to native Python types.
Each parser (`parse_kv_block`, `read_project_config`) accepts a
`coerce: bool = False` parameter ; default behaviour is byte-identical
to v6.x (strings everywhere — backward compat for existing callers that
already do their own `_bool_flag` / `int(raw)` style cast). New code
(validate_project_config.py) opts in via `coerce=True`.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from sdd_lib.paths import workspace_root, repo_root

# Le `.` est admis dans le nom de cle : les cles composees du type
# `AcceptanceGate.RequireE2E` / `.SmokeTimeout` / `.MinCoverage` sont lues
# par `validate_acceptance.py` via la hierarchie layered
# (base.yml <- team.yml <- stack.md). Avant l'audit 2026-08-26 la classe de
# caracteres excluait le point : les 3 sous-cles etaient silencieusement
# droppees cote `stack.md` ET cote `config.base.yml`, rendant mortes les
# branches de `validate_acceptance._acceptance_config()`.
_KV_RE = re.compile(r"^[-*]?\s*([A-Za-z][A-Za-z0-9_.]*)\s*:\s*(.+?)\s*$")
# Bi-racine 2026-07-25 (MIGRATION-PLAN Phase 1) : les stack.md peuvent
# référencer soit `.claude/stacks/...` (legacy) soit `.sdd/stacks/...`
# (foyer neutre). Le pattern accepte les deux — l'ancien bootstrap génère
# encore `.claude/stacks/` ; le nouveau bootstrap post-migration générera
# `.sdd/stacks/`. `stack.md` reste projet, immutable dans son format.
_STACK_ROOT_ALT = r"(?:\.claude|\.sdd)"
CANONICAL_STACK_ROOT = ".sdd"
STACK_CATEGORIES: tuple[str, ...] = (
    "backend", "frontend", "fullstack", "mobiles", "ui", "qa", "auth", "archi",
)
_ACTIVE_STACK_RE = re.compile(rf"^\s*-\s*({_STACK_ROOT_ALT}/stacks/[^\s]+\.md)\s*$")
_STACK_PATH_ANY_RE = re.compile(rf"{_STACK_ROOT_ALT}/stacks/")


@lru_cache(maxsize=32)
def stack_path_re(category: str | None = None, *, anchored: bool = True) -> re.Pattern[str]:
    """Compiled bi-root regex matching an `## Active …` stack reference line.

    SSoT for **every** consumer that parses stack paths out of `stack.md`
    (audit 2026-08-25 — `phase_planner` saw 0 active stacks while
    `sdd_full_planner` saw 8, because each had re-implemented the pattern
    with a different root hardcoded). Never re-implement this regex : import
    it.

    Groups : `(1)` = category, `(2)` = stack id (both root-agnostic).

    Args:
        category: restrict to one category (e.g. `"backend"`). `None`
            accepts any of `STACK_CATEGORIES`.
        anchored: `True` (default) matches a whole list item line
            (`  - .sdd/stacks/backend/x.md`) — use with `.match()`.
            `False` matches the path anywhere in a line — use with
            `.search()` (legacy `preflight` / `phase_planner` semantics).

    Bi-racine (MIGRATION-PLAN Phase 1) : `.claude/stacks/…` (legacy
    bootstrap) and `.sdd/stacks/…` (canonical, post-migration bootstrap)
    are both accepted on read. Use `normalize_stack_path()` before
    resolving anything on disk — only `.sdd/stacks/` exists there.
    """
    cat = re.escape(category) if category else "|".join(STACK_CATEGORIES)
    body = rf"{_STACK_ROOT_ALT}/stacks/({cat})/([\w-]+)\.md"
    if anchored:
        return re.compile(rf"^\s*-\s*{body}\s*$", re.IGNORECASE)
    return re.compile(body, re.IGNORECASE)


def normalize_stack_path(path: str) -> str:
    """Rewrite a legacy `.claude/stacks/…` reference to the canonical `.sdd/` root.

    `stack.md` is a *project* artifact that may predate the `.claude → .sdd`
    migration ; the framework only ships `.sdd/stacks/` on disk. Any caller
    that turns a declared path into a filesystem lookup MUST normalize first.
    Non-stack paths and already-canonical paths are returned unchanged.
    """
    return _STACK_PATH_ANY_RE.sub(f"{CANONICAL_STACK_ROOT}/stacks/", path, count=1)


def parse_active_stack_ids(
    text: str,
    category: str | None = None,
    *,
    first_only: bool = False,
) -> dict[str, list[str]]:
    """Extract `{category: [stack_id, …]}` from a `stack.md` body (or one section).

    Skips `#`-commented lines (a commented stack is an *inactive* stack —
    the documented opt-out in every `## Active …` section). Order of
    appearance is preserved.

    Args:
        text: full `stack.md` content or a single `## Active …` section body.
        category: restrict parsing to one category.
        first_only: keep only the first id per category (the "one active
            stack per axis" contract used by `phase_planner` / `preflight`).
    """
    pattern = stack_path_re(category, anchored=False)
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = pattern.search(line)
        if not m:
            continue
        cat, stack_id = m.group(1).lower(), m.group(2)
        bucket = out.setdefault(cat, [])
        if first_only and bucket:
            continue
        bucket.append(stack_id)
    return out


# Section parsing lives in `sdd_lib.markdown_io.section_body` (audit CRIT-3,
# SSoT consolidation). Le duplicat local `_SECTION_RE_TMPL` a ete supprime
# (audit 2026-08-26) : zero appelant en arbre, et sa variante divergente
# etait exactement le drift que CRIT-3 fermait.

# ---------------------------------------------------------------------------
# Type coercion (v7.0.0-alpha, opt-in)
# ---------------------------------------------------------------------------
_BOOL_TRUE: tuple[str, ...] = ("true", "yes", "on")
_BOOL_FALSE: tuple[str, ...] = ("false", "no", "off")
_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


def coerce_scalar(value: str) -> Any:
    """Coerce a YAML-shaped scalar string to its native Python type.

    Rules (in order) :
      - "true" / "True" / "yes" / "on"   → True
      - "false" / "False" / "no" / "off" → False
        (case-insensitive)
        Beware : "off" is a common YAML mode literal ; we DO coerce it
        to False, mirroring YAML 1.1 spec. Callers needing the *string*
        "off" (e.g. mode enums QAMode/A11yMode) must NOT use this helper
        and stick to string semantics.
      - /^-?\\d+$/        → int (`"42"` → 42, `"-3"` → -3)
      - /^-?\\d+\\.\\d+$/ → float (`"15.0"` → 15.0)
      - everything else → original string unchanged

    Empty string returns empty string (caller decides if it's valid).
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return stripped
    lower = stripped.lower()
    if lower in _BOOL_TRUE:
        return True
    if lower in _BOOL_FALSE:
        return False
    if _INT_RE.match(stripped):
        try:
            return int(stripped)
        except ValueError:
            return stripped
    if _FLOAT_RE.match(stripped):
        try:
            return float(stripped)
        except ValueError:
            return stripped
    return stripped


# Keys whose value is a string enum (mode/severity) — must stay string
# even when the literal matches a bool/numeric pattern. Centralized list
# avoids drift between coercion logic and the project-config schema.
STRING_ENUM_KEYS: frozenset[str] = frozenset({
    "QAMode", "A11yMode", "PerfMode", "CodeReviewMode", "SecurityMode",
    "SpecComplianceMode", "ArchReviewMode", "ReviewMode",
    "MutationTestingMode", "E2EMode", "ElicitorGapMode",
    "FeatAntiGigoMode", "FeatDeepenMode", "CheckpointMode",
    "TokenUsageMode",
    "A11yFailOn", "PerfFailOn", "CodeReviewFailOn", "SecurityFailOn",
    "SpecComplianceFailOn", "ArchReviewFailOn", "ReviewFailOn",
    "LibStrategy", "RuntimeException", "Capabilities",
    "AppName", "BackendName", "LibName", "FrontendName",
    "AppNamespace", "BackendNamespace",
})


def coerce_config_types(raw: dict[str, str]) -> dict[str, Any]:
    """Apply `coerce_scalar` to a config dict, except for known string-enum keys.

    String-enum keys (cf. `STRING_ENUM_KEYS`) keep their string value
    even if it matches a bool/numeric pattern (e.g. `QAMode: "off"` must
    stay "off", not False). Unknown keys are coerced.

    Idempotent : passing an already-coerced dict returns it unchanged
    (non-string values pass through `coerce_scalar`'s isinstance guard).
    """
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k in STRING_ENUM_KEYS:
            out[k] = v
        else:
            out[k] = coerce_scalar(v)
    return out


def stack_md_path(root: Path | None = None) -> Path:
    return workspace_root((root or repo_root())) / "stack" / "stack.md"


# ---------------------------------------------------------------------------
# mtime-keyed read cache (v7.0.0-alpha, audit CRIT-2)
# ---------------------------------------------------------------------------
# `stack.md` is the SSoT consumed by ~10 scripts on every /sdd-full run
# (preflight, validate_*, phase_planner, dev-*, qa). Without caching, a run
# with N=5 US triggers ≥ 20 reads + regex reparse of the same ~5-10 KB file.
# The cache is keyed on (resolved_path_str, mtime_ns) so any edit to
# stack.md invalidates the entry automatically (next call sees a new key).
# Bounded to maxsize=4 to cover the common cases (default root, occasional
# alt root from tests, optional team/profile overlays).


@lru_cache(maxsize=4)
def _read_text_cached(path_str: str, mtime_ns: int) -> str:
    """Cached file read keyed on (resolved path, mtime_ns).

    Do NOT call directly — go through `read_stack_md_text()` which
    performs the existence + stat lookup that produces the cache key.
    Raises OSError if the file vanished between stat and read (rare race
    condition handled by the caller).

    Encodage (audit 2026-08-26) : `utf-8-sig` + `errors="replace"`.
    `stack.md` est gitignored, edite a la main, sous Windows, et porte des
    commentaires accentues. Un re-save par un editeur en ANSI (cp1252) faisait
    remonter un `UnicodeDecodeError` NON attrape a travers `read_project_config`
    (~20 appelants) et `get_active_stack_paths` (~7) : tous les gates cassaient
    d'un coup, avec une traceback brute donc sans prefixe `[CLASS]` (violation
    `error-classification.md` §5). `utf-8-sig` absorbe aussi le BOM, alignant
    ce lecteur sur ses jumeaux `stack_config.py` / `stack_db_config.py` /
    `harness_preflight.py` / `conformance_run.py`.
    """
    del mtime_ns  # part of the key only — discriminates cached entries
    return Path(path_str).read_text(encoding="utf-8-sig", errors="replace")


def read_stack_md_text(root: Path | None = None) -> str | None:
    """Read `stack.md` with mtime-based caching, or None if absent.

    Used by `read_project_config`, `get_active_stack_paths`, and
    `layered_config._read_project_section`. Single source of I/O for the
    Project Config / Active Stacks lookups.

    Returns None when the file does not exist or is unreadable. The cache
    auto-invalidates when the file mtime changes (Tech Lead edit, sync_stack_md,
    git checkout).
    """
    path = stack_md_path(root)
    try:
        stat = path.stat()
    except OSError:
        return None
    try:
        return _read_text_cached(str(path.resolve()), stat.st_mtime_ns)
    except (OSError, ValueError):
        # OSError    : file vanished between stat() and read().
        # ValueError : couvre UnicodeDecodeError / LookupError (encodage exotique).
        #              Avec `errors="replace"` ci-dessus c'est desormais une
        #              ceinture de securite, plus le chemin nominal. Traiter comme
        #              absent plutot que crasher les ~27 appelants (audit 2026-08-26).
        return None



def section_body(text: str, heading: str) -> str | None:
    """Extract body between `## {heading}` and next H2 (or EOF).

    Heading is regex-escaped; whitespace tolerant.

    v7.0.0-alpha (audit CRIT-3) : delegates to `sdd_lib.markdown_io.section_body`
    (SSoT for markdown section parsing). Kept as a re-export to preserve
    the public API used by ~10 callers.
    """
    # Imported locally to avoid a circular import at module load time
    # (markdown_io is leaf, project_config is mid-tier).
    from sdd_lib.markdown_io import section_body as _ssot_section_body
    return _ssot_section_body(text, heading)


def parse_kv_block(
    block: str,
    keys: tuple[str, ...] | None = None,
    *,
    coerce: bool = False,
) -> dict[str, Any]:
    """Parse `Key: value` lines from a markdown block.

    Strips outer quotes. If `keys` is provided, only those keys are returned.

    YAML-style inline comments are stripped (audit mineur 2026-06-05 fix —
    previously `PlanReviewDefault: false  # mode café` was parsed as the
    literal string `"false  # mode café"` triggering TYPE_MISMATCH in
    validate_project_config.py). A `#` is treated as the start of a comment
    only when **not inside quotes** ; quoted values like `"secret#1"` are
    preserved intact.

    Args:
        block: raw markdown text of the section.
        keys: optional whitelist of keys to keep.
        coerce: when True (opt-in, v7.0.0-alpha), apply `coerce_config_types`
            to convert YAML-shaped int / float / bool strings to native
            Python types. Default False preserves byte-identical behaviour
            with v6.x for existing callers that handle casting themselves.
    """
    config: dict[str, str] = {}
    for line in block.splitlines():
        m = _KV_RE.match(line)
        if not m:
            continue
        key = m.group(1)
        raw_value = m.group(2)
        # Strip inline `#` comment unless `#` appears inside quotes.
        # Heuristic: if `#` is preceded by an unbalanced quote, keep as-is.
        if "#" in raw_value:
            # Count quotes before each `#` to decide if it's inside a string.
            hash_idx = raw_value.find("#")
            prefix = raw_value[:hash_idx]
            if prefix.count('"') % 2 == 0 and prefix.count("'") % 2 == 0:
                raw_value = prefix
        value = raw_value.strip().strip('"').strip("'")
        if keys is not None and key not in keys:
            continue
        if value:
            config[key] = value
    if coerce:
        return coerce_config_types(config)
    return config


def read_project_config(
    root: Path | None = None,
    *,
    keys: tuple[str, ...] | None = None,
    coerce: bool = False,
) -> dict[str, Any]:
    """Parse `## Project Config` section from stack.md (restricted, not whole file).

    v6.10.2+: applies alias normalization (FrontendName → AppName) and
    namespace auto-derive (AppNamespace ← AppName, BackendNamespace ← BackendName)
    before key filtering, so callers can keep using the canonical `{AppName}` /
    `{AppNamespace}` tokens regardless of which key the user wrote in stack.md.

    v7.0.0-alpha : `coerce=True` returns native types (int / float / bool)
    for non-enum keys. Default False = legacy behaviour (strings).

    v7.0.0-alpha (audit CRIT-2) : I/O cached on `(path, mtime_ns)` via
    `read_stack_md_text()`. Parsing still runs per call (cheap regex).
    """
    text = read_stack_md_text(root)
    if text is None:
        return {}
    block = section_body(text, "Project Config")
    if block is None:
        return {}
    raw = parse_kv_block(block)
    normalized = normalize_project_aliases(raw)
    # Expand ${VAR}/$VAR placeholders (e.g. FrontendLocalPort: ${FrontendLocalPort})
    # from .env + real env. Best-effort: unresolved placeholders stay literal.
    # Done before keys-filter/coerce so a resolved "5187" coerces to int 5187.
    from sdd_lib.env_placeholders import resolve_config
    normalized = resolve_config(normalized, root or repo_root())
    if keys is not None:
        normalized = {k: v for k, v in normalized.items() if k in keys}
    if coerce:
        return coerce_config_types(normalized)
    return normalized


def normalize_project_aliases(raw: dict[str, str]) -> dict[str, str]:
    """Naming aliases + namespace auto-derive (v6.10.2+).

    Aliases :
        FrontendName → AppName (canonical framework token)
        AppName (legacy) stays as AppName

    Auto-derivations (only if not explicit in stack.md), convention
    "namespace = project name" documented in CLAUDE.md §1 :
        AppNamespace      ← AppName
        BackendNamespace  ← BackendName

    Precedence : explicit AppName beats FrontendName when both present.

    v7.0.0-alpha audit P0-doc 2026-06-05 : warn on stderr when both
    `AppName` AND `FrontendName` are set with diverging values — the
    canonical resolution silently uses `AppName`, but the Tech Lead
    likely intended the same value (drift means one of the two is stale
    after a rename). Non-blocking; the Tech Lead arbitrates by editing
    `stack.md`.
    """
    import sys as _sys

    out = dict(raw)
    app = out.get("AppName")
    fe = out.get("FrontendName")
    if app and fe and app != fe:
        _sys.stderr.write(
            f"[project-config] WARN: AppName ('{app}') and FrontendName ('{fe}') diverge "
            f"in stack.md ## Project Config. Canonical token is AppName — FrontendName ignored.\n"
            f"FIX: drop FrontendName (or align it to AppName) to silence this warning.\n"
        )
    if "AppName" not in out and "FrontendName" in out:
        out["AppName"] = out["FrontendName"]
    if "AppNamespace" not in out and "AppName" in out:
        out["AppNamespace"] = out["AppName"]
    if "BackendNamespace" not in out and "BackendName" in out:
        out["BackendNamespace"] = out["BackendName"]
    return out


def get_active_stack_paths(root: Path | None = None, *, normalize: bool = True) -> list[str]:
    """List stack paths referenced under the `## Active ...` sections of `stack.md`.

    v7.0.0-alpha (audit CRIT-2) : I/O cached via `read_stack_md_text()`.

    Audit 2026-08-25 : returns **canonical `.sdd/stacks/...`** paths by
    default. A legacy `stack.md` still referencing `.claude/stacks/...` is
    parsed identically and rewritten on the fly, so downstream consumers
    (`context_budget` pattern matching, disk resolution) get one single
    truth. Pass `normalize=False` to get the raw declared strings (linters
    reporting on the file's own content).
    """
    text = read_stack_md_text(root)
    if text is None:
        return []
    paths: list[str] = []
    for line in text.splitlines():
        m = _ACTIVE_STACK_RE.match(line)
        if m:
            paths.append(normalize_stack_path(m.group(1)) if normalize else m.group(1))
    return paths
