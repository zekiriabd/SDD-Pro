#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (Edit / Write / Bash / PowerShell) — TDD enforcement (RED-GREEN-REFACTOR).

Audit P3 TDD (2026-06-08) — enforce test-first discipline (emprunt Superpowers
v5.1 `test-driven-development` skill). When the agent attempts to Write or
Edit production code under `workspace/src/{BackendName,AppName}/` to
ADD a new function/class/method/endpoint, this hook verifies that a
corresponding test file exists OR is being created in the same tool batch.

**Detection heuristics** (lightweight, fast) :
  - File path under `workspace/src/*/` (production scope)
  - File extension in {.cs, .ts, .tsx, .js, .jsx, .py, .kt, .java}
  - NOT under `*.Tests/`, `__tests__/`, `tests/`, `src/test/` (test scope)
  - Content contains a NEW public function/class definition (regex per language)
  - No companion test file exists for the same logical unit

**Modes** (env var `SDD_TDD_MODE` ; défaut 2026-11-07 dérivé de `CoverageMin` :
`off` si < 100, `warn` si = 100 — JAMAIS `strict` par défaut, le TDD ne bloque
pas le développement ; le verdict tests appartient au gate QA post-dev) :
  - `off`     → no-op
  - `warn`    → stderr WARN [TDD_NO_TEST_FIRST] + audit log, exit 0
  - `strict`  → exit 2 (block Write) with structured RED-first guidance

**Bypass** :
  - `SDD_DISABLE_TDD=1` env var (one-shot, audit-logged)
  - Edit of EXISTING code (refactor, no new behavior) → allowed
  - Test file itself (`*.Tests/`, `__tests__/`, etc.) → allowed
  - Non-production paths (`workspace/`, `.claude/`) → allowed

**Shell mode** (matcher `Bash|PowerShell`, audit 2026-11) : the write
targets of the command are extracted by `sdd_lib.shell_write_targets`
(`cat > X.cs <<EOF`, `Set-Content`, `Out-File`, `tee`, `cp`/`mv`/
`Copy-Item`, `python -c "open(...,'w')"`, `[IO.File]::WriteAllText`…) and
EACH target goes through the same decision as the file mode (same modes,
same bypasses, same `[TDD_NO_TEST_FIRST]` message). Content known (heredoc,
`-Value`, `echo`) → symbol regex ; copy/move → source file content ;
unknown content → fail-closed on a NEW file only. A test file with real
cases written by the same command (test + prod in one batch) counts as the
companion.

**Idempotent guard** : the hook is read-only on disk (Glob for companion
test). No side effects beyond stderr audit logging.

