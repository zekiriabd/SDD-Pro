"""sdd_lib.delivery_gate — gate de livraison fondée sur des PREUVES (audit 2026-11-07).

Constats d'audit corrigés
-------------------------
1. ``buildVerified=false`` / ``qa.executed=false`` donnaient un WARN, et un
   WARN laissait tout passer.
2. Les statuts de ``run_phases`` sont auto-déclarés par l'orchestrateur LLM :
   la livraison reposait sur l'auto-certification de celui qui livre.
3. ``--force`` / une relance contournaient la readiness.

Contrat
-------
- ``WORKFLOW_REQUIREMENTS`` est la SSoT des validations obligatoires par
  workflow. Un workflow inconnu est refusé (fail-closed).
- Une preuve n'existe que dans la table console.db ``delivery_evidence`` et
  n'est écrite que par les scripts qui EXÉCUTENT (build, tests, readiness) ou
  LISENT eux-mêmes la source vérifiée (rapport du reviewer spec-compliance).
  Aucune sous-commande CLI n'accepte ``passed`` / ``exit_code`` en argument ;
  l'écriture passe par ``_record_evidence`` (interne, producteurs listés).
- Chaque preuve porte un HMAC-SHA256 calculé avec une clé locale hors dépôt
  (``~/.sdd/delivery-gate.key``) : une ligne insérée à la main ne vaut rien.
- Une preuve n'a que deux états : ``passed`` ou non. WARN / partiel / inconnu
  sur un check obligatoire = non passé (exception documentée : la readiness
  ``WARN`` est le « GO avec avertissements » de ``validate_readiness.py``,
  exit 0 — c'est ``NO-GO`` qui est l'échec).
- Une preuve ne vaut que pour l'état exact des sources (``tree_hash``) ; un
  échec ET un succès sur le même ``tree_hash`` = résultat instable → bloqué.
  Seul un changement des sources (ou des entrées, pour readiness) lève un échec.
- ``authorize_delivery`` ne lit QUE ``delivery_evidence`` — jamais
  ``run_phases`` ni un payload d'orchestrateur — et n'a aucun paramètre
  ``force`` / ``allow_warn``. Les variables ``SDD_ALLOW_*`` / ``SDD_BYPASS_*``
  / ``SDD_FORCE*`` sont ignorées ; leur présence est consignée (raison +
  ``audit_dir_path()/delivery-gate.jsonl``), jamais silencieuse.

Classe d'erreur : ``[DELIVERY_GATE_BLOCKED]`` (error-classification.md §1.7).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from sdd_lib.paths import audit_dir_path, iso_now_ms, repo_root, workspace_root

#: Classe d'erreur émise par tout refus de livraison.
ERROR_CLASS = "DELIVERY_GATE_BLOCKED"

#: Checks connus (« readiness » : exigence anti-relance 2026-11-07).
KNOWN_CHECKS: tuple[str, ...] = ("build", "tests", "coverage", "spec_compliance", "readiness")

#: SSoT — validations obligatoires par workflow. Aucun drapeau ne les retire.
WORKFLOW_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "sdd-full": ("readiness", "build", "tests", "coverage", "spec_compliance"),
    "sdd-poc": ("build",),              # POC : pas de QA, c'est voulu
    "dev-run": ("readiness", "build"),  # + API gate côté orchestrateur si back
    "sdd-deploy": ("build",),           # commande à venir — profil déclaré seulement
    "qa-generate": ("build", "tests", "coverage"),
    "sdd-review": ("build", "tests", "spec_compliance"),
}

#: Dossiers générés exclus de l'empreinte des sources.
EXCLUDED_DIRS: frozenset[str] = frozenset({
    "bin", "obj", "node_modules", ".git", "coverage", "TestResults",
    "__pycache__", ".vs", ".idea", ".gradle", ".pytest_cache", ".venv",
    "dist", "build", "out", "target", ".sys",
})

#: Producteurs légitimes (nom consigné dans ``producer``).
PRODUCERS: frozenset[str] = frozenset({
    "verify_build.py", "verify_tests.py",
    "delivery_gate.py:record-spec", "delivery_gate.py:record-readiness",
})

#: Préfixes de variables d'environnement de contournement — IGNORÉES, consignées.
BYPASS_ENV_PREFIXES: tuple[str, ...] = ("SDD_ALLOW_", "SDD_BYPASS_", "SDD_FORCE")

KEY_FILENAME = "delivery-gate.key"
AUDIT_LOG_NAME = "delivery-gate.jsonl"

_DDL = """
CREATE TABLE IF NOT EXISTS delivery_evidence (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    feat_n        INTEGER NOT NULL,
    run_id        TEXT,
    check_name    TEXT    NOT NULL,
    passed        INTEGER NOT NULL,
    exit_code     INTEGER NOT NULL,
    command       TEXT    NOT NULL,
    details_json  TEXT    NOT NULL,
    tree_hash     TEXT    NOT NULL,
    producer      TEXT    NOT NULL,
    hmac          TEXT
)
"""


class DeliveryGateError(RuntimeError):
    """Erreur d'infrastructure de la gate (clé illisible, clé mal placée)."""


