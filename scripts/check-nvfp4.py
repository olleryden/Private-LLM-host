"""Check local API authentication and a real generated response; no key output."""

import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    base = "http://127.0.0.1:8000"
    try:
        with urlopen(base + "/v1/models", timeout=10) as response:
            print(f"FAIL: unauthenticated request returned HTTP {response.status}")
            return 1
    except HTTPError as error:
        print(f"Without key: HTTP {error.code}")
        if error.code != 401:
            return 1

    key_file = Path(__file__).resolve().parent.parent / ".secrets/vllm-api-key"
    key = key_file.read_text().strip()
    payload = {
        "model": "qwen3.8-27b",
        "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        "max_tokens": 256,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = Request(
        base + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=120) as response:
            print(f"Chat: HTTP {response.status}")
            result = json.load(response)
    except HTTPError as error:
        print(f"Chat: HTTP {error.code}")
        print(error.read().decode())
        return 1

    choice = result["choices"][0]
    content = choice["message"].get("content")
    print("Answer:", content)
    print("Finish reason:", choice.get("finish_reason"))
    print("Usage:", json.dumps(result.get("usage")))
    if not content or choice.get("finish_reason") != "stop":
        print("FAIL: no complete answer returned")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (URLError, OSError, ValueError, KeyError, IndexError) as error:
        print(f"Check failed: {error}", file=sys.stderr)
        sys.exit(1)
