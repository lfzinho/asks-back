"""One way to ask a model for schema-checked JSON: Claude (paid) or OpenRouter (free or cheap models).

Every stage that needs a model (exam setup, grading, follow-up questions, reply judging)
goes through `ask_json`. Answers are cached on disk by request, so re-runs cost nothing.
The `mock` backend never reaches this module: each stage has its own offline stand-in.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_FAST_MODEL = "claude-haiku-5-5"  # for the short follow-up and judging calls
EFFORT = "high"
# USD per million tokens for CLAUDE_MODEL (input, output, cache write 5m, cache read).
PRICES = {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3.5-super-vl:free")
REQUEST_DEADLINE_S = 120  # per attempt; a stuck provider is retried instead of waited on

CACHE_DIR = Path(os.environ.get("ASKSBACK_CACHE", Path(__file__).resolve().parent.parent / "out" / "llm-cache"))


class ModelError(Exception):
    pass


def claude_cost(usage: dict) -> float:
    """List-price cost of one Claude call, from response.usage as a dict."""
    u = {
        "input": usage.get("input_tokens") or 0,
        "output": usage.get("output_tokens") or 0,
        "cache_write": usage.get("cache_creation_input_tokens") or 0,
        "cache_read": usage.get("cache_read_input_tokens") or 0,
    }
    return sum(PRICES[k] * v for k, v in u.items()) / 1e6


def _to_openai(blocks: list[dict]) -> list[dict]:
    """Anthropic-style content blocks -> OpenAI chat content parts."""
    out = []
    for b in blocks:
        if b["type"] == "text":
            out.append({"type": "text", "text": b["text"]})
        elif b["type"] == "image":
            src = b["source"]
            out.append({"type": "image_url", "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}})
    return out


def _post(req: urllib.request.Request) -> bytes:
    """POST with a hard limit on the whole call. Socket timeouts alone are not enough: OpenRouter pads a
    slow reply with keep-alive bytes, and a stalled connection can hang for many minutes."""
    box: dict = {}

    def go():
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                box["body"] = r.read()
        except BaseException as e:  # handed to the caller below
            box["error"] = e

    t = threading.Thread(target=go, daemon=True)  # a stuck thread is abandoned, not waited on
    t.start()
    t.join(REQUEST_DEADLINE_S)
    if t.is_alive():
        raise TimeoutError(f"no answer within {REQUEST_DEADLINE_S} s")
    if "error" in box:
        raise box["error"]
    return box["body"]


def openrouter_chat(model: str, system: str, content: list[dict], schema: dict, schema_name: str,
                    retries: int = 4, reasoning: dict | None = None) -> tuple[str | None, dict, str | None, str]:
    """One chat request with JSON-schema output. Returns (text, usage, generation id, finish reason).
    A reasoning model that thinks until it runs out of tokens is asked once more with low effort."""
    out = _openrouter_once(model, system, content, schema, schema_name, retries, reasoning)
    if out[3] == "length" and reasoning is None:
        out = _openrouter_once(model, system, content, schema, schema_name, retries, {"effort": "low"})
    return out


def _openrouter_once(model, system, content, schema, schema_name, retries, reasoning):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ModelError("OPENROUTER_API_KEY is not set")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": _to_openai(content)}],
        "response_format": {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
        "max_tokens": 16000,
        "temperature": 0,
        **({"reasoning": reasoning} if reasoning else {}),
    }).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "AsksBack"}
    for attempt in range(retries + 1):
        req = urllib.request.Request(OPENROUTER_URL, data=body, headers=headers, method="POST")
        try:
            data = json.loads(_post(req))
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            daily_cap = e.code == 429 and "per-day" in detail  # waiting won't help until tomorrow
            if e.code in (429, 500, 502, 503, 504) and attempt < retries and not daily_cap:
                time.sleep(min(60, 5 * 2 ** attempt))
                continue
            raise ModelError(f"HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(5 * 2 ** attempt)
                continue
            raise ModelError(f"network error: {e}") from e
        except ValueError as e:  # not JSON (an HTML error page from a proxy, a cut-off body)
            raise ModelError(f"unreadable response: {e}") from e
    if "error" in data:  # some upstream errors come back with HTTP 200
        raise ModelError(f"provider error: {data['error']}")
    if not data.get("choices"):
        raise ModelError(f"no answer in the response: {str(data)[:200]}")
    choice = data["choices"][0]
    text = (choice.get("message") or {}).get("content")
    if isinstance(text, str):  # some models wrap JSON in a code fence despite response_format
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return text, data.get("usage") or {}, data.get("id"), choice.get("finish_reason") or ""


def claude_json(system: str | list, content: list[dict], schema: dict, *, model: str = CLAUDE_MODEL,
                effort: str = EFFORT) -> tuple[str | None, dict, str | None, list[str]]:
    """One Claude request with JSON output. Returns (JSON text or None, usage, request id, flags)."""
    import anthropic

    flags: list[str] = []
    try:
        response = anthropic.Anthropic(max_retries=4).messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APIStatusError as e:
        return None, {}, None, [f"API error {e.status_code}: {e.message}"]
    except anthropic.APIConnectionError as e:
        return None, {}, None, [f"network error: {e}"]
    usage = response.usage.to_dict()
    if response.stop_reason == "refusal":
        flags.append("model declined")
    elif response.stop_reason == "max_tokens":
        flags.append("model output was cut off")
    else:
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            flags.append("unparseable model output: no text block")
        return text, usage, response._request_id, flags
    return None, usage, response._request_id, flags


def ask_json(backend: str, system: str, content: list[dict] | str, schema: dict, name: str, *,
             fast: bool = False, cache: bool = True) -> dict:
    """Ask `backend` ("claude" or "openrouter") for JSON matching `schema`. Raises ModelError on failure.
    `fast` picks the small model for short text-only requests (follow-ups, judging)."""
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    model = (CLAUDE_FAST_MODEL if fast else CLAUDE_MODEL) if backend == "claude" else OPENROUTER_MODEL
    key = hashlib.sha256(json.dumps([backend, model, system, content, schema], sort_keys=True).encode()).hexdigest()[:24]
    path = CACHE_DIR / f"{name}-{key}.json"
    if cache and path.exists():
        return json.loads(path.read_text())

    if backend == "claude":
        text, _, _, flags = claude_json(system, content, schema, model=model, effort="low" if fast else EFFORT)
        if text is None:
            raise ModelError("; ".join(flags) or "no answer")
    elif backend == "openrouter":
        text, _, _, finish = openrouter_chat(model, system, content, schema, name)
        if not text:
            raise ModelError(f"the model returned no answer (finish reason: {finish or 'unknown'})")
    else:
        raise ModelError(f"unknown model backend {backend!r}")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ModelError(f"the model did not return JSON: {e}") from e
    if cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return data