@dataclass
class GateDecision:
    """Décision de livraison — ``allowed`` n'est vrai que sans aucun manque."""

    allowed: bool
    workflow: str
    required: tuple[str, ...]
    missing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["required"] = list(self.required)
        return d


# ---------------------------------------------------------------------------
# Clé HMAC locale (hors dépôt, hors workspace)
# ---------------------------------------------------------------------------

def key_path() -> Path:
    """Chemin de la clé : ``~/.sdd/delivery-gate.key`` (dossier utilisateur)."""
    return Path.home() / ".sdd" / KEY_FILENAME


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _load_key(*, create: bool) -> bytes | None:
    """Charge (ou crée une fois) la clé HMAC locale.

    Refuse une clé située dans le dépôt ou le workspace : elle voyagerait
    avec le code et n'authentifierait plus rien.
    """
    path = key_path()
    try:
        root = repo_root()
        inside = _is_within(path, root) or _is_within(path, workspace_root(root))
    except Exception:  # noqa: BLE001 — repo introuvable : pas de collision possible
        inside = False
    if inside:
        raise DeliveryGateError(
            f"clé HMAC dans le dépôt/workspace refusée ({path}) — elle doit vivre sous ~/.sdd/")
    if path.is_file():
        try:
            key = bytes.fromhex(path.read_text(encoding="ascii").strip())
        except (OSError, ValueError) as e:
            raise DeliveryGateError(f"clé HMAC illisible ({path}) : {e}") from e
        if len(key) < 32:
            raise DeliveryGateError(f"clé HMAC trop courte ({path})")
        return key
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _load_key(create=False)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(key.hex())
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def _canonical_payload(row: dict[str, Any]) -> bytes:
    fields = {
        "feat_n": int(row["feat_n"]),
        "check": str(row["check_name"]),
        "passed": bool(row["passed"]),
        "exit_code": int(row["exit_code"]),
        "tree_hash": str(row["tree_hash"]),
        "command": str(row["command"]),
        "ts": str(row["ts"]),
        "producer": str(row["producer"]),
        "run_id": row.get("run_id"),
        "details_sha256": hashlib.sha256(str(row["details_json"]).encode("utf-8")).hexdigest(),
    }
    return json.dumps(fields, sort_keys=True, ensure_ascii=True).encode("utf-8")


def _sign(row: dict[str, Any], key: bytes) -> str:
    return hmac.new(key, _canonical_payload(row), hashlib.sha256).hexdigest()


def _verify(row: dict[str, Any], key: bytes | None) -> bool:
    sig = row.get("hmac")
    if not key or not sig:
        return False
    return hmac.compare_digest(str(sig), _sign(row, key))


