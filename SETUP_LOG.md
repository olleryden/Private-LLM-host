# Setup log and installer inputs

Last updated: 2026-10-16

Purpose: record the manual setup accurately enough to build an installer
after the full system works. Keep commands, results, versions, failures,
and fixes here as work proceeds. This is a working record, not yet a
validated end-to-end installation guide.

## Target

- Ubuntu desktop, RTX 5090 (32GB), 96GB RAM.
- Qwen3.8-27B, initially NVIDIA NVFP4 weights with FP8 KV cache via vLLM.
- Target 131,072 tokens total context for one active request; not yet tested.
- Manual startup by default; optional continuous operation and an
  off-by-default “Start on boot” settings toggle. Shared personal
  chat/context, coding, internet-search/task tools, private Tailscale access.
- First personal sources: selected local files, documents, and repositories.

Commands below run in a terminal on the owner's desktop. The assistant's
workspace cannot currently access the NVIDIA driver; successful results
are owner-reported. `~/Projects/pLLM` is this machine's working directory,
not a required path for the future installer.

## 1. Initial diagnostics — confirmed 2026-10-15

```bash
cd ~/Projects/pLLM
nvidia-smi
uv --version
ls -lh .venv/bin/python models/
df -h .
ss -ltnp 'sport = :8000'
```

Observed:

| Item | Result |
|---|---|
| GPU | NVIDIA GeForce RTX 5090 |
| NVIDIA driver | 595.99.02 |
| CUDA capability reported by nvidia-smi | 13.2; not a CUDA toolkit version check |
| Idle VRAM | 582MiB / 32607MiB |
| Xorg / GNOME Shell VRAM | 263MiB / 62MiB |
| uv | 0.12.5, x86_64 Linux |
| Previous environment | `.venv/bin/python` missing |
| Model directory | Empty |
| Port 8000 | No listener shown |
| Available disk | Approximately 1.4T |

The previous GNOME VRAM spikes are historical observations. A single low
reading does not establish their cause or guarantee sustained headroom.
Do not repeat disruptive live GNOME experiments; see PLAN.md's VRAM notes.
The exact current OS release, Python patch version, and uv installation
procedure have not been captured for this installation.

## 2. Fresh inference environment — confirmed 2026-10-15

Commands supplied to the owner; the resulting environment and GPU check
were confirmed by the owner:

```bash
cd ~/Projects/pLLM

uv venv --python 3.12 --managed-python .venv-nvfp4

uv pip install --python .venv-nvfp4/bin/python \
  vllm --torch-backend=auto \
  --extra-index-url https://wheels.vllm.ai/nightly
```

This creates a separate environment from the historical `.venv` and avoids
installing into conda's base environment. `.venv-nvfp4/` is ignored by Git.

