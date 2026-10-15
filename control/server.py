#!/usr/bin/env python3
"""Local, manual process control for pLLM. Requires only Python's standard library."""

from __future__ import annotations

import argparse
import codecs
from collections import deque
from dataclasses import dataclass, field
import errno
import fcntl
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pty
import re
import secrets
import select
import shutil
import signal
import socket
import subprocess
import sys
import termios
import threading
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parent.parent
MAX_BODY = 65536
MAX_INPUT = 8192


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


@dataclass
class ServiceSpec:
    id: str
    name: str
    description: str
    command: tuple[str, ...]
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    port: int | None = None
    health_path: str | None = None
    url: str = ""
    ready_pattern: str | None = None
    stop_signal: int = signal.SIGTERM
    context_arg: bool = False
    external_command: tuple[str, ...] | None = None
    external_target: str = ""


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.15):
            return True
    except OSError:
        return False


def group_exists(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def session_groups(session_id: int) -> set[int]:
    """Find live job groups in the private PTY session, including shell jobs."""
    groups = set()
    proc_dir = Path("/proc")
    if not proc_dir.is_dir():
        return {session_id} if group_exists(session_id) else set()
    for entry in proc_dir.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            fields = stat[stat.rfind(")") + 2:].split()
            # After the command name: state, parent PID, group ID, session ID.
            if fields[0] != "Z" and int(fields[3]) == session_id:
                groups.add(int(fields[2]))
        except (OSError, ValueError, IndexError):
            continue
    return groups


class Transcript:
    """An incremental, bounded plain-text transcript, rather than terminal emulation."""

    def __init__(self, limit: int):
        self.limit = limit
        self.chunks: deque[dict] = deque()
        self.size = 0
        self.seq = 0
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.escape = ""
        self.truncated = False

    def append(self, raw: bytes, final: bool = False) -> str:
        text = self.decoder.decode(raw, final=final)
        clean = []
        for char in text:
            # Strip CSI/OSC escape sequences, including sequences split across reads.
            if self.escape:
                self.escape += char
                if self.escape.startswith("\x1b["):
                    if len(self.escape) > 2 and "@" <= char <= "~":
                        self.escape = ""
                elif self.escape.startswith("\x1b]"):
                    if char == "\x07" or self.escape.endswith("\x1b\\"):
                        self.escape = ""
                elif len(self.escape) >= 2:
                    self.escape = ""
                if len(self.escape) > 4096:
                    self.escape = ""
                continue
            if char == "\x1b":
                self.escape = char
            elif char in "\n\t" or (ord(char) >= 32 and ord(char) != 127):
                clean.append(char)
            elif char == "\r":
                # PTYs normally turn LF into CRLF. Keep the LF, ignore the CR.
                pass
        value = "".join(clean)
        if value:
            # Limit bytes as well as number of chunks. Avoid a large single write.
            if len(value.encode("utf-8")) > self.limit:
                value = value.encode("utf-8")[-self.limit:].decode("utf-8", "ignore")
                self.truncated = True
            self.seq += 1
            self.chunks.append({"seq": self.seq, "text": value})
            self.size += len(value.encode("utf-8"))
            while len(self.chunks) > 2048 or self.size > self.limit:
                self.size -= len(self.chunks.popleft()["text"].encode("utf-8"))
                self.truncated = True
        return value

    def read(self, after: int) -> dict:
        first = self.chunks[0]["seq"] if self.chunks else self.seq + 1
        reset = after > self.seq or after < first - 1 or (after == 0 and self.truncated)
        return {
            "chunks": [dict(chunk) for chunk in self.chunks if reset or chunk["seq"] > after],
            "next": self.seq,
            "reset": reset,
        }


class Service:
    def __init__(self, spec: ServiceSpec, output_limit: int = 262144, stop_timeout: float = 5.0):
        self.spec = spec
        self.lock = threading.RLock()
        self.proc: subprocess.Popen | None = None
        self.master: int | None = None
        self.watcher: threading.Thread | None = None
        self.transcript = Transcript(output_limit)
        self.stop_timeout = stop_timeout
        self.status = "stopped"
        self.ready = False
        self.was_ready = False
        self.error: str | None = None
        self.exit_code: int | None = None
        self.started: float | None = None
        self.stopping_at: float | None = None
        self.requested_stop = False
        self.command = list(spec.command)
        self._external_at = 0.0
        self._external_value = False
        self._http = build_opener(ProxyHandler({}))

    def external(self) -> bool:
        if self.spec.port is not None:
            return port_open(self.spec.port)
        if self.spec.external_command:
            now = time.monotonic()
            if now - self._external_at < 3:
                return self._external_value
            self._external_at = now
            try:
                result = subprocess.run(
                    self.spec.external_command, capture_output=True, text=True,
                    timeout=2, check=False, env=os.environ.copy(),
                )
                # Only a matching reverse proxy belongs to this project. An
                # unrelated Serve route is not presented as our managed service.
                config = json.loads(result.stdout) if result.returncode == 0 else {}
                self._external_value = self.spec.external_target in json.dumps(config)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                self._external_value = False
            return self._external_value
        return False

    def start(self, context: int = 131072) -> dict:
        with self.lock:
            if self.status in ("starting", "running", "stopping"):
                raise APIError(409, "This instance is already active.")
            if self.external():
                raise APIError(409, "This instance is running outside the control app. Stop it there first.")
            if self.spec.context_arg and (type(context) is not int or not 1024 <= context <= 262144):
                raise APIError(400, "Context must be an integer between 1024 and 262144 tokens.")
            command = list(self.spec.command)
            if self.spec.context_arg:
                command.append(str(context))
            environment = os.environ.copy()
            environment.update(self.spec.env)
            master, slave = pty.openpty()
            try:
                # A small exec helper establishes a controlling TTY, allowing
                # sudo prompts without unsafe preexec_fn work after threaded fork.
                proc = subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "--pty-child", str(slave), "--", *command],
                    cwd=self.spec.cwd or ROOT, env=environment,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    pass_fds=(slave,), close_fds=True,
                )
            except (OSError, ValueError) as exc:
                os.close(master)
                self.status = "failed"
                self.error = f"Could not start this instance: {exc}"
                raise APIError(500, self.error) from exc
            finally:
                os.close(slave)
            os.set_blocking(master, False)
            self.proc = proc
            self.master = master
            self.command = command
            self.status = "starting"
            self.ready = False
            self.was_ready = False
            self.error = None
            self.exit_code = None
            self.started = time.monotonic()
            self.stopping_at = None
            self.requested_stop = False
            # Preserve monotonically increasing sequence numbers across restarts.
            self.transcript.decoder = codecs.getincrementaldecoder("utf-8")("replace")
            self.transcript.escape = ""
            self.transcript.append(b"\n--- Starting instance ---\n")
            self.watcher = threading.Thread(target=self._watch, name=f"watch-{self.spec.id}", daemon=True)
            self.watcher.start()
            return self.snapshot()

    def _signal(self, sig: int) -> None:
        proc = self.proc
        if not proc:
            return
        groups = session_groups(proc.pid)
        for group in groups | {proc.pid}:
            try:
                os.killpg(group, sig)
            except ProcessLookupError:
                if group == proc.pid and proc.poll() is None:
                    # The exec helper may not have reached setsid yet. Its PID
                    # is ours; never signal a process found by listening port.
                    try:
                        proc.send_signal(sig)
                    except ProcessLookupError:
                        pass
            except PermissionError:
                # A sudo child may run as root; its owned sudo monitor forwards
                # the signal. Do not issue a new privileged command to kill it.
                continue

    def stop(self) -> dict:
        with self.lock:
            if self.status not in ("starting", "running", "stopping"):
                if self.external():
                    raise APIError(409, "This instance was started elsewhere. Stop it in its original terminal.")
                return self.snapshot()
            if not self.requested_stop:
                self.requested_stop = True
                self.stopping_at = time.monotonic()
                self.status = "stopping"
                self.ready = False
                self._signal(self.spec.stop_signal)
            return self.snapshot()

    def interrupt(self) -> dict:
        with self.lock:
            if self.status not in ("starting", "running") or self.proc is None:
                raise APIError(409, "This instance has no active managed terminal.")
            try:
                attrs = termios.tcgetattr(self.master)
                if attrs[3] & termios.ISIG:
                    # Deliver the configured interrupt character through the
                    # TTY, so bash forwards Ctrl+C to its foreground job group.
                    interrupt = attrs[6][termios.VINTR]
                    os.write(self.master, interrupt if isinstance(interrupt, bytes) else bytes([interrupt]))
                else:
                    os.killpg(os.tcgetpgrp(self.master), signal.SIGINT)
            except (OSError, termios.error) as exc:
                raise APIError(409, "The terminal cannot accept an interrupt right now.") from exc
            return self.snapshot()

    def input(self, data: str) -> dict:
        if not isinstance(data, str) or not data or len(data.encode("utf-8")) > MAX_INPUT:
            raise APIError(400, f"Input must contain 1–{MAX_INPUT} UTF-8 bytes.")
        with self.lock:
            if self.master is None or self.status not in ("starting", "running"):
                raise APIError(409, "This instance has no active managed terminal.")
            raw = data.encode("utf-8")
            try:
                written = os.write(self.master, raw)
            except (BlockingIOError, OSError) as exc:
                raise APIError(409, "The terminal cannot accept input right now.") from exc
            if written != len(raw):
                raise APIError(409, "The terminal accepted only part of the input; do not resend a password automatically.")
            # Input is never copied into a log by the supervisor. The PTY itself
            # echoes ordinary commands; sudo disables echo for its password.
            return {"accepted": written}

    def _healthy(self) -> bool:
        if self.spec.port is not None and self.spec.health_path:
            try:
                with self._http.open(
                    f"http://127.0.0.1:{self.spec.port}{self.spec.health_path}", timeout=0.4
                ) as response:
                    return response.status == 200
            except (OSError, ValueError):
                return False
        return self.ready if self.spec.ready_pattern else True

    def _watch(self) -> None:
        proc = self.proc
        master = self.master
        assert proc is not None and master is not None
        next_probe = 0.0
        orphan_at: float | None = None
        killed = False
        eof = False
        pattern_tail = ""
        try:
            while True:
                readable, _, _ = select.select([master] if not eof else [], [], [], 0.12)
                if readable:
                    try:
                        raw = os.read(master, 16384)
                    except BlockingIOError:
                        raw = None
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        raw = b""
                    if raw:
                        with self.lock:
                            value = self.transcript.append(raw)
                            if self.spec.ready_pattern:
                                pattern_tail = (pattern_tail + value)[-8192:]
                                if re.search(self.spec.ready_pattern, pattern_tail) and not self.requested_stop:
                                    self.ready = True
                                    self.was_ready = True
                                    self.status = "running"
                    elif raw == b"":
                        eof = True
                now = time.monotonic()
                code = proc.poll()
                with self.lock:
                    stopping_at = self.stopping_at
                    stopping = self.requested_stop
                if code is None and not stopping and now >= next_probe:
                    healthy = self._healthy()
                    with self.lock:
                        if not self.requested_stop:
                            self.ready = healthy
                            self.was_ready = self.was_ready or healthy
                            self.status = "running" if healthy else "starting"
                    next_probe = now + 0.8
                if code is not None and session_groups(proc.pid):
                    # Do not leave children behind if a launcher exits first.
                    if orphan_at is None:
                        orphan_at = now
                        self._signal(self.spec.stop_signal)
                deadline = stopping_at if stopping_at is not None else orphan_at
                if deadline is not None and now - deadline >= self.stop_timeout and not killed:
                    self._signal(signal.SIGKILL)
                    killed = True
                if code is not None:
                    children = bool(session_groups(proc.pid))
                    # A descendant zombie may remain until init reaps it. All
                    # executable descendants are gone after SIGKILL; don't hang.
                    if not children or (killed and now - (deadline or now) >= self.stop_timeout + 0.5):
                        if eof or not readable:
                            break
        except Exception as exc:
            with self.lock:
                self.error = f"Terminal monitoring failed: {exc}"
            self._signal(signal.SIGKILL)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        finally:
            with self.lock:
                self.transcript.append(b"", final=True)
                self.master = None
                self.ready = False
                self.exit_code = proc.poll()
                if self.requested_stop:
                    self.status = "stopped"
                    self.error = None
                elif self.error or self.exit_code != 0 or not self.was_ready:
                    self.status = "failed"
                    if not self.error:
                        self.error = f"Process exited with code {self.exit_code}. Open the terminal output for details."
                else:
                    self.status = "stopped"
                self.transcript.append(f"\n--- Instance exited ({self.exit_code}) ---\n".encode())
            try:
                os.close(master)
            except OSError:
                pass

    def snapshot(self) -> dict:
        with self.lock:
            active = self.status in ("starting", "running", "stopping")
            status = self.status
            if not active and self.external():
                status = "external"
            echo = True
            if self.master is not None:
                try:
                    echo = bool(termios.tcgetattr(self.master)[3] & termios.ECHO)
                except (OSError, termios.error):
                    pass
            return {
                "id": self.spec.id, "name": self.spec.name, "description": self.spec.description,
                "status": status, "pid": self.proc.pid if active and self.proc else None,
                "uptime": max(0, time.monotonic() - self.started) if active and self.started else 0,
                "managed": active, "ready": self.ready if active else False,
                "url": self.spec.url, "command": self.command,
                "terminal_available": active and self.master is not None,
                "error": self.error, "echo": echo, "exit_code": self.exit_code,
            }

    def output(self, after: int = 0) -> dict:
        if type(after) is not int or after < 0:
            raise APIError(400, "Output cursor must be a nonnegative integer.")
        with self.lock:
            return self.transcript.read(after)

    def close(self) -> None:
        with self.lock:
            if self.status in ("starting", "running", "stopping"):
                self.stop()
        watcher = self.watcher
        if watcher and watcher is not threading.current_thread():
            watcher.join(self.stop_timeout + 3)
            if watcher.is_alive():
                with self.lock:
                    self._signal(signal.SIGKILL)
                watcher.join(2)


