"""proc_module_clusterer.py — Group stored procedures into business modules.

User model (confirmed): **1 proc = 1 User Story**, **1 module = 1 FEAT**. A
module is the set of procedures that act on the same business object:

    usp_Contact_Insert / usp_Contact_Delete / usp_Contact_List   → module "Contact"
    usp_Order_Create   / usp_GetOrders      / usp_UpdateOrder     → module "Order"

Heuristic (deterministic, 0 token):
  1. strip a known routine prefix (usp_, sp_, proc_, p_, fn_, ufn_, tvf_, f_…)
  2. tokenise on `_`, `-`, or CamelCase boundaries
  3. drop VERB tokens (insert/get/update/delete/...) and NOISE tokens
     (list/all/byid/by/details/...) → the remaining nouns = the module/object
  4. fall back to a shared-table footprint, then to the schema, when no object
     can be derived (so nothing is ever dropped — traceability over tidiness)

The module name becomes the FEAT `{Name}` (PascalCase, no accents). Two procs
of the same module never get separate FEATs; a proc with no derivable object is
parked in a `Misc` module rather than discarded.

Public API:
    parse_routine_name(raw) -> {prefix, verb, object, tokens}
    learn_name_profile(names) -> {usable, structural, actions, stats}
    cluster(routines) -> {module_name: [routine, ...]}   # routines annotated in place
    cluster_with_report(routines) -> (modules, report)   # + how the grouping was decided

Each routine is annotated in place with `verb`, `object` (its OWN business
object, before any sub-object merge) and `module` (the FEAT it landed in).
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = 1

_PREFIXES = ("usp_", "sp_", "proc_", "prc_", "p_", "ufn_", "fn_", "tvf_", "udf_", "f_")

# Canonical verb → normalised label (drives the US title later).
#
# Audit 2026-08-25: this vocabulary was English-only, which broke the core model
# on a French-named database — and SDD_Pro is a French-first framework whose own
# output is in French. `usp_Facture_Valider` matched no verb, so "Valider" was
# treated as part of the business OBJECT: the module became `FactureValider`
# instead of `Facture`, and it got its own FEAT. On a French legacy database
# that fragments "1 module = 1 FEAT" into "1 procedure = 1 FEAT" — the exact
# anti-pattern the clustering exists to prevent. Verbs are matched
# accent-insensitively (`Créer` and `Creer` both work).
_VERBS = {
    # --- create ---
    "insert": "create", "ins": "create", "add": "create", "create": "create",
    "new": "create", "creer": "create", "creation": "create", "ajouter": "create",
    "ajout": "create", "inserer": "create", "insertion": "create",
    "nouveau": "create", "nouvelle": "create",
    # --- save ---
    "save": "save", "upsert": "save", "merge": "save", "enregistrer": "save",
    "enregistrement": "save", "sauvegarder": "save", "sauver": "save",
    # --- update ---
    "update": "update", "upd": "update", "edit": "update", "modify": "update",
    "set": "update", "modifier": "update", "modification": "update",
    "maj": "update", "actualiser": "update", "changer": "update",
    # --- delete ---
    "delete": "delete", "del": "delete", "remove": "delete", "rmv": "delete",
    "drop": "delete", "supprimer": "delete", "suppression": "delete",
    "effacer": "delete", "retirer": "delete", "purger": "delete",
    # --- read ---
    "get": "read", "list": "read", "select": "read", "sel": "read", "read": "read",
    "fetch": "read", "find": "read", "search": "read", "load": "read",
    "lookup": "read", "count": "read", "exists": "read", "check": "read",
    "report": "read", "export": "read",
    "lire": "read", "lister": "read", "obtenir": "read", "recuperer": "read",
    "rechercher": "read", "chercher": "read", "trouver": "read",
    "consulter": "read", "afficher": "read", "compter": "read",
    "existe": "read", "exporter": "read", "extraire": "read", "charger": "read",
    # --- validate ---
    "validate": "validate", "valider": "validate", "validation": "validate",
    "verifier": "validate", "verification": "validate", "controler": "validate",
    "controle": "validate",
    # --- compute ---
    "calc": "compute", "compute": "compute", "calculer": "compute",
    "calcul": "compute", "recalculer": "compute",
    # --- process ---
    "process": "process", "traiter": "process", "traitement": "process",
    "generer": "process", "generation": "process", "cloturer": "process",
    "cloture": "process",
    # --- import / sync / notify ---
    "import": "import", "importer": "import", "importation": "import",
    "sync": "sync", "synchroniser": "sync", "synchro": "sync",
    "send": "notify", "notify": "notify", "notifier": "notify",
    "envoyer": "notify", "alerter": "notify", "relancer": "notify",
    # `Liste` as the ACTION, e.g. `SP_API_ShopperAds_Liste_Impression`. English
    # `list` already worked because it sits in both vocabularies and the verb
    # check runs first; `liste` was only in _NOISE, so it was silently dropped
    # and the routine ended up with no verb at all (audit 2026-08-25).
    "liste": "read",
}

# Subsystem / namespace tokens. These are NOT the business object — but they are
# not noise either: a BI reporting routine and an API routine acting on the same
# object belong to different subsystems and must not be merged into one FEAT.
# They are kept as a module PREFIX (`BI-Campgne`) instead of being glued into the
# object name, which used to yield `BiCampgnePv`.
# Deliberately a short, explicit list: guessing a namespace from any short
# uppercase token would eat real business acronyms (`PV`, `TVA`, `RIB`).
_NAMESPACES = {
    "bi": "BI", "api": "API", "ws": "WS", "etl": "ETL", "rpt": "RPT",
    "adm": "ADM", "sys": "SYS", "job": "JOB", "batch": "BATCH", "svc": "SVC",
    "web": "WEB", "dwh": "DWH", "ods": "ODS",
}
# Tokens that are neither verb nor object — noise to strip from the object name.
# French qualifiers included for the same reason as the verbs above; they are
# kept in the US NAME (finding M4) so two US of a module stay distinguishable.
_NOISE = frozenset({
    "list", "all", "byid", "by", "id", "ids", "details", "detail", "info",
    "data", "rows", "row", "result", "results", "page", "paged", "full", "single",
    "tbl", "tmp", "temp", "v", "vw",
    "liste", "tous", "toutes", "tout", "par", "complet", "complete",
    "unitaire", "pagine", "resultat", "resultats", "donnees", "lignes", "ligne",
    "infos", "fiche",
})

# Routine-TYPE markers — a subset of the noise above, kept apart because of what
# happens DOWNSTREAM. Position-independent on purpose: real databases put them at
# the front (`SP_`, `STP_`), in the middle (`BI_SP_…`) or glued into a CamelCase
# hump (`BriefPrcFidme`). The `_PREFIXES` list below only ever matched a LEADING
# one, so `STP_` and an inner `Prc` leaked into the business object name
# (audit 2026-08-25, real samples from the field).
#
# Unlike the other noise, these are NOT returned as qualifier tokens: the noise a
# name drops from the module is reused to keep two US of one module distinct
# (`Consulter-Contact-ParId` vs `Consulter-Contact-Liste`), and "this object is a
# stored procedure" distinguishes nothing — it just produced US named
# `Consulter-Client-Usp`.
_TYPE_MARKERS = frozenset({
    "sp", "stp", "sproc", "usp", "proc", "prc", "prcd",
    "fn", "ufn", "udf", "tvf", "func",
})
_NOISE = _NOISE | _TYPE_MARKERS

# Accent folding for the two vocabularies above (é→e, à→a, ç→c…). SQL identifiers
# rarely carry accents, but a French shop that names one `usp_Facture_Créer` must
# not silently fall off the mapping.
_ACCENTS = str.maketrans(
    "àáâãäåçèéêëìíîïñòóôõöùúûüýÿÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝ",
    "aaaaaaceeeeiiiinooooouuuuyyAAAAAACEEEEIIIINOOOOOUUUUY",
)


def _fold(token: str) -> str:
    """Lower-cased, accent-folded token for vocabulary lookup."""
    return (token or "").translate(_ACCENTS).lower()


# --------------------------------------------------------------------------- #
# DYNAMIC corpus profiling (audit 2026-08-25)
# --------------------------------------------------------------------------- #
# Confirmed with the Tech Lead: a real database has 100+ different naming
# structures — `SP_Bpm_PrcUpdateConfiguration_Select`,
# `STP_BriefPrcFidme_Select_by_ID`, `BI_SP_Campgne_PV_DeleteById`,
# `SP_API_ShopperAds_Liste_Impression`. Prefixes vary, subsystem tokens sit at
# different depths, abbreviations are undecodable (`Prc`, `Campgne`, `Fidme`),
# verbs appear at the front, in the middle, at the end, sometimes TWICE, in two
# languages. Any fixed list of prefixes/verbs/noise fixes one structure out of a
# hundred and risks breaking another.
#
# So the structure is MEASURED instead of declared. Two statistics separate a
# structural token from a business token without knowing any convention:
#
#   document frequency — a business object (`Campgne`, `ShopperAds`) appears in a
#     handful of names; a structural marker (`SP`, `STP`, `BI`, `Prc`) appears in
#     a large share of them.
#   positional concentration — a structural marker sits at a fixed depth (almost
#     always the first or second token), while a business token floats.
#
# Requiring BOTH is what protects a database whose dominant business object is
# frequent: `Client` may appear in 30% of names, but not always in position 0.
#
# The same idea discovers ACTIONS with no verb dictionary: a frequent token
# concentrated at the LAST position is the action (`…_Select`, `…_Liste_…`).

# A segment must appear in at least this share of names to be a candidate marker.
_PROFILE_DF_RATIO = 0.15
# …and in at least this many names (guards tiny corpora where ratios are noise).
_PROFILE_MIN_DF = 3
# Below this many routines, statistics mean nothing — fall back to the static
# vocabularies, and say so in the report rather than pretending to have learned.
_PROFILE_MIN_NAMES = 8

_SEGMENT_SPLIT_RE = re.compile(r"[_\-\s]+")


def _segments(name: str) -> list[str]:
    """Split a routine name on its EXPLICIT delimiters only — never CamelCase.

    The distinction is load-bearing. `ShopperAds` is one delimited segment and
    one business concept; splitting it on the CamelCase hump let the profiler see
    `Shopper` as a frequent standalone token and classify it as structural,
    which silently renamed the module to `Ads`. Structural analysis therefore
    works on segments; CamelCase is only split later, inside a segment that
    survived.
    """
    return [s for s in _SEGMENT_SPLIT_RE.split(str(name or "").split(".")[-1].strip("[]")) if s]


def _is_business_segment(segment: str) -> bool:
    """A segment that is neither a known verb, nor noise, nor a bare number."""
    f = _fold(segment)
    return not (f in _VERBS or f in _NOISE or f.isdigit())


def _head_segment(segments: list[str]) -> str:
    """The DEEPEST business segment of a name — its head noun.

    `SP_Client_Creer` → `Client`. `SP_Bpm_PrcWorkflow_Select` → `PrcWorkflow`.
    This is the discriminator the first attempt lacked: a subsystem prefix
    (`SP`, `BI`, `Bpm`) is NEVER the head noun, because something business-y
    always follows it, whereas a real object frequently IS the head.
    """
    for segment in reversed(segments):
        if _is_business_segment(segment):
            return _fold(segment)
    return ""


def learn_name_profile(names: list[str]) -> dict[str, Any]:
    """Infer a database's own naming structure from its routine names.

    Returns `{"usable", "structural", "actions", "stats"}`:
      structural — segments to drop from the business object (prefixes, routine
                   type markers, subsystem codes), discovered, not declared.
      actions    — segments this database uses as a verb, whatever the language,
                   because they always sit last.

    The rule for `structural` is: FREQUENT **and never the head noun**. Both
    halves matter. Frequency alone flags a dominant business object; "sits at the
    front" alone flags every object in a `PREFIX_Object_Verb` convention, which
    is how the first version of this profiler erased `Client`.

    Pure and deterministic: same corpus in, same profile out.
    """
    per_name = [_segments(n) for n in names]
    per_name = [s for s in per_name if s]
    n = len(per_name)
    if n < _PROFILE_MIN_NAMES:
        return {"usable": False, "structural": set(), "actions": set(),
                "stats": {"names": n, "reason": "corpus too small to profile"}}

    df: dict[str, int] = {}
    head_count: dict[str, int] = {}
    last_count: dict[str, int] = {}
    for segments in per_name:
        head = _head_segment(segments)
        folded = [_fold(s) for s in segments]
        for f in set(folded):                  # once per NAME, not per occurrence
            df[f] = df.get(f, 0) + 1
        if head:
            head_count[head] = head_count.get(head, 0) + 1
        if folded:
            last_count[folded[-1]] = last_count.get(folded[-1], 0) + 1

    threshold = max(_PROFILE_MIN_DF, int(round(_PROFILE_DF_RATIO * n)))
    structural: set[str] = set()
    actions: set[str] = set()
    for segment, count in df.items():
        if count < threshold:
            continue
        # Verbs and noise already have their own handling; letting them fall into
        # `structural` would be a confusing duplicate classification.
        if segment in _VERBS or segment in _NOISE:
            continue
        if head_count.get(segment, 0) == 0:
            # Frequent, and never the head noun of any name → structure.
            structural.add(segment)
        elif (last_count.get(segment, 0) == count
              and segment not in _VERBS):
            # Frequent, always the LAST segment, unknown to the verb dictionary →
            # this database's own action word. Discovered, not declared.
            actions.add(segment)

    return {
        "usable": True,
        "structural": structural,
        "actions": actions,
        "stats": {
            "names": n,
            "distinctSegments": len(df),
            "dfThreshold": threshold,
            "structural": sorted(structural),
            "actions": sorted(actions),
        },
    }


def _strip_known_prefix(name: str) -> str:
    core = name.strip().strip("[]")
    low = core.lower()
    for pre in _PREFIXES:
        if low.startswith(pre):
            return core[len(pre):]
    return core


def _keep_case(token: str) -> str:
    """Capitalise a word, but leave an acronym intact.

    `str.capitalize()` turned `PV` into `Pv` and `TVA` into `Tva` — a fidelity
    loss on identifiers that carry meaning (`PV`, `RIB`, `TVA`, `HT`, `TTC`).
    A token that is entirely upper-case and at least two characters long is an
    acronym, not a word.
    """
    t = token or ""
    if len(t) >= 2 and t.isupper():
        return t
    return t.capitalize()


# Accent-aware character classes: the previous pattern used bare [a-z]/[A-Z],
# so `Créer` split into ("Cr", "er") and never matched anything.
_UPPER = "A-ZÀ-ÖØ-Þ"
_LOWER = "a-zß-öø-ÿ"
_TOKEN_RE = re.compile(
    rf"[{_UPPER}]+(?=[{_UPPER}][{_LOWER}])|[{_UPPER}]?[{_LOWER}]+|[{_UPPER}]+|\d+"
)


def _split_tokens(core: str) -> list[str]:
    # split on separators, then on CamelCase humps
    parts: list[str] = []
    for chunk in re.split(r"[_\-\s]+", core):
        if not chunk:
            continue
        parts.extend(_TOKEN_RE.findall(chunk) or [chunk])
    return [p for p in parts if p]


def parse_routine_name(
    raw: str, profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Split a routine name into namespace / verb / business object / qualifiers.

    `profile` (from `learn_name_profile`) makes this DYNAMIC: tokens the corpus
    itself revealed as structural are dropped whatever they are, and a token the
    corpus uses as a trailing action is read as the verb even if it belongs to no
    dictionary. Without a profile the static vocabularies apply — which is the
    right behaviour for a handful of routines, where statistics say nothing.
    """
    profile = profile or {}
    learned_structural: set[str] = profile.get("structural") or set()
    learned_actions: set[str] = profile.get("actions") or set()

    segments = _segments(raw)
    verb = None
    namespace = ""
    object_tokens: list[str] = []
    noise_tokens: list[str] = []

    # The TRAILING action decides the verb, before anything is consumed. In
    # `SP_Bpm_PrcUpdateConfiguration_Select` the first dictionary verb (`Update`)
    # is part of the object's NAME while the real action is the final `Select`;
    # reading left-to-right took `Update` as the verb and glued `Select` onto the
    # object, inventing a `ConfigurationSelect` that does not exist.
    action_segment = ""
    for seg in reversed(segments):
        f = _fold(seg)
        if f in learned_actions or f in _VERBS:
            action_segment = f
            verb = _VERBS.get(f) or "read"
            break
        if _is_business_segment(seg):
            break              # a business segment ends the trailing-action zone

    # Tokens are only extracted from segments that survive structural filtering,
    # so a CamelCase business term (`ShopperAds`) is never dissected by it.
    consumed_action = False
    for seg in segments:
        sf = _fold(seg)
        if sf in learned_structural:
            if sf in _NAMESPACES and not namespace:
                namespace = _NAMESPACES[sf]
            continue
        if sf == action_segment and not consumed_action:
            consumed_action = True
            continue
        for tok in _split_tokens(seg):
            tl = _fold(tok)
            # A namespace is only recognised BEFORE the business object starts —
            # afterwards the same token is business content (`Client_Web` is about
            # a web client, not the WEB subsystem).
            if not object_tokens and not namespace and tl in _NAMESPACES:
                namespace = _NAMESPACES[tl]
                continue
            if verb is None and tl in _VERBS:
                verb = _VERBS[tl]
                continue
            # A SECOND dictionary verb is not business content either.
            if verb is not None and tl in _VERBS and not object_tokens:
                noise_tokens.append(tok)
                continue
            # Audit 2026-08-25 (M4): noise is dropped from the MODULE name, but
            # it is exactly what distinguishes two US of the same module
            # (`GetContactById` vs `GetContactList` both reduced to
            # "Consulter-Contact"). Returned so the US name can stay unique.
            if tl in _NOISE:
                if tl not in _TYPE_MARKERS:
                    noise_tokens.append(tok)
                continue
            object_tokens.append(tok)

    obj = "".join(_keep_case(t) for t in object_tokens) if object_tokens else ""
    return {"prefix_stripped": "_".join(segments), "verb": verb, "object": obj,
            "namespace": namespace,
            "tokens": [t for s in segments for t in _split_tokens(s)],
            "noise": noise_tokens}


