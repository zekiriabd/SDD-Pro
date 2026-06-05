#!/usr/bin/env python3
"""SDD_Pro: deterministic complexity scoring for User Stories (v6.8+).

Computes a 1-10 complexity score and S/M/L/XL effort estimate for a US
from 6 measurable signals extracted from the US markdown:

    Signal                          Weight      Cap
    ──────────────────────────────────────────────
    ACs count                       1.0/AC      4.0
    Covers items                    0.5/item    3.0
    AC text length (log-scaled)     variable    2.0
    Complexity keywords             0.5/match   3.0
    Dependencies                    0.5/dep     2.0
    User Story length (log-scaled)  variable    1.0
    ──────────────────────────────────────────────
                                                15.0 raw

Score = round(raw / 15 * 9 + 1) clamped to [1, 10].

Estimate mapping:
    1-2 → S      3-4 → M      5-6 → L      7-8 → XL      9-10 → XL+ (split suggested)

The script is purely deterministic (no LLM call). It optionally updates
the `## Metadata` JSON block (set by us.template.md v6.8+) with keys
`complexity` and `effort_estimate`, leaving other keys untouched.

Usage:
    python compute_us_complexity.py --us 1-2                # print score + signals
    python compute_us_complexity.py --us 1-2 --apply        # write to ## Metadata
    python compute_us_complexity.py --us 1-2 --json         # machine-readable output
    python compute_us_complexity.py --us 1-2 --apply --json

Exit codes:
    0  Success
    1  US file not found ([US_NOT_FOUND])
    4  US parse error (missing sections) ([US_PARSE_ERROR])
    5  I/O error
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.stderr import error_block  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402


COMPLEXITY_KEYWORDS: frozenset[str] = frozenset({
    # async / concurrency
    "asynchrone", "async", "concurrence", "concurrent", "parallel", "thread",
    "websocket", "stream", "streaming", "polling", "real-time", "realtime",
    # data integrity
    "transaction", "rollback", "atomic", "consistency", "isolation",
    "lock", "deadlock", "retry", "idempotent", "idempotence",
    # security
    "encryption", "encrypt", "hash", "signature", "jwt", "oauth", "sso",
    "permission", "authorization", "authz", "rbac", "abac",
    # heavy ops
    "batch", "queue", "schedule", "cron", "background-job", "worker",
    "upload", "download", "export", "import", "migration",
    # integrations
    "webhook", "api-externe", "external-api", "third-party",
    "saga", "compensating",
    # data
    "pagination", "cursor", "search", "filter-complex", "aggregation",
    "join", "n-plus-1",
})

US_ID_RE = re.compile(r"^\d+-\d+$")
AC_LINE_RE = re.compile(r"(?m)^- AC-\d+:\s*(.+)$")
COVERS_LINE_RE = re.compile(r"(?m)^- (SFD|BR|AC|FD)-\d+\b")
COVERS_SECTION_RE = re.compile(
    r"(?ms)^## Covers\s*$\r?\n(.*?)(?=^##\s|\Z)"
)
DEPS_SECTION_RE = re.compile(
    r"(?ms)^## Dependencies\s*$\r?\n(.*?)(?=^##\s|\Z)"
)
DEPS_LINE_RE = re.compile(r"(?m)^- (.+)$")
USER_STORY_SECTION_RE = re.compile(
    r"(?ms)^## User Story\s*$\r?\n(.*?)(?=^##\s|\Z)"
)
METADATA_BLOCK_RE = re.compile(
    r"(?ms)(^## Metadata\s*$.*?```json\s*\r?\n)(.*?)(\r?\n```)"
)


def resolve_us_path(us_id: str) -> Path | None:
    if not US_ID_RE.match(us_id):
        return None
    us_dir = repo_root() / "workspace" / "output" / "us"
    matches = sorted(us_dir.glob(f"{us_id}-*.md"))
    if len(matches) != 1:
        return None
    return matches[0]


def extract_signals(content: str) -> dict:
    """Extract the 6 raw signals from US content. Pure function."""
    # ACs
    acs = AC_LINE_RE.findall(content)
    ac_count = len(acs)
    ac_text_total = sum(len(a) for a in acs)

    # Covers (SFD/BR/AC/FD bullets in ## Covers section only — avoid double-count with ACs)
    covers_section = COVERS_SECTION_RE.search(content)
    covers_count = (
        len(COVERS_LINE_RE.findall(covers_section.group(1)))
        if covers_section else 0
    )

    # Dependencies (non-NONE lines)
    deps_section = DEPS_SECTION_RE.search(content)
    deps_count = 0
    if deps_section:
        for m in DEPS_LINE_RE.findall(deps_section.group(1)):
            stripped = m.strip()
            if stripped and stripped.upper() != "NONE" and not stripped.startswith("<"):
                deps_count += 1

    # User Story length
    us_section = USER_STORY_SECTION_RE.search(content)
    user_story_len = len(us_section.group(1).strip()) if us_section else 0

    # Complexity keywords (case-insensitive substring match)
    haystack = content.lower()
    kw_matches = sum(1 for kw in COMPLEXITY_KEYWORDS if kw in haystack)

    return {
        "ac_count": ac_count,
        "ac_text_total": ac_text_total,
        "covers_count": covers_count,
        "deps_count": deps_count,
        "user_story_len": user_story_len,
        "keyword_matches": kw_matches,
    }


def score_signals(signals: dict) -> dict:
    """Map signals to weighted contributions and compute score 1-10."""
    # Weights calibrated against anchor US (counter=M, batch-async-pdf=XL split).
    contrib = {
        "acs": min(signals["ac_count"] * 0.6, 4.0),
        "covers": min(signals["covers_count"] * 0.25, 3.0),
        # log-scaled : len 0 -> 0 ; len 1000 -> ~2.0 ; saturating
        "ac_text": min(math.log1p(signals["ac_text_total"]) / math.log(1000) * 2.0, 2.0)
            if signals["ac_text_total"] > 0
            else 0.0,
        "keywords": min(signals["keyword_matches"] * 0.5, 3.0),
        "deps": min(signals["deps_count"] * 0.5, 2.0),
        # log-scaled : len 0 -> 0 ; len 500 -> ~1.0 ; saturating
        "user_story": min(math.log1p(signals["user_story_len"]) / math.log(500), 1.0)
            if signals["user_story_len"] > 0
            else 0.0,
    }
    raw = sum(contrib.values())
    # Normalize raw in [0, 15] -> score in [1, 10]
    score = int(round(raw / 15.0 * 9 + 1))
    score = max(1, min(10, score))
    return {"contributions": contrib, "raw": round(raw, 3), "score": score}


def estimate_from_score(score: int) -> tuple[str, str]:
    """Return (estimate, advisory_note)."""
    if score <= 2:
        return "S", ""
    if score <= 4:
        return "M", ""
    if score <= 6:
        return "L", ""
    if score <= 8:
        return "XL", "consider splitting per us-granularity.md if AC count > 5"
    return "XL", "WARN: score >= 9 — strongly suggests split (cf. us-granularity.md hard cap)"


def update_metadata_block(content: str, complexity: int, estimate: str) -> tuple[str, bool]:
    """Inject complexity + effort_estimate into the ## Metadata JSON block.

    Returns (new_content, modified). If ## Metadata section absent or its
    JSON block is invalid, returns (content, False) without raising.
    """
    m = METADATA_BLOCK_RE.search(content)
    if not m:
        return content, False
    prefix, json_body, suffix = m.group(1), m.group(2), m.group(3)
    try:
        data = json.loads(json_body) if json_body.strip() else {}
        if not isinstance(data, dict):
            return content, False
    except json.JSONDecodeError:
        return content, False
    data["complexity"] = complexity
    data["effort_estimate"] = estimate
    new_json = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    new_block = prefix + new_json + suffix
    new_content = content[: m.start()] + new_block + content[m.end():]
    return new_content, True


def write_atomic(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Deterministic complexity scoring for User Stories (v6.8+).",
    )
    p.add_argument("--us", required=True, help="US short id, e.g. 1-2")
    p.add_argument("--apply", action="store_true",
                   help="Write computed score into ## Metadata JSON block")
    p.add_argument("--json", action="store_true",
                   help="Print machine-readable JSON instead of human format")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    us_path = resolve_us_path(args.us)
    if us_path is None:
        error_block(
            f"compute_us_complexity — US {args.us} not found",
            f"[US_NOT_FOUND] no unique match for workspace/output/us/{args.us}-*.md",
            "verify --us format ({n}-{m}) and that /us-generate has run",
        )
        return FAIL_FAST
    try:
        content = us_path.read_text(encoding="utf-8")
    except OSError as e:
        error_block(
            f"compute_us_complexity — read failed: {us_path}",
            f"[IO] {e}",
            "check file permissions",
        )
        return 5

    signals = extract_signals(content)
    scored = score_signals(signals)
    estimate, advisory = estimate_from_score(scored["score"])

    result = {
        "us": us_path.name,
        "signals": signals,
        "contributions": scored["contributions"],
        "raw_score": scored["raw"],
        "complexity": scored["score"],
        "effort_estimate": estimate,
        "advisory": advisory,
        "applied": False,
    }

    if args.apply:
        new_content, modified = update_metadata_block(
            content, scored["score"], estimate
        )
        if modified:
            try:
                write_atomic(us_path, new_content)
                result["applied"] = True
            except OSError as e:
                error_block(
                    f"compute_us_complexity — write failed: {us_path}",
                    f"[IO] {e}",
                    "check file permissions / free disk space",
                )
                return 5
        else:
            result["advisory"] = (
                (result["advisory"] + " | " if result["advisory"] else "")
                + "## Metadata section missing or JSON invalid — add it (cf. us.template.md v6.8) to enable --apply"
            )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"US: {result['us']}")
        print(f"Signals: {signals}")
        print(f"Contributions: " + ", ".join(
            f"{k}={v:.2f}" for k, v in scored["contributions"].items()
        ))
        print(f"Raw score: {scored['raw']:.2f} / 15.0")
        print(f"Complexity: {scored['score']}/10  ->  Effort: {estimate}")
        if result["advisory"]:
            print(f"Advisory: {result['advisory']}")
        if result["applied"]:
            print(f"[OK] Metadata block updated in {us_path.name}")
        elif args.apply:
            print(f"[SKIP] Metadata block not updated (cf. advisory)")
    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
