#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook — protection des fichiers framework et des
artefacts de gate.

Deux points d'entrée dans le MÊME module (dispatch sur `tool_name`) :

  * matcher `Edit|Write|MultiEdit|NotebookEdit` → mode fichier : refuse (ou
    avertit) les écritures sur les chemins `FRAMEWORK_OWNED` (`.sdd/`,
    `.claude/`, `.codex/`, `.gemini/`) et sur les **artefacts de gate**
    `GATE_ARTIFACT_DIRS` (`workspace/.sys/.validation/`, `.acceptance/`,
    `.audit/`, `.state/`), que seuls les scripts Python déterministes ont
    vocation à produire — sauf les fichiers que `loader.yml` (`writes:`)
    attribue explicitement à l'agent appelant (rapports d'auditeurs,
    `{n}-api-tests.json` de qa, sentinels `.state/*.flag` d'arch/dev-*).
  * matcher `Bash|PowerShell` → mode shell : même politique appliquée aux
    commandes qui ÉCRIVENT sur ces chemins (redirections, `tee`, `sed -i`,
    `cp`/`mv`/`rm`, `Set-Content`/`Out-File`/`Remove-Item`…, `python -c`
    ouvrant un fichier en écriture, `git checkout --`/`git restore` sur
    `.sdd`/`.claude`). **Heuristique assumée** : tokenisation de la ligne
    de commande, pas d'interprétation shell — un contournement par
    variable (`D=.sdd; rm -rf $D`) ou par script intermédiaire n'est pas
    détecté. Ce mode est une barrière contre l'écriture *accidentelle* ou
    *paresseuse* d'un agent, pas une sandbox.

Politique de mode (audit sécurité 2026-11) :

  | Contexte                                   | Mode par défaut |
  |--------------------------------------------|-----------------|
  | CI (`sdd_lib.ci.is_ci`)                    | `strict` (DENY) |
  | appel depuis un sous-agent (`agent_id`)    | `strict` (DENY) |
  | session principale (Tech Lead humain)      | `warn` (ALLOW + WARN) |

  Override unique : `SDD_PROTECT_FRAMEWORK_MODE=warn|strict|off` — variable
  elle-même protégée par `block_env_bypass` (`SDD_PROTECT_*`), donc
  positionnable uniquement dans l'environnement du process Claude Code,
  jamais inline par un agent.

Exit codes : 0 = allow (warn/off/hors périmètre), 2 = deny.