def _sanitize_module(name: str) -> str:
    """FEAT-safe PascalCase module name, CamelCase humps preserved.

    Audit 2026-08-25: this used `str.capitalize()` on each space-separated word,
    which flattened the humps the object builder had just produced —
    `ClientAdresse` came back as `Clientadresse` and `CampgnePV` as `Campgnepv`.
    That is a fidelity loss on its own (the FEAT name is what the Tech Lead
    reads on disk), and it also blinded the sub-object fold, which compares
    module names token by token: a one-word `Clientadresse` has no `Client`
    prefix to match. Tokens are re-split and re-cased through `_keep_case`, so
    acronyms survive too.
    """
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", str(name or "")).strip()
    if not cleaned:
        return "Misc"
    return "".join(
        _keep_case(tok)
        for word in cleaned.split()
        for tok in (_split_tokens(word) or [word])
    )


# --------------------------------------------------------------------------- #
# Sub-object folding (audit 2026-08-25)
# --------------------------------------------------------------------------- #
# A relational model names its dependent objects after their aggregate root:
# `ClientAdresse`, `ClientContact`, `CommandeLigne`, `FactureLigneTva`. The name
# heuristic reads each of those as a business object of its own, so a database
# with a `Client` module and a `ClientAdresse` module produced TWO FEATs for one
# aggregate — the same fragmentation the clustering exists to prevent, only one
# level down.
#
# The fold is deliberately narrow, because the cost of a wrong merge (two real
# business objects collapsed into one FEAT) is higher than the cost of a missed
# one (one extra FEAT, still traceable):
#
#   - PREFIX only. `ClientAdresse` folds into `Client` because the FIRST token
#     names the aggregate root. `AdresseClient` does NOT fold: there the head
#     noun is `Adresse`, and folding it into `Client` would be a guess about
#     which of the two words carries the module.
#   - The parent must ALREADY be a module of this corpus. A lone `ClientAdresse`
#     with no `Client` routine anywhere keeps its own module — inventing a
#     `Client` FEAT with no procedure in it would be worse.
#   - Token boundaries only, never string prefixes. `Clientele` must not fold
#     into `Client`; the comparison is on the CamelCase token tuple.
#   - `Misc` never absorbs anything (it is the "could not tell" bucket, not an
#     aggregate root).
#
# The routine keeps its own `object` (`ClientAdresse`), so the US slug stays
# distinctive inside the merged FEAT — CLAUDE.md §1 forbids two US of one FEAT
# sharing a {Name}.


