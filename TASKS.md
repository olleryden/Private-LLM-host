# Private LLM Host — Tasks

Last updated: 2026-11-16. Kong AI Gateway (Konnect-managed) was added in
front of vLLM; the next iteration integrates it (PLAN.md). Read PLAN.md for
the handoff and SETUP_LOG.md for commands/results. Checked items below are
completed evidence, not claims that every component is currently running.

## Kong AI Gateway: added 2026-11-15 to 2026-11-16

- [x] Owner chooses to keep the Konnect control plane. Exception to the
      local-only rule, for configuration and analytics only.
- [x] Find Kong holding `127.0.0.1:8000`. It blocked vLLM and made pLLM
      Control report Qwen as running.
- [x] Recreate `kong-ai-gateway` with host networking, proxy
      `127.0.0.1:8100`, admin/GUI/status listeners off, and the vLLM key
      in container env. The old container was kept for rollback.
- [x] Verify the loopback-only listener (refused on LAN, Tailscale, and
      Docker addresses) and a free `:8000`.
- [x] Owner confirms node `ello-lin` Connected/In sync/Compatible, and
      creates provider `ello-lin-vllm` and model `qwen3.8-27b`.
- [x] Verify chat and streaming through Kong, gateway-added vLLM auth,
      and Kong overhead of about 2 ms.
- [x] Document setup, usage, access management, and operations
      (KONG.md, SETUP_LOG.md §22).
- [ ] **Next iteration, step A:** analyze what Kong changes across the
      project from the updated docs. Confirm the loose-ends list in PLAN.md.
- [ ] **Next iteration, step B:** edit code to close the loose ends below,
      with tests, and keep the docs consistent.
- [ ] Switch Open WebUI's persisted connection to Kong: `:8100/v1`,
      placeholder key, manual model ID. Then update
      `scripts/serve-webui.sh` and PHONE_CHAT.md.
- [ ] Make pLLM Control identify Qwen more robustly than "something is
      listening on :8000", and show Kong's status. Decide whether it
      manages Kong.
- [ ] Add a repository script to create or recreate the Kong container
      without embedded secrets, with no restart policy by default. Check
      the current restart policy.
- [ ] Rotate the exposed vLLM API key; this needs the recreate script.
- [ ] Owner checks in Konnect:
  - [ ] the provider header shows `{vault://env/pllm-vllm-auth}`;
  - [ ] `docker rm kong-ai-gateway-old`;
  - [ ] the unused data-plane certificate is deleted;
  - [ ] the data-plane key is rotated if the exposed key is the active one.
- [ ] Before sharing Kong beyond the PC: add an API-key auth strategy and
      consumers, align the key header with `Authorization: Bearer`
      clients, and test that keyless requests get 401.

## Security hardening: tailnet exposure review, 2026-11-16

Details stay in the ignored `personal/` folder, not in this pushed file.

- [ ] Enable two-factor login on the identity account used for Tailscale,
      and on Konnect.
- [ ] Check and tighten the remote shell access settings.
- [ ] Narrow file-sharing services to what is needed.
- [ ] Confirm a strong, unique Open WebUI owner password. It is the only
      check before chat for tailnet devices.
- [ ] Optionally restrict tailnet devices to the ports they need.

## Local instance controls — requested after wrap-up

- [x] Add one local dashboard with visible per-instance state, Start/Stop,
      optional recent output/input, and a workspace shell.
- [x] Reuse validated model/UI scripts without changing inference flags.
- [x] Keep starts explicit, use readiness checks, and report external
      instances without killing/adopting arbitrary processes.
- [x] Add detached launch/reopen and explicit quit behavior; closing a browser
      tab does not stop instances. Hosting stays manual; no keep-awake changes.
- [x] Add an Ubuntu Applications launcher; validate process/API behavior
      with disposable children and the live workspace terminal.
- [ ] Owner acceptance: start/stop the real Qwen and chat services in the app,
      enter sudo password for sharing if requested, and chat from the iPhone.
- [ ] Evaluate a full terminal emulator only if the transcript/line input
      is insufficient. Full-screen terminal apps currently need a terminal.

## Phone control and controller-only startup