# ---------------------------------------------------------------------------
# Empreintes
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root: Path, excluded: Iterable[str]) -> Iterable[Path]:
    excluded = set(excluded)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in excluded)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def compute_tree_hash(paths: list[Path]) -> str:
    """sha256 déterministe des sources (chemins relatifs + contenus).

    Exclut les dossiers générés (``EXCLUDED_DIRS`` : bin/, obj/,
    node_modules/, .git/, coverage/, TestResults/, …). Une racine absente
    contribue un marqueur ``<absent>`` — l'empreinte reste déterministe.
    """
    h = hashlib.sha256()
    for idx, base in enumerate(sorted({Path(p) for p in paths}, key=str)):
        h.update(f"#root{idx}:{base.name}\n".encode("utf-8"))
        if base.is_file():
            h.update(f"F {base.name}\0{sha256_file(base)}\n".encode("utf-8"))
            continue
        if not base.is_dir():
            h.update(b"<absent>\n")
            continue
        for f in _iter_files(base, EXCLUDED_DIRS):
            rel = f.relative_to(base).as_posix()
            try:
                digest = sha256_file(f)
            except OSError:
                digest = "<unreadable>"
            h.update(f"{rel}\0{digest}\n".encode("utf-8"))
    return h.hexdigest()


def readiness_inputs(feat_n: int, root: Path | None = None) -> list[Path]:
    """Entrées de la readiness : FEAT, US, mockups de la FEAT + stack.md + constitution."""
    ws = workspace_root(root or repo_root())
    files: list[Path] = []
    for sub, pattern in (("feats", f"{feat_n}-*.md"), ("us", f"{feat_n}-*.md"),
                         ("ui", f"{feat_n}-*.html")):
        d = ws / sub
        if d.is_dir():
            files.extend(sorted(d.glob(pattern)))
    for extra in (ws / "stack" / "stack.md", ws / ".sys" / ".context" / "constitution.md"):
        if extra.is_file():
            files.append(extra)
    return files


def compute_readiness_hash(feat_n: int, root: Path | None = None) -> str:
    """Empreinte des entrées de readiness — seul son changement lève un NO-GO."""
    files = readiness_inputs(feat_n, root)
    ws = workspace_root(root or repo_root())
    h = hashlib.sha256(f"readiness:{feat_n}\n".encode("utf-8"))
    for f in files:
        try:
            rel = f.relative_to(ws).as_posix()
        except ValueError:
            rel = f.name
        h.update(f"{rel}\0{sha256_file(f)}\n".encode("utf-8"))
    return h.hexdigest()


def default_project_roots(root: Path | None = None) -> list[Path]:
    """Racine des sources livrées : ``workspace/src``."""
    return [workspace_root(root or repo_root()) / "src"]


# ---------------------------------------------------------------------------
# Persistance
# ---------------------------------------------------------------------------

def _ensure_table(conn: sqlite3.Connection) -> None:
    """Garde idempotente (la migration 0009 reste le chemin nominal)."""
    conn.execute(_DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_evidence_feat_check "
                 "ON delivery_evidence(feat_n, check_name, id)")


def _record_evidence(*, feat_n: int, check: str, run_id: str | None, passed: bool,
                     exit_code: int, command: str, details: dict, tree_hash: str,
                     producer: str) -> int:
    """Écrit une preuve signée (INTERNE — réservée aux scripts de vérification).

    Exposée par AUCUNE sous-commande CLI : ``passed`` / ``exit_code``
    proviennent toujours de l'exécution ou de la lecture faite par le
    producteur lui-même.
    """
    from sdd_lib.console_db import connect, ensure_initialized

    if check not in KNOWN_CHECKS:
        raise ValueError(f"check inconnu : {check!r}")
    if producer not in PRODUCERS:
        raise ValueError(f"producteur non autorisé : {producer!r}")
    key = _load_key(create=True)
    assert key is not None
    row: dict[str, Any] = {
        "ts": iso_now_ms(), "feat_n": int(feat_n), "run_id": run_id,
        "check_name": check, "passed": 1 if passed else 0, "exit_code": int(exit_code),
        "command": command,
        "details_json": json.dumps(details, sort_keys=True, ensure_ascii=False, default=str),
        "tree_hash": tree_hash, "producer": producer,
    }
    row["hmac"] = _sign(row, key)
    ensure_initialized()
    with connect() as conn:
        _ensure_table(conn)
        cur = conn.execute(
            "INSERT INTO delivery_evidence (ts, feat_n, run_id, check_name, passed, exit_code,"
            " command, details_json, tree_hash, producer, hmac)"
            " VALUES (:ts, :feat_n, :run_id, :check_name, :passed, :exit_code, :command,"
            " :details_json, :tree_hash, :producer, :hmac)", row)
        new_id = int(cur.lastrowid)
    audit_event("evidence", feat_n=feat_n, check=check, passed=bool(passed),
                exit_code=exit_code, producer=producer, evidence_id=new_id, run_id=run_id)
    return new_id


