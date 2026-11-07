from __future__ import annotations

import json
import sys
import time

import pytest

from sdd_scripts import server_control as sc
from sdd_scripts.server_control import PortTarget, parse_target


def test_parse_target_accepts_labelled_port() -> None:
    assert parse_target("Frontend:5173") == PortTarget("Frontend", 5173)


@pytest.mark.parametrize("value", ["5173", ":5173", "Back:0", "Back:65536", "Back:abc"])
def test_parse_target_rejects_invalid_values(value: str) -> None:
    with pytest.raises(Exception):
        parse_target(value)


# ── Audit sécurité 2026-11 : registre de PID, plus de kill aveugle par port ──

def test_stop_without_registry_refuses_and_kills_nothing(tmp_path, monkeypatch, capsys):
    killed: list[int] = []
    monkeypatch.setattr(sc, "stop_pid", lambda pid, **_: killed.append(pid))
    monkeypatch.setattr(sc, "listener_pids", lambda port: {4242})
    rc = sc.main(["--registry", str(tmp_path / "none.json"), "--port", "Db:5432"])
    assert rc == sc.EXIT_REFUSED
    assert killed == []
    assert "aucun registre" in capsys.readouterr().err


def test_unregistered_port_listener_is_not_killed(tmp_path, monkeypatch):
    reg = tmp_path / "pids.json"
    sc.save_registry(reg, [])
    killed: list[int] = []
    monkeypatch.setattr(sc, "stop_pid", lambda pid, **_: killed.append(pid))
    monkeypatch.setattr(sc, "listener_pids", lambda port: {4242})
    rc = sc.cmd_stop([PortTarget("Db", 5432)], reg)
    assert rc == sc.EXIT_REFUSED
    assert killed == []


def test_recycled_pid_with_other_image_is_skipped(tmp_path, monkeypatch):
    reg = tmp_path / "pids.json"
    sc.save_registry(reg, [{"label": "Back", "port": 8080, "pid": 777, "image": "dotnet.exe",
                            "cmd": "dotnet run"}])
    killed: list[int] = []
    monkeypatch.setattr(sc, "stop_pid", lambda pid, **_: killed.append(pid))
    monkeypatch.setattr(sc, "process_image", lambda pid: "explorer.exe")
    rc = sc.cmd_stop([PortTarget("Back", 8080)], reg)
    assert rc == sc.EXIT_REFUSED
    assert killed == []


def test_force_port_keeps_legacy_behaviour(tmp_path, monkeypatch):
    killed: list[int] = []
    calls = {"n": 0}

    def _listeners(port):
        calls["n"] += 1
        return {4242} if calls["n"] == 1 else set()

    monkeypatch.setattr(sc, "stop_pid", lambda pid, **_: killed.append(pid))
    monkeypatch.setattr(sc, "listener_pids", _listeners)
    rc = sc.main(["--registry", str(tmp_path / "none.json"), "--port", "X:9999", "--force-port"])
    assert rc == sc.EXIT_OK
    assert killed == [4242]


def test_start_records_pid_and_stop_kills_it(tmp_path):
    reg = tmp_path / "state" / "serve.pids.json"
    rc = sc.cmd_start("Probe", 45999, str(tmp_path),
                      [sys.executable, "-c", "import time; time.sleep(60)"], reg)
    assert rc == sc.EXIT_OK
    entries = json.loads(reg.read_text(encoding="utf-8"))["processes"]
    assert len(entries) == 1
    pid = entries[0]["pid"]
    assert entries[0]["port"] == 45999 and entries[0]["started_at"]
    assert sc.process_image(pid) is not None
    try:
        rc = sc.cmd_stop([PortTarget("Probe", 45999)], reg)
        assert rc == sc.EXIT_OK
        for _ in range(20):
            if sc.process_image(pid) is None:
                break
            time.sleep(0.2)
        assert sc.process_image(pid) is None
        assert json.loads(reg.read_text(encoding="utf-8"))["processes"] == []
    finally:
        if sc.process_image(pid) is not None:
            sc.stop_pid(pid)