Fast-path : Bash detection of NEW symbols (regex) is < 10ms typical.
"""
from __future__ import annotations

import json as _json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.ci import is_ci  # noqa: E402,F401 — conservé (compat tests monkeypatch)
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_file_path,
    is_subagent_call,  # noqa: F401 — conservé (compat)
    read_hook_input,
)
from sdd_lib.paths import normalize, repo_root  # noqa: E402


#: Production file extensions that should follow TDD
_PROD_EXTENSIONS = frozenset({
    ".cs", ".ts", ".tsx", ".js", ".jsx",
    ".py", ".kt", ".java",
    ".razor",  # Blazor components (limited TDD relevance, but checked)
})

#: Path segments that mark TEST files (bypass)
_TEST_PATH_MARKERS = (
    ".tests/",      # .NET convention {Project}.Tests/
    "__tests__/",   # JS/TS convention
    "/tests/",      # Python/Go convention
    "/test/",       # Java/Kotlin Gradle convention (src/test/kotlin)
    "/spec/",       # JS spec convention
    ".test.",       # filename.test.ts
    ".spec.",       # filename.spec.ts
    "_test.",       # filename_test.py / filename_test.go
    "test_",        # test_filename.py
)

#: Path segments that are NOT production (skip TDD entirely).
#: Flatten 2026-07-06 : ex-`workspace/input/` sources vivent directement sous
#: workspace/ (feats, ui, stack, assets, discovery) — listées ici pour rester
#: hors-scope TDD sans exclure workspace/src/ (le code production).
_NON_PROD_PATH_MARKERS = (
    "workspace/feats/",
    "workspace/ui/",
    "workspace/stack/",
    "workspace/assets/",
    "workspace/discovery/",
    ".claude/",
    "node_modules/",
    "bin/", "obj/", "dist/", "build/",
    "__pycache__/", ".venv/", "venv/",
    ".gradle/", "target/",
)

#: Regex per extension to detect a "new public definition" (function/class/method).
#: Conservative : matches obvious patterns, not exhaustive. False negatives OK
#: (skill prompts user); false positives create noise but the WARN can be
#: bypassed.
_NEW_SYMBOL_PATTERNS: dict[str, list[str]] = {
    # Audit 2026-11 : `internal`/`private`/`protected` et classes sans
    # modificateur (internal implicite en C#) comptent aussi — l'ancien
    # filtre `public` seul laissait passer tout le code `internal sealed`.
    ".cs": [
        r"^\s*(?:(?:public|internal|private|protected|static|sealed|abstract|partial|file|readonly|unsafe|new)\s+)*(?:class|record|struct|interface)\s+\w+",
        r"^\s*(?:public|internal|private|protected)\s+(?:(?:static|async|virtual|override|sealed|abstract|partial|new|extern|unsafe)\s+)*\w[\w<>?,\[\]\s]*\s+\w+\s*\(",
    ],
    ".ts": [
        r"^\s*export\s+(?:async\s+)?(?:function|class|const|interface|type)\s+\w+",
        r"^\s*export\s+default\s+(?:async\s+)?(?:function|class)\s+\w*",
    ],
    ".tsx": [
        r"^\s*export\s+(?:async\s+)?(?:function|class|const|interface|type)\s+\w+",
        r"^\s*export\s+default\s+(?:async\s+)?(?:function|class)\s+\w*",
    ],
    ".js": [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+",
        r"^\s*(?:export\s+)?class\s+\w+",
    ],
    ".jsx": [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+",
        r"^\s*(?:export\s+)?class\s+\w+",
    ],
    ".py": [
        r"^\s*def\s+[a-zA-Z]\w*\s*\(",
        r"^\s*class\s+[a-zA-Z]\w*\s*[:\(]",
    ],
    ".kt": [
        r"^\s*(?:(?:public|internal|private|protected|open|override|suspend|inline|operator|infix|tailrec)\s+)*fun\s+(?:<[^>]*>\s*)?[\w.]+\s*\(",
        r"^\s*(?:(?:public|internal|private|protected|open|abstract|sealed|data|enum|inner|value|annotation)\s+)*(?:class|interface|object)\s+\w+",
    ],
    ".java": [
        r"^\s*(?:(?:public|protected|private|static|abstract|final|sealed)\s+)*(?:class|interface|record|enum)\s+\w+",
        r"^\s*(?:public|protected|private)\s+(?:(?:static|abstract|final|synchronized)\s+)*\w[\w<>?,\[\]\s]*\s+\w+\s*\(",
    ],
    ".razor": [
        r"@code\s*\{",  # presence of code block in Razor
    ],
}


#: Seuil au-delà duquel le TDD est « appliqué » (signal) — en deçà il est off.
_TDD_FULL_COVERAGE = 100
#: Défaut framework de CoverageMin quand stack.md / team.yml ne le fixent pas.
_DEFAULT_COVERAGE_MIN = 80


def _coverage_min() -> int:
    """CoverageMin effectif du projet (layered config → stack.md → défaut 80).

    Même source que le gate coverage QA (`parse_coverage.detect_coverage_min`),
    sans importer ce module (il tire console_db — trop lourd pour un hook
    déclenché à chaque Write/Bash). Toute erreur → défaut (80 → TDD off).
    """
    try:
        import contextlib
        import io
        from sdd_lib.layered_config import read_layered_config
        # read_layered_config émet des WARN [ENV_MISSING] sur stderr sans
        # rapport avec CoverageMin — muets ici (hook appelé à chaque outil).
        with contextlib.redirect_stderr(io.StringIO()):
            raw = read_layered_config(keys=("CoverageMin",)).get("CoverageMin")
        if raw not in (None, ""):
            return int(str(raw).strip())
    except Exception:  # noqa: BLE001 — config illisible : défaut, jamais bloquant
        pass
    try:
        from sdd_lib.project_config import stack_md_path
        text = stack_md_path().read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?m)^\s*CoverageMin\s*:\s*(\d+)", text)
        if m:
            return int(m.group(1))
    except Exception:  # noqa: BLE001
        pass
    return _DEFAULT_COVERAGE_MIN


def _resolve_mode(payload: dict | None = None) -> str:
    """Return TDD mode — le TDD ne bloque JAMAIS le développement par défaut.

    Organisation SDD-Pro (décision Tech Lead 2026-11-07) : backend → frontend
    → tests unitaires écrits par `qa` APRÈS le développement. Le verdict sur
    les tests appartient au gate QA (coverage vs `CoverageMin`, puis delivery
    gate `verify_tests --coverage`), pas à ce hook :

      - `SDD_TDD_MODE` explicite (off|warn|strict, protégé par
        block_env_bypass) → honoré. `strict` = opt-in humain uniquement.
      - `CoverageMin` < 100 → `off` : le projet n'exige pas une couverture
        totale, la discipline test-first ne s'applique pas.
      - `CoverageMin` = 100 → `warn` : signal `[TDD_NO_TEST_FIRST]` en
        stderr + audit, jamais de blocage ; la QA tranche ensuite.

    L'ancien défaut `strict` (CI + sous-agents, audit 2026-11) interbloquait
    dev-backend/dev-frontend, à qui l'écriture de tests est interdite
    (`[QA_OWNERSHIP_VIOLATION]`). `payload` est conservé pour compatibilité.
    """
    explicit = os.environ.get("SDD_TDD_MODE", "").strip().lower()
    if explicit in ("off", "warn", "strict"):
        return explicit
    if _coverage_min() < _TDD_FULL_COVERAGE:
        return "off"
    return "warn"


#: Marqueurs d'un VRAI test (au moins un cas). Un fichier compagnon qui n'en
#: contient aucun (squelette vide) ne satisfait pas le contrat test-first.
_TEST_CASE_MARKERS = re.compile(
    r"\[(?:Fact|Theory|Test|TestMethod|TestCase|DataTestMethod)\b"
    r"|@Test\b|@ParameterizedTest\b"
    r"|\b(?:it|test)\s*(?:\.\w+\s*)?\("
    r"|^\s*(?:async\s+)?def\s+test_\w*\s*\("
    r"|\bfun\s+`[^`]+`\s*\(",
    re.MULTILINE,
)


def _has_test_cases(path: Path) -> bool:
    try:
        if path.stat().st_size > 2_000_000:
            return True
        return bool(_TEST_CASE_MARKERS.search(path.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def _is_production_path(path_norm: str) -> bool:
    """True if path is in workspace/src/ and not in a test sub-tree."""
    if not path_norm.startswith("workspace/src/"):
        return False
    low = path_norm.lower()
    if any(marker in low for marker in _TEST_PATH_MARKERS):
        return False
    if any(marker in low for marker in _NON_PROD_PATH_MARKERS):
        return False
    return True


def _get_extension(path_str: str) -> str:
    """Return lowercase file extension, including the dot."""
    for ext in sorted(_PROD_EXTENSIONS, key=len, reverse=True):
        if path_str.lower().endswith(ext):
            return ext
    return ""


def _content_introduces_new_symbol(content: str, ext: str) -> bool:
    """True if content contains a NEW public symbol per language regex."""
    patterns = _NEW_SYMBOL_PATTERNS.get(ext, [])
    for pat in patterns:
        if re.search(pat, content, re.MULTILINE):
            return True
    return False


def _has_companion_test(prod_path: Path, root: Path) -> bool:
    """Best-effort lookup for an existing test file covering this prod file.

    Strategy : Glob for `*<stem>*` under common test directories.
    Returns True if any match — conservative (false positives allowed).
    """
    stem = prod_path.stem
    if not stem or len(stem) < 3:
        return True  # too short, allow

    test_dirs = [
        # .NET
        *root.glob("workspace/src/*.Tests"),
        # Node/TS
        *root.glob("workspace/src/*/src/__tests__"),
        *root.glob("workspace/src/*/__tests__"),
        # Python
        *root.glob("workspace/src/*/tests"),
        # Kotlin/Java Gradle
        *root.glob("workspace/src/*/src/test"),
    ]

    test_filename_patterns = [
        f"*{stem}*.cs",
        f"*{stem}*.ts", f"*{stem}*.tsx",
        f"*{stem}*.js", f"*{stem}*.jsx",
        f"test_{stem}.py", f"{stem}_test.py", f"*{stem}*.py",
        f"{stem}Test.kt", f"{stem}Tests.kt", f"*{stem}*.kt",
        f"{stem}Test.java", f"*{stem}*.java",
    ]

    for td in test_dirs:
        if not td.is_dir():
            continue
        for pattern in test_filename_patterns:
            try:
                matches = list(td.rglob(pattern))
            except OSError:
                continue
            # Audit 2026-11 : un compagnon vide (0 [Fact]/[Test]/it(/def test_)
            # ne compte pas.
            if any(m.is_file() and _has_test_cases(m) for m in matches):
                return True

    return False


def _repo_rel(file_path: str, root: Path) -> str:
    """Repo-relative forward-slash path (input absolute or relative)."""
    path_norm = normalize(file_path)
    try:
        if Path(path_norm).is_absolute():
            path_norm = str(Path(path_norm).relative_to(root)).replace("\\", "/")
    except (ValueError, OSError):
        pass
    return path_norm


def _violation(path_norm: str, content: str | None, root: Path,
               batch_tests: tuple[tuple[str, str], ...] = ()) -> str | None:
    """Return the extension when writing `content` at `path_norm` breaks
    test-first, else None. Shared by file mode and shell mode.

    `content is None` (shell write whose content is unknown) : fail-closed
    on a NEW file only — modifying an existing file with unknown content is
    treated like an Edit without new symbol (refactor).
    `batch_tests` : `(test_path, content)` written by the SAME shell command
    (test + prod in one heredoc batch) — a companion with real test cases
    there satisfies the contract.
    """
    if not _is_production_path(path_norm):
        return None
    ext = _get_extension(path_norm)
    if not ext:
        return None
    prod_path = root / path_norm
    if content is None:
        if prod_path.exists():
            return None
    else:
        if not isinstance(content, str) or not content.strip():
            return None
        if not _content_introduces_new_symbol(content, ext):
            # Pure refactor / value change / config tweak — TDD allows
            return None
    stem = prod_path.stem
    for tpath, tcontent in batch_tests:
        if stem and stem.lower() in tpath.lower().rsplit("/", 1)[-1] \
                and _TEST_CASE_MARKERS.search(tcontent or ""):
            return None
    if _has_companion_test(prod_path, root):
        return None
    return ext


def _message(ext: str, path_norm: str, via: str = "") -> str:
    return (
        f"[TDD_NO_TEST_FIRST] About to write a NEW production symbol "
        f"({ext}) at {path_norm}{via}, but no companion test file detected.\n"
        f"  RED-GREEN-REFACTOR contract (SDDPro v7.0.0+ emprunt Superpowers v5.1) :\n"
        f"    1. Write the FAILING test first (in *.Tests/, __tests__/, tests/, or src/test/)\n"
        f"    2. Run the test, confirm RED\n"
        f"    3. Then write the minimal production code to make it GREEN\n"
        f"    4. Refactor if needed\n"
        f"  Bypass options :\n"
        f"    - SDD_TDD_MODE=warn (default interactive) — this becomes WARN only\n"
        f"    - SDD_TDD_MODE=off — disable TDD enforcement entirely\n"
        f"    - SDD_DISABLE_TDD=1 — one-shot bypass (audit-logged)\n"
        f"  Skill reference : @.sdd/skills/test-driven-development/SKILL.md\n"
    )


def _emit(mode: str, msg: str) -> int:
    if mode == "strict":
        sys.stderr.write(f"ERROR: {msg}")
        return HOOK_DENY
    # warn mode
    sys.stderr.write(f"WARN {msg}")
    return HOOK_ALLOW


#: Opérations shell qui PRODUISENT un fichier (les suppressions ne
#: concernent pas le contrat test-first).
_SHELL_PRODUCING_OPS = frozenset({"redirect", "write", "copy", "move", "inplace",
                                  "inline", "download", "git", "archive"})


def _shell_content(t, base: Path) -> str | None:
    """Contenu écrit par une cible shell : connu (heredoc, -Value…), sinon
    lu depuis la source d'une copie/déplacement, sinon None (inconnu)."""
    if t.content is not None:
        return t.content
    for src in t.sources:
        sp = Path(src) if Path(src).is_absolute() else base / (t.cwd or "") / src
        try:
            if sp.is_file() and sp.stat().st_size <= 2_000_000:
                return sp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return None


