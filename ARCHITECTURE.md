# Architecture — Private LLM Host

Last updated: 2026-11-16 (Kong AI Gateway added). This describes the current
installation and clearly separates unimplemented features. See SETUP_LOG.md
for exact commands/fixes.

## Hardware and model

Ubuntu 24.04.4 LTS; RTX 5090 32GB; Ryzen 9 9950X3D; 96GB DDR5; NVMe storage.
Driver 595.99.02. Model: `nvidia/Qwen3.8-27B-NVFP4`, revision
`482ca0f3832238542f8f5295dde86b5f22711d80`.
NVIDIA's checkpoint mixes NVFP4 and FP8 layers; it is not uniformly 4-bit.

vLLM runs in `.venv-nvfp4`: Python 3.12.14, vLLM
`0.32.0rc1.dev251+gee8c47961`, PyTorch `2.14.0+cu132`.
Current manual launcher: scripts/serve-nvfp4.sh. It binds to loopback :8000,
uses a local API key, FP8 KV cache, one active request, eager text-only
execution, and disabled FlashInfer autotuning. Embedded MTP is present in
the checkpoint but not enabled. Prefix caching is enabled.

The 131,072-token configuration passed a 119,751-token synthetic recall
request; this is one capacity check, not full quality/stability validation.
Model allocation was 18.96GiB. Long-test sample: 31,546 / 32,607MiB GPU
memory used; this was not peak monitoring. Desktop workloads share VRAM.

## Current components and request flow

```text
iPhone Safari + Tailscale
    -> private HTTPS Serve route on the PC
    -> Open WebUI (127.0.0.1:8080, user login)
         -> application database: accounts, chats, folders, settings
         -> authenticated request to vLLM (127.0.0.1:8000/v1)
              -> Qwen weights + GPU execution
         <- streamed reasoning/answer
    <- browser display and saved conversation
```

Local browser access is http://127.0.0.1:8080. Private remote URL is
https://ello-lin.tailad2999.ts.net. Tailscale Serve uses the foreground
command without `--bg`. The last configuration check confirmed that route;
an explicit iPhone/cellular acceptance test remains open. No public Funnel
or home-router port forwarding is part of this design.

Open WebUI 0.12.2 runs in separate `.venv-webui` using Python 3.11.16 and
CPU-only torch 2.14.1. It connects to vLLM server-side, so the phone does not
need the model API key. CPU-only UI dependencies preserve inference VRAM.

### Local listeners

| Address | Component | Reachable from |
|---|---|---|
| `127.0.0.1:8000` | vLLM (OpenAI-compatible API, shared key) | This PC only |
| `127.0.0.1:8080` | Open WebUI | This PC; tailnet via Serve :443 while sharing runs |
| `127.0.0.1:8100` | Kong AI Gateway proxy (Docker, host network) | This PC only |
| `127.0.0.1:8787` | pLLM Control | This PC; tailnet owner via Serve :8443 |

The control app detects Qwen by an open `:8000`. Nothing else may use that
port.

## Kong AI Gateway (Konnect-managed)

Added 2026-11-15 to 2026-11-16; details in KONG.md and SETUP_LOG.md §22.
Kong is an optional OpenAI-compatible front door that can add per-client
keys, ACLs, rate limits, and usage analytics in front of the single-key vLLM
server.

```text
Local OpenAI-compatible client (this PC)
    -> Kong data plane, Docker host network, 127.0.0.1:8100/v1
         adds Authorization: Bearer <vLLM key> from container env PLLM_VLLM_AUTH
    -> vLLM 127.0.0.1:8000/v1/chat/completions -> Qwen
Kong data plane --outbound only--> Kong Konnect (EU): config sync, usage stats
```

- **Control plane.** Konnect is hosted by Kong. It stores the AI gateway
  `ello-ai-gateway`, the provider `ello-lin-vllm`, and the model
  `qwen3.8-27b`. This is the owner-approved exception to local-only
  operation: configuration and analytics only. Prompts and replies stay on
  the PC.
- **Trust boundary.** Konnect account access can change routing (for
  example, the upstream URL or policies), but cannot open Kong's listener.
  The listener is set by container environment on the PC. Protect the
  Konnect login with two-factor authentication.
