// console-db.js — read-only access to workspace/output/db/console.db (SDD_Pro v6.10)
//
// Implementation strategy (v6.10.3+) :
//   1. Try Node's built-in `node:sqlite` (DatabaseSync) — in-process,
//      microsecond-scale, no process spawn. Available without flag in
//      Node 22.5+ (with --experimental-sqlite) and stable in Node 24+.
//   2. Fallback to Python spawnSync (legacy v6.10) when `node:sqlite`
//      is unavailable (Node 20.x or experimental flag not enabled).
//
// Why this matters : under load Fastify processes requests via the event
// loop. Each `spawnSync` blocks the loop for the duration of the Python
// process startup (~10-50ms cold). With `node:sqlite` the same query
// blocks for ~0.1ms (in-process SQL eval), 100-1000× less event-loop
// pressure under concurrent requests.
//
// The Python fallback is intentional : it keeps `npm install fastify`
// as the only requirement (no C++ toolchain needed for `better-sqlite3`),
// matching the original v6.10 footprint.
//
// Exposed queries (used by server.js):
//   - dbAvailable()             : { ok, path, error, mode }
//   - dashboardOverview()       : { feats: [{feat_n, name, stats:{...}}, ...] }
//   - featStats(featN)          : detail of one FEAT
//   - auditTokens()             : context_budget + token_usage aggregates
//   - stateRuns()               : runs + run_phases + recent events
//   - gatesHistory(featN?)      : gates history (optional feat filter)

import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const CONSOLE_DIR = dirname(dirname(__filename));
const WORKSPACE   = resolve(CONSOLE_DIR, "..");
const REPO_ROOT   = resolve(WORKSPACE, "..");
const PY_ROOT     = join(REPO_ROOT, ".claude", "python");
const DB_PATH     = join(WORKSPACE, "output", "db", "console.db");

// Allow override (CI / tests / Python from a venv)
const PY_BIN = process.env.SDD_PYTHON || "python";

// ─────────────────────────────────────────────
// Native SQLite (node:sqlite) — opt-in via SDD_CONSOLE_NATIVE_SQLITE=1
// or auto-enabled when SDD_CONSOLE_NATIVE_SQLITE is unset and the module
// is importable. Set SDD_CONSOLE_NATIVE_SQLITE=0 to force the Python path.
// ─────────────────────────────────────────────
let NATIVE_DB = null;
let MODE = "python"; // diagnostic flag exposed via dbAvailable()
const wantNative = process.env.SDD_CONSOLE_NATIVE_SQLITE !== "0";
if (wantNative) {
  try {
    const { DatabaseSync } = await import("node:sqlite");
    if (existsSync(DB_PATH)) {
      NATIVE_DB = new DatabaseSync(DB_PATH, { readOnly: true });
      MODE = "native";
    }
  } catch {
    // Module absent (Node < 22.5) or experimental flag missing — stay in python mode.
    NATIVE_DB = null;
  }
}

function nativeSql(sql, params = []) {
  try {
    const stmt = NATIVE_DB.prepare(sql);
    // DatabaseSync.all() accepts positional args, not array
    const rows = params.length > 0 ? stmt.all(...params) : stmt.all();
    return rows;
  } catch {
    return [];
  }
}

function pythonQuery(subcommand, featN, extraArgs = []) {
  // Subcommands of query_console_db.py return rich nested JSON (api-gate,
  // coverage, feat-stats…) — keep these on the Python path; we don't
  // replicate that aggregation logic in JS.
  const args = [
    "-m", "sdd_scripts.query_console_db",
    subcommand,
    "--feat", String(featN),
    ...extraArgs,
  ];
  const res = spawnSync(PY_BIN, args, {
    cwd: PY_ROOT,
    encoding: "utf8",
    timeout: 5000,
    windowsHide: true,
  });
  if (res.status !== 0) {
    return null;
  }
  try {
    return JSON.parse(res.stdout);
  } catch {
    return null;
  }
}

