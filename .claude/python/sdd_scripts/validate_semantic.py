#!/usr/bin/env python3
"""SDD_Pro: deterministic semantic validation (0 token LLM).

Re-introduces a cross-artefact semantic check layer (vocabulary + regex,
no LLM call).

Checks (strictness=standard):
- VAGUE_TERM         : vague terms in FEAT / US (fast, easy, scalable, …)
- SECURITY_GAP       : auth/credential keywords without protection mention
- SENSITIVE_DATA     : PII mentioned without privacy mention
- ROUTE_CONTRACT_GAP : /api/* in FEAT without backend endpoint (if code generated)

Usage:
    python validate_semantic.py --feat-number {n}
    python validate_semantic.py --feat-number {n} --json
    python validate_semantic.py --feat-number {n} --strictness conservative|standard|strict

Exit code: always 0 (semantic = WARN only, never blocking).

Migrated from .claude/scripts/validate-semantic.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.project_config import (  # noqa: E402
    read_stack_md_text as _read_stack_md_text,
    section_body as _section_body,
)
from sdd_lib.exit_codes import SUCCESS  # noqa: E402


VAGUE_CONSERVATIVE = [
    "fast", "rapide", "easy", "facile", "scalable", "user-friendly",
]

VAGUE_STANDARD = [
    "fast", "quick", "rapide", "vite", "rapidement",
    "easy", "facile", "intuitive", "intuitif",
    "user-friendly", "convivial",
    "scalable", "performant", "responsive",
    "robust", "robuste", "reliable", "fiable",
    "many", "several", "plusieurs", "beaucoup",
    "simple", "simply", "simplement",
]

VAGUE_STRICT = VAGUE_STANDARD + [
    "appropriate", "approprie", "adequate", "adequat",
    "reasonable", "raisonnable", "proper", "correct",
    "efficient", "efficace", "optimized", "optimise",
    "clean", "propre", "elegant",
    "modern", "moderne", "flexible", "dynamic", "dynamique",
    "smooth", "fluide", "seamless",
]

# v6.10.5 (audit 2026-05-19) — proper-noun / dev-tool context exclusion
# for VAGUE_TERM matches. Triggered by 4× false-positives on CMS Sprint
# FEAT 1 where "vite" matched the React build tool Vite (`VITE_API_URL`,
# `import.meta.env.VITE_*`, `vite.config.ts`), not the French adverb.
#
# When a matched line contains ANY of these context markers WITHIN ±40
# chars of the match, skip the match. Keep the dict tightly scoped to
# known false positives — do NOT generalize to "any capital letter
# nearby" (which would mask legitimate sentence-starting adjectives).
VAGUE_PROPER_NOUN_CONTEXTS: dict[str, tuple[str, ...]] = {
    "vite":  ("Vite", "VITE_", "vite.config", "import.meta.env",
              "vitejs", "vite-plugin", "bundler"),
    "fast":  ("FastAPI", "Fastify", "FastEndpoints", "fastapi", "fastify"),
    # Add new entries here when a new false-positive pattern is observed.
    # Always trace the cause in the inline comment.
}

SECURITY_KEYWORDS = [
    "password", "mot de passe", "motdepasse", "mdp",
    "token", "jwt", "bearer", "refresh token",
    "auth", "authentication", "authentification", "login", "connexion", "signin", "sign in",
    "credential", "identifiant", "secret", "api key", "cle api", "clef api",
]

PROTECTION_KEYWORDS = [
    r"hash", r"hashed", r"hashé", r"bcrypt", r"argon", r"argon2", r"scrypt", r"pbkdf2",
    r"sha-?(?:256|512)",
    r"encrypt", r"encrypted", r"chiffr", r"chiffrement", r"aes", r"rsa",
    r"salt", r"sel cryptographique",
    r"https", r"tls", r"ssl",
    r"httponly", r"http-only", r"samesite", r"secure cookie", r"cookie secure",
    r"environment variable", r"variable d'environnement", r"env var", r"env variable",
]

PII_KEYWORDS = [
    "email", "e-mail", "courriel",
    "phone", "téléphone", "telephone", "mobile",
    "postal address", "adresse postale",
    "birth date", "birthday", "date de naissance",
    "ssn", "social security", "sécurité sociale",
    "credit card", "carte bancaire", "iban", "rib",
]

PRIVACY_KEYWORDS = [
    "encrypt", "chiffr", "mask", "masqu", "anonymized", "anonymis", "redact", "redig",
    "gdpr", "rgpd", "privacy", "vie privée", "confidential", "confidentiel",
    "access control", "contrôle d'accès", "rbac", "role-based",
    "audit log", "journal d'audit",
]

# Backend route declaration patterns (multi-stack)
ROUTE_DECL_RE = re.compile(
    r"(?im)(?:Map(?:Get|Post|Put|Delete|Patch)|"
    r"\[Http(?:Get|Post|Put|Delete|Patch)(?:\(|\])|"
    r"@(?:Get|Post|Put|Delete|Patch)Mapping|"
    r"app\.(?:get|post|put|delete|patch)|"
    r"@app\.(?:get|post|put|delete|patch))"
    r"\s*\(?\s*[\"']([^\"')]+)[\"']"
)

ROUTE_SPEC_RE = re.compile(r"""(?i)["`/]?(/api/[a-z0-9_\-/.{}:]+)""")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument(
        "--strictness",
        default="standard",
        choices=["conservative", "standard", "strict"],
    )
    p.add_argument("--json", action="store_true")
    return p.parse_args()


