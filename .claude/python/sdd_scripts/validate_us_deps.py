#!/usr/bin/env python3
"""SDD_Pro: validate User Story dependency graph (v6.8+).

Parses the `## Dependencies` section of every US under workspace/output/us/
and reports:
  - cycles ([US_DEPS_CYCLE])      — blocking
  - missing references ([US_DEPS_MISSING]) — blocking
  - orphans ([US_DEPS_ORPHAN])    — informational

Also exposes a topological order for /dev-run STEP 6.2 (--topo flag).

Dependency syntax in US `## Dependencies` section:
  - {n}-{m}        # one US short id per bullet
  - NONE           # explicit "no deps" sentinel
  - <placeholder>  # bullets starting with `<` are ignored (template stub)

Usage:
    python validate_us_deps.py --feat 1                  # human report for FEAT 1
    python validate_us_deps.py --feat 1 --json           # machine output
    python validate_us_deps.py --feat 1 --topo           # print topo order (one per line)
    python validate_us_deps.py --us-id 1-2               # report on single US
    python validate_us_deps.py --all                     # all US in workspace/output/us/

Exit codes (granular — documented exception to sdd_lib/exit_codes.py convention) :
    0  Graph valid (no cycles, no missing refs); orphans only -> warn, exit 0
    1  No US found / cannot resolve [US_NOT_FOUND]
    2  Invalid args [INVALID_ARG]
    3  Cycle(s) detected [US_DEPS_CYCLE]
    4  Missing references detected [US_DEPS_MISSING]
    5  I/O error

Note (v7.0.0 P1 #10) : This script uses 6 distinct exit codes (vs the
canonical 0/1/2/3 of sdd_lib/exit_codes.py) because callers (`/dev-run`
STEP 2.bis) need to distinguish cycle (3) from missing-ref (4) for
different error messaging. For callers that don't need granularity :
treat any non-zero as FAIL_FAST. Documented exception, not drift.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.stderr import error_block, warn  # noqa: E402


US_ID_RE = re.compile(r"^\d+-\d+$")
US_FILE_RE = re.compile(r"^(\d+)-(\d+)-(.+)\.md$")
DEPS_SECTION_RE = re.compile(
    r"(?ms)^## Dependencies\s*$\r?\n(.*?)(?=^##\s|\Z)"
)
DEPS_BULLET_RE = re.compile(r"(?m)^- (.+)$")


def discover_us_files(feat: int | None) -> list[Path]:
    us_dir = repo_root() / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    if feat is None:
        return sorted(p for p in us_dir.glob("*-*-*.md") if p.is_file())
    return sorted(p for p in us_dir.glob(f"{feat}-*-*.md") if p.is_file())


def short_id_from_filename(path: Path) -> str | None:
    m = US_FILE_RE.match(path.name)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def parse_us_deps(content: str) -> set[str]:
    """Return the set of short-id deps declared in ## Dependencies.

    Returns empty set if `NONE` is declared, section absent, or only
    placeholders / invalid bullets.
    """
    section = DEPS_SECTION_RE.search(content)
    if not section:
        return set()
    deps: set[str] = set()
    for raw in DEPS_BULLET_RE.findall(section.group(1)):
        bullet = raw.strip()
        if not bullet or bullet.startswith("<"):
            continue
        if bullet.upper() == "NONE":
            continue
        if US_ID_RE.match(bullet):
            deps.add(bullet)
    return deps


def build_graph(us_files: list[Path]) -> tuple[dict[str, set[str]], dict[str, Path]]:
    """Return (graph, id_to_path).

    graph: node short-id -> set of dependency short-ids
    id_to_path: short-id -> Path of the US file
    """
    graph: dict[str, set[str]] = {}
    id_to_path: dict[str, Path] = {}
    for path in us_files:
        sid = short_id_from_filename(path)
        if sid is None:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            graph[sid] = set()
            id_to_path[sid] = path
            continue
        graph[sid] = parse_us_deps(content)
        id_to_path[sid] = path
    return graph, id_to_path


def detect_missing(graph: dict[str, set[str]]) -> dict[str, list[str]]:
    """For each node, list deps that point to a non-existent node."""
    known = set(graph)
    missing: dict[str, list[str]] = {}
    for node, deps in graph.items():
        bad = sorted(d for d in deps if d not in known)
        if bad:
            missing[node] = bad
    return missing


def detect_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return a list of cycles (each cycle = ordered list of nodes).

    Uses Tarjan's strongly-connected-components algorithm. Only SCCs of
    size >= 2 are returned (or self-loops, SCC size 1 with self-edge).
    """
    # Tarjan's SCC
    index_counter = [0]
    stack: list[str] = []
    lowlinks: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlinks[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        for successor in graph.get(node, set()):
            if successor not in index:
                if successor in graph:  # skip missing refs (handled separately)
                    strongconnect(successor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[successor])
            elif on_stack.get(successor, False):
                lowlinks[node] = min(lowlinks[node], index[successor])

        if lowlinks[node] == index[node]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == node:
                    break
            if len(scc) > 1 or (len(scc) == 1 and scc[0] in graph.get(scc[0], set())):
                sccs.append(sorted(scc))

    for node in graph:
        if node not in index:
            strongconnect(node)

    return sccs


def detect_orphans(graph: dict[str, set[str]]) -> list[str]:
    """Nodes referenced by nobody (no incoming edges). Informational."""
    referenced: set[str] = set()
    for deps in graph.values():
        referenced.update(deps)
    return sorted(node for node in graph if node not in referenced)


def layered_kahn_batches(graph: dict[str, set[str]]) -> list[list[str]] | None:
    """Layered Kahn's algorithm — v7.0.0 audit P0 R3.

    Returns batches such that NO node in batch K depends on ANY node in
    batch K (strict). All deps of nodes in batch K are in batches 0..K-1.
    This is the STRICT version of topological_sort that prevents
    intra-batch races on shared files (e.g. {LibName}/, schema.json).

    Returns None if a cycle exists.

    Ties within a layer broken alphabetically for determinism.
    Missing refs ignored (treated as no-op deps), same as topological_sort.

    Caller chunks each layer further by `MaxParallel` ; the chunk-level
    parallelism is safe because all nodes in a layer are pairwise independent.
    """
    known = set(graph)
    adj: dict[str, set[str]] = {n: {d for d in deps if d in known}
                                for n, deps in graph.items()}
    dependents: dict[str, set[str]] = {n: set() for n in adj}
    for node, deps in adj.items():
        for d in deps:
            dependents.setdefault(d, set()).add(node)
    indegree: dict[str, int] = {n: len(adj[n]) for n in adj}

    batches: list[list[str]] = []
    remaining = set(adj)
    while remaining:
        # Layer = all nodes with indegree 0 RIGHT NOW (sorted for determinism)
        layer = sorted(n for n in remaining if indegree[n] == 0)
        if not layer:
            return None  # cycle — nodes remain but none is ready
        batches.append(layer)
        # Consume the layer atomically (decrement indegree of dependents)
        for node in layer:
            remaining.discard(node)
            for dep_of_node in dependents.get(node, set()):
                if dep_of_node in remaining:
                    indegree[dep_of_node] -= 1
    return batches


def topological_sort(graph: dict[str, set[str]]) -> list[str] | None:
    """Kahn's algorithm. Returns None if a cycle exists.

    Order: deps come BEFORE their dependents. Ties broken alphabetically
    for determinism. Missing refs are ignored (treated as no-op deps).
    """
    known = set(graph)
    # Adjusted graph: drop missing refs.
    adj: dict[str, set[str]] = {n: {d for d in deps if d in known}
                                for n, deps in graph.items()}
    indegree: dict[str, int] = {n: 0 for n in adj}
    for deps in adj.values():
        for d in deps:
            indegree[d] = indegree.get(d, 0)
    # Build reverse: who depends on me?
    dependents: dict[str, set[str]] = {n: set() for n in adj}
    for node, deps in adj.items():
        for d in deps:
            dependents.setdefault(d, set()).add(node)
            indegree[node] = indegree.get(node, 0)
    # Recompute indegree properly: indegree[node] = number of unresolved deps.
    indegree = {n: len(adj[n]) for n in adj}

    ready = sorted(n for n, deg in indegree.items() if deg == 0)
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for dep_of_node in sorted(dependents.get(node, set())):
            indegree[dep_of_node] -= 1
            if indegree[dep_of_node] == 0:
                # Insert in sorted position
                ready.append(dep_of_node)
                ready.sort()
    if len(order) != len(adj):
        return None  # cycle
    return order


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate US dependency graph + topological sort.",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--feat", type=int, help="FEAT number to scope analysis")
    g.add_argument("--us-id", help="Single US short id (e.g. 1-2)")
    g.add_argument("--all", action="store_true", help="All US in workspace/output/us/")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--topo", action="store_true",
                   help="Print topological order (one short id per line)")
    p.add_argument("--layered-batches", action="store_true",
                   help="v7.0.0 R3 — print layered Kahn batches : one batch per line, "
                        "space-separated US ids. Within a batch, US are pairwise "
                        "independent (no dep). Use this output for strict-safe "
                        "parallel scheduling in /dev-run STEP 6.a/6.c.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # Resolve scope.
    if args.us_id:
        if not US_ID_RE.match(args.us_id):
            error_block(
                "validate_us_deps — invalid --us-id",
                f"[INVALID_ARG] expected format `n-m`, got {args.us_id!r}",
                "validate_us_deps.py --us-id 1-2",
            )
            return 2
        us_dir = repo_root() / "workspace" / "output" / "us"
        matches = sorted(us_dir.glob(f"{args.us_id}-*.md"))
        if len(matches) != 1:
            error_block(
                f"validate_us_deps — US {args.us_id} not found",
                f"[US_NOT_FOUND] no unique match for {args.us_id}-*.md",
                "verify --us-id format and that /us-generate has run",
            )
            return 1
        us_files = matches
    elif args.all:
        us_files = discover_us_files(None)
    else:
        us_files = discover_us_files(args.feat)

    if not us_files:
        error_block(
            "validate_us_deps — no US found",
            "[US_NOT_FOUND] workspace/output/us/ empty for requested scope",
            "run /us-generate {n} first",
        )
        return 1

    graph, id_to_path = build_graph(us_files)
    missing = detect_missing(graph)
    cycles = detect_cycles(graph)
    orphans = detect_orphans(graph)
    topo = topological_sort(graph)

    summary = {
        "node_count": len(graph),
        "edge_count": sum(len(d) for d in graph.values()),
        "cycles": cycles,
        "missing": missing,
        "orphans": orphans,
        "topo": topo,
    }

    # --topo: just print the order, terse.
    if args.topo:
        if topo is None:
            error_block(
                "validate_us_deps — topo failed (cycle)",
                f"[US_DEPS_CYCLE] {len(cycles)} cycle(s) detected: {cycles}",
                "break the cycle by adjusting `## Dependencies` in offending US",
            )
            return 3
        for node in topo:
            print(node)
        return 0

    # --layered-batches: emit strict-safe parallel batches (v7.0.0 R3)
    if args.layered_batches:
        batches = layered_kahn_batches(graph)
        if batches is None:
            error_block(
                "validate_us_deps — layered batches failed (cycle)",
                f"[US_DEPS_CYCLE] {len(cycles)} cycle(s) detected: {cycles}",
                "break the cycle by adjusting `## Dependencies` in offending US",
            )
            return 3
        for batch in batches:
            print(" ".join(batch))
        return 0

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"Scope: {len(graph)} US, {summary['edge_count']} deps")
        if cycles:
            print(f"\n[US_DEPS_CYCLE] {len(cycles)} cycle(s):")
            for c in cycles:
                print(f"  - {' -> '.join(c)} -> {c[0]}")
        if missing:
            print(f"\n[US_DEPS_MISSING] {len(missing)} US with missing refs:")
            for node, bad in missing.items():
                print(f"  - {node} -> {bad}")
        if orphans and len(orphans) < len(graph):
            print(f"\n[US_DEPS_ORPHAN] {len(orphans)} US not referenced by anyone (INFO):")
            for o in orphans:
                print(f"  - {o}")
        if topo and not cycles:
            print(f"\nTopo order: {' -> '.join(topo)}")
        if not cycles and not missing:
            print("\n[OK] graph valid")

    # Exit code priority: cycles > missing > clean.
    if cycles:
        return 3
    if missing:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