Sources checked during setup:
[vLLM GPU installation](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/)
and [NVIDIA checkpoint instructions](https://huggingface.co/nvidia/Qwen3.8-27B-NVFP4).

The nightly index and automatic backend selection are moving targets.
Repeating this command later may produce different packages. An installer
must use a tested, reproducible dependency set and compatible wheel sources.

## 3. GPU execution check — passed 2026-10-15

```bash
.venv-nvfp4/bin/python - <<'PY'
import torch
import vllm

print("vLLM:", vllm.__version__)
print("PyTorch:", torch.__version__)
print("PyTorch CUDA:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())

assert torch.cuda.is_available(), "PyTorch cannot access the GPU"
print("GPU:", torch.cuda.get_device_name(0))

x = torch.randn((1024, 1024), device="cuda", dtype=torch.float16)
y = x @ x
torch.cuda.synchronize()
print("GPU matrix multiplication: passed")
PY
```

Reported output:

```text
vLLM: 0.32.0rc1.dev251+gee8c47961
PyTorch: 2.14.0+cu132
PyTorch CUDA: 13.2
CUDA available: True
GPU: NVIDIA GeForce RTX 5090
GPU matrix multiplication: passed
```

Three PyTorch warnings mentioned deprecated opaque-type APIs and `typ='value'`.
They did not prevent this check from passing. No workaround was applied.
This validates basic CUDA execution, not NVFP4 model loading or inference.

## 4. Model download — confirmed 2026-10-15

```bash
cd ~/Projects/pLLM

.venv-nvfp4/bin/python - <<'PY'
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download

repo = "nvidia/Qwen3.8-27B-NVFP4"
revision = HfApi().model_info(repo).sha
destination = Path("models/Qwen3.8-27B-NVFP4-NVIDIA")

print("Downloading revision:", revision, flush=True)
snapshot_download(
    repo_id=repo,
    revision=revision,
    local_dir=destination,
)
(destination / "download-revision.txt").write_text(revision + "\n")
print("Download complete:", destination.resolve())
PY
```

Source: [Hugging Face download guide](https://huggingface.co/docs/huggingface_hub/guides/download).
Owner confirmed `du -sh` reports `21G` and the revision file contains
`482ca0f3832238542f8f5295dde86b5f22711d80`. This confirms the downloader
completed according to the recorded script; inference validation is next.
The script resolves the current revision at each invocation; the finished
installer should use an explicitly tested revision instead.

## 5. Reproducibility evidence — pending collection

Capture on the desktop after installation (commands not yet confirmed run):

```bash
cat /etc/os-release
.venv-nvfp4/bin/python --version
uv pip freeze --python .venv-nvfp4/bin/python > requirements-nvfp4.txt
```

Keep the tested package list with the eventual installer. A freeze file
alone does not preserve nightly wheels, their download sources, driver
requirements, or model revisions. Record these before calling the setup
reproducible; verify from a fresh environment.

## 6. First model launch — startup confirmed 2026-10-15

Run in Bash on the desktop. Uses a generated local API key (never paste
the key into chat), manual foreground execution, one GPU, text-only mode,
eager execution, 32K initial context, and FP8 KV cache. Speculative decoding
is not enabled. The 90% GPU memory budget needs validation alongside the GUI.
No service installation, boot enablement, or sleep changes are performed.
The full log is written to `nvfp4-first-launch.log`.

```bash
cd ~/Projects/pLLM

.venv-nvfp4/bin/python - <<'PY'
from pathlib import Path
import secrets

directory = Path(".secrets")
directory.mkdir(mode=0o700, exist_ok=True)
directory.chmod(0o700)
key = directory / "vllm-api-key"
if not key.exists():
    with key.open("x") as handle:
        handle.write(secrets.token_urlsafe(32) + "\n")
key.chmod(0o600)
PY

export VLLM_API_KEY="$(cat .secrets/vllm-api-key)"
set -o pipefail

.venv-nvfp4/bin/vllm serve models/Qwen3.8-27B-NVFP4-NVIDIA \
  --served-model-name qwen3.8-27b \
  --host 127.0.0.1 --port 8000 \
  --tensor-parallel-size 1 \
  --max-model-len 32768 \
  --max-num-seqs 1 \
  --max-num-batched-tokens 1024 \
  --gpu-memory-utilization 0.90 \
  --kv-cache-dtype fp8_e4m3 \
  --enforce-eager \
  --language-model-only \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  2>&1 | tee nvfp4-first-launch.log
```

Source: [NVIDIA checkpoint](https://huggingface.co/nvidia/Qwen3.8-27B-NVFP4)
and [vLLM API key environment variable](https://docs.vllm.ai/en/latest/configuration/env_vars/).
The vendor multi-GPU example is adapted here for a single 5090.
Owner confirmed application startup complete on `127.0.0.1:8000` with the
intended parsed flags despite duplicated/garbled text in the pasted terminal
transcript. No need to rerun solely because of that pasted text.

| Startup observation | Result |
|---|---|
| Quantization | `modelopt_mixed`, `CutlassNvFp4LinearKernel` selected |
| Model allocation | 18.96GiB |
| Available KV cache memory | 8.75GiB |
| Reported GPU cache pool | 195,515 tokens |
| Configured request context | 32,768 tokens; max one active request |
| Prefix caching / FlashInfer autotune | Enabled by default |
| Speculative decoding | Disabled (`None`) |
| API application startup | Complete |

Startup warned that FlashInfer kernels were disabled because cubins or
compilation prerequisites were missing, but later selected FlashInfer paths
and completed startup. Do not infer that generation works or that the warning
is harmless; test a real request before choosing a dependency fix. The log
suggests `vllm download-kernels`; no repair has been run or validated.
Other messages: PyTorch deprecations, eager-mode optimization warnings,
FP8 KV scaling/accuracy warning, model sampling defaults, and a system-message
ordering/prefix-cache warning for `/v1/messages`. Test long-context quality
and coding-client behavior before accepting those paths.

The reported cache pool makes 128K a plausible next capacity test, not a
validated context limit. Authentication and generation remain unconfirmed.
Use Ctrl+C to stop. Increase toward 128K only after local inference works.

## 7. First chat request — failed 2026-10-15

Keep the server running; execute from a second desktop terminal. Reads the
local API key without printing it. Disables thinking for this short check.

```bash
cd ~/Projects/pLLM

curl --fail-with-body http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat .secrets/vllm-api-key)" \
  --data '{
    "model": "qwen3.8-27b",
    "messages": [{"role": "user", "content": "What is 2 + 2? Answer in one short sentence."}],
    "max_tokens": 256,
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

Expect HTTP success and an answer in `choices[0].message.content`. Record
any request error or engine traceback before changing packages. Separately
verify that `/v1/models` without Authorization returns HTTP 401.

### Observed failure and next diagnostics

Owner's authenticated chat request returned HTTP 500 with
`InternalServerError` / “The server had an error while processing your
request.” A subsequent unauthenticated `/v1/models` check returned curl's
`HTTP 000`, meaning no HTTP response was obtained. Server process exit or
transport failure is possible; neither API authentication nor generation
has passed. Startup success alone was insufficient.

The earlier FlashInfer warning is a possible lead, not an established
cause. No dependency repair or relaunch has yet been confirmed. Collect
from the desktop's second terminal before changing anything:

```bash
cd ~/Projects/pLLM
tail -n 160 nvfp4-first-launch.log
ss -ltnp 'sport = :8000'
nvidia-smi
```

Capture the relevant traceback and update this log with the tested fix.

## Remaining setup stages

1. Model download completed; revision recorded in §4.
2. Startup completed on loopback; test API authentication and a real response.
3. Validate 128K using actual long prompts and ordinary desktop activity;
   record context/output limits, latency, throughput, and peak VRAM.
4. Verify streaming, tool calling, and multi-turn tool results.
5. Configure launch/stop behavior, opt-in boot startup (off by default),
   restart behavior, explicit keep-awake preference, and logs.
6. Configure Tailscale/private Serve and test an external owner device.
7. Add the shared application, retrieval, memory, persistence, and backups.
8. Complete restore/reboot checks and the 24-hour acceptance test.

## Installer follow-up — requested, implementation deferred until setup works

- Start with a tested Ubuntu/RTX 5090 profile; detect unsupported hardware
  and report it clearly rather than claiming universal support.
- Check GPU/driver, disk space, ports, and dependencies before changes.
- Install pinned dependencies in an isolated environment and download the
  tested model revision; make reruns and interrupted downloads recoverable.
- Generate configuration and secrets locally; never embed owner credentials
  or personal source paths in the installer or this log.
- Provide guided device enrollment and personal-folder selection; explain
  any steps that require user interaction or elevated permissions.
- Validate each stage automatically, show useful progress/errors, and
  include service status, backup/restore, upgrade/rollback, and uninstall.
- Test installation from a clean supported system before release. Preserve
  personal files and application data unless removal is explicitly selected.

## Clarified product requirements — 2026-10-15

Owner clarified that 24/7 is an optional hosting mode. The default is manual
launch; a settings control may enable boot startup. Installer/service setup
must not enable boot startup automatically. Test both settings and deliberate
stop behavior. Support regular chat and coding with tool execution, including
internet search/page retrieval and user-triggered tasks; actual task types
and providers remain to be selected. No launch policy or tools have yet been
implemented. NVIDIA download is now confirmed in §4; startup is confirmed; request validation remains pending.

## 8. First-request diagnosis and proposed repair — 2026-10-15

Owner provided the engine traceback. FlashInfer prefill attempted to build
`batch_prefill_with_kv_cache_dtype_q_bf16_dtype_kv_e4m3...` on the first
request. `flashinfer/jit/cpp_ext.py` called `subprocess.run` for Ninja,
raising `FileNotFoundError: [Errno 2] No such file or directory: 'ninja'`.
The engine raised EngineDeadError and the API server shut down, explaining
HTTP 500 followed by HTTP 000. No memory exhaustion appears in this trace.

This establishes that Ninja was not executable on the server's PATH, not
whether a Ninja binary existed elsewhere. Calling `.venv-nvfp4/bin/vllm`
directly does not add that environment's bin directory to PATH. Future
launchers should explicitly set child-process PATH. Python patch version
is now known from traceback paths: managed CPython 3.12.14.

Proposed repair (not yet confirmed run or successful):

```bash
cd ~/Projects/pLLM
uv pip freeze --python .venv-nvfp4/bin/python > requirements-before-kernel-fix.txt
source .venv-nvfp4/bin/activate
uv pip install --python .venv-nvfp4/bin/python ninja
ninja --version
vllm download-kernels
```

[vLLM's download-kernels command](https://docs.vllm.ai/en/latest/cli/)
installs matching precompiled FlashInfer kernels. Activation makes the
environment's executable tools available to subprocesses. Preserve the
pre-change dependency list, capture downloaded package versions, and retry
the same 32K launch from the activated terminal. If kernel download fails,
record its error before trying a different installation route. The presence
of nvcc and the need for any further JIT compilation remain unverified.

Installer requirement: provision kernel dependencies explicitly and run an
actual authenticated generation during installation, not just a readiness
check. The above repair is proposed; only a successful retry can validate it.

## 9. Kernel repair retry checkpoint

Owner reports running §8's commands. Direct inspection of environment
package metadata confirms:

| Package | Installed version |
|---|---|
| ninja | 1.13.2 |
| flashinfer-python | 0.7.1 |
| flashinfer-cubin | 0.7.1 |
| flashinfer-jit-cache | 0.7.1+cu130 |

These are observed versions, not proof of a successful generated response.
The JIT cache CUDA suffix is recorded as installed; do not infer request
compatibility from metadata alone.

Saved `scripts/serve-nvfp4.sh` with the same inference arguments as §6.
It sets the environment's bin directory on PATH, checks local prerequisites,
reads the existing API key without printing it, and launches in the foreground.
Default context is 32,768 tokens. It does not configure boot startup or sleep.
Verified with `bash -n`; GPU startup/request behavior is pending retry.

Run on the desktop:

```bash
cd ~/Projects/pLLM
set -o pipefail
bash scripts/serve-nvfp4.sh 32768 2>&1 | tee nvfp4-retry.log
```

Wait for application startup complete, then run §7's chat request and the
unauthenticated `/v1/models` check from a second terminal. Preserve any new
traceback. Do not increase context until generation and auth checks pass.

## 10. Second request failure and runtime-path fix — 2026-10-16

Owner reports HTTP 500 again. Inspected `nvfp4-retry.log` directly:

- Prefill progressed and scheduler state shows one output token; no complete
  response was returned. The missing-Ninja failure did not recur.
- FlashInfer XQA decode module loading failed with
  `libcudart.so.12: cannot open shared object file` and the server shut down.
- The module's build.ninja selects `/home/olleryden/miniforge3/bin/nvcc`;
  `nvcc --version` confirms CUDA 12.9. PyTorch remains CUDA 13.2. The
  driver-reported CUDA capability is separate from these compiler versions.
- CUDA 12 runtime already exists at
  `/home/olleryden/miniforge3/targets/x86_64-linux/lib/libcudart.so.12`.
- Autotuning logged temporary allocation failures and fallback tactics;
  another allocation warning appeared during the request. The final fatal
  traceback is the missing runtime library, not a CUDA OOM exception.

Updated `scripts/serve-nvfp4.sh` to discover the selected CUDA toolkit from
CUDA_HOME/CUDA_PATH or nvcc on PATH, and add its runtime directory to the
server's LD_LIBRARY_PATH. This changes only the launched process environment,
not system configuration. Also added
`--kernel-config '{"enable_flashinfer_autotune":false}'` to avoid autotune
scratch-memory spikes during initial validation. Context and GPU memory
budget remain 32K and 0.90 for this controlled retry.

Validation: `bash -n` passed. Running `ldd` on the failing XQA module with
the toolkit's targets library directory on LD_LIBRARY_PATH resolves
libcudart.so.12 and shows no missing dependencies. This verifies library
resolution only; mixed runtime behavior and actual generation remain untested.
No new packages were installed for this change. Clean installer work should
explicitly select compatible compiler/runtime paths instead of inheriting
an arbitrary conda setup.

Retry on desktop:

```bash
cd ~/Projects/pLLM
set -o pipefail
bash scripts/serve-nvfp4.sh 32768 2>&1 | tee nvfp4-retry2.log
```

Then rerun §7's authenticated chat request and the unauthenticated models
check. Mark the repair successful only after a valid generated response.

## 11. Repaired 32K generation and authentication — passed 2026-10-16

Owner supplied `nvfp4-retry2.log` startup output for API PID 88830 / engine
PID 89059. It confirms `enable_flashinfer_autotune=False`, explicit skipping
of autotuning, model allocation 18.96GiB, available KV cache 8.65GiB and a
reported 193,331-token pool. Application startup completed at 00:10:23.
No allocator OOM appears in this supplied startup output.

Created `scripts/check-nvfp4.py` to check no-key rejection and submit the
short arithmetic request using the existing local key. An initial sandboxed
HTTP attempt was denied by the tool environment (Operation not permitted).
Running the check with local network access outside that sandbox succeeded:

```text
Without key: HTTP 401
Chat: HTTP 200
Answer: 2 + 2 = **4**
Finish reason: stop
prompt_tokens: 20
completion_tokens: 9
total_tokens: 29
reasoning_tokens: 0
```

This validates the runtime-path/kernel repair for actual short generation
and no-key API rejection. It does not validate tool calling, streaming,
long-context quality, throughput, or clean installation. The selected
checkpoint and runtime versions remain those recorded above.

Next proposed desktop steps (128K not yet validated):

1. Stop the current foreground server with Ctrl+C and wait for shutdown.
2. Start the same configuration at 131,072 total context:

   ```bash
   cd ~/Projects/pLLM
   set -o pipefail
   bash scripts/serve-nvfp4.sh 131072 2>&1 | tee nvfp4-128k.log
   ```

3. After startup, from a second terminal run:

   ```bash
   cd ~/Projects/pLLM
   .venv-nvfp4/bin/python scripts/check-nvfp4.py
   ```

4. Validate real long prompts with token accounting, reserved output space,
   source-recall checks, latency, and observed GPU memory. Starting with a
   128K flag or repeating the short check does not complete this validation.

## 12. Over-100K input test — passed 2026-10-16

Inspected `nvfp4-128k.log`: active context 131,072 tokens, KV memory
8.66GiB, reported cache capacity 254,942 tokens, and application startup
complete. Owner also supplied successful short chat and 401 checks.

Added `scripts/check-long-context.py`. It generates synthetic records with
fresh random lookup values near the start, middle, and end; sizes the
prompt through the running server's `/tokenize` endpoint using the same
chat template options; then requests a streamed JSON answer with thinking
disabled, temperature 0, and a 512-token output cap. This tests raw prompt
processing and recall; it does not use document retrieval or personal data.
Verified the request directly against the local API with network access
outside the tool sandbox:

```bash
.venv-nvfp4/bin/python scripts/check-long-context.py --target-tokens 120000
```

| Measurement | Observed result |
|---|---|
| Prepared prompt | 119,751 tokens (server tokenizer and generation usage agree) |
| Completion | 86 tokens; reasoning tokens 0 |
| Total context used | 119,837 tokens |
| Recall | Exact matches for all three values at start/middle/end |
| Finish reason | stop |
| First non-empty answer content | 38.4523 seconds after request submission |
| Full streamed response | 42.6522 seconds |
| GPU sample during processing | 31,546MiB / 32,607MiB; 100% utilization; 60°C |
| Test verdict | passed |

Structured result: [JSON artifact](./results/nvfp4-context-120000-1792102613599167162.json).
The script saves each run under `results/` with a unique name. A GPU sample
is not peak-memory monitoring; remaining headroom and normal desktop
behavior still require observation. The first-content timing includes
request processing/prefill, not just token decoding. This is one synthetic
recall test, not a broad quality or throughput benchmark. It does not prove
the exact 131,072-token boundary or sustained reliability.

Current verified launch: NVIDIA revision
`482ca0f3832238542f8f5295dde86b5f22711d80`, vLLM
`0.32.0rc1.dev251+gee8c47961`, PyTorch `2.14.0+cu132`, FP8 KV,
eager text-only execution, autotune disabled, correct toolkit library PATH,
and one active request. This now demonstrates >100K input on the RTX 5090.
Continue with dependency capture, representative documents/code, streaming
and tool-calling behavior, and extended stability tests.

## 13. Chat UI and phone-access milestone — 2026-10-16

Owner requested browser chat first, accessible from an iPhone on Tailscale,
with other milestones deferred/placeholders. Tailscale 1.102.3 already
installed/Running/Online; node DNS `ello-lin.tailad2999.ts.net`, Serve config
empty. Docker and Podman were absent. Selected isolated Python installation:

```bash
uv venv --python 3.11 --managed-python .venv-webui
uv pip install --python .venv-webui/bin/python open-webui==0.12.2 --torch-backend=cpu
```

Verified installed Python 3.11.16, Open WebUI 0.12.2, torch 2.14.1+cpu,
`torch.version.cuda=None`. Captured requirements-webui.txt. A sandboxed
`uv pip freeze` initially failed because uv's global cache was read-only;
retried successfully with `uv --cache-dir /tmp/pllm-uv-cache pip freeze
--python .venv-webui/bin/python > requirements-webui.txt`.

Added scripts/serve-webui.sh: loopback:8080, server-side local compatible
API/key, generated persistent application secret, ignored persistent data,
UI login enabled, further signup disabled while permitting first-admin
bootstrap, CPU isolation, and offline mode for deferred embeddings/voice.
Search, memory, and code execution defaults disabled. No custom UI or
personal-data integrations created. Manual start used:

```bash
PLLM_WEBUI_URL=https://ello-lin.tailad2999.ts.net bash scripts/serve-webui.sh > webui.log 2>&1
```

Local checks passed: `/` and `/health` HTTP 200; `/api/models` without a UI
login HTTP 401. Offline startup logged the absence of cached default
embedding weights; this is not a chat readiness failure. Retrieval remains
unconfigured. No browser chat through an owner account has yet been tested.

Attempted foreground private sharing:

```bash
tailscale serve --https=443 http://127.0.0.1:8080
```

Tailscale reports Serve not enabled on the tailnet and provides an owner
account enablement URL. Awaiting that account action; route/HTTPS/iPhone
chat remain unverified. No `--bg` or boot enablement was used. PHONE_CHAT.md
contains local bootstrap, restart, shutdown, iPhone Safari/Tailscale, and
cellular-network verification instructions. Owner must choose their UI
password locally; no credentials have been requested in chat.

## 14. Tailscale account enabled; local privilege step pending — 2026-10-16

Owner confirmed Serve enabled in their Tailscale account. Resuming the
pending command reported account success but local `serve config denied`.
`tailscale serve status --json` returned `{}`. Attempted
`sudo -n tailscale serve --https=443 http://127.0.0.1:8080`; sudo requires a
password, so no route was started. This is an OS privilege requirement,
not an automatic tool-approval rejection. No broader operator privilege
was granted and no persistent/background route was enabled.

Next owner terminal action:

```bash
sudo tailscale serve --https=443 http://127.0.0.1:8080
```

Owner enters their Ubuntu password locally, keeps this foreground command
running, and tests the printed private URL from iPhone. Route and phone
validation remain pending; account-level enablement is complete.

## 15. Chat latency investigation — 2026-10-16

Owner reports 5–20 seconds before any visible reasoning/answer for a short
new chat. Inspected recent `nvfp4-128k.log`, `webui.log`, source, and only
configuration/timing metadata in the UI database; no message content was
printed or changed.

Observed:

- Active decoding windows generally ~19.7–20 tokens/s; these are server
  interval averages, not end-to-end per-request throughput measurements.
- Multiple windows have Running=1, Waiting=1. Launcher has max_num_seqs=1.
- Persisted `task.title.enable`, `task.tags.enable`, and
  `task.follow_up.enable` are true; `task.model.params` is empty.
  Autocomplete is already false.
- Recent chat parameter dictionaries have no reasoning-effort override.
- Qwen's documented default is thinking on with xhigh reasoning effort.
- UI source consumes streamed `reasoning`, `reasoning_content`, and
  `thinking` deltas, so absence of all reasoning-field support is not an
  established cause.
- A direct streaming comparison (thinking off / low / default, same short
  synthetic question, max 128 output tokens) could not connect to :8000.
  Independent listener check was empty; GPU sample 832MiB used. No timing
  result or latency improvement was obtained from that attempt.

Likely contributors: additional UI generation jobs can queue behind user
requests or occupy the only active sequence before the next turn; high
reasoning effort increases work before the final answer. Queue association
with specific UI jobs and precise first-token attribution remain unproven.
The 128K cap itself does not mean every short chat sends 128K input tokens.
No setting changes, process restarts, or new packages were performed.

Next practical trial: disable Follow-up / Chat Title / Tag Generation in
Admin Settings → Interface; leave autocomplete off. Then manually restart
the model as needed and measure stream timings with thinking off, low,
and default. Compare direct API and UI. Preserve separate deep-reasoning
choice rather than silently changing the behavior of all chats.

Sources: [Open WebUI performance guidance](https://docs.openwebui.com/troubleshooting/performance/),
[task models](https://docs.openwebui.com/features/administration/task-models/),
and [Qwen reasoning controls](https://huggingface.co/Qwen/Qwen3.8-27B).

## 16. External performance research — 2026-10-16

Owner confirmed disabling automatic UI title/tag/follow-up generation.
Researched first-hand single-RTX-5090 Qwen3.8-27B measurements, excluding
laptop/dual-card/aggregate numbers from the primary comparison. Sources,
methods, specific rates, and limitations are in PERFORMANCE.md. Reports
use different weight exports and runtime versions; none establishes a
matched benchmark of our exact NVIDIA revision and vLLM build.

Local inspection confirms eager execution disables compilation/graphs;
MTP is off, but model config declares one MTP layer and the safetensors
index includes 15 MTP tensor entries. No full quantization configuration or
personal chat contents are retained in the research note. Candidate test
order is direct measured baseline, graph/compilation trial, then isolated
MTP trial with long-context revalidation. No engine/model changes performed.

## 17. End-of-session handoff and data ownership — 2026-10-16

Owner requested wrapping up and keeping documentation current. Rewrote
PLAN.md, TASKS.md, and ARCHITECTURE.md as concise current references,
retaining this detailed command/failure history. Updated README.md,
PHONE_CHAT.md, PERFORMANCE.md, and persistent project preferences.

Read-only final checks:

- Foreground Tailscale Serve config confirms HTTPS :443 on
  ello-lin.tailad2999.ts.net proxies to http://127.0.0.1:8080.
- UI :8080 is listening; no model :8000 listener. Do not claim current
  inference availability just because previous tests passed.
- UI DB has one account/two chats and zero folder/memory/knowledge records.
  Only counts/configuration/schema were inspected, not chat contents.
- Stored tags=false, follow-ups=false, title=true. Owner reported disabling
  all three; record the discrepancy for next time, without overriding it.
- Memories=false and web search=false. No project memory isolation or
  source ingestion has been configured.

Explained application boundaries/storage in ARCHITECTURE.md: Open WebUI
is a replaceable application around the vLLM API, with settings for request
parameters, prompt/context construction, persistence, UI, permissions, and
optional tools. A project is folder metadata/grouping in SQLite, not a new
trained model or automatic disk-folder/repository access. Memory is stored
separately from chat history and currently disabled. Actual DATA_DIR is
`.data/open-webui/`; webui.db holds chats/settings/folders, uploads/ holds
attachments, vector_db/ holds indexes if used, and .secrets/ holds local
keys. These paths are Git-ignored and need their own consistent backup.

Owner feedback: UI feels bloated; keep client selection open. Next session
should measure latency, test graph/compilation and later MTP in isolated
trials, and decide the client direction before adding features or building
the installer. No runtime/settings changes, new benchmarks, migrations,
or service shutdown/startup were performed during this wrap-up.

## 18. Subsequent WebUI shutdown and local instance-control app — 2026-10-16

After the wrap-up, the owner asked how to stop WebUI because it had no
visible desktop terminal. Direct host inspection confirmed `open-webui`
PID 92671 listening on :8080. SIGTERM was sent to that confirmed process;
the next socket check showed no :8080 listener. Saved app data was retained.
The owner's separate foreground Tailscale Serve session was not stopped.

The owner then requested one minimal application for instance status,
Start/Stop, and optional terminal output/input, instead of multiple desktop
terminals. Implemented pLLM Control:

- `control/server.py`: Python 3.12 standard-library HTTP/PTY supervisor,
  loopback :8787, no newly installed dependencies. Instance definitions
  reuse existing model and WebUI scripts, foreground sudo Serve, and an
  optional manual workspace shell. Model context defaults to 131072 with
  a 32768 option. Inference flags and WebUI settings were not changed.
- `control/web/`: buildless HTML/CSS/JS with instance states and explicit
  controls. Terminal transcript and line input are collapsed initially.
  Password masking, Ctrl+C, and Ctrl+D are supported; full-screen terminal
  applications require a normal terminal.
- Health-gated model/UI readiness, bounded in-memory Unicode transcripts,
  explicit graceful stops with bounded escalation, and Linux PTY-session
  cleanup for shell jobs in separate process groups. External listeners and
  the existing Serve session are reported without adoption/termination.
- Local Host/Origin checks, per-launch API token, no CORS, and framing/CSP
  headers. Metadata `.data/control/server.json` and manager logs are private
  (0600) within an ignored 0700 directory. Input is not copied to disk logs;
  normal terminal echo still appears in the live transcript.
- `control/launcher.py` and `scripts/start-control.sh`: detached launch,
  reopen existing app, status, and explicit shutdown. No boot integration,
  system sleep changes, model startup, or UI startup on opening the app.
- `pLLM Control.desktop`: validated desktop entry for this checkout, copied
  to `~/.local/share/applications/pllm-control.desktop`. This provides an
  Applications menu entry, not a login/boot service. Its absolute paths must
  be regenerated for another installation path.
- Model subprocess PATH detects the existing `~/miniforge3/bin/nvcc` if a
  desktop launch lacks it, retaining the existing script's CUDA-runtime fix.

Launch and lifecycle commands:

```bash
cd ~/Projects/pLLM
bash scripts/start-control.sh
# Opens http://127.0.0.1:8787; no terminal needs to remain open.

bash scripts/start-control.sh --status
bash scripts/start-control.sh --stop
# Explicitly stop all manager-owned instances and quit:
bash scripts/start-control.sh --stop-all
```

For this session's verification, the app was launched with `--no-open`.
After a backend update, it was stopped/reopened with no managed instances
running. The existing external Serve session was retained. A live API check
started only the workspace shell, waited for readiness, sent a harmless
`printf`, verified its exact output, and gracefully stopped the shell.
Qwen and Open WebUI were not started during implementation/testing.

Automated checks:

```bash
/usr/bin/python3 -m unittest discover -s tests -v
gjs -c 'const B=imports.byteArray; const G=imports.gi.GLib; new Function(B.toString(G.file_get_contents(ARGV[0])[1])); print("JavaScript syntax OK");' control/web/app.js
desktop-file-validate 'pLLM Control.desktop'
bash -n scripts/start-control.sh
```

**21 integration tests passed** in 5.853s against the final backend. Tests
use disposable Python/bash children and loopback servers, covering no
autostart, health readiness, failed exits, duplicate starts, PTY input/output,
foreground-job Ctrl+C, graceful/escalated cleanup, orphan/job groups,
bounded/sanitized Unicode output, external-listener preservation, API
authentication/origin checks, invalid requests, and shutdown/start exclusion.

Real Firefox QA with an isolated profile passed: four service cards,
correct state/control availability, terminal expansion, context and input
focus retained during polling, and no observed JS errors/rejections. Desktop
and 500px responsive layouts showed no horizontal overflow. Firefox's
minimum viewport prevented a true 390px phone-size capture. Screenshots
remain ignored under `.data/control/`; the QA-owned browser was closed.

Owner acceptance of real model/UI startup through this app and the sudo
sharing prompt remains pending. Full boot/recovery/soak tests remain open.
See CONTROL.md; PLAN.md, TASKS.md, ARCHITECTURE.md, README.md, PHONE_CHAT.md,
and persistent INSTRUCTIONS.md were updated for this explicit scope change.

## 19. Direct desktop shortcut — 2026-10-16

Owner requested launching directly from the desktop. `xdg-user-dir DESKTOP`
returned `/home/olleryden/Desktop`. Copied the existing validated desktop
entry to `~/Desktop/pLLM Control.desktop` with executable mode 0755, without
overwriting a different file. The Applications menu entry remains available.

Attempted `gio set "$HOME/Desktop/pLLM Control.desktop" metadata::trusted true`;
GIO reported `Setting attribute metadata::trusted not supported` in this
session. If Ubuntu requires trust approval, the owner should right-click
the desktop icon, select Allow Launching once, then double-click it.
No instances were started or stopped while creating the shortcut.

## 20. External sharing without a visible terminal — 2026-10-16

Owner could not find the terminal corresponding to “Running elsewhere.”
Read-only `tailscale serve status --json` still reported the foreground
route to `http://127.0.0.1:8080`. Host process inspection found the root-owned
chain sudo 94477 → sudo 94480 → tailscale 94481, terminal pts/5. The top sudo
was reparented to user systemd PID 2678; tailscale had state `Tl+` (stopped).
There was no original desktop terminal process attached to that chain.

The dashboard detects the matching route, not the original terminal or
the external CLI process's state/uptime. Updated the frontend to say
“Detected outside app,” show unknown external uptime as a dash, and explain
that the original terminal may no longer be open. No manager restart or
service mutation is necessary; refreshing loads the new static assets.

Suggested one-time owner cleanup for these specifically observed PIDs:
send SIGCONT to 94481, then SIGINT, using sudo. These are ephemeral process
IDs, not reusable installer commands; inspect the exact command before any
future cleanup. No privileged process was signaled during this inspection.
