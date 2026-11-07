#!/usr/bin/env python3
"""SDD_Pro PreToolUse hook (matcher=`Read|Grep|Glob|Bash|PowerShell`) — accès aux secrets.

Audit sécurité 2026-11. Empêche un SOUS-AGENT de lire (et donc de faire
entrer dans son contexte, son transcript et la télémétrie du provider) un
fichier porteur de secrets.

Politique :

  | Appelant                         | Cible "toujours sensible" | Config générée avec secret réel |
  |----------------------------------|---------------------------|---------------------------------|
  | sous-agent (`agent_id` présent)  | DENY exit 2               | DENY exit 2                     |
  | session principale (Tech Lead)   | WARN exit 0               | WARN exit 0                     |

  * **Toujours sensible** : `.env`, `.env.*` (sauf `.env.example`,
    `.env.sample`, `.env.template`), tout chemin sous un dossier `secrets/`,
    `*.pem`, `*.pfx`, `*.p12`, `id_rsa*`, `workspace/.sys/.secrets/**`.
  * **Config générée** (sous `workspace/src/`) : `appsettings*.json`,
    `application*.yml|yaml|properties`, `config/default.json`. Le refus est
    *conditionné au contenu* : DENY seulement si le fichier contient une
    valeur réelle (ni vide, ni `${VAR}`) sur une clé
    Password/Secret/Token/ApiKey/ConnectionString, ou un `Password=` /
    `Pwd=` en clair dans une chaîne de connexion. Choix délibéré : `arch`
    doit pouvoir Read puis Edit ces fichiers pour y propager des
    placeholders (l'outil Edit exige un Read préalable) — un refus
    inconditionnel casserait le pipeline sans gain quand le fichier ne
    contient que des `${VAR}`.

Détection par tool :
  * Read : `tool_input.file_path`.
  * Grep : `tool_input.path` (fichier) et `tool_input.glob`.
  * Glob : `tool_input.pattern` (+ `path`) — un glob qui vise nommément ces
    fichiers.
  * Bash / PowerShell : tout token de la commande qui désigne un tel
    fichier (`cat`, `type`, `Get-Content`, `less`, `head`, `grep`, `cp`,
    `source`, `< .env`, `python -c open(…)`, `[IO.File]::ReadAllText(…)`…),
    les globs passés à une commande de lecture (`cat .en*`, `type .e?v`) et
    le code des heredocs d'interpréteur (`python - <<EOF open('.env') EOF`).
    Le corps d'un heredoc de DONNÉES (`cat > f <<EOF`) n'est pas analysé
    (découpage partagé `sdd_lib.shell_write_targets.split_segments`).
    Heuristique : un `grep -r Password workspace/src` (répertoire entier)
    n'est PAS détecté, pas plus qu'un chemin construit dynamiquement.

Classe : `[SECRET_ACCESS_FORBIDDEN]`. Bypass : `SDD_ALLOW_SECRET_ACCESS=1`
dans l'environnement du process Claude Code (protégé par
`block_env_bypass`, jamais inline).

Ce module expose aussi les helpers de détection partagés par
`preflight_secret_scan` et `pre_write_lint` (`find_secret_values`,
`file_secret_findings`, `classify_secret_path`, `generated_config_files`).
"""
from __future__ import annotations

import os
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402
from sdd_lib.hook_input import (  # noqa: E402
    get_nested,
    get_tool_name,
    is_subagent_call,
    read_hook_input,
)
from sdd_lib.stderr import warn  # noqa: E402

# --------------------------------------------------------------------------- #
# Détection de valeurs secrètes (helpers partagés)
# --------------------------------------------------------------------------- #

#: Une clé est "secrète" si son nom SE TERMINE par l'un de ces suffixes
#: (insensible à la casse). `PasswordInput` (sélecteur CSS) n'en est pas une ;
#: `DB_PASSWORD`, `ClientSecret`, `AccessToken`, `ApiKey` en sont.
_SECRET_KEY_SUFFIX = r"(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|connectionstring|clientsecretvalue|private[_-]?key)"
_SECRET_KEY_RE = re.compile(r"^[\w.\-]*" + _SECRET_KEY_SUFFIX + r"$", re.IGNORECASE)

