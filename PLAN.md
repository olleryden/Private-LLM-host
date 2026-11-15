# Private LLM Host — Plan

Last updated: 2026-11-16. Kong AI Gateway, with a Konnect control plane, was
added in front of vLLM. The next iteration integrates it with the rest of
the project.

## Goal and preferences

Run Qwen locally on the Ubuntu/RTX 5090 desktop, usable from desktop and
owner devices through private Tailscale access. Support normal chat, coding,
selected local documents/repositories, web search, and user-triggered tasks.
Target over 100K context. Start manually by default; optional boot startup
must be off by default. Keep custom development small and preserve exact
setup evidence for a guided installer after the system is useful and stable.
Everything runs on the PC. The one owner-approved exception is the Kong
Konnect hosted control plane, which holds gateway configuration and
analytics only; prompts and replies stay local.

## Current handoff

- **Kong AI Gateway (2026-11-15 to 2026-11-16):**
  - Docker data plane `kong-ai-gateway` on host networking, proxy
    `127.0.0.1:8100/v1`, managed from Konnect gateway `ello-ai-gateway`.
  - Provider `ello-lin-vllm` and model `qwen3.8-27b` → vLLM `:8000`.
  - Chat, streaming, and gateway-added vLLM auth pass; Kong adds about
    2 ms per request.
  - Kong was moved off `:8000`, where it had blocked vLLM and confused
    pLLM Control.
  - Open WebUI still calls vLLM directly; no Kong client auth is configured
    yet.
  - The vLLM key was exposed in an assistant session; rotation is pending.
  - Details: KONG.md, SETUP_LOG.md §22.
- **Inference works:** NVIDIA Qwen3.8-27B NVFP4, FP8 KV, configured 131,072
  tokens, one active request. A 119,751-token synthetic input recalled
  start/middle/end values correctly. First content 38.45s, full reply 42.65s.
- **Verified stack:** vLLM `0.32.0rc1.dev251+gee8c47961`, PyTorch
  `2.14.0+cu132`, driver 595.99.02. Model revision
  `482ca0f3832238542f8f5295dde86b5f22711d80`.
- **Working fixes:** executable PATH for Ninja, matching FlashInfer kernels,
  CUDA toolkit runtime path, and disabled autotuning. Eager mode remains
  enabled; compilation/CUDA graphs and speculative decoding remain off.
- **Chat UI installed:** Open WebUI 0.12.2 in a separate CPU-only environment,
  with persistent data and one owner account. Browser chats are stored.
- **Private route configured:** foreground Tailscale Serve maps
  `https://ello-lin.tailad2999.ts.net` to local UI :8080. Tailnet chat requests
  appear in logs. An explicit iPhone-over-cellular acceptance test remains open.
- **Lifecycle update:** WebUI was then gracefully stopped at the owner's
  request and port :8080 verified closed. Model :8000 was already stopped.
  The owner then cleared the old sharing command and started sharing in the
  app. It was gracefully stopped while loading protected phone controls.
- **Control app:** a small local dashboard on :8787 now manages explicit
  model/UI/Serve starts and stops, shows readiness, and offers optional
  terminal output/input plus a workspace shell. Existing external instances
  are observed rather than adopted. See CONTROL.md for usage and limits.
- **Desktop launch:** Applications entry and `~/Desktop/pLLM Control.desktop`
  are installed. The executable desktop shortcut may require right-click →
  Allow Launching once; setting trusted metadata from Codex was unsupported.
- **External sharing investigation:** the old root-owned Serve command was
  found paused on pts/5, reparented to the user system manager, with its
  foreground route still present. It has no visible original terminal.
  External state wording now says “Detected outside app,” with unknown
  uptime shown as a dash. The owner subsequently resolved this old instance.
- **Phone controller requested:** owner-restricted HTTPS :8443 → controller
  :8787, opt-in controller-only startup setting, and user service implemented.
  Owner chose availability before desktop login. Unit is enabled/running,
  lingering is enabled, and the owner activated the persistent route.
  Real HTTPS page/API and shell start/input/stop pass. See PHONE_CONTROL.md.
  Qwen and Chat stay manual; iPhone/cellular/reboot tests remain pending.
- **Performance concern:** owner reports 5–20s to first text; active decode
  log windows are about 20 tokens/s. Direct controlled latency comparison is
  pending. External single-5090 reports show faster results with differing
  weights/settings; see PERFORMANCE.md.
- **UI task settings:** owner reported disabling titles/tags/follow-ups.
  Final persisted-state check found tags=false, follow-ups=false, titles=true.
  Reconcile title generation next time; no setting was changed at wrap-up.
- **Personal context/tools:** memory, knowledge ingestion, web search, code
  execution, and task tools remain unconfigured/disabled. No project folder
  or saved memory records exist in the UI database at wrap-up.

## Decisions to revisit

Open WebUI is an evaluation client. The owner finds it feature-heavy and
wants to understand its behavior and data ownership. Before committing to
it, decide whether a reduced configuration is comfortable or whether a
lighter existing client is preferable. The requested service-control app
is separate from chat-client replacement. A new chat UI and polished
installer remain deferred.
History/memory belong to the application; changing clients needs an explicit
data migration/export plan, while the same vLLM model can be reused.

## Resume next time

### Next iteration: integrate the Kong change across the project

Owner request (2026-11-16): accommodate and analyze what the Kong addition
changes for the project as a whole, based on the updated documentation, then
edit whatever code is needed to tie loose ends together.

**Step A, analysis.** Re-read README.md, KONG.md, ARCHITECTURE.md,
SETUP_LOG.md §22, and TASKS.md. Write down how Kong changes each part:

- request flow, lifecycle and boot defaults, security boundaries;
- installer inputs;
- the local-only rule;
- chat-client choice.

Confirm or update the loose-ends list below before editing code.

**Step B, code.** Close the loose ends, with tests where behavior changes.
Known loose ends at handoff:

1. **Open WebUI → Kong.** Switch the persisted connection to
   `127.0.0.1:8100/v1` with a placeholder key and manual model ID
   `qwen3.8-27b`. Then update `scripts/serve-webui.sh`: its base URL and
   key, the `.secrets/vllm-api-key` requirement, and fresh-database
   defaults. Update PHONE_CHAT.md to match.
2. **pLLM Control awareness.**
   - Qwen is detected by any listener on `:8000` (`port_open`); identify it
     more robustly.
   - Show Kong's status. Chat will depend on Kong after item 1.
   - Decide whether the app starts and stops Kong or only reports it.
     Hosting stays manual.
3. **Kong container script.** Add a repository script that creates or
   recreates `kong-ai-gateway` from the SETUP_LOG §22 settings, without
   embedding secrets. Default to no restart policy (boot startup off).
   Also check the current container's restart policy.
4. **vLLM key rotation.** Rotate the exposed key using item 3:
   `.secrets/vllm-api-key` → restart Qwen → recreate Kong → update any
   direct clients.
5. **Konnect cleanup (owner).**
   - Confirm the provider header shows `{vault://env/pllm-vllm-auth}`.
   - Remove `kong-ai-gateway-old`.
   - Delete the data-plane certificate that does not match `~/kong-ai`.
   - Rotate the data-plane key if the exposed one is in use.
6. **Kong client access.** Before Kong is shared beyond the PC, add an
   API-key auth strategy and consumers. Align the key header name with
   OpenAI-style `Authorization: Bearer` clients, and test that requests
   without a key are rejected.
7. **Security hardening (owner, sudo).** Two-factor login on the Tailscale
   identity account and on Konnect. Key-only SSH. Narrower Samba sharing.
   A strong Open WebUI password. See TASKS.md.
8. **Docs.** Keep README.md, ARCHITECTURE.md, KONG.md, TASKS.md,
   SETUP_LOG.md, and this plan consistent with whatever the code changes.

### Then continue

1. Open pLLM Control and use it for explicit service startup. Confirm actual
   model/UI readiness and optional sharing; no instance starts just by opening it.
   Verify the now-active :8443 control link on the iPhone and after a real
   reboot. The control app is configured to start before desktop login.
2. Reconcile the title-generation toggle. Measure direct streamed latency
   and decode speed with fixed short prompts, then compare the UI. Kong
   adds about 2 ms; measure through Kong once Open WebUI uses it.
3. Test compilation/CUDA graphs on the same checkpoint as an isolated
   candidate. Keep the current launcher as fallback; preserve 128K capacity.
4. Test embedded MTP separately if justified; verify acceptance, memory,
   tool behavior, and actual >100K input before adopting.
5. Decide the chat-client direction, then finish phone/cellular validation.
6. Add selected local documents and web search, then an existing coding
   client and one user-triggered task. Prefer usable small milestones.
   Coding clients can use Kong at `127.0.0.1:8100/v1`.
7. Use it for real work before polished installer/settings development.

## End-to-end roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Local serving, authentication, context, reproducibility | Inference and >100K synthetic recall pass; latency/stability work open |
| 1 | Streaming and multi-turn tool calls | Streaming exercised; actual tool round trips pending |
| 2 | Private remote access | Serve route configured; external iPhone test pending |
| 3 | Manual lifecycle, optional boot toggle, hosting sleep preference | Local control app added; boot/recovery/sleep preferences pending |
| 4 | Chat UI and coding clients | Open WebUI running/evaluated; client choice open, coding pending |
| 5 | Readiness, logs, backup/restore, pinned upgrades/rollback | Partial evidence; operational checks pending |
| 6 | Local personal knowledge and editable memory | Pending; first sources are local files/docs/repos |
| 7 | Real remote workflows and sustained acceptance | Pending; no 24-hour soak or restore/reboot validation |
| After acceptance | Guided installer for tested Ubuntu/5090 profile | Deferred; setup log and dependency snapshots retained |

Kong AI Gateway (2026-11-16) is an optional local API front door. It is
not a phase of its own. It supports phases 2, 4, and 5: per-client access,
coding clients, and usage visibility.
Cloud model accounts, voice/vision, multi-model routing, and Wake-on-LAN are
future options. The earlier Cloudflare design is not on the current path.
Kong Konnect is the only hosted service in use, for gateway configuration.

## Documentation map

- TASKS.md: completed checklist and ordered outstanding work.
- SETUP_LOG.md: exact commands, observed results, failures, fixes, sources.
- ARCHITECTURE.md: current components, request flow, settings, data storage.
- PHONE_CHAT.md: manual startup and iPhone/Tailscale access.
- PERFORMANCE.md: external measurements and controlled tuning candidates.
- CONTROL.md: local instance dashboard, launch/stop behavior, terminal limits.
- KONG.md: Kong AI Gateway/Konnect setup, usage, access management, operations.
- personal/: local-only context (account IDs, network details, security
  review). Git-ignored except its README; read it when present.
- README.md: quick entry point. INSTRUCTIONS.md: persistent project preferences.

Detailed setup history remains in SETUP_LOG.md, including the later WebUI
shutdown and service-control app. Validated inference flags and chat UI
settings were not changed while adding lifecycle controls.
