# Performance comparison and next tuning steps

Checked: 2026-10-16. External results below are first-hand community reports,
not independently reproduced here. Same GPU/model family does not imply the
same checkpoint, runtime, prompt, sampling, or measurement method.

## Local evidence

- RTX 5090 32GB, NVIDIA Qwen3.8-27B NVFP4 checkpoint at revision
  `482ca0f3832238542f8f5295dde86b5f22711d80`.
- vLLM `0.32.0rc1.dev251+gee8c47961`, PyTorch `2.14.0+cu132`.
- Eager execution: torch.compile and CUDA graphs disabled. Autotune off
  after scratch-memory allocation problems. Speculative decoding off.
- FP8 KV, one active sequence, 1,024-token prefill batches, configured 128K.
- Active generation windows in server logs: approximately 19.7–20 tokens/s.
  This is an interval-average observation, not a controlled decode benchmark.
- Synthetic long test: 119,751 input / 86 output tokens, first answer
  content 38.45s, complete response 42.65s, three recall values correct.
- Owner reports 5–20s to first visible text on short new UI chats. Owner
  reported disabling title/tag/follow-up jobs; the final persisted-state
  check found tags/follow-ups off but titles on. No improvement has been
  measured yet. Initial direct short-latency probe found no model server.

## Published single-desktop-5090 comparison points

| Author/report | Measured configuration | Reported generation rate | Important differences |
|---|---|---|---|
| [Murai Labs](https://github.com/Murai-Labs/qwen3.8-27b-rtx5090) | vLLM 0.27.1, NVFP4, 256/2,048-token prompts, one request | Baseline 51.5/52.5 tokens/s; MTP-3 107.6/97.3 | Different mixed-precision weights, WSL2; launch does not force eager. Their MTP configuration had an approximately 110K context ceiling. |
| [Florian Bauer](https://github.com/devbauerflorian/qwen3.8-27b-rtx5090) | vLLM 0.28.0, alternate W4A4 NVFP4, cold single-stream prompts | 1K: baseline 86.7, MTP-2 182.3 tokens/s. Actual 131,135-token prompt: baseline 71.5, MTP-2 153.7 | Smaller reported 17.1GB model allocation; graph-enabled launch. MTP results use a dedicated card and 0.965 GPU budget. Cold long-prompt first token 31.11s without MTP. |
| [Gigaxel](https://github.com/Gigaxel/qwen3.8-27b-5090-bench) | NInfer engine, MTP-3, INT8 group-64 KV, actual source-code prompts, one request | 128,000-token input: mean decode 144.2 tokens/s, mean first token 56.4s | Different engine/weight packaging and KV implementation. Five measured runs after warm-up, 512 output tokens; full prefill, no prefix reuse. |

Rates above are per-request decode figures. Excluded dual-5090 runs, laptop
5090 results, and concurrency/aggregate headlines from the main comparison.
The reported ~50–87 tokens/s non-speculative short-prompt results are above
our observed ~20; differences prevent assigning a measured speedup to any
one setting. Long-prompt first-token times in the tens of seconds also
show why configured context and actual prompt length must be distinguished.

## Major differences to investigate

1. **Eager execution:** our startup logs explicitly disable compilation and
   CUDA graphs. Compared serving scripts leave those enabled. A controlled
   graph-enabled trial on the current weights is the first backend candidate;
   its memory use must be checked without losing the required 128K capacity.
2. **Speculative decoding:** ours is off. Authors show large improvements
   with MTP on their own setups. The current local checkpoint has
   `mtp_num_hidden_layers=1` and 15 MTP tensors in its weight index, so there
   is an embedded head to investigate; actual vLLM compatibility, memory,
   acceptance, and >100K behavior are not validated.
3. **Quantization details:** the NVIDIA model uses mixed NVFP4/FP8, whereas
   some faster reports use smaller W4A4 exports. An NVFP4 label alone does
   not make checkpoints equivalent. Do not assume equal quality or change
   weights before measuring the current engine properly.
4. **Prefill batching:** ours is 1,024, chosen for memory stability. Try a
   larger batch only in a measured trial; it may help prompt processing but
   increases activation memory and is not an explanation for all decode loss.
5. **Measurement and UI:** baseline with direct streamed requests, no queue,
   fixed actual prompt/output token counts, warm and cold runs, and separate
   first-reasoning/first-answer timing. Thinking changes tokens generated;
   it does not by itself explain a lower measured tokens/second rate.

## Next experiment order

Keep scripts/serve-nvfp4.sh as the verified fallback until alternatives pass.
First measure direct API latency and decode throughput with background UI
tasks disabled. Then change graph/compilation behavior on the same weights,
followed by MTP as a separate experiment. At each step repeat actual
over-100K input recall and verify remaining desktop VRAM headroom. Consider
alternate checkpoints/engines only after those comparisons. No performance
flags, weights, or running services were changed by this research.

Runtime references:
[vLLM Qwen recipe](https://github.com/vllm-project/recipes/blob/main/models/Qwen/Qwen3.8-27B.yaml),
[NVIDIA checkpoint](https://huggingface.co/nvidia/Qwen3.8-27B-NVFP4).
