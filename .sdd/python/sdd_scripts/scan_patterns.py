#!/usr/bin/env python3
"""SDD_Pro: scan_patterns — exécute les catalogues de patterns (0 token LLM).

Audit 2026-08-28, corrections #2 (câblage) et #6 (déterministe vs LLM).
--------------------------------------------------------------------------

`python/security_patterns.yaml` (333 L, 23 classes OWASP dont 8 hard-blocking)
et `python/code_review_patterns.yaml` (134 L, 12 classes) existaient avec CWE,
sévérités et regex compilables — et AUCUN consommateur runtime. Les tests
vérifiaient leur cohérence documentaire ; la détection, elle, était confiée à
un LLM lisant la version en prose du même catalogue dans le prompt de l'agent.

Le YAML l'annonçait lui-même : « future v7.0.1 will switch the agent to read
this YAML at runtime ». Ce script est ce basculement.

Ce que ça change, concrètement
------------------------------

Détecter `AKIA[0-9A-Z]{16}` est le cas d'école du déterministe. Le confier à
un modèle sur un contexte de plusieurs dizaines de milliers de tokens donne un
rappel inconnu, non reproductible d'un run à l'autre, et payant. Ici : rappel
de 100 % sur les patterns du catalogue, résultat identique à chaque exécution,
coût nul.

Le LLM ne disparaît pas — il change de poste. Il passe de **détecteur** à
**trieur** : écarter les faux positifs, juger l'exploitabilité, traiter ce que
la regex ne peut pas voir. C'est là qu'il a un avantage réel.

La frontière est d'ailleurs déjà tracée par le catalogue lui-même, et elle est
honnête : sur 23 classes de sécurité, **11 sont exécutables ici** et **12 ne le
sont pas** — `[SEC_BROKEN_AUTHN]`, `[SEC_IDOR]`, `[SEC_SSRF_RISK]`,
`[SEC_JWT_MISCONFIG]`… Ce sont exactement les classes qui
exigent de comprendre un flux, pas de reconnaître une forme. Le script les
déclare `llm_only` dans son manifeste au lieu de faire semblant de les couvrir :
un scan qui prétend à l'exhaustivité qu'il n'a pas est plus dangereux qu'un
scan partiel qui borne son périmètre.

Anti-patterns
-------------

4 patterns portent `anti_pattern: true` (« le point d'entrée du framework est
présent, donc la protection est requise »). Le catalogue ne déclare pas la
regex de la protection attendue — seulement un `hint` en prose. Ce script
supporte un champ `requires:` pour ça, et déclare `skipped_unscannable` toute
règle `anti_pattern` qui n'en a pas, au lieu de l'ignorer en silence. Ajouter
les `requires:` manquants relève du propriétaire du catalogue sécurité.

Usage
-----
    python -m sdd_scripts.scan_patterns --feat-number 1
    python -m sdd_scripts.scan_patterns --feat-number 1 --json
    python -m sdd_scripts.scan_patterns --feat-number 1 --catalog security
    python -m sdd_scripts.scan_patterns --feat-number 1 --path workspace/src/Api

Exit codes (sdd_lib.exit_codes + dérogation documentée)
    0 SUCCESS         scan effectué (verdict GREEN ou WARN)
    1 FAIL_FAST       argument invalide / catalogue illisible
    3 INFRA_BLOCKED   échec d'écriture console.db
    4 verdict RED     (dérogation, même sémantique que ingest_axe/ingest_lighthouse :
                      le code est présent et scannable, c'est le RÉSULTAT qui est
                      rouge — un caller CI doit pouvoir distinguer des deux)
                      neutralisable par --no-fail
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.config_loader import ConfigError, load_yaml  # noqa: E402
from sdd_lib.console_safe import ensure_console_safe  # noqa: E402
from sdd_lib.console_db import (  # noqa: E402
    connect,
    ensure_initialized,
    insert_qa_code_review_batch,
    insert_qa_security_batch,
    record_auditor_run,
    replace_qa_auditor_for_feat,
)
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.paths import iso_now_ms, normalize, repo_root, workspace_root  # noqa: E402

INFRA_BLOCKED = 3
VERDICT_RED_EXIT = 4

#: Producteur de findings (colonne `detector`, schema v8). Le scan ne remplace
#: que ses propres lignes ; celles des reviewers LLM (`'agent'`) coexistent.
DETECTOR = "deterministic"

# --------------------------------------------------------------------------- #
# Périmètre de fichiers — aligné sur quality_scan.py (même corpus, même
# exclusions) pour qu'un findings « file:line » soit comparable entre les deux.
# --------------------------------------------------------------------------- #

SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".cs", ".razor", ".cshtml", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".vue", ".py", ".kt", ".kts", ".java", ".json", ".yml", ".yaml", ".config",
)

EXCLUDE_DIRS: tuple[str, ...] = (
    "bin", "obj", "node_modules", ".vs", ".git", "dist", "build", "coverage",
    "TestResults", ".angular", "_framework", "__pycache__", ".venv", "venv",
)

#: `lang` du catalogue → extensions. `any` = tout le corpus.
LANG_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "any": SOURCE_EXTENSIONS,
    "csharp": (".cs", ".razor", ".cshtml"),
    "node": (".ts", ".js", ".mjs", ".cjs"),
    "react": (".tsx", ".jsx"),
    "vue": (".vue",),
    "python": (".py",),
    "jvm": (".java", ".kt", ".kts"),
    "kotlin": (".kt", ".kts"),
    "java": (".java",),
}

SEVERITY_ORDER = ("info", "minor", "moderate", "serious", "critical", "blocker")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}

CATALOGS: dict[str, dict[str, str]] = {
    "security": {
        "yaml": "security_patterns.yaml",
        "table": "qa_security",
        "auditor": "security",
        "fail_on_key": "SecurityFailOn",
    },
    "code-review": {
        "yaml": "code_review_patterns.yaml",
        "table": "qa_code_review",
        "auditor": "code-review",
        "fail_on_key": "CodeReviewFailOn",
    },
}

#: Longueur max d'une ligne rendue dans le message d'un finding. Une ligne
#: minifiée de 400 KB ne doit pas atterrir dans console.db.
SNIPPET_MAX = 160


# --------------------------------------------------------------------------- #
# Chargement des catalogues
# --------------------------------------------------------------------------- #

def catalog_path(name: str, root: Path) -> Path:
    return root / ".sdd" / "python" / CATALOGS[name]["yaml"]


def load_catalog(name: str, root: Path) -> dict[str, Any]:
    """Charge un catalogue et pré-compile ses regex.

    Une regex non compilable est écartée avec sa raison plutôt que de faire
    échouer le scan entier : un catalogue partiellement cassé doit encore
    protéger sur ses classes saines. `test_security_patterns.py` garantit par
    ailleurs que toutes compilent — cette tolérance est une ceinture, pas une
    excuse.
    """
    data = load_yaml(catalog_path(name, root))
    classes: list[dict[str, Any]] = []
    llm_only: list[str] = []
    degraded: list[str] = []
    unscannable: list[dict[str, str]] = []
    bad_regex: list[dict[str, str]] = []

    for cls in data.get("classes") or []:
        prefix = cls.get("prefix") or ""
        patterns = cls.get("patterns") or []
        if not patterns:
            llm_only.append(prefix)
            continue
        compiled: list[dict[str, Any]] = []
        for pat in patterns:
            if pat.get("anti_pattern") and not pat.get("requires"):
                unscannable.append({
                    "class": prefix,
                    "reason": "anti_pattern sans `requires:` — la protection "
                              "attendue n'est pas déclarée en regex",
                    "hint": str(pat.get("hint") or ""),
                })
                continue
            try:
                rx = re.compile(pat["regex"])
            except (re.error, KeyError, TypeError) as exc:
                bad_regex.append({"class": prefix, "regex": str(pat.get("regex")),
                                  "error": str(exc)})
                continue
            req = None
            if pat.get("requires"):
                try:
                    req = re.compile(pat["requires"])
                except re.error as exc:
                    bad_regex.append({"class": prefix,
                                      "regex": str(pat.get("requires")),
                                      "error": f"requires: {exc}"})
                    continue
            compiled.append({
                "regex": rx,
                "requires": req,
                "anti_pattern": bool(pat.get("anti_pattern")),
                "lang": str(pat.get("lang") or "any"),
                "file_glob": pat.get("file_glob"),
                "hint": str(pat.get("hint") or ""),
            })
        if compiled:
            classes.append({
                "prefix": prefix,
                "severity": str(cls.get("severity") or "info").lower(),
                "hard_blocking": bool(cls.get("hard_blocking")),
                "owasp": cls.get("owasp"),
                "cwe": cls.get("cwe"),
                "description": str(cls.get("description") or ""),
                "patterns": compiled,
            })
        else:
            # La classe déclarait des patterns mais aucun n'est exécutable.
            # Ce n'est PAS la même chose qu'une classe sans regex : ici le
            # catalogue a une intention de détection déterministe qu'il ne
            # sait pas encore exprimer. Confondre les deux masquerait une
            # dette réparable derrière un « c'est du ressort du LLM ».
            degraded.append(prefix)

    return {
        "name": name,
        "classes": classes,
        "llm_only": sorted(llm_only),
        "degraded": sorted(set(degraded)),
        "skipped_unscannable": unscannable,
        "bad_regex": bad_regex,
    }


# --------------------------------------------------------------------------- #
# Périmètre
# --------------------------------------------------------------------------- #

def is_excluded(rel_path: str) -> bool:
    """Exclusion ancrée aux SEGMENTS de chemin, jamais en sous-chaîne.

    Reprend la correction de `quality_scan.py` : un `object_mapper.py` ne doit
    pas être exclu parce que son nom contient « obj ».
    """
    norm = rel_path.replace("\\", "/")
    padded = f"/{norm}/"
    return any(f"/{d}/" in padded for d in EXCLUDE_DIRS)


def iter_source_files(scan_root: Path, repo: Path) -> list[Path]:
    if not scan_root.is_dir():
        return []
    exts = set(SOURCE_EXTENSIONS)
    out: list[Path] = []
    for f in scan_root.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in exts:
            continue
        try:
            rel = normalize(str(f.relative_to(repo)))
        except ValueError:
            rel = normalize(str(f))
        if is_excluded(rel):
            continue
        out.append(f)
    return sorted(out)


def _pattern_applies(pat: dict[str, Any], path: Path, rel: str) -> bool:
    exts = LANG_EXTENSIONS.get(pat["lang"], SOURCE_EXTENSIONS)
    if path.suffix.lower() not in exts:
        return False
    glob = pat.get("file_glob")
    if glob:
        g = normalize(str(glob))
        if not (fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(path.name, Path(g).name)):
            return False
    return True


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #

def _snippet(line: str) -> str:
    s = line.strip()
    return s if len(s) <= SNIPPET_MAX else s[: SNIPPET_MAX - 1] + "…"


def scan_files(catalog: dict[str, Any], files: Iterable[Path], repo: Path) -> list[dict[str, Any]]:
    """Retourne la liste des findings, triée par sévérité décroissante puis chemin.

    Deux sémantiques de match cohabitent :

    - **normale** : chaque occurrence de la regex produit un finding avec sa
      ligne. Une même classe peut sortir plusieurs fois dans un fichier — c'est
      voulu, chaque site est à corriger.
    - **anti_pattern** : la regex marque un point d'entrée (`WebApplication.
      CreateBuilder`, `express()`) et `requires` la protection attendue. Le
      finding n'est émis que si le point d'entrée est présent ET la protection
      absente **du même fichier**, une seule fois par fichier. Le périmètre au
      fichier est une limite assumée : une protection déclarée dans un module
      voisin produirait un faux positif, ce que le triage LLM doit trancher.
    """
    findings: list[dict[str, Any]] = []
    file_cache: dict[Path, tuple[str, list[str]]] = {}

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        file_cache[path] = (text, lines)
        try:
            rel = normalize(str(path.relative_to(repo)))
        except ValueError:
            rel = normalize(str(path))

        for cls in catalog["classes"]:
            for pat in cls["patterns"]:
                if not _pattern_applies(pat, path, rel):
                    continue

                if pat["anti_pattern"]:
                    entry = pat["regex"].search(text)
                    if not entry or pat["requires"].search(text):
                        continue
                    findings.append(_finding(
                        cls, pat, rel,
                        line=text[: entry.start()].count("\n") + 1,
                        message=f"{cls['prefix'][1:-1]} — {pat['hint'] or cls['description']} "
                                f"(point d'entrée présent, protection absente du fichier)",
                    ))
                    continue

                for m in pat["regex"].finditer(text):
                    ln = text[: m.start()].count("\n") + 1
                    src = lines[ln - 1] if 0 < ln <= len(lines) else ""
                    findings.append(_finding(
                        cls, pat, rel, line=ln,
                        message=f"{pat['hint'] or cls['description']} — `{_snippet(src)}`",
                    ))

    findings = _dedupe(findings)
    findings.sort(key=lambda f: (
        -SEVERITY_RANK.get(f["severity"], 0), f["file_path"], f["line"] or 0
    ))
    return findings


def _dedupe(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Un finding par (classe, fichier, ligne) — la première occurrence gagne.

    Nécessaire parce qu'une même ligne peut satisfaire plusieurs fois la même
    classe. Cas réel : `var md5 = System.Security.Cryptography.MD5.Create();`
    matche deux fois `(?i)\\b(MD5|SHA-?1|DES|RC4|ECB)\\b` (le nom de variable
    ET l'appel). Deux lignes dans `qa_security` pour un seul défaut gonflent le
    compte de findings et faussent le verdict autant que le rapport humain.

    La déduplication est volontairement étroite : deux classes distinctes sur
    la même ligne restent deux findings (un secret en dur DANS une requête
    concaténée, c'est bien deux problèmes), et la même classe sur deux lignes
    différentes reste deux findings (deux sites à corriger).
    """
    seen: set[tuple[str, str, int]] = set()
    out: list[dict[str, Any]] = []
    for f in findings:
        key = (f["issue_class"], f["file_path"], f["line"] or 0)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _finding(cls: dict[str, Any], pat: dict[str, Any], rel: str, *,
             line: int, message: str) -> dict[str, Any]:
    return {
        "issue_class": cls["prefix"],
        "severity": cls["severity"],
        "hard_blocking": cls["hard_blocking"],
        "owasp": cls.get("owasp"),
        "cwe": cls.get("cwe"),
        "file_path": rel,
        "line": line,
        "message": message,
        "detector": "deterministic",
    }


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #

def compute_verdict(findings: list[dict[str, Any]], fail_on: str) -> tuple[str, list[str]]:
    """Retourne ``(verdict, raisons)`` avec ``verdict ∈ {GREEN, WARN, RED}``.

    Deux chemins vers le rouge, dans cet ordre de priorité :
      1. une classe `hard_blocking` a matché — RED quel que soit `fail_on` ;
      2. une sévérité ≥ `fail_on`.
    Sinon WARN s'il y a des findings, GREEN s'il n'y en a aucun. C'est la même
    arithmétique que celle appliquée aux verdicts d'agents, pour que le rapport
    consolidé n'ait pas deux échelles.
    """
    if not findings:
        return "GREEN", []
    reasons: list[str] = []
    hard = sorted({f["issue_class"] for f in findings if f["hard_blocking"]})
    if hard:
        reasons.append(f"classe(s) hard-blocking : {', '.join(hard)}")
    threshold = SEVERITY_RANK.get((fail_on or "critical").lower(), SEVERITY_RANK["critical"])
    over = sorted({f["issue_class"] for f in findings
                   if SEVERITY_RANK.get(f["severity"], 0) >= threshold})
    if over:
        reasons.append(f"sévérité ≥ {fail_on} : {', '.join(over)}")
    return ("RED" if reasons else "WARN"), reasons


def _resolve_fail_on(key: str, override: str | None) -> str:
    if override:
        return override.lower()
    try:
        from sdd_lib.layered_config import read_layered_config
        cfg = read_layered_config() or {}
        val = cfg.get(key)
        if isinstance(val, str) and val.lower() in SEVERITY_RANK:
            return val.lower()
    except Exception:  # noqa: BLE001 — un config illisible ne doit pas bloquer un scan
        pass
    return "critical"


# --------------------------------------------------------------------------- #
# Persistance
# --------------------------------------------------------------------------- #

def persist(conn: sqlite3.Connection, *, catalog_name: str, feat_n: int,
            verdict: str, findings: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    """Écrit les findings + le marqueur d'exécution + une ligne de journal.

    Le `replace_qa_auditor_for_feat` en tête rend le scan idempotent : relancer
    sur la même FEAT remplace, n'accumule pas. Sans ça, trois runs tripleraient
    le compte de findings et le verdict deviendrait absurde.

    Mais le remplacement est BORNÉ à `detector='deterministic'` (schema v8).
    `ingest_agent_report` écrit les findings des reviewers LLM dans les MÊMES
    tables ; une purge non bornée les effaçait, et comme `/sdd-review` tourne
    APRÈS les agents dans `/sdd-full` (gate 4.8 après STEP 6.4.B), le verdict
    consolidé se calculait sur les seules regex — plus faible que la réalité,
    sur une gate bloquante. Régression introduite puis fermée le 2026-08-28 ;
    `test_scan_patterns.TestNoClobbering` la verrouille.
    """
    cfg = CATALOGS[catalog_name]
    ts = iso_now_ms()
    if catalog_name == "security":
        replace_qa_auditor_for_feat(conn, "qa_security", feat_n, mode="scan",
                                    detector=DETECTOR)
        insert_qa_security_batch(conn, feat_n=feat_n, mode="scan",
                                 verdict=verdict.lower(), issues=findings,
                                 extracted_at=ts, detector=DETECTOR)
    else:
        replace_qa_auditor_for_feat(conn, "qa_code_review", feat_n,
                                    detector=DETECTOR)
        insert_qa_code_review_batch(conn, feat_n=feat_n, verdict=verdict.lower(),
                                    issues=findings, extracted_at=ts,
                                    detector=DETECTOR)

    # Marqueur d'exécution sous un id PROPRE (`security-scan`, non `security`).
    #
    # `/sdd-review --ensure-scans` exige la présence des sources `security` et
    # `code-review` et bloque (exit 3) si l'une manque. Enregistrer le scan
    # sous l'id de l'agent aurait satisfait cette exigence sans que l'agent
    # ait tourné : la gate aurait cessé de détecter un `security-reviewer`
    # absent, et les 11 classes `llm_only` (IDOR, SSRF, BROKEN_AUTHN…) auraient
    # été réputées vérifiées alors qu'aucune regex ne les couvre.
    #
    # Le scan est un producteur distinct : il renforce le verdict, il ne
    # remplace pas l'agent.
    record_auditor_run(conn, feat_n=feat_n, auditor=f"{cfg['auditor']}-scan",
                       findings_count=len(findings), verdict=verdict,
                       extracted_at=ts, payload=manifest)

    # Le scan déterministe est journalisé comme les agents : un coût nul est
    # une information, il mesure ce qu'on a cessé de payer au LLM.
    try:
        from sdd_lib import journal
        journal.record(
            conn, agent=f"scan_patterns:{catalog_name}", kind="script",
            ts=ts, feat_n=feat_n, phase="pattern-scan",
            decision=f"deterministic scan ({manifest['scanned_classes']} classes, "
                     f"{manifest['files_scanned']} fichiers)",
            gate=cfg["auditor"], gate_verdict=verdict,
            outcome="ok" if verdict != "RED" else "fail",
            error_class=None if verdict != "RED" else findings[0]["issue_class"],
            notes=f"llm_only={len(manifest['llm_only_classes'])} "
                  f"degraded={len(manifest.get('degraded_classes') or [])} "
                  f"unscannable={len(manifest['skipped_unscannable'])}",
        )
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Rendu
# --------------------------------------------------------------------------- #

_VERDICT_ICON = {"GREEN": "🟢", "WARN": "🟡", "RED": "🔴"}


def render_md(result: dict[str, Any]) -> str:
    m = result["manifest"]
    out = [
        f"# Pattern scan — {result['catalog']} — FEAT {result['feat_n']}",
        "",
        f"{_VERDICT_ICON.get(result['verdict'], '')} **{result['verdict']}** · "
        f"{len(result['findings'])} finding(s) · "
        f"{m['files_scanned']} fichier(s) · {m['scanned_classes']} classe(s) scannée(s) · "
        f"seuil `{result['fail_on']}`",
        "",
    ]
    for r in result["reasons"]:
        out.append(f"- {r}")
    if result["reasons"]:
        out.append("")

    if result["findings"]:
        out.append("| sévérité | classe | fichier:ligne | détail |")
        out.append("|---|---|---|---|")
        for f in result["findings"][:100]:
            out.append(f"| {f['severity']} | `{f['issue_class']}` "
                       f"| {f['file_path']}:{f['line']} | {f['message']} |")
        if len(result["findings"]) > 100:
            out.append(f"| … | … | … | {len(result['findings']) - 100} finding(s) non affichés |")
        out.append("")

    out.append("## Périmètre du déterministe")
    out.append("")
    out.append(f"**{m['scanned_classes']} classe(s) couvertes par regex.**")
    out.append("")
    out.append(f"**{len(m['llm_only_classes'])} classe(s) relèvent du LLM par nature** — "
               "aucune regex dans le catalogue, elles exigent de comprendre un flux "
               "et non de reconnaître une forme :")
    out.append("")
    for c in m["llm_only_classes"]:
        out.append(f"- `{c}`")
    out.append("")
    if m.get("degraded_classes"):
        out.append(f"**{len(m['degraded_classes'])} classe(s) dégradées** — le catalogue "
                   "porte une intention de détection déterministe qu'il ne sait pas "
                   "encore exprimer. Dette réparable, à ne pas confondre avec la "
                   "catégorie précédente :")
        out.append("")
        for c in m["degraded_classes"]:
            out.append(f"- `{c}`")
        out.append("")
    if m["skipped_unscannable"]:
        out.append(f"**{len(m['skipped_unscannable'])} règle(s) anti-pattern non "
                   "exécutables** — le catalogue déclare le point d'entrée mais pas "
                   "la protection attendue (`requires:` manquant) :")
        out.append("")
        for s in m["skipped_unscannable"]:
            out.append(f"- `{s['class']}` — {s['hint']}")
        out.append("")
    if m["bad_regex"]:
        out.append(f"**{len(m['bad_regex'])} regex non compilable(s)** — écartées :")
        for b in m["bad_regex"]:
            out.append(f"- `{b['class']}` : {b['error']}")
        out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def run_catalog(catalog_name: str, *, feat_n: int, scan_root: Path, repo: Path,
                fail_on: str | None = None,
                catalog_root: Path | None = None) -> dict[str, Any]:
    """Exécute un catalogue et retourne le résultat (sans persistance).

    ``repo`` sert UNIQUEMENT à relativiser les chemins des findings.
    ``catalog_root`` localise les fichiers de patterns et vaut par défaut la
    racine du framework. Les deux coïncident en production, mais pas quand
    `SDD_HOME` déporte le foyer neutre — ni dans les tests, où le code scanné
    est un répertoire temporaire alors que le catalogue reste celui du dépôt.
    Confondre les deux rendait le scan intestable hors du dépôt.
    """
    catalog = load_catalog(catalog_name, catalog_root or repo_root())
    files = iter_source_files(scan_root, repo)
    findings = scan_files(catalog, files, repo)
    effective_fail_on = _resolve_fail_on(CATALOGS[catalog_name]["fail_on_key"], fail_on)
    verdict, reasons = compute_verdict(findings, effective_fail_on)
    croot = catalog_root or repo_root()
    cfile = catalog_path(catalog_name, croot)
    manifest = {
        "catalog": catalog_name,
        "catalog_file": (
            normalize(str(cfile.relative_to(croot))) if _under(cfile, croot)
            else normalize(str(cfile))
        ),
        "files_scanned": len(files),
        "scan_root": normalize(str(scan_root.relative_to(repo))) if _under(scan_root, repo) else str(scan_root),
        "scanned_classes": len(catalog["classes"]),
        "llm_only_classes": catalog["llm_only"],
        "degraded_classes": catalog["degraded"],
        "skipped_unscannable": catalog["skipped_unscannable"],
        "bad_regex": catalog["bad_regex"],
        "detector": "deterministic",
    }
    return {
        "catalog": catalog_name,
        "feat_n": feat_n,
        "verdict": verdict,
        "reasons": reasons,
        "fail_on": effective_fail_on,
        "findings": findings,
        "manifest": manifest,
    }


def _under(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="scan_patterns",
        description="Exécute security_patterns.yaml / code_review_patterns.yaml (0 token)",
    )
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument("--catalog", choices=("security", "code-review", "all"), default="all")
    p.add_argument("--path", default=None,
                   help="racine de scan (défaut: workspace/src)")
    p.add_argument("--fail-on", choices=SEVERITY_ORDER, default=None,
                   help="override du seuil ({Kind}FailOn du Project Config)")
    p.add_argument("--no-fail", action="store_true",
                   help="ne pas sortir en 4 sur verdict RED")
    p.add_argument("--dry-run", action="store_true",
                   help="scanne sans écrire dans console.db")
    p.add_argument("--json", action="store_true")
    p.add_argument("--db-path", default=None)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()  # cp1252 guard (verdicts emoji)
    args = parse_args(argv)
    if args.feat_number < 1:
        print("ERROR: scan_patterns failed\n"
              "CAUSE: [INVALID_ARG] --feat-number doit être ≥ 1\n"
              "FIX: python -m sdd_scripts.scan_patterns --feat-number 1",
              file=sys.stderr)
        return FAIL_FAST

    repo = repo_root()
    scan_root = Path(args.path) if args.path else workspace_root(repo) / "src"
    if not scan_root.is_absolute():
        scan_root = repo / scan_root

    names = ("security", "code-review") if args.catalog == "all" else (args.catalog,)
    results: list[dict[str, Any]] = []
    try:
        for name in names:
            results.append(run_catalog(name, feat_n=args.feat_number,
                                       scan_root=scan_root, repo=repo,
                                       fail_on=args.fail_on))
    except ConfigError as exc:
        print(f"ERROR: scan_patterns failed\n"
              f"CAUSE: [INVALID_ARG] catalogue illisible: {exc}\n"
              f"FIX: vérifier .sdd/python/*_patterns.yaml", file=sys.stderr)
        return FAIL_FAST

    if not args.dry_run:
        try:
            db = Path(args.db_path) if args.db_path else None
            ensure_initialized(db)
            with connect(db) as conn:
                for r in results:
                    persist(conn, catalog_name=r["catalog"], feat_n=args.feat_number,
                            verdict=r["verdict"], findings=r["findings"],
                            manifest=r["manifest"])
        except sqlite3.Error as exc:
            print(f"ERROR: scan_patterns failed\n"
                  f"CAUSE: [INFRA_BLOCKED] écriture console.db impossible: {exc}\n"
                  f"FIX: vérifier workspace/db/console.db", file=sys.stderr)
            return INFRA_BLOCKED

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0],
                         ensure_ascii=False, indent=2, default=str))
    else:
        print("\n".join(render_md(r) for r in results), end="")

    worst = "GREEN"
    for r in results:
        if r["verdict"] == "RED":
            worst = "RED"
            break
        if r["verdict"] == "WARN":
            worst = "WARN"
    if worst == "RED" and not args.no_fail:
        return VERDICT_RED_EXIT
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
