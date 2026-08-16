# Private LLM Host

Run a privately-hosted LLM on a home desktop, and use it as the "brain"
behind an agentic coding assistant (à la Claude Code / the Claude VS Code
extension) — usable both locally on the desktop and remotely from a laptop
anywhere with internet access.

## Hardware (desktop, home)

| Component | Spec |
|---|---|
| OS | Ubuntu |
| GPU | RTX 5090, 32GB VRAM (Blackwell generation) |
| CPU | AMD Ryzen 9 9950X3D |
| RAM | 96GB DDR5-6000 |
| Storage | 4TB PCIe 5 NVMe |

## Model

First target model: **Qwen3.8-27B** (Apache 2.0), served via vLLM at NVFP4
quantization. See `ARCHITECTURE.md` for full model/serving details.

## Docs

- [`PLAN.md`](./PLAN.md) — phased roadmap and current status. Start here for
  "where are we and what's next."
- [`TASKS.md`](./TASKS.md) — granular, ordered task checklist for the
  current phase.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — full system design: components,
  diagrams, data flow, key decisions.