// Generic SQL → JSON. v6.10.3+ : native (in-process, ~0.1ms) when
// `node:sqlite` is loadable, falls back to spawning Python (~10-50ms)
// otherwise. Same synchronous signature in both modes — zero impact on
// call sites.
//
// v6.10.5 (audit 2026-05-19) : fallback Python uses sdd_lib.console_db
// connect_ro() — URI mode=ro, no WAL pragma, no ensure_initialized().
// Safe on read-only mounts / sandboxes where the previous code died with
// "unable to open database file" because it tried to enable WAL on a
// read-only DB.
function pythonSql(sql, params = []) {
  if (NATIVE_DB) {
    return nativeSql(sql, params);
  }
  const code = `
import json, sys
sys.path.insert(0, r"${PY_ROOT.replace(/\\/g, "\\\\")}")
from sdd_lib.console_db import connect_ro
try:
    with connect_ro() as conn:
        rows = conn.execute(${JSON.stringify(sql)}, ${JSON.stringify(params)}).fetchall()
        print(json.dumps([dict(r) for r in rows], default=str))
except FileNotFoundError:
    print("[]")
`;
  const res = spawnSync(PY_BIN, ["-c", code], {
    cwd: PY_ROOT,
    encoding: "utf8",
    timeout: 5000,
    windowsHide: true,
  });
  if (res.status !== 0) {
    return [];
  }
  try {
    return JSON.parse(res.stdout);
  } catch {
    return [];
  }
}

// Public escape hatch — used by server.js inline routes that need ad-hoc
// SQL without going through a dedicated export. Same semantics as the
// internal pythonSql (returns [] on error, never throws).
export function rawSql(sql, params = []) {
  return pythonSql(sql, params);
}

// v7.0.0 P0 C2 fix : mirror console gate decisions into console.db `gates`
// table for cross-FEAT historical queries. status.json remains the live
// source of truth ; this is best-effort analytics — failures are logged
// (returned in result) but never thrown to the HTTP handler.
//
// Writes go through the Python CLI (`record_gate_decision.py`) because the
// Node-side connection is opened read-only (connect_ro / DatabaseSync
// readOnly:true). Centralizing writes in Python preserves the
// "Python writes, Node reads" architectural invariant (cf. console-db.js
// header comment line 11-12) and keeps schema migration logic in one place.
//
// Returns { ok: boolean, error?: string } — never throws.
export function recordGateDecision({
  featN,
  gateName,
  decision,
  byUser = null,
  comment = null,
  decidedAt = null,
  runId = null,
}) {
  const args = [
    "-m", "sdd_scripts.record_gate_decision",
    "--feat-n", String(featN),
    "--gate-name", String(gateName),
    "--decision", String(decision),
  ];
  if (byUser)    args.push("--by-user",    String(byUser));
  if (comment)   args.push("--comment",    String(comment));
  if (decidedAt) args.push("--decided-at", String(decidedAt));
  if (runId)     args.push("--run-id",     String(runId));

  const res = spawnSync(PY_BIN, args, {
    cwd: PY_ROOT,
    encoding: "utf8",
    timeout: 5000,
    windowsHide: true,
  });
  if (res.status === 0) return { ok: true };
  return {
    ok: false,
    error: (res.stderr || res.stdout || `record_gate_decision exited ${res.status}`).trim(),
  };
}

export function dbAvailable() {
  if (!existsSync(DB_PATH)) {
    return { ok: false, path: DB_PATH, mode: MODE, error: "DB absente — lancer python -m sdd_scripts.init_console_db" };
  }
  // Smoke: try a trivial query
  const res = pythonSql("SELECT version FROM schema_version LIMIT 1");
  if (Array.isArray(res) && res.length > 0) {
    return { ok: true, path: DB_PATH, mode: MODE, schema_version: res[0].version };
  }
  return { ok: false, path: DB_PATH, mode: MODE, error: "DB illisible ou schema_version absente" };
}

// ─────────────────────────────────────────────
// Aggregated dashboards
// ─────────────────────────────────────────────

export function listFeats() {
  return pythonSql(
    "SELECT feat_n, name, status, ac_count, sfd_count FROM feats ORDER BY feat_n"
  );
}

export function featStats(featN) {
  const data = pythonQuery("feat-stats", featN);
  if (!data) {
    return { feat_n: featN, error: "query failed", api_gate: {present:false}, coverage:{present:false}, quality:{present:false} };
  }
  return data;
}

export function dashboardOverview() {
  const feats = listFeats();
  return {
    feats: feats.map((f) => ({ ...f, stats: featStats(f.feat_n) })),
    generated_at: new Date().toISOString(),
    db_path: "workspace/output/db/console.db",
  };
}

// ─────────────────────────────────────────────
// /api/audit replacement — tokens + context budget
// ─────────────────────────────────────────────

