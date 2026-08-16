# Self-hosted coding agent — architecture & design notes

Status: **planning phase** — decisions below are locked directionally, exact implementation details (flags, configs) to be finalized during build.
Last updated: 2026-08-16

## 1. Goal

Run a privately-hosted LLM on a home desktop, and use it as the "brain" behind an
agentic coding assistant (à la the Claude Code / Claude VS Code extension) — usable
both locally on the desktop and remotely from a laptop anywhere with internet access.

## 2. Hardware (desktop, home)

| Component | Spec |
|---|---|
| OS | Ubuntu |
| GPU | RTX 5090, 32GB VRAM (Blackwell generation) |
| CPU | AMD Ryzen 9 9950X3D |
| RAM | 96GB DDR5-6000 |
| Storage | 4TB PCIe 5 NVMe |

Headroom notes: 32GB VRAM comfortably fits the target model even at higher precision
(see §3). 96GB system RAM and 4TB NVMe are not bottlenecks for this workload — the
whole model lives in VRAM, system RAM just needs to cover OS + serving process +
agent tooling overhead.

## 3. Model — Qwen3.8-27B

Released 2026-08-13/14 (Apache 2.0). Key facts relevant to this build:

- **27–28B dense parameters**, hybrid attention: only 16 of 64 layers do full
  (quadratic) attention; the other 48 use a constant-size linear-attention state.
  This keeps KV cache size small even at very long context — good news for feeding
  an agent large repo context without exploding VRAM use.
- **262,144 token native context**, extensible to 1M via YaRN.
- Native vision-language model (multimodal) — **v1 of this project only uses the
  text/coding path**; vision is a possible stretch goal (e.g. screenshot-driven
  debugging) later.
- Ships with a built-in MTP (multi-token prediction) draft head — enables
  speculative decoding for faster generation, natively supported in vLLM.
- Benchmarks position it as strong specifically for coding/agentic work — e.g.
  Terminal-Bench and SWE-bench Pro scores competitive with much larger closed
  models. This is a good match for the intended use case (agentic coding).

**VRAM budget by precision** (weights only, before KV cache):

| Precision | Approx. size | Notes |
|---|---|---|
| BF16 | ~56GB | Doesn't fit on one 32GB card |
| FP8 | ~28GB | Fits, tight headroom for KV cache/context |
| NVFP4 | ~24.6GB | Blackwell-native 4-bit; official vLLM recipe validated on this exact GPU generation; leaves the most headroom for long context |
| GGUF (4-bit, llama.cpp path) | ~14–17GB | Not the current plan (see §4), noted as a fallback option |

**Recommended starting precision: NVFP4.** There's an official vLLM deployment
recipe for Qwen3.8-27B at NVFP4 specifically targeting Blackwell GPUs, and it
leaves the most VRAM free for large context windows, which matters for a coding
agent sending substantial file/repo context per turn. FP8 is the fallback if
NVFP4 tooling proves unstable (it's a newer/more exotic quantization format;
FP8 is more broadly battle-tested).

## 4. Architecture — components

Three independent layers. Decisions locked for each:

### 4.1 Model serving layer — **vLLM**

- Chosen over llama.cpp/Ollama because: official deployment recipe exists for
  this exact model + GPU generation; native support for the model's built-in
  speculative decoding head; automatic prefix/prompt caching (important for
  agentic coding — repeated/growing context across turns doesn't need to be
  reprocessed from scratch each time); designed for the continuous-batching
  request pattern an agent produces (multiple tool-call round trips per task).
- Trade-off accepted: more setup friction than llama.cpp — likely needs a
  recent/nightly build to match this model + GPU generation, more configuration
  surface (quantization format, batching, context length limits).
- Exposes an OpenAI-compatible API (`/v1/chat/completions`, `/v1/completions`)
  on a local port (e.g. `:8000`), bound to localhost/internal interface only —
  never exposed directly to the internet (that's Cloudflare's job, see §4.2).
- Must run with a tool-calling/function-calling parser matching Qwen3.8's chat
  template — required for agent tools (file edits, terminal commands, etc.) to
  work correctly. To verify during build.
- Runs as a systemd service: starts on boot, restarts on crash, logs to
  journal. Keeps the model resident in VRAM rather than reloading per request.
- Practical max context length for v1: start well below the 262K/1M ceiling
  (e.g. 64K–128K) to keep KV cache size predictable; raise once validated.

### 4.2 Network & auth layer — **Cloudflare Tunnel + Access**

- `cloudflared` runs on the desktop, creates an outbound-only tunnel to
  Cloudflare's edge — no inbound ports opened on the home router/firewall.
