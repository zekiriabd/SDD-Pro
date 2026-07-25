#!/usr/bin/env python3
"""generate_specbook.py — assemble the human "Cahier des charges" (.docx + .md).

Role (v7.0.0 audit reverse-quality 2026-07-24)
----------------------------------------------
Deterministic, 0-token renderer that turns every FEAT under ``workspace/feats/``
into a single Word document written for a NON-technical reader (a manager /
"gérant"): plain functional language, technical parts vulgarised. It is the
render half of a two-part feature; the reasoning half (rewriting terse
SFD/BR/AC bullets into human prose) is done by the ``specbook-writer`` agent,
which caches one humanised section per FEAT under
``workspace/docs/.sys/sections/{feat-id}.md``.

Two operating modes, both always produce a valid document:
  * **humanised** — a fresh cached section exists for the FEAT (hash matches the
    current FEAT content) → its plain-language prose is rendered.
  * **raw fallback** — no cache / stale cache → the FEAT's own bullets are
    rendered as-is and the chapter is flagged "à humaniser". This guarantees the
    book is never empty or broken just because the LLM step has not run yet.

Idempotence: the whole book is rebuilt from the glob on every run (like
``index_adrs.py`` rebuilds INDEX.md). The ``.docx`` payload is byte-stable for
identical inputs (see ``sdd_lib.docx_writer``), and a sibling ``.md`` mirror is
emitted for git-friendly diffing.

Outputs (under ``workspace/docs/``):
  * ``cahier-des-charges.docx``  — the Word deliverable
  * ``cahier-des-charges.md``    — markdown mirror (review / diff)
  * ``.sys/specbook-manifest.json`` — per-FEAT hash + mode (drives the agent)

Exit codes: 0 ok · 2 no FEAT found · 3 I/O error.

Zero third-party dependency (SDD_Pro ``dependencies = []`` policy).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --- sys.path bootstrap so the script runs via `python .sdd/python/...` ---
_HERE = Path(__file__).resolve()
_PYROOT = _HERE.parent.parent  # .sdd/python
if str(_PYROOT) not in sys.path:
    sys.path.insert(0, str(_PYROOT))

from sdd_lib.docx_writer import DocxBuilder  # noqa: E402
from sdd_lib.exit_codes import SUCCESS, FAIL_FAST, INFRA_BLOCKED  # noqa: E402
from sdd_lib.markdown_io import parse_frontmatter, section_body  # noqa: E402

# Ordered functional sections we lift verbatim from a FEAT for the raw fallback.
_LIST_SECTIONS = [
    ("Actors", "Acteurs concernés"),
    ("Functional Needs", "Ce que le système doit permettre"),
    ("Business Rules", "Règles de gestion"),
    ("Acceptance Criteria", "Comment on saura que c'est réussi"),
    ("Functional Deliverables", "Ce qui est livré"),
    ("Out of Scope", "Ce qui n'est pas inclus"),
]

# Humanised section headings the agent MUST emit (order = rendering order).
_HUMAN_SECTIONS = [
    "Résumé",
    "À quoi ça sert",
    "Qui l'utilise",
    "Ce que le système doit permettre",
    "Règles de gestion",
    "Comment on saura que c'est réussi",
    "Ce qui est livré",
    "Ce qui n'est pas inclus",
    "Note technique (vulgarisée)",
]

_ID_PREFIX_RE = re.compile(r"^\s*[-*]\s*(?:[A-Z]{1,5}-\d+\s*:\s*)?(.*\S)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


def feat_hash(text: str) -> str:
    """Content hash used to detect when a cached humanised section is stale."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class FeatSpec:
    path: Path
    feat_id: str
    name: str
    status: str
    content_hash: str
    context: str = ""
    objective: str = ""
    sections: dict[str, list[str]] = field(default_factory=dict)
    is_reverse: bool = False
    confidence: str = ""  # reverse only: high|medium|low


def _clean_bullets(body: str | None, keep_ids: bool = False) -> list[str]:
    if not body:
        return []
    out: list[str] = []
    for line in body.splitlines():
        if keep_ids:
            m = _BULLET_RE.match(line)
        else:
            m = _ID_PREFIX_RE.match(line) if _BULLET_RE.match(line) else None
        if m:
            val = m.group(1).strip()
            if val and not val.startswith("<"):  # skip template placeholders
                out.append(val)
    return out


def _first_paragraph(body: str | None) -> str:
    if not body:
        return ""
    lines = [ln.strip() for ln in body.strip().splitlines() if ln.strip()]
    prose = [ln for ln in lines if not ln.startswith(("-", "*", "<", "#"))]
    return " ".join(prose).strip()


