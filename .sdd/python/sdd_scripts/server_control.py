#!/usr/bin/env python3
"""Start / register / stop SDD runtime processes (/sdd-serve, /sdd-kill-server).

Audit sécurité 2026-11 — l'ancienne version tuait TOUT process en écoute sur
le port demandé (`netstat` → `taskkill /F`) : un `/sdd-kill-server --port
5432` arrêtait PostgreSQL, un port partagé tuait l'IDE ou un autre projet.

Désormais :

* `/sdd-serve` lance chaque service via `start` (ou déclare un PID lancé
  autrement via `register`). Le PID, le port, la commande, l'image process
  observée et l'heure sont enregistrés dans
  `workspace/.sys/.state/serve.pids.json`.
* `stop` (et la forme historique `--port LABEL:PORT`) ne tue QUE les PID
  enregistrés pour ces ports, après avoir vérifié que le process existe
  encore et que son image correspond à celle enregistrée (`tasklist /FI` sous
  Windows, `ps` ailleurs) — un PID recyclé par l'OS n'est jamais tué.
* Sans fichier de PID (ou sans entrée pour le port) : refus explicite.
  `--force-port` réactive l'ancien comportement (kill de tout listener du
  port), à n'utiliser qu'en connaissance de cause.

Pas de `shell=True` : `start` reçoit la commande en argv après `--`
(résolution `shutil.which` pour `npm` → `npm.cmd` sous Windows).

Exit codes : 0 = OK / rien à faire ; 1 = refus (pas de registre, entrée
manquante) ; 2 = arrêt partiel ; 3 = erreur d'infrastructure.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

PIDS_FILENAME = "serve.pids.json"
EXIT_OK, EXIT_REFUSED, EXIT_PARTIAL, EXIT_INFRA = 0, 1, 2, 3


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


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def pids_file(root: Path | None = None) -> Path:
    from sdd_lib.paths import repo_root, workspace_root
    return workspace_root(root or repo_root()) / ".sys" / ".state" / PIDS_FILENAME


def load_registry(path: Path) -> list[dict] | None:
    """Entries list, or None when the file does not exist."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("processes") if isinstance(data, dict) else data
    return [e for e in entries or [] if isinstance(e, dict)]


