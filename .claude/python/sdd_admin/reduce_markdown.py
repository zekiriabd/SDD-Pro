#!/usr/bin/env python3
"""SDD_Pro — Reduce markdown size by stripping deterministic archeology.

Audit consolidé 2026-06-07 — outil créé sur demande "réduction tokens
des MD du framework". Méthode déterministe (pas LLM, pas de risque
de perte sémantique) qui cible 4 classes de bruit :

1. Annotations audit closures inline (`> **v7.0.0-alpha (audit MAJ-5, ...)**`)
   — souvent 5-10 lignes de "pourquoi ce fix a été appliqué", utile en
   archéologie git blame, pollution dans le prompt LLM.
2. Commentaires bash `# Audit MXX closure 2026-XX-XX — ...` à
   l'intérieur des blocs de code (idem).
3. Stubs déjà supprimés mais référencés en intro (`> Stubs originaux
   supprimés au sweep v7.0.0-alpha 2026-05-20`).
4. Blocs "Pourquoi historique" multi-lignes qui peuvent être condensés
   en pointeurs ADR / CHANGELOG.

Usage :
    python reduce_markdown.py [--dry-run] [--file PATH] [--top N]
                              [--threshold-lines N]

Options :
    --dry-run         : montre les modifications sans les appliquer
    --file PATH       : restreint à un fichier précis
    --top N           : restreint aux N plus gros .md sous .claude/
    --threshold-lines : ne compresser que les blocs >= N lignes (défaut 3)

Exit codes :
    0 SUCCESS    — opération complète (modifications appliquées ou dry-run propre)
    3 INFRA_BLOCKED — accès fichier / parsing impossible
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402

# Pattern 1 : annotations audit en blockquote
# Ex: > **v7.0.0-alpha (audit MAJ-5, 2026-06-04)** : l'ancien sous-STEP 5.5
#     > "Threat model pré-dev" est retiré (...)
#     > [continue sur plusieurs lignes]
_AUDIT_BLOCKQUOTE_RE = re.compile(
    r"(?:^|\n)(> \*\*v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc))?[^*\n]*\(audit [^)]+\)\*\*[^\n]*\n"
    r"(?:>[^\n]*\n)*)",
    re.MULTILINE,
)

# Pattern 2 : commentaires bash audit closure
# Ex: # Audit M10 closure 2026-06-07 — atomic write + fsync ...
_AUDIT_BASH_COMMENT_RE = re.compile(
    r"^\s*#\s*Audit\s+[A-Z]+\d+\s+closure\s+\d{4}-\d{2}-\d{2}[^\n]*\n",
    re.MULTILINE,
)

# Pattern 3 : stubs supprimés au sweep
# Ex: > **v7.0.0 merge** : fusionne ... + ... . Stubs originaux **supprimés au sweep v7.0.0-alpha 2026-05-20**
_SWEEP_REF_RE = re.compile(
    r"Stubs?\s+(?:originaux\s+)?\*\*supprimés?\s+au\s+sweep\s+v\d+\.\d+\.\d+[^*]*\*\*[^.\n]*\.",
)

# Pattern 4 : annotations footnote audit dans tableaux/listes
# Ex: " — audit C3, 2026-06-06" en fin de cellule de tableau
# RESTRICT : exiger au moins 1 chiffre après les capitales (`C3`, `MAJ-5`,
# `CRIT-11`) pour éviter le faux positif sur `audit CTO 2026-05-20`
# (où "CTO" sans chiffre ne doit pas matcher — sinon supprimer le `,`
# casse la grammaire de la phrase environnante, vu sur MIGRATION.md L7).
_AUDIT_INLINE_NOTE_RE = re.compile(
    r"\s*[—–-]\s*audit\s+[A-Z]+-?\d+,?\s+\d{4}-\d{2}-\d{2}",
)

# Pattern 5 : blocs vXXX-alpha annotations en début de section
_VERSION_ANNOT_BLOCK_RE = re.compile(
    r"(?:^|\n)(> \*\*v\d+\.\d+\.\d+[^*\n]*\([^)]*\d{4}-\d{2}-\d{2}\)\*\*[^\n]*\n"
    r"(?:>[^\n]*\n)*)",
    re.MULTILINE,
)


def reduce_text(text: str, threshold_lines: int = 3) -> tuple[str, dict[str, int]]:
    """Apply all reduction patterns. Returns (reduced_text, stats).

    stats keys :
      - pattern_1_audit_blocks : lignes retirées (audit blockquote)
      - pattern_2_audit_bash   : lignes retirées (commentaires bash)
      - pattern_3_sweep_refs   : occurrences retirées (sweep stubs)
      - pattern_4_inline_notes : occurrences retirées (footnote audit)
      - pattern_5_version_annot : lignes retirées (version annotations)
    """
    stats = {k: 0 for k in (
        "pattern_1_audit_blocks", "pattern_2_audit_bash",
        "pattern_3_sweep_refs", "pattern_4_inline_notes",
        "pattern_5_version_annot",
    )}

    def _remove_audit_block(m: re.Match) -> str:
        block = m.group(1)
        n_lines = block.count("\n")
        if n_lines >= threshold_lines:
            stats["pattern_1_audit_blocks"] += n_lines
            return "\n" if m.group(0).startswith("\n") else ""
        return m.group(0)

    text = _AUDIT_BLOCKQUOTE_RE.sub(_remove_audit_block, text)

    def _remove_bash_comment(m: re.Match) -> str:
        stats["pattern_2_audit_bash"] += 1
        return ""

    text = _AUDIT_BASH_COMMENT_RE.sub(_remove_bash_comment, text)

    def _remove_sweep(m: re.Match) -> str:
        stats["pattern_3_sweep_refs"] += 1
        return ""

    text = _SWEEP_REF_RE.sub(_remove_sweep, text)

    def _remove_inline_note(m: re.Match) -> str:
        stats["pattern_4_inline_notes"] += 1
        return ""

    text = _AUDIT_INLINE_NOTE_RE.sub(_remove_inline_note, text)

    def _remove_version_annot(m: re.Match) -> str:
        block = m.group(1)
        n_lines = block.count("\n")
        if n_lines >= threshold_lines:
            stats["pattern_5_version_annot"] += n_lines
            return "\n" if m.group(0).startswith("\n") else ""
        return m.group(0)

    text = _VERSION_ANNOT_BLOCK_RE.sub(_remove_version_annot, text)

    # Normalise multiple blank lines (>=3 consecutive) → 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text, stats


def process_file(path: Path, dry_run: bool, threshold: int) -> tuple[int, int, dict[str, int]]:
    """Returns (lines_before, lines_after, stats)."""
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc

    reduced, stats = reduce_text(original, threshold_lines=threshold)
    lines_before = original.count("\n") + 1
    lines_after = reduced.count("\n") + 1

    if not dry_run and reduced != original:
        path.write_text(reduced, encoding="utf-8")

    return lines_before, lines_after, stats


def find_top_md(root: Path, n: int) -> list[Path]:
    """Return top N largest .md files under .claude/ by line count."""
    claude_root = root / ".claude"
    if not claude_root.is_dir():
        return []
    candidates: list[tuple[int, Path]] = []
    for md in claude_root.rglob("*.md"):
        try:
            lines = sum(1 for _ in md.open(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        candidates.append((lines, md))
    candidates.sort(reverse=True, key=lambda x: x[0])
    return [p for _, p in candidates[:n]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reduce markdown size by stripping deterministic archeology"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="show modifications without applying")
    parser.add_argument("--file", default=None,
                        help="restrict to one file path (relative to repo root)")
    parser.add_argument("--top", type=int, default=None,
                        help="restrict to top N largest .md under .claude/")
    parser.add_argument("--threshold-lines", type=int, default=3,
                        help="only compress blocks >= N lines (default 3)")
    args = parser.parse_args(argv)

    try:
        root = repo_root()
    except Exception as exc:
        print(f"[FAIL] cannot resolve repo root: {exc}", file=sys.stderr)
        return INFRA_BLOCKED

    targets: list[Path] = []
    if args.file:
        target = root / args.file if not Path(args.file).is_absolute() else Path(args.file)
        if not target.is_file():
            print(f"[FAIL] file not found: {target}", file=sys.stderr)
            return INFRA_BLOCKED
        targets = [target]
    elif args.top:
        targets = find_top_md(root, args.top)
    else:
        targets = list((root / ".claude").rglob("*.md"))

    total_before = 0
    total_after = 0
    total_stats: dict[str, int] = {}
    files_modified = 0

    for path in targets:
        try:
            before, after, stats = process_file(path, args.dry_run, args.threshold_lines)
        except RuntimeError as exc:
            print(f"[WARN] {exc}", file=sys.stderr)
            continue
        delta = before - after
        if delta > 0:
            files_modified += 1
            rel = path.relative_to(root)
            print(f"{'[DRY]' if args.dry_run else '[OK] '} {rel}: {before} -> {after} lines (-{delta})")
            for k, v in stats.items():
                if v > 0:
                    total_stats[k] = total_stats.get(k, 0) + v
        total_before += before
        total_after += after

    print()
    print(f"=== Summary ({'DRY-RUN' if args.dry_run else 'APPLIED'}) ===")
    print(f"Files scanned   : {len(targets)}")
    print(f"Files modified  : {files_modified}")
    print(f"Lines total     : {total_before} -> {total_after} (-{total_before - total_after}, -{100*(total_before-total_after)/max(total_before,1):.1f}%)")
    if total_stats:
        print("Breakdown by pattern :")
        for k, v in sorted(total_stats.items()):
            print(f"  {k:32s} : {v}")
    return SUCCESS


if __name__ == "__main__":
    sys.exit(main())
