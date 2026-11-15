"""Private Tailscale access and opt-in startup for the lightweight controller."""

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parent.parent
UNIT = "pllm-control.service"


def read_config(state_dir):
    path = Path(state_dir) / "remote.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get("origin"), str):
        raise ValueError("Invalid private-control configuration.")
    origin = value.get("origin", "")
    url = urlsplit(origin)
    if (url.scheme != "https" or not url.hostname or
            not re.fullmatch(r"[a-z0-9.-]+\.ts\.net", url.hostname) or
            url.port != 8443 or url.username or url.password or url.path or
            url.query or url.fragment or origin != f"https://{url.hostname}:8443" or
            not isinstance(value.get("owner_login"), str) or
            not value["owner_login"].strip() or
            type(value.get("before_login", True)) is not bool):
        raise ValueError("Invalid private-control configuration.")
    return value


def write_config(state_dir, config):
    directory = Path(state_dir)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "remote.json"
    temporary = directory / f".remote-{os.getpid()}.json"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(config, stream)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def unit_text(root):
    if any(char in str(root) for char in "\r\n"):
        raise ValueError("The project directory cannot contain line breaks.")
    def quoted(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    return (
        "[Unit]\nDescription=pLLM Control (models start manually)\n\n"
        "[Service]\nType=simple\n"
        f"WorkingDirectory={str(root).replace('%', '%%')}\n"
        f"ExecStart=/usr/bin/python3 {quoted(Path(root) / 'control/server.py')}\n"
        "Environment=PYTHONUNBUFFERED=1\nUMask=0077\n"
        "Restart=on-failure\nRestartSec=3\nTimeoutStopSec=25\n"
        "KillMode=control-group\n\n[Install]\nWantedBy=default.target\n"
    )


def install_unit(home=None, root=ROOT):
    directory = (Path(home) if home else Path.home()) / ".config/systemd/user"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / UNIT
    text = unit_text(root)
    if path.exists() and "pLLM Control (models start manually)" not in path.read_text():
        raise RuntimeError("A different pllm-control.service exists; it was not overwritten.")
    path.write_text(text)
    return path


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Command failed.")
    return result.stdout.strip()


def set_autostart(state_dir, enabled):
    if type(enabled) is not bool:
        raise ValueError("Automatic startup must be true or false.")
    config = read_config(state_dir)
    if not config:
        raise ValueError("Set up private phone controls on the PC first.")
    if not (Path.home() / ".config/systemd/user" / UNIT).is_file():
        raise ValueError("The control-app startup service has not been installed.")
    if enabled and config.get("before_login", True):
        run(["loginctl", "--no-ask-password", "enable-linger", getpass.getuser()])
    run(["systemctl", "--user", "enable" if enabled else "disable", UNIT])
    return startup_status(state_dir)


def startup_status(state_dir):
    config = read_config(state_dir)
    if not config:
        return {"configured": False, "autostart": False, "before_login": False, "url": ""}
    result = subprocess.run(
        ["systemctl", "--user", "is-enabled", UNIT], capture_output=True, text=True, timeout=3
    )
    return {
        "configured": True, "autostart": result.returncode == 0,
        "before_login": config.get("before_login", True), "url": config["origin"],
    }


def prepare(state_dir, before_login=True):
    status = json.loads(run(["tailscale", "status", "--json"]))
    if status.get("BackendState") != "Running":
        raise RuntimeError("Connect this PC to Tailscale first.")
    device = status.get("Self", {})
    hostname = device.get("DNSName", "").rstrip(".").lower()
    owner = status.get("User", {}).get(str(device.get("UserID")), {}).get("LoginName")
    if not owner or not re.fullmatch(r"[a-z0-9.-]+\.ts\.net", hostname):
        raise RuntimeError("Could not identify the owner of this Tailscale device. Tagged devices need a separate access policy.")
    config = {"origin": f"https://{hostname}:8443", "owner_login": owner, "before_login": before_login}
    write_config(state_dir, config)
    read_config(state_dir)
    install_unit()
    run(["systemctl", "--user", "daemon-reload"])
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true", help="Write owner restriction and startup unit without enabling sharing or startup")
    parser.add_argument("--after-login", action="store_true", help="Start the controller after desktop login rather than before login")
    args = parser.parse_args()
    state_dir = ROOT / ".data/control"
    try:
        config = prepare(state_dir, not args.after_login)
        print("Private control URL: " + config["origin"], flush=True)
        print("Only your Tailscale account may access these controls.", flush=True)
        if args.prepare_only:
            print("Prepared. Sharing and automatic startup have not been enabled.")
            return 0
        opener = build_opener(ProxyHandler({}))
        with opener.open("http://127.0.0.1:8787/", timeout=3) as response:
            if response.headers.get("X-pLLM-Control-Remote") != "1":
                raise RuntimeError("Restart pLLM Control to load private-access protection before running setup.")
        # Owner-only checks are on disk before any remote route can be exposed.
        result = subprocess.run([
            "sudo", "tailscale", "serve", "--bg", "--https=8443", "http://127.0.0.1:8787"
        ])
        if result.returncode:
            raise RuntimeError("Private sharing was not enabled. Run this setup again to retry.")
        set_autostart(state_dir, True)
        print("Automatic control-app startup enabled. Qwen and Chat still start manually.")
        print("If the controller is already open, its next launch/restart will load this update.")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