def _module_tokens(module: str) -> tuple[str, ...]:
    """Folded CamelCase token tuple of a module name, for boundary-safe compare."""
    return tuple(_fold(t) for t in _split_tokens(module))


def _merge_subobjects(
    modules: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Fold `{Root}{SubObject}` modules into `{Root}` when `{Root}` is a module.

    Returns the rewritten module map and `{merged_module: target_module}` for the
    report. Multi-level compounds resolve transitively
    (`ClientAdresseLigne` → `ClientAdresse` → `Client`) via the target chain.
    """
    by_tokens: dict[tuple[str, ...], str] = {}
    for name in modules:
        by_tokens.setdefault(_module_tokens(name), name)

    direct: dict[str, str] = {}
    for name in modules:
        if name == "Misc":
            continue
        tokens = _module_tokens(name)
        if len(tokens) < 2:
            continue
        # Longest proper prefix wins, so the fold walks up one level at a time
        # and a `ClientAdresse` module (if it exists) is preferred over `Client`.
        for cut in range(len(tokens) - 1, 0, -1):
            parent = by_tokens.get(tokens[:cut])
            if parent and parent != name and parent != "Misc":
                direct[name] = parent
                break

    def _resolve(name: str) -> str:
        seen = {name}
        target = name
        while target in direct:
            nxt = direct[target]
            if nxt in seen:          # defensive: a cycle cannot happen (strictly
                break                # decreasing token count) but must not hang
            seen.add(nxt)
            target = nxt
        return target

    merges = {name: _resolve(name) for name in direct}
    merges = {src: dst for src, dst in merges.items() if src != dst}
    if not merges:
        return modules, {}

    merged: dict[str, list[dict[str, Any]]] = {}
    for name, members in modules.items():
        target = merges.get(name, name)
        for r in members:
            r["module"] = target
        merged.setdefault(target, []).extend(members)
    return merged, merges


# A naming convention is only usable if it actually GROUPS. Below these
# thresholds the heuristic is producing one module per routine — i.e. the
# database has no parseable convention — and the dependency graph is a better
# signal than the names (audit 2026-08-25, confirmed by the Tech Lead: "les
# nommages c'est pas structuré, chaque fois un nom différent").
# Aligned with `_PROFILE_MIN_NAMES` (audit 2026-08-25): below that count the
# corpus profile is not learned at all, so the naming path runs on the static
# vocabularies alone and its fragmentation says nothing about the DATABASE — only
# about the sample. Switching strategy on that evidence would be a coin toss.
_AUTO_MIN_ROUTINES = _PROFILE_MIN_NAMES
# modules / routines above which naming is useless. Lowered 0.75 → 0.50
# (audit 2026-08-25) now that sub-object folding runs first: 0.75 only fired when
# the heuristic was producing very nearly one module per routine, which let the
# common "grouped in pairs but not in aggregates" case through unnoticed. At 0.50
# the naming path must average at least two routines per module to be kept — the
# minimum for "1 module = 1 FEAT" to mean anything.
_AUTO_FRAGMENTATION = 0.50
_AUTO_VERBLESS = 0.5          # share of routines whose verb could not be read


def cluster_with_report(
    routines: list[dict[str, Any]], *, use_cohesion: bool | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Group routines into modules, and report HOW the grouping was decided.

    Strategy selection (audit 2026-08-25):
      - `use_cohesion=True`  → dependency cohesion, unconditionally.
      - `use_cohesion=False` → the name heuristic, unconditionally.
      - `use_cohesion=None`  → AUTO (default): try the names, measure whether
        they actually cluster, and fall back to cohesion when they do not.

    On the naming path, sub-objects are folded into their aggregate root
    (`ClientAdresse` → `Client`, see `_merge_subobjects`) BEFORE fragmentation is
    measured — the fold is part of what the naming strategy can achieve, so it
    must be taken into account when judging whether that strategy works.

    AUTO exists because the name heuristic silently degrades to "1 routine =
    1 module" on a database with no convention — which quietly destroys the
    "1 module = 1 FEAT" model and produces one FEAT per stored procedure. The
    fallback is only adopted when it demonstrably groups better, so a database
    WITH a convention keeps the more readable, name-derived module names.
    """
    n = len(routines)
    # Learn this database's own structure first: the profile drives the verb and
    # object reading on BOTH paths, so it must exist even when cohesion is forced.
    profile = learn_name_profile([r.get("name", "") for r in routines])
    if use_cohesion is True:
        modules = _cluster_by_cohesion(routines, profile)
        return modules, {"strategy": "cohesion", "reason": "forced",
                         "routines": n, "modules": len(modules),
                         "profile": profile.get("stats", {})}

    named, merges = _cluster_by_name(routines, profile)
    verbless = sum(1 for r in routines if not r.get("verb"))
    fragmentation = (len(named) / n) if n else 0.0
    report: dict[str, Any] = {
        "strategy": "naming",
        "reason": "naming convention usable",
        "routines": n,
        "modules": len(named),
        "fragmentation": round(fragmentation, 3),
        "verblessRatio": round((verbless / n) if n else 0.0, 3),
        "profile": profile.get("stats", {}),
        # `{ClientAdresse: Client, ...}` — sub-objects folded into their
        # aggregate root, so a Tech Lead can see WHY two objects share a FEAT.
        "subObjectMerges": dict(sorted(merges.items())),
    }
    if use_cohesion is False:
        report["reason"] = "forced"
        return named, report

    unusable = n >= _AUTO_MIN_ROUTINES and (
        fragmentation >= _AUTO_FRAGMENTATION
        or (verbless / n) >= _AUTO_VERBLESS
    )
    if not unusable:
        return named, report

    cohesive = _cluster_by_cohesion(routines, profile)
    # Only switch if the dependency graph genuinely groups better. On a database
    # whose routines share no table and call nothing (or whose bodies are
    # encrypted), cohesion cannot group either — keeping the names is then the
    # honest outcome, and the report says so instead of pretending.
    if len(cohesive) < len(named):
        report.update({
            "strategy": "cohesion",
            "reason": (f"naming unusable (fragmentation="
                       f"{fragmentation:.2f}, verbless="
                       f"{verbless}/{n}) — grouped by dependency cohesion"),
            "modules": len(cohesive),
            "modulesByNaming": len(named),
        })
        return cohesive, report

    # Cohesion just overwrote every routine's `module`/`verb` annotation while it
    # was being evaluated. Since its grouping is rejected, restore the naming
    # one — otherwise the returned modules and the annotations disagree, and the
    # US slugs would be built from a module the FEAT does not use.
    named, merges = _cluster_by_name(routines, profile)
    report["subObjectMerges"] = dict(sorted(merges.items()))
    report["reason"] = (
        f"naming unusable (fragmentation={fragmentation:.2f}) but the dependency "
        f"graph groups no better ({len(cohesive)} modules) — review manually"
    )
    report["degraded"] = True
    report["modulesByCohesion"] = len(cohesive)
    return named, report


def cluster(
    routines: list[dict[str, Any]], *, use_cohesion: bool | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Group routines into modules. Annotates each routine with `verb`/`module`.

    Thin wrapper over `cluster_with_report` for callers that do not need the
    strategy report. See that function for the selection rules.
    """
    return cluster_with_report(routines, use_cohesion=use_cohesion)[0]


def _cluster_by_name(
    routines: list[dict[str, Any]], profile: dict[str, Any] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Name heuristic: strip prefix/namespace/verb/noise, the rest is the object.

    `routines` items use at least {"name": str}. Optional {"schema", "signals"}
    refine the fallback (shared-table footprint, schema grouping).
    `profile` carries the corpus-learned structure (see `learn_name_profile`).

    Returns `(modules, sub_object_merges)`; see `_merge_subobjects`.
    """
    modules: dict[str, list[dict[str, Any]]] = {}
    for r in routines:
        parsed = parse_routine_name(r["name"], profile)
        r["verb"] = parsed["verb"]
        r["noise"] = parsed["noise"]
        module = parsed["object"]
        # The routine's OWN object, kept even when the module it lands in is its
        # aggregate root — this is what keeps the US slug distinctive after a
        # sub-object fold (`Consulter-ClientAdresse` inside FEAT `Client`).
        r["object"] = module
        if not module:
            # Fallback 1: dominant written table; Fallback 2: schema; else Misc.
            sig = r.get("signals") or {}
            written = sig.get("tablesWritten") or []
            read = sig.get("tablesRead") or []
            if written:
                module = _singularize(written[0])
            elif read:
                module = _singularize(read[0])
            elif r.get("schema"):
                module = str(r["schema"])
        module = _sanitize_module(module or "Misc")
        r["module"] = module
        modules.setdefault(module, []).append(r)
    return _merge_subobjects(modules)


def _cluster_by_cohesion(
    routines: list[dict[str, Any]], profile: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """P0.2 cohesion grouping: use the dependency graph, keep verb annotation.

    The names still drive the verb / object / US slug — only the MODULE comes
    from the graph. The learned profile is threaded through so a name read here
    is parsed exactly as it would have been on the naming path.
    """
    from sdd_reverse.sql_dependency_graph import cohesion_modules

    objects = []
    for r in routines:
        sig = r.get("signals") or {}
        objects.append({
            "fqName": r["name"],
            "tablesRead": sig.get("tablesRead") or [],
            "tablesWritten": sig.get("tablesWritten") or [],
            "callsProcs": sig.get("calls") or [],
        })
    assignment = cohesion_modules(objects)
    modules: dict[str, list[dict[str, Any]]] = {}
    for r in routines:
        parsed = parse_routine_name(r["name"], profile)
        r["verb"] = parsed["verb"]
        r["noise"] = parsed["noise"]
        r["object"] = parsed["object"]
        module = _sanitize_module(assignment.get(r["name"], "") or "Misc")
        r["module"] = module
        modules.setdefault(module, []).append(r)
    return modules


# Words that END in -s without being plural. Naively stripping the `s` produced
# module names like `Statu`, `Pay` or `Coli`, which then split a business object
# across two FEATs depending on how each routine happened to be named.
_INVARIABLE = frozenset({
    "status", "statuts", "pays", "colis", "alias", "bonus", "campus", "corpus",
    "news", "series", "analysis", "basis", "axis", "process", "access",
    "adresse", "adresses",   # handled by the generic rule, listed for clarity
})


def _singularize(table: str) -> str:
    # Table names are now schema-qualified (`dbo.Invoices`, finding D1) — a module
    # must be named after the OBJECT, so drop the schema before singularising,
    # otherwise the fallback produced modules called "DboInvoice".
    t = str(table).rsplit(".", 1)[-1].strip().strip("[]`\"")
    if len(t) > 3 and t.lower().endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 2 and t.lower().endswith("s") and not t.lower().endswith("ss"):
        return t[:-1]
    return t
