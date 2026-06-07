"""Unit tests for sdd_state.py — state machine + events (v6.10: in console.db).

Coverage:
- new-run → insère ligne dans `runs` + event `run.start` dans `events`
- set-phase start → status=running dans `run_phases` + event phase.start
- set-phase pass → status=pass dans `run_phases` + event phase.end + endedAt
- end-run success → status=success dans `runs` + event run.end + durationMs ≥ 0
- get-run --latest → renvoie le runId le plus récent pour un FeatNumber
- list-runs → liste filtrée par FeatNumber, tri startedAt desc, limit
- show-run → JSON complet sur stdout
- emit-event → insère ligne dans `events`
- Persistance entre invocations (round-trip)

v6.10 BREAKING : plus de fichiers run-*.json ni events.jsonl — tout
vit dans `workspace/output/db/console.db` (SQLite, WAL).

Stratégie : repo_root() détecte `.claude/` en remontant depuis CWD.
On crée un fake repo (avec `.claude/` factice) et lance le script avec
`cwd=fake_repo` → la DB atterrit dans `fake_repo/workspace/output/db/console.db`.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "sdd_state.py"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run sdd_state.py in subprocess with strict SDD_REPO_ROOT isolation.

    v7.0.1 fix : pass SDD_REPO_ROOT=cwd explicitly to the subprocess. Without
    this, repo_root() falls back to CWD walk and finds the REAL repo above
    %TEMP% (Windows : %TEMP% is under C:\\Users\\…\\AppData), polluting the
    real workspace/output/db/console.db with test data. Combined with the
    paths.py fix (honor override unconditionally), this gives proper test
    isolation.
    """
    cmd = [sys.executable, str(SCRIPT)] + args
    env = os.environ.copy()
    env["SDD_REPO_ROOT"] = str(cwd)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd), env=env)


def _setup_fake_repo(root: Path) -> None:
    """Minimal `.claude/` pour que repo_root() détecte le fake repo."""
    (root / ".claude").mkdir(parents=True)