- [x] Add a distinct private control origin on HTTPS :8443 with exact
      Tailscale owner-identity checks, local binding, API token, Host/Origin
      restrictions, and mobile chat links using the PC's private hostname.
- [x] Add an optional controller startup checkbox; install/validate a user
      service that starts no model/UI. Keep defaults off until explicit setup.
- [x] Manually start the validated user service and test security/lifecycle
      with disposable children. Full suite: 31 passing tests.
- [x] Owner chooses pre-login controls and activates persistent :8443 route;
      enable user service and lingering. Controller runs without Qwen/Chat.
- [x] Verify actual owner identity through Tailscale HTTPS, remote API,
      mobile chat URL, and harmless shell start/input/output/stop.
- [ ] Verify iPhone/cellular start/stop, real reboot behavior, and actual
      controller availability before desktop login.

## Next session — responsiveness and client choice

- [ ] Reconcile the stored title-generation setting. Owner reported turning
      off all three background jobs; final DB check found title=true,
      tags=false, follow-ups=false. Do not silently change owner settings.
- [ ] Start the verified model manually if needed and measure direct streamed
      short requests: first reasoning, first answer, total time, token counts,
      and decode throughput. Compare thinking off / low / default.
- [ ] Compare the same workload through Open WebUI; check for queue delay,
      background work, or buffering. Owner reported 5–20s before first text;
      historical active decode windows are about 20 tokens/s.
- [ ] Test CUDA graphs/compilation as a separate candidate on the current
      weights. Preserve the working launcher and recheck 128K fit/recall.
- [ ] Evaluate embedded MTP separately if justified: startup compatibility,
      acceptance, generation quality, VRAM, and >100K behavior.
- [ ] Decide whether a simplified Open WebUI setup or a lighter existing
      chat client is preferable. Owner finds the current UI bloated.
      Preserve chat/account data before any migration; no replacement chosen.

## Completed foundation

- [x] Review Markdown plan and completed work; retain current setup evidence.
- [x] Confirm target hardware and owner-reported driver 595.99.02 / idle
      VRAM baseline 582MiB. Verify Ubuntu 24.04.4 LTS from the host.
- [x] Select Qwen3.8-27B and NVIDIA NVFP4 for the current trial.
- [x] Create `.venv-nvfp4`; verify Python 3.12.14, vLLM
      `0.32.0rc1.dev251+gee8c47961`, torch `2.14.0+cu132`, CUDA GPU matmul.
- [x] Download NVIDIA weights (21G), revision
      `482ca0f3832238542f8f5295dde86b5f22711d80`.
- [x] Diagnose first generation crash: Ninja unavailable on executable PATH.
- [x] Provision Ninja 1.13.2, FlashInfer Python/cubin 0.7.1 and JIT cache
      0.7.1+cu130; record the installed versions.
- [x] Diagnose second crash: CUDA-12-linked JIT module could not load
      libcudart.so.12. Locate existing CUDA 12.9 toolkit/runtime.
- [x] Add correct runtime path and disable FlashInfer autotuning after
      transient scratch-allocation failures. Verify actual generation.
- [x] Save manual launcher with loopback binding, API key, FP8 KV, one
      active request, eager/text-only mode, and no boot enablement.
- [x] Verify generated chat HTTP 200 and no-key models request HTTP 401.
- [x] Start at 131,072 total context and pass short chat/auth checks there.
- [x] Process 119,751 synthetic input tokens + 86 output tokens; exact
      start/middle/end recall. First content 38.45s, full response 42.65s.
- [x] Save repeatable short/auth and long-context checks plus result artifact.
- [x] Research single-5090 measurements; save sources/differences in
      PERFORMANCE.md. No performance settings changed during research.
- [x] Document no further need to reproduce superseded checkpoint setups.

## Chat UI and phone access

- [x] Select Tailscale for owner devices; inspect installed Tailscale 1.102.3.
- [x] Install Open WebUI 0.12.2 in separate Python 3.11.16 environment with
      torch 2.14.1+cpu. Capture requirements-webui.txt.
- [x] Add manual UI launcher with authenticated server-side vLLM connection,
      persistent local app data, app secret, and account login.
