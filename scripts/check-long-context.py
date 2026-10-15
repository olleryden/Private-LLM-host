"""Synthetic long-context capacity/recall check against the local vLLM API."""

import argparse
import json
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-tokens", type=int, default=120000)
    args = parser.parse_args()
    if not 1000 <= args.target_tokens <= 127000:
        parser.error("target must be between 1000 and 127000 tokens")
    root = Path(__file__).resolve().parent.parent
    key = (root / ".secrets/vllm-api-key").read_text().strip()
    base = "http://127.0.0.1:8000"
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

    def post(path, payload, timeout=120):
        return urlopen(Request(base + path, data=json.dumps(payload).encode(),
                               headers=headers), timeout=timeout)

    expected = {name: secrets.token_hex(10) for name in ("alpha", "beta", "gamma")}

    def messages(records):
        lines = [f"Record {i:06d}: warehouse item is ordinary; review status is unchanged.\n"
                 for i in range(records)]
        middle = records // 2
        text = (
            "Read the records below as data. At the end, answer the lookup question.\n"
            f"LOOKUP alpha = {expected['alpha']}\n"
            + "".join(lines[:middle])
            + f"LOOKUP beta = {expected['beta']}\n"
            + "".join(lines[middle:])
            + f"LOOKUP gamma = {expected['gamma']}\n"
            + 'Return only a JSON object with keys alpha, beta, gamma and their exact '
              'LOOKUP values from the records. Do not infer or invent any values.'
        )
        return [{"role": "user", "content": text}]

    records = max(1, args.target_tokens // 16)
    for _ in range(8):
        chat = messages(records)
        with post("/tokenize", {"model": "qwen3.8-27b", "messages": chat,
                               "chat_template_kwargs": {"enable_thinking": False}}) as response:
            count = json.load(response)["count"]
        print(f"Prepared {records} records, {count} prompt tokens", flush=True)
        if args.target_tokens - 1024 <= count <= args.target_tokens:
            break
        records = max(1, int(records * (args.target_tokens - 256) / count))
    else:
        raise ValueError("Could not size the prompt; no generation submitted")

    print("Submitting long prompt; generation may take several minutes...", flush=True)
    started = time.monotonic()
    first_content = None
    parts = []
    usage = None
    finish = None
    with post("/v1/chat/completions", {
        "model": "qwen3.8-27b", "messages": chat, "max_tokens": 512,
        "temperature": 0, "stream": True, "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }, timeout=1800) as response:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            if "error" in event:
                raise ValueError(f"Streaming error: {event['error']}")
            if event.get("usage"):
                usage = event["usage"]
            for choice in event.get("choices", []):
                content = choice.get("delta", {}).get("content")
                if content:
                    if first_content is None:
                        first_content = time.monotonic() - started
                        print(f"First answer content after {first_content:.2f}s", flush=True)
                    parts.append(content)
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
    elapsed = time.monotonic() - started
    answer = "".join(parts)
    match = re.search(r"\{.*\}", answer, flags=re.DOTALL)
    observed = None
    if match:
        try:
            observed = json.loads(match.group())
        except json.JSONDecodeError:
            pass
    recalled = {name: isinstance(observed, dict) and observed.get(name) == value
                for name, value in expected.items()}
    actual_prompt = (usage or {}).get("prompt_tokens")
    passed = (all(recalled.values()) and finish == "stop" and
              actual_prompt == count)
    result = {
        "target_tokens": args.target_tokens, "tokenized_prompt_tokens": count,
        "usage": usage, "first_content_seconds": first_content,
        "total_seconds": elapsed, "finish_reason": finish,
        "expected": expected, "answer": answer, "recall_pass": recalled,
        "passed": passed,
        "limitations": "Synthetic single-request recall test; not broad quality, peak VRAM, or soak validation.",
    }
    destination = root / "results" / f"nvfp4-context-{args.target_tokens}-{time.time_ns()}.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    print("Saved:", destination, flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HTTPError as error:
        print(f"HTTP {error.code}: {error.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except (URLError, OSError, ValueError, KeyError) as error:
        print(f"Long-context check failed: {error}", file=sys.stderr)
        sys.exit(1)
