"""scan_legacy.py — Detect languages + frameworks in workspace/old/{P}/.

Reads `language_signatures.yml` (single source of truth for D1) and matches
file content via regex evidence_patterns to score each language.

Public API:
    load_signatures(yaml_path) -> dict
    normalize_bytes(file_bytes) -> bytes              # ADV-11 + ADV-20
    scan_project(project_root, signatures, exclusions=None) -> ScanResult

ScanResult shape (machine-readable):
    {
        "primaryLanguage": "aspx-webforms",
        "languagesDetected": [{"id", "label", "confidence", "filesCount", "locTotal"}, ...],
        "frameworksDetected": [{"id", "version", "evidence"}, ...],
        "scanDurationMs": int,
        "filesScanned": int,
        "filesSkipped": int,
    }

ADV-11 / ADV-20 closure: normalize_bytes strips BOMs (UTF-8/UTF-16-LE/UTF-16-BE)
and unifies EOL (CRLF/LF/CR → LF) BEFORE any size/content measurement.
This guarantees cross-OS fingerprint stability.
"""

from __future__ import annotations

import logging
import pathlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Module logger — capture-able by callers, suppressed by default if no
# handler is configured. Used to surface malformed regex in
# `language_signatures.yml` instead of swallowing them silently (audit
# 2026-06-10 P0 closure).
_LOG = logging.getLogger("sdd_reverse.scan_legacy")


def _warn_bad_pattern(
    lang_id: str,
    pattern_kind: str,
    pattern: str,
    err: re.error,
    *,
    file: Path | None = None,
) -> None:
    """Emit a structured WARN for a malformed regex in language_signatures.yml.

    Centralizes the previously-silent ``except re.error`` swallows so a
    misconfigured signature is auditable (CI logs, /sdd-reverse-status,
    eventual ingest). Does NOT raise — the scan continues with reduced
    accuracy on the offending pattern.
    """
    where = f" file={file}" if file is not None else ""
    _LOG.warning(
        "[SCAN_LEGACY_BAD_REGEX] lang=%s kind=%s pattern=%r err=%s%s",
        lang_id, pattern_kind, pattern, err, where,
    )

# Default exclusions applied to every scan (in addition to per-language).
DEFAULT_GLOBAL_EXCLUSIONS = frozenset(
    {".git", ".svn", ".hg", "node_modules", "__pycache__", ".vs", ".idea",
     ".gradle", "target", "bin", "obj", "dist", "build", "packages", "vendor",
     # Audit 2026-08-25: `.sys` is the reverse's OWN machine-managed output
     # (`proc-snapshot/*.sql`, `schema-snapshot/*.sql`, inventory, caches).
     # Scanning it made the module re-read its own artifacts as if they were
     # legacy source: T-SQL language scores inflated by generated snapshots, and
     # `db_schema_extractor` parsing our rendered `CREATE TABLE` documentation as
     # discovered DDL. A reverse must never feed on its own output.
     ".sys"}
)

# Binary file extensions to skip (no content read).
BINARY_EXTENSIONS = frozenset(
    {".exe", ".dll", ".so", ".dylib", ".pyc", ".pyo", ".class", ".jar",
     ".zip", ".tar", ".gz", ".7z", ".rar", ".pdf", ".png", ".jpg", ".jpeg",
     ".gif", ".bmp", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot",
     ".mp3", ".mp4", ".avi", ".mov", ".wav", ".bin", ".dat", ".db",
     ".sqlite", ".sqlite3"}
)

# Bug #4 fix: auto-generated files matched by filename suffix (not folder).
# Excluded from language scoring AND framework detection to avoid LOC inflation.
AUTO_GENERATED_SUFFIXES = frozenset({
    ".designer.cs",     # WebForms auto-generated controls
    ".designer.vb",     # WebForms VB
    ".g.cs",            # Roslyn source generators
    ".g.i.cs",          # XAML/MSBuild
    ".Designer.cs",     # alternate casing
    ".AssemblyInfo.cs", # MSBuild auto-generated
})

# Bug #1 fix: cross-language framework manifest files. Scanned independently of
# any specific language's file_extensions — every framework_signature in
# language_signatures.yml is evaluated against each of these files.
FRAMEWORK_MANIFEST_FILES = frozenset({
    "Web.config", "web.config",
    "App.config", "app.config",
    "web.xml", "applicationContext.xml", "faces-config.xml",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "package.json", "tsconfig.json",
    "composer.json",
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "packages.config",
    "Cargo.toml", "go.mod",
})