- [x] Verify page/health HTTP 200 and unauthenticated UI model API HTTP 401.
- [x] Confirm owner account and saved chats exist; browser chat requests
      succeeded in application/model logs, including a tailnet-origin request.
- [x] Owner enables Serve at account level; local sudo step documented.
- [x] Confirm foreground HTTPS route for ello-lin.tailad2999.ts.net →
      localhost:8080. No `--bg` or boot startup enabled by this setup.
- [x] Owner disables tags/follow-ups; title generation needs reconciliation.
- [x] Record application/project/history/memory storage in ARCHITECTURE.md.
- [ ] Explicitly verify chat from iPhone on cellular with Tailscale connected.
- [ ] Verify streaming/reconnect behavior on the actual phone/browser.

## Phase 0 follow-up — serving evidence

- [ ] Capture final full dependency/wheel-source snapshot after fixes; retain
      model revision and tested launch config for reproducibility.
- [ ] Test representative document/code inputs, near-boundary context, and
      repeated requests; one synthetic result does not establish full quality.
- [ ] Observe ordinary GUI activity and peak memory during model use.
      Earlier GNOME debugging caused forced logouts; do not repeat live
      shell replacement experiments. Display refresh is not a proven cause.
- [ ] Decide whether GUI coexistence needs further tuning from measurements;
      do not switch to headless operation preemptively.

## Phase 1 — tools and coding

- [ ] Validate real multi-turn tool calls and results with qwen3_coder parser.
- [ ] Choose an existing coding client and verify scoped project edits and
      terminal commands against the authenticated private model endpoint.
- [ ] Add internet search/page fetch and source links through a configured
      application/tool runner; document which requests leave the PC.
- [ ] Define and test one user-triggered task: parameters, permissions,
      result reporting, failure, and cancellation.
- [ ] Verify each client's context/tool integration explicitly. Direct vLLM
      clients do not inherit WebUI projects/history/memory automatically.

## Phases 3–5 — lifecycle, reliability, data

- [x] Add Start/Stop and visible state in a separate minimal local control app;
      define browser-close and explicit application-quit behavior.
- [x] Add optional controller-only automatic startup setting, off by default.
- [ ] Test actual enabled/disabled reboot behavior and deliberate controller
      quit without unwanted restart. Models remain manual in both modes.
- [ ] Offer explicit keep-awake behavior while hosting; preserve normal
      sleep preferences. Wake-on-LAN is deferred.
- [ ] Test readiness, crash recovery, bounded logs, and reconnects.
- [ ] Implement and test consistent backups/restores of application DB,
      uploads/indexes, configuration, and necessary secrets. Git ignores app
      data and does not back it up. Preserve state before any client change.
- [ ] Document pinned upgrades and rollback; avoid logging personal prompts.

## Phase 6 — personal context (deferred)

- [x] Confirm first sources: owner-selected local files, documents, repos.
- [ ] Inventory source roots/types/size and update frequency; exclude keys,
      credentials, dependency directories, and build output by default.
- [ ] Configure local extraction/CPU embedding and search with source references.
- [ ] Test semantic queries and exact code symbols; refresh additions,
      updates, deletions, and stale-index behavior.
- [ ] Implement editable saved preferences/project summaries and explicit
      scope. WebUI memory is currently disabled; folder membership alone
      is not a validated project memory-isolation mechanism.
- [ ] Keep chat retention, source deletion, and memory cleanup distinct.
- [ ] Verify local processing/provider choices before ingesting personal data.

## Phase 7 — acceptance and later installer

- [ ] Validate real remote chat/coding/document workflows and unanswerable queries.
- [ ] Test reboot behavior with boot startup off and on, retaining chat/memory.
- [ ] Run a 24-hour realistic soak test and a restore test.
- [x] Create SETUP_LOG.md and capture installation errors/fixes/results.
- [ ] After practical use proves worthwhile, implement a guided installer
      for the tested Ubuntu/5090 profile with pins, resumable downloads,
      generated secrets/config, clear errors, and manual lifecycle defaults.
- [ ] Test clean install, reruns, recovery, upgrades, and uninstall/data retention.

No personal source ingestion, live web tools, coding agent, memory system,
custom replacement chat UI, or polished installer is implemented yet.
