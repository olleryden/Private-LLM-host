My desktop PC is running ubuntu, and the specs are:
GPU: RTX 5090 32GB
CPU: AMD Ryden 9 9950X3D
RAM: 96GB DDR5 6000MHZ
SSD: 4TB PCIE-5 nvme

The model I am first wanting to use is the new Qwen 3.8 27B model.
Important to:
*  Update in the PLAN.md file whenever progress is made, new tasks or subtasks appear. Both to track where we are in the project, but mainly to be able to switch between chats and still receive the correct context (and also decide on which part of the system to work on next).
* Keep the design and architecture scribbled down in the ARCHITECTURE.md file. This is so we can visualize the design later and sketch it up.
* Update and keep track in the TASKS.md file.
* Keep SETUP_LOG.md updated with exact setup commands, observed results,
  dependency/model revisions, errors, and fixes. Distinguish owner-confirmed
  desktop results from proposed commands. The owner wants a guided,
  reproducible installer after the setup works end to end; preserve enough
  detail to implement and test it without requiring hosting expertise.
* Hosting starts manually by default; boot startup must be optional via
  settings and off by default. Support regular chat and coding with tools,
  including internet search and user-triggered tasks. Keep installer and
  service defaults aligned with these preferences.
* Open WebUI is an evaluation client, not a committed architecture choice.
  The owner finds its feature load excessive; prioritize understanding data
  ownership and a simpler daily experience. Preserve app data before any
  client migration. Measure latency before adding more features or changing
  the validated inference configuration.
* The owner requested a separate minimal local application for instance
  status, Start/Stop, and optional terminal output/input. pLLM Control
  supervises the existing launch scripts; keep hosting manual and terminal
  details optional. Closing its browser leaves hosting active; explicit quit
  can stop its managed instances. It is not a replacement chat client.
* The owner subsequently requested phone control after switching the PC on.
  Optional automatic startup of the lightweight controller is authorized;
  Qwen and WebUI still start only on demand. Keep private control access
  separate from chat sharing so stopping inference/chat never removes the
  remote controls. Restrict remote commands to the owner's Tailscale identity.
  The owner chose controller availability before desktop login; its optional
  user service, lingering, and persistent private :8443 route are enabled
  on this PC. New-install defaults still require explicit opt-in.
* Everything runs on the owner's PC: no cloud models or hosted tools. The one
  owner-approved exception (2026-11-15) is Kong Konnect as the hosted
  control plane for the local Kong AI Gateway. It holds configuration and
  analytics only; prompts and replies stay on the PC. Keep secrets out of
  Konnect, for example with `{vault://env/...}` references.
* Pushed docs must not contain secrets, account identifiers, or detailed
  security findings. Put personal or sensitive context in `personal/`,
  which is Git-ignored except its README. Read it for extra context when
  it exists.
* Keep the "Patch notes" section at the end of README.md current. Add a
  dated entry, newest first, for every notable change, with three parts:
  "What changed" (brief), "What it means" (practical implications: new
  abilities, new dependencies, behavior changes, security/privacy
  trade-offs, risks), and "Still open". Point to SETUP_LOG.md for evidence
  rather than repeating it.
* Before every commit, check whether the system architecture changed:
  services, ports, request paths, trust boundaries, or lifecycle. If it did:
  1. Regenerate the Archify diagram in a new
     `.archify/architecture-pllm-<timestamp>/` folder, pinned to `HEAD`.
  2. Re-export `.archify/pllm-architecture.svg` with
     `scripts/export-diagram-svg.mjs`.
  3. Update the README "Architecture" section: the figure, the
     interactive link, and the one-line service table.

  Hooks in `.claude/settings.json` run `scripts/arch-diagram-check.py`.
  They list architecture-relevant changes when a prompt mentions a commit,
  and ask before a `git commit` whose diagram was not refreshed.