# BOMs ordered longest-first to avoid mis-matching the shorter UTF-16 BOM
# inside a UTF-32 stream (defensive — we only strip the first matching one).
_BOMS = (
    b"\xef\xbb\xbf",      # UTF-8
    b"\xff\xfe",          # UTF-16-LE
    b"\xfe\xff",          # UTF-16-BE
)


@dataclass
class LanguageMatch:
    """One detected language with per-file aggregates."""

    id: str
    label: str
    family: str
    confidence_cap: str
    files: list[Path] = field(default_factory=list)
    loc_total: int = 0
    score_total: float = 0.0
    # Audit F-05: number of matches on patterns flagged `discriminative: true`,
    # i.e. evidence that CANNOT come from a sibling dialect of the same
    # `exclusive_group`. A dialect with 0 here has only been seen through DDL
    # shared by every engine — see `_absorb_phantom_dialects`.
    discriminative_hits: int = 0
    # NOTE: framework signatures detected during scan are aggregated globally
    # in ScanResult.frameworks (cross-language). The previous per-language
    # field was never populated — removed 2026-06-10 (audit closure).


@dataclass
class ScanResult:
    primary_language: str | None
    languages: list[LanguageMatch]
    frameworks: list[dict[str, Any]]
    files_scanned: int
    files_skipped: int
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "primaryLanguage": self.primary_language,
            "languagesDetected": [
                {
                    "id": lm.id,
                    "label": lm.label,
                    "family": lm.family,
                    "confidence": _score_to_confidence(lm.score_total, lm.confidence_cap),
                    "filesCount": len(lm.files),
                    "locTotal": lm.loc_total,
                }
                for lm in self.languages
            ],
            "frameworksDetected": self.frameworks,
            "filesScanned": self.files_scanned,
            "filesSkipped": self.files_skipped,
            "scanDurationMs": self.duration_ms,
        }


def normalize_bytes(file_bytes: bytes) -> bytes:
    """Strip BOMs + unify EOL (ADV-11 + ADV-20)."""
    for bom in _BOMS:
        if file_bytes.startswith(bom):
            file_bytes = file_bytes[len(bom):]
            break
    file_bytes = file_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return file_bytes


def decode_text(data: bytes) -> str:
    """Decode (normalized) legacy bytes to str with encoding fallback.

    Order : UTF-8 strict → cp1252 (dominant Windows/FR legacy encoding) →
    UTF-8 with replacement. Audit 2026-06-10 M18 : decoding everything as
    ``utf-8 errors=replace`` silently corrupted cp1252 accented FR text
    (labels, comments, SQL littéraux) into U+FFFD without any WARN —
    evidence quality degraded invisibly. cp1252 is attempted as a whole-file
    decode so mixed mojibake is impossible (one encoding per file).
    """
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except (UnicodeDecodeError, LookupError):
        return data.decode("utf-8", errors="replace")


