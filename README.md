# Private LLM Host

Run Qwen on a home desktop and access it from your other devices anywhere
with internet while hosting is active. Start manually by default; optional
continuous hosting and a “Start on boot” setting are planned. Build a personal assistant with shared chat
history, searchable local files/documents/code repositories, and durable
memory. Support regular chat and coding, with tools for web search, local
information, and user-triggered tasks.

## Hardware (desktop, home)

| Component | Spec |
|---|---|
| OS | Ubuntu |
| GPU | RTX 5090, 32GB VRAM (Blackwell generation) |
| CPU | AMD Ryzen 9 9950X3D |
| RAM | 96GB DDR5-6000 |
| Storage | 4TB PCIe 5 NVMe |

## Model

Current setup: **Qwen3.8-27B**, using NVIDIA's NVFP4 checkpoint and vLLM
on the RTX 5090. The fresh `.venv-nvfp4` environment passes GPU execution
checks; model download, 32K startup, short generated responses, and API
key checks pass. The 131,072-token configuration also passed a synthetic
119,751-token input test with correct start/middle/end recall. Real-workload
quality and sustained stability remain to be validated.
Target context: 131,072 tokens for one active request.

Open WebUI 0.12.2 provides browser chat with local persistent data. Private
Tailscale Serve is configured at https://ello-lin.tailad2999.ts.net; an
explicit iPhone/cellular acceptance test remains open. The owner finds the
UI feature-heavy, so client choice remains under evaluation. Personal
knowledge, memory, search, and task tools are still deferred.

Open **pLLM Control** from Ubuntu's Applications menu, or run:

```bash
cd ~/Projects/pLLM
bash scripts/start-control.sh
```

The app at <http://127.0.0.1:8787> shows the model, chat UI, and private
sharing as separate instances, with Start/Stop and optional terminal input.
Qwen and Chat start only when requested. See [CONTROL.md](./CONTROL.md) for lifecycle
and launch details. Chat-client choice and latency tuning remain open.

Optional [phone controls](./PHONE_CONTROL.md) use a separate private URL on
port 8443 and start with the PC, before desktop login in the selected setup.
The private control link is active. Qwen and Chat still start on demand.

[Kong AI Gateway](./KONG.md) is an OpenAI-compatible front door to the same
model, at `http://127.0.0.1:8100/v1` (this PC only). It runs as a Docker
container, configured from Kong Konnect, Kong's hosted control plane.
Prompts stay on the PC. Konnect, which holds gateway configuration and
analytics, is the project's one accepted hosted service. Kong adds the
vLLM key itself; it will later add per-client keys and access rules.
Open WebUI still talks to vLLM directly until it is switched over.

Personal or sensitive context, such as account IDs, network details, and
security findings, belongs in [`personal/`](./personal/README.md). Only that
folder's README is pushed.

## Architecture

![pLLM architecture: phone and local clients reach Qwen on vLLM through Tailscale Serve, Open WebUI, and Kong AI Gateway; pLLM Control starts services; Kong syncs config with Konnect](./.archify/pllm-architecture.svg)

Diagram as of 2026-11-16. The interactive version is
[`.archify/architecture-pllm-20261116-010025/pllm-architecture.html`](./.archify/architecture-pllm-20261116-010025/pllm-architecture.html);
open it locally in a browser.

| Service | Use |
|---|---|
| vLLM · Qwen3.8-27B (`127.0.0.1:8000`) | Runs the model and serves an OpenAI-compatible API protected by a key |
| Open WebUI (`127.0.0.1:8080`) | Chat app with login; stores chats and accounts in `.data/open-webui` |
| Kong AI Gateway (`127.0.0.1:8100`) | Gateway in Docker for local API clients; adds the vLLM key |
| Kong Konnect (hosted, EU) | Holds Kong's configuration and usage stats; never sees prompts |
| pLLM Control (`127.0.0.1:8787`) | Dashboard that starts and stops Qwen, Chat, and phone sharing |
| Tailscale Serve `:443` | Private HTTPS route from your devices to Open WebUI; started manually |
| Tailscale Serve `:8443` | Private HTTPS route to pLLM Control; only the owner's Tailscale login gets in |

## Docs

- **Planning and tasks:** the self-hosted Vikunja tracker on this PC,
  project Personal Assistant → pLLM. Start there for "where are we and
  what's next." [`PLAN.md`](./PLAN.md) and [`TASKS.md`](./TASKS.md) only
  point there now.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — current components, request flow,
  how WebUI wraps the model, and where projects/history/memories live.
- [`SETUP_LOG.md`](./SETUP_LOG.md) — commands, verified results, pending
  steps, and reproducibility inputs for the eventual guided installer.

- [`PHONE_CHAT.md`](./PHONE_CHAT.md) — desktop account setup, private iPhone
  access, and manual UI/Serve start and stop instructions.

- [`PERFORMANCE.md`](./PERFORMANCE.md) — measured speed comparisons,
  configuration differences, and controlled tuning candidates.
- [`CONTROL.md`](./CONTROL.md) — single local control app, instance states,
  optional terminal input, and manual start/stop behavior.
