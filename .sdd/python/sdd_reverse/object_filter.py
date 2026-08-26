"""object_filter.py — Bound the scope of a database introspection run (M6).

Audit finding M6 (2026-08-25): `--full` had no way to restrict what it read. On a
legacy database with a few thousand objects that means every body loaded into
memory, one snapshot file per object, and a `needs_llm` list long enough for the
global cost cap (`[COST_CAP_EXCEEDED]`, $50 by default) to cut the run in half —
leaving a partial set of FEATs and no way to target the interesting schema.

Filtering happens on the ROWS, after the fetch, deliberately:
  - the catalog queries stay untouched, so the read-only guard keeps validating
    exactly the same constant SQL (no parameter injection surface);
  - the same filter applies identically to a live run and to a
    `--from-introspection` replay.

Per the framework's "no silent caps" rule, `apply()` always reports what it
dropped and why — a truncated run must never read as a complete one.

Public API:
    ObjectFilter(schemas=…, include=…, exclude=…, limit=…)
    ObjectFilter.apply(rows, columns) -> (kept_rows, report)
    ObjectFilter.is_active -> bool
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any, Sequence


def _norm(patterns: Sequence[str] | None) -> list[str]:
    """Split comma-separated CLI values and drop blanks."""
    out: list[str] = []
    for raw in patterns or []:
        out.extend(p.strip() for p in str(raw).split(",") if p.strip())
    return out


def _matches(name: str, schema: str, patterns: list[str]) -> bool:
    """Case-insensitive glob against both the bare and the qualified name."""
    bare = name.lower()
    qualified = f"{schema}.{name}".lower() if schema else bare
    return any(fnmatch.fnmatch(bare, p.lower()) or fnmatch.fnmatch(qualified, p.lower())
               for p in patterns)


@dataclass
class ObjectFilter:
    schemas: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    limit: int = 0

    def __post_init__(self) -> None:
        self.schemas = _norm(self.schemas)
        self.include = _norm(self.include)
        self.exclude = _norm(self.exclude)
        self.limit = int(self.limit or 0)

    @property
    def is_active(self) -> bool:
        return bool(self.schemas or self.include or self.exclude or self.limit)

    def apply(
        self, rows: list[tuple], columns: Sequence[str],
    ) -> tuple[list[tuple], dict[str, Any]]:
        """Filter catalog rows. Returns (kept, report).

        `report` carries the counts AND the names dropped by truncation, so the
        caller can log a complete account of what the run did not cover.
        """
        if not self.is_active:
            return rows, {"active": False, "kept": len(rows), "dropped": 0}

        idx_schema = columns.index("schema")
        idx_name = columns.index("name")
        schemas_lc = {s.lower() for s in self.schemas}

        kept: list[tuple] = []
        by_schema = by_exclude = by_include = 0
        for row in rows:
            schema = str(row[idx_schema] or "")
            name = str(row[idx_name] or "")
            if schemas_lc and schema.lower() not in schemas_lc:
                by_schema += 1
                continue
            if self.exclude and _matches(name, schema, self.exclude):
                by_exclude += 1
                continue
            if self.include and not _matches(name, schema, self.include):
                by_include += 1
                continue
            kept.append(row)

        truncated: list[str] = []
        if self.limit and len(kept) > self.limit:
            truncated = [
                f"{r[idx_schema]}.{r[idx_name]}" for r in kept[self.limit:]
            ]
            kept = kept[: self.limit]

        report = {
            "active": True,
            "kept": len(kept),
            "dropped": by_schema + by_exclude + by_include + len(truncated),
            "droppedBySchema": by_schema,
            "droppedByExclude": by_exclude,
            "droppedByInclude": by_include,
            "truncatedByLimit": len(truncated),
            # No silent caps: name what a --limit run did not look at.
            "truncatedObjects": truncated[:200],
            "criteria": {
                "schemas": self.schemas, "include": self.include,
                "exclude": self.exclude, "limit": self.limit,
            },
        }
        return kept, report

    def describe(self, report: dict[str, Any]) -> str:
        """One human line for the chat/log, per output-protocol."""
        if not report.get("active"):
            return ""
        bits = []
        if self.schemas:
            bits.append(f"schémas={','.join(self.schemas)}")
        if self.include:
            bits.append(f"inclus={','.join(self.include)}")
        if self.exclude:
            bits.append(f"exclus={','.join(self.exclude)}")
        if self.limit:
            bits.append(f"limite={self.limit}")
        msg = (f"périmètre borné ({' · '.join(bits)}) : {report['kept']} objet(s) "
               f"retenu(s), {report['dropped']} écarté(s)")
        if report.get("truncatedByLimit"):
            msg += (f" dont {report['truncatedByLimit']} par --limit "
                    f"(couverture INCOMPLÈTE)")
        return msg