def load_signatures(yaml_path: str | Path) -> dict[str, Any]:
    """Load language_signatures.yml into a dict.

    Raises FileNotFoundError if absent, ValueError if schemaVersion missing.
    """
    p = Path(yaml_path)
    if not p.is_file():
        raise FileNotFoundError(f"language_signatures.yml not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "schemaVersion" not in data or "languages" not in data:
        raise ValueError(f"Invalid signatures file: {p} (missing schemaVersion or languages)")
    if data["schemaVersion"] != 1:
        raise ValueError(f"Unsupported schemaVersion: {data['schemaVersion']}")
    return data


def _score_to_confidence(score: float, cap: str) -> str:
    """Map cumulative score to confidence enum, applying cap.

    Heuristic: score >= 5 → high, >= 2 → medium, else low.
    Always min(computed, cap).
    """
    if score >= 5.0:
        computed = "high"
    elif score >= 2.0:
        computed = "medium"
    else:
        computed = "low"
    rank = {"high": 3, "medium": 2, "low": 1}
    cap_normalized = cap if cap in rank else "low"
    return computed if rank[computed] <= rank[cap_normalized] else cap_normalized


def _lang_excludes_path(lang: dict[str, Any], rel_parts: tuple[str, ...], filename: str) -> bool:
    """Apply a language's `excluded_paths` YAML entries to one file.

    Audit 2026-06-10 M18 : these entries were declared on all 13 languages
    but never applied (dead config — `.min.js` was never filtered, `vendor/`
    only via global defaults). Two entry shapes are supported :
        - `dir/`  → directory-name match anywhere in the relative path
        - `.suffix` (no trailing slash) → filename suffix match (e.g. `.min.js`)
    """
    for entry in lang.get("excluded_paths") or []:
        e = str(entry).strip()
        if not e:
            continue
        if e.endswith("/"):
            if e.rstrip("/") in rel_parts:
                return True
        elif filename.endswith(e):
            return True
    return False


def _should_skip_path(path: Path, project_root: Path, exclusions: set[str]) -> bool:
    """Return True if `path` should be ignored (excluded dir, binary, OR auto-gen)."""
    try:
        rel = path.relative_to(project_root)
    except ValueError:
        return True
    for part in rel.parts:
        if part in exclusions:
            return True
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    # Bug #4 fix: exclude auto-generated files (preserve LOC accuracy)
    name = path.name
    for suffix in AUTO_GENERATED_SUFFIXES:
        if name.endswith(suffix):
            return True
    return False


def _count_loc(content_bytes_normalized: bytes) -> int:
    """Count non-empty lines (LOC) on normalized bytes."""
    if not content_bytes_normalized:
        return 0
    lines = content_bytes_normalized.split(b"\n")
    return sum(1 for line in lines if line.strip())


def _normalize_path(p: Path) -> Path:
    """Resolve to absolute + ensure UTF-8 representation (ADV-8 — Unicode safety)."""
    try:
        return p.resolve()
    except (OSError, ValueError):
        # Fallback: return as-is, downstream callers handle missing/unreadable
        return p


def _read_file_with_sampling(path: Path, max_size_kb: int | None) -> tuple[bytes, bool]:
    """Read file bytes, applying head_tail sampling if larger than `max_size_kb`.

    Returns (bytes_to_scan, was_sampled).
    ADV-8 closure: gros fichiers (> max_size_kb) lus en mode sampling
    (premiers 200KB + derniers 200KB) pour borner mémoire et tokens.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return b"", False
    if max_size_kb is None or size <= max_size_kb * 1024:
        try:
            return path.read_bytes(), False
        except (OSError, UnicodeDecodeError):
            return b"", False
    # Sampling mode: head 200KB + tail 200KB
    sample_size = 200 * 1024
    try:
        with open(path, "rb") as f:
            head = f.read(sample_size)
            try:
                f.seek(-sample_size, 2)  # SEEK_END
                tail = f.read(sample_size)
            except OSError:
                tail = b""
            return head + b"\n/* ...SAMPLED... */\n" + tail, True
    except OSError:
        return b"", False


def _exclusive_rank(
    lang: dict[str, Any],
    score: float,
    discriminative_hits: int,
    lang_order: dict[str, int],
) -> tuple[int, float, int]:
    """Sort key for the exclusivity arbitration — lowest wins.

    Ordered by (1) does this dialect have EXCLUSIVE evidence here, (2) raw
    score, (3) declaration order in `language_signatures.yml`. Criterion (1)
    is the load-bearing one: score alone is not a dialect proof, because the
    shared `CREATE PROCEDURE` / `CREATE FUNCTION` DDL matches every engine.
    """
    return (
        0 if discriminative_hits else 1,
        -score,
        lang_order.get(lang["id"], 10_000),
    )


def _resolve_exclusive_groups(
    scored: list[tuple[dict[str, Any], float, int]],
    lang_order: dict[str, int],
) -> list[tuple[dict[str, Any], float, int]]:
    """Keep a single winner per `exclusive_group` FOR ONE FILE.

    Audit F-05 (2026-08-25). The four SQL dialects share the `.sql` extension
    AND share evidence patterns (`CREATE PROCEDURE` alone matches T-SQL,
    PL/pgSQL, PL/SQL *and* MySQL), so every T-SQL file was being claimed by all
    four buckets at once. Two consequences, the second the expensive one:

      * artefacts emitted once per dialect — views/triggers/parseWarnings ×4
      * `confidence_caps_applied` is min-monotone over detected languages
        (`language_signatures.yml` §5.6), so a purely T-SQL application
        (`cap: high`) was demoted to `medium` because PL/SQL and MySQL
        (`cap: medium`, scaffold-validated only) were believed present. The
        whole specification ladder then inherits that lowered confidence.

    A file is written in ONE dialect: the best-ranked one wins
    (cf. `_exclusive_rank`). Ties break on declaration order in
    `language_signatures.yml`, which puts the dominant legacy dialect first —
    deterministic, and never alphabetical (that would hand a tie to `mysql`
    over `tsql`).

    Languages with no `exclusive_group` are passed through untouched, so this is
    a no-op for every non-SQL language.
    """
    if len(scored) < 2:
        return scored

    winners: dict[str, str] = {}   # group -> winning language id
    for lang, score, hits in scored:
        group = lang.get("exclusive_group")
        if not group:
            continue
        champion = winners.get(group)
        if champion is None:
            winners[group] = lang["id"]
            continue
        current = next(e for e in scored if e[0]["id"] == champion)
        if (_exclusive_rank(lang, score, hits, lang_order)
                < _exclusive_rank(*current, lang_order)):
            winners[group] = lang["id"]

    # Filter in place — the input order is preserved so that downstream
    # first-wins behaviour (framework detection) is unaffected by this pass.
    return [
        entry for entry in scored
        if not entry[0].get("exclusive_group")
        or winners.get(entry[0]["exclusive_group"]) == entry[0]["id"]
    ]


def _absorb_phantom_dialects(
    matches: dict[str, "LanguageMatch"],
    all_langs: dict[str, dict[str, Any]],
    lang_order: dict[str, int],
) -> None:
    """Second F-05 pass, PROJECT-wide: fold dialects that never proved themselves.

    Per-file exclusivity (`_resolve_exclusive_groups`) guarantees one dialect
    per file but not one dialect per project: a single `.sql` file whose only
    evidence is the shared DDL still opens a bucket of its own. That phantom
    bucket is not cosmetic — `confidence_caps_applied` is min-monotone over the
    detected languages, so one file wrongly attributed to `mysql` or `plsql`
    (`cap: medium`, scaffold-validated only) demotes an entire SQL Server
    application from `high` to `medium`, and the whole specification ladder
    inherits it. This is the audit's fallback requirement — "exclude the
    dialects that were not retained from the confidence-cap computation" —
    enforced by removing them outright rather than special-casing the cap.

    A dialect survives only if it carries EXCLUSIVE evidence somewhere in the
    project (a pattern flagged `discriminative: true`). Dialects that never did
    are absorbed into the group's best-ranked survivor: their files move over,
    so nothing is lost for the extractor downstream — only the misattribution.

    A genuinely polyglot repository is preserved: PostgreSQL scripts carrying
    `LANGUAGE plpgsql` and MySQL scripts carrying `DELIMITER` each keep their
    own bucket, because each proved itself.
    """
    groups: dict[str, list[LanguageMatch]] = {}
    for lm in matches.values():
        group = all_langs.get(lm.id, {}).get("exclusive_group")
        if group:
            groups.setdefault(group, []).append(lm)

    for members in groups.values():
        if len(members) < 2:
            continue
        proven = [lm for lm in members if lm.discriminative_hits]
        phantoms = [lm for lm in members if not lm.discriminative_hits]
        if not phantoms:
            continue
        # No dialect proved itself: keep the best-ranked one rather than
        # dropping the group entirely (fail-safe — never lose the SQL files).
        pool = proven or members
        winner = min(
            pool,
            key=lambda lm: _exclusive_rank(
                all_langs[lm.id], lm.score_total, lm.discriminative_hits, lang_order),
        )
        for lm in phantoms:
            if lm is winner:
                continue
            winner.files.extend(lm.files)
            winner.loc_total += lm.loc_total
            winner.score_total += lm.score_total
            del matches[lm.id]
        winner.files.sort(key=str)


def scan_project(
    project_root: str | Path,
    signatures: dict[str, Any],
    exclusions: set[str] | None = None,
) -> ScanResult:
    """Scan `project_root` and return a ScanResult.

    - Skips dirs in DEFAULT_GLOBAL_EXCLUSIONS + per-language excluded_paths
    - Reads file bytes, normalizes (BOM + EOL), runs evidence regex
    - Aggregates score per language
    - Applies per-language max_file_size_kb sampling (ADV-8)
    - Handles Unicode paths with UnicodeDecodeError fallback (ADV-8)
    """
    project = _normalize_path(Path(project_root))
    if not project.is_dir():
        raise FileNotFoundError(f"Project root not found: {project}")

    t0 = time.monotonic()
    excl = set(DEFAULT_GLOBAL_EXCLUSIONS)
    if exclusions:
        excl |= set(exclusions)

    # Build per-language lookup keyed by file extension.
    lang_by_ext: dict[str, list[dict[str, Any]]] = {}
    all_langs: dict[str, dict[str, Any]] = {}
    all_langs_order: dict[str, int] = {}
    for idx, lang in enumerate(signatures["languages"]):
        all_langs[lang["id"]] = lang
        all_langs_order[lang["id"]] = idx
        for ext in lang.get("file_extensions", []):
            lang_by_ext.setdefault(ext.lower(), []).append(lang)

    matches: dict[str, LanguageMatch] = {}
    frameworks_seen: dict[str, dict[str, Any]] = {}
    files_scanned = 0
    files_skipped = 0

    for path in project.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip_path(path, project, excl):
            files_skipped += 1
            continue

        ext = path.suffix.lower()
        candidates = lang_by_ext.get(ext, [])
        if not candidates:
            files_skipped += 1
            continue

        # M18 : per-language excluded_paths (dir/ + filename-suffix entries).
        rel_parts = path.relative_to(project).parts
        candidates = [
            lang for lang in candidates
            if not _lang_excludes_path(lang, rel_parts, path.name)
        ]
        if not candidates:
            files_skipped += 1
            continue

        # Per-language max_file_size_kb sampling (ADV-8). The first matching
        # candidate language drives the limit (conservative — use min across cands).
        max_kb = None
        for lang in candidates:
            lang_max = lang.get("max_file_size_kb")
            if lang_max:
                max_kb = lang_max if max_kb is None else min(max_kb, lang_max)
        raw, was_sampled = _read_file_with_sampling(path, max_kb)
        if not raw:
            files_skipped += 1
            continue

        try:
            content = normalize_bytes(raw)
            content_str = decode_text(content)
        except (UnicodeDecodeError, UnicodeError):
            files_skipped += 1
            continue

        files_scanned += 1
        loc = _count_loc(content)

        # Score against each candidate language.
        scored: list[tuple[dict[str, Any], float, int]] = []
        for lang in candidates:
            file_score = 0.0
            file_discriminative = 0
            for ep in lang.get("evidence_patterns") or []:
                pattern = ep.get("pattern")
                weight = float(ep.get("weight", 0.0))
                if not pattern:
                    continue
                try:
                    if re.search(pattern, content_str):
                        file_score += weight
                        if ep.get("discriminative"):
                            file_discriminative += 1
                except re.error as err:
                    # Skip malformed regex but don't crash the scan.
                    _warn_bad_pattern(lang["id"], "evidence_pattern", pattern, err, file=path)
                    continue

            if file_score <= 0:
                continue
            scored.append((lang, file_score, file_discriminative))

        # Mutually exclusive groups (audit F-05, 2026-08-25) — one file cannot
        # be written in two dialects of the same engine family at once. See
        # `_resolve_exclusive_groups`.
        scored = _resolve_exclusive_groups(scored, all_langs_order)

        for lang, file_score, file_discriminative in scored:
            lm = matches.get(lang["id"])
            if lm is None:
                lm = LanguageMatch(
                    id=lang["id"],
                    label=lang["label"],
                    family=lang.get("family", "unknown"),
                    confidence_cap=lang.get("confidence_cap", "low"),
                )
                matches[lang["id"]] = lm
            lm.files.append(path)
            lm.loc_total += loc
            lm.score_total += file_score
            lm.discriminative_hits += file_discriminative

            # Framework detection
            for fsig in lang.get("framework_signatures") or []:
                fevidence = fsig.get("evidence")
                if not fevidence:
                    continue
                try:
                    m = re.search(fevidence, content_str)
                except re.error as err:
                    _warn_bad_pattern(lang["id"], "framework_evidence", fevidence, err, file=path)
                    continue
                if not m:
                    continue
                fid = fsig.get("id", "unknown")
                version: str | None = None
                vex = fsig.get("version_extract")
                if vex:
                    try:
                        vm = re.search(vex, content_str)
                        if vm and vm.groups():
                            version = vm.group(1)
                    except re.error as err:
                        _warn_bad_pattern(lang["id"], "version_extract", vex, err, file=path)
                if fid not in frameworks_seen:
                    frameworks_seen[fid] = {
                        "id": fid,
                        "version": version,
                        "evidence": str(path.relative_to(project)),
                    }

    # Bug #1 fix: cross-file framework_signatures scan against manifest files
    # (Web.config, pom.xml, package.json, …) — these files are NOT in any
    # language's file_extensions but DO carry framework target/version info.
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        if path.name not in FRAMEWORK_MANIFEST_FILES:
            continue
        if _should_skip_path(path, project, excl):
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        try:
            text = decode_text(normalize_bytes(raw))
        except (UnicodeDecodeError, UnicodeError):
            continue
        rel_path = str(path.relative_to(project))
        for lang in signatures["languages"]:
            for fsig in lang.get("framework_signatures") or []:
                fevidence = fsig.get("evidence")
                if not fevidence:
                    continue
                try:
                    m = re.search(fevidence, text)
                except re.error as err:
                    _warn_bad_pattern(lang["id"], "framework_evidence_manifest", fevidence, err, file=path)
                    continue
                if not m:
                    continue
                fid = fsig.get("id", "unknown")
                version: str | None = None
                vex = fsig.get("version_extract")
                if vex:
                    try:
                        vm = re.search(vex, text)
                        if vm and vm.groups():
                            version = vm.group(1)
                    except re.error as err:
                        _warn_bad_pattern(lang["id"], "version_extract_manifest", vex, err, file=path)
                if fid not in frameworks_seen:
                    frameworks_seen[fid] = {
                        "id": fid,
                        "version": version,
                        "evidence": rel_path,
                    }

    # Audit F-05, project-wide pass: fold the dialects that never carried
    # exclusive evidence into the one that did — see `_absorb_phantom_dialects`.
    _absorb_phantom_dialects(matches, all_langs, all_langs_order)

    duration_ms = int((time.monotonic() - t0) * 1000)
    # Sort matches by score desc, then by files count desc, then by id.
    sorted_matches = sorted(
        matches.values(),
        key=lambda m: (-m.score_total, -len(m.files), m.id),
    )
    primary = sorted_matches[0].id if sorted_matches else None
    return ScanResult(
        primary_language=primary,
        languages=sorted_matches,
        frameworks=list(frameworks_seen.values()),
        files_scanned=files_scanned,
        files_skipped=files_skipped,
        duration_ms=duration_ms,
    )


# --- Lecture texte centralisée (audit 2026-06-11 B5) -------------------------
# Remplace les 7 copies locales de `_read_text()` qui vivaient dans
# config_extractor / css_palette_extractor / data_access_extractor /
# db_schema_extractor / dependency_inventory / deps_graph_builder /
# ui_template_parser. Ajoute un cap de taille generique : un dump SQL de
# production de plusieurs centaines de Mo partait integralement en RAM sans
# garde-fou. Comportement au-dela du cap : lecture TRONQUEE head (le moins
# destructeur — les CREATE TABLE/imports/usings vivent en tete de fichier),
# jamais d'exception.
DEFAULT_READ_CAP_BYTES = 5 * 1024 * 1024  # 5 Mo


def read_text_normalized(path, max_bytes: int | None = DEFAULT_READ_CAP_BYTES) -> str:
    """Read + normalize + decode a legacy file, with a size cap.

    Returns "" on any I/O error (best-effort extractors). Files larger than
    `max_bytes` are read head-truncated (pass max_bytes=None to disable).
    Decoding via decode_text (utf-8 strict -> cp1252 -> replace) — unifie les
    2 variantes historiques (certains modules perdaient le fallback cp1252).
    """
    p = pathlib.Path(path)
    try:
        if max_bytes is not None:
            try:
                too_big = p.stat().st_size > max_bytes
            except OSError:
                return ""
            if too_big:
                with open(p, "rb") as f:
                    raw = f.read(max_bytes)
                return decode_text(normalize_bytes(raw))
        raw = p.read_bytes()
    except OSError:
        return ""
    return decode_text(normalize_bytes(raw))