- **Secrets.** The vLLM key reaches Kong through a container environment
  variable, referenced from Konnect as `{vault://env/pllm-vllm-auth}`. The
  data-plane certificate lives in `~/kong-ai/`.
- **Current use.** Open WebUI still calls vLLM directly. Routing it through
  Kong is the planned next step: the base URL becomes `:8100/v1`, with a
  manual model ID, because Kong does not serve `/v1/models`.
- **Lifecycle.** Kong runs as a Docker container that pLLM Control does
  not manage. Its restart policy, and therefore its boot behavior, is still
  to be checked against the off-by-default boot preference.

### Identity along the request path

Every hop terminates the previous connection and opens a new one, so device
identity does not travel down the chain:

| Hop | What it can identify |
|---|---|
| Tailscale Serve | The tailnet user and device connecting to the PC |
| Open WebUI | The logged-in Open WebUI account; this login is the user check for chat |
| Kong (or vLLM directly) | Only Open WebUI: source `127.0.0.1` and one shared key for all users and devices |

Open WebUI can forward `X-OpenWebUI-User-*` and `-Chat-Id` headers when
`ENABLE_FORWARD_USER_INFO_HEADERS=true`, optionally signed as a JWT. This
identifies the Open WebUI user, not the device. Per-device identity in Kong
requires devices to call Kong directly with their own consumer keys.
Anyone who gets a device onto the owner's tailnet faces Open WebUI's
password for chat. Other tailnet-reachable services need the same review
(TASKS.md → Security hardening).

## What Open WebUI adds around the model

Yes: it is an application layer around the model server. It stores chats,
selects messages/instructions for requests, exposes model parameters,
formats streamed output, manages user accounts, and can orchestrate tools
and retrieval when configured. It does not retrain Qwen as you chat.

Its many settings come from several separate jobs:

| Setting area | What it controls |
|---|---|
| Generation | Parameters sent to vLLM/model, e.g. output limit, temperature, reasoning effort |
| Conversation/project | Saved chats, selected history, folder instructions, attachments |
| Application | Appearance, accounts, permissions, storage, connection selection |
| Optional orchestration | Retrieval, memory, web search, tools, title/tag/follow-up requests |

Some controls change the prompt, some change inference parameters, and
others only affect the application. Exposing a setting does not establish
that every connected model/runtime supports it. Additional UI generation
jobs call the same model and can consume capacity/queue user requests.

Current evaluation: the owner finds the interface feature-heavy. Keep it
replaceable, avoid adding features for now, and decide whether simplifying
this client or choosing a lighter existing client fits daily use better.
No replacement application has been selected or implemented.

## Where projects, chats, and memories live

The launcher sets DATA_DIR to:

`/home/olleryden/Projects/pLLM/.data/open-webui/`

| Data | Current local storage |
|---|---|
| Accounts, chat history, app settings | `webui.db` (SQLite) |
| Project/folder metadata and chat membership | `folder` / `chat` records in `webui.db` |
| Saved memory entries, if enabled | `memory` records in `webui.db`; memory lookup can also use a vector index |
| Uploaded attachments | `uploads/` plus file records in the database |
| Document/memory search indexes, if configured | `vector_db/` in this default installation |
| Transient caches | `cache/` |
| Model weights | Separate `models/Qwen3.8-27B-NVFP4-NVIDIA/` |
| Model API key and app signing secret | Separate ignored `.secrets/` |
| Kong gateway configuration (provider, model, future consumers) | Kong Konnect (hosted, EU), not on the PC |
| Kong data-plane certificate/key | `~/kong-ai/` (outside the repository) |

A WebUI “project” is a logical folder grouping chats, with optional default
model, instructions, and attached knowledge. It is not automatically a real
filesystem directory with that project name, a mounted code repository,
or a newly trained model. The same account on phone/desktop sees the
server-stored state. Browser caches/session state also exist, but the PC
application database is the durable record in this setup.

Chat history is not the same as long-term memory. The application chooses
what history, instructions, and retrieved material to include in a request;
Qwen only processes what it receives. Putting chats in the same folder does
not automatically load all sibling conversations into every request.

At wrap-up there are two saved chats and one account, but no folders,
knowledge collections, or memory records. Memory and web search are disabled.
The built-in memory schema is user-linked and can have paths/types; project
memory isolation is not configured or proven. Do not assume folder membership
alone creates a separate memory bank.