- [`PHONE_CONTROL.md`](./PHONE_CONTROL.md) — private iPhone controls,
  owner authentication, and optional controller-only startup.
- [`KONG.md`](./KONG.md) — Kong AI Gateway and Konnect: setup, usage,
  managing access, and operations.
- [`personal/`](./personal/README.md) — local-only personal context. Its
  contents are Git-ignored except the folder README.

## Patch notes

Newest first. Dates are when the work was done, which can be earlier than
the commit. Each entry has three parts: what changed, what it means for
using and running pLLM, and what is still open. SETUP_LOG.md has the
commands and evidence.

### 2026-11-17 — Planning moved to Vikunja

**What changed**

- The plan and task checklist moved from PLAN.md and TASKS.md to the
  self-hosted Vikunja tracker, project Personal Assistant → pLLM. Both
  files now only point there; their last Markdown versions are in Git
  history.
- pLLM is now one sub-project of Personal Assistant. The others are
  Memory bank, a harness-agnostic memory that takes over roadmap phase 6,
  and Docker management, an overview of the container deployments.

**What it means**

- **One place for status.** Open work, priorities, and done milestones
  are cards on the pLLM board, each with its steps as a checklist.
  Assistants read and update them through Vikunja's MCP server instead of
  editing Markdown.
- **Planning now depends on Vikunja.** It runs in Docker on this PC, and
  the plan exists only in its database until backups are set up. That is
  the top card in Docker management.
- **Grouping uses title prefixes.** Related cards share a prefix such as
  "Kong:", because the current Vikunja MCP token cannot attach labels or
  link tasks.

**Still open:** everything that was open in TASKS.md, now on the board.

### 2026-11-16 — Architecture diagram and commit-time check

**What changed**