#: JSON : "Key": "value"
_JSON_PAIR_RE = re.compile(r'"(?P<key>[\w.\-]+)"\s*:\s*"(?P<val>(?:[^"\\]|\\.)*)"')
#: YAML / stack.md / .env : [- ]KEY: value | KEY=value (une ligne)
_LINE_PAIR_RE = re.compile(
    r"^[^\S\n]*(?:-[^\S\n]+)?(?:export[^\S\n]+)?(?P<key>[A-Za-z_][\w.\-]*)[^\S\n]*[:=][^\S\n]*(?P<val>[^\n]*?)[^\S\n]*$",
    re.MULTILINE,
)
#: Mot de passe en clair dans une chaîne de connexion (ADO.NET / ODBC / JDBC).
_CONNSTR_PWD_RE = re.compile(r"(?:^|[;\s\"'])(?:password|pwd)\s*=\s*(?P<val>[^;\"'$\s][^;\"']{2,})", re.IGNORECASE)
#: Mot de passe dans une URI : scheme://user:PASS@host
_URI_PWD_RE = re.compile(r"[a-z][a-z0-9+.\-]*://[^:/\s@\"']+:(?P<val>[^@\s\"'$]{3,})@", re.IGNORECASE)

_PLACEHOLDER_FULL_RE = re.compile(r"^\$\{\w+\}$|^\$\w+$|^%\w+%$|^\{\{.*\}\}$|^<[^>]*>$")
_PLACEHOLDER_WORDS = frozenset({
    "", "todo", "changeme", "change_me", "replace_me", "replaceme", "xxx", "***",
    "null", "none", "~", "false", "true", "secret", "password", "your-password",
    "your_password", "<password>",
})


def is_placeholder(value: str) -> bool:
    """True si `value` n'est pas un secret réel (vide, `${VAR}`, TODO…)."""
    v = (value or "").strip().strip("\"'").strip()
    if v.lower() in _PLACEHOLDER_WORDS:
        return True
    if _PLACEHOLDER_FULL_RE.match(v):
        return True
    # Valeur entièrement composée de placeholders `${A}${B}` / `${A}:${B}`.
    if "${" in v and not re.sub(r"\$\{\w+\}", "", v).strip(" :;/@-_."):
        return True
    return False


_STRICT_KEY_RE = re.compile(r"(?:password|passwd|pwd)$", re.IGNORECASE)
_ENV_STYLE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SYMBOLS = set("_-+/=.!@#$%^&*~:")


def _is_real_secret(key: str, value: str) -> bool:
    """Décide si `value` est un secret réel pour la clé `key`.

    * clés `*Password|*Pwd` et clés d'env en MAJUSCULES (`DB_PASSWORD`,
      `AUTH_JWT_SECRET`, stack.md / .env) : toute valeur non-placeholder ;
    * autres clés `*Token|*Secret|*ApiKey` (camelCase JSON/YAML) : seuil
      d'entropie — ≥ 16 caractères, ou ≥ 8 avec lettre + chiffre + symbole.
      Évite les faux positifs du type `"SemainePaireToken": "semainePaire"`
      (jeton de formulaire, pas un secret — cas réel PolEmploiAuto).
    """
    v = (value or "").strip().strip("\"'").strip()
    if is_placeholder(v):
        return False
    if _STRICT_KEY_RE.search(key) or _ENV_STYLE_KEY_RE.match(key):
        return True
    if len(v) >= 16 and " " not in v:
        return True
    return (len(v) >= 8 and any(c.isdigit() for c in v) and any(c.isalpha() for c in v)
            and any(c in _SYMBOLS for c in v))


def _redact(val: str) -> str:
    v = val.strip()
    return (v[:2] + "***") if len(v) > 2 else "***"


