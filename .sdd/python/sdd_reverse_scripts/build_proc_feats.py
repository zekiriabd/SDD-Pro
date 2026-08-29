"""build_proc_feats.py — Deterministic FEAT assembler for db-reverse (rung 2).

Confirmed model: **1 module = 1 FEAT**, composed by REMONTÉE from the module's
SQL objects — the assembler reads the derived inventory AND the User Stories
produced by rung 1, NEVER the raw SQL bodies (escalier contract: rung 2 never
re-reads the source). 0 token, deterministic, passes validate_reverse_feat.py.

Each SQL object of the module becomes one capability (SFD + FD + AC), carrying
its snapshot evidence. Confidence is min-monotone over the module's objects (a
dynamic-SQL or encrypted object caps the whole FEAT).

Audit 2026-08-25 closes the two critical findings that lived here:

  - **C2 — the assembler never read the US.** Its own docstring claimed "their
    titles are folded into the FD lines"; the code only ever opened
    `inventory.json`. Consequence: the `reverse-sql-analyst` agent (deep tier)
    analysed every complex object into a US that NOTHING downstream consumed,
    so the FEAT — and the `.docx` specification book derived from it — stayed a
    paraphrase of regex signals. Real US titles, real AC counts and the
    `extraction` marker are now folded in.

  - **C3 — `## Covers` was never back-filled.** Both US generators wrote
    "back-fill par l'assembleur (rung 2)" and the assembler never touched a US
    file, so FEAT→US traceability existed nowhere on disk. `validate_readiness`
    marks SFD and FD coverage as REQUIRED, so every DB-reverse FEAT was a
    guaranteed `[READINESS_NO_GO]` at `/sdd-full` phase 2.6 — the exact opposite
    of the "FEATs consommables par /sdd-full" promise. The assembler now writes
    `Covers:` into each US and resolves its `Parent FEAT hash` sentinel (D4).

  - **M5 — silent clobbering.** A FEAT annotated by a human during the review the
    REVERSE-GATE asks for was overwritten without warning on the next run. The
    generated body is now fingerprinted in the frontmatter; a divergence means a
    human edited it, and the file is preserved unless `--force`.

CLI:
    python build_proc_feats.py --project DB [--unit U-N | --all] [--workspace DIR]
                              [--force] [--no-covers] [--json]

Exit codes: 0 OK · 2 inventory/IO error · 3 usage · 4 human edits preserved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

PY_ROOT = Path(__file__).resolve().parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.atomic_write_local import atomic_write_text

HASH_SENTINEL = "sha256:COMPUTE_REQUIRED"
_FINGERPRINT_KEY = "generated-fingerprint"

_VERB_LABEL = {
    "create": "créer", "save": "enregistrer", "update": "mettre à jour",
    "delete": "supprimer", "read": "consulter", "validate": "valider",
    "compute": "calculer", "process": "traiter", "import": "importer",
    "sync": "synchroniser", "notify": "notifier",
}

_KIND_LABEL = {
    "VIEW": "vue", "SQL_TRIGGER": "trigger", "TRIGGER": "trigger",
    "SQL_SCALAR_FUNCTION": "fonction", "SQL_INLINE_TABLE_VALUED_FUNCTION": "fonction table",
    "SQL_TABLE_VALUED_FUNCTION": "fonction table",
    "PACKAGE": "package", "PACKAGE BODY": "package",
}

_US_TITLE_RE = re.compile(r"^#\s+US-(\d+)\s*:\s*(.+?)\s*$", re.MULTILINE)
# Tolerate the bold form `- **AC-1** :` alongside `- AC-1:`. Observed on a
# real base (2026-08-27): 4 User Stories written by an LLM analyst used the
# bold variant, and their 13 acceptance criteria were therefore invisible to
# the FEAT `Covers:` back-fill — the RICHEST stories were the ones silently
# dropped from the traceability chain.
_AC_ID_RE = re.compile(r"^\s*-\s*\**\s*(AC-\d+)\s*\**\s*:", re.MULTILINE)
_EXTRACTION_RE = re.compile(r"^extraction:\s*(\w+)\s*$", re.MULTILINE)
_COVERS_SECTION_RE = re.compile(r"(^##\s+Covers\s*$)(.*?)(?=^##\s|\Z)",
                                re.MULTILINE | re.DOTALL)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ev(evidence: str, conf: str) -> str:
    e = (evidence or "unknown:1").strip().replace(" ", "_")
    if ":" not in e.rsplit("/", 1)[-1]:
        e += ":1"
    return f"<!-- evidence: {e} --> <!-- confidence: {conf} -->"


def _covers_us(n: int, proc: dict, us_index: dict[str, dict] | None) -> str:
    """`<!-- covers: {n}-{m}#AC-x, … -->` for the US of ONE SQL object.

    Audit 2026-08-25 (M3, residual). The FEAT already named its US in prose
    ("→ User Story `3-2-Consulter-Client`"), which a human reads and a checker
    cannot. `check_ladder_traceability.py` needs the machine-readable form to
    verify the rung above actually points at the rung below — without it, the
    downward half of the ladder was unverifiable on the DB path.

    Empty string when the US does not exist yet: the assembler must still run
    when rung 1 has not (that is how `/sdd-db-reverse-full` bootstraps), and
    a `covers:` pointing at a file that is not there would be worse than none.
    """
    us = (us_index or {}).get(proc["fqName"]) or {}
    ac_ids = us.get("acIds") or []
    if not ac_ids:
        return ""
    refs = ", ".join(f"{n}-{proc['usIndex']}#{ac}" for ac in ac_ids)
    return f" <!-- covers: {refs} -->"


def _covers_all(n: int, procs: list[dict], us_index: dict[str, dict] | None) -> str:
    """Same, for a module-level umbrella item carried by EVERY US of the module."""
    refs = []
    for p in procs:
        us = (us_index or {}).get(p["fqName"]) or {}
        for ac in (us.get("acIds") or []):
            refs.append(f"{n}-{p['usIndex']}#{ac}")
    return f" <!-- covers: {', '.join(refs)} -->" if refs else ""


def _gate(conf: str) -> str:
    allow = "true" if conf == "high" else "false"
    reason = "" if conf == "high" else " ; reason=confidence_below_high"
    return f"<!-- REVERSE-GATE: confidence={conf} ; allow-sdd-full={allow}{reason} -->"


def _kind_label(proc: dict) -> str:
    return _KIND_LABEL.get(str(proc.get("routineType") or "").upper(), "procédure")


# --------------------------------------------------------------------------- #
# C2 — read the User Stories the escalier actually produced
# --------------------------------------------------------------------------- #

def read_us_index(us_dir: Path, n: int, procs: list[dict]) -> dict[str, dict]:
    """Load the module's US files, keyed by fqName.

    Returns `{fqName: {path, title, acCount, acIds, extraction}}`. A missing US
    is simply absent from the map — the FEAT must still assemble when rung 1 has
    not run yet (that is how `/sdd-db-reverse-full` bootstraps, and how the
    offline tests exercise the assembler).
    """
    index: dict[str, dict] = {}
    for p in procs:
        path = us_dir / f"{n}-{p['usIndex']}-{p['usName']}.md"
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        title_m = _US_TITLE_RE.search(text)
        ac_ids = _AC_ID_RE.findall(text)
        extraction_m = _EXTRACTION_RE.search(text)
        index[p["fqName"]] = {
            "path": path,
            "title": (title_m.group(2).strip() if title_m else ""),
            "acIds": ac_ids,
            "acCount": len(ac_ids),
            "extraction": (extraction_m.group(1) if extraction_m else "unknown"),
        }
    return index


# Matches both the canonical frontmatter form ("parent-feat:") and the prose
# body form ("Parent FEAT:") that LLM analysts sometimes write.
_PARENT_FEAT_RE = re.compile(
    r"^((?:Parent FEAT|parent-feat):\s*)(.+?)\s*$", re.MULTILINE
)


def _fix_parent_feat(us_index: dict[str, dict], n: int, module_name: str) -> list[str]:
    """Correct 'Parent FEAT: {n}-{wrong}' in every US of this module.

    LLM analyst agents sometimes guess the database name instead of the module
    name for the 'Parent FEAT:' field (BUG-1: observed on NounouJob run,
    'parent-feat: 1-NounouJob' instead of '1-Contrat'). The assembler is the
    only component that knows the authoritative module name from inventory, so it
    fixes the US files in-place after loading the US index.
    """
    expected = f"{n}-{module_name}"
    fixed: list[str] = []
    for entry in us_index.values():
        path: Path = entry["path"]
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text = _PARENT_FEAT_RE.sub(
            lambda m: m.group(1) + expected
            if m.group(2).strip() != expected else m.group(0),
            text,
        )
        if new_text != text:
            path.write_text(new_text, encoding="utf-8", newline="")
            fixed.append(str(path))
    return fixed


def build_module_feat(
    unit: dict, *, n: int, project: str, db_type: str,
    us_index: dict[str, dict] | None = None,
) -> tuple[str, dict[str, list[str]]]:
    """Render the FEAT and the FEAT→US coverage map.

    The second return value is `{fqName: [SFD-i, FD-i, AC-i]}` — the IDs each US
    covers, which is what `Covers:` needs (C3) and what `validate_readiness`
    checks for.
    """
    us_index = us_index or {}
    name = unit["suggestedName"]
    language = unit.get("language", "tsql")
    conf = unit.get("confidenceEstimate", "high")
    procs = unit.get("procedures", [])
    sources = sorted({p.get("evidence", "").split(":")[0] for p in procs if p.get("evidence")})
    coverage: dict[str, list[str]] = {p["fqName"]: [] for p in procs}

    analysed = sum(1 for p in procs
                   if us_index.get(p["fqName"], {}).get("extraction") == "analyzed")
    templated = sum(1 for p in procs
                    if us_index.get(p["fqName"], {}).get("extraction") == "templated")

    L: list[str] = []
    L.append("---")
    L.append("generated-by: sdd-reverse")
    L.append(f"legacy-sources: [{', '.join(sources[:10])}]")
    L.append(f"confidence: {conf}")
    L.append(f"extraction-date: {_now()}")
    L.append(f"language-detected: {language}")
    L.append(f"source-unit: {unit['id']}")
    # C2 — make the provenance of the FEAT auditable: how many of its capabilities
    # were LLM-analysed vs templated. Previously unknowable from the artifact.
    L.append(f"us-analyzed: {analysed}")
    L.append(f"us-templated: {templated}")
    L.append("---")
    L.append("")
    L.append(f"# FEAT {n} — {name} (reverse objets SQL `{project}`)")
    L.append("")
    L.append(_gate(conf))
    L.append("")
    banner = (
        f"> ⚠️ FEAT générée par reverse engineering des objets SQL "
        f"({db_type}). Module `{name}` = {len(procs)} objet(s) SQL. "
        f"Chaque objet = 1 User Story. Lecture seule de la base."
    )
    if conf != "high":
        banner += (
            f" **Confidence {conf}** — revue humaine requise avant `/sdd-full` "
            f"(SQL dynamique ou objet chiffré détectés)."
        )
    if templated and not analysed:
        banner += (
            f" **{templated} US sur {len(procs)} sont des gabarits déterministes "
            f"non analysés** — relire avant de coder."
        )
    L.append(banner)
    L.append("")

    L.append("## Actors")
    L.append("")
    L.append("- **Utilisateur métier** — déclenche les opérations du module via l'application cible.")
    L.append("- **Équipe data / DBA** — détient les objets SQL legacy reversés (lecture seule).")
    L.append("")

    L.append("## Functional Needs")
    L.append("")
    L.append(
        f"- SFD-1: Le module `{name}` doit offrir les capacités encapsulées par "
        f"ses {len(procs)} objet(s) SQL legacy. {_ev(sources[0] + ':1' if sources else None, conf)}"
        f"{_covers_all(n, procs, us_index)}"
    )
    # SFD-1 is the module-level umbrella need: no single US delivers it, they all
    # contribute to it. It must therefore be covered by EVERY US of the module —
    # otherwise it stays an orphan and `validate_readiness` blocks /sdd-full on a
    # need that is in fact fully covered (caught by the readiness-gate test).
    for p in procs:
        coverage[p["fqName"]].append("SFD-1")
    sfd = 2
    for p in procs:
        us = us_index.get(p["fqName"], {})
        verb = _VERB_LABEL.get(p.get("verb") or "", "exécuter")
        # C2 — the US title (written by the analyst when the object was complex)
        # is the business phrasing; the verb is the fallback when no US exists.
        capability = us.get("title") or f"**{verb}** via `{p['fqName']}`"
        L.append(
            f"- SFD-{sfd}: Permettre de {capability} "
            f"(US {n}-{p['usIndex']}). {_ev(p.get('evidence'), p.get('confidence', conf))}"
            f"{_covers_us(n, p, us_index)}"
        )
        coverage[p["fqName"]].append(f"SFD-{sfd}")
        sfd += 1
    L.append("")

    L.append("## Functional Deliverables")
    L.append("")
    for i, p in enumerate(procs, start=1):
        us = us_index.get(p["fqName"], {})
        params_hint = ""
        tw = p.get("tablesWritten") or []
        tr = p.get("tablesRead") or []
        if tw:
            params_hint = f" — écrit {', '.join(tw[:5])}"
        elif tr:
            params_hint = f" — lit {', '.join(tr[:5])}"
        flags = []
        if p.get("hasTransaction"):
            flags.append("transactionnelle")
        if p.get("dynamicSql"):
            flags.append("SQL dynamique")
        if p.get("encrypted"):
            flags.append("chiffrée")
        if us.get("extraction") == "analyzed":
            flags.append(f"analysée, {us.get('acCount', 0)} AC")
        elif us.get("extraction") == "templated":
            flags.append("gabarit non analysé")
        fl = f" [{', '.join(flags)}]" if flags else ""
        title = f" « {us['title']} »" if us.get("title") else ""
        L.append(
            f"- FD-{i}: Reproduire le comportement de la {_kind_label(p)} "
            f"`{p['fqName']}`{title}{params_hint}{fl} "
            f"→ User Story `{n}-{p['usIndex']}-{p['usName']}`. "
            f"{_ev(p.get('evidence'), p.get('confidence', conf))}"
            f"{_covers_us(n, p, us_index)}"
        )
        coverage[p["fqName"]].append(f"FD-{i}")
    L.append("")

    L.append("## Business Rules")
    L.append("")
    br = 1
    any_br = False
    for p in procs:
        if p.get("raises"):
            L.append(
                f"- BR-{br}: `{p['fqName']}` applique des préconditions/erreurs "
                f"({', '.join(p['raises'])}) — à préserver. {_ev(p.get('evidence'), p.get('confidence', conf))}"
                f"{_covers_us(n, p, us_index)}"
            )
            coverage[p["fqName"]].append(f"BR-{br}")
            br += 1
            any_br = True
        if p.get("hasTransaction"):
            L.append(
                f"- BR-{br}: `{p['fqName']}` est atomique (transaction explicite) — "
                f"tout-ou-rien à préserver. {_ev(p.get('evidence'), p.get('confidence', conf))}"
                f"{_covers_us(n, p, us_index)}"
            )
            coverage[p["fqName"]].append(f"BR-{br}")
            br += 1
            any_br = True
    if not any_br:
        L.append(
            f"- BR-1: Le comportement métier est porté par les objets SQL du module ; "
            f"aucune règle transverse explicite détectée. {_ev(sources[0] + ':1' if sources else None, conf)}"
            f"{_covers_all(n, procs, us_index)}"
        )
        # Same umbrella logic as SFD-1: a module-level rule is carried by all its
        # US, so none of them may leave it orphan.
        for p in procs:
            coverage[p["fqName"]].append("BR-1")
    L.append("")

    L.append("## Acceptance Criteria")
    L.append("")
    for i, p in enumerate(procs, start=1):
        verb = _VERB_LABEL.get(p.get("verb") or "", "exécuter")
        tw = p.get("tablesWritten") or []
        us_ac = us_index.get(p["fqName"], {})
        # BUG-3: "le résultat attendu est retourné" is non-verifiable and useless as
        # an AC. Use the LLM title when available; fall back to a type-aware phrase.
        if tw:
            effect = f"les données de {', '.join(tw[:3])} reflètent l'opération"
        elif us_ac.get("title"):
            effect = f"le comportement attendu de « {us_ac['title']} » est reproduit"
        else:
            effect = f"la {_kind_label(p)} `{p['fqName']}` retourne le résultat attendu sans erreur"
        L.append(
            f"- AC-{i}: Given le module `{name}` en place, when on appelle "
            f"l'équivalent de `{p['fqName']}` ({verb}), then {effect}. "
            f"{_ev(p.get('evidence'), p.get('confidence', conf))}"
            f"{_covers_us(n, p, us_index)}"
        )
        coverage[p["fqName"]].append(f"AC-{i}")
    L.append("")

    L.append("## Project Config")
    L.append("")
    L.append(f"<!-- à compléter par le Tech Lead : stack cible, ORM, stratégie objets SQL ({db_type}) -->")
    L.append("")
    return "\n".join(L), coverage


# --------------------------------------------------------------------------- #
# M5 — never clobber a human review
# --------------------------------------------------------------------------- #

def _fingerprint(body: str) -> str:
    """Hash of the FEAT body EXCLUDING the fingerprint line itself."""
    stripped = "\n".join(
        line for line in body.splitlines()
        if not line.startswith(f"{_FINGERPRINT_KEY}:")
    )
    return hashlib.sha256(stripped.encode("utf-8")).hexdigest()[:16]


def _stamp(body: str) -> str:
    """Insert the fingerprint into the frontmatter of a freshly generated FEAT."""
    fp = _fingerprint(body)
    lines = body.splitlines()
    # Frontmatter opens on line 0 with '---'; place the key right after it.
    if lines and lines[0].strip() == "---":
        lines.insert(1, f"{_FINGERPRINT_KEY}: {fp}")
    return "\n".join(lines)


def human_edited(path: Path) -> bool:
    """True if the file on disk diverges from the fingerprint it was stamped with.

    No fingerprint at all → treated as human-owned too: a FEAT written before
    this guard existed must not be silently replaced either.

    BUG-2 exception: a FEAT that was stamped before its US existed (both
    us-analyzed and us-templated are 0) carries a fingerprint that locks in
    empty content. Once US are available the assembler must be allowed to
    regenerate it — otherwise the race condition between rung 1 and rung 2
    permanently blocks the pipeline.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.search(rf"^{_FINGERPRINT_KEY}:\s*([0-9a-f]+)\s*$", text, re.MULTILINE)
    if not m:
        return True
    # Allow regeneration when the stamped FEAT had no US content yet.
    if (re.search(r"^us-analyzed:\s*0\s*$", text, re.MULTILINE) and
            re.search(r"^us-templated:\s*0\s*$", text, re.MULTILINE)):
        return False
    return _fingerprint(text) != m.group(1)


