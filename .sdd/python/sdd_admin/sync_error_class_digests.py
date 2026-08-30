#!/usr/bin/env python3
"""Generate per-agent slices of error-classification.md (audit 2026-06-12, block 5).

`error-classification.md` is ~38 KB and was loaded IN FULL by ~12 agents, each
of which only uses 1-3 error families. This script emits a small digest per
agent — the §0 quick-ref (full 16-family navigation map, so NO class is ever
invisible) + that agent's relevant §1.X families + the universal format/loop
sections (§2/§3/§5) + a pointer to the full file for on-demand reads.

TOK-C2 (audit tokens 2026-08-30): error-classification.md is now path-scoped
(no longer auto-injected); the universal core (3-line ERROR format + mental
rule) moved to output-protocol.md §7.3/§7.5 (the one rule still unconditional),
so §2/§5 in the source — and thus in these digests — are now a skeleton +
pointer rather than the full prose. Digests remain the nominal agent channel.

Deterministic, 0-token. Idempotent. Mirrors `sync_stack_md.py` ergonomics:
    sync_error_class_digests.py            # (re)write all digests
    sync_error_class_digests.py --check    # exit 1 if any digest is stale (CI)
    sync_error_class_digests.py --dry-run  # print what would change

Outputs: .sdd/digests/error-classification.{agent}.md

NOTE (TOK-C1/C2 fix, audit 2026-06-12): digests live OUTSIDE `.claude/rules/`
on purpose. Claude Code natively auto-injects every `.md` under `.claude/rules/`
(recursively) into every main-loop AND sub-agent context. When the digests
lived under `.claude/rules/digests/`, ALL 12 were force-loaded into EVERY
context (~139 KB) on top of the full `error-classification.md` — the exact
opposite of the per-agent slimming they were built for. Keeping them under
`.sdd/digests/` makes them Read-on-demand only (their intended access).

Agents keep §0 + their families; anything outside their slice is still listed
(by family) in §0 and resolvable by reading the full file — consistent with
the "Read on-demand for edge cases" rule. Rewiring an agent to its digest is a
pure token optimization, never a correctness change.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]
if str(_REPO_ROOT / ".sdd" / "python") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / ".sdd" / "python"))
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.paths import rules_dir  # noqa: E402
_SRC = rules_dir(_REPO_ROOT) / "error-classification.md"
_OUT_DIR = _REPO_ROOT / ".sdd" / "digests"

# agent_id -> list of §1.X family keys to inline (besides the always-included
# §0 quick-ref + §1.1 runtime + §2/§3/§5 universal sections). Source of the
# mapping = auditor-coordination.md + build-and-loop.md family usage.
AGENT_FAMILIES: dict[str, list[str]] = {
    "dev-backend":               ["1.2", "1.3", "1.4", "1.5", "1.8"],
    "dev-frontend":              ["1.3", "1.4", "1.5", "1.6", "1.8"],
    "qa":                        ["1.4", "1.7"],
    "arch":                      ["1.2", "1.3", "1.5"],
    "po":                        ["1.2", "1.3"],
    "constitutioner":            ["1.2", "1.3"],
    "elicitor":                  ["1.2"],
    "code-reviewer":             ["1.3", "1.6", "1.10"],
    "security-reviewer":         ["1.11"],
    "spec-compliance-reviewer":  ["1.13"],
    "arch-reviewer":             ["1.14"],
    "adversarial-reviewer":      ["1.15"],
}

# Universal sections every digest carries (always relevant: the ERROR format,
# the build_loop decision table, the mental rule, runtime, unknown).
_ALWAYS_FAMILIES = ["1.1", "1.16"]
_ALWAYS_TOP_SECTIONS = ["2", "3", "5"]  # ## 2 Format, ## 3 build_loop, ## 5 mental rule


def _split_sections(text: str) -> dict[str, str]:
    """Return {key: block} where key ∈ {'header','quickref','1.1'..'1.16','2'..'5'}.

    'header' = everything before '## 0'. 'quickref' = the '## 0' block. Each
    '### 1.X ...' is its own block. Each top-level '## N ...' (N>=2) is a block.
    Blocks include their own heading line and run until the next peer heading.
    """
    lines = text.splitlines(keepends=True)
    sections: dict[str, str] = {}
    buf: list[str] = []
    cur = "header"

    def flush(key: str, content: list[str]) -> None:
        if content:
            sections[key] = "".join(content).rstrip() + "\n"

    h2 = re.compile(r"^##\s+(\d+)\.")
    h3 = re.compile(r"^###\s+(\d+\.\d+)\b")
    for ln in lines:
        m3 = h3.match(ln)
        m2 = h2.match(ln)
        if m3:
            flush(cur, buf); buf = [ln]; cur = m3.group(1)
        elif m2:
            n = m2.group(1)
            flush(cur, buf); buf = [ln]
            cur = "quickref" if n == "0" else n
        else:
            buf.append(ln)
    flush(cur, buf)
    return sections


def _render(agent: str, sections: dict[str, str]) -> str:
    fams = AGENT_FAMILIES[agent]
    out: list[str] = []
    out.append(f"# Error Classification — digest for `{agent}`\n")
    out.append(
        "> **GENERATED — do not edit.** Slice of `@.claude/rules/error-classification.md` "
        f"for the `{agent}` agent (audit 2026-06-12, block 5). Regenerate via "
        "`python .sdd/python/sdd_admin/sync_error_class_digests.py`.\n>\n"
        "> Contains the §0 quick-ref (full 16-family map) + this agent's families + "
        "the universal format/loop sections. For a class OUTSIDE this slice, §0 names "
        "its family — Read the full file on-demand (rule `build-and-loop.md §8`).\n"
    )
    # §0 quick-ref always
    if "quickref" in sections:
        out.append(sections["quickref"])
    # Always-on families + agent families, in numeric order, de-duplicated.
    selected = sorted(
        set(_ALWAYS_FAMILIES) | set(fams),
        key=lambda k: tuple(int(p) for p in k.split(".")),
    )
    out.append("\n## 1. Familles pertinentes\n")
    for key in selected:
        if key in sections:
            out.append(sections[key])
    # Universal top-level sections (format, build_loop, mental rule).
    for key in _ALWAYS_TOP_SECTIONS:
        if key in sections:
            out.append(sections[key])
    body = "\n".join(s.rstrip() for s in out) + "\n"
    return body


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sync_error_class_digests")
    p.add_argument("--check", action="store_true", help="exit 1 if any digest is stale")
    p.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
    args = p.parse_args(argv)

    if not _SRC.is_file():
        sys.stderr.write(f"ERROR: source not found: {_SRC}\n")
        return FAIL_FAST
    sections = _split_sections(_SRC.read_text(encoding="utf-8"))
    if "quickref" not in sections:
        sys.stderr.write("ERROR: could not locate '## 0' quick-ref section\n")
        return FAIL_FAST

    stale: list[str] = []
    wrote: list[str] = []
    for agent in sorted(AGENT_FAMILIES):
        target = _OUT_DIR / f"error-classification.{agent}.md"
        rendered = _render(agent, sections)
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current == rendered:
            continue
        if args.check:
            stale.append(agent)
        elif args.dry_run:
            sys.stdout.write(f"[DRY-RUN] would update {target.relative_to(_REPO_ROOT)}\n")
        else:
            _OUT_DIR.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
            wrote.append(agent)

    if args.check:
        if stale:
            sys.stderr.write(
                "ERROR: [DIGEST_STALE] error-class digests out of sync with "
                f"error-classification.md: {sorted(stale)}\n"
                "FIX: python .sdd/python/sdd_admin/sync_error_class_digests.py\n"
            )
            return FAIL_FAST
        sys.stdout.write(f"[OK] {len(AGENT_FAMILIES)} digests in sync\n")
        return SUCCESS
    if not args.dry_run:
        sys.stdout.write(f"[OK] wrote {len(wrote)} / {len(AGENT_FAMILIES)} digests "
                         f"(unchanged: {len(AGENT_FAMILIES) - len(wrote)})\n")
    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