def find_secret_values(text: str) -> list[tuple[str, str, int]]:
    """Return `(key, redacted_value, line_no)` for every REAL secret in `text`.

    Couvre JSON (`"Password": "x"`), YAML/stack.md/.env (`KEY: x`, `KEY=x`),
    chaînes de connexion (`Password=x;`) et URIs (`proto://u:x@h`). Les
    placeholders `${VAR}` ne sont jamais signalés (faux positif historique
    `${DB_PASSWORD}`, audit 2026-11).
    """
    if not text:
        return []
    found: list[tuple[str, str, int]] = []
    seen: set[tuple[str, int]] = set()

    def _add(key: str, val: str, pos: int) -> None:
        line = text.count("\n", 0, pos) + 1
        if (key.lower(), line) in seen:
            return
        seen.add((key.lower(), line))
        found.append((key, _redact(val), line))

    for m in _JSON_PAIR_RE.finditer(text):
        key, val = m.group("key"), m.group("val")
        if _SECRET_KEY_RE.match(key) and not key.lower().endswith("connectionstring"):
            if _is_real_secret(key, val):
                _add(key, val, m.start())
    for m in _LINE_PAIR_RE.finditer(text):
        key, val = m.group("key"), m.group("val")
        if val.startswith(("{", "[")) or val.endswith((",", "{")):
            continue  # objet/tableau YAML ou ligne JSON (traitée plus haut)
        if _SECRET_KEY_RE.match(key) and not key.lower().endswith("connectionstring"):
            clean = re.sub(r"\s+#.*$", "", val)
            if _is_real_secret(key, clean):
                _add(key, clean, m.start())
    for m in _CONNSTR_PWD_RE.finditer(text):
        if not is_placeholder(m.group("val")):
            _add("Password", m.group("val"), m.start())
    for m in _URI_PWD_RE.finditer(text):
        if not is_placeholder(m.group("val")):
            _add("uri-password", m.group("val"), m.start())
    return found


def file_secret_findings(path: Path) -> list[tuple[str, str, int]]:
    """`find_secret_values` sur un fichier ; [] si illisible ou trop gros."""
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return []
        return find_secret_values(path.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return []


# --------------------------------------------------------------------------- #
# Classification des chemins
# --------------------------------------------------------------------------- #

_ENV_ALLOWED = frozenset({".env.example", ".env.sample", ".env.template", ".env.dist"})
_CONFIG_NAME_GLOBS = ("appsettings*.json", "application*.yml", "application*.yaml",
                      "application*.properties")


def _norm(p: str) -> str:
    return p.strip().strip("\"'`").replace("\\", "/")


def classify_secret_path(path: str) -> str | None:
    """'always' | 'config' | None pour un chemin (relatif ou absolu, ou glob).

    'config' n'est retourné que pour un fichier sous `workspace/src/`.
    """
    p = _norm(path)
    if not p:
        return None
    low = p.lower()
    base = low.rsplit("/", 1)[-1]
    if base == ".env" or (base.startswith(".env.") and base not in _ENV_ALLOWED):
        return "always"
    if base.endswith((".pem", ".pfx", ".p12")) or base.startswith("id_rsa"):
        return "always"
    segs = low.split("/")
    if "secrets" in segs[:-1] or ".secrets" in segs[:-1]:
        return "always"
    if "workspace/src/" in low or low.startswith("src/"):
        if any(fnmatch(base, g) for g in _CONFIG_NAME_GLOBS):
            return "config"
        if low.endswith("config/default.json"):
            return "config"
    return None


def generated_config_files(workspace: Path, limit: int = 200) -> list[Path]:
    """Fichiers de config générés sous `workspace/src/` (profondeur bornée)."""
    src = workspace / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    skip = {"node_modules", "bin", "obj", "dist", "build", "target", ".git", ".venv", "venv"}
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip]
        depth = Path(dirpath).relative_to(src).parts
        if len(depth) > 6:
            dirnames[:] = []
        for name in filenames:
            full = Path(dirpath) / name
            if classify_secret_path(str(full)) == "config":
                out.append(full)
                if len(out) >= limit:
                    return out
    return out


