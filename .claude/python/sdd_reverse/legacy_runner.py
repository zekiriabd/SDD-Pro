"""SDD_Pro Reverse Engineering Phase 4 — Legacy runner (library).

Detects the appropriate runtime for a legacy project (from runner_signatures.yml),
launches the runtime as a subprocess, waits for HTTP readiness, returns a
handle for cleanup.

This module is pure library code (no CLI). The CLI wrapper lives in
sdd_reverse_scripts/legacy_runner.py.

Error class prefixes (cf. rules/reverse-engineering.md):
- [REVERSE_UI_RUNNER_UNSUPPORTED] : no matching signature for language
- [REVERSE_UI_RUNNER_UNAVAILABLE] : binary not in PATH
- [REVERSE_UI_RUNNER_TIMEOUT]     : process up but no HTTP ready before timeout
- [REVERSE_UI_PORT_CONFLICT]      : 5 successive ports occupied
- [REVERSE_UI_ARTIFACT_MISSING]   : required artifact (.csproj, pom.xml) absent
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml


# --------------------------------------------------------------------- types


@dataclass
class RunnerSignature:
    """Declarative runner spec loaded from runner_signatures.yml."""

    language: str
    runner_id: str
    label: str
    detect_cmd: list[str]
    detect_exit_ok: list[int]
    launch_cmd: list[str]  # template with {port}, {abs_project_path}, etc.
    ready_url: str  # template with {port}
    default_port: int
    timeout_s: int
    platform: list[str]
    artifacts_required: list[str] = field(default_factory=list)
    notes: str = ""
    # Host used in base_url returned to caller. Defaults to 127.0.0.1 for
    # POSIX-style servers (php -S, dotnet run, mvn, gradle). IIS Express
    # overrides to "localhost" because HTTP.SYS Host header is strict.
    host: str = "127.0.0.1"


@dataclass
class RunnerError:
    """Structured error with [REVERSE_UI_*] class prefix."""

    code: str  # e.g. "REVERSE_UI_RUNNER_UNAVAILABLE"
    detail: str
    fix: str = ""


@dataclass
class LaunchResult:
    """Outcome of launch_legacy(). Either ok=True with handle, or ok=False with errors."""

    ok: bool
    mode: str  # "runtime" | "fallback-static"
    language: str = ""
    runner_id: str = ""
    base_url: str = ""
    pid: int | None = None
    pidfile_path: str = ""
    process: subprocess.Popen[bytes] | None = None
    ready_at: str = ""
    errors: list[RunnerError] = field(default_factory=list)
    warnings: list[RunnerError] = field(default_factory=list)


class RunnerNotSupportedError(Exception):
    """No signature in runner_signatures.yml matches the language."""


class RunnerBinaryMissingError(Exception):
    """Runner binary not found in PATH (detect_cmd failed)."""


class RunnerArtifactMissingError(Exception):
    """A required project artifact (e.g. *.csproj) is absent."""


class RunnerPortConflictError(Exception):
    """5 successive ports occupied around default_port."""


class RunnerReadyTimeoutError(Exception):
    """Process started but HTTP not ready before timeout_s."""


# ----------------------------------------------------------- signatures load


def load_signatures(yaml_path: Path) -> list[RunnerSignature]:
    """Parse runner_signatures.yml into a list of RunnerSignature.

    Raises FileNotFoundError if yaml_path absent, ValueError if schema invalid.
    """
    if not yaml_path.is_file():
        raise FileNotFoundError(f"runner_signatures.yml not found at {yaml_path}")

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "runners" not in raw:
        raise ValueError(f"runner_signatures.yml schema invalid (missing 'runners' key)")

    if raw.get("schema_version") != 1:
        raise ValueError(
            f"runner_signatures.yml schema_version unsupported "
            f"(got {raw.get('schema_version')!r}, expected 1)"
        )

    result: list[RunnerSignature] = []
    for entry in raw["runners"]:
        result.append(
            RunnerSignature(
                language=entry["language"],
                runner_id=entry["runner_id"],
                label=entry.get("label", entry["runner_id"]),
                detect_cmd=list(entry["detect_cmd"]),
                detect_exit_ok=list(entry.get("detect_exit_ok", [0])),
                launch_cmd=list(entry["launch_cmd"]),
                ready_url=entry["ready_url"],
                default_port=int(entry["default_port"]),
                timeout_s=int(entry.get("timeout_s", 60)),
                platform=list(entry.get("platform", ["win32", "linux", "darwin"])),
                artifacts_required=list(entry.get("artifacts_required", [])),
                notes=entry.get("notes", ""),
                host=entry.get("host", "127.0.0.1"),
            )
        )
    return result


def detect_signature_for_language(
    signatures: list[RunnerSignature],
    language: str,
    platform: str | None = None,
) -> RunnerSignature | None:
    """Return the first signature matching language and current platform.

    Platform defaults to sys.platform. Returns None if no match.
    """
    plat = platform if platform is not None else sys.platform
    for sig in signatures:
        if sig.language == language and plat in sig.platform:
            return sig
    return None


# ------------------------------------------------------------- availability


def is_runner_available(
    sig: RunnerSignature,
    *,
    _subprocess_run: Any = None,  # injected for tests
) -> bool:
    """Return True if the runner binary is present and executable on this system.

    Runs detect_cmd with a 5s timeout. Treats exit codes in detect_exit_ok as OK.
    Captures stdout/stderr to avoid polluting the parent CLI.
    """
    runner = _subprocess_run if _subprocess_run is not None else subprocess.run
    try:
        completed = runner(
            sig.detect_cmd,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return completed.returncode in sig.detect_exit_ok


# --------------------------------------------------------- artifact lookup


def find_artifact_path(project_path: Path, pattern: str) -> Path | None:
    """Find the first file matching a glob pattern (e.g. '*.csproj') under project_path.

    Searches recursively. Returns None if no match. Excludes hidden dirs (.git, .sys).
    """
    for candidate in sorted(project_path.rglob(pattern)):
        # Skip files inside hidden / generated dirs
        parts_set = set(candidate.relative_to(project_path).parts)
        if any(p.startswith(".") for p in parts_set):
            continue
        if {"bin", "obj", "target", "build", "node_modules"} & parts_set:
            continue
        return candidate
    return None


def resolve_launch_tokens(
    launch_cmd: list[str],
    project_path: Path,
    port: int,
    sig: RunnerSignature,
) -> list[str]:
    """Substitute {port}, {abs_project_path}, {csproj_path}, {pom_path},
    {gradle_path} in launch_cmd.

    Raises RunnerArtifactMissingError if a referenced artifact is absent
    or if artifacts_required contains a pattern with no match.
    """
    abs_project_path = str(project_path.resolve())

    # Pre-compute artifact paths only if referenced
    joined = " ".join(launch_cmd)
    csproj_path = ""
    pom_path = ""
    gradle_path = ""

    if "{csproj_path}" in joined:
        match = find_artifact_path(project_path, "*.csproj")
        if match is None:
            raise RunnerArtifactMissingError(
                f"runner {sig.runner_id} requires *.csproj but none found under {project_path}"
            )
        csproj_path = str(match.resolve())

    if "{pom_path}" in joined:
        match = find_artifact_path(project_path, "pom.xml")
        if match is None:
            raise RunnerArtifactMissingError(
                f"runner {sig.runner_id} requires pom.xml but none found under {project_path}"
            )
        pom_path = str(match.resolve())

    if "{gradle_path}" in joined:
        match = find_artifact_path(project_path, "build.gradle")
        if match is None:
            match = find_artifact_path(project_path, "build.gradle.kts")
        if match is None:
            raise RunnerArtifactMissingError(
                f"runner {sig.runner_id} requires build.gradle[.kts] but none found under {project_path}"
            )
        gradle_path = str(match.resolve())

    # Validate artifacts_required even if not referenced in launch_cmd
    for pattern in sig.artifacts_required:
        if find_artifact_path(project_path, pattern) is None:
            raise RunnerArtifactMissingError(
                f"runner {sig.runner_id} requires artifact matching {pattern!r} under {project_path}"
            )

    return [
        token.format(
            port=port,
            abs_project_path=abs_project_path,
            csproj_path=csproj_path,
            pom_path=pom_path,
            gradle_path=gradle_path,
        )
        for token in launch_cmd
    ]


# -------------------------------------------------------------- port mgmt


def _is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if port is free to bind on host."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        result = sock.connect_ex((host, port))
        # connect_ex returns 0 if a service is already listening (port occupied)
        return result != 0
    finally:
        sock.close()


def find_free_port(
    default_port: int,
    max_attempts: int = 5,
    *,
    _is_free: Any = None,  # injected for tests
) -> int:
    """Find a free port starting at default_port, trying max_attempts consecutive ports.

    Raises RunnerPortConflictError if all attempts fail.
    """
    checker = _is_free if _is_free is not None else _is_port_free
    for offset in range(max_attempts):
        port = default_port + offset
        if checker(port):
            return port
    raise RunnerPortConflictError(
        f"ports {default_port}-{default_port + max_attempts - 1} all occupied"
    )


# ---------------------------------------------------------------- ready check


def wait_ready(
    ready_url: str,
    timeout_s: int,
    *,
    _http_get: Any = None,  # injected for tests
    _sleep: Any = None,  # injected for tests
    _now: Any = None,  # injected for tests
) -> bool:
    """Poll ready_url with HTTP GET until status_code < 500 or timeout_s elapsed.

    Returns True if ready, False if timeout (no exception — caller decides).

    Per ADR: status codes 200/302/401/403/404 all count as "process up"
    (only 5xx or connection error mean not ready).
    """
    sleeper = _sleep if _sleep is not None else time.sleep
    now = _now if _now is not None else time.time

    def _default_http_get(url: str) -> int:
        req = Request(url, headers={"User-Agent": "SDDPro-Reverse-Runner/1.0"})
        with urlopen(req, timeout=2) as resp:
            return int(resp.status)

    fetcher = _http_get if _http_get is not None else _default_http_get

    deadline = now() + timeout_s
    while now() < deadline:
        try:
            status = fetcher(ready_url)
        except (URLError, ConnectionError, OSError, TimeoutError):
            sleeper(1)
            continue
        if status < 500:
            return True
        sleeper(1)
    return False


# --------------------------------------------------------------- pidfile


def write_pidfile(project_path: Path, pid: int, runner_id: str, port: int) -> Path:
    """Write {project_path}/.sys/.runner.pid with PID + metadata.

    Returns the pidfile path. Idempotent : overwrites any existing pidfile.
    """
    sys_dir = project_path / ".sys"
    sys_dir.mkdir(parents=True, exist_ok=True)
    pidfile = sys_dir / ".runner.pid"
    pidfile.write_text(
        f"{pid}\n{runner_id}\n{port}\n{int(time.time())}\n",
        encoding="utf-8",
    )
    return pidfile


def read_pidfile(project_path: Path) -> dict[str, Any] | None:
    """Read PID + metadata from {project_path}/.sys/.runner.pid.

    Returns None if absent or malformed.
    """
    pidfile = project_path / ".sys" / ".runner.pid"
    if not pidfile.is_file():
        return None
    try:
        lines = pidfile.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) < 4:
            return None
        return {
            "pid": int(lines[0]),
            "runner_id": lines[1],
            "port": int(lines[2]),
            "started_at": int(lines[3]),
            "path": str(pidfile),
        }
    except (ValueError, OSError):
        return None


def cleanup_pidfile_process(
    project_path: Path,
    *,
    _kill: Any = None,  # injected for tests
) -> bool:
    """Terminate the process referenced in {project_path}/.sys/.runner.pid, if any.

    Returns True if a process was killed (or pidfile removed), False if nothing to do.
    Always best-effort : silent if pid no longer exists.
    """
    meta = read_pidfile(project_path)
    if meta is None:
        return False

    killer = _kill if _kill is not None else os.kill
    pid: int = meta["pid"]
    try:
        # Send SIGTERM (Windows: TerminateProcess via os.kill)
        killer(pid, _get_terminate_signal())
    except (ProcessLookupError, PermissionError, OSError):
        # Process already gone or we can't kill it; remove pidfile anyway
        pass

    pidfile = Path(meta["path"])
    try:
        pidfile.unlink()
    except OSError:
        pass
    return True


def _get_terminate_signal() -> int:
    """SIGTERM on POSIX, equivalent on Windows."""
    if sys.platform == "win32":
        # On Windows, os.kill(pid, signal.CTRL_BREAK_EVENT) works for console apps;
        # for general process termination, use signal.SIGTERM (which Python maps
        # to TerminateProcess via the C runtime).
        import signal

        return signal.SIGTERM
    import signal

    return signal.SIGTERM


# ------------------------------------------------------------- main launch


def launch_legacy(
    project_path: Path,
    signatures: list[RunnerSignature],
    language: str,
    *,
    port: int | None = None,
    timeout_s_override: int | None = None,
    platform: str | None = None,
    _subprocess_popen: Any = None,  # injected for tests
    _subprocess_run: Any = None,  # injected for tests (used by is_runner_available)
    _is_free: Any = None,  # injected for tests
    _wait_ready_fn: Any = None,  # injected for tests
) -> LaunchResult:
    """Detect + launch the legacy runtime for the given language.

    Returns LaunchResult with ok=True (mode=runtime) on success,
    or ok=False (mode=fallback-static) with errors[] on any failure.
    Never raises — failures are encoded in the LaunchResult.
    """
    plat = platform if platform is not None else sys.platform
    sig = detect_signature_for_language(signatures, language, plat)
    if sig is None:
        return LaunchResult(
            ok=False,
            mode="fallback-static",
            language=language,
            errors=[
                RunnerError(
                    code="REVERSE_UI_RUNNER_UNSUPPORTED",
                    detail=f"no runner signature for language {language!r} on platform {plat!r}",
                    fix=(
                        "add a 'runners[]' entry in "
                        ".claude/python/sdd_reverse/runner_signatures.yml "
                        f"with language={language!r} and platform including {plat!r}"
                    ),
                )
            ],
        )

    # 1. Detect binary availability
    if not is_runner_available(sig, _subprocess_run=_subprocess_run):
        return LaunchResult(
            ok=False,
            mode="fallback-static",
            language=language,
            runner_id=sig.runner_id,
            errors=[
                RunnerError(
                    code="REVERSE_UI_RUNNER_UNAVAILABLE",
                    detail=(
                        f"runner binary not found: {sig.detect_cmd[0]!r} "
                        f"(detect_cmd: {sig.detect_cmd})"
                    ),
                    fix=(
                        f"install {sig.label} and ensure {sig.detect_cmd[0]!r} "
                        "is in PATH"
                    ),
                )
            ],
        )

    # 2. Resolve artifacts + tokens
    if port is None:
        try:
            port = find_free_port(sig.default_port, max_attempts=5, _is_free=_is_free)
        except RunnerPortConflictError as exc:
            return LaunchResult(
                ok=False,
                mode="fallback-static",
                language=language,
                runner_id=sig.runner_id,
                errors=[
                    RunnerError(
                        code="REVERSE_UI_PORT_CONFLICT",
                        detail=str(exc),
                        fix=(
                            "free up the port range or set default_port in "
                            "runner_signatures.yml to a different value"
                        ),
                    )
                ],
            )

    try:
        resolved_cmd = resolve_launch_tokens(sig.launch_cmd, project_path, port, sig)
    except RunnerArtifactMissingError as exc:
        return LaunchResult(
            ok=False,
            mode="fallback-static",
            language=language,
            runner_id=sig.runner_id,
            errors=[
                RunnerError(
                    code="REVERSE_UI_ARTIFACT_MISSING",
                    detail=str(exc),
                    fix="check the legacy project contains the required manifest files",
                )
            ],
        )

    ready_url = sig.ready_url.format(port=port)
    effective_timeout = (
        timeout_s_override if timeout_s_override is not None else sig.timeout_s
    )

    # 3. Spawn subprocess
    popener = _subprocess_popen if _subprocess_popen is not None else subprocess.Popen
    try:
        proc = popener(
            resolved_cmd,
            cwd=str(project_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except (FileNotFoundError, OSError) as exc:
        return LaunchResult(
            ok=False,
            mode="fallback-static",
            language=language,
            runner_id=sig.runner_id,
            errors=[
                RunnerError(
                    code="REVERSE_UI_RUNNER_UNAVAILABLE",
                    detail=f"subprocess failed: {exc}",
                    fix=(
                        f"verify {sig.detect_cmd[0]!r} is callable and the launch "
                        f"command {resolved_cmd!r} is valid"
                    ),
                )
            ],
        )

    pidfile = write_pidfile(project_path, proc.pid, sig.runner_id, port)

    # 4. Wait ready
    ready_fn = _wait_ready_fn if _wait_ready_fn is not None else wait_ready
    is_ready = ready_fn(ready_url, effective_timeout)
    if not is_ready:
        # Cleanup the process we just started
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            pidfile.unlink()
        except OSError:
            pass
        return LaunchResult(
            ok=False,
            mode="fallback-static",
            language=language,
            runner_id=sig.runner_id,
            base_url=f"http://{sig.host}:{port}",
            errors=[
                RunnerError(
                    code="REVERSE_UI_RUNNER_TIMEOUT",
                    detail=(
                        f"process pid={proc.pid} started but HTTP {ready_url!r} "
                        f"did not respond < 500 within {effective_timeout}s"
                    ),
                    fix=(
                        "increase timeout_s in runner_signatures.yml, "
                        "check legacy logs in stderr, or verify the legacy "
                        "actually serves a route at /"
                    ),
                )
            ],
        )

    return LaunchResult(
        ok=True,
        mode="runtime",
        language=language,
        runner_id=sig.runner_id,
        base_url=f"http://{sig.host}:{port}",
        pid=proc.pid,
        pidfile_path=str(pidfile),
        process=proc,
        ready_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
