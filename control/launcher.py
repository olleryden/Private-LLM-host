#!/usr/bin/env python3
"""Open the local control app without keeping a desktop terminal open."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".data" / "control"
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def connection():
    try:
        metadata = json.loads((STATE / "server.json").read_text())
        port = int(metadata["port"])
        if not 1 <= port <= 65535 or not isinstance(metadata["token"], str):
            return None
        url = f"http://127.0.0.1:{port}"
        request = urllib.request.Request(
            url + "/api/state", headers={"X-PLLM-Token": metadata["token"]}
        )
        with HTTP.open(request, timeout=1) as response:
            if response.headers.get("X-pLLM-Control") != "1":
                return None
            state = json.load(response)
        if not isinstance(state.get("services"), list):
            return None
        return url, metadata["token"], state
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        return None


def stop_app(active, stop_services):
    url, token, _ = active
    request = urllib.request.Request(
        url + "/api/shutdown",
        data=json.dumps({"stop_services": stop_services}).encode(),
        headers={"X-PLLM-Token": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with HTTP.open(request, timeout=5) as response:
            json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error).get("error", str(error))
        except (ValueError, OSError):
            message = str(error)
        raise RuntimeError(message) from error
    for _ in range(100):
        if connection() is None:
            print("Control app stopped.")
            return
        time.sleep(0.1)
    raise RuntimeError("Shutdown is still in progress. Check the control app log.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true", help="Show the current instances")
    action.add_argument("--stop", action="store_true", help="Quit if no managed instances are active")
    action.add_argument("--stop-all", action="store_true", help="Stop managed instances and quit")
    parser.add_argument("--no-open", action="store_true", help="Start without opening the browser")
    parser.add_argument("--port", type=int, default=8787, help="Local port for a new control app")
    args = parser.parse_args()
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.chmod(0o700)
    lock_fd = os.open(STATE / "launcher.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(lock_fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        active = connection()
        if args.status:
            if active is None:
                print("Control app is stopped.")
            else:
                print(active[0])
                for service in active[2]["services"]:
                    print(f"{service['name']}: {service['status']}")
            return 0
        if args.stop or args.stop_all:
            if active is None:
                print("Control app is already stopped.")
            else:
                stop_app(active, args.stop_all)
            return 0
        if active is None:
            log_path = STATE / "control.log"
            if log_path.exists() and log_path.stat().st_size > 1024 * 1024:
                log_path.replace(STATE / "control.previous.log")
            log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(log_fd, "a") as log:
                process = subprocess.Popen(
                    [sys.executable, str(ROOT / "control" / "server.py"), "--port", str(args.port)],
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            for _ in range(100):
                active = connection()
                if active is not None:
                    break
                if process.poll() is not None:
                    raise RuntimeError(f"Control app could not start. See {log_path}")
                time.sleep(0.1)
            if active is None:
                raise RuntimeError(f"Control app is still starting. See {log_path}")
        url = active[0]
        print(f"pLLM Control: {url}")
        if not args.no_open:
            subprocess.Popen(
                ["xdg-open", url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