def parse_feat(path: Path) -> FeatSpec:
    text = path.read_text(encoding="utf-8", errors="replace")
    h = feat_hash(text)

    # FEAT ID / name / status (frontmatter-less FEATs use body lines).
    fid = ""
    m = re.search(r"^FEAT ID:\s*(.+)$", text, re.MULTILINE)
    if m:
        fid = m.group(1).strip()
    name = ""
    m = re.search(r"^#\s*FEAT:\s*(.+)$", text, re.MULTILINE)
    if m:
        name = m.group(1).strip()
    if not fid:
        # derive from filename {n}-{Name}
        fid = path.stem
    if not name:
        name = re.sub(r"^\d+-", "", path.stem).replace("-", " ")
    status = ""
    m = re.search(r"^Status:\s*(.+)$", text, re.MULTILINE)
    if m:
        status = m.group(1).strip()

    is_reverse = "REVERSE-GATE" in text or "[REV]" in text or "reverse" in text.lower()[:400]
    confidence = ""
    m = re.search(r"REVERSE-GATE:.*?confidence\s*=\s*(\w+)", text)
    if m:
        confidence = m.group(1).strip().lower()
    else:
        fm = parse_frontmatter(text)
        if fm and "confidence" in fm[0]:
            confidence = fm[0]["confidence"].strip().lower()

    spec = FeatSpec(
        path=path, feat_id=fid, name=name, status=status, content_hash=h,
        is_reverse=is_reverse, confidence=confidence,
    )
    spec.context = _first_paragraph(section_body(text, "Context"))
    spec.objective = _first_paragraph(section_body(text, "Objective"))
    for heading, _label in _LIST_SECTIONS:
        spec.sections[heading] = _clean_bullets(section_body(text, heading))
    return spec


def load_humanised(feat_id: str, content_hash: str, sections_dir: Path) -> dict | None:
    """Return {heading: [lines]} for a fresh cached section, else None."""
    p = sections_dir / f"{feat_id}.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    if not fm:
        return None
    meta, _body = fm
    if meta.get("feat_hash") != content_hash:
        return None  # stale — FEAT changed since humanisation
    out: dict[str, list[str] | str] = {}
    for heading in _HUMAN_SECTIONS:
        body = section_body(text, heading)
        if body is None:
            continue
        bullets = _clean_bullets(body, keep_ids=True)
        out[heading] = bullets if bullets else _first_paragraph(body)
    return out


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

_CONF_LABEL = {
    "high": "élevée", "medium": "moyenne", "low": "faible",
}


def _render_chapter(doc: DocxBuilder, spec: FeatSpec, human: dict | None, idx: int) -> str:
    """Render one FEAT chapter. Returns the mode used ('humanised'|'raw')."""
    doc.heading(f"{idx}. {spec.name}", level=1)
    meta_rows = [["Identifiant", spec.feat_id], ["Statut", spec.status or "—"]]
    if spec.is_reverse:
        meta_rows.append(["Origine", "Rétro-ingénierie (code/BD existant)"])
        if spec.confidence:
            meta_rows.append(
                ["Niveau de confiance", _CONF_LABEL.get(spec.confidence, spec.confidence)]
            )
    else:
        meta_rows.append(["Origine", "Spécification neuve"])
    doc.table(meta_rows)

    if spec.is_reverse and spec.confidence and spec.confidence != "high":
        doc.callout(
            "Cette fonctionnalité a été reconstituée à partir d'un système existant ; "
            "certains éléments demandent une validation humaine avant réalisation.",
            label="À valider",
        )

    if human:
        for heading in _HUMAN_SECTIONS:
            if heading not in human:
                continue
            val = human[heading]
            doc.heading(heading, level=2)
            if isinstance(val, list):
                doc.bullet_list(val)
            elif val:
                doc.paragraph(val)
        return "humanised"

    # -- raw fallback -------------------------------------------------------
    doc.callout(
        "Rédaction fonctionnelle simplifiée non encore générée pour cette "
        "fonctionnalité — le texte ci-dessous reprend la spécification brute.",
        label="À humaniser",
    )
    if spec.context:
        doc.heading("Contexte", level=2)
        doc.paragraph(spec.context)
    if spec.objective:
        doc.heading("À quoi ça sert", level=2)
        doc.paragraph(spec.objective)
    for heading, label in _LIST_SECTIONS:
        items = spec.sections.get(heading) or []
        if items:
            doc.heading(label, level=2)
            doc.bullet_list(items)
    return "raw"


