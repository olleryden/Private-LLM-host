# pLLM Control

A small local control app for the existing services. It provides one place
to see which instances are stopped, loading, ready, or failed, and to start
and stop them. It does not replace the chat client or change inference settings.

## Open the app

Double-click **pLLM Control** on the desktop. If Ubuntu initially treats it
as an untrusted launcher, right-click it and choose **Allow Launching**,
then double-click it. The shortcut is `~/Desktop/pLLM Control.desktop`.
Setting its trusted metadata from the Codex session was unsupported, so
that first-use desktop action may be necessary.

You can also open Ubuntu's Applications view and search for **pLLM Control**.
Both shortcuts open the same local app without keeping a desktop terminal open.

Alternatively:

```bash
cd ~/Projects/pLLM
bash scripts/start-control.sh
```

This opens **http://127.0.0.1:8787** in your browser. The control app runs
separately from the launching terminal; you can close that terminal.
Running the command again reopens the same app. No model, chat UI, shell,
or sharing session starts until you choose Start.

`pLLM Control.desktop` is the source of the Applications entry, installed at
`~/.local/share/applications/pllm-control.desktop`. Its paths refer to this
PC; recreate them if moving the repository. It is not a login item or boot
service. To reinstall the shortcut on this PC:

```bash
install -Dm644 'pLLM Control.desktop' ~/.local/share/applications/pllm-control.desktop
```

## Instances

| Instance | What Start runs | Ready means |
|---|---|---|
| Qwen engine | Existing `serve-nvfp4.sh`, 128K context by default; 32K selectable | Model HTTP health check passes |
| Chat interface | Existing `serve-webui.sh` with the private phone URL | UI HTTP health check passes |
| Phone access | Foreground `sudo tailscale serve --https=443 http://127.0.0.1:8080` | Serve reports that the private proxy is available |
| Workspace terminal | A shell in this repository | Shell process is running |

Start Qwen and the chat interface for local chat. Start phone access too
for the iPhone. The Tailscale daemon and phone VPN must already be connected.
Phone access can request your Ubuntu password: expand its terminal and
use the masked input. The password is sent to the local sudo prompt,
not saved as a control-app setting.

The app reports instances it detects outside its control as external.
It does not adopt them or stop arbitrary processes occupying their ports.
To manage everything here, stop an older manually launched instance first,
then start its replacement from the app.

“Detected outside app” reports an existing listener or matching Tailscale
route, not an attached terminal window. An old process can outlive its
original window. External process IDs and uptime are not tracked here,
so the app shows a dash for those fields.

The app identifies Qwen by any listener on `127.0.0.1:8000`. On 2026-11-15
a Kong container held that port and was shown as an external Qwen, while
vLLM could not start. Kong now uses `127.0.0.1:8100` (KONG.md). The app does
not show or manage Kong; making detection more robust and adding Kong
status are planned (PLAN.md, next iteration).

## Optional terminal

Expand the selected instance's terminal to see recent output and send
input. Send adds an Enter; Ctrl+C interrupts the foreground task, and
Ctrl+D sends end-of-input. Use masked input for passwords. The separate
workspace terminal accepts normal shell commands.

This is a bounded text transcript with line input, not a full terminal
emulator. Full-screen applications such as Vim or htop need a normal
terminal. Output is kept in memory for the current app session, with old
output discarded when the limit is reached. Restarting an instance keeps
recent output visible within that session.

## Closing and stopping

- Closing the browser tab leaves the control app and its instances running.
- Stop on an instance terminates that instance's process group. Sharing
  uses an interrupt so its foreground Serve session can clean up.
- Quit control app stops the manager; if it owns active instances, the UI
  asks before also stopping them. It never stops externally owned instances.
- Stopping the model does not remove weights. Stopping the chat interface
  does not remove saved chats or settings.

Command-line alternatives, requiring no extra terminal to remain open:

```bash
bash scripts/start-control.sh --status
bash scripts/start-control.sh --stop
# Deliberately stop all instances owned by this manager, then quit:
bash scripts/start-control.sh --stop-all
```

Automatic startup of the lightweight controller is now an explicit option
under Control settings, after one-time phone-control setup. Qwen and Chat
remain manual. Sleep behavior is unchanged.

## Private access and files

The manager binds only to `127.0.0.1:8787`. Optional owner-restricted
Tailscale Serve on HTTPS :8443 exposes the controls to your own devices;
chat sharing stays on :443 → :8080. Tailscale identity headers are checked
before remote page/API access. API tokens and strict host/origin checks
remain. See [PHONE_CONTROL.md](./PHONE_CONTROL.md) for setup and phone use.

The Python-standard-library backend and buildless frontend need no new
environment or downloaded dependencies. Runtime metadata and the manager's
small diagnostic log live in ignored `.data/control/`; terminal transcripts
are not written there. Keep WebUI data/secrets in their existing locations.

The desktop launcher can use a detached process. Optional user-service
startup runs only the controller, with failure recovery for the controller;
it never restores running models automatically. Deliberately quitting the
manager stops its managed processes. The phone interface keeps Quit hidden
and blocks its endpoint to preserve remote reachability.
