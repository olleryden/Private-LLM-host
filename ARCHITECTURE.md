# Architecture — Private LLM Host

Last updated: 2026-10-16. This describes the current installation and clearly
separates unimplemented features. See SETUP_LOG.md for exact commands/fixes.

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
separate from the chat UI and is not exposed by the existing Tailscale route.
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
API token. Runtime metadata lives in ignored `.data/control/`; terminal
transcripts are bounded in memory. This is a local process-control surface,
not a remotely exposed shell or a full terminal emulator. CONTROL.md explains
launching, lifecycle, limitations, and command-line alternatives.

The owner subsequently requested graceful WebUI shutdown, and :8080 was
verified closed; the model was already stopped. The owner's independent
Serve terminal was left alone. Boot startup and keep-awake behavior remain
explicit opt-ins and are not configured by the control app.

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