# --------------------------------------------------------------------------- #
# C3 — write FEAT→US traceability into the User Stories
# --------------------------------------------------------------------------- #

def backfill_covers(
    us_path: Path, ids: list[str], *, feat_hash: str | None = None,
) -> bool:
    """Write `Covers:` into a US and resolve its Parent FEAT hash sentinel.

    Returns True when the file changed. Idempotent: re-running with the same IDs
    rewrites the same content.
    """
    try:
        text = us_path.read_text(encoding="utf-8")
    except OSError:
        return False
    original = text

    covers_body = "\n" + "\n".join(f"- {i}" for i in ids) + "\n\n" if ids else "\n"
    if _COVERS_SECTION_RE.search(text):
        text = _COVERS_SECTION_RE.sub(
            lambda m: m.group(1) + covers_body, text, count=1)
    else:
        # No Covers section (hand-written US, or an older template) — append one
        # rather than silently skipping the traceability the readiness gate needs.
        text = text.rstrip("\n") + "\n\n## Covers\n" + covers_body

    if feat_hash:
        text = text.replace(HASH_SENTINEL, f"sha256:{feat_hash}")

    if text == original:
        return False
    # newline='' keeps the file's own line endings (no CRLF injection on Windows).
    us_path.write_text(text, encoding="utf-8", newline="")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic FEAT assembler for db-reverse.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", default="workspace")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--unit", help="single unit U-N")
    g.add_argument("--all", action="store_true", help="every module/unit")
    ap.add_argument("--force", action="store_true",
                    help="overwrite a FEAT even if it was edited by a human (M5)")
    ap.add_argument("--no-covers", action="store_true",
                    help="skip the Covers back-fill in the US files")
    ap.add_argument("--stamp", action="store_true",
                    help="(GAP-1) add generated-fingerprint to existing sdd-reverse FEATs "
                         "that lack one (e.g. written by reverse-sql-feat-composer). "
                         "Content is unchanged; the stamp enables M5 protection on re-runs.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)

    # GAP-1: --stamp mode adds missing fingerprints to existing sdd-reverse FEATs.
    # Runs before inventory loading (independent of module selection).
    if getattr(args, "stamp", False):
        stamped: list[str] = []
        feats_dir_stamp = ws / "feats"
        for feat_path in sorted(feats_dir_stamp.glob("*.md")):
            try:
                text = feat_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if "generated-by: sdd-reverse" not in text:
                continue
            if re.search(rf"^{_FINGERPRINT_KEY}:\s*[0-9a-f]+\s*$", text, re.MULTILINE):
                continue  # already stamped
            stamped_text = _stamp(text)
            atomic_write_text(feat_path, stamped_text)
            stamped.append(feat_path.name)
        if args.json:
            print(json.dumps({"stamped": stamped}, ensure_ascii=False, indent=2))
        else:
            print(f"[REVERSE] --stamp: {len(stamped)} FEAT(s) estampillée(s) (M5 activé).")
        return 0

    inv_path = ws / "old" / args.project / ".sys" / "inventory.json"
    try:
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: build_proc_feats — inventory missing\nCAUSE: [REVERSE_UNIT_NOT_FOUND] {exc}",
              file=sys.stderr)
        return 2

    feats_dir = ws / "feats"
    feats_dir.mkdir(parents=True, exist_ok=True)
    us_dir = ws / "us"
    db_type = inventory.get("databaseType", "SqlServer")
    units = inventory.get("units", [])
    if args.unit:
        units = [u for u in units if u["id"] == args.unit]
        if not units:
            print(f"ERROR: build_proc_feats\nCAUSE: [REVERSE_UNIT_NOT_FOUND] {args.unit}", file=sys.stderr)
            return 2

    # BUG-2 — Orchestration barrier: refuse to assemble a FEAT when LLM-routed
    # objects are still missing their US (rung 1 not finished yet). --force skips
    # the barrier (useful for debugging or re-runs where some US are intentionally
    # absent). The check uses the `tier` field stored by the orchestrator in each
    # procedure record: tier=none objects are deterministic and never produce a US.
    if not args.force:
        missing_us: list[str] = []
        for u in units:
            n_pre = inventory["_featAllocations"][u["id"]]
            for p in u.get("procedures", []):
                if (p.get("tier") or "none") == "none":
                    continue
                expected_us = us_dir / f"{n_pre}-{p['usIndex']}-{p['usName']}.md"
                if not expected_us.is_file():
                    missing_us.append(p["fqName"])
        if missing_us:
            print(
                f"ERROR: build_proc_feats — barrière rung 1→2, {len(missing_us)} US manquante(s)\n"
                f"CAUSE: [REVERSE_FEAT_VALIDATE_FAILED] objets sans US : "
                + ", ".join(missing_us[:6]) + (" …" if len(missing_us) > 6 else "") + "\n"
                f"FIX: attendre la fin des agents rung 1, "
                f"puis relancer build_proc_feats.py (--force pour bypasser)",
                file=sys.stderr,
            )
            return 5

    written: list[str] = []
    preserved: list[str] = []
    covers_updated: list[str] = []
    parent_feat_fixed: list[str] = []
    for u in units:
        n = inventory["_featAllocations"][u["id"]]
        procs = u.get("procedures", [])
        us_index = read_us_index(us_dir, n, procs)
        # BUG-1: correct 'Parent FEAT:' lines that LLM agents wrote incorrectly.
        parent_feat_fixed.extend(_fix_parent_feat(us_index, n, u["suggestedName"]))
        feat, coverage = build_module_feat(
            u, n=n, project=args.project, db_type=db_type, us_index=us_index)
        out = feats_dir / f"{n}-{u['suggestedName']}.md"

        if out.exists() and not args.force and human_edited(out):
            preserved.append(str(out))
        else:
            atomic_write_text(out, _stamp(feat))
            written.append(str(out))

        if not args.no_covers:
            feat_hash = hashlib.sha256(out.read_bytes()).hexdigest()[:8]
            for p in procs:
                us = us_index.get(p["fqName"])
                if not us:
                    continue
                if backfill_covers(us["path"], coverage.get(p["fqName"], []),
                                   feat_hash=feat_hash):
                    covers_updated.append(str(us["path"]))

    if args.json:
        print(json.dumps({"written": written, "preserved": preserved,
                          "coversUpdated": covers_updated,
                          "parentFeatFixed": parent_feat_fixed},
                         ensure_ascii=False, indent=2))
    else:
        extra = ""
        if covers_updated:
            extra += f" · {len(covers_updated)} US tracées (Covers + hash)"
        if parent_feat_fixed:
            extra += f" · {len(parent_feat_fixed)} US corrigées (Parent FEAT)"
        if preserved:
            extra += f" · {len(preserved)} FEAT préservée(s) (édition humaine, --force pour écraser)"
        print(f"[REVERSE] {len(written)} FEAT(s) module assemblée(s) depuis les US "
              f"+ l'inventaire{extra}.")
    # A preserved FEAT is not a failure, but the caller must be able to notice.
    return 4 if preserved and not written else 0


if __name__ == "__main__":
    raise SystemExit(main())
