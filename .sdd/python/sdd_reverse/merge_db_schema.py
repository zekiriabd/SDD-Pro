"""merge_db_schema.py — Deterministic union of base + enrichment (ADV-3).

Phase 2 produces db-schema.enrichment.json (separate file). This script
applies a strict union onto db-schema.json (base) and writes
db-schema.merged.json. Phase 3 reads .merged.json if present, else falls
back to base.

Public API:
    merge_schemas(base, enrichment, force_overrides=None) -> tuple[merged, conflicts]
    main(argv=None) -> int      # CLI

Rules:
    - Union strict : keys(merged) ⊇ keys(base). Assertion before write.
    - Never delete entities/fields from base.
    - addedField with type conflict vs base → ADV-12: base wins by default,
      INFO [REVERSE_ENRICHMENT_TYPE_CONFLICT] emitted in `conflicts[]`.
      Override per-field with --force-enrichment-on Entity.field.
    - addedRelation referencing unknown entity → REJECTED, ERROR
      [REVERSE_ENRICHMENT_INVALID] (never silently dropped).
    - observedEntitiesNotInBase / observedRelationsNotInBase (audit C3
      2026-06-10) : entités/relations DÉDUITES par le tech-auditor depuis le
      code (requêtes SQL inline) alors qu'elles sont absentes du DDL source.
      Appended into merged with `"deduced": true` (clearly flagged — the
      extractor caps their confidence to medium per §9.2). Base entity of the
      same name wins (observed skipped + conflict INFO). Invalid observed
      relations are recorded in conflicts[], never silently dropped, never
      fatal (the observed channel is explicitly speculative).
      Avant ce canal, le run EDI perdait 19 entités + 10 FKs en prose.

Exit codes:
    0  merged successfully
    1  validation failure (e.g. missing args, base unparseable)
    2  enrichment_invalid (ADV-3 hard fail)
    3  I/O error
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path
from typing import Any

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.atomic_write_local import atomic_write_text


def _index_entities(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["name"]: e for e in schema.get("entities", [])}


def _index_fields(entity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["name"]: f for f in entity.get("fields", [])}


def merge_schemas(
    base: dict[str, Any],
    enrichment: dict[str, Any],
    force_overrides: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Union base + enrichment.

    Args:
        base: db-schema.json content
        enrichment: db-schema.enrichment.json content
        force_overrides: set of "Entity.field" strings allowed to override base

    Returns:
        (merged_schema, conflicts) — conflicts is a list of issue dicts
        with `class` (REVERSE_ENRICHMENT_TYPE_CONFLICT |
        REVERSE_ENRICHMENT_INVALID), `entity`, `field` (opt), `message`.

    Raises ValueError on hard ADV-3 violation (unknown entity reference).
    """
    force_overrides = force_overrides or set()
    merged = copy.deepcopy(base)
    merged["completeness"] = "enriched"
    merged["mergeDate"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    merged["mergedFrom"] = ["db-schema.json", "db-schema.enrichment.json"]
    conflicts: list[dict[str, Any]] = []

    base_entities = _index_entities(merged)

    # === observedEntitiesNotInBase (C3 — deduced entities channel) ===
    # Processed FIRST so addedRelations/observedRelations can reference them.
    # Shape tolerance : `name` OR `entity` ; `fields` (dict list) OR
    # `observedFields` (bare column-name list — typed "unknown").
    for obs in enrichment.get("observedEntitiesNotInBase") or []:
        name = obs.get("name") or obs.get("entity")
        if not name:
            continue
        if name in base_entities:
            conflicts.append({
                "class": "REVERSE_ENRICHMENT_TYPE_CONFLICT",
                "entity": name,
                "message": "observed entity already in base schema — base wins, "
                           "observed copy skipped",
                "resolution": "base_wins",
            })
            continue
        fields = obs.get("fields")
        if not fields and obs.get("observedFields"):
            fields = [
                {"name": fn, "type": "unknown", "primaryKey": fn.lower() == "id",
                 "identity": False, "nullable": True, "default": None}
                for fn in obs["observedFields"] if isinstance(fn, str)
            ]
        evidence = obs.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        ent = {
            "name": name,
            "table": obs.get("table") or name,
            "fields": fields or [],
            "evidence": evidence,
            "deduced": True,
        }
        merged.setdefault("entities", []).append(ent)
        base_entities[name] = ent

    # === observedRelationsNotInBase (C3 — deduced FKs channel) ===
    for obs_rel in enrichment.get("observedRelationsNotInBase") or []:
        from_e = obs_rel.get("from", {}).get("entity")
        to_e = obs_rel.get("to", {}).get("entity")
        if from_e not in base_entities or to_e not in base_entities:
            conflicts.append({
                "class": "REVERSE_ENRICHMENT_INVALID",
                "entity": from_e or "?",
                "message": (
                    f"observed relation references unknown entity "
                    f"(from={from_e}, to={to_e}) — skipped (speculative channel)"
                ),
                "resolution": "skipped",
            })
            continue
        rel = copy.deepcopy(obs_rel)
        rel["deduced"] = True
        merged.setdefault("relations", []).append(rel)

    # === addedFields ===
    for added in enrichment.get("addedFields") or []:
        entity_name = added.get("entity")
        field_data = added.get("field")
        if not entity_name or not field_data:
            continue
        if entity_name not in base_entities:
            # ADV-3 hard fail: enrichment references unknown entity
            raise ValueError(
                f"[REVERSE_ENRICHMENT_INVALID] addedField references unknown entity "
                f"'{entity_name}' (not in base schema)"
            )
        ent = base_entities[entity_name]
        existing_fields = _index_fields(ent)
        fname = field_data.get("name")
        if not fname:
            continue
        if fname not in existing_fields:
            # Pure addition: append
            ent.setdefault("fields", []).append(field_data)
            continue
        # Field exists: check type conflict (ADV-12)
        existing_type = existing_fields[fname].get("type", "").strip().lower()
        new_type = (field_data.get("type") or "").strip().lower()
        if existing_type and new_type and existing_type != new_type:
            override_key = f"{entity_name}.{fname}"
            if override_key in force_overrides:
                # Override: enrichment wins
                idx = next(i for i, f in enumerate(ent["fields"]) if f["name"] == fname)
                ent["fields"][idx] = field_data
                conflicts.append({
                    "class": "REVERSE_ENRICHMENT_TYPE_CONFLICT",
                    "entity": entity_name,
                    "field": fname,
                    "message": (
                        f"type conflict resolved by --force-enrichment-on "
                        f"{override_key} (base={existing_type} → enrichment={new_type})"
                    ),
                    "resolution": "enrichment_wins",
                })
            else:
                conflicts.append({
                    "class": "REVERSE_ENRICHMENT_TYPE_CONFLICT",
                    "entity": entity_name,
                    "field": fname,
                    "message": (
                        f"base={existing_type} vs enrichment={new_type}. "
                        f"Base wins by default. Override with "
                        f"--force-enrichment-on {override_key}"
                    ),
                    "resolution": "base_wins",
                })
            # else: identical type → silent idempotent

    # === addedRelations ===
    existing_relations = {(r.get("name"), r["from"]["entity"], r["from"]["field"])
                          for r in merged.get("relations") or []
                          if r.get("from")}
    for added_rel in enrichment.get("addedRelations") or []:
        from_e = added_rel.get("from", {}).get("entity")
        to_e = added_rel.get("to", {}).get("entity")
        if from_e not in base_entities or to_e not in base_entities:
            raise ValueError(
                f"[REVERSE_ENRICHMENT_INVALID] addedRelation references unknown entity "
                f"(from={from_e}, to={to_e})"
            )
        key = (added_rel.get("name"), from_e, added_rel.get("from", {}).get("field"))
        if key in existing_relations:
            continue
        merged.setdefault("relations", []).append(added_rel)

    # === addedIndexes ===
    existing_idx_names = {i.get("name") for i in merged.get("indexes") or []}
    for added_idx in enrichment.get("addedIndexes") or []:
        if added_idx.get("name") in existing_idx_names:
            continue
        merged.setdefault("indexes", []).append(added_idx)

    # === addedConstraints ===
    existing_constr_names = {c.get("name") for c in merged.get("constraints") or []}
    for added_c in enrichment.get("addedConstraints") or []:
        if added_c.get("name") in existing_constr_names:
            continue
        merged.setdefault("constraints", []).append(added_c)

    # Sanity assertion: merged ⊇ base keys
    for ent_name, base_ent in _index_entities(base).items():
        merged_ent = next((e for e in merged["entities"] if e["name"] == ent_name), None)
        assert merged_ent is not None, f"merge violated: {ent_name} disappeared"
        base_fnames = {f["name"] for f in base_ent.get("fields", [])}
        merged_fnames = {f["name"] for f in merged_ent.get("fields", [])}
        assert base_fnames.issubset(merged_fnames), (
            f"merge violated: {ent_name} lost fields {base_fnames - merged_fnames}"
        )

    return merged, conflicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="merge_db_schema",
        description="Merge db-schema.enrichment.json onto base db-schema.json (ADV-3 union strict).",
    )
    parser.add_argument("--base", required=True, help="Path to db-schema.json")
    parser.add_argument("--enrichment", required=True, help="Path to db-schema.enrichment.json")
    parser.add_argument("--output", required=True, help="Path to db-schema.merged.json")
    parser.add_argument(
        "--force-enrichment-on", action="append", default=[], metavar="Entity.field",
        help="Allow enrichment to override base on this field (repeatable). ADV-12 escape hatch.",
    )
    parser.add_argument("--json", action="store_true", help="Emit conflicts report as JSON on stdout")
    args = parser.parse_args(argv)
    from sdd_reverse.console_safe import ensure_console_safe
    ensure_console_safe()

    base_path = Path(args.base)
    enrich_path = Path(args.enrichment)
    output_path = Path(args.output)

    if not base_path.is_file():
        print(f"ERROR: base not found: {base_path}", file=sys.stderr)
        return 1
    if not enrich_path.is_file():
        print(f"ERROR: enrichment not found: {enrich_path}", file=sys.stderr)
        return 1

    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
        enrichment = json.loads(enrich_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: I/O or JSON parse error: {e}", file=sys.stderr)
        return 3

    force_overrides = set(args.force_enrichment_on)

    try:
        merged, conflicts = merge_schemas(base, enrichment, force_overrides)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        atomic_write_text(output_path, json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"ERROR: write failed: {e}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps({
            "ok": True,
            "output": str(output_path),
            "entitiesCount": len(merged.get("entities", [])),
            "relationsCount": len(merged.get("relations", [])),
            "conflicts": conflicts,
        }, ensure_ascii=False))
    else:
        # ASCII markers (M10 — Windows cp1252 console compat)
        deduced = sum(1 for e in merged.get("entities", []) if e.get("deduced"))
        print(f"[GREEN] [MERGE-DB-SCHEMA] {output_path.name} - "
              f"{len(merged.get('entities', []))} entities ({deduced} deduced), "
              f"{len(merged.get('relations', []))} relations, "
              f"{len(conflicts)} conflict(s).")
        for c in conflicts:
            print(f"  [WARN] [{c['class']}] {c.get('entity', '')}.{c.get('field', '')}: {c['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