def _fetch_rows(feat_n: int, check: str) -> list[dict[str, Any]]:
    from sdd_lib.console_db import connect, ensure_initialized

    ensure_initialized()
    with connect() as conn:
        _ensure_table(conn)
        rows = conn.execute(
            "SELECT * FROM delivery_evidence WHERE feat_n = ? AND check_name = ? ORDER BY id",
            (int(feat_n), check)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def bypass_env_present(env: Any = None) -> list[str]:
    """Variables de contournement présentes (ignorées mais consignées)."""
    env = os.environ if env is None else env
    return sorted(k for k, v in env.items()
                  if v and any(k.upper().startswith(p) for p in BYPASS_ENV_PREFIXES))


def audit_event(event: str, **fields: Any) -> None:
    """Append-only JSONL sous ``audit_dir_path()/delivery-gate.jsonl`` (best-effort)."""
    try:
        d = audit_dir_path()
        d.mkdir(parents=True, exist_ok=True)
        rec = {"ts": iso_now_ms(), "event": event, **fields}
        with open(d / AUDIT_LOG_NAME, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def note_ignored_bypass_env(producer: str, **fields: Any) -> list[str]:
    """Consigne (jamais silencieux) les variables de contournement vues par un producteur."""
    ignored = bypass_env_present()
    if ignored:
        audit_event("bypass_env_ignored", producer=producer, variables=ignored, **fields)
    return ignored


# ---------------------------------------------------------------------------
# Contrôles sémantiques par check (re-vérifiés à l'autorisation)
# ---------------------------------------------------------------------------

def _semantic_problem(check: str, row: dict[str, Any]) -> str | None:
    """Re-vérifie qu'une preuve « passed » porte les éléments d'une exécution réelle."""
    try:
        details = json.loads(row.get("details_json") or "{}")
    except ValueError:
        return "détails de preuve illisibles"
    if check in ("build", "tests") and int(row["exit_code"]) != 0:
        return f"exit code {row['exit_code']} ≠ 0"
    if check == "build":
        artifacts = details.get("artifacts") or []
        if not artifacts:
            return "aucun artefact de build relevé"
        for a in artifacts:
            p = Path(a.get("path", ""))
            if not p.is_file():
                return f"artefact de build absent : {p}"
            try:
                if sha256_file(p) != a.get("sha256"):
                    return f"artefact de build modifié depuis la preuve : {p}"
            except OSError:
                return f"artefact de build illisible : {p}"
    elif check == "tests":
        if int(details.get("executed", 0)) <= 0:
            return "0 test exécuté"
        if int(details.get("failed", 1)) != 0:
            return f"{details.get('failed')} test(s) en échec"
        if not details.get("report_sha256"):
            return "rapport de tests non empreinté"
    elif check == "coverage":
        pct, thr = details.get("coverage_pct"), details.get("threshold")
        if pct is None or thr is None:
            return "couverture non mesurée"
        if float(pct) < float(thr):
            return f"couverture {pct}% < seuil {thr}%"
    elif check == "spec_compliance":
        if str(details.get("verdict", "")).upper() not in ("GREEN", "YELLOW"):
            return f"verdict spec-compliance {details.get('verdict')!r}"
        if int(details.get("blocking_findings", 1)) != 0:
            return f"{details.get('blocking_findings')} finding(s) bloquant(s)"
    elif check == "readiness":
        if str(details.get("decision", "")).upper() not in ("GO", "WARN"):
            return f"readiness {details.get('decision')!r}"
    return None


# ---------------------------------------------------------------------------
# Autorisation
# ---------------------------------------------------------------------------

def authorize_delivery(*, feat_n: int, workflow: str, run_id: str | None,
                       project_roots: list[Path]) -> GateDecision:
    """Décide la livraison à partir des SEULES preuves ``delivery_evidence``.

    Pour chaque check requis : preuve la plus récente pour (feat_n, check) ;
    absente → missing ; empreinte ≠ état courant → stale ; échec, preuve non
    authentifiée, résultat instable sur le même état, ou éléments d'exécution
    incohérents (artefact disparu, 0 test…) → failed.

    Aucun paramètre force / allow_warn ; aucune variable d'environnement ne
    modifie la décision. Workflow inconnu → refusé (fail-closed).
    """
    ignored = bypass_env_present()
    required = WORKFLOW_REQUIREMENTS.get(workflow)
    if required is None:
        dec = GateDecision(False, workflow, (), reasons=[
            f"workflow inconnu {workflow!r} — refus par défaut "
            f"(connus : {', '.join(sorted(WORKFLOW_REQUIREMENTS))})"])
        _finish(dec, feat_n, run_id, ignored, infra=True)
        return dec

    dec = GateDecision(False, workflow, tuple(required))
    infra = False
    try:
        key = _load_key(create=False)
    except DeliveryGateError as e:
        key, infra = None, True
        dec.reasons.append(f"[INFRA_BLOCKED] {e}")
    hashes: dict[str, str] = {}

    for check in required:
        try:
            rows = _fetch_rows(feat_n, check)
        except (sqlite3.Error, OSError) as e:
            dec.failed.append(check)
            dec.reasons.append(f"{check} : console.db illisible ({e}) [INFRA_BLOCKED]")
            continue
        if not rows:
            dec.missing.append(check)
            dec.reasons.append(f"{check} : aucune preuve d'exécution")
            continue
        forged = [r["id"] for r in rows if not _verify(r, key)]
        if forged:
            dec.failed.append(check)
            dec.reasons.append(f"{check} : preuve non authentifiée (HMAC absent ou faux, "
                               f"ligne(s) {forged})")
            continue
        latest = rows[-1]
        scope = "readiness" if check == "readiness" else "src"
        if scope not in hashes:
            hashes[scope] = (compute_readiness_hash(feat_n) if scope == "readiness"
                             else compute_tree_hash(project_roots))
        what = "des entrées FEAT/US" if scope == "readiness" else "des sources"
        if latest["tree_hash"] != hashes[scope]:
            dec.stale.append(check)
            dec.reasons.append(f"{check} : preuve #{latest['id']} périmée (état {what} modifié "
                               f"depuis) — relancer la vérification")
            continue
        same = [r for r in rows if r["tree_hash"] == latest["tree_hash"]]
        if any(r["passed"] for r in same) and any(not r["passed"] for r in same):
            dec.failed.append(check)
            dec.reasons.append(f"{check} : résultat instable sur le même état {what} (échec et "
                               f"succès coexistent) — seul un changement {what} lève l'échec")
            continue
        if not latest["passed"]:
            dec.failed.append(check)
            dec.reasons.append(f"{check} : échec prouvé (preuve #{latest['id']}, "
                               f"exit {latest['exit_code']})")
            continue
        problem = _semantic_problem(check, latest)
        if problem:
            dec.failed.append(check)
            dec.reasons.append(f"{check} : {problem}")

    _finish(dec, feat_n, run_id, ignored, infra=infra)
    return dec


def _finish(dec: GateDecision, feat_n: int, run_id: str | None, ignored: list[str],
            *, infra: bool) -> None:
    if ignored:
        dec.reasons.append(f"variables de contournement ignorées : {', '.join(ignored)} "
                           f"(sans effet sur la décision)")
    dec.allowed = (not infra and dec.workflow in WORKFLOW_REQUIREMENTS
                   and not (dec.missing or dec.failed or dec.stale))
    if ignored:
        audit_event("bypass_env_ignored", producer="authorize_delivery", feat_n=feat_n,
                    workflow=dec.workflow, run_id=run_id, variables=ignored)
    audit_event("authorize", feat_n=feat_n, workflow=dec.workflow, run_id=run_id,
                allowed=dec.allowed, missing=dec.missing, failed=dec.failed, stale=dec.stale)


def format_error_3l(dec: GateDecision, feat_n: int) -> str:
    """Bloc ERROR 3 lignes (output-protocol.md §7.3)."""
    parts = []
    if dec.missing:
        parts.append(f"manquant={','.join(dec.missing)}")
    if dec.failed:
        parts.append(f"échec={','.join(dec.failed)}")
    if dec.stale:
        parts.append(f"périmé={','.join(dec.stale)}")
    first = next((r for r in dec.reasons if not r.startswith("variables de contournement")), "")
    detail = " ; ".join(p for p in ("; ".join(parts), first) if p) or "refus"
    return (f"ERROR: delivery-gate feat {feat_n} workflow {dec.workflow} failed\n"
            f"CAUSE: [{ERROR_CLASS}] {detail}\n"
            f"FIX: exécuter verify_build.py / verify_tests.py --coverage / delivery_gate.py "
            f"record-spec|record-readiness sur l'état courant et corriger jusqu'au vert — "
            f"aucun flag ni variable ne lève ce refus")


# ---------------------------------------------------------------------------
# Helpers partagés par les producteurs (verify_build / verify_tests)
# ---------------------------------------------------------------------------

#: Marqueurs de type de projet (alignés sur ``validate_acceptance.PROJECT_TYPE_MARKERS``).
PROJECT_TYPE_MARKERS: dict[str, tuple[str, ...]] = {
    "dotnet": ("*.csproj", "*.slnx", "*.sln"),
    "node": ("package.json",),
    "kotlin": ("build.gradle.kts", "build.gradle"),
    "python": ("pyproject.toml", "requirements.txt"),
}


def detect_project_type(project_dir: Path) -> str | None:
    """Type de projet d'un dossier (même logique que validate_acceptance)."""
    for ptype, markers in PROJECT_TYPE_MARKERS.items():
        for marker in markers:
            if "*" in marker:
                if any(project_dir.glob(marker)):
                    return ptype
            elif (project_dir / marker).is_file():
                return ptype
    return None


def detect_projects(src: Path) -> list[tuple[Path, str]]:
    """Projets sous ``workspace/src/*`` (tri déterministe)."""
    if not src.is_dir():
        return []
    out: list[tuple[Path, str]] = []
    for p in sorted((d for d in src.iterdir() if d.is_dir() and not d.name.startswith(".")),
                    key=lambda d: d.name):
        if p.name in EXCLUDED_DIRS:
            continue
        ptype = detect_project_type(p)
        if ptype:
            out.append((p, ptype))
    return out


def read_gate_command(key: str, root: Path | None = None) -> str | None:
    """Lit ``DeliveryGate.<key>`` brut dans ``## Project Config`` de stack.md.

    Lecture BRUTE (pas ``parse_kv_block``, qui retire les guillemets de tête et
    casserait ``"C:\Program Files\…\MSBuild.exe" X.slnx``). Une valeur
    entièrement entourée de backticks est dé-backtickée.
    """
    import re

    from sdd_lib.project_config import read_stack_md_text, section_body

    text = read_stack_md_text(root or repo_root())
    if not text:
        return None
    body = section_body(text, "Project Config") or ""
    rx = re.compile(rf"^[-*]?\s*DeliveryGate\.{re.escape(key)}\s*:\s*(.+?)\s*$")
    for line in body.splitlines():
        m = rx.match(line)
        if m:
            value = m.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] == "`":
                value = value[1:-1].strip()
            return value or None
    return None


def run_command(cmd: str | list[str], *, cwd: Path, timeout: int) -> tuple[int, str, float]:
    """Exécute réellement une commande ; retourne (exit_code, sortie tronquée, durée s).

    Chaîne → ``shell=True`` (commande Tech Lead de stack.md, guillemets Windows
    préservés) ; liste → exécution directe. Timeout → 124 ; introuvable → 127.
    """
    import shutil
    import subprocess
    import time

    if isinstance(cmd, list) and cmd:
        cmd = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), shell=isinstance(cmd, str),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out[-2000:], round(time.monotonic() - t0, 3)
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s", round(time.monotonic() - t0, 3)
    except FileNotFoundError as e:
        return 127, f"commande introuvable : {e}", round(time.monotonic() - t0, 3)
    except OSError as e:
        return 126, f"erreur OS : {e}", round(time.monotonic() - t0, 3)