- The README has an [Architecture](#architecture) section: a refreshed
  Archify diagram (now including Kong and Konnect) and a one-line table
  of services.
- Claude Code hooks (`.claude/settings.json`) check, before each commit,
  whether the architecture changed since the diagram was last updated.
  They run `scripts/arch-diagram-check.py`; `scripts/export-diagram-svg.mjs`
  re-exports the README figure.

**What it means**

- **The current setup is visible at a glance.** One picture shows how your
  phone, the PC's services, and Konnect connect, without reading
  ARCHITECTURE.md.
- **The diagram is less likely to go stale.** When your message mentions a
  commit, Claude is told which architecture-relevant files changed since
  the last diagram update. Before Claude itself runs `git commit` with
  such changes and no refreshed diagram, you are asked first; it is never
  a hard block.
- **The check only covers commits made through Claude.** Commits you make
  yourself in a terminal are not checked. Ask for a commit message first,
  as usual, to get the check.

**Still open:** an optional git pre-commit warning for commits made outside
Claude. The hooks are active; the prompt check fired on 2026-11-16.

### 2026-11-16 — Kong AI Gateway and personal context

**What changed**

- [Kong AI Gateway](./KONG.md) now sits in front of vLLM at
  `http://127.0.0.1:8100/v1`. It is configured from Kong Konnect, Kong's
  hosted control plane, and it adds the vLLM key itself.
- Kong was moved off port 8000, where it had been blocking vLLM.
- Sensitive notes moved into a new local-only
  [`personal/`](./personal/README.md) folder.

**What it means**

- **Easier to connect tools.** Coding agents, scripts, and other
  OpenAI-compatible tools on this PC can use Qwen through Kong without
  knowing the vLLM key. This is the base for per-tool keys, per-model
  access rules, rate limits, and usage statistics later.
- **Chat is unchanged.** Open WebUI still talks to vLLM directly until it
  is switched over.
- **A hosted service is now involved.** Konnect stores the gateway
  settings and sees usage metadata: request counts, token counts, and
  latency. It never sees prompts or replies. Anyone who logs in to the
  Konnect account can change routing, though not open Kong to the network,
  so protect that login with two-factor authentication. If the internet
  drops, Kong keeps running with its last settings.
- **Kong is a new thing to keep running.** It is a Docker container that
  pLLM Control does not show or manage; use `docker start` and
  `docker stop`. Whether it starts at boot has not been checked yet.
- **Kong has no access control yet.** Any program on this PC can use Kong
  without a key. That is acceptable only because Kong is reachable from
  this PC alone. Add per-client keys before sharing it with other devices.
- **Some clients need a manual model name.** Kong does not answer the
  model-list request, so enter `qwen3.8-27b` by hand.
- **No noticeable slowdown.** Kong adds about 2 ms; generation takes
  seconds.
- **Qwen starts and shows its status correctly again.** pLLM Control still
  assumes that whatever runs on port 8000 is Qwen, so keep that port free
  for vLLM.
- **The vLLM API key should be treated as exposed.** It leaked into an
  assistant session. Only programs on this PC can reach vLLM, which limits
  the risk, but the key should still be rotated.
- **Sensitive details now have a home.** Account IDs, addresses, and
  security findings stay in `personal/`, and the pushed docs refer to it
  in general terms. Git does not back up that folder, so include it in
  your own backups.

**Still open:** routing Open WebUI through Kong, rotating the key, Kong
status in pLLM Control, client keys, and security hardening. PLAN.md
schedules these as the next iteration.

### 2026-11-08 — Architecture diagrams

**What changed**

- Interactive diagrams were added in `.archify/` (committed 2026-11-15):
  - the pLLM architecture;
  - two examples: a central MCP tools platform, and an agent flow that
    searches for A* and then writes `astar.py`.

**What it means**

- **A picture of the system.** Open the HTML files in a browser to see how
  the parts connect.
- **Some of it is future design.** The MCP and agent examples show how the
  planned tool features could work, not how they work today.
- **They show the system as of 2026-11-08.** Kong is not in them yet;
  regenerate them after the integration iteration.

### 2026-10-16 — Phone controls

**What changed**

- [Phone controls](./PHONE_CONTROL.md) are available at private HTTPS
  `:8443`.
- The controller can start with the PC, before desktop login. Committed
  2026-11-15.

**What it means**

- **Start Qwen from your phone.** Switch the PC on, then start Qwen and
  Chat from the phone without sitting at the desk.
- **A small always-on process.** The lightweight controller now runs from
  boot. Qwen and Chat still use no GPU until you start them.
- **Your Tailscale login is the only lock.** There is no extra password, so
  anyone with a device signed in to your Tailscale account can do
  everything except Quit. That includes starting the Workspace terminal,
  which is a real shell on the PC running as you. Securing that account
  matters most; restricting the shell to the desktop is an option.
- **You can't lock yourself out.** Quit is blocked from the phone, so the
  remote controls can't be stopped by accident.
- **Not fully tested yet.** Real iPhone, cellular, and reboot tests are
  still pending.

### 2026-10-16 — pLLM Control

**What changed**

- A local [control app](./CONTROL.md) at `127.0.0.1:8787` starts and stops
  Qwen, Chat, and phone sharing.
- It has readiness checks, optional terminal output and input, launchers,
  and tests.

**What it means**

- **One place instead of several terminals.** You no longer keep a
  terminal open per service.
- **Closing the browser stops nothing.** Services keep running; an
  explicit Quit in the app stops what it started.
- **Some services are shown but not controlled.** Services started outside
  the app appear as "Detected outside app", and the app will not stop
  them.
- **Status is a guess based on ports.** Status comes from open ports, which
  is how Kong on :8000 was mistaken for Qwen.
- **The sudo password stays out of the app.** Sharing may ask for it in
  the app's terminal; it goes straight to sudo and is not saved.

### 2026-10-16 — Chat UI and private phone access

**What changed**

- [Open WebUI](./PHONE_CHAT.md) 0.12.2 is installed with an owner login.
- A private Tailscale Serve route makes it reachable from your devices.

**What it means**

- **Chat from any of your devices.** Chats are stored on the PC in
  `.data/open-webui/` and are the same everywhere. That folder is not in
  Git, so back it up separately.
- **Phone access is private.** It works only through Tailscale; there is no
  public URL and no router port forwarding.
- **The Open WebUI login is the user check for chat.** Open WebUI holds the
  model key on the PC, so phones never need it.
- **Background jobs slow your chat.** Automatic UI jobs such as titles and
  tags share the model's single request slot, which adds waiting time.
- **Open WebUI is still an evaluation.** Changing chat client later needs
  a data export or migration.
- **There is room to get faster.** First visible text takes 5–20 s and
  generation runs at about 20 tokens/s. Published results on the same GPU
  are faster, so tuning remains open (PERFORMANCE.md).

### 2026-10-15 to 2026-10-16 — Local inference

**What changed**

- Qwen3.8-27B (NVIDIA NVFP4) runs on vLLM on the RTX 5090: loopback-only
  API with a key, FP8 KV cache, 131,072-token context.
- Crashes on the first request were fixed: Ninja on PATH, matching
  FlashInfer kernels, the CUDA runtime path, and autotuning turned off.

**What it means**

- **The model runs entirely on your PC.** No data leaves it for inference.
- **One request at a time.** Simultaneous requests queue, including the
  UI's background jobs.
- **Very long inputs work but take time.** A 119,751-token input was
  recalled correctly, but the answer took about 38 s to start.
- **Speed was traded for stability.** Eager mode (no CUDA graphs) and no
  speculative decoding keep startup reliable but leave speed on the
  table.
- **The model thinks before it answers.** Reasoning tokens take time even
  for short replies.
- **It shares the GPU with your desktop.** While running, vLLM reserves
  about 90% of GPU memory, and startup takes about 90 s.
- **Upgrade with care.** The vLLM build is a pre-release dev version.
  Upgrades need testing, and the setup log records exact versions for a
  future installer.

### 2026-08-16 — Project plan

**What changed**

- Initial README, plan, architecture, and task documents.

**What it means**

- **The ground rules were set.** Everything runs locally, hosting starts
  manually with boot startup off by default, access is private, and a
  guided installer comes only after the system proves useful.