Migrated from .claude/hooks/protect-framework.ps1 (2026-05-13).
"""
from __future__ import annotations

import os
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.ci import is_ci  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_caller_agent_type,
    get_file_path,
    get_nested,
    get_tool_name,
    is_subagent_call,
    read_hook_input,
)
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


#: Bascule de politique (audit 2026-11) : True = un appel émis depuis un
#: sous-agent est traité en `strict` par défaut. Constante de module (et non
#: env var) pour qu'aucun agent ne puisse la désactiver à chaud ; seul
#: `SDD_PROTECT_FRAMEWORK_MODE` (protégé par block_env_bypass) l'emporte.
SUBAGENT_STRICT_DEFAULT = True

# Framework-owned paths, relative to repo root. P1-5 fix 2026-06-07 :
# was substring-matched via `any(p in normalized_path for p in ...)` which
# could (a) false-positive on a project file like `workspace/src/X/.claude/rules/foo.md`,
# (b) false-negative on `..\..\.claude\rules\x.md` paths after partial normalization.
# Now we canonicalize via `Path.resolve()` + `relative_to(repo_root)` for
# strict path-prefix matching.
#
# Extension 2026-07-25 (MIGRATION-PLAN Phase 1) : la protection couvre
# désormais les 4 racines-framework :
#   - `.sdd/`     (foyer neutre — SSoT versionné, seul édité à la main)
#   - `.claude/`  (façade Claude Code — générée post-Phase 2)
#   - `.codex/`   (façade Codex — générée)
#   - `.gemini/`  (façade Gemini/Antigravity — générée)
# Les agents produit (po, arch, dev-*, qa) ne doivent modifier AUCUNE de ces
# racines ; seul `.sdd/harness_build.py` peut écrire dans `.claude/`,
# `.codex/`, `.gemini/`.
FRAMEWORK_OWNED: tuple[str, ...] = (
    # .claude/ facade (Claude Code harness — regenerated on demand by
    # rebuild_claude_facade.py, so protection is transient but active).
    # Audit 2026-11 : `.claude/rules/` était listé deux fois — dédoublonné.
    ".claude/rules/",
    ".claude/agents/",
    ".claude/commands/",
    ".claude/CLAUDE.md",
    ".claude/settings.json",
    ".claude/settings.local.json",
    # .sdd/ neutral core (SSoT versionné — foyer neutre édité à la main)
    ".sdd/rules/",
    ".sdd/stacks/",
    ".sdd/agents/",
    ".sdd/templates/",
    ".sdd/commands/",
    ".sdd/skills/",
    ".sdd/python/",
    ".sdd/digests/",
    ".sdd/loader.yml",
    ".sdd/loader.reverse.yml",
    ".sdd/providers/",
    ".sdd/adapters/",
    ".sdd/harness_build.py",
    ".sdd/entrypoint.md",
    ".sdd/capability-matrix.yml",
    ".sdd/rules-manifest.yaml",
    ".sdd/skills-manifest.yaml",
    ".sdd/agent-bounds.yaml",
    ".sdd/config.base.yml",
    ".sdd/INVARIANTS.yml",
    ".sdd/INVARIANTS.reverse.yml",
    # .codex/ facade (Codex harness — generated post-Phase 2)
    ".codex/AGENTS.md",
    ".codex/prompts/",
    ".codex/config.toml",
    # .gemini/ facade (Gemini/Antigravity harness — generated post-Phase 2)
    ".gemini/GEMINI.md",
    ".gemini/commands/",
    ".gemini/settings.json",
    # db-reverse fact layer (workspace/old/{P}/.sys/) — written ONLY by
    # db_context_build.py --merge-hypotheses, never directly by an agent.
    # Blocks reverse-db-architect (or any other agent) from writing the
    # facts branch directly, bypassing merge_architect_output's 5-key
    # whitelist. db-context.hypotheses.json is deliberately ABSENT here —
    # that file is the architect's own, legitimate output.
    "workspace/old/*/.sys/db-context.json",
    "workspace/old/*/.sys/db-context.digest.json",
    "workspace/old/*/.sys/db-schema.json",
    "workspace/old/*/.sys/db-introspection.json",
)

#: Artefacts de gate (audit 2026-11) : verdicts lus par les hooks
#: bloquants (`validate_acceptance_gate`, `enforce_two_stage_auditor`),
#: journaux d'audit et état de run. Produits par des scripts Python ; un
#: agent qui les écrit via le tool Write peut forger un verdict. Exceptions
#: dérivées de `loader.yml` (`writes:` de l'agent appelant) — cf.
#: `_loader_allows`.
GATE_ARTIFACT_DIRS: tuple[str, ...] = (
    "workspace/.sys/.validation/",
    "workspace/.sys/.acceptance/",
    "workspace/.sys/.audit/",
    "workspace/.sys/.state/",
)

#: Préfixes de chemin (normalisés `/`, relatifs à la racine) qui, dans une
#: commande shell, désignent un périmètre protégé.
_SHELL_PROTECTED_PREFIXES: tuple[str, ...] = (
    ".sdd/", ".claude/", ".codex/", ".gemini/", *GATE_ARTIFACT_DIRS,
)
_SHELL_PROTECTED_EXACT: tuple[str, ...] = (
    ".sdd", ".claude", ".codex", ".gemini", "workspace/.sys",
    *(d.rstrip("/") for d in GATE_ARTIFACT_DIRS),
)


def _rel_to_repo(file_path: str, repo: Path) -> str | None:
    """Canonical repo-relative path (forward slashes) or None if outside."""
    try:
        p = Path(file_path)
        if not p.is_absolute():
            p = repo / p
        rel = p.resolve().relative_to(repo.resolve())
    except (ValueError, OSError):
        return None
    return normalize(str(rel))


def _matches_owned(rel_str: str) -> bool:
    # Strict prefix match : "foo/.claude/rules/" must NOT match "rules/" pattern
    for owned in FRAMEWORK_OWNED:
        if "*" in owned:
            # Per-project glob (e.g. "workspace/old/*/.sys/db-context.json") —
            # exact fnmatch, no prefix semantics.
            if fnmatch(rel_str, owned):
                return True
        elif owned.endswith("/"):
            if rel_str.startswith(owned):
                return True
        else:
            if rel_str == owned:
                return True
    return False


def _is_framework_path(file_path: str, repo: Path) -> bool:
    """Strict check : file_path resolves to a path inside one of FRAMEWORK_OWNED
    prefixes, RELATIVE to repo root. Defense against substring false-positives
    (workspace/src/X/.claude/... no longer matches) and path-traversal
    false-negatives (..\\..\\.claude\\... after resolve() lives outside repo
    and is filtered out).

    CRITICAL fix (2026-06-07) : relative `file_path` MUST be resolved against
    `repo`, NOT against `Path.cwd()`. The previous implementation used
    `Path(file_path).resolve()` which silently anchors to CWD — if pytest /
    background agent / a `cd .claude/python` shell invoked the hook, a user
    edit on `workspace/src/MyApp/x.tsx` would resolve to
    `<repo>/.claude/python/workspace/src/MyApp/x.tsx`, whose
    `relative_to(repo)` starts with `.claude/python/` → false positive +
    [FRAMEWORK_PROTECTED] in strict mode → CI blocks ALL user edits.
    Reproduced by tests `test_user_file_*_in_strict` / `..._passes_silently`.
    """
    rel = _rel_to_repo(file_path, repo)
    return bool(rel) and _matches_owned(rel)


def _is_gate_artifact(file_path: str, repo: Path) -> str | None:
    """Return the repo-relative path if it lives under a GATE_ARTIFACT_DIRS."""
    rel = _rel_to_repo(file_path, repo)
    if rel and any(rel.startswith(d) for d in GATE_ARTIFACT_DIRS):
        return rel
    return None


def _placeholder_to_glob(pattern: str) -> str:
    """`workspace/.sys/.validation/{n}-api-tests.json` → fnmatch glob."""
    return re.sub(r"\{[^}]*\}", "*", normalize(pattern).strip())


def _loader_allows(agent: str | None, rel: str, repo: Path) -> bool:
    """True if `loader.yml` lists `rel` (or a matching placeholder glob) in
    the `writes:` section of `agent`. Unknown agent → False (fail-closed)."""
    if not agent:
        return False
    try:
        from sdd_lib.loader_yml import parse_agent_section
        writes = parse_agent_section(agent, "writes", root=repo)
    except Exception:
        return False
    for raw in writes:
        glob = _placeholder_to_glob(raw)
        if not glob:
            continue
        if glob.endswith("/"):
            if rel.startswith(glob):
                return True
        elif fnmatch(rel, glob):
            return True
    return False


def _resolve_mode(payload: dict | None = None) -> str:
    """Precedence : env override > CI auto-detect > sous-agent (strict) > 'warn'.

    CI detection delegated to `sdd_lib.ci.is_ci` (SSoT, audit CTO 2026-06-07).
    """
    explicit = (os.environ.get("SDD_PROTECT_FRAMEWORK_MODE") or "").strip().lower()
    if explicit in ("warn", "strict", "off"):
        return explicit
    if is_ci():
        return "strict"
    if SUBAGENT_STRICT_DEFAULT and payload is not None and is_subagent_call(payload):
        return "strict"
    return "warn"


# --------------------------------------------------------------------------- #
# Mode shell (Bash | PowerShell)
# --------------------------------------------------------------------------- #

#: Commandes qui écrivent / détruisent (sans leurs options). PowerShell en
#: casse insensible (comparaison en lower()).
_WRITE_CMDS: frozenset[str] = frozenset({
    "tee", "cp", "mv", "rm", "rmdir", "mkdir", "touch", "truncate", "ln",
    "install", "rsync", "dd", "chmod", "chown", "patch", "unzip",
    "copy-item", "move-item", "remove-item", "rename-item", "new-item",
    "set-content", "add-content", "out-file", "clear-content", "copy", "move",
    "del", "erase", "rd", "ren", "xcopy", "robocopy", "cpi", "mi", "ri", "ni",
    "sc", "ac", "rni",
})
#: Commandes qui n'écrivent qu'avec un flag in-place.
_INPLACE_CMDS: dict[str, re.Pattern[str]] = {
    "sed": re.compile(r"(?:^|\s)-[a-zA-Z]*i"),
    "perl": re.compile(r"(?:^|\s)-[a-zA-Z]*i"),
}
#: Interpréteurs inline : écriture si un marqueur d'écriture Python/JS/PS
#: apparaît dans le même segment.
_INLINE_INTERPRETERS: frozenset[str] = frozenset({
    "python", "python3", "py", "node", "pwsh", "powershell",
})
#: Flag qui fait de l'interpréteur un exécuteur de code inline (`python -c`,
#: `node -e`, `pwsh -Command`). Sans ce flag, `python .sdd/python/x.py` est
#: l'exécution légitime d'un script framework, jamais flaggée.
_INLINE_PATH_RE = re.compile(
    r"(?:^|[\s'\"(=,])(?:\./)?((?:\.sdd|\.claude|\.codex|\.gemini|workspace/\.sys)/[^\s'\"),]*)"
)
_INLINE_FLAG_RE = re.compile(r"(?:^|\s)-(?:c|e|Command|command|EncodedCommand|ec)(?:\s|$)")
_INLINE_WRITE_MARKER = re.compile(
    r"open\s*\([^)]*['\"][wax]\+?b?['\"]|write_text|write_bytes|unlink|rmtree|"
    r"os\.remove|os\.rename|os\.replace|shutil\.|makedirs|mkdir|writeFile|"
    r"rmSync|unlinkSync|Set-Content|Out-File|Remove-Item|WriteAllText|"
    r"WriteAllBytes|\[IO\.File\]::Write",
    re.IGNORECASE,
)
#: Sous-commandes git qui réécrivent l'arbre de travail.
_GIT_TREE_CMDS: frozenset[str] = frozenset({
    "checkout", "restore", "clean", "rm", "mv", "reset", "stash", "revert",
})
_TOKEN_RE = re.compile(r"""("[^"]*"|'[^']*'|\S+)""")
_REDIRECT_RE = re.compile(r"(?<![0-9])(?:>>?|>\|)\s*")