export function auditTokens() {
  const byAgent = pythonSql(`
    SELECT agent,
           COUNT(*)           AS runs,
           SUM(tokens_used)   AS tokens_total,
           MAX(tokens_used)   AS tokens_max,
           MAX(tokens_budget) AS budget_tokens,
           SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) AS errors,
           MAX(ts)            AS last_ts
      FROM context_budget
     GROUP BY agent
     ORDER BY runs DESC
  `);
  const byAgentMapped = byAgent.map((a) => ({
    agent: a.agent,
    runs: a.runs,
    tokensTotal: a.tokens_total,
    tokensMax: a.tokens_max,
    budgetTokens: a.budget_tokens,
    avgTokens: a.runs > 0 ? Math.round(a.tokens_total / a.runs) : 0,
    usagePct: a.budget_tokens > 0 ? Math.round((a.tokens_max / a.budget_tokens) * 100) : 0,
    errors: a.errors,
    warnings: 0,
    lastTimestamp: a.last_ts,
  }));

  const recentRuns = pythonSql(`
    SELECT ts AS timestamp, agent, feat_n AS FeatNumber, us_id AS usId,
           CASE WHEN passed = 1 THEN 'pass' ELSE 'fail' END AS result,
           tokens_used   AS estimatedInputTokens,
           tokens_budget AS budgetTokens,
           passed
      FROM context_budget
     ORDER BY ts DESC LIMIT 20
  `);

  const tokenUsage = pythonSql(`
    SELECT agent,
           SUM(input_tokens)           AS input_total,
           SUM(output_tokens)          AS output_total,
           SUM(cache_read_tokens)      AS cache_read_total,
           SUM(cache_creation_tokens)  AS cache_creation_total,
           COUNT(*)                    AS calls
      FROM token_usage
     GROUP BY agent
     ORDER BY (SUM(input_tokens) + SUM(output_tokens)) DESC
  `);

  const totalRuns = byAgent.reduce((s, a) => s + (a.runs || 0), 0);

  return {
    available: byAgent.length > 0 || tokenUsage.length > 0,
    source: "workspace/output/db/console.db",
    summary: {
      totalRuns,
      totalCostUsd: 0,
      totalWarnings: 0,
      totalErrors: byAgent.reduce((s, a) => s + (a.errors || 0), 0),
      agentsCount: byAgent.length,
    },
    byAgent: byAgentMapped,
    tokenUsage,
    recentRuns,
  };
}

// ─────────────────────────────────────────────
// /api/state replacement — runs + run_phases + events
// ─────────────────────────────────────────────

export function stateRuns() {
  const allRuns = pythonSql(`
    SELECT run_id AS runId, command, feat_n AS FeatNumber, feat_name AS FeatName,
           status, current_phase AS currentPhase,
           started_at AS startedAt, ended_at AS endedAt, updated_at AS updatedAt,
           tags_json, params_json
      FROM runs ORDER BY started_at DESC LIMIT 50
  `);
  let lastRun = allRuns[0] || null;

  if (lastRun) {
    const phases = pythonSql(`
      SELECT phase, status, started_at AS startedAt, ended_at AS endedAt, payload_json
        FROM run_phases WHERE run_id = ? ORDER BY id
    `, [lastRun.runId]);
    lastRun.phases = {};
    for (const ph of phases) {
      let payload = null;
      try { payload = ph.payload_json ? JSON.parse(ph.payload_json) : null; } catch {}
      lastRun.phases[ph.phase] = {
        status: ph.status,
        startedAt: ph.startedAt,
        endedAt: ph.endedAt,
        payload,
      };
    }
  }

  const events = pythonSql(`
    SELECT ts, run_id AS runId, feat_n AS FeatNumber, us_id AS usId,
           event_type AS event, phase, payload_json
      FROM events ORDER BY id DESC LIMIT 30
  `).map((e) => {
    let payload = null;
    try { payload = e.payload_json ? JSON.parse(e.payload_json) : null; } catch {}
    return { ts: e.ts, runId: e.runId, FeatNumber: e.FeatNumber, usId: e.usId, event: e.event, phase: e.phase, payload };
  });

  return {
    available: allRuns.length > 0,
    lastRun,
    runsCount: allRuns.length,
    recentEvents: events,
  };
}

// ─────────────────────────────────────────────
// Gates history
// ─────────────────────────────────────────────

export function gatesHistory(featN = null) {
  if (featN) {
    return pythonSql(`
      SELECT gate_name, decision, decided_at, by_user, payload_json
        FROM gates WHERE feat_n = ? ORDER BY decided_at DESC
    `, [featN]);
  }
  return pythonSql(`
    SELECT feat_n, gate_name, decision, decided_at, by_user
      FROM gates ORDER BY decided_at DESC LIMIT 100
  `);
}