class Manager:
    def __init__(self, specs: list[ServiceSpec], state_dir: Path, output_limit: int = 262144, stop_timeout: float = 5.0):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_dir.chmod(0o700)
        self.lock_file = (self.state_dir / ".lock").open("a+")
        os.chmod(self.state_dir / ".lock", 0o600)
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.lock_file.close()
            raise RuntimeError("Another control app is already using this state directory.") from exc
        self.services = {spec.id: Service(spec, output_limit, stop_timeout) for spec in specs}
        self.started_at = time.time()
        self.closed = False
        self.shutdown_requested = False
        self._close_lock = threading.Lock()

    def service(self, identifier: str) -> Service:
        try:
            return self.services[identifier]
        except KeyError as exc:
            raise APIError(404, "Unknown instance.") from exc

    def state(self) -> dict:
        return {"services": [service.snapshot() for service in self.services.values()], "started_at": self.started_at}

    def start(self, identifier: str, context: int | None = None) -> dict:
        with self._close_lock:
            if self.closed or self.shutdown_requested:
                raise APIError(409, "The control app is shutting down.")
            return self.service(identifier).start(131072 if context is None else context)

    def stop(self, identifier: str) -> dict:
        return self.service(identifier).stop()

    def active(self) -> bool:
        return any(service.status in ("starting", "running", "stopping") for service in self.services.values())

    def request_shutdown(self, stop_services: bool = False) -> None:
        # Serialize this decision with Start: an instance cannot slip in after
        # a successful request to quit without stopping active instances.
        with self._close_lock:
            if self.active() and not stop_services:
                raise APIError(409, "Instances are active. Stop them first or explicitly request stop_services: true.")
            self.shutdown_requested = True

    def close(self) -> None:
        with self._close_lock:
            if self.closed:
                return
            self.closed = True
            # Signal all instances before waiting so independent stops overlap.
            for service in self.services.values():
                if service.status in ("starting", "running", "stopping"):
                    service.stop()
            for service in self.services.values():
                if service.watcher:
                    service.close()
            fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            self.lock_file.close()