def _main_shell(payload: dict, mode: str, root: Path) -> int:
    from sdd_lib.shell_write_targets import extract_write_targets, resolve_target
    cmd = (payload.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return HOOK_ALLOW
    cwd = payload.get("cwd")
    base = Path(cwd) if isinstance(cwd, str) and cwd.strip() and Path(cwd).is_dir() else root
    writes: list[tuple[object, str, str | None]] = []
    for t in extract_write_targets(cmd):
        if t.op not in _SHELL_PRODUCING_OPS or "$" in t.path:
            continue
        abs_p = resolve_target(t, base) or (root / t.path)
        path_norm = _repo_rel(str(abs_p), root)
        if Path(path_norm).is_absolute() or path_norm.startswith("../"):
            continue  # hors dépôt
        writes.append((t, path_norm, _shell_content(t, base)))
    batch_tests = tuple((pn, c or "") for _t, pn, c in writes
                        if pn.startswith("workspace/src/") and not _is_production_path(pn))
    for t, path_norm, content in writes:
        ext = _violation(path_norm, content, root, batch_tests)
        if ext:
            return _emit(mode, _message(ext, path_norm, f" [shell : {t.describe()}]"))
    return HOOK_ALLOW


def main() -> int:
    """Hook entry. Narrow exception scope per audit P3 C3 pattern."""
    try:
        payload = read_hook_input()
    except (_json.JSONDecodeError, OSError, UnicodeError, ValueError):
        return HOOK_ALLOW

    mode = _resolve_mode(payload)
    if mode == "off":
        return HOOK_ALLOW
    if os.environ.get("SDD_DISABLE_TDD") == "1":
        sys.stderr.write(
            "WARN [TDD_BYPASSED] SDD_DISABLE_TDD=1 — test-first discipline "
            "bypassed for this tool call. Audit-logged.\n"
        )
        return HOOK_ALLOW

    tool_name = payload.get("tool_name", "")
    if tool_name in ("Bash", "PowerShell"):
        try:
            root = repo_root()
        except (OSError, RuntimeError):
            return HOOK_ALLOW
        return _main_shell(payload, mode, root)
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return HOOK_ALLOW

    file_path = get_file_path(payload)
    if not file_path:
        return HOOK_ALLOW

    try:
        root = repo_root()
    except (OSError, RuntimeError):
        return HOOK_ALLOW
    # Make path relative to repo_root for consistent matching against
    # `workspace/src/` prefix (handles both absolute and relative inputs).
    path_norm = _repo_rel(file_path, root)

    # Extract proposed content (Write tool) or new_string (Edit tool)
    tool_input = payload.get("tool_input", {})
    content = tool_input.get("content") or tool_input.get("new_string") or ""
    if not isinstance(content, str) or not content.strip():
        return HOOK_ALLOW

    ext = _violation(path_norm, content, root)
    if not ext:
        return HOOK_ALLOW
    # No companion test found for a new production symbol → flag
    return _emit(mode, _message(ext, path_norm))


if __name__ == "__main__":
    sys.exit(main())
