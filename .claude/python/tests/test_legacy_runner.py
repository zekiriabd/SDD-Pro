"""Tests for sdd_reverse.legacy_runner — Phase 4 runtime detection + launch.

Covers:
- load_signatures (valid YAML, missing file, schema)
- detect_signature_for_language (match, platform filter, none)
- is_runner_available (subprocess.run mocked : success / FileNotFoundError / timeout / non-zero exit)
- find_artifact_path (glob recursive, hidden/bin/obj/target dirs excluded)
- resolve_launch_tokens (port + abs_project_path + csproj_path + pom_path + gradle_path + missing artifact)
- find_free_port (default OK, default occupied next free, all occupied raises)
- wait_ready (immediate 200, 503-then-200, timeout, connection error)
- write_pidfile + read_pidfile + cleanup_pidfile_process
- launch_legacy orchestration end-to-end with mocks
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sdd_reverse import legacy_runner


SIGNATURES_PATH = (
    Path(__file__).resolve().parent.parent / "sdd_reverse" / "runner_signatures.yml"
)


# --------------------------------------------------------------- fixtures


@pytest.fixture
def signatures():
    return legacy_runner.load_signatures(SIGNATURES_PATH)


@pytest.fixture
def minimal_sig():
    """A standalone RunnerSignature used for synthetic tests."""
    return legacy_runner.RunnerSignature(
        language="test-lang",
        runner_id="test-runner",
        label="Test runner",
        detect_cmd=["echo", "--version"],
        detect_exit_ok=[0],
        launch_cmd=["echo", "--port={port}", "--path={abs_project_path}"],
        ready_url="http://127.0.0.1:{port}/",
        default_port=9990,
        timeout_s=5,
        platform=["win32", "linux", "darwin"],
        artifacts_required=[],
    )


# ------------------------------------------------------------- signatures


def test_load_signatures_returns_list_of_runner_signature(signatures):
    assert isinstance(signatures, list)
    assert len(signatures) >= 5  # we ship 6 entries
    ids = {s.runner_id for s in signatures}
    for expected in ("iisexpress", "dotnet-run", "maven-spring-boot",
                     "gradle-spring-boot", "php-builtin", "laravel-artisan"):
        assert expected in ids, f"missing runner_id: {expected}"


def test_load_signatures_missing_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        legacy_runner.load_signatures(Path("/does/not/exist.yml"))


def test_load_signatures_invalid_schema_version(tmp_path):
    p = tmp_path / "bad.yml"
    p.write_text("schema_version: 99\nrunners: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        legacy_runner.load_signatures(p)


def test_load_signatures_missing_runners_key(tmp_path):
    p = tmp_path / "bad.yml"
    p.write_text("schema_version: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="runners"):
        legacy_runner.load_signatures(p)


def test_load_signatures_iisexpress_platform_is_win32_only(signatures):
    iis = next(s for s in signatures if s.runner_id == "iisexpress")
    assert iis.platform == ["win32"]


# ---------------------------------------------------- detect_signature


def test_detect_signature_returns_first_match(signatures):
    match = legacy_runner.detect_signature_for_language(
        signatures, "dotnet-webforms", platform="win32"
    )
    assert match is not None
    assert match.runner_id == "iisexpress"


def test_detect_signature_respects_platform_filter(signatures):
    # iisexpress is win32-only — should NOT match on linux
    match = legacy_runner.detect_signature_for_language(
        signatures, "dotnet-webforms", platform="linux"
    )
    assert match is None


def test_detect_signature_no_match_returns_none(signatures):
    assert legacy_runner.detect_signature_for_language(
        signatures, "cobol", platform="win32"
    ) is None


def test_detect_signature_defaults_to_sys_platform(signatures):
    # Smoke : just call without platform arg
    legacy_runner.detect_signature_for_language(signatures, "php-procedural")


# ----------------------------------------------------- is_runner_available


def test_is_runner_available_returns_true_on_known_exit_code(minimal_sig):
    fake_run = MagicMock(return_value=MagicMock(returncode=0))
    assert legacy_runner.is_runner_available(minimal_sig, _subprocess_run=fake_run) is True
    fake_run.assert_called_once()


def test_is_runner_available_returns_true_for_iisexpress_exit_code_1():
    """iisexpress.exe /? returns non-zero but prints usage : exit 1 is OK per signature."""
    sig = legacy_runner.RunnerSignature(
        language="x", runner_id="x", label="x",
        detect_cmd=["iisexpress.exe", "/?"],
        detect_exit_ok=[0, 1],
        launch_cmd=[], ready_url="", default_port=5099, timeout_s=60,
        platform=["win32"],
    )
    fake_run = MagicMock(return_value=MagicMock(returncode=1))
    assert legacy_runner.is_runner_available(sig, _subprocess_run=fake_run) is True


def test_is_runner_available_returns_false_on_file_not_found(minimal_sig):
    fake_run = MagicMock(side_effect=FileNotFoundError("binary missing"))
    assert legacy_runner.is_runner_available(minimal_sig, _subprocess_run=fake_run) is False


def test_is_runner_available_returns_false_on_unknown_exit(minimal_sig):
    fake_run = MagicMock(return_value=MagicMock(returncode=127))
    assert legacy_runner.is_runner_available(minimal_sig, _subprocess_run=fake_run) is False


def test_is_runner_available_returns_false_on_timeout(minimal_sig):
    import subprocess as sp
    fake_run = MagicMock(side_effect=sp.TimeoutExpired(minimal_sig.detect_cmd, 5))
    assert legacy_runner.is_runner_available(minimal_sig, _subprocess_run=fake_run) is False


# -------------------------------------------------------- find_artifact_path


def test_find_artifact_path_finds_csproj(tmp_path):
    (tmp_path / "MyApp.csproj").write_text("<Project/>", encoding="utf-8")
    found = legacy_runner.find_artifact_path(tmp_path, "*.csproj")
    assert found is not None
    assert found.name == "MyApp.csproj"


def test_find_artifact_path_searches_recursively(tmp_path):
    (tmp_path / "src" / "deep").mkdir(parents=True)
    target = tmp_path / "src" / "deep" / "MyApp.csproj"
    target.write_text("<Project/>", encoding="utf-8")
    found = legacy_runner.find_artifact_path(tmp_path, "*.csproj")
    assert found is not None
    assert found == target


def test_find_artifact_path_skips_hidden_dirs(tmp_path):
    (tmp_path / ".sys").mkdir()
    (tmp_path / ".sys" / "Ghost.csproj").write_text("<Project/>", encoding="utf-8")
    assert legacy_runner.find_artifact_path(tmp_path, "*.csproj") is None


def test_find_artifact_path_skips_bin_obj_target(tmp_path):
    for skipdir in ("bin", "obj", "target", "build", "node_modules"):
        (tmp_path / skipdir).mkdir()
        (tmp_path / skipdir / "Ignored.csproj").write_text("<Project/>", encoding="utf-8")
    assert legacy_runner.find_artifact_path(tmp_path, "*.csproj") is None


def test_find_artifact_path_no_match_returns_none(tmp_path):
    assert legacy_runner.find_artifact_path(tmp_path, "*.csproj") is None


# ----------------------------------------------------- resolve_launch_tokens


def test_resolve_launch_tokens_substitutes_port_and_path(tmp_path, minimal_sig):
    resolved = legacy_runner.resolve_launch_tokens(
        ["echo", "--port={port}", "--path={abs_project_path}"],
        tmp_path,
        port=5099,
        sig=minimal_sig,
    )
    assert resolved[0] == "echo"
    assert resolved[1] == "--port=5099"
    assert str(tmp_path.resolve()) in resolved[2]


def test_resolve_launch_tokens_csproj_path_when_present(tmp_path, minimal_sig):
    (tmp_path / "MyApp.csproj").write_text("<Project/>", encoding="utf-8")
    resolved = legacy_runner.resolve_launch_tokens(
        ["dotnet", "run", "--project", "{csproj_path}"],
        tmp_path,
        port=5100,
        sig=minimal_sig,
    )
    assert resolved[-1].endswith("MyApp.csproj")


def test_resolve_launch_tokens_raises_when_csproj_missing(tmp_path, minimal_sig):
    with pytest.raises(legacy_runner.RunnerArtifactMissingError, match=r"\*\.csproj"):
        legacy_runner.resolve_launch_tokens(
            ["dotnet", "run", "--project", "{csproj_path}"],
            tmp_path,
            port=5100,
            sig=minimal_sig,
        )


def test_resolve_launch_tokens_pom_path_when_present(tmp_path, minimal_sig):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    resolved = legacy_runner.resolve_launch_tokens(
        ["mvn", "-f", "{pom_path}", "spring-boot:run"],
        tmp_path,
        port=8081,
        sig=minimal_sig,
    )
    assert resolved[2].endswith("pom.xml")


def test_resolve_launch_tokens_gradle_path_kts_fallback(tmp_path, minimal_sig):
    # Only build.gradle.kts present (no .gradle)
    (tmp_path / "build.gradle.kts").write_text("// kts", encoding="utf-8")
    resolved = legacy_runner.resolve_launch_tokens(
        ["gradle", "-b", "{gradle_path}", "bootRun"],
        tmp_path,
        port=8082,
        sig=minimal_sig,
    )
    assert resolved[2].endswith(("build.gradle", "build.gradle.kts"))


def test_resolve_launch_tokens_artifacts_required_missing(tmp_path):
    sig_with_required = legacy_runner.RunnerSignature(
        language="x", runner_id="x", label="x",
        detect_cmd=["echo"], detect_exit_ok=[0],
        launch_cmd=["echo"], ready_url="", default_port=1,
        timeout_s=10, platform=["linux"],
        artifacts_required=["composer.json"],
    )
    with pytest.raises(legacy_runner.RunnerArtifactMissingError, match="composer.json"):
        legacy_runner.resolve_launch_tokens(["echo"], tmp_path, port=1, sig=sig_with_required)


# ------------------------------------------------------------ find_free_port


def test_find_free_port_returns_default_when_free():
    free_checker = MagicMock(return_value=True)
    assert legacy_runner.find_free_port(5099, max_attempts=5, _is_free=free_checker) == 5099


def test_find_free_port_skips_occupied_returns_next():
    seq = iter([False, False, True])
    free_checker = lambda port, host="127.0.0.1": next(seq)
    assert legacy_runner.find_free_port(5099, max_attempts=5, _is_free=free_checker) == 5101


def test_find_free_port_all_occupied_raises():
    with pytest.raises(legacy_runner.RunnerPortConflictError, match="5099-5103"):
        legacy_runner.find_free_port(
            5099, max_attempts=5, _is_free=MagicMock(return_value=False)
        )


# --------------------------------------------------------------- wait_ready


def test_wait_ready_returns_true_on_immediate_200():
    fake_get = MagicMock(return_value=200)
    fake_now = MagicMock(side_effect=[1000.0, 1000.0])
    fake_sleep = MagicMock()
    ok = legacy_runner.wait_ready(
        "http://x/", 10, _http_get=fake_get, _sleep=fake_sleep, _now=fake_now
    )
    assert ok is True
    fake_sleep.assert_not_called()


def test_wait_ready_accepts_401_and_302_as_ready():
    # status_code < 500 = process up
    for status in (200, 302, 401, 403, 404):
        ok = legacy_runner.wait_ready(
            "http://x/", 10,
            _http_get=MagicMock(return_value=status),
            _sleep=MagicMock(),
            _now=MagicMock(side_effect=[0, 0]),
        )
        assert ok is True, f"status {status} should count as ready"


def test_wait_ready_retries_on_connection_error():
    seq = iter([ConnectionError("boom"), 200])
    def fetcher(url):
        result = next(seq)
        if isinstance(result, Exception):
            raise result
        return result
    fake_now = MagicMock(side_effect=[0, 1, 2])
    ok = legacy_runner.wait_ready(
        "http://x/", 60,
        _http_get=fetcher,
        _sleep=MagicMock(),
        _now=fake_now,
    )
    assert ok is True


def test_wait_ready_times_out():
    fake_now = MagicMock(side_effect=[0, 5, 11, 12])  # exceed timeout 10
    ok = legacy_runner.wait_ready(
        "http://x/", 10,
        _http_get=MagicMock(side_effect=ConnectionError("boom")),
        _sleep=MagicMock(),
        _now=fake_now,
    )
    assert ok is False


def test_wait_ready_retries_on_500():
    seq = iter([500, 500, 200])
    fetcher = lambda url: next(seq)
    fake_now = MagicMock(side_effect=[0, 1, 2, 3])
    ok = legacy_runner.wait_ready(
        "http://x/", 60,
        _http_get=fetcher,
        _sleep=MagicMock(),
        _now=fake_now,
    )
    assert ok is True


# ---------------------------------------------------- pidfile lifecycle


def test_write_and_read_pidfile_roundtrip(tmp_path):
    pf = legacy_runner.write_pidfile(tmp_path, pid=12345, runner_id="iisexpress", port=5099)
    assert pf.is_file()
    meta = legacy_runner.read_pidfile(tmp_path)
    assert meta is not None
    assert meta["pid"] == 12345
    assert meta["runner_id"] == "iisexpress"
    assert meta["port"] == 5099


def test_read_pidfile_absent_returns_none(tmp_path):
    assert legacy_runner.read_pidfile(tmp_path) is None


def test_read_pidfile_malformed_returns_none(tmp_path):
    sys_dir = tmp_path / ".sys"
    sys_dir.mkdir()
    (sys_dir / ".runner.pid").write_text("not-a-pid", encoding="utf-8")
    assert legacy_runner.read_pidfile(tmp_path) is None


def test_cleanup_pidfile_process_kills_and_removes(tmp_path):
    legacy_runner.write_pidfile(tmp_path, pid=9999, runner_id="x", port=1)
    fake_kill = MagicMock()
    result = legacy_runner.cleanup_pidfile_process(tmp_path, _kill=fake_kill)
    assert result is True
    fake_kill.assert_called_once()
    # pidfile removed
    assert legacy_runner.read_pidfile(tmp_path) is None


def test_cleanup_pidfile_process_tolerates_dead_pid(tmp_path):
    """If the PID is gone (ProcessLookupError), still remove pidfile."""
    legacy_runner.write_pidfile(tmp_path, pid=9999, runner_id="x", port=1)
    fake_kill = MagicMock(side_effect=ProcessLookupError("gone"))
    result = legacy_runner.cleanup_pidfile_process(tmp_path, _kill=fake_kill)
    assert result is True
    assert (tmp_path / ".sys" / ".runner.pid").is_file() is False


def test_cleanup_pidfile_process_no_pidfile_returns_false(tmp_path):
    assert legacy_runner.cleanup_pidfile_process(tmp_path) is False


# ----------------------------------------------------- launch_legacy E2E


def test_launch_legacy_no_signature_returns_fallback_static(tmp_path, signatures):
    result = legacy_runner.launch_legacy(
        tmp_path, signatures, language="unknown-cobol-thing"
    )
    assert result.ok is False
    assert result.mode == "fallback-static"
    assert result.errors
    assert result.errors[0].code == "REVERSE_UI_RUNNER_UNSUPPORTED"


def test_launch_legacy_binary_unavailable_returns_fallback(tmp_path, signatures):
    fake_run = MagicMock(return_value=MagicMock(returncode=127))
    result = legacy_runner.launch_legacy(
        tmp_path, signatures,
        language="php-procedural",
        _subprocess_run=fake_run,
        platform="linux",
    )
    assert result.ok is False
    assert result.mode == "fallback-static"
    assert result.errors[0].code == "REVERSE_UI_RUNNER_UNAVAILABLE"


def test_launch_legacy_artifact_missing_returns_fallback(tmp_path, signatures):
    # dotnet-mvc needs *.csproj but tmp_path is empty
    fake_run = MagicMock(return_value=MagicMock(returncode=0))
    result = legacy_runner.launch_legacy(
        tmp_path, signatures,
        language="dotnet-mvc",
        _subprocess_run=fake_run,
        _is_free=MagicMock(return_value=True),
        platform="linux",
    )
    assert result.ok is False
    assert result.errors[0].code == "REVERSE_UI_ARTIFACT_MISSING"


def test_launch_legacy_ready_timeout_terminates_process_and_fallback(
    tmp_path, signatures
):
    """Simulate runner detected + binary OK + subprocess spawned but HTTP never ready."""
    fake_proc = MagicMock()
    fake_proc.pid = 7777
    fake_proc.terminate = MagicMock()

    def popen_factory(cmd, **kwargs):
        return fake_proc

    fake_run = MagicMock(return_value=MagicMock(returncode=0))
    fake_wait = MagicMock(return_value=False)  # never ready

    result = legacy_runner.launch_legacy(
        tmp_path, signatures,
        language="php-procedural",
        _subprocess_run=fake_run,
        _subprocess_popen=popen_factory,
        _is_free=MagicMock(return_value=True),
        _wait_ready_fn=fake_wait,
        platform="linux",
    )
    assert result.ok is False
    assert result.errors[0].code == "REVERSE_UI_RUNNER_TIMEOUT"
    fake_proc.terminate.assert_called_once()
    # pidfile cleaned up
    assert (tmp_path / ".sys" / ".runner.pid").is_file() is False


def test_launch_legacy_happy_path_runtime_mode(tmp_path, signatures):
    """Full success : detect OK + binary OK + spawn OK + ready OK."""
    fake_proc = MagicMock()
    fake_proc.pid = 12345

    fake_run = MagicMock(return_value=MagicMock(returncode=0))
    fake_wait = MagicMock(return_value=True)

    result = legacy_runner.launch_legacy(
        tmp_path, signatures,
        language="php-procedural",
        _subprocess_run=fake_run,
        _subprocess_popen=lambda cmd, **kw: fake_proc,
        _is_free=MagicMock(return_value=True),
        _wait_ready_fn=fake_wait,
        platform="linux",
    )
    assert result.ok is True
    assert result.mode == "runtime"
    assert result.runner_id == "php-builtin"
    assert result.pid == 12345
    assert result.base_url.startswith("http://127.0.0.1:")
    # pidfile written
    assert legacy_runner.read_pidfile(tmp_path) is not None


def test_launch_legacy_port_conflict_returns_fallback(tmp_path, signatures):
    fake_run = MagicMock(return_value=MagicMock(returncode=0))
    fake_is_free = MagicMock(return_value=False)  # all ports occupied

    result = legacy_runner.launch_legacy(
        tmp_path, signatures,
        language="php-procedural",
        _subprocess_run=fake_run,
        _is_free=fake_is_free,
        platform="linux",
    )
    assert result.ok is False
    assert result.errors[0].code == "REVERSE_UI_PORT_CONFLICT"


def test_launch_legacy_with_explicit_port_skips_port_finder(tmp_path, signatures):
    fake_proc = MagicMock()
    fake_proc.pid = 8888
    fake_run = MagicMock(return_value=MagicMock(returncode=0))
    fake_wait = MagicMock(return_value=True)
    # is_free should NOT be called when port is explicit
    fake_is_free = MagicMock()

    result = legacy_runner.launch_legacy(
        tmp_path, signatures,
        language="php-procedural",
        port=9999,
        _subprocess_run=fake_run,
        _subprocess_popen=lambda cmd, **kw: fake_proc,
        _wait_ready_fn=fake_wait,
        _is_free=fake_is_free,
        platform="linux",
    )
    assert result.ok is True
    assert "9999" in result.base_url
    fake_is_free.assert_not_called()


def test_launch_legacy_popen_oserror_returns_fallback(tmp_path, signatures):
    fake_run = MagicMock(return_value=MagicMock(returncode=0))

    def boom(cmd, **kw):
        raise OSError("denied")

    result = legacy_runner.launch_legacy(
        tmp_path, signatures,
        language="php-procedural",
        _subprocess_run=fake_run,
        _subprocess_popen=boom,
        _is_free=MagicMock(return_value=True),
        platform="linux",
    )
    assert result.ok is False
    assert result.errors[0].code == "REVERSE_UI_RUNNER_UNAVAILABLE"


# --------------------------------------------------------- internal port helper


def test_is_port_free_smoke():
    """Just ensure the real socket-based check returns a bool (system-dependent value)."""
    result = legacy_runner._is_port_free(65432)
    assert isinstance(result, bool)