def default_specs() -> list[ServiceSpec]:
    model_env = {}
    if not shutil.which("nvcc"):
        fallback = Path.home() / "miniforge3/bin/nvcc"
        if fallback.is_file():
            model_env["PATH"] = f"{fallback.parent}:{os.environ.get('PATH', '')}"
    return [
        ServiceSpec(
            "model", "Qwen", "Local model · vLLM · 128K context by default",
            ("bash", "scripts/serve-nvfp4.sh"), ROOT, model_env,
            port=8000, health_path="/health", url="http://127.0.0.1:8000/docs", context_arg=True,
        ),
        ServiceSpec(
            "webui", "Chat", "Open WebUI · saved conversations on this PC",
            ("bash", "scripts/serve-webui.sh"), ROOT,
            {"PLLM_WEBUI_URL": "https://ello-lin.tailad2999.ts.net"},
            port=8080, health_path="/health", url="http://127.0.0.1:8080",
        ),
        ServiceSpec(
            "sharing", "Phone access", "Tailscale Serve · private HTTPS forwarding",
            ("sudo", "-k", "tailscale", "serve", "--https=443", "http://127.0.0.1:8080"), ROOT,
            url="https://ello-lin.tailad2999.ts.net", ready_pattern=r"Available within your tailnet|Press Ctrl\+C to exit",
            stop_signal=signal.SIGINT,
            external_command=("tailscale", "serve", "status", "--json"), external_target="http://127.0.0.1:8080",
        ),
        ServiceSpec(
            "shell", "Workspace terminal", "Optional shell · commands in this project",
            ("bash", "--noprofile", "--norc", "-i"), ROOT,
            stop_signal=signal.SIGHUP,
        ),
    ]


class ControlHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], manager: Manager, web_dir: Path | None = None):
        if address[0] != "127.0.0.1":
            raise ValueError("The control app can only bind to 127.0.0.1.")
        self.manager = manager
        self.token = secrets.token_urlsafe(32)
        self.web_dir = Path(web_dir) if web_dir else Path(__file__).resolve().parent / "web"
        super().__init__(address, ControlHandler)


class ControlHandler(BaseHTTPRequestHandler):
    server: ControlHTTPServer
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args) -> None:
        # In particular, never persist request bodies, terminal input, or tokens.
        return

    def _send(self, status: int, data: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-pLLM-Control", "1")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, value: dict) -> None:
        self._send(status, json.dumps(value, ensure_ascii=True).encode())

    def _check_origin(self) -> None:
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        if host not in allowed_hosts:
            raise APIError(403, "Only localhost requests are accepted.")
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            raise APIError(403, "Cross-origin requests are not accepted.")
        if self.headers.get("Sec-Fetch-Site", "") == "cross-site":
            raise APIError(403, "Cross-site requests are not accepted.")

    def _authorize(self) -> None:
        self._check_origin()
        token = self.headers.get("X-PLLM-Token", "")
        if not secrets.compare_digest(token, self.server.token):
            raise APIError(401, "Missing or invalid local control token.")

    def _body(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "Chunked request bodies are not accepted.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise APIError(400, "Invalid request size.") from exc
        if length < 0 or length > MAX_BODY:
            raise APIError(413, "Request body is too large.")
        if self.headers.get_content_type() != "application/json":
            raise APIError(415, "Use an application/json request body.")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeError) as exc:
            raise APIError(400, "Invalid JSON request body.") from exc
        if not isinstance(data, dict):
            raise APIError(400, "The JSON request body must be an object.")
        return data

    def do_GET(self) -> None:
        try:
            self._check_origin()
            parsed = urlsplit(self.path)
            if parsed.path.startswith("/api/"):
                self._authorize()
                if parsed.path == "/api/state":
                    self._json(200, self.server.manager.state())
                    return
                match = re.fullmatch(r"/api/services/([a-z0-9_-]+)/output", parsed.path)
                if match:
                    query = parse_qs(parsed.query)
                    try:
                        after = int(query.get("after", ["0"])[0])
                    except ValueError as exc:
                        raise APIError(400, "Invalid output cursor.") from exc
                    self._json(200, self.server.manager.service(match[1]).output(after))
                    return
                raise APIError(404, "Unknown API route.")
            paths = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/static/style.css": ("style.css", "text/css; charset=utf-8")}
            if parsed.path not in paths:
                raise APIError(404, "Not found.")
            filename, content_type = paths[parsed.path]
            path = self.server.web_dir / filename
            if not path.is_file():
                raise APIError(503, "The control app frontend is not installed.")
            data = path.read_bytes()
            if filename == "index.html":
                data = data.replace(b"__PLLM_TOKEN__", html.escape(self.server.token, quote=True).encode())
            self._send(200, data, content_type)
        except APIError as exc:
            self.close_connection = True
            self._json(exc.status, {"error": str(exc)})
        except (OSError, ValueError):
            self.close_connection = True
            self._json(500, {"error": "Could not complete this request."})

    def do_POST(self) -> None:
        try:
            self._authorize()
            body = self._body()
            path = urlsplit(self.path).path
            if path == "/api/shutdown":
                stop_services = body.get("stop_services", False)
                if type(stop_services) is not bool:
                    raise APIError(400, "stop_services must be true or false.")
                self.server.manager.request_shutdown(stop_services)
                self._json(200, {"shutting_down": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            match = re.fullmatch(r"/api/services/([a-z0-9_-]+)/(start|stop|input|interrupt)", path)
            if not match:
                raise APIError(404, "Unknown API route.")
            identifier, action = match.groups()
            service = self.server.manager.service(identifier)
            if action == "start":
                value = self.server.manager.start(identifier, body.get("context"))
            elif action == "stop":
                value = self.server.manager.stop(identifier)
            elif action == "input":
                value = service.input(body.get("data"))
            else:
                value = service.interrupt()
            self._json(200, value)
        except APIError as exc:
            self.close_connection = True
            self._json(exc.status, {"error": str(exc)})
        except (OSError, ValueError):
            self.close_connection = True
            self._json(500, {"error": "Could not complete this request."})

    def do_OPTIONS(self) -> None:
        self.close_connection = True
        self._json(405, {"error": "Cross-origin access is not available."})


def pty_child(arguments: list[str]) -> None:
    slave = int(arguments[0])
    command = arguments[2:]  # fd, --, executable, args...
    try:
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        for fd in (0, 1, 2):
            os.dup2(slave, fd)
        if slave > 2:
            os.close(slave)
        os.execvpe(command[0], command, os.environ)
    except Exception as exc:
        os.write(2, f"Could not launch instance: {exc}\n".encode())
        os._exit(127)


def write_metadata(manager: Manager, server: ControlHTTPServer) -> Path:
    path = manager.state_dir / "server.json"
    value = {"pid": os.getpid(), "port": server.server_port,
             "url": f"http://127.0.0.1:{server.server_port}", "token": server.token}
    temporary = manager.state_dir / f".server-{os.getpid()}.json"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
    os.replace(temporary, path)
    return path


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--pty-child":
        pty_child(sys.argv[2:])
        return 127
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787, help="Local dashboard port (default: 8787)")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".data/control")
    args = parser.parse_args()
    manager = None
    server = None
    metadata = None
    try:
        manager = Manager(default_specs(), args.state_dir)
        server = ControlHTTPServer(("127.0.0.1", args.port), manager)
        metadata = write_metadata(manager, server)
        print(f"pLLM Control: http://127.0.0.1:{server.server_port}", flush=True)
        print("Instances start only when you choose Start. Closing the browser keeps this app running.", flush=True)

        def shutdown(signum, frame):
            # HTTPServer.shutdown must run outside its serve_forever thread.
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        server.serve_forever(poll_interval=0.2)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Could not run pLLM Control: {exc}", file=sys.stderr)
        return 1
    finally:
        if manager:
            manager.close()
        if server:
            server.server_close()
        if metadata:
            try:
                if json.loads(metadata.read_text()).get("pid") == os.getpid():
                    metadata.unlink()
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
