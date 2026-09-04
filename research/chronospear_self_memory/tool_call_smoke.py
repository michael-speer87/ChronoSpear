"""CAM-free native tool-call smoke test for an OpenAI-compatible server."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

PROMPT = 'Call the echo tool with the value "potato". Do not answer normally.'
ECHO_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "echo",
        "description": "Return the supplied value.",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class SmokeResult:
    status: str
    content: object = None
    tool_calls: object = None
    tool_calls_present: bool = False
    error_body: str | None = None


def run_smoke(base_url: str, model: str, tool_choice: str) -> SmokeResult:
    if tool_choice not in {"auto", "required"}:
        raise ValueError("tool_choice must be 'auto' or 'required'")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": [ECHO_TOOL],
        "tool_choice": tool_choice,
        "temperature": 0,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            status = getattr(response, "status", 200)
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return SmokeResult(status=f"HTTP {exc.code} {exc.reason}", error_body=body)
    except urllib.error.URLError as exc:
        return SmokeResult(status=f"CONNECTION ERROR: {exc.reason}")

    try:
        body = json.loads(raw)
        message = body["choices"][0]["message"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        return SmokeResult(status=f"INVALID RESPONSE: {exc}", error_body=raw[:1000])
    return SmokeResult(
        status=f"HTTP {status}",
        content=message.get("content"),
        tool_calls=message.get("tool_calls") if "tool_calls" in message else None,
        tool_calls_present="tool_calls" in message,
    )


def print_result(mode: str, result: SmokeResult) -> None:
    print(f"MODE: {mode}")
    print(f"HTTP/result status: {result.status}")
    print("sanitized assistant content:")
    print(json.dumps(result.content, ensure_ascii=False, indent=2))
    print("structured tool_calls payload:")
    print(json.dumps(result.tool_calls, ensure_ascii=False, indent=2))
    print(f"structured tool_calls field present={result.tool_calls_present}")
    if result.error_body is not None:
        print("response body:")
        print(result.error_body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe one native echo tool call.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--model", default="qwen3-base-v1")
    parser.add_argument("--tool-choice", choices=("auto", "required"), required=True)
    args = parser.parse_args()
    print_result(
        args.tool_choice,
        run_smoke(args.base_url, args.model, args.tool_choice),
    )


if __name__ == "__main__":
    main()