class Report:
    def __init__(self) -> None:
        self.passes: list[dict] = []
        self.warnings: list[dict] = []

    def add_pass(self, id_: str, msg: str) -> None:
        self.passes.append({"id": id_, "message": msg})

    def add_warn(self, id_: str, msg: str, context: str = "") -> None:
        self.warnings.append({"id": id_, "message": msg, "context": context})


def read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def line_number(text: str, index: int) -> int:
    if index < 0:
        return SUCCESS
    return text.count("\n", 0, index) + 1


def snippet(text: str, index: int, radius: int = 60) -> str:
    start = max(0, index - radius)
    end = min(len(text), index + radius)
    s = text[start:end]
    return re.sub(r"\s+", " ", s).strip()


def any_match(text: str, patterns: list[str]) -> bool:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def section_body(text: str, heading: str) -> str:
    """Adapter returning empty string (not None) for caller compatibility."""
    return _section_body(text, heading) or ""


def select_vocabulary(strictness: str) -> list[str]:
    if strictness == "conservative":
        return VAGUE_CONSERVATIVE
    if strictness == "strict":
        return VAGUE_STRICT
    return VAGUE_STANDARD


def main() -> int:
    args = parse_args()
    root = repo_root()
    feats_dir = root / "workspace" / "input" / "feats"
    us_dir = root / "workspace" / "output" / "us"
    src_dir = root / "workspace" / "output" / "src"
    stack_path = root / "workspace" / "input" / "stack" / "stack.md"

    vague_terms = select_vocabulary(args.strictness)
    rep = Report()

    # Locate FEAT
    feat_file: Path | None = None
    feat_name: str | None = None
    if feats_dir.is_dir():
        files = sorted(feats_dir.glob(f"{args.feat_number}-*.md"))
        if len(files) == 1:
            feat_file = files[0]
            m = re.match(rf"^{args.feat_number}-(.+)$", feat_file.stem)
            if m:
                feat_name = m.group(1)

    if feat_file is None:
        if args.json:
            print(json.dumps({
                "spec_number": args.feat_number,
                "spec_name":   None,
                "strictness":  args.strictness,
                "decision":    "SKIP",
                "warnings":    [],
                "passes":      [],
                "note":        "FEAT introuvable - validation semantique skip",
            }, indent=2, ensure_ascii=False))
        else:
            print("## 2. Validations semantiques (deterministes)")
            print()
            print(f"**Skip** : FEAT introuvable (workspace/input/feats/{args.feat_number}-*.md)")
        return SUCCESS
    feat_content = read_safe(feat_file)
    us_content = ""
    if us_dir.is_dir():
        for f in sorted(us_dir.glob(f"{args.feat_number}-*.md")):
            us_content += f"\n--- US: {f.name} ---\n"
            us_content += read_safe(f)
    full_text = feat_content + "\n" + us_content

    # Check 1 — VAGUE_TERM
    vague_count = 0
    vague_skipped = 0
    scan_sections = (
        "Acceptance Criteria", "Business Rules", "Functional Needs",
        "Objective", "Functional Deliverables",
    )
    for sec in scan_sections:
        body = section_body(feat_content, sec)
        if not body:
            continue
        body_offset = feat_content.find(body)
        for term in vague_terms:
            pat = re.compile(rf"(?i)\b{re.escape(term)}\b")
            contexts = VAGUE_PROPER_NOUN_CONTEXTS.get(term.lower(), ())
            for m in pat.finditer(body):
                absolute_index = body_offset + m.start()
                # v6.10.5 — Proper-noun / brand context exclusion (±40 chars window).
                if contexts:
                    win_start = max(0, m.start() - 40)
                    win_end   = min(len(body), m.end() + 40)
                    window = body[win_start:win_end]
                    if any(ctx in window for ctx in contexts):
                        vague_skipped += 1
                        continue
                line_no = line_number(feat_content, absolute_index)
                snip = snippet(feat_content, absolute_index, 50)
                rep.add_warn(
                    "VAGUE_TERM",
                    f"'{term}' dans ## {sec} L{line_no} - terme non mesurable",
                    f"L{line_no}: {snip}",
                )
                vague_count += 1
    if vague_count == 0:
        skip_note = (
            f", {vague_skipped} faux-positifs filtres (proper-noun contexts)"
            if vague_skipped else ""
        )
        rep.add_pass(
            "VAGUE_TERM",
            f"Aucun terme vague detecte (vocabulaire {args.strictness}, "
            f"{len(vague_terms)} termes scannes{skip_note})",
        )

    # Check 2 — SECURITY_GAP
    security_patterns = [rf"(?i)\b{re.escape(kw)}\b" for kw in SECURITY_KEYWORDS]
    protection_patterns = [rf"(?i){pat}" for pat in PROTECTION_KEYWORDS]
    has_security = any_match(feat_content, security_patterns)
    has_protection = any_match(full_text, protection_patterns)

    if has_security:
        if not has_protection:
            found: list[str] = []
            for kw in SECURITY_KEYWORDS:
                if re.search(rf"(?i)\b{re.escape(kw)}\b", feat_content):
                    found.append(kw)
                    if len(found) >= 3:
                        break
            rep.add_warn(
                "SECURITY_GAP",
                f"FEAT mentionne {', '.join(found)} mais aucun mecanisme de protection "
                "(hash/bcrypt/encrypt/tls/httponly) declare en FEAT ou US",
            )
        else:
            rep.add_pass(
                "SECURITY_OK",
                "Keywords securite presentes ET au moins un mecanisme de protection mentionne",
            )

    # Check 3 — SENSITIVE_DATA
    pii_found: list[str] = []
    for kw in PII_KEYWORDS:
        if re.search(rf"(?i)\b{re.escape(kw)}\b", feat_content):
            pii_found.append(kw)
    if pii_found:
        privacy_patterns = [rf"(?i){re.escape(kw)}" for kw in PRIVACY_KEYWORDS]
        has_privacy = any_match(full_text, privacy_patterns)
        if not has_privacy:
            rep.add_warn(
                "SENSITIVE_DATA",
                f"PII detectees ({', '.join(pii_found[:3])}) mais aucune mention de "
                "privacy/chiffrement/anonymisation/RGPD en FEAT ou US",
            )
        else:
            rep.add_pass(
                "PII_OK",
                "PII mentionnees ET au moins un mecanisme de privacy declare",
            )

    # Check 4 — ROUTE_CONTRACT_GAP
    routes_in_spec: set[str] = set()
    for m in ROUTE_SPEC_RE.finditer(full_text):
        route = m.group(1).rstrip(".,;:\"'`)")
        route = re.sub(r"[\?#].*$", "", route)
        if route and len(route) > 4:
            routes_in_spec.add(route)

    if routes_in_spec:
        backend_name: str | None = None
        # v7.0.0-alpha (audit CRIT-2) : cached mtime-keyed read.
        stack_raw = _read_stack_md_text(root)
        if stack_raw:
            m = re.search(r"(?im)^\s*BackendName\s*:\s*(\S+)", stack_raw)
            if m:
                backend_name = m.group(1).strip()

        backend_code_dir: Path | None = None
        if backend_name:
            candidate = src_dir / backend_name
            if candidate.is_dir():
                backend_code_dir = candidate

        if backend_code_dir is None:
            rep.add_pass(
                "ROUTE_CONTRACT_DEFERRED",
                f"Routes /api/* detectees ({len(routes_in_spec)}) mais code backend pas encore "
                "genere - check differe apres /dev-run",
            )
        else:
            declared_routes: set[str] = set()
            for ext in (".cs", ".ts", ".js", ".py", ".kt", ".java"):
                for f in backend_code_dir.rglob(f"*{ext}"):
                    code = read_safe(f)
                    if not code:
                        continue
                    for m in ROUTE_DECL_RE.finditer(code):
                        r = m.group(1).rstrip("/")
                        if r:
                            declared_routes.add(r)

            missing: list[str] = []
            for r in routes_in_spec:
                normalized = r.rstrip("/")
                found = False
                for d in declared_routes:
                    d_pat = "^" + re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(d)) + "$"
                    if re.match(d_pat, normalized):
                        found = True
                        break
                    r_pat = "^" + re.sub(r"\\\{[^}]+\\\}", r"[^/]+", re.escape(normalized)) + "$"
                    if re.match(r_pat, d):
                        found = True
                        break
                if not found:
                    missing.append(normalized)

            if missing:
                head = ", ".join(missing[:5])
                more = f" (+{len(missing) - 5} autres)" if len(missing) > 5 else ""
                rep.add_warn(
                    "ROUTE_CONTRACT_GAP",
                    f"Routes mentionnees en FEAT/US sans endpoint backend declare : {head}{more} - "
                    "voir [FRONTEND_BACKEND_CONTRACT_GAP] dans error-classification.md",
                )
            else:
                rep.add_pass(
                    "ROUTE_CONTRACT_OK",
                    f"Toutes les routes /api/* FEAT ({len(routes_in_spec)}) ont un endpoint backend declare",
                )

    decision = "WARN" if rep.warnings else "GO"

    if args.json:
        result = {
            "spec_number": args.feat_number,
            "spec_name":   feat_name,
            "strictness":  args.strictness,
            "decision":    decision,
            "warnings":    rep.warnings,
            "passes":      rep.passes,
            "timestamp":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("## 2. Validations semantiques (deterministes)")
        print()
        print(f"**Strictness** : {args.strictness}")
        print(f"**Decision semantique** : {decision} (non bloquant)")
        print(f"**Passes** : {len(rep.passes)} | **Warnings** : {len(rep.warnings)}")
        print()
        if rep.passes:
            print("### Validations passees")
            for p in rep.passes:
                print(f"- [PASS] {p['id']} : {p['message']}")
            print()
        if rep.warnings:
            print("### Warnings semantiques")
            for w in rep.warnings:
                print(f"- [WARN] {w['id']} : {w['message']}")
                if w["context"]:
                    print(f"  - Contexte : {w['context']}")
            print()
        print(
            f"_Note : validation semantique deterministe (vocabulaire {args.strictness}). "
            "Pour escalation petit modele sur WARN, voir SemanticValidationMode dans stack.md._"
        )

    return SUCCESS
if __name__ == "__main__":
    sys.exit(main())
