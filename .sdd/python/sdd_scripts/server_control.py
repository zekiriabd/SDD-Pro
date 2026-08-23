#!/usr/bin/env python3
"""Stop SDD runtime processes listening on explicitly supplied ports."""
from __future__ import annotations
import argparse
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass

@dataclass(frozen=True)
class PortTarget:
    label: str
    port: int

def parse_target(value: str) -> PortTarget:
    label, separator, raw_port = value.rpartition(":")
    if not separator or not label.strip():
        raise argparse.ArgumentTypeError("expected LABEL:PORT")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return PortTarget(label.strip(), port)

def _windows_listener_pids(port: int) -> set[int]:
    result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False)
    pattern = re.compile(r"^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$", re.I)
    return {int(match.group(2)) for line in result.stdout.splitlines() if (match := pattern.match(line)) and int(match.group(1)) == port}

def _unix_listener_pids(port: int) -> set[int]:
    lsof = shutil.which("lsof")
    if not lsof:
        return set()
    result = subprocess.run([lsof, "-ti", f":{port}"], capture_output=True, text=True, check=False)
    return {int(pid) for pid in result.stdout.split() if pid.isdigit()}

def listener_pids(port: int) -> set[int]:
    return _windows_listener_pids(port) if os.name == "nt" else _unix_listener_pids(port)

def stop_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
    else:
        os.kill(pid, signal.SIGTERM)

def stop_target(target: PortTarget) -> tuple[str, set[int]]:
    pids = listener_pids(target.port)
    if not pids:
        return "not-running", set()
    for pid in pids:
        stop_pid(pid)
    time.sleep(0.3)
    remaining = listener_pids(target.port)
    if remaining and os.name != "nt":
        for pid in remaining:
            os.kill(pid, signal.SIGKILL)
    return ("stopped" if not listener_pids(target.port) else "partial"), pids

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stop SDD services by port.")
    parser.add_argument("--port", action="append", type=parse_target, required=True, metavar="LABEL:PORT")
    args = parser.parse_args(argv)
    code = 0
    for target in args.port:
        status, pids = stop_target(target)
        details = ", ".join(str(pid) for pid in sorted(pids)) or "-"
        print(f"{target.label}\t{target.port}\t{status}\t{details}")
        code = max(code, 2 if status == "partial" else 0)
    return code

if __name__ == "__main__":
    raise SystemExit(main())
