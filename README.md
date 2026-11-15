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

## Docs

- [`PLAN.md`](./PLAN.md) — phased roadmap and current status. Start here for
  "where are we and what's next."
- [`TASKS.md`](./TASKS.md) — granular, ordered task checklist for the
  current phase.
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