def _norm_token(tok: str) -> str:
    return tok.strip("\"'`").replace("\\", "/")


def _is_protected_token(tok: str, repo: Path) -> bool:
    t = _norm_token(tok)
    if not t:
        return False
    if t.startswith("./"):
        t = t[2:]
    if t in _SHELL_PROTECTED_EXACT or t.startswith(_SHELL_PROTECTED_PREFIXES):
        return True
    # Variante `-Path .sdd/x`, `--out=.sdd/x` (option=valeur).
    if "=" in t:
        _, _, val = t.partition("=")
        val = val.lstrip("./")
        if val in _SHELL_PROTECTED_EXACT or val.startswith(_SHELL_PROTECTED_PREFIXES):
            return True
    # Chemin absolu sous le dépôt.
    if re.match(r"^(?:[A-Za-z]:)?/", t):
        rel = _rel_to_repo(t, repo)
        if rel and (rel in _SHELL_PROTECTED_EXACT or rel.startswith(_SHELL_PROTECTED_PREFIXES)):
            return True
    return False


def _split_segments(cmd: str) -> list[str]:
    """Split on `&&`, `||`, `|`, `;`, newline — OUTSIDE quotes only.

    `python -c "import x; x.write()"` must stay one segment (the `;` is
    Python, not shell).
    """
    out: list[str] = []
    buf: list[str] = []
    quote = ""
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in ";\n|&":
            # `&` seul = séparateur (bash background / PS call operator),
            # sauf dans une redirection `2>&1` / `&>`.
            if ch == "&" and not cmd.startswith("&&", i) and (
                    (i > 0 and cmd[i - 1] == ">") or cmd.startswith("&>", i)):
                buf.append(ch)
                i += 1
                continue
            out.append("".join(buf))
            buf = []
            i += 2 if cmd.startswith(("&&", "||"), i) else 1
            continue
        buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [seg.strip() for seg in out if seg.strip()]