def build_book(feats: list[FeatSpec], sections_dir: Path, project: str) -> tuple[bytes, str, list[dict]]:
    doc = DocxBuilder()
    doc.title("Cahier des charges", subtitle=f"{project} — spécifications fonctionnelles")
    doc.paragraph(
        "Ce document décrit, en langage clair et sans prérequis technique, "
        "l'ensemble des fonctionnalités du projet : à quoi chacune sert, qui "
        "l'utilise, les règles à respecter et la manière de vérifier qu'elle "
        "fonctionne. Il est régénéré à chaque nouvelle fonctionnalité ou analyse."
    )
    # Summary table.
    doc.heading("Sommaire des fonctionnalités", level=1)
    summary = [["#", "Fonctionnalité", "Statut", "Origine"]]
    for i, s in enumerate(feats, 1):
        origin = "Rétro-ingénierie" if s.is_reverse else "Neuve"
        summary.append([str(i), s.name, s.status or "—", origin])
    doc.table(summary, header=True)
    doc.page_break()

    manifest: list[dict] = []
    md_lines = [f"# Cahier des charges — {project}", ""]
    for i, s in enumerate(feats, 1):
        human = load_humanised(s.feat_id, s.content_hash, sections_dir)
        mode = _render_chapter(doc, s, human, i)
        if i < len(feats):
            doc.page_break()
        manifest.append({
            "feat_id": s.feat_id, "name": s.name, "hash": s.content_hash,
            "mode": mode, "is_reverse": s.is_reverse, "confidence": s.confidence,
        })
        md_lines += [f"## {i}. {s.name}", "", f"- Identifiant : {s.feat_id}",
                     f"- Statut : {s.status or '—'}", f"- Rédaction : {mode}", ""]
    return doc.to_bytes(), "\n".join(md_lines) + "\n", manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the human Cahier des charges (.docx + .md).")
    ap.add_argument("--feats-dir", default="workspace/feats")
    ap.add_argument("--out-dir", default="workspace/docs")
    ap.add_argument("--project", default=None, help="Project name for the cover page.")
    ap.add_argument("--json", action="store_true", help="Emit machine JSON result on stdout.")
    ap.add_argument("--print-hash", metavar="FEAT", default=None,
                    help="Print the content hash of a single FEAT file and exit "
                         "(used by specbook-writer to stamp its cached section).")
    args = ap.parse_args(argv)

    if args.print_hash:
        try:
            print(feat_hash(Path(args.print_hash).read_text(encoding="utf-8", errors="replace")))
            return SUCCESS
        except OSError as exc:
            print(f"ERROR: cannot read FEAT\nCAUSE: [NOT_FOUND] {exc}\nFIX: check path", file=sys.stderr)
            return FAIL_FAST

    feats_dir = Path(args.feats_dir)
    out_dir = Path(args.out_dir)
    sections_dir = out_dir / ".sys" / "sections"

    feat_paths = sorted(
        feats_dir.glob("*.md"),
        key=lambda p: (int(re.match(r"(\d+)", p.stem).group(1)) if re.match(r"(\d+)", p.stem) else 9999, p.stem),
    )
    if not feat_paths:
        msg = "ERROR: no FEAT found\nCAUSE: [FEAT_NOT_FOUND] no *.md under %s\nFIX: run /feat-generate first" % feats_dir
        print(msg, file=sys.stderr)
        return FAIL_FAST

    try:
        feats = [parse_feat(p) for p in feat_paths]
        project = args.project or Path.cwd().name
        docx_bytes, md_text, manifest = build_book(feats, sections_dir, project)

        out_dir.mkdir(parents=True, exist_ok=True)
        sections_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "cahier-des-charges.docx"
        md_path = out_dir / "cahier-des-charges.md"
        man_path = out_dir / ".sys" / "specbook-manifest.json"
        man_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic-ish writes.
        tmp = docx_path.with_suffix(".docx.tmp")
        tmp.write_bytes(docx_bytes)
        import os
        os.replace(tmp, docx_path)
        md_path.write_text(md_text, encoding="utf-8")
        man_path.write_text(json.dumps({"feats": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: specbook write failed\nCAUSE: [DISK] {exc}\nFIX: check {out_dir} is writable", file=sys.stderr)
        return INFRA_BLOCKED

    n_raw = sum(1 for m in manifest if m["mode"] == "raw")
    n_hum = len(manifest) - n_raw
    if args.json:
        print(json.dumps({"feats_total": len(manifest), "humanised": n_hum,
                          "raw": n_raw, "docx": str(docx_path)}, ensure_ascii=False))
    else:
        note = f" ({n_raw} à humaniser)" if n_raw else ""
        print(f"OK generate_specbook — cahier-des-charges.docx ({len(manifest)} fonctionnalités, {n_hum} humanisées{note})")
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
