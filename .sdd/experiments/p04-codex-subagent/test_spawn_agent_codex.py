"""Tests unitaires P0.4 — AUCUN appel réel à codex (seam _invoke_codex mocké).

Lancement : python -m pytest .sdd/experiments/p04-codex-subagent/test_spawn_agent_codex.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import spawn_agent_codex as sac  # noqa: E402
import run_experiment as rex  # noqa: E402

SCHEMA = {
    "type": "object",
    "required": ["verdict", "findings"],
    "properties": {
        "verdict": {"type": "string", "enum": ["GREEN", "WARN", "RED"]},
        "findings": {"type": "array",
                     "items": {"type": "object", "required": ["summary"]}},
    },
}
VALID_PAYLOAD = {"verdict": "WARN", "findings": [{"summary": "N+1 query"}]}


def mock_invocation(monkeypatch, **kwargs):
    """Remplace le seam subprocess par une invocation fabriquée."""
    inv = sac.CodexInvocation(**kwargs)
    calls = []

    def fake(prompt, cfg):
        calls.append((prompt, cfg))
        return inv

    monkeypatch.setattr(sac, "_invoke_codex", fake)
    return calls


# ---------------------------------------------------------------------------
# spawn_agent — parsing strict + classification d'erreur
# ---------------------------------------------------------------------------

def test_spawn_ok_json_direct(monkeypatch):
    calls = mock_invocation(monkeypatch, exit_code=0,
                            last_message=json.dumps(VALID_PAYLOAD))
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["ok"] is True
    assert res["parsed"] == VALID_PAYLOAD
    assert res["error_class"] is None
    assert res["latency_ms"] >= 0
    # le prompt embarque système + tâche + contrat de sortie
    prompt = calls[0][0]
    assert "sys" in prompt and "task" in prompt and "verdict" in prompt


def test_spawn_ok_json_dans_fence_markdown(monkeypatch):
    raw = ("Voici le résultat demandé :\n```json\n"
           + json.dumps(VALID_PAYLOAD) + "\n```\nFin.")
    mock_invocation(monkeypatch, exit_code=0, last_message=raw)
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["ok"] is True
    assert res["parsed"] == VALID_PAYLOAD


def test_spawn_ok_json_noye_dans_texte(monkeypatch):
    raw = 'Analyse terminée. {"verdict": "GREEN", "findings": []} — voilà.'
    mock_invocation(monkeypatch, exit_code=0, last_message=raw)
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["ok"] is True
    assert res["parsed"]["verdict"] == "GREEN"


def test_spawn_fallback_stdout_si_last_message_absent(monkeypatch):
    mock_invocation(monkeypatch, exit_code=0, last_message=None,
                    stdout=json.dumps(VALID_PAYLOAD))
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["ok"] is True


def test_spawn_json_unparseable(monkeypatch):
    mock_invocation(monkeypatch, exit_code=0,
                    last_message="Je ne peux pas produire de JSON, désolé.")
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["ok"] is False
    assert res["parsed"] is None
    assert res["error_class"] == "[JSON_UNPARSEABLE]"


def test_spawn_schema_mismatch(monkeypatch):
    # JSON valide mais clé requise absente + enum violée
    bad = {"verdict": "MAYBE"}
    mock_invocation(monkeypatch, exit_code=0, last_message=json.dumps(bad))
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["ok"] is False
    assert res["error_class"] == "[SCHEMA_MISMATCH]"
    assert any("findings" in e for e in res["schema_errors"])
    assert any("enum" in e for e in res["schema_errors"])


def test_spawn_empty_output(monkeypatch):
    mock_invocation(monkeypatch, exit_code=0, last_message=None, stdout="  ")
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["error_class"] == "[EMPTY_OUTPUT]"


def test_spawn_nonzero_exit_prime_sur_le_parsing(monkeypatch):
    # même si la sortie contient du JSON valide, exit != 0 => non fiable
    mock_invocation(monkeypatch, exit_code=3,
                    last_message=json.dumps(VALID_PAYLOAD))
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["ok"] is False
    assert res["error_class"] == "[NONZERO_EXIT]"


def test_spawn_timeout(monkeypatch):
    mock_invocation(monkeypatch, timed_out=True)
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["error_class"] == "[TIMEOUT]"


def test_spawn_binaire_introuvable(monkeypatch):
    mock_invocation(monkeypatch, spawn_error="binary-not-found")
    res = sac.spawn_agent("sys", "task", SCHEMA)
    assert res["error_class"] == "[SPAWN_BINARY_NOT_FOUND]"


# ---------------------------------------------------------------------------
# extract_json / validate_schema
# ---------------------------------------------------------------------------

def test_extract_json_none_sur_vide_et_garbage():
    assert sac.extract_json("") is None
    assert sac.extract_json("aucun objet ici { pas fermé") is None


def test_extract_json_string_contenant_accolades():
    raw = 'préambule {"a": "valeur avec { et } dedans", "b": 1} suite'
    assert sac.extract_json(raw) == {"a": "valeur avec { et } dedans", "b": 1}


def test_validate_schema_types_et_items():
    schema = {"type": "object", "required": ["n", "tags"],
              "properties": {"n": {"type": "integer"},
                             "tags": {"type": "array",
                                      "items": {"type": "string"}}}}
    assert sac.validate_schema({"n": 2, "tags": ["a"]}, schema) == []
    errs = sac.validate_schema({"n": True, "tags": ["a", 3]}, schema)
    assert any("$.n" in e for e in errs)          # bool refusé comme integer
    assert any("$.tags[1]" in e for e in errs)


# ---------------------------------------------------------------------------
# compute_verdict — comptage + seuil 95 %
# ---------------------------------------------------------------------------

def _fake_results(ok_count, fail_count, error_class="[JSON_UNPARSEABLE]"):
    results = []
    for i in range(ok_count):
        results.append({"fixture_id": f"fx-{i % 4}", "ok": True,
                        "latency_ms": 1000 + i, "error_class": None})
    for i in range(fail_count):
        results.append({"fixture_id": f"fx-{i % 4}", "ok": False,
                        "latency_ms": 5000, "error_class": error_class})
    return results


def test_verdict_go_a_19_sur_20():
    summary = rex.compute_verdict(_fake_results(19, 1))
    assert summary["parseable_rate"] == 0.95
    assert summary["verdict"] == "GO"
    assert summary["total_runs"] == 20
    assert summary["error_distribution"] == {"[JSON_UNPARSEABLE]": 1}


def test_verdict_nogo_a_18_sur_20():
    summary = rex.compute_verdict(_fake_results(18, 2))
    assert summary["parseable_rate"] == 0.9
    assert summary["verdict"] == "NO-GO"


def test_verdict_distribution_et_mediane():
    results = (_fake_results(2, 1, "[TIMEOUT]")
               + _fake_results(0, 2, "[SCHEMA_MISMATCH]"))
    summary = rex.compute_verdict(results)
    assert summary["error_distribution"] == {"[TIMEOUT]": 1,
                                             "[SCHEMA_MISMATCH]": 2}
    assert summary["median_latency_ms"] == 5000
    assert summary["verdict"] == "NO-GO"


def test_verdict_vide_est_nogo():
    summary = rex.compute_verdict([])
    assert summary["verdict"] == "NO-GO"
    assert summary["parseable_rate"] == 0.0


# ---------------------------------------------------------------------------
# run_experiment — round-robin + pool borné, spawn injecté (aucun codex)
# ---------------------------------------------------------------------------

def test_plan_runs_round_robin():
    fixtures = [{"id": f"f{i}"} for i in range(4)]
    planned = rex.plan_runs(fixtures, 20)
    assert len(planned) == 20
    assert [fx["id"] for fx in planned[:5]] == ["f0", "f1", "f2", "f3", "f0"]
    # 20 runs / 4 fixtures = 5 chacune
    counts = {}
    for fx in planned:
        counts[fx["id"]] = counts.get(fx["id"], 0) + 1
    assert counts == {"f0": 5, "f1": 5, "f2": 5, "f3": 5}


def test_run_experiment_avec_spawn_mocke():
    fixtures = [
        {"id": "a", "system_prompt": "s", "task": "t", "schema": {}},
        {"id": "b", "system_prompt": "s", "task": "t", "schema": {}},
    ]
    seen = []

    def fake_spawn(system_prompt, task, schema, cfg):
        seen.append(schema)
        ok = len(seen) != 3  # le 3e run échoue
        return {"ok": ok, "parsed": {} if ok else None, "raw": "{}",
                "latency_ms": 42,
                "error_class": None if ok else "[TIMEOUT]"}

    results = rex.run_experiment(fixtures, sac.CodexConfig(), total_runs=4,
                                 max_parallel=2, spawn=fake_spawn)
    assert len(results) == 4
    assert [r["fixture_id"] for r in results] == ["a", "b", "a", "b"]
    summary = rex.compute_verdict(results)
    assert summary["parseable_ok"] == 3
    assert summary["verdict"] == "NO-GO"  # 75 % < 95 %


def test_load_fixtures_reelles_et_verdict_go_full_mock(tmp_path):
    """Charge les 4 fixtures livrées, simule 20 complétions parfaites."""
    fixtures = rex.load_fixtures(HERE / "fixtures")
    assert len(fixtures) == 4

    def perfect_spawn(system_prompt, task, schema, cfg):
        obj = _minimal_instance(schema)
        errs = sac.validate_schema(obj, schema)
        assert errs == [], f"fixture-schema auto-instanciation KO: {errs}"
        return {"ok": True, "parsed": obj, "raw": json.dumps(obj),
                "latency_ms": 1, "error_class": None}

    results = rex.run_experiment(fixtures, sac.CodexConfig(), 20, 2,
                                 spawn=perfect_spawn)
    summary = rex.compute_verdict(results)
    assert summary["verdict"] == "GO"
    assert summary["parseable_rate"] == 1.0
    assert all(st == {"runs": 5, "ok": 5}
               for st in summary["per_fixture"].values())


def _minimal_instance(schema):
    """Fabrique une instance minimale conforme à un sous-schéma fixture."""
    t = schema.get("type")
    if t == "object":
        return {k: _minimal_instance(schema.get("properties", {}).get(k, {}))
                for k in schema.get("required", [])}
    if t == "array":
        return [_minimal_instance(schema.get("items", {}))]
    if t == "string":
        return schema["enum"][0] if "enum" in schema else "x"
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    return "x"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