def check_shell_command(cmd: str, repo: Path | None = None) -> list[str]:
    """Return human-readable reasons for every protected-path write detected.

    Empty list = nothing suspicious. Heuristic (see module docstring).
    """
    if not cmd or not cmd.strip():
        return []
    repo = repo or repo_root()
    reasons: list[str] = []
    for segment in _split_segments(cmd):
        if not segment.strip():
            continue
        # (a) redirection `>`/`>>` vers un chemin protégé
        for m in _REDIRECT_RE.finditer(segment):
            rest = segment[m.end():]
            tm = _TOKEN_RE.match(rest)
            if tm and _is_protected_token(tm.group(1), repo):
                reasons.append(f"redirection `{m.group(0).strip()}` vers {_norm_token(tm.group(1))}")
        tokens = [t for t in _TOKEN_RE.findall(segment)]
        if not tokens:
            continue
        protected = [_norm_token(t) for t in tokens if _is_protected_token(t, repo)]
        words = [_norm_token(t).lower() for t in tokens]
        head0 = words[0].rsplit("/", 1)[-1].removesuffix(".exe")
        if (head0 in _INLINE_INTERPRETERS and _INLINE_FLAG_RE.search(segment)
                and _INLINE_WRITE_MARKER.search(segment)):
            # Code inline : le chemin est À L'INTÉRIEUR d'une chaîne
            # (`open('.sdd/x','w')`), pas un token — recherche par sous-chaîne.
            inner = _INLINE_PATH_RE.findall(segment.replace("\\", "/"))
            if inner or protected:
                reasons.append(f"`{head0}` inline avec écriture sur "
                               f"{', '.join(sorted(set(inner + protected)))}")
                continue
        if not protected:
            continue
        # Ignore un éventuel préfixe `sudo` / chemin d'exécutable.
        head = words[0].rsplit("/", 1)[-1]
        head = head.removesuffix(".exe")
        if head == "sudo" and len(words) > 1:
            head = words[1].rsplit("/", 1)[-1]
        # (b) commande d'écriture + chemin protégé dans le même segment
        if head in _WRITE_CMDS:
            reasons.append(f"`{head}` sur {', '.join(protected)}")
            continue
        if head in _INPLACE_CMDS and _INPLACE_CMDS[head].search(segment):
            reasons.append(f"`{head} -i` sur {', '.join(protected)}")
            continue
        # (c) git checkout -- / restore / clean … sur .sdd / .claude
        if head == "git":
            sub = next((w for w in words[1:] if not w.startswith("-")), "")
            if sub in _GIT_TREE_CMDS:
                reasons.append(f"`git {sub}` sur {', '.join(protected)}")
                continue
        # (e) pipeline PowerShell `... | Out-File path` est déjà couvert par le
        #     split sur `|` (le segment aval commence par Out-File).
    return reasons