# --------------------------------------------------------------------------- #
# Hook
# --------------------------------------------------------------------------- #

_TOKEN_RE = re.compile(r"""("[^"]*"|'[^']*'|[^\s;|&<>()]+)""")


def _resolve(path: str) -> Path:
    from sdd_lib.paths import repo_root
    p = Path(_norm(path))
    return p if p.is_absolute() else repo_root() / p


def _candidate_paths(payload: dict) -> list[str]:
    tool = (get_tool_name(payload) or "").lower()
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    out: list[str] = []
    if tool == "read":
        fp = ti.get("file_path")
        if isinstance(fp, str):
            out.append(fp)
    elif tool == "grep":
        for k in ("path", "glob"):
            v = ti.get(k)
            if isinstance(v, str):
                out.append(v)
    elif tool == "glob":
        pat = ti.get("pattern")
        if isinstance(pat, str):
            base = ti.get("path") if isinstance(ti.get("path"), str) else ""
            out.append(f"{base.rstrip('/')}/{pat}" if base else pat)
    elif tool in ("bash", "powershell"):
        cmd = ti.get("command")
        if isinstance(cmd, str):
            out.extend(_shell_candidate_paths(cmd))
    return out


#: Commandes qui LISENT le contenu de leurs arguments (pour l'expansion de
#: glob : `cat .en*`, `Get-Content .e?v`). Un glob passé à une autre
#: commande (`find -name "*.pem"`, `ls`) n'est pas une lecture de contenu.
_READER_HEADS = frozenset({
    "cat", "tac", "type", "gc", "get-content", "less", "more", "head", "tail", "bat",
    "nl", "strings", "xxd", "od", "hexdump", "base64", "sed", "awk", "grep", "egrep",
    "fgrep", "rg", "findstr", "select-string", "sls", "source", ".", "cp", "copy",
    "copy-item", "cpi", "import-csv", "iconv", "sort", "uniq", "cut", "diff", "cmp",
    "vi", "vim", "nano", "notepad", "code", "openssl", "jq", "yq", "dos2unix",
})
#: Noms représentatifs de fichiers secrets, testés contre les globs.
_SECRET_PROBES = (".env", ".env.local", ".env.production", "id_rsa", "key.pem",
                  "cert.pfx", "cert.p12")
_INNER_SECRET_RE = re.compile(
    r"[\w.\-/:]*?(?:\.env[\w.]*|\.pem|\.pfx|\.p12|id_rsa\w*|"
    r"appsettings[\w.]*\.json|application[\w.\-]*\.(?:ya?ml|properties)|"
    r"config/default\.json|secrets/[\w.\-/]*)")
_INTERP_HEADS = frozenset({"python", "python3", "py", "node", "ruby", "perl", "php",
                           "pwsh", "powershell", "bash", "sh", "zsh", "cmd"})


def _head_word(tok: str) -> str:
    h = _norm(tok).lower().rsplit("/", 1)[-1]
    for suf in (".exe", ".cmd", ".bat"):
        if h.endswith(suf):
            h = h[: -len(suf)]
    return h


