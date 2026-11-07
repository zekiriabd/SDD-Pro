"""shell_write_targets — chemins écrits / supprimés / déplacés par une commande shell.

Partagé par les hooks PreToolUse `Bash|PowerShell` (`protect_framework`,
`enforce_tdd`, `block_secret_access`) pour fermer le contournement « l'outil
Write est surveillé, mais `cat > X <<EOF` ne l'est pas » (audit 2026-11 :
19 fichiers `.cs` créés sans test via heredoc, écritures sous `.sdd/` via
shell).

Principe
--------

**Extraction conservatrice, décision chez l'appelant.** Ce module ne sait pas
ce qui est protégé : il rend la liste des cibles d'écriture qu'il reconnaît
(`WriteTarget`), chaque hook applique ensuite SA logique de décision
(identique à son mode fichier) sur chaque cible.

Formes reconnues (Bash et PowerShell, casse insensible pour les cmdlets) :

* redirections `>`, `>>`, `>|`, `N>`, `&>`, `*>` (+ heredoc `cat > f <<EOF`) ;
* commandes d'écriture : `tee`, `touch`, `mkdir`, `truncate`, `dd of=`,
  `install`, `rsync`, `ln`, `patch`, `chmod`/`chown` ; destructives : `rm`,
  `rmdir`, `unlink`, `shred`, `del`, `erase`, `rd` ; déplacement : `mv`,
  `move`, `ren` ; copie (destination seule) : `cp`, `copy`, `xcopy`,
  `robocopy` ;
* cmdlets : `Set-Content`, `Add-Content`, `Out-File`, `Clear-Content`,
  `New-Item`, `Copy-Item`, `Move-Item`, `Rename-Item`, `Remove-Item`,
  `Tee-Object`, `Export-Csv`, `Export-Clixml`, `Expand-Archive`,
  `Invoke-WebRequest -OutFile` (+ alias `sc ac ni cpi mi rni ri iwr irm`) ;
* édition en place : `sed -i`, `perl -i` ; `find … -delete|-exec rm` ;
* `git checkout|restore|clean|rm|mv|reset|stash|revert|apply` sur des chemins ;
* téléchargement / archive : `curl -o`, `wget -O|-P`, `tar -C`, `unzip -d` ;
* code inline : `python|node|ruby|perl -c|-e`, `pwsh|powershell -Command`,
  heredoc vers un interpréteur (`python - <<EOF`), appels .NET
  `[IO.File]::WriteAllText(…)` : si un marqueur d'écriture (`open(…,'w')`,
  `write_text`, `shutil.`, `writeFileSync`, `WriteAllText`…) figure dans le
  code, **chaque littéral chaîne qui ressemble à un chemin** est rendu comme
  cible (fail-closed : l'appelant ne bloque que si un chemin protégé y figure
  littéralement — un `open('x.json')` en lecture à côté ne pèse pas) ;
* `bash|sh -c "…"`, `pwsh -Command "…"`, `cmd /c "…"`, `eval`,
  `Invoke-Expression` : la chaîne interne est analysée récursivement ;
* `cd|pushd|Set-Location|sl|chdir X` : le répertoire courant effectif est
  suivi segment après segment (`cd .sdd/rules && echo x > f.md`).

Hors périmètre (heuristique assumée, pas une sandbox) : chemins construits
dynamiquement (`D=.sdd; rm $D/x`, `Path('a') / 'b'`), substitution de
commande `$(…)`, script intermédiaire (`python tools/gen.py` qui écrit), alias
utilisateur. Les commandes de lecture/build (`cat`, `grep`, `git status`,
`pytest`, `dotnet build`) ne produisent AUCUNE cible : rien n'est
reconnu sans commande d'écriture, redirection ou marqueur d'écriture.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "WriteTarget",
    "extract_write_targets",
    "iter_segments",
    "resolve_target",
    "split_segments",
    "tokenize",
]

#: Profondeur max de récursion `bash -c "bash -c '…'"`.
_MAX_DEPTH = 4


@dataclass(frozen=True)
class WriteTarget:
    """Une cible d'écriture extraite d'une commande shell.

    * `path` : chemin tel qu'écrit (guillemets retirés, `\\` → `/`).
    * `op` : `redirect` | `write` | `delete` | `move` | `copy` | `inplace` |
      `git` | `download` | `archive` | `inline`.
    * `command` : mot de tête (pour les messages), ex. `tee`, `set-content`.
    * `cwd` : répertoire effectif issu des `cd` précédents dans la même
      commande (`None` = inchangé ; `"?"` = inconnu, ex. `cd $VAR`).
    * `content` : contenu écrit quand il est connu (heredoc, `echo`,
      `Set-Content -Value`), sinon `None`.
    * `sources` : chemins sources d'une copie / d'un déplacement.
    """

    path: str
    op: str
    command: str
    cwd: str | None = None
    content: str | None = None
    sources: tuple[str, ...] = ()

    def describe(self) -> str:
        if self.op == "redirect":
            return f"redirection `>` vers {self.path}"
        if self.op == "inline":
            return f"`{self.command}` inline avec écriture sur {self.path}"
        if self.op == "inplace":
            return f"`{self.command} -i` sur {self.path}"
        if self.op == "git":
            return f"`git {self.command}` sur {self.path}"
        return f"`{self.command}` sur {self.path}"


# --------------------------------------------------------------------------- #
# Découpage en segments (hors guillemets) + heredocs / here-strings
# --------------------------------------------------------------------------- #

@dataclass
class Segment:
    text: str
    #: Corps des heredocs (`<<EOF`) attachés à ce segment, dans l'ordre.
    heredocs: list[str] = field(default_factory=list)
    #: Here-strings PowerShell remplacés dans `text` par `__SDDHS{i}__`.
    herestrings: dict[str, str] = field(default_factory=dict)
    #: Séparateur qui PRÉCÈDE ce segment (`|` = pipeline).
    sep: str = ""


_HEREDOC_RE = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][\w.\-]*)\2")


def split_segments(cmd: str) -> list[Segment]:
    """Découpe sur `;`, `&&`, `||`, `|`, `&`, saut de ligne — HORS guillemets.

    `python -c "import x; x.write()"` reste un segment (le `;` est Python).
    Les corps de heredoc (`<<EOF … EOF`) et de here-string PowerShell
    (`@' … '@`) sont retirés du flot et attachés au segment qui les ouvre :
    leur contenu est de la DONNÉE, jamais une commande.
    """
    out: list[Segment] = []
    cur = Segment("")
    buf: list[str] = []
    pending: list[tuple[str, bool]] = []  # (délimiteur, strip tabs)
    quote = ""
    i, n = 0, len(cmd)
    hs_count = 0

    def _flush(sep_next: str) -> None:
        nonlocal cur, buf
        cur.text = "".join(buf).strip()
        if cur.text or cur.heredocs:
            out.append(cur)
        cur = Segment("", sep=sep_next)
        buf = []

    while i < n:
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == quote and not (quote == '"' and i > 0 and cmd[i - 1] == "\\"):
                quote = ""
            i += 1
            continue
        # Here-string PowerShell @' … '@ / @" … "@ (délimiteur de fin en début de ligne)
        if ch == "@" and i + 1 < n and cmd[i + 1] in "'\"":
            q = cmd[i + 1]
            j = i + 2
            while j < n and cmd[j] in " \t":
                j += 1
            if j < n and cmd[j] in "\r\n":
                end = re.compile(r"\r?\n[ \t]*" + re.escape(q) + "@").search(cmd, j)
                body_start = j + (2 if cmd.startswith("\r\n", j) else 1)
                if end:
                    body = cmd[body_start:end.start()]
                    i = end.end()
                else:
                    body = cmd[body_start:]
                    i = n
                key = f"__SDDHS{hs_count}__"
                hs_count += 1
                cur.herestrings[key] = body
                buf.append(key)
                continue
        if ch in "\\`" and i + 1 < n and cmd[i + 1] in "\r\n":
            # Continuation de ligne bash (antislash) / PowerShell (backtick).
            i += 3 if cmd.startswith("\r\n", i + 1) else 2
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "#" and (i == 0 or cmd[i - 1] in " \t\n;"):
            # Commentaire jusqu'à la fin de ligne.
            j = cmd.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            m = _HEREDOC_RE.match(cmd, i)
            if m:
                pending.append((m.group(3), m.group(1) == "-"))
                buf.append(m.group(0))
                i = m.end()
                continue
        if ch == "\n" and pending:
            # Consomme les corps de heredoc, dans l'ordre d'ouverture.
            pos = i + 1
            for delim, _strip in pending:
                lines: list[str] = []
                while pos < n:
                    j = cmd.find("\n", pos)
                    line = cmd[pos:] if j < 0 else cmd[pos:j]
                    pos = n if j < 0 else j + 1
                    if line.strip() == delim:
                        break
                    lines.append(line.rstrip("\r"))
                cur.heredocs.append("\n".join(lines))
            pending = []
            i = pos
            _flush(";")
            continue
        if ch in ";\n|&":
            if ch == "&" and not cmd.startswith("&&", i) and (
                    (i > 0 and cmd[i - 1] in "><") or cmd.startswith("&>", i)):
                buf.append(ch)
                i += 1
                continue
            if ch == "|" and i > 0 and cmd[i - 1] == ">":
                buf.append(ch)  # `>|` (noclobber override)
                i += 1
                continue
            two = cmd.startswith(("&&", "||"), i)
            sep = "|" if (ch == "|" and not two) else ";"
            _flush(sep)
            i += 2 if two else 1
            continue
        buf.append(ch)
        i += 1
    _flush("")
    return out


def iter_segments(cmd: str) -> list[str]:
    """Textes des segments (compat : ancienne API `_split_segments`)."""
    return [s.text for s in split_segments(cmd) if s.text]


# --------------------------------------------------------------------------- #
# Tokenisation d'un segment
# --------------------------------------------------------------------------- #

_REDIR_OPS = (">>", ">|", ">")


def tokenize(segment: str) -> list[str]:
    """Tokens d'un segment, guillemets retirés ; les redirections sont des
    tokens à part (`>`, `>>`, `<`), préfixe de fd absorbé (`2>`, `&>`, `*>`).

    """
    toks: list[str] = []
    buf: list[str] = []
    has = False
    quote = ""
    i, n = 0, len(segment)

    def _emit() -> None:
        nonlocal buf, has
        if has:
            toks.append("".join(buf))
        buf, has = [], False

    while i < n:
        ch = segment[i]
        if quote:
            if ch == quote:
                quote = ""
            elif ch == "\\" and quote == '"' and i + 1 < n and segment[i + 1] in '"\\$`':
                buf.append(segment[i + 1])
                i += 1
            else:
                buf.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote, has = ch, True
            i += 1
            continue
        if ch in " \t\r\n":
            _emit()
            i += 1
            continue
        if ch == ">":
            # Préfixe fd (`2>`, `&>`, `*>`) collé au mot courant : on le jette.
            word = "".join(buf)
            if has and re.fullmatch(r"[0-9&*]+", word):
                buf, has = [], False
            _emit()
            op = next(o for o in _REDIR_OPS if segment.startswith(o, i))
            toks.append(op)
            i += len(op)
            continue
        if ch == "<":
            _emit()
            if segment.startswith("<<", i):
                toks.append("<<")
                i += 2
                if i < n and segment[i] == "-":
                    i += 1
            else:
                toks.append("<")
                i += 1
            continue
        buf.append(ch)
        has = True
        i += 1
    _emit()
    return toks


def _norm(tok: str) -> str:
    return tok.strip().strip("`").replace("\\", "/")


def _head(word: str) -> str:
    h = _norm(word).lower().rsplit("/", 1)[-1]
    for suf in (".exe", ".cmd", ".bat"):
        h = h.removesuffix(suf)
    return h


_NULL_TARGETS = frozenset({"/dev/null", "$null", "nul", "null", "/dev/stdout", "/dev/stderr"})


def _is_pathish(tok: str) -> bool:
    t = _norm(tok)
    return bool(t) and not t.startswith("&") and t.lower() not in _NULL_TARGETS


# --------------------------------------------------------------------------- #
# Tables de commandes
# --------------------------------------------------------------------------- #

#: Toutes les positionnelles sont écrites / créées.
_WRITE_ALL: frozenset[str] = frozenset({
    "tee", "touch", "mkdir", "md", "truncate", "install", "rsync", "ln", "patch",
    "tee-object", "export-csv", "export-clixml", "new-item", "ni",
    "set-content", "sc", "add-content", "ac", "out-file", "clear-content", "clc",
})
_DELETE_ALL: frozenset[str] = frozenset({
    "rm", "rmdir", "unlink", "shred", "del", "erase", "rd", "remove-item", "ri",
})
_MOVE_ALL: frozenset[str] = frozenset({
    "mv", "move", "move-item", "mi", "ren", "rename", "rename-item", "rni",
})
_COPY: frozenset[str] = frozenset({
    "cp", "copy", "copy-item", "cpi", "xcopy", "robocopy", "scp",
})
#: Premier positionnel = mode/propriétaire, pas un chemin.
_FIRST_ARG_NOT_PATH: frozenset[str] = frozenset({"chmod", "chown", "chgrp"})

#: Paramètres PowerShell porteurs de la cible.
_PS_PATH_PARAMS = frozenset({"-path", "-literalpath", "-filepath", "-destination",
                              "-destinationpath", "-outfile", "-newname", "-pspath"})
_PS_VALUE_PARAMS = frozenset({"-value", "-inputobject"})
#: Paramètres PowerShell qui consomment une valeur (à sauter).
_PS_VALUE_TAKING = frozenset({
    "-encoding", "-itemtype", "-type", "-name", "-delimiter", "-filter", "-include",
    "-exclude", "-credential", "-stream", "-width", "-depth", "-method", "-uri",
    "-headers", "-body", "-contenttype", "-useragent", "-timeoutsec",
})
#: Options bash qui consomment l'argument suivant (non-chemin).
_BASH_VALUE_TAKING = {
    "cp": {"--backup", "-S", "--suffix"},
    "install": {"-m", "--mode", "-o", "--owner", "-g", "--group"},
    "truncate": {"-s", "--size"},
    "sed": {"-e", "--expression", "-f", "--file"},
    "gsed": {"-e", "--expression", "-f", "--file"},
    "perl": {"-e", "-E"},
    "rsync": {"-e", "--rsh", "--exclude", "--include", "--filter"},
    "mkdir": {"-m", "--mode"},
    "touch": {"-d", "--date", "-t", "-r", "--reference"},
}

_INTERPRETERS = frozenset({
    "python", "python3", "py", "node", "deno", "bun", "ruby", "perl", "php",
    "pwsh", "powershell", "bash", "sh", "zsh", "dash", "cmd",
})
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "pwsh", "powershell", "cmd"})
_INLINE_FLAGS = frozenset({"-c", "-e", "-command", "/c", "/k", "-r", "--eval", "--command"})
_WRAPPERS = frozenset({"sudo", "env", "nohup", "time", "command", "exec", "builtin",
                       "nice", "timeout", "stdbuf", "xargs", "doas", "&", "."})

#: Marqueurs d'écriture dans du code inline (Python / Node / PowerShell / .NET / Ruby / PHP).
INLINE_WRITE_MARKER = re.compile(
    r"open\s*\([^)]*['\"][wax]\+?b?t?['\"]|open\s*\([^)]*mode\s*=\s*['\"][wax]|"
    r"write_text|write_bytes|\.touch\s*\(|unlink|rmtree|os\.remove|os\.rename|os\.replace|"
    r"shutil\.|makedirs|mkdir|copyfile|writeFile|appendFile|rmSync|unlinkSync|"
    r"renameSync|copyFileSync|createWriteStream|Set-Content|Add-Content|Out-File|"
    r"Remove-Item|Copy-Item|Move-Item|New-Item|WriteAll(?:Text|Bytes|Lines)|"
    r"AppendAll(?:Text|Lines)|StreamWriter|File\]::(?:Write|Append|Copy|Move|Delete|Create)|"
    r"File\.(?:write|open\([^)]*['\"][wa])|IO\.write|file_put_contents|fwrite|"
    r"\.save\s*\(|\.dump\s*\(",
    re.IGNORECASE,
)
#: .NET statique appelé directement depuis PowerShell (sans `pwsh -c`).
_DOTNET_WRITE_RE = re.compile(
    r"\[(?:System\.)?IO\.(?:File|Directory)\]::(?:Write|Append|Copy|Move|Delete|Create|Replace)",
    re.IGNORECASE,
)
_STRING_LIT_RE = re.compile(r"""(?:[rRbBfFuU]{0,2})(['"])((?:\\.|(?!\1).)*?)\1""", re.DOTALL)
_PATHISH_LIT_RE = re.compile(r"^(?:[A-Za-z]:)?[\w.\-~/\\ ]*[/\\][\w.\-/\\ ]*$|^[\w.\-]+\.\w{1,10}$")


def _inline_literal_paths(code: str) -> list[str]:
    """Littéraux chaîne de `code` qui ressemblent à un chemin."""
    out: list[str] = []
    for m in _STRING_LIT_RE.finditer(code):
        lit = m.group(2).strip()
        if not lit or len(lit) > 400 or "\n" in lit:
            continue
        if _PATHISH_LIT_RE.match(lit):
            out.append(lit.replace("\\\\", "/").replace("\\", "/"))
    # Chemins nus hors guillemets (f-strings, concaténations) commençant par
    # un dossier caché ou `workspace/` — complément du scan de littéraux.
    for m in re.finditer(r"(?:^|[\s(=,+'\"])((?:\.[\w-]+|workspace)/[\w.\-/{}]*)", code):
        out.append(m.group(1))
    seen: set[str] = set()
    return [p for p in out if not (p in seen or seen.add(p))]


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

def _join_cwd(cwd: str | None, arg: str) -> str | None:
    if cwd == "?":
        return "?"
    a = _norm(arg)
    if not a or a in ("~", "-") or a.startswith(("$", "%", "~")):
        return "?"
    if re.match(r"^(?:[A-Za-z]:)?/", a):
        return posixpath.normpath(a)
    return posixpath.normpath(posixpath.join(cwd or ".", a))


def _positionals(tokens: list[str], head: str) -> list[str]:
    """Arguments positionnels (options et leurs valeurs exclues)."""
    out: list[str] = []
    skip_next = False
    value_taking = _BASH_VALUE_TAKING.get(head, set())
    end_opts = False
    for t in tokens:
        if skip_next:
            skip_next = False
            continue
        low = t.lower()
        if not end_opts and t == "--":
            end_opts = True
            continue
        if not end_opts and t.startswith("-") and len(t) > 1:
            if low in _PS_VALUE_TAKING or t in value_taking or low in _PS_VALUE_PARAMS \
                    or low in _PS_PATH_PARAMS:
                skip_next = True
            continue
        if not end_opts and head in {"xcopy", "robocopy", "copy", "move", "del", "erase", "rd"} \
                and t.startswith("/") and len(t) <= 4:
            continue  # switches Windows (/Y, /E, /S)
        out.append(t)
    return out


def _ps_param(tokens: list[str], names: frozenset[str]) -> list[str]:
    vals: list[str] = []
    for i, t in enumerate(tokens):
        low = t.lower()
        if ":" in low and low.split(":", 1)[0] in names:
            vals.append(t.split(":", 1)[1])
        elif low in names and i + 1 < len(tokens):
            vals.append(tokens[i + 1])
    return vals


def _resolve_hs(tok: str, seg: Segment) -> str:
    return seg.herestrings.get(tok, tok)


def _segment_targets(seg: Segment, cwd: str | None, prev_literal: str | None,
                     depth: int) -> list[WriteTarget]:
    toks_raw = tokenize(seg.text)
    if not toks_raw:
        return []
    out: list[WriteTarget] = []

    # ---- redirections -------------------------------------------------- #
    redir_content: str | None = None
    body = seg.heredocs[0] if seg.heredocs else None
    words: list[str] = []
    i = 0
    redirs: list[tuple[str, str]] = []
    while i < len(toks_raw):
        t = toks_raw[i]
        if t in (">", ">>", ">|"):
            if i + 1 < len(toks_raw):
                redirs.append((t, toks_raw[i + 1]))
            i += 2
            continue
        if t in ("<", "<<"):
            i += 2  # source d'entrée / délimiteur de heredoc
            continue
        words.append(t)
        i += 1

    # Retire les préfixes d'affectation `VAR=x` et les wrappers (`sudo`, `env`…).
    while words and (re.match(r"^[A-Za-z_]\w*=", words[0]) or _head(words[0]) in _WRAPPERS):
        h0 = _head(words[0])
        words = words[1:]
        if h0 in ("timeout",) and words:
            words = words[1:]
    head = _head(words[0]) if words else ""
    args = words[1:]

    if redirs:
        if body is not None and head in ("cat", "tee", ""):
            redir_content = body
        elif head in ("echo", "printf", "write-output", "write"):
            redir_content = " ".join(_resolve_hs(a, seg) for a in args if not a.startswith("-"))
        elif not words and prev_literal is not None:
            redir_content = prev_literal
        for _op, tgt in redirs:
            if _is_pathish(tgt):
                out.append(WriteTarget(_norm(tgt), "redirect", head or "redirect", cwd,
                                       redir_content))

    if not words:
        return out

    if head in ("sed", "perl", "gsed"):
        if any(re.match(r"^-[a-zA-Z]*i", a) or a.startswith("--in-place") for a in args):
            p_all = _positionals(args, head)
            script_opt = {"sed": ("-e", "--expression", "-f", "--file"),
                          "gsed": ("-e", "--expression", "-f", "--file"),
                          "perl": ("-e", "-E")}[head]
            files = p_all if any(a in script_opt or a.startswith(("--expression=", "--file="))
                                 for a in args) else p_all[1:]
            return out + [WriteTarget(_norm(p), "inplace", head, cwd) for p in files if _is_pathish(p)]
        if head != "perl":
            return out

    # ---- interpréteurs : code inline / heredoc / -c récursif ------------- #
    if head in _INTERPRETERS:
        inline_idx = next((k for k, a in enumerate(args) if a.lower() in _INLINE_FLAGS
                           or a.lower().startswith("-command")), None)
        code: str | None = None
        if inline_idx is not None:
            code = " ".join(_resolve_hs(a, seg) for a in args[inline_idx + 1:])
        elif body is not None and (not args or args[0] == "-" or all(a.startswith("-") for a in args)):
            code = body
        if code is not None:
            if head in _SHELLS and depth < _MAX_DEPTH:
                out.extend(_extract(code, cwd, depth + 1))
            if INLINE_WRITE_MARKER.search(code):
                for p in _inline_literal_paths(code):
                    out.append(WriteTarget(p, "inline", head, cwd))
        return out

    if head in ("eval", "invoke-expression", "iex") and depth < _MAX_DEPTH:
        out.extend(_extract(" ".join(_resolve_hs(a, seg) for a in args), cwd, depth + 1))
        return out

    # .NET statique depuis PowerShell : [IO.File]::WriteAllText('p', …)
    if _DOTNET_WRITE_RE.search(seg.text):
        for p in _inline_literal_paths(seg.text):
            out.append(WriteTarget(p, "inline", "[IO.File]", cwd))
        return out

    pos = _positionals(args, head)

    # ---- commandes PowerShell à paramètres nommés ------------------------- #
    if head in {"set-content", "sc", "add-content", "ac", "out-file", "new-item", "ni",
                "clear-content", "clc", "tee-object", "export-csv", "export-clixml"}:
        paths = _ps_param(args, _PS_PATH_PARAMS) or pos[:1]
        values = _ps_param(args, _PS_VALUE_PARAMS)
        if values:
            content: str | None = _resolve_hs(values[0], seg)
        elif head in ("set-content", "sc", "add-content", "ac", "new-item", "ni") and len(pos) > 1:
            content = _resolve_hs(pos[1], seg)
        elif prev_literal is not None:
            content = prev_literal
        elif head in ("new-item", "ni"):
            content = ""  # fichier vide
        else:
            content = None
        for p in paths:
            if _is_pathish(p):
                out.append(WriteTarget(_norm(p), "write", head, cwd, content))
        return out

    if head in {"copy-item", "cpi", "move-item", "mi", "rename-item", "rni",
                "expand-archive", "invoke-webrequest", "iwr", "invoke-restmethod", "irm"}:
        explicit_dst = _ps_param(args, frozenset({"-destination", "-destinationpath",
                                                  "-outfile", "-newname"}))
        explicit_src = _ps_param(args, frozenset({"-path", "-literalpath"}))
        srcs = explicit_src or pos[:1]
        if explicit_dst:
            dests = explicit_dst
        elif explicit_src:
            dests = pos[:1]
        else:
            dests = pos[1:2]
        op = "move" if head in {"move-item", "mi", "rename-item", "rni"} else (
            "download" if head in {"invoke-webrequest", "iwr", "invoke-restmethod", "irm"}
            else "archive" if head == "expand-archive" else "copy")
        if op == "move":
            for s in srcs:
                if _is_pathish(s):
                    out.append(WriteTarget(_norm(s), "move", head, cwd))
        for d in dests:
            if _is_pathish(d):
                out.append(WriteTarget(_norm(d), op, head, cwd,
                                       sources=tuple(_norm(s) for s in srcs if op != "download")))
        return out

    # ---- commandes bash / cmd -------------------------------------------- #
    if head in _DELETE_ALL:
        return out + [WriteTarget(_norm(p), "delete", head, cwd) for p in pos if _is_pathish(p)]
    if head in _MOVE_ALL:
        srcs = tuple(_norm(p) for p in pos[:-1])
        return out + [WriteTarget(_norm(p), "move", head, cwd, sources=srcs if p == pos[-1] else ())
                      for p in pos if _is_pathish(p)]
    if head in _WRITE_ALL or head in _FIRST_ARG_NOT_PATH:
        cand = pos[1:] if head in _FIRST_ARG_NOT_PATH else pos
        content = body if head == "tee" and body is not None else (
            prev_literal if head == "tee" else ("" if head == "touch" else None))
        return out + [WriteTarget(_norm(p), "write", head, cwd, content)
                      for p in cand if _is_pathish(p)]
    if head in _COPY:
        tdir = next((args[k + 1] for k, a in enumerate(args)
                     if a in ("-t",) and k + 1 < len(args)), None)
        tdir = tdir or next((a.split("=", 1)[1] for a in args
                             if a.startswith("--target-directory=")), None)
        if tdir:
            dest, srcs = tdir, pos
        elif head == "robocopy" and len(pos) >= 2:
            dest, srcs = pos[1], pos[:1]
        elif len(pos) >= 2:
            dest, srcs = pos[-1], pos[:-1]
        elif head in ("copy", "xcopy") and pos:
            dest, srcs = ".", pos
        else:
            return out
        if _is_pathish(dest):
            out.append(WriteTarget(_norm(dest), "copy", head, cwd,
                                   sources=tuple(_norm(s) for s in srcs)))
        return out
    if head == "dd":
        return out + [WriteTarget(_norm(a[3:]), "write", "dd", cwd)
                      for a in args if a.startswith("of=")]
    if head == "find":
        if any(a in ("-delete",) for a in args) or (
                "-exec" in args and any(_head(a) in _DELETE_ALL | _MOVE_ALL | {"sed", "perl", "tee"}
                                        for a in args[args.index("-exec") + 1:])):
            roots = [a for a in args if not a.startswith(("-", "(", ")", "!", "{")) and a != ";"]
            roots = roots[:1] if roots else ["."]
            return out + [WriteTarget(_norm(r).rstrip("/") + "/", "delete", "find", cwd)
                          for r in roots if _is_pathish(r)]
        return out
    if head == "git":
        sub_idx = next((k for k, a in enumerate(args) if not a.startswith("-")), None)
        if sub_idx is None:
            return out
        sub = args[sub_idx].lower()
        if sub in {"checkout", "restore", "clean", "rm", "mv", "reset", "stash", "revert",
                   "apply", "am", "switch"}:
            rest = args[sub_idx + 1:]
            paths = rest[rest.index("--") + 1:] if "--" in rest else [
                a for a in rest if not a.startswith("-")]
            return out + [WriteTarget(_norm(p), "git", sub, cwd) for p in paths if _is_pathish(p)]
        return out
    if head in ("curl", "wget"):
        names = {"curl": {"-o", "--output"}, "wget": {"-O", "--output-document", "-P",
                                                      "--directory-prefix"}}[head]
        dests = [args[k + 1] for k, a in enumerate(args) if a in names and k + 1 < len(args)]
        dests += [a.split("=", 1)[1] for a in args if "=" in a and a.split("=", 1)[0] in names]
        return out + [WriteTarget(_norm(d), "download", head, cwd) for d in dests if _is_pathish(d)]
    if head in ("tar", "unzip", "7z"):
        flag = {"tar": ("-C", "--directory"), "unzip": ("-d",), "7z": ()}[head]
        dests = [args[k + 1] for k, a in enumerate(args) if a in flag and k + 1 < len(args)]
        dests += [a[2:] for a in args if head == "7z" and a.startswith("-o")]
        if head == "tar" and any(re.match(r"^-?[a-zA-Z]*c", a) for a in args[:1]):
            fidx = next((k for k, a in enumerate(args) if re.match(r"^-?[a-zA-Z]*f$", a)), None)
            if fidx is not None and fidx + 1 < len(args):
                dests.append(args[fidx + 1])
        return out + [WriteTarget(_norm(d), "archive", head, cwd) for d in dests if _is_pathish(d)]
    return out


def _literal_of(seg: Segment) -> str | None:
    """Contenu littéral produit par un segment amont de pipeline (`echo x |`)."""
    toks = tokenize(seg.text)
    if not toks:
        return None
    h = _head(toks[0])
    if h in ("echo", "printf", "write-output", "write"):
        return " ".join(_resolve_hs(a, seg) for a in toks[1:] if not a.startswith("-"))
    if h == "cat" and seg.heredocs:
        return seg.heredocs[0]
    if len(toks) == 1 and (toks[0] in seg.herestrings or seg.text[:1] in "'\""):
        return _resolve_hs(toks[0], seg)
    return None


_CD_HEADS = frozenset({"cd", "pushd", "set-location", "sl", "chdir", "push-location"})


def _extract(cmd: str, cwd: str | None, depth: int) -> list[WriteTarget]:
    out: list[WriteTarget] = []
    prev: Segment | None = None
    for seg in split_segments(cmd):
        toks = tokenize(seg.text)
        if toks and _head(toks[0]) in _CD_HEADS:
            args = [a for a in toks[1:] if not a.startswith("-") or a == "-"]
            pv = _ps_param(toks[1:], frozenset({"-path", "-literalpath"}))
            target = (pv or args or ["~"])[0]
            cwd = _join_cwd(cwd, target)
            prev = seg
            continue
        if toks and _head(toks[0]) in ("popd", "pop-location"):
            cwd = "?"
            prev = seg
            continue
        prev_lit = _literal_of(prev) if (prev is not None and seg.sep == "|") else None
        out.extend(_segment_targets(seg, cwd, prev_lit, depth))
        prev = seg
    return out


def extract_write_targets(cmd: str) -> list[WriteTarget]:
    """Toutes les cibles d'écriture/suppression/déplacement reconnues dans `cmd`.

    Liste vide = aucune écriture reconnue (lecture, build, test…).
    Dédoublonnée sur (path, op, cwd), ordre conservé.
    """
    if not isinstance(cmd, str) or not cmd.strip():
        return []
    seen: set[tuple[str, str, str | None]] = set()
    out: list[WriteTarget] = []
    for t in _extract(cmd, None, 0):
        key = (t.path, t.op, t.cwd)
        if key in seen or not t.path:
            continue
        seen.add(key)
        out.append(t)
    return out


def resolve_target(target: WriteTarget, base: Path) -> Path | None:
    """Chemin absolu de `target` depuis `base` (cwd de l'outil shell).

    `None` si le répertoire courant est inconnu (`cd $VAR`) ET le chemin est
    relatif — l'appelant décide alors (fail-closed : tester aussi le chemin
    relatif à la racine du dépôt).
    """
    p = target.path
    if re.match(r"^(?:[A-Za-z]:)?/", p):
        return Path(p)
    if target.cwd == "?":
        return None
    root = base
    if target.cwd:
        c = target.cwd
        root = Path(c) if re.match(r"^(?:[A-Za-z]:)?/", c) else base / c
    return root / p
