# Private LLM Host — Plan

Status: **planning phase** — Phase 0 not yet started.
Last updated: 2026-08-16

For system design/components, see `ARCHITECTURE.md`. For the granular task
checklist, see `TASKS.md`. For hardware/model quick facts, see `README.md`.

## Goal

Run a privately-hosted LLM on a home desktop, and use it as the "brain"
behind an agentic coding assistant (à la Claude Code / the Claude VS Code
extension) — usable both locally on the desktop and remotely from a laptop
anywhere with internet access.

## Phased build plan

- **Phase 0 — local serving.** Install vLLM, serve Qwen3.8-27B (NVFP4) on
  the desktop, validate with a plain HTTP client against `localhost:8000`.
  **← current phase**
- **Phase 1 — tool calling.** Confirm the function-calling parser works
  correctly with an actual agent tool's request pattern (file edit /
  terminal tool calls), since this is what makes it usable as a coding
  agent rather than just a chat model.
- **Phase 2 — remote access.** Set up `cloudflared`, Cloudflare Access with
  a service token, test reachability from an external network (e.g. phone
  hotspot) — confirm both that access works when authenticated and is
  blocked when not.
- **Phase 3 — power management.** Apply the sleep-disable policy (or WoL,
  if preferred after Phase 2 validates everything else).
- **Phase 4 — client setup.** Configure the chosen agent extension on both
  desktop and laptop, pointing at the tunnel endpoint. Confirm end-to-end
  agentic workflows (multi-file edits, terminal commands) work over the
  remote path, not just simple chat completions.
- **Phase 5 — hardening (stretch).** systemd reliability tuning, logging,
  context-length tuning past the initial conservative default, revisit
  quantization (NVFP4 vs FP8) based on real usage.

## Future / stretch goals (post-v1)

- Multimodal (vision) usage of the model — e.g. screenshot-driven debugging.
- Monitoring/observability beyond basic logging (Prometheus/Grafana).
- Multi-model support (running more than one model, or swapping models,
  behind the same endpoint) — not needed yet given single-user,
  single-model use case.

## Changelog

- 2026-08-16 — Initial plan drafted (hardware, model choice, architecture
  decisions locked directionally).
- 2026-08-16 — Split into `README.md` / `PLAN.md` / `ARCHITECTURE.md` /
  `TASKS.md` for cleaner separation: this file now tracks phase-level
  roadmap and status only.