These local data directories are Git-ignored. Updating the repository does
not back up conversations. For a complete move/backup, preserve the data
folder (including uploads/indexes) and application secret, not just weights
or a chat export. Use a consistent backup while the UI is stopped, or the
supported database backup process; copying only a live SQLite main file can
miss WAL writes. A backup/restore procedure is still to be implemented and tested.
Changing the inference engine does not migrate app data; changing the UI
requires explicit history/memory export/import planning.

## Optional features still pending

Document ingestion/retrieval, embeddings, live file tools, durable memory,
web search, project edits/terminal actions, user-triggered tasks, and coding
client integration are not implemented. Offline mode currently prevents
embedding/voice downloads; a missing cached embedding model is logged but
chat works. No personal folders/cloud accounts were connected automatically.

A future tool runner executes model-requested actions and sends results back
to Qwen. Define tool scopes and permissions per client. A coding client
pointed directly at vLLM does not inherit WebUI history, projects, or memory.

## Lifecycle and performance

The local pLLM Control app at `127.0.0.1:8787` supervises explicit model,
chat UI, foreground Serve, and optional workspace-shell instances. It is
separate from the chat UI. Optional private HTTPS :8443 exposes the control
app separately from the :443 chat route; it does not depend on chat sharing.
Its Python-standard-library HTTP backend launches the existing scripts in
process groups with pseudo-terminals; the buildless frontend shows status,
health-based readiness, bounded output, and optional line input. No model
starts merely because the control app opens.

`scripts/start-control.sh` starts a detached manager or reopens the existing
one. Browser close leaves it running. Explicit quit with active instances
requires confirmation to stop them; normal manager shutdown cleans up its
owned process groups. Externally started instances are observed, not adopted
or killed. Sharing retains the original foreground Serve command and can
request sudo authentication inside its optional terminal.

The backend binds only to loopback and checks host, origin, and a per-launch
API token. When phone controls are configured, the exact private origin is
allowed only with the configured owner's Tailscale-User-Login header from
local Serve. Authentication is checked before serving remote HTML/assets or
API responses, including terminal logs. The runtime remote.json file is 0600.
Tailscale Serve strips spoofed peer identity headers and supplies its own.
The trust boundary is the local proxy; local programs retain existing
PC-user access. No public Funnel or raw LAN control listener is configured.

Optional pllm-control.service starts only the controller. Pre-login mode
uses the owner's systemd user manager with lingering; post-login mode is
also available. A settings toggle enables/disables future controller startup
without changing current instances. Explicit desktop Quit exits normally
without crash-policy restart; phone Quit is hidden/blocked to preserve the
control link. All model/UI launches remain explicit. See PHONE_CONTROL.md.

Runtime metadata lives in ignored `.data/control/`; terminal transcripts
are bounded in memory. This is a transcript/line-input UI, not a full
terminal emulator. No extra Python packages are required.

The owner subsequently requested graceful WebUI shutdown, and :8080 was
verified closed; the model was already stopped. The owner's independent
Serve terminal was initially left alone. The owner later resolved that old
instance. Its app-managed replacement was stopped for the remote-control
upgrade. Controller startup is an explicit opt-in; model startup and sleep
behavior remain manual/unchanged. The owner activated the persistent :8443
route; controller startup and pre-login lingering are now enabled. Real
HTTPS authentication/API/terminal checks pass; reboot/iPhone tests are pending.

Active decode logs show ~20 tokens/s; owner reports 5–20s to first visible
text. Tag/follow-up generation are now false; final persisted title setting
was true despite the owner's report of disabling it. Record/reconcile next
session rather than silently change it. Compare direct streamed timings,
then graph/compilation and MTP candidates one at a time. PERFORMANCE.md
holds external comparison points, not guaranteed speed targets.

## References

- [Qwen model card](https://huggingface.co/Qwen/Qwen3.8-27B)
- [NVIDIA checkpoint](https://huggingface.co/nvidia/Qwen3.8-27B-NVFP4)
- [WebUI folders/projects](https://docs.openwebui.com/features/chat-conversations/chat-features/conversation-organization/)
- [WebUI memory](https://docs.openwebui.com/features/chat-conversations/memory/)
- [WebUI database schema](https://docs.openwebui.com/reference/database-schema/)
- [WebUI database migration/backup](https://docs.openwebui.com/tutorials/maintenance/database/)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