def _shell_candidate_paths(cmd: str) -> list[str]:
    """Chemins candidats d'une commande Bash/PowerShell.

    * chaque token de chaque segment (lecture, copie, `source`, redirection
      d'entrée `< .env`…), plus les chemins enfouis dans du code inline
      (`python -c "open('.env')"`, `[IO.File]::ReadAllText('.env')`) ;
    * corps de heredoc / here-string : analysés seulement quand ils sont du
      CODE (interpréteur en tête) — un heredoc de données écrit dans un
      fichier (`cat > notes.md <<EOF … .pem … EOF`) n'est pas une lecture ;
    * globs passés à une commande de lecture (`cat .en*`, `type .e?v`) :
      développés contre des noms de fichiers secrets représentatifs.
    """
    from sdd_lib.shell_write_targets import split_segments
    out: list[str] = []
    for seg in split_segments(cmd):
        text = seg.text
        words = [_norm(t) for t in _TOKEN_RE.findall(text)]
        while words and (re.match(r"^[A-Za-z_]\w*=", words[0])
                         or _head_word(words[0]) in ("sudo", "env", "command", "exec")):
            words = words[1:]
        head = _head_word(words[0]) if words else ""
        code_parts = [text]
        if head in _INTERP_HEADS:
            code_parts += list(seg.heredocs) + list(seg.herestrings.values())
        for part in code_parts:
            for tok in _TOKEN_RE.findall(part):
                t = _norm(tok)
                if "=" in t and not t.startswith(("/", ".")):
                    t = t.split("=", 1)[1]
                # code inline : chemins dans des chaînes Python/PS
                out.extend(_INNER_SECRET_RE.findall(t))
                out.append(t)
        if head in _READER_HEADS:
            for t in words[1:]:
                if t.startswith("-") or not any(ch in t for ch in "*?["):
                    continue
                pat = t.rsplit("/", 1)[-1]
                if pat and pat not in ("*", "*.*") and any(fnmatch(probe, pat) for probe in _SECRET_PROBES):
                    # Le glob lui-même n'est pas classable : on rend le nom
                    # secret qu'il atteindrait (`.en*` → `.env`).
                    out.append(next(pr for pr in _SECRET_PROBES if fnmatch(pr, pat)))
    return out


def _evaluate(payload: dict) -> list[str]:
    """Reasons (one per sensitive target) — empty when nothing sensitive."""
    reasons: list[str] = []
    seen: set[str] = set()
    for raw in _candidate_paths(payload):
        kind = classify_secret_path(raw)
        if kind is None:
            continue
        key = _norm(raw)
        if key in seen:
            continue
        seen.add(key)
        if kind == "always":
            reasons.append(f"{key} (fichier de secrets)")
            continue
        # config générée : décision selon le contenu réel
        if any(ch in key for ch in "*?["):
            from sdd_lib.paths import repo_root, workspace_root
            hits = [f for f in generated_config_files(workspace_root(repo_root()))
                    if fnmatch(_norm(str(f)).lower(), "*" + key.lower().lstrip("*"))
                    and file_secret_findings(f)]
            if hits:
                reasons.append(f"{key} (glob couvrant {len(hits)} config(s) avec secret réel)")
            continue
        findings = file_secret_findings(_resolve(key))
        if findings:
            keys = ", ".join(sorted({k for k, _, _ in findings}))
            reasons.append(f"{key} (contient une valeur réelle sur : {keys})")
    return reasons


def main() -> int:
    payload = read_hook_input()
    if not payload:
        return HOOK_ALLOW
    reasons = _evaluate(payload)
    if not reasons:
        return HOOK_ALLOW
    detail = " ; ".join(reasons[:3])
    bypass = os.environ.get("SDD_ALLOW_SECRET_ACCESS", "").strip().lower() in ("1", "true", "yes")
    if is_subagent_call(payload) and not bypass:
        warn("ERROR: block-secret-access — lecture d'un fichier porteur de secrets par un sous-agent")
        warn(f"CAUSE: [SECRET_ACCESS_FORBIDDEN] {detail}")
        warn("FIX: remplacer les valeurs reelles par des placeholders ${VAR} (resolus a l'execution "
             "depuis l'environnement / .env non lu par les agents) ; Tech Lead : bypass "
             "SDD_ALLOW_SECRET_ACCESS=1 dans l'environnement du process Claude Code")
        return HOOK_DENY
    tag = "bypass SDD_ALLOW_SECRET_ACCESS=1" if bypass else "session principale"
    warn(f"WARN [SECRET_ACCESS_FORBIDDEN] ({tag}) acces a un fichier porteur de secrets : {detail} "
         "— le contenu entrera dans le contexte et le transcript.")
    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