class TestSddState(unittest.TestCase):
    def setUp(self) -> None:
        # ignore_cleanup_errors=True : on Windows, SQLite keeps -shm/-wal
        # file handles alive past the test (the subprocess that opened
        # the DB has exited but the OS lock may linger briefly). Without
        # this flag, tearDown raises WinError 145 (directory not empty).
        # The temp dir lives under %TEMP% and is GC'd by the OS anyway.
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.fake = Path(self.tmp.name)
        _setup_fake_repo(self.fake)
        self.db_path = self.fake / "workspace" / "output" / "db" / "console.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ---- helpers ----

    def _new_run(self, feat: int = 1, command: str = "/sdd-full") -> str:
        result = _run(
            ["new-run", "--feat-number", str(feat), "--command", command],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        run_id = result.stdout.strip()
        # Sprint 1.1 fix (2026-06-06) : run_id now comes from get_or_create_run_id()
        # which uses {YYYYMMDDTHHmmss}-{4-hex} format (unified with hook telemetry),
        # not the legacy uuid4().hex[:12] (12-hex). Accept both for backward-compat
        # with potential legacy environments.
        legacy_uuid12 = r"^[0-9a-f]{12}$"
        new_iso_rand4 = r"^[0-9]{8}T[0-9]{6}-[0-9a-f]{4}$"
        self.assertRegex(run_id, f"({legacy_uuid12})|({new_iso_rand4})")
        return run_id

    def _open_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _read_state(self, run_id: str) -> dict:
        """Re-build the legacy state dict shape from runs + run_phases."""
        conn = self._open_db()
        try:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            self.assertIsNotNone(row, f"run {run_id} not found in DB")
            phases = conn.execute(
                "SELECT * FROM run_phases WHERE run_id = ?", (run_id,)
            ).fetchall()
        finally:
            conn.close()
        tags = json.loads(row["tags_json"]) if row["tags_json"] else []
        out = {
            "runId":        row["run_id"],
            "FeatNumber":   row["feat_n"],
            "FeatName":     row["feat_name"],
            "command":      row["command"],
            "tags":         tags,
            "startedAt":    row["started_at"],
            "updatedAt":    row["updated_at"],
            "endedAt":      row["ended_at"],
            "status":       row["status"],
            "currentPhase": row["current_phase"],
            "phases":       {},
        }
        for ph in phases:
            out["phases"][ph["phase"]] = {
                "status":    ph["status"],
                "startedAt": ph["started_at"],
                "endedAt":   ph["ended_at"],
                "payload":   json.loads(ph["payload_json"]) if ph["payload_json"] else None,
            }
        return out

    def _read_events(self) -> list[dict]:
        """Re-build the legacy events.jsonl line shape from the events table.

        Mapping rules:
        - run.start  : top-level cmd, tags
        - run.end    : top-level status, durationMs
        - phase.start/end : top-level status, nested 'payload' if any
        - emit-event (any custom event_type) : user payload under 'payload' key
        """
        if not self.db_path.is_file():
            return []
        conn = self._open_db()
        try:
            rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
        finally:
            conn.close()
        out: list[dict] = []
        for r in rows:
            payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
            event_type = r["event_type"]
            ev = {
                "ts":         r["ts"],
                "runId":      r["run_id"],
                "FeatNumber": r["feat_n"],
                "event":      event_type,
            }
            if r["phase"]:
                ev["phase"] = r["phase"]

            if not isinstance(payload, dict):
                ev["payload"] = payload
                out.append(ev)
                continue

            if event_type in ("run.start", "run.end"):
                # Flatten everything at top level
                for k, v in payload.items():
                    ev[k] = v
            elif event_type in ("phase.start", "phase.end"):
                # status flat, inner user payload under 'payload'
                if "status" in payload:
                    ev["status"] = payload["status"]
                if "payload" in payload and payload["payload"] is not None:
                    ev["payload"] = payload["payload"]
            else:
                # Custom emit-event: user payload nested under 'payload'
                if payload:
                    ev["payload"] = payload
            out.append(ev)
        return out

    # ---- new-run ----

    def test_new_run_creates_state_file(self) -> None:
        run_id = self._new_run(feat=1, command="/sdd-full")
        state = self._read_state(run_id)
        self.assertEqual(state["runId"], run_id)
        self.assertEqual(state["FeatNumber"], 1)
        self.assertEqual(state["command"], "/sdd-full")
        self.assertEqual(state["status"], "running")
        self.assertIsNone(state["endedAt"])
        self.assertEqual(state["phases"], {})

    def test_new_run_appends_run_start_event(self) -> None:
        run_id = self._new_run(feat=2)
        events = self._read_events()
        starts = [e for e in events if e.get("event") == "run.start" and e.get("runId") == run_id]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]["FeatNumber"], 2)

    def test_new_run_rejects_zero_feat_number(self) -> None:
        result = _run(["new-run", "--feat-number", "0"], cwd=self.fake)
        self.assertEqual(result.returncode, 1)

    # ---- set-phase ----

    def test_set_phase_start_marks_running(self) -> None:
        run_id = self._new_run(feat=1)
        result = _run(
            ["set-phase", "--run-id", run_id, "--phase", "us-generate", "--status", "start"],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        state = self._read_state(run_id)
        phase = state["phases"]["us-generate"]
        self.assertEqual(phase["status"], "running")
        self.assertIsNone(phase["endedAt"])
        self.assertEqual(state["currentPhase"], "us-generate")

    def test_set_phase_pass_marks_ended(self) -> None:
        run_id = self._new_run(feat=1)
        _run(
            ["set-phase", "--run-id", run_id, "--phase", "us-generate", "--status", "start"],
            cwd=self.fake,
        )
        _run(
            ["set-phase", "--run-id", run_id, "--phase", "us-generate", "--status", "pass"],
            cwd=self.fake,
        )
        phase = self._read_state(run_id)["phases"]["us-generate"]
        self.assertEqual(phase["status"], "pass")
        self.assertIsNotNone(phase["endedAt"])

    def test_set_phase_emits_phase_end_event(self) -> None:
        run_id = self._new_run(feat=1)
        _run(
            ["set-phase", "--run-id", run_id, "--phase", "feat-validate", "--status", "pass"],
            cwd=self.fake,
        )
        events = self._read_events()
        phase_ends = [
            e for e in events
            if e.get("event") == "phase.end" and e.get("runId") == run_id
        ]
        self.assertEqual(len(phase_ends), 1)
        self.assertEqual(phase_ends[0]["phase"], "feat-validate")
        self.assertEqual(phase_ends[0]["status"], "pass")

    def test_set_phase_with_payload_json(self) -> None:
        run_id = self._new_run(feat=1)
        payload = '{"us_strict_back":4,"us_classic":1,"rate":0.8}'
        result = _run(
            [
                "set-phase", "--run-id", run_id,
                "--phase", "plan_cache_evaluation", "--status", "pass",
                "--payload-json", payload,
            ],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        phase = self._read_state(run_id)["phases"]["plan_cache_evaluation"]
        self.assertEqual(phase["payload"]["us_strict_back"], 4)
        self.assertEqual(phase["payload"]["rate"], 0.8)

    def test_set_phase_unknown_run_id_returns_error(self) -> None:
        result = _run(
            ["set-phase", "--run-id", "deadbeefdead", "--phase", "x", "--status", "pass"],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 1)

    # ---- end-run ----

    def test_end_run_success_updates_state_and_emits_event(self) -> None:
        run_id = self._new_run(feat=1)
        result = _run(
            ["end-run", "--run-id", run_id, "--status", "success"],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        state = self._read_state(run_id)
        self.assertEqual(state["status"], "success")
        self.assertIsNotNone(state["endedAt"])
        events = self._read_events()
        ends = [e for e in events if e.get("event") == "run.end" and e.get("runId") == run_id]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]["status"], "success")
        self.assertIn("durationMs", ends[0])
        self.assertGreaterEqual(ends[0]["durationMs"], 0)

    def test_end_run_unknown_run_id(self) -> None:
        result = _run(
            ["end-run", "--run-id", "ffffffffffff", "--status", "failed"],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 1)

    # ---- get-run / list-runs / show-run ----

    def test_get_run_latest_returns_most_recent(self) -> None:
        # Crée 2 runs sur le même FEAT, ordre lexicographique startedAt
        run_a = self._new_run(feat=5)
        # iso_now_ms() a précision ms → deux uuid distincts assurent fichiers distincts
        run_b = self._new_run(feat=5)
        self.assertNotEqual(run_a, run_b)
        result = _run(
            ["get-run", "--feat-number", "5", "--latest"],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0)
        # Le 2ème est plus récent (startedAt ms-précis)
        self.assertEqual(result.stdout.strip(), run_b)

    def test_get_run_missing_returns_1(self) -> None:
        result = _run(
            ["get-run", "--feat-number", "99", "--latest"],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 1)

    def test_list_runs_filters_by_feat(self) -> None:
        self._new_run(feat=1)
        self._new_run(feat=2)
        result = _run(
            ["list-runs", "--feat-number", "1"],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0)
        # Le runId du FEAT 1 doit apparaître, pas celui du FEAT 2
        # (tableau header + lignes)
        out_lines = result.stdout.splitlines()
        # En-tête + au moins une ligne data
        self.assertGreaterEqual(len(out_lines), 3)

    def test_show_run_emits_full_json(self) -> None:
        run_id = self._new_run(feat=7)
        result = _run(
            ["show-run", "--run-id", run_id],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["runId"], run_id)
        self.assertEqual(data["FeatNumber"], 7)

    # ---- emit-event ----

    def test_emit_event_custom_payload(self) -> None:
        run_id = self._new_run(feat=1)
        result = _run(
            [
                "emit-event", "--run-id", run_id,
                "--event-type", "plan_validate",
                "--payload-json", '{"us":"1-2","family":"back","exit_code":0,"result":"strict-ready"}',
            ],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        events = self._read_events()
        custom = [e for e in events if e.get("event") == "plan_validate"]
        self.assertEqual(len(custom), 1)
        self.assertEqual(custom[0]["payload"]["us"], "1-2")
        self.assertEqual(custom[0]["payload"]["result"], "strict-ready")
        self.assertEqual(custom[0]["FeatNumber"], 1)

    def test_emit_event_without_payload(self) -> None:
        run_id = self._new_run(feat=1)
        result = _run(
            ["emit-event", "--run-id", run_id, "--event-type", "dev_backend_strict_start"],
            cwd=self.fake,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        events = self._read_events()
        match = [e for e in events if e.get("event") == "dev_backend_strict_start"]
        self.assertEqual(len(match), 1)
        # Pas de payload key si absent
        self.assertNotIn("payload", match[0])

    # ---- events table integrity (v6.10) ----

    def test_events_table_each_row_valid(self) -> None:
        """v6.10: events live in SQLite, not JSONL. Verify ts + event_type
        + ISO-8601 ms timestamp on each row."""
        run_id = self._new_run(feat=1)
        _run(["set-phase", "--run-id", run_id, "--phase", "x", "--status", "start"], cwd=self.fake)
        _run(["set-phase", "--run-id", run_id, "--phase", "x", "--status", "pass"], cwd=self.fake)
        _run(["end-run", "--run-id", run_id], cwd=self.fake)
        conn = self._open_db()
        try:
            rows = conn.execute("SELECT ts, event_type FROM events ORDER BY id").fetchall()
        finally:
            conn.close()
        self.assertGreater(len(rows), 0, "events table must contain at least 1 row")
        for row in rows:
            self.assertIsNotNone(row["ts"])
            self.assertIsNotNone(row["event_type"])
            # Timestamp ISO-8601 ms (canonical iso_now_ms)
            self.assertRegex(row["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


if __name__ == "__main__":
    unittest.main()