def save_registry(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"processes": entries}, indent=2, ensure_ascii=False) + "\n"
    try:
        from sdd_lib.atomic_write import atomic_write_text
        atomic_write_text(path, payload)
    except ImportError:  # pragma: no cover
        path.write_text(payload, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Process inspection (no shell)
# --------------------------------------------------------------------------- #

def process_image(pid: int) -> str | None:
    """Lower-cased executable name of a live PID, or None if it does not exist."""
    if pid <= 0:
        return None
    if os.name == "nt":
        res = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False, encoding="utf-8", errors="replace",
        )
        for line in res.stdout.splitlines():
            cells = [c.strip('"') for c in line.split('","')]
            if len(cells) >= 2 and cells[1].strip('"') == str(pid):
                return cells[0].strip('"').lower()
        return None
    res = subprocess.run(["ps", "-p", str(pid), "-o", "comm="],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    name = res.stdout.strip()
    return Path(name).name.lower() if name else None


def _image_matches(recorded: str | None, actual: str | None) -> bool:
    if not actual:
        return False
    if not recorded:
        return False
    strip = lambda s: s.lower().removesuffix(".exe")  # noqa: E731
    return strip(recorded) == strip(actual)


def _windows_listener_pids(port: int) -> set[int]:
    result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    pattern = re.compile(r"^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$", re.I)
    return {int(match.group(2)) for line in result.stdout.splitlines()
            if (match := pattern.match(line)) and int(match.group(1)) == port}


def _unix_listener_pids(port: int) -> set[int]:
    lsof = shutil.which("lsof")
    if not lsof:
        return set()
    result = subprocess.run([lsof, "-ti", f":{port}", "-sTCP:LISTEN"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {int(pid) for pid in result.stdout.split() if pid.isdigit()}


def listener_pids(port: int) -> set[int]:
    return _windows_listener_pids(port) if os.name == "nt" else _unix_listener_pids(port)


def stop_pid(pid: int, *, tree: bool = True) -> None:
    if os.name == "nt":
        cmd = ["taskkill", "/F", "/PID", str(pid)]
        if tree:
            cmd.insert(2, "/T")  # child processes (node spawned by npm.cmd, JVM by gradlew…)
        subprocess.run(cmd, capture_output=True, check=False)
        return
    try:
        if tree:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _upsert(entries: list[dict], entry: dict) -> list[dict]:
    out = [e for e in entries if not (e.get("label") == entry["label"] and e.get("port") == entry["port"])]
    out.append(entry)
    return out


def cmd_start(label: str, port: int, cwd: str | None, argv: list[str], registry: Path,
              log_dir: Path | None = None) -> int:
    if not argv:
        print("ERROR: start requires a command after `--`", file=sys.stderr)
        return EXIT_REFUSED
    exe = shutil.which(argv[0]) or argv[0]
    log_dir = log_dir or registry.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"serve-{label.lower()}-{port}.log"
    kwargs: dict = {"cwd": cwd or None, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                                   | getattr(subprocess, "DETACHED_PROCESS", 0))
    else:
        kwargs["start_new_session"] = True
    try:
        with log_path.open("ab") as log:
            proc = subprocess.Popen([exe, *argv[1:]], stdout=log, stderr=subprocess.STDOUT, **kwargs)
    except OSError as exc:
        print(f"ERROR: start {label} failed\nCAUSE: [INFRA_BLOCKED] {exc}\n"
              f"FIX: verifier la commande `{argv[0]}` et le repertoire {cwd}", file=sys.stderr)
        return EXIT_INFRA
    time.sleep(0.3)
    image = process_image(proc.pid) or Path(exe).name.lower()
    entries = load_registry(registry) or []
    save_registry(registry, _upsert(entries, {
        "label": label, "port": port, "pid": proc.pid, "image": image,
        "cmd": " ".join(argv), "cwd": cwd or "", "log": str(log_path), "started_at": _now(),
    }))
    print(f"{label}\t{port}\tstarted\t{proc.pid}\t{log_path}")
    return EXIT_OK


def cmd_register(label: str, port: int, pid: int, cmd: str, registry: Path) -> int:
    image = process_image(pid)
    if image is None:
        print(f"ERROR: register {label}: PID {pid} does not exist", file=sys.stderr)
        return EXIT_REFUSED
    entries = load_registry(registry) or []
    save_registry(registry, _upsert(entries, {
        "label": label, "port": port, "pid": pid, "image": image, "cmd": cmd,
        "cwd": "", "log": "", "started_at": _now(),
    }))
    print(f"{label}\t{port}\tregistered\t{pid}\t{image}")
    return EXIT_OK


def _stop_forced(target: PortTarget) -> tuple[str, set[int]]:
    """Legacy behaviour (opt-in `--force-port`) : kill every listener of the port."""
    pids = listener_pids(target.port)
    if not pids:
        return "not-running", set()
    for pid in pids:
        stop_pid(pid)
    time.sleep(0.3)
    remaining = listener_pids(target.port)
    if remaining and os.name != "nt":
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    return ("stopped" if not listener_pids(target.port) else "partial"), pids


def cmd_stop(targets: list[PortTarget], registry: Path, *, force_port: bool = False) -> int:
    if force_port:
        code = EXIT_OK
        print("WARNING: --force-port — tout process en ecoute sur ces ports va etre tue "
              "(y compris hors SDD)", file=sys.stderr)
        for target in targets:
            status, pids = _stop_forced(target)
            print(f"{target.label}\t{target.port}\t{status}\t{', '.join(map(str, sorted(pids))) or '-'}")
            code = max(code, EXIT_PARTIAL if status == "partial" else EXIT_OK)
        return code

    entries = load_registry(registry)
    if entries is None:
        print(
            "ERROR: /sdd-kill-server — aucun registre de PID\n"
            f"CAUSE: [INVALID_ARG] {registry} absent : aucun service lance par /sdd-serve "
            "n'est enregistre (refus de tuer un process inconnu ecoutant sur le port)\n"
            "FIX: relancer via /sdd-serve (server_control.py start), declarer le PID "
            "(server_control.py register), ou --force-port (tue tout listener du port)",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    code = EXIT_OK
    keep: list[dict] = []
    wanted = {t.port for t in targets}
    for e in entries:
        if e.get("port") not in wanted:
            keep.append(e)
    for target in targets:
        matched = [e for e in entries if e.get("port") == target.port]
        if not matched:
            listening = listener_pids(target.port)
            state = "not-registered" + (f" (port occupe par PID {', '.join(map(str, sorted(listening)))} — "
                                        f"non tue)" if listening else "")
            print(f"{target.label}\t{target.port}\t{state}\t-")
            if listening:
                code = max(code, EXIT_REFUSED)
            continue
        for e in matched:
            pid = int(e.get("pid") or 0)
            actual = process_image(pid)
            if actual is None:
                print(f"{target.label}\t{target.port}\tnot-running\t{pid}")
                continue
            if not _image_matches(e.get("image"), actual):
                print(f"{target.label}\t{target.port}\tskipped (PID {pid} = {actual}, "
                      f"attendu {e.get('image')} — PID recycle ?)\t{pid}")
                code = max(code, EXIT_REFUSED)
                continue
            stop_pid(pid)
            time.sleep(0.3)
            if process_image(pid) is not None:
                print(f"{target.label}\t{target.port}\tpartial\t{pid}")
                keep.append(e)
                code = max(code, EXIT_PARTIAL)
            else:
                print(f"{target.label}\t{target.port}\tstopped\t{pid}")
    save_registry(registry, keep)
    return code


def cmd_list(registry: Path) -> int:
    entries = load_registry(registry)
    if entries is None:
        print("(aucun registre)")
        return EXIT_OK
    for e in entries:
        alive = process_image(int(e.get("pid") or 0))
        print(f"{e.get('label')}\t{e.get('port')}\t{e.get('pid')}\t"
              f"{'alive' if alive else 'dead'}\t{e.get('cmd')}")
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Start/stop SDD services with a PID registry.")
    p.add_argument("--registry", default=None, help="override the PID registry path")
    sub = p.add_subparsers(dest="action")

    s = sub.add_parser("start", help="launch a service and record its PID")
    s.add_argument("--label", required=True)
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--cwd", default=None)
    s.add_argument("command", nargs=argparse.REMAINDER, help="-- CMD ARGS...")

    r = sub.add_parser("register", help="record an already-running PID")
    r.add_argument("--label", required=True)
    r.add_argument("--port", type=int, required=True)
    r.add_argument("--pid", type=int, required=True)
    r.add_argument("--cmd", default="")

    k = sub.add_parser("stop", help="stop registered services by port")
    k.add_argument("--port", action="append", type=parse_target, required=True, metavar="LABEL:PORT")
    k.add_argument("--force-port", action="store_true",
                   help="legacy: kill ANY listener on the port (dangerous)")

    sub.add_parser("list", help="show the registry")
    return p


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    # Forme historique : `server_control.py --port L:P [--port …] [--force-port]` = stop.
    if args_list and args_list[0] in ("--port", "--force-port") or (
            args_list[:1] == ["--registry"] and len(args_list) > 2 and args_list[2] in ("--port", "--force-port")):
        reg_args: list[str] = []
        if args_list[:1] == ["--registry"]:
            reg_args, args_list = args_list[:2], args_list[2:]
        args_list = [*reg_args, "stop", *args_list]
    parser = _build_parser()
    args = parser.parse_args(args_list)
    registry = Path(args.registry) if args.registry else pids_file()
    if args.action == "start":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        return cmd_start(args.label, args.port, args.cwd, command, registry)
    if args.action == "register":
        return cmd_register(args.label, args.port, args.pid, args.cmd, registry)
    if args.action == "stop":
        return cmd_stop(args.port, registry, force_port=args.force_port)
    if args.action == "list":
        return cmd_list(registry)
    parser.print_help()
    return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
