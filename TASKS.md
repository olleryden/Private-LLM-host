# Private LLM Host — Tasks

Granular, ordered task checklist. Companion to `PLAN.md` (phase-level
roadmap) — this file tracks the specific next actions within the current
phase, in the order they should happen. Check items off as completed; move
the "Current focus" marker as phases change.

Last updated: 2026-08-16

## Current focus: Phase 0 — local serving

- [ ] Confirm NVIDIA driver + CUDA version on the desktop supports the RTX
      5090 (Blackwell) and the intended vLLM build.
- [ ] Install/upgrade vLLM to a build with Blackwell + NVFP4 + Qwen3.8-27B
      support (likely nightly, per the official deployment recipe).
- [ ] Download Qwen3.8-27B weights (NVFP4 quantization).
- [ ] Launch vLLM serving Qwen3.8-27B on the desktop (internal port, e.g.
      `:8000`), with context length capped conservatively (e.g. 64K–128K)
      for the first run.
- [ ] Confirm KV cache fits comfortably in remaining VRAM headroom at that
      context length.
- [ ] Validate serving with a plain HTTP client (`curl` or similar) against
      `localhost:8000` — confirm `/v1/chat/completions` responds correctly.
- [ ] Wrap vLLM in a systemd service (start on boot, restart on crash,
      journal logging).
- [ ] Decide fallback plan if NVFP4 tooling proves unstable (switch to
      FP8).

## Up next: Phase 1 — tool calling

- [ ] Identify which tool-calling/function-calling parser matches
      Qwen3.8's chat template in vLLM.
- [ ] Test a real agent tool-call pattern (file edit / terminal command)
      end-to-end against the local server.
- [ ] Confirm multi-turn tool-call round trips work (not just a single
      call).

## Later: Phase 2 — remote access

- [ ] Register/confirm a domain in Cloudflare (if not already present).
- [ ] Install and configure `cloudflared` on the desktop; create the
      tunnel.
- [ ] Map a subdomain (e.g. `llm.yourdomain.com`) through the tunnel to
      the local port.
- [ ] Set up Cloudflare Access in front of the tunnel hostname.
- [ ] Create a Cloudflare Access Service Token for programmatic (agent)
      auth.
- [ ] Decide on and stand up the reverse proxy (Caddy, tentative) for
      TLS + origin API-key check + logging.
- [ ] Test reachability from an external network (e.g. phone hotspot):
      confirm authenticated access works and unauthenticated access is
      blocked.

## Later: Phase 3 — power management

- [ ] Apply sleep-disable policy (display sleep only, system sleep
      disabled) — v1 default.
- [ ] (If revisited) Evaluate Wake-on-LAN feasibility — router support for
      WoL-over-WAN, or an always-on LAN trigger device.

## Later: Phase 4 — client setup

- [ ] Do a short hands-on comparison of Continue / Cline / Roo Code /
      OpenCode against the local server.
- [ ] Pick one and configure it on the desktop (base URL, model name, auth
      headers).
- [ ] Configure the same extension on the laptop, pointed at the tunnel
      endpoint.
- [ ] Confirm end-to-end agentic workflows (multi-file edits, terminal
      commands) work over the remote path.

## Later: Phase 5 — hardening (stretch)

- [ ] systemd reliability tuning.
- [ ] Improve logging (proxy + vLLM).
- [ ] Tune context length upward from the initial conservative default,
      based on real usage.
- [ ] Revisit NVFP4 vs FP8 based on real-world stability/quality.
