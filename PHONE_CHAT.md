# Chat from an iPhone over Tailscale

Last updated: 2026-10-16

The first milestone uses the existing Open WebUI application. Chat connects
to the real local Qwen model. Document search, web search, memory, coding
tools, and task execution are deferred; no personal folders or accounts are
connected by this setup.

## Current status

- Open WebUI 0.12.2 installed in `.venv-webui`, separate from vLLM.
- Python 3.11.16 and PyTorch 2.14.1+cpu; UI does not use GPU CUDA.
- Desktop page: <http://127.0.0.1:8080>.
- Page and health check return HTTP 200; model-list API without login
  returns HTTP 401.
- Chat data/settings live in ignored `.data/open-webui/`. The application
  secret is stored in ignored `.secrets/webui-secret-key`.
- Tailscale 1.102.3 is installed, connected, and online on the PC.
- Intended phone URL: <https://ello-lin.tailad2999.ts.net>.
- Owner confirmed Tailscale Serve is enabled in their account.
- Foreground Serve route is now confirmed: private HTTPS :443 → UI :8080.
  This PC requires sudo for route changes. A cellular iPhone test is still open.
- The owner account and saved chats exist. Sign in with the account you created.
- After the wrap-up, WebUI was gracefully stopped at the owner's request;
  port :8080 was verified closed. The model was already stopped.
- The requested local [control app](./CONTROL.md) provides Start/Stop and
  status for model, UI, and sharing in one place. Use it for future sessions;
  the foreground commands below remain available for troubleshooting.

## Start from one control app

From the iPhone, the private controller is now also available at
<https://ello-lin.tailad2999.ts.net:8443>. It is configured to start before
desktop login; Qwen and Chat remain manual. See [PHONE_CONTROL.md](./PHONE_CONTROL.md).

```bash
cd ~/Projects/pLLM
bash scripts/start-control.sh
```

In the app, start the Qwen engine and chat interface, then phone access.
If an older Serve command is still running in a terminal, stop it there
before starting its replacement in the app. Expand phone access's terminal
to enter your Ubuntu password if sudo requests it. The phone URL and login
remain unchanged. Closing the control tab leaves the services running;
Stop or Quit in the app provides explicit shutdown.

## First use on the desktop

1. Keep the Qwen server running. If it is stopped, start it in a terminal:

   ```bash
   cd ~/Projects/pLLM
   bash scripts/serve-nvfp4.sh 131072
   ```

2. For a direct manual WebUI start outside the control app, use another terminal:

   ```bash
   cd ~/Projects/pLLM
   PLLM_WEBUI_URL=https://ello-lin.tailad2999.ts.net bash scripts/serve-webui.sh
   ```

3. On the desktop, open <http://127.0.0.1:8080> and sign into the owner
   account already created. On a fresh installation only, the first account
   becomes administrator. Further signup is disabled by this configuration.
4. Select `qwen3.8-27b` and send a short message. The existing vLLM API key
   is configured on the PC; the phone does not need to know it.

## Enable private access

Account enablement and the foreground route are now confirmed. For future
manual starts after stopping it, run this on the desktop:

```bash
sudo tailscale serve --https=443 http://127.0.0.1:8080
```

Enter your normal Ubuntu password when sudo asks. Do not send it in chat. Keep the command running and use the HTTPS URL it
prints: <https://ello-lin.tailad2999.ts.net>.

Keep this command in the foreground. We deliberately omit `--bg`: sharing
is manual and is not configured to resume after reboot. Ctrl+C stops the
foreground sharing session. Do not use public `tailscale funnel` for this
setup. Tailscale access follows the tailnet's access policy; Open WebUI
also requires its own account login.

## Open it on the iPhone

1. Install the Tailscale iOS app and sign into the same tailnet as the PC.
2. Accept the iOS VPN configuration prompt and connect Tailscale.
3. In Safari, open <https://ello-lin.tailad2999.ts.net> and sign into your
   Open WebUI account.
4. Choose `qwen3.8-27b`, send a message, and confirm the reply streams.
5. Optionally add it to the Home Screen using Safari's sharing menu.
6. Test again with home Wi-Fi switched off and cellular data active,
   keeping Tailscale connected. This validates access away from home.

The PC must be awake, with vLLM, Open WebUI, and the Serve session running.
Turning Tailscale off on the phone removes this private route. Stopping
vLLM leaves the UI accessible but unable to generate replies. Stopping the
UI leaves the Serve proxy without its local web application. None of these
commands enables model/UI startup on boot or changes system sleep policy.

## If the model is missing

On the desktop, sign in as administrator and open Admin Settings →
Connections. The configured compatible API is:

- Base URL: `http://127.0.0.1:8000/v1`.
- Model: `qwen3.8-27b`.
- Authentication: the local value in `.secrets/vllm-api-key`.

The UI backend makes this connection. Do not enter `127.0.0.1:8000` as the
phone's destination: on the phone, localhost refers to the phone itself.
Existing UI settings are persisted and can override environment defaults.

## Reinstalling this UI environment

These are the commands used for the initial installation:

```bash
cd ~/Projects/pLLM
uv venv --python 3.11 --managed-python .venv-webui
uv pip install --python .venv-webui/bin/python open-webui==0.12.2 --torch-backend=cpu
```

The installed dependency snapshot is `requirements-webui.txt`; the CPU
wheel source still needs specifying when reproducing its PyTorch install.
Do not rerun environment creation just to restart the UI. Preserve
`.data/open-webui/` and `.secrets/webui-secret-key` when upgrading or moving
the installation; they contain chat/account state and the application secret.

The launch script uses offline mode to defer embedding/voice model downloads.
A missing cached embedding model is logged at startup; chat/health still
work. Document uploads/retrieval need a separate setup later. The disabled
tool/search/memory defaults are seeded into the UI's persistent settings.

## References

- [Open WebUI quick start](https://docs.openwebui.com/getting-started/quick-start/)
- [Open WebUI configuration](https://docs.openwebui.com/reference/env-configuration/)
- [Tailscale Serve command](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Tailscale on iOS](https://tailscale.com/docs/install/ios)

## Initial responsiveness settings

For a single local model, automatic UI jobs share inference capacity.
Turn off Follow-up, Chat Title, and Tag Generation in Admin Panel →
Settings → Interface for a latency trial; autocomplete was already off.
Owner reported doing this, but the final persisted-state check found tags
and follow-ups off while title generation remained on. Reconcile that next
session; no setting was changed during wrap-up. Compare direct API and UI
latency before attributing delay to Tailscale or the frontend.

Open WebUI remains an evaluation client: the owner finds it feature-heavy.
Before changing clients, preserve `.data/open-webui/` and the app secret.
See ARCHITECTURE.md for how projects, chat history, and memory are stored.
