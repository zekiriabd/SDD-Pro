#!/usr/bin/env python3
"""reverse_questions_io.py — deterministic read/write for the human-loop file.

Role (audit reverse-quality 2026-07-24, C3 — close the human loop in one run)
-----------------------------------------------------------------------------
`/sdd-reverse-questions` (agent `reverse-clarifier`) writes `questions.md` with
`## Q-N` blocks and reads back filled `- **Réponse** :` fields for `--ingest`.
Historically the human had to edit `questions.md` by hand between two manual
command invocations. The new `--interactive` close-loop mode lets the
orchestrator ask the questions IN-SESSION (AskUserQuestion) and write the
answers back, then run `--ingest` — all in one run.

To keep that loop deterministic (LLM asks, script parses/writes — the SDD_Pro
split), this module provides:
  * ``--list-open --json``      : emit the still-open questions (id/title/
    question/impact) as JSON, so the orchestrator asks exactly the right set.
  * ``--set-answer Q-N --text`` : write one answer into the block's Réponse
    field atomically (no LLM free-hand editing of the markdown structure).

It never invents a question or an answer, never changes IDs, and never touches
a block already ingested. `--ingest` (reverse-clarifier) remains the single
authority that recomputes confidence / REVERSE-GATE / US hash.

Exit codes (sdd_lib.exit_codes): 0 SUCCESS · 1 FAIL_FAST (bad args / Q-N absent)
· 3 INFRA_BLOCKED (I/O).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Exit codes: LOCAL constants (D4 — the reverse module never imports sdd_lib,
# it keeps portable local copies; cf. atomic_write_local.py / console_safe.py).
# Same semantics as sdd_lib.exit_codes: 0 SUCCESS · 1 FAIL_FAST · 3 INFRA_BLOCKED.
SUCCESS = 0
FAIL_FAST = 1
INFRA_BLOCKED = 3

# A block starts at "## Q-<id> — <title>" and runs to the next "## " or EOF.
_BLOCK_RE = re.compile(
    r"^##\s+(Q-\d+)\s*[—-]\s*(.*?)\s*$(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
# NB: use [ \t]* (NOT \s*) around values — \s matches newlines and would let a
# field capture bleed into the following line when its value is empty.
_FIELD_RE = {
    "question": re.compile(r"^-[ \t]*\*\*Question\*\*[ \t]*:[ \t]*(.*?)[ \t]*$", re.MULTILINE),
    "impact": re.compile(r"^-[ \t]*\*\*Impact\*\*[ \t]*:[ \t]*([a-zA-Z]+)", re.MULTILINE),
    "reponse": re.compile(r"^-[ \t]*\*\*Réponse\*\*[ \t]*:[ \t]*(.*?)[ \t]*$", re.MULTILINE),
    "statut": re.compile(r"^-[ \t]*\*\*Statut\*\*[ \t]*:[ \t]*(.*?)[ \t]*$", re.MULTILINE),
}
_REPONSE_LINE_RE = re.compile(r"^(-[ \t]*\*\*Réponse\*\*[ \t]*:).*$", re.MULTILINE)


def _field(block: str, key: str) -> str:
    m = _FIELD_RE[key].search(block)
    return (m.group(1).strip() if m else "")


def parse_blocks(text: str) -> list[dict]:
    """Return every Q-block as {id, title, question, impact, reponse, statut, raw}."""
    out: list[dict] = []
    for m in _BLOCK_RE.finditer(text):
        qid, title, body = m.group(1), m.group(2).strip(), m.group(3)
        out.append({
            "id": qid,
            "title": title,
            "question": _field(body, "question"),
            "impact": (_field(body, "impact") or "moderate").lower(),
            "reponse": _field(body, "reponse"),
            "statut": (_field(body, "statut") or "ouverte").lower(),
            "span": (m.start(), m.end()),
        })
    return out


def list_open(text: str) -> list[dict]:
    """Open = answer empty AND status not already ingested."""
    ordre = {"critical": 0, "moderate": 1, "minor": 2}
    blocks = [
        {k: b[k] for k in ("id", "title", "question", "impact")}
        for b in parse_blocks(text)
        if not b["reponse"] and not b["statut"].startswith(("ingér", "inexploitable"))
    ]
    blocks.sort(key=lambda b: (ordre.get(b["impact"], 1), b["id"]))
    return blocks


def set_answer(text: str, qid: str, answer: str) -> tuple[str | None, str]:
    """Write `answer` into the Réponse field of block `qid`. Returns (new_text, msg)."""
    answer = " ".join(answer.split())  # collapse newlines (one-line field)
    for b in parse_blocks(text):
        if b["id"] != qid:
            continue
        start, end = b["span"]
        block = text[start:end]
        if not _REPONSE_LINE_RE.search(block):
            return None, f"block {qid} has no '**Réponse**:' field"
        new_block = _REPONSE_LINE_RE.sub(rf"\1 {answer}", block, count=1)
        return text[:start] + new_block + text[end:], f"{qid} answered"
    return None, f"{qid} not found"


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    import os
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read/write the reverse human-loop questions.md.")
    ap.add_argument("questions", help="path to questions.md")
    ap.add_argument("--list-open", action="store_true", help="emit open questions")
    ap.add_argument("--set-answer", metavar="Q-N", default=None, help="answer this question id")
    ap.add_argument("--text", default=None, help="answer text (with --set-answer)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.questions)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read questions.md\nCAUSE: [REVERSE_QUESTIONS_PENDING] {exc}\nFIX: run /sdd-reverse-questions generate first", file=sys.stderr)
        return INFRA_BLOCKED

    if args.set_answer:
        if args.text is None:
            print("ERROR: --set-answer requires --text\nCAUSE: [INVALID_ARG] missing --text\nFIX: pass --text", file=sys.stderr)
            return FAIL_FAST
        new_text, msg = set_answer(text, args.set_answer, args.text)
        if new_text is None:
            print(f"ERROR: answer not written\nCAUSE: [REVERSE_ANSWER_INGEST_FAILED] {msg}\nFIX: check Q-N id exists", file=sys.stderr)
            return FAIL_FAST
        try:
            _atomic_write(path, new_text)
        except OSError as exc:
            print(f"ERROR: write failed\nCAUSE: [DISK] {exc}\nFIX: check writable", file=sys.stderr)
            return INFRA_BLOCKED
        print(json.dumps({"ok": True, "id": args.set_answer}) if args.json else f"OK {msg}")
        return SUCCESS

    # default / --list-open
    openq = list_open(text)
    if args.json:
        print(json.dumps({"open": openq, "count": len(openq)}, ensure_ascii=False))
    else:
        print(f"OK {len(openq)} question(s) ouverte(s)")
        for q in openq:
            print(f"  {q['id']} [{q['impact']}] {q['title']}")
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