def _main_shell(payload: dict, mode: str) -> int:
    cmd = get_nested(payload, "tool_input", "command")
    if not isinstance(cmd, str) or not cmd.strip():
        return HOOK_ALLOW
    reasons = check_shell_command(cmd, repo_root())
    if not reasons:
        return HOOK_ALLOW
    detail = " ; ".join(reasons[:4])
    if mode == "strict":
        warn("ERROR: protect-framework — commande shell qui écrit sur un chemin protégé")
        warn(f"CAUSE: [FRAMEWORK_PROTECTED] {detail}")
        warn("FIX: les fichiers framework (.sdd/, .claude/, .codex/, .gemini/) et les "
             "artefacts de gate (workspace/.sys/{.validation,.acceptance,.audit,.state}/) "
             "ne se modifient pas depuis un agent ; Tech Lead : SDD_PROTECT_FRAMEWORK_MODE=warn "
             "dans l'environnement du process Claude Code (jamais inline)")
        return HOOK_DENY
    warn(f"WARNING: protect-framework — commande shell écrivant sur un chemin protégé : {detail}")
    warn("         Maintenance framework autorisee deliberement (Tech Lead, mode warn).")
    return HOOK_ALLOW


# --------------------------------------------------------------------------- #
# Mode fichier (Edit | Write | MultiEdit | NotebookEdit)
# --------------------------------------------------------------------------- #

def _main_file(payload: dict, mode: str) -> int:
    file_path = get_file_path(payload)
    if not file_path:
        return HOOK_ALLOW
    repo = repo_root()
    # P1-5 fix 2026-06-07 : canonicalized check via repo_root + relative_to
    # (was substring match — could false-positive/negative).
    if _is_framework_path(file_path, repo):
        return _decide_framework(file_path, mode)
    gate_rel = _is_gate_artifact(file_path, repo)
    if gate_rel is not None:
        return _decide_gate_artifact(file_path, gate_rel, payload, mode, repo)
    return HOOK_ALLOW


def _decide_framework(file_path: str, mode: str) -> int:
    norm = normalize(file_path)
    if mode == "strict":
        warn(f"ERROR: protect-framework — '{file_path}' est propriete framework SDD_Pro")
        warn("CAUSE: [FRAMEWORK_PROTECTED] tentative d'edit en mode strict (CI, sous-agent ou explicite)")
        warn("FIX: (a) si edit legitime Tech Lead : SDD_PROTECT_FRAMEWORK_MODE=warn dans "
             "l'environnement du process Claude Code (jamais inline — bloque par block_env_bypass)")
        warn("     (b) si agent produit modifie le framework : c'est un BUG, ne pas bypass")
        return HOOK_DENY

    # warn mode (default interactive)
    warn(f"WARNING: '{file_path}' est un fichier propriete framework SDD_Pro.")
    warn("         Les agents produit (po, arch, dev-*, qa) ne doivent pas le modifier.")
    warn("         Maintenance framework autorisee deliberement (Tech Lead).")

    if "CLAUDE.md" in norm:
        warn("         Rappel: synchroniser .sdd/docs/CHANGELOG.md et docs/ si changement architectural.")
    if ".sdd/loader" in norm or ".claude/loader" in norm:
        warn("         Rappel: loader.yml doit refleter les reads/writes reels des agents.")
    return HOOK_ALLOW


