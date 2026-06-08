"""Anthropic prompt-caching helper — v7.0.1 (P0 performance).

Parses `cache_layer: stable|semi|volatile` annotations from `loader.yml`
and emits per-agent cache_control hints for the harness to apply when
spawning sub-agents.

Anthropic prompt-caching (since 2024) supports up to 4 cache breakpoints
per request via `"cache_control": {"type": "ephemeral"}` on a content
block. TTL ~5 min. Cached input tokens cost ~10% of standard input
($0.30/MTok vs $3.00/MTok Sonnet 4.6).

Strategy (4 breakpoints / agent invocation, ordered from most stable
to most volatile, cache-friendly):

    [1] Agent system prompt (.claude/agents/X.md)        → stable
    [2] Cross-agent rules + stacks + templates           → stable
    [3] Project-level context (CLAUDE.md, schema.json,
        constitution.md, ADRs)                           → semi
    [4] Per-US volatile reads (FEAT, US, HTML, plan)     → NO CACHE

This module exposes:
    - parse_loader_annotations(): read loader.yml and group reads by layer
    - cache_breakpoints_for(agent_name): return ordered list of
      (paths, cache_layer) tuples ready to feed into the harness

The actual Anthropic API call (Messages.create with cache_control on
the system or tool content) is done by the harness — this lib only
PREPARES the manifest.

Status v7.0.1 (audit CTO 2026-06-07):
    - Phase 1 : loader.yml annotations complete on 12 agents ✓
    - Phase 2 : THIS HELPER (parsing + manifest) — NEW
    - Phase 3 : harness wiring (apply cache_control in Agent spawn)
                — pending v7.1 refacto

Without harness wiring, this module is informational/audit only. With
wiring, baseline cache hit measured 40.8% (2026-05-20) should rise to
≥ 90% (Anthropic prompt-caching docs).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sdd_lib.paths import repo_root

CacheLayer = Literal["stable", "semi", "volatile"]
_VALID_LAYERS: tuple[CacheLayer, ...] = ("stable", "semi", "volatile")


@dataclass(frozen=True)
class CachedRead:
    """One read entry annotated with its cache layer."""
    path: str
    layer: CacheLayer
    comment: str = ""


@dataclass
class AgentCacheManifest:
    """All reads for one agent, grouped by cache layer (stable first)."""
    agent: str
    stable: list[CachedRead] = field(default_factory=list)
    semi: list[CachedRead] = field(default_factory=list)
    volatile: list[CachedRead] = field(default_factory=list)

    def all_reads(self) -> list[CachedRead]:
        """Ordered stable → semi → volatile (cache-friendly)."""
        return [*self.stable, *self.semi, *self.volatile]

    def cache_breakpoints(self) -> list[tuple[CacheLayer, list[str]]]:
        """Return up to 4 breakpoints (paths grouped by layer).

        Anthropic supports max 4 cache_control markers per request.
        We use 3 layers (stable, semi, volatile) — leaves 1 spare for
        system prompt or future expansion.
        """
        out: list[tuple[CacheLayer, list[str]]] = []
        if self.stable:
            out.append(("stable", [r.path for r in self.stable]))
        if self.semi:
            out.append(("semi", [r.path for r in self.semi]))
        if self.volatile:
            out.append(("volatile", [r.path for r in self.volatile]))
        return out

    def stats(self) -> dict[str, int]:
        return {
            "stable": len(self.stable),
            "semi": len(self.semi),
            "volatile": len(self.volatile),
            "total": len(self.stable) + len(self.semi) + len(self.volatile),
        }


# Matches lines like:
#   - workspace/input/feats/{n}-*.md   # FEAT parente · cache_layer: volatile
#   - .claude/rules/build-and-loop.md  # cache_layer: stable
_READ_LINE_RE = re.compile(
    r"^\s*-\s*"                            # YAML list dash
    r"(?P<path>[^\s#]+)"                   # the path (no spaces, no comment)
    r"(?:\s*#\s*(?P<comment>.*?))?"        # optional trailing comment
    r"\s*$",
    re.MULTILINE,
)

# Matches inline-mapping lines (dev-backend format):
#   - { path: "X", cache_layer: stable }                # comment
#   - { path: X, cache_layer: semi, status: experimental }   # comment
#
# Two alternatives so that quoted paths can contain `{` and `}` (e.g.
# "workspace/output/us/{n}-{m}-*.md") — the previous regex stopped at
# the first `}` and silently dropped 3 volatile reads of dev-backend.
# Audit 2026-06-08: bug fix + regression test.
_INLINE_READ_RE = re.compile(
    r"^\s*-\s*\{\s*"
    r"path:\s*"
    r"(?:"
    r"\"(?P<qpath>[^\"]+)\""              # quoted path: anything except `"`
    r"|"
    r"(?P<upath>[^,\"}\s]+)"              # unquoted: no `,` `"` `}` ws
    r")"
    r"\s*,\s*"
    r"cache_layer:\s*(?P<layer>stable|semi|volatile)"
    r"[^}]*\}"                            # rest of mapping
    r"(?:\s*#\s*(?P<comment>.*?))?"       # optional trailing comment
    r"\s*$",
    re.MULTILINE,
)

# Matches agent section headers (top-level YAML key with `reads:` inside):
_AGENT_HEADER_RE = re.compile(
    r"^(?P<name>[a-z][a-z0-9_-]*):\s*$",
    re.MULTILINE,
)

# Matches `cache_layer: X` in a comment:
_LAYER_RE = re.compile(r"cache_layer:\s*(?P<layer>stable|semi|volatile)")


def _extract_layer(comment: str) -> CacheLayer | None:
    """Extract cache_layer value from a trailing comment, if any."""
    m = _LAYER_RE.search(comment)
    if m is None:
        return None
    layer = m.group("layer")
    if layer not in _VALID_LAYERS:
        return None
    return layer  # type: ignore[return-value]


def parse_loader_annotations(loader_path: Path | None = None) -> dict[str, AgentCacheManifest]:
    """Parse loader.yml and return manifest per agent.

    Args:
        loader_path: optional path override (default: <repo>/.claude/loader.yml)

    Returns:
        dict mapping agent name → AgentCacheManifest

    Raises:
        FileNotFoundError: if loader.yml is missing
        ValueError: if structure is unparseable

    Hand-rolled YAML parser (consistent with sdd_lib.loader_yml — we
    intentionally avoid external deps).
    """
    if loader_path is None:
        loader_path = repo_root() / ".claude" / "loader.yml"

    if not loader_path.exists():
        raise FileNotFoundError(f"loader.yml not found: {loader_path}")

    text = loader_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    manifests: dict[str, AgentCacheManifest] = {}
    current_agent: str | None = None
    in_reads_section = False

    for line_num, raw_line in enumerate(lines, start=1):
        # Skip comment-only lines for header detection
        stripped = raw_line.lstrip()
        if stripped.startswith("#"):
            continue

        # Agent header (top-level key, no leading whitespace)
        if not raw_line.startswith(" ") and raw_line.rstrip().endswith(":"):
            header_match = _AGENT_HEADER_RE.match(raw_line)
            if header_match:
                name = header_match.group("name")
                # Skip non-agent top-level keys (version, updated)
                if name in {"version", "updated"}:
                    current_agent = None
                    in_reads_section = False
                    continue
                current_agent = name
                in_reads_section = False
                if current_agent not in manifests:
                    manifests[current_agent] = AgentCacheManifest(agent=current_agent)
                continue

        # `reads:` section start
        if current_agent and raw_line.strip() == "reads:":
            in_reads_section = True
            continue

        # End of reads (any other top-level field at same indent)
        if in_reads_section and raw_line.strip() and not raw_line.startswith("    "):
            in_reads_section = False
            continue

        # Parse read entries — try inline-mapping format first, then comment format
        if in_reads_section and current_agent:
            inline_match = _INLINE_READ_RE.match(raw_line)
            if inline_match is not None:
                path = inline_match.group("qpath") or inline_match.group("upath")
                layer = inline_match.group("layer")  # type: ignore[assignment]
                comment = inline_match.group("comment") or ""
            else:
                line_match = _READ_LINE_RE.match(raw_line)
                if line_match is None:
                    continue
                path = line_match.group("path")
                comment = line_match.group("comment") or ""
                detected = _extract_layer(comment)
                if detected is None:
                    # Unclassified read — skip (will not be cached)
                    continue
                layer = detected  # type: ignore[assignment]

            manifest = manifests[current_agent]
            entry = CachedRead(path=path, layer=layer, comment=comment)  # type: ignore[arg-type]
            if layer == "stable":
                manifest.stable.append(entry)
            elif layer == "semi":
                manifest.semi.append(entry)
            else:
                manifest.volatile.append(entry)

    return manifests


@dataclass(frozen=True)
class OrderingViolation:
    """A single out-of-order cache_layer annotation in loader.yml."""
    agent: str
    line_num: int
    path: str
    layer: CacheLayer
    previous_path: str
    previous_layer: CacheLayer

    def __str__(self) -> str:
        return (
            f"{self.agent} line {self.line_num}: "
            f"{self.layer} '{self.path}' after "
            f"{self.previous_layer} '{self.previous_path}' "
            f"(expected stable → semi → volatile)"
        )


def validate_ordering(loader_path: Path | None = None
                      ) -> dict[str, list[OrderingViolation]]:
    """Verify that each agent's `reads:` declares cache_layer in source order
    `stable → semi → volatile`.

    The reconstructed `AgentCacheManifest` always exposes reads in the
    cache-friendly order via `all_reads()`, so a tautological check on the
    manifest cannot detect drift. This function inspects loader.yml directly,
    line by line, to enforce coherent annotations at the source.

    Args:
        loader_path: optional override (default: <repo>/.claude/loader.yml)

    Returns:
        dict mapping agent name → list of OrderingViolation (empty list if OK)

    Why this matters:
        - Coherent ordering documents intent (cacheable first, volatile last)
        - Detects drift when new reads are appended without respecting layers
        - Prepares wiring for any future cache_control harness hook
    """
    if loader_path is None:
        loader_path = repo_root() / ".claude" / "loader.yml"

    if not loader_path.exists():
        raise FileNotFoundError(f"loader.yml not found: {loader_path}")

    text = loader_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    layer_rank = {"stable": 0, "semi": 1, "volatile": 2}
    violations: dict[str, list[OrderingViolation]] = {}
    current_agent: str | None = None
    in_reads_section = False
    last_layer: CacheLayer | None = None
    last_path: str = ""

    for line_num, raw_line in enumerate(lines, start=1):
        stripped = raw_line.lstrip()
        if stripped.startswith("#"):
            continue

        if not raw_line.startswith(" ") and raw_line.rstrip().endswith(":"):
            header_match = _AGENT_HEADER_RE.match(raw_line)
            if header_match:
                name = header_match.group("name")
                if name in {"version", "updated"}:
                    current_agent = None
                    in_reads_section = False
                    continue
                current_agent = name
                in_reads_section = False
                last_layer = None
                last_path = ""
                continue

        if current_agent and raw_line.strip() == "reads:":
            in_reads_section = True
            last_layer = None
            last_path = ""
            continue

        if in_reads_section and raw_line.strip() and not raw_line.startswith("    "):
            in_reads_section = False
            continue

        if in_reads_section and current_agent:
            inline_match = _INLINE_READ_RE.match(raw_line)
            if inline_match is not None:
                path = inline_match.group("qpath") or inline_match.group("upath")
                layer = inline_match.group("layer")
            else:
                line_match = _READ_LINE_RE.match(raw_line)
                if line_match is None:
                    continue
                path = line_match.group("path")
                comment = line_match.group("comment") or ""
                detected = _extract_layer(comment)
                if detected is None:
                    continue
                layer = detected

            if last_layer is not None and layer_rank[layer] < layer_rank[last_layer]:
                violations.setdefault(current_agent, []).append(
                    OrderingViolation(
                        agent=current_agent,
                        line_num=line_num,
                        path=path,
                        layer=layer,  # type: ignore[arg-type]
                        previous_path=last_path,
                        previous_layer=last_layer,
                    )
                )
            last_layer = layer  # type: ignore[assignment]
            last_path = path

    return violations


def cache_breakpoints_for(agent_name: str, loader_path: Path | None = None
                          ) -> list[tuple[CacheLayer, list[str]]]:
    """Convenience: return cache breakpoints for one agent.

    Returns:
        Up to 3 (layer, paths) tuples in cache-friendly order.

    Example:
        >>> cache_breakpoints_for("dev-backend")
        [
            ("stable", [".claude/rules/build-and-loop.md", ...]),
            ("semi",   ["workspace/output/db/schema.json", ...]),
            ("volatile", ["workspace/output/us/{n}-{m}-*.md"]),
        ]
    """
    manifests = parse_loader_annotations(loader_path)
    if agent_name not in manifests:
        return []
    return manifests[agent_name].cache_breakpoints()


def report(loader_path: Path | None = None) -> str:
    """Human-readable report of all manifests (for CLI/debug)."""
    manifests = parse_loader_annotations(loader_path)
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("SDD_Pro cache_layer manifest (from loader.yml)")
    lines.append("=" * 70)
    total = {"stable": 0, "semi": 0, "volatile": 0}
    for name, m in sorted(manifests.items()):
        stats = m.stats()
        if stats["total"] == 0:
            continue
        lines.append(
            f"  {name:30s}  stable={stats['stable']:3d}  "
            f"semi={stats['semi']:3d}  volatile={stats['volatile']:3d}  "
            f"total={stats['total']:3d}"
        )
        for k in ("stable", "semi", "volatile"):
            total[k] += stats[k]
    lines.append("-" * 70)
    grand = total["stable"] + total["semi"] + total["volatile"]
    lines.append(
        f"  {'TOTAL':30s}  stable={total['stable']:3d}  "
        f"semi={total['semi']:3d}  volatile={total['volatile']:3d}  "
        f"total={grand:3d}"
    )
    if grand > 0:
        pct_stable = 100 * total["stable"] / grand
        pct_semi = 100 * total["semi"] / grand
        pct_volatile = 100 * total["volatile"] / grand
        lines.append(
            f"  {'%':30s}  stable={pct_stable:5.1f}%  "
            f"semi={pct_semi:5.1f}%  volatile={pct_volatile:5.1f}%"
        )
    lines.append("=" * 70)
    return "\n".join(lines)


if __name__ == "__main__":
    # CLI: dump report
    print(report())
