# SDD-Pro — Codex entry point

This repository is governed by SDD-Pro. Before a feature, review, reverse-engineering, or pipeline task, read `.codex/AGENTS.md` and follow its gates, ownership rules, and deterministic Python checks.

The generated Codex prompts live in `.codex/prompts/`. Treat `.sdd/` as the neutral source of truth; generated harness files are not edited by hand. For a real multi-agent pipeline, run the SDD preflight and preserve its `UNTESTED` gate until the documented conformance run has passed.