def _decide_gate_artifact(file_path: str, rel: str, payload: dict, mode: str,
                          repo: Path) -> int:
    agent = get_caller_agent_type(payload)
    if agent and _loader_allows(agent, rel, repo):
        # Sortie déclarée de cet agent dans loader.yml (rapport d'auditeur,
        # api-tests qa, sentinel .state) — légitime, silencieux.
        return HOOK_ALLOW
    if mode == "strict":
        who = f"agent '{agent}'" if agent else "appel"
        warn(f"ERROR: protect-framework — '{file_path}' est un artefact de gate (scripts uniquement)")
        warn(f"CAUSE: [FRAMEWORK_PROTECTED] {who} tente d'ecrire {rel} hors de ses `writes:` loader.yml "
             "— un verdict ecrit a la main est un verdict forgeable")
        warn("FIX: produire l'artefact via le script deterministe qui le possede "
             "(validate_acceptance.py, ingest_agent_report.py, sdd_state.py…) ; "
             "si cet agent doit legitimement l'ecrire, le declarer dans loader.yml `writes:`")
        return HOOK_DENY
    warn(f"WARNING: '{file_path}' est un artefact de gate SDD_Pro ({rel}) — normalement produit "
         "par un script deterministe, pas ecrit a la main.")
    return HOOK_ALLOW


def _main_inner() -> int:
    mode = _resolve_mode()
    if mode == "off":
        # Audit M8 (2026-08-29) — `SDD_PROTECT_FRAMEWORK_MODE=off` is
        # documented as an audit-logged bypass, but the pre-fix code returned
        # HOOK_ALLOW in total silence: the framework-write protection could be
        # disabled for an entire session with no trace anywhere. Emit the same
        # kind of stderr audit line the strict branch below already uses.
        # Kept cheap and payload-free — this fires before reading hook input.
        warn("[protect-framework] BYPASS via SDD_PROTECT_FRAMEWORK_MODE=off — "
             "la protection d'écriture sur .sdd/** .claude/** et les artefacts de gate est DÉSACTIVÉE")
        return HOOK_ALLOW
    payload = read_hook_input()
    mode = _resolve_mode(payload)
    tool = (get_tool_name(payload) or "").lower()
    if tool in ("bash", "powershell"):
        return _main_shell(payload, mode)
    return _main_file(payload, mode)


def main() -> int:
    """Outer wrapper — fail-CLOSED (audit 2026-11).

    Avant : fail-OPEN en interactif (une exception interne = ALLOW + WARN),
    fail-CLOSED en CI seulement. Un hook de protection qui plante ne peut
    pas être un laissez-passer : DENY partout, avec le bypass explicite et
    audit-loggable `SDD_PROTECT_FRAMEWORK_FAIL_OPEN=1` (INVARIANTS.yml) pour
    le debug du hook lui-même. `_hook.py` applique la même politique à tout
    hook bloquant qui laisserait échapper une exception.
    """
    try:
        return _main_inner()
    except Exception as e:  # noqa: BLE001
        warn(f"ERROR: protect-framework — exception interne ({type(e).__name__}: {e})")
        if os.environ.get("SDD_PROTECT_FRAMEWORK_FAIL_OPEN", "").strip().lower() in ("1", "true", "yes"):
            warn("     CAUSE: [HOOK_CRASH] bypass SDD_PROTECT_FRAMEWORK_FAIL_OPEN=1 actif — ALLOW (audit-loggué)")
            return HOOK_ALLOW
        warn("CAUSE: [HOOK_CRASH] hook internal exception — possible bypass probe, refus de l'ecriture")
        warn("FIX: investiguer stderr ; debug du hook uniquement : SDD_PROTECT_FRAMEWORK_FAIL_OPEN=1 "
             "dans l'environnement du process Claude Code")
        return HOOK_DENY


if __name__ == "__main__":
    sys.exit(main())
