"""mlx_lm.server (OpenAI 互換) クライアント。"""
from __future__ import annotations

import json
import os
from typing import Iterable, Iterator

import httpx

DEFAULT_BASE_URL = os.environ.get("NEBULEUSE_LLM_URL", "http://127.0.0.1:8080/v1")
DEFAULT_MODEL = os.environ.get(
    "NEBULEUSE_LLM_MODEL",
    # 設計上は Bonsai-8B (1-bit) を想定していたが、mlx-lm 0.31 系は 1-bit 量子化を未サポート。
    # 差し替え可能な前提なので、まずは動く 4-bit モデルを既定にする。
    "mlx-community/Llama-3.2-3B-Instruct-4bit",
)
DEFAULT_TIMEOUT = float(os.environ.get("NEBULEUSE_LLM_TIMEOUT", "120"))


class LLMError(RuntimeError):
    pass


def _payload(messages: list[dict], *, stream: bool, max_tokens: int, temperature: float) -> dict:
    return {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
        # mlx-lm 拡張: 小型モデルの反復ループ抑制
        "repetition_penalty": 1.15,
    }


def chat(
    messages: list[dict],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    """非ストリーミング（テスト用）。"""
    try:
        r = httpx.post(
            f"{base_url}/chat/completions",
            json=_payload(messages, stream=False, max_tokens=max_tokens, temperature=temperature),
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LLMError(f"LLM request failed: {e}") from e
    data = r.json()
    return data["choices"][0]["message"]["content"]


def chat_stream(
    messages: list[dict],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    base_url: str = DEFAULT_BASE_URL,
) -> Iterator[str]:
    """SSE ストリーミングで content delta を逐次返す。"""
    payload = _payload(messages, stream=True, max_tokens=max_tokens, temperature=temperature)
    try:
        with httpx.stream(
            "POST",
            f"{base_url}/chat/completions",
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    return
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError:
                    continue
                for choice in obj.get("choices", []):
                    delta = choice.get("delta", {}).get("content")
                    if delta:
                        yield delta
    except httpx.HTTPError as e:
        raise LLMError(f"LLM stream failed: {e}") from e


def health(base_url: str = DEFAULT_BASE_URL) -> bool:
    try:
        r = httpx.get(f"{base_url}/models", timeout=5.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False