- A subdomain (e.g. `llm.yourdomain.com`) is mapped through the tunnel to the
  local vLLM port. Requires a domain added to Cloudflare (register one if you
  don't have one yet).
- **Cloudflare Access** (Zero Trust) sits in front of the tunnel hostname:
  unauthenticated requests get bounced at Cloudflare's edge before ever
  reaching the desktop. For interactive use this is normally an SSO/email-OTP
  login — but coding-agent clients (Continue/Cline/OpenCode/etc.) authenticate
  programmatically, not via a browser login flow. For that, use a **Cloudflare
  Access Service Token** (client ID + client secret), sent as
  `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers — this is what gets
  configured in the VS Code extension's request headers.
- Recommended defense-in-depth: also check a normal API key at the origin
  (vLLM or a thin reverse proxy in front of it), so a compromised/leaked
  service token alone isn't sufficient.
- A lightweight reverse proxy (Caddy is a reasonable choice) between
  `cloudflared` and vLLM is optional but recommended — gives you TLS/host
  handling, the API-key check above, and request logging in one place.

### 4.3 Power management — **open item, recommended default: disable sleep**

You noted the desktop sleeps/turns off sometimes. Since remote access depends
on the desktop actually being awake to run `cloudflared` and hold the model in
VRAM, this needs a deliberate policy. Options, roughly in order of simplicity:

1. **Disable system sleep, allow only the display to sleep.** Simplest, most
   reliable. Cost is a bit of extra idle power draw from a machine that's
   already fairly high-power. **Recommended default for v1.**
2. **Wake-on-LAN.** Lets the desktop actually sleep, woken by a magic packet —
   but triggering that packet *from outside your home network* needs either
   router support for WoL-over-WAN, or a small always-on device on the LAN
   (Raspberry Pi, smart plug, router script) that you can trigger remotely.
   More moving parts, worth revisiting later if power draw becomes a concern.
3. **Manual habit.** Just make sure the desktop is awake before you leave the
   house if you'll want remote access. Zero setup, relies on remembering.

### 4.4 Client layer — **existing agent tools, not a custom extension**

No need to build a Claude-Code-style extension from scratch. Continue, Cline,
Roo Code, and OpenCode (all mentioned as candidates) already support pointing
at an arbitrary OpenAI-compatible endpoint via a custom base URL + API key/
headers. This layer is configuration, not development:

- Base URL → the Cloudflare tunnel hostname (e.g. `https://llm.yourdomain.com/v1`)
- Model name → whatever vLLM is serving it as
- Auth headers → Cloudflare Access service token + origin API key (§4.2)
- Same config works from the desktop and the laptop — both go through the
  tunnel for consistency, though a "direct to localhost" shortcut when
  developing on the desktop itself is a reasonable later optimization.

## 5. Request flow (remote case)

1. VS Code (laptop, anywhere) → agent extension fires a request to the
   Cloudflare tunnel hostname.
2. Cloudflare Access checks the service-token headers; rejects unauthenticated
   traffic at the edge.
3. Cloudflare Tunnel routes the authenticated request through the outbound
   tunnel to `cloudflared` on the desktop.
4. `cloudflared` hands off to the local reverse proxy / vLLM directly.
5. vLLM runs inference on the RTX 5090 (Qwen3.8-27B), streams the response
   back along the same path.

When working directly on the desktop, the client can talk to
`localhost:8000` directly, skipping steps 2–3 entirely.

## 6. Key decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Remote access | Cloudflare Tunnel + Access | Public HTTPS endpoint, SSO/service-token gate, no VPN client required on any device |
| Inference engine | vLLM | Official recipe for this model on Blackwell GPUs; prefix caching + speculative decoding fit the agentic workload well |
| Quantization | NVFP4 (fallback: FP8) | Blackwell-native, most VRAM headroom for long context |
| Client tooling | Existing OpenAI-compatible agent extensions (Continue/Cline/Roo/OpenCode) | Avoids building a custom VS Code extension; these already do what's needed |
| Power management | Disable sleep (v1 default) | Simplest reliable option; revisit WoL if power draw matters |

## 7. Open questions / stretch goals

- Which specific agent extension to standardize on (Continue vs Cline vs Roo
  vs OpenCode) — functionally similar, worth a short hands-on comparison.
- Multimodal (vision) usage of the model — e.g. screenshot-based debugging —
  not in scope for v1, revisit later.
- Monitoring/observability (basic logging is enough for v1; Prometheus/Grafana
  would be a nice-to-have later).
- Multi-model support (running more than one model, or swapping models,
  behind the same endpoint) — not needed yet given single-user, single-model
  use case.

## 8. Phased build plan

- **Phase 0 — local serving.** Install vLLM, serve Qwen3.8-27B (NVFP4) on the
  desktop, validate with a plain HTTP client against `localhost:8000`.
- **Phase 1 — tool calling.** Confirm the function-calling parser works
  correctly with an actual agent tool's request pattern (file edit / terminal
  tool calls), since this is what makes it usable as a coding agent rather
  than just a chat model.
- **Phase 2 — remote access.** Set up `cloudflared`, Cloudflare Access with a
  service token, test reachability from an external network (e.g. phone
  hotspot) — confirm both that access works when authenticated and is blocked
  when not.
- **Phase 3 — power management.** Apply the sleep-disable policy (or WoL, if
  preferred after Phase 2 validates everything else).
- **Phase 4 — client setup.** Configure the chosen agent extension on both
  desktop and laptop, pointing at the tunnel endpoint. Confirm end-to-end
  agentic workflows (multi-file edits, terminal commands) work over the
  remote path, not just simple chat completions.
- **Phase 5 — hardening (stretch).** systemd reliability tuning, logging,
  context-length tuning past the initial conservative default, revisit
  quantization (NVFP4 vs FP8) based on real usage.
