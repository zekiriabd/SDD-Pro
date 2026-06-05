#!/usr/bin/env python3
"""SDD_Pro: HTML mockup fidelity check (dev-frontend STEP 10 + 11).

Externalises:
- STEP 10: hex tokens verification (3 modes: exact, ±X% RGB tolerance, override)
- STEP 11: text-based fidelity (labels + DS component mapping)

Deterministic, 0 token LLM. Replaces ~80 lines of LLM prose.

Usage:
    python validate_fidelity.py \\
        --html-path workspace/input/ui/1-2-Bebes.html \\
        --generated-dir workspace/output/src/AppName \\
        [--theme-path workspace/output/src/AppName/wwwroot/css/theme.css] \\
        [--hex-tolerance-max-pct 5] \\
        [--us-id 1-2] \\
        [--json]

When `--us-id {n}-{m}` is provided together with `--json`, the JSON report
is persisted to `workspace/output/.sys/.validation/fidelity-{n}-{m}.json`
(canonical location, never the repo root). Stdout receives the human
verdict in that mode. Without `--us-id`, `--json` keeps legacy stdout
behaviour (backward-compat for tests / ad-hoc runs).

Exit codes:
    0 PASS  — exact matches or fully tolerated
    1 WARN  — partial tolerance / minor missing labels
    2 FAIL  — missing hex tokens / missing components / many missing labels

Migrated from .claude/scripts/validate-fidelity.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

_US_ID_RE = re.compile(r"^\d+-\d+$")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.console_db import connect, ensure_initialized, insert_validation_report  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402
from sdd_lib.exit_codes import CORRECTIBLE  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--html-path", required=True)
    p.add_argument("--generated-dir", required=True)
    p.add_argument("--theme-path", default="")
    p.add_argument("--hex-tolerance-max-pct", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--us-id",
        default="",
        help="US identifier `{n}-{m}` — when set with --json, persists report "
             "to workspace/output/.sys/.validation/fidelity-{n}-{m}.json",
    )
    return p.parse_args()


_HEX_RE = re.compile(r"#([0-9a-fA-F]{6})\b")
_SCRIPT_RE = re.compile(r"(?is)<script[^>]*>.*?</script>")
_STYLE_RE = re.compile(r"(?is)<style[^>]*>.*?</style>")
_LABEL_RE = re.compile(r">([^<>\r\n]{3,80})<")
_NUMERIC_ONLY_RE = re.compile(r"^[\s\d\.,;:|\-_]+$")

STRUCTURAL_TAGS: tuple[str, ...] = (
    "header", "aside", "main", "nav", "footer",
    "section", "table", "form", "dialog", "select",
)

DS_EXPECTATIONS: dict[str, list[str]] = {
    "table":  ["RadzenDataGrid", "<Table", "v-data-table", "MudTable"],
    "button": ["RadzenButton", "<Button", "v-btn", "MudButton"],
    "form":   ["RadzenTemplateForm", "<Form", "v-form", "EditForm"],
    "dialog": ["DialogService", "<Dialog", "v-dialog", "MudDialog"],
    "select": ["RadzenDropDown", "<Select", "v-select", "MudSelect"],
}

RENDER_EXTENSIONS: tuple[str, ...] = (
    "*.razor", "*.tsx", "*.jsx", "*.vue", "*.html", "*.cshtml"
)
CSS_EXTENSIONS: tuple[str, ...] = ("*.css", "*.razor.css")


def hex_to_rgb(hex6: str) -> tuple[int, int, int]:
    return (int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16))


def rgb_distance_pct(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """Euclidean distance in RGB space, normalized to 0-100%."""
    diff = sum((a[i] - b[i]) ** 2 for i in range(3))
    return math.sqrt(diff / (3 * 65025)) * 100


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def collect_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        out.extend(root.rglob(pat))
    return out


def main() -> int:
    args = parse_args()

    html_path = Path(args.html_path)
    if not html_path.is_file():
        warn(f"FAIL: HTML mockup not found: {args.html_path}")
        return CORRECTIBLE
    generated_dir = Path(args.generated_dir)
    if not generated_dir.is_dir():
        warn(f"FAIL: Generated dir not found: {args.generated_dir}")
        return CORRECTIBLE
    html = read_file(html_path)

    # ===== STEP 10: hex tokens =====
    hex_expected = sorted({m.group(1).lower() for m in _HEX_RE.finditer(html)})

    theme_content = ""
    if args.theme_path:
        tp = Path(args.theme_path)
        if tp.is_file():
            theme_content = read_file(tp)

    css_files = collect_files(generated_dir, CSS_EXTENSIONS)
    css_aggregated_parts = [theme_content] + [read_file(f) for f in css_files]
    css_aggregated = "\n".join(css_aggregated_parts)

    tokens_report: list[dict[str, object]] = []
    css_hex_list = [m.group(1).lower() for m in _HEX_RE.finditer(css_aggregated)]

    for hex6 in hex_expected:
        r_ex, g_ex, b_ex = hex_to_rgb(hex6)
        exact_match = re.search(rf"(?i)#{hex6}\b", css_aggregated) is not None
        tolerated_hex: str | None = None

        if not exact_match and args.hex_tolerance_max_pct > 0:
            for cand in css_hex_list:
                if cand == hex6:
                    continue
                dist = rgb_distance_pct((r_ex, g_ex, b_ex), hex_to_rgb(cand))
                if dist <= args.hex_tolerance_max_pct:
                    tolerated_hex = cand
                    break

        override_match = re.search(rf"ui-fidelity-override:\s*hex-{hex6}", html) is not None

        if exact_match:
            status = "MATCH-EXACT"
        elif tolerated_hex:
            status = "MATCH-TOLERATED"
        elif override_match:
            status = "MATCH-OVERRIDE"
        else:
            status = "MISSING"

        tokens_report.append({
            "hex": f"#{hex6}",
            "rgb": f"{r_ex},{g_ex},{b_ex}",
            "status": status,
            "matched_hex": f"#{tolerated_hex}" if tolerated_hex else None,
        })

    # ===== STEP 11: labels + components =====
    html_clean = _STYLE_RE.sub("", _SCRIPT_RE.sub("", html))
    labels_set: set[str] = set()
    for m in _LABEL_RE.finditer(html_clean):
        text = m.group(1).strip()
        if text and not _NUMERIC_ONLY_RE.match(text):
            labels_set.add(text)
    labels = sorted(labels_set)

    structural_present: list[str] = []
    for tag in STRUCTURAL_TAGS:
        if re.search(rf"<{tag}\b", html, re.IGNORECASE):
            structural_present.append(tag)

    render_files = collect_files(generated_dir, RENDER_EXTENSIONS)
    render_aggregated = "\n".join(read_file(f) for f in render_files)

    labels_report: list[dict[str, object]] = []
    for label in labels:
        if len(label) < 4:
            continue
        found = re.search(re.escape(label), render_aggregated) is not None
        labels_report.append({"label": label, "status": "FOUND" if found else "MISSING"})

    components_report: list[dict[str, object]] = []
    for tag in structural_present:
        if tag not in DS_EXPECTATIONS:
            continue
        expected = DS_EXPECTATIONS[tag]
        matched: str | None = None
        for comp in expected:
            if re.search(re.escape(comp), render_aggregated):
                matched = comp
                break
        components_report.append({
            "html_tag": tag,
            "expected_any_of": " | ".join(expected),
            "matched_component": matched,
            "status": "FOUND" if matched else "MISSING",
        })

    # ===== Summary + decision =====
    tokens_exact = sum(1 for t in tokens_report if t["status"] == "MATCH-EXACT")
    tokens_tol = sum(1 for t in tokens_report if t["status"] == "MATCH-TOLERATED")
    tokens_over = sum(1 for t in tokens_report if t["status"] == "MATCH-OVERRIDE")
    tokens_missing = sum(1 for t in tokens_report if t["status"] == "MISSING")
    labels_found = sum(1 for l in labels_report if l["status"] == "FOUND")
    labels_missing = sum(1 for l in labels_report if l["status"] == "MISSING")
    comps_found = sum(1 for c in components_report if c["status"] == "FOUND")
    comps_missing = sum(1 for c in components_report if c["status"] == "MISSING")

    if tokens_missing > 0 or labels_missing > 5 or comps_missing > 0:
        exit_code = 2
        decision = "FAIL"
    elif tokens_tol > 0 or labels_missing > 0:
        exit_code = 1
        decision = "WARN"
    else:
        exit_code = 0
        decision = "PASS"

    if args.json:
        result = {
            "summary": {
                "hex_total":          len(tokens_report),
                "hex_exact":          tokens_exact,
                "hex_tolerated":      tokens_tol,
                "hex_override":       tokens_over,
                "hex_missing":        tokens_missing,
                "labels_total":       len(labels_report),
                "labels_found":       labels_found,
                "labels_missing":     labels_missing,
                "components_total":   len(components_report),
                "components_found":   comps_found,
                "components_missing": comps_missing,
                "decision":           decision,
            },
            "tokens":     tokens_report,
            "labels":     labels_report,
            "components": components_report,
        }
        json_text = json.dumps(result, indent=2)

        if args.us_id:
            if not _US_ID_RE.match(args.us_id):
                warn(
                    f"FAIL: invalid --us-id '{args.us_id}' "
                    "(expected pattern {n}-{m} with digits)"
                )
                return CORRECTIBLE
            # Persist to console.db (table validation_reports) — replaces fidelity-{n}-{m}.json
            feat_n = int(args.us_id.split("-")[0])
            ensure_initialized()
            with connect() as conn:
                insert_validation_report(
                    conn, feat_n=feat_n, report_type="fidelity",
                    verdict=decision, summary=f"us={args.us_id}",
                    payload=result, file_path=None,
                )
            print(f"Fidelity report : console.db (validation_reports, type=fidelity, us={args.us_id})")
            print(f"Decision        : {decision} (exit {exit_code})")
        else:
            print(json_text)
    else:
        print()
        print("=== Fidelity Check ===")
        print(
            f"Tokens hex : {len(tokens_report)} total / {tokens_exact} exact / "
            f"{tokens_tol} toleres / {tokens_over} override / {tokens_missing} missing"
        )
        print(f"Labels     : {len(labels_report)} total / {labels_found} found / {labels_missing} missing")
        print(f"Components : {len(components_report)} total / {comps_found} found / {comps_missing} missing")

        if tokens_missing:
            warn("\n[FAIL] Tokens hex manquants :")
            for t in tokens_report:
                if t["status"] == "MISSING":
                    warn(f"  {t['hex']}  rgb={t['rgb']}")
        if labels_missing:
            warn("\n[WARN/FAIL] Libelles manquants :")
            for l in labels_report:
                if l["status"] == "MISSING":
                    warn(f"  {l['label']}")
        if comps_missing:
            warn("\n[FAIL] Composants DS manquants :")
            for c in components_report:
                if c["status"] == "MISSING":
                    warn(f"  <{c['html_tag']}> expected one of: {c['expected_any_of']}")
        print(f"\nDecision : {decision} (exit {exit_code})")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
