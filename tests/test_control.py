"""Integration tests using disposable Python children, never project services.

Run with ``python3 -m unittest discover -s tests -v``.  The HTTP cases bind only
to an ephemeral loopback port; no model, GPU, desktop service, or Tailscale
configuration is required.
"""

from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from control.server import APIError, ControlHTTPServer, Manager, ServiceSpec


def wait_for(predicate, timeout=6.0, description="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.025)
    raise AssertionError(f"Timed out waiting for {description}")


def process_alive(pid):
    """Reaped or zombie children cannot keep a server or terminal running."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat[stat.rfind(")") + 2] != "Z"
    except FileNotFoundError:
        return False


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pllm-control-test-")
        self.root = Path(self.temp.name)
        self.managers = []
        self.extra_processes = []
        self.extra_pids = []

    def tearDown(self):
        for manager in reversed(self.managers):
            manager.close()
        for process in self.extra_processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        # Also contain a failing orphan-cleanup test rather than leaving its
        # deliberately detached-from-parent child behind on the developer PC.
        for pid in self.extra_pids:
            if process_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.temp.cleanup()

    def make_manager(self, code, *, service_id="dummy", **kwargs):
        manager_options = {}
        for name in ("output_limit", "stop_timeout"):
            if name in kwargs:
                manager_options[name] = kwargs.pop(name)
        spec = ServiceSpec(
            id=service_id,
            name="Disposable test child",
            description="No project services",
            command=kwargs.pop("command", (sys.executable, "-u", "-c", code)),
            cwd=self.root,
            **kwargs,
        )
        manager = Manager(
            [spec], self.root / f"state-{len(self.managers)}",
            stop_timeout=manager_options.pop("stop_timeout", 0.3),
            **manager_options,
        )
        self.managers.append(manager)
        return manager, manager.services[service_id]

    @staticmethod
    def output_text(service, after=0):
        return "".join(chunk["text"] for chunk in service.output(after)["chunks"])

    def test_manager_never_autostarts(self):
        marker = self.root / "started"
        manager, service = self.make_manager(
            f"from pathlib import Path; Path({str(marker)!r}).touch()"
        )
        self.assertFalse(marker.exists())
        self.assertIsNone(service.snapshot()["pid"])
        self.assertFalse(manager.active())
        self.assertFalse(service.snapshot()["ready"])

    def test_shutdown_refusal_preserves_use_and_success_blocks_new_starts(self):
        manager, service = self.make_manager(
            "import sys; print('READY',flush=True); "
            "exec(\"for line in sys.stdin:\\n print('ACK:'+line.strip(),flush=True)\")",
            ready_pattern="READY",
        )
        manager.start("dummy")
        wait_for(lambda: service.snapshot()["ready"], description="active instance before shutdown")
        with self.assertRaises(APIError) as refused:
            manager.request_shutdown()
        self.assertEqual(refused.exception.status, 409)
        service.input("still usable\n")
        wait_for(lambda: "ACK:still usable" in self.output_text(service), description="use after refused shutdown")
        manager.stop("dummy")
        wait_for(lambda: service.snapshot()["status"] == "stopped", description="stop after refused shutdown")
        manager.start("dummy")
        wait_for(lambda: service.snapshot()["ready"], description="restart after refused shutdown")
        pid = service.snapshot()["pid"]
        manager.request_shutdown(stop_services=True)
        manager.close()
        self.assertFalse(process_alive(pid), "Confirmed shutdown must clean its managed child")

        marker = self.root / "start-after-shutdown"
        idle_manager, _ = self.make_manager(
            f"from pathlib import Path; Path({str(marker)!r}).touch()"
        )
        idle_manager.request_shutdown()
        with self.assertRaises(APIError) as blocked:
            idle_manager.start("dummy")
        self.assertEqual(blocked.exception.status, 409)
        self.assertFalse(marker.exists(), "A successful quit decision must prevent later starts")

    def test_running_process_is_not_ready_until_signal(self):
        _, service = self.make_manager(
            "import time; print('LOADING', flush=True); time.sleep(.35); "
            "print('APPLICATION READY', flush=True); time.sleep(60)",
            ready_pattern="APPLICATION READY",
        )
        service.start()
        wait_for(lambda: "LOADING" in self.output_text(service), description="child loading")
        loading = service.snapshot()
        self.assertTrue(process_alive(loading["pid"]))
        self.assertFalse(loading["ready"])
        wait_for(lambda: service.snapshot()["ready"], description="readiness signal")

    def test_health_endpoint_must_succeed_before_instance_is_ready(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        ready_file = self.root / "healthy"
        code = f"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if Path({str(ready_file)!r}).exists() else 503)
        self.end_headers()
    def log_message(self, *_):
        pass
server = HTTPServer(('127.0.0.1', {port}), Handler)
print('LISTENING', flush=True)
server.serve_forever()
"""
        _, service = self.make_manager(code, port=port, health_path="/health")
        service.start()
        wait_for(lambda: "LISTENING" in self.output_text(service), description="health server listening")
        self.assertTrue(process_alive(service.snapshot()["pid"]))
        self.assertFalse(service.snapshot()["ready"], "An open port returning 503 is not healthy")
        ready_file.touch()
        wait_for(lambda: service.snapshot()["ready"], description="successful health endpoint")

    def test_failed_exit_retains_reason_and_diagnostic_output(self):
        manager, service = self.make_manager(
            "import sys; print('Intentional test failure',file=sys.stderr); sys.exit(7)",
            ready_pattern="NEVER READY",
        )
        service.start()
        wait_for(lambda: service.snapshot()["status"] == "failed", description="failed child state")
        snapshot = service.snapshot()
        self.assertEqual(snapshot["exit_code"], 7)
        self.assertIn("7", snapshot["error"])
        self.assertIn("Intentional test failure", self.output_text(service))
        self.assertFalse(snapshot["ready"])
        self.assertIsNone(snapshot["pid"])
        self.assertFalse(manager.active())

    def test_terminal_input_and_unicode_output(self):
        _, service = self.make_manager(
            "import sys,time; print('READY'); "
            "value=sys.stdin.readline().rstrip('\\n'); "
            "print('RECEIVED:'+value+' — 世界'); time.sleep(60)",
            ready_pattern="READY",
        )
        service.start()
        wait_for(lambda: service.snapshot()["ready"], description="interactive child")
        service.input("hello terminal\n")
        wait_for(
            lambda: "RECEIVED:hello terminal — 世界" in self.output_text(service),
            description="input consumed by child PTY",
        )

    def test_interrupt_reaches_child_without_stopping_manager(self):
        _, service = self.make_manager(
            "import signal,time; "
            "signal.signal(signal.SIGINT, lambda *_: print('INTERRUPTED',flush=True)); "
            "print('READY'); time.sleep(60)",
            ready_pattern="READY",
        )
        service.start()
        wait_for(lambda: service.snapshot()["ready"], description="interruptible child")
        pid = service.snapshot()["pid"]
        service.interrupt()
        wait_for(lambda: "INTERRUPTED" in self.output_text(service), description="SIGINT output")
        self.assertTrue(process_alive(pid))

    def test_duplicate_start_does_not_spawn_another_process(self):
        marker = self.root / "launches"
        _, service = self.make_manager(
            f"from pathlib import Path; import time; "
            f"p=Path({str(marker)!r}); p.open('a').write('launch\\n'); "
            "print('READY'); time.sleep(60)",
            ready_pattern="READY",
        )
        service.start()
        wait_for(lambda: service.snapshot()["ready"], description="first child")
        pid = service.snapshot()["pid"]
        with self.assertRaises(APIError):
            service.start()
        self.assertEqual(service.snapshot()["pid"], pid)
        self.assertEqual(marker.read_text().splitlines(), ["launch"])

    def test_stop_reaches_descendants_and_escalates_if_ignored(self):
        pid_file = self.root / "descendant.pid"
        child_code = (
            "import signal,time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('DESCENDANT READY',flush=True); time.sleep(60)"
        )
        _, service = self.make_manager(
            "import subprocess,sys,time; from pathlib import Path; "
            f"p=subprocess.Popen([sys.executable,'-u','-c',{child_code!r}]); "
            f"Path({str(pid_file)!r}).write_text(str(p.pid)); "
            "print('READY'); time.sleep(60)",
            ready_pattern="DESCENDANT READY",
        )
        service.start()
        wait_for(lambda: service.snapshot()["ready"], description="parent and descendant")
        parent_pid = service.snapshot()["pid"]
        child_pid = int(pid_file.read_text())
        self.extra_pids.append(child_pid)
        service.stop()
        wait_for(lambda: not process_alive(parent_pid), description="parent termination")
        wait_for(lambda: not process_alive(child_pid), description="descendant termination")

    def test_stop_allows_child_to_finish_gracefully(self):
        finished = self.root / "graceful-shutdown"
        code = f"""
from pathlib import Path
import signal
import time
def finish(*_):
    Path({str(finished)!r}).write_text('saved')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, finish)
print('READY', flush=True)
time.sleep(60)
"""
        _, service = self.make_manager(code, ready_pattern="READY")
        service.start()
        wait_for(lambda: service.snapshot()["ready"], description="graceful child")
        service.stop()
        wait_for(lambda: service.snapshot()["status"] == "stopped", description="graceful shutdown")
        self.assertEqual(finished.read_text(), "saved")
        self.assertEqual(service.snapshot()["exit_code"], 0)

    def test_interactive_shell_interrupts_foreground_job_and_accepts_next_command(self):
        _, service = self.make_manager(
            "", command=("bash", "--noprofile", "--norc", "-i"),
            env={"PS1": "TESTPROMPT> ", "PROMPT_COMMAND": "", "INPUTRC": "/dev/null", "TERM": "dumb"},
            ready_pattern="TESTPROMPT> ", stop_signal=signal.SIGHUP,
        )
        service.start()
        wait_for(lambda: service.snapshot()["ready"], description="interactive bash prompt")
        pid_file = self.root / "foreground.pid"
        code = (
            "import os,time; from pathlib import Path; "
            f"Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)"
        )
        service.input(f"{shlex.quote(sys.executable)} -u -c {shlex.quote(code)}\n")
        wait_for(pid_file.exists, description="foreground child PID")
        child_pid = int(pid_file.read_text())
        self.extra_pids.append(child_pid)
        before_interrupt = service.output()["next"]
        service.interrupt()
        wait_for(lambda: not process_alive(child_pid), description="foreground job interrupted")
        wait_for(
            lambda: "TESTPROMPT> " in self.output_text(service, before_interrupt),
            description="shell prompt after Ctrl+C",
        )
        after_prompt = service.output()["next"]
        service.input("printf '%s\\n' 'AFTER INTERRUPT'\n")
        wait_for(
            lambda: "\nAFTER INTERRUPT\n" in self.output_text(service, after_prompt),
            description="next shell command",
        )

    def test_close_cleans_foreground_jobs_in_other_process_groups(self):
        manager, service = self.make_manager(
            "", command=("bash", "--noprofile", "--norc", "-i"),
            env={"PS1": "TESTPROMPT> ", "PROMPT_COMMAND": "", "INPUTRC": "/dev/null", "TERM": "dumb"},
            ready_pattern="TESTPROMPT> ", stop_signal=signal.SIGHUP,
        )
        service.start()
        wait_for(lambda: service.snapshot()["ready"], description="shell for cleanup test")
        pid_file = self.root / "foreground-ignoring-signals.pid"
        code = (
            "import os,signal,time; from pathlib import Path; "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            "signal.signal(signal.SIGHUP,signal.SIG_IGN); "
            f"Path({str(pid_file)!r}).write_text(str(os.getpid())); "
            "print('FOREGROUND CHILD READY',flush=True); time.sleep(60)"
        )
        service.input(f"{shlex.quote(sys.executable)} -u -c {shlex.quote(code)}\n")
        wait_for(pid_file.exists, description="foreground child started")
        child_pid = int(pid_file.read_text())
        self.extra_pids.append(child_pid)
        shell_pid = service.snapshot()["pid"]
        self.assertNotEqual(os.getpgid(child_pid), os.getpgid(shell_pid))
        manager.close()
        wait_for(lambda: not process_alive(shell_pid), description="interactive shell cleanup")
        wait_for(lambda: not process_alive(child_pid), description="foreground job cleanup")

    def test_parent_exit_cannot_leave_its_descendant_running(self):
        pid_file = self.root / "orphan.pid"
        _, service = self.make_manager(
            "import subprocess,sys; from pathlib import Path; "
            "p=subprocess.Popen([sys.executable,'-u','-c','import time; time.sleep(60)']); "
            f"Path({str(pid_file)!r}).write_text(str(p.pid)); print('PARENT DONE')"
        )
        service.start()
        wait_for(pid_file.exists, description="descendant PID")
        child_pid = int(pid_file.read_text())
        self.extra_pids.append(child_pid)
        wait_for(lambda: not process_alive(child_pid), description="orphan containment")

    def test_existing_port_is_detected_without_adopting_or_killing_its_owner(self):
        external = subprocess.Popen(
            [sys.executable, "-u", "-c",
             "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); "
             "s.listen(); print(s.getsockname()[1]); time.sleep(60)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.extra_processes.append(external)
        port_text = external.stdout.readline().strip()
        self.assertTrue(port_text.isdigit(), external.stderr.read() if external.poll() is not None else "")
        marker = self.root / "unwanted-start"
        manager, service = self.make_manager(
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
            port=int(port_text),
        )
        snapshot = service.snapshot()
        self.assertFalse(snapshot["managed"])
        with self.assertRaises(APIError):
            service.start()
        self.assertFalse(marker.exists())
        try:
            service.stop()
        except APIError:
            pass
        manager.close()
        self.assertIsNone(external.poll(), "An externally started listener must not be terminated")

    def test_output_is_bounded_sanitized_and_unicode_safe(self):
        _, service = self.make_manager(
            "import os,time; "
            "os.write(1, ('雪🙂'*3000+'\\x1b]52;c;YWJj\\x07"
            "\\x1b[31mFINAL 世界\\x1b[0m\\x00\\n').encode()); time.sleep(60)",
            output_limit=2048,
        )
        service.start()
        wait_for(lambda: "FINAL 世界" in self.output_text(service), description="bounded output tail")
        result = service.output(0)
        text = self.output_text(service)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x00", text)
        self.assertNotIn("\ufffd", text)
        self.assertLessEqual(len(text.encode("utf-8")), 4096)
        self.assertIn("FINAL 世界", text)
        self.assertTrue(result["reset"])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pllm-control-http-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.marker = self.root / "started"
        spec = ServiceSpec(
            id="dummy", name="Harmless test child", description="HTTP contract",
            command=(
                sys.executable, "-u", "-c",
                "import time; from pathlib import Path; "
                f"Path({str(self.marker)!r}).touch(); print('READY'); time.sleep(60)",
            ),
            cwd=self.root, ready_pattern="READY",
        )
        self.manager = Manager([spec], self.root / "state", stop_timeout=0.3)
        self.addCleanup(self.manager.close)
        self.server = ControlHTTPServer(("127.0.0.1", 0), self.manager)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_http)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def close_http(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path="/api/state", *, method="GET", payload=None, headers=None,
                authenticate=True, raw_body=None):
        request_headers = {"X-PLLM-Control": "1"}
        if authenticate:
            request_headers["X-PLLM-Token"] = self.server.token
        if payload is not None:
            raw_body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=raw_body, headers=request_headers)
            response = connection.getresponse()
            body = response.read()
            try:
                data = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = body.decode(errors="replace")
            return response.status, data, dict(response.getheaders())
        finally:
            connection.close()

    def test_authenticated_state_never_starts_services(self):
        status, data, _ = self.request(headers={"Origin": self.origin})
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in data["services"]], ["dummy"])
        self.assertFalse(self.marker.exists())
        self.assertIsNone(data["services"][0]["pid"])

    def test_missing_or_incorrect_token_is_rejected(self):
        status, _, _ = self.request(authenticate=False)
        self.assertIn(status, (401, 403))
        status, _, _ = self.request(headers={"X-PLLM-Token": "wrong"})
        self.assertIn(status, (401, 403))
        self.assertFalse(self.marker.exists())

    def test_host_and_cross_origin_requests_are_rejected(self):
        for headers in (
            {"Host": "attacker.example"},
            {"Host": f"attacker.example:{self.server.server_port}"},
            {"Origin": "https://attacker.example"},
            {"Origin": "null"},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            with self.subTest(headers=headers):
                status, _, response_headers = self.request(headers=headers)
                self.assertIn(status, (400, 403))
                self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        self.assertFalse(self.marker.exists())

    def test_unknown_service_and_action_cannot_execute_a_command(self):
        for path in (
            "/api/services/unknown/start",
            "/api/services/dummy/arbitrary-command",
            "/api/services/..%2f..%2fbin%2fsh/start",
        ):
            with self.subTest(path=path):
                status, _, _ = self.request(path, method="POST", payload={})
                self.assertEqual(status, 404)
        self.assertFalse(self.marker.exists())

    def test_invalid_json_types_and_unbounded_request_lengths_are_rejected(self):
        path = "/api/services/dummy/input"
        status, _, _ = self.request(
            path, method="POST", raw_body=b"{not json}",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        for payload in ([], "command", {"data": 123}, {"data": None}):
            with self.subTest(payload=payload):
                status, _, _ = self.request(path, method="POST", payload=payload)
                self.assertEqual(status, 400)
        # A declaration exceeding the cap must be rejected before the handler
        # waits for the rest of a maliciously slow request body.
        status, _, _ = self.request(
            path, method="POST", raw_body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "100000000"},
        )
        self.assertEqual(status, 413)
        self.assertFalse(self.marker.exists())

    def test_start_output_stop_end_to_end(self):
        status, _, _ = self.request("/api/services/dummy/start", method="POST", payload={})
        self.assertEqual(status, 200)
        service = self.manager.services["dummy"]
        wait_for(lambda: service.snapshot()["ready"], description="HTTP-started child")
        status, _, _ = self.request("/api/services/dummy/start", method="POST", payload={})
        self.assertEqual(status, 409)
        status, data, _ = self.request("/api/services/dummy/output?after=0")
        self.assertEqual(status, 200)
        self.assertIn("READY", "".join(chunk["text"] for chunk in data["chunks"]))
        pid = service.snapshot()["pid"]
        status, _, _ = self.request("/api/services/dummy/stop", method="POST", payload={})
        self.assertEqual(status, 200)
        wait_for(lambda: not process_alive(pid), description="HTTP-stopped child")


if __name__ == "__main__":
    unittest.main()
